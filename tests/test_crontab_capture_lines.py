'''
Unit tests for crontab._captureLines: the capture schedule written by getTimes(), every
minute by day and every night_interval_minutes at night.
'''

from frankAllSkyCam import crontab


def _schedules(lines):
    return [line.split(" python3")[0] for line in lines]


def test_night_runs_every_two_minutes_by_default():
    assert _schedules(crontab._captureLines(7, 19, 2, "log")) == ["*/1 7-18 * * *", "*/2 19-23 * * *", "*/2 0-6 * * * "]


def test_night_interval_follows_the_setting():
    assert _schedules(crontab._captureLines(7, 19, 1, "log")) == ["*/1 7-18 * * *", "*/1 19-23 * * *", "*/1 0-6 * * * "]


def test_lines_run_the_capture_and_log_it():
    for line in crontab._captureLines(7, 19, 1, "/home/pi/frankAllSkyCam/log"):
        assert "python3 -m frankAllSkyCam >/home/pi/frankAllSkyCam/log/capture.log 2>&1" in line
        assert line.endswith(crontab.MARKER + "\n")


def test_extreme_latitudes_skip_empty_ranges():
    assert _schedules(crontab._captureLines(0, 0, 2, "log")) == ["*/2 0-23 * * *"]
