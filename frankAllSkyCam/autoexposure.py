'''
Auto-exposure by feedback: measures the brightness of the previous capture and
adjusts the exposure toward a target mean for the next shot. Alternative to
exposurecalc.py (SQM curve); the interface mirrors exposurecalc.getExposure(sq,
esp_secs, appPath), so __main__.py picks a module with [exposure] exposure_mode.

Each capture is a fresh cron run, so the feedback (exposure, mean, clip fraction)
lives in a state file (appPath/sqm/autoexposure_state.json).

Twilight handoff (same test at dusk and dawn, see should_use_isp): if the
unclamped prediction (compute_raw_next) is below min_exposure_secs, the sky is too
bright for a floored fixed shutter, so the ISP's own auto-exposure drives the
capture and its metered result is stored via record_isp_exposure.

Saturation guard: the mean clips at 255, so a saturated frame understates how
overexposed it was. clip_frac (fraction of the ROI at or near the ceiling, see
SATURATION_CLIP_FRAC_THRESHOLD) is stored with the mean, and getExposure cuts
harder than the plain ratio when the previous frame was clipped.
'''

import os
import json
import math
import cv2
from configparser import ConfigParser

from frankAllSkyCam import starscalc, fileManager

STATE_FILENAME = "autoexposure_state.json"

# pixel value (0-255) at or above which a ROI pixel counts as clipped for clip_frac
SATURATION_CLIP_PIXEL_THRESHOLD = 250

# maximum multiplicative INCREASE per step in compute_raw_next. Decreases are not
# limited (a clipped previous frame needs a hard cut). The cap stops a near-black
# frame, whose mean is mostly sensor noise, from being extrapolated 20x or more.
MAX_EXPOSURE_STEP_FACTOR = 5.0

# the [sqm] sqmFolder key of config.txt (default "sqm")
_config = ConfigParser()
_config.read(fileManager.getConfigFileName())
SQM_FOLDER = _config.get('sqm', 'sqmFolder', fallback='sqm')


def _state_path(appPath, state_filename=STATE_FILENAME):
    return os.path.join(appPath, SQM_FOLDER, state_filename)


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


def _write_state(appPath, exposure_secs, mean_val, clip_frac, state_filename=STATE_FILENAME):
    state = {"exposure_secs": float(exposure_secs), "mean": mean_val, "clip_frac": clip_frac}
    with open(_state_path(appPath, state_filename), "w") as f:
        json.dump(state, f)


def recordExposureResult(jpg_file_name, exposure_secs, appPath, roi_percent=70, state_filename=STATE_FILENAME):
    '''
    Call right after capture, before the overlays are drawn: it measures the raw frame
    (overlays would bias the mean).
    state_filename overrides the state file (default STATE_FILENAME), so a diagnostic
    can run the same math on a separate file.
    '''
    try:
        gray = cv2.imread(jpg_file_name, cv2.IMREAD_GRAYSCALE)
        if gray is None:
            return
        mean_val, clip_frac = _measure_roi(gray, roi_percent)
        _write_state(appPath, exposure_secs, mean_val, clip_frac, state_filename)
    except Exception as e:
        print("WARNING: autoexposure.recordExposureResult failed: " + str(e))


def record_isp_exposure(metadata_file, jpg_file_name, appPath, roi_percent=70):
    '''
    Reads back the exposure the ISP chose for a capture taken without --shutter
    (libcamera-still --metadata JSON sidecar) and stores it in the same state file
    recordExposureResult writes. On failure the state is left unchanged (there is no
    fallback to exposurecalc/sqmexp.csv, which belongs to exposure_mode = sqm_based).

    Returns the exposure in seconds, or None if the metadata is missing, unparseable
    or lacks ExposureTime; callers also use it for cloud detection and the watermark.
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
    The feedback loop's prediction for the next exposure, before getExposure's clamps.
    Used by should_use_isp and getExposure. An increase over last_exposure is capped at
    MAX_EXPOSURE_STEP_FACTOR; decreases are not limited.
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


def moon_adjusted_target_mean(base_target_mean, dark_sky_target_mean, moon_alt_deg, moon_illumination):
    '''
    Target mean for true night (never used in the twilight bands): dark_sky_target_mean
    with no moon, falling toward base_target_mean as the moon gets brighter and higher
    (moonglow raises the background whatever the shutter, so a higher target would only
    add noise and clipping).

    moon_factor = max(0, sin(moon_alt_deg)) * moon_illumination.
    moon_illumination: 0 (new) to 1 (full); moon_alt_deg: degrees above the horizon.
    '''
    if moon_alt_deg is None or moon_illumination is None:
        return dark_sky_target_mean
    moon_factor = max(0.0, math.sin(math.radians(moon_alt_deg))) * max(0.0, min(1.0, moon_illumination))
    return dark_sky_target_mean + (base_target_mean - dark_sky_target_mean) * moon_factor


def should_use_isp(appPath, target_mean, min_exposure_secs,
                    saturation_clip_frac_threshold=0.05, saturation_severity_gain=8.0):
    '''
    True if the ISP should auto-expose this capture instead of a fixed shutter: the
    saturation-adjusted prediction (the same one getExposure uses) is below
    min_exposure_secs, or there is no usable prior state. The test has no direction, so
    it serves dusk and dawn alike. A frame saturated by cloud deep in the night can also
    trigger a temporary handoff; the next measurement pulls it back.
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
                 saturation_clip_frac_threshold=0.05, saturation_severity_gain=8.0,
                 state_filename=STATE_FILENAME):
    '''
    sq is ignored (interface parity with exposurecalc.getExposure). Callers check
    should_use_isp() first, so the min_exposure_secs floor is only a backstop here.
    state_filename: see recordExposureResult.
    '''
    try:
        with open(_state_path(appPath, state_filename), "r") as f:
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
