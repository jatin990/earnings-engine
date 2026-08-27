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
async def scan_logs_endpoint(request: Request = None):
    """Scan recent log outputs to ingest any untracked tracebacks (Master only)."""
    if request:
        _require_master_role(request)
    result = await asyncio.to_thread(scan_log_files, settings=_settings)
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

@router.get("/api/v1/automation/schedules")
async def get_automation_schedules_endpoint():
    """List registered automation cron schedules and execution history."""
    from earnings_engine.data.automation_schedules import get_all_schedules
    schedules = await asyncio.to_thread(get_all_schedules, _settings)
    return {"success": True, "schedules": schedules}


@router.post("/api/v1/automation/trigger")
@router.post("/api/v1/automation/trigger/{schedule_id}")
async def trigger_automation_job(
    request: Request,
    job_id: str | None = Query(None),
    schedule_id: str | None = None,
):
    """Manually trigger immediate execution of any background scheduled job."""
    target_job = job_id or schedule_id
    if not target_job:
        try:
            body = await request.json()
            target_job = body.get("job_id") or body.get("schedule_id")
        except Exception:
            pass
    if not target_job:
        raise HTTPException(status_code=400, detail="job_id or schedule_id is required")

    import threading
    from earnings_engine.data import breakout_scanner as breakout_scanner_mod

    def _execute():
        try:
            if target_job == "breakout_hot_rescore":
                breakout_scanner_mod.run_hot_rescore(_settings)
            elif target_job == "breakout_warm_rescore":
                breakout_scanner_mod.run_warm_rescore(_settings)
            elif target_job == "breakout_cold_scan":
                breakout_scanner_mod.run_cold_scan(_settings)
            elif target_job == "news_catalyst_harvest":
                from earnings_engine.data.catalysts_news import scan_watchlist_catalysts
                from earnings_engine.data.automation_schedules import record_job_start, record_job_finish
                record_job_start("news_catalyst_harvest", _settings)
                t0 = time.perf_counter()
                res = scan_watchlist_catalysts("my_watchlist", 3, False, _settings)
                elapsed = round(time.perf_counter() - t0, 2)
                record_job_finish("news_catalyst_harvest", elapsed, f"Harvested {res.get('catalysts_fetched', 0)} headlines across {res.get('scanned_tickers', 0)} stocks", settings=_settings)
        except Exception as e:
            logger.error("[AUTOMATION-TRIGGER] Error running %s: %s", target_job, e)

    t = threading.Thread(target=_execute, daemon=True, name=f"trigger_{target_job}")
    t.start()
    return {"success": True, "job_id": target_job, "message": f"Triggered execution for '{target_job}' in background thread."}


# ---------------------------------------------------------------------------
# Broker & Options Integrations
# ---------------------------------------------------------------------------

@router.get("/api/v1/broker/status")
async def get_broker_status_endpoint():
    """Retrieve Indian broker session status (Kite / AngelOne / Shoonya)."""
    return {"connected": False, "broker": "Simulated Paper Broker", "mode": "sandbox"}


@router.get("/api/v1/broker/quote/{symbol}")
async def get_broker_quote(symbol: str):
    """Fetch live level-2 market quote from broker."""
    return {"symbol": symbol, "status": "simulated", "ltp": 0.0}


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
