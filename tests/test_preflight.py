import pytest
from th_preflight import check_dependencies, run_preflight


def test_check_dependencies():
    ok, missing = check_dependencies(["requests", "pytest"])
    assert ok is True
    assert len(missing) == 0


def test_check_dependencies_missing():
    ok, missing = check_dependencies(["non_existent_module_xyz_123"])
    assert ok is False
    assert "non_existent_module_xyz_123" in missing


def test_run_preflight_mock(monkeypatch, tmp_path):
    fake_db = tmp_path / "mock.sqlite"
    fake_db.touch()
    monkeypatch.setattr("db_path.find_9router_db", lambda: str(fake_db))
    monkeypatch.setattr("tor_manager.is_port_open", lambda port: True)
    mock_client = type("MockClient", (), {"name": "mock", "test_connection": lambda self: (True, "OK")})()
    monkeypatch.setattr("th_preflight.get_mail_client", lambda cfg: mock_client)

    ok = run_preflight()
    assert ok is True


def test_run_preflight_imap_failure(monkeypatch, tmp_path):
    fake_db = tmp_path / "mock.sqlite"
    fake_db.touch()
    monkeypatch.setattr("db_path.find_9router_db", lambda: str(fake_db))
    monkeypatch.setattr("tor_manager.is_port_open", lambda port: True)
    mock_client = type("MockClient", (), {"name": "mock", "test_connection": lambda self: (False, "Auth failed")})()
    monkeypatch.setattr("th_preflight.get_mail_client", lambda cfg: mock_client)

    ok = run_preflight()
    assert ok is False


def test_run_preflight_non_imap_provider(monkeypatch, tmp_path):
    fake_db = tmp_path / "mock.sqlite"
    fake_db.touch()
    monkeypatch.setattr("db_path.find_9router_db", lambda: str(fake_db))
    monkeypatch.setattr("tor_manager.is_port_open", lambda port: True)
    mock_client = type("MockClient", (), {"name": "tempmail.lol"})()
    monkeypatch.setattr("th_preflight.get_mail_client", lambda cfg: mock_client)

    ok = run_preflight()
    assert ok is True


def test_run_preflight_db_missing(monkeypatch, tmp_path):
    missing_db = tmp_path / "missing.sqlite"
    monkeypatch.setattr("db_path.find_9router_db", lambda: str(missing_db))
    monkeypatch.setattr("tor_manager.is_port_open", lambda port: True)
    monkeypatch.setattr("th_preflight.get_mail_client", lambda cfg: type("MockClient", (), {"name": "mock", "test_connection": lambda s: (True, "OK")})())

    ok = run_preflight()
    assert ok is False


def test_run_preflight_db_unreadable(monkeypatch, tmp_path):
    bad_db = tmp_path / "corrupt.sqlite"
    bad_db.write_text("not a sqlite database")
    monkeypatch.setattr("db_path.find_9router_db", lambda: str(bad_db))
    monkeypatch.setattr("tor_manager.is_port_open", lambda port: True)
    monkeypatch.setattr("th_preflight.get_mail_client", lambda cfg: type("MockClient", (), {"name": "mock", "test_connection": lambda s: (True, "OK")})())

    ok = run_preflight()
    assert ok is False


def test_run_preflight_deps_missing(monkeypatch, tmp_path):
    fake_db = tmp_path / "mock.sqlite"
    fake_db.touch()
    monkeypatch.setattr("db_path.find_9router_db", lambda: str(fake_db))
    monkeypatch.setattr("tor_manager.is_port_open", lambda port: True)
    monkeypatch.setattr("th_preflight.check_dependencies", lambda deps: (False, ["missing_pkg"]))
    monkeypatch.setattr("th_preflight.get_mail_client", lambda cfg: type("MockClient", (), {"name": "mock", "test_connection": lambda s: (True, "OK")})())

    ok = run_preflight()
    assert ok is False


def test_tui_exit(monkeypatch):
    import th_tui

    monkeypatch.setattr("th_tui.is_port_open", lambda port: True)
    monkeypatch.setattr("rich.prompt.Prompt.ask", lambda *args, **kwargs: "0")
    monkeypatch.setattr("rich.console.Console.clear", lambda self: None)
    th_tui.main()


def test_tui_menu_options(monkeypatch):
    import th_tui

    # Simulate sequence of inputs: "3" (preflight), then Enter, "4" (rotate), Enter, "5" (list accounts), Enter, "0" (exit)
    inputs = ["3", "", "4", "", "5", "", "0"]

    def fake_ask(*args, **kwargs):
        if inputs:
            return inputs.pop(0)
        return "0"

    monkeypatch.setattr("th_tui.is_port_open", lambda port: True)
    monkeypatch.setattr("rich.prompt.Prompt.ask", fake_ask)
    monkeypatch.setattr("rich.console.Console.clear", lambda self: None)
    monkeypatch.setattr("th_tui.run_preflight", lambda: True)
    monkeypatch.setattr("th_tui.rotate_tor_ip", lambda: True)
    monkeypatch.setattr(
        "th_tui.load_state",
        lambda: {
            "accounts": [
                {"email": "test@domain.com", "api_key": "thk_1234567890abcdef", "verified": True, "injected": True}
            ]
        },
    )

    th_tui.main()


def test_tui_menu_register_and_farm(monkeypatch):
    import th_tui

    # Simulate: "1" (register success), Enter, "1" (register fail), Enter, "2" (farm), Enter, "0" (exit)
    inputs = ["1", "", "1", "", "2", "", "0"]

    def fake_ask(*args, **kwargs):
        if inputs:
            return inputs.pop(0)
        return "0"

    monkeypatch.setattr("th_tui.is_port_open", lambda port: True)
    monkeypatch.setattr("rich.prompt.Prompt.ask", fake_ask)
    monkeypatch.setattr("rich.prompt.IntPrompt.ask", lambda *args, **kwargs: 2)
    monkeypatch.setattr("rich.console.Console.clear", lambda self: None)
    monkeypatch.setattr("th_tui.ensure_tor_running", lambda: True)

    reg_results = [
        ({"email": "reg@test.com", "api_key": "thk_reg123"}, None),
        (None, "Signup error"),
    ]

    def fake_register(cfg):
        return reg_results.pop(0)

    monkeypatch.setattr("th_tui.register_one", fake_register)
    monkeypatch.setattr("th_tui.inject_9router", lambda key, email, cfg: (True, "OK"))
    monkeypatch.setattr("th_tui.run_farm", lambda n: None)
    monkeypatch.setattr("th_tui.load_state", lambda: {"accounts": []})
    monkeypatch.setattr("th_tui.save_state", lambda st: None)

    th_tui.main()


