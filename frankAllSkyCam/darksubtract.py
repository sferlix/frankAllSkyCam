'''
Dark frame subtraction - the standard astrophotography fix for hot pixels
and dark current: cancels the whole per-pixel dark signal captured under
the same settings, rather than correcting a pre-calibrated list of
coordinates (see hotpixels.py). More general (also cancels diffuse dark
current that isn't an isolated red outlier), but requires a physical dark
library captured with the dome covered - see capturedarks.py.

Opt-in via directory presence: no appPath/darks/manifest.json -> load()
returns None -> applyToFile() is a no-op. A library is only valid for the
exact additional_night_params/night_mode/night_sharpness/night_contrast it
was captured under - load() checks this and refuses a stale library rather
than silently subtracting the wrong thing.

Not textbook-perfect: real dark subtraction happens on linear RAW data
before any ISP processing. This pipeline only has JPEG output, already
through a nonlinear contrast curve and lossy compression by the time it's
captured. Still expected to meaningfully cancel a localized hot-pixel
spike; less rigorous for subtle diffuse dark current.
'''

import os
import json
import numpy as np
import cv2

DARKS_DIRNAME = "darks"
MANIFEST_FILENAME = "manifest.json"


def _darks_dir(appPath):
    return os.path.join(appPath, DARKS_DIRNAME)


def darkFilename(exposure_secs):
    return "dark_%03ds.png" % round(exposure_secs)


def load(appPath, additional_night_params, night_mode, night_sharpness, night_contrast):
    '''
    Returns (exposures, frames) - exposures sorted ascending (list of
    float seconds), frames a matching list of numpy arrays (as returned by
    cv2.imread) - or None if the library is missing, empty, incomplete, or
    was captured under different night parameters than currently active.
    '''
    manifest_path = os.path.join(_darks_dir(appPath), MANIFEST_FILENAME)
    try:
        with open(manifest_path, "r") as f:
            manifest = json.load(f)
    except (FileNotFoundError, ValueError, OSError):
        return None

    current = {
        "additional_night_params": additional_night_params,
        "night_mode": night_mode,
        "night_sharpness": night_sharpness,
        "night_contrast": night_contrast,
    }
    for key, value in current.items():
        if str(manifest.get(key)) != str(value):
            print("WARNING: darks library was captured with " + key + "=" +
                  str(manifest.get(key)) + " but current setting is " +
                  str(value) + " - ignoring stale dark library")
            return None

    exposures = sorted(float(e) for e in manifest.get("exposures", []))
    if not exposures:
        return None

    frames = []
    for exp in exposures:
        path = os.path.join(_darks_dir(appPath), darkFilename(exp))
        frame = cv2.imread(path)
        if frame is None:
            print("WARNING: darks manifest references missing/unreadable file " + path)
            return None
        frames.append(frame)

    return exposures, frames


def _interpolatedDark(exposures, frames, exposure_secs):
    '''
    Linearly interpolates between the two library exposures bracketing
    exposure_secs (dark current accumulates ~linearly with time). Clamps
    to the nearest end frame rather than extrapolating past the library's
    range.
    '''
    if exposure_secs <= exposures[0]:
        return frames[0].astype(np.float32)
    if exposure_secs >= exposures[-1]:
        return frames[-1].astype(np.float32)

    for i in range(len(exposures) - 1):
        lo, hi = exposures[i], exposures[i + 1]
        if lo <= exposure_secs <= hi:
            t = (exposure_secs - lo) / (hi - lo)
            return frames[i].astype(np.float32) * (1 - t) + frames[i + 1].astype(np.float32) * t

    return frames[-1].astype(np.float32)  # unreachable given the guards above


def subtract(image, exposures, frames, exposure_secs):
    dark = _interpolatedDark(exposures, frames, exposure_secs)
    return np.clip(image.astype(np.float32) - dark, 0, 255).astype(np.uint8)


def applyToFile(jpg_file_name, appPath, exposure_secs, additional_night_params,
                 night_mode, night_sharpness, night_contrast):
    library = load(appPath, additional_night_params, night_mode, night_sharpness, night_contrast)
    if library is None:
        return False
    exposures, frames = library

    image = cv2.imread(jpg_file_name)
    if image is None:
        print("WARNING: darksubtract.applyToFile could not read " + jpg_file_name)
        return False
    if image.shape[:2] != frames[0].shape[:2]:
        print("WARNING: darks library resolution does not match this frame - skipping dark subtraction")
        return False

    corrected = subtract(image, exposures, frames, exposure_secs)
    cv2.imwrite(jpg_file_name, corrected)
    return True
