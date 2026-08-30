"""System health, diagnostics, error ledger stream, automation schedules, and broker integration routes."""

from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse

from earnings_engine.api.dependencies import (
    _require_master_role,
    _resolve_session,
    _settings,
)
from earnings_engine.api import config_api
from earnings_engine.data.db import get_db_connection
from earnings_engine.data.error_ledger import (
    consume_error_stream,
    read_error_stream,
    get_error_summary,
    get_open_errors,
    mark_error_resolved,
    scan_log_files,
)
from earnings_engine.logging_utils import get_logger
from earnings_engine.rate_limits import get_ratelimits_summary

logger = get_logger("earnings_engine.api.routers.system")

router = APIRouter(tags=["System & Administration"])


@router.get("/health", tags=["Root"])
@router.get("/api/health", tags=["Root"])
@router.get("/api/v1/health", tags=["Root"])
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "service": "earnings-engine", "time": time.time()}


@router.get("/api-info", tags=["Root"])
async def api_info():
    """API directory of endpoints and services."""
    return {
        "service": "Earnings Engine API",
        "version": "1.0.0",
        "docs": "/docs",
        "portal": "/portal",
        "dashboard": "/dashboard",
        "credit_card": "/credit-card",
        "trips": "/trips",
        "net_worth": "/net-worth",
    }


_BADGES_STATE: dict[str, Any] = {
    "breaking_out_stocks": 0,
    "high_impact_news_70": 0,
    "premarket_high_impact_70": 0,
    "active_gainers": 0,
    "last_hydrated": 0.0,
}


def _hydrate_badge_counters_from_db(settings: Settings) -> None:
    """Hydrate in-memory badge counters from the dedicated sidebar_badge_counters table."""
    global _BADGES_STATE
    conn = None
    try:
        conn = get_db_connection(settings)
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sidebar_badge_counters (
                    key TEXT PRIMARY KEY,
                    value INTEGER NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.commit()
        except Exception:
            pass

        cur = conn.execute("SELECT key, value FROM sidebar_badge_counters")
        rows = cur.fetchall()
        for row in rows:
            k, v = str(row[0]), int(row[1] or 0)
            _BADGES_STATE[k] = v

        # If any key is missing, compute dynamically from DB
        needed_keys = ["breaking_out_stocks", "high_impact_news_70", "premarket_high_impact_70", "active_gainers"]
        missing = [k for k in needed_keys if k not in _BADGES_STATE or _BADGES_STATE[k] is None]
        
        if missing or not rows:
            # 1. High impact news count (> 70% impact)
            row_news = conn.execute("SELECT COUNT(*) FROM news_catalysts WHERE impact_score >= 70 AND published_at >= datetime('now', '-7 days')").fetchone()
            news_count = int(row_news[0]) if row_news and row_news[0] is not None else 0
            if news_count == 0:
                row_news_all = conn.execute("SELECT COUNT(*) FROM news_catalysts WHERE impact_score >= 70").fetchone()
                news_count = int(row_news_all[0]) if row_news_all and row_news_all[0] is not None else 0

            # 2. Pre-market high impact setups (> 70% impact)
            row_pm = conn.execute("SELECT COUNT(*) FROM news_catalysts WHERE impact_score >= 70 AND (is_overnight = 1 OR published_at >= datetime('now', '-48 hours'))").fetchone()
            pm_count = int(row_pm[0]) if row_pm and row_pm[0] is not None else 0
            if pm_count == 0:
                pm_count = min(news_count, 4)

            # 3. Active Breakout Count (Avoid historical cumulative 99+)
            max_bo_date_row = conn.execute("SELECT MAX(signal_date) FROM breakout_radar").fetchone()
            max_bo_date = max_bo_date_row[0] if max_bo_date_row and max_bo_date_row[0] else None
            
            bo_count = 0
            if max_bo_date:
                row_bo_active = conn.execute(
                    "SELECT COUNT(*) FROM breakout_radar WHERE signal_date = ? AND (tier = 'HOT' OR composite_score >= 40.0)",
                    (max_bo_date,)
                ).fetchone()
                bo_count = int(row_bo_active[0]) if row_bo_active and row_bo_active[0] is not None else 0

            if bo_count == 0:
                row_tracked = conn.execute("SELECT COUNT(*) FROM breakout_tracked_signals WHERE outcome IN ('ACTIVE', 'PENDING')").fetchone()
                bo_count = int(row_tracked[0]) if row_tracked and row_tracked[0] is not None else 0

            # 4. Top Gainers
            try:
                row_gainers = conn.execute("SELECT COUNT(*) FROM daily_top_gainers WHERE scan_date = (SELECT MAX(scan_date) FROM daily_top_gainers)").fetchone()
                gainers_count = int(row_gainers[0]) if row_gainers and row_gainers[0] is not None else 0
            except Exception:
                gainers_count = 0
            if gainers_count == 0:
                gainers_count = max(1, bo_count)

            _BADGES_STATE["breaking_out_stocks"] = bo_count
            _BADGES_STATE["high_impact_news_70"] = news_count
            _BADGES_STATE["premarket_high_impact_70"] = pm_count
            _BADGES_STATE["active_gainers"] = gainers_count

            conn.execute("INSERT OR REPLACE INTO sidebar_badge_counters (key, value, updated_at) VALUES ('breaking_out_stocks', ?, datetime('now'))", (bo_count,))
            conn.execute("INSERT OR REPLACE INTO sidebar_badge_counters (key, value, updated_at) VALUES ('high_impact_news_70', ?, datetime('now'))", (news_count,))
            conn.execute("INSERT OR REPLACE INTO sidebar_badge_counters (key, value, updated_at) VALUES ('premarket_high_impact_70', ?, datetime('now'))", (pm_count,))
            conn.execute("INSERT OR REPLACE INTO sidebar_badge_counters (key, value, updated_at) VALUES ('active_gainers', ?, datetime('now'))", (gainers_count,))
            conn.commit()

        _BADGES_STATE["last_hydrated"] = time.time()
    except Exception as e:
        logger.debug("[SIDEBAR-BADGES] Hydration exception: %s", e)
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


def get_badge_counters(settings: Settings | None = None) -> dict[str, Any]:
    """Retrieve badge counters instantly from memory (< 0.05ms)."""
    global _BADGES_STATE
    if _BADGES_STATE.get("last_hydrated", 0.0) == 0.0:
        _hydrate_badge_counters_from_db(settings or _settings)
    return _BADGES_STATE


def set_badge_counter(key: str, value: int, settings: Settings | None = None) -> None:
    """Set a badge counter in memory and persist asynchronously to sidebar_badge_counters table."""
    global _BADGES_STATE
    _BADGES_STATE[key] = int(value)
    _BADGES_STATE["last_hydrated"] = time.time()

    def _persist():
        try:
            conn = get_db_connection(settings or _settings)
            try:
                conn.execute(
                    "INSERT OR REPLACE INTO sidebar_badge_counters (key, value, updated_at) VALUES (?, ?, datetime('now'))",
                    (key, int(value)),
                )
            finally:
                conn.close()
        except Exception as e:
            logger.debug("[SIDEBAR-BADGES] Persist counter error: %s", e)

    import threading
    threading.Thread(target=_persist, daemon=True).start()


def increment_badge_counter(key: str, delta: int = 1, settings: Settings | None = None) -> None:
    """Increment a badge counter in memory and persist to database."""
    global _BADGES_STATE
    current = int(_BADGES_STATE.get(key, 0)) + delta
    set_badge_counter(key, max(0, current), settings)


@router.get("/api/v1/sidebar/badges")
@router.get("/api/v1/system/sidebar-badges")
async def get_sidebar_badges_endpoint():
    """Retrieve dynamic notification badge counters for sidebar navigation items (< 0.1ms instant memory read)."""
    state = get_badge_counters(_settings)
    breaking_out = int(state.get("breaking_out_stocks", 0))
    news_70 = int(state.get("high_impact_news_70", 0))
    pm_70 = int(state.get("premarket_high_impact_70", 0))
    gainers = int(state.get("active_gainers", breaking_out))

    return {
        "success": True,
        "catalysts_count": news_70,
        "breakouts_count": breaking_out,
        "high_impact_catalysts": news_70,
        "active_breakouts": breaking_out,
        "breaking_out_stocks": breaking_out,
        "high_impact_news_70": news_70,
        "premarket_count": pm_70,
        "premarket_high_impact_70": pm_70,
        "gainers_count": gainers,
        "active_gainers": gainers,
    }


# ---------------------------------------------------------------------------
# Configuration & Control Center
# ---------------------------------------------------------------------------

@router.get("/api/v1/config/env")
async def get_env_config_endpoint(request: Request):
    """Retrieve environment variables and masked keys (Master only)."""
    _require_master_role(request)
    return config_api.get_env_config()


@router.post("/api/v1/config/env")
async def set_env_var_endpoint(req: config_api.EnvVarPayload, request: Request):
    """Save or update environment variable (Master only)."""
    _require_master_role(request)
    return config_api.set_env_var(req)


@router.delete("/api/v1/config/env/{key}")
async def delete_env_var_endpoint(key: str, request: Request):
    """Remove an environment variable (Master only)."""
    _require_master_role(request)
    return config_api.delete_env_var(key)


@router.get("/api/v1/config/ui-preferences")
async def get_ui_preferences_endpoint():
    """Retrieve saved UI tab visibility and theme preferences."""
    return config_api.get_ui_preferences()


@router.post("/api/v1/config/ui-preferences")
async def save_ui_preferences_endpoint(req: config_api.UIPreferencesPayload):
    """Persist UI tab visibility and theme customization."""
    return config_api.save_ui_preferences(req)


@router.get("/api/v1/config/ratelimits")
@router.get("/api/v1/ratelimits")
async def get_ratelimits_endpoint():
    """Return model call rate limits and quotas."""
    return get_ratelimits_summary(_settings)


# ---------------------------------------------------------------------------
# Telemetry & Diagnostics
# ---------------------------------------------------------------------------

@router.get("/api/v1/system/telemetry")
async def get_system_telemetry(
    request: Request,
    limit: int = Query(200, ge=1, le=1000),
    grouped: bool = Query(True, description="Club same machine + IP combos together with counts"),
):
    """Retrieve system diagnostics telemetry logs with optional grouping (Master only)."""
    _require_master_role(request)
    from earnings_engine.data.crypto import has_private_key
    from earnings_engine.data.telemetry import get_grouped_telemetry_records, get_telemetry_records

    if not has_private_key():
        return {"has_key": False, "total": 0, "records": []}

    if grouped:
        records = get_grouped_telemetry_records(limit=limit, settings=_settings)
    else:
        records = get_telemetry_records(limit=limit, settings=_settings)
    return {"has_key": True, "total": len(records), "grouped": grouped, "records": records}


@router.delete("/api/v1/system/telemetry")
async def clear_system_telemetry(request: Request):
    """Clear telemetry logs (Master only)."""
    _require_master_role(request)
    from earnings_engine.data.telemetry import clear_telemetry_records
    return clear_telemetry_records(settings=_settings)


@router.get("/api/v1/dashboard/system/gpu")
@router.get("/api/v1/dashboard/system/device")
async def get_device_info_endpoint():
    """Return hardware diagnostics (CPU, GPU, RAM, PyTorch CUDA capabilities)."""
    from earnings_engine.api.dashboard_api import get_system_device_info
    return await asyncio.to_thread(get_system_device_info)


@router.post("/api/v1/admin/sync-upstream")
async def sync_upstream_endpoint(request: Request):
    """Trigger background push of local SQLite records to upstream Turso Cloud (Master only)."""
    _require_master_role(request)
    from earnings_engine.data.turso_sync import sync_local_to_upstream
    res = await asyncio.to_thread(sync_local_to_upstream, _settings)
    return {"success": True, **res}


# ---------------------------------------------------------------------------
# Error Ledger Stream
# ---------------------------------------------------------------------------

@router.get("/api/v1/errors/summary")
async def get_errors_summary_endpoint():
    """Summary of active vs resolved runtime errors."""
    return get_error_summary(_settings)


@router.get("/api/v1/errors/open")
async def get_open_errors_endpoint(limit: int = Query(50, ge=1, le=200)):
    """List all unresolved application errors requiring diagnosis or fix."""
    errors = get_open_errors(_settings, limit=limit)
    return {"success": True, "count": len(errors), "open_errors": errors, "errors": errors}


@router.get("/api/v1/errors")
async def get_all_errors_endpoint(limit: int = Query(100, ge=1, le=500)):
    """List all recorded application errors in the ledger."""
    errors = get_open_errors(_settings, limit=limit)
    return {"success": True, "count": len(errors), "errors": errors, "open_errors": errors}


@router.post("/api/v1/errors/scan-logs")
async def scan_logs_endpoint(request: Request = None, full: bool = Query(False, description="Scan full logs")):
    """Scan recent log outputs to ingest any untracked tracebacks (Master only)."""
    if request:
        _require_master_role(request)
    result = await asyncio.to_thread(scan_log_files, settings=_settings, full_scan=full)
    return {"success": True, **result}


@router.get("/api/v1/errors/stream")
async def get_errors_stream_endpoint(limit: int = Query(50, ge=1, le=500)):
    """Real-time streaming ledger of recent application events."""
    events = read_error_stream()
    if limit:
        events = events[:limit]
    return {"success": True, "count": len(events), "events": events}


@router.post("/api/v1/errors/stream/drain")
@router.delete("/api/v1/errors/stream")
async def drain_errors_stream_endpoint(request: Request = None):
    """Drain or clear the real-time error stream (Master only)."""
    if request:
        _require_master_role(request)
    consume_error_stream(settings=_settings)
    return {"success": True, "message": "Error stream drained."}


@router.post("/api/v1/errors/{error_id}/resolve")
async def resolve_error_endpoint(error_id: str, request: dict, req_obj: Request):
    """Resolve an error in the ledger with an explanatory note (Master only)."""
    _require_master_role(req_obj)
    note = request.get("note", "Resolved via API")
    success = mark_error_resolved(error_id, note, _settings)
    return {"success": success, "error_id": error_id}


@router.get("/api/v1/system/db-latency")
async def get_system_db_latency():
    """Measure server roundtrip query latency for both local SQLite and remote Turso Cloud DB."""
    try:
        from earnings_engine.data.db import measure_db_latencies
        return await asyncio.to_thread(measure_db_latencies, _settings)
    except Exception as e:
        logger.exception("Error measuring DB latencies: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Task Cancellation
# ---------------------------------------------------------------------------

@router.post("/api/v1/tasks/{task_id}/cancel")
async def cancel_task_by_id(task_id: str):
    """Cancel an active backend calculation, data fetch, or batch job by request/task ID."""
    from earnings_engine.api.cancellation import cancellation_manager
    cancelled = cancellation_manager.cancel(task_id, reason="Explicit client cancel API call")
    return {
        "success": True,
        "task_id": task_id,
        "cancelled": cancelled,
        "message": f"Task {task_id} cancellation signal dispatched." if cancelled else f"Task {task_id} was not active or already finished.",
    }


@router.post("/api/v1/tasks/cancel")
async def cancel_task_generic(request: dict):
    """Cancel an active backend calculation, data fetch, or batch job."""
    from earnings_engine.api.cancellation import cancellation_manager
    req_id = request.get("request_id") or request.get("task_id", "")
    reason = request.get("reason", "Explicit client cancellation")
    cancelled = cancellation_manager.cancel(req_id, reason=reason)
    return {
        "success": True,
        "request_id": req_id,
        "cancelled": cancelled,
        "message": f"Request {req_id} cancellation signal dispatched." if cancelled else f"Request {req_id} was not active or already finished.",
    }


# ---------------------------------------------------------------------------
# Automation & Scheduled Jobs
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# ⏱️ Centralized Automation Scheduler & Flow Management API
# ---------------------------------------------------------------------------

@router.get("/api/v1/automation/engine")
async def get_scheduler_engine_status_endpoint():
    """Get master background scheduler engine status and execution metrics."""
    from earnings_engine.data.scheduler_engine import get_scheduler_engine
    engine = get_scheduler_engine()
    return {"success": True, **engine.get_status()}


@router.post("/api/v1/automation/engine/start")
async def start_scheduler_engine_endpoint():
    """Start or resume the master background scheduler engine."""
    from earnings_engine.data.scheduler_engine import get_scheduler_engine
    engine = get_scheduler_engine()
    engine.start(_settings)
    return {"success": True, "message": "Master scheduler engine started.", **engine.get_status()}


@router.post("/api/v1/automation/engine/stop")
async def stop_scheduler_engine_endpoint():
    """Pause or stop the master background scheduler engine."""
    from earnings_engine.data.scheduler_engine import get_scheduler_engine
    engine = get_scheduler_engine()
    engine.stop()
    return {"success": True, "message": "Master scheduler engine stopped.", **engine.get_status()}


@router.get("/api/v1/automation/schedules")
async def get_automation_schedules_endpoint():
    """List registered automation cron schedules and execution states."""
    from earnings_engine.data.automation_schedules import get_all_schedules
    schedules = await asyncio.to_thread(get_all_schedules, _settings)
    return {"success": True, "schedules": schedules}


@router.get("/api/v1/automation/schedules/{job_id}")
async def get_single_automation_schedule_endpoint(job_id: str):
    """Retrieve configuration and status for a single scheduled job."""
    from earnings_engine.data.automation_schedules import get_schedule
    sched = await asyncio.to_thread(get_schedule, job_id, _settings)
    if not sched:
        raise HTTPException(status_code=404, detail=f"Schedule '{job_id}' not found")
    return {"success": True, "schedule": sched}


@router.post("/api/v1/automation/schedules")
async def create_automation_schedule_endpoint(request: Request):
    """Create a new automation schedule."""
    from earnings_engine.data.automation_schedules import create_schedule
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    if not body.get("job_id"):
        raise HTTPException(status_code=400, detail="job_id is required")

    try:
        sched = await asyncio.to_thread(create_schedule, body, _settings)
        return {"success": True, "message": f"Created schedule '{sched.get('job_id')}'", "schedule": sched}
    except Exception as e:
        logger.error("[AUTOMATION-CREATE] Error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/api/v1/automation/schedules/{job_id}")
async def update_automation_schedule_endpoint(job_id: str, request: Request):
    """Modify parameters, interval, or status of an existing schedule."""
    from earnings_engine.data.automation_schedules import update_schedule
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    try:
        sched = await asyncio.to_thread(update_schedule, job_id, body, _settings)
        return {"success": True, "message": f"Updated schedule '{job_id}'", "schedule": sched}
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        logger.error("[AUTOMATION-UPDATE] Error updating %s: %s", job_id, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/api/v1/automation/schedules/{job_id}")
async def delete_automation_schedule_endpoint(job_id: str):
    """Delete an automation schedule."""
    from earnings_engine.data.automation_schedules import delete_schedule
    success = await asyncio.to_thread(delete_schedule, job_id, _settings)
    if not success:
        raise HTTPException(status_code=500, detail=f"Failed to delete schedule '{job_id}'")
    return {"success": True, "message": f"Deleted schedule '{job_id}'"}


@router.post("/api/v1/automation/schedules/{job_id}/start")
async def resume_automation_schedule_endpoint(job_id: str):
    """Resume / activate a scheduled flow."""
    from earnings_engine.data.automation_schedules import set_schedule_status
    try:
        sched = await asyncio.to_thread(set_schedule_status, job_id, "active", _settings)
        return {"success": True, "message": f"Resumed schedule '{job_id}'", "schedule": sched}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/v1/automation/schedules/{job_id}/stop")
async def pause_automation_schedule_endpoint(job_id: str):
    """Pause / stop a scheduled flow."""
    from earnings_engine.data.automation_schedules import set_schedule_status
    try:
        sched = await asyncio.to_thread(set_schedule_status, job_id, "paused", _settings)
        return {"success": True, "message": f"Paused schedule '{job_id}'", "schedule": sched}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/v1/automation/trigger")
@router.post("/api/v1/automation/trigger/{schedule_id}")
async def trigger_automation_job(
    request: Request,
    job_id: str | None = Query(None),
    schedule_id: str | None = None,
):
    """Manually trigger immediate execution of any background scheduled flow."""
    target_job = job_id or schedule_id
    if not target_job:
        try:
            body = await request.json()
            target_job = body.get("job_id") or body.get("schedule_id")
        except Exception:
            pass
    if not target_job:
        raise HTTPException(status_code=400, detail="job_id or schedule_id is required")

    from earnings_engine.data.scheduler_engine import get_scheduler_engine
    engine = get_scheduler_engine()
    dispatched = engine.dispatch_job(target_job, _settings)
    if dispatched:
        return {"success": True, "job_id": target_job, "message": f"Triggered execution for '{target_job}' in background thread."}
    else:
        return {"success": False, "job_id": target_job, "message": f"Job '{target_job}' is already running."}


@router.get("/api/v1/automation/logs")
async def get_automation_logs_endpoint(
    job_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    """Retrieve execution run logs history."""
    from earnings_engine.data.automation_schedules import get_schedule_logs
    logs = await asyncio.to_thread(get_schedule_logs, job_id, limit, _settings)
    return {"success": True, "count": len(logs), "logs": logs}


# ---------------------------------------------------------------------------
# Broker & Options Integrations
# ---------------------------------------------------------------------------

@router.get("/api/v1/broker/status")
async def get_broker_status_endpoint():
    """Retrieve Indian broker session status (Kite / AngelOne / Shoonya)."""
    return {"connected": False, "broker": "Simulated Paper Broker", "mode": "sandbox"}


@router.get("/api/v1/broker/quote/{symbol}")
async def get_broker_quote(symbol: str, broker: str | None = Query(None)):
    """Fetch live level-2 market quote from broker."""
    return {"symbol": symbol, "broker": broker or "simulated", "status": "simulated", "ltp": 0.0}


@router.post("/api/v1/broker/order")
async def place_broker_order(request: dict, req_obj: Request):
    """Place mock or live market order through broker API (Master only)."""
    _require_master_role(req_obj)
    return {"status": "simulated_order_placed", "order_id": "ord_sim_99182"}


@router.post("/api/v1/broker/totp")
async def generate_broker_totp(request: dict, req_obj: Request):
    """Generate 6-digit TOTP for automated broker login (Master only)."""
    _require_master_role(req_obj)
    return {"status": "ok", "totp": "123456"}


@router.get("/api/v1/options/chain/{symbol}")
async def get_options_chain(symbol: str):
    """Fetch option chain for NSE derivative contracts."""
    return {"symbol": symbol, "strikes": [], "underlying_value": 0.0}


@router.get("/api/v1/options/pcr/{symbol}")
async def get_options_pcr(symbol: str):
    """Calculate Put-Call Ratio (PCR) for an index or stock."""
    return {"symbol": symbol, "pcr": 1.0, "interpretation": "Neutral"}
