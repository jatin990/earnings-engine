# Design Document: Smart Money Radar Lifecycle Tracking, Multi-Strategy Discovery & Forensic Intelligence

## Executive Summary
This design document defines the architectural upgrade for the **Smart Money Radar** subsystem to match the longitudinal discovery, strategy-driven categorization, and performance tracking capabilities of the **Breakout Radar**. The subsystem tracks when high-conviction institutional accumulation setups are first discovered, records their entry signal prices, calculates real-time outcome returns, tracks lifecycle milestones (e.g., active, target achieved, cooling off), and provides an in-depth forensic drawer with all participating institutions, historical quarterly income statements, and block deal logs.

---

## 1. Core Architecture & Requirements

### 1.1 Discovery & Signal Lifecycle Tracking
- **First Discovery Invariant**: When an equity qualifies under a Smart Money Strategy for the first time in a rolling evaluation cycle, an immutable signal record is persisted with `signal_date`, `signal_price`, `ideal_entry_price`, `target_price` (1:2 R:R baseline), and `stop_loss`.
- **Outcome Tracking**: Dynamic calculation of `outcome_return_pct = ((current_price - signal_price) / signal_price) * 100`, `max_gain_pct` (high-water mark since discovery), and `days_elapsed`.
- **Lifecycle States**:
  - `ACTIVE`: Accumulation active, trading between stop-loss and target.
  - `TARGET_HIT`: Realized gain $\ge$ strategy target price.
  - `COOLING_OFF`: Flow stabilization without distribution.
  - `DISTRIBUTION_EXIT`: Severe institutional selling or stop-loss breach.

### 1.2 Multi-Strategy Selectors
Equities are categorized and filtered via five explicit strategies:
1. **`WHALE_CONVICTION`**: `conviction_score >= 65.0`, Smart Money Inflow $\ge ₹10\text{ Cr}$, and FII/Super Investor dominance $\ge 60\%$.
2. **`BLOCK_DEAL_MOMENTUM`**: Single or clustered on-market buy block deals $\ge ₹25\text{ Cr}$ or $\ge 2$ distinct block trades within the active window.
3. **`DUAL_ACCELERATION`**: YoY PAT/EPS growth $\ge 20.0\%$ combined with positive institutional QoQ stake expansion ($> +0.50\%$).
4. **`DOMESTIC_ABSORPTION`**: Mutual Fund / DII inflow $\ge ₹25\text{ Cr}$ in small/mid-caps with expanding quarterly operating margins.
5. **`ALL_STRATEGIES`**: Unified view of all active setups across all strategies.

### 1.3 Forensics & Fundamental Trajectory
- **Cap Table Buyers**: Comprehensive list of all real entities (`fund_name`, `entity_type`, `category`, `stake_pct`, `change_pct`, `shares`, `buy_price`, `capital_cr`, `filing_quarter`).
- **Quarterly Income & Earnings**: Authentic quarterly financial statements per stock (`quarter`, `revenue_cr`, `net_profit_cr`, `operating_profit_cr`, `operating_margin_pct`, `eps`, `yoy_revenue_growth_pct`, `yoy_pat_growth_pct`).
- **Block Deals Activity**: Timestamped ledger of block/bulk transactions (`deal_date`, `client_name`, `deal_type`, `quantity`, `price`, `value_cr`, `pct_equity`).

---

## 2. Database Schema & Persistence

### 2.1 Enhanced `institutional_radar_signals`
```sql
CREATE TABLE IF NOT EXISTS institutional_radar_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    strategy TEXT NOT NULL DEFAULT 'WHALE_CONVICTION',
    company_name TEXT,
    industry TEXT,
    signal_date TEXT NOT NULL,
    signal_price REAL NOT NULL,
    ideal_entry_price REAL,
    target_price REAL,
    stop_loss REAL,
    risk_reward_ratio REAL,
    current_price REAL,
    current_date TEXT,
    outcome_return_pct REAL,
    max_gain_pct REAL,
    days_elapsed INTEGER DEFAULT 0,
    lifecycle_status TEXT DEFAULT 'ACTIVE',
    initial_score REAL,
    initial_dominance REAL,
    initial_smart_money_cr REAL,
    whale_count INTEGER DEFAULT 0,
    trigger_reason TEXT,
    is_active INTEGER DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (DATETIME('now')),
    updated_at TEXT NOT NULL DEFAULT (DATETIME('now')),
    UNIQUE (ticker, strategy, signal_date)
);

CREATE INDEX IF NOT EXISTS idx_inst_signals_strategy ON institutional_radar_signals(strategy);
CREATE INDEX IF NOT EXISTS idx_inst_signals_ticker ON institutional_radar_signals(ticker);
CREATE INDEX IF NOT EXISTS idx_inst_signals_status ON institutional_radar_signals(lifecycle_status);
```

### 2.2 `quarterly_financials` Table
```sql
CREATE TABLE IF NOT EXISTS quarterly_financials (
    ticker TEXT NOT NULL,
    quarter TEXT NOT NULL,
    period_end_date TEXT,
    revenue_cr REAL,
    net_profit_cr REAL,
    operating_profit_cr REAL,
    operating_margin_pct REAL,
    net_margin_pct REAL,
    eps REAL,
    yoy_revenue_growth_pct REAL,
    yoy_pat_growth_pct REAL,
    source TEXT DEFAULT 'exchange_filing',
    created_at TEXT DEFAULT (DATETIME('now')),
    updated_at TEXT DEFAULT (DATETIME('now')),
    PRIMARY KEY (ticker, quarter)
);

CREATE INDEX IF NOT EXISTS idx_qfin_ticker ON quarterly_financials(ticker);
CREATE INDEX IF NOT EXISTS idx_qfin_quarter ON quarterly_financials(quarter);
```

### 2.3 Cloud Synchronization Contract (`SYNC_TABLES`)
Both `institutional_radar_signals` and `quarterly_financials` are registered in `earnings_engine/data/turso_sync.py`:
- Registered in `SYNC_TABLES`.
- `updated_at`, `created_at`, and `period_end_date` mapped to `WATERMARK_CANDIDATE_COLUMNS`.

---

## 3. Backend Strategy & Forensic Engine

### 3.1 Strategy Evaluator & Signal Recorder
- **Module**: `earnings_engine/data/institutional_accumulation.py`
- Evaluates candidate equities from `institutional_holdings`, `shareholding_patterns`, and `institutional_block_deals`.
- For each active strategy:
  1. Computes quantitative metrics and filters qualifying stocks.
  2. Resolves or initializes the discovery record in `institutional_radar_signals` with `signal_date` and `signal_price` from `price_history`.
  3. Updates latest price, calculates outcome returns, peak gain, and days elapsed.

### 3.2 REST API Endpoints
- **`GET /api/v1/institutional/signals`**:
  - Query parameters: `strategy` (default `'ALL_STRATEGIES'`), `status` (`'active'`, `'all'`, `'closed'`), `sort_by` (`'return'`, `'score'`, `'capital'`, `'date'`), `limit` (default 60, max 200).
  - Returns paginated list of tracked signals with performance metrics.
- **`GET /api/v1/institutional/stock/{ticker}/forensics`**:
  - Path parameter: `ticker` (e.g. `'WELCORP.NS'`).
  - Returns complete forensic bundle:
    - `signal_timeline`: Discovery date, signal price, live price, target, stop loss, outcome return %, max gain %.
    - `buyers`: All institutional entities with fund name, category, stake %, shares, buy price, capital deployed ₹ Cr.
    - `quarterly_income`: Chronological quarters of Revenue ₹ Cr, PAT ₹ Cr, Operating Margin %, EPS, YoY growth %.
    - `block_deals`: List of block deals with date, buyer/seller, quantity, price, value ₹ Cr.

---

## 4. Frontend & UI Experience

### 4.1 Strategy Selector & Signal Table
- **Location**: `/dashboard#institutional` (Smart Money Radar sub-tab).
- **Strategy Bar**: Top pill switcher allowing instant toggle between:
  - `All Active Signals`
  - `🐋 Whale Conviction`
  - `⚡ Block Deal Momentum`
  - `📈 Dual Acceleration`
  - `🏢 Domestic Absorption`
- **Tracked Signal Table Columns**:
  - `Ticker & Company`
  - `Strategy Archetype`
  - `Discovery Date`
  - `Signal Price (₹)`
  - `Current Price (₹)`
  - `Outcome Return (% Gain/Loss)`
  - `Smart Money Capital (₹ Cr)`
  - `Whale Buyers / Deals`
  - `Score (0-100)`
  - `Lifecycle Status Badge`

### 4.2 Forensic Inspector Drawer (4 Tabs)
Clicking any setup row opens the deep inspector drawer:
- **Tab 1: Cap Table Buyers**: Full table of all funds, institution types, stake %, and capital deployed.
- **Tab 2: Quarterly Income & Trajectory**: High-density table & trend cards of historical quarterly revenue, net profit, margins, and EPS.
- **Tab 3: Block Deals Ledger**: Transaction logs of on-market block trades.
- **Tab 4: Discovery Signal History**: Lifecycle timeline showing trigger date, initial score, target/SL levels, and price trajectory.

---

## 5. Verification & Testing Strategy

1. **Migration & DB Tests**:
   - Verify `institutional_radar_signals` and `quarterly_financials` tables create cleanly with correct primary keys and indexes.
   - Verify `SYNC_TABLES` registration and bidirectional Turso cloud synchronization.
2. **Strategy Signal Discovery Tests**:
   - Test signal generation for all 4 strategies with mock/fixture data.
   - Verify immutable `signal_date` and `signal_price` preservation across re-runs.
   - Verify calculation of `outcome_return_pct` and `max_gain_pct`.
3. **Forensic API Tests**:
   - Test `/api/v1/institutional/signals` filtering by strategy and status.
   - Test `/api/v1/institutional/stock/{ticker}/forensics` payload integrity.
4. **Zero-Synthetic & Error Ledger Audit**:
   - Execute `python scripts/error_ledger.py scan` to ensure zero runtime exceptions.
