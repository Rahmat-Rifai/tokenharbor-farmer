import time
import requests
from mail_clients.base import BaseEmailClient, extract_verification_link


class TempikClient(BaseEmailClient):
    name = "tempik"

    def __init__(self, api_url: str, domain: str):
        self.api_url = api_url.rstrip("/")
        self.domain = domain
        self.session_id = None
        self._ensure_session()

    def _ensure_session(self):
        try:
            r = requests.get(f"{self.api_url}/api/session", timeout=10)
            self.session_id = r.json().get("sessionId")
        except Exception:
            pass

    def generate_email(self) -> tuple[str, str]:
        try:
            if not self.session_id:
                self._ensure_session()
            headers = {"x-session-id": self.session_id} if self.session_id else {}
            r = requests.post(f"{self.api_url}/api/inboxes", json={"domain": self.domain}, headers=headers, timeout=12)
            addr = r.json().get("address", "")
            return addr, addr
        except Exception:
            return "", ""

    def wait_verification_link(self, addr: str, timeout: int = 120) -> str:
        start = time.time()
        headers = {"x-session-id": self.session_id} if self.session_id else {}
        url = f"{self.api_url}/api/inboxes/{addr}/messages"
        while time.time() - start < timeout:
            try:
                r = requests.get(url, headers=headers, timeout=10)
                msgs = r.json()
                if isinstance(msgs, list):
                    for m in msgs:
                        text = f"{m.get('subject', '')} {m.get('body', '')}"
                        link = extract_verification_link(text)
                        if link:
                            return link
            except Exception:
                pass
            time.sleep(4)
        return ""
