import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json
import pytest
from config_loader import load_config, save_config

def test_load_default_config(tmp_path, monkeypatch):
    test_cfg_path = tmp_path / "config.json"
    monkeypatch.setattr("config_loader.CONFIG_PATH", str(test_cfg_path))
    
    cfg = load_config()
    assert cfg["mail_provider"] == "gmail_catchall"
    assert "deepseek-v4.1-flash:free" in cfg["model_locks"]
    assert cfg["tor_socks_port"] == 9050

def test_save_and_reload_config(tmp_path, monkeypatch):
    test_cfg_path = tmp_path / "config.json"
    monkeypatch.setattr("config_loader.CONFIG_PATH", str(test_cfg_path))
    
    cfg = load_config()
    cfg["tor_socks_port"] = 9150
    save_config(cfg)
    
    reloaded = load_config()
    assert reloaded["tor_socks_port"] == 9150

def test_load_actual_config_file():
    cfg = load_config()
    assert cfg["mail_provider"] == "gmail_catchall"
    assert cfg["install_9r"] is True
