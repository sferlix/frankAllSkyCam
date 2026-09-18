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
MAX_CALIBRATION_CLOUD_PCT = 10.0  # initial, unvalidated default (same caveat as
                               # staticmask.py's own generation constants - revisit
                               # once real generated masks have been visually
                               # reviewed). A frame with real cloud sitting over
                               # part of the sky reads dark there, same as a real
                               # obstruction would - config.txt's days_retention
                               # (3 by default) means the calibration set is
                               # realistically only 3-4 nights of frames, so even
                               # one partly-cloudy night can bias the median stack
                               # (confirmed on a real generated mask, 2026-09-18:
                               # two large excluded regions that didn't follow the
                               # actual tree silhouette at all, sitting over open
                               # starfield with the Milky Way visible through them
                               # in the preview). Frames above this threshold are
                               # dropped before the median/Otsu step in
                               # staticmask.generate_mask, not after - keeping a
                               # contaminated frame OUT of the stack in the first
                               # place, rather than trying to correct for it
                               # afterward.
CALIBRATION_CLOUD_SKIP_MINUTES = 20  # initial, unvalidated default. Cloud cover
                               # persists over real time far more than it varies
                               # frame to frame (confirmed on real data,
                               # 2026-09-18: a full-night sample found long
                               # unbroken cloudy stretches, e.g. 19:35-21:56
                               # straight through at 15-82% cloud) - once a
                               # candidate reads above MAX_CALIBRATION_CLOUD_PCT,
                               # every file within this many real minutes
                               # afterward is skipped without even being opened
                               # (checked via a cheap mtime stat, not a decode),
                               # rather than re-running the full, expensive
                               # analyze_sky_robust (star detection + multiple
                               # signals) on each one only to reach the same
                               # conclusion. Only a cloudy reading triggers a
                               # skip - a clear one never does, since clear
                               # frames are exactly what this is trying to find
                               # as many of as (cheaply) possible. If the sky
                               # clears within the skip window, those specific
                               # frames are missed - an acceptable cost for the
                               # speedup given a real night typically has far
                               # more usable frames than MIN_CALIBRATION_FRAMES
                               # needs (see MAX_CALIBRATION_CLOUD_PCT's own
                               # comment for the real yield data).


def _select_calibration_frames(img_root, max_frames=MAX_CALIBRATION_FRAMES):
    '''
    Returns up to max_frames real night-frame image paths found under
    img_root (searched one level of day-subfolder deep, matching
    fileManager.getOutputFileName's own img/YYYYMMDD/ layout), evenly
    sampled across the available set if more than max_frames are found.
    Night frames only - see staticmask.py's module docstring for why.

    Also clear-sky only (see MAX_CALIBRATION_CLOUD_PCT): a candidate is
    scored with the real, currently-installed starscalc.analyze_sky_robust
    (same function production uses, not a re-derived approximation) and
    dropped if it reads above the cloud threshold. Archived frames have no
    known exposure_secs (this platform's libcamera-still output has no
    EXIF - see starscalc._read_exposure_seconds), so this runs the night
    branch's weaker "exposure unknown" fallback signal rather than its
    full exposure-normalized one; a generous threshold is used to allow
    for that.

    A cloudy reading fast-forwards CALIBRATION_CLOUD_SKIP_MINUTES of real
    time ahead before the next frame is even opened, rather than paying
    for the full analyze_sky_robust call on every frame of what's usually
    a long, unbroken cloudy stretch - see that constant's own comment.

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

        # skip_star_detection: this filter only needs cloud_pct, and star
        # detection (_find_stars) is the single most expensive part of the
        # night-branch pipeline - confirmed on a real 84.33.110.109 run,
        # 2026-09-18: a single real night frame's full analysis measured
        # ~16s, and a full mask-generation run over a 4308-frame retention
        # window took over 40 minutes. cloud_cover never depends on
        # star_count (independent code paths after the same obstruction/sky
        # mask), so skipping it changes nothing about which frames get kept.
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
    overlay[mask == 255] = [0, 255, 255]  # yellow, matching this session's diagnostic overlay convention
    cv2.imwrite(preview_path, overlay)
    print("Saved preview overlay to " + preview_path + " - review it before trusting this mask.")


if __name__ == "__main__":
    main()
