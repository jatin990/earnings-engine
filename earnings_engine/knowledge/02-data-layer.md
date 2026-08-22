# 02 — Data Layer

> Related: [01-overview](01-overview.md) → [03-features-labels](03-features-labels.md) → [06-dataset-predict](06-dataset-predict.md)

## Shared SQLite Database (`prices.sqlite3`)
Location: `data/cache/prices/prices.sqlite3`

**Tables:**
- `price_history`: ticker, date, open/high/low/close, volume — PK `(ticker, date)`
- `ticker_metrics`: ticker, as_of_date, metrics (JSON) — PK `(ticker, as_of_date)`. **Used for once-per-day caching of price-derived report fields** (`week_change`, `pct_from_52w_high/low`, `thirty_day_return_pct`, `week_high/low`, `earnings_week_move_pct`) — `enrich_upcoming_results()` reads today's row if present, otherwise recomputes and stores.
- `earnings_history`: ticker, earnings_date, eps_estimate, eps_reported, surprise_pct — PK `(ticker, earnings_date)`
- `earnings_freshness`: ticker, fetched_at — PK `(ticker)`
- `event_dataset`: ID columns (ticker, market, earnings_date, asof_date, reaction_date) + FEATURE_COLUMNS + LABEL_COLUMNS — PK `(ticker, earnings_date)`
- `ticker_market_cap`: ticker, market_cap, fetched_at — PK `(ticker)`, freshness 1 day
- `kronos_predictions`: id, ticker, run_at, predicted_at, lookback, pred_len, prediction_json, current_price, support, resistance, return_pct, trend, explanation — index `idx_kronos_pred_ticker_run (ticker, run_at DESC)`
- `watchlists`: name, ticker, added_at — PK `(name, ticker)`. SQLite-backed watchlist storage (see `data/watchlists.py`)
- `universes`: universe_name, ticker, updated_at — PK `(universe_name, ticker)`. 100% SQLite-backed universe storage for IN, US, NSE_ALL, NSE_LARGE_CAP, and custom universes.
- `universe_freshness`: universe_name, fetched_at — PK `(universe_name)`
- `swing_ranges`: watchlist, ticker, lower_bound, upper_bound, source, cycles, avg_cycle_days, last_updated — PK `(watchlist, ticker)`. Keyed per watchlist so users can maintain independent range hypotheses.
- `swing_cycle_history`: watchlist, ticker, cycle_idx, cycle_start, cycle_end, duration_days, lower_bound, upper_bound — PK `(watchlist, ticker, cycle_idx)`

## `data/earnings.py`
**Constants:** `COLUMNS = ["earnings_date", "eps_estimate", "eps_reported", "surprise_pct"]`

**Functions:**
- `_db_path(settings)` / `_connect(settings)` — shared SQLite, creates `earnings_history` + `earnings_freshness`
- `_is_fresh(ticker, settings)` / `_mark_fresh(ticker, settings)` — freshness via `earnings_freshness`
- `_write_earnings(ticker, settings, df)` — upsert, dedup by earnings_date
- `_migrate_from_parquet(ticker, settings)` — auto-migrate old .parquet
- `fetch_earnings(ticker, settings, force=False)` / `load_earnings(ticker, settings)`
- `upcoming_earnings(tickers, settings, days=14, source=None, start_date=None)` — future events in `[start_date, start_date + days)` window (default start_date = today)
- `_fetch_earnings_for_ticker(args)` / `ingest_earnings(tickers, settings, force=False)` — 10 workers, batches of 50, 2s delay
- `ingest_earnings_incremental(tickers, settings)` — fetches earnings **only** for tickers missing earnings rows; skips tickers with no price history or listed < 90 days ago (too new for quarterly earnings). Returns `{total, already_cached, fetched, skipped_no_listing, errors}`.

**Logging:** summary `"loaded cached earnings for X/Y tickers"`

## `data/coverage.py`
**Function:**
- `get_data_coverage(tickers, settings=None)` — reports per-ticker data coverage from the shared SQLite DB in a single SQL query (LEFT JOINs across `price_history`, `earnings_history`, `earnings_freshness`). Returns `{total, with_prices, with_earnings, rows}` where each row has `ticker`, `price_start/price_end/price_rows`, `earnings_start/earnings_end/earnings_rows`, `has_prices`, `has_earnings`, `listing_date` (price start, listing-date proxy), `earnings_fresh`. Used by the dashboard Data Coverage tab for any universe (IN, US, NSE_ALL, NSE_LARGE_CAP, WATCHLIST).

## `data/watchlists.py`
SQLite-backed watchlist storage (replaces the flat-file `my_watchlist.txt` approach).
- `get_watchlist(name, settings=None)`
- `add_to_watchlist(name, ticker, settings=None)` — rejects duplicates
- `remove_from_watchlist(name, ticker, settings=None)`
- `list_watchlists(settings=None)`

## `data/swing_ranges.py`
SQLite-backed swing range and cycle history storage. Keyed by `(watchlist, ticker)`.
- `get_swing_range(watchlist, ticker, settings=None)`
- `set_user_range(watchlist, ticker, lower, upper, cycles=None, settings=None)` — persists `source='user'`
- `record_auto_range(watchlist, ticker, lower, upper, cycles=None, avg_days=None, cycles_data=None, settings=None)` — records `source='auto'`, never overwrites `source='user'`
- `clear_user_range(watchlist, ticker, settings=None)`
- `list_ranges(watchlist, settings=None)`
- `get_cycle_history(watchlist, ticker, settings=None)`


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
SQLite-backed universe storage (`universes` & `universe_freshness` tables).
- `store_universe(name, tickers, settings=None)` / `get_universe(name, settings=None)`
- `add_to_universe(name, ticker, settings=None)` / `remove_from_universe(name, ticker, settings=None)`
- `list_universes(settings=None)`
- `load_universe(market, settings=None)` — loads IN, US, NSE_ALL, NSE_LARGE_CAP or custom universe directly from SQLite
- `load_nse_all(force_refresh=False, settings=None)` — checks `universe_freshness` in SQLite, queries nsetools when stale, stores in SQLite
- `load_nse_large_cap(force_refresh=False, settings=None)` — checks `universe_freshness` in SQLite, queries yfinance when stale, stores in SQLite
- `load_all(settings=None)` — combines IN + US from SQLite
- Market cap caching: `store_market_cap`, `load_market_cap`, `load_all_market_caps`, `is_market_cap_fresh`, `ingest_market_caps`

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