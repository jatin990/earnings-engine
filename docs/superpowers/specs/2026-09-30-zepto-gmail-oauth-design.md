# Specification: Zepto Hub Gmail OAuth 2.0 Linking

## 1. Overview & Objective
Enable linking a Google/Gmail account via OAuth 2.0 in the Zepto Dark Store Management Hub (`/zepto`). This establishes the foundational auth and token management layer required to securely read store-related emails, dispatch reports, and parse dark store metrics in subsequent phases.

## 2. Configuration & Environment Variables
Configured via `.env` / `earnings_engine.config.Settings`:
- `GOOGLE_CLIENT_ID`: OAuth 2.0 Client ID generated from Google Cloud Console.
- `GOOGLE_CLIENT_SECRET`: OAuth 2.0 Client Secret.
- `GOOGLE_REDIRECT_URI`: OAuth callback URI (default: `http://localhost:8000/api/v1/zepto/gmail/callback` or dynamic based on Host header).
- Scopes requested:
  - `https://www.googleapis.com/auth/gmail.readonly`
  - `openid`
  - `https://www.googleapis.com/auth/userinfo.email`
  - `https://www.googleapis.com/auth/userinfo.profile`

## 3. Database Schema & Data Access Layer
File: `earnings_engine/data/zepto_db.py`

### Table: `zepto_gmail_auth`
```sql
CREATE TABLE IF NOT EXISTS zepto_gmail_auth (
    id TEXT PRIMARY KEY,               -- 'primary' default identifier
    email TEXT NOT NULL,
    access_token TEXT NOT NULL,
    refresh_token TEXT,
    token_expiry TEXT,
    token_type TEXT DEFAULT 'Bearer',
    scopes TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'CONNECTED',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

### Data Access Functions
- `ensure_zepto_schema()`: Migration logic creating `zepto_gmail_auth` table and indexes.
- `save_gmail_auth(email, access_token, refresh_token, token_expiry, scopes)`: Store or update token record.
- `get_gmail_auth(auth_id='primary') -> dict | None`: Retrieve credentials.
- `delete_gmail_auth(auth_id='primary') -> bool`: Delete auth record upon disconnection.
- `get_valid_gmail_token(auth_id='primary') -> str | None`: Returns active `access_token`, automatically refreshing if expired or expiring within 5 minutes.

### Turso Cloud Sync Contract
- Register `zepto_gmail_auth` in `SYNC_TABLES` list in `earnings_engine/data/turso_sync.py`.

## 4. API Endpoints
File: `earnings_engine/api/routers/zepto.py`

- `GET /api/v1/zepto/gmail/status`:
  - Returns `{ "configured": bool, "connected": bool, "email": str | None, "token_expiry": str | None, "updated_at": str | None }`
- `GET /api/v1/zepto/gmail/auth-url`:
  - Builds Google OAuth authorization URL with anti-CSRF state token and parameters:
    - `access_type=offline`
    - `prompt=consent`
    - `response_type=code`
    - `scope=...`
    - `redirect_uri=...`
- `GET /api/v1/zepto/gmail/callback`:
  - Validates `state`, exchanges `code` for tokens with Google endpoint (`https://oauth2.googleapis.com/token`).
  - Queries UserInfo endpoint (`https://www.googleapis.com/oauth2/v2/userinfo`) to get user email.
  - Persists tokens via `save_gmail_auth`.
  - Redirects browser to `/zepto#gmail?status=connected`.
- `POST /api/v1/zepto/gmail/disconnect`:
  - Attempts token revocation with Google (`https://oauth2.googleapis.com/revoke`).
  - Calls `delete_gmail_auth('primary')`.
  - Returns `{ "status": "success", "message": "Gmail account disconnected" }`.

## 5. Frontend & UI Integration
Files:
- `earnings_engine/reports/templates/hubs/zepto/index.html`
- `earnings_engine/reports/templates/hubs/zepto/_gmail.html`
- `earnings_engine/ui/js/modules/zepto.js`

### UI Features:
1. **Header Gmail Badge**: Top navigation pill indicating connection status (`📧 Connect Gmail` / `🟢 Gmail: user@gmail.com`).
2. **Dedicated Tab**: `📧 Gmail Integration` in tab bar navigation (`#gmail`).
3. **Disconnected State Card**:
   - Instructions and status of `.env` configuration (`GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`).
   - High-visibility "Connect Gmail Account" button initiating OAuth flow.
4. **Connected State Card**:
   - Connected Gmail badge with user email, scope indicators, last refreshed timestamp.
   - "Disconnect Account" button with confirm dialog.
   - Next-phase placeholder for mailbox parser and metric extraction.

## 6. Verification & Testing
- Add unit and integration tests in `tests/test_zepto_gmail_auth.py`:
  - Auth URL generation with valid scopes & redirect parameters.
  - Mocked OAuth callback code exchange & token storage.
  - Automatic token refresh logic.
  - Status and disconnect lifecycle.
  - SQLite and Turso sync contract registration tests.
