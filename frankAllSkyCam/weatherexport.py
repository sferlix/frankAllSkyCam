'''
 combines SQM/star-count/cloud-cover from the current capture, tonight's
 astronomical-twilight night start/end (see calculateEphem.py), and a live
 reading from your WS90-style weather station, into a single JSON file
 published to the same FTP site as the AllSkyCam image (see
 [weather_export] in config.txt).

 Fetches station_url directly (config.txt's own [weather_export] section)
 rather than reusing generateExtraData.py's persisted ws90_data.json, so
 this feature stays independent of that script's own config file
 (generateExtraData.conf) and cron schedule.

 Runs on every capture, day and night (see __main__.py's call site) - the
 weather-station reading and cloud cover are meaningful around the clock.
 SQM and star count are the exception: both are already forced to 0 outside
 a real dark-sky exposure by their own producers (sqmreader.readSQM's
 daytime branch, starscalc._analyze_day), the same rule SQM measurement
 itself follows, so this module never has to gate on time of day itself -
 it just publishes whatever it's given.
'''

import os
import json
import datetime
import urllib.request
from frankAllSkyCam import fileManager

LOCAL_JSON_FILENAME = "weather.json"

# short and single-attempt on purpose: this runs inside the main capture
# loop (every 1-2 minutes at night), which the rest of the codebase is
# careful to keep fast (see __main__.py's camera-lock release comment) - a
# slow/unreachable station must degrade to "zeros for this run" almost
# immediately, not stall the next scheduled capture. Unlike
# generateExtraData.py's own apiCallJson (3 retries, exponential backoff,
# worst case ~14s), which is fine on that script's own 5-minute cadence but
# not here.
FETCH_TIMEOUT_SECS = 3


def _fetchWS90Sensors(station_url):
    if not station_url:
        return {}
    try:
        # some hosts (e.g. a shared-hosting WAF in front of a published
        # feed) reject urllib's default/short UA strings with a 406 - a
        # full browser-style one works reliably (same fix already applied
        # in generateExtraData.py's own fetch)
        req = urllib.request.Request(station_url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT_SECS) as response:
            data = json.loads(response.read().decode('utf-8'))
        return data.get("sensors", {})
    except Exception as e:
        print("WARNING: could not fetch " + station_url + ": " + str(e))
        return {}


def _sensorValue(sensors, key, fallback_key=None, default=0.0):
    # station unreachable / no station_url configured / key missing from
    # this particular payload (e.g. a WS90 firmware without a given sensor)
    # all look the same here: fall back to a safe default rather than
    # raise, since a missing weather reading must never block the export
    # of the (independently valid) SQM/star count/cloud cover fields.
    entry = sensors.get(key)
    if entry is None and fallback_key:
        entry = sensors.get(fallback_key)
    if entry is None:
        return default
    return entry.get("value", default)


def buildExportData(station_url, sqm, star_count, cloud_cover, when, night_start, night_end):
    sensors = _fetchWS90Sensors(station_url)

    return {
        "timestamp": when.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        # from calculateEphem.calculate()'s tz-aware nightStartDt/nightEndDt
        # (astronomical twilight, sun at -18deg) - same UTC ISO8601 format
        # as timestamp above, not the "HH:MM+1"-style string the on-image
        # overlay uses, which a generic JSON consumer can't parse.
        "NightStart": night_start.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "NightEnd": night_end.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "CloudCover": cloud_cover,
        "DewPoint": _sensorValue(sensors, "dewpoint"),
        "Humidity": _sensorValue(sensors, "humidity_u8", fallback_key="humidity"),
        "Pressure": _sensorValue(sensors, "pressure"),
        "SeaLevelPressure": _sensorValue(sensors, "pressure_msl"),
        # no rate sensor in the WS90 payload - rain_status (0/1 "is it
        # raining right now") is the closest available signal, by request.
        "RainRate": _sensorValue(sensors, "rain_status"),
        "SkyQuality": sqm,
        # illuminance (lux) is an ambient-light reading from the station,
        # not the same physical quantity as SQM's mag/arcsec2 - reads ~0 at
        # night regardless of real sky darkness/moon, but it's the only
        # "brightness" field the station provides.
        "SkyBrightness": _sensorValue(sensors, "illuminance"),
        "Temperature": _sensorValue(sensors, "temperature_s"),
        "UVIndex": _sensorValue(sensors, "uv"),
        "WindDirection": _sensorValue(sensors, "wind_direction"),
        "WindSpeed": _sensorValue(sensors, "wind_speed"),
        "WindGust": _sensorValue(sensors, "wind_speed_2"),
        "StarCount": star_count,
    }


def exportAndUpload(appPath, station_url, sqm, star_count, cloud_cover, when,
                     night_start, night_end,
                     isFTP, FTP_server, FTP_login, FTP_pass, FTP_fileName):
    export_data = buildExportData(station_url, sqm, star_count, cloud_cover, when,
                                   night_start, night_end)

    local_path = appPath + LOCAL_JSON_FILENAME
    try:
        with open(local_path, "w", encoding='utf8') as f:
            json.dump(export_data, f, indent=2)
    except Exception as e:
        print("ERROR writing " + local_path + ": " + str(e))
        return

    fileManager.saveToFTP(isFTP, local_path, FTP_server, FTP_login, FTP_pass, FTP_fileName)
