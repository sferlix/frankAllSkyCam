'''
fileManager.saveToFTP() must not block forever on a dead FTP session (ftplib has no
socket timeout by default).
'''

import socket
import threading
import time

from frankAllSkyCam import fileManager


def test_ftp_session_is_opened_with_a_timeout(monkeypatch, tmp_path):
    seen = {}

    class FakeFTP:
        def __init__(self, *args, **kwargs):
            seen["kwargs"] = kwargs
            raise OSError("stop here")

    monkeypatch.setattr(fileManager.ftplib, "FTP", FakeFTP)
    local = tmp_path / "img.jpg"
    local.write_bytes(b"x")

    fileManager.saveToFTP(True, str(local), "h", "u", "p", "img.jpg")

    assert seen["kwargs"].get("timeout") == fileManager.FTP_TIMEOUT_SECS
    assert 0 < fileManager.FTP_TIMEOUT_SECS <= 120


def test_silent_server_does_not_hang_and_is_reported_as_ftp_error(monkeypatch, tmp_path, capsys):
    # a server that accepts the TCP connection and then never sends the FTP greeting
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    held = []
    threading.Thread(target=lambda: held.append(srv.accept()), daemon=True).start()

    monkeypatch.setattr(fileManager.ftplib.FTP, "port", port)
    monkeypatch.setattr(fileManager, "FTP_TIMEOUT_SECS", 0.5)
    local = tmp_path / "img.jpg"
    local.write_bytes(b"x")

    start = time.monotonic()
    try:
        fileManager.saveToFTP(True, str(local), "127.0.0.1", "u", "p", "img.jpg")
    finally:
        srv.close()
        for conn, _ in held:
            conn.close()
    elapsed = time.monotonic() - start

    assert elapsed < 5
    assert "FTP ERROR" in capsys.readouterr().out
