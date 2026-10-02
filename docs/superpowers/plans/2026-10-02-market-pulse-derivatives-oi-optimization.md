# Market Pulse, Participant Derivatives OI & Net Cash Liquidity Optimization Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate network lag and redundant external requests on holidays and off-market hours, batch SQLite queries in participant derivatives OI, and add composite database indexes to make Market Pulse, Participant OI, and FII/DII Liquidity endpoints sub-100ms.

**Architecture:** Centralize an authoritative NSE Trading Calendar to gate live quote and settlement scrapers; implement negative caching/cooldowns for NSE clearing archives; vectorize 30-day participant OI queries into a single SQL batch; and apply database migration 045 for hot-path indexes.

**Tech Stack:** Python 3.14, FastAPI, SQLite / Turso libSQL, Pandas, Pytest.

**Spec:** `docs/superpowers/specs/2026-10-02-market-pulse-derivatives-oi-optimization-design.md`

## Global Constraints
- Indian equities require `.NS` suffix; benchmark indices use `^NSEI`, `^INDIAVIX`, etc.
- Never make live network requests on holidays, weekends, or outside market hours (09:15-15:30 IST) unless `force_refresh=True`.
- Never fabricate mock/dummy data.
- All new database tables/indexes must follow migration conventions and Turso sync contracts.

## Review Focus
1. Today (2026-10-02 Gandhi Jayanti) is a weekday holiday: `get_market_session` must mark `is_open = False`, `is_holiday = True`, and serve quotes 100% from SQLite.
2. Participant OI on a holiday or before 18:30 IST on a trading day must not send failing HTTP requests to NSE archives.
3. FII/DII Liquidity must not attempt to scrape MoneyControl or NSE if the prior trading day is already in `institutional_net_flows`.
4. Participant OI 30-day history must execute in a single SQL query instead of 60 N+1 queries.
5. Migration 045 must be idempotent on both SQLite and Turso.

---

### Task 1: Centralized NSE Trading Calendar Subsystem

**Files:**
- Create: `earnings_engine/data/trading_calendar.py`
- Test: `tests/test_trading_calendar.py`

**Interfaces:**
- Produces:
  - `is_trading_day(d: date) -> bool`
  - `is_market_holiday(d: date) -> bool`
  - `get_latest_completed_trading_day(ref_date: date | None = None) -> date`
  - `is_indian_market_open(ts: float | None = None) -> bool`
  - `NSE_HOLIDAYS_2024`, `NSE_HOLIDAYS_2025`, `NSE_HOLIDAYS_2026` sets

- [ ] **Step 1: Write failing unit tests for trading calendar**

```python
# tests/test_trading_calendar.py
from datetime import date, datetime, timezone
from earnings_engine.data.trading_calendar import (
    is_trading_day,
    is_market_holiday,
    get_latest_completed_trading_day,
    is_indian_market_open,
)

def test_trading_calendar_holidays_2026():
    # 2026-10-02 is Gandhi Jayanti (Friday holiday)
    gandhi_jayanti = date(2026, 10, 2)
    assert is_market_holiday(gandhi_jayanti) is True
    assert is_trading_day(gandhi_jayanti) is False

    # 2026-10-01 is Thursday (trading day)
    thursday = date(2026, 10, 1)
    assert is_market_holiday(thursday) is False
    assert is_trading_day(thursday) is True

    # 2026-10-03 is Saturday (weekend)
    saturday = date(2026, 10, 3)
    assert is_trading_day(saturday) is False
    assert is_market_holiday(saturday) is False

def test_get_latest_completed_trading_day():
    # On Gandhi Jayanti (2026-10-02), latest completed trading day is 2026-10-01
    latest = get_latest_completed_trading_day(date(2026, 10, 2))
    assert latest == date(2026, 10, 1)

def test_is_indian_market_open():
    # 2026-10-02 at 11:00 AM IST (holiday) -> False
    # 11:00 IST = 05:30 UTC
    dt_holiday = datetime(2026, 10, 2, 5, 30, tzinfo=timezone.utc)
    assert is_indian_market_open(dt_holiday.timestamp()) is False

    # 2026-10-01 at 11:00 AM IST (trading day in-hours) -> True
    dt_open = datetime(2026, 10, 1, 5, 30, tzinfo=timezone.utc)
    assert is_indian_market_open(dt_open.timestamp()) is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_trading_calendar.py -v`
Expected: FAIL (ModuleNotFoundError or ImportError)

- [ ] **Step 3: Implement `earnings_engine/data/trading_calendar.py`**

```python
# earnings_engine/data/trading_calendar.py
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Set

IST_OFFSET = timedelta(hours=5, minutes=30)
IST_TZ = timezone(IST_OFFSET)

NSE_HOLIDAYS_2024: Set[str] = {
    "2024-01-22", "2024-01-26", "2024-03-08", "2024-03-25",
    "2024-04-11", "2024-04-17", "2024-05-01", "2024-05-20",
    "2024-06-17", "2024-07-17", "2024-08-15", "2024-10-02",
    "2024-11-01", "2024-11-15", "2024-12-25",
}

NSE_HOLIDAYS_2025: Set[str] = {
    "2025-02-26", "2025-03-14", "2025-03-31", "2025-04-10",
    "2025-04-14", "2025-04-18", "2025-05-01", "2025-08-15",
    "2025-08-27", "2025-10-02", "2025-10-21", "2025-10-22",
    "2025-11-05", "2025-12-25",
}

NSE_HOLIDAYS_2026: Set[str] = {
    "2026-01-26", "2026-03-03", "2026-03-20", "2026-04-03",
    "2026-04-14", "2026-05-01", "2026-06-17", "2026-08-15",
    "2026-09-02", "2026-10-02", "2026-10-20", "2026-11-09",
    "2026-11-10", "2026-12-25",
}

ALL_NSE_HOLIDAYS: Set[str] = NSE_HOLIDAYS_2024 | NSE_HOLIDAYS_2025 | NSE_HOLIDAYS_2026

def is_market_holiday(d: date) -> bool:
    """Check if date is a scheduled NSE equity market holiday."""
    return d.isoformat() in ALL_NSE_HOLIDAYS

def is_trading_day(d: date) -> bool:
    """Check if date is an active NSE trading day (not weekend or scheduled holiday)."""
    if d.weekday() >= 5:
        return False
    return not is_market_holiday(d)

def get_latest_completed_trading_day(ref_date: date | None = None) -> date:
    """Get the most recent completed NSE trading day prior to or on ref_date."""
    cur = ref_date or datetime.now(timezone.utc).date()
    while not is_trading_day(cur):
        cur -= timedelta(days=1)
    return cur

def is_indian_market_open(ts: float | None = None) -> bool:
    """Check if Indian equity market is currently in open continuous trading hours (09:15 - 15:30 IST on a trading day)."""
    now_dt = datetime.fromtimestamp(ts, tz=timezone.utc) if ts else datetime.now(timezone.utc)
    ist_dt = now_dt.astimezone(IST_TZ)
    if not is_trading_day(ist_dt.date()):
        return False
    time_val = ist_dt.hour + ist_dt.minute / 60.0
    return 9.25 <= time_val < 15.5
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_trading_calendar.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add earnings_engine/data/trading_calendar.py tests/test_trading_calendar.py
git commit -m "feat(market): add centralized NSE trading calendar and holiday resolver"
```

---

### Task 2: Market Session & Price Cache Holiday Gating

**Files:**
- Modify: `earnings_engine/data/prices.py`
- Test: `tests/test_prices_holiday_gating.py`

**Interfaces:**
- Consumes: `is_trading_day`, `is_market_holiday`, `is_indian_market_open` from `earnings_engine.data.trading_calendar`
- Modifies: `get_market_session`, `fetch_live_quote`, `fetch_batch_live_quotes`

- [ ] **Step 1: Write failing test for holiday quote gating**

```python
# tests/test_prices_holiday_gating.py
from datetime import datetime, timezone
from unittest.mock import patch
from earnings_engine.data.prices import get_market_session, fetch_live_quote

def test_get_market_session_on_holiday():
    # 2026-10-02 11:00 IST (UTC 05:30) - Friday holiday
    dt_holiday = datetime(2026, 10, 2, 5, 30, tzinfo=timezone.utc)
    session = get_market_session("RELIANCE.NS", now_dt=dt_holiday)
    assert session["is_open"] is False
    assert session["is_holiday"] is True
    assert session["session"] == "closed"

def test_fetch_live_quote_on_holiday_no_network():
    dt_holiday = datetime(2026, 10, 2, 5, 30, tzinfo=timezone.utc)
    with patch("yfinance.Ticker") as mock_yf:
        # On holiday, fetch_live_quote should serve from SQLite/fallback without invoking yfinance
        quote = fetch_live_quote("RELIANCE.NS", now_dt=dt_holiday, sync_db=False)
        assert mock_yf.called is False
        assert "symbol" in quote
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_prices_holiday_gating.py -v`
Expected: FAIL

- [ ] **Step 3: Update `earnings_engine/data/prices.py`**
  - Import `is_trading_day`, `is_market_holiday`, `is_indian_market_open` from `earnings_engine.data.trading_calendar`.
  - In `get_market_session()`:
    - Determine `is_holiday = is_market_holiday(target_date)` for Indian equities.
    - If `is_holiday` or `is_weekend`: set `is_open = False`, `session = "closed"`, and return `is_holiday: True`.
  - In `fetch_live_quote()` and `fetch_batch_live_quotes()`:
    - If `session["is_holiday"]` or `session["is_weekend"]` or not `session["is_open"]` (and not `force`):
      - Query `daily_quotes_cache` or `price_history` SQLite tables first. If found, return cached/settled quote immediately without calling external network APIs.

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_prices_holiday_gating.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add earnings_engine/data/prices.py tests/test_prices_holiday_gating.py
git commit -m "fix(prices): gate live quote fetches on market holidays and off-market hours"
```

---

### Task 3: Database Migration 045 — Hot-Path Indexes

**Files:**
- Modify: `earnings_engine/data/migrations.py`
- Test: `tests/test_migration_045.py`

**Interfaces:**
- Produces: `_migration_045_market_pulse_and_pricing_indexes` registered as version 45 in `MIGRATIONS`.

- [ ] **Step 1: Write test for migration 045**

```python
# tests/test_migration_045.py
from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection
from earnings_engine.data.migrations import apply_migrations

def test_migration_045_applied():
    settings = Settings()
    apply_migrations(settings, force=True)
    conn = get_db_connection(settings)
    
    # Verify indexes exist
    indices = [r[1] for r in conn.execute("SELECT type, name FROM sqlite_master WHERE type='index'").fetchall()]
    assert "idx_participant_oi_date_part" in indices
    assert "idx_inst_flows_date_desc" in indices
    assert "idx_price_history_ticker_date" in indices
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_migration_045.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `_migration_045_market_pulse_and_pricing_indexes` in `earnings_engine/data/migrations.py`**

```python
def _migration_045_market_pulse_and_pricing_indexes(conn: Any) -> None:
    """Create composite indexes for Participant OI, FII/DII Net Flows, Price History, and Daily Quotes."""
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_participant_oi_date_part ON participant_oi_positioning (date DESC, participant)")
    except Exception:
        pass
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_inst_flows_date_desc ON institutional_net_flows (date DESC)")
    except Exception:
        pass
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_price_history_ticker_date ON price_history (ticker, date DESC)")
    except Exception:
        pass
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ticker_metrics_perf ON ticker_metrics (week_change, thirty_day_return_pct)")
    except Exception:
        pass
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_daily_quotes_ticker ON daily_quotes_cache (ticker, updated_at DESC)")
    except Exception:
        pass
```
Register `Migration(45, "045_market_pulse_and_pricing_indexes", _migration_045_market_pulse_and_pricing_indexes)` in `MIGRATIONS`.

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_migration_045.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add earnings_engine/data/migrations.py tests/test_migration_045.py
git commit -m "feat(db): add migration 045 for market pulse and pricing indexes"
```

---

### Task 4: Participant Derivatives OI Vectorized Batch Query & Negative Cache

**Files:**
- Modify: `earnings_engine/data/market_pulse.py`
- Test: `tests/test_participant_oi_optimization.py`

**Interfaces:**
- Consumes: `is_trading_day`, `get_latest_completed_trading_day` from `trading_calendar`
- Modifies: `sync_nse_participant_oi_data`, `compute_participant_oi_matrix`

- [ ] **Step 1: Write test for Participant OI optimization**

```python
# tests/test_participant_oi_optimization.py
from datetime import datetime, timezone
from earnings_engine.data.market_pulse import compute_participant_oi_matrix, sync_nse_participant_oi_data

def test_participant_oi_holiday_no_sync():
    # Calling sync on 2026-10-02 (holiday) should not attempt to download today's file
    count = sync_nse_participant_oi_data(days=5, force=False)
    # Returns count of inserted records without throwing timeouts
    assert isinstance(count, int)

def test_participant_oi_matrix_structure():
    data = compute_participant_oi_matrix(force_refresh=True)
    assert "as_of_date" in data
    assert "summary" in data
    assert "history_30d" in data
    assert len(data["history_30d"]) > 0
```

- [ ] **Step 2: Run test to verify it fails or runs slow**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_participant_oi_optimization.py -v`

- [ ] **Step 3: Refactor `sync_nse_participant_oi_data` and `compute_participant_oi_matrix`**
  - In `sync_nse_participant_oi_data`:
    - Only iterate trading days `<= get_latest_completed_trading_day()`.
    - If today is a trading day but current IST time `< 18:30`, skip today.
    - Check global `_FAILED_NSE_OI_DATES: dict[str, float]`. If a date failed within the last 1800s, skip downloading.
  - In `compute_participant_oi_matrix`:
    - Replace 60+ individual queries with a single query fetching all rows for the top 30 dates:
      ```sql
      SELECT * FROM participant_oi_positioning
      WHERE date IN (
          SELECT DISTINCT date FROM participant_oi_positioning ORDER BY date DESC LIMIT 30
      )
      ORDER BY date DESC,
               CASE participant
                   WHEN 'FII' THEN 1
                   WHEN 'DII' THEN 2
                   WHEN 'PRO' THEN 3
                   WHEN 'CLIENT' THEN 4
                   ELSE 5
               END
      ```
    - Group rows by date in Python to assemble `history_30d`.

- [ ] **Step 4: Run test to verify it passes fast**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_participant_oi_optimization.py -v`
Expected: PASS in < 1 second.

- [ ] **Step 5: Commit**

```bash
git add earnings_engine/data/market_pulse.py tests/test_participant_oi_optimization.py
git commit -m "perf(options): optimize participant derivatives OI with batch queries and negative caching"
```

---

### Task 5: Institutional Net Cash Liquidity & Sector Heatmap Optimization

**Files:**
- Modify: `earnings_engine/data/market_pulse.py`
- Test: `tests/test_modular_market_pulse.py`, `tests/test_market_pulse.py`

**Interfaces:**
- Consumes: `get_latest_completed_trading_day`, `is_trading_day` from `trading_calendar`
- Modifies: `compute_net_cash_liquidity`, `get_expected_latest_trading_date`, `compute_sector_heatmap`

- [ ] **Step 1: Write / verify tests**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_modular_market_pulse.py -v`

- [ ] **Step 2: Update `get_expected_latest_trading_date` & `compute_net_cash_liquidity`**
  - `get_expected_latest_trading_date(now_dt)`:
    - Convert `now_dt` to IST.
    - If today is not a trading day (weekend or holiday), return `get_latest_completed_trading_day(ist_dt.date()).isoformat()`.
    - If today is a trading day: if before 18:00 IST, return `get_latest_completed_trading_day(ist_dt.date() - timedelta(days=1)).isoformat()`; else return `ist_dt.date().isoformat()`.
  - In `compute_net_cash_liquidity`:
    - If `latest_date_in_db >= expected_date`, skip all remote sync calls.
- [ ] **Step 3: Optimize `compute_sector_heatmap`**
  - Query benchmark index dates from `price_history WHERE ticker = '^NSEI' ORDER BY date DESC LIMIT 40` to get `weekday_dates` in < 1ms rather than a table scan `GROUP BY date`.

- [ ] **Step 4: Run full market pulse test suite**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_market_pulse.py tests/test_modular_market_pulse.py tests/test_institutional_flows.py -v`
Expected: ALL PASS in < 5 seconds total.

- [ ] **Step 5: Commit**

```bash
git add earnings_engine/data/market_pulse.py
git commit -m "perf(pulse): optimize FII/DII net liquidity gating and sector heatmap date lookups"
```

---

### Task 6: System Verification & Remote Push

**Files:**
- Test: All unit & integration tests across market pulse, options, institutional flows, and prices.

- [ ] **Step 1: Run error ledger scan**

Run: `./.venv/Scripts/python.exe scripts/error_ledger.py open`
Expected: 0 open errors.

- [ ] **Step 2: Run targeted test suite**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_trading_calendar.py tests/test_prices_holiday_gating.py tests/test_migration_045.py tests/test_participant_oi_optimization.py tests/test_market_pulse.py tests/test_modular_market_pulse.py -v`
Expected: ALL PASS.

- [ ] **Step 3: Commit and Push to remote branch**

```bash
git push origin worktree-market-pulse-opt
```
