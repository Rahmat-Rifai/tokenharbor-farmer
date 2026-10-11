import sqlite3
import json
import pytest
from unittest.mock import patch, MagicMock

from inject_th_kv import inject_into_db, sync_9router_http, inject_9router
from db_path import find_9router_db


def test_inject_into_db_creates_connection(tmp_path):
    db_file = tmp_path / "test_9router.sqlite"
    conn = sqlite3.connect(str(db_file))
    conn.execute("""
        CREATE TABLE providerConnections (
            id TEXT PRIMARY KEY,
            provider TEXT,
            authType TEXT,
            name TEXT,
            email TEXT,
            priority INTEGER,
            isActive INTEGER,
            data TEXT,
            createdAt TEXT,
            updatedAt TEXT
        )
    """)
    conn.execute("CREATE TABLE kv (scope TEXT, key TEXT, value TEXT)")
    conn.commit()
    conn.close()

    cfg = {
        "default_model": "deepseek-v4.1-flash:free",
        "model_locks": ["deepseek-v4.1-flash:free", "mimo-v2.5:free", "qwen3.8-27b:free"]
    }
    ok, label = inject_into_db(str(db_file), "thk_live_testkey123", "user@test.com", cfg)
    assert ok is True
    assert "TH" in label

    conn = sqlite3.connect(str(db_file))
    cur = conn.cursor()
    row = cur.execute("SELECT provider, authType, name, email, data FROM providerConnections LIMIT 1").fetchone()
    provider, auth_type, name, email, raw_data = row
    assert provider == "openai-compatible"
    assert auth_type == "apikey"
    assert name == label
    assert email == "user@test.com"

    data = json.loads(raw_data)
    assert data["apiKey"] == "thk_live_testkey123"
    assert data["defaultModel"] == "deepseek-v4.1-flash:free"
    assert data["modelLock_deepseek-v4.1-flash:free"] == 1
    assert data["modelLock_mimo-v2.5:free"] == 1
    assert data["modelLock_qwen3.8-27b:free"] == 1
    assert data["providerSpecificData"]["prefix"] == "th"
    assert data["providerSpecificData"]["baseUrl"] == "https://tokenharbor.ai/v1"
    assert data["providerSpecificData"]["nodeName"] == "tokenharbor"

    # Check customModels in kv table
    kv_rows = cur.execute("SELECT key, value FROM kv WHERE scope='customModels'").fetchall()
    assert len(kv_rows) >= 3
    assert any("th/deepseek-v4.1-flash:free" in k[0] for k in kv_rows)
    assert not any("tokenbor" in k[0] for k in kv_rows)
    conn.close()


def test_inject_into_db_with_provider_nodes(tmp_path):
    db_file = tmp_path / "test_9router_nodes.sqlite"
    conn = sqlite3.connect(str(db_file))
    conn.execute("""
        CREATE TABLE providerNodes (
            id TEXT PRIMARY KEY,
            name TEXT,
            type TEXT,
            apiType TEXT,
            baseUrl TEXT,
            prefix TEXT,
            createdAt TEXT,
            updatedAt TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE providerConnections (
            id TEXT PRIMARY KEY,
            provider TEXT,
            authType TEXT,
            name TEXT,
            email TEXT,
            priority INTEGER,
            isActive INTEGER,
            data TEXT,
            createdAt TEXT,
            updatedAt TEXT
        )
    """)
    conn.execute("CREATE TABLE kv (scope TEXT, key TEXT, value TEXT)")
    conn.commit()
    conn.close()

    cfg = {
        "default_model": "deepseek-v4.1-flash:free",
        "model_locks": ["deepseek-v4.1-flash:free", "mimo-v2.5:free"]
    }

    # First injection: creates providerNode and connection
    ok1, label1 = inject_into_db(str(db_file), "key_1", "user1@test.com", cfg)
    assert ok1 is True

    # Second injection: reuses existing providerNode and adds connection
    ok2, label2 = inject_into_db(str(db_file), "key_2", "user2@test.com", cfg)
    assert ok2 is True

    conn = sqlite3.connect(str(db_file))
    cur = conn.cursor()

    # providerNodes check
    node_rows = cur.execute("SELECT id, name, type, apiType, baseUrl, prefix FROM providerNodes").fetchall()
    assert len(node_rows) == 1
    assert node_rows[0][0] == "openai-compatible-chat-tokenharbor"
    assert node_rows[0][1] == "TokenHarbor"
    assert node_rows[0][2] == "openai-compatible"
    assert node_rows[0][3] == "chat"
    assert node_rows[0][4] == "https://tokenharbor.ai/v1"
    assert node_rows[0][5] == "th"

    # providerConnections check
    conns = cur.execute("SELECT id, provider, authType, name, email FROM providerConnections ORDER BY createdAt ASC").fetchall()
    assert len(conns) == 2
    assert conns[0][1] == "openai-compatible-chat-tokenharbor"
    assert conns[0][2] == "apikey"
    assert conns[0][3] == "TH th1"
    assert conns[0][4] == "user1@test.com"

    assert conns[1][1] == "openai-compatible-chat-tokenharbor"
    assert conns[1][2] == "apikey"
    assert conns[1][3] == "TH th2"
    assert conns[1][4] == "user2@test.com"

    # kv check
    kv_rows = cur.execute("SELECT key FROM kv WHERE scope='customModels'").fetchall()
    assert len(kv_rows) == 4
    for k in kv_rows:
        assert "|th/" in k[0]
        assert "tokenbor" not in k[0]

    conn.close()


def test_inject_into_db_multiple_connections_no_drop(tmp_path):
    db_file = tmp_path / "test_9router.sqlite"
    conn = sqlite3.connect(str(db_file))
    conn.execute("""
        CREATE TABLE providerConnections (
            id TEXT PRIMARY KEY,
            provider TEXT,
            authType TEXT,
            name TEXT,
            email TEXT,
            priority INTEGER,
            isActive INTEGER,
            data TEXT,
            createdAt TEXT,
            updatedAt TEXT
        )
    """)
    conn.execute("CREATE TABLE kv (scope TEXT, key TEXT, value TEXT)")
    conn.commit()
    conn.close()

    cfg = {
        "default_model": "deepseek-v4.1-flash:free",
        "model_locks": ["deepseek-v4.1-flash:free", "mimo-v2.5:free", "qwen3.8-27b:free"]
    }

    # First injection
    ok1, label1 = inject_into_db(str(db_file), "key_1", "user1@test.com", cfg)
    assert ok1 is True
    assert label1 == "TH th1"

    # Second injection
    ok2, label2 = inject_into_db(str(db_file), "key_2", "user2@test.com", cfg)
    assert ok2 is True
    assert label2 == "TH th2"

    conn = sqlite3.connect(str(db_file))
    cur = conn.cursor()
    rows = cur.execute("SELECT id, name, email FROM providerConnections ORDER BY createdAt ASC").fetchall()
    assert len(rows) == 2
    assert rows[0][1] == "TH th1"
    assert rows[1][1] == "TH th2"

    kv_rows = cur.execute("SELECT key FROM kv WHERE scope='customModels'").fetchall()
    assert len(kv_rows) == 6
    conn.close()


def test_inject_into_db_failure_invalid_db():
    ok, err = inject_into_db("/nonexistent/directory/db.sqlite", "key", "email@test.com", {})
    assert ok is False
    assert len(err) > 0


def test_find_9router_db_env_override(tmp_path, monkeypatch):
    custom_db = tmp_path / "custom_data.sqlite"
    custom_db.write_text("")
    monkeypatch.setenv("NINE_ROUTER_DB", str(custom_db))
    assert find_9router_db() == str(custom_db)


def test_find_9router_db_fallback(monkeypatch):
    monkeypatch.delenv("NINE_ROUTER_DB", raising=False)
    db = find_9router_db()
    assert isinstance(db, str)
    assert db.endswith("data.sqlite")


def test_sync_9router_http_success():
    cfg = {"r9_url": "http://localhost:20128", "r9_pass": "secret"}
    with patch("requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200)
        assert sync_9router_http(cfg) is True
        mock_post.assert_called_once_with(
            "http://localhost:20128/api/auth/login",
            json={"password": "secret"},
            timeout=3
        )


def test_sync_9router_http_failure():
    cfg = {"r9_url": "http://localhost:20128", "r9_pass": "secret"}
    with patch("requests.post", side_effect=Exception("Connection refused")):
        assert sync_9router_http(cfg) is False


def test_inject_9router_end_to_end(tmp_path, monkeypatch):
    db_file = tmp_path / "test_9router.sqlite"
    conn = sqlite3.connect(str(db_file))
    conn.execute("""
        CREATE TABLE providerConnections (
            id TEXT PRIMARY KEY,
            provider TEXT,
            authType TEXT,
            name TEXT,
            email TEXT,
            priority INTEGER,
            isActive INTEGER,
            data TEXT,
            createdAt TEXT,
            updatedAt TEXT
        )
    """)
    conn.execute("CREATE TABLE kv (scope TEXT, key TEXT, value TEXT)")
    conn.commit()
    conn.close()

    monkeypatch.setenv("NINE_ROUTER_DB", str(db_file))

    with patch("inject_th_kv.sync_9router_http") as mock_sync:
        mock_sync.return_value = True
        ok, label = inject_9router("my_api_key", "my_user@test.com")
        assert ok is True
        assert label == "TH th1"
        mock_sync.assert_called_once()
