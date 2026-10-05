'''
Display stretch for fixed-shutter (night and twilight-band) frames, in any exposure mode.

The camera renders the night sky dark: the sky background sits near REFERENCE_BACKGROUND
and --contrast has no effect with --immediate. applyToFile() brightens the saved frame
after the cloud/star analysis and the exposure feedback, so no measurement sees it:
 - colour balance in linear light (the camera's tone curve, TONE_CURVE, is undone first),
   to a slightly cool grey for a dark sky or to a moonlit blue under the Moon; balancing
   the encoded values instead would push brighter features (Milky Way, stars) to pink;
 - one fixed midtone curve on brightness only, the same factor for all three channels, so
   a background at REFERENCE_BACKGROUND lands on the configured brightness and hues hold;
 - colour noise smoothed and saturation lowered slightly, and colour faded on features much
   brighter than the sky (stars), whose colour at this scale is mostly debayer artefact;
 - the brightness grain the stretch lifts with the sky smoothed by non-local means.

The curve is the same for every frame and the balance follows a running average of the
sky colour, so a timelapse does not flicker and real brightness changes (moonrise,
clouds) stay visible; in twilight each frame uses its own sky colour. The balance fades
out when a colour channel of the sky is too weak to carry it, and the whole effect fades
out between FADE_FULL_SUN_ALT and FADE_ZERO_SUN_ALT, where the twilight-band frames hand
over to the ISP-exposed ones. In twilight it also fades out with the balance, so a colour
cast is never brightened.
'''

import json
import os
import time

import cv2
import numpy as np

REFERENCE_BACKGROUND = 32 / 255.0
BLACK_POINT = 4 / 255.0
ROI_RADIUS_RATIO = 0.35          # sky disc used for the background colour, x image width
SKY_MIN_GRAY = 12                # darker pixels in it (trees, frame border) are not sky
SKY_MIN_PIXELS = 1000
LUMA_BGR = np.array([0.114, 0.587, 0.299])

# camera tone curve (linear -> encoded, 16-bit pairs), libcamera vc4 imx477 tuning
TONE_CURVE = [0, 0, 1024, 5040, 2048, 9338, 3072, 12356, 4096, 15312, 5120, 18051, 6144, 20790,
              7168, 23193, 8192, 25744, 9216, 27942, 10240, 30035, 11264, 32005, 12288, 33975,
              13312, 35815, 14336, 37600, 15360, 39168, 16384, 40642, 18432, 43379, 20480, 45749,
              22528, 47753, 24576, 49621, 26624, 51253, 28672, 52698, 30720, 53796, 32768, 54876,
              36864, 57012, 40960, 58656, 45056, 59954, 49152, 61183, 53248, 62355, 57344, 63419,
              61440, 64476, 65535, 65535]
_LINEAR = np.array(TONE_CURVE[0::2], dtype=np.float64) / 65535.0
_ENCODED = np.array(TONE_CURVE[1::2], dtype=np.float64) / 65535.0
_TO_LINEAR_LUT = np.interp(np.arange(256) / 255.0, _ENCODED, _LINEAR).astype(np.float32)

STATE_FILE = "log/display_stretch_state.json"
COLOUR_AVERAGE_WEIGHT = 0.15     # weight of the newest frame in the running sky colour
TWILIGHT_SUN_ALT = -18.0         # above this the sky colour changes too fast to average
STATE_MAX_AGE_SECS = 1800        # older state is ignored (first frame of the night)

NEUTRAL_MIN_CHANNEL = 4 / 255.0  # weakest-channel background (above BLACK_POINT): no balance
NEUTRAL_FULL_CHANNEL = 12 / 255.0  # ... full balance
GAIN_LIMITS = (0.4, 3.0)
# balance target (BGR, linear light): a slightly cool grey for a dark sky, blending into
# MOON_TARGET_BGR as the Moon brightens (starscalc.moon_sky_brightness, full at
# MOON_FULL_BRIGHTNESS), since moonlight makes a clear sky genuinely blue and greying it
# turns the Moon salmon
SKY_TARGET_BGR = np.array([1.08, 1.0, 0.92])
MOON_TARGET_BGR = np.array([1.42, 1.0, 0.56])
MOON_FULL_BRIGHTNESS = 0.025

CHROMA_SIGMA_PX = 1.5            # colour (not brightness) smoothing
SATURATION = 0.85
HIGHLIGHT_FADE_ABOVE = 40.0      # luma above the sky background where colour is faded to ...
HIGHLIGHT_COLOUR_KEEP = 0.25     # ... this share
LUMA_DENOISE_H = 4               # non-local means strength on brightness after the stretch; 0 disables

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


def to_linear(encoded):
    # encoded 0..1 values -> linear light, through the inverse TONE_CURVE
    return np.interp(encoded, _ENCODED, _LINEAR)


def to_encoded(linear):
    return np.interp(np.clip(linear, 0.0, 1.0), _LINEAR, _ENCODED).astype(np.float32)


def _sky_pixels(image):
    h, w = image.shape[:2]
    yy, xx = np.ogrid[:h, :w]
    disc = (xx - w / 2.0) ** 2 + (yy - h / 2.0) ** 2 < (ROI_RADIUS_RATIO * w) ** 2
    sky = disc & (cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) > SKY_MIN_GRAY)
    return sky if sky.sum() >= SKY_MIN_PIXELS else disc


def sky_background(image):
    # per-channel median of the sky disc, after the black point, 0..1 (BGR, encoded)
    bg = np.median(image[_sky_pixels(image)], axis=0) / 255.0
    return np.clip((bg - BLACK_POINT) / (1.0 - BLACK_POINT), 0.0, 1.0)


def neutral_strength(bg):
    # 0..1: how far the sky colour can be balanced, from its weakest channel
    weakest = float(np.min(bg))
    return float(np.clip((weakest - NEUTRAL_MIN_CHANNEL) / (NEUTRAL_FULL_CHANNEL - NEUTRAL_MIN_CHANNEL), 0.0, 1.0))


def sky_target(moon_brightness):
    # the colour (BGR, relative, linear light) the sky is balanced to under this Moon
    w = 0.0
    if moon_brightness and moon_brightness > 0:
        w = min(1.0, moon_brightness / MOON_FULL_BRIGHTNESS)
    return SKY_TARGET_BGR + w * (MOON_TARGET_BGR - SKY_TARGET_BGR)


def neutral_gains(bg, target=SKY_TARGET_BGR):
    # linear-light gains that bring the sky background bg (as sky_background() returns it) to
    # target at its own luminance, scaled by neutral_strength
    bg = np.asarray(bg, dtype=np.float64)
    strength = neutral_strength(bg)
    if strength <= 0.0:
        return np.ones(3)
    lin = np.maximum(to_linear(bg * (1.0 - BLACK_POINT) + BLACK_POINT), 1e-6)
    gains = np.clip(float(LUMA_BGR @ lin) / lin, *GAIN_LIMITS) * np.asarray(target, dtype=np.float64)
    return 1.0 + strength * (gains - 1.0)


def sun_fade(sun_alt):
    # 1 in full night, 0 from FADE_ZERO_SUN_ALT upward
    if sun_alt is None:
        return 1.0
    return float(np.clip((FADE_ZERO_SUN_ALT - sun_alt) / (FADE_ZERO_SUN_ALT - FADE_FULL_SUN_ALT), 0.0, 1.0))


def _calm_colour(image, sky):
    # colour smoothed and slightly desaturated, and faded on features far brighter than the sky
    ycc = cv2.cvtColor(image, cv2.COLOR_BGR2YCrCb).astype(np.float32)
    luma = ycc[..., 0]
    sky_luma = float(np.median(luma[sky]))
    keep = SATURATION * (1.0 - (1.0 - HIGHLIGHT_COLOUR_KEEP) *
                         np.clip((luma - sky_luma) / HIGHLIGHT_FADE_ABOVE, 0.0, 1.0))
    for c in (1, 2):
        chroma = cv2.GaussianBlur(ycc[..., c] - 128.0, (0, 0), CHROMA_SIGMA_PX)
        ycc[..., c] = 128.0 + keep * chroma
    ycc = np.clip(ycc + 0.5, 0, 255).astype(np.uint8)
    if LUMA_DENOISE_H > 0:
        # the stretch lifts the sensor grain with the sky; smooth it on brightness only
        ycc[..., 0] = cv2.fastNlMeansDenoising(np.ascontiguousarray(ycc[..., 0]), None, h=LUMA_DENOISE_H,
                                               templateWindowSize=5, searchWindowSize=15)
    return cv2.cvtColor(ycc, cv2.COLOR_YCrCb2BGR)


def stretch(image, target, gains, fade=1.0):
    # the displayed frame (uint8 BGR) for image (uint8 BGR); gains apply in linear light
    linear = _TO_LINEAR_LUT[image] * np.asarray(gains, dtype=np.float32)
    encoded = to_encoded(linear)
    luma = encoded @ LUMA_BGR.astype(np.float32)
    lifted = mtf(np.clip((luma - BLACK_POINT) / (1.0 - BLACK_POINT), 0.0, 1.0), np.float32(midtone_for(target)))
    scale = np.where(luma > 1e-4, lifted / np.maximum(luma, 1e-4), 0.0)[..., None]
    out = encoded * scale
    peak = np.maximum(out.max(axis=2, keepdims=True), 1.0)  # a channel over 1 scales all three
    out = np.clip((out / peak) * 255.0 + 0.5, 0, 255).astype(np.uint8)
    out = _calm_colour(out, _sky_pixels(image)).astype(np.float32)
    original = image.astype(np.float32)
    blended = original + np.float32(fade) * (out - original)
    return np.clip(blended + 0.5, 0, 255).astype(np.uint8)


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


def applyToFile(jpg_file_name, app_path, target, neutral_sky=True, sun_alt=None, now=None, moon_brightness=None):
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
                gains = neutral_gains(bg, sky_target(moon_brightness))
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
