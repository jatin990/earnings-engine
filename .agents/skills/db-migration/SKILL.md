---
name: db-migration
description: Schema migrations, table registration in Turso sync, watermarks, indexing, and bidirectional replication safety for SQLite and libSQL. Use when adding or altering database tables.
---

# SQLite & Turso Database Migration Protocol

Use this skill whenever creating new tables, altering existing schemas, adding indexes, or modifying replication behavior.

---

## 1. Migration File Creation Standards

All migrations live under `scripts/migrations/` and must be sequential, idempotent, and transactional:
- **Filename convention**: `NNN_<descriptive_snake_case>.py` (e.g. `044_add_trade_setups_ledger.py`).
- **Idempotency**: Use `CREATE TABLE IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`, and safe column addition checks (inspect `PRAGMA table_info(...)` before running `ALTER TABLE ADD COLUMN`).
- **Connection Pragma**:
  ```python
  conn.execute("PRAGMA journal_mode = WAL;")
  conn.execute("PRAGMA busy_timeout = 5000;")
  conn.execute("PRAGMA synchronous = NORMAL;")
  ```

---

## 2. Mandatory Turso Sync Contract

Whenever a table is added or modified, update `earnings_engine/data/turso_sync.py`:

1. **`SYNC_TABLES`**:
   Add the table name to the authoritative replication list:
   ```python
   SYNC_TABLES = [
       ...,
       "your_new_table",
   ]
   ```
2. **`WATERMARK_CANDIDATE_COLUMNS`**:
   Register timestamp/date column candidates used for incremental sync:
   ```python
   WATERMARK_CANDIDATE_COLUMNS = [
       ...,
       "updated_at",
       "created_at",
       "timestamp",
       "date",
   ]
   ```
3. **`DATE_ONLY_COLUMNS`**:
   If the column contains date-only values formatted `YYYY-MM-DD`, register it:
   ```python
   DATE_ONLY_COLUMNS = {"date", "earnings_date", "asof_date"}
   ```

---

## 3. Bidirectional Replication Safety Rules

- **Primary Keys**: Always define explicit `PRIMARY KEY`s or `UNIQUE` constraints to enable deterministic replication.
- **Insert Semantics**: In sync logic and bulk ingest routines, use `INSERT OR IGNORE` or `ON CONFLICT DO UPDATE` so repeated sync cycles never crash on duplicates.
- **Offline / Local Fallback**: Always ensure local SQLite operations succeed even if Turso remote connection (`TURSO_DATABASE_URL`) times out or is unreachable.

---

## 4. Verification & Testing Routine

Run the targeted migration test suite after completing migration scripts:
```bash
./.venv/Scripts/python.exe -m pytest tests/test_migrations.py -v
```
Scan the error ledger to ensure zero database locks or syntax errors:
```bash
./.venv/Scripts/python.exe scripts/error_ledger.py scan
```
