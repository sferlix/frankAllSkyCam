'''
Unit tests for sqmcache.py: reuse window, interval 1 (off) and unreadable cache files.
'''

import os

from frankAllSkyCam import sqmcache


def _app(tmp_path):
    os.makedirs(tmp_path / "log", exist_ok=True)
    return str(tmp_path)


def test_interval_of_one_minute_never_reuses(tmp_path):
    app = _app(tmp_path)
    sqmcache.save(app, 20.5, "n", now=1000.0)
    assert sqmcache.load(app, 1, now=1010.0) is None


def test_reading_is_reused_until_it_is_due(tmp_path):
    app = _app(tmp_path)
    sqmcache.save(app, 20.5, "n", now=1000.0)
    assert sqmcache.load(app, 5, now=1060.0) == (20.5, "n")
    assert sqmcache.load(app, 5, now=1000.0 + 5 * 60 - sqmcache.SLACK_SECS - 1) == (20.5, "n")
    assert sqmcache.load(app, 5, now=1000.0 + 5 * 60 - sqmcache.SLACK_SECS) is None
    assert sqmcache.load(app, 5, now=990.0) is None  # clock went back


def test_missing_or_broken_cache_means_measure(tmp_path):
    app = _app(tmp_path)
    assert sqmcache.load(app, 5) is None
    (tmp_path / sqmcache.CACHE_FILE).write_text("{not json")
    assert sqmcache.load(app, 5) is None
    sqmcache.save(app, 19.9, "y", now=50.0)
    assert sorted(os.listdir(tmp_path / "log")) == ["sqm_last.json"]
