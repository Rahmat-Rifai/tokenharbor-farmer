import json
import os
from pathlib import Path

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

DEFAULT_CONFIG = {
    "mail_provider": "gmail_catchall",
    "gmail_address": "",
    "gmail_app_password": "",
    "domain": "arxpays.my.id",
    "tempik_api": "https://tempik.meowx.web.id",
    "tempik_dom": "meowx.web.id",
    "tor_socks_port": 9050,
    "tor_control_port": 9051,
    "r9_url": "http://localhost:20128",
    "r9_pass": "123456",
    "install_9r": True,
    "default_model": "deepseek-v4.1-flash:free",
    "model_locks": [
        "deepseek-v4.1-flash:free",
        "mimo-v2.5:free",
        "qwen3.8-27b:free"
    ]
}

def load_config() -> dict:
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                merged = dict(DEFAULT_CONFIG)
                merged.update(data)
                return merged
        except Exception:
            pass
    return dict(DEFAULT_CONFIG)

def save_config(cfg: dict) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
