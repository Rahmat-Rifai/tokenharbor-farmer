import pytest
import socket
import urllib.error
from tor_manager import (
    is_port_open,
    parse_tor_status,
    rotate_tor_ip,
    find_tor_exe,
    ensure_tor_running,
)


def test_is_port_open_for_closed_port():
    # An obscure local port that is closed
    assert is_port_open(59998) is False


def test_is_port_open_for_active_port():
    # Spin up temporary listening socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    s.listen(1)
    port = s.getsockname()[1]
    try:
        assert is_port_open(port) is True
    finally:
        s.close()


def test_parse_tor_status():
    bootstrap_log = "Bootstrapped 100% (done): Done"
    assert "100%" in parse_tor_status(bootstrap_log)
    assert parse_tor_status("") == ""
    assert parse_tor_status(None) == ""


def test_rotate_tor_ip_mock(monkeypatch):
    class MockSocket:
        def __init__(self, *args, **kwargs):
            self.sent = b""

        def sendall(self, data):
            self.sent += data

        def recv(self, n):
            if b"AUTHENTICATE" in self.sent:
                return b"250 OK\r\n"
            return b"250 OK\r\n"

        def close(self):
            pass

    monkeypatch.setattr("socket.create_connection", lambda *args, **kwargs: MockSocket())
    assert rotate_tor_ip(9051) is True


def test_rotate_tor_ip_failure(monkeypatch):
    def fail_connection(*args, **kwargs):
        raise ConnectionRefusedError("Connection refused")

    monkeypatch.setattr("socket.create_connection", fail_connection)
    assert rotate_tor_ip(9051) is False


def test_rotate_tor_ip_bad_response(monkeypatch):
    class BadMockSocket:
        def __init__(self, *args, **kwargs):
            self.sent = b""

        def sendall(self, data):
            self.sent += data

        def recv(self, n):
            return b"515 Bad authentication\r\n"

        def close(self):
            pass

    monkeypatch.setattr("socket.create_connection", lambda *args, **kwargs: BadMockSocket())
    assert rotate_tor_ip(9051) is False


def test_find_tor_exe(tmp_path):
    tor_dir = tmp_path / "tor"
    tor_dir.mkdir()
    assert find_tor_exe(str(tor_dir)) is None

    sub_dir = tor_dir / "Tor"
    sub_dir.mkdir()
    fake_exe = sub_dir / "tor.exe"
    fake_exe.write_text("fake binary")

    assert find_tor_exe(str(tor_dir)) == str(fake_exe)


def test_ensure_tor_running_already_open(monkeypatch):
    monkeypatch.setattr("tor_manager.is_port_open", lambda port, host="127.0.0.1": True)
    assert ensure_tor_running() is True


def test_ensure_tor_running_with_existing_binary(tmp_path, monkeypatch):
    tor_dir = tmp_path / "tor"
    tor_dir.mkdir()
    fake_exe = tor_dir / "tor.exe"
    fake_exe.write_text("binary")

    # port open sequence: initially false, then true after launch
    calls = 0

    def mock_is_port_open(port, host="127.0.0.1"):
        nonlocal calls
        calls += 1
        return calls > 1

    monkeypatch.setattr("tor_manager.is_port_open", mock_is_port_open)
    monkeypatch.setattr("time.sleep", lambda s: None)

    popen_called = False

    def mock_popen(args, stdout=None, stderr=None):
        nonlocal popen_called
        popen_called = True
        return None

    monkeypatch.setattr("subprocess.Popen", mock_popen)

    assert ensure_tor_running(tor_dir=str(tor_dir), socks_port=9050, control_port=9051) is True
    assert popen_called is True
    torrc_content = (tor_dir / "torrc").read_text()
    assert 'DataDirectory "' in torrc_content


def test_ensure_tor_running_download_failure(tmp_path, monkeypatch):
    tor_dir = tmp_path / "tor"
    tor_dir.mkdir()

    monkeypatch.setattr("tor_manager.is_port_open", lambda port, host="127.0.0.1": False)

    def mock_urlopen(*args, **kwargs):
        raise urllib.error.URLError("Network unreachable")

    monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)

    assert ensure_tor_running(tor_dir=str(tor_dir)) is False

