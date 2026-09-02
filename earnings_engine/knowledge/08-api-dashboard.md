# 08 — API & Dashboard

> Related: [02-data-layer](02-data-layer.md) → [07-reports](07-reports.md) → [09-cli-config](09-cli-config.md)

## `api/server.py` (FastAPI)
**Endpoints:**
- `GET /health` — health check
- `GET /api/v1/price-history/{ticker}` — OHLCV price data
- `GET /api/v1/earnings-history/{ticker}` — earnings history
- `GET /api/v1/market-cap/{ticker}` — market cap
- `GET /api/v1/market-context/{ticker}` — enriched market context
- `GET /api/v1/upcoming-earnings` — upcoming earnings events
- `GET /api/v1/universe/{market}` — ticker universe
- `GET /api/v1/market-caps` — all cached market caps
- `GET /api/v1/universe/files` — list universe files
- `POST /api/v1/universe/add` — add tickers to universe file
- `POST /api/v1/universe/remove` — remove tickers from universe file
- `POST /api/v1/universe/create` — create a new universe file (body `{"file","tickers"}`)
- `GET /api/v1/correlation/summary` — aggregate macro metrics for Tri-Factor Institutional-Earnings-Returns synergy
- `GET /api/v1/correlation/tri-confluence?universe=&min_score=&sort_by=&limit=` — scan & rank equities exhibiting direct positive correlation across institutional flows, earnings beats, and returns
- `GET /api/v1/correlation/ticker/{ticker}` — multi-quarter time series, correlation coefficients, and institutional holdings for a specific ticker
- `POST /api/v1/correlation/recalculate` — flush cache and bulk-sync Tri-Factor synergy metrics into SQLite cache
- `GET /dashboard` — serve interactive dashboard HTML
- `GET /api/v1/dashboard/overview` — dataset summary + refresh status + watchlist + universe files
- `GET /api/v1/dashboard/results` — upcoming earnings with market context
- `GET /api/v1/dashboard/swing` — swing setups with support/resistance and enriched swing range
- `GET /api/v1/swing-range?watchlist=&ticker=` — current swing range and cycle history for a ticker
- `POST /api/v1/swing-range` — set user override for swing range (support, resistance, cycles)
- `DELETE /api/v1/swing-range?watchlist=&ticker=` — clear user override (reverts to auto)
- `GET /api/v1/swing-range/history?watchlist=&ticker=` — cycle timing history ("time each time")
- `GET /api/v1/swing-range/list?watchlist=` — list all stored swing ranges for a watchlist
- `GET /api/v1/dashboard/kronos` — Kronos predictions
- `POST /api/v1/dashboard/kronos/run` — run Kronos predictions on-demand
- `GET /api/v1/dashboard/kronos/latest?tickers=` — latest prediction per ticker
- `GET /api/v1/dashboard/kronos/audit?tickers=&limit=` — full prediction history
- `POST /api/v1/dashboard/refresh` — refresh prices/earnings/market caps
- `GET /api/v1/dashboard/refresh-status` — last-refresh timestamps
- `GET /api/v1/dashboard/data-coverage?market=` — per-ticker price/earnings coverage for a universe (Data Coverage tab)
- `POST /api/v1/dashboard/earnings/incremental` — fetch earnings only for tickers missing them (body `{"market"|"tickers"}`)
- `GET /api/v1/watchlist` — get watchlist from `my_watchlist.txt`
- `POST /api/v1/watchlist/add` — add ticker to watchlist
- `POST /api/v1/watchlist/remove` — remove ticker from watchlist
- `GET /api/v1/playground/endpoints` — raw API endpoint catalog for the Playground API console
- `GET /api/v1/playground/search?q=` — symbol autocomplete across NSE_ALL + US (live nsetools refresh + typed-symbol fallback)
- `GET /api/v1/playground/ticker/{ticker}` — raw yfinance snapshot (fast_info/.info, price, market cap, earnings dates)
- `GET /api/v1/playground/ticker/{ticker}/history?period=&interval=` — raw yfinance OHLCV history (capped 120 rows)
- `GET /api/v1/playground/nse?force_refresh=` — NSE universe sizes + samples
- `GET /api/v1/playground/nse/result-calendar?from_date=&to_date=` — raw NSE result-calendar payload (companies + result dates) from nseindia.com
- `GET /api/v1/playground/nse/event-calendar?from_date=&to_date=` — raw NSE event-calendar payload (board meetings, results, dividends) from nseindia.com
- `GET /api/v1/playground/nse/financial-calendar/{symbol}?from_date=&to_date=` — normalized NSE result dates for one symbol (raw payload kept separate)
- `POST /api/v1/audit/log` — log daily news/catalyst stock prediction (body: `ticker`, `strategy_name`, `signal`, `entry_price`, `horizon`, `headline`)
- `POST /api/v1/audit/log/bulk` — bulk-log predictions array
- `POST /api/v1/audit/run` — execute automated evaluation of pending predictions against actual prices
- `GET /api/v1/audit/metrics?strategy=` — retrieve performance scorecard (Win Rate %, Profit Factor, Sharpe Ratio, Brier Score, etc.)
- `GET /api/v1/audit/history?strategy=&ticker=&status=&limit=&offset=` — paginated audit ledger
- `GET /api/v1/audit/strategies` — list all strategies with prediction counts
- `POST /api/v1/audit/import-kronos` — import historical Kronos forecasts and audit outcomes
- `POST /api/v1/audit/backtest` — execute 1-year multi-strategy backtest simulation (body: `{"strategy", "days", "universe"}`)
- `POST /api/v1/backtest/run` — unified multi-strategy backtest engine dispatcher (`strategy`: `swing`, `kronos`, `earnings`, `news`, `auditor_all`; returns standardized KPIs, equity curve, and trade log)
- `POST /api/v1/backtest/swing/run` — dedicated swing channel backtest simulation
- `GET /api/v1/dashboard/results/report?days=&past_days=&market=` — report-style HTML fragments (day sections, legend, popups, `months` summary array, `day_sections_meta`) for Results tab (defaults to ±2 months / 60D past & 60D future with 4-month interactive pill tabs)
- `GET /api/v1/gainers/top?market=` — top daily market gainers with volume surge multiples & drivers (supports Indian and US markets)
- `GET /api/v1/gainers/patterns` — recurring 52W / breakout pattern matrix
- `GET /api/v1/scanner/categories?universe=` — active category scanner hub counts and metadata
- `GET /api/v1/scanner/category/{category_id}?universe=&limit=` — candidates matching specific category setups
- `POST /api/v1/dashboard/predict/run` — on-demand Kronos AI forecast for individual ticker or batch

Root endpoint lists: `universe_create`, `kronos_predictions`, `kronos_run`, `kronos_latest`, `kronos_audit`, `audit_strategy`, `backtest_run`.

## `api/routers/` (Modular REST Handlers)
FastAPI routes are organized into modular router files under `earnings_engine/api/routers/`:
- `stocks.py`: Stock overview, decoupled micro-APIs, valuation, and notes (`/api/v1/stock/...`)
- `consensus.py`: Multi-model AI consensus execution, model selector, and trace inspection (`/api/v1/consensus/...`)
- `institutional.py`: Institutional accumulation scores, flow deltas, and fund portfolio catalog (`/api/v1/institutional/...`)
- `breakout.py`: 5-strategy Breakout Radar, tracked signal history, and outcome auditing (`/api/v1/breakout/...`)
- `news.py`: News harvesting, catalyst analysis, and structured extraction (`/api/v1/news/...`)
- `premarket.py`: Pre-market gap scanner, overnight news, and session outcomes (`/api/v1/premarket/...`)
- `system.py`: Sub-millisecond sidebar badge counters, health status, and schedule controls
- `trading_agents.py`: Autonomous financial multi-agent workflows
- `tri_confluence.py`: Tri-Factor Synergy & Institutional-Earnings-Returns cross-correlation analytics (`/api/v1/correlation/...`)
- `cards.py`, `wealth.py`, `trips.py`, `zepto.py`, `auth.py`: Scoped application hubs and RBAC session control

## `api/dashboard_api.py`
**Purpose:** Data aggregation for the interactive dashboard tabs.

**Functions:**
- `mark_refreshed(source, rows, status, message)` — record refresh timestamp
- `get_refresh_status()` — get all refresh timestamps
- `get_upcoming_results(days, market)` — upcoming earnings + market context
- `get_event_dataset_summary()` — SQLite `event_dataset` stats (rows, tickers, up-rate, date range)
- `get_swing_setups(market, limit)` — support/resistance + momentum + swing signals
- `get_kronos_predictions(tickers, lookback, pred_len)` — Kronos AI predictions, **persists each forecast via `store_prediction()`** (payload = forecast dict + lookback/pred_len; ticker key = `symbol` or `ticker`)
- `get_kronos_predictions_audit(tickers, limit)` — full history from `data/predictions.py`
- `get_kronos_latest_predictions(tickers)` — latest per ticker from `data/predictions.py`
- `create_universe_file(name, tickers)` — sanitizes name to `[A-Za-z0-9_-]`, writes to `data/universes/{name}.txt`, returns success/name/file/tickers/path
- `get_watchlist()` / `add_to_watchlist(ticker)` / `remove_from_watchlist(ticker)` — server-side watchlist CRUD via `my_watchlist.txt`
- `get_universe_files()` — list NSE universe files with metadata
- `refresh_data(market, tickers, force)` — refresh prices/earnings/market caps
- `get_data_coverage(market)` — per-ticker price/earnings coverage for a universe (Data Coverage tab)
- `ingest_earnings_incremental_api(market, tickers)` — fetch earnings for tickers missing them, in batches

**Data sources:**
- SQLite `prices.sqlite3` (event_dataset, price_history, earnings_history, ticker_market_cap, kronos_predictions)
- NSE universe files (`nse_top.txt`, `us_top.txt`, `nse_all.txt`, `nse_large_cap.txt`, `my_watchlist.txt`)
- Kronos predictor (`kronos_predictor.py`)
- Market context enrichment (`market_context.py`)

## `kronos_predictor.py`
- `predict_portfolio(...)` — Kronos AI predictions (support/resistance, return_pct, trend, explanation)