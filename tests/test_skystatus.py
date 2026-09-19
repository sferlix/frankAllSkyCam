'''
Tests for skystatus: the capture's sky_status.json (UTC times, sun/moon fields, atomic
write, never raising) and its optional FTP upload.
'''

import datetime
import json
import os

from frankAllSkyCam import skystatus

CEST = datetime.timezone(datetime.timedelta(hours=2))  # Europe/Rome in September


def _write(tmp_path, **overrides):
    when = datetime.datetime(2026, 9, 8, 6, 9, 0, tzinfo=CEST)
    args = dict(sqm=16.44, star_count=3, cloud_cover=20.0, when=when,
                night_start=datetime.datetime(2026, 9, 7, 21, 28, 0, tzinfo=CEST),
                night_end=datetime.datetime(2026, 9, 8, 5, 12, 0, tzinfo=CEST))
    args.update(overrides)
    assert skystatus.write_status(str(tmp_path) + os.sep, **args) is True
    with open(tmp_path / skystatus.STATUS_FILENAME, encoding="utf8") as f:
        return json.load(f)


def test_fields_are_iso8601_utc_with_the_local_time_alongside(tmp_path):
    data = _write(tmp_path)

    # Europe/Rome is UTC+2 in September: every instant must be converted,
    # not just re-formatted in local time
    assert data["timestamp"] == "2026-09-08T04:09:00Z"
    assert data["timestamp_local"] == "2026-09-08T06:09:00+02:00"
    assert data["night_start"] == "2026-09-07T19:28:00Z"
    assert data["night_end"] == "2026-09-08T03:12:00Z"


def test_sky_values_are_written_as_given(tmp_path):
    data = _write(tmp_path)
    assert data["sqm"] == 16.44
    assert data["star_count"] == 3
    assert data["cloud_cover"] == 20.0


SUN_MOON = dict(
    sun_rise=datetime.datetime(2026, 9, 8, 7, 4, 0, tzinfo=CEST),
    sun_set=datetime.datetime(2026, 9, 8, 19, 34, 0, tzinfo=CEST),
    moon_rise=datetime.datetime(2026, 9, 8, 13, 3, 0, tzinfo=CEST),
    moon_set=datetime.datetime(2026, 9, 9, 0, 2, 0, tzinfo=CEST),
    moon_illumination=0.5612,
    moon_phase="First Quarter",
)


def test_sun_and_moon_times_are_written_as_utc(tmp_path):
    data = _write(tmp_path, **SUN_MOON)

    assert data["sun_rise"] == "2026-09-08T05:04:00Z"
    assert data["sun_set"] == "2026-09-08T17:34:00Z"
    assert data["moon_rise"] == "2026-09-08T11:03:00Z"
    assert data["moon_set"] == "2026-09-08T22:02:00Z"   # 00:02 local next day


def test_moon_phase_is_the_illuminated_percentage_and_a_name(tmp_path):
    data = _write(tmp_path, **SUN_MOON)   # illuminated fraction 0.5612
    assert data["moon_illumination_pct"] == 56.1
    assert data["moon_phase"] == "First Quarter"
    assert "moon_illumination" not in data


def test_sun_and_moon_fields_are_null_when_not_given(tmp_path):
    data = _write(tmp_path)
    for key in ("sun_rise", "sun_set", "moon_rise", "moon_set", "moon_illumination_pct", "moon_phase"):
        assert key in data and data[key] is None


def test_file_says_nothing_about_a_weather_station(tmp_path):
    _write(tmp_path)
    raw = (tmp_path / skystatus.STATUS_FILENAME).read_text(encoding="utf8").lower()
    assert "ws90" not in raw and "station" not in raw


def test_overwrites_atomically_and_leaves_no_temp_file(tmp_path):
    _write(tmp_path, cloud_cover=10.0)
    data = _write(tmp_path, cloud_cover=55.5)
    assert data["cloud_cover"] == 55.5
    assert sorted(os.listdir(tmp_path)) == [skystatus.STATUS_FILENAME]


def test_a_write_failure_never_raises(tmp_path):
    # capture must never fail because a status file could not be written
    missing = str(tmp_path / "no" / "such" / "dir") + os.sep
    when = datetime.datetime(2026, 9, 8, 6, 9, 0, tzinfo=CEST)
    assert skystatus.write_status(missing, 16.0, 0, 0.0, when, when, when) is False


# --- optional upload of the file to a website ---------------------------------------------

def _uploads(monkeypatch):
    calls = []
    monkeypatch.setattr(skystatus.fileManager, "saveToFTP", lambda *a: calls.append(a))
    return calls


def test_upload_sends_the_status_file_when_enabled(tmp_path, monkeypatch):
    _write(tmp_path)
    calls = _uploads(monkeypatch)

    skystatus.upload_status(str(tmp_path) + os.sep, True, True, "ftp.example.org", "user", "pw",
                            "/your_folder/status/sky_status.json")

    assert calls == [(True, str(tmp_path) + os.sep + skystatus.STATUS_FILENAME, "ftp.example.org",
                      "user", "pw", "/your_folder/status/sky_status.json")]


def test_upload_does_nothing_when_the_flag_is_off(tmp_path, monkeypatch):
    _write(tmp_path)
    calls = _uploads(monkeypatch)
    skystatus.upload_status(str(tmp_path) + os.sep, False, True, "h", "u", "p", "/x.json")
    assert calls == []


def test_upload_does_nothing_without_a_remote_file_name(tmp_path, monkeypatch):
    _write(tmp_path)
    calls = _uploads(monkeypatch)
    skystatus.upload_status(str(tmp_path) + os.sep, True, True, "h", "u", "p", "")
    assert calls == []


def test_upload_does_nothing_when_there_is_no_status_file(tmp_path, monkeypatch):
    calls = _uploads(monkeypatch)   # nothing was written: never upload a missing (or stale) file
    skystatus.upload_status(str(tmp_path) + os.sep, True, True, "h", "u", "p", "/x.json")
    assert calls == []


def test_upload_passes_the_master_ftp_switch_through(tmp_path, monkeypatch):
    # saveToFTP itself returns early when isFTP is False: the flag alone never uploads
    _write(tmp_path)
    calls = _uploads(monkeypatch)
    skystatus.upload_status(str(tmp_path) + os.sep, True, False, "h", "u", "p", "/x.json")
    assert calls[0][0] is False


def test_upload_never_raises(tmp_path, monkeypatch):
    _write(tmp_path)

    def boom(*a):
        raise OSError("connection reset")

    monkeypatch.setattr(skystatus.fileManager, "saveToFTP", boom)
    skystatus.upload_status(str(tmp_path) + os.sep, True, True, "h", "u", "p", "/x.json")

