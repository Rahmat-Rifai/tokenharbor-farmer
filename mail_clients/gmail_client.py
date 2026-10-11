import imaplib
import email
import time
import random
import string
from mail_clients.base import BaseEmailClient, extract_verification_link


class GmailCatchAllClient(BaseEmailClient):
    name = "gmail_catchall"

    def __init__(self, gmail_address: str, gmail_app_password: str, domain: str):
        self.gmail_address = gmail_address.strip()
        self.gmail_app_password = gmail_app_password.replace(" ", "").strip()
        self.domain = domain.strip()
        self.imap_host = "imap.gmail.com"
        self.imap_port = 993

    def generate_email(self) -> tuple[str, str]:
        rand_prefix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
        addr = f"{rand_prefix}@{self.domain}"
        return addr, addr

    def test_connection(self) -> tuple[bool, str]:
        try:
            M = imaplib.IMAP4_SSL(self.imap_host, self.imap_port, timeout=15)
            M.login(self.gmail_address, self.gmail_app_password)
            M.logout()
            return True, "Gmail IMAP OK"
        except Exception as e:
            return False, str(e)

    def wait_verification_link(self, addr: str, timeout: int = 120) -> str:
        start = time.time()
        while time.time() - start < timeout:
            try:
                M = imaplib.IMAP4_SSL(self.imap_host, self.imap_port, timeout=15)
                M.login(self.gmail_address, self.gmail_app_password)
                for folder in ['"[Gmail]/Spam"', 'INBOX']:
                    res, _ = M.select(folder)
                    if res != 'OK':
                        continue
                    typ, data = M.search(None, f'TO "{addr}"')
                    if typ != 'OK' or not data[0]:
                        typ, data = M.search(None, f'TEXT "{addr.split("@")[0]}"')
                    if typ == 'OK' and data[0]:
                        nums = data[0].split()
                        for num in reversed(nums[-3:]):
                            typ2, msg_data = M.fetch(num, '(RFC822)')
                            if typ2 != 'OK' or not msg_data or not msg_data[0]:
                                continue
                            msg = email.message_from_bytes(msg_data[0][1])
                            body = ''
                            for part in msg.walk():
                                if part.get_content_type() in ('text/plain', 'text/html'):
                                    payload = part.get_payload(decode=True)
                                    if payload:
                                        body += payload.decode('utf-8', 'replace')
                            link = extract_verification_link(body)
                            if link:
                                try:
                                    M.store(num, '+FLAGS', '\\Seen')
                                    M.logout()
                                except Exception:
                                    pass
                                return link
                M.logout()
            except Exception:
                pass
            time.sleep(5)
        return ""
