import os
import sys
import socket
import subprocess
import time
import urllib.request
import zipfile
import tarfile

TOR_DEFAULT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tor")
# Official Tor Expert Bundle archive for Windows
TOR_BUNDLE_URL = "https://archive.torproject.org/tor-package-archive/torbrowser/14.0.7/tor-expert-bundle-windows-x86_64-14.0.7.tar.gz"


def is_port_open(port: int, host: str = "127.0.0.1") -> bool:
    try:
        s = socket.create_connection((host, port), timeout=1.5)
        s.close()
        return True
    except Exception:
        return False


def rotate_tor_ip(control_port: int = 9051, host: str = "127.0.0.1") -> bool:
    try:
        s = socket.create_connection((host, control_port), timeout=5)
        s.sendall(b"AUTHENTICATE\r\n")
        r1 = s.recv(100)
        s.sendall(b"SIGNAL NEWNYM\r\n")
        r2 = s.recv(100).decode(errors="ignore")
        s.close()
        return "250 OK" in r2 or "OK" in r2
    except Exception:
        return False


def parse_tor_status(text: str) -> str:
    return text.strip() if text else ""


def find_tor_exe(tor_dir: str) -> str | None:
    for root, _, files in os.walk(tor_dir):
        if "tor.exe" in files:
            return os.path.join(root, "tor.exe")
        if "tor" in files:
            return os.path.join(root, "tor")
    return None


def ensure_tor_running(tor_dir: str = None, socks_port: int = 9050, control_port: int = 9051) -> bool:
    if is_port_open(socks_port):
        return True

    if tor_dir is None:
        tor_dir = TOR_DEFAULT_DIR

    os.makedirs(tor_dir, exist_ok=True)
    data_dir = os.path.join(tor_dir, "data").replace("\\", "/")
    os.makedirs(data_dir, exist_ok=True)

    torrc_path = os.path.join(tor_dir, "torrc")
    with open(torrc_path, "w", encoding="utf-8") as f:
        f.write(
            f"SocksPort 127.0.0.1:{socks_port}\n"
            f"ControlPort 127.0.0.1:{control_port}\n"
            f"CookieAuthentication 0\n"
            f'DataDirectory "{data_dir}"\n'
        )

    tor_exe = find_tor_exe(tor_dir)
    if not tor_exe:
        print(f"  [Tor] Downloading Tor Expert Bundle to {tor_dir}...")
        tar_path = os.path.join(tor_dir, "tor.tar.gz")
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            req = urllib.request.Request(TOR_BUNDLE_URL, headers=headers)
            with urllib.request.urlopen(req, timeout=60) as resp, open(tar_path, "wb") as out_f:
                out_f.write(resp.read())

            with tarfile.open(tar_path, "r:gz") as tar:
                tar.extractall(path=tor_dir)
            if os.path.exists(tar_path):
                os.remove(tar_path)
        except Exception as e:
            print(f"  [Tor] Download failed: {e}")
            return False

        tor_exe = find_tor_exe(tor_dir)

    if not tor_exe:
        print("  [Tor] tor.exe not found.")
        return False

    print(f"  [Tor] Starting Tor process from {tor_exe}...")
    try:
        subprocess.Popen([tor_exe, "-f", torrc_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        print(f"  [Tor] Failed to launch Tor: {e}")
        return False

    for _ in range(30):
        time.sleep(1)
        if is_port_open(socks_port):
            print(f"  [Tor] Tor started and listening on {socks_port}.")
            return True

    return False
