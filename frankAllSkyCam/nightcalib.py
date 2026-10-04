'''
Automatic per-install calibration of the night moon model in starscalc.py.

Every night capture appends one row of sky measurements (starscalc features) to
log/night_calibration_samples.csv. Once the samples cover enough moonless and moonlit
nights, fit() derives the clear-sky constants from them without any labels, and the
result is written to night_calibration.json. starscalc only uses the moon model while
a calibration exists for the current camera settings (fingerprint()); until then the
previous night signals apply.

How the fit finds clear sky without labels:
 - clear moonless sky: moonless frames with at least the median star count and at most
   the 60th-percentile texture; their median rate, star count and colour;
 - moon coefficient: (rate - clear rate) / moon_brightness per moonlit frame; clear sky
   is the darkest sky for its Moon, so the coefficient is taken near the low end
   (K_QUANTILE) and refined as the median of the frames close to it;
 - clear colour: a line through the colour of those clear frames against the Moon's
   share of the clear-sky rate, lowered by COLOUR_MARGIN_MADS median absolute
   deviations as a safety margin.

A calibration is refreshed every RECALIBRATE_DAYS from the last WINDOW_DAYS of samples;
a fit is attempted at most once every ATTEMPT_HOURS. Samples recorded under other camera
settings are ignored, so changing them starts a new calibration.
'''

import csv
import datetime
import hashlib
import json
import os
import statistics

SAMPLES_FILE = "log/night_calibration_samples.csv"
CALIBRATION_FILE = "night_calibration.json"
FIELDS = ["time_utc", "night", "fingerprint", "sun_alt", "moon_brightness", "exposure",
          "rate", "nbr", "tex", "stars", "moon_in_frame"]

WINDOW_DAYS = 60
RECALIBRATE_DAYS = 30
ATTEMPT_HOURS = 24

MOONLESS_MAX_BRIGHTNESS = 0.005
MOONLIT_MIN_BRIGHTNESS = 0.05
MIN_MOONLESS_FRAMES = 100
MIN_MOONLIT_FRAMES = 100
MIN_NIGHTS = 3                  # for both the clear moonless frames and the moonlit frames
MIN_MAX_MOON_BRIGHTNESS = 0.15  # the moonlit frames must include a reasonably bright Moon
MIN_CLEAR_STARS = 30            # a clear moonless sky shows at least this many stars
MIN_CLEAR_MOONLIT_FRAMES = 30
K_QUANTILE = 0.3
COLOUR_MARGIN_MADS = 3.0

BOUNDS = {"clear_rate": (0.01, 100.0), "moon_rate_coeff": (0.5, 1000.0),
          "nbr_clear_dark": (-0.5, 0.8), "nbr_clear_slope": (0.1, 1.5),  # clear sky turns bluer under moonlight
          "clear_star_count": (MIN_CLEAR_STARS, 10000)}


def fingerprint(additional_night_params, night_contrast, night_sharpness, width, height, roi_ratio):
    # short hash of the camera settings the calibration depends on
    key = "|".join(str(v).strip() for v in (additional_night_params, night_contrast, night_sharpness,
                                            width, height, roi_ratio))
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


def record(app_path, features, fp, now=None):
    # append one sample (features filled by starscalc.analyze_sky_robust); never raises
    try:
        if not features or features.get("moon_brightness") is None or features.get("stars") is None:
            return False
        if features["sun_alt"] >= -18.0:
            return False
        now = now or datetime.datetime.now().astimezone()
        night = (now - datetime.timedelta(hours=12)).date().isoformat()
        path = os.path.join(app_path, SAMPLES_FILE)
        new_file = not os.path.exists(path)
        with open(path, "a", newline="") as f:
            w = csv.writer(f)
            if new_file:
                w.writerow(FIELDS)
            w.writerow([now.astimezone(datetime.timezone.utc).isoformat(timespec="seconds"), night, fp,
                        round(features["sun_alt"], 2), round(features["moon_brightness"], 5),
                        round(features["exposure"], 4), round(features["rate"], 5), round(features["nbr"], 4),
                        round(features["tex"], 3), int(features["stars"]), int(features["moon_in_frame"])])
        return True
    except Exception as e:
        print("nightcalib.record failed: " + str(e))
        return False


def load(app_path, fp):
    # the calibration dict for these camera settings, or None
    try:
        with open(os.path.join(app_path, CALIBRATION_FILE)) as f:
            data = json.load(f)
        if data.get("fingerprint") != fp:
            return None
        return data.get("params")
    except Exception:
        return None


def maybe_calibrate(app_path, fp, now=None):
    # fit and save a calibration when none exists for fp or it is due; never raises.
    # Returns the new params, or None when nothing was written.
    try:
        now = now or datetime.datetime.now(datetime.timezone.utc)
        path = os.path.join(app_path, CALIBRATION_FILE)
        state = {}
        if os.path.exists(path):
            with open(path) as f:
                state = json.load(f)
        if _too_soon(state.get("last_attempt"), now, datetime.timedelta(hours=ATTEMPT_HOURS)):
            return None
        if state.get("fingerprint") == fp and state.get("params") and \
                _too_soon(state.get("created"), now, datetime.timedelta(days=RECALIBRATE_DAYS)):
            return None

        since = now - datetime.timedelta(days=WINDOW_DAYS)
        _prune_samples(app_path, since)
        rows = read_samples(app_path, fp, since)
        state["last_attempt"] = now.isoformat(timespec="seconds")
        try:
            params, info = fit(rows)
        except ValueError as e:
            state["last_result"] = "not calibrated: " + str(e)
            _write_json(path, state)
            print("nightcalib: " + state["last_result"])
            return None
        state.update(fingerprint=fp, created=now.isoformat(timespec="seconds"), params=params, info=info,
                     last_result="calibrated")
        _write_json(path, state)
        print("nightcalib: calibrated " + json.dumps(params))
        return params
    except Exception as e:
        print("nightcalib.maybe_calibrate failed: " + str(e))
        return None


def read_samples(app_path, fp, since):
    rows = []
    path = os.path.join(app_path, SAMPLES_FILE)
    if not os.path.exists(path):
        return rows
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            try:
                if r["fingerprint"] != fp or datetime.datetime.fromisoformat(r["time_utc"]) < since:
                    continue
                rows.append(dict(night=r["night"], mb=float(r["moon_brightness"]), rate=float(r["rate"]),
                                 nbr=float(r["nbr"]), tex=float(r["tex"]), stars=float(r["stars"])))
            except (KeyError, ValueError):
                continue
    return rows


def fit(rows):
    # (params, info) from sample rows (keys night, mb, rate, nbr, tex, stars);
    # raises ValueError when the samples are not enough or the result is not plausible
    moonless = [r for r in rows if r["mb"] < MOONLESS_MAX_BRIGHTNESS]
    lit = [r for r in rows if r["mb"] >= MOONLIT_MIN_BRIGHTNESS]
    if len(moonless) < MIN_MOONLESS_FRAMES:
        raise ValueError("%d moonless frames, need %d" % (len(moonless), MIN_MOONLESS_FRAMES))
    if len(lit) < MIN_MOONLIT_FRAMES:
        raise ValueError("%d moonlit frames, need %d" % (len(lit), MIN_MOONLIT_FRAMES))
    if len({r["night"] for r in lit}) < MIN_NIGHTS:
        raise ValueError("moonlit frames from fewer than %d nights" % MIN_NIGHTS)
    if max(r["mb"] for r in lit) < MIN_MAX_MOON_BRIGHTNESS:
        raise ValueError("no frames with a bright enough Moon yet")

    star_cut = _quantile([r["stars"] for r in moonless], 0.5)
    tex_cut = _quantile([r["tex"] for r in moonless], 0.6)
    clear = [r for r in moonless if r["stars"] >= star_cut and r["tex"] <= tex_cut]
    if len({r["night"] for r in clear}) < MIN_NIGHTS:
        raise ValueError("clear moonless frames from fewer than %d nights" % MIN_NIGHTS)
    clear_stars = statistics.median(r["stars"] for r in clear)
    if clear_stars < MIN_CLEAR_STARS:
        raise ValueError("no clear moonless sky yet (median %.0f stars)" % clear_stars)
    clear_rate = statistics.median(r["rate"] for r in clear)

    coeffs = [(r["rate"] - clear_rate) / r["mb"] for r in lit]
    k0 = _quantile(coeffs, K_QUANTILE)
    if k0 <= 0:
        raise ValueError("moonlit frames are not brighter than moonless ones")
    k = statistics.median(c for c in coeffs if 0.6 * k0 <= c <= 1.4 * k0)
    clear_lit = [r for r, c in zip(lit, coeffs) if 0.7 * k <= c <= 1.3 * k]
    if len(clear_lit) < MIN_CLEAR_MOONLIT_FRAMES or len({r["night"] for r in clear_lit}) < MIN_NIGHTS:
        raise ValueError("not enough clear moonlit frames yet")

    points = [(0.0, r["nbr"]) for r in clear]
    for r in clear_lit:
        points.append((k * r["mb"] / (clear_rate + k * r["mb"]), r["nbr"]))
    mx = sum(x for x, _ in points) / len(points)
    my = sum(y for _, y in points) / len(points)
    sxx = sum((x - mx) ** 2 for x, _ in points)
    if sxx <= 0:
        raise ValueError("no colour spread between moonless and moonlit clear frames")
    slope = sum((x - mx) * (y - my) for x, y in points) / sxx
    intercept = my - slope * mx
    mad = statistics.median(abs(y - (intercept + slope * x)) for x, y in points)

    params = dict(clear_rate=round(clear_rate, 4), moon_rate_coeff=round(k, 3),
                  nbr_clear_dark=round(intercept - COLOUR_MARGIN_MADS * mad, 4),
                  nbr_clear_slope=round(slope, 4), clear_star_count=round(clear_stars, 1))
    for name, (lo, hi) in BOUNDS.items():
        if not lo <= params[name] <= hi:
            raise ValueError("%s=%s outside %s..%s" % (name, params[name], lo, hi))
    info = dict(samples=len(rows), moonless=len(moonless), clear_moonless=len(clear), moonlit=len(lit),
                colour_points=len(points), nights=len({r["night"] for r in rows}))
    return params, info


def _prune_samples(app_path, since):
    # drop samples older than since, whatever their fingerprint
    path = os.path.join(app_path, SAMPLES_FILE)
    if not os.path.exists(path):
        return
    with open(path, newline="") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        keep = []
        for row in reader:
            try:
                if datetime.datetime.fromisoformat(row[0]) >= since:
                    keep.append(row)
            except (IndexError, ValueError):
                continue
    tmp = path + ".tmp"
    with open(tmp, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header or FIELDS)
        w.writerows(keep)
    os.replace(tmp, path)


def _quantile(values, q):
    v = sorted(values)
    return v[min(len(v) - 1, max(0, int(round(q * (len(v) - 1)))))]


def _too_soon(iso, now, interval):
    if not iso:
        return False
    try:
        return now - datetime.datetime.fromisoformat(iso) < interval
    except ValueError:
        return False


def _write_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=1)
    os.replace(tmp, path)
