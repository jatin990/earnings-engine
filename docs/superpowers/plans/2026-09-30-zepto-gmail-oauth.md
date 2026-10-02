# Zepto Hub Gmail OAuth 2.0 Linking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Google OAuth 2.0 account linking for the Zepto Dark Store Hub, securely persisting tokens in SQLite (with Turso sync registration) and providing a reactive connection UI and disconnect lifecycle.

**Architecture:** 
- Database layer: `zepto_gmail_auth` table in SQLite (`zepto_db.py`), tracked in `turso_sync.py` `SYNC_TABLES`. Helper functions manage storage, retrieval, and auto-refresh of access tokens using refresh tokens.
- REST API layer: FastAPI endpoints in `earnings_engine/api/routers/zepto.py` providing `/api/v1/zepto/gmail/status`, `/api/v1/zepto/gmail/auth-url`, `/api/v1/zepto/gmail/callback`, and `/api/v1/zepto/gmail/disconnect`.
- UI layer: `_gmail.html` partial, `#gmail` tab in `index.html`, and client state handling in `earnings_engine/ui/js/modules/zepto.js`.

**Tech Stack:** Python 3.14 / FastAPI, httpx (async HTTP requests), SQLite / WAL, Jinja2, Tailwind CSS, Vanilla JS.

**Spec:** `docs/superpowers/specs/2026-09-30-zepto-gmail-oauth-design.md`

## Global Constraints
- `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI` read from environment variables.
- Scopes requested: `https://www.googleapis.com/auth/gmail.readonly openid https://www.googleapis.com/auth/userinfo.email https://www.googleapis.com/auth/userinfo.profile`.
- Zero-tolerance for mock/fake tokens in production.
- `SYNC_TABLES` rule: Every new table MUST be added to `SYNC_TABLES` in `earnings_engine/data/turso_sync.py`.
- Run targeted tests using `.\.venv\Scripts\python.exe -m pytest <test_path> -v`.

## Review Focus
1. Missing Google client credentials in `.env` — Must return `configured: false` with friendly instructions, never 500 error.
2. Expired access token with valid refresh token — Must transparently refresh and update database without forcing the user to re-link.
3. State mismatch or CSRF token tampering on callback — Must return 400 Bad Request with explicit error message.
4. User cancellation or denied access on Google consent screen — Must handle `?error=access_denied` gracefully and redirect with clean status message.
5. Table sync contract — Must be in `SYNC_TABLES` with watermark candidates for Turso bidirectional merge.

---

### Task 1: Database Schema & Token Management DAL

**Files:**
- Modify: `earnings_engine/data/zepto_db.py`
- Modify: `earnings_engine/data/turso_sync.py:115-125`
- Test: `tests/test_zepto_gmail_auth.py`

**Interfaces:**
- Produces:
  - `save_gmail_auth(email: str, access_token: str, refresh_token: str | None, token_expiry: str | None, scopes: str, auth_id: str = "primary") -> dict`
  - `get_gmail_auth(auth_id: str = "primary") -> dict | None`
  - `delete_gmail_auth(auth_id: str = "primary") -> bool`
  - `get_valid_gmail_token(auth_id: str = "primary", settings: Settings | None = None) -> str | None`

- [ ] **Step 1: Write the failing tests for DAL and SYNC_TABLES**

Create `tests/test_zepto_gmail_auth.py`:
```python
import pytest
from earnings_engine.data.zepto_db import (
    ensure_zepto_schema,
    save_gmail_auth,
    get_gmail_auth,
    delete_gmail_auth,
)
from earnings_engine.data.turso_sync import SYNC_TABLES

def test_sync_tables_includes_zepto_gmail_auth():
    assert "zepto_gmail_auth" in SYNC_TABLES

def test_gmail_auth_crud_lifecycle():
    ensure_zepto_schema()
    # Save auth
    record = save_gmail_auth(
        email="darkstore@zepto.in",
        access_token="ya29.test_token",
        refresh_token="1//refresh_token",
        token_expiry="2026-12-31T23:59:59Z",
        scopes="https://www.googleapis.com/auth/gmail.readonly",
    )
    assert record["email"] == "darkstore@zepto.in"
    assert record["access_token"] == "ya29.test_token"

    # Get auth
    loaded = get_gmail_auth()
    assert loaded is not None
    assert loaded["email"] == "darkstore@zepto.in"

    # Delete auth
    deleted = delete_gmail_auth()
    assert deleted is True
    assert get_gmail_auth() is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_zepto_gmail_auth.py -v`
Expected: FAIL because `zepto_gmail_auth` is not in `SYNC_TABLES` and functions do not exist.

- [ ] **Step 3: Implement minimal schema and DAL functions**

1. In `earnings_engine/data/turso_sync.py`: Add `"zepto_gmail_auth"` to `SYNC_TABLES`.
2. In `earnings_engine/data/zepto_db.py`:
   - In `ensure_zepto_schema()` add `CREATE TABLE IF NOT EXISTS zepto_gmail_auth (...)`.
   - Implement `save_gmail_auth`, `get_gmail_auth`, `delete_gmail_auth`, and `get_valid_gmail_token`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_zepto_gmail_auth.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add earnings_engine/data/zepto_db.py earnings_engine/data/turso_sync.py tests/test_zepto_gmail_auth.py
git commit -m "feat(zepto): add zepto_gmail_auth schema, DAL, and turso sync registration"
```

---

### Task 2: FastAPI REST API Endpoints for Google OAuth Flow

**Files:**
- Modify: `earnings_engine/api/routers/zepto.py`
- Test: `tests/test_zepto_gmail_auth.py`

**Interfaces:**
- Consumes: `get_gmail_auth`, `save_gmail_auth`, `delete_gmail_auth` from `zepto_db`
- Produces:
  - `GET /api/v1/zepto/gmail/status`
  - `GET /api/v1/zepto/gmail/auth-url`
  - `GET /api/v1/zepto/gmail/callback`
  - `POST /api/v1/zepto/gmail/disconnect`

- [ ] **Step 1: Write tests for the Gmail OAuth API endpoints**

Append to `tests/test_zepto_gmail_auth.py`:
```python
from fastapi.testclient import TestClient
from earnings_engine.api.server import app

client = TestClient(app)

def test_gmail_status_unconfigured(monkeypatch):
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)
    resp = client.get("/api/v1/zepto/gmail/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["configured"] is False
    assert data["connected"] is False

def test_gmail_auth_url_generation(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "mock-client-id.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "mock-secret")
    resp = client.get("/api/v1/zepto/gmail/auth-url")
    assert resp.status_code == 200
    data = resp.json()
    assert "auth_url" in data
    assert "mock-client-id" in data["auth_url"]
    assert "access_type=offline" in data["auth_url"]
    assert "state" in data

def test_gmail_disconnect_lifecycle(monkeypatch):
    save_gmail_auth("test@gmail.com", "tok", "ref", "exp", "scope")
    resp = client.post("/api/v1/zepto/gmail/disconnect")
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"
    assert get_gmail_auth() is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_zepto_gmail_auth.py -k "test_gmail_status" -v`
Expected: FAIL with 404 Not Found.

- [ ] **Step 3: Implement endpoints in `earnings_engine/api/routers/zepto.py`**

Declare explicit static routes:
- `/api/v1/zepto/gmail/status`
- `/api/v1/zepto/gmail/auth-url`
- `/api/v1/zepto/gmail/callback`
- `/api/v1/zepto/gmail/disconnect`

Use `httpx` to handle Google OAuth token exchange and user info fetching with proper exception handling.

- [ ] **Step 4: Run test to verify it passes**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_zepto_gmail_auth.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add earnings_engine/api/routers/zepto.py tests/test_zepto_gmail_auth.py
git commit -m "feat(zepto): implement gmail oauth rest endpoints and lifecycle"
```

---

### Task 3: UI Integration & Reactivity in Zepto Hub

**Files:**
- Create: `earnings_engine/reports/templates/hubs/zepto/_gmail.html`
- Modify: `earnings_engine/reports/templates/hubs/zepto/index.html:220-350`
- Modify: `earnings_engine/ui/js/modules/zepto.js`
- Test: `tests/test_zepto_hub.py`

**Interfaces:**
- Consumes: REST endpoints `/api/v1/zepto/gmail/status`, `/api/v1/zepto/gmail/auth-url`, `/api/v1/zepto/gmail/disconnect`.
- Produces: Reactive Gmail connection header badge, `#gmail` tab navigation, and connect/disconnect workflows.

- [ ] **Step 1: Write integration test for Zepto template rendering with Gmail tab**

In `tests/test_zepto_hub.py`:
```python
def test_zepto_hub_renders_gmail_tab(client):
    resp = client.get("/zepto")
    assert resp.status_code == 200
    assert "tabBtn-gmail" in resp.text
    assert "tabContent-gmail" in resp.text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_zepto_hub.py -k "test_zepto_hub_renders_gmail_tab" -v`
Expected: FAIL

- [ ] **Step 3: Implement `_gmail.html`, header button, and `zepto.js` controller**

1. Create `earnings_engine/reports/templates/hubs/zepto/_gmail.html`:
   - Configured vs unconfigured `.env` warning box.
   - Connected vs disconnected Obsidian glass panels.
   - Connect button, Disconnect button, and Token validity health pill.
2. In `earnings_engine/reports/templates/hubs/zepto/index.html`:
   - Add Gmail status badge in header (`#gmailHeaderStatusBtn`).
   - Add `tabBtn-gmail` in navigation bar.
   - Include `{% include "hubs/zepto/_gmail.html" %}` in `#tabContent-gmail`.
3. In `earnings_engine/ui/js/modules/zepto.js`:
   - Add `checkGmailStatus()`, `connectGmail()`, `disconnectGmail()`.
   - Call `checkGmailStatus()` during `init()` and handle URL hash `#gmail` and query params (`?status=connected`).

- [ ] **Step 4: Run tests to verify all tests pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_zepto_hub.py -v`
Run: `.\.venv\Scripts\python.exe -m pytest tests/test_zepto_gmail_auth.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add earnings_engine/reports/templates/hubs/zepto/ earnings_engine/ui/js/modules/zepto.js tests/test_zepto_hub.py
git commit -m "feat(zepto): add gmail oauth connection tab and reactive ui controller"
```

---

### Task 4: Documentation & Memory Persistence

**Files:**
- Modify: `C:\Users\91700\.claude\projects\D--earnings-engine\memory\database-and-sync-mechanics.md`
- Create: `C:\Users\91700\.claude\projects\D--earnings-engine\memory\zepto-gmail-oauth-subsystem.md`
- Modify: `C:\Users\91700\.claude\projects\D--earnings-engine\memory\MEMORY.md`

- [ ] **Step 1: Document `zepto_gmail_auth` schema and Turso sync contract in persistent memory**
- [ ] **Step 2: Run error ledger check (`python scripts/error_ledger.py scan`) to ensure zero errors introduced**
- [ ] **Step 3: Push changes to remote branch**
