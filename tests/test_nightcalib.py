'''
Unit tests for nightcalib.py: label-free fit, its refusals, the record/load/
maybe_calibrate cycle and the camera-settings fingerprint.

Synthetic samples drawn from a known clear sky (rate 0.6 + 15 * moon brightness,
colour 0.15 + 0.45 * moon share, 90 stars) mixed with brighter, greyer cloudy frames.
'''

import datetime
import json
import os
import random

import pytest

from frankAllSkyCam import nightcalib as nc

TRUE = dict(clear_rate=0.6, moon_rate_coeff=15.0, nbr_dark=0.15, nbr_slope=0.45, stars=90)


def _sample(night, mb, cloudy, rng):
    clear_rate = TRUE["clear_rate"] + TRUE["moon_rate_coeff"] * mb
    frac = TRUE["moon_rate_coeff"] * mb / clear_rate
    if cloudy:
        return dict(night=night, mb=mb, rate=clear_rate * rng.uniform(1.6, 4.0),
                    nbr=TRUE["nbr_dark"] + TRUE["nbr_slope"] * frac - rng.uniform(0.2, 0.5),
                    tex=rng.uniform(5, 12), stars=rng.randint(0, 8))
    expected_stars = TRUE["stars"] * (TRUE["clear_rate"] / clear_rate) ** 1.5
    return dict(night=night, mb=mb, rate=clear_rate * rng.uniform(0.95, 1.05),
                nbr=TRUE["nbr_dark"] + TRUE["nbr_slope"] * frac + rng.gauss(0, 0.01),
                tex=rng.uniform(3, 4.5), stars=max(0, int(rng.gauss(expected_stars, 5))))


def _month(rng, cloudy_fraction=0.4):
    rows = []
    for n in range(30):
        night = "2026-09-%02d" % (n + 1)
        peak = 0.6 * max(0.0, 1 - abs(n - 15) / 10.0)   # Moon brightest mid-month, none at the ends
        for i in range(40):
            mb = 0.0 if i < 15 else peak * (i - 14) / 25.0
            rows.append(_sample(night, mb, rng.random() < cloudy_fraction, rng))
    return rows


def test_fit_recovers_the_clear_sky():
    params, info = nc.fit(_month(random.Random(1)))
    assert params["clear_rate"] == pytest.approx(TRUE["clear_rate"], rel=0.05)
    assert params["moon_rate_coeff"] == pytest.approx(TRUE["moon_rate_coeff"], rel=0.1)
    assert params["nbr_clear_slope"] == pytest.approx(TRUE["nbr_slope"], abs=0.05)
    # the clear colour is lowered by a safety margin, never raised
    assert TRUE["nbr_dark"] - 0.08 < params["nbr_clear_dark"] < TRUE["nbr_dark"]
    assert params["clear_star_count"] == pytest.approx(TRUE["stars"], rel=0.1)
    assert info["nights"] == 30


def test_fit_refuses_without_moonlit_nights():
    rows = [r for r in _month(random.Random(2)) if r["mb"] == 0.0]
    with pytest.raises(ValueError, match="moonlit"):
        nc.fit(rows)


def test_fit_refuses_when_every_moonless_night_was_cloudy():
    rng = random.Random(3)
    rows = [r for r in _month(rng, 0.0) if r["mb"] > 0] + \
           [_sample("2026-09-%02d" % (n + 1), 0.0, True, rng) for n in range(30) for _ in range(10)]
    with pytest.raises(ValueError, match="clear moonless"):
        nc.fit(rows)


def test_fit_refuses_when_every_moonlit_night_was_cloudy():
    rng = random.Random(7)
    rows = [r for r in _month(rng, 0.0) if r["mb"] == 0.0] +            [_sample(r["night"], r["mb"], True, rng) for r in _month(rng, 0.0) if r["mb"] > 0]
    with pytest.raises(ValueError):
        nc.fit(rows)


def test_fit_refuses_with_too_few_frames():
    with pytest.raises(ValueError, match="moonless frames"):
        nc.fit(_month(random.Random(4))[:50])


FEATURES = dict(sun_alt=-30.0, moon_brightness=0.1, exposure=10.0, rate=2.1, nbr=0.4, tex=4.0,
                stars=20, moon_in_frame=False)


def test_record_writes_only_dark_frames_with_features(tmp_path):
    (tmp_path / "log").mkdir()
    assert nc.record(str(tmp_path), FEATURES, "fp1")
    assert not nc.record(str(tmp_path), dict(FEATURES, sun_alt=-15.0), "fp1")
    assert not nc.record(str(tmp_path), {}, "fp1")
    assert not nc.record(str(tmp_path), dict(FEATURES, moon_brightness=None), "fp1")
    lines = (tmp_path / nc.SAMPLES_FILE).read_text().splitlines()
    assert lines[0].split(",") == nc.FIELDS and len(lines) == 2


def _write_samples(app_path, rows, fp, start):
    os.makedirs(os.path.join(app_path, "log"), exist_ok=True)
    for i, r in enumerate(rows):
        t = start + datetime.timedelta(days=int(r["night"][-2:]) - 1, minutes=i % 40 * 10)
        f = dict(sun_alt=-30.0, moon_brightness=r["mb"], exposure=10.0, rate=r["rate"], nbr=r["nbr"],
                 tex=r["tex"], stars=r["stars"], moon_in_frame=False)
        assert nc.record(app_path, f, fp, now=t)


def test_maybe_calibrate_cycle(tmp_path):
    app = str(tmp_path)
    start = datetime.datetime(2026, 9, 1, 22, tzinfo=datetime.timezone.utc)
    _write_samples(app, _month(random.Random(5)), "fp1", start)
    now = start + datetime.timedelta(days=31)

    assert nc.load(app, "fp1") is None
    params = nc.maybe_calibrate(app, "fp1", now=now)
    assert params is not None and nc.load(app, "fp1") == params
    assert nc.load(app, "fp2") is None                                   # other camera settings

    assert nc.maybe_calibrate(app, "fp1", now=now + datetime.timedelta(hours=1)) is None   # attempted today
    assert nc.maybe_calibrate(app, "fp1", now=now + datetime.timedelta(days=2)) is None    # not due yet
    assert nc.maybe_calibrate(app, "fp1", now=now + datetime.timedelta(days=31)) is not None  # refresh
    # the refresh window keeps only the last WINDOW_DAYS of samples (pruned from the file)
    assert len(nc.read_samples(app, "fp1", start)) < 30 * 40


def test_changed_settings_ignore_old_samples(tmp_path):
    app = str(tmp_path)
    start = datetime.datetime(2026, 9, 1, 22, tzinfo=datetime.timezone.utc)
    _write_samples(app, _month(random.Random(6)), "fp1", start)
    now = start + datetime.timedelta(days=31)
    assert nc.maybe_calibrate(app, "fp2", now=now) is None
    state = json.loads((tmp_path / nc.CALIBRATION_FILE).read_text())
    assert state["last_result"].startswith("not calibrated")


def test_fingerprint_changes_with_camera_settings():
    a = nc.fingerprint("--gain 14 --awbgains 2.7,1.5", "2.5", "0", 1024, 768, 0.65)
    assert a == nc.fingerprint("--gain 14 --awbgains 2.7,1.5 ", "2.5", "0", "1024", "768", 0.65)
    assert a != nc.fingerprint("--gain 10 --awbgains 2.7,1.5", "2.5", "0", 1024, 768, 0.65)
    assert a != nc.fingerprint("--gain 14 --awbgains 2.7,1.5", "2.5", "0", 800, 600, 0.65)
