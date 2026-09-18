'''
Unit tests for staticmask.py - the auto-generated static obstruction mask
(median-stack + Otsu threshold + morphological smoothing over real night
frames, see docs/superpowers/specs/2026-09-14-cloud-detection-rework-design.md
section 4). Synthetic arrays, not real captures - matches this project's
existing test style (test_starscalc_haze.py, test_starscalc_texture_only.py).
'''

import numpy as np
import pytest

from frankAllSkyCam import staticmask

HEIGHT, WIDTH = 200, 200


def _roi_full():
    return np.full((HEIGHT, WIDTH), 255, dtype=np.uint8)


def test_generate_mask_excludes_fixed_dark_region():
    # a fixed dark rectangle (simulating a tree silhouette) present at the
    # same location in every frame, against a bright, frame-to-frame-varying
    # background (simulating real sky/cloud variation) - the fixed dark
    # region must read as obstruction (255); the varying bright region must
    # not.
    roi = _roi_full()
    rng = np.random.default_rng(seed=42)
    frames = []
    for _ in range(10):
        frame = rng.integers(140, 200, size=(HEIGHT, WIDTH), dtype=np.uint8)
        frame[150:190, 20:60] = 10  # fixed dark obstruction, same spot every frame
        frames.append(frame)

    mask = staticmask.generate_mask(frames, roi)

    assert np.all(mask[160:180, 30:50] == 255)  # well inside the fixed dark region
    assert np.mean(mask[0:100, 100:200] == 0) > 0.8  # varying bright region, mostly clear


def test_generate_mask_raises_on_empty_list():
    with pytest.raises(ValueError):
        staticmask.generate_mask([], _roi_full())


def test_save_and_load_mask_round_trip(tmp_path):
    mask = np.zeros((HEIGHT, WIDTH), dtype=np.uint8)
    mask[50:100, 50:100] = 255
    path = str(tmp_path / "mask.png")

    staticmask.save_mask(mask, path)
    loaded = staticmask.load_mask(path)

    assert loaded is not None
    assert np.array_equal(loaded, mask)


def test_load_mask_returns_none_when_missing(tmp_path):
    path = str(tmp_path / "does_not_exist.png")

    assert staticmask.load_mask(path) is None


def test_get_static_mask_returns_none_when_missing(tmp_path):
    path = str(tmp_path / "does_not_exist.png")

    assert staticmask.get_static_mask((HEIGHT, WIDTH), path) is None


def test_get_static_mask_returns_none_on_shape_mismatch(tmp_path):
    mask = np.zeros((HEIGHT, WIDTH), dtype=np.uint8)
    path = str(tmp_path / "mask.png")
    staticmask.save_mask(mask, path)

    result = staticmask.get_static_mask((HEIGHT, WIDTH + 10), path)

    assert result is None


def test_get_static_mask_returns_mask_when_shape_matches(tmp_path):
    mask = np.zeros((HEIGHT, WIDTH), dtype=np.uint8)
    mask[10:20, 10:20] = 255
    path = str(tmp_path / "mask.png")
    staticmask.save_mask(mask, path)

    result = staticmask.get_static_mask((HEIGHT, WIDTH), path)

    assert result is not None
    assert np.array_equal(result, mask)


def test_get_static_mask_returns_none_when_implausibly_large(tmp_path, capsys):
    # Finding 3a: a degenerate mask (e.g. from a false Otsu split with no
    # real obstruction) must never be loaded and used live - it must fall
    # back to the dynamic masks, exactly like the shape-mismatch case.
    mask = np.zeros((HEIGHT, WIDTH), dtype=np.uint8)
    mask[:, :] = 255  # 100% excluded, well above MAX_PLAUSIBLE_EXCLUDED_PCT
    path = str(tmp_path / "mask.png")
    staticmask.save_mask(mask, path)

    result = staticmask.get_static_mask((HEIGHT, WIDTH), path)

    assert result is None
    assert "WARNING" in capsys.readouterr().out


def test_get_static_mask_returns_mask_when_excluded_pct_within_threshold(tmp_path):
    # exclude a fraction just under MAX_PLAUSIBLE_EXCLUDED_PCT (60%) so this
    # actually exercises the guard's accept boundary, not just any old
    # mask - HEIGHT=WIDTH=200, so 110 excluded rows out of 200 is 55%.
    assert staticmask.MAX_PLAUSIBLE_EXCLUDED_PCT == 60.0  # guards the 55% assumption below
    mask = np.zeros((HEIGHT, WIDTH), dtype=np.uint8)
    mask[0:110, :] = 255  # 55% excluded, just under the 60% threshold
    path = str(tmp_path / "mask.png")
    staticmask.save_mask(mask, path)

    result = staticmask.get_static_mask((HEIGHT, WIDTH), path)

    assert result is not None
    assert np.array_equal(result, mask)


def test_save_mask_raises_on_write_failure(tmp_path):
    # Finding 5: cv2.imwrite returns False (rather than raising) when the
    # parent directory doesn't exist - save_mask must not swallow that.
    mask = np.zeros((HEIGHT, WIDTH), dtype=np.uint8)
    bad_path = str(tmp_path / "does_not_exist" / "mask.png")

    with pytest.raises((IOError, OSError)):
        staticmask.save_mask(mask, bad_path)
