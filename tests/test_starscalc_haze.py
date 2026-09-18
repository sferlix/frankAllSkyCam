'''
Unit tests for starscalc._estimate_cloud_cover_haze - the broad-scale
background-patchiness signal added to catch thin/smooth veil cloud that the
existing texture and radiance-rate signals miss (see its docstring for the
real-capture evidence). Synthetic arrays, not real captures - this signal's
own real-image calibration is documented in starscalc.py itself and can't
be re-derived from a unit test; these only check the pure math (clip01
mapping, sky_mask scoping) behaves as documented at the boundaries.
'''

import numpy as np
import pytest

from frankAllSkyCam import starscalc as sc

HEIGHT, WIDTH = 768, 1024  # matches this install's configured capture resolution


def test_uniform_background_scores_zero():
    # no large-scale structure at all -> p90-p10 spread ~0, well under
    # HAZE_SPREAD_LOW -> clipped to 0, same as a real clear night
    gray = np.full((HEIGHT, WIDTH), 30, dtype=np.uint8)
    sky_mask = np.full((HEIGHT, WIDTH), 255, dtype=np.uint8)

    score = sc._estimate_cloud_cover_haze(gray, sky_mask)

    assert score == 0.0


def test_large_patch_scores_at_ceiling():
    # half the sky much brighter than the other, gap far exceeding
    # HAZE_SPREAD_HIGH -> clipped to 1.0, same as a real heavily patchy night
    gray = np.full((HEIGHT, WIDTH), 30, dtype=np.uint8)
    gray[:, WIDTH // 2:] = 120
    sky_mask = np.full((HEIGHT, WIDTH), 255, dtype=np.uint8)

    score = sc._estimate_cloud_cover_haze(gray, sky_mask)

    assert score == 1.0


def test_moderate_patch_scores_strictly_between():
    # a smaller step than the ceiling case - should land strictly inside
    # (0, 1), not saturate either boundary. Step size (27, not the 17 used
    # before the 2026-09-18 zenith-only-ROI change) re-picked for the new
    # inner-ROI measurement: cropping to HAZE_INNER_ROI_RATIO samples
    # proportionally more of the blurred transition zone around the step
    # than the old full-ROI measurement did, softening the spread for any
    # given step size - the old value (47) now lands at the 0.0 floor
    # instead of strictly between.
    gray = np.full((HEIGHT, WIDTH), 30, dtype=np.uint8)
    gray[:, WIDTH // 2:] = 57
    sky_mask = np.full((HEIGHT, WIDTH), 255, dtype=np.uint8)

    score = sc._estimate_cloud_cover_haze(gray, sky_mask)

    assert 0.0 < score < 1.0


def test_score_is_stable_under_uniform_brightness_scaling():
    # regression for the 2026-09-13 false-100% bug: autoexposure's true-
    # night target_mean boost (30 -> up to 35+) uniformly brightens the
    # whole frame for the exact same physical sky - a frame scaled up by a
    # higher target_mean must not read as more cloudy than the identical
    # relative structure at the old target_mean=30 baseline. Real numbers
    # from that bug (mean_gray 35.09, raw spread 14.648 -> wrongly 100%,
    # rescaled -> 50.8%, matching the night's own visual ~50% estimate) are
    # exactly this shape: same relative patchiness, different absolute
    # brightness.
    sky_mask = np.full((HEIGHT, WIDTH), 255, dtype=np.uint8)
    gray_base = np.full((HEIGHT, WIDTH), 30, dtype=np.uint8)
    gray_base[:, WIDTH // 2:] = 43  # same relative step as the moderate-patch case

    # same relative structure, uniformly scaled up by 35/30 (the boosted
    # true-night target_mean over the old default) - background 30->35,
    # patch 43->43*(35/30)=~50.2
    gray_scaled = np.full((HEIGHT, WIDTH), 35, dtype=np.uint8)
    gray_scaled[:, WIDTH // 2:] = round(43 * (35.0 / 30.0))

    score_base = sc._estimate_cloud_cover_haze(gray_base, sky_mask)
    score_scaled = sc._estimate_cloud_cover_haze(gray_scaled, sky_mask)

    assert score_scaled == pytest.approx(score_base, abs=0.02)


def test_sky_mask_excludes_obstruction_from_spread():
    # a bright corner entirely outside sky_mask (e.g. a foreground tree
    # silhouette candidate, or the guard-band-eroded margin) must not affect
    # the measured spread at all
    gray = np.full((HEIGHT, WIDTH), 30, dtype=np.uint8)
    gray[:100, :100] = 255  # excluded corner
    sky_mask = np.full((HEIGHT, WIDTH), 255, dtype=np.uint8)
    sky_mask[:100, :100] = 0

    score = sc._estimate_cloud_cover_haze(gray, sky_mask)

    assert score == 0.0


def test_horizon_ring_glow_does_not_trigger_ceiling():
    # regression for the 2026-09-18 live v49 false-positive: this site's own
    # horizon light-pollution glow (a bright ring near the ROI edge, well
    # outside HAZE_INNER_ROI_RATIO's zenith-only disk) inflated the full-ROI
    # p90-p10 spread past HAZE_SPREAD_HIGH on real clear, star-filled nights
    # (e.g. 76 stars detected, still read "Clouds: 100%" - see starscalc.py's
    # updated _estimate_cloud_cover_haze docstring for the real frame
    # evidence). A bright ring confined to the outer part of the ROI, with a
    # uniform zenith, must no longer peg this signal at the ceiling.
    gray = np.full((HEIGHT, WIDTH), 30, dtype=np.uint8)
    sky_mask = np.full((HEIGHT, WIDTH), 255, dtype=np.uint8)
    cy, cx = HEIGHT // 2, WIDTH // 2
    yy, xx = np.ogrid[:HEIGHT, :WIDTH]
    dist = np.sqrt((yy - cy) ** 2 + (xx - cx) ** 2)
    outer_ring = (dist > 300) & (dist < 380)  # well outside the inner disk (radius ~179)
    gray[outer_ring] = 120

    score = sc._estimate_cloud_cover_haze(gray, sky_mask)

    assert score == 0.0


def test_zenith_fully_masked_scores_zero_not_full_roi_fallback():
    # if the inner (zenith-only) disk has no sky pixels at all - e.g. an
    # obstruction sitting exactly at frame center - falling back to the full
    # ROI would silently reintroduce the horizon-glow false positive this
    # signal was just fixed to avoid. Must return 0.0 instead and let the
    # other two analyze_sky_robust signals (still full-ROI) carry the frame.
    gray = np.full((HEIGHT, WIDTH), 30, dtype=np.uint8)
    gray[:, WIDTH // 2:] = 120  # would score 1.0 under the old full-ROI behavior
    sky_mask = np.full((HEIGHT, WIDTH), 255, dtype=np.uint8)
    cy, cx = HEIGHT // 2, WIDTH // 2
    yy, xx = np.ogrid[:HEIGHT, :WIDTH]
    dist = np.sqrt((yy - cy) ** 2 + (xx - cx) ** 2)
    sky_mask[dist < 200] = 0  # blanks out the entire inner disk (radius ~179)

    score = sc._estimate_cloud_cover_haze(gray, sky_mask)

    assert score == 0.0


def test_patch_reaching_the_zenith_still_scores_at_ceiling():
    # confirms the fix doesn't just suppress everything: a patch that DOES
    # reach the zenith (unlike the horizon-ring-only case above) must still
    # be caught, same as the known real overcast/hazy patch (2026-09-11
    # 21:22-22:30, 1-7 stars, correctly read 100% both before and after this
    # change per the real-dataset check documented in the docstring).
    gray = np.full((HEIGHT, WIDTH), 30, dtype=np.uint8)
    gray[:, WIDTH // 2:] = 120  # same step as test_large_patch_scores_at_ceiling,
                                # which also still passes: the step runs through
                                # the frame center, so it bisects the inner disk too
    sky_mask = np.full((HEIGHT, WIDTH), 255, dtype=np.uint8)

    score = sc._estimate_cloud_cover_haze(gray, sky_mask)

    assert score == 1.0
