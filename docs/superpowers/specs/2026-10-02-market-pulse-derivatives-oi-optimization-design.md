# Technical Design Spec: Market Pulse, Participant OI & Institutional Liquidity Optimization

**Date**: 2026-10-02  
**Author**: Antigravity  
**Status**: Draft / Under Review  

---

## 1. Objectives & Scope

This specification addresses high latency, redundant network fetches, and unindexed database queries across:
1. **Participant Derivatives Open Interest (OI) & Long/Short Matrix** (`/api/v1/market-pulse/participant-oi`)
2. **Institutional Net Cash Liquidity (FII + DII)** (`/api/v1/market-pulse/liquidity`, `/api/v1/market-pulse/institutional-flows`)
3. **Daily Market Pulse & Macro Radar** (`/api/v1/market-pulse`, `/api/v1/market/pulse`, `/api/v1/market-pulse/sectors`, `/api/v1/market-pulse/indices`)

### Key Requirements
- **Holiday & Off-Market Awareness**: Respect NSE holidays (such as 2026-10-02 Gandhi Jayanti) and closed market hours. On holidays, weekends, and outside 09:15–15:30 IST, serve prices and indicators directly from SQLite (`price_history` / `daily_quotes_cache`) with zero remote HTTP calls.
- **Negative Caching & Cooldown**: Prevent synchronous retries for unreleased files or non-trading days (NSE clearing CSVs and NSE live settlement API).
- **Batch / Vectorized DB Queries**: Eliminate N+1 queries in participant OI and full-table group-bys in sector calculations.
- **Index Migration (045)**: Ensure optimal B-tree indexes for all hot query paths.

---

## 2. Architecture & Subsystems

```
┌─────────────────────────────────────────────────────────────┐
│                 Trading Calendar Subsystem                  │
│  - NSE Holiday List (2024, 2025, 2026)                      │
│  - is_trading_day(d)                                        │
│  - get_latest_completed_trading_day(ref_date)               │
│  - is_market_open(ts) -> True only on trading days in-hours │
└──────────────┬──────────────────────────────┬───────────────┘
               │                              │
               ▼                              ▼
┌──────────────────────────────┐ ┌──────────────────────────────┐
│  Prices & Session Engine     │ │   Market Pulse Data Engine   │
│  (prices.py)                 │ │   (market_pulse.py)          │
│  - get_market_session()      │ │  - compute_net_cash_liquidity│
│  - is_holiday -> true        │ │  - compute_participant_oi    │
│  - Off-market -> DB directly │ │  - compute_sector_heatmap    │
│  - Zero remote yfinance calls│ │  - Negative cache & cooldown │
└──────────────────────────────┘ └──────────────┬───────────────┘
                                                │
                                                ▼
┌─────────────────────────────────────────────────────────────┐
│             Database Indexing & Batch Query Layer           │
│  - Migration 045: Composite indexes for pulse & pricing     │
│  - Vectorized SELECT IN for 30-day participant OI           │
│  - Index benchmark date lookup for sector heatmap           │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Detailed Component Specifications

### 3.1 Centralized Trading Calendar (`earnings_engine/data/trading_calendar.py`)
- Define authoritative holiday schedules for Indian equities (NSE):
  - 2024, 2025, 2026 official NSE holidays.
- Provide helper methods:
  - `is_trading_day(d: date) -> bool`: Returns `False` if Saturday/Sunday or in NSE holiday calendar.
  - `is_market_holiday(d: date) -> bool`: Returns `True` if `d` is an official holiday.
  - `get_latest_completed_trading_day(ref_date: date | None = None) -> date`: Walks back to the most recent completed trading date.
  - `is_indian_market_open(ts: float | None = None) -> bool`: Validates IST time `09:15 <= time < 15:30` on a valid `is_trading_day`.

### 3.2 Price Session & Live Quote Off-Market Gating (`earnings_engine/data/prices.py`)
- In `get_market_session(ticker)`:
  - For Indian equities (`.NS` / `^NSEI` / etc.), check `is_indian_market_open(now_ts)` and `is_trading_day(now_dt)`.
  - If holiday or weekend: set `is_open = False`, `is_holiday = is_market_holiday(now_dt)`, `is_weekend = now_dt.weekday() >= 5`, `session = "closed"`.
- In `fetch_live_quote()` and `fetch_batch_live_quotes()`:
  - If market is closed or it is a holiday/weekend: check SQLite `daily_quotes_cache` or `price_history` first. Return settled database prices directly without triggering remote HTTP network requests.

### 3.3 Participant Derivatives OI Optimization (`earnings_engine/data/market_pulse.py`)
- **Remote Sync Gating**:
  - `sync_nse_participant_oi_data`:
    1. Only consider dates `<= get_latest_completed_trading_day()`.
    2. If today is a trading day but current IST time `< 18:30` (settlement release target), skip today.
    3. Maintain `_FAILED_NSE_OI_DATES: dict[str, float]` in memory: if an archive URL returns 404 or fails, store the timestamp and do not retry for 1800 seconds (30 mins).
- **Batch Query Execution**:
  - Replace sequential 30-date loop queries with a single SQL query:
    ```sql
    SELECT * FROM participant_oi_positioning
    WHERE date IN (
        SELECT DISTINCT date FROM participant_oi_positioning
        ORDER BY date DESC LIMIT 30
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
  - Parse into memory map `{date: {participant: row}}` in Python.

### 3.4 Institutional Net Cash Liquidity Optimization (`earnings_engine/data/market_pulse.py`)
- `get_expected_latest_trading_date()`:
  - If before 18:00 IST on a trading day, target `get_latest_completed_trading_day(today - 1 day)`.
  - If on a weekend or holiday, target `get_latest_completed_trading_day(today)`.
- If `latest_date_in_db >= expected_date`, skip all remote sync calls.
- In `sync_real_fii_dii_cash_flows`, if market is holiday or closed, avoid spinning or retrying without cooldown.

### 3.5 Daily Market Pulse & Sector Heatmap Optimization
- In `compute_sector_heatmap`:
  - Determine active trading dates using `SELECT date FROM price_history WHERE ticker = '^NSEI' ORDER BY date DESC LIMIT 40` (sub-millisecond index lookup) instead of `GROUP BY date` on the entire table.
- Cache computed sector metrics in memory with off-market TTL.

### 3.6 Migration 045 (`earnings_engine/data/migrations.py`)
- Add `_migration_045_market_pulse_and_pricing_indexes(conn)`:
  - `idx_participant_oi_date_part`: `ON participant_oi_positioning (date DESC, participant)`
  - `idx_inst_flows_date_desc`: `ON institutional_net_flows (date DESC)`
  - `idx_price_history_ticker_date`: `ON price_history (ticker, date DESC)`
  - `idx_ticker_metrics_perf`: `ON ticker_metrics (week_change, thirty_day_return_pct)`
  - `idx_daily_quotes_ticker`: `ON daily_quotes_cache (ticker, updated_at DESC)`

---

## 4. Verification Plan

1. **Unit & Integration Tests**:
   - Test `trading_calendar.py` with holiday dates (including 2026-10-02 Gandhi Jayanti), weekends, and normal trading days.
   - Test `prices.py:get_market_session` and quote serving during holidays (confirm zero remote calls).
   - Test `compute_participant_oi_matrix` batch query correctness and negative caching.
   - Test `compute_net_cash_liquidity` holiday expectation.
   - Test migration 045 execution and index creation.
2. **Performance Baseline Comparison**:
   - Run `pytest tests/test_market_pulse.py tests/test_modular_market_pulse.py` to confirm test suite execution time drops dramatically and 100% passes.
