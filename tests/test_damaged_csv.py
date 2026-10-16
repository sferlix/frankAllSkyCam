'''
CSV files damaged by an unclean shutdown (NUL bytes, truncated rows) must not stop the
readers: nightcalib samples (and their layout migration), skyprojection calibration
samples and the SQM exposure table. Also the raw-frame archive kept for analysis checks.
'''

import datetime
import os
import random

from frankAllSkyCam import nightcalib as nc
from frankAllSkyCam import rawframes
from frankAllSkyCam import skyprojection as sp

from test_nightcalib import FEATURES, _month, _write_samples


def _damage(path, after_line):
    # replace one line with NUL bytes plus a truncated row, as an interrupted write leaves it
    lines = open(path, newline="").read().split("\n")
    lines[after_line] = "\0" * 40 + lines[after_line][:17]
    open(path, "w", newline="").write("\n".join(lines))


def test_samples_with_nul_bytes_are_still_read(tmp_path):
    app = str(tmp_path)
    start = datetime.datetime(2026, 9, 1, 22, tzinfo=datetime.timezone.utc)
    _write_samples(app, _month(random.Random(5)), "fp1", start)
    path = os.path.join(app, nc.SAMPLES_FILE)
    _damage(path, 500)
    rows = nc.read_samples(app, "fp1", start - datetime.timedelta(days=1))
    assert len(rows) == 30 * 40 - 1


def test_calibration_runs_on_a_damaged_samples_file(tmp_path):
    app = str(tmp_path)
    start = datetime.datetime(2026, 9, 1, 22, tzinfo=datetime.timezone.utc)
    _write_samples(app, _month(random.Random(5)), "fp1", start)
    path = os.path.join(app, nc.SAMPLES_FILE)
    _damage(path, 500)
    params = nc.maybe_calibrate(app, "fp1", now=start + datetime.timedelta(days=31))
    assert params is not None
    # pruning rewrote the file without the damaged row
    assert "\0" not in open(path, newline="").read()


def test_record_migrates_the_legacy_layout_and_logs_cloud_and_stars(tmp_path):
    app = str(tmp_path)
    (tmp_path / "log").mkdir()
    path = tmp_path / nc.SAMPLES_FILE
    legacy = ",".join(nc.FIELDS[:nc.LEGACY_FIELD_COUNT])
    old_row = "2026-10-01T22:00:00+00:00,2026-10-01,fp1,-30.0,0.1,10.0,2.1,0.4,4.0,20,0"
    path.write_text(legacy + "\n" + old_row + "\n" + "\0" * 30 + "\n")
    assert nc.record(app, dict(FEATURES, cloud_pct=12.34, reported_stars=88), "fp1")
    lines = path.read_text().splitlines()
    assert lines[0].split(",") == nc.FIELDS
    assert lines[1].split(",") == old_row.split(",") + ["", ""]
    assert lines[2].split(",")[-2:] == ["12.3", "88"]
    assert len(lines) == 3
    # rows without the new values still record, with empty fields
    assert nc.record(app, FEATURES, "fp1")
    assert path.read_text().splitlines()[3].split(",")[-2:] == ["", ""]
    assert len(nc.read_samples(app, "fp1", datetime.datetime(2026, 9, 1, tzinfo=datetime.timezone.utc))) == 3


def test_skyprojection_samples_with_nul_bytes(tmp_path):
    csv_path = str(tmp_path / "sky_calibration.csv")
    sp.record_calibration_sample(csv_path, "2026-09-14T12:00:00+00:00", "sun", 40.0, 180.0, 500.0, 300.0)
    with open(csv_path, "a", newline="") as f:
        f.write("\0" * 20 + "2026-09-14T12:3\n")
    sp.record_calibration_sample(csv_path, "2026-09-14T13:00:00+00:00", "sun", 41.0, 190.0, 520.0, 310.0)
    assert len(sp.load_calibration_samples(csv_path, "sun")) == 2


def test_raw_frames_keeps_one_frame_per_interval_and_prunes(tmp_path):
    app = str(tmp_path)
    src = tmp_path / "frame.jpg"
    src.write_bytes(b"jpeg")
    t0 = 1_800_000_000.0
    assert rawframes.save(app, str(src), now=t0)
    assert not rawframes.save(app, str(src), now=t0 + 10 * 60)           # too soon
    src2 = tmp_path / "frame2.jpg"
    src2.write_bytes(b"jpeg2")
    assert rawframes.save(app, str(src2), now=t0 + 30 * 60)
    folder = tmp_path / rawframes.RAW_DIR
    assert sorted(os.listdir(folder)) == ["frame.jpg", "frame2.jpg"]
    # past KEEP_DAYS both expire; the new frame is kept
    src3 = tmp_path / "frame3.jpg"
    src3.write_bytes(b"jpeg3")
    assert rawframes.save(app, str(src3), now=t0 + (rawframes.KEEP_DAYS + 1) * 86400)
    assert os.listdir(folder) == ["frame3.jpg"]


def test_raw_frames_never_raises(tmp_path):
    assert not rawframes.save(str(tmp_path), str(tmp_path / "missing.jpg"))
