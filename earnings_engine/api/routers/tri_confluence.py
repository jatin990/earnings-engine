"""Tri-Factor Synergy & Institutional-Earnings-Returns Correlation Routes."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Query

from earnings_engine.api.dependencies import _settings
from earnings_engine.data import tri_confluence as conf_mod
from earnings_engine.logging_utils import get_logger

logger = get_logger("earnings_engine.api.routers.tri_confluence")

router = APIRouter(tags=["Tri-Factor Synergy & Cross-Correlation"])


@router.get("/api/v1/correlation/summary")
async def get_tri_confluence_summary():
    """Retrieve macro summary metrics for Tri-Factor Institutional-Earnings-Returns synergy."""
    try:
        data = await asyncio.to_thread(conf_mod.get_tri_confluence_summary, settings=_settings)
        return data
    except Exception as e:
        logger.exception("Error in get_tri_confluence_summary: %s", e)
        raise HTTPException(status_code=500, detail=f"Error fetching synergy summary: {str(e)}")


@router.get("/api/v1/correlation/tri-confluence")
async def get_tri_confluence_scanner(
    universe: str = Query("ALL", description="Universe filter (ALL, NIFTY 50, NIFTY 500, NSE_ALL, US)"),
    min_score: float = Query(0.0, ge=0.0, le=100.0, description="Minimum Synergy Score (0-100)"),
    sort_by: str = Query("score", description="Sort field: score, hit_rate, inst_corr, surp_corr, latest_delta, market_cap"),
    limit: int = Query(100, ge=1, le=300, description="Max results to return"),
):
    """Scan and rank equities exhibiting direct positive correlation across institutional flows, earnings beats, and returns."""
    try:
        items = await asyncio.to_thread(
            conf_mod.get_tri_confluence_scanner,
            universe=universe,
            min_score=min_score,
            sort_by=sort_by,
            limit=limit,
            settings=_settings,
        )
        return {
            "success": True,
            "count": len(items),
            "total": len(items),
            "universe": universe,
            "sort_by": sort_by,
            "min_score": min_score,
            "items": items,
            "stocks": items,
        }
    except Exception as e:
        logger.exception("Error in get_tri_confluence_scanner: %s", e)
        raise HTTPException(status_code=500, detail=f"Error fetching tri-factor scanner: {str(e)}")


@router.get("/api/v1/correlation/ticker/{ticker}")
async def get_ticker_tri_confluence(ticker: str):
    """Retrieve detailed multi-quarter time series, correlation coefficients, and institutional holdings for a specific ticker."""
    try:
        data = await asyncio.to_thread(conf_mod.compute_ticker_tri_confluence, ticker=ticker, settings=_settings)
        return {
            "success": True,
            "ticker": ticker,
            **data,
        }
    except Exception as e:
        logger.exception("Error in get_ticker_tri_confluence for %s: %s", ticker, e)
        raise HTTPException(status_code=500, detail=f"Error fetching ticker confluence data: {str(e)}")


@router.post("/api/v1/correlation/recalculate")
async def recalculate_tri_confluence():
    """Flush the database & in-memory cache and recompute tri-factor synergy correlations across all tickers."""
    try:
        count = await asyncio.to_thread(conf_mod.sync_tri_confluence_db, universe="ALL", settings=_settings)
        summary = await asyncio.to_thread(conf_mod.get_tri_confluence_summary, settings=_settings)
        return {
            "success": True,
            "status": "recalculated",
            "synced_count": count,
            "message": f"Tri-Factor Synergy recalculated and synced to SQLite for {count} tickers.",
            "summary": summary,
        }
    except Exception as e:
        logger.exception("Error in recalculate_tri_confluence: %s", e)
        raise HTTPException(status_code=500, detail=f"Recalculation error: {str(e)}")
