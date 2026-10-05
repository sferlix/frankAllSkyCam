'''
Unit tests for displaystretch.py: the fixed curve, the grey balance and its fade-out,
the sun-altitude fade, the running sky colour and the never-raise file handling.
'''

import os

import cv2
import numpy as np

from frankAllSkyCam import displaystretch as ds


def _frame(bgr, size=(240, 320)):
    return np.full(size + (3,), bgr, dtype=np.uint8)


def _write(tmp_path, bgr, name="frame.jpg"):
    path = str(tmp_path / name)
    cv2.imwrite(path, _frame(bgr), [cv2.IMWRITE_JPEG_QUALITY, 100])
    os.makedirs(tmp_path / "log", exist_ok=True)
    return path


def test_reference_background_lands_on_target():
    ref = int(round(ds.REFERENCE_BACKGROUND * 255))
    out = ds.stretch(_frame((ref, ref, ref)), 0.20, np.ones(3))
    assert abs(int(out[0, 0, 0]) - round(0.20 * 255)) <= 1


def test_curve_keeps_black_white_and_order():
    levels = np.arange(256, dtype=np.uint8).reshape(1, 256, 1).repeat(3, axis=2)
    out = ds.stretch(levels, 0.20, np.ones(3))[0, :, 0].astype(int)
    assert out[0] == 0 and out[255] == 255
    assert np.all(np.diff(out) >= 0)
    assert out[32] > 32  # night sky lifted


def test_grey_balance_neutralises_a_green_sky():
    image = _frame((24, 36, 25))
    out = ds.stretch(image, 0.20, ds.neutral_gains(ds.sky_background(image)))
    b, g, r = out[0, 0].astype(int)
    assert max(b, g, r) - min(b, g, r) <= 2


def test_grey_balance_fades_out_on_a_weak_channel():
    assert ds.neutral_strength(np.array([0.35, 0.12, 0.0])) == 0.0
    assert np.allclose(ds.neutral_gains(np.array([0.35, 0.12, 0.0])), 1.0)
    assert ds.neutral_strength(np.array([0.1, 0.1, 0.1])) == 1.0
    assert 0.0 < ds.neutral_strength(np.array([0.1, 0.1, 8 / 255.0])) < 1.0


def test_sun_fade():
    assert ds.sun_fade(-30.0) == 1.0
    assert ds.sun_fade(None) == 1.0
    assert ds.sun_fade(-5.0) == 0.0
    assert 0.0 < ds.sun_fade(-9.0) < 1.0


def test_night_frame_is_rewritten(tmp_path):
    path = _write(tmp_path, (24, 36, 25))
    assert ds.applyToFile(path, str(tmp_path), 0.20, True, -40.0, now=1000.0)
    b, g, r = cv2.imread(path)[100, 100].astype(int)
    assert min(b, g, r) > 40 and max(b, g, r) - min(b, g, r) <= 3
    assert sorted(os.listdir(tmp_path)) == ["frame.jpg", "log"]  # no temp file left


def test_stretch_without_grey_balance_still_lifts(tmp_path):
    path = _write(tmp_path, (24, 36, 25))
    assert ds.applyToFile(path, str(tmp_path), 0.20, False, -40.0)
    b, g, r = cv2.imread(path)[100, 100].astype(int)
    assert g > 36 and g - b > 5  # brighter, colour kept
    assert not os.path.exists(tmp_path / ds.STATE_FILE)


def test_disabled_or_daylight_leaves_the_file_untouched(tmp_path):
    path = _write(tmp_path, (24, 36, 25))
    before = open(path, "rb").read()
    assert not ds.applyToFile(path, str(tmp_path), 0.0, True, -40.0)
    assert not ds.applyToFile(path, str(tmp_path), 0.20, True, -4.0)
    assert open(path, "rb").read() == before


def test_twilight_colour_cast_is_not_brightened(tmp_path):
    path = _write(tmp_path, (95, 30, 2))  # deep-twilight cobalt: red crushed out
    before = open(path, "rb").read()
    assert not ds.applyToFile(path, str(tmp_path), 0.20, True, -9.0)
    assert open(path, "rb").read() == before
    assert not ds.applyToFile(path, str(tmp_path), 0.20, False, -9.0)
    assert open(path, "rb").read() == before


def test_unreadable_file_never_raises(tmp_path):
    os.makedirs(tmp_path / "log")
    bad = tmp_path / "bad.jpg"
    bad.write_bytes(b"not a jpeg")
    assert not ds.applyToFile(str(bad), str(tmp_path), 0.20, True, -40.0)
    assert bad.read_bytes() == b"not a jpeg"
    assert not ds.applyToFile(str(tmp_path / "missing.jpg"), str(tmp_path), 0.20, True, -40.0)


def test_running_sky_colour_at_night_but_not_in_twilight(tmp_path):
    first = ds.sky_background(_frame((24, 36, 25)))
    second = ds.sky_background(_frame((36, 36, 36)))
    os.makedirs(tmp_path / "log")
    ds._running_background(str(tmp_path), first, 1000.0)
    night = ds._running_background(str(tmp_path), second, 1060.0)
    expected = (1 - ds.COLOUR_AVERAGE_WEIGHT) * first + ds.COLOUR_AVERAGE_WEIGHT * second
    assert np.allclose(night, expected, atol=1e-5)
    twilight = ds._running_background(str(tmp_path), first, 1120.0, weight=1.0)
    assert np.allclose(twilight, first, atol=1e-5)
    stale = ds._running_background(str(tmp_path), second, 1120.0 + ds.STATE_MAX_AGE_SECS + 1)
    assert np.allclose(stale, second, atol=1e-5)
