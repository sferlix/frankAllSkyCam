'''
Analyzes an AllSkyCam JPEG to count stars and estimate cloud cover.

Approach (see docs/design discussion): a fixed brightness threshold and a
star-count-derived cloud formula both fail badly across real conditions
(fully overcast skies mis-read as clear, clear skies mis-read as cloudy),
and neither accounts for the Moon or for tree silhouettes intruding into
the analysis circle. This version:

 - excludes foreground obstructions (trees, structures) and the Moon disk
   (plus its flare/diffraction-spike halo) from analysis, detected directly
   from the image itself rather than from lens/site calibration data;
 - finds stars via band-pass filtering (isolates point sources from both
   the smooth background and broad glare) with a per-image adaptive
   threshold (median + MAD, not a fixed constant), followed by shape
   filtering (circularity, elongation) and spatial declustering to reject
   dense clumps of false triggers (the signature of foliage texture,
   distinct from sparse real stars);
 - estimates cloud cover from three independent physical signals: sky
   radiance rate (mean brightness / exposure time - clouds reach the same
   brightness in a much shorter exposure than the camera's own adaptive
   exposure would pick for clear sky), mid-scale ("cloud-scale") texture,
   isolated by band-pass from both star-scale and gradient-scale content,
   and (night only, see _estimate_cloud_cover_haze) broad-scale background
   patchiness - thin/smooth veil cloud is invisible to the other two (it
   raises neither the radiance rate enough at typical exposures nor the
   band-pass texture, which is actually calibrated the other way: real
   clear-sky texture at that scale, from faint stars/sensor noise, reads
   *higher* than a smoothing veil does), but still breaks up the sky's
   otherwise smooth glow into patches at a much coarser scale than either.

Daytime frames get a separate branch (no stars to find; different cloud
physics): trees are lit rather than black, so obstruction is detected via
local high-pass texture instead of near-black pixels - no real-star content
competes with it during the day, unlike at night. Cloud cover is estimated
via the Normalized Red-Blue Ratio (NRBR = (B-R)/(B+R)), a standard
sky-camera technique: clear sky is strongly blue (Rayleigh scattering), a
cloud is white/gray (R roughly equal to B). The Sun is masked the same way
the Moon is at night (large near-saturated blob + halo).

Interface: analyze_sky_robust(image_path, diametro_rapporto, sensibilita,
min_contrasto, exposure_secs=None) -> (star_count, cloud_cover_percent).
Day/night and Moon awareness are self-contained (derived from the image
itself). exposure_secs is optional (default None, fully backward
compatible): pass it when the caller already knows the applied exposure
(as __main__.py does) for accurate exposure-normalized cloud detection -
libcamera-still on this platform does not embed EXIF, so without it,
cloud detection falls back to a weaker texture+brightness-only estimate.
'''

import cv2
import numpy as np
import math

try:
    from PIL import Image, ExifTags
except ImportError:
    Image = None

DAYTIME_MEAN_THRESHOLD = 85   # ROI mean above this -> day branch (night max observed ~58, a real
                               # midday-sun frame measured 115; well clear of both)

OBSTRUCTION_GRAY_MAX = 20        # candidate foreground-obstruction pixel: near-black (night only)
OBSTRUCTION_MIN_AREA_FRAC = 0.003
OBSTRUCTION_MEAN_MAX = 20        # a real tree canopy mixes near-black gaps with lit branch
                                  # highlights; requiring the whole component's mean under 10
                                  # was rejecting genuine ambient-lit trees entirely (verified:
                                  # 20 still doesn't false-trigger on clear-sky control images)

DAY_OBSTRUCTION_WIN = 15         # local-variance window: lit foliage is high-frequency textured,
DAY_OBSTRUCTION_HIGHPASS_SIGMA = 4  # unlike smooth sky (blue or overcast) - no real-star content
DAY_OBSTRUCTION_BASELINE_MULT = 3.0  # competes with this signal during the day, unlike at night
DAY_OBSTRUCTION_MARGIN = 3.0

BRIGHT_SOURCE_GRAY_MIN = 235     # candidate Sun/Moon/flare pixel: near-saturated
BRIGHT_SOURCE_MIN_AREA_FRAC = 0.0005
BRIGHT_SOURCE_HALO_FACTOR = 4.0
BRIGHT_SOURCE_HALO_MARGIN = 15

GUARD_BAND_PX = 41               # odd kernel size; ~20px margin around every exclusion edge

STAR_SMALL_SIGMA = 1.0           # keeps stars, denoises - tuned for a 17mm fisheye's very
                                  # small (often ~1-2px) star footprint; lower still (0.6-0.8)
                                  # gets noticeably less stable, higher over-smooths real stars
STAR_LARGE_SIGMA = 20            # removes stars, keeps background/glare trend
STAR_MIN_AREA = 1
STAR_MAX_AREA = 150
STAR_THRESH_PERCENTILE = 99.0    # per-region adaptive threshold (see _find_stars)
STAR_THRESH_GRID_ROWS = 3        # a single whole-frame threshold fails when the sky is
STAR_THRESH_GRID_COLS = 4        # part-clear/part-gradient (e.g. a light-pollution or
STAR_THRESH_MIN_CELL_PIXELS = 500  # cloud-glow band across only part of the frame)
STAR_MAX_ASPECT = 2.5            # rejects plane/satellite trails

CLUSTER_KERNEL = np.ones((25, 25), np.uint8)
CLUSTER_REJECT_COUNT = 10        # >=10 candidates merging under dilation = foliage texture, not stars.
                                  # Real star groupings of a handful within 25px happen constantly by
                                  # chance in any real starfield - a low threshold here was rejecting
                                  # up to ~50% of genuine stars. Now mostly a backstop: the obstruction
                                  # mask + guard-band erosion do the actual foliage/edge rejection.

STAR_CLOUD_GATE_GRID_ROWS = 3    # a star sitting in a region that independently reads as cloud-like
STAR_CLOUD_GATE_GRID_COLS = 4    # (same texture signal as cloud%, scored per-region instead of for
STAR_CLOUD_GATE_MIN_CELL_PIXELS = 200  # the whole frame) is almost certainly cloud/foliage texture,
STAR_CLOUD_GATE_THRESHOLD = 0.3  # not a real star - handles partly-cloudy frames without a single
                                  # whole-frame cloud% cutoff either wiping out real stars in the
                                  # clear part or letting cloud texture through in the cloudy part

CLOUD_TEX_SMALL_SIGMA = 6        # removes star-scale content
CLOUD_TEX_LARGE_SIGMA = 80       # removes gradient-scale content (moon glow, vignette)
CLOUD_RATE_LOG_LOW = 0.65        # calibrated clear-sky radiance rate (mean gray / exposure secs)
CLOUD_RATE_LOG_HIGH = 10.0       # calibrated heavily-overcast radiance rate
CLOUD_TEX_LOW = 5.3              # calibrated clear-sky texture std
CLOUD_TEX_HIGH = 14.0            # calibrated structured-cloud texture std
CLOUD_BRIGHTNESS_LOW = 33.0      # calibrated clear-sky mean gray (no exposure normalization)
CLOUD_BRIGHTNESS_HIGH = 50.0     # calibrated overcast mean gray

DAY_NRBR_CLEAR = 0.40            # calibrated clear-blue-sky NRBR (zenith measured ~0.53, margin
                                  # kept for natural whitening toward the horizon under clear sky)
DAY_NRBR_CLOUD = 0.12            # calibrated white/gray NRBR (measured on Sun-flare/near-white
                                  # pixels as a stand-in for overcast, which reads the same way:
                                  # R roughly equal to B)

HAZE_BG_SIGMA = 120              # heavy enough to discard both star-scale and cloud-scale
                                  # ("texture") content, keeping only the broadest glow structure
HAZE_SPREAD_LOW = 6.0            # calibrated clear-sky p90-p10 spread of that broad background
                                  # (max observed 5.6 across 3 real clear-sky reference captures)
HAZE_SPREAD_HIGH = 14.0          # calibrated patchy-cloud/moon-behind-cloud spread (10.6-12.6
                                  # observed on real partly-cloudy and moon-behind-cloud captures) -
                                  # small reference set (6 real images); revisit if false-flagging
                                  # a genuinely clear night, or missing an actually hazy one


def analyze_sky_robust(image_path, diametro_rapporto=0.75, sensibilita=0.5, min_contrasto=25, exposure_secs=None, twilight_isp_mode=False):
    """
    Analizza il cielo notturno per contare le stelle e stimare la copertura nuvolosa.

    INPUT:
    - image_path: percorso del file immagine
    - diametro_rapporto: dimensione della ROI circolare (0.1 - 1.0)
    - sensibilita: parametro per il filtro di circolarita' (0.1 - 1.0)
    - min_contrasto: soglia minima di intensita' per distinguere una stella dal rumore
    - exposure_secs: durata di esposizione applicata (se nota); migliora la stima
      delle nuvole. Se omesso, si tenta l'EXIF del file e infine un fallback
      basato solo su luminosita'/texture. Ignorato se twilight_isp_mode=True.
    - twilight_isp_mode: True se lo scatto e' stato esposto dall'ISP (twilight
      handoff) anziche' con uno shutter fisso/predetto - in tal caso la
      luminosita' e' normalizzata dall'ISP stesso e non e' informativa per le
      nuvole (stesso motivo per cui il branch diurno usa NRBR invece della
      luminosita'), quindi la copertura nuvolosa usa NRBR anche di notte.

    OUTPUT:
    - star_count: numero di stelle rilevate
    - cloud_cover: percentuale di copertura nuvolosa (0-100)
    """
    print("calculating stars on: " + image_path)
    img = cv2.imread(image_path)
    if img is None:
        return 0, 100.0

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    roi = roi_mask(gray, diametro_rapporto)

    if gray[roi == 255].mean() > DAYTIME_MEAN_THRESHOLD:
        return _analyze_day(img, gray, roi)

    obstruction = _obstruction_mask(gray, roi)
    bright_source, source_found = _bright_source_mask(gray, roi)

    sky = roi.copy()
    sky[obstruction == 255] = 0
    sky[bright_source == 255] = 0

    if not np.any(sky == 255):
        # entire ROI obstructed/masked out - nothing left to analyze
        return 0, 100.0

    sky_eroded = _erode_guard_band(sky)

    star_count = _find_stars(gray, sky_eroded, min_contrasto, sensibilita)
    if twilight_isp_mode:
        cloud_cover = _estimate_cloud_cover_nrbr(img, sky_eroded)
    else:
        cloud_cover = _estimate_cloud_cover(image_path, gray, sky, sky_eroded, exposure_secs)
        if not source_found:
            # skipped with the Moon (or another dominant bright source) in
            # frame - its glow extends well beyond _bright_source_mask's
            # halo at this signal's HAZE_BG_SIGMA smoothing scale, and
            # confounds the same broad-glow-patchiness signal this measures
            # (confirmed on a real clear+Moon reference: spread 23.5, higher
            # than any real cloud case measured). Only real gap this leaves:
            # thin veil cloud specifically while the Moon is also in frame -
            # falls back to the two signals above, same as before this signal
            # existed.
            haze_cover = _estimate_cloud_cover_haze(gray, sky_eroded)
            cloud_cover = round(max(cloud_cover, 100.0 * haze_cover), 1)

    print("end of starscalc. Stars =" + str(star_count) + ", clouds = " + str(cloud_cover) +
          "%" + (" (moon in frame)" if source_found else ""))
    return star_count, cloud_cover


def _analyze_day(img, gray, roi):
    sun_mask, sun_found = _bright_source_mask(gray, roi)
    obstruction = _day_obstruction_mask(gray, roi)

    sky = roi.copy()
    sky[sun_mask == 255] = 0
    sky[obstruction == 255] = 0

    if not np.any(sky == 255):
        return 0, 100.0

    sky_eroded = _erode_guard_band(sky)

    cloud_cover = _estimate_cloud_cover_nrbr(img, sky_eroded)

    print("end of starscalc (day). clouds = " + str(cloud_cover) + "%" +
          (" (sun in frame)" if sun_found else ""))
    return 0, cloud_cover


def _estimate_cloud_cover_nrbr(img, sky_mask):
    # Color-based (Normalized Red-Blue Ratio), not brightness-based: clear
    # sky is strongly blue, cloud is white/gray (R roughly equal to B),
    # regardless of exposure. Shared with the daytime branch, which needs
    # this same exposure-independence for the same reason: both daytime and
    # twilight_isp_mode frames are ISP auto-exposed, so brightness is
    # normalized by the ISP's own metering and carries little information
    # about cloud cover - unlike a night frame captured at a fixed/predicted
    # shutter speed, where the radiance-rate heuristic in
    # _estimate_cloud_cover applies instead.
    b, _, r = cv2.split(img.astype(np.float64))
    nrbr = (b - r) / (b + r + 1e-6)
    sky_nrbr = nrbr[sky_mask == 255]
    score = np.clip((DAY_NRBR_CLEAR - sky_nrbr) / (DAY_NRBR_CLEAR - DAY_NRBR_CLOUD), 0, 1)
    return round(100.0 * score.mean(), 1)


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


def _bright_source_mask(gray, roi):
    # the Sun or Moon (or any other dominant bright source: a bright planet, a
    # stray light) shows up as a large near-saturated blob; mask it plus a
    # generous halo so its flare and diffraction spikes can't be miscounted as
    # stars (night) or read as white/cloud-like via NRBR (day)
    candidate = ((gray > BRIGHT_SOURCE_GRAY_MIN) & (roi == 255)).astype(np.uint8) * 255
    n, labels, stats, centroids = cv2.connectedComponentsWithStats(candidate, connectivity=8)
    roi_area = np.sum(roi == 255)
    out = np.zeros_like(candidate)
    found = False
    for i in range(1, n):
        area = stats[i, cv2.CC_STAT_AREA]
        if area > BRIGHT_SOURCE_MIN_AREA_FRAC * roi_area:
            found = True
            cx, cy = centroids[i]
            r = int(math.sqrt(area / math.pi) * BRIGHT_SOURCE_HALO_FACTOR) + BRIGHT_SOURCE_HALO_MARGIN
            cv2.circle(out, (int(cx), int(cy)), r, 255, -1)
    return out, found


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
    Catches thin/smooth veil cloud that both signals above miss: confirmed on
    a real capture (SQM 21.31, Exp 48.02s, 70 stars still visible) that read
    3.3% cloud despite a visible broad veil - its mean_gray (34.2) and
    cloud-scale tex_std (4.4) both landed inside the range measured on
    genuinely clear reference nights (mean_gray 32-36, tex_std 3.0-4.0), so
    neither existing signal had anything to key off. The gap: cloud-scale
    texture (_estimate_cloud_cover) is calibrated on the assumption that
    cloud reads as *more* texture than clear sky at that band-pass scale -
    true for structured/cumulus cloud, backwards for a smooth veil, which
    reads as *less* texture than the faint-star/sensor-noise floor a clear
    sky already has there.

    A thin veil is still real cloud, though, and light pollution scattering
    through it still breaks the sky's otherwise smooth glow into patches -
    just at a much coarser scale than either existing signal's band-pass
    isolates. Heavily blurring past both star-scale and cloud-scale content
    (HAZE_BG_SIGMA) leaves only that broad structure, and its p90-p10 spread
    across the sky area is measurably tighter on a real clear night (max 5.6
    across 3 references) than on a real patchy/hazy one (10.6-12.6 across a
    partly-cloudy and a moon-behind-cloud reference) - see analyze_sky_robust
    for the source_found gate this needs (the Moon's glow at this smoothing
    scale is itself an even larger confound: 23.5 on a real clear+Moon
    reference, higher than any real cloud case measured).

    Calibrated on 6 real images total (3 clear, 3 cloudy/hazy) - the
    smallest reference set of any signal in this module. Revisit
    HAZE_SPREAD_LOW/HIGH if this over- or under-reports in practice.
    '''
    bg = cv2.GaussianBlur(gray.astype(np.float64), (0, 0), sigmaX=HAZE_BG_SIGMA)
    vals = bg[sky_mask == 255]
    spread = np.percentile(vals, 90) - np.percentile(vals, 10)
    return _clip01((spread - HAZE_SPREAD_LOW) / (HAZE_SPREAD_HIGH - HAZE_SPREAD_LOW))


def _clip01(x):
    return max(0.0, min(1.0, x))


def _read_exposure_seconds(image_path):
    # opportunistic fallback for callers that don't pass exposure_secs directly;
    # confirmed absent on this platform's libcamera-still output, kept in case a
    # different build/config does embed it
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
