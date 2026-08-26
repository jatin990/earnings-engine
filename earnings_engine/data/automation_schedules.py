"""Automation Schedules & Background Task Monitor.

Tracks recurring engine schedules, last execution duration, status (active/idle/running/error),
next scheduled execution countdowns, and summary audit metrics in SQLite / Turso.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any

from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection

logger = logging.getLogger(__name__)

# Standard automated background schedules definition registry
DEFAULT_SCHEDULES: list[dict[str, Any]] = [
    {
        "job_id": "breakout_hot_rescore",
        "job_name": "⚡ Breakout Hot Rescore",
        "category": "Breakout Radar",
        "interval_seconds": 60,
        "description": "High-frequency parallel re-scoring of Hot candidate setups using latest live prices.",
    },
    {
        "job_id": "breakout_warm_rescore",
        "job_name": "⚡ Breakout Warm Rescore",
        "category": "Breakout Radar",
        "interval_seconds": 300,
        "description": "Re-scores coiling/warm stocks to detect promotions into Hot or demotions.",
    },
    {
        "job_id": "breakout_cold_scan",
        "job_name": "🌐 Cold Universe Sweep",
        "category": "Breakout Radar",
        "interval_seconds": 3600,
        "description": "Full universe multi-factor scan discovering fresh compression and momentum setups.",
    },
    {
        "job_id": "news_catalyst_harvest",
        "job_name": "📰 News Catalyst Harvester",
        "category": "Market Catalysts",
        "interval_seconds": 600,
        "description": "Continuous harvesting of corporate order wins, earnings surprises, and regulatory filings.",
    },
    {
        "job_id": "category_scanner_sweep",
        "job_name": "🔍 Multi-Category Scanner",
        "category": "Scanner",
        "interval_seconds": 1800,
        "description": "Multi-category technical scans across 52W Highs, Volume Surges, and Squeeze Coils.",
    },
    {
        "job_id": "quarter_repeaters_sync",
        "job_name": "🔁 Quarter Repeaters Sync",
        "category": "Seasonality",
        "interval_seconds": 7200,
        "description": "Historical quarter-over-quarter earnings surprise repeater pattern evaluation.",
    },
]


def init_automation_schedules(settings: Settings | None = None) -> None:
    """Ensure all default background schedules are seeded in the database."""
    settings = settings or Settings()
    try:
        from earnings_engine.data.migrations import apply_migrations
        apply_migrations(settings)
        conn = get_db_connection(settings)
        now_dt = datetime.now(timezone.utc)
        now_iso = now_dt.isoformat()

        for s in DEFAULT_SCHEDULES:
            next_iso = (now_dt + timedelta(seconds=s["interval_seconds"])).isoformat()
            conn.execute(
                """
                INSERT OR IGNORE INTO automation_schedules (
                    job_id, job_name, category, interval_seconds,
                    last_run_at, next_run_at, status, last_duration_s,
                    total_runs, last_summary, error_message, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    s["job_id"],
                    s["job_name"],
                    s["category"],
                    s["interval_seconds"],
                    None,
                    next_iso,
                    "active",
                    0.0,
                    0,
                    f"Initialized. Ready for scheduled run ({s['interval_seconds']}s interval).",
                    None,
                    now_iso,
                ),
            )
        if hasattr(conn, "commit"):
            conn.commit()
    except Exception as e:
        logger.debug("[SCHEDULES] Init schedules error: %s", e)


def record_job_start(job_id: str, settings: Settings | None = None) -> None:
    """Record that a background job has started execution."""
    settings = settings or Settings()
    try:
        conn = get_db_connection(settings)
        now_iso = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """
            UPDATE automation_schedules
            SET status = 'running', updated_at = ?
            WHERE job_id = ?
            """,
            (now_iso, job_id),
        )
        if hasattr(conn, "commit"):
            conn.commit()
    except Exception as e:
        logger.debug("[SCHEDULES] Record job start error for %s: %s", job_id, e)


def record_job_finish(
    job_id: str,
    duration_s: float = 0.0,
    summary: str = "",
    error_message: str | None = None,
    settings: Settings | None = None,
) -> None:
    """Record job completion, update next scheduled run timestamp, and increment run counter."""
    settings = settings or Settings()
    try:
        conn = get_db_connection(settings)
        now_dt = datetime.now(timezone.utc)
        now_iso = now_dt.isoformat()

        # Find interval
        row = conn.execute("SELECT interval_seconds, total_runs FROM automation_schedules WHERE job_id = ?", (job_id,)).fetchone()
        interval = 300
        total_runs = 0
        if row:
            interval = int(row[0] or 300)
            total_runs = int(row[1] or 0)
        else:
            # Fallback to default definition if missing
            match = next((s for s in DEFAULT_SCHEDULES if s["job_id"] == job_id), None)
            if match:
                interval = match["interval_seconds"]

        next_iso = (now_dt + timedelta(seconds=interval)).isoformat()
        status = "error" if error_message else "active"

        conn.execute(
            """
            UPDATE automation_schedules
            SET last_run_at = ?,
                next_run_at = ?,
                status = ?,
                last_duration_s = ?,
                total_runs = ?,
                last_summary = ?,
                error_message = ?,
                updated_at = ?
            WHERE job_id = ?
            """,
            (
                now_iso,
                next_iso,
                status,
                round(float(duration_s), 2),
                total_runs + 1,
                summary,
                error_message,
                now_iso,
                job_id,
            ),
        )
        if hasattr(conn, "commit"):
            conn.commit()
    except Exception as e:
        logger.debug("[SCHEDULES] Record job finish error for %s: %s", job_id, e)


def get_all_schedules(settings: Settings | None = None) -> list[dict[str, Any]]:
    """Retrieve all automation schedule states with dynamic countdown seconds."""
    settings = settings or Settings()
    init_automation_schedules(settings)
    schedules: list[dict[str, Any]] = []

    try:
        conn = get_db_connection(settings)
        rows = conn.execute("SELECT * FROM automation_schedules ORDER BY category, job_name").fetchall()
        now_dt = datetime.now(timezone.utc)

        for r in rows:
            if hasattr(r, "keys"):
                d = dict(r)
            else:
                d = {
                    "job_id": r[0],
                    "job_name": r[1],
                    "category": r[2],
                    "interval_seconds": r[3],
                    "last_run_at": r[4],
                    "next_run_at": r[5],
                    "status": r[6],
                    "last_duration_s": r[7],
                    "total_runs": r[8],
                    "last_summary": r[9],
                    "error_message": r[10],
                    "updated_at": r[11],
                }

            # Calculate live seconds until next scheduled execution
            secs_until = 0
            if d.get("next_run_at"):
                try:
                    next_dt = datetime.fromisoformat(d["next_run_at"].replace("Z", "+00:00"))
                    secs_until = max(0, int((next_dt - now_dt).total_seconds()))
                except Exception:
                    secs_until = d.get("interval_seconds", 60)
            else:
                secs_until = d.get("interval_seconds", 60)

            d["seconds_until_next"] = secs_until
            d["interval_formatted"] = _format_interval(d.get("interval_seconds", 60))
            d["last_run_formatted"] = _format_time_ago(d.get("last_run_at"))
            d["next_run_formatted"] = _format_time_in(secs_until)
            schedules.append(d)

    except Exception as e:
        logger.warning("[SCHEDULES] Failed fetching schedules: %s", e)

    return schedules


def get_schedule(job_id: str, settings: Settings | None = None) -> dict[str, Any] | None:
    """Retrieve a single automation schedule state by job_id."""
    schedules = get_all_schedules(settings)
    for s in schedules:
        if s.get("job_id") == job_id:
            return s
    return None


def _format_interval(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        return f"{seconds // 60}m"
    else:
        return f"{seconds // 3600}h"


def _format_time_ago(iso_str: str | None) -> str:
    if not iso_str:
        return "Never"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        delta = datetime.now(timezone.utc) - dt
        secs = max(0, int(delta.total_seconds()))
        if secs < 60:
            return f"{secs}s ago"
        elif secs < 3600:
            return f"{secs // 60}m ago"
        elif secs < 86400:
            return f"{secs // 3600}h ago"
        else:
            return f"{secs // 86400}d ago"
    except Exception:
        return iso_str[:16]


def _format_time_in(seconds: int) -> str:
    if seconds <= 0:
        return "Due now"
    m = seconds // 60
    s = seconds % 60
    if m > 0:
        return f"in {m}m {s}s"
    return f"in {s}s"
