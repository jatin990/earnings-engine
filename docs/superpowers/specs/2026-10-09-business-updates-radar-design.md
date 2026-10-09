# Business Updates Radar & Pre-Earnings Alpha Studio — Architecture Specification

## 1. Overview & Business Objectives
Investors and swing traders in Indian equities (NSE/BSE) often find that standard quarterly earnings results are preceded by **Corporate Business & Operational Updates** (e.g., PC Jeweller issuing quarterly business updates, Titan revenue trajectories, DMart standalone revenues, Godrej Properties / Macrotech pre-sales, Bajaj Auto / Tata Motors monthly volume & dispatch metrics, HDFC Bank / Federal Bank advances & deposit updates).

These operational disclosures typically occur 5 to 20 days prior to the official Board Meeting for Financial Results. They serve two critical functions:
1. **Immediate Alpha**: Strong volume/sales growth triggers rapid price discovery and multi-day swing momentum.
2. **Predictive Lead Indicator**: Provides an empirical forecast of upcoming quarterly financial performance (beating or missing Street consensus) allowing traders to position ahead of official declared results.

This subsystem provides:
- A dedicated **Business Updates Screen & Feed** in News Harvester isolating business/operational updates from general news and final result declarations.
- A **Predictive Seasonality & Anticipated Schedule Engine** that predicts when specific companies are due to drop their operational updates based on historical quarterly/monthly disclosure cycles.
- A **Pre-Earnings Runup & Outcome Bridge** that correlates update reactions ($T_{update}$) to official result reactions ($T_{results}$).

---

## 2. Taxonomy & Ingestion Rules

### 2.1 Classification Criteria
A news or exchange announcement is classified as `Business Updates & Operational Disclosures` when it matches any of the following patterns and is **NOT** a standard declared result or board meeting intimation:
- **Quarterly Business Updates**: `"business update for q"`, `"quarterly business update"`, `"key operational highlights"`, `"operational performance update"`, `"quarterly operating update"`, `"q1 business update"`, `"q2 business update"`, `"q3 business update"`, `"q4 business update"`.
- **Monthly Sales & Dispatches**: `"monthly sales"`, `"production and sales"`, `"production and offtake"`, `"monthly dispatch"`, `"vehicle sales"`, `"jlr wholesales"`.
- **Real Estate Bookings & Pre-Sales**: `"quarterly pre-sales"`, `"quarterly bookings"`, `"gross booking value"`, `"collections update"`.
- **Banking / NBFC Operational Numbers**: `"gross advances and deposits"`, `"cASA ratio update"`, `"quarterly loan growth"`, `"disbursements update"`.
- **Order Inflow & Execution Updates**: `"quarterly order inflow"`, `"order book update"`, `"capacity commissioning"`.

### 2.2 Exclusions
- Standard Board Meeting intimations (`"board meeting to consider financial results"`).
- Official declared Financial Results (`"un-audited financial results"`, `"audited financial results"` where full P&L is submitted as Form 33).
- Routine administrative/secretarial filings without operational or business performance metrics.

---

## 3. Data Model & Storage

### 3.1 SQLite Schema: `business_update_schedules`
Tracks recurring corporate update cadence and historical release timestamps:

```sql
CREATE TABLE IF NOT EXISTS business_update_schedules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    company_name TEXT,
    update_type TEXT NOT NULL, -- 'QUARTERLY_BUSINESS_UPDATE', 'MONTHLY_SALES', 'REALTY_BOOKINGS', 'BANKING_ADVANCES'
    frequency TEXT NOT NULL, -- 'QUARTERLY', 'MONTHLY'
    typical_days_after_period INTEGER DEFAULT 5, -- Days after quarter/month end when company drops update
    last_update_date TEXT, -- YYYY-MM-DD
    last_update_headline TEXT,
    last_update_reaction_1d REAL,
    last_update_reaction_3d REAL,
    next_expected_window_start TEXT, -- YYYY-MM-DD
    next_expected_window_end TEXT, -- YYYY-MM-DD
    confidence_score REAL DEFAULT 0.85,
    status TEXT DEFAULT 'ANTICIPATED', -- 'ANTICIPATED', 'DROPPED', 'OVERDUE'
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(ticker, update_type)
);

CREATE INDEX IF NOT EXISTS idx_bus_sched_ticker ON business_update_schedules (ticker);
CREATE INDEX IF NOT EXISTS idx_bus_sched_window ON business_update_schedules (next_expected_window_start, next_expected_window_end);
```

### 3.2 Registration in `turso_sync.py` (`SYNC_TABLES`)
- `SYNC_TABLES.append("business_update_schedules")`
- Watermark candidates: `updated_at`, `created_at`, `last_update_date`
- Date-only handling for `last_update_date`, `next_expected_window_start`, `next_expected_window_end`.

---

## 4. API Subsystem (`earnings_engine/api/routers/news.py`)

### 4.1 Endpoints
1. `GET /api/v1/news/business-updates`
   - Parameters: `watchlist`, `days`, `category` (Quarterly, Monthly, Realty, Banking), `search`, `limit`.
   - Returns list of verified business update filings with sentiment, extracted quantitative metrics (e.g. YoY growth, revenue numbers), and price reactions.
2. `GET /api/v1/news/business-updates/schedules`
   - Parameters: `status` (`ANTICIPATED`, `DROPPED`, `OVERDUE`), `window_days` (e.g. within next 7/14 days), `frequency`.
   - Returns anticipated business update timetable with countdown, expected dates, and past quarter historical performance.
3. `POST /api/v1/news/business-updates/sync-schedules`
   - Recalculates expected dates based on recent calendar quarter/month ends and historical announcement cadences.

---

## 5. UI Architecture (`_catalysts.html` & `catalysts.js`)

### 5.1 Subtabs in Catalysts & News Hub
1. **📰 Live News Feed**: General market-wide catalysts, order wins, FDA approvals, litigation.
2. **🏢 Business Updates Feed**: Dedicated feed of operational disclosures, pre-earnings notices, sales numbers, and key operational highlights.
3. **🗓️ Anticipated Updates Schedule**: Interactive calendar / timeline cards showing which companies are expected to report business updates over the next 1–14 days.
4. **📊 Trade Outcomes**: Historical post-catalyst return analysis.

### 5.2 UI Components & Metrics
- **Top KPI Cards**:
  - `Quarterly Updates Dropped`: Count of updates for the current quarter cycle.
  - `Bullish Sentiment Bias`: % of business updates showing positive operational growth.
  - `Next 7 Days Anticipated`: Count of companies in their expected disclosure window.
  - `Avg Pre-Earnings Drift`: Average price move between update date and official result date.
- **Filter Toolbar**:
  - Filter by Update Type (`All`, `Quarterly Update`, `Monthly Sales`, `Realty Pre-Sales`, `Banking Advances`).
  - Search ticker / keyword.
  - Timeframe filter (`7D`, `14D`, `30D`, `Current Quarter Window`).
- **Interactive Inspector Drawer**:
  - Displays full disclosure body, extracted metrics, timeline to upcoming Board Meeting for Results, and past 4 quarters update reactions.

---

## 6. Testing & Quality Assurance
- **Unit Tests**:
  - `test_business_updates_classification`: Validate regex pattern matches and non-result exclusions.
  - `test_anticipated_schedules_calculation`: Validate expected window dates given quarter-end dates (e.g. Q3 ends Dec 31 -> Jan 2–7 window).
  - `test_business_updates_api_contracts`: Validate `/api/v1/news/business-updates` and `/api/v1/news/business-updates/schedules`.
- **Frontend Validation**:
  - Run `node -c` on modified JS files.
  - Check zero-token default and proper empty states.
