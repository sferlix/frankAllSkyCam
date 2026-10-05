'''
Display stretch for fixed-shutter (night and twilight-band) frames, in any exposure mode.

The camera renders the night sky dark: the sky background sits near REFERENCE_BACKGROUND
and --contrast has no effect with --immediate. applyToFile() lifts the midtones with a
fixed curve, so a background at REFERENCE_BACKGROUND lands on the configured brightness,
and grey-balances the sky. It runs on the saved frame after the cloud/star analysis and
the exposure feedback, so no measurement sees the stretched image.

The curve is the same for every frame and the grey-balance gains follow a running
average of the sky colour, so a timelapse does not flicker and real brightness changes
(moonrise, clouds) stay visible; in twilight each frame uses its own sky colour. The grey balance fades out when a colour channel of the
sky is too weak to carry it, and the whole effect fades out between FADE_FULL_SUN_ALT and
FADE_ZERO_SUN_ALT, where the twilight-band frames hand over to the ISP-exposed ones. In
twilight it also fades out with the grey balance, so a colour cast is never brightened.
'''

import json
import os
import time

import cv2
import numpy as np

REFERENCE_BACKGROUND = 32 / 255.0
BLACK_POINT = 4 / 255.0
ROI_RADIUS_RATIO = 0.25          # central sky disc used for the background colour, x image width
LUMA_BGR = np.array([0.114, 0.587, 0.299])

STATE_FILE = "log/display_stretch_state.json"
COLOUR_AVERAGE_WEIGHT = 0.15     # weight of the newest frame in the running sky colour
TWILIGHT_SUN_ALT = -18.0         # above this the sky colour changes too fast to average
STATE_MAX_AGE_SECS = 1800        # older state is ignored (first frame of the night)

NEUTRAL_MIN_CHANNEL = 4 / 255.0  # weakest-channel background (above BLACK_POINT): no grey balance
NEUTRAL_FULL_CHANNEL = 12 / 255.0  # ... full grey balance
GAIN_LIMITS = (0.5, 2.5)

FADE_FULL_SUN_ALT = -12.0
FADE_ZERO_SUN_ALT = -6.0

JPEG_QUALITY = 95


def mtf(x, m):
    # midtones transfer function: 0 -> 0, m -> 0.5, 1 -> 1
    return ((m - 1.0) * x) / ((2.0 * m - 1.0) * x - m)


def midtone_for(target):
    # the midtone that maps REFERENCE_BACKGROUND (after the black point) to target
    ref = (REFERENCE_BACKGROUND - BLACK_POINT) / (1.0 - BLACK_POINT)
    return mtf(ref, target)


def sky_background(image):
    # per-channel median of the central sky disc, after the black point, 0..1 (BGR)
    h, w = image.shape[:2]
    yy, xx = np.ogrid[:h, :w]
    disc = (xx - w / 2.0) ** 2 + (yy - h / 2.0) ** 2 < (ROI_RADIUS_RATIO * w) ** 2
    bg = np.median(image[disc], axis=0) / 255.0
    return np.clip((bg - BLACK_POINT) / (1.0 - BLACK_POINT), 0.0, 1.0)


def neutral_strength(bg):
    # 0..1: how far the sky colour can be grey-balanced, from its weakest channel
    weakest = float(np.min(bg))
    return float(np.clip((weakest - NEUTRAL_MIN_CHANNEL) / (NEUTRAL_FULL_CHANNEL - NEUTRAL_MIN_CHANNEL), 0.0, 1.0))


def neutral_gains(bg):
    # per-channel gains that make bg grey at its own luminance, scaled by neutral_strength
    bg = np.asarray(bg, dtype=np.float64)
    strength = neutral_strength(bg)
    if strength <= 0.0:
        return np.ones(3)
    gains = np.clip(float(LUMA_BGR @ bg) / bg, *GAIN_LIMITS)
    return 1.0 + strength * (gains - 1.0)


def sun_fade(sun_alt):
    # 1 in full night, 0 from FADE_ZERO_SUN_ALT upward
    if sun_alt is None:
        return 1.0
    return float(np.clip((FADE_ZERO_SUN_ALT - sun_alt) / (FADE_ZERO_SUN_ALT - FADE_FULL_SUN_ALT), 0.0, 1.0))


def stretch(image, target, gains, fade=1.0):
    # the displayed frame (uint8 BGR) for image (uint8 BGR)
    a = image.astype(np.float32) / 255.0
    lifted = np.clip((a - BLACK_POINT) / (1.0 - BLACK_POINT), 0.0, 1.0)
    lifted = np.clip(lifted * np.asarray(gains, dtype=np.float32), 0.0, 1.0)
    lifted = mtf(lifted, np.float32(midtone_for(target)))
    out = a + np.float32(fade) * (lifted - a)
    return np.clip(out * 255.0 + 0.5, 0, 255).astype(np.uint8)


def _running_background(app_path, bg, now, weight=COLOUR_AVERAGE_WEIGHT):
    # running average of the sky colour across frames, stored in STATE_FILE
    path = os.path.join(app_path, STATE_FILE)
    try:
        with open(path) as f:
            state = json.load(f)
        if 0 <= now - float(state["time"]) <= STATE_MAX_AGE_SECS:
            bg = (1.0 - weight) * np.asarray(state["bg"], dtype=np.float64) + weight * bg
    except (OSError, ValueError, KeyError, TypeError):
        pass
    try:
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump({"time": now, "bg": [round(float(v), 6) for v in bg]}, f)
        os.replace(tmp, path)
    except OSError as e:
        print("displaystretch: could not save state: " + str(e))
    return bg


def applyToFile(jpg_file_name, app_path, target, neutral_sky=True, sun_alt=None, now=None):
    # stretches the saved frame in place; never raises, leaves the file untouched on failure.
    # Returns True when the file was rewritten.
    try:
        fade = sun_fade(sun_alt)
        if target <= 0 or fade <= 0:
            return False
        image = cv2.imread(jpg_file_name)
        if image is None:
            print("displaystretch: could not read " + jpg_file_name)
            return False
        gains = np.ones(3)
        twilight = sun_alt is not None and sun_alt > TWILIGHT_SUN_ALT
        if neutral_sky or twilight:
            bg = _running_background(app_path, sky_background(image), time.time() if now is None else now,
                                     1.0 if twilight else COLOUR_AVERAGE_WEIGHT)
            if neutral_sky:
                gains = neutral_gains(bg)
            # in twilight a sky whose colour cannot be balanced is left as captured:
            # stretching it would only brighten the colour cast
            if twilight:
                fade *= neutral_strength(bg)
                if fade <= 0:
                    return False
        out = stretch(image, target, gains, fade)
        root, ext = os.path.splitext(jpg_file_name)
        tmp = root + ".stretch" + ext
        try:
            if not cv2.imwrite(tmp, out, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]):
                print("displaystretch: could not write " + tmp)
                return False
            os.replace(tmp, jpg_file_name)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
        return True
    except Exception as e:
        print("displaystretch.applyToFile failed: " + str(e))
        return False
