import time
import requests
from mail_clients.base import BaseEmailClient, extract_verification_link


class TempmailClient(BaseEmailClient):
    name = "tempmail.lol"

    def generate_email(self) -> tuple[str, str]:
        try:
            r = requests.post("https://api.tempmail.lol/v2/inbox/create", timeout=15)
            d = r.json()
            return d.get("address", ""), d.get("token", "")
        except Exception:
            return "", ""

    def wait_verification_link(self, token: str, timeout: int = 120) -> str:
        start = time.time()
        while time.time() - start < timeout:
            try:
                r = requests.get(f"https://api.tempmail.lol/v2/inbox?token={token}", timeout=15)
                emails = r.json().get("emails", [])
                for em in emails:
                    link = extract_verification_link(em.get("body", ""))
                    if link:
                        return link
            except Exception:
                pass
            time.sleep(5)
        return ""
