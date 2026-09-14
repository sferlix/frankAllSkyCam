'''
  main program frankAllSkycam
  by Francesco Sferlazza, 2023
'''

import os
import sys
import csv
import fcntl
import datetime
from fractions import Fraction
import time
from zoneinfo import ZoneInfo
from importlib import resources  # Python 3.7+
from configparser import ConfigParser
from frankAllSkyCam import fileManager, drawtext, getextdata, logos, calculateEphem, sqmreader, exposurecalc, autoexposure, starscalc, hotpixels, darksubtract, weatherexport

config = ConfigParser()
configFileName = fileManager.getConfigFileName()
config.read(configFileName)
appPath = os.path.expanduser("~") + "/frankAllSkyCam/"

time_zone = str(config['site']['time_zone'])
inte = str(config['site']['inte'])

logFolder = appPath + str(config['system']['logFolder'])
outputFolder = appPath + str(config['system']['otuputFolder'])
outputLocalWebFile = str(config['system']['outputLocalWebFile'])
horiz = str(config['resolution']['horiz'])
vert = str(config['resolution']['vert'])
rotation = int(config['resolution']['picture_rotation'])
picture_rotation = str(config['resolution']['picture_rotation'])

additional_night_params = str(config['libcamera']['additional_night_params'])
additional_day_params = str(config['libcamera']['additional_day_params'])
night_mode = str(config['libcamera'].get('night_mode', '')).strip()
night_sharpness = str(config['libcamera'].get('night_sharpness', '0')).strip()
night_contrast = str(config['libcamera'].get('night_contrast', '1.0')).strip()

font_size   = int(config['font']['font_size'])
font_colorR = int(config['font']['font_colorR'])
font_colorG = int(config['font']['font_colorG'])
font_colorB = int(config['font']['font_colorB'])
font_color = [font_colorR,font_colorG,font_colorB]

top_left_x     = int(config['text_coords']['top_left_x'])
top_left_y     = int(config['text_coords']['top_left_y'])
top_right_x    = int(config['text_coords']['top_right_x'])
top_right_y    = int(config['text_coords']['top_right_y'])
bottom_left_x  = int(config['text_coords']['bottom_left_x'])
bottom_left_y  = int(config['text_coords']['bottom_left_y'])
bottom_right_x = int(config['text_coords']['bottom_right_x'])
bottom_right_y = int(config['text_coords']['bottom_right_y'])
top_center_x   = int(config['text_coords']['top_center_x'])
top_center_y   = int(config['text_coords']['top_center_y'])

text_positions = [[top_left_x,top_left_y],[top_right_x,top_right_y],[bottom_left_x,bottom_left_y],[bottom_right_x,bottom_right_y],[top_center_x,top_center_y]]

et_use         = str(config['extra_text']['et_use'])
et_data_file   = str(config['extra_text']['et_data_file'])
et_x_pos       = int(config['extra_text']['et_x_pos'])
et_y_pos       = int(config['extra_text']['et_y_pos'])
et_font_size   = int(config['extra_text']['et_font_size'])
et_font_colorR = int(config['extra_text']['et_font_colorR'])
et_font_colorG = int(config['extra_text']['et_font_colorG'])
et_font_colorB = int(config['extra_text']['et_font_colorB'])
et_font_color = [et_font_colorR,et_font_colorG,et_font_colorB]

compass_filename = str(config['compass']['compass_filename'])
compass_x_pos = int(config['compass']['compass_x_pos'])
compass_y_pos = int(config['compass']['compass_y_pos'])
compass_rot_angle = int(config['compass']['compass_rot_angle'])

logo_filename = str(config['logo']['logo_filename'])
logo_x_pos = int(config['logo']['logo_x_pos'])
logo_y_pos = int(config['logo']['logo_y_pos'])

phase_filename = str(config['moon_phase_img']['moon_filename'])
phase_x_pos = int(config['moon_phase_img']['moon_x_pos'])
phase_y_pos = int(config['moon_phase_img']['moon_y_pos'])

jupiter_x_pos = int(config['planets']['jupiter_x_pos'])
jupiter_y_pos = int(config['planets']['jupiter_y_pos'])
mars_x_pos = int(config['planets']['mars_x_pos'])
mars_y_pos = int(config['planets']['mars_y_pos'])
saturn_x_pos = int(config['planets']['saturn_x_pos'])
saturn_y_pos = int(config['planets']['saturn_y_pos'])
venus_x_pos = int(config['planets']['venus_x_pos'])
venus_y_pos = int(config['planets']['venus_y_pos'])

esp_secs = float(config['exposure']['esp_secs'])
# exposure_mode/[auto_exposure] are optional - fallback() keeps this working
# on existing config.txt files that predate this feature (no re-seeding).
exposure_mode = config.get('exposure', 'exposure_mode', fallback='sqm_based')
ae_target_mean = config.getfloat('auto_exposure', 'target_mean', fallback=30.0)
# true-night-only boosted target (see the sun_alt gate in _run() and
# autoexposure.moon_adjusted_target_mean) - falls back to ae_target_mean
# itself (i.e. no boost at all) so an existing config.txt missing this key
# keeps tonight's exposure byte-identical to before this feature existed;
# only takes effect once the key is added (defaults/config.txt ships one).
ae_target_mean_dark_sky = config.getfloat('auto_exposure', 'target_mean_dark_sky', fallback=ae_target_mean)
ae_roi_percent = config.getfloat('auto_exposure', 'roi_percent', fallback=70.0)
ae_min_exposure_secs = config.getfloat('auto_exposure', 'min_exposure_secs', fallback=1.0)
ae_seed_exposure_secs = config.getfloat('auto_exposure', 'seed_exposure_secs', fallback=5.0)
# twilight-handoff/saturation-guard settings - see autoexposure.py module
# docstring for why the crossover test replaces a fixed sun-altitude band.
ae_twilight_guard_deg = config.getfloat('auto_exposure', 'twilight_guard_deg', fallback=3.0)
# hard backstop, independent of should_use_isp()'s feedback-ratio test - see
# _run()'s twilight_isp_mode gate for why this exists (real dusk/night data,
# 2026-09-09: the ISP-harvested exposure hard-capped around 0.06s at a
# different AnalogueGain than fixed-shutter night capture uses, so
# should_use_isp()'s ratio math could never produce a raw_next above the
# floor - twilight_isp_mode stayed True from dusk through the entire night
# on two real installations). Defaults to -18 deg (astronomical twilight,
# the same boundary calculateEphem.py already uses for "true night" /
# nightStart) - past this point cloud cover can only make the sky darker,
# never brighter, so forcing the fixed-shutter floor here is always the
# safe direction; worst case is one underexposed frame the feedback loop
# corrects next cycle, versus the alternative (an unreachable exit
# condition) losing the rest of the night.
ae_twilight_isp_backstop_deg = config.getfloat('auto_exposure', 'twilight_isp_backstop_deg', fallback=18.0)
# see defaults/config.txt for why this is much lower than min_exposure_secs -
# only used between twilight_guard_deg and twilight_isp_backstop_deg.
ae_twilight_min_exposure_secs = config.getfloat('auto_exposure', 'twilight_min_exposure_secs', fallback=0.02)
ae_twilight_ev_bias = config.getfloat('auto_exposure', 'twilight_ev_bias', fallback=0.3)
ae_saturation_clip_frac_threshold = config.getfloat('auto_exposure', 'saturation_clip_frac_threshold', fallback=0.05)
ae_saturation_severity_gain = config.getfloat('auto_exposure', 'saturation_severity_gain', fallback=8.0)
use_sqm_le = config['sqm']['use_sqm_le']

isFTP = str(config['ftp']['isFTP'])=='True'
FTP_server = str(config['ftp']['FTP_server'])
FTP_login = str(config['ftp']['FTP_login'])
FTP_pass = str(config['ftp']['FTP_pass'])
FTP_uploadFolder = str(config['ftp']['FTP_uploadFolder'])
FTP_fileNameAllSkyImg = str(config['ftp']['FTP_fileNameAllSkyImgJPG'])
FTP_fileName = FTP_uploadFolder + "/" + FTP_fileNameAllSkyImg
# optional - fallback() keeps this working on existing config.txt files
# that predate this feature (no re-seeding). Defaults to disabled: an
# upgrading install with isFTP already True must not suddenly start
# uploading to an unconfigured FTP_fileNameWeatherJSON path.
weather_export_enabled = config.getboolean('weather_export', 'enabled', fallback=False)
weather_export_station_url = config.get('weather_export', 'station_url', fallback='')
FTP_fileNameWeatherJSON = config.get('ftp', 'FTP_fileNameWeatherJSON', fallback='')

tz = ZoneInfo(time_zone)
x = datetime.datetime.now(tz)

# camera-exclusive section is SQM measurement (its own test shots also drive
# libcamera-still, via sqmreader's getPseudoSQM) through the main capture -
# nothing after that (analysis, watermark, save, FTP) touches the camera, so
# it deliberately runs lock-free and may overlap the next run's camera phase.
CAMERA_LOCK_PATH = logFolder + "/camera.lock"
CAMERA_LOCK_RETRY_SECS = 5
CAMERA_LOCK_MAX_WAIT_SECS = 90  # past this, assume the other run is stuck, not just slow

# twilight-handoff ISP metadata sidecar (see autoexposure.record_isp_exposure)
# - overwritten every run, not per-capture-unique, same convention as
# sqmreader.py's own fixed sqm_temp.jpg path.
ISP_METADATA_PATH = logFolder + "/isp_metadata.json"

def _acquireCameraLock():
    fileManager.createPath(logFolder)
    fd = open(CAMERA_LOCK_PATH, "w")
    waited = 0
    while True:
       try:
          fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
          return fd
       except BlockingIOError:
          if waited >= CAMERA_LOCK_MAX_WAIT_SECS:
             print("WARNING: camera busy for " + str(waited) + "s - assuming the other run is stuck, killing the capture process")
             os.system("ps -ef|grep -E 'libcamera-still|rpicam-still' | grep -v color|awk '{print $2}'|xargs kill -9 1> /dev/null 2>&1")
             time.sleep(1)
             try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return fd
             except BlockingIOError:
                print("ERROR: still could not get the camera lock after cleanup - skipping this cycle")
                fd.close()
                return None
          print("Camera busy (another run still capturing), waiting " + str(CAMERA_LOCK_RETRY_SECS) + "s...")
          time.sleep(CAMERA_LOCK_RETRY_SECS)
          waited += CAMERA_LOCK_RETRY_SECS

def _releaseCameraLock(fd):
    if fd is not None and not fd.closed:
       try:
          fcntl.flock(fd, fcntl.LOCK_UN)
       except OSError:
          pass
       fd.close()

def _logExecutionTime(start):
    # single measurement point for the whole run (capture, analysis,
    # watermark, FTP upload) regardless of which path main() exits through -
    # appended, not overwritten, since capture.log itself is overwritten by
    # every cron invocation (crontab.py's ">") and so can't show a trend
    # across runs/nights the way this file can.
    end = datetime.datetime.now(tz)
    duration = round((end - start).total_seconds(), 1)
    print("Execution time: " + str(duration) + " secs")
    try:
       with open(logFolder + "/execution_time.log", "a") as f:
          f.write(start.isoformat() + "," + end.isoformat() + "," + str(duration) + "\n")
    except OSError as e:
       print("WARNING: could not append to execution_time.log: " + str(e))


def main():

    print("Execution started at: " +str(x))

    try:
       _run()
    finally:
       _logExecutionTime(x)


def _run():

    # createAppFolders() (fileManager.getConfigFileName, called at module
    # import time above) only provisions this on a fresh install - existing
    # installs upgrading to a version that adds a new folder never get it
    # created that way, so it's ensured here too, on every run, since
    # darksubtract.applyToFile()/capturedarks.py both need it to exist.
    fileManager.createPath(appPath + "darks")

    cameraLock = _acquireCameraLock()
    if cameraLock is None:
       print("Skipping this cycle - camera unavailable.")
       return

    data = calculateEphem.calculate(x)
    # full daytime (sun above horizon, isTimelapse False): frankAllSkyCam
    # never computes SQM at all here, hardware reading or camera-based
    # pseudo-SQM - calculateExposure() always returns 0 regardless of sqm
    # during the day, so there is nothing for a reading to drive.
    sqm, sqm_le = readsqm(daytime=not data["isTimelapse"])

    # twilight handoff (dusk and dawn share this test, no direction flag):
    # while the sun is below the horizon but the feedback loop's own honest
    # prediction is still under min_exposure_secs, the sky isn't dark enough
    # yet for a floored fixed shutter to be meaningful - let the ISP's own
    # auto-exposure keep driving capture instead (see autoexposure.py).
    # twilight_guard_deg is only a cold-start guard against stale state
    # right at the horizon crossing, not the thing sizing the handoff.
    sun_alt = data["sunAlt"]
    twilight_isp_mode = False
    exposure_min_secs = ae_min_exposure_secs
    # set alongside twilight_isp_mode below whenever this frame falls in the
    # -twilight_isp_backstop_deg..-twilight_guard_deg band: real fixed-shutter
    # capture (twilight_isp_mode=False), but still twilight-bright rather
    # than deep-night-dark, so its cloud detection needs the same NRBR
    # treatment as an ISP-driven frame - see cloud_is_isp_driven below.
    twilight_fixed_shutter_band = False
    if exposure_mode == "auto_exposure" and sun_alt < 0:
       if sun_alt >= -ae_twilight_guard_deg:
          twilight_isp_mode = True
       elif sun_alt <= -ae_twilight_isp_backstop_deg:
          # past astronomical twilight - unchanged from v47: always the
          # normal fixed-shutter floor, never the ISP.
          twilight_isp_mode = False
       else:
          # between twilight_guard_deg and twilight_isp_backstop_deg: used to
          # ask should_use_isp() here, but real dusk+dawn data (2026-09-10/11,
          # tools/twilight_shadow_probe.py) showed that deadlocks the exact
          # same way the pre-v47 bug did all night, just confined to this
          # band instead - twilight_isp_mode got stuck True for the entire
          # band (80 real minutes dusk, ~23 real minutes dawn), because an
          # ISP-driven frame's harvested exposure/mean sits at a different
          # AnalogueGain than fixed-shutter capture uses, so
          # should_use_isp()'s ratio math can never honestly conclude the
          # sky is dark enough. The shadow probe's parallel run of the
          # ordinary feedback-ratio calc (autoexposure.getExposure, no ISP
          # deferral at all) with a much lower floor tracked the real sky
          # smoothly across this exact band on both nights, so run it here
          # for real instead - see twilight_min_exposure_secs.
          twilight_isp_mode = False
          exposure_min_secs = ae_twilight_min_exposure_secs
          twilight_fixed_shutter_band = True

    # target_mean boost: only past astronomical twilight (same boundary as
    # twilight_isp_mode's own hard backstop above) - the -3..-18deg bands
    # stay on the plain ae_target_mean unchanged, so this doesn't confound
    # the v48 twilight-handoff fix currently mid-validation there (see
    # autoexposure.moon_adjusted_target_mean's docstring for why boosting
    # is safe/wanted here but not in twilight).
    #
    # dawn crossing back out of this band: the state file (autoexposure_
    # state.json) only carries exposure/mean forward, not which target
    # produced them, so the very next cycle after sun_alt crosses back above
    # -twilight_isp_backstop_deg computes raw_next off a mean that
    # converged under the (possibly boosted) true-night target against a
    # target that just dropped back to plain ae_target_mean - a one-time
    # ~(ae_target_mean/ae_target_mean_dark_sky) step, same direction/kind as
    # the saturation guard's existing (much larger) downward cuts. Downward
    # steps are deliberately uncapped in compute_raw_next - this is not the
    # v46/v48 bug (an unbounded *upward* extrapolation off a noise-floor
    # reading that fed back into should_use_isp() every cycle); it's a
    # single bounded correction that only pushes exposure down, and this
    # band no longer calls should_use_isp() at all (see the v47 comment
    # above), so there's no oscillation path back into ISP-driven capture.
    target_mean = ae_target_mean
    if exposure_mode == "auto_exposure" and sun_alt <= -ae_twilight_isp_backstop_deg:
       target_mean = autoexposure.moon_adjusted_target_mean(
          ae_target_mean, ae_target_mean_dark_sky, data.get("moonAlt"), data.get("moonIllumination"))

    exposure = calculateExposure(sqm, twilight_isp_mode, sun_alt, exposure_min_secs, target_mean)

    data["sqm"] = sqm
    data["exposure"] = exposure
    data["inte"] = inte
    data["stars"] = 0
    data["clouds"] = 0

    calculateEphem.printData(data)


    jpg_file_name = fileManager.getOutputFileName(outputFolder, x) + data["suffisso"] + ".jpg"
    print("executing capture:")

    command = fileManager.getCameraBinary() + " -n -o " + jpg_file_name
    command += " --width " + str(horiz)
    command += " --height "+ str(vert)
    # twilight-handoff frames omit --immediate so the ISP's own AGC/AWB
    # convergence loop runs before the still is taken, instead of grabbing
    # whatever the sensor's gain register happens to hold right now.
    # Confirmed on a real dawn sequence: with --immediate, ExposureTime
    # (--metadata) stayed frozen at an identical value (0.07s) across 6+
    # consecutive twilight_isp_mode captures spanning several real minutes
    # while the frame visibly brightened underneath it - the AGC's gain was
    # only advancing one small damped step per run (the sensor register
    # persisting the previous fixed-shutter capture's very different state)
    # rather than converging within a single capture. Every other mode
    # (fixed-shutter night, full daytime) keeps --immediate - neither
    # exhibits this, since neither hands off from an unrelated exposure
    # regime mid-capture the way the twilight crossover does.
    if not twilight_isp_mode:
       command += " --immediate "
    if exposure >0:
       exposure = exposure * 1000000
       command +=" --shutter " + str(int(exposure)) + " "
       command += additional_night_params
       # --denoise cdn_hq (rather than cdn_off) enables the ISP's colour-
       # denoise block - this is chrominance-only (it's the same setting
       # rpicam-still's "auto" mode already picks for stills) so it doesn't
       # touch luminance/spatial detail (i.e. star point sources), but it
       # does suppress single-pixel colour anomalies from hot/stuck
       # photosites. cdn_hq's throughput cost is irrelevant here since this is
       # a single still capture, not video/preview. Fixed regardless of
       # additional_night_params - always wins over any conflicting --denoise
       # there.
       #
       # night_mode/night_sharpness/night_contrast (config [libcamera]) are
       # tunable rather than hardcoded, each defaulting to the value already
       # in production so this is a no-op until explicitly changed:
       # - night_mode: pin a sensor readout mode, e.g. "2028:1520:12" for the
       #   imx477's true 2x2-binned full-FOV mode (real SNR gain for faint
       #   stars, but a hot photosite's signal is concentrated into one
       #   binned pixel before the ISP's defect correction sees it). Empty by
       #   default - libcamera picks a mode itself.
       # - night_sharpness/night_contrast: the ISP's daylight-tuned defaults
       #   were assumed to crush faint stars, so both were pinned down
       #   (sharpness 0, contrast 1.0) - untested against real captures.
       #   A known-good pre-regression capture on this same camera used
       #   contrast 2.5 (the ISP default, unset) with visibly fewer hot-pixel
       #   artifacts, so that assumption needs to be re-tested; defaults here
       #   keep the current (unverified) values unless overridden.
       if night_mode:
          command += " --mode " + night_mode
       command += " --denoise cdn_hq --sharpness " + night_sharpness + " --contrast " + night_contrast + " "
    else:
       if twilight_isp_mode:
          # let the ISP auto-expose this twilight frame (same as full
          # daytime) and harvest what it actually chose back via metadata,
          # to warm the feedback loop for when it does take over.
          # ISP_METADATA_PATH is a fixed, overwritten-every-run path - if
          # this capture fails/is killed before writing it, a stale file
          # from a previous run must not be read back as if it were fresh.
          try:
             os.remove(ISP_METADATA_PATH)
          except OSError:
             pass
          # deliberately does NOT use additional_day_params (--metering
          # average) here: on a fisheye, "average" factors in the bright
          # horizon ring, visible well before the zenith is at twilight,
          # pulling the ISP's target down exactly when the opposite is
          # needed. Centre-weighted metering reads the still-dark zenith
          # instead. Full daytime keeps --metering average, below - the sky
          # fills the whole frame fairly evenly by then, so this bias
          # doesn't apply and isn't reported as wrong.
          command += " --metering centre "
          command += " --metadata " + ISP_METADATA_PATH + " --metadata-format json "
          # --ev nudges the ISP's own metered target - a small, twilight-
          # only bias on top of the centre-metering fix above.
          if ae_twilight_ev_bias:
             command += " --ev " + str(ae_twilight_ev_bias)
       else:
          command += additional_day_params

    try:
       #launch the command line
       print(command)
       os.system(command)

       print("Image captured")

       # release the camera lock now - nothing from here on (analysis,
       # watermark, save, FTP upload) touches libcamera, so it must not
       # block the next scheduled run's own SQM measurement/capture
       _releaseCameraLock(cameraLock)
       cameraLock = None

       extra_text = [""]
       if et_use =="y":
          #extra_text needed
          extra_string = getextdata.getData(et_data_file)
          extra_text = [extra_string, et_font_size, et_font_color, et_x_pos, et_y_pos]

       exposure_secs = exposure / 1000000.0 if exposure > 0 else None

       # twilight-handoff frame: the ISP drove this capture, so harvest
       # what it actually chose (real exposure, not the algorithm's guess)
       # to warm the feedback loop, and use that real value for cloud
       # detection below instead of leaving exposure_secs unknown.
       harvested_exposure_secs = None
       if twilight_isp_mode:
          harvested_exposure_secs = autoexposure.record_isp_exposure(
             ISP_METADATA_PATH, jpg_file_name, appPath, roi_percent=ae_roi_percent)
          if harvested_exposure_secs is not None:
             data["exposure"] = harvested_exposure_secs

       if exposure_secs is not None:
          # dark frame subtraction (see darksubtract.py) is the primary
          # correction - no-op unless appPath/darks/manifest.json exists
          # for this install AND matches today's night params exactly.
          # Falls back to the coordinate-list correction (hotpixels.py) if
          # no valid dark library is present - cheaper to set up (no
          # physical dome-covering step) but only corrects pre-calibrated
          # coordinates rather than the whole dark-current pattern. Both
          # run before star/cloud detection and the watermark overlay, on
          # the raw captured frame still at jpg_file_name, same
          # requirement as autoexposure.recordExposureResult below.
          if not darksubtract.applyToFile(jpg_file_name, appPath, exposure_secs,
                                           additional_night_params, night_mode,
                                           night_sharpness, night_contrast):
             hotpixels.applyToFile(jpg_file_name, appPath)

       # calculate stars (night) and clouds (day or night) - a twilight-
       # handoff frame has no exposure_secs (no --shutter was used) but
       # does have the ISP's harvested real value, which is just as good
       # for exposure-normalized cloud detection
       cloud_exposure_secs = exposure_secs if exposure_secs is not None else harvested_exposure_secs

       # cloud_exposure_secs being unknown with the sun below the horizon
       # means the ISP metered this capture, not just under exposure_mode=
       # "auto_exposure": calculateExposure() returns 0 for any sq<9 SQM
       # reading regardless of exposure_mode, and that 0 routes capture
       # into the same ISP-auto (additional_day_params) branch as a real
       # twilight-handoff frame - just without the metadata harvesting,
       # since that's still gated on twilight_isp_mode above. Confirmed on
       # a real sqm_based-mode night: every dusk/dawn frame in that window
       # (exposure_mode never "auto_exposure", so twilight_isp_mode was
       # always False here) read exposure_secs=None into
       # _estimate_cloud_cover's brightness fallback, which is calibrated
       # for deep-night mean_gray (33-50) - an ISP-metered twilight frame
       # is brighter than that by construction, so it pegged at 100% cloud
       # on a clear sky, repeatably, every dusk and dawn. Widening the
       # flag (without touching the capture command / exposure_mode logic
       # above) routes these frames to the exposure-independent NRBR
       # signal instead, same as a real auto_exposure-mode handoff frame.
       #
       # twilight_fixed_shutter_band covers a related but distinct case
       # (found 2026-09-13, real dusk/dawn frames from the v48 band):
       # cloud_exposure_secs is NOT None there - it's a real, very short
       # fixed-shutter value (twilight_min_exposure_secs, ~0.02s) - so the
       # check above doesn't catch it, and it fell through to the night
       # brightness fallback same as the bug this comment describes.
       # mean_gray/exposure_secs at that exposure comes out in the
       # thousands (calibrated night range is ~0.5-7), pegging cloud cover
       # at 100% on a clear twilight sky, reproduced directly against real
       # frames (skycam_20260912_20011789236063NTL.jpg,
       # skycam_20260913_06321789273923NTL.jpg - both visibly clear, both
       # reported 100%). Originally routed to the same NRBR path as
       # twilight_isp_mode (2026-09-13 hotfix) - but NRBR is calibrated
       # against ISP-auto-white-balanced frames, and this band's real
       # fixed-shutter capture uses the *night* command's fixed
       # --awbgains (tuned for star color, not daylight balance): on real
       # frames this produced its own, milder but still real, 20-48%
       # false-positive on confirmed-clear dawn sky (2026-09-14, see
       # starscalc.py's CLOUD_TEX_REFERENCE_MEAN/twilight_fixed_shutter_band
       # texture-only path for the fix and its validation). So
       # twilight_fixed_shutter_band is now threaded through separately
       # from cloud_is_isp_driven/twilight_isp_mode instead of folded into
       # it - it needs its own signal (mean-rescaled texture), not NRBR.
       cloud_is_isp_driven = twilight_isp_mode or (cloud_exposure_secs is None and sun_alt < 0)
       print("calculating stars on: " + jpg_file_name)
       sst, scl  = starscalc.analyze_sky_robust(jpg_file_name, 0.65, 0.4, 30, exposure_secs=cloud_exposure_secs,
                                                 twilight_isp_mode=cloud_is_isp_driven,
                                                 twilight_fixed_shutter_band=twilight_fixed_shutter_band)
       data["stars"] = sst
       data["clouds"] = scl

       # runs every capture, day and night - sqm/sst are already forced to
       # 0 outside a true night capture (readsqm()'s daytime=True branch,
       # starscalc._analyze_day()), so this never actually publishes a
       # computed SQM/star count from daylight, only real zeros. cloud_cover
       # (scl) is independently valid day or night (see comment above).
       if weather_export_enabled:
          weatherexport.exportAndUpload(appPath, weather_export_station_url, sqm, sst, scl, x,
                                         data["nightStartDt"], data["nightEndDt"],
                                         isFTP, FTP_server, FTP_login, FTP_pass,
                                         FTP_uploadFolder + FTP_fileNameWeatherJSON)

       if exposure_secs is not None:
          # feed this run's own raw (pre-watermark) frame back into the
          # auto-exposure state file, regardless of which mode is active,
          # so switching to auto_exposure later doesn't start cold. Day
          # captures (exposure_secs None) aren't tracked - the ISP drives
          # exposure itself in daylight, this feedback loop doesn't apply.
          autoexposure.recordExposureResult(jpg_file_name, exposure_secs, appPath, roi_percent=ae_roi_percent)


       photo = drawtext.printWatermark(data, jpg_file_name, font_size, font_color, sqm_le, rotation, text_positions, extra_text)

       images = {
           "logo": [logo_filename != "", logo_filename, logo_x_pos, logo_y_pos, 0],
           "phase":  [phase_filename != "", phase_filename, phase_x_pos, phase_y_pos, 0],
           "compass": [compass_filename != "", compass_filename, compass_x_pos, compass_y_pos, compass_rot_angle],
           "jupiter": [data["Jupiter"], "jupiter.png", jupiter_x_pos, jupiter_y_pos, 0],
           "mars": [data["Mars"], "mars.png", mars_x_pos, mars_y_pos, 0],
           "saturn": [data["Saturn"], "saturn.png", saturn_x_pos, saturn_y_pos, 0],
           "venus": [data["Venus"], "venus.png", venus_x_pos, venus_y_pos, 0]
       }

       print(images)
       photo = logos.imagesPaste(images, photo)
       photo.save(jpg_file_name, "jpeg")

       #generate /update alive.txt to say we are still alive
       textcommand = "touch " + logFolder +  "/alive.txt"
       os.system(textcommand)

       pass
    except:
       print("ERROR: " + str(sys.exc_info()[0]))
       pass
       return
    finally:
       # safety net - no-op if already released right after capture above;
       # guarantees the lock never leaks if an error occurred before that point
       _releaseCameraLock(cameraLock)

    time.sleep(1)

    # transfer files to your local web server folder
    if outputLocalWebFile != "":
       fileManager.saveToWEB(jpg_file_name, outputLocalWebFile)

    # transfer files to your FTP server
    fileManager.saveToFTP(isFTP, jpg_file_name,FTP_server,FTP_login,FTP_pass,FTP_fileName+".jpg")

    print("AllSkyCam is done.")
    return

def readsqm(daytime=False):

   sq=0
   le =""
   try:

      sq, le  = sqmreader.readSQM(daytime=daytime)
   except Exception as e:
      # bare "except: print(...)" (no message) used to swallow the actual
      # error, and left sq=0 - indistinguishable from a genuine full-daytime
      # reading, so a night-time read failure would silently be captured
      # with additional_day_params instead of night settings. Surfacing the
      # real exception at least makes that failure diagnosable in cron logs.
      print("ERROR while calculating SQM: " + str(e))
   print("sqm = " + str(sq))
   print("sqm_le = " + str(le))
   return sq, le

def calculateExposure(sq, twilight_isp_mode=False, sun_alt=None, min_exposure_secs=None, target_mean=None):
   if min_exposure_secs is None:
      min_exposure_secs = ae_min_exposure_secs
   if target_mean is None:
      target_mean = ae_target_mean

   # pseudo-SQM/SQM reads bright ("sq<9") during any below-horizon
   # auto_exposure capture - not just the twilight_isp_mode guard band, but
   # also the fixed-shutter band between twilight_guard_deg and
   # twilight_isp_backstop_deg (see _run()) - so sq<9 alone can't mean "no
   # need to change exposure" there the way it does in full daytime. Real
   # dusk+dawn data never actually saw sq<9 that deep in the band (sq was
   # already >=9 right at the -3deg edge), but nothing guarantees that under
   # every sky/cloud condition, so this stays exposure_mode/sun_alt-driven
   # rather than relying on that coincidence.
   below_horizon_auto = exposure_mode == "auto_exposure" and sun_alt is not None and sun_alt < 0
   if sq < 9 and not below_horizon_auto:
      # no need to change the exposure.
      return 0

   # compute both predictions every time (the inactive one is cheap: pure
   # sqm math, or a JSON state-file read) so exposure_compare.csv always has
   # both sides for comparison, whichever mode is actually driving capture -
   # including during twilight_isp_mode, where auto_ex shows what the old
   # floored behavior would have forced (e.g. reads 1.0 where the bug used
   # to force it), for validating the fix on real nights. Computed even
   # when sq<9 here so a bright-twilight reading doesn't leave a silent gap
   # in the CSV right where the fix needs to be checked.
   sqm_based_ex = exposurecalc.getExposure(sq, esp_secs=esp_secs, appPath=appPath)
   auto_ex = autoexposure.getExposure(sq, esp_secs=esp_secs, appPath=appPath,
                                       target_mean=target_mean,
                                       min_exposure_secs=min_exposure_secs,
                                       seed_exposure_secs=ae_seed_exposure_secs,
                                       saturation_clip_frac_threshold=ae_saturation_clip_frac_threshold,
                                       saturation_severity_gain=ae_saturation_severity_gain)

   if sq < 9 and not below_horizon_auto:
      # full daytime only (see guard above) - sq<9 still means "no need to
      # change exposure" for capture purposes, applied_ex stays 0, but the
      # comparison row above is worth keeping.
      logExposureComparison(sq, sqm_based_ex, auto_ex, 0, twilight_isp_mode, target_mean)
      return 0

   ex = auto_ex if exposure_mode == "auto_exposure" else sqm_based_ex
   # esp_secs (config.txt) caps the exposure actually used - applied here,
   # before logging/returning, so "applied_secs" in exposure_compare.csv and
   # the caller's data["exposure"] (shown on the watermark) both reflect what
   # --shutter actually receives, not the model's raw uncapped prediction.
   # sqm_based_ex/auto_ex stay uncapped above - they're a comparison of the
   # two models' raw output, not what got applied. During twilight_isp_mode
   # the ISP drives capture instead (see _run()), so applied_ex is 0 the
   # same way full daytime's is - it's not what --shutter would have used.
   applied_ex = 0 if twilight_isp_mode else min(ex, esp_secs)

   logExposureComparison(sq, sqm_based_ex, auto_ex, applied_ex, twilight_isp_mode, target_mean)

   return applied_ex

def logExposureComparison(sq, sqm_based_ex, auto_ex, applied_ex, twilight_isp_mode=False, target_mean=None):
   # target_mean: which target actually drove auto_ex this row - without it,
   # a given auto_exposure_secs is ambiguous between "old target, darker
   # sky" and "boosted/moon-scaled target, similar sky", which is exactly
   # what validating the target_mean_dark_sky boost/moon scaling needs to
   # tell apart. Appended as a new trailing column, same pattern as
   # capture_mode's own v47 addition - the header (below) is only ever
   # written once, so an existing exposure_compare.csv keeps its old header
   # while new rows carry the extra field; already-existing 6-vs-7-field
   # parsers need to keep tolerating this.
   csv_path = logFolder + "/exposure_compare.csv"
   file_exists = os.path.exists(csv_path)
   capture_mode = "twilight_isp" if twilight_isp_mode else exposure_mode
   try:
      with open(csv_path, "a", newline="") as f:
         writer = csv.writer(f)
         if not file_exists:
            writer.writerow(["timestamp", "sqm", "exposure_mode", "capture_mode", "sqm_based_secs", "auto_exposure_secs", "applied_secs", "target_mean"])
         writer.writerow([datetime.datetime.now(tz).isoformat(), sq, exposure_mode, capture_mode, sqm_based_ex, auto_ex, applied_ex, target_mean])
   except Exception as e:
      print("WARNING: could not write exposure_compare.csv: " + str(e))


if __name__ == "__main__":
    main()

def outputDailyFolder():
   return outF

