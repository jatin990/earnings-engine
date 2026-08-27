"""Watchlists, Universes, Ticker Management, and Market Status Routes."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from earnings_engine.api.dependencies import _settings
from earnings_engine.api import dashboard_api
from earnings_engine.data import watchlists as watchlists_mod
from earnings_engine.logging_utils import get_logger

logger = get_logger("earnings_engine.api.routers.watchlists")

router = APIRouter(tags=["Watchlists & Universes"])


# ---------------------------------------------------------------------------
# LITERAL ROUTES (Defined BEFORE Parameterized Routes for Strict Precedence)
# ---------------------------------------------------------------------------

@router.get("/api/v1/watchlist/quotes")
async def get_watchlist_quotes_endpoint(
    name: str = Query("my_watchlist", description="Watchlist name"),
    watchlist: str | None = Query(None, description="Alias for name"),
):
    """Retrieve live OHLCV price quotes, volume, and percentage returns for tickers in a watchlist."""
    wl_name = watchlist or name
    try:
        quotes = await asyncio.to_thread(dashboard_api.get_watchlist_quotes_api, watchlist=wl_name, settings=_settings)
        return quotes
    except Exception as e:
        logger.exception("Error in get_watchlist_quotes: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/v1/watchlist/all")
async def get_all_watchlists_endpoint():
    """Retrieve all watchlists and their assigned tickers."""
    try:
        all_wl = await asyncio.to_thread(watchlists_mod.all_watchlists, settings=_settings)
        return {"watchlists": all_wl}
    except Exception as e:
        logger.exception("Error in get_all_watchlists: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/v1/watchlist/names")
async def get_watchlist_names_endpoint():
    """Retrieve list of distinct watchlist names."""
    try:
        rows = await asyncio.to_thread(watchlists_mod.list_watchlists, settings=_settings)
        names = [r["name"] if isinstance(r, dict) else r for r in rows]
        return {"names": names}
    except Exception as e:
        logger.exception("Error in get_watchlist_names: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/v1/universe/names")
async def get_universe_names_endpoint():
    """Retrieve available universe options."""
    try:
        from earnings_engine.data.universe import get_available_universes
        univs = await asyncio.to_thread(get_available_universes, settings=_settings)
        return {"universes": univs}
    except Exception as e:
        logger.exception("Error in get_universe_names: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/v1/market/recent-additions")
async def get_recent_market_additions_endpoint(
    days: int = Query(180, ge=1, le=365, description="Look-back window in days"),
    limit: int = Query(100, ge=1, le=500),
):
    """Retrieve recently listed or re-listed equities added to market."""
    try:
        from earnings_engine.api import stock_api as _stock_api
        return await asyncio.to_thread(_stock_api.get_recent_market_additions, days=days, limit=limit, settings=_settings)
    except Exception as e:
        logger.exception("Error in get_recent_market_additions: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/v1/market/status")
async def get_market_status_endpoint():
    """Return live NSE market status (Open / Closed / Holiday / Session)."""
    try:
        status = await asyncio.to_thread(dashboard_api.get_market_live_status)
        return status
    except Exception as e:
        logger.exception("Error in get_market_status: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# PARAMETERIZED ROUTES
# ---------------------------------------------------------------------------

@router.get("/api/v1/watchlist/{name}")
async def get_single_watchlist_endpoint(name: str):
    """Retrieve tickers within a specific watchlist."""
    try:
        tickers = await asyncio.to_thread(watchlists_mod.get_watchlist, name=name, settings=_settings)
        return {"name": name, "count": len(tickers), "tickers": tickers}
    except Exception as e:
        logger.exception("Error in get_single_watchlist for %s: %s", name, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/v1/watchlist/{name}")
async def save_watchlist_endpoint(name: str, request: dict):
    """Save or replace full ticker list for a watchlist."""
    tickers = request.get("tickers", [])
    try:
        await asyncio.to_thread(watchlists_mod.create_watchlist, name=name, settings=_settings)
        for t in tickers:
            await asyncio.to_thread(watchlists_mod.add_to_watchlist, name=name, ticker=t, settings=_settings)
        saved = await asyncio.to_thread(watchlists_mod.get_watchlist, name=name, settings=_settings)
        return {"success": True, "name": name, "count": len(saved), "tickers": saved}
    except Exception as e:
        logger.exception("Error saving watchlist %s: %s", name, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/api/v1/watchlist/{name}")
async def delete_watchlist_endpoint(name: str):
    """Delete an entire watchlist."""
    try:
        deleted = await asyncio.to_thread(watchlists_mod.delete_watchlist, name=name, settings=_settings)
        return {"success": True, "name": name, "deleted": deleted}
    except Exception as e:
        logger.exception("Error deleting watchlist %s: %s", name, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/v1/watchlist/{name}/item")
async def add_watchlist_item_endpoint(name: str, request: dict):
    """Add a single ticker to a watchlist."""
    ticker = request.get("ticker", "").upper().strip()
    if not ticker:
        raise HTTPException(status_code=400, detail="Ticker is required")
    try:
        added = await asyncio.to_thread(watchlists_mod.add_to_watchlist, name=name, ticker=ticker, settings=_settings)
        return {"success": True, "name": name, "ticker": ticker, "added": added}
    except Exception as e:
        logger.exception("Error adding ticker %s to watchlist %s: %s", ticker, name, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/api/v1/watchlist/{name}/item")
async def remove_watchlist_item_endpoint(
    name: str,
    ticker: str = Query(..., description="Ticker symbol to remove"),
):
    """Remove a single ticker from a watchlist."""
    try:
        removed = await asyncio.to_thread(watchlists_mod.remove_from_watchlist, name=name, ticker=ticker, settings=_settings)
        return {"success": True, "name": name, "ticker": ticker, "removed": removed}
    except Exception as e:
        logger.exception("Error removing ticker %s from watchlist %s: %s", ticker, name, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/v1/universe/{name}")
async def get_universe_tickers_endpoint(name: str):
    """Retrieve tickers belonging to a market universe."""
    try:
        from earnings_engine.data.universe import load_universe
        tickers = await asyncio.to_thread(load_universe, name, settings=_settings)
        return {"universe": name, "count": len(tickers), "tickers": tickers}
    except Exception as e:
        logger.exception("Error in get_universe_tickers for %s: %s", name, e)
        raise HTTPException(status_code=500, detail=str(e))
