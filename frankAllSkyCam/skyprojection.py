'''
Sky projection calibration - the foundation for geometric sun/moon masking
(and, later, star-catalog matching), see
docs/superpowers/specs/2026-09-14-cloud-detection-rework-design.md section 5.

Deliberately does NOT compute pixel positions from a lens formula (approach
A, rejected in the spec - a formula assumed correct would mask a
confidently wrong region if either the assumed lens model or the camera's
mounting rotation is off). Instead: ephemeris gives the astronomically
EXACT (alt, az) for any timestamp (no calibration needed, ephem is already
accurate) - what actually needs calibrating is the mapping from (alt, az)
to a pixel position for THIS specific camera, and that mapping is built
here purely from real observed data (see
tools/skycalibration_collector.py), with an explicit refusal to answer for
any query too far from what has actually been observed.

This is a first iteration (see spec section 5/10 and the plan header this
module was built under): lookup_pixel_position is deliberately the
simplest safe thing that could work - nearest-neighbor within a distance
cutoff - not the more sophisticated parametric fisheye model discussed as
a possible future refinement once real accumulated data shows the need.
'''

import csv
import math
import os

import ephem


DEFAULT_MAX_LOOKUP_DISTANCE_DEG = 5.0  # initial default, not yet validated -
    # how far (in the simple Euclidean alt/az distance below) a query
    # position may be from the nearest real calibration sample before this
    # refuses to answer. Revisit once real calibration data shows the
    # actual nearest-neighbor pixel error at a given distance.

_CALIBRATION_CSV_HEADER = ["timestamp_utc", "body", "alt_deg", "az_deg", "pixel_x", "pixel_y"]


def _observer(dt_utc, lat, lon, elevation):
    site = ephem.Observer()
    site.lat = str(lat)
    site.lon = str(lon)
    site.elevation = elevation
    site.date = dt_utc  # ephem expects UTC
    return site


def sun_alt_az(dt_utc, lat, lon, elevation):
    '''dt_utc must be a timezone-aware or naive-but-UTC datetime.'''
    site = _observer(dt_utc, lat, lon, elevation)
    sun = ephem.Sun(site)
    sun.compute(site)
    return math.degrees(sun.alt), math.degrees(sun.az)


def moon_alt_az(dt_utc, lat, lon, elevation):
    '''dt_utc must be a timezone-aware or naive-but-UTC datetime.'''
    site = _observer(dt_utc, lat, lon, elevation)
    moon = ephem.Moon(site)
    moon.compute(site)
    return math.degrees(moon.alt), math.degrees(moon.az)


def record_calibration_sample(csv_path, timestamp_utc_iso, body, alt_deg, az_deg, pixel_x, pixel_y):
    '''
    Appends one calibration sample row to csv_path, writing the header
    first if the file doesn't exist yet. Called from a cron job (see
    tools/skycalibration_collector.py) - any write failure here (e.g. a
    permissions or disk-space problem) is caught and reported as a
    WARNING print rather than propagated, matching this project's
    established "never a raw traceback out of a diagnostic/collector
    tool" convention (see staticmask.py's own WARNING prints).
    '''
    try:
        file_exists = os.path.isfile(csv_path)
        with open(csv_path, "a", newline="") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(_CALIBRATION_CSV_HEADER)
            writer.writerow([timestamp_utc_iso, body, alt_deg, az_deg, pixel_x, pixel_y])
    except OSError as e:
        print("WARNING: could not write calibration sample to " + str(csv_path) +
              " - " + str(e))


def load_calibration_samples(csv_path, body):
    '''Returns a list of (alt_deg, az_deg, pixel_x, pixel_y) tuples for the given body ("sun" or "moon").'''
    if not os.path.isfile(csv_path):
        return []
    samples = []
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["body"] != body:
                continue
            samples.append((float(row["alt_deg"]), float(row["az_deg"]), float(row["pixel_x"]), float(row["pixel_y"])))
    return samples


def lookup_pixel_position(alt_deg, az_deg, samples, max_distance_deg=DEFAULT_MAX_LOOKUP_DISTANCE_DEG):
    '''
    Nearest-neighbor lookup among real calibration samples. Distance is a
    simple Euclidean distance in (alt, az) degree-space, not a true
    great-circle angular distance - a deliberate first-iteration
    simplification. This distorts near the poles of that coordinate system
    (alt near +/-90), but real sun/moon positions relevant to this camera's
    sky-facing ROI stay well away from those poles, so the distortion is
    not expected to matter in practice - not yet empirically confirmed.

    Azimuth is handled as a circular coordinate: the distance is computed
    using wrapped azimuth delta to correctly handle the 0°/360° wraparound
    (e.g., az=359° is only 2° away from az=1°, not 358°).

    Returns (pixel_x, pixel_y) of the nearest sample if within
    max_distance_deg, else None - callers must treat None as "no confident
    answer", falling back to whatever they did before this lookup existed
    (see docs/superpowers/specs/2026-09-14-cloud-detection-rework-design.md
    section 5's "no confident data -> don't guess" contract). No caller in
    this plan consumes this yet; wiring it into live masking is a later
    plan (spec section 6/7), once real accumulated data exists to validate
    against.
    '''
    if not samples:
        return None

    best = None
    best_dist = None
    for sample_alt, sample_az, pixel_x, pixel_y in samples:
        # Compute wrapped azimuth distance to handle circular nature of azimuth
        az_delta = abs(az_deg - sample_az)
        az_delta = min(az_delta, 360.0 - az_delta)
        dist = math.hypot(alt_deg - sample_alt, az_delta)
        if best_dist is None or dist < best_dist:
            best_dist = dist
            best = (pixel_x, pixel_y)

    if best_dist is None or best_dist > max_distance_deg:
        return None
    return best
