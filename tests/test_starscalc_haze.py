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
    # (0, 1), not saturate either boundary
    gray = np.full((HEIGHT, WIDTH), 30, dtype=np.uint8)
    gray[:, WIDTH // 2:] = 40
    sky_mask = np.full((HEIGHT, WIDTH), 255, dtype=np.uint8)

    score = sc._estimate_cloud_cover_haze(gray, sky_mask)

    assert 0.0 < score < 1.0


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
