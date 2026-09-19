'''
One-off tool that builds the master dark frame library for darksubtract.py.

Run it manually with the dome/lens physically covered. For each exposure in
EXPOSURES_SECS it captures DARK_FRAMES_PER_EXPOSURE darks with the same libcamera-still
parameters as a night capture (additional_night_params, night_mode, night_sharpness,
night_contrast), averages them into one master dark and saves it as lossless PNG.
Re-run it whenever one of those settings changes: darksubtract.py refuses a library
captured under different settings.

While it runs, the regular capture job and the watchdog are paused
(crontab.pauseCaptureJobs()) and restored afterward, also on a crash, Ctrl-C or abort
(try/finally).

Usage:
    python -m frankAllSkyCam.capturedarks
'''

import os
import sys
import json
import time
import cv2
import numpy as np
from configparser import ConfigParser
from frankAllSkyCam import fileManager, darksubtract, crontab

EXPOSURES_SECS = [5, 15, 30, 45, 60]
DARK_FRAMES_PER_EXPOSURE = 5  # averaged into one master dark: a single dark adds its own
                               # read/thermal noise to every frame it is subtracted from,
                               # averaging N reduces that by ~sqrt(N)
MIN_USABLE_FRAMES_PER_EXPOSURE = 2  # fewer successful captures than this: refuse to average


def _average_frames(frames):
    '''
    Pixel-wise mean of same-shape frames (cv2.imread arrays), rounded and clipped back
    to uint8. Averaging reduces the random read/thermal noise; the fixed pattern stays.
    '''
    stacked = np.stack([f.astype(np.float32) for f in frames], axis=0)
    return np.clip(np.round(stacked.mean(axis=0)), 0, 255).astype(np.uint8)


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
    print("This will capture " + str(len(EXPOSURES_SECS)) + " exposures x " +
          str(DARK_FRAMES_PER_EXPOSURE) + " frames each (averaged into one " +
          "master dark per exposure): " + str(EXPOSURES_SECS) + " seconds, " +
          "using today's night settings:")
    print("  additional_night_params = " + additional_night_params)
    print("  night_mode = " + (night_mode or "(none)"))
    print("  night_sharpness = " + night_sharpness)
    print("  night_contrast = " + night_contrast)

    # Pause before the interactive prompt: the wait for the user to cover the dome is
    # unbounded and a scheduled capture during it would contend for the camera
    print("Pausing regular captures and the watchdog while this runs...")
    original_crontab = crontab.pauseCaptureJobs()
    try:
        input("Press Enter once the dome is covered...")
        print("=" * 60)

        _captureAllDarks(darks_dir, horiz, vert, additional_night_params,
                          night_mode, night_sharpness, night_contrast)

        manifest = {
            "additional_night_params": additional_night_params,
            "night_mode": night_mode,
            "night_sharpness": night_sharpness,
            "night_contrast": night_contrast,
            "exposures": EXPOSURES_SECS,
            "frames_per_exposure": DARK_FRAMES_PER_EXPOSURE,
        }
        with open(os.path.join(darks_dir, darksubtract.MANIFEST_FILENAME), "w") as f:
            json.dump(manifest, f, indent=2)

        print("=" * 60)
        print("Done - dark library written to " + darks_dir)
        print("You can uncover the dome now.")
    finally:
        print("Restoring your regular capture schedule...")
        crontab.resumeCaptureJobs(original_crontab)


def _captureAllDarks(darks_dir, horiz, vert, additional_night_params,
                      night_mode, night_sharpness, night_contrast):
    for exp in EXPOSURES_SECS:
        out_path = os.path.join(darks_dir, darksubtract.darkFilename(exp))
        frames = []
        expected_shape = None
        for i in range(DARK_FRAMES_PER_EXPOSURE):
            temp_path = os.path.join(darks_dir, "_tmp_" + str(i) + "_" + darksubtract.darkFilename(exp))
            command = fileManager.getCameraBinary() + " -n -o " + temp_path
            command += " --width " + horiz + " --height " + vert
            command += " --immediate --encoding png"
            command += " --shutter " + str(int(exp * 1000000)) + " "
            command += additional_night_params
            if night_mode:
                command += " --mode " + night_mode
            command += " --denoise cdn_hq --sharpness " + night_sharpness + " --contrast " + night_contrast + " "
            print("Capturing " + str(exp) + "s dark " + str(i + 1) + "/" +
                  str(DARK_FRAMES_PER_EXPOSURE) + " -> " + temp_path)
            print(command)
            os.system(command)
            time.sleep(1)

            frame = cv2.imread(temp_path)
            if os.path.isfile(temp_path):
                os.remove(temp_path)
            if frame is None:
                print("WARNING: capture failed or unreadable at " + temp_path + " - skipping this frame")
                continue
            if expected_shape is None:
                expected_shape = frame.shape
            elif frame.shape != expected_shape:
                print("WARNING: " + temp_path + " was " + str(frame.shape) +
                      ", expected " + str(expected_shape) + " - skipping this frame")
                continue
            frames.append(frame)

        if len(frames) < MIN_USABLE_FRAMES_PER_EXPOSURE:
            print("ERROR: only " + str(len(frames)) + " usable frame(s) captured at " +
                  str(exp) + "s (need at least " + str(MIN_USABLE_FRAMES_PER_EXPOSURE) +
                  "). Aborting - check the camera and try again.")
            sys.exit(1)

        master = _average_frames(frames)
        cv2.imwrite(out_path, master)
        print("Averaged " + str(len(frames)) + " frames -> master dark " + out_path)


if __name__ == "__main__":
    main()
