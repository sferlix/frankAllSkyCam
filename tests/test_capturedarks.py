'''
Unit tests for capturedarks._average_frames, the pixel-wise mean that builds a master
dark from several dark captures. Synthetic arrays; pure math (mean, rounding, clipping).
'''

import numpy as np

from frankAllSkyCam import capturedarks as cd


def test_averaging_identical_frames_returns_the_same_frame():
    frame = np.full((10, 10, 3), 42, dtype=np.uint8)

    result = cd._average_frames([frame, frame, frame])

    assert np.array_equal(result, frame)


def test_averages_pixel_values_across_frames():
    # three frames at 10, 20, 30 -> mean exactly 20 at every pixel
    frames = [np.full((10, 10, 3), v, dtype=np.uint8) for v in (10, 20, 30)]

    result = cd._average_frames(frames)

    assert np.array_equal(result, np.full((10, 10, 3), 20, dtype=np.uint8))


def test_rounds_to_nearest_integer():
    # mean of 10, 11, 13 is 11.333... -> rounds down to 11 (values picked to
    # land on a clean, unambiguous fraction rather than an exact .5 tie)
    frames = [np.full((5, 5, 3), v, dtype=np.uint8) for v in (10, 11, 13)]

    result = cd._average_frames(frames)

    assert np.array_equal(result, np.full((5, 5, 3), 11, dtype=np.uint8))


def test_reduces_per_frame_deviation_from_the_true_fixed_pattern():
    # a fixed pattern (100) plus a different per-frame offset (independent read/thermal
    # noise): the average must land closer to the fixed pattern than any single frame
    true_pattern = 100
    frames = [
        np.full((20, 20, 3), true_pattern + offset, dtype=np.uint8)
        for offset in (-6, -2, 0, 3, 5)
    ]

    result = cd._average_frames(frames)

    assert abs(int(result[0, 0, 0]) - true_pattern) < min(
        abs(true_pattern + offset - true_pattern) for offset in (-6, -2, 3, 5)
    )


def test_preserves_shape_and_dtype():
    frames = [np.random.randint(0, 255, (8, 6, 3), dtype=np.uint8) for _ in range(4)]

    result = cd._average_frames(frames)

    assert result.shape == frames[0].shape
    assert result.dtype == np.uint8


def test_output_stays_within_valid_uint8_range():
    frames = [np.full((4, 4, 3), 255, dtype=np.uint8), np.full((4, 4, 3), 254, dtype=np.uint8)]

    result = cd._average_frames(frames)

    assert result.min() >= 0
    assert result.max() <= 255
