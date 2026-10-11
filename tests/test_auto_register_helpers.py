import pytest
import os
import json
from unittest.mock import MagicMock, patch

from th_auto_register import make_signup_body, test_model_completion as run_test_model_completion, register_one
from th_tor_farm import load_state, save_state, run_farm


def test_make_signup_body():
    action_info = {
        "action_id": "601deb87587212e262e9f8b231f1cf29b6a227a0ad",
        "action_key": "kb3df6a1d48e1a01307dd1ff043d81c6e",
        "next_action": "601deb87587212e262e9f8b231f1cf29b6a227a0ad",
    }
    body, headers = make_signup_body("test@arxpays.my.id", "Password123!Aa", action_info)
    assert "Content-Type" in headers
    assert headers["Next-Action"] == "601deb87587212e262e9f8b231f1cf29b6a227a0ad"
    assert "test@arxpays.my.id" in body
    assert "Password123!Aa" in body


def test_state_load_save(tmp_path, monkeypatch):
    state_file = tmp_path / "test_state.json"
    monkeypatch.setattr("th_tor_farm.STATE_FILE", str(state_file))

    st = load_state()
    assert st == {"accounts": []}

    st["accounts"].append({"email": "test@test.com", "api_key": "thk_123"})
    save_state(st)

    reloaded = load_state()
    assert len(reloaded["accounts"]) == 1
    assert reloaded["accounts"][0]["email"] == "test@test.com"


def test_state_corrupt_file(tmp_path, monkeypatch):
    state_file = tmp_path / "corrupt_state.json"
    state_file.write_text("{bad json...", encoding="utf-8")
    monkeypatch.setattr("th_tor_farm.STATE_FILE", str(state_file))

    st = load_state()
    assert st == {"accounts": []}


def test_test_model_completion():
    with patch("requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp
        ok, info = run_test_model_completion("test-key")
        assert ok is True
        assert info == "200"

    with patch("requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_post.return_value = mock_resp
        ok, info = run_test_model_completion("test-key")
        assert ok is False
        assert info == "401"

    with patch("requests.post", side_effect=Exception("network down")):
        ok, info = run_test_model_completion("test-key")
        assert ok is False
        assert "network down" in info


def test_register_one_success(monkeypatch):
    mock_mail = MagicMock()
    mock_mail.name = "MockMail"
    mock_mail.generate_email.return_value = ("user@example.com", "ident123")
    mock_mail.wait_verification_link.return_value = "https://tokenharbor.ai/verify?token=abc"

    monkeypatch.setattr("th_auto_register.get_mail_client", lambda cfg: mock_mail)
    monkeypatch.setattr(
        "th_auto_register.th_action_resolver.resolve_signup_action",
        lambda proxies: {"action_id": "act1", "action_key": "k1", "next_action": "act1"},
    )

    mock_session = MagicMock()

    # s.get(login)
    mock_get_login = MagicMock()
    mock_get_login.status_code = 200

    # s.post(login)
    mock_post_login = MagicMock()
    mock_post_login.status_code = 200
    mock_post_login.text = '{"signedIn": true, "userId": "usr_999"}'

    # s.get(api/keys)
    mock_get_keys = MagicMock()
    mock_get_keys.status_code = 200
    mock_get_keys.json.return_value = {"keys": [{"id": "key_del_1"}]}

    # s.delete(api/keys)
    mock_del_key = MagicMock()
    mock_del_key.status_code = 200

    # s.post(api/keys)
    mock_post_key = MagicMock()
    mock_post_key.status_code = 201
    mock_post_key.json.return_value = {"plaintext": "thk_secret_123"}

    # s.post(api/me/privacy)
    mock_post_privacy = MagicMock()
    mock_post_privacy.status_code = 200
    mock_post_privacy.text = '{"ok":true}'

    # s.get(verify_link)
    mock_get_verify = MagicMock()
    mock_get_verify.status_code = 200

    def mock_get(url, **kwargs):
        if "mode=signup" in url:
            return mock_get_login
        elif "/api/keys" in url:
            return mock_get_keys
        elif "verify" in url:
            return mock_get_verify
        return MagicMock(status_code=200)

    def mock_post(url, **kwargs):
        if url.endswith("/login"):
            return mock_post_login
        elif url.endswith("/api/keys"):
            return mock_post_key
        elif url.endswith("/api/me/privacy"):
            return mock_post_privacy
        return MagicMock(status_code=200)

    mock_session.get.side_effect = mock_get
    mock_session.post.side_effect = mock_post
    mock_session.delete.return_value = mock_del_key

    monkeypatch.setattr("requests.Session", lambda: mock_session)

    cfg = {"tor_socks_port": 9050, "tor_control_port": 9051}
    acct, err = register_one(cfg)

    assert err is None
    assert acct is not None
    assert acct["email"] == "user@example.com"
    assert acct["userId"] == "usr_999"
    assert acct["api_key"] == "thk_secret_123"
    assert acct["verified"] is True
    assert acct["consent"] is True


def test_register_one_flagged_rotates_tor(monkeypatch):
    mock_mail = MagicMock()
    mock_mail.name = "MockMail"
    mock_mail.generate_email.return_value = ("user@example.com", "ident123")

    monkeypatch.setattr("th_auto_register.get_mail_client", lambda cfg: mock_mail)
    monkeypatch.setattr(
        "th_auto_register.th_action_resolver.resolve_signup_action",
        lambda proxies=None, **kw: {"action_id": "act1", "action_key": "k1", "next_action": "act1"},
    )
    monkeypatch.setattr("th_auto_register.th_action_resolver.invalidate_action_cache", lambda: True)

    rotated = []
    monkeypatch.setattr("th_auto_register.rotate_tor_ip", lambda cp: rotated.append(cp))
    monkeypatch.setattr("time.sleep", lambda s: None)

    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = '{"error": "Human check required"}'
    mock_session.post.return_value = mock_resp
    mock_session.get.return_value = MagicMock(status_code=200)

    monkeypatch.setattr("requests.Session", lambda: mock_session)

    cfg = {"tor_socks_port": 9050, "tor_control_port": 9051}
    acct, err = register_one(cfg)

    assert acct is None
    assert err == "Human check required"
    assert len(rotated) == 1
    assert rotated[0] == 9051


def test_register_one_empty_email(monkeypatch):
    mock_mail = MagicMock()
    mock_mail.name = "EmptyMailClient"
    mock_mail.generate_email.return_value = ("", "")
    monkeypatch.setattr("th_auto_register.get_mail_client", lambda cfg: mock_mail)

    acct, err = register_one({})
    assert acct is None
    assert "Failed to generate email address using EmptyMailClient" in err


def test_register_one_retry_on_initial_failure_succeeds(monkeypatch):
    mock_mail = MagicMock()
    mock_mail.name = "MockMail"
    mock_mail.generate_email.return_value = ("retry@example.com", "id_retry")
    mock_mail.wait_verification_link.return_value = "https://tokenharbor.ai/verify?token=retry"
    monkeypatch.setattr("th_auto_register.get_mail_client", lambda cfg: mock_mail)

    invalidated = []
    monkeypatch.setattr("th_auto_register.th_action_resolver.invalidate_action_cache", lambda: invalidated.append(True))

    resolved_calls = []
    def mock_resolve(proxies=None, force_refresh=False):
        resolved_calls.append(force_refresh)
        return {"action_id": "act_retry", "action_key": "k_retry", "next_action": "act_retry"}

    monkeypatch.setattr("th_auto_register.th_action_resolver.resolve_signup_action", mock_resolve)

    mock_session = MagicMock()
    post_calls = 0

    def mock_post(url, **kwargs):
        nonlocal post_calls
        if url.endswith("/login"):
            post_calls += 1
            resp = MagicMock()
            if post_calls == 1:
                resp.status_code = 500
                resp.text = '{"error": "Invalid action key"}'
            else:
                resp.status_code = 200
                resp.text = '{"signedIn": true, "userId": "usr_retry"}'
            return resp
        elif url.endswith("/api/keys"):
            resp = MagicMock(status_code=201)
            resp.json.return_value = {"plaintext": "thk_retry_ok"}
            return resp
        elif url.endswith("/api/me/privacy"):
            resp = MagicMock(status_code=200)
            resp.text = '{"ok": true}'
            return resp
        return MagicMock(status_code=200)

    mock_session.post.side_effect = mock_post
    mock_session.get.return_value = MagicMock(status_code=200, json=lambda: {"keys": []})
    monkeypatch.setattr("requests.Session", lambda: mock_session)

    cfg = {"tor_socks_port": 9050, "tor_control_port": 9051}
    acct, err = register_one(cfg)

    assert err is None
    assert acct is not None
    assert acct["email"] == "retry@example.com"
    assert len(invalidated) == 1
    assert True in resolved_calls  # force_refresh=True was invoked


def test_run_farm(tmp_path, monkeypatch):
    state_file = tmp_path / "test_state.json"
    monkeypatch.setattr("th_tor_farm.STATE_FILE", str(state_file))
    monkeypatch.setattr("th_tor_farm.ensure_tor_running", lambda **kw: True)
    monkeypatch.setattr("th_tor_farm.time.sleep", lambda s: None)

    rotated = []
    monkeypatch.setattr("th_tor_farm.rotate_tor_ip", lambda cp: rotated.append(cp))

    call_count = [0]

    def mock_register(cfg):
        call_count[0] += 1
        return {
            "email": f"user{call_count[0]}@example.com",
            "password": "pwd",
            "userId": f"usr_{call_count[0]}",
            "api_key": f"thk_{call_count[0]}",
            "verified": True,
            "consent": True,
        }, None

    monkeypatch.setattr("th_tor_farm.register_one", mock_register)
    monkeypatch.setattr("th_tor_farm.test_model_completion", lambda k: (True, "200"))
    monkeypatch.setattr("th_tor_farm.inject_9router", lambda k, e, cfg: (True, "TH injected"))

    run_farm(target_count=2, no_inject=False)

    saved = load_state()
    assert len(saved["accounts"]) == 2
    assert saved["accounts"][0]["email"] == "user1@example.com"
    assert saved["accounts"][1]["email"] == "user2@example.com"
    assert saved["accounts"][0]["injected"] is True
    assert saved["accounts"][0]["test_result"] == "200"
    # success % 2 == 0 triggers rotation
    assert len(rotated) >= 1


def test_run_farm_catches_unhandled_exceptions(tmp_path, monkeypatch):
    state_file = tmp_path / "test_state_exc.json"
    monkeypatch.setattr("th_tor_farm.STATE_FILE", str(state_file))
    monkeypatch.setattr("th_tor_farm.ensure_tor_running", lambda **kw: True)
    monkeypatch.setattr("th_tor_farm.time.sleep", lambda s: None)
    monkeypatch.setattr("th_tor_farm.rotate_tor_ip", lambda cp: True)

    attempts = 0

    def mock_register(cfg):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("Unexpected network disconnect!")
        return {
            "email": "survivor@example.com",
            "password": "pwd",
            "userId": "usr_survivor",
            "api_key": "thk_survivor",
            "verified": True,
            "consent": True,
        }, None

    monkeypatch.setattr("th_tor_farm.register_one", mock_register)
    monkeypatch.setattr("th_tor_farm.test_model_completion", lambda k: (True, "200"))
    monkeypatch.setattr("th_tor_farm.inject_9router", lambda k, e, cfg: (True, "TH injected"))

    run_farm(target_count=1, no_inject=False)

    saved = load_state()
    assert len(saved["accounts"]) == 1
    assert saved["accounts"][0]["email"] == "survivor@example.com"


def test_auto_register_single_cli_success(tmp_path, monkeypatch):
    from th_auto_register import main as auto_register_main

    state_file = tmp_path / "test_state_cli.json"
    monkeypatch.setattr("th_auto_register.STATE_FILE", str(state_file))
    monkeypatch.setattr("th_auto_register.ensure_tor_running", lambda **kw: True)
    monkeypatch.setattr(
        "th_auto_register.register_one",
        lambda cfg: (
            {
                "email": "cli@example.com",
                "password": "pwd",
                "userId": "usr_cli",
                "api_key": "thk_cli",
                "verified": True,
                "consent": True,
            },
            None,
        ),
    )
    monkeypatch.setattr("th_auto_register.test_model_completion", lambda k: (True, "200"))
    monkeypatch.setattr("th_auto_register.inject_9router", lambda k, e, cfg: (True, "Injected"))

    # Test "single" argument
    code = auto_register_main(["single"])
    assert code == 0

    saved = json.loads(state_file.read_text(encoding="utf-8"))
    assert len(saved["accounts"]) == 1
    assert saved["accounts"][0]["email"] == "cli@example.com"
    assert saved["accounts"][0]["injected"] is True


def test_auto_register_single_cli_no_args_and_failure(tmp_path, monkeypatch):
    from th_auto_register import main as auto_register_main

    state_file = tmp_path / "test_state_cli2.json"
    monkeypatch.setattr("th_auto_register.STATE_FILE", str(state_file))
    monkeypatch.setattr("th_auto_register.ensure_tor_running", lambda **kw: True)
    monkeypatch.setattr("th_auto_register.register_one", lambda cfg: (None, "Tor timeout"))

    # Test empty args (defaulting to single) with failure
    code = auto_register_main([])
    assert code == 1

    # Test unknown mode
    code_unknown = auto_register_main(["unknown_mode"])
    assert code_unknown == 1
