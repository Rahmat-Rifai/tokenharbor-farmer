import os
import sys
import sqlite3

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from config_loader import load_config
import db_path
import tor_manager
from mail_clients import get_mail_client


def check_dependencies(deps: list[str]) -> tuple[bool, list[str]]:
    missing = []
    for d in deps:
        try:
            __import__(d)
        except ImportError:
            missing.append(d)
    return len(missing) == 0, missing


def run_preflight() -> bool:
    print("\n=== TOKENHARBOR FARMER — PREFLIGHT CHECK ===")
    cfg = load_config()
    all_ok = True

    # 1. Dependencies
    ok_deps, missing = check_dependencies(["requests", "socks", "rich"])
    tag = "✅" if ok_deps else "❌"
    print(f"  {tag} Python Dependencies: {', '.join(missing) if missing else 'All OK'}")
    all_ok &= ok_deps

    # 2. Tor ports
    socks_port = cfg.get("tor_socks_port", 9050)
    ctrl_port = cfg.get("tor_control_port", 9051)
    socks_ok = tor_manager.is_port_open(socks_port)
    ctrl_ok = tor_manager.is_port_open(ctrl_port)
    tag_tor = "✅" if socks_ok else "⚠️"
    print(f"  {tag_tor} Tor Socks {socks_port}: {'Ready' if socks_ok else 'Not started (will auto-start)'}")
    tag_ctrl = "✅" if ctrl_ok else "⚠️"
    print(f"  {tag_ctrl} Tor Control {ctrl_port}: {'Ready' if ctrl_ok else 'Not started (will auto-start)'}")

    # 3. 9Router DB
    r9_db = db_path.find_9router_db()
    db_exists = os.path.exists(r9_db)
    db_readable = False
    if db_exists:
        try:
            conn = sqlite3.connect(f"file:{r9_db}?mode=ro", uri=True)
            conn.execute("SELECT 1")
            conn.close()
            db_readable = True
        except Exception:
            db_readable = False
            all_ok = False
    else:
        all_ok = False

    tag_db = "✅" if (db_exists and db_readable) else "❌"
    db_status = "Found & Readable" if (db_exists and db_readable) else ("Unreadable" if db_exists else "Not found")
    print(f"  {tag_db} 9Router SQLite DB: {r9_db} ({db_status})")

    # 4. Email provider & IMAP connectivity
    mail_prov = cfg.get("mail_provider", "gmail_catchall")
    print(f"  ✅ Email Provider: {mail_prov}")
    try:
        mail_client = get_mail_client(cfg)
        if hasattr(mail_client, "test_connection") and callable(getattr(mail_client, "test_connection")):
            imap_ok, imap_msg = mail_client.test_connection()
            if imap_ok:
                print("  ✅ Email IMAP: Connected")
            else:
                print(f"  ❌ Email IMAP: Failed ({imap_msg})")
                all_ok = False
    except Exception as e:
        print(f"  ❌ Email IMAP: Failed ({e})")
        all_ok = False

    print()
    return bool(all_ok)


if __name__ == "__main__":
    ok = run_preflight()
    sys.exit(0 if ok else 1)
