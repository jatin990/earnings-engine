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
- `GET /dashboard` — serve interactive dashboard HTML
- `GET /api/v1/dashboard/overview` — dataset summary + refresh status + watchlist + universe files
- `GET /api/v1/dashboard/results` — upcoming earnings with market context
- `GET /api/v1/dashboard/swing` — swing setups with support/resistance
- `GET /api/v1/dashboard/kronos` — Kronos predictions
- `POST /api/v1/dashboard/kronos/run` — run Kronos predictions on-demand
- `GET /api/v1/dashboard/kronos/latest?tickers=` — latest prediction per ticker
- `GET /api/v1/dashboard/kronos/audit?tickers=&limit=` — full prediction history
- `POST /api/v1/dashboard/refresh` — refresh prices/earnings/market caps
- `GET /api/v1/dashboard/refresh-status` — last-refresh timestamps
- `GET /api/v1/watchlist` — get watchlist from `my_watchlist.txt`
- `POST /api/v1/watchlist/add` — add ticker to watchlist
- `POST /api/v1/watchlist/remove` — remove ticker from watchlist

Root endpoint lists: `universe_create`, `kronos_predictions`, `kronos_run`, `kronos_latest`, `kronos_audit`.

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

**Data sources:**
- SQLite `prices.sqlite3` (event_dataset, price_history, earnings_history, ticker_market_cap, kronos_predictions)
- NSE universe files (`nse_top.txt`, `us_top.txt`, `nse_all.txt`, `nse_large_cap.txt`, `my_watchlist.txt`)
- Kronos predictor (`kronos_predictor.py`)
- Market context enrichment (`market_context.py`)

## `kronos_predictor.py`
- `predict_portfolio(...)` — Kronos AI predictions (support/resistance, return_pct, trend, explanation)