'''
Counts stars and estimates cloud cover from an AllSkyCam JPEG.

Interface: analyze_sky_robust(image_path, diametro_rapporto, sensibilita,
min_contrasto, exposure_secs=None, ...) -> (star_count, cloud_cover_percent).

Both branches mask foreground obstructions (the generated static mask if one
exists, otherwise a per-frame heuristic) and the Sun/Moon with a halo, then
work on the remaining sky, eroded by a guard band.

Night (ROI mean gray <= DAYTIME_MEAN_THRESHOLD):
 - stars: band-pass filter, adaptive per-region threshold, shape filter and
   declustering;
 - cloud cover: the maximum of the radiance rate (mean gray / exposure), the
   cloud-scale texture, the zenith-only broad-glow patchiness ("haze", skipped
   with the Moon in frame) and a floor from too few stars on a dark, moonless
   sky.

Day: no stars are counted; cloud cover is the mean cloud-likeness of the
Normalized Red-Blue Ratio, NRBR = (B-R)/(B+R) (clear sky is blue, cloud is
grey/white). Twilight frames use NRBR (ISP-metered) or texture only (fixed
short shutter); see analyze_sky_robust.

exposure_secs enables the exposure-normalized radiance signal. Without it
(libcamera-still writes no EXIF) the night estimate uses brightness + texture.
'''

import cv2
import numpy as np
import math

from frankAllSkyCam import fileManager, staticmask

try:
    from PIL import Image, ExifTags
except ImportError:
    Image = None

DAYTIME_MEAN_THRESHOLD = 85   # ROI mean gray above this -> day branch

OBSTRUCTION_GRAY_MAX = 20        # night: candidate obstruction pixels are near-black
OBSTRUCTION_MIN_AREA_FRAC = 0.003
OBSTRUCTION_MEAN_MAX = 20        # a candidate component counts if its mean gray is below this

DAY_OBSTRUCTION_WIN = 15         # day: lit foliage is found as high local variance of the
DAY_OBSTRUCTION_HIGHPASS_SIGMA = 4  # high-passed image (window in px, high-pass sigma)
DAY_OBSTRUCTION_BASELINE_MULT = 3.0
DAY_OBSTRUCTION_MARGIN = 3.0

BRIGHT_SOURCE_GRAY_MIN = 235     # candidate Sun/Moon pixel: near-saturated
BRIGHT_SOURCE_MIN_AREA_FRAC = 0.0005  # smallest blob, as a fraction of the ROI
BRIGHT_SOURCE_HALO_FACTOR = 4.0  # halo radius = factor * blob radius + margin (px)
BRIGHT_SOURCE_HALO_MARGIN = 15

GUARD_BAND_PX = 41               # odd kernel size; erodes ~20px around every exclusion edge

STAR_SMALL_SIGMA = 1.0           # denoises, keeps stars (stars are ~1-2px on this lens)
STAR_LARGE_SIGMA = 20            # removes stars, keeps the background/glare trend
STAR_MIN_AREA = 1
STAR_MAX_AREA = 150
STAR_THRESH_PERCENTILE = 99.0    # per-cell adaptive threshold (see _find_stars): each grid cell
STAR_THRESH_GRID_ROWS = 3        # is judged against its own noise floor, so a glow band
STAR_THRESH_GRID_COLS = 4        # across part of the frame doesn't suppress stars elsewhere
STAR_THRESH_MIN_CELL_PIXELS = 500
STAR_MAX_ASPECT = 2.5            # rejects plane/satellite trails

CLUSTER_KERNEL = np.ones((25, 25), np.uint8)
CLUSTER_REJECT_COUNT = 10        # >= this many candidates merging under dilation = foliage, not stars

STAR_CLOUD_GATE_GRID_ROWS = 3    # a star in a grid cell whose texture score reaches the
STAR_CLOUD_GATE_GRID_COLS = 4    # threshold is treated as cloud/foliage texture and dropped
STAR_CLOUD_GATE_MIN_CELL_PIXELS = 200
STAR_CLOUD_GATE_THRESHOLD = 0.3

CLOUD_TEX_SMALL_SIGMA = 6        # texture band-pass: removes star-scale content...
CLOUD_TEX_LARGE_SIGMA = 80       # ...and gradient-scale content (moon glow, vignette)
CLOUD_RATE_LOG_LOW = 0.65        # radiance rate (mean gray / exposure secs) of a clear sky
CLOUD_RATE_LOG_HIGH = 10.0       # ...and of a heavily overcast sky
CLOUD_TEX_LOW = 5.3              # texture std of a clear sky
CLOUD_TEX_HIGH = 14.0            # ...and of structured cloud
CLOUD_BRIGHTNESS_LOW = 33.0      # exposure-less fallback: mean gray of a clear sky
CLOUD_BRIGHTNESS_HIGH = 50.0     # ...and of an overcast sky

CLOUD_TEX_REFERENCE_MEAN = 30.0  # ROI mean gray the texture thresholds are calibrated at; the
                                  # texture-only path scales tex_std by this / actual mean

DAY_NRBR_CLEAR = 0.40            # twilight ISP path only: NRBR of clear blue sky (score 0)...
DAY_NRBR_CLOUD = 0.12            # ...and of white/grey cloud (score 1)
DAY_NRBR_AGG_PERCENTILE = 40     # that path reports this percentile of the per-pixel scores

# Day branch: per-pixel score is linear from 0 (NRBR >= CLEAR) to 1 (NRBR <= CLOUD);
# cloud cover is the mean score. A percentile would read 0 for any sky under ~60% cloud.
# Near sunrise/sunset (sun below ~8 degrees) NRBR whitens and clear sky reads high.
DAY_NRBR_MEAN_CLEAR = 0.40
DAY_NRBR_MEAN_CLOUD = 0.20

# Day branch: the halo around a saturated blob is capped at this fraction of the ROI
# radius, so a large sunlit cloud is not masked away as if it were the Sun. The night
# (Moon) mask is uncapped.
DAY_HALO_MAX_RADIUS_FRAC = 0.45

# Night star-deficit floor: on a dark (sun below -18 deg), moonless sky, very few
# detected stars imply cloud. Floor is 100% at FULL_STARS or fewer, falling linearly
# to 0 at NONE_STARS; never applied with the Moon in frame or without star detection.
STAR_DEFICIT_FULL_STARS = 5
STAR_DEFICIT_NONE_STARS = 20
STAR_DEFICIT_MAX_SUN_ALT_DEG = -18.0
STAR_DEFICIT_MAX_MOON_FACTOR = 0.1

HAZE_BG_SIGMA = 120              # blur that leaves only the broadest glow structure
HAZE_SPREAD_LOW = 11.0           # haze scores 0 at or below this p90-p10 spread of the blurred sky
HAZE_SPREAD_HIGH = 14.0          # ...and 100% at or above this one
HAZE_SPREAD_REFERENCE_MEAN = 30.0  # ROI mean gray the two spreads are calibrated at; the
                                  # measured spread is scaled by this / actual mean

HAZE_INNER_ROI_RATIO = 0.35      # haze is measured over this zenith-only fraction of the ROI


def analyze_sky_robust(image_path, diametro_rapporto=0.75, sensibilita=0.5, min_contrasto=25, exposure_secs=None, twilight_isp_mode=False, twilight_fixed_shutter_band=False, skip_star_detection=False, sun_alt_deg=None, moon_factor=None):
    """
    Conta le stelle e stima la copertura nuvolosa di un frame (giorno o notte).

    INPUT:
    - image_path: percorso del file immagine
    - diametro_rapporto: dimensione della ROI circolare (0.1 - 1.0)
    - sensibilita: parametro per il filtro di circolarita' (0.1 - 1.0)
    - min_contrasto: soglia minima di intensita' per distinguere una stella dal rumore
    - exposure_secs: esposizione applicata, se nota; abilita il segnale radiance-rate
      normalizzato sull'esposizione. Se omesso si prova l'EXIF, poi un fallback
      luminosita'/texture. Ignorato con twilight_isp_mode o twilight_fixed_shutter_band.
    - twilight_isp_mode: frame esposto dall'ISP (luminosita' non informativa): la
      copertura nuvolosa usa NRBR anche di notte.
    - twilight_fixed_shutter_band: shutter fisso molto breve (~0.02s) in fascia
      crepuscolare, con white balance notturno fisso: radiance-rate e NRBR non sono
      applicabili, si usa solo la texture (_estimate_cloud_cover_texture_only).
      Ha priorita' su twilight_isp_mode. Un frame con ROI piu' luminosa di
      DAYTIME_MEAN_THRESHOLD prende comunque il ramo diurno.
    - skip_star_detection: non esegue _find_stars (star_count = None); cloud_cover
      non dipende dal conteggio delle stelle.
    - sun_alt_deg, moon_factor: altezza del Sole (gradi) e moon_brightness_factor()
      (0-1); abilitano il pavimento notturno 'star-deficit' (STAR_DEFICIT_*). Se uno
      dei due e' None il pavimento e' disattivato.

    OUTPUT:
    - star_count: numero di stelle (None se skip_star_detection nel ramo notturno;
      0 nei rami diurno/degenerato)
    - cloud_cover: copertura nuvolosa in percentuale (0-100)
    """
    print("calculating stars on: " + image_path)
    img = cv2.imread(image_path)
    if img is None:
        return 0, 100.0

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    roi = roi_mask(gray, diametro_rapporto)

    if gray[roi == 255].mean() > DAYTIME_MEAN_THRESHOLD:
        return _analyze_day(img, gray, roi)

    obstruction = _get_obstruction_mask(gray, roi, is_night=True)
    bright_source, source_found, _ = _bright_source_mask(gray, roi)

    sky = roi.copy()
    sky[obstruction == 255] = 0
    sky[bright_source == 255] = 0

    if not np.any(sky == 255):
        # entire ROI obstructed/masked out - nothing left to analyze
        return 0, 100.0

    sky_eroded = _erode_guard_band(sky)

    star_count = None if skip_star_detection else _find_stars(gray, sky_eroded, min_contrasto, sensibilita)
    if twilight_fixed_shutter_band:
        cloud_cover = _estimate_cloud_cover_texture_only(gray, sky_eroded)
    elif twilight_isp_mode:
        cloud_cover = _estimate_cloud_cover_nrbr(img, sky_eroded)
    else:
        cloud_cover = _estimate_cloud_cover(image_path, gray, sky, sky_eroded, exposure_secs)
        if not source_found:
            # skipped with the Moon (or another dominant bright source) in frame: its glow
            # dominates the broad-glow spread this signal measures
            haze_cover = _estimate_cloud_cover_haze(gray, sky_eroded)
            cloud_cover = round(max(cloud_cover, 100.0 * haze_cover), 1)
        cloud_cover = round(max(cloud_cover, _star_deficit_floor(star_count, source_found, sun_alt_deg, moon_factor)), 1)

    print("end of starscalc. Stars =" + ("skipped" if star_count is None else str(star_count)) +
          ", clouds = " + str(cloud_cover) + "%" + (" (moon in frame)" if source_found else ""))
    return star_count, cloud_cover


def _analyze_day(img, gray, roi):
    sun_mask, sun_found, _ = _bright_source_mask(gray, roi, max_halo_radius_frac=DAY_HALO_MAX_RADIUS_FRAC)
    obstruction = _get_obstruction_mask(gray, roi, is_night=False)

    sky = roi.copy()
    sky[sun_mask == 255] = 0
    sky[obstruction == 255] = 0

    if not np.any(sky == 255):
        return 0, 100.0

    sky_eroded = _erode_guard_band(sky)

    cloud_cover = _estimate_cloud_cover_nrbr_day(img, sky_eroded)

    print("end of starscalc (day). clouds = " + str(cloud_cover) + "%" +
          (" (sun in frame)" if sun_found else ""))
    return 0, cloud_cover


def _estimate_cloud_cover_nrbr(img, sky_mask):
    # Color-based, so independent of exposure: used for day frames and for
    # twilight_isp_mode frames, whose brightness is set by the ISP's own metering.
    b, _, r = cv2.split(img.astype(np.float64))
    nrbr = (b - r) / (b + r + 1e-6)
    sky_nrbr = nrbr[sky_mask == 255]
    score = np.clip((DAY_NRBR_CLEAR - sky_nrbr) / (DAY_NRBR_CLEAR - DAY_NRBR_CLOUD), 0, 1)
    # percentile of the per-pixel scores, see DAY_NRBR_AGG_PERCENTILE
    return round(100.0 * np.percentile(score, DAY_NRBR_AGG_PERCENTILE), 1)


def _estimate_cloud_cover_nrbr_day(img, sky_mask):
    # Same color signal as _estimate_cloud_cover_nrbr, aggregated as a mean of the
    # linear score (see DAY_NRBR_MEAN_CLEAR/_CLOUD).
    b, _, r = cv2.split(img.astype(np.float64))
    nrbr = (b - r) / (b + r + 1e-6)
    sky_nrbr = nrbr[sky_mask == 255]
    score = np.clip((DAY_NRBR_MEAN_CLEAR - sky_nrbr) / (DAY_NRBR_MEAN_CLEAR - DAY_NRBR_MEAN_CLOUD), 0, 1)
    return round(100.0 * float(np.mean(score)), 1)


def moon_brightness_factor(moon_alt_deg, moon_illumination):
    # 0 (moon down or new) .. 1 (full moon at zenith); None when either input
    # is unknown. Same formula as autoexposure.moon_adjusted_target_mean.
    if moon_alt_deg is None or moon_illumination is None:
        return None
    return max(0.0, math.sin(math.radians(moon_alt_deg))) * max(0.0, min(1.0, moon_illumination))


def _star_deficit_floor(star_count, source_found, sun_alt_deg, moon_factor):
    # Minimum cloud cover (0-100) implied by too few stars on a sky that is
    # known to be fully dark and moonless - see STAR_DEFICIT_*. Returns 0.0
    # (no opinion) whenever any gate is not positively satisfied.
    if star_count is None or source_found:
        return 0.0
    if sun_alt_deg is None or sun_alt_deg >= STAR_DEFICIT_MAX_SUN_ALT_DEG:
        return 0.0
    if moon_factor is None or moon_factor >= STAR_DEFICIT_MAX_MOON_FACTOR:
        return 0.0
    span = STAR_DEFICIT_NONE_STARS - STAR_DEFICIT_FULL_STARS
    return 100.0 * float(np.clip((STAR_DEFICIT_NONE_STARS - star_count) / span, 0.0, 1.0))


def _estimate_cloud_cover_texture_only(gray, sky_mask):
    '''
    Twilight fixed-shutter signal: the same band-pass texture std as
    _estimate_cloud_cover's texture_score (CLOUD_TEX_LOW/HIGH), without the
    radiance-rate term (meaningless at ~0.02s exposures), without the haze signal
    (calibrated for deep night only) and without NRBR (this band uses the night
    fixed white balance, not the ISP's auto balance NRBR is calibrated on).

    tex_std is scaled by CLOUD_TEX_REFERENCE_MEAN / the masked ROI mean, since it
    is an absolute pixel-value std that grows with frame brightness. The scaling
    divides by the mean of the same region the texture is measured over, so a
    large cloud patch much brighter than the rest of the frame damps its own score.
    '''
    small = cv2.GaussianBlur(gray, (0, 0), sigmaX=CLOUD_TEX_SMALL_SIGMA)
    large = cv2.GaussianBlur(gray, (0, 0), sigmaX=CLOUD_TEX_LARGE_SIGMA)
    texture = small.astype(np.float64) - large.astype(np.float64)
    tex_std = texture[sky_mask == 255].std()
    mean_val = gray[sky_mask == 255].mean()
    if mean_val > 0:
        tex_std = tex_std * (CLOUD_TEX_REFERENCE_MEAN / mean_val)
    return round(100.0 * _clip01((tex_std - CLOUD_TEX_LOW) / (CLOUD_TEX_HIGH - CLOUD_TEX_LOW)), 1)


def _erode_guard_band(sky):
    guard = np.ones((GUARD_BAND_PX, GUARD_BAND_PX), np.uint8)
    sky_eroded = cv2.erode(sky, guard)
    if not np.any(sky_eroded == 255):
        sky_eroded = sky  # ROI too small for the guard band; fall back unguarded
    return sky_eroded


def roi_mask(gray, ratio):
    # shared with autoexposure.py: ratio=1.0 -> full width, ratio=0.5 -> circle
    # diameter = 50% of image width, centered in frame
    height, width = gray.shape[:2]
    mask = np.zeros((height, width), dtype=np.uint8)
    radius = int((width * ratio) / 2)
    center = (width // 2, height // 2)
    cv2.circle(mask, center, radius, 255, -1)
    return mask


def _get_obstruction_mask(gray, roi, is_night, mask_path=None):
    '''
    Returns the static mask (staticmask.py, generate_mask.py) when one exists and
    matches the frame's shape, otherwise the per-frame heuristic
    (_obstruction_mask at night, _day_obstruction_mask by day).
    mask_path overrides the production path (for tests).
    '''
    if mask_path is None:
        mask_path = fileManager.getStaticMaskFileName()

    static = staticmask.get_static_mask(gray.shape, mask_path)
    if static is not None:
        return static

    if is_night:
        return _obstruction_mask(gray, roi)
    return _day_obstruction_mask(gray, roi)


def _obstruction_mask(gray, roi):
    # foreground obstructions (trees, structures) are unlit and read near-black,
    # unlike sky background which always retains some floor from airglow/light
    # pollution even on the clearest nights
    candidate = ((gray < OBSTRUCTION_GRAY_MAX) & (roi == 255)).astype(np.uint8) * 255
    n, labels, stats, _ = cv2.connectedComponentsWithStats(candidate, connectivity=8)
    obstruction = np.zeros_like(candidate)
    roi_area = np.sum(roi == 255)
    for i in range(1, n):
        area = stats[i, cv2.CC_STAT_AREA]
        comp_mask = labels == i
        if area > OBSTRUCTION_MIN_AREA_FRAC * roi_area and gray[comp_mask].mean() < OBSTRUCTION_MEAN_MAX:
            obstruction[comp_mask] = 255
    return obstruction


def _bright_source_mask(gray, roi, max_halo_radius_frac=None):
    # Mask of near-saturated blobs (Sun, Moon, bright planet, stray light) plus a halo,
    # so flare and diffraction spikes are not counted as stars (night) or read as
    # cloud (day). Returns (mask, found, centroid of the largest blob or None).
    # max_halo_radius_frac caps the halo radius as a fraction of the ROI radius
    # (None = uncapped).
    candidate = ((gray > BRIGHT_SOURCE_GRAY_MIN) & (roi == 255)).astype(np.uint8) * 255
    n, labels, stats, centroids = cv2.connectedComponentsWithStats(candidate, connectivity=8)
    roi_area = np.sum(roi == 255)
    max_halo_radius = None
    if max_halo_radius_frac is not None:
        max_halo_radius = int(max_halo_radius_frac * math.sqrt(roi_area / math.pi))
    out = np.zeros_like(candidate)
    found = False
    largest_area = 0
    largest_centroid = None
    for i in range(1, n):
        area = stats[i, cv2.CC_STAT_AREA]
        if area > BRIGHT_SOURCE_MIN_AREA_FRAC * roi_area:
            found = True
            cx, cy = centroids[i]
            r = int(math.sqrt(area / math.pi) * BRIGHT_SOURCE_HALO_FACTOR) + BRIGHT_SOURCE_HALO_MARGIN
            if max_halo_radius is not None:
                r = min(r, max_halo_radius)
            cv2.circle(out, (int(cx), int(cy)), r, 255, -1)
            if area > largest_area:
                largest_area = area
                largest_centroid = (float(cx), float(cy))
    return out, found, largest_centroid


def _day_obstruction_mask(gray, roi):
    # daytime trees are lit, not black, so the night obstruction test doesn't
    # apply; foliage instead has strong fine-grained (leaf/branch-edge) texture
    # that smooth sky - blue or overcast - doesn't. High-pass first so a gradual
    # sky gradient near the horizon isn't mistaken for texture.
    g = gray.astype(np.float64)
    highpass = g - cv2.GaussianBlur(g, (0, 0), sigmaX=DAY_OBSTRUCTION_HIGHPASS_SIGMA)
    win = DAY_OBSTRUCTION_WIN
    mean = cv2.blur(highpass, (win, win))
    sq_mean = cv2.blur(highpass * highpass, (win, win))
    local_std = np.sqrt(np.clip(sq_mean - mean * mean, 0, None))

    baseline = np.median(local_std[roi == 255])
    thr = baseline * DAY_OBSTRUCTION_BASELINE_MULT + DAY_OBSTRUCTION_MARGIN
    flagged = ((local_std > thr) & (roi == 255)).astype(np.uint8) * 255
    flagged = cv2.morphologyEx(flagged, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    flagged = cv2.dilate(flagged, np.ones((5, 5), np.uint8))
    return flagged


def _star_threshold_map(residual, sky_mask, min_contrasto):
    # a single whole-frame threshold fails on a part-clear/part-gradient sky
    # (e.g. a light-pollution or cloud-glow band across only part of the
    # frame): the gradient's own residual footprint inflates a global
    # percentile enough to also suppress real faint stars in the genuinely
    # clear part. Computing the percentile per grid cell instead lets each
    # region judge itself against its own local noise floor.
    floor = min_contrasto * 0.3
    all_vals = residual[sky_mask == 255]
    global_thresh = max(floor, np.percentile(all_vals, STAR_THRESH_PERCENTILE))

    h, w = residual.shape
    rows, cols = STAR_THRESH_GRID_ROWS, STAR_THRESH_GRID_COLS
    thresh_grid = np.full((rows, cols), global_thresh, dtype=np.float64)
    cell_h = h // rows + 1
    cell_w = w // cols + 1

    for r in range(rows):
        for c in range(cols):
            y0, y1 = r * cell_h, min((r + 1) * cell_h, h)
            x0, x1 = c * cell_w, min((c + 1) * cell_w, w)
            cell_sky = sky_mask[y0:y1, x0:x1]
            cell_vals = residual[y0:y1, x0:x1][cell_sky == 255]
            if cell_vals.size >= STAR_THRESH_MIN_CELL_PIXELS:
                local_thresh = np.percentile(cell_vals, STAR_THRESH_PERCENTILE)
                # hybrid floor: never let one locally-uniform cell drop far
                # below the whole-frame baseline, or it over-triggers on
                # subtle texture that reads as "high" only in that cell
                thresh_grid[r, c] = max(floor, local_thresh, 0.5 * global_thresh)
            # else: too few sky pixels in this cell for a stable estimate -
            # leave it at global_thresh

    return cv2.resize(thresh_grid, (w, h), interpolation=cv2.INTER_LINEAR)


def _find_stars(gray, sky_mask, min_contrasto, sensibilita):
    small = cv2.GaussianBlur(gray, (0, 0), sigmaX=STAR_SMALL_SIGMA)
    large = cv2.GaussianBlur(gray, (0, 0), sigmaX=STAR_LARGE_SIGMA)
    residual = np.clip(small.astype(np.float64) - large.astype(np.float64), 0, None)

    if not np.any(sky_mask == 255):
        return 0
    thresh_map = _star_threshold_map(residual, sky_mask, min_contrasto)

    binary = (residual > thresh_map).astype(np.uint8) * 255
    binary[sky_mask == 0] = 0

    n, labels, stats, centroids = cv2.connectedComponentsWithStats(binary, connectivity=8)
    circ_target = 0.35 + (sensibilita * 0.35)

    candidates = []
    for i in range(1, n):
        area = stats[i, cv2.CC_STAT_AREA]
        if not (STAR_MIN_AREA <= area <= STAR_MAX_AREA):
            continue
        comp_mask = (labels == i).astype(np.uint8)
        cnts, _ = cv2.findContours(comp_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not cnts:
            continue
        cnt = cnts[0]
        perimeter = cv2.arcLength(cnt, True)
        if perimeter == 0:
            continue
        circularity = 4 * math.pi * area / (perimeter * perimeter)
        if circularity <= circ_target:
            continue
        (_, _), (rw, rh), _ = cv2.minAreaRect(cnt)
        aspect = max(rw, rh) / max(min(rw, rh), 1.0)
        if aspect >= STAR_MAX_ASPECT:
            continue  # elongated: a satellite/plane trail, not a star
        candidates.append(centroids[i])

    survivors = _decluster(candidates, gray.shape)
    if not survivors:
        return 0

    cloud_grid, cell_h, cell_w = _cloud_texture_grid(
        gray, sky_mask, STAR_CLOUD_GATE_GRID_ROWS, STAR_CLOUD_GATE_GRID_COLS
    )
    kept = 0
    for (cx, cy) in survivors:
        r = min(int(cy // cell_h), STAR_CLOUD_GATE_GRID_ROWS - 1)
        c = min(int(cx // cell_w), STAR_CLOUD_GATE_GRID_COLS - 1)
        if cloud_grid[r, c] < STAR_CLOUD_GATE_THRESHOLD:
            kept += 1
    return kept


def _decluster(candidates, shape):
    # real stars are spatially sparse; foliage texture triggers dense clumps of
    # small false candidates. Reject any candidate that merges, under a modest
    # dilation, with several others - keep isolated ones. Returns the surviving
    # (cx, cy) points, not just a count, so callers can filter further.
    if not candidates:
        return []

    pt_mask = np.zeros(shape, dtype=np.uint8)
    for (cx, cy) in candidates:
        cv2.circle(pt_mask, (int(cx), int(cy)), 2, 255, -1)
    dilated = cv2.dilate(pt_mask, CLUSTER_KERNEL)
    _, cluster_labels = cv2.connectedComponents(dilated)

    counts = {}
    labels_per_candidate = []
    for (cx, cy) in candidates:
        lab = cluster_labels[int(cy), int(cx)]
        counts[lab] = counts.get(lab, 0) + 1
        labels_per_candidate.append(lab)

    return [pt for pt, lab in zip(candidates, labels_per_candidate) if counts[lab] < CLUSTER_REJECT_COUNT]


def _cloud_texture_grid(gray, sky_mask, grid_rows, grid_cols):
    # same band-pass texture signal used for whole-frame cloud%, scored per
    # spatial region instead of once for the whole sky - lets a star
    # candidate be judged against the cloud condition of its own neighborhood
    small = cv2.GaussianBlur(gray, (0, 0), sigmaX=CLOUD_TEX_SMALL_SIGMA)
    large = cv2.GaussianBlur(gray, (0, 0), sigmaX=CLOUD_TEX_LARGE_SIGMA)
    texture = small.astype(np.float64) - large.astype(np.float64)

    h, w = gray.shape
    cell_h = h // grid_rows + 1
    cell_w = w // grid_cols + 1
    scores = np.zeros((grid_rows, grid_cols))
    for r in range(grid_rows):
        for c in range(grid_cols):
            y0, y1 = r * cell_h, min((r + 1) * cell_h, h)
            x0, x1 = c * cell_w, min((c + 1) * cell_w, w)
            cell_vals = texture[y0:y1, x0:x1][sky_mask[y0:y1, x0:x1] == 255]
            if cell_vals.size >= STAR_CLOUD_GATE_MIN_CELL_PIXELS:
                tex_std = cell_vals.std()
                scores[r, c] = _clip01((tex_std - CLOUD_TEX_LOW) / (CLOUD_TEX_HIGH - CLOUD_TEX_LOW))
            # else: not enough sky in this cell to judge - leave at 0 (don't suppress)
    return scores, cell_h, cell_w


def _estimate_cloud_cover(image_path, gray, sky, sky_eroded, exposure_secs):
    texture_mask = sky_eroded if np.any(sky_eroded == 255) else sky

    small = cv2.GaussianBlur(gray, (0, 0), sigmaX=CLOUD_TEX_SMALL_SIGMA)
    large = cv2.GaussianBlur(gray, (0, 0), sigmaX=CLOUD_TEX_LARGE_SIGMA)
    texture = small.astype(np.float64) - large.astype(np.float64)
    tex_std = texture[texture_mask == 255].std()
    texture_score = _clip01((tex_std - CLOUD_TEX_LOW) / (CLOUD_TEX_HIGH - CLOUD_TEX_LOW))

    mean_gray = gray[sky == 255].mean()

    if not exposure_secs or exposure_secs <= 0:
        exposure_secs = _read_exposure_seconds(image_path)  # opportunistic EXIF fallback

    if exposure_secs and exposure_secs > 0:
        # exposure known: use the exposure-normalized signal, strictly more
        # informative than raw brightness for the same mean_gray value
        rate = mean_gray / exposure_secs
        brightness_signal = _clip01(
            (math.log(max(rate, 1e-6)) - math.log(CLOUD_RATE_LOG_LOW)) /
            (math.log(CLOUD_RATE_LOG_HIGH) - math.log(CLOUD_RATE_LOG_LOW))
        )
    else:
        # exposure unknown: weaker fallback - clouds still read brighter than a
        # clear sky even without knowing the applied exposure, just less reliably
        # (a very dark clear sky under a long exposure and a moonlit-through-thin
        # -cloud sky under a short one can land close together in raw brightness)
        brightness_signal = _clip01((mean_gray - CLOUD_BRIGHTNESS_LOW) / (CLOUD_BRIGHTNESS_HIGH - CLOUD_BRIGHTNESS_LOW))

    return round(100.0 * max(texture_score, brightness_signal), 1)


def _estimate_cloud_cover_haze(gray, sky_mask):
    '''
    Thin, smooth veil cloud, which the radiance-rate and texture signals miss.

    The gray image is blurred with HAZE_BG_SIGMA, leaving only the broad glow
    structure; the p90-p10 spread of that background is the patchiness. The spread
    is scaled by HAZE_SPREAD_REFERENCE_MEAN / the mean value (it is an absolute
    pixel-value spread) and mapped linearly from HAZE_SPREAD_LOW (0) to
    HAZE_SPREAD_HIGH (1).

    It is measured over the zenith-only sub-ROI (HAZE_INNER_ROI_RATIO): the
    horizon light-pollution glow inflates the spread of the full ROI on clear
    nights. A cloud patch confined to the outer part of the frame is therefore not
    seen by this signal. The caller skips it when the Moon is in frame.
    '''
    inner_roi = roi_mask(gray, HAZE_INNER_ROI_RATIO)
    inner_mask = cv2.bitwise_and(sky_mask, inner_roi)
    if not np.any(inner_mask == 255):
        # zenith fully obstructed: no measurement, let the other signals carry the frame
        return 0.0

    bg = cv2.GaussianBlur(gray.astype(np.float64), (0, 0), sigmaX=HAZE_BG_SIGMA)
    vals = bg[inner_mask == 255]
    spread = np.percentile(vals, 90) - np.percentile(vals, 10)
    mean_val = vals.mean()
    if mean_val > 0:
        spread = spread * (HAZE_SPREAD_REFERENCE_MEAN / mean_val)
    return _clip01((spread - HAZE_SPREAD_LOW) / (HAZE_SPREAD_HIGH - HAZE_SPREAD_LOW))


def _clip01(x):
    return max(0.0, min(1.0, x))


def _read_exposure_seconds(image_path):
    # fallback when the caller passes no exposure_secs (libcamera-still writes no EXIF)
    if Image is None:
        return None
    try:
        with Image.open(image_path) as im:
            exif = im.getexif()
            exif_ifd = exif.get_ifd(0x8769)  # Exif IFD
            val = exif_ifd.get(33434)  # ExposureTime tag
            if val is None:
                return None
            return float(val)
    except Exception:
        return None
