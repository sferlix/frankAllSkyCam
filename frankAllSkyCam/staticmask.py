'''
Auto-generated static obstruction mask - replaces starscalc.py's two dynamic,
per-frame obstruction heuristics (_obstruction_mask for night, brightness-
based; _day_obstruction_mask for day, texture-based) with a single mask
learned once from real night captures and reused for both. See
docs/superpowers/specs/2026-09-14-cloud-detection-rework-design.md section 4
for the full rationale (the dynamic day-side texture heuristic was confirmed
this session to also flag real cloud edges as "foliage", not just trees).

Must be generated from NIGHT frames specifically, not day frames: the
darkness threshold below only works because night foliage reads near-black
against a sky that always retains some airglow/light-pollution floor (the
same physical basis starscalc._obstruction_mask already relies on) - daytime
foliage is lit, not dark, so a day-frame stack would not reliably separate
obstruction from sky by darkness. Obstruction geometry itself is time-of-day
independent (a tree is a tree at any hour), so a mask learned from night
frames is valid to reuse for the day branch too.

Mask polarity matches starscalc._obstruction_mask's existing convention:
255 = obstruction (excluded), 0 = clear sky. This is the OPPOSITE of
roi_mask's 255=included convention - deliberate, so this module's output is
a drop-in replacement at every existing obstruction-mask call site with no
change to the surrounding "sky[obstruction==255]=0" logic.

KNOWN LIMITATION (accepted for this iteration, not an oversight): the frames
this mask is calibrated from are read from disk post-processing (see
generate_mask.py), i.e. after __main__.py has already burned in fixed-
position overlays - logo, compass, planet icons - pasted at configured pixel
coordinates. Because these overlay elements sit at the same pixel location
in every frame, they survive the median stack intact just like a real
obstruction does, so any overlay element that falls inside the analyzed ROI
becomes a permanent excluded region in the generated mask. A full fix would
require capturing pre-watermark frames, which is a larger architectural
change out of scope for this iteration; this module and generate_mask.py's
CLI output are expected to be used with that limitation understood.
'''

import os

import cv2
import numpy as np

MASK_BLUR_SIGMA = 3       # initial default, not yet validated against real
                           # masks - removes hot-pixel/sensor-noise-scale
                           # variation from the median stack before
                           # thresholding, without blurring real obstruction
                           # edges (much smaller than GUARD_BAND_PX=41 used
                           # elsewhere in starscalc.py for edge margins).
                           # Revisit once real generated masks have been
                           # visually reviewed (see spec section 5/10 - this
                           # whole rework is explicitly iterative).
MASK_SMOOTH_KERNEL = 15   # initial default, same caveat as MASK_BLUR_SIGMA -
                           # closes small gaps and removes small noise blobs
                           # in the thresholded mask, smaller than
                           # GUARD_BAND_PX so it doesn't over-erode real
                           # obstruction boundaries.
MAX_PLAUSIBLE_EXCLUDED_PCT = 60.0  # initial, unvalidated default, same caveat
                           # as MASK_BLUR_SIGMA/MASK_SMOOTH_KERNEL - Otsu's
                           # threshold always finds SOME bimodal split, even
                           # on a stack with no real obstruction at all
                           # (fisheye vignetting near the ROI edge is a
                           # plausible false split). A mask excluding more
                           # than this fraction of its own pixels is treated
                           # as implausible and rejected, both at generation
                           # time (generate_mask.py) and at load time
                           # (get_static_mask below), so a bad mask can never
                           # be worse than the dynamic-mask fallback. Revisit
                           # once real generated masks have been visually
                           # reviewed (see spec section 5/10).


def generate_mask(gray_images, roi):
    '''
    gray_images: list of 2D grayscale np.ndarray, all the same shape, all
    real NIGHT frames (see module docstring for why).
    roi: the circular ROI mask (roi_mask's output, 255=inside/analyzed).

    Returns a uint8 mask, same shape as the inputs, 255=obstruction
    (excluded), 0=clear sky - see module docstring for polarity rationale.
    '''
    if not gray_images:
        raise ValueError("generate_mask requires at least one image")

    stacked = np.stack(gray_images, axis=0)
    median = np.median(stacked, axis=0).astype(np.uint8)
    blurred = cv2.GaussianBlur(median, (0, 0), sigmaX=MASK_BLUR_SIGMA)

    # Otsu's threshold computed from ROI-restricted pixel values only - the
    # full frame includes the pitch-black region outside the fisheye circle,
    # which would skew the bimodal fit away from the real obstruction/sky
    # split inside the ROI.
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
    shape: the (height, width) of the current frame being analyzed.
    path: where the generated mask is expected to live (see
    fileManager.getStaticMaskFileName()).

    Returns the loaded mask if present and shape-compatible, else None (the
    caller in starscalc.py falls back to today's dynamic masks - a fresh
    install with no generated mask yet, or one where the capture resolution
    changed since the mask was generated, is never worse off than today).
    '''
    mask = load_mask(path)
    if mask is None:
        return None
    if mask.shape != shape:
        print("WARNING: static mask shape " + str(mask.shape) +
              " does not match image shape " + str(shape) + " - ignoring, falling back")
        return None

    # Plausibility guard: get_static_mask only receives the mask array, not
    # the ROI it was generated from, so we use the fraction of ALL pixels in
    # the mask that are 255 as a practical proxy for "fraction of the ROI
    # excluded" (the mask is 0 everywhere outside the ROI by construction, so
    # this proxy is conservative - it never overstates the excluded ROI
    # fraction). See MAX_PLAUSIBLE_EXCLUDED_PCT above for why this guard
    # exists.
    excluded_pct = 100.0 * np.count_nonzero(mask == 255) / mask.size
    if excluded_pct > MAX_PLAUSIBLE_EXCLUDED_PCT:
        print("WARNING: static mask excludes " + ("%.1f" % excluded_pct) +
              "% of its pixels, above the " + ("%.1f" % MAX_PLAUSIBLE_EXCLUDED_PCT) +
              "% plausibility threshold - ignoring, falling back")
        return None

    return mask
