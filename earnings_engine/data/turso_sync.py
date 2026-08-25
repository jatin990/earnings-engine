"""Upstream Turso Cloud and Local SQLite Bidirectional Synchronization.

Enables local SQLite execution with high speed and zero network latency, while
automatically keeping local data and upstream Turso Cloud synchronized on startup.
"""
from __future__ import annotations

import logging
import os
import sqlite3
import time
from typing import Any

from earnings_engine.config import Settings
from earnings_engine.data.db import (
    _cache_path,
    is_turso_enabled,
    TursoConnection,
)

logger = logging.getLogger("earnings_engine.data.turso_sync")

# Core state tables synchronized between local SQLite and upstream Turso Cloud
SYNC_TABLES = [
    "watchlists",
    "watchlist_meta",
    "passcodes",
    "user_auth",
    "user_sessions",
    "consensus_predictions",
    "breakout_radar",
]


def _get_table_columns(conn: Any, table_name: str) -> list[str]:
    """Return list of column names for a table."""
    try:
        cur = conn.execute(f"PRAGMA table_info({table_name})")
        rows = cur.fetchall()
        cols = []
        for r in rows:
            if hasattr(r, "get"):
                cols.append(r.get("name"))
            elif isinstance(r, (tuple, list)) and len(r) > 1:
                cols.append(r[1])
        return [c for c in cols if c]
    except Exception as e:
        logger.debug("[TURSO-SYNC] Failed to get schema for %s: %s", table_name, e)
        return []


def sync_local_to_upstream(settings: Settings | None = None) -> dict[str, Any]:
    """Synchronize state between local SQLite and Upstream Turso Cloud.

    Pushes newly created/updated local records to Turso and pulls remote cloud
    records down to local SQLite.
    """
    s = settings or Settings()
    url = os.getenv("TURSO_DATABASE_URL", "").strip()
    token = os.getenv("TURSO_AUTH_TOKEN", "").strip()

    if not (url and token):
        logger.info("[TURSO-SYNC] Upstream Turso credentials not configured. Running in pure local SQLite mode.")
        return {"status": "skipped", "reason": "No Turso credentials configured"}

    start_t = time.perf_counter()
    logger.info("[TURSO-SYNC] Starting upstream synchronization with Turso Cloud...")

    db_path = str(_cache_path(s))
    s.ensure_dirs()

    try:
        local_conn = sqlite3.connect(db_path, timeout=30.0)
        local_conn.execute("PRAGMA journal_mode=WAL")
        remote_conn = TursoConnection(url, token)
        
        local_tables = {r[0] for r in local_conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() if r}
        remote_tables = {r[0] for r in remote_conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() if r}
    except Exception as e:
        logger.error("[TURSO-SYNC] Failed to establish database connection for sync: %s", e)
        return {"status": "error", "error": str(e)}

    stats: dict[str, dict[str, int]] = {}
    total_pushed = 0
    total_pulled = 0

    try:
        for table in SYNC_TABLES:
            if table not in local_tables:
                continue

            # Ensure table exists on remote Turso
            if table not in remote_tables:
                try:
                    cur = local_conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,))
                    row = cur.fetchone()
                    if row and row[0]:
                        remote_conn.execute(row[0])
                        remote_tables.add(table)
                except Exception as e:
                    logger.debug("[TURSO-SYNC] Could not create remote table %s: %s", table, e)

            cols = _get_table_columns(local_conn, table)
            if not cols:
                continue

            col_str = ", ".join([f'"{c}"' for c in cols])
            placeholders = ", ".join(["?" for _ in cols])
            upsert_sql = f'INSERT OR REPLACE INTO "{table}" ({col_str}) VALUES ({placeholders})'

            # 1. Fetch Local Rows
            local_rows = local_conn.execute(f'SELECT {col_str} FROM "{table}"').fetchall()

            # 2. Push Local Rows Upstream to Turso
            pushed = 0
            if local_rows and table in remote_tables:
                try:
                    remote_conn.executemany(upsert_sql, local_rows)
                    pushed = len(local_rows)
                except Exception as e:
                    logger.warning("[TURSO-SYNC] Upstream push error on table %s: %s", table, e)

            # 3. Pull Remote Rows Down to Local SQLite
            pulled = 0
            if table in remote_tables:
                try:
                    remote_rows = remote_conn.execute(f'SELECT {col_str} FROM "{table}"').fetchall()
                    if remote_rows:
                        with local_conn:
                            local_conn.executemany(upsert_sql, [tuple(r) for r in remote_rows])
                        pulled = len(remote_rows)
                except Exception as e:
                    logger.debug("[TURSO-SYNC] Downstream pull error on table %s: %s", table, e)

            stats[table] = {"pushed": pushed, "pulled": pulled}
            total_pushed += pushed
            total_pulled += pulled

    finally:
        try:
            local_conn.close()
        except Exception:
            pass

    elapsed = time.perf_counter() - start_t
    logger.info(
        "[TURSO-SYNC] Upstream sync completed in %.2fs. Pushed %d records, pulled %d records across %d tables.",
        elapsed,
        total_pushed,
        total_pulled,
        len(stats),
    )

    return {
        "status": "success",
        "elapsed_seconds": round(elapsed, 2),
        "total_pushed": total_pushed,
        "total_pulled": total_pulled,
        "tables": stats,
    }
