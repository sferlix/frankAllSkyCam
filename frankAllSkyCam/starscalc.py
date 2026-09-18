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
the Moon is at night (large near-saturated blob + halo). The per-pixel
NRBR score is aggregated via a percentile, not the mean - see
DAY_NRBR_AGG_PERCENTILE - since a wide fisheye ROI also picks up genuine
non-cloud whitening (circumsolar aureole, horizon-ward Rayleigh whitening)
that contaminates a minority of sky pixels without it being cloud.

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

from frankAllSkyCam import fileManager, staticmask

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

CLOUD_TEX_REFERENCE_MEAN = 30.0  # the ROI mean brightness CLOUD_TEX_LOW/HIGH were calibrated
                                  # against (same historical target_mean=30 baseline as
                                  # HAZE_SPREAD_REFERENCE_MEAN) - see
                                  # _estimate_cloud_cover_texture_only's mean-rescaling: tex_std
                                  # is a raw pixel-value std, not exposure/brightness-normalized,
                                  # so it scales with whatever absolute brightness the frame
                                  # happens to sit at. Confirmed on a real frame (2026-09-14,
                                  # dusk 09-12 20:01, roi_mean 70.6): unscaled tex_std=10.87 would
                                  # peg texture_score near 64% on a frame independently confirmed
                                  # clear (NRBR=0.0 on the same frame) - rescaled by 30/70.6 it
                                  # drops to 4.62, correctly below CLOUD_TEX_LOW.

DAY_NRBR_CLEAR = 0.40            # calibrated clear-blue-sky NRBR (zenith measured ~0.53, margin
                                  # kept for natural whitening toward the horizon under clear sky)
DAY_NRBR_CLOUD = 0.12            # calibrated white/gray NRBR (measured on Sun-flare/near-white
                                  # pixels as a stand-in for overcast, which reads the same way:
                                  # R roughly equal to B)
DAY_NRBR_AGG_PERCENTILE = 40     # a single DAY_NRBR_CLEAR margin isn't enough on a wide fisheye
                                  # ROI: confirmed on a real clear day (0.65 ROI), NRBR-derived
                                  # cloud-score climbs from ~30% at zenith to 80-97% near the
                                  # horizon and, independently, on the sun's side of the frame even
                                  # well short of the bright-source halo (75%+ within 45 degrees of
                                  # the sun's azimuth, out to near zenith) - real effects (Rayleigh
                                  # whitening toward the horizon; circumsolar aureole), not noise.
                                  # Both contaminate a MINORITY of sky pixels, so the mean is pulled
                                  # up disproportionately; a below-median percentile is far less
                                  # sensitive to that tail while a genuinely mostly-overcast sky
                                  # (most pixels high-scoring) is barely affected - confirmed against
                                  # 40 real daytime frames from one real camera/day: this percentile
                                  # cut the false-positive tail on clear/lightly-hazy frames by
                                  # 10-30 points while leaving the two most heavily-clouded frames in
                                  # that set within ~1 point of the old mean-based score. Single
                                  # day/site/season of validation - revisit with more reference days
                                  # (other seasons, other sun-elevation ranges) before trusting the
                                  # exact percentile value.

HAZE_BG_SIGMA = 120              # heavy enough to discard both star-scale and cloud-scale
                                  # ("texture") content, keeping only the broadest glow structure
HAZE_SPREAD_LOW = 11.0           # revised 2026-09-10 from the original 6.0 (max observed 5.6 across
                                  # only 3 real clear-sky captures - too small a sample, see below).
                                  # A same-day retrospective scan of 36 real deep-night frames across
                                  # 3 full nights (84.33.110.109) found the original 6.0 produced a
                                  # recurring false-positive floor on two entirely clear nights - full-
                                  # ROI spread sat at 4.2-10.52 all night on both (only the horizon
                                  # ring: this site's own light-pollution glow, not cloud - a zenith-
                                  # only inner-ROI check on the same frames stayed under 6.0 the whole
                                  # time), which the old constant reported as up to 56.5% cloud on an
                                  # ordinary clear night. 11.0 sits just above that real clear-night
                                  # ceiling, fully eliminating it (verified: 0% ceiling across both
                                  # clear nights, vs. 13% residual at 10.0). Real cost, not free: a
                                  # genuinely foggy night sampled the same round (independently
                                  # confirmed via visual review - 5-6 stars only, matches production's
                                  # own 86%/100% reports that night) had two readings whose spread
                                  # (9.03, 9.81) falls in the same overlap band as the clear-night
                                  # ceiling - those now read ~0% instead of 38-48%. The same fog episode
                                  # still registers at 100% three separate times (01:00, 02:20, 03:40),
                                  # so the event as a whole is still caught - this is reduced within-
                                  # event granularity on 2 of 10 sampled readings, not a missed event.
                                  # Chosen over 10.0 because the user's explicit priority is eliminating
                                  # night-side false positives entirely, not minimizing this cost.
                                  # Revisit with more reference nights before pushing this further.
HAZE_SPREAD_HIGH = 14.0          # unchanged - calibrated patchy-cloud/moon-behind-cloud spread (10.6-
                                  # 12.6 observed on real partly-cloudy and moon-behind-cloud captures) -
                                  # small reference set (6 real images); revisit if false-flagging
                                  # a genuinely clear night, or missing an actually hazy one
HAZE_SPREAD_REFERENCE_MEAN = 30.0  # the ROI mean brightness both constants above were calibrated
                                  # against (autoexposure.py's own historical target_mean default) -
                                  # see _estimate_cloud_cover_haze's mean-rescaling for why this
                                  # matters: this signal is an absolute pixel-value spread, not
                                  # exposure-normalized like _estimate_cloud_cover's radiance rate.

HAZE_INNER_ROI_RATIO = 0.35      # zenith-only sub-ROI the spread is now measured over (see
                                  # _estimate_cloud_cover_haze) - same ratio tools/night_cloud_
                                  # reference_collector.py's diagnostic haze_spread_inner column
                                  # has used since 2026-09-10 specifically to separate this site's
                                  # horizon light-pollution glow from real cloud (see that constant's
                                  # own comment above, "a zenith-only inner-ROI check... stayed under
                                  # 6.0"). Verified 2026-09-18 by re-running the real end-to-end
                                  # function against 9 archived frames across 4 nights: see
                                  # _estimate_cloud_cover_haze's own docstring for the real numbers.


def analyze_sky_robust(image_path, diametro_rapporto=0.75, sensibilita=0.5, min_contrasto=25, exposure_secs=None, twilight_isp_mode=False, twilight_fixed_shutter_band=False):
    """
    Analizza il cielo notturno per contare le stelle e stimare la copertura nuvolosa.

    INPUT:
    - image_path: percorso del file immagine
    - diametro_rapporto: dimensione della ROI circolare (0.1 - 1.0)
    - sensibilita: parametro per il filtro di circolarita' (0.1 - 1.0)
    - min_contrasto: soglia minima di intensita' per distinguere una stella dal rumore
    - exposure_secs: durata di esposizione applicata (se nota); migliora la stima
      delle nuvole. Se omesso, si tenta l'EXIF del file e infine un fallback
      basato solo su luminosita'/texture. Ignorato se twilight_isp_mode=True o
      twilight_fixed_shutter_band=True.
    - twilight_isp_mode: True se lo scatto e' stato esposto dall'ISP (twilight
      handoff) anziche' con uno shutter fisso/predetto - in tal caso la
      luminosita' e' normalizzata dall'ISP stesso e non e' informativa per le
      nuvole (stesso motivo per cui il branch diurno usa NRBR invece della
      luminosita'), quindi la copertura nuvolosa usa NRBR anche di notte.
    - twilight_fixed_shutter_band: True se lo scatto e' un vero scatto a
      shutter fisso (non ISP) ma comunque nella fascia crepuscolare (fra
      twilight_guard_deg e twilight_isp_backstop_deg) - qui l'esposizione e'
      reale ma troppo breve (~0.02s) per il segnale radiance-rate notturno
      (calibrato su esposizioni multi-secondo), e NRBR non e' applicabile
      perche' questo frame usa il bilanciamento del bianco fisso notturno
      (--awbgains), non quello automatico diurno su cui NRBR e' calibrato
      (vedi CLOUD_TEX_REFERENCE_MEAN e _estimate_cloud_cover_texture_only).
      Ha priorita' su twilight_isp_mode se entrambi fossero True (non
      dovrebbe succedere nella pratica: sono impostati in rami alternativi
      di __main__.py). NB: `gray[roi==255].mean() > DAYTIME_MEAN_THRESHOLD`
      is checked before this parameter is ever consulted (see below) - if a
      real frame in this band ever crossed that threshold it would silently
      take the day path (NRBR) instead, reviving the false-positive this
      parameter exists to fix. Checked against a real full dusk+dawn dataset
      (86 frames, 2026-09-14, sun_alt computed per-frame): ROI mean stays
      30-69 throughout the genuine -twilight_isp_backstop_deg..
      -twilight_guard_deg band on both crossings (peaking at 68.73 right at
      the -3deg edge itself), comfortably under DAYTIME_MEAN_THRESHOLD=85 -
      not observed as a live problem, but the margin (~16 points) is real
      data, not a guarantee; revisit if a future report shows this band
      silently reading day-branch values.

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

    obstruction = _get_obstruction_mask(gray, roi, is_night=True)
    bright_source, source_found, _ = _bright_source_mask(gray, roi)

    sky = roi.copy()
    sky[obstruction == 255] = 0
    sky[bright_source == 255] = 0

    if not np.any(sky == 255):
        # entire ROI obstructed/masked out - nothing left to analyze
        return 0, 100.0

    sky_eroded = _erode_guard_band(sky)

    star_count = _find_stars(gray, sky_eroded, min_contrasto, sensibilita)
    if twilight_fixed_shutter_band:
        cloud_cover = _estimate_cloud_cover_texture_only(gray, sky_eroded)
    elif twilight_isp_mode:
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
    sun_mask, sun_found, _ = _bright_source_mask(gray, roi)
    obstruction = _get_obstruction_mask(gray, roi, is_night=False)

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
    # percentile, not mean - see DAY_NRBR_AGG_PERCENTILE
    return round(100.0 * np.percentile(score, DAY_NRBR_AGG_PERCENTILE), 1)


def _estimate_cloud_cover_texture_only(gray, sky_mask):
    '''
    Twilight-fixed-shutter-band signal (real fixed shutter, ~0.02s floor,
    night --awbgains) - found 2026-09-14 after the 2026-09-13 NRBR-routing
    hotfix for this band (see __main__.py's twilight_fixed_shutter_band
    comment) turned out to have its own 20-48% false-positive on confirmed-
    clear dawn sky: NRBR's DAY_NRBR_CLEAR/CLOUD anchors are calibrated
    against ISP-auto-white-balanced frames (daytime and twilight_isp_mode),
    but this band's real fixed-shutter capture uses the night command's
    fixed --awbgains (tuned for accurate star color, not daylight balance) -
    a manual white balance NRBR was never validated against, and measured
    real NRBR here (~0.24-0.33) sits well below the "genuinely clear" anchor
    despite the sky being genuinely clear.

    Uses the same band-pass texture std as _estimate_cloud_cover's
    texture_score (CLOUD_TEX_LOW/HIGH), but WITHOUT that function's
    brightness_signal (radiance-rate, mean_gray/exposure_secs) - that's the
    signal that pegs to 100% at this band's sub-second exposures in the
    first place (calibrated for multi-second night exposures, see the
    2026-09-13/v38 history in memory), so it can't be reused here even
    partially via max(). Also deliberately does NOT stack the haze signal
    (_estimate_cloud_cover_haze) - HAZE_SPREAD_LOW/HIGH are deep-night-only
    calibrated and unvalidated at this band's brightness/exposure, and
    stacking a second unvalidated signal on top of this one would confound
    which one is responsible for a bad reading.

    Rescaled by CLOUD_TEX_REFERENCE_MEAN/actual ROI mean, same reason and
    same technique as _estimate_cloud_cover_haze's own mean-rescaling: raw
    tex_std is an absolute pixel-value std, not exposure-normalized, so it
    scales with whatever brightness this band's fixed-shutter feedback loop
    happens to be converging on at that moment (unlike NRBR, a ratio that's
    scale-invariant by construction) - see CLOUD_TEX_REFERENCE_MEAN's own
    comment for the real frame that would have false-positived without it.

    Validated (2026-09-14) against a first 6-frame sample in this band, all
    independently confirmed clear (visual + matching NRBR=0 where NRBR
    itself was correct): all 6 read 0% (below CLOUD_TEX_LOW) after
    rescaling, including the two where NRBR was wrong (05:20/05:30 dawn
    today, NRBR 45.5%/19.5%, this signal 0%/0%) and the one where raw
    (unrescaled) tex_std would itself have been wrong (dusk 09-12 20:01,
    roi_mean 70.6, raw tex_std 10.87 -> ~64%, rescaled -> 4.62 -> 0%).

    Broader same-day check (86 real frames, full dusk+dawn crossing,
    sun_alt computed per real frame timestamp) found this is NOT a clean
    0% everywhere in the band: 06:15-06:39 dawn (sun_alt -8.70 to -3.14,
    still confirmed clear) read a small non-zero residual, 0.6% rising to
    4.8% and decaying back to 0 - real, not sampled by the smaller probe
    above. A large improvement on the 20-48% NRBR false-positive this
    replaces, but NOT literal zero everywhere, unlike HAZE_SPREAD_LOW's own
    validated ceiling (0% residual, the bar the user has held this class of
    fix to before). No real cloudy-twilight-band reference frame exists
    yet, so real-cloud sensitivity in this specific band is UNVERIFIED -
    revisit once the reference collectors
    (tools/*_cloud_reference_collector.py) accumulate a real cloudy sample
    in this band.

    Known limitation (found via unit testing, not yet seen live): unlike
    _estimate_cloud_cover_haze's rescaling (which corrects for a globally,
    separately-caused exposure/target_mean shift), this rescale divides by
    the mean of the SAME masked region the texture is measured over - so a
    real cloud patch that is both large AND much brighter than the rest of
    the frame (plausible for light-pollution-lit cloud at night) inflates
    its own reference mean and damps its own score, biasing this signal
    toward under-reporting exactly that case. Not fixed here - would need a
    real bright-patch-at-night twilight-band reference frame to calibrate
    against, which doesn't exist yet either; flagged for whoever reviews
    this once real cloudy data lands.
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
    Prefers the auto-generated static mask (see staticmask.py,
    generate_mask.py) when one exists and matches this frame's shape; falls
    back to the existing dynamic heuristic (_obstruction_mask at night,
    _day_obstruction_mask during the day) otherwise - a fresh install with
    no generated mask yet behaves exactly as it did before this function
    existed.

    mask_path: overridable for tests (see autoexposure.py's state_filename
    parameter for the same pattern/reason) - defaults to the real
    production path.
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


def _bright_source_mask(gray, roi):
    # the Sun or Moon (or any other dominant bright source: a bright planet, a
    # stray light) shows up as a large near-saturated blob; mask it plus a
    # generous halo so its flare and diffraction spikes can't be miscounted as
    # stars (night) or read as white/cloud-like via NRBR (day). Also returns
    # the largest qualifying blob's centroid (the real sun/moon, not a
    # smaller artifact) - needed by tools/skycalibration_collector.py for
    # sky-projection calibration (see
    # docs/superpowers/specs/2026-09-14-cloud-detection-rework-design.md
    # section 5); None when nothing was found.
    candidate = ((gray > BRIGHT_SOURCE_GRAY_MIN) & (roi == 255)).astype(np.uint8) * 255
    n, labels, stats, centroids = cv2.connectedComponentsWithStats(candidate, connectivity=8)
    roi_area = np.sum(roi == 255)
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

    Originally calibrated on 6 real images total (3 clear, 3 cloudy/hazy) -
    the smallest reference set of any signal in this module, and it showed:
    a 2026-09-10 retrospective scan of 36 real frames across 3 full nights
    found the original HAZE_SPREAD_LOW produced a recurring false-positive
    floor (up to 56.5% reported) on two entirely clear nights, driven by
    this site's own horizon light-pollution glow rather than cloud - see
    HAZE_SPREAD_LOW's own comment for the full real-frame evidence and the
    revised value's trade-off. Revisit again once the night-side reference
    collector (tools/night_cloud_reference_collector.py) has accumulated
    more labeled real nights.

    Rescaled by HAZE_SPREAD_REFERENCE_MEAN/actual ROI mean - unlike
    _estimate_cloud_cover's radiance rate (mean/exposure, already
    exposure-normalized), this is a raw pixel-value spread, so it scales
    with whatever absolute brightness autoexposure's feedback loop happens
    to be converging on. That was a constant (target_mean=30) for the
    entire real dataset this signal was calibrated and validated against,
    so it was invisible until autoexposure gained a true-night target-mean
    boost/moon-scaling (target_mean now 30-35+ depending on the Moon):
    confirmed on a real 2026-09-13 frame (mean_gray 35.09, 76 stars still
    visible, a barely-hazy sky) that the unscaled spread (14.648) pegged
    this signal at 100% - rescaled by 30/35.09, it drops to 12.52 -> 50.8%,
    matching the same night's own visual estimate (~50%). Every other real
    reference row on file (all captured before that boost existed, at the
    old fixed target_mean=30) shifts by under half a point under this
    rescaling - it's a no-op on the exact dataset HAZE_SPREAD_LOW/HIGH were
    validated against, and only corrects the new target_mean-driven cases.

    Measured over a zenith-only sub-ROI (HAZE_INNER_ROI_RATIO), not the full
    sky_mask passed in - added 2026-09-18 after the rescaling above still
    left a live false-positive: real v49 frames with a clearly star-filled
    sky (7-76 stars) kept reading 100% whole-frame cloud_cover (e.g.
    skycam_20260917_01281789601283YTL.jpg: 24 stars in its own overlay).
    Root cause: the mean-rescaling above corrects for a globally-caused
    brightness shift, but this site's own horizon light-pollution glow is a
    spatially localized confound - it inflates the p90-p10 spread across the
    FULL ROI regardless of whether the zenith itself is genuinely clear,
    exactly the mechanism HAZE_SPREAD_LOW's own comment already documented
    from the 2026-09-10 retrospective scan ("a zenith-only inner-ROI check
    on the same frames stayed under 6.0"), which was never wired into
    production - only ever a manual diagnostic, later formalized as
    tools/night_cloud_reference_collector.py's haze_spread_inner column
    (logged unrescaled, for visibility only, not the same as this function's
    own rescaled output).

    Verified by re-running the real, fully-parameterized analyze_sky_robust
    (diametro_rapporto=0.65, sensibilita=0.4, min_contrasto=30 - production's
    own args) end-to-end against 9 real archived frames spanning 4 nights
    (2026-09-11, 09-13, 09-16, 09-17; both pre-v49 and live-v49 captures):
    every one of the 8 frames independently known to be a false positive
    (7-76 stars, previously reporting 79-100%) now reads 6.3-20.9%, while
    the one frame independently confirmed as a real overcast/hazy patch
    (2026-09-11 22:00, 1 star, washed-out uniform sky glow) stays exactly at
    100% - both before and after this change. Checked what's left driving
    each of those 8 residual readings (analyze_sky_robust's other two
    signals, computed from the same rows' logged tex_std/radiance_rate):
    in all 8, the reported value matches max(texture_score, brightness_
    signal) to within rounding - i.e. this signal itself now reads at or
    below the noise floor on every one of them, not just "lower than
    before". The other two signals were already carrying these frames; this
    change stops haze from silently overriding them.

    Real, deliberate cost, not free, though not yet observed as an actual
    miss: a cloud patch that sits only in the outer ~2/3 of the frame
    (between HAZE_INNER_ROI_RATIO and the full ROI) without ever reaching
    the zenith is now invisible to this specific signal - the same kind of
    narrowed-but-bounded trade-off HAZE_SPREAD_LOW and the texture-only
    signal's self-referential mean already carry elsewhere in this module.
    The other two signals in analyze_sky_robust (radiance rate, cloud-scale
    texture) are unaffected - they already operate over the full sky_mask -
    so this only narrows the one signal that was structurally blind to a
    uniform/broad veil in the first place.
    '''
    inner_roi = roi_mask(gray, HAZE_INNER_ROI_RATIO)
    inner_mask = cv2.bitwise_and(sky_mask, inner_roi)
    if not np.any(inner_mask == 255):
        # zenith fully obstructed/masked (e.g. an obstruction sitting exactly
        # at frame center - the Moon/bright-source case is already excluded
        # upstream via analyze_sky_robust's source_found gate, so this isn't
        # that). Falling back to the full ROI here would silently reintroduce
        # the exact horizon-glow false-positive this change exists to fix, on
        # the one path where the caller has the least reason to trust the
        # result. This signal only exists to catch what the other two miss
        # (see this function's own docstring) - if it can't measure the
        # zenith at all, 0.0 and let radiance rate / cloud-scale texture
        # (still full-ROI, unaffected by this change) carry the frame.
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
