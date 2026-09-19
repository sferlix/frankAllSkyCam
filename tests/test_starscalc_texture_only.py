'''
Unit tests for starscalc._estimate_cloud_cover_texture_only, the twilight fixed-shutter
cloud signal. Synthetic arrays: they check the mean-rescaling, the mapping to 0..100
and the scoping to sky_mask.
'''

import numpy as np
import pytest

from frankAllSkyCam import starscalc as sc

HEIGHT, WIDTH = 768, 1024  # matches this install's configured capture resolution


def test_uniform_background_scores_zero():
    # no texture at all -> tex_std ~0, well under CLOUD_TEX_LOW -> clipped to 0
    gray = np.full((HEIGHT, WIDTH), 30, dtype=np.uint8)
    sky_mask = np.full((HEIGHT, WIDTH), 255, dtype=np.uint8)

    score = sc._estimate_cloud_cover_texture_only(gray, sky_mask)

    assert score == 0.0


def test_large_patch_scores_at_ceiling():
    # a small saturated patch: large enough to register, small enough not to dominate
    # the whole-ROI mean used for rescaling; the gap far exceeds CLOUD_TEX_HIGH -> 100
    gray = np.full((HEIGHT, WIDTH), 30, dtype=np.uint8)
    gray[:, WIDTH - int(WIDTH * 0.08):] = 255
    sky_mask = np.full((HEIGHT, WIDTH), 255, dtype=np.uint8)

    score = sc._estimate_cloud_cover_texture_only(gray, sky_mask)

    assert score == 100.0


def test_large_bright_half_is_damped_by_its_own_mean():
    # known limitation: the rescale divides by the mean of the same masked region the
    # texture is measured over, so a patch that is both large and much brighter than the
    # rest of the frame inflates its own reference mean and damps its own score. A 30 -> 120
    # step across half the frame reads far below the ceiling here.
    gray = np.full((HEIGHT, WIDTH), 30, dtype=np.uint8)
    gray[:, WIDTH // 2:] = 120
    sky_mask = np.full((HEIGHT, WIDTH), 255, dtype=np.uint8)

    score = sc._estimate_cloud_cover_texture_only(gray, sky_mask)

    assert score < 50.0


def test_score_is_stable_under_uniform_brightness_scaling():
    # a clear twilight-band frame with a high ROI mean (70.6, against the
    # CLOUD_TEX_REFERENCE_MEAN=30 baseline) must not read more cloudy than the same relative
    # structure at the baseline brightness
    sky_mask = np.full((HEIGHT, WIDTH), 255, dtype=np.uint8)
    gray_base = np.full((HEIGHT, WIDTH), 30, dtype=np.uint8)
    gray_base[:, WIDTH // 2:] = 34  # a small, moderate relative step

    scale = 70.6 / 30.0
    gray_scaled = np.full((HEIGHT, WIDTH), round(30 * scale), dtype=np.uint8)
    gray_scaled[:, WIDTH // 2:] = round(34 * scale)

    score_base = sc._estimate_cloud_cover_texture_only(gray_base, sky_mask)
    score_scaled = sc._estimate_cloud_cover_texture_only(gray_scaled, sky_mask)

    assert score_scaled == pytest.approx(score_base, abs=2.0)


def test_sky_mask_excludes_obstruction_from_texture():
    # a bright corner outside sky_mask must not affect the texture, provided the mask margin
    # absorbs the blur radius (CLOUD_TEX_LARGE_SIGMA=80 is wider than the 41px guard band).
    # Production passes a guard-band-eroded mask (sky_eroded); mirrored here with a generous
    # excluded margin before eroding.
    gray = np.full((HEIGHT, WIDTH), 30, dtype=np.uint8)
    gray[:80, :80] = 255  # excluded corner
    sky_mask = np.full((HEIGHT, WIDTH), 255, dtype=np.uint8)
    sky_mask[:280, :280] = 0
    sky_mask = sc._erode_guard_band(sky_mask)

    score = sc._estimate_cloud_cover_texture_only(gray, sky_mask)

    assert score == 0.0


def test_real_twilight_band_measurements_stay_below_ceiling():
    # ROI means seen in this band (32.75-70.55): a uniform frame at any of these
    # brightness levels must stay at 0 - wrong or missing rescaling could produce a
    # false texture reading from blur-edge noise
    sky_mask = np.full((HEIGHT, WIDTH), 255, dtype=np.uint8)
    for real_roi_mean in (32.75, 36.36, 39.20, 70.55):
        gray = np.full((HEIGHT, WIDTH), round(real_roi_mean), dtype=np.uint8)
        score = sc._estimate_cloud_cover_texture_only(gray, sky_mask)
        assert score == 0.0
