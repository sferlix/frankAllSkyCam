'''
Unit tests for starscalc._estimate_cloud_cover_texture_only - the twilight
fixed-shutter-band cloud signal (real short exposure, night --awbgains,
neither NRBR nor the radiance-rate branch of _estimate_cloud_cover apply -
see that function's docstring for the real-frame evidence). Synthetic
arrays, not real captures - real-frame validation is documented in
starscalc.py itself; these only check the pure math (mean-rescaling,
clip01 mapping, sky_mask scoping) behaves as documented at the boundaries.
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
    # a small, saturated patch - large enough to register, small enough that
    # its own brightness doesn't dominate the whole-ROI mean used for
    # rescaling (see test_large_bright_half_is_damped_by_its_own_mean below
    # for what happens when it does) - gap far exceeding CLOUD_TEX_HIGH even
    # after rescaling -> clipped to 100
    gray = np.full((HEIGHT, WIDTH), 30, dtype=np.uint8)
    gray[:, WIDTH - int(WIDTH * 0.08):] = 255
    sky_mask = np.full((HEIGHT, WIDTH), 255, dtype=np.uint8)

    score = sc._estimate_cloud_cover_texture_only(gray, sky_mask)

    assert score == 100.0


def test_large_bright_half_is_damped_by_its_own_mean():
    # documents a real, deliberate limitation of this signal (not a bug):
    # unlike _estimate_cloud_cover_haze's rescaling (which corrects for a
    # separately-caused global exposure/target_mean shift), this rescale
    # divides by the mean of the SAME masked region the texture is measured
    # over - so a patch that is both large AND much brighter than the rest
    # of the frame (plausible for real light-pollution-lit cloud at night)
    # inflates its own reference mean and can damp its own score. A step
    # from 30 to 120 across half the frame - which would read as ceiling
    # (100) on a signal without this self-referential rescaling, e.g.
    # _estimate_cloud_cover_haze's own ceiling test uses the same step and
    # scores 1.0 - reads far below ceiling here.
    gray = np.full((HEIGHT, WIDTH), 30, dtype=np.uint8)
    gray[:, WIDTH // 2:] = 120
    sky_mask = np.full((HEIGHT, WIDTH), 255, dtype=np.uint8)

    score = sc._estimate_cloud_cover_texture_only(gray, sky_mask)

    assert score < 50.0


def test_score_is_stable_under_uniform_brightness_scaling():
    # regression for the 2026-09-14 false-positive this signal replaces
    # NRBR for: a real clear twilight-band frame (roi_mean 70.6, well above
    # the CLOUD_TEX_REFERENCE_MEAN=30 baseline) must not read more cloudy
    # than the identical relative structure at the reference baseline
    # brightness - same shape as _estimate_cloud_cover_haze's own
    # brightness-scaling regression test.
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
    # a bright corner outside sky_mask (e.g. a foreground tree silhouette
    # candidate) must not affect the measured texture, PROVIDED the mask
    # margin around it is wide enough to absorb this signal's blur radius
    # (CLOUD_TEX_LARGE_SIGMA=80, wider than the 41px guard band alone - a
    # real, pre-existing property of the reused CLOUD_TEX blur scale, not
    # introduced by this signal) - callers always pass a guard-band-eroded
    # mask in production (see analyze_sky_robust's sky_eroded), mirrored
    # here via a generously-sized excluded margin before eroding.
    gray = np.full((HEIGHT, WIDTH), 30, dtype=np.uint8)
    gray[:80, :80] = 255  # excluded corner
    sky_mask = np.full((HEIGHT, WIDTH), 255, dtype=np.uint8)
    sky_mask[:280, :280] = 0
    sky_mask = sc._erode_guard_band(sky_mask)

    score = sc._estimate_cloud_cover_texture_only(gray, sky_mask)

    assert score == 0.0


def test_real_twilight_band_measurements_stay_below_ceiling():
    # regression for the actual 2026-09-14 diagnostic: real ROI means
    # observed in this band (32.75-70.55, see starscalc.py's
    # CLOUD_TEX_REFERENCE_MEAN comment) rescaled a uniform-ish real sky back
    # toward the CLOUD_TEX_LOW floor. A uniform frame at any of these real
    # brightness levels (no synthetic patch at all) must stay at 0 - if
    # mean-rescaling were missing or wrong-signed, a bright uniform frame
    # alone could produce a false texture reading from blur-edge noise.
    sky_mask = np.full((HEIGHT, WIDTH), 255, dtype=np.uint8)
    for real_roi_mean in (32.75, 36.36, 39.20, 70.55):
        gray = np.full((HEIGHT, WIDTH), round(real_roi_mean), dtype=np.uint8)
        score = sc._estimate_cloud_cover_texture_only(gray, sky_mask)
        assert score == 0.0
