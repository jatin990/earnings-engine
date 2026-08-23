---
name: sqlite-turso-optimizer
description: High-performance SQLite, libSQL, and Turso database optimization, indexing strategies, Write-Ahead Logging (WAL), batch upserts, in-memory TTL caching, and connection management.
---

# SQLite & Turso Optimizer Skill

## Overview
Optimization patterns for local SQLite databases and remote Turso/libSQL deployments used in quantitative engines, caching layers, and high-frequency analytical dashboards.

## Core Optimization Rules

### 1. SQLite Pragmas for High Concurrency
Always initialize SQLite connections with WAL mode and fast synchronous settings:
```sql
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA temp_store = MEMORY;
PRAGMA cache_size = -64000; -- 64MB memory cache
PRAGMA busy_timeout = 5000; -- 5 second timeout before throwing lock error
```

### 2. Strategic Composite Indexing
- Create indexes matching the `WHERE` + `ORDER BY` query patterns:
```sql
-- Fast earnings queries by date & ticker
CREATE INDEX IF NOT EXISTS idx_earnings_date_ticker ON earnings_history (earnings_date, ticker);

-- Fast swing ranges queries
CREATE INDEX IF NOT EXISTS idx_swing_ranges_lookup ON swing_ranges (watchlist, ticker);
```

### 3. High-Throughput Batch Upserts
Use `INSERT INTO ... ON CONFLICT DO UPDATE` or `INSERT OR REPLACE`:
```python
with conn:
    conn.executemany(
        """
        INSERT INTO price_history (ticker, date, open, high, low, close, volume)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(ticker, date) DO UPDATE SET
            open=excluded.open,
            high=excluded.high,
            low=excluded.low,
            close=excluded.close,
            volume=excluded.volume
        """,
        records
    )
```

### 4. Hybrid Local SQLite + Turso Sync
- Run local reads on local SQLite disk / memory cache for ultra-low latency (< 1ms).
- Sync mutations or cloud backups asynchronously to Turso via `@libsql/client` or Turso HTTP API.
