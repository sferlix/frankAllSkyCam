'''
Unit tests for the moonlight handling of the night cloud estimate in starscalc.py:

1. The expected moonlight (CLOUD_RATE_MOON_COEFF * moon_factor) is subtracted from the
   radiance rate, so a clear moonlit sky reads clear; moonless frames are unchanged.
2. The haze signal is skipped from HAZE_MAX_MOON_FACTOR up.
3. calculateEphem reports the Moon's current altitude, not the one at moonset.

Synthetic arrays; they check the behaviour and the gating.
'''

import datetime
import importlib
import sys
import types

import cv2
import numpy as np
import pytest

from frankAllSkyCam import starscalc as sc

HEIGHT, WIDTH = 768, 1024


def _flat_sky(gray_value):
    gray = np.full((HEIGHT, WIDTH), gray_value, dtype=np.uint8)
    sky = sc.roi_mask(gray, 0.65)
    return gray, sky


# --- 1. radiance rate ---------------------------------------------------------

def test_clear_moonlit_rate_reads_clear():
    # clear sky under moon_factor 0.37 (measured rate ~3.0): mean 30 at 10 s
    gray, sky = _flat_sky(30)
    assert sc._estimate_cloud_cover("x.jpg", gray, sky, sky, 10.0, moon_factor=0.0) > 40.0
    assert sc._estimate_cloud_cover("x.jpg", gray, sky, sky, 10.0, moon_factor=0.37) < 5.0


def test_moonlit_overcast_still_reads_cloudy():
    # overcast under moon_factor 0.47 (measured rate ~13): mean 39 at 3 s
    gray, sky = _flat_sky(39)
    assert sc._estimate_cloud_cover("x.jpg", gray, sky, sky, 3.0, moon_factor=0.47) > 90.0


def test_no_moon_correction_when_moon_is_down_or_unknown():
    gray, sky = _flat_sky(30)
    base = sc._estimate_cloud_cover("x.jpg", gray, sky, sky, 10.0)
    assert sc._estimate_cloud_cover("x.jpg", gray, sky, sky, 10.0, moon_factor=0.0) == base
    assert sc._estimate_cloud_cover("x.jpg", gray, sky, sky, 10.0, moon_factor=None) == base


def test_rate_below_the_moonlight_estimate_reads_zero():
    gray, sky = _flat_sky(10)
    assert sc._estimate_cloud_cover("x.jpg", gray, sky, sky, 10.0, moon_factor=0.9) == 0.0


# --- 2. haze gate -------------------------------------------------------------

def _dark_night_frame(tmp_path):
    img = np.full((HEIGHT, WIDTH, 3), 20, dtype=np.uint8)
    path = str(tmp_path / "dark.jpg")
    cv2.imwrite(path, img)
    return path


@pytest.fixture
def saturated_haze(monkeypatch):
    # no static mask, and a haze signal that always reads fully hazy
    monkeypatch.setattr(sc, "_get_obstruction_mask",
                        lambda gray, roi, is_night, mask_path=None: np.zeros_like(gray))
    monkeypatch.setattr(sc, "_estimate_cloud_cover_haze", lambda gray, sky_mask: 1.0)


def test_haze_counts_with_a_low_moon(tmp_path, saturated_haze):
    _, cloud = sc.analyze_sky_robust(_dark_night_frame(tmp_path), 0.65, 0.4, 30, exposure_secs=100.0,
                                     skip_star_detection=True, moon_factor=0.05)
    assert cloud == 100.0


def test_haze_is_skipped_with_the_moon_well_up(tmp_path, saturated_haze):
    _, cloud = sc.analyze_sky_robust(_dark_night_frame(tmp_path), 0.65, 0.4, 30, exposure_secs=100.0,
                                     skip_star_detection=True, moon_factor=sc.HAZE_MAX_MOON_FACTOR)
    assert cloud == 0.0


# --- 3. calculateEphem moon altitude -------------------------------------------

CONFIG = """[site]
latitude = 44.75
longitude = 9.29
elevation = 100
time_zone = Europe/Rome
inte = n
[system]
logFolder = log/
otuputFolder = img/
"""


def _has_tz_database():
    try:
        from zoneinfo import ZoneInfo
        ZoneInfo("Europe/Rome")
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _has_tz_database(), reason="no IANA time zone database (install tzdata)")
def test_calculate_ephem_reports_the_current_moon_altitude(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / "frankAllSkyCam").mkdir(parents=True)
    (home / "frankAllSkyCam" / "config.txt").write_text(CONFIG)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    # wand needs the ImageMagick library, which calculate() does not use
    for name in ("wand", "wand.image", "wand.drawing", "wand.color"):
        monkeypatch.setitem(sys.modules, name, types.SimpleNamespace(Image=None, Drawing=None, Color=None))
    sys.modules.pop("frankAllSkyCam.calculateEphem", None)
    ce = importlib.import_module("frankAllSkyCam.calculateEphem")
    monkeypatch.setattr(ce, "calculatePlanetsVisibility", lambda dt: {})

    from frankAllSkyCam import skyprojection
    dt = datetime.datetime(2026, 9, 21, 19, 28, tzinfo=datetime.timezone.utc)
    data = ce.calculate(dt)
    expected = skyprojection.moon_alt_az(dt, 44.75, 9.29, 100)[0]
    assert expected > 15.0
    assert data["moonAlt"] == pytest.approx(expected, abs=0.5)
    sys.modules.pop("frankAllSkyCam.calculateEphem", None)
