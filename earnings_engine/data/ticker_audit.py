"""Persistent audit logging for on-demand ticker refreshes and metric recalculations."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection
from earnings_engine.logging_utils import get_logger

logger = get_logger("earnings_engine.data.ticker_audit")

_INITIALIZED_DBS: set[str] = set()


def init_audit_db(settings: Settings | None = None) -> None:
    """Initialize the audit log table once per database target."""
    settings = settings or Settings()
    db_key = str(settings.data_dirs.get("prices", "default"))
    if db_key in _INITIALIZED_DBS:
        return
    conn = get_db_connection(settings)
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ticker_audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                refreshed_at TEXT NOT NULL,
                has_changes INTEGER NOT NULL DEFAULT 0,
                changes_summary TEXT NOT NULL,
                previous_values TEXT,
                updated_values TEXT,
                diff_json TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_ticker_time ON ticker_audit_log (ticker, refreshed_at DESC)")
        conn.commit()
    _INITIALIZED_DBS.add(db_key)


def record_audit_entry(
    ticker: str,
    has_changes: bool,
    changes_summary: list[str] | str,
    previous_values: dict[str, Any] | None = None,
    updated_values: dict[str, Any] | None = None,
    diff_data: dict[str, Any] | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Record an audit trail entry for a recalculated ticker."""
    settings = settings or Settings()
    init_audit_db(settings)

    ticker = ticker.strip().upper()
    now_iso = datetime.now().isoformat(timespec="seconds")
    summary_text = "\n".join(changes_summary) if isinstance(changes_summary, list) else str(changes_summary or "")
    prev_json = json.dumps(previous_values or {}, default=str)
    upd_json = json.dumps(updated_values or {}, default=str)
    diff_json = json.dumps(diff_data or {}, default=str)

    conn = get_db_connection(settings)
    with conn:
        cursor = conn.execute(
            """
            INSERT INTO ticker_audit_log 
            (ticker, refreshed_at, has_changes, changes_summary, previous_values, updated_values, diff_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ticker,
                now_iso,
                1 if has_changes else 0,
                summary_text,
                prev_json,
                upd_json,
                diff_json,
            ),
        )
        conn.commit()
        entry_id = cursor.lastrowid

    logger.info("Recorded audit log for %s (id=%s, has_changes=%s)", ticker, entry_id, has_changes)
    return {
        "id": entry_id,
        "ticker": ticker,
        "refreshed_at": now_iso,
        "has_changes": bool(has_changes),
        "changes_summary": summary_text,
        "previous_values": previous_values or {},
        "updated_values": updated_values or {},
        "diff_data": diff_data or {},
    }


def get_audit_history(
    ticker: str | None = None,
    limit: int = 50,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """Retrieve audit history for a specific ticker or across all recent refreshes."""
    settings = settings or Settings()
    init_audit_db(settings)

    conn = get_db_connection(settings)
    if ticker:
        sym = ticker.strip().upper()
        rows = conn.execute(
            """
            SELECT id, ticker, refreshed_at, has_changes, changes_summary, previous_values, updated_values, diff_json
            FROM ticker_audit_log
            WHERE ticker = ?
            ORDER BY refreshed_at DESC, id DESC
            LIMIT ?
            """,
            (sym, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT id, ticker, refreshed_at, has_changes, changes_summary, previous_values, updated_values, diff_json
            FROM ticker_audit_log
            ORDER BY refreshed_at DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    results = []
    for r in rows:
        try:
            prev_val = json.loads(r[5]) if r[5] else {}
        except Exception:
            prev_val = {}
        try:
            upd_val = json.loads(r[6]) if r[6] else {}
        except Exception:
            upd_val = {}
        try:
            diff_val = json.loads(r[7]) if r[7] else {}
        except Exception:
            diff_val = {}

        results.append({
            "id": r[0],
            "ticker": r[1],
            "refreshed_at": r[2],
            "has_changes": bool(r[3]),
            "changes_summary": r[4],
            "previous_values": prev_val,
            "updated_values": upd_val,
            "diff_data": diff_val,
        })
    return results
