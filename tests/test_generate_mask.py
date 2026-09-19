'''
Unit tests for generate_mask.py's frame selection, with a temp directory of small
synthetic JPEGs: day/night filtering, the clear-sky filter and its skip window,
sampling cap, folder/file-name filtering and shape filtering. The mask math itself is
covered by tests/test_staticmask.py.
'''

import os

import cv2
import numpy as np
import pytest

from frankAllSkyCam import generate_mask, staticmask

HEIGHT, WIDTH = 100, 100


def _write_frame(path, mean_gray, height=HEIGHT, width=WIDTH):
    img = np.full((height, width, 3), mean_gray, dtype=np.uint8)
    cv2.imwrite(path, img)


def test_select_calibration_frames_keeps_only_night_frames(tmp_path):
    day_dir = tmp_path / "20260101"
    day_dir.mkdir()
    _write_frame(str(day_dir / "skycam_20260101_080000.jpg"), 200)  # well above DAYTIME_MEAN_THRESHOLD
    # both below DAYTIME_MEAN_THRESHOLD and CLOUD_BRIGHTNESS_LOW (33): a uniform synthetic
    # frame has no known exposure_secs, so it is scored by the brightness-only fallback
    _write_frame(str(day_dir / "skycam_20260101_010000.jpg"), 30)
    _write_frame(str(day_dir / "skycam_20260101_020000.jpg"), 28)

    result = generate_mask._select_calibration_frames(str(tmp_path), max_frames=10)

    assert len(result) == 2
    assert all(os.path.basename(p) != "skycam_20260101_080000.jpg" for p in result)


def test_select_calibration_frames_caps_and_samples_evenly(tmp_path):
    day_dir = tmp_path / "20260101"
    day_dir.mkdir()
    for i in range(20):
        _write_frame(str(day_dir / f"skycam_20260101_{i:02d}0000.jpg"), 30)

    result = generate_mask._select_calibration_frames(str(tmp_path), max_frames=5)

    assert len(result) == 5


def test_select_calibration_frames_returns_empty_when_none_found(tmp_path):
    day_dir = tmp_path / "20260101"
    day_dir.mkdir()
    _write_frame(str(day_dir / "skycam_20260101_080000.jpg"), 200)

    result = generate_mask._select_calibration_frames(str(tmp_path), max_frames=10)

    assert result == []


def test_select_calibration_frames_ignores_startrail_composites(tmp_path):
    # startrail composites land in the same img/YYYYMMDD/ folder and can read dark enough
    # to pass the night check: they must never be selected
    day_dir = tmp_path / "20260101"
    day_dir.mkdir()
    _write_frame(str(day_dir / "skycam_20260101_010000.jpg"), 30)
    _write_frame(str(day_dir / "skycam_20260101_020000.jpg"), 30)
    _write_frame(str(day_dir / "startrail_20260101.jpg"), 30)  # dark composite, not a real capture

    result = generate_mask._select_calibration_frames(str(tmp_path), max_frames=10)

    assert len(result) == 2
    assert all("startrail" not in os.path.basename(p) for p in result)


def test_select_calibration_frames_ignores_non_daily_folders(tmp_path):
    # archive folders under img/ (aurora/, startrails/, ...) can hold skycam_*.jpg-named
    # frames: only YYYYMMDD-named folders may be searched
    day_dir = tmp_path / "20260101"
    day_dir.mkdir()
    _write_frame(str(day_dir / "skycam_20260101_010000.jpg"), 30)

    aurora_dir = tmp_path / "aurora"
    aurora_dir.mkdir()
    _write_frame(str(aurora_dir / "skycam_20240514_080000.jpg"), 30)

    result = generate_mask._select_calibration_frames(str(tmp_path), max_frames=10)

    assert len(result) == 1
    assert "aurora" not in result[0]


def test_select_calibration_frames_drops_cloudy_night_frames(tmp_path, capsys):
    # cloud in the calibration set biases the median stack like an obstruction does. A
    # uniform gray well above CLOUD_BRIGHTNESS_LOW (33) reads as cloudy under the
    # brightness-only fallback used for archived frames (no known exposure_secs).
    day_dir = tmp_path / "20260101"
    day_dir.mkdir()
    _write_frame(str(day_dir / "skycam_20260101_010000.jpg"), 30)   # clear - kept
    _write_frame(str(day_dir / "skycam_20260101_020000.jpg"), 48)   # reads as heavily cloudy - dropped

    result = generate_mask._select_calibration_frames(str(tmp_path), max_frames=10)

    assert len(result) == 1
    assert "010000" in os.path.basename(result[0])
    assert "dropped" in capsys.readouterr().out.lower()


def test_select_calibration_frames_fast_forwards_past_a_cloudy_stretch(tmp_path, capsys):
    # a cloudy reading fast-forwards CALIBRATION_CLOUD_SKIP_MINUTES (checked via mtime).
    # Timeline (mtime offsets in minutes): 0 = clear (kept), 5 = cloudy (dropped, skip
    # window until 25), 10 = clear but inside the window (never opened), 30 = clear and
    # past the window (kept).
    day_dir = tmp_path / "20260101"
    day_dir.mkdir()
    base = 1_000_000  # arbitrary epoch reference; only relative offsets matter
    frames = [
        ("skycam_20260101_000000.jpg", 30, 0),    # clear - kept
        ("skycam_20260101_000500.jpg", 48, 5),    # cloudy - dropped, starts a 20min skip
        ("skycam_20260101_001000.jpg", 30, 10),   # inside the skip window - never opened
        ("skycam_20260101_003000.jpg", 30, 30),   # past the skip window - kept
    ]
    for name, gray_val, minute_offset in frames:
        path = str(day_dir / name)
        _write_frame(path, gray_val)
        t = base + minute_offset * 60
        os.utime(path, (t, t))

    result = generate_mask._select_calibration_frames(str(tmp_path), max_frames=10)

    kept = {os.path.basename(p) for p in result}
    assert kept == {"skycam_20260101_000000.jpg", "skycam_20260101_003000.jpg"}
    out = capsys.readouterr().out.lower()
    assert "dropped 1" in out
    assert "fast-forwarded past 1" in out


def test_select_calibration_frames_drops_frames_with_mismatched_shape(tmp_path, capsys):
    # frames whose shape differs from the most common one are dropped, so a resolution
    # change cannot break np.stack later
    day_dir = tmp_path / "20260101"
    day_dir.mkdir()
    for i in range(5):
        _write_frame(str(day_dir / f"skycam_20260101_0{i}0000.jpg"), 30, height=HEIGHT, width=WIDTH)
    _write_frame(str(day_dir / "skycam_20260101_090000.jpg"), 30, height=HEIGHT + 20, width=WIDTH + 20)

    result = generate_mask._select_calibration_frames(str(tmp_path), max_frames=10)

    assert len(result) == 5
    assert all("090000" not in os.path.basename(p) for p in result)
    assert "dropped 1" in capsys.readouterr().out.lower()


def test_refuse_if_rotated_exits_on_nonzero_rotation(capsys):
    with pytest.raises(SystemExit) as excinfo:
        generate_mask._refuse_if_rotated(90)

    assert excinfo.value.code == 1
    assert "picture_rotation" in capsys.readouterr().out


def test_refuse_if_rotated_allows_zero_rotation(capsys):
    generate_mask._refuse_if_rotated(0)  # must not raise

    assert capsys.readouterr().out == ""


def test_refuse_if_implausible_exits_above_threshold(capsys):
    with pytest.raises(SystemExit) as excinfo:
        generate_mask._refuse_if_implausible(staticmask.MAX_PLAUSIBLE_EXCLUDED_PCT + 1.0)

    assert excinfo.value.code == 1
    assert "implausible" in capsys.readouterr().out


def test_refuse_if_implausible_allows_below_threshold(capsys):
    generate_mask._refuse_if_implausible(staticmask.MAX_PLAUSIBLE_EXCLUDED_PCT - 1.0)  # must not raise

    assert capsys.readouterr().out == ""
