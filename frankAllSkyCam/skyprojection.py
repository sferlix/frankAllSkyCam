'''
Sky projection calibration: maps a body's (alt, az) to a pixel position for this
camera. The (alt, az) of the Sun and Moon come from the ephemeris; the mapping to
pixels is not a lens formula but is built from observed samples (see
tools/skycalibration_collector.py), and lookups too far from any observed sample
are refused.

lookup_pixel_position is a nearest-neighbor search within a distance cutoff.
'''

import csv
import math
import os

import ephem


DEFAULT_MAX_LOOKUP_DISTANCE_DEG = 5.0  # maximum (alt, az) distance in degrees between a
    # query and the nearest sample; farther queries return None

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
    Appends one calibration sample row to csv_path (header written if the file is new).
    Write failures are printed as a WARNING, not raised (it runs from a cron job).
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
    Nearest-neighbor lookup among the calibration samples. The distance is Euclidean in
    (alt, az) degree space, with the azimuth difference wrapped at 360 degrees.

    Returns (pixel_x, pixel_y) of the nearest sample if within max_distance_deg, else
    None ("no confident answer": callers must not guess).
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
