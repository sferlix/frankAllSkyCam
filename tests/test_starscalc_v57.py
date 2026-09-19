'''
Unit tests for the day-time cloud aggregation, the day halo cap and the night
star-deficit floor in starscalc.py:

1. Day cloud cover is the mean of the linear NRBR score (a 40th percentile would read
   0 for any sky under ~60% cloud).
2. The day bright-source halo is capped, so a large sunlit cloud is not masked away as
   if it were the Sun.
3. Night star-deficit floor: very few stars on a dark, moonless sky imply cloud (100%
   at <= 5 stars, fading to 0 at 20).

Synthetic arrays; they check the behaviour and the gating.
'''

import cv2
import numpy as np
import pytest

from frankAllSkyCam import starscalc as sc

HEIGHT, WIDTH = 768, 1024  # matches this install's configured capture resolution


def _nrbr_img(cloud_fraction):
    img = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
    split = int(HEIGHT * cloud_fraction)
    img[:split, :] = (150, 150, 150)  # BGR: B == R -> NRBR 0, cloud-like
    img[split:, :] = (200, 120, 50)   # NRBR 0.6, clear blue
    return img


FULL_MASK = np.full((HEIGHT, WIDTH), 255, dtype=np.uint8)


# --- 1. day aggregation ------------------------------------------------------

def test_day_mean_reports_a_partly_cloudy_sky_instead_of_zero():
    # 30% cloud (a 40th percentile would read exactly 0.0 here)
    result = sc._estimate_cloud_cover_nrbr_day(_nrbr_img(0.30), FULL_MASK)
    assert result == pytest.approx(30.0, abs=1.0)


def test_day_mean_extremes():
    assert sc._estimate_cloud_cover_nrbr_day(_nrbr_img(0.0), FULL_MASK) == 0.0
    assert sc._estimate_cloud_cover_nrbr_day(_nrbr_img(1.0), FULL_MASK) == 100.0


def test_day_mean_is_linear_between_the_anchors():
    # a uniform sky exactly midway between DAY_NRBR_MEAN_CLEAR and _CLOUD
    mid = (sc.DAY_NRBR_MEAN_CLEAR + sc.DAY_NRBR_MEAN_CLOUD) / 2.0
    # NRBR = (B-R)/(B+R): pick B,R so it equals mid
    b, r = 100 * (1 + mid), 100 * (1 - mid)
    img = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
    img[:, :] = (round(b), 100, round(r))
    assert sc._estimate_cloud_cover_nrbr_day(img, FULL_MASK) == pytest.approx(50.0, abs=1.5)


def test_twilight_nrbr_function_is_left_alone():
    # the shared percentile version still serves twilight_isp_mode frames
    assert sc._estimate_cloud_cover_nrbr(_nrbr_img(0.30), FULL_MASK) == 0.0


# --- 2. halo cap ----------------------------------------------------------------

def _roi_and_gray_with_saturated_blob(radius):
    gray = np.full((HEIGHT, WIDTH), 120, dtype=np.uint8)
    cv2.circle(gray, (300, 384), radius, 255, -1)
    return gray, sc.roi_mask(gray, 0.65)


def test_halo_is_capped_when_a_cap_is_given():
    gray, roi = _roi_and_gray_with_saturated_blob(90)
    roi_radius = np.sqrt((roi == 255).sum() / np.pi)

    uncapped, found, _ = sc._bright_source_mask(gray, roi)
    capped, found_c, _ = sc._bright_source_mask(gray, roi, max_halo_radius_frac=0.45)

    assert found and found_c
    assert (capped == 255).sum() < (uncapped == 255).sum()
    ys, xs = np.nonzero(capped)
    assert xs.max() - 300 <= 0.45 * roi_radius + 1


def test_default_bright_source_mask_is_unchanged():
    # night branch (Moon) and the collectors call it without the new argument
    gray, roi = _roi_and_gray_with_saturated_blob(60)
    a, _, _ = sc._bright_source_mask(gray, roi)
    b, _, _ = sc._bright_source_mask(gray, roi, max_halo_radius_frac=None)
    assert np.array_equal(a, b)


def test_day_analysis_still_sees_cloud_beside_a_large_saturated_blob(tmp_path, monkeypatch):
    # blue sky; a big unsaturated white cloud on the left; a large saturated
    # core inside it. Uncapped, the 4x halo swallows the whole cloud.
    img = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
    img[:, :] = (200, 120, 50)
    img[:, :512] = (200, 200, 200)                # cloud body, gray 200 < 235
    cv2.circle(img, (300, 384), 90, (255, 255, 255), -1)  # saturated core
    path = tmp_path / "day.jpg"
    cv2.imwrite(str(path), img)
    monkeypatch.setattr(sc.staticmask, "get_static_mask", lambda shape, p: None)

    _, cloud = sc.analyze_sky_robust(str(path), diametro_rapporto=0.65)

    assert cloud >= 15.0


# --- 3. night star-deficit floor ---------------------------------------------------

DARK = dict(sun_alt_deg=-25.0, moon_factor=0.0)


def test_star_floor_ramp_on_a_dark_moonless_sky():
    f = sc._star_deficit_floor
    assert f(0, False, **DARK) == 100.0
    assert f(5, False, **DARK) == 100.0
    assert f(10, False, **DARK) == pytest.approx(100.0 * 10 / 15)
    assert f(14, False, **DARK) == pytest.approx(40.0)
    assert f(20, False, **DARK) == 0.0
    assert f(80, False, **DARK) == 0.0


def test_star_floor_is_off_unless_the_sky_is_known_dark():
    f = sc._star_deficit_floor
    assert f(2, False, sun_alt_deg=None, moon_factor=0.0) == 0.0     # sun altitude unknown
    assert f(2, False, sun_alt_deg=-25.0, moon_factor=None) == 0.0   # moon unknown
    assert f(2, False, sun_alt_deg=-12.0, moon_factor=0.0) == 0.0    # astronomical twilight
    assert f(2, False, sun_alt_deg=-25.0, moon_factor=0.5) == 0.0    # bright moon up
    assert f(2, True, **DARK) == 0.0                                  # moon/bright source in frame
    assert f(None, False, **DARK) == 0.0                              # star detection skipped


def test_star_floor_raises_the_reported_cloud_cover(tmp_path, monkeypatch):
    monkeypatch.setattr(sc, "_find_stars", lambda *a, **k: 2)
    monkeypatch.setattr(sc, "_estimate_cloud_cover", lambda *a, **k: 10.0)
    monkeypatch.setattr(sc, "_estimate_cloud_cover_haze", lambda *a, **k: 0.0)
    monkeypatch.setattr(sc.staticmask, "get_static_mask", lambda shape, p: None)
    path = tmp_path / "night.jpg"
    cv2.imwrite(str(path), np.full((HEIGHT, WIDTH, 3), 30, dtype=np.uint8))

    _, without = sc.analyze_sky_robust(str(path), 0.65, 0.4, 30, exposure_secs=40.0)
    _, with_floor = sc.analyze_sky_robust(str(path), 0.65, 0.4, 30, exposure_secs=40.0, **DARK)
    _, skipped = sc.analyze_sky_robust(str(path), 0.65, 0.4, 30, exposure_secs=40.0,
                                       skip_star_detection=True, **DARK)

    assert without == 10.0        # unchanged when the caller doesn't say it is dark
    assert with_floor == 100.0
    assert skipped == 10.0        # no star count -> no floor


def test_star_floor_never_lowers_an_already_high_reading(tmp_path, monkeypatch):
    monkeypatch.setattr(sc, "_find_stars", lambda *a, **k: 12)   # floor would be ~53
    monkeypatch.setattr(sc, "_estimate_cloud_cover", lambda *a, **k: 80.0)
    monkeypatch.setattr(sc, "_estimate_cloud_cover_haze", lambda *a, **k: 0.0)
    monkeypatch.setattr(sc.staticmask, "get_static_mask", lambda shape, p: None)
    path = tmp_path / "night.jpg"
    cv2.imwrite(str(path), np.full((HEIGHT, WIDTH, 3), 30, dtype=np.uint8))

    _, cloud = sc.analyze_sky_robust(str(path), 0.65, 0.4, 30, exposure_secs=40.0, **DARK)

    assert cloud == 80.0


# --- moon factor helper ----------------------------------------------------------------

def test_moon_brightness_factor_matches_the_autoexposure_formula():
    assert sc.moon_brightness_factor(None, 0.5) is None
    assert sc.moon_brightness_factor(30.0, None) is None
    assert sc.moon_brightness_factor(-10.0, 1.0) == 0.0            # below horizon
    assert sc.moon_brightness_factor(90.0, 1.0) == pytest.approx(1.0)
    assert sc.moon_brightness_factor(30.0, 0.4) == pytest.approx(0.2)
