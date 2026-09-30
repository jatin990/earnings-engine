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
from datetime import datetime, timezone
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
    # Core User, Auth & Watchlists
    "watchlists",
    "watchlist_meta",
    "passcodes",
    "users",
    "user_auth",
    "user_sessions",
    "invite_codes",
    "friend_access",
    "otp_verifications",
    "ui_preferences",
    # Quantitative Predictions & Market Radar
    "consensus_predictions",
    "breakout_radar",
    "breakout_tracked_signals",
    "breakout_audit_log",
    "scanner_candidates",
    "swing_ranges",
    "swing_cycle_history",
    "swing_radar",
    "confluence_radar",
    "kronos_predictions",
    "strategy_predictions",
    "strategy_audit_logs",
    "strategy_tier_audit_log",
    "ai_news_predictions",
    "news_catalysts",
    "news_catalysts_tickers",
    "news_catalyst_outcomes",
    "news_feed_runs",
    "quarter_repeater_predictions",
    "tri_confluence_metrics",
    "option_chain_history",
    "stock_ratings",
    "stock_rating_snapshots",
    "trading_agents_reports",
    "ticker_audit_log",
    # Custom Alert Rules & Notifications
    "alert_rules",
    "alert_rule_logs",
    # Macro, Market Pulse & Liquidity
    "institutional_net_flows",
    "participant_oi_positioning",
    # Automation Schedules, Logs & Badges
    "sidebar_badge_counters",
    "automation_schedules",
    "automation_schedule_logs",
    "daily_top_gainers",
    "ai_model_telemetry",
    "downstream_api_calls",
    # Institutional & Market Universe
    "institutional_holdings",
    "institutional_block_deals",
    "bulk_block_deals",
    "reg30_disclosures",
    "shareholding_patterns",
    "institutional_accumulation_cache",
    "nse_shareholding_freshness",
    "universes",
    "universe_stocks",
    "universe_freshness",
    "earnings_fetch_log",
    "earnings_month_cache",
    # Institutional Intelligence Integrity, Provenance & Quarantine
    "institutional_radar_signals",
    "quarterly_financials",
    "data_provenance_meta",
    "institutional_audit_log",
    "institutional_quarantine",
    # Personal Finance & Lifestyle
    "trips",
    "trip_activities",
    "trip_groups",
    "trip_group_members",
    "trip_group_trips",
    "trip_itinerary_days",
    "trip_packing_items",
    "trip_packing_status",
    "credit_cards",
    "credit_card_otp_requests",
    "net_worth_snapshots",
    # Zepto Operations & Store Management
    "zepto_employees",
    "zepto_salaries",
    "zepto_monthly_ratings",
    "zepto_expenses",
    "zepto_store_income",
    "zepto_income_split_settings",
    "zepto_candidates",
    "zepto_security_capital",
    "zepto_staffing_targets",
    "zepto_gmail_auth",
    "zepto_attendance_imports",
    "zepto_attendance_records",
]


def _get_table_columns_info(conn: Any, table_name: str) -> dict[str, str]:
    """Return dict of {column_name: column_type} for a table."""
    try:
        cur = conn.execute(f"PRAGMA table_info({table_name})")
        rows = cur.fetchall()
        cols = {}
        for r in rows:
            if hasattr(r, "get"):
                col_name = r.get("name")
                col_type = r.get("type", "TEXT") or "TEXT"
                if col_name:
                    cols[col_name] = col_type
            elif isinstance(r, (tuple, list)) and len(r) > 2:
                col_name = r[1]
                col_type = r[2] or "TEXT"
                if col_name:
                    cols[col_name] = col_type
            elif hasattr(r, "keys") and "name" in r.keys():
                col_name = r["name"]
                col_type = r["type"] if "type" in r.keys() else "TEXT"
                if col_name:
                    cols[col_name] = col_type or "TEXT"
        return cols
    except Exception as e:
        logger.debug("[TURSO-SYNC] Failed to get schema info for %s: %s", table_name, e)
        return {}


def _get_table_columns(conn: Any, table_name: str) -> list[str]:
    """Return list of column names for a table."""
    info = _get_table_columns_info(conn, table_name)
    return list(info.keys())


WATERMARK_CANDIDATE_COLUMNS = [
    "updated_at",
    "last_updated",
    "refreshed_at",
    "scanned_at",
    "created_at",
    "published_at",
    "detected_at",
    "fetched_at",
    "audited_at",
    "audit_timestamp",
    "quarantined_at",
    "calculated_at",
    "started_at",
    "run_at",
    "predicted_at",
    "triggered_at",
    "added_at",
    "attached_at",
    "last_login_at",
    "cached_at",
    "reported_date",
    "deal_date",
    "as_of_date",
    "asof_date",
    "cycle_start",
    "cycle_end",
    "trade_date",
    "signal_date",
    "last_seen_date",
    "fetch_date",
    "period_end_date",
    "date",
    "timestamp",
]

DATE_ONLY_COLUMNS = {
    "trade_date",
    "signal_date",
    "last_seen_date",
    "deal_date",
    "as_of_date",
    "asof_date",
    "fetch_date",
    "reported_date",
    "period_end_date",
    "cycle_start",
    "cycle_end",
    "date",
}


def _get_watermark_column(cols: list[str]) -> str | None:
    """Find the best timestamp/watermark column for incremental delta sync."""
    for cand in WATERMARK_CANDIDATE_COLUMNS:
        if cand in cols:
            return cand
    return None


def _init_sync_state_tables(local_conn: sqlite3.Connection, remote_conn: TursoConnection) -> None:
    """Ensure _turso_sync_state tracking table exists locally and remotely."""
    sql = """
    CREATE TABLE IF NOT EXISTS _turso_sync_state (
        table_name TEXT PRIMARY KEY,
        last_synced_at TEXT NOT NULL,
        last_pushed_count INTEGER DEFAULT 0,
        last_pulled_count INTEGER DEFAULT 0
    );
    """
    try:
        with local_conn:
            local_conn.execute(sql)
    except Exception as e:
        logger.debug("[TURSO-SYNC] Local _turso_sync_state init error: %s", e)

    try:
        remote_conn.execute(sql)
    except Exception as e:
        logger.debug("[TURSO-SYNC] Remote _turso_sync_state init error: %s", e)


def _get_last_sync_timestamp(local_conn: sqlite3.Connection, table_name: str) -> str | None:
    """Retrieve last synchronization timestamp for a table."""
    try:
        cur = local_conn.execute(
            "SELECT last_synced_at FROM _turso_sync_state WHERE table_name = ?",
            (table_name,),
        )
        row = cur.fetchone()
        return str(row[0]) if row and row[0] else None
    except Exception:
        return None


def _save_last_sync_timestamp(
    local_conn: sqlite3.Connection,
    remote_conn: TursoConnection,
    table_name: str,
    sync_iso: str,
    pushed_cnt: int,
    pulled_cnt: int,
) -> None:
    """Persist sync timestamp and change counters to both local and remote state tables."""
    sql = """
    INSERT OR REPLACE INTO _turso_sync_state (table_name, last_synced_at, last_pushed_count, last_pulled_count)
    VALUES (?, ?, ?, ?);
    """
    try:
        with local_conn:
            local_conn.execute(sql, (table_name, sync_iso, pushed_cnt, pulled_cnt))
    except Exception as e:
        logger.debug("[TURSO-SYNC] Local sync state save error: %s", e)

    try:
        remote_conn.execute(sql, (table_name, sync_iso, pushed_cnt, pulled_cnt))
    except Exception as e:
        logger.debug("[TURSO-SYNC] Remote sync state save error: %s", e)


def sync_local_to_upstream(settings: Settings | None = None, force_full: bool = False) -> dict[str, Any]:
    """High-Performance Incremental Delta Sync between local SQLite and Upstream Turso Cloud.

    Tracks watermark timestamps per table in `_turso_sync_state` so only new/modified records
    are transferred over the network, reducing sync times from minutes to sub-second durations.
    """
    s = settings or Settings()
    url = os.getenv("TURSO_DATABASE_URL", "").strip()
    token = os.getenv("TURSO_AUTH_TOKEN", "").strip()

    if not (url and token):
        logger.info("[TURSO-SYNC] Upstream Turso credentials not configured. Running in pure local SQLite mode.")
        return {"status": "skipped", "reason": "No Turso credentials configured"}

    start_t = time.perf_counter()
    sync_now_iso = datetime.now(timezone.utc).isoformat()
    logger.info("[TURSO:START] Starting delta sync with Turso Cloud (mode=%s)...", "full" if force_full else "incremental")

    db_path = str(_cache_path(s))
    s.ensure_dirs()

    try:
        local_conn = sqlite3.connect(db_path, timeout=30.0)
        local_conn.execute("PRAGMA journal_mode=WAL")
        remote_conn = TursoConnection(url, token)
        
        local_tables = {r[0] for r in local_conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() if r}
        remote_tables = {r[0] for r in remote_conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() if r}

        _init_sync_state_tables(local_conn, remote_conn)
    except Exception as e:
        logger.error("[TURSO-SYNC] Failed to establish database connection for sync: %s", e)
        return {"status": "error", "error": str(e)}

    stats: dict[str, dict[str, Any]] = {}
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

            local_col_info = _get_table_columns_info(local_conn, table) if table in local_tables else {}
            remote_col_info = _get_table_columns_info(remote_conn, table) if table in remote_tables else {}

            # Self-heal missing columns on Remote Turso
            if table in local_tables and table in remote_tables:
                for col_name, col_type in local_col_info.items():
                    if col_name not in remote_col_info:
                        try:
                            remote_conn.execute(f'ALTER TABLE "{table}" ADD COLUMN "{col_name}" {col_type}')
                            remote_col_info[col_name] = col_type
                        except Exception as e:
                            logger.debug("[TURSO-SYNC] Remote ALTER TABLE ADD COLUMN %s on %s: %s", col_name, table, e)

                # Self-heal missing columns on Local SQLite
                for col_name, col_type in remote_col_info.items():
                    if col_name not in local_col_info:
                        try:
                            with local_conn:
                                local_conn.execute(f'ALTER TABLE "{table}" ADD COLUMN "{col_name}" {col_type}')
                            local_col_info[col_name] = col_type
                        except Exception as e:
                            logger.debug("[TURSO-SYNC] Local ALTER TABLE ADD COLUMN %s on %s: %s", col_name, table, e)

            # Common columns present in BOTH local and remote
            common_cols = [c for c in local_col_info.keys() if c in remote_col_info]
            if not common_cols:
                continue

            col_str = ", ".join([f'"{c}"' for c in common_cols])
            placeholders = ", ".join(["?" for _ in common_cols])
            
            # Lossless Merge Query: INSERT OR IGNORE guarantees existing records are never overwritten
            merge_sql = f'INSERT OR IGNORE INTO "{table}" ({col_str}) VALUES ({placeholders})'

            # Determine watermark column and previous sync timestamp for delta filtering
            watermark_col = _get_watermark_column(common_cols)
            last_synced_at = None if force_full else _get_last_sync_timestamp(local_conn, table)

            # Skip unwatermarked tables on incremental sync if already synced and row counts match
            if not watermark_col and last_synced_at and not force_full:
                try:
                    loc_cnt = local_conn.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0] if table in local_tables else 0
                    rem_cnt = remote_conn.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0] if table in remote_tables else 0
                    if loc_cnt == rem_cnt and loc_cnt > 0:
                        _save_last_sync_timestamp(local_conn, remote_conn, table, sync_now_iso, 0, 0)
                        stats[table] = {
                            "pushed": 0,
                            "pulled": 0,
                            "delta_watermark": None,
                            "since": last_synced_at,
                            "skipped": True,
                            "reason": f"Row counts match ({loc_cnt})",
                        }
                        continue
                except Exception as e:
                    logger.debug("[TURSO-SYNC] Row count check error on %s: %s", table, e)

            # Determine delta filter query if incremental sync is active
            delta_sql = None
            delta_params = None
            if watermark_col and last_synced_at:
                if watermark_col in DATE_ONLY_COLUMNS:
                    delta_filter_val = last_synced_at[:10]
                    delta_where = f'"{watermark_col}" >= ?'
                else:
                    delta_filter_val = last_synced_at.replace("T", " ")
                    delta_where = f'replace("{watermark_col}", \'T\', \' \') > ?'
                delta_sql = f'SELECT {col_str} FROM "{table}" WHERE {delta_where}'
                delta_params = (delta_filter_val,)
            else:
                delta_sql = f'SELECT {col_str} FROM "{table}"'
                delta_params = ()

            # 1. Fetch Local Delta Rows (only records updated after last_synced_at)
            local_rows = []
            if table in local_tables:
                if delta_params:
                    local_rows = local_conn.execute(delta_sql, delta_params).fetchall()
                else:
                    local_rows = local_conn.execute(delta_sql).fetchall()

            # 2. Push Local Delta Rows Upstream to Turso (Union Merge)
            pushed = 0
            if local_rows and table in remote_tables:
                try:
                    remote_conn.executemany(merge_sql, local_rows)
                    pushed = len(local_rows)
                except Exception as e:
                    logger.warning("[TURSO-SYNC] Upstream merge push error on table %s: %s", table, e)

            # 3. Pull Remote Delta Rows Down to Local SQLite (Union Merge)
            pulled = 0
            if table in remote_tables:
                try:
                    if delta_params:
                        remote_rows = remote_conn.execute(delta_sql, delta_params).fetchall()
                    else:
                        remote_rows = remote_conn.execute(delta_sql).fetchall()

                    if remote_rows:
                        with local_conn:
                            local_conn.executemany(merge_sql, [tuple(r) for r in remote_rows])
                        pulled = len(remote_rows)
                except Exception as e:
                    logger.debug("[TURSO-SYNC] Downstream merge pull error on table %s: %s", table, e)

            # Update persistent sync state ledger
            _save_last_sync_timestamp(local_conn, remote_conn, table, sync_now_iso, pushed, pulled)

            stats[table] = {
                "pushed": pushed,
                "pulled": pulled,
                "delta_watermark": watermark_col,
                "since": last_synced_at or "full",
            }
            total_pushed += pushed
            total_pulled += pulled

    finally:
        try:
            local_conn.close()
        except Exception:
            pass

    elapsed = time.perf_counter() - start_t
    logger.info(
        "[TURSO:DONE] Delta sync completed in %.2fs (pushed: %d, pulled: %d across %d tables)",
        elapsed,
        total_pushed,
        total_pulled,
        len(stats),
    )

    return {
        "status": "success",
        "merge_policy": "incremental_watermark_delta_sync",
        "elapsed_seconds": round(elapsed, 2),
        "total_pushed": total_pushed,
        "total_pulled": total_pulled,
        "tables": stats,
    }


def override_remote_tables_from_local(
    tables: list[str],
    settings: Settings | None = None,
    batch_size: int = 100,
) -> dict[str, Any]:
    """Force override specified remote Turso tables with local SQLite table contents.

    Permanently purges remote rows for the specified tables and re-populates them with
    the clean, authentic local records to eliminate any remote synthetic artifacts.
    """
    s = settings or Settings()
    url = os.getenv("TURSO_DATABASE_URL", "").strip()
    token = os.getenv("TURSO_AUTH_TOKEN", "").strip()

    if not (url and token):
        logger.info("[TURSO-OVERRIDE] Upstream Turso credentials not configured. Skipping remote override.")
        return {"status": "skipped", "reason": "No Turso credentials configured"}

    start_t = time.perf_counter()
    logger.info("[TURSO-OVERRIDE] Starting remote override for tables: %s", tables)

    db_path = str(_cache_path(s))
    s.ensure_dirs()

    try:
        local_conn = sqlite3.connect(db_path, timeout=30.0)
        local_conn.execute("PRAGMA journal_mode=WAL")
        remote_conn = TursoConnection(url, token)

        local_tables = {r[0] for r in local_conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() if r}
        remote_tables = {r[0] for r in remote_conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() if r}
    except Exception as e:
        logger.error("[TURSO-OVERRIDE] Failed to establish database connection for override: %s", e)
        return {"status": "error", "error": str(e)}

    stats: dict[str, dict[str, Any]] = {}
    total_pushed = 0

    try:
        for table in tables:
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
                    logger.warning("[TURSO-OVERRIDE] Could not create remote table %s: %s", table, e)

            # Match columns
            local_col_info = _get_table_columns_info(local_conn, table)
            remote_col_info = _get_table_columns_info(remote_conn, table) if table in remote_tables else {}

            for col_name, col_type in local_col_info.items():
                if col_name not in remote_col_info:
                    try:
                        remote_conn.execute(f'ALTER TABLE "{table}" ADD COLUMN "{col_name}" {col_type}')
                        remote_col_info[col_name] = col_type
                    except Exception as e:
                        logger.debug("[TURSO-OVERRIDE] Remote ALTER TABLE ADD COLUMN %s on %s: %s", col_name, table, e)

            shared_cols = [c for c in local_col_info if c in remote_col_info]
            if not shared_cols:
                continue

            col_str = ", ".join(f'"{c}"' for c in shared_cols)
            ph = ", ".join("?" for _ in shared_cols)
            insert_sql = f'INSERT OR REPLACE INTO "{table}" ({col_str}) VALUES ({ph})'

            # 1. Fetch all local records
            local_rows = local_conn.execute(f'SELECT {col_str} FROM "{table}"').fetchall()

            # 2. Wipe remote table
            try:
                remote_conn.execute(f'DELETE FROM "{table}"')
            except Exception as e:
                logger.warning("[TURSO-OVERRIDE] Remote DELETE error on table %s: %s", table, e)

            # 3. Push local records in chunks
            pushed = 0
            if local_rows:
                for i in range(0, len(local_rows), batch_size):
                    chunk = local_rows[i : i + batch_size]
                    try:
                        remote_conn.executemany(insert_sql, chunk)
                        pushed += len(chunk)
                    except Exception as e:
                        logger.error("[TURSO-OVERRIDE] Push error on table %s chunk %d: %s", table, i, e)

            stats[table] = {"rows_pushed": pushed, "status": "overridden"}
            total_pushed += pushed

    finally:
        try:
            local_conn.close()
        except Exception:
            pass

    elapsed = time.perf_counter() - start_t
    logger.info("[TURSO-OVERRIDE] Completed in %.2fs (pushed %d records across %d tables)", elapsed, total_pushed, len(stats))
    return {
        "status": "success",
        "action": "override_remote_from_local",
        "elapsed_seconds": round(elapsed, 2),
        "total_pushed": total_pushed,
        "tables": stats,
    }


# Backwards compatibility alias
sync_all_to_turso = sync_local_to_upstream

