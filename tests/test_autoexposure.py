'''
Unit tests for the pure decision logic in autoexposure.py:
 - compute_raw_next: the feedback-loop prediction (plain ratio, step-limited
   on the upward side only - see MAX_EXPOSURE_STEP_FACTOR)
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


def test_compute_raw_next_caps_extreme_upward_extrapolation():
    # an ISP-driven frame at exposure=0.06s measured mean=1.6 (near-black, mostly noise).
    # The plain ratio (0.06*30/1.6 = 1.125s, 18.75x) is capped at MAX_EXPOSURE_STEP_FACTOR
    # (5x) over last_exposure.
    result = autoexposure.compute_raw_next(0.06, 1.6, target_mean=30.0)

    assert result == pytest.approx(0.06 * autoexposure.MAX_EXPOSURE_STEP_FACTOR)
    assert result < 1.125  # the real, unclamped, overshooting value


def test_compute_raw_next_does_not_cap_downward_steps():
    # a clipped previous frame may cut the exposure by any factor: only growth is capped
    # (the saturation test below needs a ~7.6x downward step)
    result = autoexposure.compute_raw_next(1.0, 229.0, target_mean=30.0)

    assert result == pytest.approx(1.0 * (30.0 / 229.0))


# ---- moon_adjusted_target_mean (true-night target boost) ---------------

def test_moon_adjusted_target_mean_full_boost_when_moon_below_horizon():
    # Moon below the horizon - full boost regardless of illumination
    result = autoexposure.moon_adjusted_target_mean(
        base_target_mean=30.0, dark_sky_target_mean=35.0, moon_alt_deg=-10.0, moon_illumination=1.0)
    assert result == pytest.approx(35.0)


def test_moon_adjusted_target_mean_full_boost_when_moon_new():
    # Moon above the horizon but new (0 illumination) - full boost
    result = autoexposure.moon_adjusted_target_mean(
        base_target_mean=30.0, dark_sky_target_mean=35.0, moon_alt_deg=45.0, moon_illumination=0.0)
    assert result == pytest.approx(35.0)


def test_moon_adjusted_target_mean_falls_back_to_base_at_full_moon_zenith():
    # full moon straight overhead - sin(90deg)=1, illumination=1 -> no boost
    # at all, falls all the way back to the old, conservative target
    result = autoexposure.moon_adjusted_target_mean(
        base_target_mean=30.0, dark_sky_target_mean=35.0, moon_alt_deg=90.0, moon_illumination=1.0)
    assert result == pytest.approx(30.0)


def test_moon_adjusted_target_mean_interpolates_partway():
    # half-illuminated moon at 30deg altitude: moon_factor = sin(30deg)*0.5 = 0.25
    result = autoexposure.moon_adjusted_target_mean(
        base_target_mean=30.0, dark_sky_target_mean=35.0, moon_alt_deg=30.0, moon_illumination=0.5)
    assert result == pytest.approx(35.0 + (30.0 - 35.0) * 0.25)


def test_moon_adjusted_target_mean_defaults_to_boost_when_moon_data_missing():
    # calculateEphem couldn't supply moon data - safest is still the boost,
    # not silently reverting to the conservative value for an unrelated reason
    result = autoexposure.moon_adjusted_target_mean(
        base_target_mean=30.0, dark_sky_target_mean=35.0, moon_alt_deg=None, moon_illumination=None)
    assert result == pytest.approx(35.0)


# ---- should_use_isp (the twilight crossover test) ----------------------

def test_should_use_isp_true_when_no_state_file(appPath):
    # no history yet at all - safest default is to let the ISP keep driving
    assert autoexposure.should_use_isp(appPath, target_mean=30.0, min_exposure_secs=1.0) is True


def test_should_use_isp_true_when_raw_next_below_floor(appPath):
    # a twilight-bright previous frame (1.0s gave mean=229): the unclamped prediction
    # 1.0*(30/229) =~ 0.13s is under the 1.0s floor, so the ISP keeps driving
    write_state(appPath, exposure_secs=1.0, mean=229.0)
    assert autoexposure.should_use_isp(appPath, target_mean=30.0, min_exposure_secs=1.0) is True


def test_should_use_isp_stays_true_after_a_near_black_isp_frame(appPath):
    # an ISP-driven capture at 0.06s measured mean=1.6. Without the upward step cap the
    # plain ratio (1.125s) would exceed the 1.0s floor and hand the next capture to a fixed
    # shutter; with the cap raw_next stays at 0.3s, under the floor, so the ISP keeps driving.
    write_state(appPath, exposure_secs=0.06, mean=1.6)
    assert autoexposure.should_use_isp(appPath, target_mean=30.0, min_exposure_secs=1.0) is True


def test_should_use_isp_false_when_raw_next_at_or_above_floor(appPath):
    # a real night frame: last_exposure=6s measured mean=25, close to target
    # -> raw_next ~= 6*(30/25) = 7.2s, comfortably above the floor
    write_state(appPath, exposure_secs=6.0, mean=25.0)
    assert autoexposure.should_use_isp(appPath, target_mean=30.0, min_exposure_secs=1.0) is False


def test_should_use_isp_stays_stuck_across_a_real_frame_duration_ceiling(appPath):
    # a stuck ISP-sourced state (harvested exposure ~0.06s, at a different gain than
    # fixed-shutter capture) keeps deferring to the ISP: should_use_isp has no way out of it
    # by itself. The escape is the sun-altitude backstop in __main__.py
    # (ae_twilight_isp_backstop_deg), which stops calling it past astronomical twilight.
    for mean_at_ceiling in (1.026, 13.703, 50.787):
        write_state(appPath, exposure_secs=0.06, mean=mean_at_ceiling)
        assert autoexposure.should_use_isp(appPath, target_mean=30.0, min_exposure_secs=1.0) is True


def test_should_use_isp_exits_cleanly_once_isp_reports_a_real_exposure(appPath):
    # a correctly exposed harvested ISP frame (last fixed-shutter frame: exposure=1.93s,
    # mean=34.90, close to target 30) must hand back to fixed-shutter control: the upward
    # step cap must not trap it behind the floor
    write_state(appPath, exposure_secs=1.93, mean=34.904)
    assert autoexposure.should_use_isp(appPath, target_mean=30.0, min_exposure_secs=1.0) is False


def test_should_use_isp_applies_same_saturation_adjustment_as_getExposure(appPath):
    # a cloud reflecting light pollution saturates a 20s exposure (clip_frac=0.6, mean=255).
    # The plain ratio (20*30/255 = 2.35s) is above the floor, the saturation-adjusted value
    # (2.35 / (1+0.6*8) = 0.41s) is below it: True only if should_use_isp applies the same
    # adjustment as getExposure.
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
    # exposure 1.0s, clip_frac 0.42: the plain ratio (1.0*30/229 = 0.131s) overshoots what
    # the frame needed, since a clipped mean says nothing about how far past 255 it was;
    # the severity term pulls the estimate down
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
    # a full moon in the ROI clips a few pixels (clip_frac ~0.002) without the frame being
    # overexposed: no saturation cut
    write_state(appPath, exposure_secs=6.0, mean=45.0, clip_frac=0.002)
    ex = autoexposure.getExposure(11.0, esp_secs=60.0, appPath=appPath,
                                   target_mean=30.0, min_exposure_secs=1.0,
                                   saturation_clip_frac_threshold=0.05,
                                   saturation_severity_gain=8.0)
    assert ex == pytest.approx(6.0 * (30.0 / 45.0), rel=1e-3)


def test_getExposure_backward_compatible_with_state_missing_clip_frac(appPath):
    # state files without a "clip_frac" key still work
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
