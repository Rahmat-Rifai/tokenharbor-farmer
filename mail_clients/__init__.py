from mail_clients.base import BaseEmailClient, extract_verification_link
from mail_clients.gmail_client import GmailCatchAllClient
from mail_clients.tempik_client import TempikClient
from mail_clients.tempmail_client import TempmailClient

__all__ = [
    "BaseEmailClient",
    "extract_verification_link",
    "GmailCatchAllClient",
    "TempikClient",
    "TempmailClient",
    "get_mail_client",
]


def get_mail_client(cfg: dict) -> BaseEmailClient:
    provider = str(cfg.get("mail_provider", "gmail_catchall")).lower()
    if provider in ("gmail_catchall", "gmail_imap", "gmail"):
        return GmailCatchAllClient(
            cfg.get("gmail_address", ""),
            cfg.get("gmail_app_password", ""),
            cfg.get("domain", "arxpays.my.id")
        )
    elif provider == "tempik":
        return TempikClient(
            cfg.get("tempik_api", "https://tempik.meowx.web.id"),
            cfg.get("tempik_dom", "meowx.web.id")
        )
    else:
        return TempmailClient()
