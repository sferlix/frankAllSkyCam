'''
Unit tests for starscalc._estimate_cloud_cover_nrbr's percentile aggregation
(DAY_NRBR_AGG_PERCENTILE). Synthetic arrays, not real captures - the
percentile value itself is calibrated on real daytime frames (see the
comment on DAY_NRBR_AGG_PERCENTILE in starscalc.py); these only check the
aggregation behaves as documented: a mean is sensitive to any contaminated
minority of pixels (circumsolar aureole, horizon-ward whitening), a
below-median percentile isn't, while a majority-cloudy sky still reads high
either way.
'''

import numpy as np

from frankAllSkyCam import starscalc as sc

HEIGHT, WIDTH = 768, 1024  # matches this install's configured capture resolution


def _make_img(cloud_fraction):
    # first `cloud_fraction` of rows read as cloud-like (B == R, NRBR == 0,
    # well below DAY_NRBR_CLOUD -> score 1.0), the rest as clear blue sky
    # (NRBR well above DAY_NRBR_CLEAR -> score 0.0)
    img = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
    split = int(HEIGHT * cloud_fraction)
    img[:split, :] = (150, 150, 150)  # BGR: B == R -> cloud-like
    img[split:, :] = (200, 120, 50)   # BGR: B >> R -> clear-blue-like
    return img


def test_uniform_clear_sky_scores_zero():
    img = _make_img(cloud_fraction=0.0)
    sky_mask = np.full((HEIGHT, WIDTH), 255, dtype=np.uint8)

    assert sc._estimate_cloud_cover_nrbr(img, sky_mask) == 0.0


def test_uniform_overcast_sky_scores_full():
    img = _make_img(cloud_fraction=1.0)
    sky_mask = np.full((HEIGHT, WIDTH), 255, dtype=np.uint8)

    assert sc._estimate_cloud_cover_nrbr(img, sky_mask) == 100.0


def test_minority_contamination_does_not_inflate_score():
    # 30% of the sky reads cloud-like (e.g. circumsolar aureole or the
    # horizon-ward band) - below DAY_NRBR_AGG_PERCENTILE, so the reported
    # score stays at the majority (clear) value instead of being dragged up
    # to the 30% a plain mean would report
    img = _make_img(cloud_fraction=0.30)
    sky_mask = np.full((HEIGHT, WIDTH), 255, dtype=np.uint8)

    assert sc._estimate_cloud_cover_nrbr(img, sky_mask) == 0.0


def test_majority_cloud_still_reads_high():
    # 70% of the sky is genuinely cloud-like - well above
    # DAY_NRBR_AGG_PERCENTILE, so a real mostly-overcast sky is not
    # suppressed by the switch away from the mean
    img = _make_img(cloud_fraction=0.70)
    sky_mask = np.full((HEIGHT, WIDTH), 255, dtype=np.uint8)

    assert sc._estimate_cloud_cover_nrbr(img, sky_mask) == 100.0
