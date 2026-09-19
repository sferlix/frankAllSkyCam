'''
Unit tests for starscalc._estimate_cloud_cover_haze, the broad-scale background
patchiness signal (thin veil cloud). Synthetic arrays: they check the mapping to
0..1 and the scoping to the zenith-only inner ROI and to sky_mask.
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
    # a smaller step than the ceiling case: lands strictly inside (0, 1). The step (27) is
    # sized for the zenith-only inner ROI, which samples more of the blurred transition
    gray = np.full((HEIGHT, WIDTH), 30, dtype=np.uint8)
    gray[:, WIDTH // 2:] = 57
    sky_mask = np.full((HEIGHT, WIDTH), 255, dtype=np.uint8)

    score = sc._estimate_cloud_cover_haze(gray, sky_mask)

    assert 0.0 < score < 1.0


def test_score_is_stable_under_uniform_brightness_scaling():
    # a uniformly brighter frame with the same relative structure (target_mean boost 30 -> 35)
    # must not read as more cloudy: the spread is scaled by HAZE_SPREAD_REFERENCE_MEAN / mean
    sky_mask = np.full((HEIGHT, WIDTH), 255, dtype=np.uint8)
    gray_base = np.full((HEIGHT, WIDTH), 30, dtype=np.uint8)
    gray_base[:, WIDTH // 2:] = 43  # same relative step as the moderate-patch case
# same relative structure, uniformly scaled up by 35/30 (target_mean 35 instead of 30):
# background 30->35, patch 43->43*(35/30)=~50.2
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
    # horizon light-pollution glow: a bright ring in the outer part of the ROI with a
    # uniform zenith must not push the signal to the ceiling (only the zenith-only disk is
    # measured)
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
    # an inner disk with no sky pixels at all (e.g. an obstruction at frame center) gives
    # 0.0 instead of falling back to the full ROI
    gray = np.full((HEIGHT, WIDTH), 30, dtype=np.uint8)
    gray[:, WIDTH // 2:] = 120  # would score 1.0 over the full ROI
    sky_mask = np.full((HEIGHT, WIDTH), 255, dtype=np.uint8)
    cy, cx = HEIGHT // 2, WIDTH // 2
    yy, xx = np.ogrid[:HEIGHT, :WIDTH]
    dist = np.sqrt((yy - cy) ** 2 + (xx - cx) ** 2)
    sky_mask[dist < 200] = 0  # blanks out the entire inner disk (radius ~179)

    score = sc._estimate_cloud_cover_haze(gray, sky_mask)

    assert score == 0.0


def test_patch_reaching_the_zenith_still_scores_at_ceiling():
    # a patch that reaches the zenith is still caught
    gray = np.full((HEIGHT, WIDTH), 30, dtype=np.uint8)
    gray[:, WIDTH // 2:] = 120  # same step as test_large_patch_scores_at_ceiling; it bisects the inner disk
    sky_mask = np.full((HEIGHT, WIDTH), 255, dtype=np.uint8)

    score = sc._estimate_cloud_cover_haze(gray, sky_mask)

    assert score == 1.0
