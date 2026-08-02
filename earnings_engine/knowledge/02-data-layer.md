# 02 — Data Layer

> Related: [01-overview](01-overview.md) → [03-features-labels](03-features-labels.md) → [06-dataset-predict](06-dataset-predict.md)

## Shared SQLite Database (`prices.sqlite3`)
Location: `data/cache/prices/prices.sqlite3`

**Tables:**
- `price_history`: ticker, date, open/high/low/close, volume — PK `(ticker, date)`
- `ticker_metrics`: ticker, as_of_date, metrics (JSON) — PK `(ticker, as_of_date)`
- `earnings_history`: ticker, earnings_date, eps_estimate, eps_reported, surprise_pct — PK `(ticker, earnings_date)`
- `earnings_freshness`: ticker, fetched_at — PK `(ticker)`
- `event_dataset`: ID columns (ticker, market, earnings_date, asof_date, reaction_date) + FEATURE_COLUMNS + LABEL_COLUMNS — PK `(ticker, earnings_date)`
- `ticker_market_cap`: ticker, market_cap, fetched_at — PK `(ticker)`, freshness 1 day
- `kronos_predictions`: id, ticker, run_at, predicted_at, lookback, pred_len, prediction_json, current_price, support, resistance, return_pct, trend, explanation — index `idx_kronos_pred_ticker_run (ticker, run_at DESC)`

## `data/earnings.py`
**Constants:** `COLUMNS = ["earnings_date", "eps_estimate", "eps_reported", "surprise_pct"]`

**Functions:**
- `_db_path(settings)` / `_connect(settings)` — shared SQLite, creates `earnings_history` + `earnings_freshness`
- `_is_fresh(ticker, settings)` / `_mark_fresh(ticker, settings)` — freshness via `earnings_freshness`
- `_write_earnings(ticker, settings, df)` — upsert, dedup by earnings_date
- `_migrate_from_parquet(ticker, settings)` — auto-migrate old .parquet
- `fetch_earnings(ticker, settings, force=False)` / `load_earnings(ticker, settings)`
- `upcoming_earnings(tickers, settings, days=14)` — future events, **dedups by `(ticker, earnings_date)`**
- `_fetch_earnings_for_ticker(args)` / `ingest_earnings(tickers, settings, force=False)` — 10 workers, batches of 50, 2s delay

**Logging:** summary `"loaded cached earnings for X/Y tickers"`

## `data/prices.py`
**Constants:** `COLUMNS = ["open", "high", "low", "close", "volume"]`

**Functions:**
- `_cache_path(settings)` — `prices.sqlite3`
- `_connect(settings)` / `_is_fresh(ticker, settings)` (any rows) / `_write_prices(ticker, settings, df)`
- `fetch_prices(ticker, settings, force=False)` / `load_prices(ticker, settings)`
- `store_price_metrics(ticker, settings, metrics, as_of_date=None)` / `load_price_metrics(ticker, settings, as_of_date=None)`
- `_fetch_prices_for_ticker(args)` / `ingest_prices(tickers, settings, force=False)` — 10 workers, batches of 50, 2s delay

**Logging:** `"prices ingest batch X/Y complete: N/M tickers processed"`

## `data/universe.py`
**Constants:** `UNIVERSE_DIR`, `NSE_ALL_FILE`, `NSE_LARGE_CAP_FILE`, `NSE_ALL_MAX_AGE_DAYS = 7`, `NSE_LARGE_CAP_MIN_CR = 1000`, `MARKET_CAP_MAX_AGE_DAYS = 1`

**Market cap caching:** `_db_path`, `_connect_market_cap` (creates `ticker_market_cap`), `is_market_cap_fresh`, `store_market_cap`, `load_market_cap`, `load_all_market_caps`, `ingest_market_caps`

**Functions:**
- `_read_universe(name)` / `load_universe(market)` / `load_universe_from_file(path)` / `load_all()`
- NSE_ALL: `_is_nse_all_fresh`, `_fetch_nse_all_from_nsetools`, `_write_nse_all_file`, `_read_nse_all_file`, `load_nse_all(force_refresh=False)` — 7-day cache, nsetools fallback
- NSE_LARGE_CAP: `_is_nse_large_cap_fresh`, `_fetch_nse_large_cap_from_yfinance`, `_write_nse_large_cap_file`, `_read_nse_large_cap_file`, `load_nse_large_cap(force_refresh=False)` — 7-day cache, yfinance fallback

## `data/market_context.py`
**Functions:**
- `_score_surprise(surprise)` — 1-9 score
- `_score_previous_earnings(earnings, lookback=3)` — 1-9 quality, averages quarter scores
- `_week_high_low_around(prices, earnings_date)` — (high_pct, low_pct, high_price, low_price) ±4 business days
- `enrich_upcoming_results(df, settings=None)` — adds market context columns

**Scoring scale:** >=15%→9, >=10%→8, >=5%→7, >=0%→6, >=-5%→5, >=-10%→4, else→3, empty→5

**Columns added:** market_cap, current_price, week_change, pct_from_52w_high/low, thirty_day_return_pct, earnings_week_move_pct, earnings_week_high/low_pct, earnings_week_high/low_price, week_high, week_low, prev_quarter_earnings_score, prev_3q_earnings_score, q1/q2/q3_earnings_score, q1/q2/q3_week_high/low_pct, q1/q2/q3_week_high/low_price, next_resistance, current_support, eps_estimate, eps_reported, surprise_pct

## `data/predictions.py` (Kronos audit)
**Purpose:** Persistence + audit for Kronos predictions.

**Functions:**
- `_db_path(settings)` / `_connect(settings)` — creates `kronos_predictions` + index
- `_row_to_dict(row)`
- `store_prediction(ticker, settings, payload, run_at=None, predicted_at=None) -> int`
- `load_prediction_history(tickers=None, limit=None, settings=None) -> list[dict]` — ORDER BY run_at DESC, id DESC
- `load_latest_predictions(tickers=None, settings=None) -> list[dict]` — first per ticker from history