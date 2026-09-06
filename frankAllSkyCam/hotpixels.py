'''
Static hot-pixel correction.

A small, fixed set of sensor defects survives every camera-parameter lever
tried on frankAllSkyCam's red-dot regression (sensor mode, denoise, gain,
contrast) because they are individual defective photosites, not exposure- or
gain-driven noise - confirmed by the same pixel positions recurring across
consecutive frames under identical settings. Parameter tuning can't remove
them; only correcting the exact known coordinates can.

Opt-in via file presence: no hotpixels.json in appPath -> load() returns
None -> applyToFile() is a no-op. Coordinates are specific to one physical
sensor, so this file is never shipped in defaults/ and never shared between
installs - each camera gets its own, produced by calibratehotpixels.py.
'''

import os
import json
import numpy as np
import cv2

HOTPIXELS_FILENAME = "hotpixels.json"


def _file_path(appPath):
    return os.path.join(appPath, HOTPIXELS_FILENAME)


def load(appPath):
    '''
    Returns (width, height, coords) from appPath/hotpixels.json, or None if
    the file is missing, empty, or malformed. coords is a list of (x, y)
    int tuples in the same pixel space as the configured capture resolution.
    '''
    try:
        with open(_file_path(appPath), "r") as f:
            data = json.load(f)
        coords = [(int(x), int(y)) for x, y in data["coordinates"]]
        if not coords:
            return None
        return int(data["width"]), int(data["height"]), coords
    except (FileNotFoundError, KeyError, ValueError, TypeError, OSError):
        return None


def correctImage(image, coords, radius=2):
    '''
    Replaces each (x, y) in coords with the per-channel median of its
    surrounding (2*radius+1)^2 neighborhood, excluding the center pixel
    itself. image is a numpy array as returned by cv2.imread (H, W, C).
    '''
    out = image.copy()
    h, w = image.shape[:2]
    for x, y in coords:
        if not (0 <= x < w and 0 <= y < h):
            continue
        y0, y1 = max(0, y - radius), min(h, y + radius + 1)
        x0, x1 = max(0, x - radius), min(w, x + radius + 1)
        patch = image[y0:y1, x0:x1].reshape(-1, image.shape[2])
        idx = (y - y0) * (x1 - x0) + (x - x0)
        keep = np.ones(patch.shape[0], dtype=bool)
        keep[idx] = False
        out[y, x] = np.median(patch[keep], axis=0)
    return out


def applyToFile(jpg_file_name, appPath):
    '''
    Loads appPath/hotpixels.json (if any), corrects jpg_file_name in place,
    and returns True if a correction was applied. Must run before any
    watermark/logo/text overlay is drawn onto jpg_file_name (same
    requirement as autoexposure.recordExposureResult), since the
    coordinates are calibrated against the raw captured frame.
    '''
    calibration = load(appPath)
    if calibration is None:
        return False
    cal_width, cal_height, coords = calibration

    image = cv2.imread(jpg_file_name)
    if image is None:
        print("WARNING: hotpixels.applyToFile could not read " + jpg_file_name)
        return False

    h, w = image.shape[:2]
    if (w, h) != (cal_width, cal_height):
        print("WARNING: hotpixels.json was calibrated for " + str(cal_width) + "x" +
              str(cal_height) + " but this frame is " + str(w) + "x" + str(h) +
              " - skipping hot-pixel correction")
        return False

    corrected = correctImage(image, coords)
    # starscalc/autoexposure/drawtext all re-read this file from disk rather
    # than taking an in-memory array, so this write can't be avoided - but
    # quality 100 (vs cv2's default ~95) keeps it as close to lossless as a
    # JPEG re-encode gets, since the final watermark save re-encodes again.
    cv2.imwrite(jpg_file_name, corrected, [cv2.IMWRITE_JPEG_QUALITY, 100])
    return True
