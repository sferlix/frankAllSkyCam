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
    # (0, 1), not saturate either boundary. Step size (17, not the original
    # 10, or the 13 used between the 2026-09-10 HAZE_SPREAD_LOW revision and
    # the 2026-09-13 reference-mean rescaling) chosen to produce a rescaled
    # spread ~13.2 - comfortably between HAZE_SPREAD_LOW=11.0 and
    # HAZE_SPREAD_HIGH=14.0 after _estimate_cloud_cover_haze rescales by
    # HAZE_SPREAD_REFERENCE_MEAN/actual mean (background=30, patch=47 here
    # raises the whole-frame mean, which pulls the raw spread trying to hit
    # ~13 back down under LOW - see _estimate_cloud_cover_haze's docstring
    # for why this rescaling exists).
    gray = np.full((HEIGHT, WIDTH), 30, dtype=np.uint8)
    gray[:, WIDTH // 2:] = 47
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
