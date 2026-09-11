# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

**Earnings Engine** (Nexus Intelligence Platform) is a quantitative equity research engine and intelligence dashboard for **NSE India (`.NS`) and US equities**. Key capabilities include:
- Predicting 1-day post-earnings price direction and calibrated probabilities via LightGBM + Platt scaling.
- 14-day neural price trajectory forecasting via Kronos AI (PyTorch / CUDA).
- Multi-Model AI Consensus Engine (DeepSeek-R1, Llama-3.3-70B, Qwen-2.5-72B, Mistral-Large) via OpenRouter / OmniRoute gateway.
- Breakout Radar, Swing range detector, and Institutional accumulation tracking.
- Quarterly walk-forward out-of-sample backtesting framework.
- FastAPI REST API backend and responsive multi-hub web dashboard (`/dashboard`, `/stock/{ticker}`, `/portal`, `/net-worth`, `/credit-cards`, `/trips`).

---

## Common Development Commands

### Environment & Setup
Always run within the virtual environment:
```bash
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
# Or invoke Python directly
.\.venv\Scripts\python.exe <command>
```

### Running Tests
Always favor targeted test execution during development to avoid slow full-suite runs:
```bash
# Run a specific test file (recommended default for development)
pytest tests/test_predict.py

# Run a single test function (fastest verification loop)
pytest tests/test_predict.py -k "test_predict_upcoming_runs"

# Run with verbose output
pytest -v tests/test_stock_api.py

# Run full test suite (only for final pre-release / full regression pass)
pytest
```

### Running the API & Dashboard
```bash
# Start dashboard and open browser (runs FastAPI at http://localhost:8000/dashboard)
earnings-engine dashboard

# Run FastAPI server directly with uvicorn reload
python run_api.py
# Or:
uvicorn earnings_engine.api.server:app --host 0.0.0.0 --port 8000 --reload
```

### Data Ingestion & Dataset Construction
```bash
# Ingest full NSE universe (prices, earnings, calendar, market cap)
earnings-engine ingest --market NSE_ALL

# Incremental earnings ingestion (fast missing-only check)
earnings-engine ingest --market NSE_ALL --incremental

# Ingest specific tickers
earnings-engine ingest --ticker TCS.NS INFY.NS RELIANCE.NS

# Ingest institutional shareholding & AMFI fund portfolios
earnings-engine ingest-institutional --limit 500

# Build Point-in-Time event dataset (features + labels)
earnings-engine build-dataset --market NSE_ALL
```

### Model Prediction & Backtesting
```bash
# Predict upcoming earnings reaction direction & confidence (GBM)
earnings-engine predict --market NSE_ALL --days 14

# Run Kronos AI 14-day price prediction (auto-detects CUDA / PyTorch GPU)
earnings-engine kronos-predict --market IN --device cuda:0

# Pre-compute & cache predictions (two-phase workflow)
earnings-engine cache-predictions --market NSE_ALL --earnings-only --days 14

# Run quarterly walk-forward backtest
earnings-engine backtest --model gbm --threshold 0.5 --cost 0.001
```

### Error Ledger & Verification Tools
```bash
# Scan error stream and inspect open errors
python scripts/error_ledger.py open
python scripts/error_ledger.py summary

# Run pre/post-task health gate
python scripts/error_ledger.py check

# Run full data audit and live-sync runner
python scripts/verify_and_sync_all_data.py
```

---

## High-Level Architecture & Code Structure

```
earnings-engine/
├── earnings_engine/
│   ├── api/                  # FastAPI app & routing
│   │   ├── server.py         # App factory, middleware, mount points
│   │   ├── routers/          # Modular API route handlers (dashboard, stocks, institutional, breakout, etc.)
│   │   ├── stock_api.py      # Ticker intelligence, EPS surprise, valuation
│   │   └── dashboard_api.py  # Dashboard aggregations, coverage, watchlists
│   ├── backtest/             # Walk-forward backtester (engine.py, breakout/swing backtests)
│   ├── brokers/              # Broker API adapters (Angel One, Zerodha, Dhan, Fyers, TOTP)
│   ├── consensus/            # Multi-Model AI Consensus Engine
│   │   ├── context_builder.py# Point-in-Time quantitative context builder
│   │   ├── model_runner.py   # Parallel async LLM inference (DeepSeek, Llama, Qwen, Mistral)
│   │   ├── aggregator.py     # Voting, targets synthesis, stop losses
│   │   └── storage.py        # Consensus persistence & accuracy settlement
│   ├── data/                 # Data layer & ingestion pipelines
│   │   ├── db.py             # SQLite schemas & connection management (prices.sqlite3)
│   │   ├── turso_sync.py     # Cloud Turso database synchronization
│   │   ├── prices.py         # Daily OHLCV price ingestion, indicators, caching
│   │   ├── earnings.py       # Earnings dates, EPS history, surprises
│   │   ├── nse_api.py        # Direct NSE India exchange scrapers & session handler
│   │   ├── universe.py       # Market universe resolution (IN, US, NSE_ALL, custom)
│   │   ├── market_context.py # 52W metrics, price channels, quality scores
│   │   └── providers/        # Multi-provider price fallback framework (NSE, yfinance)
│   ├── features/             # Point-in-Time (PIT) feature engineering
│   │   ├── price_features.py # 16 technical momentum, volatility, surge metrics
│   │   ├── earnings_features.py # Historical surprise streaks & beat ratios
│   │   └── labels.py         # 1-day post-earnings reaction calculation
│   ├── models/               # Direction models (Base, AlwaysUp, PastUpRate, GBClassifier)
│   ├── reports/              # HTML/CSV report rendering & Jinja2 templates
│   ├── trading_agents/       # Autonomous trading agent workflows & execution
│   ├── ui/                   # Frontend static assets (CSS, modular JS, dashboard.js)
│   ├── cli.py                # Click CLI command definitions
│   ├── config.py             # Central settings (Settings dataclass, environment vars)
│   └── kronos_predictor.py   # Kronos AI 14-day neural sequence prediction pipeline
├── scripts/                  # Operational scripts (error_ledger.py, verify_and_sync_all_data.py)
└── tests/                    # Pytest test suite
```

---

## Critical Engineering Rules & Conventions

### 1. Strict Point-in-Time (PIT) Guarantee
- **Never use future data**: In `features/`, `dataset.py`, and `backtest/`, feature computation for an event date $T$ must filter prices strictly up to $T-1$ (`prices.loc[prices.index <= asof_date]`).
- Post-earnings reaction is computed as $\text{reaction\_return} = \frac{\text{close}(T+1)}{\text{close}(T-1)} - 1$.
- Walk-forward backtesting folds must cut chronologically by `earnings_date < fold_start` with per-fold model refitting.

### 2. Timeframe & Temporal Association
- Every metric, delta, signal, accumulation flow, momentum score, and forecast must explicitly specify its horizon/window in both backend payloads and UI cards/tables (e.g., `7D Return: +4.2%`, `Funds: +4 / -0 (QoQ / ~90d)`, `Volume Surge: 2.4x (5D vs 63D)`).

### 3. Anti-Fabrication & Real Data Integrity
- Never use synthetic dummy values, seeded pseudo-random data, or mock fallbacks in production endpoints.
- If data is missing or exchange is closed, return `None`, `0.0`, or `[]` with an honest status indicator (e.g., `Market Closed`, `No Institutional Filings On Record`).

### 4. On-Demand AI Inference & Zero-Token Default
- Never trigger automatic LLM inference or OmniRoute gateway requests on page, modal, or table load.
- Ingestion and stock inspection default to zero token usage; AI analysis (Consensus, Thesis, News Triage) must be purely on-demand and user-triggered.

### 5. FastAPI Routing Precedence
- In `earnings_engine/api/server.py` and routers, **always define explicit static/literal routes before parameterized routes** (e.g., define `/api/v1/watchlist/quotes` and `/api/v1/watchlist/names` *before* `/api/v1/watchlist/{name}`).

### 6. Database & Storage Layer & Remote DB Sync
- Primary database is SQLite at `data/cache/prices/prices.sqlite3` (or `earnings_engine.db` in root).
- Optional Turso Cloud replication via `turso_sync.py` with watermark delta sync when `TURSO_DATABASE_URL` and `TURSO_AUTH_TOKEN` are configured. Always wrap remote database calls with local SQLite fallback.
- **MANDATORY Remote DB Sync Rule for New Tables**: Whenever ANY new SQLite table or schema entity is added anywhere in the codebase (data scanners, modules, routers, migrations, storage handlers, or cache layers), you MUST:
  1. Add the table name to `SYNC_TABLES` in `earnings_engine/data/turso_sync.py`.
  2. If the table has a timestamp or update column (e.g., `updated_at`, `created_at`, `scanned_at`, `date`, `asof_date`, `timestamp`), verify it is present in `WATERMARK_CANDIDATE_COLUMNS` (and `DATE_ONLY_COLUMNS` if formatted as `YYYY-MM-DD`).
  3. Ensure table creation SQL is valid SQLite/libSQL so bidirectional lossless sync (`INSERT OR IGNORE`) and remote table auto-creation / column self-healing work seamlessly without manual intervention.

### 7. Ticker Symbol Suffixes & Market Handling
- NSE Indian equities require the `.NS` suffix (e.g., `TCS.NS`, `RELIANCE.NS`). US equities have no suffix.
- Use `market_of(ticker)` from `earnings_engine.config` to resolve market type (`"IN"` vs `"US"`).

### 8. Agent Performance & Workflow Efficiency
Empirical timing profiles across agent sessions show ~70% of wall-clock time is network turn-latency and ~20% is heavy sub-processes (such as full-suite pytest or slow integration tests). Follow these operational rules to maximize throughput:
- **Batch Independent Tool Calls**: Always issue independent file reads, content searches (`Grep`), file listings (`Glob`), or checks concurrently in a single response turn rather than serializing them across multiple 3–4s round-trips.
- **Targeted Test Runs Over Full Suites**: During iterative development and verification, run only the targeted test file or function under modification (`pytest tests/<test_file>.py -k "<test_func>"`). Never trigger the full test suite or slow integration/E2E test suites (e.g., `tests/test_stock_detail_e2e.py`) unless explicitly requested or performing final pre-release validation.
- **Context Hygiene & Output Bounding**: Keep tool outputs bounded (use `head_limit`, specific `grep` patterns, line slices with `offset`/`limit` in `Read`). Avoid printing massive raw logs, full directory dumps, or large payloads into context, which inflates prefill latency and degrades prompt caching.
- **Session Compaction & Clean Turn Cycles**: For multi-stage or prolonged tasks, proactively compact or reset context when switching phases. Plan operations comprehensively to minimize iterative micro-turn churn.

