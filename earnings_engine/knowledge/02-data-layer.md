# 02 — Data Layer

> Related: [01-overview](01-overview.md) → [03-features-labels](03-features-labels.md) → [06-dataset-predict](06-dataset-predict.md)

## Shared SQLite Database (`prices.sqlite3`)
Location: `data/cache/prices/prices.sqlite3`

**Tables:**
- `price_history`: ticker, date, open/high/low/close, volume — PK `(ticker, date)`
- `ticker_metrics`: ticker, as_of_date, metrics (JSON) — PK `(ticker, as_of_date)`. Used for once-per-day caching of price-derived report fields.
- `earnings_history`: ticker, earnings_date, eps_estimate, eps_reported, surprise_pct — PK `(ticker, earnings_date)`
- `earnings_freshness`: ticker, fetched_at — PK `(ticker)`
- `event_dataset`: ID columns + FEATURE_COLUMNS + LABEL_COLUMNS — PK `(ticker, earnings_date)`
- `ticker_market_cap`: ticker, market_cap, fetched_at — PK `(ticker)`, freshness 1 day
- `kronos_predictions`: id, ticker, run_at, predicted_at, lookback, pred_len, prediction_json, current_price, support, resistance, return_pct, trend, explanation — index `idx_kronos_pred_ticker_run (ticker, run_at DESC)`
- `consensus_predictions`: id, ticker, event_date, consensus_json, model_breakdown, targets, stop_loss, outcome — multi-model AI consensus persistence
- `institutional_accumulation_cache`: ticker, accumulation_score, increase_pct, increase_amt_cr, total_holding_cr, net_flow_cr, top_buyers, updated_at — precomputed institutional metrics cache
- `tri_confluence_metrics`: ticker, clean_ticker, company_name, sector, industry, market, market_cap, market_cap_cr, current_price, synergy_score, grade, rating_label, rating_badge, status_desc, hit_rate_pct, confluent_quarters, total_quarters, corr_inst_return, corr_surprise_return, corr_inst_surprise, latest_quarter, latest_inst_pct, latest_inst_delta, latest_surprise_pct, latest_return_pct, latest_confluence_aligned, quarters_json, top_holders_json, insights_json, calculated_at, updated_at — persistent table for Tri-Factor institutional-earnings-returns cross-correlation and confluence scoring (Migration 28)
- `breakout_radar` / `breakout_tracked_signals`: id, ticker, strategy_name, trigger_price, stop_loss, target_price, detected_at, status, outcome_return — tracked breakout setups
- `breakout_audit_log`: id, signal_id, evaluated_at, exit_price, exit_return, win_loss, deduplication_hash
- `option_chain_history`: symbol, strike_price, expiry_date, call_oi, put_oi, spot_price, pcr, fetched_at — NSE derivatives option chain persistence
- `participant_oi_history`: date, client_oi, dii_oi, fii_oi, pro_oi, net_ratio — 7-day participant derivatives OI breakdown
- `sidebar_badges`: tab_name, badge_count, metadata_json, updated_at — sub-millisecond sidebar badge counters
- `automation_schedules`: schedule_id, task_name, cron_expr, next_run_at, status, last_error — master scheduler persistence
- `watchlists`: name, ticker, added_at — PK `(name, ticker)`
- `universes`: universe_name, ticker, updated_at — PK `(universe_name, ticker)`
- `universe_freshness`: universe_name, fetched_at — PK `(universe_name)`
- `swing_ranges`: watchlist, ticker, lower_bound, upper_bound, source, cycles, avg_cycle_days, last_updated — PK `(watchlist, ticker)`
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

## `data/institutional_accumulation.py` & `institutional_catalog.py`
**Purpose:** Multi-tier institutional shareholding & AMFI fund tracking across 410+ entities.
- Calculates 3 key metrics: Increase %, Increase Amount (₹ Cr), and Total Holding Amount (₹ Cr).
- Caches pre-computed metrics into `institutional_accumulation_cache` for sub-10ms query performance.

## `data/tri_confluence.py`
**Purpose:** Tri-Factor Alpha Synergy and Cross-Correlation engine.
- Reconstructs quarterly historical vectors aligning $\Delta \text{Inst}$ (FII + DII), EPS Surprise %, and Returns.
- Computes Pearson correlation coefficients ($r_{\text{inst, ret}}$, $r_{\text{surp, ret}}$, $r_{\text{inst, surp}}$), Triple Confluence Hit Rate %, and composite Synergy Score (0–100) with letter grades (A+ Triple Alpha, A High Synergy, B Moderate, C/D Divergent).
- In-memory TTL caching for fast scanner and macro summary responses.

## `data/breakout_scanner.py`
**Purpose:** 5-strategy breakout scanner (Compression, 52W High Momentum, Volume Expansion, S/R Breach, Composite ALL).
- Tracks candidate pools, records signals in `breakout_tracked_signals`, and audits realized outcomes in `breakout_audit_log` with deduplication hashing.

## `data/market_pulse.py` & `option_chain.py`
**Purpose:** Market-wide pulse, 7-day Participant OI matrix (FII, DII, Client, Pro), sector heatmaps, and NSE option chain persistence in `option_chain_history`.

## `data/omniroute_client.py` & `consensus/`
**Purpose:** Universal AI proxy to OmniRoute gateway supporting Antigravity, local/cloud models, DeepSeek-R1, Llama-3.3-70B, Qwen-2.5-72B, and Mistral-Large with sliding-window rate limiting.