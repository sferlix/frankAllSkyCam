'''
Static hot-pixel correction.

A small fixed set of individual defective photosites is corrected at known
coordinates (camera parameters cannot remove them).

Opt-in by file: without hotpixels.json in appPath load() returns None and
applyToFile() does nothing. The coordinates belong to one physical sensor, so the file
is never shipped in defaults/; produce it per install with calibratehotpixels.py.
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
    Loads appPath/hotpixels.json (if any), corrects jpg_file_name in place and returns
    True if a correction was applied. Must run before any overlay is drawn: the
    coordinates refer to the raw captured frame.
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
    # starscalc/autoexposure/drawtext re-read the file from disk; quality 100 keeps the
    # re-encode near-lossless
    cv2.imwrite(jpg_file_name, corrected, [cv2.IMWRITE_JPEG_QUALITY, 100])
    return True
