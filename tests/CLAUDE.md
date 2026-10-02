# CLAUDE.md — Testing Suite (`tests/`)

> Subsystem guide for pytest test conventions, targeted execution, mocking, and PIT test hygiene.

---

## 1. Scope & Architecture

The test suite validates quantitative feature calculations, database replication, API endpoints, Point-in-Time integrity, and multi-model consensus behavior.

- **Feature & Quant Tests**: `tests/test_features.py`, `tests/test_labels.py`, `tests/test_dataset.py`
- **Data & Storage Tests**: `tests/test_db.py`, `tests/test_turso_sync.py`, `tests/test_new_listings.py`
- **API Router Tests**: `tests/test_api.py`, `tests/test_routers_*.py`
- **Model & Prediction Tests**: `tests/test_predict.py`, `tests/test_consensus.py`, `tests/test_kronos.py`
- **End-to-End Tests**: `tests/test_stock_detail_e2e.py` (slow E2E tests, only run on demand)

---

## 2. Core Testing Invariants

### 2.1 Targeted Execution Rule (Strict Efficiency)
- **Always run targeted tests** during iterative development (use forward slashes `./.venv/Scripts/python.exe` to prevent Git Bash escaping issues):
  ```bash
  ./.venv/Scripts/python.exe -m pytest tests/test_new_listings.py -v
  ./.venv/Scripts/python.exe -m pytest tests/test_db.py -k "test_turso_sync"
  ```
- **Prohibition**: Never run the full test suite or slow E2E suites (`test_stock_detail_e2e.py`) during incremental coding tasks.

### 2.2 Test Isolation & Database Hygiene
- Always use in-memory or temporary SQLite databases (`:memory:` or `tmp_path`) for unit tests.
- Never write test records to production databases (`prices.sqlite3` or `earnings_engine.db`).

### 2.3 External API Mocking
- Mock all external network calls (NSE India scrapers, Yahoo Finance, Broker APIs, OpenRouter/OmniRoute).
- Verify offline deterministic behavior across all unit test paths.

### 2.4 Point-in-Time (PIT) Verification
- Ensure tests strictly assert that features computed for event date $T$ only reference price bars where $\text{date} \le T-1$.
