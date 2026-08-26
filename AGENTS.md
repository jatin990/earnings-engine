# Earnings Engine — Agent Master Guidelines & Knowledge Base

> **Primary Instruction for AI Agents**: This document is the single source of truth for repository architecture, operating rules, error ledger protocols, subsystem design, database schemas, feature engineering, data flows, CLI workflows, and common modification points. Read and adhere strictly to these guidelines before making changes.

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
- **Push Policy**: Do **NOT** push to the remote repository after every individual change. Push to remote once every **5 local commits** (or when explicitly commanded by the user).

### 1.3 Execution Environment
- **OS**: Windows (PowerShell / pwsh)
- **Python Virtual Environment**: `.\.venv\Scripts\python.exe` (always invoke through `.venv` or ensure virtualenv is activated)

### 1.4 Universal Timeframe & Temporal Association Protocol
**Mandatory Rule Across the Hub, Backend APIs, UI Dashboards, and Reports**:
Every metric, delta, signal, accumulation flow, momentum score, and forecast **MUST ALWAYS explicitly state and display its associated timeframe, period, or comparison horizon**.
- **Institutional Flows & Funds**: Always specify the reporting window (e.g., `Funds: +4 / -0 (QoQ / ~90d)`, `Latest Filing: Q1 FY27 vs Q4 FY26`). Never display bare fund counts or stake changes without the quarterly/temporal baseline.
- **Price Returns & Momentum**: Always label the exact interval (e.g., `7D Return: +4.2%`, `30D Return: -1.8%`, `52W High / Low`). Never display standalone "+X%" without the timeframe.
- **Volume & Volatility Surges**: Always state the comparison window (e.g., `Volume Surge: 2.4x (5D avg vs 63D baseline)`, `21-Day Annualized Volatility`).
- **AI Forecasting & Consensus**: Always display the explicit prediction timeframe (e.g., `Forecast Horizon: 14 Trading Days`, `Kronos 14-Day Trajectory`, `Quarter Repeater: Q2 FY27 Target`).
- **Catalysts & Scanner Setups**: Always include both publication recency (`Published 4h ago / 2026-08-26`) and expected catalyst impact horizon (`Impact Window: 1–3 Days`).
- **Timestamps & Freshness**: Every table, card, drawer, and modal MUST present its last-updated timestamp or data freshness indicator (e.g., `As of 2026-08-26 15:30 IST`, `Market Feed: 🟢 Live Quote` or `📊 EOD Snapshot`).

---

## 2. Project Architecture & Directory Layout

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
│   ├── dataset.py                    # Event dataset generation & historical aggregation
│   ├── predict.py                    # GBM upcoming earnings scoring pipeline
│   ├── kronos_predictor.py           # Kronos AI 14-day price sequence forecast
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
│   │   ├── auth.py                   # Nexus Authentication, OTP, session tokens & RBAC
│   │   ├── passcodes.py              # Passcode generation, validation & scope enforcement
│   │   ├── prices.py                 # Daily OHLCV price ingestion, caching & indicators
│   │   ├── earnings.py               # Corporate earnings dates, EPS estimates & surprises
│   │   ├── watchlists.py             # Watchlist management (SQLite + Turso sync)
│   │   ├── universe.py               # Market universe resolution (IN, NSE_ALL, US, etc.)
│   │   ├── market_context.py         # 52W range, week high/low around earnings
│   │   ├── predictions.py            # Kronos prediction persistence and audit trail
│   │   ├── swing_ranges.py           # Swing ranges and cycle timing history
│   │   ├── strategy_auditor.py       # Multi-strategy backtest and outcome auditing
│   │   └── coverage.py               # Price & earnings data coverage reporting
│   ├── features/                     # Point-in-Time (PIT) Feature Engineering
│   │   ├── price_features.py         # Technical momentum, volatility & volume metrics
│   │   ├── earnings_features.py      # Historical surprise streak & beat frequency
│   │   └── labels.py                 # 1-day post-earnings reaction calculation
│   ├── models/                       # Predictive Models & Heuristics
│   │   ├── base.py                   # BaseModel abstract class
│   │   ├── baseline.py               # AlwaysUp and PastUpRateBaseline heuristics
│   │   ├── classifier.py             # LightGBM Classifier with Platt probability calibration
│   │   └── registry.py               # Model registration & lookup
│   ├── backtest/
│   │   └── engine.py                 # Quarterly walk-forward backtesting framework
│   ├── breakout/
│   │   └── radar.py                  # Breakout Radar scanner, tracking & outcome verification
│   ├── reports/
│   │   ├── render.py                 # Report generation (HTML/CSV/Telegram/Email)
│   │   ├── checker.py                # Database verification & report audit subworkflow
│   │   └── templates/                # Jinja2 & HTML templates (stock_detail.html, portal.html, dashboard/)
│   └── ui/                           # Frontend static assets (CSS, JS, dashboard.js)
```

---

## 3. Overall Nexus Platform Architecture

```mermaid
graph TD
    User([User / Browser / API Client]) --> Gateway[Nexus Gateway / Portal : /portal]
    
    subgraph Nexus Security & Access Control
        Gateway --> AuthMiddleware[Nexus Auth Middleware]
        AuthMiddleware --> TokenAuth[HMAC-SHA256 Token Auth 'nexus_session']
        AuthMiddleware --> PasscodeAuth[Passcode Engine 'NEXUS-MASTER' / Scoped Invites]
        AuthMiddleware --> OTPAuth[6-Digit Email OTP Engine via Resend / SMTP]
        PasscodeAuth --> RBAC[Fine-Grained RBAC & Scope Verifier]
    end

    subgraph Nexus Scoped Application Hubs
        RBAC --> HubDashboard[1. Market Intelligence & Earnings Hub : /dashboard]
        RBAC --> HubStock[2. Stock Detail & AI Consensus Engine : /stock/:ticker]
        RBAC --> HubBreakout[3. Breakout Radar & Scanner Hub : /dashboard#breakout]
        RBAC --> HubWealth[4. Net Worth & Asset Allocation Hub : /net-worth]
        RBAC --> HubCards[5. Credit Card & Rewards Hub : /credit-cards]
        RBAC --> HubTrips[6. Travel & Trips Hub : /trips]
        RBAC --> HubAdmin[7. Passcode Management & Admin Hub : /passcodes]
    end

    subgraph Intelligence & Quantitative Pipelines
        HubStock --> Consensus[Multi-Model AI Consensus Engine]
        Consensus --> Models[DeepSeek-R1 | Llama-3.3-70B | Qwen-2.5-72B | Mistral-Large]
        HubStock --> Kronos[Kronos AI 14-Day Deep Sequence Forecast]
        HubDashboard --> LightGBM[LightGBM Directional Classifier]
        HubBreakout --> RadarScanner[Breakout Radar Algorithm]
    end

    subgraph Data & Persistence Layer
        Consensus & Kronos & LightGBM & RadarScanner & HubWealth & HubCards --> Storage[SQLite Storage : prices.sqlite3 / earnings_engine.db]
        Storage <--> Turso[Turso Cloud DB Replication]
    end
```

### 3.1 Nexus Scoped Hub Specifications
1. **Nexus Gateway & Portal (`/portal`)**:
   - Master entry point for authentication, onboarding, hub switching, and session management.
   - Handles passcode entry, OTP verification flows, and direct deep-linking via `?code=NEXUS-XXXXXX`.
2. **Market Intelligence & Earnings Hub (`/dashboard`, `/stock/{ticker}`)**:
   - 13,133+ event Point-in-Time dataset with LightGBM earnings reaction probability estimation.
   - Multi-Model AI Consensus Engine featuring per-model rate limiting, individual execution triggers, and structured schema extraction.
   - Kronos AI deep sequence forecasting (14-day price paths with support/resistance levels).
   - Real-time stock quotes, deliverable volume spikes, 52-week position analysis, and EPS derivation engine.
3. **Breakout Radar Hub (`/dashboard#breakout`)**:
   - Automated scanner detecting compression breakouts, volume surges, and 52-week momentum setups across NSE All, Nifty 50, and custom universes.
   - Tracks detected breakouts and audits real-world post-signal performance.
4. **Credit Cards & Wealth Hub (`/credit-cards`, `/net-worth`)**:
   - Credit card statement cycle management, rewards optimization by spend category, and bill payment tracking.
   - Net worth consolidation across equities, mutual funds, provident funds (EPF/PPF), real estate, and liquid cash.
5. **Admin & Passcode Hub (`/passcodes`, `/api/v1/auth/*`)**:
   - Generates scoped, single-use, or permanent access passcodes (`NEXUS-<CODE>`) with fine-grained hub permissions and device tracking.

---

## 4. Comprehensive Knowledge Base

### 4.1 Database Architecture & Table Schemas (`prices.sqlite3` / `earnings_engine.db`)
The storage layer uses a centralized SQLite database (`data/cache/prices/prices.sqlite3` or `earnings_engine.db`), backed by optional remote Turso synchronization (`TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN`).

| Table Name | Primary Key / Index | Description & Columns |
| :--- | :--- | :--- |
| `price_history` | `(ticker, date)` | Daily OHLCV price series (`open`, `high`, `low`, `close`, `volume`). |
| `earnings_history` | `(ticker, earnings_date)` | Corporate earnings calendar (`eps_estimate`, `eps_reported`, `surprise_pct`). |
| `earnings_freshness` | `(ticker)` | Ingestion tracking timestamp (`fetched_at`). Max age 1 day unless `--force`. |
| `ticker_metrics` | `(ticker, as_of_date)` | Once-per-day cache of price-derived report fields (`week_change`, `pct_from_52w_high/low`, `thirty_day_return_pct`, `earnings_week_move_pct`). |
| `ticker_market_cap` | `(ticker)` | Fundamental company market capitalization and fetch timestamp (`fetched_at`). |
| `event_dataset` | `(ticker, earnings_date)` | Built point-in-time dataset containing features, labels, and reaction returns. |
| `consensus_predictions` | `(id)` / `(ticker, event_date)` | Multi-model AI consensus predictions, model breakdowns, target prices, stop losses, and settlement auditing. |
| `kronos_predictions` | `(id)` / `idx_kronos (ticker, run_at DESC)` | 14-day Kronos AI deep sequence forecasts, support, resistance, and price trajectories. |
| `breakout_radar` | `(id)` / `(ticker, detected_at)` | High-conviction breakout setups, trigger price, targets, stop loss, and outcome logs. |
| `watchlists` | `(name, ticker)` | User watchlists (`swing`, `my_watchlist`, etc.) with Turso Cloud replication. |
| `universes` | `(universe_name, ticker)` | Ticker universe memberships (`IN`, `US`, `NSE_ALL`, `NSE_LARGE_CAP`, custom). |
| `universe_freshness` | `(universe_name)` | Universe metadata cache freshness (`fetched_at`). |
| `swing_ranges` | `(watchlist, ticker)` | Support and resistance channel bounds, cycle counts, and user vs auto source. |
| `swing_cycle_history` | `(watchlist, ticker, cycle_idx)` | Historical swing cycle durations and channel extremes. |
| `strategy_predictions` | `(id)` / `(strategy_name, ticker, entry_date)` | Multi-strategy forecast log for systematic performance auditing. |
| `strategy_audit_logs` | `(id)` / `(prediction_id)` | Realized return, win/loss status, and settlement metrics per strategy signal. |

---

### 4.2 Point-in-Time (PIT) Feature Engineering & Labels

#### 1. Label Computation (`features/labels.py`)
- Post-earnings reaction is computed as:
  $$\text{reaction\_return} = \frac{\text{close}(T+1)}{\text{close}(T-1)} - 1$$
- Binary classification label:
  $$\text{label} = \begin{cases} 1 & \text{if } \text{reaction\_return} > 0 \\ 0 & \text{otherwise} \end{cases}$$
- `compute_reaction()` returns `None` if $T-1$ or $T+1$ price bars are missing, if the trading day gap exceeds 10 days, or if prices are non-positive.

#### 2. Price Technical Features (`features/price_features.py`)
Requires a minimum of 70 trading days of historical price data before `asof_date` ($T-1$):
- `ret_5d`, `ret_21d`, `ret_63d`: Trailing momentum returns.
- `vol_21d`: 21-day annualized volatility.
- `vol_ratio_5d_63d`: Short-to-medium term volatility compression/expansion ratio.
- `volume_ratio_5d_63d`: Volume surge indicator.
- `abs_ret_mean_21d`: Mean absolute daily return over 21 trading sessions.
- `dist_52w_high`, `dist_52w_low`: Percentage distance from 52-week high and low.

#### 3. Earnings Track Record Features (`features/earnings_features.py`)
Computed strictly from earnings events prior to the current announcement:
- `n_past_events`: Number of historical earnings releases available.
- `past_reaction_mean`: Mean historical post-earnings reaction return.
- `past_reaction_std`: Volatility/dispersion of past post-earnings moves.
- `past_up_rate`: Fraction of past earnings resulting in a positive reaction.
- `last_reaction_return`: Reaction return on the immediately preceding earnings date.
- `last_surprise_pct`: EPS surprise percentage on the immediately preceding earnings date.

---

### 4.3 Multi-Model AI Consensus Engine (`consensus/`)
- **Parallel AI Architecture**:
  - `deepseek/deepseek-r1`: Deep reasoning & chain-of-thought analysis.
  - `meta-llama/llama-3.3-70b-instruct`: Institutional macro & fundamental momentum.
  - `qwen/qwen-2.5-72b-instruct`: Algorithmic structure & volume pattern recognition.
  - `mistralai/mistral-large` (fallback `google/gemini-2.0-flash-001`): News catalyst & filing analysis.
- **Workflow**:
  1. `context_builder.py` aggregates point-in-time stock data: live prices, swing momentum, deliverable volume, 3Q EPS surprise quality, and news catalysts.
  2. `model_runner.py` executes parallel asynchronous queries to OpenRouter / LLM endpoints.
  3. `rate_limits.py` tracks sliding-window RPM (requests per minute) and RPD (requests per day) per model.
  4. **Single-Model Partial Execution**: When the user triggers an individual model (e.g. `⚡ Run DeepSeek-R1`), only that model is queried. Its new prediction is merged with existing cached outputs from the other models, and `aggregator.aggregate_predictions()` re-computes the unified consensus verdict.
  5. `storage.py` records predictions with settlement dates for accuracy auditing.

---

### 4.4 Predictive Models & Walk-Forward Backtesting

#### 1. Models (`models/`)
- `GBClassifier` (`gbm`): LightGBM classifier with Platt probability calibration (`CalibratedClassifierCV(method="sigmoid", cv=3)` when $N \ge 150$).
- `PastUpRate` (`past_up_rate`): Empirical Bayes shrinkage model regularizing ticker-specific up rates toward the global universe base rate (shrinkage factor = 4.0).
- `AlwaysUp` (`always_up`): Base rate benchmark.
- `Kronos AI`: Deep neural sequence model generating 14-day price paths with support/resistance levels (GPU accelerated via `--device cuda:0`).

#### 2. Walk-Forward Backtesting Engine (`backtest/engine.py`)
- Simulates realistic quarterly out-of-sample deployment without future data leakage.
- `BacktestConfig`: `initial_train_frac = 0.4`, `test_window_days = 90`, `cost_per_trade = 0.001` (10 bps slippage/commission).
- Trade simulation:
  - Long if $\hat{p} \ge \text{threshold}$ (e.g. 0.50).
  - Short if $\hat{p} \le 1 - \text{threshold}$.
  - Net return: $\text{trade\_return} = \text{side} \times \text{reaction\_return} - \text{cost\_per\_trade}$.
- Metrics: Win rate, coverage, Sharpe ratio per event, profit factor, and maximum drawdown.

---

### 4.5 End-to-End Data Flows

#### Ingestion Flow
```
CLI: earnings-engine ingest --market NSE_ALL
  ├── data/prices.py: Ingest OHLCV prices (ThreadPoolExecutor 10 workers, batch 50, 2s delay)
  ├── data/earnings.py: Ingest earnings calendar & EPS surprise history
  └── data/universe.py: Ingest & update market cap database
```

#### Dataset Construction Flow
```
CLI: earnings-engine build-dataset
  └── dataset.py: build_dataset()
        ├── Load prices & earnings from SQLite
        ├── features/labels.py: compute_reaction()
        ├── features/price_features.py: compute_price_features()
        ├── features/earnings_features.py: compute_earnings_features()
        └── Save unified rows to SQLite `event_dataset` table
```

#### Prediction & Report Generation Flow
```
CLI: earnings-engine upcoming-results --market NSE_ALL --days 14
  ├── data/earnings.py: upcoming_earnings() look-ahead window
  ├── data/market_context.py: enrich_upcoming_results() (52W range, week high/low, quality scores)
  ├── predict.py: score with LightGBM / Kronos AI
  └── reports/render.py: generate styled HTML reports & CSV exports
```

---

## 5. Critical Engineering Quirks & Gotchas

> [!IMPORTANT]
> **1. Point-in-Time (PIT) Guarantee**:
> In `features/` and `dataset.py`, never leak future information. All feature computation for event date $T$ must strictly filter `prices.loc[prices.index <= asof_date]` where `asof_date` is the trading day before earnings announcement ($T-1$).

> [!WARNING]
> **2. FastAPI Route Precedence**:
> In `earnings_engine/api/server.py`, explicit literal routes (e.g. `/api/v1/watchlist/quotes`, `/api/v1/watchlist/all`, `/api/v1/watchlist/names`, `/api/v1/consensus/models`) **MUST ALWAYS** be defined **before** parameterized routes like `/api/v1/watchlist/{name}`. Otherwise, FastAPI matches literal route strings as path parameters.

> [!TIP]
> **3. Turso Remote Database Error Handling**:
> When querying remote Turso instances, always encapsulate calls with local SQLite fallback in case of network timeouts (`ConnectionResetError` / `ReadTimeout`).

> [!NOTE]
> **4. yfinance Symbol Suffixes & Aliases**:
> Indian NSE equities require the `.NS` suffix (e.g., `TCS.NS`, `RELIANCE.NS`). Maintain symbol alias mappings where tickers have renamed on NSE (e.g., `STERTECH.NS` $\rightarrow$ `STLTECH.NS`).

> [!TIP]
> **5. Rate Limit Sliding Windows**:
> OpenRouter and LLM APIs enforce strict RPM and daily quotas. `RateLimitTracker` tracks sliding-window deques across 1m, 1h, and 24h intervals and captures response headers (`x-ratelimit-remaining`, `x-ratelimit-reset`).

---

## 6. Common Modification Points & Capability Map

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
| **Modify Swing Range Detection or Scan** | `earnings_engine/data/swing_ranges.py` + `dashboard_api.py` |
| **Modify Breakout Radar Scanning Logic** | `earnings_engine/breakout/radar.py` |

---

## 7. CLI Command Quick Reference

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
