# Smart Money Radar Lifecycle Tracking & Forensic Intelligence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build longitudinal discovery tracking, strategy-driven categorization, outcome return measurement, and deep forensic inspection (Cap Table Buyers, Quarterly Income Trajectory, Block Deals, Discovery Timeline) for Smart Money Radar.

**Architecture:** Enhances `institutional_radar_signals` with strategy tags (`WHALE_CONVICTION`, `BLOCK_DEAL_MOMENTUM`, `DUAL_ACCELERATION`, `DOMESTIC_ABSORPTION`), introduces `quarterly_financials` table registered in `SYNC_TABLES`, creates an automated signal lifecycle tracker computing outcome returns against discovery prices, provides enriched REST APIs (`/signals` and `/stock/{ticker}/forensics`), and delivers an interactive strategy pill switcher and 4-tab forensic drawer in the dashboard UI.

**Tech Stack:** Python 3.11+, FastAPI, SQLite (WAL mode), Turso / libSQL sync, Vanilla JavaScript (ES6+), High-Density CSS.

**Spec:** `docs/superpowers/specs/2026-09-13-smart-money-radar-lifecycle-tracking-design.md`

## Global Constraints
- Strict Anti-Fabrication Guarantee: Zero synthetic or mock data; all data originates from persisted real filings or exchange logs.
- Point-in-Time (PIT) Integrity: Signal discovery timestamp and initial price must be immutable once created.
- Mandatory `SYNC_TABLES` Contract: All new tables must be registered in `earnings_engine/data/turso_sync.py`.
- Universal Temporal Baselines: Every UI card and metric must display its temporal window or baseline (e.g., `Discovery: 2026-08-15`, `Return: +18.4% since signal`).
- Always commit and push changes upon task completion.

---

### Task 1: Database Migration & Cloud Sync Registration

**Files:**
- Modify: `earnings_engine/data/migrations.py`
- Modify: `earnings_engine/data/turso_sync.py:27-140`
- Test: `tests/test_institutional_migrations.py`

**Interfaces:**
- Produces: `institutional_radar_signals` table with `strategy` column and indices; `quarterly_financials` table; `SYNC_TABLES` updated in `turso_sync.py`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_institutional_migrations.py
from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection
from earnings_engine.data.migrations import apply_migrations
from earnings_engine.data.turso_sync import SYNC_TABLES, WATERMARK_CANDIDATE_COLUMNS

def test_migration_smart_money_signals_and_financials(tmp_path, monkeypatch):
    monkeypatch.delenv("TURSO_DATABASE_URL", raising=False)
    monkeypatch.delenv("TURSO_AUTH_TOKEN", raising=False)
    monkeypatch.setenv("EARNINGS_ENGINE_DB_NAME", f"test_{tmp_path.name}.sqlite3")
    s = Settings()
    s.data_dirs["prices"] = tmp_path
    s.data_dirs["earnings"] = tmp_path
    s.ensure_dirs()
    apply_migrations(s)

    conn = get_db_connection(s)
    # Verify institutional_radar_signals columns
    sig_cols = [r[1] for r in conn.execute("PRAGMA table_info(institutional_radar_signals)").fetchall()]
    assert "strategy" in sig_cols
    assert "outcome_return_pct" in sig_cols
    assert "lifecycle_status" in sig_cols
    assert "ideal_entry_price" in sig_cols
    assert "target_price" in sig_cols
    assert "stop_loss" in sig_cols

    # Verify quarterly_financials table
    qfin_cols = [r[1] for r in conn.execute("PRAGMA table_info(quarterly_financials)").fetchall()]
    assert "ticker" in qfin_cols
    assert "quarter" in qfin_cols
    assert "revenue_cr" in qfin_cols
    assert "net_profit_cr" in qfin_cols
    assert "operating_margin_pct" in qfin_cols
    assert "eps" in qfin_cols

    # Verify SYNC_TABLES
    assert "institutional_radar_signals" in SYNC_TABLES
    assert "quarterly_financials" in SYNC_TABLES
    assert "period_end_date" in WATERMARK_CANDIDATE_COLUMNS
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_institutional_migrations.py -v`
Expected: FAIL with missing table or column assertion errors.

- [ ] **Step 3: Implement migration and sync registration**

Add migration in `earnings_engine/data/migrations.py`:
```python
def _migration_035_smart_money_strategies_and_financials(conn: Any) -> None:
    """Add strategy columns to institutional_radar_signals and create quarterly_financials table."""
    # 1. Upgrade institutional_radar_signals if strategy column is missing
    sig_cols = [r[1] for r in conn.execute("PRAGMA table_info(institutional_radar_signals)").fetchall()]
    if "strategy" not in sig_cols:
        conn.execute("ALTER TABLE institutional_radar_signals ADD COLUMN strategy TEXT NOT NULL DEFAULT 'WHALE_CONVICTION'")
    if "ideal_entry_price" not in sig_cols:
        conn.execute("ALTER TABLE institutional_radar_signals ADD COLUMN ideal_entry_price REAL")
    if "target_price" not in sig_cols:
        conn.execute("ALTER TABLE institutional_radar_signals ADD COLUMN target_price REAL")
    if "stop_loss" not in sig_cols:
        conn.execute("ALTER TABLE institutional_radar_signals ADD COLUMN stop_loss REAL")
    if "risk_reward_ratio" not in sig_cols:
        conn.execute("ALTER TABLE institutional_radar_signals ADD COLUMN risk_reward_ratio REAL")
    if "outcome_return_pct" not in sig_cols:
        conn.execute("ALTER TABLE institutional_radar_signals ADD COLUMN outcome_return_pct REAL")
    if "lifecycle_status" not in sig_cols:
        conn.execute("ALTER TABLE institutional_radar_signals ADD COLUMN lifecycle_status TEXT DEFAULT 'ACTIVE'")
    if "company_name" not in sig_cols:
        conn.execute("ALTER TABLE institutional_radar_signals ADD COLUMN company_name TEXT")
    if "industry" not in sig_cols:
        conn.execute("ALTER TABLE institutional_radar_signals ADD COLUMN industry TEXT")
    if "current_date" not in sig_cols:
        conn.execute("ALTER TABLE institutional_radar_signals ADD COLUMN current_date TEXT")
    if "days_elapsed" not in sig_cols:
        conn.execute("ALTER TABLE institutional_radar_signals ADD COLUMN days_elapsed INTEGER DEFAULT 0")
    if "whale_count" not in sig_cols:
        conn.execute("ALTER TABLE institutional_radar_signals ADD COLUMN whale_count INTEGER DEFAULT 0")
    if "trigger_reason" not in sig_cols:
        conn.execute("ALTER TABLE institutional_radar_signals ADD COLUMN trigger_reason TEXT")

    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_inst_signals_strategy ON institutional_radar_signals(strategy)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_inst_signals_status ON institutional_radar_signals(lifecycle_status)")
    except Exception:
        pass

    # 2. Create quarterly_financials table
    conn.execute("""
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
        )
    """)
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_qfin_ticker ON quarterly_financials(ticker)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_qfin_quarter ON quarterly_financials(quarter)")
    except Exception:
        pass
```

Register migration 35 in `_MIGRATIONS` list in `migrations.py`.
In `earnings_engine/data/turso_sync.py`, ensure `"quarterly_financials"` is in `SYNC_TABLES`, and `"period_end_date"` is in `WATERMARK_CANDIDATE_COLUMNS`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_institutional_migrations.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add earnings_engine/data/migrations.py earnings_engine/data/turso_sync.py tests/test_institutional_migrations.py
git commit -m "feat(institutional): add migration 035 for smart money strategies and quarterly financials table

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 2: Strategy Signal Discovery Engine & Lifecycle Tracking

**Files:**
- Modify: `earnings_engine/data/institutional_accumulation.py`
- Test: `tests/test_institutional_strategy_signals.py`

**Interfaces:**
- Produces: `evaluate_and_track_strategy_signals(settings, as_of_date)` returning tracked signal objects per strategy; `get_tracked_smart_money_signals(strategy, status, limit, settings)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_institutional_strategy_signals.py
import pytest
from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection
from earnings_engine.data.migrations import apply_migrations
from earnings_engine.data.institutional_accumulation import (
    evaluate_and_track_strategy_signals,
    get_tracked_smart_money_signals,
)

@pytest.fixture
def test_env(tmp_path, monkeypatch):
    monkeypatch.delenv("TURSO_DATABASE_URL", raising=False)
    monkeypatch.delenv("TURSO_AUTH_TOKEN", raising=False)
    monkeypatch.setenv("EARNINGS_ENGINE_DB_NAME", f"test_{tmp_path.name}.sqlite3")
    s = Settings()
    s.data_dirs["prices"] = tmp_path
    s.data_dirs["earnings"] = tmp_path
    s.ensure_dirs()
    apply_migrations(s)

    conn = get_db_connection(s)
    with conn:
        conn.execute("INSERT OR REPLACE INTO tickers (ticker, name, market_cap) VALUES ('WELCORP.NS', 'Welspun Corp Ltd', 20000.0)")
        conn.execute("INSERT OR REPLACE INTO price_history (ticker, date, open, high, low, close, volume) VALUES ('WELCORP.NS', '2026-08-01', 500.0, 520.0, 495.0, 500.0, 1000000)")
        conn.execute("INSERT OR REPLACE INTO price_history (ticker, date, open, high, low, close, volume) VALUES ('WELCORP.NS', '2026-08-30', 600.0, 610.0, 590.0, 600.0, 1500000)")
        conn.execute("""
            INSERT OR REPLACE INTO shareholding_patterns (ticker, quarter, raw_quarter, promoter_pct, fii_pct, dii_mf_pct, public_retail_pct, other_pct, filing_date)
            VALUES ('WELCORP.NS', 'Q1 FY27', 'Jun 2026', 48.0, 25.0, 15.0, 12.0, 0.0, '2026-08-05')
        """)
        conn.execute("""
            INSERT OR REPLACE INTO shareholding_patterns (ticker, quarter, raw_quarter, promoter_pct, fii_pct, dii_mf_pct, public_retail_pct, other_pct, filing_date)
            VALUES ('WELCORP.NS', 'Q4 FY26', 'Mar 2026', 48.0, 18.0, 14.0, 20.0, 0.0, '2026-05-05')
        """)
    return s

def test_evaluate_and_track_strategy_signals(test_env):
    s = test_env
    res = evaluate_and_track_strategy_signals(settings=s)
    assert res["total_signals"] >= 1

    signals = get_tracked_smart_money_signals(strategy="ALL_STRATEGIES", settings=s)
    assert len(signals) >= 1
    sig = signals[0]
    assert sig["ticker"] == "WELCORP.NS"
    assert sig["signal_price"] > 0
    assert sig["current_price"] == 600.0
    assert sig["outcome_return_pct"] is not None
    assert sig["target_price"] > sig["signal_price"]
    assert sig["stop_loss"] < sig["signal_price"]
    assert sig["lifecycle_status"] in ("ACTIVE", "TARGET_HIT")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_institutional_strategy_signals.py -v`
Expected: FAIL with ImportError or missing function.

- [ ] **Step 3: Implement strategy evaluation & lifecycle tracking**

In `earnings_engine/data/institutional_accumulation.py`:
1. Define strategy qualification functions:
   - `_qualifies_whale_conviction(stock)`: `conviction_score >= 65.0` and `smart_money_cr >= 10.0` and `dominance_pct >= 60.0`.
   - `_qualifies_block_deal_momentum(stock, block_deals_cr, block_count)`: `block_deals_cr >= 25.0` or `block_count >= 2`.
   - `_qualifies_dual_acceleration(stock)`: `eps_growth_yoy >= 20.0` and `fii_delta + dii_delta >= 0.50`.
   - `_qualifies_domestic_absorption(stock)`: `dii_cr >= 25.0` and `cap_category in ('Small Cap', 'Mid Cap', 'Micro Cap')`.
2. Implement `evaluate_and_track_strategy_signals(settings=None, as_of_date=None)`:
   - Scans stocks across universe.
   - For each qualifying stock and matching strategy, queries `institutional_radar_signals` for existing `(ticker, strategy)`.
   - If not found: cuts discovery record with `signal_date` (filing date or earliest qualification date), `signal_price` (close price on signal date), `ideal_entry_price = signal_price`, `target_price = round(signal_price * 1.20, 2)`, `stop_loss = round(signal_price * 0.92, 2)`, `risk_reward_ratio = 2.5`.
   - Updates `current_price`, `outcome_return_pct = round(((current_price - signal_price) / signal_price) * 100.0, 2)`, `max_gain_pct`, `days_elapsed = (current_date - signal_date).days`, and `lifecycle_status` (`TARGET_HIT` if `current_price >= target_price`, `DISTRIBUTION_EXIT` if `current_price <= stop_loss`, else `ACTIVE`).
3. Implement `get_tracked_smart_money_signals(strategy='ALL_STRATEGIES', status='active', limit=60, settings=None)`:
   - Returns enriched tracked signal objects formatted for the frontend table.

- [ ] **Step 4: Run test to verify it passes**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_institutional_strategy_signals.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add earnings_engine/data/institutional_accumulation.py tests/test_institutional_strategy_signals.py
git commit -m "feat(institutional): implement strategy evaluation and lifecycle tracking engine

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 3: Quarterly Financials & Earnings Trajectory Enrichment

**Files:**
- Modify: `earnings_engine/data/institutional_accumulation.py`
- Test: `tests/test_quarterly_financials.py`

**Interfaces:**
- Produces: `get_stock_quarterly_financials(ticker, limit=6, settings=None)` returning historical quarterly income statements and growth trends.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_quarterly_financials.py
import pytest
from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection
from earnings_engine.data.migrations import apply_migrations
from earnings_engine.data.institutional_accumulation import get_stock_quarterly_financials

@pytest.fixture
def test_db(tmp_path, monkeypatch):
    monkeypatch.delenv("TURSO_DATABASE_URL", raising=False)
    monkeypatch.delenv("TURSO_AUTH_TOKEN", raising=False)
    monkeypatch.setenv("EARNINGS_ENGINE_DB_NAME", f"test_{tmp_path.name}.sqlite3")
    s = Settings()
    s.data_dirs["prices"] = tmp_path
    s.data_dirs["earnings"] = tmp_path
    s.ensure_dirs()
    apply_migrations(s)

    conn = get_db_connection(s)
    with conn:
        conn.execute("""
            INSERT OR REPLACE INTO quarterly_financials 
            (ticker, quarter, period_end_date, revenue_cr, net_profit_cr, operating_margin_pct, eps, yoy_revenue_growth_pct, yoy_pat_growth_pct)
            VALUES ('RELIANCE.NS', 'Q1 FY27', '2026-06-30', 235000.0, 19500.0, 17.5, 28.8, 11.2, 14.5)
        """)
        conn.execute("""
            INSERT OR REPLACE INTO quarterly_financials 
            (ticker, quarter, period_end_date, revenue_cr, net_profit_cr, operating_margin_pct, eps, yoy_revenue_growth_pct, yoy_pat_growth_pct)
            VALUES ('RELIANCE.NS', 'Q4 FY26', '2026-03-31', 228000.0, 18900.0, 16.8, 27.9, 9.8, 12.0)
        """)
    return s

def test_get_stock_quarterly_financials(test_db):
    s = test_db
    records = get_stock_quarterly_financials("RELIANCE.NS", settings=s)
    assert len(records) == 2
    assert records[0]["quarter"] == "Q1 FY27"
    assert records[0]["revenue_cr"] == 235000.0
    assert records[0]["net_profit_cr"] == 19500.0
    assert records[0]["operating_margin_pct"] == 17.5
    assert records[0]["yoy_pat_growth_pct"] == 14.5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_quarterly_financials.py -v`
Expected: FAIL with missing function.

- [ ] **Step 3: Implement quarterly financials provider**

In `earnings_engine/data/institutional_accumulation.py`:
```python
def get_stock_quarterly_financials(
    ticker: str,
    limit: int = 6,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """Retrieve historical quarterly income statements, margins, and growth trajectory."""
    settings = settings or Settings()
    conn = get_db_connection(settings)
    rows = conn.execute(
        """
        SELECT quarter, period_end_date, revenue_cr, net_profit_cr, operating_profit_cr,
               operating_margin_pct, net_margin_pct, eps, yoy_revenue_growth_pct, yoy_pat_growth_pct, source
        FROM quarterly_financials
        WHERE ticker = ?
        ORDER BY quarter DESC
        LIMIT ?
        """,
        (ticker, limit),
    ).fetchall()

    results = []
    for r in rows:
        results.append({
            "quarter": r[0],
            "period_end_date": r[1],
            "revenue_cr": r[2],
            "net_profit_cr": r[3],
            "operating_profit_cr": r[4],
            "operating_margin_pct": r[5],
            "net_margin_pct": r[6],
            "eps": r[7],
            "yoy_revenue_growth_pct": r[8],
            "yoy_pat_growth_pct": r[9],
            "source": r[10],
        })
    return results
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_quarterly_financials.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add earnings_engine/data/institutional_accumulation.py tests/test_quarterly_financials.py
git commit -m "feat(institutional): implement quarterly financials query engine

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 4: Forensic REST APIs & Endpoints

**Files:**
- Modify: `earnings_engine/api/routers/institutional.py`
- Test: `tests/test_institutional_api_signals.py`

**Interfaces:**
- Produces: `GET /api/v1/institutional/signals` and `GET /api/v1/institutional/stock/{ticker}/forensics`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_institutional_api_signals.py
import pytest
from fastapi.testclient import TestClient
from earnings_engine.server import app

def test_api_institutional_signals_and_forensics(monkeypatch):
    client = TestClient(app)
    # 1. Signals endpoint
    resp = client.get("/api/v1/institutional/signals?strategy=ALL_STRATEGIES&limit=20")
    assert resp.status_code == 200
    data = resp.json()
    assert "signals" in data
    assert "macro_summary" in data

    # 2. Stock forensics endpoint
    resp_f = client.get("/api/v1/institutional/stock/RELIANCE.NS/forensics")
    assert resp_f.status_code == 200
    fdata = resp_f.json()
    assert "ticker" in fdata
    assert "signal_timeline" in fdata
    assert "buyers" in fdata
    assert "quarterly_income" in fdata
    assert "block_deals" in fdata
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_institutional_api_signals.py -v`
Expected: FAIL with 404 Not Found or missing endpoints.

- [ ] **Step 3: Implement REST endpoints**

In `earnings_engine/api/routers/institutional.py`:
1. Add `GET /signals`:
```python
@router.get("/signals", summary="Smart Money Radar Tracked Signals")
async def get_smart_money_signals(
    strategy: str = Query("ALL_STRATEGIES", description="Strategy key"),
    status: str = Query("active", description="Signal lifecycle status: active, all, closed"),
    sort_by: str = Query("score", description="Sort order: return, score, capital, date"),
    limit: int = Query(60, ge=1, le=200),
):
    import earnings_engine.data.institutional_accumulation as inst_mod
    data = await asyncio.to_thread(
        inst_mod.get_tracked_smart_money_signals,
        strategy=strategy,
        status=status,
        sort_by=sort_by,
        limit=limit,
        settings=_settings,
    )
    return data
```

2. Add `GET /stock/{ticker}/forensics`:
```python
@router.get("/stock/{ticker}/forensics", summary="Stock Forensic Dossier")
async def get_stock_forensics(ticker: str):
    import earnings_engine.data.institutional_accumulation as inst_mod
    data = await asyncio.to_thread(
        inst_mod.get_stock_forensic_dossier,
        ticker=ticker,
        settings=_settings,
    )
    if not data:
        raise HTTPException(status_code=404, detail=f"No forensic dossier found for {ticker}")
    return data
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_institutional_api_signals.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add earnings_engine/api/routers/institutional.py tests/test_institutional_api_signals.py
git commit -m "feat(api): add smart money signals and forensic dossier REST endpoints

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 5: Frontend UI: Strategy Switcher, Tracked Radar Table & 4-Tab Inspector Drawer

**Files:**
- Modify: `earnings_engine/reports/templates/dashboard/index.html` (or institutional partial)
- Modify: `earnings_engine/ui/js/modules/institutional.js`
- Test: Manual browser/HTTP contract verification test in `tests/test_ui_institutional_endpoints.py`

**Interfaces:**
- Produces: Interactive strategy pill buttons (`All Active Signals`, `🐋 Whale Conviction`, `⚡ Block Deal Momentum`, `📈 Dual Acceleration`, `🏢 Domestic Absorption`), tracked radar table columns with discovery date, signal price, live price, outcome return %, and 4-tab forensic inspector drawer (Buyers, Quarterly Income, Block Deals, Signal Timeline).

- [ ] **Step 1: Write endpoint UI contract test**

```python
# tests/test_ui_institutional_endpoints.py
from fastapi.testclient import TestClient
from earnings_engine.server import app

def test_ui_institutional_api_contracts():
    client = TestClient(app)
    # Check dashboard loads
    resp = client.get("/dashboard")
    assert resp.status_code == 200
    assert "Smart Money Radar" in resp.text
```

- [ ] **Step 2: Update `institutional.js` with Strategy Selector and 4-Tab Forensic Drawer**

In `earnings_engine/ui/js/modules/institutional.js`:
1. Add `this._smartMoneyStrategy = 'ALL_STRATEGIES';`
2. Render strategy pill switcher in `renderSmartMoneySection()`:
   - Buttons: `[All Active Signals]`, `[🐋 Whale Conviction]`, `[⚡ Block Deal Momentum]`, `[📈 Dual Acceleration]`, `[🏢 Domestic Absorption]`
   - Add `selectSmartMoneyStrategy(strat)` callback to refresh data.
3. Update table rendering to display:
   - `Ticker & Company`
   - `Strategy Badge`
   - `Signal Date (Discovered)`
   - `Signal Price (₹)`
   - `Current Price (₹)`
   - `Outcome Return (% Gain/Loss)`
   - `Smart Money (₹ Cr)`
   - `Conviction Score`
   - `Lifecycle Status`
4. Update `inspectSmartMoneyStock(stock)`:
   - Fetch `/api/v1/institutional/stock/${encodeURIComponent(ticker)}/forensics`.
   - Render 4 tabs:
     - **Tab 1: Cap Table Buyers**: Full table of all funds, institution types, stake %, and capital deployed.
     - **Tab 2: Quarterly Income & Trajectory**: Table of historical quarterly revenue, net profit, margins, and EPS.
     - **Tab 3: Block Deals Ledger**: Transaction logs of on-market block trades.
     - **Tab 4: Discovery Signal History**: Lifecycle timeline showing trigger date, initial score, target/SL levels, and price trajectory.

- [ ] **Step 3: Run UI test to verify passes**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_ui_institutional_endpoints.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add earnings_engine/ui/js/modules/institutional.js earnings_engine/reports/templates/dashboard/index.html tests/test_ui_institutional_endpoints.py
git commit -m "feat(ui): add strategy selector and 4-tab forensic inspector drawer to smart money radar

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 6: End-to-End Verification, Seed Script & Error Ledger Audit

**Files:**
- Modify: `scripts/verify_institutional_data.py`
- Test: Full integration test suite

- [ ] **Step 1: Update CLI verification script**

Add `--eval-signals` flag to `scripts/verify_institutional_data.py` to trigger batch signal evaluation and lifecycle tracking across the universe.

- [ ] **Step 2: Run all institutional tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_institutional_migrations.py tests/test_institutional_strategy_signals.py tests/test_quarterly_financials.py tests/test_institutional_api_signals.py tests/test_ui_institutional_endpoints.py -v
```
Expected: All tests PASS.

- [ ] **Step 3: Error Ledger Hygiene Scan**

Run: `.\.venv\Scripts\python.exe scripts/error_ledger.py scan`
Expected: 0 new errors.

- [ ] **Step 4: Final Git Commit and Remote Push**

```bash
git add scripts/verify_institutional_data.py
git commit -m "feat(institutional): finalize smart money radar tracking and forensic intelligence

Co-Authored-By: Claude Code <noreply@anthropic.com>"
git push origin new_report
```
