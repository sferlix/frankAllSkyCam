'''
Keeps a small archive of night frames exactly as the cloud and star analysis saw them
(before the display stretch and the watermark), for checking the analysis later.
At most one frame every INTERVAL_MINUTES is kept, for KEEP_DAYS.
'''

import os
import shutil
import time

RAW_DIR = "log/raw_frames"
INTERVAL_MINUTES = 30
KEEP_DAYS = 14


def save(app_path, jpg_file_name, now=None):
    # copies the frame when the newest archived one is old enough and prunes expired ones;
    # never raises. Returns True when the frame was copied.
    try:
        now = now if now is not None else time.time()
        folder = os.path.join(app_path, RAW_DIR)
        os.makedirs(folder, exist_ok=True)
        newest = 0.0
        for name in os.listdir(folder):
            path = os.path.join(folder, name)
            mtime = os.path.getmtime(path)
            if mtime < now - KEEP_DAYS * 86400:
                os.remove(path)
            else:
                newest = max(newest, mtime)
        if newest > now - (INTERVAL_MINUTES - 1) * 60:
            return False
        target = os.path.join(folder, os.path.basename(jpg_file_name))
        shutil.copyfile(jpg_file_name, target)
        os.utime(target, (now, now))
        return True
    except Exception as e:
        print("rawframes.save failed: " + str(e))
        return False
