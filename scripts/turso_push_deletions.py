#!/usr/bin/env python3
"""turso_push_deletions.py -- Purge deletion remnants from remote Turso DB.

Compares local vs remote tickers per SYNC_TABLE. For any tickers present in remote
but NOT in local, issues DELETE on the remote Turso database. This cleans up rows
that should have been removed during sync but were missed.

Usage:
    python scripts/turso_push_deletions.py                # dry-run (default)
    python scripts/turso_push_deletions.py --apply        # actually delete
    python scripts/turso_push_deletions.py --apply --tables breakout_radar,kronos_predictions
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import logging

# ── Tables that do NOT have a 'ticker' column and must be skipped ──────────────
# These tables use non-ticker primary keys (user IDs, UUIDs, etc.) so the
# ticker-based deletion logic does not apply.
NON_TICKER_TABLES = frozenset({
    # Auth & Users
    "passcodes", "users", "user_auth", "user_sessions",
    "invite_codes", "friend_access", "otp_verifications", "ui_preferences",
    # Personal Finance & Lifestyle
    "trips", "trip_activities", "trip_groups", "trip_group_members",
    "trip_group_trips", "trip_itinerary_days", "trip_packing_items",
    "trip_packing_status", "credit_cards", "credit_card_otp_requests",
    "net_worth_snapshots",
    # Zepto Operations
    "zepto_employees", "zepto_salaries", "zepto_monthly_ratings",
    "zepto_expenses", "zepto_store_income", "zepto_income_split_settings",
    "zepto_candidates", "zepto_security_capital", "zepto_staffing_targets",
    # Universe / Generic
    "universes", "universe_freshness",
    # Alert Rules (row-level UUIDs)
    "alert_rules", "alert_rule_logs",
    # Automation & Telemetry (non-ticker PKs)
    "automation_schedules", "automation_schedule_logs",
    "ai_model_telemetry", "downstream_api_calls",
    "sidebar_badge_counters",
    # Provenance (UUID-based)
    "data_provenance_meta",
})

logger = logging.getLogger("turso_push_deletions")


# ──────────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────────

def _get_distinct_tickers(conn, table: str) -> set[str]:
    """Return set of distinct ticker values for a table (uses :table: syntax)."""
    rows = conn.execute(
        f'SELECT DISTINCT "ticker" FROM "{table}"'
    ).fetchall()
    return {r[0] for r in rows if r[0] is not None}


def _print_summary_table(results: dict) -> None:
    """Pretty-print a formatted summary table of remote-only tickers and deletions."""
    hdr = ("Table", "Remote", "Local", "Remote-Only", "Deletions")
    sep = ("-" * 36, "-" * 8, "-" * 8, "-" * 12, "-" * 10)
    print("\n" + "=" * 80)
    print("  REMOTE-ONLY TICKERS & DELETIONS SUMMARY")
    print("=" * 80)
    print(f"  {hdr[0]:<36} {hdr[1]:>8} {hdr[2]:>8} {hdr[3]:>12} {hdr[4]:>10}")
    print(f"  {sep[0]:<36} {sep[1]:>8} {sep[2]:>8} {sep[3]:>12} {sep[4]:>10}")

    total_remote = total_local = total_remote_only = total_deletions = 0
    any_remote_only = False

    for tbl, info in results.items():
        if info.get("skipped"):
            print(f"  {tbl:<36} {'--':>8} {'--':>8} {'SKIPPED':>12} {'--':>10}")
            continue
        rm = info.get("remote_count", 0)
        lc = info.get("local_count", 0)
        ro = info.get("remote_only", 0)
        dl = info.get("deletions", 0)
        total_remote += rm
        total_local += lc
        total_remote_only += ro
        total_deletions += dl
        if ro:
            any_remote_only = True
            tickers = ", ".join(info.get("remote_only_tickers", []))
            print(f"  {tbl:<36} {rm:>8} {lc:>8} {ro:>12} {dl:>10}")
            print(f"    -> {tickers}")
        else:
            print(f"  {tbl:<36} {rm:>8} {lc:>8} {ro:>12} {dl:>10}")

    print(f"  {'-' * 36} {'-' * 8} {'-' * 8} {'-' * 12} {'-' * 10}")
    print(f"  {'TOTAL':<36} {total_remote:>8} {total_local:>8} {total_remote_only:>12} {total_deletions:>10}")
    print("=" * 80)

    if total_remote_only == 0:
        print("  Remote database is clean. No orphan tickers found.\n")
    elif total_deletions > 0:
        print(f"  {total_deletions} rows deleted across {sum(1 for v in results.values() if v.get('deletions', 0) > 0)} tables.\n")
    else:
        print(f"  {total_remote_only} orphan tickers found in {sum(1 for v in results.values() if v.get('remote_only', 0) > 0)} tables. Re-run with --apply to purge.\n")


# ──────────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Compare local vs remote tickers for each SYNC_TABLE and purge "
            "remote-only deletion remnants."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--apply", action="store_true", default=False,
        help="Actually execute deletions (default is dry-run, print only).",
    )
    parser.add_argument(
        "--tables", type=str, default=None,
        help="Comma-separated list of tables to process (default: all SYNC_TABLES).",
    )
    parser.add_argument(
        "--batch-size", type=int, default=100,
        help="Max DELETE statements per HTTP batch request (default: 100).",
    )
    parser.add_argument(
        "--rate-limit", type=float, default=0.5,
        help="Seconds between remote API calls (default: 0.5).",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", default=False,
        help="Print debug/SQL output.",
    )
    args = parser.parse_args()

    # ── Turso credentials check ─────────────────────────────────────────────
    url = os.getenv("TURSO_DATABASE_URL", "").strip()
    token = os.getenv("TURSO_AUTH_TOKEN", "").strip()

    if not url or not token:
        print("TURSO_DATABASE_URL / TURSO_AUTH_TOKEN is not set. Nothing to do.")
        return 0

    # ── Import project modules ──────────────────────────────────────────────
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from earnings_engine.data.turso_sync import SYNC_TABLES
    from earnings_engine.data.db import TursoConnection, _cache_path
    from earnings_engine.config import Settings

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, format="%(levelname)s: %(message)s")
    else:
        logging.basicConfig(level=logging.INFO, format="%(message)s")

    # ── Connections ──────────────────────────────────────────────────────────
    remote_conn = TursoConnection(url, token)
    settings = Settings()
    settings.ensure_dirs()
    import sqlite3
    local_conn = sqlite3.connect(str(_cache_path(settings)), timeout=30.0)
    local_conn.execute("PRAGMA journal_mode=WAL")

    # Quick connectivity check
    try:
        remote_conn.execute("SELECT 1")
    except Exception as exc:
        print(f"ERROR: Cannot reach Turso remote: {exc}")
        return 1

    # ── Table list ──────────────────────────────────────────────────────────
    if args.tables:
        requested = [t.strip() for t in args.tables.split(",") if t.strip()]
        table_list = [t for t in requested if t in SYNC_TABLES]
        unknown = [t for t in requested if t not in SYNC_TABLES]
        if unknown:
            print(f"WARNING: Tables not in SYNC_TABLES (skipped): {', '.join(unknown)}")
    else:
        table_list = list(SYNC_TABLES)

    # ── Process tables ──────────────────────────────────────────────────────
    results: dict[str, dict] = {}
    pending_deletes: list[tuple[str, str]] = []   # (table, ticker)

    for table in table_list:
        info: dict = {"remote_count": 0, "local_count": 0, "remote_only": 0,
                      "deletions": 0, "remote_only_tickers": []}

        # Check if the table exists remotely
        try:
            remote_tables = {
                r[0] for r in remote_conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall() if r
            }
            if table not in remote_tables:
                info["skipped"] = True
                info["skip_reason"] = "table does not exist on remote"
                results[table] = info
                logger.info("SKIP %-36s  (not on remote)", table)
                time.sleep(args.rate_limit)
                continue
        except Exception as exc:
            info["skipped"] = True
            info["skip_reason"] = str(exc)
            results[table] = info
            logger.info("SKIP %-36s  (error listing remote tables: %s)", table, exc)
            time.sleep(args.rate_limit)
            continue

        # Check if table has a ticker column locally
        if table not in NON_TICKER_TABLES:
            try:
                cols = {row[1] for row in local_conn.execute(f"PRAGMA table_info({table})").fetchall()}
                if "ticker" not in cols:
                    info["skipped"] = True
                    info["skip_reason"] = "no ticker column"
                    results[table] = info
                    logger.info("SKIP %-36s  (no ticker column locally)", table)
                    time.sleep(args.rate_limit)
                    continue
            except Exception:
                info["skipped"] = True
                info["skip_reason"] = "table does not exist locally"
                results[table] = info
                logger.info("SKIP %-36s  (error reading local table info)", table)
                time.sleep(args.rate_limit)
                continue
        else:
            info["skipped"] = True
            info["skip_reason"] = "non-ticker table"
            results[table] = info
            logger.info("SKIP %-36s  (non-ticker table)", table)
            continue

        # Fetch distinct tickers from remote
        try:
            remote_tickers = _get_distinct_tickers(remote_conn, table)
            info["remote_count"] = len(remote_tickers)
        except Exception as exc:
            info["skipped"] = True
            info["skip_reason"] = f"remote query error: {exc}"
            results[table] = info
            logger.warning("ERROR %-36s  (remote query: %s)", table, exc)
            time.sleep(args.rate_limit)
            continue

        time.sleep(args.rate_limit)

        # Fetch distinct tickers from local
        try:
            local_tickers = _get_distinct_tickers(local_conn, table)
            info["local_count"] = len(local_tickers)
        except Exception as exc:
            info["skipped"] = True
            info["skip_reason"] = f"local query error: {exc}"
            results[table] = info
            logger.warning("ERROR %-36s  (local query: %s)", table, exc)
            continue

        # Compute remote-only (deletion remnants)
        remote_only = sorted(remote_tickers - local_tickers)
        info["remote_only"] = len(remote_only)
        info["remote_only_tickers"] = remote_only

        if remote_only:
            any_remote_only = True
            logger.info(
                "FOUND %-36s  remote-only=%d  tickers=%s",
                table, len(remote_only),
                ", ".join(remote_only[:10]) + ("..." if len(remote_only) > 10 else ""),
            )
            if not args.apply:
                for t in remote_only:
                    pending_deletes.append((table, t))
            else:
                # Batch DELETEs for this table (Turso executemany batches up to 500)
                delete_sql = f'DELETE FROM "{table}" WHERE "ticker" = ?'
                batch_size = args.batch_size
                total_deleted = 0
                for i in range(0, len(remote_only), batch_size):
                    chunk = remote_only[i : i + batch_size]
                    params = [(t,) for t in chunk]
                    try:
                        cursor = remote_conn.executemany(delete_sql, params)
                        deleted = cursor.rowcount if cursor.rowcount > 0 else len(chunk)
                        total_deleted += deleted
                        logger.debug(
                            "  DELETE batch %d-%d on %s: %d affected",
                            i, i + len(chunk), table, deleted,
                        )
                    except Exception as exc:
                        logger.error(
                            "  DELETE batch %d-%d on %s FAILED: %s",
                            i, i + len(chunk), table, exc,
                        )
                    if i + batch_size < len(remote_only):
                        time.sleep(args.rate_limit)
                info["deletions"] = total_deleted
        else:
            logger.debug("OK   %-36s  (no remote-only tickers)", table)

        results[table] = info

    # ── Summary ─────────────────────────────────────────────────────────────
    _print_summary_table(results)

    if pending_deletes:
        print(f"DRY-RUN: {len(pending_deletes)} rows would be deleted. Re-run with --apply to execute.\n")

    any_deletions = any(r.get("deletions", 0) > 0 for r in results.values())
    return 0 if not any_deletions else 2


if __name__ == "__main__":
    sys.exit(main())
