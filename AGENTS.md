# Earnings Engine — Agent Master Guidelines & Knowledge Base

> **Primary Instruction for AI Agents**: This document is the single source of truth for repository architecture, operating rules, error ledger protocols, subsystem design, CLI workflows, and common modification points. Read and adhere strictly to these guidelines before making changes.

---

## 1. Core Operating Protocols & Rules

### 1.1 Error Ledger & Self-Healing Protocol
Whenever you work on this repository, you must maintain zero-error hygiene using the integrated ledger:
1. **Pre-Task Check**: Check active errors at the start of any task:
   ```bash
   python scripts/error_ledger.py open
   ```
2. **Post-Task Verification**: Verify that changes introduced no unhandled exceptions or regressions:
   ```bash
   python scripts/error_ledger.py scan
   python scripts/smart_test.py
   ```
3. **Resolution Logging**: When you fix an existing issue, resolve it in the ledger:
   ```bash
   python scripts/error_ledger.py resolve <error_id> "<explanation of the fix>"
   ```

### 1.2 Git Commit & Push Protocol
- **Local Commits**: Keep committing changes locally as each feature, fix, or refactor is completed and verified.
- **Push Policy**: Do **NOT** push to the remote repository after every individual change. Only push once per day after **10:00 PM IST** (or when explicitly commanded by the user).

### 1.3 Execution Environment
- **OS**: Windows (PowerShell / pwsh)
- **Python Virtual Environment**: `.\.venv\Scripts\python.exe` (always invoke through `.venv` or ensure virtualenv is activated)

---

## 2. Project Architecture & Subsystems

```
earnings-engine/
├── AGENTS.md                         # Master Agent Guidelines & Knowledge Base
├── COMMANDS.md                       # CLI command reference
├── pyproject.toml                    # Dependencies & entrypoint (`earnings-engine`)
├── scripts/
│   ├── error_ledger.py               # Centralized exception logging and tracking
│   └── smart_test.py                 # Change-aware selective test runner
├── earnings_engine/
│   ├── config.py                     # App settings & environment loading
│   ├── logging_utils.py              # Centralized logging setup
│   ├── emailing.py                   # SMTP report dispatching
│   ├── rate_limits.py                # Sliding-window per-model & provider rate limit tracker
│   ├── api/
│   │   ├── server.py                 # FastAPI application, route mounting, UI endpoints
│   │   ├── stock_api.py              # Dedicated stock intelligence & EPS derivation routes
│   │   └── dashboard_api.py          # Dashboard aggregation, watchlists & coverage API
│   ├── consensus/                    # Multi-Model AI Consensus Engine
│   │   ├── context_builder.py        # Point-in-time quantitative context aggregator
│   │   ├── model_runner.py           # Parallel LLM inference (DeepSeek-R1, Llama-70B, Qwen-72B, Mistral)
│   │   ├── aggregator.py             # Directional voting, target synthesis & risk calculation
│   │   └── storage.py                # Prediction persistence & historical audit trail
│   ├── data/                         # Ingestion & Data Management
│   │   ├── db.py                     # SQLite / Turso database connection & table schemas
│   │   ├── turso.py                  # Turso Cloud database sync & pipeline client
│   │   ├── prices.py                 # Daily OHLCV price ingestion, caching & indicators
│   │   ├── earnings.py               # Corporate earnings dates, EPS estimates & surprises
│   │   ├── watchlists.py             # Watchlist management (SQLite + Turso sync)
│   │   ├── universe.py               # Market universe resolution (IN, NSE_ALL, US, etc.)
│   │   ├── market_context.py         # 52W range, week high/low around earnings
│   │   └── predictions.py            # Legacy prediction cache management
│   ├── features/                     # Point-in-Time (PIT) Feature Engineering
│   │   ├── price_features.py         # Technical momentum, volatility & volume metrics
│   │   ├── earnings_features.py      # Historical surprise streak & beat frequency
│   │   └── labels.py                 # 1-day post-earnings reaction calculation
│   ├── models/                       # Predictive Models & Heuristics
│   │   ├── base.py                   # BaseModel abstract class
│   │   ├── baseline.py               # PastUpRateBaseline heuristics
│   │   ├── classifier.py             # LightGBM Classifier with Platt probability calibration
│   │   └── registry.py               # Model registration & lookup
│   ├── backtest/
│   │   └── engine.py                 # Quarterly walk-forward backtesting framework
│   ├── breakout/
│   │   └── radar.py                  # Breakout Radar scanner, tracking & outcome verification
│   ├── reports/
│   │   ├── render.py                 # Report generation (HTML/CSV/Telegram/Email)
│   │   └── templates/                # Jinja2 & HTML templates (stock_detail.html, dashboard/)
│   └── ui/                           # Frontend static assets (CSS, JS, dashboard.js)
```

---

## 3. Subsystem Deep-Dives

### 3.1 AI Consensus Engine (`earnings_engine/consensus/`)
- **Models**:
  - `deepseek/deepseek-r1`: Deep reasoning & chain-of-thought analysis.
  - `meta-llama/llama-3.3-70b-instruct`: Institutional macro & fundamental momentum.
  - `qwen/qwen-2.5-72b-instruct`: Algorithmic structure & volume pattern recognition.
  - `mistralai/mistral-large` (fallback `google/gemini-2.0-flash-001`): News catalyst analysis.
- **Workflow**:
  1. `context_builder.py` gathers real-time live price, swing momentum, volume spikes, quarterly EPS history, and news catalysts.
  2. `model_runner.py` sends parallel requests to OpenRouter / LLM APIs.
  3. `rate_limits.py` tracks sliding-window RPM/RPD per model and records response headers.
  4. If a single model is run (e.g. user clicks "⚡ Run DeepSeek-R1"), `server.py` merges the single output with cached predictions from other models and triggers `aggregator.aggregate_predictions()` for a unified consensus verdict.
  5. `storage.py` saves the forecast with settlement date for future accuracy auditing.

### 3.2 Data Layer & Cloud Sync (`earnings_engine/data/`)
- **Database**: SQLite (`earnings_engine.db`) with fallback and optional Turso Cloud replication (`TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN`).
- **Key Tables**:
  - `price_history`: Daily OHLCV prices per ticker.
  - `earnings_calendar`: Earnings announcement dates, reported EPS, estimated EPS, surprise %.
  - `consensus_predictions`: Historical AI forecasts, direction, stop loss, targets, settlement status.
  - `breakout_radar`: Detected breakouts, trigger price, target, stop loss, and outcome tracking.
  - `watchlists`: User watchlist groupings (`swing`, `my_watchlist`, etc.).
  - `ticker_metrics` / `ticker_market_cap`: Fundamental market cap and metadata.

### 3.3 Stock Intelligence & EPS Derivation (`earnings_engine/api/stock_api.py`)
- **Live Pricing**: `/api/v1/stock/{ticker}/quote` and `/api/v1/stock/{ticker}` fetch live intraday prices via `yfinance` fast_info.
- **Missing EPS Calculation**: `/api/v1/stock/{ticker}/calculate-eps` automatically derives missing historical EPS for passed earnings dates using trailing quarterly income statements or user manual overrides.

### 3.4 Breakout Radar & Swing Scanner
- Scans `IN` (Nifty 50), `NSE_ALL`, or custom watchlists for high-conviction breakout setups based on 52W highs, volume expansion, and compression channels.
- Persists found breakouts to database and tracks if targets or stop losses are hit over subsequent trading sessions.

---

## 4. Critical Engineering Quirks & Gotchas

> [!IMPORTANT]
> **1. Point-in-Time (PIT) Guarantee**:
> In `features/` and `dataset.py`, never leak future information. All feature computation for event date $T$ must strictly filter `prices.loc[prices.index <= asof_date]` where `asof_date` is the trading day before earnings announcement.

> [!WARNING]
> **2. FastAPI Route Precedence**:
> In `earnings_engine/api/server.py`, explicit literal routes (e.g. `/api/v1/watchlist/quotes`, `/api/v1/watchlist/all`, `/api/v1/watchlist/names`) **MUST ALWAYS** be defined **before** parameterized routes like `/api/v1/watchlist/{name}`. Otherwise, FastAPI will treat literal words like `"quotes"` as path parameters.

> [!TIP]
> **3. Turso Remote Database Error Handling**:
> When querying remote Turso instances, always encapsulate calls with local SQLite fallback in case of network timeouts (`ConnectionResetError` / `ReadTimeout`).

> [!NOTE]
> **4. yfinance Symbol Suffixes**:
> Indian NSE equities require the `.NS` suffix (e.g., `TCS.NS`, `RELIANCE.NS`). Check for symbol aliases where applicable (e.g., `STERTECH.NS` $\rightarrow$ `STLTECH.NS`).

---

## 5. Common Modification Points

| Goal | Primary Files to Change |
| :--- | :--- |
| **Add a new technical / fundamental feature** | `earnings_engine/features/price_features.py` or `earnings_features.py` + `dataset.py` |
| **Modify post-earnings reaction label** | `earnings_engine/features/labels.py` (`compute_reaction`) |
| **Add a new AI model to Consensus Engine** | `earnings_engine/rate_limits.py` (`AVAILABLE_AI_MODELS`) + `model_runner.py` + `templates/stock_detail.html` |
| **Modify Walk-Forward Backtesting** | `earnings_engine/backtest/engine.py` |
| **Add or edit REST API endpoints** | `earnings_engine/api/server.py` or `stock_api.py` / `dashboard_api.py` |
| **Modify Stock Detail UI or AI Matrix** | `earnings_engine/reports/templates/stock_detail.html` |
| **Modify Main Dashboard UI & Tabs** | `earnings_engine/reports/templates/dashboard/` + `earnings_engine/ui/js/dashboard.js` |
| **Add a new CLI command** | `earnings_engine/cli.py` |
| **Modify Database Schemas or Turso Sync** | `earnings_engine/data/db.py` + `turso.py` |

---

## 6. CLI Command Quick Reference

### Ingestion & Data
```bash
# Ingest entire NSE market (prices, earnings, calendar, market caps)
earnings-engine ingest --market NSE_ALL

# Fast incremental ingestion (only missing earnings dates)
earnings-engine ingest --market NSE_ALL --incremental

# Ingest specific tickers
earnings-engine ingest --ticker TCS.NS INFY.NS RELIANCE.NS
```

### AI Predictions & Consensus
```bash
# Run LightGBM earnings reaction predictions
earnings-engine predict --market NSE_ALL --days 14

# Run Kronos AI 14-day price prediction (uses CUDA GPU if available)
earnings-engine kronos-predict --market IN --device cuda:0

# Pre-compute and cache all AI predictions
earnings-engine cache-predictions --market NSE_ALL --earnings-only --days 14
```

### Backtesting & Datasets
```bash
# Build Point-in-Time event dataset
earnings-engine build-dataset --market NSE_ALL

# Run walk-forward backtest
earnings-engine backtest --model gbm --threshold 0.5 --cost 0.001
```

### Dashboard & Server
```bash
# Start interactive web dashboard (opens http://localhost:8000/dashboard)
earnings-engine dashboard

# Run API server directly
python run_api.py
```

### Verification & Testing
```bash
# Run change-aware test runner
python scripts/smart_test.py

# Run full pytest suite
pytest
```
