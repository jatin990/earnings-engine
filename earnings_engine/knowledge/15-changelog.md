# 15 — Recent Changes Log

> Related: [14-modification-points](14-modification-points.md) → [00-index](00-index.md)

## 2026-08-03 (prediction history + watchlist fixes)
- Enhanced Prediction History modal (`showKronosHistory()` in `reports/templates/dashboard.html`) — added "Price at Prediction" column showing the stored price from when the prediction was made, plus "Current Price" column fetching live market data, and "Δ %" column showing percentage change between prediction price and current price.
- Fixed watchlist universe dropdown — added `populateUniverseDropdown()` function that fetches available universe files from `/api/v1/universe/files` and populates the `watchlistUniverseSelect` dropdown on init.
- Fixed `loadWatchlistPredictions()` to use the selected universe file (fetches tickers from `/api/v1/universe/{universe}`) instead of always using the hardcoded watchlist.
- Added `populateUniverseDropdown()` call to `app.init()` in dashboard.html.
- Confirmed completion of all 8 major enhancement tasks from the project plan.

## 2026-08-03 (dashboard enhancements - swing/kronos/delete/last-quarter)
- Added `DELETE /api/v1/dashboard/kronos/audit/{ticker}/{run_at}` endpoint for deleting predictions from audit trail. Backed by `delete_kronos_prediction()` in `api/dashboard_api.py` and `delete_prediction()` in `data/predictions.py`.
- Added delete button (🗑️) in Kronos Audit tab table for each prediction row.
- Added `GET /api/v1/dashboard/kronos/history/{ticker}` endpoint for fetching all historical predictions for a specific ticker. Backed by `get_kronos_predictions_for_ticker()` in `api/dashboard_api.py`.
- Added click-to-view-history feature in Kronos Latest tab: clicking any prediction card opens a modal showing all historical predictions for that ticker with live price deltas.
- Added "List" sub-tab in Kronos tab showing all latest predictions in table format.
- Enhanced Swing tab: added Next Earnings date, Kronos 14D Return %, Kronos Trend, and Kronos explanation text to each swing card. Swing cards now pull Kronos prediction data from the audit trail.
- Removed 3Q earnings score (`prev_3q_earnings_score`, `q1_earnings_score`, `q2_earnings_score`, `q3_earnings_score`) from `enrich_upcoming_results()` in `market_context.py`. Now only computes last quarter score (`prev_quarter_earnings_score`) and last quarter week high/low (`last_week_high_pct`, `last_week_low_pct`, `last_week_high_price`, `last_week_low_price`).
- Updated `test_enrich_upcoming_results_adds_individual_quarter_scores_and_week_hl` → renamed to `test_enrich_upcoming_results_adds_last_quarter_score_and_week_hl` to test last quarter only.
- Fixed dropdown styling: added CSS `select { background-color: #1e293b !important; color: var(--light) !important; }` to make dropdowns dark-themed.
- Added loading spinners for API calls: `loadResults()`, `loadSwing()`, `runKronos()`, `refreshData()`, `summarizeResults()` now show spinner animations during fetches.
- Moved `tests/test_kronos_integration.py` to `tests/manual/` folder so it doesn't run in the default test suite (takes too long due to live Kronos predictions). Run manually with `python -m pytest tests/manual/ -v`.
- All 69 tests pass (excluding manual tests).

## 2026-08-03 (dashboard results / universe selector fix)
- Added 7-day return calculation (`seven_day_return_pct`) in `data/market_context.py` after line 186, included in `metrics_payload` dict and both `rows.append({...})` dicts (lines ~302-339 and ~343-380).
- Kronos predictions now merge into Results tab via `get_upcoming_results()` in `api/dashboard_api.py` (lines 102-160). Each result row includes `kronos_prediction` object (return_pct, support, resistance, trend, confidence, run_at).
- Added LLM summarization endpoint `POST /api/v1/dashboard/results/summarize` in `api/server.py` (lines 746-766) backed by `summarize_results_with_llm()` in `api/dashboard_api.py` (lines 369-414). Uses Ollama `llama3.2:3b` at `http://localhost:11434/api/generate` (configurable via `OLLAMA_HOST` and `OLLAMA_MODEL` env vars).
- Added tab refresh status tracking via `get_tab_refresh_status()` in `api/dashboard_api.py` (lines 359-366) and `GET /api/v1/dashboard/tab-refresh-status` endpoint in `api/server.py` (lines 740-743). Returns per-tab (results, swing, kronos, watchlist) last-refresh metadata.
- Enhanced `dashboard.html` Results tab with new columns: `7D Ret` and `Kronos Trend`. Updated table colspan from 8 to 10 to match new columns.
- Added action buttons to Results tab: `✨ LLM Summary` (calls `/api/v1/dashboard/results/summarize`) and `🔄 Refresh Results` (calls `app.refreshResults()`).
- Added individual tab refresh functions in dashboard.html: `refreshResults()`, `refreshKronos()`, `refreshWatchlist()`, and `summarizeResults()`.
- Updated `renderResultsWidgets()` and `renderResultsTable()` in dashboard.html to display new `seven_day_return_pct` and `kronos_prediction` data with color coding (green for positive, red for negative).
- Fixed `GET /api/v1/universe/files` returning 400 — moved the static `/files` route **before** the dynamic `/api/v1/universe/{market}` route in `api/server.py` (FastAPI matches in registration order; the dynamic route was shadowing the static one).
- Added `generate_watchlist_kronos()` to `api/dashboard_api.py` — generates Kronos predictions for watchlist tickers with multithreaded batch processing (4 workers via `ThreadPoolExecutor`). Persists all forecasts to audit trail. Accepts `tickers` list (optional, defaults to watchlist), `lookback` (default 120), and `pred_len` (default 14).
- Registered `POST /api/v1/dashboard/watchlist/kronos` endpoint in `api/server.py` for watchlist-based Kronos generation.
- Enhanced Watchlist tab in `dashboard.html` with Kronos integration: shows prediction status table with columns (Ticker, Prediction Date, 14D Return %, Trend, Action), "Generate" button for tickers without predictions, "Regenerate" button for existing predictions, "Generate All" button for batch generation, and "Refresh" button. Implements `loadWatchlistPredictions()`, `generateForTicker()`, and `generateForWatchlist()` JavaScript functions.
- Added 8 new integration tests in `tests/test_kronos_integration.py` covering watchlist-based prediction generation, batch generation, empty watchlist handling, prediction persistence, regeneration, and status tracking.
- Added `_resolve_tickers(market)` helper in `api/dashboard_api.py`. The Results, Swing, and Refresh endpoints now default to `load_all()` (IN+US) when no market is selected, matching the CLI `upcoming-results` default — previously the dashboard defaulted to watchlist-only, showing far fewer results than the CLI report.
- `_resolve_tickers` supports `ALL`, `WATCHLIST`, `IN`/`US`/`NSE_ALL`/`NSE_LARGE_CAP`, and user-created universe file names (so created watchlists are selectable and usable).
- Added universe selector dropdowns to the dashboard Results, Swing, and Refresh controls (`resultsMarket`, `swingMarket`, `refreshMarket`) with options: All Markets, My Watchlist, NSE Top, US Top, NSE Large Cap, NSE All (All Markets is the default).
- `loadResults()` and `loadSwing()` JS now read the selected universe and pass `&market=` to the API.
- `loadUniverseFiles()` now populates user-created universe/watchlist files into the Results & Swing selectors (in addition to the file table), so a newly-created watchlist can be selected as the active universe.
- Verified: dashboard default Results count now matches the CLI `upcoming_earnings(load_all())` count exactly (consistency). To see more upcoming results, run `earnings-engine ingest` to refresh the cache (e.g. cache currently has earnings for 29/89 tickers).

## 2026-08-02 (Kronos audit + dashboard features)
- Added `data/predictions.py` — Kronos prediction persistence + audit layer. New SQLite table `kronos_predictions` (id, ticker, run_at, predicted_at, lookback, pred_len, prediction_json, current_price, support, resistance, return_pct, trend, explanation) with index `idx_kronos_pred_ticker_run`. Functions: `store_prediction()`, `load_prediction_history()`, `load_latest_predictions()`.
- Added 7 tests in `tests/test_kronos_audit.py` covering store/load history/latest predictions for the Kronos audit layer.
- `get_kronos_predictions()` in `api/dashboard_api.py` now persists each forecast via `store_prediction()` (payload = forecast dict + lookback/pred_len; ticker key = `symbol` or `ticker`).
- Added `get_kronos_predictions_audit(tickers, limit)` and `get_kronos_latest_predictions(tickers)` to `api/dashboard_api.py` backed by `data/predictions.py`.
- Added `create_universe_file(name, tickers)` to `api/dashboard_api.py` — sanitizes name to `[A-Za-z0-9_-]`, writes to `data/universes/{name}.txt`, returns success/name/file/tickers/path.
- Added API endpoints to `api/server.py`: `POST /api/v1/universe/create` (body `{"file","tickers"}`), `GET /api/v1/dashboard/kronos/latest?tickers=`, `GET /api/v1/dashboard/kronos/audit?tickers=&limit=`. Root endpoint lists `universe_create`, `kronos_predictions`, `kronos_run`, `kronos_latest`, `kronos_audit`.
- `dashboard.html` Kronos tab now has Latest/Audit sub-tabs. Latest shows the most recent prediction per ticker; Audit shows full history (default limit 200) with sortable columns (ticker, run_at, return_pct) and live price delta (Δ ₹ and Δ %) fetched from `/api/v1/market-context/{ticker}` (null/NaN shown as "—").
- `dashboard.html` Watchlist tab now has a "New Watchlist" input + create button calling `POST /api/v1/universe/create` then reloading universe files.
- `dashboard.html` Results tab now shows the result count in the header: `(N in next D days)`.
- Fixed duplicate rows in Results tab — `upcoming_earnings()` in `data/earnings.py` now deduplicates by `(ticker, earnings_date)` via `drop_duplicates(keep="first")` before sorting.
- Added regression test `test_upcoming_earnings_no_duplicates` in `tests/test_caching.py` — fetches "DUP" and asserts `upcoming_earnings(["DUP","DUP","DUP"])` returns exactly 1 row.
- Confirmed the Results date filter is the `days` look-ahead window (default 14) surfaced via the `(N in next D days)` count in the UI header.

## 2026-08-02 (dashboard API)
- Added `api/dashboard_api.py` — dashboard data aggregation module for results, swing, kronos, watchlist, and refresh status.
- Added dashboard endpoints to `api/server.py` — overview, results, swing, kronos/run, refresh, refresh-status, watchlist CRUD.
- Rewrote `dashboard.html` with tab-based navigation (Results, Swing, Kronos, Watchlist) backed by SQLite and NSE universe files.
- Added server-side watchlist persistence via `my_watchlist.txt` (GET/ADD/REMOVE endpoints).
- Added refresh status tracking with per-source timestamps (prices, earnings, market_caps, results, swing, kronos, watchlist).
- Added 7 new dashboard API tests in `test_api.py` (overview, results, swing, refresh-status, watchlist CRUD, dashboard endpoint).
- Updated `test_render_dashboard` in `tests/test_predict.py` to verify tab-based layout and dashboard endpoints.
- Updated `API_README.md` with dashboard data endpoint documentation.

## 2026-08-01 (earlier)
- Fixed `ValueError` in `render.py` for string percent values (`'4.2%'`) — added `_to_float()` helper
- Reduced log spam: removed per-ticker logs from `load_earnings()` and `load_prices()`, added summary logs
- Fixed CLI `upcoming-results` log to show ticker count instead of full list
- Fixed HTML overflow: added `table-layout: fixed`, `overflow-wrap`, `min-width: 0`, responsive grid
- Added 52W low price in brackets to gap display (e.g. `-12.5% (120)`)
- Added `+`/`-` signs to all percent displays
- Segregated earnings week move into high/low: `earnings_week_high_pct`, `earnings_week_low_pct`
- Added Quality Rating explanation section in report cards
- Extracted HTML templates from `render.py` into `reports/templates/*.html` files
- Fixed double-formatting bug in `cli.py` — the enriched DataFrame was being formatted to display strings, then passed to `render_upcoming_results_report()` which formatted again. Now cli.py passes raw numeric data to the renderer and uses a separate `display` copy for the CLI table.
- Fixed market cap `Cr` conversion in `render.py` — was dividing by 1000 (`k Cr`), now divides by 1e7 correctly (`213,861.5 Cr`)
- Fixed quality score formatting in `render.py` — added `/9` suffix via `_fmt(..., suffix="/9")`
- Fixed signed zero display — `+0.00%` now shows `+` for zero values when `signed=True`
- Added regression test `test_upcoming_results_formats_market_cap_quality_and_52w_gaps` in `tests/test_predict.py`
- Fixed quality score logic in `market_context.py` — 3Q score now averages individual quarter scores (via `_score_surprise()`) instead of scoring the average surprise. This ensures 3Q can never exceed the max individual quarter score.
- Fixed table word wrap in `earnings_report_page.html` — table cells now use `white-space: nowrap` so the ledger scrolls horizontally instead of wrapping text
- Added regression test `test_quality_score_3q_is_average_of_individual_quarters` in `tests/test_predict.py`
- Added individual quarter scores (`q1_earnings_score`, `q2_earnings_score`, `q3_earnings_score`) to `enrich_upcoming_results()` output — each quarter scored individually via `_score_surprise()`
- Changed `earnings_week_high_pct`/`earnings_week_low_pct` to compute from the previous 3 quarters' earnings dates (±4 business days) via new `_week_high_low_around()` helper, instead of the last 5 trading days
- Updated card template to display Q1/Q2/Q3 individual scores
- Added regression test `test_enrich_upcoming_results_adds_individual_quarter_scores_and_week_hl` in `tests/test_predict.py`
- Updated `test_enrich_upcoming_results_computes_momentum_and_support_levels` expected 3Q score from 6 to 7 (corrected arithmetic: [12,8,-3] → [8,7,5] → avg 6.67 → 7)
- Collapsed CLI display columns — 52W gaps and quality scores now shown as combined `52w_gap` and `quality` columns instead of separate columns
- Added per-quarter week high/low columns (`q1_week_high_pct`, `q1_week_low_pct`, `q1_week_high_price`, `q1_week_low_price`, etc.) to `enrich_upcoming_results()` output
- Redesigned `card.html` template with 4 big sections: Stock & Price Info, Quarterly Metrics (Result Week ±4 Days), Quality Scores, Setup & Risk/Reward
- Updated `earnings_report_page.html` ledger table to 13 columns with per-quarter week high/low (Q1, Q2, Q3), separate 3Q Avg column, and `Quality<br>(t-Q1/t-Q2/t-Q3)` header
- Changed week high/low and 52W high/low display format to 2-line: percentages on line 1 (e.g., `+8.7%/+0.0%`), prices on line 2 (e.g., `(8,500/7,800)`)
- Added `_fmt_pct_only()` and `_fmt_hl_pair()` helpers in `render.py`, replaced `_fmt_pct_with_price()` with `_fmt_hl_pair()` for 2-line high/low formatting
- Fixed zero value formatting — `0.0%` no longer shows `+` sign (changed `value >= 0` to `value > 0` for `+` prefix in `_fmt()`)
- Quality scores in ledger table now show as `6/9 | 7/9 | 6/9` (just scores, no `t-Q1:` prefix)
- Fixed ledger table overflow — cells now use `white-space: normal` and `word-wrap: break-word` to prevent content cutoff
- Updated `result_row.html` template to use `{pct_from_52w_high_low}` placeholder (combined high/low) instead of separate `{pct_from_52w_high}/{pct_from_52w_low}`
- Updated `card.html` template to use `{pct_from_52w_high_low}` placeholder for 52W High/Low metric
- Added `NSE_ALL` market option to all CLI commands — fetches all NSE stocks via nsetools library
- Added `load_nse_all()` function to `universe.py` — fetches all NSE stock codes from nsetools, caches to `nse_all.txt`, refreshes if older than 7 days
- Added nsetools dependency (`nsetools>=2.0`) for fetching all NSE stock codes
- Added 5 new tests in `tests/test_universe.py` for NSE_ALL feature
- Migrated earnings cache from Parquet to SQLite — now stored in shared `prices.sqlite3` database, table `earnings_history`. Added `earnings_freshness` table for tracking fetch timestamps. Old `.parquet` files auto-migrated on first access.
- Migrated dataset cache from Parquet to SQLite — now stored in shared `prices.sqlite3` database, table `event_dataset`. Old `dataset.parquet` auto-migrated on first access.
- Added `NSE_LARGE_CAP` market option to all CLI commands — fetches NSE stocks with market cap > 1000cr via yfinance `fast_info`
- Added `load_nse_large_cap()` function to `universe.py` — fetches market cap for all NSE_ALL tickers, filters to > 1000cr, caches to `nse_large_cap.txt`, refreshes if older than 7 days
- Added 5 new tests in `tests/test_universe.py` for NSE_LARGE_CAP feature
- Added market cap caching to shared SQLite database — new `ticker_market_cap` table with ticker-level freshness check (1 day). Functions: `store_market_cap()`, `load_market_cap()`, `is_market_cap_fresh()`, `load_all_market_caps()`, `ingest_market_caps()`.
- Updated `market_context.py` `enrich_upcoming_results()` to check SQLite market cap cache before fetching from yfinance. Stores fetched market cap in cache.
- Updated `cli.py` `ingest` command to also fetch and cache market cap for all tickers (with ticker-level freshness check, skips fresh entries).
- Added 5 new tests in `tests/test_universe.py` for market cap caching
- Made `ingest_earnings()` multithreaded — 10 parallel workers, batched in groups of 50, 2s delay between batches, skips tickers with fresh cache. Added `_fetch_earnings_for_ticker()` helper.
- Made `ingest_prices()` multithreaded — 10 parallel workers, batched in groups of 50, 2s delay between batches, skips tickers with fresh cache. Added `_fetch_prices_for_ticker()` helper.
- Fixed `UNIQUE constraint failed` error in `_write_earnings()` — added `drop_duplicates(subset=["earnings_date"])` before insert and changed to `INSERT OR REPLACE` to handle duplicate earnings dates from yfinance.
- Added EPS estimate, EPS reported, and surprise % to individual stock card in `card.html` template — displayed in the "Stock & Price Info" section.
- Added `eps_estimate`, `eps_reported`, `surprise_pct` columns to `enrich_upcoming_results()` output — extracted from the most recent earnings event.
- Updated `render.py` to format and pass EPS data to card template.