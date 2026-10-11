import re
from abc import ABC, abstractmethod

_LINK_RE = re.compile(r'(https://tokenharbor\.ai/verify-email\?[^\s"<>]+)', re.IGNORECASE)


def extract_verification_link(text: str) -> str:
    match = _LINK_RE.search(text or "")
    return match.group(1) if match else ""


class BaseEmailClient(ABC):
    name: str = "base"

    @abstractmethod
    def generate_email(self) -> tuple[str, str]:
        """Returns (email_address, token_or_state)"""
        pass

    @abstractmethod
    def wait_verification_link(self, identifier: str, timeout: int = 120) -> str:
        """Polls inbox and returns the TokenHarbor verification link, or empty string if timeout"""
        pass
