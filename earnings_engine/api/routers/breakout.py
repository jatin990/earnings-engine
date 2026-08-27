"""Breakout Radar Scanner, Setup Tracking, and AI Outcome Auditing Routes."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Query

from earnings_engine.api.dependencies import _settings
from earnings_engine.data import breakout_scanner as breakout_scanner_mod
from earnings_engine.logging_utils import get_logger

logger = get_logger("earnings_engine.api.routers.breakout")

router = APIRouter(tags=["Breakout Radar & Scanner"])


@router.get("/api/v1/breakout-radar")
async def get_breakout_radar_endpoint(
    universe: str | None = Query(None, description="Universe filter (None = all)"),
    asof_date: str | None = Query(None, description="As-of date (YYYY-MM-DD)"),
):
    """Retrieve active Breakout Radar candidates."""
    try:
        setups = await asyncio.to_thread(
            breakout_scanner_mod.get_cached_scan_results,
            universe=universe,
            settings=_settings,
            asof_date=asof_date,
        )
        return {"success": True, "count": len(setups), "setups": setups}
    except Exception as e:
        logger.exception("Error in get_breakout_radar: %s", e)
        raise HTTPException(status_code=500, detail=f"Error fetching breakout radar: {str(e)}")


@router.post("/api/v1/breakout-radar/evaluate")
async def evaluate_breakout_candidates_endpoint(request: dict | None = None):
    """Trigger background scanning sweep of high-conviction breakout setups."""
    universe = (request or {}).get("universe") or (request or {}).get("market")
    try:
        results = await asyncio.to_thread(
            breakout_scanner_mod.run_breakout_scan,
            settings=_settings,
            universe=universe,
        )
        count = len(results) if results else 0
        return {"success": True, "detected_count": count, "message": f"Breakout scan complete. Found {count} setups."}
    except Exception as e:
        logger.exception("Error in evaluate_breakout_candidates: %s", e)
        raise HTTPException(status_code=500, detail=f"Breakout evaluation failed: {str(e)}")


@router.get("/api/v1/breakout-radar/status")
async def get_breakout_scan_status(
    universe: str | None = Query(None, description="Universe filter"),
):
    """Retrieve current breakout scanner status and metadata."""
    try:
        status = await asyncio.to_thread(breakout_scanner_mod.get_scan_status, universe=universe)
        return {"success": True, **status}
    except Exception as e:
        logger.exception("Error in get_breakout_scan_status: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/v1/breakout-radar/audit-log")
async def get_breakout_audit_log_endpoint(
    ticker: str | None = Query(None, description="Filter by ticker"),
    limit: int = Query(50, ge=1, le=200),
):
    """Retrieve historical audit logs of tracked breakout signals."""
    try:
        logs = await asyncio.to_thread(
            breakout_scanner_mod.get_breakout_audit_log,
            ticker=ticker,
            limit=limit,
            settings=_settings,
        )
        return {"success": True, "count": len(logs), "logs": logs}
    except Exception as e:
        logger.exception("Error in get_breakout_audit_log: %s", e)
        raise HTTPException(status_code=500, detail=f"Error fetching breakout audit log: {str(e)}")


@router.get("/api/v1/breakout-radar/evaluate/{ticker}")
async def evaluate_single_breakout(ticker: str):
    """Evaluate breakout potential for a single ticker."""
    try:
        result = await asyncio.to_thread(
            breakout_scanner_mod.evaluate_stock_breakout,
            ticker=ticker,
            settings=_settings,
        )
        return {"success": True, "ticker": ticker, "evaluation": result}
    except Exception as e:
        logger.exception("Error evaluating breakout for %s: %s", ticker, e)
        raise HTTPException(status_code=500, detail=f"Error evaluating breakout: {str(e)}")


@router.get("/api/v1/breakout-radar/ai-reasoning/{ticker}")
async def get_breakout_ai_reasoning_endpoint(ticker: str):
    """Return structured AI reasoning breakdown for a detected breakout setup."""
    try:
        reasoning = await asyncio.to_thread(
            breakout_scanner_mod.generate_breakout_ai_reasoning,
            ticker=ticker,
            settings=_settings,
        )
        return {"success": True, "ticker": ticker, **(reasoning or {})}
    except Exception as e:
        logger.exception("Error fetching breakout AI reasoning for %s: %s", ticker, e)
        raise HTTPException(status_code=500, detail=f"Error fetching AI reasoning: {str(e)}")
