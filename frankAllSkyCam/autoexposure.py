'''
 alternative to exposurecalc.py: instead of predicting exposure from a
 pre-calibrated SQM curve, this measures the actual brightness of the
 previous capture and adjusts exposure toward a target for the next shot.

 frankAllSkyCam has no persistent process - each capture is a fresh cron
 invocation - so feedback is carried across runs via a small state file
 (appPath/sqm/autoexposure_state.json) rather than in-memory, the way a
 continuous-capture daemon would do it.

 Interface mirrors exposurecalc.getExposure(sq, esp_secs, appPath), so
 __main__.py can pick either module by config ([exposure] exposure_mode).

 Twilight handoff (dusk and dawn share this, no direction flag - see
 should_use_isp): min_exposure_secs exists to stop the feedback loop
 collapsing toward zero in genuine darkness, but applied blindly it used to
 force a false floor the instant the sun crossed the horizon, while the sky
 was still twilight-bright and genuinely needed a sub-floor exposure -
 producing a ~30x overexposed, blown-white frame every dusk/dawn. Rather
 than widen min_exposure_secs or guess a fixed sun-altitude band (which
 would have to assume a "typical" twilight brightness curve - wrong under
 real cloud cover in either direction, see should_use_isp), __main__.py now
 asks should_use_isp() before ever computing a fixed shutter: if the
 feedback loop's own honest, unclamped prediction (compute_raw_next) is
 still below the floor, the ISP's own auto-exposure drives that capture
 instead, and its real metered result is harvested via record_isp_exposure
 to keep the state file warm - so by the time the algorithm does take over,
 raw_next is already at or above the floor on its own, and the floor stops
 distorting anything.

 Saturation-severity guard: independent of the above, a previous frame that
 came back saturated (e.g. a cloud reflecting light pollution at night)
 makes the plain ratio unreliable - mean clips at 255 the same way whether
 the true overexposure was 2x or 30x over, so "target_mean/255" always
 lands on the same understated cut. clip_frac (the fraction of the ROI at
 or near the sensor ceiling) is tracked alongside mean precisely to carry
 that missing magnitude information, and getExposure uses it to cut harder
 than the plain ratio when a real previous frame was actually clipped -
 not just bright (see SATURATION_CLIP_FRAC_THRESHOLD; a bright point
 source like the Moon alone measures nowhere near this on real captures).
'''

import os
import json
import cv2
from configparser import ConfigParser

from frankAllSkyCam import starscalc, fileManager

STATE_FILENAME = "autoexposure_state.json"

# pixel value (0-255) at/above which a ROI pixel counts as "clipped" for
# clip_frac - matches the sensor's practical 8-bit ceiling region.
SATURATION_CLIP_PIXEL_THRESHOLD = 250

# max single-step multiplicative INCREASE compute_raw_next is allowed to
# request over last_exposure - growing the shutter, never shrinking it (a
# large downward step is the correct, wanted response to a genuinely
# overexposed/clipped previous frame - see the saturation-severity guard
# below, which needs to be free to cut hard). Confirmed on a real dusk
# sequence (one-minute cadence): should_use_isp() flapped True/False every
# run right at the twilight-handoff crossover - each ISP-driven run wrote
# a near-black state (exposure=0.06s, mean~1.2-1.6, real numbers from the
# capture), and the very next (fixed-shutter) run extrapolated the plain
# ratio straight off it: 0.06*(30/1.6)=1.125s and 0.06*(30/1.2)=1.5s,
# matching the two real overexposed frames (1.11s/mean 53.9 and 1.48s/mean
# 52.3) almost exactly. At that exposure/mean level the raw mean is
# dominated by sensor black-level/read noise rather than real scene
# signal, so scaling it up 19-25x amplifies that noise floor into a
# ~1.7-1.8x overshoot past target_mean - and the overexposed result then
# reads bright enough to flip should_use_isp() straight back to
# ISP-driven, repeating the cycle every single run instead of converging.
# A real, working transition (see the auto_exposure module docstring's own
# dawn-sequence numbers, Exp(s) 4.25 -> 1.01) moves by roughly 4x in one
# step - 5x leaves headroom above that while decisively blocking the
# ~19-25x blowup that caused this.
MAX_EXPOSURE_STEP_FACTOR = 5.0

# sqmreader.py/config.txt both call this the (user-configurable) [sqm]
# sqmFolder key - default "sqm" matches what was previously hardcoded here.
_config = ConfigParser()
_config.read(fileManager.getConfigFileName())
SQM_FOLDER = _config.get('sqm', 'sqmFolder', fallback='sqm')


def _state_path(appPath):
    return os.path.join(appPath, SQM_FOLDER, STATE_FILENAME)


def _measure_roi(gray, roi_percent, clip_pixel_threshold=SATURATION_CLIP_PIXEL_THRESHOLD):
    roi = starscalc.roi_mask(gray, roi_percent / 100.0)
    roi_pixel_count = cv2.countNonZero(roi)
    mean_val = float(cv2.mean(gray, mask=roi)[0])

    clip_frac = 0.0
    if roi_pixel_count > 0:
        clipped = cv2.inRange(gray, clip_pixel_threshold, 255)
        clipped = cv2.bitwise_and(clipped, roi)
        clip_frac = cv2.countNonZero(clipped) / float(roi_pixel_count)

    return mean_val, clip_frac


def _write_state(appPath, exposure_secs, mean_val, clip_frac):
    state = {"exposure_secs": float(exposure_secs), "mean": mean_val, "clip_frac": clip_frac}
    with open(_state_path(appPath), "w") as f:
        json.dump(state, f)


def recordExposureResult(jpg_file_name, exposure_secs, appPath, roi_percent=70):
    '''
    Call right after capture, before drawtext/logos touch the file - this
    measures the raw, unwatermarked frame. A file re-read on a later run
    would already carry the logo/compass/planet/text overlays, which would
    bias the mean, so the measurement never happens that way.
    '''
    try:
        gray = cv2.imread(jpg_file_name, cv2.IMREAD_GRAYSCALE)
        if gray is None:
            return
        mean_val, clip_frac = _measure_roi(gray, roi_percent)
        _write_state(appPath, exposure_secs, mean_val, clip_frac)
    except Exception as e:
        print("WARNING: autoexposure.recordExposureResult failed: " + str(e))


def record_isp_exposure(metadata_file, jpg_file_name, appPath, roi_percent=70):
    '''
    Twilight-handoff harvest: when the ISP drove this run's real capture
    (no --shutter passed, same as a full daytime frame), read back what it
    actually chose from libcamera-still's --metadata JSON sidecar and
    record it into the same state file recordExposureResult writes to -
    warms the feedback loop with a real measurement instead of the
    stale/seeded value that otherwise sits there until the algorithm takes
    over. Never falls back to exposurecalc/sqmexp.csv on failure - that
    curve is exclusive to exposure_mode = sqm_based; here, a failure just
    means this run doesn't update the state, and the previous value carries
    forward unchanged.

    Returns the harvested exposure in seconds, or None if the metadata
    file was missing/unparseable/lacked ExposureTime - callers use this to
    also feed the real exposure into cloud detection and the watermark for
    this run (see __main__.py).
    '''
    try:
        with open(metadata_file, "r") as f:
            meta = json.load(f)
        exposure_secs = float(meta["ExposureTime"]) / 1_000_000.0
        if exposure_secs <= 0:
            return None

        gray = cv2.imread(jpg_file_name, cv2.IMREAD_GRAYSCALE)
        if gray is None:
            return None
        mean_val, clip_frac = _measure_roi(gray, roi_percent)
        _write_state(appPath, exposure_secs, mean_val, clip_frac)
        return exposure_secs
    except Exception as e:
        print("WARNING: autoexposure.record_isp_exposure failed: " + str(e))
        return None


def compute_raw_next(last_exposure, last_mean, target_mean):
    '''
    The feedback loop's honest prediction for the next exposure, with none
    of getExposure's clamps applied yet. should_use_isp calls this
    directly (before any fixed-shutter capture happens at all) to decide
    whether the sky is really dark enough yet for a floored value to be
    meaningful; getExposure calls it too, as the first step of the value it
    actually returns.

    The plain ratio is capped to at most a MAX_EXPOSURE_STEP_FACTOR
    increase over last_exposure - see that constant's comment for the real
    twilight-oscillation bug this closes. Downward steps are left
    unclamped (a previous frame reading badly overexposed/clipped needs to
    be free to cut exposure hard - see the saturation-severity guard
    below). Still "raw": this is the naive-ratio step limited, not a
    smarter model, and should_use_isp/getExposure's own further
    adjustments still apply on top of it.
    '''
    if last_mean <= 0 or last_exposure <= 0:
        return None
    raw = last_exposure * (target_mean / last_mean)
    return min(raw, last_exposure * MAX_EXPOSURE_STEP_FACTOR)


def _severity_adjusted_next(raw_next, last_clip_frac, saturation_clip_frac_threshold,
                             saturation_severity_gain):
    if raw_next is None:
        return None
    if last_clip_frac >= saturation_clip_frac_threshold:
        # the previous frame was genuinely clipped, not just bright - the
        # plain ratio understates how far over target it really was, so
        # cut harder in proportion to how much of the ROI was pinned
        severity = 1.0 + last_clip_frac * saturation_severity_gain
        return raw_next / severity
    return raw_next


def should_use_isp(appPath, target_mean, min_exposure_secs,
                    saturation_clip_frac_threshold=0.05, saturation_severity_gain=8.0):
    '''
    The twilight-handoff crossover test - the same check applies verbatim
    approaching dusk and approaching dawn, since it only asks "is the sky
    honestly dark enough yet", never "which direction is the sun moving".
    True means: let the ISP's own auto-exposure drive this capture (and
    harvest its result via record_isp_exposure) rather than computing a
    fixed shutter - the feedback loop's own unclamped, saturation-adjusted
    prediction says the true need is still below min_exposure_secs, so
    forcing that floor now would just reproduce the old overexposed-frame
    bug. Also true (safest default) when there's no usable prior state yet.

    Uses the same saturation adjustment as getExposure (not just the plain
    ratio) so both callers ask the identical "what does the sky honestly
    need" question - deliberately, this means a previous frame saturated by
    something other than twilight (e.g. a cloud reflecting light pollution
    deep in the night) can also trigger a temporary ISP handoff, which is
    the physically correct call: the ISP will auto-expose the actual bright
    cloud correctly, and the next real measurement pulls things back once
    the cloud passes.
    '''
    try:
        with open(_state_path(appPath), "r") as f:
            state = json.load(f)
        last_exposure = float(state["exposure_secs"])
        last_mean = float(state["mean"])
        last_clip_frac = float(state.get("clip_frac", 0.0))
    except (FileNotFoundError, KeyError, ValueError, TypeError, OSError):
        return True

    raw_next = compute_raw_next(last_exposure, last_mean, target_mean)
    raw_next = _severity_adjusted_next(raw_next, last_clip_frac,
                                        saturation_clip_frac_threshold, saturation_severity_gain)
    return raw_next is None or raw_next < min_exposure_secs


def getExposure(sq, esp_secs=None, appPath=None, target_mean=30.0,
                 min_exposure_secs=1.0, seed_exposure_secs=5.0,
                 saturation_clip_frac_threshold=0.05, saturation_severity_gain=8.0):
    '''
    sq (SQM) is accepted for interface parity with exposurecalc.getExposure
    but not used here - this mode tracks the previous frame's own measured
    brightness instead of a pre-calibrated SQM curve.

    Callers are expected to have already checked should_use_isp() - by the
    time this runs, raw_next is expected to already be at or above
    min_exposure_secs, so that floor should rarely bind here; it stays as
    a defensive backstop, not the thing doing the real clamping.
    '''
    try:
        with open(_state_path(appPath), "r") as f:
            state = json.load(f)
        last_exposure = float(state["exposure_secs"])
        last_mean = float(state["mean"])
        last_clip_frac = float(state.get("clip_frac", 0.0))
    except (FileNotFoundError, KeyError, ValueError, TypeError, OSError):
        return seed_exposure_secs

    raw_next = compute_raw_next(last_exposure, last_mean, target_mean)
    if raw_next is None:
        return seed_exposure_secs

    raw_next = _severity_adjusted_next(raw_next, last_clip_frac,
                                        saturation_clip_frac_threshold, saturation_severity_gain)

    next_exposure = raw_next
    if esp_secs is not None:
        next_exposure = min(next_exposure, esp_secs)
    next_exposure = max(next_exposure, min_exposure_secs)

    return round(next_exposure, 4)
