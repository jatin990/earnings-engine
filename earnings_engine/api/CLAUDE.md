# CLAUDE.md — API Subsystem (`earnings_engine/api/`)

> Subsystem guide for FastAPI application, routers, dependencies, and REST API contracts.

---

## 1. Scope & Architecture

The API subsystem exposes REST endpoints for the quantitative equity research platform, scanners, institutional intelligence, multi-model consensus, and operational hubs.

- **Main Entrypoint**: `earnings_engine/api/server.py` (FastAPI instance, middleware, CORS, router mounts)
- **Domain Routers**: `earnings_engine/api/routers/*.py` (22 domain routers mounted under `/api/v1`)
- **Shared Dependencies**: `earnings_engine/api/dependencies.py` (auth, DB sessions, rate limiting)
- **Specialized Endpoints**: `stock_api.py`, `dashboard_api.py`, `recalculate_api.py`, `playground_api.py`

---

## 2. Core Invariants & Rules

### 2.1 Static vs. Parameterized Route Precedence
- **Strict Rule**: In `server.py` and all router files, **always declare explicit static/literal routes BEFORE parameterized routes**.
  ```python
  # CORRECT:
  @router.get("/api/v1/watchlist/quotes")
  def get_watchlist_quotes(): ...

  @router.get("/api/v1/watchlist/{name}")
  def get_watchlist_by_name(name: str): ...
  ```

### 2.2 On-Demand AI Inference & Zero-Token Default
- **Never invoke automated LLM calls** on GET endpoints, page load, modal open, or table renders.
- AI Consensus inference endpoints must only be triggered via explicit POST actions (e.g., `/api/v1/consensus/run`).

### 2.3 Real-Data Integrity & Error Responses
- **No Mock/Dummy Payloads**: Return `None`, `0.0`, `[]`, or HTTP 404/422 with meaningful details if data is missing.
- When markets are closed, return structured metadata (`status: "market_closed"`, snapshot timestamp) rather than fabricated metrics.
- Suffix rule: Indian equities require `.NS` (`TCS.NS`), US equities do not. Resolve via `market_of(ticker)` from `earnings_engine.config`.

### 2.4 Authentication & Session Contracts
- Passcode validation (`/api/v1/auth/passcode`), 6-digit OTP, and HMAC-SHA256 tokens.
- Secure cookie and header parsing handled in `dependencies.py` and `routers/auth.py`.

---

## 3. Targeted Testing

```bash
# Run API router unit tests
./.venv/Scripts/python.exe -m pytest tests/test_api.py -v
./.venv/Scripts/python.exe -m pytest tests/ -k "router or api"
```
