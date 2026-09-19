'''
The capture's own sky numbers - SQM, star count, cloud cover, night start/end, sun and
moon rise/set, moon phase and illumination - written after every capture to
sky_status.json in the app folder, and optionally uploaded to an FTP server
(upload_status, enabled by the customer in config.txt).

It is independent of any weather station: WS90 data is exported separately, as its
own JSON, by tools/generateExtraData.py.

Best-effort: a failure to write or upload never fails a capture.
'''

import datetime
import json
import os

from frankAllSkyCam import fileManager

STATUS_FILENAME = "sky_status.json"


def _utc(dt):
    return None if dt is None else dt.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_status(app_path, sqm, star_count, cloud_cover, when, night_start, night_end,
                 sun_rise=None, sun_set=None, moon_rise=None, moon_set=None,
                 moon_illumination=None, moon_phase=None):
    '''
    when, night_start, night_end and the sun/moon times are timezone-aware
    datetimes. night_* are astronomical twilight (sun at -18deg). sun_rise is the
    next sunrise while the sun is below the horizon and the last one otherwise;
    moon_rise likewise; sun_set and moon_set are the next ones (as on the overlay).
    moon_illumination is the illuminated fraction (0 new .. 1 full), written as a
    percentage (moon_illumination_pct); moon_phase is a name.
    Anything not given is written as null.

    sqm and star_count are 0 outside a real dark-sky exposure and published as given.
    Returns True on success, False (after printing why) on failure. Written via a temp
    file + rename so a reader never sees a half-written file.
    '''
    status = {
        "timestamp": _utc(when),
        # ISO8601 with a numeric offset, for anything that wants the site's
        # own wall-clock time without redoing the UTC conversion
        "timestamp_local": when.isoformat(timespec="seconds"),
        "night_start": _utc(night_start),
        "night_end": _utc(night_end),
        "sun_rise": _utc(sun_rise),
        "sun_set": _utc(sun_set),
        "moon_rise": _utc(moon_rise),
        "moon_set": _utc(moon_set),
        "moon_illumination_pct": None if moon_illumination is None else round(100.0 * moon_illumination, 1),
        "moon_phase": moon_phase,
        "sqm": sqm,
        "star_count": star_count,
        "cloud_cover": cloud_cover,
    }
    path = os.path.join(app_path, STATUS_FILENAME)
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf8") as f:
            json.dump(status, f, indent=2)
        os.replace(tmp, path)
        return True
    except Exception as e:
        print("WARNING: could not write " + path + ": " + str(e))
        return False


def upload_status(app_path, enabled, is_ftp, ftp_server, ftp_login, ftp_pass, remote_path):
    '''
    Uploads sky_status.json to the FTP server (fileManager.saveToFTP, with its socket
    timeout) when the customer has enabled it. Does nothing if not enabled, without a
    remote file name, or without a status file. is_ftp is the master FTP switch,
    honoured by saveToFTP. Never raises. Returns True if an upload was attempted.
    '''
    path = os.path.join(app_path, STATUS_FILENAME)
    if not enabled or not remote_path or not os.path.isfile(path):
        return False
    try:
        fileManager.saveToFTP(is_ftp, path, ftp_server, ftp_login, ftp_pass, remote_path)
        return True
    except Exception as e:
        print("WARNING: could not upload " + path + ": " + str(e))
        return False
