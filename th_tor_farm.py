import os
import sys
import json
import time
import random
from config_loader import load_config
from th_auto_register import register_one, test_model_completion, log
from tor_manager import ensure_tor_running, rotate_tor_ip
from inject_th_kv import inject_9router

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


def run_farm(target_count: int = 10, no_inject: bool = False) -> None:
    cfg = load_config()
    print(f"\n=== TOKENHARBOR FARMER — Target: {target_count} Accounts ===")

    ensure_tor_running(
        socks_port=cfg.get("tor_socks_port", 9050),
        control_port=cfg.get("tor_control_port", 9051),
    )

    state = load_state()
    exist = {a["email"] for a in state["accounts"]}
    success = 0
    fail_count = 0

    while len(state["accounts"]) < target_count:
        curr_num = len(state["accounts"]) + 1
        print(f"\n[{curr_num}/{target_count}] {'='*40}")

        try:
            acct, err = register_one(cfg)
        except Exception as e:
            acct, err = None, f"Unhandled exception during registration: {e}"
        if not acct:
            fail_count += 1
            log(f"Registration failed: {err}", "ERROR")
            if fail_count >= 3:
                log("Rotating Tor circuit...", "WARN")
                rotate_tor_ip(cfg.get("tor_control_port", 9051))
                time.sleep(8)
                fail_count = 0
            time.sleep(5)
            continue

        if acct["email"] in exist:
            continue

        test_ok, test_info = test_model_completion(acct["api_key"])
        log(f"Model test: {'OK' if test_ok else 'FAIL'} ({test_info})")
        acct["test_result"] = test_info

        injected = False
        if not no_inject and cfg.get("install_9r", True):
            injected, imsg = inject_9router(acct["api_key"], acct["email"], cfg)
            log(f"9Router inject: {'OK' if injected else 'FAIL'} ({imsg})")
        acct["injected"] = injected

        state["accounts"].append(acct)
        exist.add(acct["email"])
        save_state(state)
        success += 1
        fail_count = 0

        v = "Y" if acct["verified"] else "N"
        c = "Y" if acct["consent"] else "N"
        inj = "Y" if injected else "N"
        print(f"  RESULT: {acct['email']} [v:{v}] [c:{c}] [inj:{inj}]")

        if success % 2 == 0:
            rotate_tor_ip(cfg.get("tor_control_port", 9051))

        time.sleep(random.randint(5, 10))

    print(f"\n=== SELESAI: Total {len(state['accounts'])} akun tersimpan di {STATE_FILE} ===")


if __name__ == "__main__":
    count = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 1
    no_inj = "--no-inject" in sys.argv
    run_farm(count, no_inj)
