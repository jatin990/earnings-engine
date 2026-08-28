"""Institutional Accumulation, Fund Holdings, and Distribution Tracker Routes."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Query

from earnings_engine.api.dependencies import _settings
from earnings_engine.data import institutional_accumulation as inst_mod
from earnings_engine.logging_utils import get_logger

logger = get_logger("earnings_engine.api.routers.institutional")

router = APIRouter(tags=["Institutional Accumulation & Funds"])


@router.get("/api/v1/institutional/summary")
async def get_institutional_summary():
    """Retrieve macro institutional accumulation & distribution metrics."""
    try:
        accumulated = await asyncio.to_thread(inst_mod.get_top_accumulated_stocks, limit=10, settings=_settings)
        distributed = await asyncio.to_thread(inst_mod.get_top_distributed_stocks, limit=10, settings=_settings)
        return {
            "success": True,
            "top_accumulated": accumulated[:5] if accumulated else [],
            "top_distributed": distributed[:5] if distributed else [],
            "total_accumulated": len(accumulated),
            "total_distributed": len(distributed),
        }
    except Exception as e:
        logger.exception("Error in get_institutional_summary: %s", e)
        raise HTTPException(status_code=500, detail=f"Error fetching institutional summary: {str(e)}")


@router.get("/api/v1/institutional/accumulating")
async def get_institutional_accumulating(
    universe: str | None = Query(None, description="Universe filter"),
    min_score: float = Query(60.0, ge=0.0, le=100.0),
    limit: int = Query(50, ge=1, le=200),
):
    """Retrieve top stocks being heavily accumulated by institutions."""
    try:
        stocks = await asyncio.to_thread(
            inst_mod.get_top_accumulated_stocks,
            universe=universe,
            min_score=min_score,
            limit=limit,
            settings=_settings,
        )
        return {"success": True, "count": len(stocks), "items": stocks, "stocks": stocks}
    except Exception as e:
        logger.exception("Error in get_institutional_accumulating: %s", e)
        raise HTTPException(status_code=500, detail=f"Error fetching accumulating stocks: {str(e)}")


@router.get("/api/v1/institutional/distributing")
async def get_institutional_distributing(
    limit: int = Query(50, ge=1, le=200),
):
    """Retrieve stocks experiencing institutional distribution or stakeholder exits."""
    try:
        stocks = await asyncio.to_thread(inst_mod.get_top_distributed_stocks, limit=limit, settings=_settings)
        return {"success": True, "count": len(stocks), "items": stocks, "stocks": stocks}
    except Exception as e:
        logger.exception("Error in get_institutional_distributing: %s", e)
        raise HTTPException(status_code=500, detail=f"Error fetching distributing stocks: {str(e)}")


@router.get("/api/v1/institutional/top-additions")
async def get_top_stake_additions(
    min_delta: float = Query(3.0, ge=0.5, le=50.0),
    limit: int = Query(50, ge=1, le=200),
):
    """Retrieve top stocks with >= min_delta% institutional additions (latest quarter & historical surges)."""
    try:
        data = await asyncio.to_thread(inst_mod.get_top_stake_additions, min_delta=min_delta, limit=limit, settings=_settings)
        return data
    except Exception as e:
        logger.exception("Error in get_top_stake_additions: %s", e)
        raise HTTPException(status_code=500, detail=f"Error fetching top additions: {str(e)}")


@router.get("/api/v1/institutional/funds")
async def get_top_institutional_funds(
    limit: int = Query(25, ge=1, le=100),
):
    """Retrieve top mutual funds and institutional entities with their active positions."""
    try:
        funds = await asyncio.to_thread(inst_mod.get_all_funds_activity, limit=limit, settings=_settings)
        return {"success": True, "count": len(funds), "funds": funds}
    except Exception as e:
        logger.exception("Error in get_top_institutional_funds: %s", e)
        raise HTTPException(status_code=500, detail=f"Error fetching funds: {str(e)}")


@router.get("/api/v1/institutional/fund/{fund_name:path}")
async def get_fund_portfolio(fund_name: str):
    """Reverse lookup: retrieve all equities held and recent actions for a specific mutual fund or super investor."""
    try:
        items = await asyncio.to_thread(inst_mod.get_fund_portfolio_activity, fund_name=fund_name, settings=_settings)
        return {"success": True, "fund_name": fund_name, "count": len(items), "holdings": items}
    except Exception as e:
        logger.exception("Error in get_fund_portfolio for %s: %s", fund_name, e)
        raise HTTPException(status_code=500, detail=f"Error fetching fund portfolio: {str(e)}")


@router.get("/api/v1/institutional/stock/{ticker}")
async def get_stock_institutional_details(ticker: str):
    """Retrieve detailed institutional shareholding breakdown for a specific stock."""
    try:
        details = await asyncio.to_thread(inst_mod.get_stock_institutional_activity, ticker=ticker, settings=_settings)
        return {"success": True, "ticker": ticker, **(details or {})}
    except Exception as e:
        logger.exception("Error in get_stock_institutional_details for %s: %s", ticker, e)
        raise HTTPException(status_code=500, detail=f"Error fetching stock institutional data: {str(e)}")


@router.post("/api/v1/institutional/scan")
async def run_institutional_scan(request: dict | None = None):
    """Trigger background computation of institutional flows via live corporate ownership fetch."""
    ticker = (request or {}).get("ticker")
    try:
        if ticker:
            res = await asyncio.to_thread(inst_mod.fetch_live_corporate_ownership, ticker=ticker, settings=_settings)
        else:
            res = {"message": "Provide a ticker for targeted institutional ownership fetch"}
        return {"success": True, "result": res}
    except Exception as e:
        logger.exception("Error in run_institutional_scan: %s", e)
        raise HTTPException(status_code=500, detail=f"Institutional scan failed: {str(e)}")
