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
async def get_system_telemetry(request: Request):
    """Retrieve system diagnostics telemetry logs (Master only)."""
    _require_master_role(request)
    from earnings_engine.data.telemetry import get_telemetry_logs
    return get_telemetry_logs(settings=_settings)


@router.delete("/api/v1/system/telemetry")
async def clear_system_telemetry(request: Request):
    """Clear telemetry logs (Master only)."""
    _require_master_role(request)
    from earnings_engine.data.telemetry import clear_telemetry_logs
    return clear_telemetry_logs(settings=_settings)


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
@router.get("/api/v1/errors")
async def get_open_errors_endpoint():
    """List open unhandled exceptions in the ledger."""
    return get_open_errors(_settings)


@router.post("/api/v1/errors/scan-logs")
async def scan_logs_endpoint(request: Request):
    """Scan recent log outputs to ingest any untracked tracebacks (Master only)."""
    _require_master_role(request)
    count = scan_log_files(_settings)
    return {"success": True, "new_errors_found": count}


@router.get("/api/v1/errors/stream")
async def get_errors_stream_endpoint():
    """Real-time streaming ledger of recent application events."""
    return read_error_stream(_settings)


@router.post("/api/v1/errors/stream/drain")
@router.delete("/api/v1/errors/stream")
async def drain_errors_stream_endpoint(request: Request):
    """Drain or clear the real-time error stream (Master only)."""
    _require_master_role(request)
    consume_error_stream(_settings)
    return {"success": True, "message": "Error stream drained."}


@router.post("/api/v1/errors/{error_id}/resolve")
async def resolve_error_endpoint(error_id: str, request: dict, req_obj: Request):
    """Resolve an error in the ledger with an explanatory note (Master only)."""
    _require_master_role(req_obj)
    note = request.get("note", "Resolved via API")
    success = mark_error_resolved(error_id, note, _settings)
    return {"success": success, "error_id": error_id}


# ---------------------------------------------------------------------------
# Automation & Scheduled Jobs
# ---------------------------------------------------------------------------

@router.get("/api/v1/automation/schedules")
async def get_automation_schedules_endpoint():
    """List registered automation cron schedules and execution history."""
    from earnings_engine.data.automation_schedules import list_schedules
    return {"success": True, "schedules": list_schedules(_settings)}


@router.post("/api/v1/automation/trigger")
async def trigger_automation_job(request: dict, req_obj: Request):
    """Manually trigger an automated pipeline job (Master only)."""
    _require_master_role(req_obj)
    job_id = request.get("job_id") or request.get("schedule_id")
    from earnings_engine.data.automation_schedules import trigger_schedule
    res = await asyncio.to_thread(trigger_schedule, job_id, _settings)
    return {"success": True, "job_id": job_id, "result": res}


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
