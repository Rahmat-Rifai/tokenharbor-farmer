import re
import json
import os
import requests

CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".th_action_cache.json")
BASE_URL = "https://tokenharbor.ai"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

# Known live action IDs discovered from TokenHarbor production deployment
DEFAULT_FALLBACK_ACTION = {
    "action_id": "601deb87587212e262e9f8b231f1cf29b6a227a0ad",
    "action_key": "kb3df6a1d48e1a01307dd1ff043d81c6e",
    "next_action": "601deb87587212e262e9f8b231f1cf29b6a227a0ad"
}

def parse_action_from_html(html: str) -> dict | None:
    action_1_match = re.search(r'name="\$ACTION_1:0"\s+value="([^"]+)"', html or "")
    if not action_1_match:
        action_1_match = re.search(r'value="([^"]+)"[^>]*name="\$ACTION_1:0"', html or "")
        
    action_key_match = re.search(r'name="\$ACTION_KEY"\s+value="([^"]+)"', html or "")
    if not action_key_match:
        action_key_match = re.search(r'value="([^"]+)"[^>]*name="\$ACTION_KEY"', html or "")

    if action_1_match and action_key_match:
        val_unescaped = action_1_match.group(1).replace('&quot;', '"')
        action_id = ""
        try:
            d = json.loads(val_unescaped)
            action_id = d.get("id", "")
        except Exception:
            id_m = re.search(r'"id":\s*"([^"]+)"', val_unescaped)
            action_id = id_m.group(1) if id_m else ""

        action_key = action_key_match.group(1)
        if action_id and action_key:
            return {
                "action_id": action_id,
                "action_key": action_key,
                "next_action": action_id
            }
    return None

def invalidate_action_cache() -> bool:
    """Delete .th_action_cache.json if it exists."""
    try:
        if os.path.exists(CACHE_FILE):
            os.remove(CACHE_FILE)
            return True
    except Exception:
        pass
    return False


def resolve_signup_action(proxies: dict = None, force_refresh: bool = False) -> dict:
    if not force_refresh and os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if data.get("action_id") and data.get("action_key") and data.get("next_action"):
                    return data
        except Exception:
            pass

    headers = {"User-Agent": UA}
    url = f"{BASE_URL}/login?mode=signup"

    html = ""
    try:
        r = requests.get(url, headers=headers, proxies=proxies, timeout=25)
        if r.status_code == 200:
            html = r.text
    except Exception:
        # Fallback direct request without proxy
        try:
            r = requests.get(url, headers=headers, timeout=20)
            if r.status_code == 200:
                html = r.text
        except Exception:
            pass

    parsed = parse_action_from_html(html) if html else None
    if not parsed:
        parsed = dict(DEFAULT_FALLBACK_ACTION)

    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(parsed, f, indent=2)
    except Exception:
        pass

    return parsed
