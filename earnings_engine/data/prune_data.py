"""Data retention and storage compaction engine.

Enforces retention policies across historical pricing, quarterly earnings, and auxiliary caches:
- Price History: Retention capped at 1 year (365 calendar days).
- Earnings History: Retention capped at 2 years (730 calendar days).
- Auxiliary Logs: Stale fetch logs and month caches pruned.
- Database Compaction: Executes VACUUM on SQLite databases to reclaim disk space.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta
from typing import Any

from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection, _cache_path, is_turso_enabled

logger = logging.getLogger("earnings_engine.data.prune_data")


def prune_price_history(days: int = 365, settings: Settings | None = None) -> int:
    """Delete price_history rows older than `days` (default 365 days / 1 year)."""
    s = settings or Settings()
    cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    logger.info("Pruning price_history older than %s (%d days)...", cutoff_date, days)

    conn = get_db_connection(s)
    try:
        cur = conn.execute(
            "DELETE FROM price_history WHERE date < ?",
            (cutoff_date,),
        )
        deleted = cur.rowcount if hasattr(cur, "rowcount") and cur.rowcount is not None and cur.rowcount >= 0 else 0
        conn.commit()
        logger.info("Pruned %d rows from price_history.", deleted)
        return deleted
    finally:
        conn.close()


def prune_earnings_history(days: int = 730, settings: Settings | None = None) -> int:
    """Delete historical earnings older than `days` (default 730 days / 2 years).

    Preserves upcoming and current earnings events (earnings_date >= today).
    """
    s = settings or Settings()
    cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    today_str = datetime.now().strftime("%Y-%m-%d")
    logger.info("Pruning earnings_history older than %s (%d days)...", cutoff_date, days)

    conn = get_db_connection(s)
    try:
        cur = conn.execute(
            "DELETE FROM earnings_history WHERE earnings_date < ? AND earnings_date < ?",
            (cutoff_date, today_str),
        )
        deleted = cur.rowcount if hasattr(cur, "rowcount") and cur.rowcount is not None and cur.rowcount >= 0 else 0
        conn.commit()
        logger.info("Pruned %d rows from earnings_history.", deleted)
        return deleted
    finally:
        conn.close()


def prune_auxiliary_tables(settings: Settings | None = None) -> dict[str, int]:
    """Prune stale rows from auxiliary log and cache tables."""
    s = settings or Settings()
    conn = get_db_connection(s)
    results = {}

    try:
        # Check existing tables
        tables_res = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        table_names = {r[0] if isinstance(r, tuple) or hasattr(r, "__getitem__") else r["name"] for r in tables_res}

        if "earnings_month_cache" in table_names:
            cur = conn.execute("DELETE FROM earnings_month_cache WHERE updated_at < DATE('now', '-30 days')")
            results["earnings_month_cache"] = cur.rowcount if hasattr(cur, "rowcount") and cur.rowcount is not None else 0

        if "earnings_fetch_log" in table_names:
            cur = conn.execute("DELETE FROM earnings_fetch_log WHERE fetch_date < DATE('now', '-90 days')")
            results["earnings_fetch_log"] = cur.rowcount if hasattr(cur, "rowcount") and cur.rowcount is not None else 0

        if "ticker_audit_log" in table_names:
            try:
                cur = conn.execute("DELETE FROM ticker_audit_log WHERE refreshed_at < DATE('now', '-180 days')")
                results["ticker_audit_log"] = cur.rowcount if hasattr(cur, "rowcount") and cur.rowcount is not None else 0
            except Exception as e:
                logger.warning("Could not prune ticker_audit_log: %s", e)

        conn.commit()
        logger.info("Pruned auxiliary tables: %s", results)
        return results
    finally:
        conn.close()


def vacuum_database(settings: Settings | None = None) -> bool:
    """Execute VACUUM on the SQLite database to reclaim disk space and rebuild indexes."""
    s = settings or Settings()
    db_path = _cache_path(s)

    if db_path.exists():
        logger.info("Compacting local SQLite database via VACUUM at %s...", db_path)
        try:
            conn = sqlite3.connect(str(db_path), isolation_level=None, timeout=60.0)
            try:
                conn.execute("VACUUM;")
                conn.execute("PRAGMA optimize;")
                logger.info("Local SQLite database compacted successfully.")
            finally:
                conn.close()
            return True
        except Exception as exc:
            logger.error("Failed to vacuum SQLite database: %s", exc)
            return False

    if is_turso_enabled():
        logger.info("Turso remote cloud database detected; VACUUM is managed by LibSQL engine.")
        return True

    logger.warning("Database path %s does not exist, skipping VACUUM.", db_path)
    return False


def prune_all_data(
    price_days: int = 365,
    earnings_days: int = 730,
    vacuum: bool = True,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Execute complete data retention policy: prune prices (>1y), earnings (>2y), auxiliary caches, and vacuum."""
    s = settings or Settings()
    prices_deleted = prune_price_history(days=price_days, settings=s)
    earnings_deleted = prune_earnings_history(days=earnings_days, settings=s)
    aux_deleted = prune_auxiliary_tables(settings=s)

    vacuumed = False
    if vacuum:
        vacuumed = vacuum_database(settings=s)

    return {
        "success": True,
        "prices_deleted": prices_deleted,
        "earnings_deleted": earnings_deleted,
        "auxiliary_deleted": aux_deleted,
        "vacuumed": vacuumed,
        "retention_policy": {
            "price_days": price_days,
            "earnings_days": earnings_days,
        },
    }
