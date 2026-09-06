'''
One-off calibration tool for hotpixels.py.

Finds pixel coordinates that recur across several night frames from the
same camera - fixed sensor defects - as opposed to genuine stars,
satellites, planes or cosmic ray hits, which don't repeat at the same
position frame to frame. Not part of the automated per-capture pipeline;
run manually, occasionally, per install, against that camera's own
already-watermarked archived JPGs (frankAllSkyCam/img/<date>/*.jpg).

Usage:
    python -m frankAllSkyCam.calibratehotpixels <folder-of-night-jpgs> \
        --layout brallo|pregola|none [--out hotpixels.json] \
        [--min-fraction 0.7] [--tolerance-px 6]

Brallo and Pregola need separate runs (different sensor, different
defects) and separate output files - never share a hotpixels.json between
installs.
'''

import sys
import os
import glob
import json
import argparse
import numpy as np
import cv2
from PIL import Image

# text/logo/icon regions to exclude, measured directly off real frames from
# each camera (pixel bounding boxes of the actual red-channel text glyphs,
# not eyeballed) - a first pass reused this session's ad hoc compare_dots*
# boxes and produced false "recurring hot pixels" that were actually just
# watermark text edges peeking past too-tight cutoffs (e.g. the bottom of
# "Clouds: 0%" past y=335, or "Night: ...+1" past x=230) - text is static
# and repeats every frame exactly like a real defect would, so an
# under-sized exclusion box is worse than no box at all for this tool.
# Margins here are generous on purpose.
LAYOUTS = {
    "brallo": [
        (slice(0, 365), slice(0, 465)),
        (slice(0, 25), slice(440, 600)),
        (slice(0, 100), slice(790, 1024)),
        (slice(100, 200), slice(895, 1024)),
        (slice(600, 768), slice(0, 290)),
        (slice(560, 768), slice(870, 1024)),
    ],
    "pregola": [
        (slice(0, 385), slice(0, 300)),
        (slice(0, 25), slice(420, 565)),
        (slice(0, 105), slice(785, 1024)),
        (slice(105, 205), slice(905, 1024)),
        (slice(590, 768), slice(0, 270)),
        (slice(595, 725), slice(895, 1024)),
        (slice(725, 768), slice(840, 1024)),
    ],
    "none": [],
}


def _red_dot_mask(img):
    r, g, b = img[..., 0], img[..., 1], img[..., 2]
    return (r > 55) & (r > g * 1.7) & (r > b * 1.7)


def _blank_regions(mask, boxes):
    m = mask.copy()
    for rows, cols in boxes:
        m[rows, cols] = False
    return m


def _frame_centroids(path, boxes):
    '''Returns (width, height, [(x, y), ...]) for one frame's candidate blobs.'''
    im = np.array(Image.open(path).convert("RGB")).astype(int)
    mask = _blank_regions(_red_dot_mask(im), boxes)
    height, width = im.shape[:2]
    num_labels, _, _, centroids = cv2.connectedComponentsWithStats(
        mask.astype(np.uint8), connectivity=8)
    # label 0 is the background component, skip it
    return width, height, [(float(x), float(y)) for x, y in centroids[1:]]


def _cluster_across_frames(per_frame_centroids, tolerance_px, min_occurrences):
    '''
    Greedy cross-frame matching: a candidate in frame i is grouped with the
    closest not-yet-used candidate within tolerance_px in every later
    frame. Groups that recur in at least min_occurrences frames are kept
    as fixed defects; everything else (real stars, satellites, single-frame
    noise) is dropped.
    '''
    used = [set() for _ in per_frame_centroids]
    fixed = []
    for i, centroids in enumerate(per_frame_centroids):
        for j, (x, y) in enumerate(centroids):
            if j in used[i]:
                continue
            group = [(x, y)]
            used[i].add(j)
            for i2 in range(i + 1, len(per_frame_centroids)):
                best_j2, best_d = None, tolerance_px
                for j2, (x2, y2) in enumerate(per_frame_centroids[i2]):
                    if j2 in used[i2]:
                        continue
                    d = max(abs(x - x2), abs(y - y2))
                    if d < best_d:
                        best_j2, best_d = j2, d
                if best_j2 is not None:
                    used[i2].add(best_j2)
                    group.append(per_frame_centroids[i2][best_j2])
            if len(group) >= min_occurrences:
                avg_x = sum(g[0] for g in group) / len(group)
                avg_y = sum(g[1] for g in group) / len(group)
                fixed.append((int(round(avg_x)), int(round(avg_y))))
    return fixed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", help="folder of night JPGs from one camera")
    parser.add_argument("--layout", choices=LAYOUTS.keys(), default="none",
                         help="text/logo exclusion boxes for this camera's watermark layout")
    parser.add_argument("--out", default="hotpixels.json")
    parser.add_argument("--min-fraction", type=float, default=0.7,
                         help="a coordinate must recur in at least this fraction of frames to count as a fixed defect")
    parser.add_argument("--tolerance-px", type=int, default=6,
                         help="max pixel distance to consider two blobs the same position")
    args = parser.parse_args()

    files = sorted(glob.glob(os.path.join(args.folder, "*.jpg")))
    if len(files) < 5:
        print("Need at least 5 frames to calibrate reliably (got " + str(len(files)) + ")")
        sys.exit(1)

    boxes = LAYOUTS[args.layout]
    min_occurrences = max(3, int(round(len(files) * args.min_fraction)))

    per_frame_centroids = []
    width = height = None
    for f in files:
        w, h, centroids = _frame_centroids(f, boxes)
        if width is None:
            width, height = w, h
        elif (w, h) != (width, height):
            print("ERROR: " + f + " is " + str(w) + "x" + str(h) +
                  ", expected " + str(width) + "x" + str(height) +
                  " - all frames must be the same resolution")
            sys.exit(1)
        per_frame_centroids.append(centroids)
        print(f + ": " + str(len(centroids)) + " candidate blobs")

    fixed = _cluster_across_frames(per_frame_centroids, args.tolerance_px, min_occurrences)
    print("Found " + str(len(fixed)) + " coordinates recurring in >= " +
          str(min_occurrences) + "/" + str(len(files)) + " frames")

    with open(args.out, "w") as f:
        json.dump({"width": width, "height": height, "coordinates": fixed}, f, indent=2)
    print("Wrote " + args.out)


if __name__ == "__main__":
    main()
