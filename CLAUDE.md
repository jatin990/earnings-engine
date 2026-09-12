# CLAUDE.md — Nexus Intelligence Platform (Earnings Engine)

> **Single Source of Truth** for Claude Code on the **Earnings Engine** repository.
> Contains core system architecture, strict operating rules, database sync contracts, and capability mapping.
> **CLI / Command Reference**: See [`COMMANDS.md`](./COMMANDS.md) for all ingestion, prediction, backtesting, server, and ledger commands.

---

## 1. System Overview

**Earnings Engine (Nexus Intelligence Platform)** is a quantitative equity research engine and multi-hub operations platform for **NSE India (`.NS`) and US equities**.

### Core Ecosystem & Scoped Hubs
- **Market & Quant Intelligence**: 13,133+ event Point-in-Time dataset; LightGBM + Platt scaling 1-day earnings reaction probabilities; Kronos AI 14-day neural price forecasting (PyTorch / CUDA); Multi-Model AI Consensus Engine (DeepSeek-R1, Llama-3.3-70B, Qwen-2.5-72B, Mistral-Large) via OpenRouter / OmniRoute gateway.
- **Scanners & Radar**: Breakout Radar (`/dashboard#breakout`), Swing & Tri-Confluence Radar (`...#swing`, `...#tri-confluence`), Options Chain & Participant OI Pulse (`...#options`), Premarket Pulse (`...#premarket`), News Catalysts & Impact (`...#news`), and Autonomous Trading Agents (`...#trading-agents`).
- **Institutional Forensics**: Shareholding patterns, QoQ fund accumulation flows, AMFI mutual fund portfolio tracking, provenance tracking, and data quarantine (`/dashboard#institutional`).
- **Operations & Lifestyle**: Net Worth consolidation (`/net-worth`), Credit Cards & Rewards (`/credit-cards`), Trips & Expense Settlement (`/trips`), and Zepto Dark Store Operations & P&L (`/zepto`).
- **Security & Access**: Nexus Gateway (`/portal`), Passcode engine (`NEXUS-<CODE>`), 6-digit email OTPs, HMAC-SHA256 session tokens, and fine-grained RBAC.

---

## 2. Critical Operating Rules & Constraints

### 2.1 Git Commit & Remote Push Protocol
- **Strict Rule**: **Always create a git commit and push changes to the remote branch upon completing each task.**
- Follow conventional commits (`feat:`, `fix:`, `refactor:`, `test:`, `docs:`) and include required co-authorship attribution.

### 2.2 Error Ledger & Self-Healing Protocol
Maintain zero-error hygiene using `scripts/error_ledger.py`:
1. **Pre-Task Check**: `python scripts/error_ledger.py open`
2. **Post-Task Verification**: `python scripts/error_ledger.py scan` (verify no new exceptions introduced).
3. **Resolution Logging**: `python scripts/error_ledger.py resolve <error_id> "<resolution details>"`

### 2.3 Strict Point-in-Time (PIT) Guarantee
- **Never leak future information**: In `features/`, `dataset.py`, and `backtest/`, feature computation for an event date $T$ must strictly filter price bars up to $T-1$ (`prices.loc[prices.index <= asof_date]`).
- Post-earnings reaction: $\text{reaction\_return} = (\text{close}(T+1) / \text{close}(T-1)) - 1$.
- Binary label: $1$ if $\text{reaction\_return} > 0$, else $0$. Return `None` if $T-1$ or $T+1$ bars are absent or trading gap $>10$ days.
- Walk-forward backtests must split chronologically with per-fold model retraining.

### 2.4 Universal Timeframe & Temporal Association Protocol
Every metric, delta, signal, accumulation flow, momentum score, and forecast **MUST ALWAYS explicitly state its window or baseline** in backend payloads and UI cards:
- Returns/Momentum: `7D Return: +4.2%`, `30D Return: -1.8%`, `52W High / Low` (never standalone `+X%`).
- Institutional Flows: `Funds: +4 / -0 (QoQ / ~90d)`, `Filing: Q1 FY27 vs Q4 FY26`.
- Volume/Volatility: `Volume Surge: 2.4x (5D vs 63D avg)`, `21-Day Annualized Volatility`.
- AI Predictions: `Forecast Horizon: 14 Trading Days`, `Reaction Window: 1-Day Post-Earnings`.
- Freshness: Explicit timestamp or state (`As of 2026-09-12 15:30 IST`, `🟢 Live Quote`, `📊 EOD Snapshot`).

### 2.5 Strict Anti-Fabrication & Real-Data Integrity
- **Zero-tolerance for mock/dummy data**: NEVER use static placeholders, seeded pseudo-random values (`hashlib.md5(...) % N`), or dummy fallbacks in production code.
- If data is missing or markets are closed, return `None`, `0.0`, or `[]` with an honest status tag (`Market Closed · Weekend Snapshot`, `No Institutional Filings On Record`).

### 2.6 On-Demand AI Inference & Zero-Token Default
- Never trigger automated LLM inference or OmniRoute gateway calls on page load, modal open, or table render.
- Ingestion and data inspection default to zero token usage; AI inference is strictly on-demand via explicit user click.

### 2.7 Remote DB Sync & Mandatory `SYNC_TABLES` Rule
The system operates on local SQLite (`data/cache/prices/prices.sqlite3` or `earnings_engine.db`) with cloud Turso replication via `earnings_engine/data/turso_sync.py`:
- **MANDATORY Rule for New Tables**: Whenever ANY new SQLite table is added anywhere in the codebase:
  1. Add table name to `SYNC_TABLES` in `earnings_engine/data/turso_sync.py`.
  2. If the table has a date/timestamp column (`updated_at`, `created_at`, `scanned_at`, `date`, `asof_date`, `timestamp`), ensure it exists in `WATERMARK_CANDIDATE_COLUMNS` (and `DATE_ONLY_COLUMNS` if `YYYY-MM-DD`).
  3. Ensure valid SQLite/libSQL syntax compatible with `INSERT OR IGNORE` union merge.
- Always encapsulate remote Turso calls with local SQLite fallbacks to guard against network timeouts.

### 2.8 FastAPI Routing Precedence
- In `server.py` and routers, **always define explicit static/literal routes before parameterized routes** (e.g., `/api/v1/watchlist/quotes` *before* `/api/v1/watchlist/{name}`).

### 2.9 Ticker Symbol Suffixes & Market Conventions
- Indian equities require the `.NS` suffix (`TCS.NS`, `RELIANCE.NS`). US equities have no suffix.
- Use `market_of(ticker)` from `earnings_engine.config` to resolve market type (`"IN"` vs `"US"`).

### 2.10 Agent Performance & Workflow Efficiency
- **Targeted Test Execution**: Run targeted tests during development (`.\.venv\Scripts\python.exe -m pytest tests/<test_file>.py -k "<test_func>"`). Never run full-suite or slow E2E tests (`test_stock_detail_e2e.py`) during iterative tasks.
- **Batch Tool Calls**: Concurrently issue multiple independent `Read`, `Grep`, or `Glob` calls in a single response turn.
- **Context Hygiene**: Bound tool outputs with `head_limit`, specific `grep` patterns, and line offsets. Avoid dumping large payloads or raw logs.
- **Memory Persistence**: Persist modified database schemas, table column orders, and API contracts to `.claude/projects/.../memory/` so they survive context compaction.

---

## 3. High-Level Architecture & Code Structure

```
earnings-engine/
├── CLAUDE.md                         # Authoritative Agent Guidelines & Operating Rules
├── AGENTS.md                         # Pointer to CLAUDE.md
├── COMMANDS.md                       # Comprehensive CLI & operational command reference
├── scripts/                          # Operational scripts (error_ledger.py, verify_and_sync_all_data.py)
├── earnings_engine/
│   ├── config.py                     # App settings, environment vars, market_of()
│   ├── rate_limits.py                # Sliding-window per-model rate limiter
│   ├── dataset.py                    # PIT dataset generation & feature assembly
│   ├── predict.py                    # LightGBM scoring pipeline
│   ├── kronos_predictor.py           # Kronos AI 14-day neural forecast runner
│   ├── api/                          # FastAPI app (server.py) & 22 domain routers in routers/
│   ├── consensus/                    # Multi-Model AI Consensus (runner, aggregator, context_builder, storage)
│   ├── brokers/                      # Broker integrations (Angel One, Zerodha, Dhan, Fyers, TOTP)
│   ├── trading_agents/               # Autonomous execution agents & strategy modules
│   ├── data/                         # SQLite connection pools, turso_sync.py (SYNC_TABLES), scrapers & providers
│   ├── features/                     # PIT technical (price_features.py) & earnings (earnings_features.py) metrics
│   ├── models/                       # Classifiers (LightGBM + Platt calibration, baseline heuristics)
│   ├── backtest/                     # Quarterly walk-forward backtesting engine
│   ├── breakout/                     # Breakout Radar detection algorithms & tracking
│   ├── reports/                      # HTML/CSV report rendering & Jinja2 templates (dashboard/, stock_detail.html)
│   └── ui/                           # Frontend static assets (CSS, modular JS, dashboard.js)
└── tests/                            # Pytest suite
```

---

## 4. Capability Map (Quick Modification Reference)

| Task / Goal | Key Files to Touch |
| :--- | :--- |
| **Add / edit REST API endpoint** | Domain router in `earnings_engine/api/routers/<domain>.py` + mount in `server.py` |
| **Add a new SQLite database table** | `earnings_engine/data/db.py` (schema) + **`earnings_engine/data/turso_sync.py` (`SYNC_TABLES`)** |
| **Add technical / fundamental feature** | `earnings_engine/features/price_features.py` or `earnings_features.py` + `dataset.py` |
| **Modify reaction calculation / label** | `earnings_engine/features/labels.py` (`compute_reaction`) |
| **Add / update AI model in Consensus** | `earnings_engine/rate_limits.py` (`AVAILABLE_AI_MODELS`) + `consensus/model_runner.py` |
| **Update Breakout / Swing / Confluence** | `earnings_engine/breakout/radar.py`, `earnings_engine/data/swing_ranges.py`, or `routers/tri_confluence.py` |
| **Modify Institutional Tracking / AMFI** | `earnings_engine/data/institutional.py` + `api/routers/institutional.py` |
| **Modify Options / Open Interest** | `earnings_engine/data/options.py` + `api/routers/options.py` |
| **Modify Dashboard UI tabs / modals** | `earnings_engine/reports/templates/dashboard/` + `earnings_engine/ui/js/dashboard.js` |
| **Modify Stock Detail view / AI matrix** | `earnings_engine/reports/templates/stock_detail.html` + `earnings_engine/ui/js/stock_detail.js` |
| **Add a new CLI command** | `earnings_engine/cli.py` + document in `COMMANDS.md` |
| **Update Walk-Forward Backtest** | `earnings_engine/backtest/engine.py` |
