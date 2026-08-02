# Implementation Plan

## Overview
Add an auditable, persistent trail for every Kronos AI price prediction: store each run in the shared SQLite cache, surface it on the Kronos tab as "Latest" and "Audit" views (with live current price + change since prediction), plus fix two bugs (duplicate Results rows, weak date filter) and add the ability to create new watchlist files.

## Feature List (executed one-by-one)
1. **Audit persistence layer** — new `data/predictions.py` module + `kronos_predictions` table in `prices.sqlite3`.
2. **Persist on run** — `dashboard_api.get_kronos_predictions()` stores every forecast dict before returning.
3. **API endpoints** — `GET /api/v1/dashboard/kronos/audit`, `GET .../kronos/latest`, `POST /api/v1/universe/create`.
4. **Kronos tab UI** — split into Latest + Audit tabs; Audit table shows run date, predicted price, live current price, change vs prediction.
5. **Create watchlist UI** — input + button in Watchlist tab → `POST /api/v1/universe/create`.
6. **Bug: duplicate earnings rows** — dedup `earnings.py` normalize path by `earnings_date` (regression test).
7. **Bug: date filter** — verify `days` param flows end-to-end; surface count in UI.
8. **Tests** — `tests/test_kronos_audit.py` + regression tests in `test_caching.py`.
9. **Docs** — update `KNOWLEDGE_BASE.md` Section 10 + module refs per Cline rules.

## Types / Data Schema
New SQLite table `kronos_predictions`:
- `id` INTEGER PRIMARY KEY AUTOINCREMENT
- `ticker` TEXT NOT NULL
- `run_at` TEXT NOT NULL (ISO timestamp of the prediction run)
- `predicted_at` TEXT NOT NULL (the price-date the prediction was made at)
- `lookback` INTEGER, `pred_len` INTEGER
- `prediction_json` TEXT NOT NULL (full forecast dict as JSON)
- `current_price` REAL (price at prediction time)
- `support` REAL, `resistance` REAL
- `return_pct` REAL, `trend` TEXT
- `explanation` TEXT
- Index on `(ticker, run_at DESC)`.

## Files
### New
- `earnings_engine/data/predictions.py` — SQLite audit CRUD for Kronos predictions.
- `tests/test_kronos_audit.py` — audit persistence + latest-per-ticker tests.

### Modified
- `earnings_engine/api/dashboard_api.py` — persist forecasts in `get_kronos_predictions`; add `get_kronos_predictions_audit()` + `get_kronos_latest_predictions()` + `create_universe_file()`.
- `earnings_engine/api/server.py` — new endpoints: `/audit`, `/latest`, `POST /api/v1/universe/create`.
- `earnings_engine/data/earnings.py` — dedup normalize path (bug fix).
- `earnings_engine/reports/templates/dashboard.html` — Kronos Latest/Audit sub-tabs, current-price-change column, create-watchlist control.
- `earnings_engine/KNOWLEDGE_BASE.md` — Section 10 + module section updates.

## Functions
### New
- `data/predictions.py`:
  - `store_prediction(ticker, settings, payload) -> int`
  - `load_prediction_history(tickers=None, limit=None) -> list[dict]` (full audit)
  - `load_latest_predictions(tickers=None) -> list[dict]` (latest per ticker)
- `dashboard_api.py`:
  - `get_kronos_predictions_audit(tickers=None, limit=None) -> list[dict]`
  - `get_kronos_latest_predictions(tickers=None) -> list[dict]`
  - `create_universe_file(name, tickers) -> dict`
- `server.py`: new route handlers (thin wrappers).

### Modified
- `get_kronos_predictions()` — call `store_prediction` for each result.
- `earnings.py` `_write_earnings` / normalize — add `drop_duplicates(subset=["earnings_date"])`.

## Classes
None new (follow existing module-function pattern).

## Dependencies
None new (uses existing `sqlite3`, `pandas`, `json`, `Settings`).

## Testing
- `tests/test_kronos_audit.py`: store+load round-trip, latest-per-ticker, dedup-by-timestamp, JSON payload fidelity. Uses `tmp_path` Settings override (no network).
- `tests/test_caching.py`: add `test_upcoming_earnings_no_duplicates`.
- Full suite: `python -m pytest tests/ -v`.

## Implementation Order
1. Create `data/predictions.py` + tests, verify in isolation.
2. Wire persistence into `dashboard_api.get_kronos_predictions`.
3. Add API endpoints in `server.py`.
4. Frontend Kronos Latest/Audit tabs + create-watchlist.
5. Fix duplicate-earnings bug in `earnings.py` + regression test.
6. Run full test suite; update KNOWLEDGE_BASE.md.
