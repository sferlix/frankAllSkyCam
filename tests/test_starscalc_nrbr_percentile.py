'''
Unit tests for the percentile aggregation of starscalc._estimate_cloud_cover_nrbr
(DAY_NRBR_AGG_PERCENTILE, used by the twilight ISP path). Synthetic arrays: a minority
of cloud-like pixels (aureole, horizon whitening) does not raise the score, a
majority-cloudy sky still reads high.
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
    # 30% of the sky reads cloud-like: below DAY_NRBR_AGG_PERCENTILE, so the score stays
    # at the clear majority value instead of the 30% a plain mean would give
    img = _make_img(cloud_fraction=0.30)
    sky_mask = np.full((HEIGHT, WIDTH), 255, dtype=np.uint8)

    assert sc._estimate_cloud_cover_nrbr(img, sky_mask) == 0.0


def test_majority_cloud_still_reads_high():
    # 70% of the sky is cloud-like: above DAY_NRBR_AGG_PERCENTILE, so a mostly overcast
    # sky still reads high
    img = _make_img(cloud_fraction=0.70)
    sky_mask = np.full((HEIGHT, WIDTH), 255, dtype=np.uint8)

    assert sc._estimate_cloud_cover_nrbr(img, sky_mask) == 100.0
