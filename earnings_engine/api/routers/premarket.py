"""Pre-Market Setups and Overnight SEBI Filings API Routes."""

from __future__ import annotations

import asyncio
from fastapi import APIRouter, HTTPException, Query

from earnings_engine.api.dependencies import _settings
from earnings_engine.data.pre_market_setups import (
    get_premarket_setups,
    scan_premarket_filings,
)
from earnings_engine.logging_utils import get_logger

logger = get_logger("earnings_engine.api.routers.premarket")

router = APIRouter(tags=["Pre-Market Setups"])


@router.get("/api/v1/premarket/setups")
async def get_premarket_setups_endpoint(
    window: str = Query("standard_6pm", description="Window mode: standard_6pm, full_post_market, early_morning, all_recent"),
    category: str = Query("ALL", description="Category filter (e.g. Order Wins, SEBI, USFDA)"),
    direction: str = Query("ALL", description="Direction filter: ALL, BULLISH, BEARISH"),
    min_impact: float = Query(0.0, ge=0.0, le=100.0, description="Minimum impact score threshold"),
    search: str = Query("", description="Keyword search query"),
    days: int = Query(7, ge=1, le=30, description="Days lookback"),
    limit: int = Query(100, ge=1, le=500, description="Max setups to return"),
    live: bool = Query(False, description="Whether to refresh live quotes"),
):
    """Retrieve scored pre-market setups from after-hours SEBI submissions and news (6:00 PM to 09:15 AM)."""
    try:
        data = await asyncio.to_thread(
            get_premarket_setups,
            window_mode=window,
            days_lookback=days,
            category_filter=category,
            direction_filter=direction,
            min_impact=min_impact,
            search_query=search,
            limit=limit,
            live_quotes=live,
            settings=_settings,
        )
        return data
    except Exception as e:
        logger.error(f"[PREMARKET] Failed fetching pre-market setups: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/v1/premarket/summary")
async def get_premarket_summary_endpoint(
    window: str = Query("standard_6pm"),
    days: int = Query(7),
):
    """Retrieve pre-market summary metrics for KPI dashboard cards."""
    try:
        data = await asyncio.to_thread(
            get_premarket_setups,
            window_mode=window,
            days_lookback=days,
            limit=10,
            settings=_settings,
        )
        return {
            "success": True,
            "summary": data.get("summary", {}),
            "as_of": data.get("as_of"),
            "window_mode": window,
        }
    except Exception as e:
        logger.error(f"[PREMARKET] Failed fetching summary: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/v1/premarket/scan")
async def post_premarket_scan_endpoint():
    """Trigger background refresh and scan of overnight SEBI filings & news."""
    try:
        res = await asyncio.to_thread(scan_premarket_filings, settings=_settings)
        return res
    except Exception as e:
        logger.error(f"[PREMARKET] Scan failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
