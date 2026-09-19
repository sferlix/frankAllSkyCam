'''
CLI tool: (re)generates the static obstruction mask from the recent night captures
of this install. Installed as the console script frankallskycam-generate-mask (see
pyproject.toml); run it again whenever the fixed obstructions change (a tree grows,
something is mounted near the camera).

Usage: frankallskycam-generate-mask
'''

import glob
import os
import shutil
import sys
from collections import Counter
from configparser import ConfigParser

import cv2
import numpy as np

from frankAllSkyCam import fileManager, staticmask, starscalc

CALIBRATION_ROI_RATIO = 0.65  # matches __main__.py's own analyze_sky_robust call
MAX_CALIBRATION_FRAMES = 60   # bounds runtime/memory; evenly sampled if more are available
MIN_CALIBRATION_FRAMES = 5    # below this, refuse rather than generate a mask from too little data
MAX_CALIBRATION_CLOUD_PCT = 10.0  # frames reading above this cloud cover are left out of the
                               # stack: cloud reads dark like an obstruction and would bias it
CALIBRATION_CLOUD_SKIP_MINUTES = 20  # after a cloudy frame, files within this many minutes are
                               # skipped unopened (cloud persists; checked by mtime, not decode)


def _select_calibration_frames(img_root, max_frames=MAX_CALIBRATION_FRAMES):
    '''
    Returns up to max_frames night-frame paths from the YYYYMMDD day folders of
    img_root (fileManager.getOutputFileName's layout), evenly sampled if there are more.

    Only real captures ("skycam_*.jpg") in YYYYMMDD folders are read: this excludes
    composites such as startrail_*.jpg and curated archive folders (aurora/, ...).

    Only night frames (see staticmask.py) with a cloud cover of at most
    MAX_CALIBRATION_CLOUD_PCT are kept, scored with starscalc.analyze_sky_robust.
    Archived frames have no known exposure, so this uses the night branch's
    brightness/texture fallback. A cloudy frame makes the scan skip the next
    CALIBRATION_CLOUD_SKIP_MINUTES of files.

    Frames whose shape differs from the most common one are dropped, so a resolution
    change inside the retention window cannot break the stack.
    '''
    all_paths = sorted(glob.glob(os.path.join(img_root, "[0-9]" * 8, "skycam_*.jpg")))
    night_candidates = []  # (path, shape) for frames that pass the night + clear-sky checks
    cloudy_dropped = 0
    skipped = 0
    skip_until = None  # real epoch seconds; frames older than this are skipped unopened
    for path in all_paths:
        if skip_until is not None:
            try:
                mtime = os.path.getmtime(path)
            except OSError:
                mtime = None
            if mtime is not None and mtime < skip_until:
                skipped += 1
                continue
            skip_until = None

        img = cv2.imread(path)
        if img is None:
            continue
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        roi = starscalc.roi_mask(gray, CALIBRATION_ROI_RATIO)
        if gray[roi == 255].mean() > starscalc.DAYTIME_MEAN_THRESHOLD:
            continue  # day frame, not a night calibration candidate at all

        # only cloud_pct is needed and star detection is the most expensive step;
        # cloud_cover does not depend on it
        _, cloud_pct = starscalc.analyze_sky_robust(path, diametro_rapporto=CALIBRATION_ROI_RATIO,
                                                     skip_star_detection=True)
        if cloud_pct > MAX_CALIBRATION_CLOUD_PCT:
            cloudy_dropped += 1
            skip_until = os.path.getmtime(path) + CALIBRATION_CLOUD_SKIP_MINUTES * 60
            continue

        night_candidates.append((path, gray.shape))

    if cloudy_dropped > 0:
        print("NOTE: dropped " + str(cloudy_dropped) + " candidate night frame(s) "
              "reading above " + ("%.1f" % MAX_CALIBRATION_CLOUD_PCT) + "% cloud "
              "cover - real cloud sitting over part of the sky would otherwise "
              "bias the calibration median the same way a real obstruction does." +
              (" Fast-forwarded past " + str(skipped) + " more, within " +
               str(CALIBRATION_CLOUD_SKIP_MINUTES) + " minutes of a cloudy reading, "
               "without re-checking each one." if skipped > 0 else ""))

    if not night_candidates:
        return []

    shape_counts = Counter(shape for _, shape in night_candidates)
    modal_shape = shape_counts.most_common(1)[0][0]
    night_paths = [path for path, shape in night_candidates if shape == modal_shape]
    dropped = len(night_candidates) - len(night_paths)
    if dropped > 0:
        print("NOTE: dropped " + str(dropped) + " candidate frame(s) with a shape "
              "different from the modal shape " + str(modal_shape) + " (likely a "
              "capture resolution change during the retention window).")

    if len(night_paths) > max_frames:
        indices = np.linspace(0, len(night_paths) - 1, max_frames).astype(int)
        night_paths = [night_paths[i] for i in indices]

    return night_paths


def _refuse_if_rotated(picture_rotation):
    '''
    Exits (sys.exit(1)) if picture_rotation is non-zero: __main__.py rotates the stored
    frames in place, but starscalc analyzes them unrotated, so a mask calibrated from
    rotated frames would be misaligned (and the shape check would not notice).
    '''
    if picture_rotation != 0:
        print("ERROR: config.txt's [resolution] picture_rotation is set to " +
              str(picture_rotation) + " (non-zero). __main__.py rotates and "
              "watermarks captures IN PLACE before saving them (see "
              "drawtext.py's photo.rotate(rotation) and __main__.py's "
              "photo.save(...)), so the stored frames this tool reads are "
              "already rotated - a mask calibrated from them would be "
              "misaligned when applied to the unrotated frames starscalc.py "
              "actually analyzes, and PIL's rotate() without expand=True "
              "keeps the same array shape, so nothing else would catch the "
              "misalignment. Refusing rather than generating a silently "
              "misaligned mask; counter-rotating support is future work.")
        sys.exit(1)


def _refuse_if_implausible(excluded_pct):
    '''
    Exits (sys.exit(1)) if excluded_pct exceeds staticmask.MAX_PLAUSIBLE_EXCLUDED_PCT:
    Otsu's threshold always finds some split, even without a real obstruction.
    '''
    if excluded_pct > staticmask.MAX_PLAUSIBLE_EXCLUDED_PCT:
        print("ERROR: generated mask excludes " + ("%.1f" % excluded_pct) +
              "% of the analyzed sky area, above the " +
              ("%.1f" % staticmask.MAX_PLAUSIBLE_EXCLUDED_PCT) + "% plausibility "
              "threshold - this looks implausible (Otsu's threshold always finds "
              "SOME bimodal split, even without a real obstruction, e.g. from "
              "fisheye vignetting near the ROI edge). Refusing to save it - "
              "review the input frames and/or MASK_BLUR_SIGMA/MASK_SMOOTH_KERNEL "
              "in staticmask.py, then try again.")
        sys.exit(1)


def main():
    config_path = fileManager.getConfigFileName()  # also ensures ~/frankAllSkyCam/ exists
    app_path = os.path.dirname(config_path)
    img_root = os.path.join(app_path, "img")

    config = ConfigParser()
    config.read(config_path)
    picture_rotation = int(config['resolution']['picture_rotation'])
    _refuse_if_rotated(picture_rotation)

    print("Scanning " + img_root + " for real, clear-sky night frames...")
    frame_paths = _select_calibration_frames(img_root)

    if len(frame_paths) < MIN_CALIBRATION_FRAMES:
        print("ERROR: found only " + str(len(frame_paths)) + " usable clear-sky night frames "
              "(need at least " + str(MIN_CALIBRATION_FRAMES) + "). This also happens on a run "
              "of cloudy/hazy nights, not just too few captures overall - wait for more real "
              "clear nights and try again.")
        sys.exit(1)

    print("Using " + str(len(frame_paths)) + " real night frames.")
    gray_images = []
    for path in frame_paths:
        img = cv2.imread(path)
        gray_images.append(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))

    roi = starscalc.roi_mask(gray_images[0], CALIBRATION_ROI_RATIO)
    mask = staticmask.generate_mask(gray_images, roi)

    excluded_pct = 100.0 * np.sum(mask == 255) / np.sum(roi == 255)
    print("Mask excludes " + ("%.1f" % excluded_pct) + "% of the analyzed sky area.")
    _refuse_if_implausible(excluded_pct)

    mask_path = fileManager.getStaticMaskFileName()
    if os.path.isfile(mask_path):
        backup_path = mask_path + ".bak"
        print("Backing up existing mask to " + backup_path)
        shutil.copy(mask_path, backup_path)

    staticmask.save_mask(mask, mask_path)
    print("Saved static mask to " + mask_path)

    preview_path = mask_path.replace(".png", "_preview.png")
    overlay = cv2.imread(frame_paths[-1])
    overlay[mask == 255] = [0, 255, 255]  # excluded area in yellow
    cv2.imwrite(preview_path, overlay)
    print("Saved preview overlay to " + preview_path + " - review it before trusting this mask.")


if __name__ == "__main__":
    main()
