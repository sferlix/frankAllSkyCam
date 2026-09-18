'''
Unit tests for starscalc._get_obstruction_mask - prefers the static mask
when present and shape-compatible, falls back to today's existing dynamic
obstruction masks otherwise (see
docs/superpowers/specs/2026-09-14-cloud-detection-rework-design.md
section 4: a fresh install with no generated mask yet must be no worse off
than before this change).
'''

import numpy as np

from frankAllSkyCam import staticmask
from frankAllSkyCam import starscalc as sc

HEIGHT, WIDTH = 200, 200


def _roi_full():
    return np.full((HEIGHT, WIDTH), 255, dtype=np.uint8)


def test_uses_static_mask_when_present(tmp_path):
    gray = np.full((HEIGHT, WIDTH), 30, dtype=np.uint8)
    roi = _roi_full()
    static = np.zeros((HEIGHT, WIDTH), dtype=np.uint8)
    static[0:50, 0:50] = 255
    mask_path = str(tmp_path / "mask.png")
    staticmask.save_mask(static, mask_path)

    result = sc._get_obstruction_mask(gray, roi, is_night=True, mask_path=mask_path)

    assert np.array_equal(result, static)


def test_falls_back_to_dynamic_night_mask_when_missing(tmp_path):
    gray = np.full((HEIGHT, WIDTH), 30, dtype=np.uint8)
    gray[150:190, 20:60] = 5  # dark foreground obstruction candidate
    roi = _roi_full()
    mask_path = str(tmp_path / "does_not_exist.png")

    result = sc._get_obstruction_mask(gray, roi, is_night=True, mask_path=mask_path)
    expected = sc._obstruction_mask(gray, roi)

    assert np.array_equal(result, expected)


def test_falls_back_to_dynamic_day_mask_when_missing(tmp_path):
    gray = np.full((HEIGHT, WIDTH), 100, dtype=np.uint8)
    roi = _roi_full()
    mask_path = str(tmp_path / "does_not_exist.png")

    result = sc._get_obstruction_mask(gray, roi, is_night=False, mask_path=mask_path)
    expected = sc._day_obstruction_mask(gray, roi)

    assert np.array_equal(result, expected)


def test_falls_back_on_shape_mismatch(tmp_path):
    gray = np.full((HEIGHT, WIDTH), 30, dtype=np.uint8)
    roi = _roi_full()
    static = np.zeros((HEIGHT, WIDTH + 10), dtype=np.uint8)  # wrong shape
    mask_path = str(tmp_path / "mask.png")
    staticmask.save_mask(static, mask_path)

    result = sc._get_obstruction_mask(gray, roi, is_night=True, mask_path=mask_path)
    expected = sc._obstruction_mask(gray, roi)

    assert np.array_equal(result, expected)
