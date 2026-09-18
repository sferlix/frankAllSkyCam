'''
CLI tool: (re)generates the static obstruction mask from the user's own
recent real night captures. Installed as a console-script entry point
(frankallskycam-generate-mask, see pyproject.toml) so it can be re-run any
time a site's fixed obstructions change (a tree grows, something new gets
mounted near the camera) - see
docs/superpowers/specs/2026-09-14-cloud-detection-rework-design.md section 4.

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


def _select_calibration_frames(img_root, max_frames=MAX_CALIBRATION_FRAMES):
    '''
    Returns up to max_frames real night-frame image paths found under
    img_root (searched one level of day-subfolder deep, matching
    fileManager.getOutputFileName's own img/YYYYMMDD/ layout), evenly
    sampled across the available set if more than max_frames are found.
    Night frames only - see staticmask.py's module docstring for why.

    Only real capture files (fileManager.getOutputFileName's "skycam_*.jpg"
    naming) are considered - this deliberately excludes other composite
    files that land in the same img/YYYYMMDD/ folders, e.g. startrail.py's
    "startrail_YYYYMMDD.jpg" max-stacked star-trail composites, which often
    also read below the day/night brightness threshold and would otherwise
    be miscounted as ordinary night frames (and could dominate the preview
    overlay, since they tend to sort last alphabetically).

    Only searches YYYYMMDD-named subfolders (the normal daily rotation
    fileManager.getOutputFileName creates) - NOT every subfolder of img/.
    Confirmed via a real run against 84.33.110.109 (2026-09-14): this
    site's img/ also holds user-curated archive folders (aurora/, aurora2/,
    startrails/, timelapses/) containing real skycam_*.jpg-named frames
    deliberately preserved outside the normal ~4-day rotation specifically
    because they document unusual events (e.g. aurora activity, from May
    and October 2024) - a plain "*/skycam_*.jpg" glob pulled these in as
    if they were ordinary recent night frames, and one (11 Oct 2024) ended
    up in the actual calibration stack and as the preview's background
    image. These are exactly the wrong frames to calibrate from: not
    representative of "any recent night" (curated for being unusual) and
    over a year stale (site geometry may have changed since). A YYYYMMDD
    folder-name filter excludes every one of these non-daily folders by
    construction, without needing to know their names in advance.

    Frames whose shape does not match the modal (most common) shape among
    the candidates actually read are dropped - guards against a capture
    resolution change partway through the retention window crashing
    staticmask.generate_mask's np.stack on mismatched array shapes.
    '''
    all_paths = sorted(glob.glob(os.path.join(img_root, "[0-9]" * 8, "skycam_*.jpg")))
    night_candidates = []  # (path, shape) for frames that pass the night check
    for path in all_paths:
        img = cv2.imread(path)
        if img is None:
            continue
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        roi = starscalc.roi_mask(gray, CALIBRATION_ROI_RATIO)
        if gray[roi == 255].mean() <= starscalc.DAYTIME_MEAN_THRESHOLD:
            night_candidates.append((path, gray.shape))

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
    Exits the process (sys.exit(1)) if picture_rotation is non-zero.

    __main__.py rotates and watermarks captures IN PLACE before saving them
    (see drawtext.py's photo.rotate(rotation) and __main__.py's
    photo.save(...)), so the stored frames this tool reads are already
    rotated whenever picture_rotation != 0. A mask calibrated from them
    would be misaligned when applied to the unrotated frames starscalc.py
    actually analyzes at capture time. PIL's rotate() without expand=True
    keeps the same array shape, so nothing else (e.g. the shape check in
    staticmask.get_static_mask) would catch this misalignment. Refusing
    cleanly here, rather than generating a silently misaligned mask, is the
    required v1 behavior - counter-rotating support is future work.
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
    Exits the process (sys.exit(1)) if excluded_pct exceeds
    staticmask.MAX_PLAUSIBLE_EXCLUDED_PCT - see that constant's comment in
    staticmask.py for why this guard exists (Otsu's threshold always finds
    SOME bimodal split, even without a real obstruction).
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

    print("Scanning " + img_root + " for real night frames...")
    frame_paths = _select_calibration_frames(img_root)

    if len(frame_paths) < MIN_CALIBRATION_FRAMES:
        print("ERROR: found only " + str(len(frame_paths)) + " usable night frames "
              "(need at least " + str(MIN_CALIBRATION_FRAMES) + "). "
              "Wait for more real captures and try again.")
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
    overlay[mask == 255] = [0, 255, 255]  # yellow, matching this session's diagnostic overlay convention
    cv2.imwrite(preview_path, overlay)
    print("Saved preview overlay to " + preview_path + " - review it before trusting this mask.")


if __name__ == "__main__":
    main()
