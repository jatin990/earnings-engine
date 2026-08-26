"""Upstream Turso Cloud and Local SQLite Lossless Bidirectional Merge.

Enables local SQLite execution with high speed and zero network latency, while
automatically keeping local data and upstream Turso Cloud merged on startup.

Merging Rules (Strict No-Override / Lossless Union Policy):
1. Records existing on Local but missing in Remote are pushed to Remote.
2. Records existing on Remote but missing in Local are pulled down to Local.
3. Existing records with matching Primary Keys are NEVER overwritten or deleted
   (using INSERT OR IGNORE / non-destructive union semantics).
4. Watchlists, predictions, and radars union-merge together across both environments.
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

# Core state tables synchronized and merged bidirectionally
SYNC_TABLES = [
    "watchlists",
    "watchlist_meta",
    "passcodes",
    "user_auth",
    "user_sessions",
    "consensus_predictions",
    "breakout_radar",
    "scanner_candidates",
    "swing_ranges",
    "swing_cycle_history",
    "kronos_predictions",
    "strategy_predictions",
    "strategy_audit_logs",
    "ai_news_predictions",
    "news_catalysts",
    "universes",
    "daily_top_gainers",
    "trips",
    "trip_activities",
    "trip_groups",
    "trip_group_members",
    "trip_group_trips",
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
    """Lossless bidirectional union merge between local SQLite and Upstream Turso Cloud.

    Merges all local and remote data without destructive overrides or deletions.
    """
    s = settings or Settings()
    url = os.getenv("TURSO_DATABASE_URL", "").strip()
    token = os.getenv("TURSO_AUTH_TOKEN", "").strip()

    if not (url and token):
        logger.info("[TURSO-SYNC] Upstream Turso credentials not configured. Running in pure local SQLite mode.")
        return {"status": "skipped", "reason": "No Turso credentials configured"}

    start_t = time.perf_counter()
    logger.info("[TURSO-SYNC] Starting lossless union merge with Turso Cloud (no overrides)...")

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
            if table not in local_tables and table not in remote_tables:
                continue

            # Ensure table exists on remote Turso if it exists locally
            if table in local_tables and table not in remote_tables:
                try:
                    cur = local_conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,))
                    row = cur.fetchone()
                    if row and row[0]:
                        remote_conn.execute(row[0])
                        remote_tables.add(table)
                except Exception as e:
                    logger.debug("[TURSO-SYNC] Could not create remote table %s: %s", table, e)

            # Ensure table exists locally if it exists on remote
            if table in remote_tables and table not in local_tables:
                try:
                    cur = remote_conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,))
                    row = cur.fetchone()
                    if row and row[0]:
                        with local_conn:
                            local_conn.execute(row[0])
                        local_tables.add(table)
                except Exception as e:
                    logger.debug("[TURSO-SYNC] Could not create local table %s: %s", table, e)

            cols = _get_table_columns(local_conn if table in local_tables else remote_conn, table)
            if not cols:
                continue

            col_str = ", ".join([f'"{c}"' for c in cols])
            placeholders = ", ".join(["?" for _ in cols])
            
            # Lossless Merge Query: INSERT OR IGNORE guarantees existing records are never overwritten
            merge_sql = f'INSERT OR IGNORE INTO "{table}" ({col_str}) VALUES ({placeholders})'

            # 1. Fetch Local Rows
            local_rows = []
            if table in local_tables:
                local_rows = local_conn.execute(f'SELECT {col_str} FROM "{table}"').fetchall()

            # 2. Push Local Rows Upstream to Turso (Union Merge)
            pushed = 0
            if local_rows and table in remote_tables:
                try:
                    remote_conn.executemany(merge_sql, local_rows)
                    pushed = len(local_rows)
                except Exception as e:
                    logger.warning("[TURSO-SYNC] Upstream merge push error on table %s: %s", table, e)

            # 3. Pull Remote Rows Down to Local SQLite (Union Merge)
            pulled = 0
            if table in remote_tables:
                try:
                    remote_rows = remote_conn.execute(f'SELECT {col_str} FROM "{table}"').fetchall()
                    if remote_rows:
                        with local_conn:
                            local_conn.executemany(merge_sql, [tuple(r) for r in remote_rows])
                        pulled = len(remote_rows)
                except Exception as e:
                    logger.debug("[TURSO-SYNC] Downstream merge pull error on table %s: %s", table, e)

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
        "[TURSO-SYNC] Lossless merge completed in %.2fs. Merged %d local records & %d remote records across %d tables (no overrides).",
        elapsed,
        total_pushed,
        total_pulled,
        len(stats),
    )

    return {
        "status": "success",
        "merge_policy": "lossless_union_no_overrides",
        "elapsed_seconds": round(elapsed, 2),
        "total_pushed": total_pushed,
        "total_pulled": total_pulled,
        "tables": stats,
    }
