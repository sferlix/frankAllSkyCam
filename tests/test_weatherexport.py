'''
Unit tests for weatherexport.buildExportData's pure JSON-shaping logic
(no network, no FTP): station_url="" short-circuits _fetchWS90Sensors, so
these only exercise field construction - the new NightStart/NightEnd
addition in particular.
'''

import datetime

from frankAllSkyCam import weatherexport


def test_night_start_end_are_iso8601_utc():
    # fixed offset, not ZoneInfo("Europe/Rome") - avoids depending on the
    # IANA tzdata package being installed (present on Linux/the Pi by
    # default, not guaranteed on a bare Windows Python)
    tz = datetime.timezone(datetime.timedelta(hours=2))  # CEST, matches September
    when = datetime.datetime(2026, 9, 8, 6, 9, 0, tzinfo=tz)
    night_start = datetime.datetime(2026, 9, 7, 21, 28, 0, tzinfo=tz)
    night_end = datetime.datetime(2026, 9, 8, 5, 12, 0, tzinfo=tz)

    data = weatherexport.buildExportData("", 16.44, 0, 100.0, when, night_start, night_end)

    # Europe/Rome is UTC+2 in September (CEST) - both fields must convert,
    # not just re-format in local time
    assert data["NightStart"] == "2026-09-07T19:28:00Z"
    assert data["NightEnd"] == "2026-09-08T03:12:00Z"
    assert data["timestamp"] == "2026-09-08T04:09:00Z"


def test_missing_station_url_still_produces_zeroed_weather_fields():
    tz = datetime.timezone.utc
    when = datetime.datetime(2026, 9, 8, 4, 9, 0, tzinfo=tz)

    data = weatherexport.buildExportData("", 16.44, 3, 20.0, when, when, when)

    assert data["CloudCover"] == 20.0
    assert data["StarCount"] == 3
    assert data["SkyQuality"] == 16.44
    assert data["Temperature"] == 0.0
