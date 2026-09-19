'''
Unit tests for analyze_sky_robust's skip_star_detection parameter: it skips the
expensive star detection (star_count becomes None) and must never change cloud_cover,
which is computed independently.

Uses a real temp JPEG because it tests the wiring of the top-level function.
'''

import cv2
import numpy as np

from frankAllSkyCam import starscalc as sc

HEIGHT, WIDTH = 768, 1024  # matches this install's configured capture resolution


def _write_night_frame(path, mean_gray=30):
    # a bit of texture, so _find_stars has something to work on (a flat frame finds zero
    # stars either way)
    rng = np.random.default_rng(42)
    img = np.clip(mean_gray + rng.normal(0, 3, (HEIGHT, WIDTH)), 0, 255).astype(np.uint8)
    img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    cv2.imwrite(str(path), img)


def test_skip_star_detection_returns_none_star_count(tmp_path):
    path = tmp_path / "night.jpg"
    _write_night_frame(path)

    star_count, cloud_cover = sc.analyze_sky_robust(str(path), diametro_rapporto=0.65,
                                                      skip_star_detection=True)

    assert star_count is None
    assert isinstance(cloud_cover, float)


def test_default_behavior_still_runs_star_detection(tmp_path):
    path = tmp_path / "night.jpg"
    _write_night_frame(path)

    star_count, cloud_cover = sc.analyze_sky_robust(str(path), diametro_rapporto=0.65)

    assert star_count is not None
    assert isinstance(star_count, int)


def test_skipping_star_detection_does_not_change_cloud_cover(tmp_path):
    path = tmp_path / "night.jpg"
    _write_night_frame(path)

    _, cloud_with_stars = sc.analyze_sky_robust(str(path), diametro_rapporto=0.65,
                                                 skip_star_detection=False)
    _, cloud_skipped = sc.analyze_sky_robust(str(path), diametro_rapporto=0.65,
                                              skip_star_detection=True)

    assert cloud_skipped == cloud_with_stars


def test_day_branch_unaffected_by_skip_star_detection(tmp_path):
    # the day branch never runs star detection: skip_star_detection must be a no-op there
    path = tmp_path / "day.jpg"
    img = np.full((HEIGHT, WIDTH, 3), 150, dtype=np.uint8)  # well above DAYTIME_MEAN_THRESHOLD
    cv2.imwrite(str(path), img)

    result_default = sc.analyze_sky_robust(str(path), diametro_rapporto=0.65)
    result_skipped = sc.analyze_sky_robust(str(path), diametro_rapporto=0.65, skip_star_detection=True)

    assert result_default == result_skipped
    assert result_default[0] == 0  # day branch always reports 0 stars, not None
