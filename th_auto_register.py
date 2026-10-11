import requests
import re
import json
import random
import string
import uuid
import urllib.parse
import time
import os
import sys
from datetime import datetime

from config_loader import load_config
from mail_clients import get_mail_client
import th_action_resolver
from tor_manager import rotate_tor_ip, ensure_tor_running
from inject_th_kv import inject_9router

BASE = "https://tokenharbor.ai"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
ROUTER = urllib.parse.quote('["",{"children":["login",{"children":["__PAGE__",{},null,null,0]},null,null,0]},null,null,20]')


STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "th_tor_state.json")


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"accounts": []}


def save_state(st: dict) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(st, f, indent=2)


def log(msg, lv="INFO"):
    print(f"  [{datetime.now().strftime('%H:%M:%S')}] [{lv}] {msg}", flush=True)


def make_signup_body(email: str, pwd: str, action_info: dict) -> tuple[str, dict]:
    fp = str(uuid.uuid4())
    bd = "----WebKitFormBoundary" + "".join(random.choices(string.ascii_uppercase + string.digits, k=16))
    parts = []

    def af(n, v=""):
        parts.append(f'--{bd}\r\nContent-Disposition: form-data; name="{n}"\r\n\r\n{v}')

    af("1_$ACTION_REF_1")
    af("1_$ACTION_1:0", json.dumps({"id": action_info["action_id"], "bound": "$@1"}))
    af("1_$ACTION_1:1", '["$undefined"]')
    af("1_$ACTION_KEY", action_info["action_key"])
    af("1_device_fingerprint", fp)
    af("1_timezone")
    af("1_next")
    af("1_email", email)
    af("1_password", pwd)
    af("1_invite_code")
    af("0", '["$undefined","$K1"]')
    body = "\r\n".join(parts) + f"\r\n--{bd}--\r\n"
    headers = {
        "Content-Type": f"multipart/form-data; boundary={bd}",
        "Accept": "text/x-component",
        "Next-Action": action_info["next_action"],
        "Next-Router-State-Tree": ROUTER,
        "Origin": BASE,
        "Referer": f"{BASE}/login?mode=signup",
    }
    return body, headers


def test_model_completion(key: str, model: str = "mimo-v2.5:free") -> tuple[bool, str]:
    try:
        r = requests.post(
            f"{BASE}/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            timeout=40,
            json={"model": model, "messages": [{"role": "user", "content": "say ok"}], "max_tokens": 15},
        )
        return r.status_code == 200, str(r.status_code)
    except Exception as e:
        return False, str(e)[:30]


def register_one(cfg: dict = None) -> tuple[dict | None, str | None]:
    if cfg is None:
        cfg = load_config()

    socks_port = cfg.get("tor_socks_port", 9050)
    socks_proxies = {
        "http": f"socks5h://127.0.0.1:{socks_port}",
        "https": f"socks5h://127.0.0.1:{socks_port}",
    }

    mail_client = get_mail_client(cfg)
    email, email_ident = mail_client.generate_email()
    if not email:
        return None, f"Failed to generate email address using {mail_client.name}"
    pwd = "".join(random.choices(string.ascii_letters + string.digits, k=12)) + "!Aa1"
    log(f"Email: {email} ({mail_client.name})")

    action_info = th_action_resolver.resolve_signup_action(proxies=socks_proxies)

    s = requests.Session()
    s.headers.update({"User-Agent": UA})

    try:
        s.get(f"{BASE}/login?mode=signup", proxies=socks_proxies, timeout=30)
    except Exception:
        pass

    body, headers = make_signup_body(email, pwd, action_info)
    r = None
    for attempt in range(3):
        try:
            r = s.post(f"{BASE}/login", data=body, headers=headers, proxies=socks_proxies, timeout=40)
            break
        except Exception as e:
            log(f"Signup attempt {attempt+1} failed: {str(e)[:40]}")
            time.sleep(3)

    if r is None or "signedIn" not in r.text:
        log("Initial signup failed or action rejected; invalidating action cache and retrying with fresh action...", "WARN")
        th_action_resolver.invalidate_action_cache()
        action_info = th_action_resolver.resolve_signup_action(proxies=socks_proxies, force_refresh=True)
        body, headers = make_signup_body(email, pwd, action_info)
        r = None
        for attempt in range(2):
            try:
                r = s.post(f"{BASE}/login", data=body, headers=headers, proxies=socks_proxies, timeout=40)
                break
            except Exception as e:
                log(f"Signup retry attempt {attempt+1} failed: {str(e)[:40]}")
                time.sleep(3)

    if r is None:
        return None, "Connection timeout via Tor"

    if "signedIn" not in r.text:
        errs = [e for e in re.findall(r'"error"\s*:\s*"([^"]+)"', r.text) if e not in ("$f", "$undefined")]
        err = errs[0] if errs else f"HTTP {r.status_code}"
        if "couldn't create" in err.lower() or "human check" in err.lower() or "rate" in err.lower():
            log("Exit node flagged — rotating circuit...", "WARN")
            rotate_tor_ip(cfg.get("tor_control_port", 9051))
            time.sleep(6)
        return None, err

    uid = re.findall(r'"userId":\s*"([^"]+)"', r.text)
    user_id = uid[0] if uid else "?"
    log(f"Signup OK - userId: {user_id}")

    # Delete default auto-keys to keep clean
    try:
        r2 = s.get(f"{BASE}/api/keys", headers={"Accept": "application/json"}, proxies=socks_proxies, timeout=20)
        for k in r2.json().get("keys", []):
            try:
                s.delete(f"{BASE}/api/keys/{k['id']}", proxies=socks_proxies, timeout=10)
            except Exception:
                pass
    except Exception:
        pass

    # Create fresh dedicated API key
    key_label = f"th-{random.randint(100, 999)}"
    r3 = s.post(
        f"{BASE}/api/keys",
        json={"label": key_label},
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        proxies=socks_proxies,
        timeout=30,
    )
    if r3.status_code != 201:
        return None, f"Key creation failed ({r3.status_code})"

    key = r3.json().get("plaintext")
    if not key:
        return None, "No plaintext in key response"
    log(f"API Key: {key[:20]}...")

    # Enable free models
    rc = s.post(
        f"{BASE}/api/me/privacy",
        json={"free_models_enabled": True},
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        proxies=socks_proxies,
        timeout=25,
    )
    consent = False
    if rc.status_code == 200:
        try:
            res = rc.json()
            consent = bool(isinstance(res, dict) and res.get("ok") is True)
        except Exception:
            consent = False
        if not consent and hasattr(rc, "text"):
            consent = '"ok":true' in rc.text or '"ok": true' in rc.text
    log(f"Free models enabled: {'Y' if consent else 'N'}")

    # Wait for email verification link
    log(f"Waiting verification email ({mail_client.name})...")
    v_link = mail_client.wait_verification_link(email_ident, timeout=90)
    verified = False
    if v_link:
        try:
            rv = s.get(v_link, proxies=socks_proxies, timeout=25, allow_redirects=True)
            verified = rv.status_code in (200, 302, 307)
        except Exception:
            try:
                rv = requests.get(v_link, timeout=20, allow_redirects=True)
                verified = rv.status_code in (200, 302, 307)
            except Exception:
                pass
    log(f"Email verified: {'Y' if verified else 'N'}")

    return {
        "email": email,
        "password": pwd,
        "userId": user_id,
        "api_key": key,
        "verified": verified,
        "consent": consent,
    }, None


def main(argv=None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    mode = argv[0].lower() if argv else "single"
    if mode == "single":
        cfg = load_config()
        ensure_tor_running(
            socks_port=cfg.get("tor_socks_port", 9050),
            control_port=cfg.get("tor_control_port", 9051),
        )
        acct, err = register_one(cfg)
        if acct:
            test_ok, test_info = test_model_completion(acct["api_key"])
            log(f"Model test: {'OK' if test_ok else 'FAIL'} ({test_info})")
            acct["test_result"] = test_info

            injected, imsg = inject_9router(acct["api_key"], acct["email"], cfg)
            log(f"9Router inject: {'OK' if injected else 'FAIL'} ({imsg})")
            acct["injected"] = injected

            state = load_state()
            state["accounts"] = [a for a in state.get("accounts", []) if a.get("email") != acct["email"]]
            state["accounts"].append(acct)
            save_state(state)

            v = "Y" if acct.get("verified") else "N"
            c = "Y" if acct.get("consent") else "N"
            inj = "Y" if injected else "N"

            print("\n" + "=" * 55)
            print("  TOKENHARBOR SINGLE REGISTRATION SUMMARY")
            print("=" * 55)
            print(f"  Email:        {acct['email']}")
            print(f"  User ID:      {acct.get('userId', 'N/A')}")
            print(f"  API Key:      {acct['api_key']}")
            print(f"  Verified:     {v}")
            print(f"  Consent:      {c}")
            print(f"  Model Test:   {'OK' if test_ok else 'FAIL'} ({test_info})")
            print(f"  9Router:      {'OK' if injected else 'FAIL'} ({imsg})")
            print(f"  Saved to:     {STATE_FILE}")
            print("=" * 55 + "\n")
            return 0
        else:
            print(f"\nRegistration failed: {err}")
            return 1
    else:
        print(f"Unknown mode: {mode}. Supported modes: single")
        return 1


if __name__ == "__main__":
    sys.exit(main())
