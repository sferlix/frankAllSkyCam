'''
Static obstruction mask: one mask learned from recent night captures (see
generate_mask.py) and used by starscalc.py for both day and night, in place of the
per-frame obstruction heuristics.

It must be generated from night frames: night foliage is near-black against a sky
that keeps an airglow/light-pollution floor, which is what the darkness threshold
relies on. Obstruction geometry does not change with the hour, so the mask is valid
by day too.

Polarity matches starscalc._obstruction_mask: 255 = obstruction (excluded),
0 = clear sky - the opposite of roi_mask, so it drops in where
"sky[obstruction == 255] = 0" is applied.

Known limitation: the frames are read after __main__.py has burned in the logo,
compass and planet icons; an overlay element inside the analyzed ROI survives the
median stack and becomes a permanently excluded region.
'''

import os

import cv2
import numpy as np

MASK_BLUR_SIGMA = 3       # blur applied to the median stack: removes hot-pixel/noise-scale
                           # variation without blurring obstruction edges
MASK_SMOOTH_KERNEL = 15   # closes small gaps and removes small blobs in the thresholded mask
MAX_PLAUSIBLE_EXCLUDED_PCT = 60.0  # a mask excluding more than this % is rejected, at generation
                           # and at load (Otsu always finds some split, even with no obstruction)


def generate_mask(gray_images, roi):
    '''
    gray_images: 2D grayscale arrays of the same shape, all night frames.
    roi: circular ROI mask (roi_mask output, 255 = inside).
    Returns a uint8 mask of the same shape: 255 = obstruction, 0 = clear sky.
    '''
    if not gray_images:
        raise ValueError("generate_mask requires at least one image")

    stacked = np.stack(gray_images, axis=0)
    median = np.median(stacked, axis=0).astype(np.uint8)
    blurred = cv2.GaussianBlur(median, (0, 0), sigmaX=MASK_BLUR_SIGMA)

    # Otsu's threshold is computed from ROI pixels only: the black area outside the fisheye
    # circle would skew the split
    roi_values = blurred[roi == 255].reshape(-1, 1)
    otsu_thresh, _ = cv2.threshold(roi_values, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    obstruction = np.zeros_like(blurred)
    obstruction[(blurred < otsu_thresh) & (roi == 255)] = 255

    kernel = np.ones((MASK_SMOOTH_KERNEL, MASK_SMOOTH_KERNEL), np.uint8)
    obstruction = cv2.morphologyEx(obstruction, cv2.MORPH_CLOSE, kernel)
    obstruction = cv2.morphologyEx(obstruction, cv2.MORPH_OPEN, kernel)

    return obstruction


def save_mask(mask, path):
    ok = cv2.imwrite(path, mask)
    if not ok:
        raise IOError("Failed to write static mask to " + path +
                       " - cv2.imwrite returned False (e.g. missing parent "
                       "directory or unwritable path)")


def load_mask(path):
    if not os.path.isfile(path):
        return None
    return cv2.imread(path, cv2.IMREAD_GRAYSCALE)


def get_static_mask(shape, path):
    '''
    shape: (height, width) of the frame being analyzed.
    path: the generated mask (fileManager.getStaticMaskFileName()).
    Returns the mask if present and matching the shape, else None (the caller falls
    back to the per-frame heuristics).
    '''
    mask = load_mask(path)
    if mask is None:
        return None
    if mask.shape != shape:
        print("WARNING: static mask shape " + str(mask.shape) +
              " does not match image shape " + str(shape) + " - ignoring, falling back")
        return None

    # Plausibility guard: the mask alone is available here, so the fraction of 255 pixels of
    # the whole mask stands in for the excluded ROI fraction (it never overstates it, the
    # mask is 0 outside the ROI)
    excluded_pct = 100.0 * np.count_nonzero(mask == 255) / mask.size
    if excluded_pct > MAX_PLAUSIBLE_EXCLUDED_PCT:
        print("WARNING: static mask excludes " + ("%.1f" % excluded_pct) +
              "% of its pixels, above the " + ("%.1f" % MAX_PLAUSIBLE_EXCLUDED_PCT) +
              "% plausibility threshold - ignoring, falling back")
        return None

    return mask
