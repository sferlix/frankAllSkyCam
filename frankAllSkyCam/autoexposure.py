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
'''

import os
import json
import cv2
from configparser import ConfigParser

from frankAllSkyCam import starscalc, fileManager

STATE_FILENAME = "autoexposure_state.json"

# sqmreader.py/config.txt both call this the (user-configurable) [sqm]
# sqmFolder key - default "sqm" matches what was previously hardcoded here.
_config = ConfigParser()
_config.read(fileManager.getConfigFileName())
SQM_FOLDER = _config.get('sqm', 'sqmFolder', fallback='sqm')


def _state_path(appPath):
    return os.path.join(appPath, SQM_FOLDER, STATE_FILENAME)


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
        roi = starscalc.roi_mask(gray, roi_percent / 100.0)
        mean_val = float(cv2.mean(gray, mask=roi)[0])

        state = {"exposure_secs": float(exposure_secs), "mean": mean_val}
        with open(_state_path(appPath), "w") as f:
            json.dump(state, f)
    except Exception as e:
        print("WARNING: autoexposure.recordExposureResult failed: " + str(e))


def getExposure(sq, esp_secs=None, appPath=None, target_mean=30.0,
                 min_exposure_secs=1.0, seed_exposure_secs=5.0):
    '''
    sq (SQM) is accepted for interface parity with exposurecalc.getExposure
    but not used here - this mode tracks the previous frame's own measured
    brightness instead of a pre-calibrated SQM curve.
    '''
    try:
        with open(_state_path(appPath), "r") as f:
            state = json.load(f)
        last_exposure = float(state["exposure_secs"])
        last_mean = float(state["mean"])
    except (FileNotFoundError, KeyError, ValueError, TypeError, OSError):
        return seed_exposure_secs

    if last_mean <= 0 or last_exposure <= 0:
        return seed_exposure_secs

    next_exposure = last_exposure * (target_mean / last_mean)

    if esp_secs is not None:
        next_exposure = min(next_exposure, esp_secs)
    next_exposure = max(next_exposure, min_exposure_secs)

    return round(next_exposure, 4)
