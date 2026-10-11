# Spec: TokenHarbor Modular Farmer & 9Router Injector

- **Date:** 2026-10-11
- **Status:** Draft / Approved by User
- **Target Working Directory:** `C:\FAI\tokenHarbor`
- **Reference Directories / Upstream:**
  - Upstream Repo: `https://github.com/Sekolah76/tokenharbor-farmer`
  - Reference Farm: `C:\FAI\grook_farm`

---

## 1. Background & Goals

TokenHarbor (`https://tokenharbor.ai`) provides a free tier for several AI models (such as `deepseek-v4.1-flash:free`, `mimo-v2.5:free`, and `qwen3.8-27b:free`). To farm accounts reliably, bypass sign-up rate limits, and make farmed API keys immediately available to a local 9Router instance, this project sets up an automated farming tool in `C:\FAI\tokenHarbor`.

### Key Challenges & Solutions
1. **Dynamic Next.js Server Actions:** TokenHarbor uses Next.js Server Actions for signup. Hardcoded action IDs become invalid across deployments. The system includes an automated Server Action resolver (`th_action_resolver.py`) that parses live action parameters from `https://tokenharbor.ai/login?mode=signup`.
2. **IP Rate Limits & Rotation:** TokenHarbor enforces `signup_ip_required` and rate limits on IPs. The tool integrates a portable Tor manager (`tor_manager.py`) that downloads/launches Tor Expert Bundle locally (SocksPort 9050, ControlPort 9051) and performs `SIGNAL NEWNYM` circuit rotation.
3. **Flexible Email Verification:** Supports multi-provider email verification (Gmail Catch-All via IMAP SSL for domains like `arxpays.my.id`, Tempik API `tempik.meowx.web.id`, and Tempmail.lol) with automatic link extraction (`https://tokenharbor.ai/verify-email?...`).
4. **9Router Dual Injection:** Automatically injects generated API keys into 9Router's local SQLite database (`~/AppData/Roaming/9router/db/data.sqlite`) and notifies/reloads 9Router HTTP API (`http://localhost:20128`) without dropping existing connections.
5. **Configurable Model Locks:** Uses user-specified model lock `deepseek-v4.1-flash:free` (alongside `mimo-v2.5:free` and `qwen3.8-27b:free`).

---

## 2. System Architecture

```text
C:\FAI\tokenHarbor\
├── config.json                     # Central configuration
├── run.bat / setup.bat             # Windows batch runners
├── tor/                            # Portable Tor Expert Bundle
│   ├── tor.exe
│   ├── torrc
│   └── data/
├── mail_clients/                   # Modular email adapters
│   ├── __init__.py
│   ├── base.py                     # BaseEmailClient interface
│   ├── gmail_client.py             # Gmail Catch-All via IMAP SSL
│   ├── tempik_client.py            # Tempik REST client
│   └── tempmail_client.py          # Tempmail.lol REST client
├── th_action_resolver.py           # Dynamic Server Action parser
├── th_auto_register.py             # Single account registration pipeline
├── th_tor_farm.py                  # Batch farm loop with Tor IP rotation
├── th_tui.py                       # Interactive Rich TUI menu
├── th_preflight.py                 # System & environment health check
├── tor_manager.py                  # Portable Tor bundle downloader & controller
├── inject_th_kv.py                 # 9Router SQLite DB & HTTP injector
├── db_path.py                      # 9Router SQLite database locator
├── requirements.txt                # Python dependencies
└── th_tor_state.json               # Farmed accounts & keys state storage
```

---

## 3. Component Specifications

### 3.1 Central Configuration (`config.json`)
```json
{
  "mail_provider": "gmail_catchall",
  "gmail_address": "",
  "gmail_app_password": "",
  "domain": "arxpays.my.id",
  "tempik_api": "https://tempik.meowx.web.id",
  "tempik_dom": "meowx.web.id",
  "tor_socks_port": 9050,
  "tor_control_port": 9051,
  "r9_url": "http://localhost:20128",
  "r9_pass": "123456",
  "install_9r": true,
  "default_model": "deepseek-v4.1-flash:free",
  "model_locks": [
    "deepseek-v4.1-flash:free",
    "mimo-v2.5:free",
    "qwen3.8-27b:free"
  ]
}
```

### 3.2 Dynamic Server Action Resolver (`th_action_resolver.py`)
- Scrapes `https://tokenharbor.ai/login?mode=signup` via requests (with Tor or fallback direct connection).
- Extracts `$ACTION_1:0` (`id`), `$ACTION_KEY`, and matching `Next-Action` header value.
- Caches the action parameters in memory and on disk (`.th_action_cache.json`).
- If a registration returns action mismatch or HTTP 500/redirect error, invalidates cache and re-scrapes immediately.

### 3.3 Modular Email Engine (`mail_clients/`)
- **`BaseEmailClient`**: Defines `create_inbox() -> tuple[email_address, token_or_state]` and `wait_verification_link(email_or_token, timeout=120) -> str`.
- **`GmailCatchAllClient`**: Connects via IMAP SSL (`imap.gmail.com:993`). Generates address `{rand_str}@{domain}`. Polls `INBOX` and `[Gmail]/Spam` for emails from TokenHarbor, extracting `https://tokenharbor.ai/verify-email?[^"\s<>]+`.
- **`TempikClient`**: Uses session-based inbox creation on `tempik_api` and polls `/api/inboxes/{addr}/messages` for verification link.
- **`TempmailClient`**: Uses `api.tempmail.lol/v2/inbox/create` and polls inbox messages for verification link.

### 3.4 Portable Tor Manager (`tor_manager.py`)
- Checks port 9050 & 9051 availability.
- If not running and `tor/tor.exe` does not exist:
  - Downloads Tor Expert Bundle zip for Windows from official Tor release or backup archive.
  - Extracts to `tor/`.
  - Writes `torrc` configured for SocksPort 9050, ControlPort 9051, `CookieAuthentication 0`.
- Launches `tor.exe` in background subprocess.
- Provides `rotate_ip()` function sending `AUTHENTICATE\r\nSIGNAL NEWNYM\r\n` to ControlPort 9051.

### 3.5 9Router Injector (`inject_th_kv.py` & `db_path.py`)
- Resolves 9Router SQLite path at `~/AppData/Roaming/9router/db/data.sqlite`.
- Inserts new provider connection into `providerConnections`:
  - `provider`: `'openai-compatible'`
  - `authType`: `'api_key'`
  - `data` JSON:
    - `baseUrl`: `'https://tokenharbor.ai/v1'`
    - `prefix`: `'th'`
    - `apiKey`: `api_key`
    - `defaultModel`: `'deepseek-v4.1-flash:free'`
    - `modelLock_deepseek-v4.1-flash:free`: 1
    - `modelLock_mimo-v2.5:free`: 1
    - `modelLock_qwen3.8-27b:free`: 1
- Appends model mapping entries to `kv` table (`scope='customModels'`).
- Sends reload/ping request to 9Router HTTP API (`http://localhost:20128`) if reachable.

### 3.6 Core Registration Pipeline (`th_auto_register.py`)
1. Create email using configured client.
2. Generate random password meeting TokenHarbor criteria.
3. Fetch signup action parameters from `th_action_resolver`.
4. Submit `POST /login` (multipart/form-data) via Tor SOCKS5.
5. On success:
   - Call `GET /api/keys` and delete default generated keys.
   - Call `POST /api/keys` to create dedicated key (`th-XXX`).
   - Call `POST /api/me/privacy` with `{"free_models_enabled": true}`.
   - Poll verification email link and execute `GET` request on verification URL.
   - Perform smoke test via `POST /v1/chat/completions` using `mimo-v2.5:free` or `deepseek-v4.1-flash:free`.
   - Inject key to 9Router and record record in `th_tor_state.json`.

---

## 4. Error Handling & Resilience
- **Tor Circuit Failure / Bad Exit Node:** When TokenHarbor returns "We couldn't create your account" or "Please complete human check", immediately triggers `SIGNAL NEWNYM` and delays 8 seconds.
- **Action ID Expiry:** Auto-resolver detects stale response and refetches fresh hashes.
- **State Persistence:** `th_tor_state.json` tracks all created accounts, API keys, verification status, and injection state, preventing duplicate registrations.

---

## 5. Verification Plan
1. **Preflight Check:** Run `python th_preflight.py` to confirm Python packages, Tor availability, email IMAP connectivity, and 9Router DB access.
2. **Single Registration Test:** Run `python th_auto_register.py single` to verify end-to-end registration of 1 account, email link verification, consent activation, API key creation, smoke test, and 9Router injection.
3. **9Router Verification:** Verify that the new connection and model lock `deepseek-v4.1-flash:free` appear in 9Router.
