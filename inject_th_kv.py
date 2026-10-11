import sqlite3
import json
import uuid
import requests
from datetime import datetime, timezone

import db_path
from db_path import find_9router_db
from config_loader import load_config


def inject_into_db(db_file: str, api_key: str, email: str, cfg: dict) -> tuple[bool, str]:
    """Inject TokenHarbor API key and connection into 9Router SQLite DB.

    Creates an openai-compatible providerConnection and sets model locks
    for deepseek-v4.1-flash:free, mimo-v2.5:free, and qwen3.8-27b:free.
    Also registers customModels entries in the kv table.
    """
    conn = None
    try:
        conn = sqlite3.connect(db_file)
        cur = conn.cursor()
        nid = 'conn-' + str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        count = 0
        try:
            count = cur.execute(
                "SELECT COUNT(*) FROM providerConnections "
                "WHERE (data LIKE '%tokenharbor.ai%' OR provider LIKE '%tokenharbor%') "
                "AND (authType IN ('apikey', 'api_key') OR authType IS NOT NULL)"
            ).fetchone()[0]
        except Exception:
            pass

        label = f"TH th{count+1}"
        default_model = (cfg.get("default_model") if cfg else None) or "deepseek-v4.1-flash:free"
        model_locks = (cfg.get("model_locks") if cfg else None) or [
            "deepseek-v4.1-flash:free",
            "mimo-v2.5:free",
            "qwen3.8-27b:free"
        ]

        # Check or create providerNode if table exists
        provider_name = "TokenHarbor"
        default_node_id = "openai-compatible-chat-tokenharbor"
        provider_id = "openai-compatible"

        try:
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='providerNodes'")
            if cur.fetchone():
                cur.execute(
                    "SELECT id FROM providerNodes WHERE baseUrl LIKE '%tokenharbor.ai%' OR name LIKE '%TokenHarbor%'"
                )
                node_row = cur.fetchone()
                if node_row:
                    provider_id = node_row[0]
                else:
                    cur.execute(
                        "INSERT INTO providerNodes (id, name, type, apiType, baseUrl, prefix, createdAt, updatedAt) "
                        "VALUES (?, ?, 'openai-compatible', 'chat', 'https://tokenharbor.ai/v1', 'th', ?, ?)",
                        (default_node_id, provider_name, now, now)
                    )
                    provider_id = default_node_id
        except Exception:
            provider_id = "openai-compatible"

        data_dict = {
            "apiKey": api_key,
            "label": label,
            "defaultModel": default_model,
            "testStatus": "active",
            "providerSpecificData": {
                "prefix": "th",
                "apiType": "chat",
                "baseUrl": "https://tokenharbor.ai/v1",
                "nodeName": "tokenharbor"
            },
            "errorCode": None,
            "backoffLevel": 0,
            "lastUsedAt": None,
            "consecutiveUseCount": 0
        }

        for m in model_locks:
            data_dict[f"modelLock_{m}"] = 1

        cur.execute(
            "INSERT INTO providerConnections (id, provider, authType, name, email, priority, isActive, data, createdAt, updatedAt) "
            "VALUES (?, ?, 'apikey', ?, ?, 0, 1, ?, ?, ?)",
            (nid, provider_id, label, email, json.dumps(data_dict), now, now)
        )

        # Inject customModels to kv table if kv table exists
        try:
            for m in model_locks:
                mid = f"th/{m}"
                k = f"{nid}|{mid}|llm"
                v = json.dumps({"providerAlias": nid, "id": mid, "type": "llm", "name": mid})
                cur.execute("SELECT COUNT(*) FROM kv WHERE scope='customModels' AND key=?", (k,))
                if cur.fetchone()[0] == 0:
                    cur.execute("INSERT INTO kv (scope, key, value) VALUES ('customModels', ?, ?)", (k, v))
        except Exception:
            pass

        conn.commit()
        return True, label
    except Exception as e:
        return False, str(e)
    finally:
        if conn:
            conn.close()


def sync_9router_http(cfg: dict) -> bool:
    """Notify/reload 9Router HTTP API without dropping existing connections."""
    r9_url = ((cfg.get("r9_url") if cfg else None) or "http://localhost:20128").rstrip("/")
    r9_pass = (cfg.get("r9_pass") if cfg else None) or "123456"
    try:
        requests.post(f"{r9_url}/api/auth/login", json={"password": r9_pass}, timeout=3)
        return True
    except Exception:
        return False


def inject_9router(api_key: str, email: str, cfg: dict = None) -> tuple[bool, str]:
    """Find 9Router DB, inject connection with model locks, and sync via HTTP."""
    if cfg is None:
        cfg = load_config()
    db = db_path.find_9router_db()
    ok, msg = inject_into_db(db, api_key, email, cfg)
    if ok:
        sync_9router_http(cfg)
    return ok, msg
