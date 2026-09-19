'''
Tests for the WS90 export in defaults/tools/generateExtraData.py: the tool fetches the
station JSON, saves it as tools/ws90_data.json and optionally uploads it ([ftp] section of
generateExtraData.conf). It is independent of the capture's sky_status.json.

The tool is a user-editable script outside the package, so it is imported straight from
its file. No network: the station and the FTP layer are replaced by fakes.
'''

import importlib.util
import io
import json
import os
import shutil

import pytest

REPO = os.path.join(os.path.dirname(__file__), "..")
TOOLS = next(d for d in (os.path.join(REPO, "frankAllSkyCam", "defaults", "tools"),
                         os.path.join(REPO, "defaults", "tools")) if os.path.isdir(d))

WS90 = {"sensors": {"temperature_s": {"value": 18.2, "unit": "C"},
                    "humidity_u8": {"value": 64, "unit": "%"},
                    "wind_speed": {"value": 4.5, "unit": "km/h"}}}


@pytest.fixture
def tool(tmp_path):
    # a private copy so tests can point basePath at tmp_path
    for f in ("generateExtraData.py", "generateExtraData.conf"):
        shutil.copy(os.path.join(TOOLS, f), tmp_path / f)
    (tmp_path / "tools").mkdir()
    spec = importlib.util.spec_from_file_location("gen_extra_data", tmp_path / "generateExtraData.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.basePath = str(tmp_path) + os.sep
    return module


def _fake_station(monkeypatch, tool, payload=WS90, fail=False):
    def urlopen(req, timeout=None):
        if fail:
            raise OSError("station unreachable")
        return io.BytesIO(json.dumps(payload).encode("utf-8"))

    monkeypatch.setattr(tool.urllib.request, "urlopen", urlopen)


def test_a_disabled_station_is_not_queried_and_writes_nothing(tool, tmp_path, monkeypatch):
    monkeypatch.setattr(tool, "METEO_ENABLED", False)
    _fake_station(monkeypatch, tool, fail=True)   # would raise if it were queried

    assert tool.getMeteoStationData("http://station/data") == ("", {})
    assert not (tmp_path / "tools" / "ws90_data.json").exists()


def test_the_station_json_is_saved_as_its_own_file(tool, tmp_path, monkeypatch):
    monkeypatch.setattr(tool, "METEO_ENABLED", True)
    monkeypatch.setattr(tool, "WS90FTP_ENABLED", False)
    _fake_station(monkeypatch, tool)

    text, sensors = tool.getMeteoStationData("http://station/data")

    assert sensors["temperature_s"]["value"] == 18.2
    assert "Hum: 64 %" in text
    assert json.loads((tmp_path / "tools" / "ws90_data.json").read_text()) == WS90


def test_the_ws90_json_is_uploaded_when_ftp_is_enabled(tool, tmp_path, monkeypatch):
    uploads = []
    monkeypatch.setattr(tool, "METEO_ENABLED", True)
    monkeypatch.setattr(tool, "WS90FTP_ENABLED", True)
    monkeypatch.setattr(tool, "FTP_UPLOAD_PATH", "/your_folder/ws90_data.json")
    monkeypatch.setattr(tool, "_ftp_upload", lambda local, remote: uploads.append((local, remote)))
    _fake_station(monkeypatch, tool)

    tool.getMeteoStationData("http://station/data")

    assert uploads == [(str(tmp_path) + os.sep + "tools/ws90_data.json", "/your_folder/ws90_data.json")]


def test_an_unreachable_station_gives_no_file_and_no_upload(tool, tmp_path, monkeypatch):
    uploads = []
    monkeypatch.setattr(tool, "METEO_ENABLED", True)
    monkeypatch.setattr(tool, "WS90FTP_ENABLED", True)
    monkeypatch.setattr(tool, "_ftp_upload", lambda *a: uploads.append(a))
    _fake_station(monkeypatch, tool, fail=True)

    assert tool.getMeteoStationData("http://station/data") == ("", {})
    assert uploads == [] and not (tmp_path / "tools" / "ws90_data.json").exists()


def test_a_failing_upload_never_raises(tool, monkeypatch):
    def boom(*a):
        raise OSError("connection reset")

    monkeypatch.setattr(tool, "_ftp_upload", boom)
    tool.sendWS90_data_to_web("/some/ws90_data.json")   # must not raise


def test_ftp_upload_uses_a_socket_timeout(tool, tmp_path, monkeypatch):
    seen = {}

    class FakeFTP:
        def __init__(self, host, user, password, **kwargs):
            seen.update(kwargs=kwargs)
            raise OSError("stop here")

    monkeypatch.setattr(tool, "FTP", FakeFTP)
    local = tmp_path / "x.json"
    local.write_text("{}")

    with pytest.raises(OSError):
        tool._ftp_upload(str(local), "/x.json")

    assert 0 < seen["kwargs"]["timeout"] <= 120


def test_the_tool_does_not_know_the_capture_status_file():
    # the two exports are independent: the WS90 tool never reads or merges sky_status.json
    source = open(os.path.join(TOOLS, "generateExtraData.py"), encoding="utf-8").read()
    conf = open(os.path.join(TOOLS, "generateExtraData.conf"), encoding="utf-8").read()
    assert "sky_status" not in source and "sky_status" not in conf
