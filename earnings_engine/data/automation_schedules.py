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
        "job_id": "breakout_all_strategies_parallel",
        "job_name": "🚀 Breakout All 5 Strategies Parallel Sweep",
        "category": "Breakout Radar",
        "interval_seconds": 1800,
        "run_after_hours": 0,
        "market_session": "market_hours_only",
        "params_json": '{"universe": "NSE_ALL", "strategy": "ALL", "min_score": 30}',
        "description": "Parallel background sweep executing all 5 quantitative, delivery, derivatives, and volume profile breakout strategies simultaneously across the market universe.",
    },
    {
        "job_id": "breakout_delivery_absorption_scan",
        "job_name": "🏛️ NSE Delivery Absorption Sweep",
        "category": "Breakout Radar",
        "interval_seconds": 3600,
        "run_after_hours": 0,
        "market_session": "market_hours_only",
        "is_enabled": 0,
        "params_json": '{"universe": "NSE_ALL", "strategy": "NSE_DELIVERY_ABSORPTION", "min_score": 30}',
        "description": "Automated scan identifying institutional block delivery accumulation spikes exceeding 60% and delivery resistance ceilings.",
    },
    {
        "job_id": "breakout_fo_call_wall_scan",
        "job_name": "🎯 NSE F&O Call Wall Gamma Squeeze",
        "category": "Breakout Radar",
        "interval_seconds": 1800,
        "run_after_hours": 0,
        "market_session": "market_hours_only",
        "is_enabled": 0,
        "params_json": '{"universe": "NSE_ALL", "strategy": "NSE_FO_CALL_WALL", "min_score": 30}',
        "description": "Derivatives option chain scanner evaluating call open interest walls, short-covering velocity, and PCR momentum.",
    },
    {
        "job_id": "breakout_volume_profile_scan",
        "job_name": "📊 Volume Profile VAH Expansion Scan",
        "category": "Breakout Radar",
        "interval_seconds": 3600,
        "run_after_hours": 0,
        "market_session": "market_hours_only",
        "is_enabled": 0,
        "params_json": '{"universe": "NSE_ALL", "strategy": "VOLUME_PROFILE_VAH", "min_score": 30}',
        "description": "63-day volume profile analysis detecting Value Area High (VAH) breakouts and low volume node liquidity vacuums.",
    },
    {
        "job_id": "breakout_donchian_squeeze_scan",
        "job_name": "🌪️ Donchian TTM Volatility Squeeze",
        "category": "Breakout Radar",
        "interval_seconds": 1800,
        "run_after_hours": 0,
        "market_session": "market_hours_only",
        "is_enabled": 0,
        "params_json": '{"universe": "NSE_ALL", "strategy": "DONCHIAN_TTM_SQUEEZE", "min_score": 30}',
        "description": "John Carter TTM Squeeze (Bollinger inside Keltner) and 55-Day Donchian channel trend breakout scanner.",
    },
    {
        "job_id": "breakout_hot_rescore",
        "job_name": "⚡ Breakout Hot Rescore",
        "category": "Breakout Radar",
        "interval_seconds": 60,
        "run_after_hours": 0,
        "market_session": "market_hours_only",
        "params_json": '{"universe": "NSE_ALL", "pool": "hot", "strategy": "ALL"}',
        "description": "High-frequency parallel re-scoring of Hot candidate setups using latest live prices during market hours across all strategies.",
    },
    {
        "job_id": "breakout_warm_rescore",
        "job_name": "⚡ Breakout Warm Rescore",
        "category": "Breakout Radar",
        "interval_seconds": 300,
        "run_after_hours": 0,
        "market_session": "market_hours_only",
        "params_json": '{"universe": "NSE_ALL", "pool": "warm", "strategy": "ALL"}',
        "description": "Re-scores coiling/warm stocks across all breakout models to detect promotions into Hot or demotions during market hours.",
    },
    {
        "job_id": "breakout_cold_scan",
        "job_name": "🌐 Cold Universe Sweep (Classic)",
        "category": "Breakout Radar",
        "interval_seconds": 3600,
        "run_after_hours": 0,
        "market_session": "market_hours_only",
        "is_enabled": 0,
        "params_json": '{"universe": "NSE_ALL", "strategy": "CLASSIC_TECHNICAL", "min_score": 35}',
        "description": "Full universe multi-factor scan discovering fresh compression and momentum setups using Classic 20D/52W model.",
    },
    {
        "job_id": "news_catalyst_harvest",
        "job_name": "📰 News Catalyst Harvester",
        "category": "Market Catalysts",
        "interval_seconds": 600,
        "run_after_hours": 0,
        "market_session": "market_hours_only",
        "params_json": '{"watchlist": "my_watchlist", "limit": 10}',
        "description": "Continuous harvesting of corporate order wins, earnings surprises, and regulatory filings.",
    },
    {
        "job_id": "category_scanner_sweep",
        "job_name": "🔍 Multi-Category Scanner",
        "category": "Scanner",
        "interval_seconds": 1800,
        "run_after_hours": 0,
        "market_session": "market_hours_only",
        "params_json": '{"universe": "NSE_TOP", "limit": 100}',
        "description": "Multi-category technical scans across 52W Highs, Volume Surges, and Squeeze Coils.",
    },
    {
        "job_id": "quarter_repeaters_sync",
        "job_name": "🔁 Quarter Repeaters Sync",
        "category": "Seasonality",
        "interval_seconds": 7200,
        "run_after_hours": 0,
        "market_session": "market_hours_only",
        "params_json": '{"universe": "NSE_ALL"}',
        "description": "Historical quarter-over-quarter earnings surprise repeater pattern evaluation.",
    },
    {
        "job_id": "institutional_sync",
        "job_name": "🏛️ Institutional Flows Sync",
        "category": "Institutional",
        "interval_seconds": 7200,
        "run_after_hours": 0,
        "market_session": "market_hours_only",
        "params_json": '{"watchlist": "my_watchlist"}',
        "description": "Continuous sync of institutional fund portfolios, FII/DII entries, and block deals.",
    },
    {
        "job_id": "swing_hot_rescore",
        "job_name": "🔄 Swing Hot Buy Zone Rescore",
        "category": "Swing Trading",
        "interval_seconds": 300,
        "run_after_hours": 0,
        "market_session": "market_hours_only",
        "params_json": '{"universe": "ALL", "pool": "hot"}',
        "description": "Rapid 5-minute re-evaluation of stocks actively in the horizontal Support Buy Zone.",
    },
    {
        "job_id": "swing_warm_rescore",
        "job_name": "🔄 Swing Warm Pool Rescore",
        "category": "Swing Trading",
        "interval_seconds": 900,
        "run_after_hours": 0,
        "market_session": "market_hours_only",
        "params_json": '{"universe": "ALL", "pool": "warm"}',
        "description": "15-minute evaluation of coiling swing channels for promotion into Hot Buy Zone.",
    },
    {
        "job_id": "swing_cold_scan",
        "job_name": "🔄 Swing Full Channel Sweep",
        "category": "Swing Trading",
        "interval_seconds": 3600,
        "run_after_hours": 0,
        "market_session": "market_hours_only",
        "params_json": '{"universe": "ALL", "min_score": 20}',
        "description": "Hourly universe sweep discovering fresh support/resistance horizontal trading bands.",
    },
    {
        "job_id": "kronos_hot_pool_rescore",
        "job_name": "🔮 Kronos Hot Pool AI Forecast",
        "category": "AI Forecasting",
        "interval_seconds": 600,
        "run_after_hours": 0,
        "market_session": "market_hours_only",
        "is_enabled": 0,
        "params_json": '{"merge_tolerance_pct": 0.5, "lookback": 120, "pred_len": 14}',
        "description": "Background Kronos AI sequence prediction for Hot pool stocks with ±0.5% audit merging.",
    },
    {
        "job_id": "confluence_radar_sweep",
        "job_name": "🎯 Cross-Strategy Confluence Radar Sweep",
        "category": "Confluence Radar",
        "interval_seconds": 900,
        "run_after_hours": 0,
        "market_session": "market_hours_only",
        "params_json": '{"min_level": 1, "limit": 50}',
        "description": "15-minute background sweep discovering high-conviction multi-module confluence setups across Breakout, Swing, AI Consensus, and Institutional Delivery.",
    },
    {
        "job_id": "kronos_cache_warmup",
        "job_name": "🧠 Kronos Forecast Warmup",
        "category": "Custom",
        "interval_seconds": 86400,
        "run_after_hours": 0,
        "market_session": "market_hours_only",
        "is_enabled": 0,
        "params_json": '{"watchlist": "my_watchlist", "device": "cuda:0"}',
        "description": "Pre-computes and caches Kronos AI 14-day sequence price predictions.",
    },
]


_SCHEDULES_SEEDED = False


def init_automation_schedules(settings: Settings | None = None, force: bool = False) -> None:
    """Ensure all default background schedules are seeded in the database."""
    global _SCHEDULES_SEEDED
    if _SCHEDULES_SEEDED and not force:
        return
    settings = settings or Settings()
    try:
        from earnings_engine.data.migrations import apply_migrations
        apply_migrations(settings)
        conn = get_db_connection(settings)
        now_dt = datetime.now(timezone.utc)
        now_iso = now_dt.isoformat()

        for s in DEFAULT_SCHEDULES:
            next_iso = (now_dt + timedelta(seconds=s["interval_seconds"])).isoformat()
            run_after = int(s.get("run_after_hours", 0))
            session = s.get("market_session", "market_hours_only")
            is_en = int(s.get("is_enabled", 1))
            conn.execute(
                """
                INSERT OR IGNORE INTO automation_schedules (
                    job_id, job_name, category, interval_seconds,
                    last_run_at, next_run_at, status, last_duration_s,
                    total_runs, last_summary, error_message, updated_at,
                    is_enabled, params_json, run_after_hours, market_session
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    s["job_id"],
                    s["job_name"],
                    s["category"],
                    s["interval_seconds"],
                    None,
                    next_iso,
                    "active" if is_en else "paused",
                    0.0,
                    0,
                    f"Initialized. Ready for scheduled run ({s['interval_seconds']}s interval).",
                    None,
                    now_iso,
                    is_en,
                    s.get("params_json"),
                    run_after,
                    session,
                ),
            )
            # If params_json is null on existing row, update it
            if s.get("params_json"):
                conn.execute(
                    """
                    UPDATE automation_schedules
                    SET params_json = ?
                    WHERE job_id = ? AND (params_json IS NULL OR params_json = '')
                    """,
                    (s["params_json"], s["job_id"]),
                )
            conn.execute(
                """
                UPDATE automation_schedules
                SET run_after_hours = ?,
                    market_session = ?
                WHERE job_id = ?
                """,
                (run_after, session, s["job_id"]),
            )
            # If job is disabled in code defaults (e.g. redundant individual sweeps or kronos), ensure is_enabled is synced
            if is_en == 0:
                conn.execute(
                    """
                    UPDATE automation_schedules
                    SET is_enabled = 0,
                        status = 'paused'
                    WHERE job_id = ?
                    """,
                    (s["job_id"],),
                )

        # 1. Reset any stuck 'running' status back to 'active' on server startup
        conn.execute("UPDATE automation_schedules SET status = 'active' WHERE status = 'running'")

        # 2. Reset overdue next_run_at timestamps so jobs don't storm-fire concurrently on startup
        overdue_rows = conn.execute("SELECT job_id, interval_seconds, next_run_at FROM automation_schedules WHERE is_enabled = 1").fetchall()
        stagger_offset = 60
        for r_job, r_int, r_next in overdue_rows:
            is_overdue = False
            if not r_next:
                is_overdue = True
            else:
                try:
                    dt = datetime.fromisoformat(r_next.replace("Z", "+00:00"))
                    if dt < now_dt:
                        is_overdue = True
                except Exception:
                    is_overdue = True
            if is_overdue:
                fut_iso = (now_dt + timedelta(seconds=max(int(r_int or 600), stagger_offset))).isoformat()
                conn.execute("UPDATE automation_schedules SET next_run_at = ?, updated_at = ? WHERE job_id = ?", (fut_iso, now_iso, r_job))
                stagger_offset += 60

        if hasattr(conn, "commit"):
            conn.commit()
        _SCHEDULES_SEEDED = True
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


def append_schedule_log(
    job_id: str,
    started_at: str,
    finished_at: str | None = None,
    duration_s: float = 0.0,
    status: str = "success",
    summary: str = "",
    error_details: str | None = None,
    settings: Settings | None = None,
) -> None:
    """Record an execution run record in the automation_schedule_logs table."""
    settings = settings or Settings()
    try:
        conn = get_db_connection(settings)
        now_iso = datetime.now(timezone.utc).isoformat()
        
        # Get category and job_name if available
        row = conn.execute("SELECT job_name, category FROM automation_schedules WHERE job_id = ?", (job_id,)).fetchone()
        job_name = row[0] if row else job_id
        category = row[1] if row else "Automation"

        conn.execute(
            """
            INSERT INTO automation_schedule_logs (
                job_id, job_name, category, started_at, finished_at,
                duration_s, status, summary, error_details, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                job_name,
                category,
                started_at,
                finished_at or now_iso,
                round(float(duration_s), 2),
                status,
                summary,
                error_details,
                now_iso,
            ),
        )
        if hasattr(conn, "commit"):
            conn.commit()
    except Exception as e:
        logger.debug("[SCHEDULES] Append schedule log error for %s: %s", job_id, e)


def get_schedule_logs(
    job_id: str | None = None,
    limit: int = 50,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """Fetch execution run logs for a specific job or all background jobs."""
    settings = settings or Settings()
    logs: list[dict[str, Any]] = []
    try:
        conn = get_db_connection(settings)
        if job_id:
            rows = conn.execute(
                """
                SELECT id, job_id, job_name, category, started_at, finished_at,
                       duration_s, status, summary, error_details, created_at
                FROM automation_schedule_logs
                WHERE job_id = ?
                ORDER BY started_at DESC
                LIMIT ?
                """,
                (job_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, job_id, job_name, category, started_at, finished_at,
                       duration_s, status, summary, error_details, created_at
                FROM automation_schedule_logs
                ORDER BY started_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        for r in rows:
            if hasattr(r, "keys"):
                d = dict(r)
            else:
                d = {
                    "id": r[0],
                    "job_id": r[1],
                    "job_name": r[2],
                    "category": r[3],
                    "started_at": r[4],
                    "finished_at": r[5],
                    "duration_s": r[6],
                    "status": r[7],
                    "summary": r[8],
                    "error_details": r[9],
                    "created_at": r[10],
                }
            d["started_ago"] = _format_time_ago(d.get("started_at"))
            logs.append(d)
    except Exception as e:
        logger.debug("[SCHEDULES] Fetch schedule logs error: %s", e)
    return logs


def create_schedule(job: dict[str, Any], settings: Settings | None = None) -> dict[str, Any]:
    """Create a new automation schedule."""
    settings = settings or Settings()
    init_automation_schedules(settings)
    job_id = job.get("job_id", "").strip().lower().replace(" ", "_")
    if not job_id:
        raise ValueError("job_id is required")

    job_name = job.get("job_name", job_id)
    category = job.get("category", "Custom")
    interval = int(job.get("interval_seconds", 300))
    run_after_hours = 1 if job.get("run_after_hours", True) else 0
    market_session = job.get("market_session", "all" if run_after_hours else "market_hours_only")
    params_json = job.get("params_json")
    if isinstance(params_json, (dict, list)):
        import json
        params_json = json.dumps(params_json)

    is_enabled = 1 if job.get("is_enabled", True) else 0
    now_dt = datetime.now(timezone.utc)
    now_iso = now_dt.isoformat()
    next_iso = (now_dt + timedelta(seconds=interval)).isoformat()
    status = "active" if is_enabled else "paused"

    conn = get_db_connection(settings)
    conn.execute(
        """
        INSERT OR REPLACE INTO automation_schedules (
            job_id, job_name, category, interval_seconds,
            last_run_at, next_run_at, status, last_duration_s,
            total_runs, last_summary, error_message, updated_at,
            is_enabled, params_json, run_after_hours, market_session
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            job_id,
            job_name,
            category,
            interval,
            None,
            next_iso,
            status,
            0.0,
            0,
            f"Created schedule ({interval}s interval).",
            None,
            now_iso,
            is_enabled,
            params_json,
            run_after_hours,
            market_session,
        ),
    )
    if hasattr(conn, "commit"):
        conn.commit()

    return get_schedule(job_id, settings) or {}


def update_schedule(job_id: str, updates: dict[str, Any], settings: Settings | None = None) -> dict[str, Any]:
    """Update fields of an existing automation schedule."""
    settings = settings or Settings()
    conn = get_db_connection(settings)
    now_dt = datetime.now(timezone.utc)
    now_iso = now_dt.isoformat()

    existing = get_schedule(job_id, settings)
    if not existing:
        raise ValueError(f"Schedule '{job_id}' not found")

    job_name = updates.get("job_name", existing["job_name"])
    category = updates.get("category", existing["category"])
    interval = int(updates.get("interval_seconds", existing["interval_seconds"]))
    params_json = updates.get("params_json", existing.get("params_json"))
    if isinstance(params_json, (dict, list)):
        import json
        params_json = json.dumps(params_json)

    is_enabled = existing.get("is_enabled", 1)
    if "is_enabled" in updates:
        is_enabled = 1 if updates["is_enabled"] else 0

    run_after_hours = existing.get("run_after_hours", 1)
    if "run_after_hours" in updates:
        run_after_hours = 1 if updates["run_after_hours"] else 0

    market_session = updates.get("market_session", existing.get("market_session", "all" if run_after_hours else "market_hours_only"))
    # If market_session explicitly changed, sync run_after_hours
    if market_session == "market_hours_only":
        run_after_hours = 0
    elif "run_after_hours" not in updates:
        run_after_hours = 1

    status = existing.get("status", "active")
    if "status" in updates:
        status = updates["status"]
    elif not is_enabled:
        status = "paused"
    elif status == "paused":
        status = "active"

    # If interval changed, recalculate next_run_at
    next_iso = existing.get("next_run_at")
    if interval != existing["interval_seconds"] or not next_iso:
        next_iso = (now_dt + timedelta(seconds=interval)).isoformat()

    conn.execute(
        """
        UPDATE automation_schedules
        SET job_name = ?,
            category = ?,
            interval_seconds = ?,
            next_run_at = ?,
            status = ?,
            is_enabled = ?,
            params_json = ?,
            run_after_hours = ?,
            market_session = ?,
            updated_at = ?
        WHERE job_id = ?
        """,
        (
            job_name,
            category,
            interval,
            next_iso,
            status,
            is_enabled,
            params_json,
            run_after_hours,
            market_session,
            now_iso,
            job_id,
        ),
    )
    if hasattr(conn, "commit"):
        conn.commit()

    return get_schedule(job_id, settings) or {}


def delete_schedule(job_id: str, settings: Settings | None = None) -> bool:
    """Delete an automation schedule from SQLite."""
    settings = settings or Settings()
    try:
        conn = get_db_connection(settings)
        conn.execute("DELETE FROM automation_schedules WHERE job_id = ?", (job_id,))
        if hasattr(conn, "commit"):
            conn.commit()
        return True
    except Exception as e:
        logger.error("[SCHEDULES] Error deleting schedule %s: %s", job_id, e)
        return False


def set_schedule_status(job_id: str, status: str, settings: Settings | None = None) -> dict[str, Any]:
    """Pause or resume a schedule."""
    is_enabled = 1 if status == "active" else 0
    return update_schedule(job_id, {"status": status, "is_enabled": is_enabled}, settings)


def get_all_schedules(settings: Settings | None = None) -> list[dict[str, Any]]:
    """Retrieve all automation schedule states with dynamic countdown seconds."""
    settings = settings or Settings()
    init_automation_schedules(settings)
    schedules: list[dict[str, Any]] = []

    try:
        conn = get_db_connection(settings)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM automation_schedules ORDER BY category, job_name")
        col_names = [col[0] for col in cursor.description] if cursor.description else []
        rows = cursor.fetchall()
        now_dt = datetime.now(timezone.utc)

        for r in rows:
            if hasattr(r, "keys"):
                d = dict(r)
            elif col_names:
                d = dict(zip(col_names, r))
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
            is_active = d.get("status") in ("active", "running")
            if d.get("next_run_at") and is_active:
                try:
                    next_dt = datetime.fromisoformat(d["next_run_at"].replace("Z", "+00:00"))
                    secs_until = max(0, int((next_dt - now_dt).total_seconds()))
                except Exception:
                    secs_until = d.get("interval_seconds", 60)
            else:
                secs_until = d.get("interval_seconds", 60)

            d["seconds_until_next"] = secs_until
            d["is_enabled"] = bool(d.get("is_enabled", 1))
            raw_run_after = d.get("run_after_hours")
            d["run_after_hours"] = bool(raw_run_after if raw_run_after is not None else 1)
            d["market_session"] = d.get("market_session") or ("all" if d["run_after_hours"] else "market_hours_only")
            d["interval_formatted"] = _format_interval(d.get("interval_seconds", 60))
            d["last_run_formatted"] = _format_time_ago(d.get("last_run_at"))
            d["next_run_formatted"] = _format_time_in(secs_until) if is_active else "Paused"
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
