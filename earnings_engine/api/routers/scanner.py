"""Category Scanner, 12 Core Setups, Top 10 Gainers, and Pattern Discovery Routes."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Query

from earnings_engine.api.dependencies import _settings
from earnings_engine.data import category_scanner as scanner_mod
from earnings_engine.data import gainers_patterns as gainers_mod
from earnings_engine.logging_utils import get_logger

logger = get_logger("earnings_engine.api.routers.scanner")

router = APIRouter(tags=["Category Scanner & Top Gainers"])


@router.get("/api/v1/scanner/categories")
async def get_scanner_categories(
    universe: str = Query("NSE_TOP", description="Universe or watchlist name"),
):
    """Retrieve all 12 systematic category scan definitions and match counts."""
    try:
        cats = await asyncio.to_thread(
            scanner_mod.get_categories_overview,
            universe_or_watchlist=universe,
            settings=_settings,
        )
        return {"success": True, "count": len(cats), "categories": cats}
    except Exception as e:
        logger.exception("Error in get_scanner_categories: %s", e)
        raise HTTPException(status_code=500, detail=f"Error fetching categories: {str(e)}")


@router.get("/api/v1/scanner/category/{category_id}")
async def get_scanner_category_matches(
    category_id: str,
    universe: str = Query("NSE_TOP", description="Universe or watchlist name"),
    limit: int = Query(50, ge=1, le=200),
):
    """Retrieve tickers matching a specific category scanner rule."""
    try:
        matches = await asyncio.to_thread(
            scanner_mod.scan_category,
            category_id=category_id,
            universe_or_watchlist=universe,
            limit=limit,
            settings=_settings,
        )
        return {"success": True, "category_id": category_id, "count": len(matches), "matches": matches}
    except Exception as e:
        logger.exception("Error in get_scanner_category_matches for %s: %s", category_id, e)
        raise HTTPException(status_code=500, detail=f"Error fetching category matches: {str(e)}")


@router.post("/api/v1/scanner/scan")
async def run_full_category_scan(request: dict | None = None):
    """Execute complete multi-universe scan across all 12 categories."""
    universe = (request or {}).get("universe", "NSE_TOP")
    try:
        res = await asyncio.to_thread(scanner_mod.compute_and_save_scanner_universe, universe, _settings)
        return {"success": True, "result": res}
    except Exception as e:
        logger.exception("Error in run_full_category_scan: %s", e)
        raise HTTPException(status_code=500, detail=f"Scanner execution failed: {str(e)}")


@router.get("/api/v1/gainers/daily")
@router.get("/api/v1/gainers/top10")
async def get_top10_gainers_endpoint(
    universe: str = Query("NSE_ALL", description="Universe or watchlist name"),
    date: str | None = Query(None, description="Date (YYYY-MM-DD), defaults to latest"),
    top_n: int = Query(10, ge=1, le=50),
):
    """Retrieve verified Top 10 Gainers with volume surges, circuit bounds, and pattern tags."""
    try:
        gainers = await asyncio.to_thread(
            gainers_mod.get_daily_top_gainers,
            universe_or_watchlist=universe,
            date=date,
            top_n=top_n,
            settings=_settings,
        )
        return {"success": True, "count": len(gainers), "gainers": gainers}
    except Exception as e:
        logger.exception("Error in get_top10_gainers: %s", e)
        raise HTTPException(status_code=500, detail=f"Error fetching top gainers: {str(e)}")


@router.get("/api/v1/gainers/patterns")
async def get_pattern_discovery_endpoint():
    """Retrieve pattern discovery summary and clustering across top gainers."""
    try:
        patterns = await asyncio.to_thread(gainers_mod.get_pattern_matrix_summary)
        return {"success": True, "patterns": patterns}
    except Exception as e:
        logger.exception("Error in get_pattern_discovery: %s", e)
        raise HTTPException(status_code=500, detail=f"Error fetching pattern discovery: {str(e)}")


@router.get("/api/v1/gainers/upcoming-setups")
async def get_upcoming_breakout_setups_endpoint(
    universe: str = Query("NSE_TOP", description="Universe or watchlist name"),
):
    """Retrieve upcoming breakout setup candidates."""
    try:
        setups = await asyncio.to_thread(
            gainers_mod.scan_upcoming_breakout_setups,
            universe_or_watchlist=universe,
            settings=_settings,
        )
        return {"success": True, "count": len(setups), "setups": setups}
    except Exception as e:
        logger.exception("Error in get_upcoming_breakout_setups: %s", e)
        raise HTTPException(status_code=500, detail=f"Error fetching upcoming setups: {str(e)}")


@router.post("/api/v1/gainers/evaluate")
async def evaluate_gainers_patterns_endpoint(request: dict | None = None):
    """Trigger background computation of top gainers and chart pattern recognition."""
    universe = (request or {}).get("universe", "NSE_ALL")
    try:
        res = await asyncio.to_thread(
            gainers_mod.compute_stock_daily_telemetry,
            universe_or_watchlist=universe,
            settings=_settings,
        )
        return {"success": True, "result": res}
    except Exception as e:
        logger.exception("Error in evaluate_gainers_patterns: %s", e)
        raise HTTPException(status_code=500, detail=f"Gainers evaluation failed: {str(e)}")
