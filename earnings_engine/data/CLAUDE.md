# CLAUDE.md — Data & Storage Subsystem (`earnings_engine/data/`)

> Subsystem guide for SQLite database schemas, connection pools, cloud Turso replication, and market scrapers/providers.

---

## 1. Scope & Architecture

The data subsystem manages local SQLite persistence (`prices.sqlite3`, `earnings_engine.db`), cloud synchronization via Turso/libSQL, and market data ingestion pipelines.

- **Schema & Pools**: `earnings_engine/data/db.py` (database connections, WAL mode, schema definitions)
- **Cloud Replication**: `earnings_engine/data/turso_sync.py` (bidirectional SQLite <-> Turso sync)
- **Market Data & Scrapers**:
  - `prices.py`: Historical bars, live quote caching, weekend freshness gates
  - `institutional.py`: Shareholding patterns, mutual fund holdings, QoQ flows
  - `options.py`: NSE options chain, participant OI pulse
  - `swing_ranges.py`: Multi-timeframe swing high/low ranges
  - `new_listings.py`: Recent IPO tracker and debut performance metrics

---

## 2. Mandatory Rules & Invariants

### 2.1 The Mandatory `SYNC_TABLES` Contract
**Whenever ANY new table is added anywhere in the codebase:**
1. **Register Table**: Add the table name string to `SYNC_TABLES` list in `earnings_engine/data/turso_sync.py`.
2. **Watermark Candidates**: If the table includes timestamp/date columns (`updated_at`, `created_at`, `scanned_at`, `date`, `asof_date`), verify it is listed in `WATERMARK_CANDIDATE_COLUMNS`.
3. **Date-Only Handling**: If the watermark column format is `YYYY-MM-DD`, add it to `DATE_ONLY_COLUMNS`.
4. **Union Merge Syntax**: Use valid SQLite/libSQL syntax (`INSERT OR IGNORE INTO ...`) for replication compatibility.
5. **Memory Persistence**: Persist new table schemas to `.claude/projects/.../memory/` to survive compaction.

### 2.2 Local SQLite Fallback Guarantee
- Always wrap cloud Turso / libSQL network calls with local SQLite fallbacks. Network timeouts or Turso downtime must never crash local reads/writes.
- PRAGMA configuration for SQLite: `journal_mode=WAL`, `busy_timeout=5000`, `synchronous=NORMAL`.

### 2.3 Strict Anti-Fabrication & Real-Data Integrity
- **Zero Mock Data**: Never generate pseudo-random numbers (`hashlib.md5(...) % N`) or fake records.
- If market scrapers fail or data is missing, return `None`, `0.0`, or `[]` with an honest status flag (`status: "unavailable"`).

---

## 3. Targeted Testing & Verification

```bash
# Run data and sync tests
./.venv/Scripts/python.exe -m pytest tests/test_db.py -v
./.venv/Scripts/python.exe -m pytest tests/test_turso_sync.py -v
./.venv/Scripts/python.exe -m pytest tests/test_new_listings.py -v
```
