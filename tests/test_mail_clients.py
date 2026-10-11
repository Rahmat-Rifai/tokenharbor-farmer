from unittest.mock import MagicMock, patch
import pytest
from mail_clients.base import extract_verification_link, BaseEmailClient
from mail_clients import get_mail_client
from mail_clients.gmail_client import GmailCatchAllClient
from mail_clients.tempik_client import TempikClient
from mail_clients.tempmail_client import TempmailClient
from config_loader import load_config


def test_extract_verification_link():
    sample_body = """
    Please confirm your account by visiting the link below:
    https://tokenharbor.ai/verify-email?token=abcdef123456&type=signup
    Thank you!
    """
    link = extract_verification_link(sample_body)
    assert link == "https://tokenharbor.ai/verify-email?token=abcdef123456&type=signup"


def test_extract_verification_link_empty_or_none():
    assert extract_verification_link("") == ""
    assert extract_verification_link(None) == ""
    assert extract_verification_link("No link here!") == ""


def test_factory_with_config_loader():
    cfg = load_config()
    client = get_mail_client(cfg)
    assert isinstance(client, GmailCatchAllClient)
    assert client.name == "gmail_catchall"
    assert client.domain == cfg["domain"]


def test_factory_returns_correct_client():
    cfg_tempmail = {"mail_provider": "tempmail"}
    client = get_mail_client(cfg_tempmail)
    assert isinstance(client, BaseEmailClient)
    assert client.name == "tempmail.lol"
    assert isinstance(client, TempmailClient)

    cfg_gmail = {
        "mail_provider": "gmail_catchall",
        "gmail_address": "test@gmail.com",
        "gmail_app_password": "pass word 123",
        "domain": "arxpays.my.id"
    }
    client_gmail = get_mail_client(cfg_gmail)
    assert isinstance(client_gmail, BaseEmailClient)
    assert client_gmail.name == "gmail_catchall"
    assert isinstance(client_gmail, GmailCatchAllClient)
    assert client_gmail.gmail_app_password == "password123"

    with patch("requests.get") as mock_get:
        mock_get.return_value.json.return_value = {"sessionId": "test-session-123"}
        cfg_tempik = {
            "mail_provider": "tempik",
            "tempik_api": "https://tempik.test",
            "tempik_dom": "test.com"
        }
        client_tempik = get_mail_client(cfg_tempik)
        assert isinstance(client_tempik, BaseEmailClient)
        assert client_tempik.name == "tempik"
        assert isinstance(client_tempik, TempikClient)


def test_gmail_client_generate_email():
    client = GmailCatchAllClient("test@gmail.com", "pass", "arxpays.my.id")
    addr, token = client.generate_email()
    assert addr == token
    assert addr.endswith("@arxpays.my.id")
    assert len(addr.split("@")[0]) == 10


def test_tempik_client_generate_and_wait():
    with patch("requests.get") as mock_get, patch("requests.post") as mock_post:
        mock_get.return_value.json.return_value = {"sessionId": "sess-123"}
        client = TempikClient("https://tempik.test", "tempik.test")

        mock_post.return_value.json.return_value = {"address": "user123@tempik.test"}
        addr, token = client.generate_email()
        assert addr == "user123@tempik.test"
        assert token == "user123@tempik.test"

        mock_get.return_value.json.return_value = [
            {"subject": "Verify", "body": "Go to https://tokenharbor.ai/verify-email?token=xyz987"}
        ]
        link = client.wait_verification_link(addr, timeout=5)
        assert link == "https://tokenharbor.ai/verify-email?token=xyz987"


def test_tempik_client_generate_email_failure():
    with patch("requests.get") as mock_get, patch("requests.post") as mock_post:
        mock_get.return_value.json.return_value = {"sessionId": "sess-123"}
        client = TempikClient("https://tempik.test", "tempik.test")

        mock_post.side_effect = Exception("Network timeout")
        addr, token = client.generate_email()
        assert addr == ""
        assert token == ""


def test_tempmail_client_generate_email_failure():
    with patch("requests.post") as mock_post:
        mock_post.side_effect = Exception("Connection error")
        client = TempmailClient()
        addr, token = client.generate_email()
        assert addr == ""
        assert token == ""


def test_tempmail_client_generate_and_wait():
    with patch("requests.post") as mock_post, patch("requests.get") as mock_get:
        client = TempmailClient()
        mock_post.return_value.json.return_value = {
            "address": "random@tempmail.lol",
            "token": "tok_123"
        }
        addr, token = client.generate_email()
        assert addr == "random@tempmail.lol"
        assert token == "tok_123"

        mock_get.return_value.json.return_value = {
            "emails": [
                {"body": "Confirm: https://tokenharbor.ai/verify-email?token=lol123"}
            ]
        }
        link = client.wait_verification_link(token, timeout=5)
        assert link == "https://tokenharbor.ai/verify-email?token=lol123"


def test_gmail_client_test_connection():
    with patch("imaplib.IMAP4_SSL") as mock_imap_cls:
        mock_imap = MagicMock()
        mock_imap_cls.return_value = mock_imap

        client = GmailCatchAllClient("test@gmail.com", "pass", "arxpays.my.id")
        ok, msg = client.test_connection()
        assert ok is True
        assert msg == "Gmail IMAP OK"
        mock_imap.login.assert_called_once_with("test@gmail.com", "pass")
        mock_imap.logout.assert_called_once()

    with patch("imaplib.IMAP4_SSL") as mock_imap_cls:
        mock_imap_cls.side_effect = Exception("Auth failed")
        client = GmailCatchAllClient("test@gmail.com", "pass", "arxpays.my.id")
        ok, msg = client.test_connection()
        assert ok is False
        assert "Auth failed" in msg


def test_gmail_client_wait_verification_link():
    with patch("imaplib.IMAP4_SSL") as mock_imap_cls, patch("time.sleep") as mock_sleep:
        mock_imap = MagicMock()
        mock_imap_cls.return_value = mock_imap

        # Folder select OK
        mock_imap.select.return_value = ('OK', [b'1'])
        # Search returns one message number
        mock_imap.search.return_value = ('OK', [b'101'])

        raw_email = (
            b"From: noreply@tokenharbor.ai\r\n"
            b"To: user123@arxpays.my.id\r\n"
            b"Subject: Confirm\r\n"
            b"Content-Type: text/plain; charset=utf-8\r\n\r\n"
            b"Click here: https://tokenharbor.ai/verify-email?token=gmailtok456"
        )
        mock_imap.fetch.return_value = ('OK', [(b'101 (RFC822 {150})', raw_email)])

        client = GmailCatchAllClient("test@gmail.com", "pass", "arxpays.my.id")
        link = client.wait_verification_link("user123@arxpays.my.id", timeout=10)

        assert link == "https://tokenharbor.ai/verify-email?token=gmailtok456"
        mock_imap.store.assert_called_with(b'101', '+FLAGS', '\\Seen')


def test_wait_verification_link_timeouts():
    # Tempmail timeout
    with patch("requests.get") as mock_get, patch("time.sleep"):
        mock_get.return_value.json.return_value = {"emails": []}
        client = TempmailClient()
        assert client.wait_verification_link("fake_tok", timeout=0.01) == ""

    # Tempik timeout
    with patch("requests.get") as mock_get, patch("time.sleep"):
        mock_get.return_value.json.return_value = []
        client = TempikClient("https://tempik.test", "tempik.test")
        assert client.wait_verification_link("user@tempik.test", timeout=0.01) == ""

    # Gmail timeout
    with patch("imaplib.IMAP4_SSL") as mock_imap_cls, patch("time.sleep"):
        mock_imap = MagicMock()
        mock_imap_cls.return_value = mock_imap
        mock_imap.select.return_value = ('OK', [b'1'])
        mock_imap.search.return_value = ('OK', [b''])
        client = GmailCatchAllClient("test@gmail.com", "pass", "arxpays.my.id")
        assert client.wait_verification_link("user@arxpays.my.id", timeout=0.01) == ""

