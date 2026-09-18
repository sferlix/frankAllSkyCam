'''
Unit tests for generate_mask.py's frame-selection logic. Uses a temp
directory of small synthetic JPEGs (not real captures) to test the
day/night filtering and sampling-cap behavior in isolation from real image
I/O and from staticmask.generate_mask's own math (already covered in
tests/test_staticmask.py).
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
    # both below DAYTIME_MEAN_THRESHOLD AND CLOUD_BRIGHTNESS_LOW (33) - a
    # uniform-gray synthetic frame has no known exposure_secs (matches a
    # real archived frame - see MAX_CALIBRATION_CLOUD_PCT's own comment),
    # so it's scored by the weaker brightness-only fallback; 40 used to be
    # used here too, but reads as ~41% cloud under that fallback since the
    # clear-sky filter was added - not what this test is checking
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
    # Finding 2: startrail.py's max-stacked composites land in the same
    # img/YYYYMMDD/ folder and often read dark enough to pass the night
    # check too - they must never be selected as calibration frames.
    day_dir = tmp_path / "20260101"
    day_dir.mkdir()
    _write_frame(str(day_dir / "skycam_20260101_010000.jpg"), 30)
    _write_frame(str(day_dir / "skycam_20260101_020000.jpg"), 30)
    _write_frame(str(day_dir / "startrail_20260101.jpg"), 30)  # dark composite, not a real capture

    result = generate_mask._select_calibration_frames(str(tmp_path), max_frames=10)

    assert len(result) == 2
    assert all("startrail" not in os.path.basename(p) for p in result)


def test_select_calibration_frames_ignores_non_daily_folders(tmp_path):
    # Found via a real run against 84.33.110.109 (2026-09-14): img/ also
    # holds user-curated archive folders (aurora/, aurora2/, startrails/,
    # timelapses/) containing real skycam_*.jpg-named frames deliberately
    # preserved outside the normal daily rotation - a glob that searches
    # every subfolder of img/ (not just YYYYMMDD-named ones) pulls these
    # in as if they were ordinary recent night frames. One (from Oct 2024)
    # ended up driving a real generated mask before this fix.
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
    # regression for the 2026-09-18 mask review: a real generated mask had
    # two large excluded regions that didn't follow the actual tree
    # silhouette at all, sitting over open starfield - traced to real cloud
    # cover in part of the (only ~3-4 night, per config.txt's
    # days_retention) calibration set biasing the median the same way a
    # real obstruction does. A uniform gray value well above
    # CLOUD_BRIGHTNESS_LOW (33) reads as cloudy under the weaker
    # "exposure unknown" fallback this archived-frame path uses (no known
    # exposure_secs), same as a real thin/hazy frame would with no
    # brightness reference to correct against.
    day_dir = tmp_path / "20260101"
    day_dir.mkdir()
    _write_frame(str(day_dir / "skycam_20260101_010000.jpg"), 30)   # clear - kept
    _write_frame(str(day_dir / "skycam_20260101_020000.jpg"), 48)   # reads as heavily cloudy - dropped

    result = generate_mask._select_calibration_frames(str(tmp_path), max_frames=10)

    assert len(result) == 1
    assert "010000" in os.path.basename(result[0])
    assert "dropped" in capsys.readouterr().out.lower()


def test_select_calibration_frames_drops_frames_with_mismatched_shape(tmp_path, capsys):
    # Finding 4: a capture resolution change partway through the retention
    # window must not crash np.stack later - frames whose shape doesn't
    # match the modal shape are dropped here instead.
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
