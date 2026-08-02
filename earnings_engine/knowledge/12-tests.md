# 12 — Test Coverage

> Related: [11-notes](11-notes.md) → [13-config-env](13-config-env.md)

## `tests/test_backtest.py`
- Tests `run_backtest()` and `compute_metrics()`
- Verifies trade simulation, metrics calculation

## `tests/test_caching.py`
- Tests price/earnings cache freshness and loading
- `test_upcoming_earnings_no_duplicates` — fetches "DUP", asserts `upcoming_earnings(["DUP","DUP","DUP"])` returns exactly 1 row

## `tests/test_classifier.py`
- Tests `GBClassifier` fit/predict/probability calibration

## `tests/test_dataset.py`
- Tests `build_ticker_events()` and feature computation

## `tests/test_kronos_audit.py`
- 7 tests covering store/load history/latest predictions for the Kronos audit layer (`data/predictions.py`)

## `tests/test_predict.py`
- Tests `build_upcoming_events()` and `predict_upcoming()`
- Tests `render_upcoming_results_report()` formatting: market cap Cr conversion, quality /9 scores, 52W gap 2-line format, per-quarter week high/low, signed percents
- Tests `enrich_upcoming_results()` with per-quarter week high/low and individual quarter scores
- Tests quality score 3Q averaging logic
- Tests CLI `upcoming-results` command with email, CSV export, log files
- Tests `render_dashboard` tab-based layout and dashboard endpoints

## `tests/test_universe.py`
- Tests `load_universe()`, `load_all()`, `load_universe_from_file()`
- Tests `load_nse_all()` cache freshness, stale refresh, no-cache fetch, error fallback
- Tests `load_universe('NSE_ALL')` integration
- Tests `load_nse_large_cap()` cache freshness, stale refresh, no-cache fetch, error fallback
- Tests `load_universe('NSE_LARGE_CAP')` integration
- Tests market cap caching: `store_market_cap()`, `load_market_cap()`, `is_market_cap_fresh()`, `load_all_market_caps()`, `ingest_market_caps()` cache hit

## `test_api.py` (repo root)
- 7 dashboard API tests: overview, results, swing, refresh-status, watchlist CRUD, dashboard endpoint