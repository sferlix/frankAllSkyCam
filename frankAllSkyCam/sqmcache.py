'''
Reuse of the last night SQM reading between measurements ([sqm] sqm_interval_minutes).

At night the pseudo-SQM takes up to four extra captures (about 11 s of camera time) before
every frame. The night sky brightness changes slowly, so with an interval above 1 minute
the last reading is reused until it is that old, which leaves more of each minute for the
exposure itself.
'''

import json
import os
import time

CACHE_FILE = "log/sqm_last.json"
SLACK_SECS = 30   # cron start jitter must not turn a due measurement into a reuse


def load(app_path, interval_minutes, now=None):
    # (sqm, sqm_le) of the last reading while it is younger than interval_minutes, else None
    if interval_minutes <= 1:
        return None
    try:
        with open(os.path.join(app_path, CACHE_FILE)) as f:
            cached = json.load(f)
        age = (time.time() if now is None else now) - float(cached["time"])
        if 0 <= age < interval_minutes * 60 - SLACK_SECS:
            return float(cached["sqm"]), cached["sqm_le"]
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


def save(app_path, sqm, sqm_le, now=None):
    # stores a reading for load(); never raises
    path = os.path.join(app_path, CACHE_FILE)
    try:
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump({"time": time.time() if now is None else now, "sqm": sqm, "sqm_le": sqm_le}, f)
        os.replace(tmp, path)
    except OSError as e:
        print("sqmcache: could not save: " + str(e))
