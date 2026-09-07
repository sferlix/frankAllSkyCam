'''
Unit tests for the pure decision logic in autoexposure.py:
 - compute_raw_next: the unclamped feedback-loop prediction
 - should_use_isp: the twilight-handoff crossover test (dusk and dawn share
   this one code path - no direction flag)
 - getExposure's saturation-severity guard: a previous frame with a large
   clipped fraction can't be trusted at face value by the plain ratio
 - record_isp_exposure: harvesting the ISP's own metered exposure from a
   libcamera-still --metadata JSON sidecar during the twilight-handoff window

These don't need a camera or a real config.txt - _state_path just needs an
appPath with a writable "sqm" subfolder, which the appPath fixture provides.
'''

import json
import os

import cv2
import numpy as np
import pytest

from frankAllSkyCam import autoexposure


@pytest.fixture
def appPath(tmp_path):
    (tmp_path / autoexposure.SQM_FOLDER).mkdir(parents=True, exist_ok=True)
    return str(tmp_path) + os.sep


def write_state(appPath, exposure_secs, mean, clip_frac=None):
    state = {"exposure_secs": exposure_secs, "mean": mean}
    if clip_frac is not None:
        state["clip_frac"] = clip_frac
    with open(autoexposure._state_path(appPath), "w") as f:
        json.dump(state, f)


# ---- compute_raw_next -------------------------------------------------

def test_compute_raw_next_scales_by_target_over_last_mean():
    # last frame ran 2s and measured mean 60; target is 30 -> half as bright
    # wanted, so half the exposure
    assert autoexposure.compute_raw_next(2.0, 60.0, target_mean=30.0) == pytest.approx(1.0)


def test_compute_raw_next_none_when_last_mean_zero():
    assert autoexposure.compute_raw_next(2.0, 0.0, target_mean=30.0) is None


def test_compute_raw_next_none_when_last_exposure_zero():
    assert autoexposure.compute_raw_next(0.0, 60.0, target_mean=30.0) is None


# ---- should_use_isp (the twilight crossover test) ----------------------

def test_should_use_isp_true_when_no_state_file(appPath):
    # no history yet at all - safest default is to let the ISP keep driving
    assert autoexposure.should_use_isp(appPath, target_mean=30.0, min_exposure_secs=1.0) is True


def test_should_use_isp_true_when_raw_next_below_floor(appPath):
    # a twilight-bright previous frame: last_exposure=1.0s produced mean=229
    # (this mirrors the real overexposed bug frame) - the honest, unclamped
    # prediction is 1.0*(30/229) =~ 0.13s, well under the 1.0s floor, so the
    # ISP - not the fixed-shutter algorithm - should still be driving capture
    write_state(appPath, exposure_secs=1.0, mean=229.0)
    assert autoexposure.should_use_isp(appPath, target_mean=30.0, min_exposure_secs=1.0) is True


def test_should_use_isp_false_when_raw_next_at_or_above_floor(appPath):
    # a real night frame: last_exposure=6s measured mean=25, close to target
    # -> raw_next ~= 6*(30/25) = 7.2s, comfortably above the floor
    write_state(appPath, exposure_secs=6.0, mean=25.0)
    assert autoexposure.should_use_isp(appPath, target_mean=30.0, min_exposure_secs=1.0) is False


def test_should_use_isp_applies_same_saturation_adjustment_as_getExposure(appPath):
    # mid-night, a cloud reflecting light pollution saturates a 20s exposure
    # (clip_frac=0.6, mean=255). Chosen so the PLAIN ratio (20*30/255 ~=
    # 2.35s) sits ABOVE the floor - should_use_isp would wrongly return
    # False without the saturation adjustment - while the adjusted value
    # (2.35 / (1+0.6*8) ~= 0.41s) sits BELOW it. True here is only
    # explicable if should_use_isp actually applied the same adjustment
    # getExposure does, not a divergent plain-ratio-only check.
    write_state(appPath, exposure_secs=20.0, mean=255.0, clip_frac=0.6)

    result = autoexposure.should_use_isp(appPath, target_mean=30.0, min_exposure_secs=1.0,
                                          saturation_clip_frac_threshold=0.05,
                                          saturation_severity_gain=8.0)

    assert result is True


# ---- saturation-severity guard inside getExposure -----------------------

def test_getExposure_plain_ratio_when_not_saturated(appPath):
    write_state(appPath, exposure_secs=6.0, mean=25.0, clip_frac=0.0)
    ex = autoexposure.getExposure(11.0, esp_secs=60.0, appPath=appPath,
                                   target_mean=30.0, min_exposure_secs=1.0)
    assert ex == pytest.approx(6.0 * (30.0 / 25.0), rel=1e-3)


def test_getExposure_cuts_harder_when_previous_frame_was_saturated(appPath):
    # real bug-frame numbers: exposure floored to 1.0s, measured clip_frac
    # 0.42 (measured on the actual attached overexposed capture at
    # roi_percent=70, clip threshold 250). The plain ratio alone
    # (1.0 * 30/229 =~ 0.131s) still way overshoots what the frame needed
    # (~0.03-0.045s per sqmexp.csv at that SQM) because a clipped mean
    # carries no information about how far past 255 the true mean was -
    # the severity term is what pulls the estimate back down.
    write_state(appPath, exposure_secs=1.0, mean=229.0, clip_frac=0.42)
    plain_ratio = 1.0 * (30.0 / 229.0)

    ex = autoexposure.getExposure(11.74, esp_secs=60.0, appPath=appPath,
                                   target_mean=30.0, min_exposure_secs=0.001,
                                   saturation_clip_frac_threshold=0.05,
                                   saturation_severity_gain=8.0)

    assert ex < plain_ratio
    # matches the closed-form severity formula exactly
    expected = round(plain_ratio / (1.0 + 0.42 * 8.0), 4)
    assert ex == pytest.approx(expected)


def test_getExposure_ignores_small_clip_frac_from_a_bright_point_source(appPath):
    # a full moon in the ROI clips a couple of pixels (real luna.jpg sample
    # measured clip_frac ~0.002) without the frame being genuinely
    # overexposed - must not trigger the harsh saturation cut
    write_state(appPath, exposure_secs=6.0, mean=45.0, clip_frac=0.002)
    ex = autoexposure.getExposure(11.0, esp_secs=60.0, appPath=appPath,
                                   target_mean=30.0, min_exposure_secs=1.0,
                                   saturation_clip_frac_threshold=0.05,
                                   saturation_severity_gain=8.0)
    assert ex == pytest.approx(6.0 * (30.0 / 45.0), rel=1e-3)


def test_getExposure_backward_compatible_with_state_missing_clip_frac(appPath):
    # state files written before this change have no "clip_frac" key at all
    write_state(appPath, exposure_secs=6.0, mean=25.0)  # no clip_frac
    ex = autoexposure.getExposure(11.0, esp_secs=60.0, appPath=appPath,
                                   target_mean=30.0, min_exposure_secs=1.0)
    assert ex == pytest.approx(6.0 * (30.0 / 25.0), rel=1e-3)


# ---- recordExposureResult writes clip_frac ------------------------------

def test_recordExposureResult_writes_clip_frac(appPath, tmp_path):
    # a synthetic frame: half the ROI pinned at 255, half mid-gray
    img = np.full((200, 200), 100, dtype=np.uint8)
    img[:, 100:] = 255
    jpg_path = str(tmp_path / "frame.jpg")
    cv2.imwrite(jpg_path, img)

    autoexposure.recordExposureResult(jpg_path, 1.0, appPath, roi_percent=100)

    with open(autoexposure._state_path(appPath)) as f:
        state = json.load(f)
    assert state["clip_frac"] == pytest.approx(0.5, abs=0.02)


# ---- record_isp_exposure (twilight metadata harvest) ---------------------

def test_record_isp_exposure_reads_metadata_and_records_state(appPath, tmp_path):
    meta_path = str(tmp_path / "meta.json")
    with open(meta_path, "w") as f:
        json.dump({"ExposureTime": 314}, f)  # microseconds, real value from the Pi

    img = np.full((50, 50), 40, dtype=np.uint8)
    jpg_path = str(tmp_path / "frame.jpg")
    cv2.imwrite(jpg_path, img)

    result = autoexposure.record_isp_exposure(meta_path, jpg_path, appPath, roi_percent=100)

    assert result == pytest.approx(314 / 1_000_000.0)
    with open(autoexposure._state_path(appPath)) as f:
        state = json.load(f)
    assert state["exposure_secs"] == pytest.approx(314 / 1_000_000.0)


def test_record_isp_exposure_returns_none_when_metadata_missing(appPath, tmp_path):
    jpg_path = str(tmp_path / "frame.jpg")
    cv2.imwrite(jpg_path, np.full((50, 50), 40, dtype=np.uint8))

    result = autoexposure.record_isp_exposure(
        str(tmp_path / "does_not_exist.json"), jpg_path, appPath, roi_percent=100)

    assert result is None


def test_record_isp_exposure_returns_none_when_exposuretime_key_absent(appPath, tmp_path):
    meta_path = str(tmp_path / "meta.json")
    with open(meta_path, "w") as f:
        json.dump({"AnalogueGain": 1.0}, f)  # no ExposureTime key
    jpg_path = str(tmp_path / "frame.jpg")
    cv2.imwrite(jpg_path, np.full((50, 50), 40, dtype=np.uint8))

    result = autoexposure.record_isp_exposure(meta_path, jpg_path, appPath, roi_percent=100)

    assert result is None
