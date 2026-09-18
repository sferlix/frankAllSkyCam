'''
One-off tool to build a master dark frame library for darksubtract.py.

Run manually, interactively, with the dome/lens physically covered (no
light reaching the sensor - this camera has no shutter, so this can't be
automated mid-sequence). Captures DARK_FRAMES_PER_EXPOSURE raw darks at
each of a fixed spread of exposure durations, using the exact same
libcamera-still parameters (additional_night_params, night_mode,
night_sharpness, night_contrast) as a real night capture, and averages
them into one master dark per exposure - see DARK_FRAMES_PER_EXPOSURE's
own comment for why a single dark isn't enough. Saved as lossless PNG
(subtracting from a JPEG dark would reintroduce compression noise). Needs
re-running whenever any of those settings change in config.txt -
darksubtract.py checks this and refuses a stale library rather than
silently using it.

A full session (multiple exposures x multiple frames each, some up to a
minute long) would otherwise race the regular scheduled capture for the
camera, and can run long enough to trip the watchdog's reboot-if-stalled
check - so this pauses both the regular capture job and the watchdog
(see crontab.pauseCaptureJobs()) for the duration, and always restores
them afterward (a crash, Ctrl-C, or the frame-count guard below aborting
all still trigger the restore, via try/finally).

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
DARK_FRAMES_PER_EXPOSURE = 5  # averaged into one master dark per exposure - a
                               # single dark frame's own read/thermal noise gets
                               # subtracted into every light frame right along
                               # with the fixed pattern (hot pixels, dark
                               # current) it's meant to correct, since noise
                               # adds in quadrature rather than cancelling;
                               # averaging N frames reduces that injected noise
                               # by ~sqrt(N) while the fixed pattern - identical
                               # across all N - averages to the same value a
                               # single frame would already show. 5 is a modest
                               # default, not a rigorously tuned one: this
                               # pipeline's JPEG output is already lossy/
                               # nonlinear (see darksubtract.py's own
                               # docstring), so a large stack has diminishing
                               # returns here - raise it if the covered-lens
                               # session length isn't a concern for your install.
MIN_USABLE_FRAMES_PER_EXPOSURE = 2  # below this (e.g. capture failures), refuse
                                     # to average rather than silently build a
                                     # master dark from too little data


def _average_frames(frames):
    '''
    Pixel-wise mean of same-shape frames (as returned by cv2.imread),
    rounded and clipped back to uint8 - builds a master dark from several
    individual dark captures at the same exposure. The fixed pattern (hot
    pixels, dark current) is identical across all N and averages to the
    same value a single frame would already show; each frame's own
    independent read/thermal noise is what actually gets reduced (~sqrt(N)).
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

    # Pausing here, before the interactive prompt below rather than after
    # it: the wait for the user to physically cover the dome and press
    # Enter is itself unbounded, and a regular scheduled capture firing
    # during that wait would already contend with this tool for the camera
    # - see crontab.pauseCaptureJobs()'s own docstring for why the watchdog
    # is paused along with the capture job itself, not just outlasted.
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
