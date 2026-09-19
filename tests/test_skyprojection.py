'''
Unit tests for skyprojection.py: ephemeris sun/moon position, calibration sample
storage and the nearest-neighbor lookup (None when there is no confident answer).
'''

import datetime
import os

import pytest

from frankAllSkyCam import skyprojection as sp

# site coordinates from defaults/config.txt: plausible inputs for range and sanity
# checks, not exact ephem values
LAT, LON, ELEVATION = 44.75, 9.29, 1150


def test_sun_alt_az_below_horizon_at_local_midnight_in_january():
    # 2026-01-15 00:00 local (UTC+1, no DST) = 2026-01-14 23:00 UTC: the Sun must be well
    # below the horizon at this latitude at this hour
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
    # a value still in radians (max ~6.28) would pass the range checks above; at this fixed
    # date/time az is ~253.8 degrees, above 2*pi, so this only passes for degrees
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
    # csv_path's parent directory doesn't exist, so open(..., "a") raises OSError:
    # record_calibration_sample runs from a cron job and must not propagate it
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
    # azimuth is circular: a sample at az=359 is close to a query at az=1 (about 2 degrees
    # apart, not 358), so it must be found within max_distance_deg=5.0
    samples = [(45.0, 359.0, 500.0, 380.0)]  # true distance: about 2 degrees (alt diff + az wraparound)

    result = sp.lookup_pixel_position(45.0, 1.0, samples, max_distance_deg=5.0)

    # found, not rejected as too far
    assert result == (500.0, 380.0)
