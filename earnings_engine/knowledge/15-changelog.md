# 15 — Recent Changes Log

> Related: [14-modification-points](14-modification-points.md) → [00-index](00-index.md)

## 2026-08-22 (Multi-Strategy Backtest Engine, Results ±2M Window, Popups & UI Enhancements)
- **Multi-Strategy Backtest Engine** (`backtest/swing_backtest.py`, `data/strategy_auditor.py`, `api/server.py`):
  - Unified `/api/v1/backtest/run` dispatcher supporting individual strategy simulations:
    1. 🎯 **Swing Channel**: 20-day S/R channel support bounce, volume surge mult, and stop-loss buffer.
    2. 🔮 **Kronos AI Time-Series**: 14-day Transformer forecast horizon backtesting.
    3. ⚡ **Earnings & Results Reaction**: Post-earnings announcement drift and pre-event momentum.
    4. 📰 **News & Catalyst Momentum**: High-impact news catalyst breakouts.
    5. 🏆 **Multi-Strategy Benchmark (All)**: Unified cross-strategy performance comparison matrix.
  - Added strategy selector dropdown `#btStrategy` in Backtest tab (`_backtest.html`) with dynamic KPIs, trade logs, and equity curves.
  - Fixed `load_universe_from_file(name_or_path, settings)` in `data/universe.py` to handle both settings and database/text watchlists cleanly.
- **Results Tab Enhancements, ±2 Months Window & 4-Month Sub-Tabs Breakdown** (`_results.html`, `dashboard_api.py`, `render.py`, `server.py`, `dashboard.js`):
  - Results tab no longer auto-loads by default on page open; presents a clean call-to-action empty state.
  - Added range presets selector defaulting to **`⚡ ±2 Months (Past 60D & Next 60D)`** along with ±1 Month, Upcoming 14/30/60D, Past 60D, and Custom range.
  - Updated backend `get_upcoming_results` and `get_results_report_components` (`render.py`) to query `[-past_days, +days]` window (120 days total) and compute `months` array + `day_sections_meta`.
  - **4-Month Sub-Tabs**: Added interactive pill buttons above report sections showing count badges across the ±2 months window (e.g. `🌐 All (±2M) (44)`, `◀ Jul 2026 (35)`, `⭐ Aug 2026 (8)`, `▶ Sep 2026 (1)`).
  - **Dynamic Month Filtering**: Clicking any month tab instantly filters the day sections, updates pagination, and updates the header badge (e.g. `35 results across 15 dates in Jul 2026`).
  - Fixed ticker extraction in `_resolve_tickers` so dictionary items from SQLite watchlists are properly unwrapped into strings.
- **Results Popups & Stock Modal Fix** (`dashboard.js`, `_head.html`):
  - Implemented `window.openPopup(ticker)` and `window.closePopups()` in `dashboard.js` with keyboard `Escape` shortcut support.
  - Elevated `.popup-modal` `z-index` to `3000` with glassmorphic backdrop blur to guarantee popups render over sticky table headers.
- **On-Demand Single Ticker Predictions** (`dashboard.js`, `dashboard_api.py`):
  - Implemented `app.runPredictionForTickerSingle(ticker)` to power on-demand `🔮 Predict` buttons in Scanner, Gainers, and Results tables.
  - Automatically loads GPU forecast and launches the 14-Day OHLCV Realized vs Forecast Benchmark Modal.
- **Top Gainers & Patterns Market Selector**:
  - Added Market Selector (`gainersMarketSelect`) to toggle between Indian (`₹`) and US (`$`) universes with live currency formatting.
- **Broker Integrations & Indian Data Providers**:
  - Direct NSE Bhavcopy archives via `jugaad-data` / `nselib`.
  - Max Pain & PCR option chain analytics in `data/providers.py`.
  - Zerodha KiteConnect, Angel One SmartAPI, DhanHQ, and Fyers broker adapters with TOTP automation (`brokers/totp.py`).

## 2026-08-22 (Multi-Strategy Prediction Auditor & 1-Year Backtest Engine)
- **Strategy Auditor Core Engine** (`data/strategy_auditor.py`):
  - Created SQLite tables `strategy_predictions` and `strategy_audit_logs` in `prices.sqlite3` with indexed lookup on `(ticker, strategy_name, created_at)`.
  - Implemented `log_prediction()`, `log_predictions_bulk()`, `audit_predictions()`, and `calculate_strategy_metrics()`.
  - Computes comprehensive performance metrics: Win Rate %, Profit Factor, Sharpe Ratio (annualized), Sortino Ratio (downside deviation), Brier Score (probability calibration), Directional Precision (Bullish vs Bearish), and market breakdown.
- **Historical Ingestion & 1-Year Multi-Strategy Backtesting**:
  - `import_kronos_predictions()`: imports historical Kronos forecasts from `kronos_predictions` into `strategy_predictions` under strategy `'Kronos_AI'`, automatically evaluating past predictions against historical closing prices.
  - `backtest_strategy_history()`: runs 1-year historical simulation across core strategies (`Kronos_1Y_Backtest`, `News_Momentum_Breakout`, `Earnings_Drift_GBM`, `Mean_Reversion_52W`, and `ALL`), logging decisions and auditing outcomes.
- **CLI Commands (`cli.py`)**:
  - `earnings-engine audit-strategy log` — log predictions (single or bulk from JSON)
  - `earnings-engine audit-strategy run` — execute on-demand outcome auditing
  - `earnings-engine audit-strategy metrics` — terminal scorecard with formatted strategy and market breakdowns
  - `earnings-engine audit-strategy import-kronos` — import existing Kronos predictions
  - `earnings-engine audit-strategy backtest` — run 1-year multi-strategy backtest
- **REST Endpoints (`api/server.py`)**:
  - `POST /api/v1/audit/log`, `POST /api/v1/audit/log/bulk`, `POST /api/v1/audit/run`, `GET /api/v1/audit/metrics`, `GET /api/v1/audit/history`, `GET /api/v1/audit/strategies`, `DELETE /api/v1/audit/prediction/{id}`, `POST /api/v1/audit/import-kronos`, `POST /api/v1/audit/backtest`.
- **Dashboard UI (`ui/index.html` + `ui/js/strategy_auditor.js`)**:
  - Added Strategy Auditor tab with 5-metric performance scorecard, quick-add prediction form, strategy breakdown table, and audit ledger with pagination.
  - Added "Import Kronos" and "1Y Backtest" action buttons.
- **Tests (`tests/test_strategy_auditor.py`)**: 33 unit tests covering schema creation, prediction logging, outcome evaluation, metric calculations, Kronos import, and backtesting.

## 2026-08-15 (100% SQLite Universe Storage Migration)
- **Migrated Universe Storage to SQLite** (`data/universe.py` + `api/server.py`):
  - Replaced text-file caching (`nse_all.txt`, `nse_large_cap.txt`, `nse_top.txt`, `us_top.txt`) with shared SQLite tables `universes` and `universe_freshness` in `prices.sqlite3`.
  - Automatic seed & migration on startup for `IN`, `US`, and any legacy universes.
  - Added SQLite CRUD functions: `store_universe()`, `get_universe()`, `add_to_universe()`, `remove_from_universe()`, `list_universes()`, `is_universe_fresh()`.
  - `load_universe()`, `load_nse_all()`, `load_nse_large_cap()`, and `load_all()` now read directly from SQLite without filesystem file locks or text parses.
  - Updated API endpoints in `api/server.py` (`GET /api/v1/universe/files`, `GET /api/v1/universe/{market}`, `POST /api/v1/universe/add`, `POST /api/v1/universe/remove`) to use SQLite directly.
  - Updated tests in `tests/test_universe.py`.

## 2026-08-15 (Custom Swing Ranges across Watchlist and Swing tabs)
- **Custom Swing Ranges & Cycle History** (`data/swing_ranges.py` + `data/market_context.py`): added SQLite tables `swing_ranges` and `swing_cycle_history` keyed by `(watchlist, ticker)`.
- **Auto Detection & User Overrides**: auto-detection calculates horizontal support (min close) / resistance (max close) over a 20-day window, counts low→high→low oscillation cycles, and measures each cycle's duration in days ("time each time"). User overrides (`source='user'`) are protected and take precedence over auto-detection.
- **Enriched Swing Setups & APIs** (`api/dashboard_api.py` + `api/server.py`):
  - `GET /api/v1/swing-range?watchlist=&ticker=` — returns current range, source (`auto` | `user`), and cycle history.
  - `POST /api/v1/swing-range` — saves user override.
  - `DELETE /api/v1/swing-range?watchlist=&ticker=` — resets to auto-detection.
  - `GET /api/v1/swing-range/history?watchlist=&ticker=` — returns detected cycle history and timing.
  - `GET /api/v1/swing-range/list?watchlist=` — returns all ranges in a watchlist.
  - `get_swing_setups(market=...)` now enriches cards with `swing_range` and updates `current_support` / `next_resistance` when overridden.
- **UI Integration** (`ui/js/dashboard.js` + `_body_footer.html`):
  - Swing cards display swing range metrics (`₹Support – ₹Resistance · N cyc · ~Xd avg`), `[Auto]` / `[Custom]` badge, and `✎ Range` button.
  - Watchlist chips display range badges and a `⚙` button opening the range editor.
  - Added `#swingRangeModal` for viewing cycle timing ("time each time"), editing bounds/cycles, saving custom ranges, and resetting to auto.
- New tests: `tests/test_swing_ranges.py` (CRUD, auto protection, cycle history, dashboard API helpers, `get_swing_setups` integration, FastAPI endpoints).

## 2026-08-14 (Custom watchlist name casing fix in Swing tab)
- **Bug fix (`api/dashboard_api.py`)**: `_resolve_tickers()` uppercased the `market` parameter before looking it up as a DB watchlist name, causing custom-named watchlists (e.g. "My Picks", "tech_watch") to return empty when used in the Swing tab's "Load Setups" button. The function now tries the **original casing** first (`get_watchlist(market, ...)`) and falls back to uppercase (`get_watchlist(mu, ...)`) for legacy universe-file compatibility.
- **Windows path fix**: The file-fallback path also used `Path !=` comparison (`f_mu != f`) which is **case-insensitive on Windows**, so the uppercase file was never reached. Replaced with a `mu != market` string comparison instead.
- New tests: `test_resolve_tickers_preserves_original_casing_for_db_watchlist`, `test_resolve_tickers_falls_back_to_uppercase_casing` — 166 passed.

## 2026-08-06 (Data Coverage dashboard tab + incremental earnings fetch)
- **Data Coverage tab** (`reports/templates/dashboard.html` + `api/server.py` + `api/dashboard_api.py`): new dashboard tab showing per-ticker price/earnings date ranges, row counts, listing date, and earnings freshness for any universe (ALL, WATCHLIST, IN, US, NSE_LARGE_CAP, NSE_ALL). Backed by `GET /api/v1/dashboard/data-coverage?market=` → `get_data_coverage(market)` → `data/coverage.py:get_data_coverage(tickers)` (single SQL query over `price_history`/`earnings_history`/`earnings_freshness`). Includes a ticker filter and a 🔄 Refresh button.
- **Incremental earnings fetch**: `data/earnings.py:ingest_earnings_incremental()` fetches earnings only for tickers missing earnings rows (skips no-price-history and <90-day-old listings). Wired to the dashboard's "⚡ Fetch Missing Earnings" button (`POST /api/v1/dashboard/earnings/incremental` → `ingest_earnings_incremental_api`) and to the `ingest --incremental` CLI flag.
- New tests: `tests/test_coverage.py` (coverage stats, ticker filtering, empty DB, incremental fetch skip/fetch paths, data-coverage API endpoint). Full suite: 129 passed.

## 2026-08-04 (checker fix + manual verification + per-day colors + per-day ranking + cache-versioning)
- **Checker bug fix** (`reports/checker.py`): split field sources by true origin — live-yfinance fields (`current_price`, `week_change`, `pct_from_52w_high/low`, `week_high`, `week_low`, `market_cap`) are now cache-verified only (not recomputed from stale `price_history`); price-history fields (`thirty_day_return_pct`, `earnings_week_move_pct`, `next_resistance`, `current_support`) are recomputed; earnings scores (`prev_quarter_earnings_score`, `prev_3q_earnings_score`, `q1/q2/q3_earnings_score`) are now fully recomputed from `earnings_history`. Added `unverified` counter for fields that can't be confirmed (no cache row). Fixes the ALPHAGEO false-inconsistency report.
- **Manual independent verification test** (`tests/manual/test_manual_report_verification.py`): picks the latest report CSV, documents a field spec (meaning + formula + true source for every field), rebuilds each calculation from raw SQLite **without calling production code**, and prints per-field pass/fail + mismatches. Run manually with `python -m pytest tests/manual/ -v`.
- **Per-day color grouping**: each distinct `earnings_date` gets a color from a dark-theme palette; ledger rows and cards are tinted via `{day_class}`; a date→color legend is added to the report header.
- **Per-day best-to-worst ranking**: rows are grouped by `earnings_date`, each day's sublist sorted by momentum (`thirty_day_return_pct + earnings_week_move_pct`), tie-broken by `prev_3q_earnings_score` then `market_cap`. Applied to ledger, cards, and CSV.
- New tests: `test_check_report_frame_marks_unverified_when_cache_missing`, `test_check_report_frame_recomputes_earnings_scores` (ALPHAGEO regression), `test_day_color_assignment`, `test_per_day_ranking`. Full suite: 90 passed.

## 2026-08-04 (report checker subworkflow + date-range param + once-per-day caching)
- **Report checker subworkflow** (`reports/checker.py`): new `ReportChecker` verifies every field in the enriched report DataFrame against the database. For each field it compares against the cached value (or a recomputation from the raw data source). If a report field is empty, the original calculation is re-run from the raw prices/earnings to confirm it is genuinely empty (not a bug that dropped data). Any mismatch is logged as an inconsistency. Exposed via `--check` flag on `upcoming-results` and standalone `check-report --csv <path>` command.
- **Date-range parameter**: `upcoming_earnings()`, `build_upcoming_events()`, and `predict_upcoming()` now accept `start_date` (window = `[start_date, start_date + days)`; defaults to today for backward compatibility). CLI `--start-date`/`--from` option added to `calendar`, `upcoming-results`, and `predict`.
- **Once-per-day caching**: `enrich_upcoming_results()` in `data/market_context.py` now reads `week_change`, `pct_from_52w_high`/`pct_from_52w_low`, `thirty_day_return_pct`, `week_high`/`week_low`, and `earnings_week_move_pct` from the existing `ticker_metrics` SQLite table (keyed by `(ticker, as_of_date)`), recomputing and re-storing only once per day. On same-day re-runs the cached values are reused.
- New tests: `tests/test_checker.py` (4 tests), `test_upcoming_earnings_with_start_date` in `tests/test_caching.py`, CLI `--check` + `--start-date` tests in `tests/test_predict.py`. Full suite: 87 passed.

## 2026-08-03 (report per-quarter fields restored + NSE playground dropdown fix)
- **Restored per-quarter fields in `enrich_upcoming_results()`** (`data/market_context.py`): the 2026-08-03 change that removed `prev_3q_earnings_score`, `q1_earnings_score`, `q2_earnings_score`, `q3_earnings_score`, and the per-quarter week high/low columns (`q1_week_high_pct`, `q1_week_low_pct`, `q1_week_high_price`, `q1_week_low_price`, `q2_*`, `q3_*`) was reverted. The report templates (`card.html`, `earnings_report_page.html`) and `render.py` still reference these fields, so the report was rendering blanks for Q1/Q2/Q3 Week H/L and quality scores. Now `enrich_upcoming_results()` computes the last 3 quarters' scores + week high/low (±4 business days around each earnings date) and the 3Q average (capped at max individual score), keeping the data layer, renderer, and templates consistent.
- **Fixed NSE playground 2nd dropdown empty** (`reports/templates/dashboard.html`): `app.pg.init()` now guards against a non-array catalog response, `populateGroup()` only overwrites the group select when groups exist, and `populateEndpoints()` shows a "No endpoints for this group" fallback option instead of leaving the endpoint dropdown blank. The NSE group has 7 catalog entries (universe, universe_files, market_caps, nse_universe_info, nse_result_calendar, nse_event_calendar, nse_financial_calendar).
- New regression tests: `test_enrich_upcoming_results_adds_individual_quarter_scores_and_week_hl` (per-quarter scores + week H/L restored) and `test_endpoint_catalog_nse_group_has_endpoints_for_dropdown` (NSE group has ≥7 endpoints). Full suite: 80 passed.

## 2026-08-03 (NSE financial calendar / result dates)
- Added `data/nse_api.py` — official NSE India API client (`https://www.nseindia.com/api/`): `fetch_result_calendar(from, to)` (raw result-calendar payload), `fetch_event_calendar(from, to)` (raw event-calendar payload: board meetings, results, dividends), `get_financial_calendar(symbol, from, to)` (normalized result dates for one symbol, raw payload kept separate). Browser-like session with homepage cookie priming + headers; all calls wrapped in try/except returning `{"error": ...}` on failure.
- New endpoints in `api/server.py`: `GET /api/v1/playground/nse/result-calendar?from_date=&to_date=`, `GET /api/v1/playground/nse/event-calendar?from_date=&to_date=`, `GET /api/v1/playground/nse/financial-calendar/{symbol}?from_date=&to_date=`.
- Added the 3 NSE calendar endpoints to the Playground API console catalog (NSE group) — now 17 catalog entries.
- New tests in `tests/test_playground.py`: catalog includes NSE calendar, `get_financial_calendar` normalizes result dates (raw kept separate), error fallback. Full suite: 78 passed.

## 2026-08-03 (Playground API console + ZOMATO timezone fix + Swing next-earnings)
- **Playground tab → API console**: Postman-style raw JSON explorer grouping the real API endpoints by source (Market Data / NSE / yfinance / Kronos). Symbol input with autocomplete (search across NSE_ALL + US via `GET /api/v1/playground/search?q=`), group + endpoint selector (`GET /api/v1/playground/endpoints` catalog), editable params auto-filled from the symbol, raw JSON response viewer with copy button, status + latency, loading/error states. Existing NSE Universe Stats + Kronos Quick Run preserved in a collapsible secondary section.
- **Kronos raw output**: the console exposes the raw `POST /api/v1/dashboard/kronos/run` payload (forecast_series, gbm_prediction, projected_close) plus `kronos/latest`, `kronos/audit`, `kronos/history/{ticker}` — no normalized English view.
- **Fix `['ZOMATO.NS']: possibly delisted; no timezone found`**: `kronos_predictor.fetch_historical_data()` now retries with explicit start/end dates + `auto_adjust=False`, falls back to `yf.download`, and only uses synthetic data if every live path fails (logged clearly). NSE symbols like ZOMATO are treated as permanently listed, never silently "delisted".
- **Playground symbol search robustness**: `search_symbols()` refreshes `nse_all.txt` from nsetools live when the cache misses a symbol, and falls back to offering the typed symbol + its `.NS` variant (so ZOMATO is always selectable).
- **Fix Swing tab "Next Earnings" always null**: `get_swing_setups()` pre-fetches the cached upcoming-earnings calendar for the batch and populates `earnings_date` per swing card (fallback to live `get_upcoming_earnings_date()`), so the Swing tab shows a real next earnings date.
- New endpoints: `GET /api/v1/playground/endpoints`, `GET /api/v1/playground/search`.
- New tests: `tests/test_playground.py` (catalog, search fallback, Swing earnings date, ZOMATO timezone retry). Full suite: 75 passed.

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