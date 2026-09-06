'''
One-off tool to build a dark frame library for darksubtract.py.

Run manually, interactively, with the dome/lens physically covered (no
light reaching the sensor - this camera has no shutter, so this can't be
automated mid-sequence). Captures a dark frame at each of a fixed spread
of exposure durations, using the exact same libcamera-still parameters
(additional_night_params, night_mode, night_sharpness, night_contrast) as
a real night capture, saved as lossless PNG (subtracting from a JPEG dark
would reintroduce compression noise). Needs re-running whenever any of
those settings change in config.txt - darksubtract.py checks this and
refuses a stale library rather than silently using it.

Usage:
    python -m frankAllSkyCam.capturedarks
'''

import os
import json
import time
from configparser import ConfigParser
from frankAllSkyCam import fileManager, darksubtract

EXPOSURES_SECS = [5, 15, 30, 45, 60]


def main():
    config = ConfigParser()
    config.read(fileManager.getConfigFileName())

    horiz = str(config['resolution']['horiz'])
    vert = str(config['resolution']['vert'])
    additional_night_params = str(config['libcamera']['additional_night_params'])
    night_mode = str(config['libcamera'].get('night_mode', '')).strip()
    night_sharpness = str(config['libcamera'].get('night_sharpness', '0')).strip()
    night_contrast = str(config['libcamera'].get('night_contrast', '1.0')).strip()

    appPath = os.path.expanduser("~") + "/frankAllSkyCam/"
    darks_dir = os.path.join(appPath, darksubtract.DARKS_DIRNAME)
    os.makedirs(darks_dir, exist_ok=True)

    print("=" * 60)
    print("Cover the dome/lens completely now - no light should reach the sensor.")
    print("This will capture " + str(len(EXPOSURES_SECS)) + " dark frames: " +
          str(EXPOSURES_SECS) + " seconds each, using today's night settings:")
    print("  additional_night_params = " + additional_night_params)
    print("  night_mode = " + (night_mode or "(none)"))
    print("  night_sharpness = " + night_sharpness)
    print("  night_contrast = " + night_contrast)
    input("Press Enter once the dome is covered...")
    print("=" * 60)

    for exp in EXPOSURES_SECS:
        out_path = os.path.join(darks_dir, darksubtract.darkFilename(exp))
        command = "libcamera-still -n -o " + out_path
        command += " --width " + horiz + " --height " + vert
        command += " --immediate --encoding png"
        command += " --shutter " + str(int(exp * 1000000)) + " "
        command += additional_night_params
        if night_mode:
            command += " --mode " + night_mode
        command += " --denoise cdn_hq --sharpness " + night_sharpness + " --contrast " + night_contrast + " "
        print("Capturing " + str(exp) + "s dark -> " + out_path)
        print(command)
        os.system(command)
        time.sleep(1)

    manifest = {
        "additional_night_params": additional_night_params,
        "night_mode": night_mode,
        "night_sharpness": night_sharpness,
        "night_contrast": night_contrast,
        "exposures": EXPOSURES_SECS,
    }
    with open(os.path.join(darks_dir, darksubtract.MANIFEST_FILENAME), "w") as f:
        json.dump(manifest, f, indent=2)

    print("=" * 60)
    print("Done - dark library written to " + darks_dir)
    print("You can uncover the dome now.")


if __name__ == "__main__":
    main()
