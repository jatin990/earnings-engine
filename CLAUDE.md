# CLAUDE.md — Nexus Intelligence Platform (Earnings Engine)

> **Single Source of Truth** for Claude Code operating on the **Earnings Engine** repository.
> Combines architecture specifications, operating protocols, database sync contracts, capability mapping, and development workflows.

---

## 1. System Overview & Platform Architecture

**Earnings Engine (Nexus Intelligence Platform)** is a production quantitative equity research engine and multi-hub operations platform for **NSE India (`.NS`) and US equities**.

### Core Capabilities
- **Earnings Intelligence**: 13,133+ event Point-in-Time dataset; 1-day post-earnings reaction probability via LightGBM + Platt scaling.
- **Deep Sequence Forecasting**: Kronos AI 14-day neural price trajectories with support/resistance mapping (PyTorch / CUDA).
- **Multi-Model AI Consensus**: Parallel inference (DeepSeek-R1, Llama-3.3-70B, Qwen-2.5-72B, Mistral-Large) via OpenRouter / OmniRoute gateway with per-model rate limiting, structured schema extraction, and directional voting.
- **Quantitative Market Scanners**: Breakout Radar, Swing Range & Cycle Timing, Tri-Confluence Radar, Options Chain & Open Interest (OI) positioning, and Premarket Pulse.
- **Institutional Forensics**: Shareholding patterns, QoQ fund accumulation flows, AMFI mutual fund portfolio tracking, provenance tracking, and data quarantine.
- **Autonomous Trading & Brokerage**: Multi-broker adapters (Angel One, Zerodha, Dhan, Fyers, TOTP) and autonomous trading agent workflows.
- **Operations & Lifestyle Hubs**: Net Worth tracking, Credit Cards & Rewards optimization, Travel/Trips expense splitting, and Zepto Store Operations & P&L management.
- **Security & Access**: Nexus Gateway (`/portal`), Passcode engine (`NEXUS-<CODE>`), 6-digit email OTPs, HMAC-SHA256 session tokens, and fine-grained RBAC.

### Scoped Application Hubs & Routing
| Hub | Route / Anchor | Description |
| :--- | :--- | :--- |
| **Nexus Gateway** | `/portal`, `/passcodes` | Authentication, passcodes, invite codes, RBAC, session lifecycle |
| **Market Intelligence** | `/dashboard`, `/stock/{ticker}` | Earnings calendar, quotes, EPS surprise derivation, 52W range, AI Consensus, Kronos AI |
| **Breakout Radar** | `/dashboard#breakout` | Momentum breakouts, volume surges, compression squeezes, outcome audit logs |
| **Swing & Tri-Confluence** | `/dashboard#swing`, `...#tri-confluence` | Support/resistance channels, cycle counts, multi-timeframe indicator confluence |
| **Options & Market Pulse** | `/dashboard#options`, `...#premarket` | Option chain analysis, participant OI positioning (FII/DII/Retail), gap setups |
| **Institutional Forensics** | `/dashboard#institutional` | Corporate shareholding, institutional net flows, block deals, AMFI fund holdings |
| **News Catalysts** | `/dashboard#news` | News ingestion, catalyst triage, ticker impact windows, outcome auditing |
| **Trading Agents** | `/dashboard#trading-agents` | Autonomous agent execution, multi-strategy logs, decision audits |
| **Net Worth Hub** | `/net-worth` | Multi-asset wealth consolidation (equities, mutual funds, EPF/PPF, real estate, cash) |
| **Credit Cards Hub** | `/credit-cards` | Statement billing cycles, spend rewards optimization, bill payments |
| **Trips Hub** | `/trips` | Group travel itinerary, activity schedules, multi-member expense settlement |
| **Zepto Store Hub** | `/zepto` | Quick-commerce dark store operations, staff rosters, salaries, expenses, P&L splits |

---

## 2. Critical Operating Protocols & Rules

### 2.1 Git Commit & Remote Push Protocol
- **Strict Rule**: **Always commit and push changes to the remote branch upon completing each task.**
- Ensure changes are tested and verified before committing.
- Commit messages must follow conventional commits (`feat:`, `fix:`, `refactor:`, `test:`, `docs:`) and include required co-authorship attribution.

### 2.2 Error Ledger & Self-Healing Protocol
Zero-error hygiene must be maintained across all tasks using `scripts/error_ledger.py`:
1. **Pre-Task Check**: `python scripts/error_ledger.py open` (inspect open issues before starting).
2. **Post-Task Verification**: `python scripts/error_ledger.py scan` (verify no new exceptions are logged in stdout/stderr streams).
3. **Resolution Logging**: `python scripts/error_ledger.py resolve <error_id> "<resolution details>"`.

### 2.3 Strict Point-in-Time (PIT) Guarantee
- **Never leak future information**: In `features/`, `dataset.py`, and `backtest/`, feature computation for an event date $T$ must strictly filter price bars up to $T-1$ (`prices.loc[prices.index <= asof_date]`).
- Post-earnings reaction is defined strictly as:
  $$\text{reaction\_return} = \frac{\text{close}(T+1)}{\text{close}(T-1)} - 1$$
- Binary label: $1$ if $\text{reaction\_return} > 0$, else $0$. Return `None` if $T-1$ or $T+1$ bars are absent or trading gap $>10$ days.
- Walk-forward backtest splits must be cut chronologically with strict per-fold model retraining.

### 2.4 Universal Timeframe & Temporal Association Protocol
Every metric, delta, signal, accumulation flow, momentum score, and forecast **MUST ALWAYS explicitly declare its window or baseline** in backend payloads and UI cards:
- **Returns / Momentum**: `7D Return: +4.2%`, `30D Return: -1.8%`, `52W High / Low`. Never standalone `+X%`.
- **Institutional Flows**: `Funds: +4 / -0 (QoQ / ~90d)`, `Filing: Q1 FY27 vs Q4 FY26`.
- **Volume / Volatility**: `Volume Surge: 2.4x (5D vs 63D avg)`, `21-Day Annualized Volatility`.
- **AI Predictions**: `Forecast Horizon: 14 Trading Days`, `Reaction Window: 1-Day Post-Earnings`.
- **Data Freshness**: Always display last update timestamp or status (`As of 2026-09-12 15:30 IST`, `🟢 Live Quote`, `📊 EOD Snapshot`).

### 2.5 Strict Anti-Fabrication & Real-Data Integrity
- **Zero-tolerance for mock/synthetic data**: NEVER use static placeholders, seeded pseudo-random values (`hashlib.md5(...) % N`), or dummy fallbacks in production endpoints.
- If data is missing or markets are closed, return `None`, `0.0`, or `[]` with an explicit status indicator (e.g., `Market Closed · Weekend Snapshot`, `No Institutional Filings On Record`, `Pending Exchange Disclosure`).

### 2.6 On-Demand AI Inference & Zero-Token Default
- **Never trigger automated LLM inference** or OmniRoute gateway calls on page load, modal open, or table render.
- Ingestion and data viewing default to zero token usage. AI inference (Consensus, Thesis, News Triage) is strictly on-demand via explicit user click/trigger.

### 2.7 Remote DB Synchronization & Mandatory `SYNC_TABLES` Rule
The system operates on local SQLite (`data/cache/prices/prices.sqlite3` or `earnings_engine.db`) with cloud Turso replication via `earnings_engine/data/turso_sync.py`:
- **MANDATORY Rule for New Tables**: Whenever ANY new SQLite table or schema entity is added anywhere in the codebase:
  1. Register the table name in `SYNC_TABLES` in `earnings_engine/data/turso_sync.py`.
  2. If the table has a date/timestamp column (`updated_at`, `created_at`, `scanned_at`, `date`, `asof_date`, `timestamp`), ensure it exists in `WATERMARK_CANDIDATE_COLUMNS` (and `DATE_ONLY_COLUMNS` if formatted `YYYY-MM-DD`).
  3. Ensure table creation SQL uses standard SQLite/libSQL so bidirectional sync (`INSERT OR IGNORE`) and auto-column creation work without errors.
- Always encapsulate remote Turso calls with local SQLite fallbacks to prevent network timeout breakages.

### 2.8 FastAPI Routing Precedence
- In `earnings_engine/api/server.py` and routers, **always define explicit static/literal routes before parameterized routes** (e.g., define `/api/v1/watchlist/quotes` and `/api/v1/watchlist/names` *before* `/api/v1/watchlist/{name}`).

### 2.9 Ticker Symbol Suffixes & Market Conventions
- Indian equities require the `.NS` suffix (e.g., `TCS.NS`, `RELIANCE.NS`). US equities have no suffix.
- Use `market_of(ticker)` from `earnings_engine.config` to resolve market type (`"IN"` vs `"US"`).
- Maintain symbol alias mappings when NSE tickers change (e.g., `STERTECH.NS` $\rightarrow$ `STLTECH.NS`).

### 2.10 Agent Performance, Workflow Efficiency & Context Hygiene
- **Batch Independent Tool Calls**: Concurrently issue multiple independent `Read`, `Grep`, or `Glob` calls in a single turn.
- **Model Tiering**:
  - *Reasoning / High-Effort*: Multi-stage architecture, quantitative algorithms (PIT logic, consensus synthesis), root-cause debugging across systems, security reviews.
  - *Fast Execution*: Routine implementation, boilerplate, test authoring, running test suites, search/inspection.
- **Targeted Test Execution**: Run only the targeted test file or function under modification (`pytest tests/<test_file>.py -k "<test_func>"`). Avoid running full test suites or slow E2E tests (`tests/test_stock_detail_e2e.py`) during development.
- **Context Hygiene**: Bound tool outputs with `head_limit`, specific `grep` patterns, and line offsets. Never dump large raw logs or JSON payloads into the conversation.
- **Persist Schemas & Contracts to Persistent Memory**: When modifying or creating database schemas, table column orders, or core API contracts, persist the exact schemas and signatures to `.claude/projects/.../memory/` immediately to survive context compaction.

---

## 3. Codebase Directory Layout

```
earnings-engine/
├── CLAUDE.md                         # Authoritative Agent Guidelines & Knowledge Base
├── AGENTS.md                         # Pointer to CLAUDE.md (legacy agent compatibility)
├── COMMANDS.md                       # CLI command reference guide
├── pyproject.toml                    # Package dependencies & CLI entrypoints
├── run_api.py                        # Standalone API runner
├── scripts/
│   ├── error_ledger.py               # Centralized exception logging, audit & self-healing
│   ├── verify_and_sync_all_data.py   # Full data audit and live-sync runner
│   └── migrate_sqlite_to_turso.py    # Remote Turso database migration utility
├── earnings_engine/
│   ├── config.py                     # Global settings, environment loading, market_of()
│   ├── logging_utils.py              # Structured logging configuration
│   ├── emailing.py                   # SMTP / Resend report & OTP dispatching
│   ├── rate_limits.py                # Sliding-window per-model & provider rate limiter
│   ├── dataset.py                    # Point-in-Time dataset generation & feature assembly
│   ├── predict.py                    # LightGBM upcoming earnings scoring pipeline
│   ├── kronos_predictor.py           # Kronos AI 14-day deep sequence forecast runner
│   ├── api/                          # FastAPI REST API Backend
│   │   ├── server.py                 # App factory, middleware (auth/CORS), route mounting
│   │   ├── stock_api.py              # Dedicated stock intelligence & EPS derivation routes
│   │   ├── dashboard_api.py          # Dashboard aggregations, watchlists & coverage
│   │   └── routers/                  # 22 Modular Domain Routers:
│   │       ├── auth.py               # Nexus auth, sessions, OTP, passcodes & RBAC
│   │       ├── audit.py              # Prediction & strategy audit logs
│   │       ├── breakout.py           # Breakout radar, setup scanners, tracked signals
│   │       ├── cards.py              # Credit cards, statements, reward optimization
│   │       ├── consensus.py          # Multi-Model AI Consensus triggers & results
│   │       ├── dashboard.py          # Core dashboard views & telemetry
│   │       ├── institutional.py      # Shareholding patterns, AMFI funds, block deals
│   │       ├── kronos.py             # Kronos AI forecast generation & trajectories
│   │       ├── news.py               # News ingestion, catalyst triage & impact
│   │       ├── options.py            # Option chains & participant OI positioning
│   │       ├── playground.py         # Quantitative backtest & strategy playground
│   │       ├── premarket.py          # Premarket pulse, top gainers, index gaps
│   │       ├── repeaters.py          # Quarter repeater historical patterns
│   │       ├── scanner.py            # Market scanner candidate discovery
│   │       ├── stocks.py             # Stock metrics, 52W range, historical quotes
│   │       ├── swing.py              # Swing ranges, support/resistance, cycle logs
│   │       ├── system.py             # System telemetry, Turso sync triggers, health
│   │       ├── trading_agents.py     # Autonomous trading agents & execution logs
│   │       ├── tri_confluence.py     # Tri-confluence multi-timeframe radar
│   │       ├── trips.py              # Travel itineraries, activities, expense splits
│   │       ├── watchlists.py         # Watchlist management & cloud sync
│   │       └── zepto.py              # Zepto dark store ops, rosters, salaries, P&L
│   ├── consensus/                    # Multi-Model AI Consensus Engine
│   │   ├── context_builder.py        # Point-in-time quantitative context aggregator
│   │   ├── model_runner.py           # Parallel LLM inference (DeepSeek, Llama, Qwen, Mistral)
│   │   ├── aggregator.py             # Directional voting, target synthesis & risk calculation
│   │   └── storage.py                # Prediction persistence & settlement audit trail
│   ├── brokers/                      # Broker Integrations (Angel One, Zerodha, Dhan, Fyers, TOTP)
│   ├── trading_agents/               # Autonomous execution agents & strategy modules
│   ├── data/                         # Data Access & Ingestion Pipelines
│   │   ├── db.py                     # SQLite connection pools & table schemas
│   │   ├── turso_sync.py             # Turso Cloud bidirectional delta sync (SYNC_TABLES)
│   │   ├── auth.py                   # Session tokens, HMAC auth, and RBAC verification
│   │   ├── passcodes.py              # Passcode generation, validation & scope enforcement
│   │   ├── prices.py                 # Daily OHLCV price ingestion, caching & indicators
│   │   ├── earnings.py               # Corporate earnings dates, EPS estimates & surprises
│   │   ├── nse_api.py                # Direct NSE India exchange scrapers & session cookies
│   │   ├── universe.py               # Universe resolution (IN, NSE_ALL, US, custom)
│   │   ├── market_context.py         # 52W metrics, price channels, quality scores
│   │   └── providers/                # Multi-provider fallback framework (NSE, yfinance)
│   ├── features/                     # Point-in-Time (PIT) Feature Engineering
│   │   ├── price_features.py         # 16 technical momentum, volatility & volume metrics
│   │   ├── earnings_features.py      # Historical surprise streaks & beat frequency
│   │   └── labels.py                 # 1-day post-earnings reaction calculation
│   ├── models/                       # Predictive Models & Heuristics
│   │   ├── base.py                   # BaseModel abstract interface
│   │   ├── baseline.py               # AlwaysUp & PastUpRate empirical Bayes models
│   │   ├── classifier.py             # LightGBM with Platt probability calibration
│   │   └── registry.py               # Model registration & factory
│   ├── backtest/                     # Walk-forward backtesting engine & simulation
│   ├── breakout/                     # Breakout Radar detection algorithms & tracking
│   ├── reports/                      # HTML/CSV report rendering & Jinja2 templates
│   │   └── templates/                # stock_detail.html, portal.html, dashboard/
│   └── ui/                           # Frontend static assets (CSS, modular JS, dashboard.js)
└── tests/                            # Pytest suite
```

---

## 4. Database Architecture & Key Tables

Primary SQLite database located at `data/cache/prices/prices.sqlite3` (or `earnings_engine.db`), synchronized with Turso Cloud via `SYNC_TABLES`:

| Domain | Key Tables |
| :--- | :--- |
| **Auth & Security** | `passcodes`, `users`, `user_auth`, `user_sessions`, `invite_codes`, `friend_access`, `otp_verifications`, `ui_preferences` |
| **Market Data** | `price_history`, `earnings_history`, `earnings_freshness`, `ticker_metrics`, `ticker_market_cap`, `universes`, `universe_stocks`, `universe_freshness` |
| **Quant Models** | `event_dataset`, `consensus_predictions`, `kronos_predictions`, `strategy_predictions`, `strategy_audit_logs`, `quarter_repeater_predictions` |
| **Scanners & Radar** | `breakout_radar`, `breakout_tracked_signals`, `breakout_audit_log`, `scanner_candidates`, `swing_ranges`, `swing_cycle_history`, `swing_radar`, `confluence_radar`, `tri_confluence_metrics`, `option_chain_history` |
| **Institutional** | `institutional_holdings`, `institutional_block_deals`, `shareholding_patterns`, `institutional_accumulation_cache`, `institutional_radar_signals`, `institutional_quarantine`, `data_provenance_meta` |
| **Macro & News** | `institutional_net_flows`, `participant_oi_positioning`, `news_catalysts`, `news_catalysts_tickers`, `news_catalyst_outcomes`, `ai_news_predictions` |
| **Operations** | `net_worth_snapshots`, `credit_cards`, `credit_card_otp_requests`, `trips`, `trip_activities`, `trip_groups`, `zepto_employees`, `zepto_salaries`, `zepto_expenses`, `zepto_store_income` |

---

## 5. Common Modification Points & Capability Map

| Goal | Key Files to Touch |
| :--- | :--- |
| **Add/edit REST API endpoint** | Relevant router in `earnings_engine/api/routers/<domain>.py` + mount in `server.py` |
| **Add a new SQLite database table** | `earnings_engine/data/db.py` (schema) + **`earnings_engine/data/turso_sync.py` (`SYNC_TABLES`)** |
| **Add technical / fundamental feature** | `earnings_engine/features/price_features.py` or `earnings_features.py` + `dataset.py` |
| **Modify reaction calculation / label** | `earnings_engine/features/labels.py` (`compute_reaction`) |
| **Add / update AI model in Consensus** | `earnings_engine/rate_limits.py` (`AVAILABLE_AI_MODELS`) + `consensus/model_runner.py` + `templates/stock_detail.html` |
| **Update Breakout / Swing / Confluence** | `earnings_engine/breakout/radar.py`, `earnings_engine/data/swing_ranges.py`, or `routers/tri_confluence.py` |
| **Modify Institutional Tracking / AMFI** | `earnings_engine/data/institutional.py` + `api/routers/institutional.py` |
| **Modify Options / Open Interest** | `earnings_engine/data/options.py` + `api/routers/options.py` |
| **Modify Dashboard UI tabs or modals** | `earnings_engine/reports/templates/dashboard/` + `earnings_engine/ui/js/dashboard.js` |
| **Modify Stock Detail view or AI matrix** | `earnings_engine/reports/templates/stock_detail.html` + `earnings_engine/ui/js/stock_detail.js` |
| **Add a new CLI command** | `earnings_engine/cli.py` |
| **Update Walk-Forward Backtest** | `earnings_engine/backtest/engine.py` |

---

## 6. Development Commands Reference

### Environment Activation
Always run within the project virtual environment:
```powershell
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
# Direct execution
.\.venv\Scripts\python.exe <command>
```

### Targeted Testing (Recommended Default)
```bash
# Run a specific test file
pytest tests/test_predict.py

# Run a single targeted test function
pytest tests/test_stock_api.py -k "test_get_stock_details"

# Run tests with verbose output
pytest -v tests/test_consensus.py
```

### Running the API Server & Dashboard
```bash
# Start dashboard and automatically launch browser (FastAPI on port 8000)
earnings-engine dashboard

# Run FastAPI server directly with live reload
python run_api.py
# Or:
uvicorn earnings_engine.api.server.py:app --host 0.0.0.0 --port 8000 --reload
```

### Data Ingestion
```bash
# Ingest full NSE universe (prices, earnings, calendar, market cap)
earnings-engine ingest --market NSE_ALL

# Fast incremental ingestion (missing earnings only)
earnings-engine ingest --market NSE_ALL --incremental

# Ingest specific tickers
earnings-engine ingest --ticker TCS.NS INFY.NS RELIANCE.NS

# Ingest institutional shareholding & AMFI fund portfolios
earnings-engine ingest-institutional --limit 500
```

### Prediction & Backtesting
```bash
# LightGBM 1-day earnings reaction prediction
earnings-engine predict --market NSE_ALL --days 14

# Kronos AI 14-day sequence trajectory (auto-detects CUDA GPU)
earnings-engine kronos-predict --market IN --device cuda:0

# Pre-compute & cache predictions
earnings-engine cache-predictions --market NSE_ALL --earnings-only --days 14

# Build Point-in-Time event dataset
earnings-engine build-dataset --market NSE_ALL

# Run quarterly walk-forward backtest
earnings-engine backtest --model gbm --threshold 0.5 --cost 0.001
```

### Error Ledger & Verification Tools
```bash
# Inspect open errors before starting work
python scripts/error_ledger.py open

# Scan error streams after finishing work
python scripts/error_ledger.py scan

# Check ledger health summary
python scripts/error_ledger.py summary

# Run full-system data audit and live-sync runner
python scripts/verify_and_sync_all_data.py
```
