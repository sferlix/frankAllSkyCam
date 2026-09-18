'''
Unit tests for skyprojection.py - ephemeris sun/moon position, real-data
calibration sample storage, and the deliberately simple first-iteration
nearest-neighbor lookup (see
docs/superpowers/specs/2026-09-14-cloud-detection-rework-design.md
section 5 - approach B, "no confident data -> don't guess").
'''

import datetime
import os

import pytest

from frankAllSkyCam import skyprojection as sp

# Real site coordinates from this project's own defaults/config.txt, used
# only as plausible real-world inputs for range/sanity checks below - not
# asserting exact ephem output values (no independently-verified reference
# to check against, same reasoning calculateEphem.py's own lack of unit
# tests has historically had - see frankallskycam_twilight_handoff_status
# memory).
LAT, LON, ELEVATION = 44.75, 9.29, 1150


def test_sun_alt_az_below_horizon_at_local_midnight_in_january():
    # 2026-01-15 00:00 local (UTC+1, no DST) = 2026-01-14 23:00 UTC - the
    # Sun must be well below the horizon at this latitude at this hour,
    # regardless of exact ephem precision.
    dt_utc = datetime.datetime(2026, 1, 14, 23, 0, tzinfo=datetime.timezone.utc)

    alt, az = sp.sun_alt_az(dt_utc, LAT, LON, ELEVATION)

    assert alt < -30
    assert 0 <= az < 360


def test_sun_alt_az_above_horizon_near_local_solar_noon_in_june():
    dt_utc = datetime.datetime(2026, 6, 21, 11, 0, tzinfo=datetime.timezone.utc)

    alt, az = sp.sun_alt_az(dt_utc, LAT, LON, ELEVATION)

    assert alt > 40  # near summer solstice, close to solar noon


def test_moon_alt_az_returns_plausible_ranges():
    dt_utc = datetime.datetime(2026, 6, 21, 22, 0, tzinfo=datetime.timezone.utc)

    alt, az = sp.moon_alt_az(dt_utc, LAT, LON, ELEVATION)

    assert -90 <= alt <= 90
    assert 0 <= az < 360
    # A value still in radians (max ~6.28) would also pass the two range
    # checks above, so a missing math.degrees() conversion in moon_alt_az
    # would go completely undetected by this test alone. Confirmed for
    # this fixed date/time that az is ~253.8 degrees, comfortably above
    # 2*pi (~6.283) - this assertion can only pass for a genuinely
    # degrees-scaled azimuth.
    assert az > 6.3


def test_record_and_load_calibration_sample_round_trip(tmp_path):
    csv_path = str(tmp_path / "calibration.csv")

    sp.record_calibration_sample(csv_path, "2026-06-21T22:00:00+00:00", "sun", 45.0, 180.0, 512.0, 384.0)
    sp.record_calibration_sample(csv_path, "2026-06-21T23:00:00+00:00", "moon", 10.0, 90.0, 200.0, 300.0)

    sun_samples = sp.load_calibration_samples(csv_path, "sun")
    moon_samples = sp.load_calibration_samples(csv_path, "moon")

    assert sun_samples == [(45.0, 180.0, 512.0, 384.0)]
    assert moon_samples == [(10.0, 90.0, 200.0, 300.0)]


def test_load_calibration_samples_returns_empty_when_missing(tmp_path):
    csv_path = str(tmp_path / "does_not_exist.csv")

    assert sp.load_calibration_samples(csv_path, "sun") == []


def test_record_calibration_sample_write_failure_does_not_raise(tmp_path, capsys):
    # csv_path's parent directory doesn't exist, so open(..., "a") raises
    # OSError (FileNotFoundError). record_calibration_sample is called
    # from a cron job (tools/skycalibration_collector.py) - it must never
    # let a write failure propagate as a raw traceback, matching this
    # project's established "never a traceback" convention for
    # diagnostic/collector tools (see staticmask.py's own WARNING prints).
    csv_path = str(tmp_path / "no_such_dir" / "calibration.csv")

    sp.record_calibration_sample(csv_path, "2026-06-21T22:00:00+00:00", "sun", 45.0, 180.0, 512.0, 384.0)

    assert "WARNING" in capsys.readouterr().out
    assert not os.path.isfile(csv_path)


def test_lookup_pixel_position_returns_none_when_no_samples():
    assert sp.lookup_pixel_position(45.0, 180.0, []) is None


def test_lookup_pixel_position_returns_nearest_within_range():
    samples = [
        (44.0, 179.0, 500.0, 380.0),   # distance ~1.4 deg from query
        (10.0, 90.0, 200.0, 300.0),    # far away
    ]

    result = sp.lookup_pixel_position(45.0, 180.0, samples, max_distance_deg=5.0)

    assert result == (500.0, 380.0)


def test_lookup_pixel_position_returns_none_when_too_far():
    samples = [(10.0, 90.0, 200.0, 300.0)]  # far from the query position

    result = sp.lookup_pixel_position(45.0, 180.0, samples, max_distance_deg=5.0)

    assert result is None


def test_lookup_pixel_position_handles_azimuth_wraparound():
    # Azimuth is circular: 359° and 1° are only 2° apart, not 358°.
    # A sample at az=359° should be recognized as close to a query at az=1°.
    # This test catches the bug where unwrapped Euclidean az-distance would
    # compute 358° and wrongly reject it as "too far" even with
    # max_distance_deg=5.0.
    samples = [(45.0, 359.0, 500.0, 380.0)]  # true distance: ~2° (alt diff + az wraparound)

    result = sp.lookup_pixel_position(45.0, 1.0, samples, max_distance_deg=5.0)

    # Should find it, not reject it as "too far"
    assert result == (500.0, 380.0)
