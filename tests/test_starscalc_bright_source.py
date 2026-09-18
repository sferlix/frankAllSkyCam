'''
Unit tests for starscalc._bright_source_mask's centroid return value - added
to support sky-projection calibration (see
docs/superpowers/specs/2026-09-14-cloud-detection-rework-design.md section
5), which needs the actually-observed pixel position of the real bright
source, not just its halo mask. The mask/found behavior is pre-existing and
unchanged; only the new third return value is tested here.
'''

import numpy as np

from frankAllSkyCam import starscalc as sc

HEIGHT, WIDTH = 400, 400


def test_returns_none_centroid_when_nothing_found():
    gray = np.full((HEIGHT, WIDTH), 30, dtype=np.uint8)
    roi = np.full((HEIGHT, WIDTH), 255, dtype=np.uint8)

    _, found, centroid = sc._bright_source_mask(gray, roi)

    assert found is False
    assert centroid is None


def test_returns_centroid_of_single_bright_blob():
    gray = np.full((HEIGHT, WIDTH), 30, dtype=np.uint8)
    gray[100:140, 200:240] = 255  # a real bright blob, well above BRIGHT_SOURCE_MIN_AREA_FRAC
    roi = np.full((HEIGHT, WIDTH), 255, dtype=np.uint8)

    _, found, centroid = sc._bright_source_mask(gray, roi)

    assert found is True
    assert centroid is not None
    cx, cy = centroid
    assert 210 < cx < 230  # near the blob's real center (220, 120)
    assert 110 < cy < 130


def test_returns_centroid_of_largest_blob_when_multiple_found():
    # The large blob is placed at earlier rows/cols than the small blob, so
    # cv2.connectedComponentsWithStats (which labels in raster-scan order,
    # top-to-bottom / left-to-right first-encounter) assigns it the SMALLER
    # label and visits it FIRST in the `for i in range(1, n)` accumulator
    # loop. This makes "largest wins" and "last-processed wins" produce
    # different, distinguishable centroids, so the test genuinely proves the
    # running-max-by-area accumulator logic rather than coincidentally
    # passing a "last blob wins" bug too.
    gray = np.full((HEIGHT, WIDTH), 30, dtype=np.uint8)
    gray[50:130, 50:130] = 255    # large blob, 80x80 = 6400px - the "real" source, scanned FIRST
    gray[300:320, 300:320] = 255  # small blob, 20x20 = 400px, scanned LAST
    roi = np.full((HEIGHT, WIDTH), 255, dtype=np.uint8)

    _, found, centroid = sc._bright_source_mask(gray, roi)

    assert found is True
    cx, cy = centroid
    assert 80 < cx < 100  # near the large blob's center (90, 90), not the small one
    assert 80 < cy < 100
