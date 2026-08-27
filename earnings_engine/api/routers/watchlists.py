"""Watchlists, Universes, Ticker Management, and Market Status Routes."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from earnings_engine.api.dependencies import _settings
from earnings_engine.api import dashboard_api
from earnings_engine.data import watchlists as watchlists_mod
from earnings_engine.logging_utils import get_logger

logger = get_logger("earnings_engine.api.routers.watchlists")

router = APIRouter(tags=["Watchlists & Universes"])


# ---------------------------------------------------------------------------
# LITERAL ROUTES (Defined BEFORE Parameterized Routes for Strict Precedence)
# ---------------------------------------------------------------------------

@router.get("/api/v1/watchlist/all")
async def get_all_watchlists_endpoint():
    """Retrieve all custom watchlists and built-in universes with full ordered ticker lists and metadata."""
    try:
        res = await asyncio.to_thread(dashboard_api.get_all_watchlists_and_universes)
        return res
    except Exception as e:
        logger.exception("Error in get_all_watchlists: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/v1/watchlist/names")
async def get_watchlist_names_endpoint():
    """Fast summary of watchlist names and universe metadata for dropdowns (no heavy ticker arrays)."""
    try:
        res = await asyncio.to_thread(dashboard_api.get_watchlist_names_summary)
        return res
    except Exception as e:
        logger.exception("Error in get_watchlist_names: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/v1/watchlist/list")
async def get_watchlist_list_endpoint():
    """List all named watchlists in SQLite."""
    try:
        lists = await asyncio.to_thread(dashboard_api.get_universe_files)
        return {"watchlists": lists}
    except Exception as e:
        logger.exception("Error in get_watchlist_list: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/v1/watchlist/quotes")
@router.get("/api/v1/watchlist/{name}/quotes")
async def get_watchlist_quotes_endpoint(
    name: str | None = None,
    watchlist: str | None = Query(None, description="Watchlist name"),
    tickers: str | None = Query(None, description="Comma-separated ticker list (overrides watchlist name)"),
    live: bool = Query(False, description="Force live intraday / price fetching"),
):
    """Retrieve full OHLCV, pricing, market cap, and swing levels for tickers in a watchlist."""
    wl_name = watchlist or (name if name and name != "quotes" else None) or "my_watchlist"
    ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()] if tickers else None
    try:
        quotes = await asyncio.to_thread(
            dashboard_api.get_watchlist_quotes_api,
            watchlist=wl_name,
            tickers=ticker_list,
            live=live,
            settings=_settings,
        )
        return quotes
    except Exception as e:
        logger.exception("Error in get_watchlist_quotes: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/v1/watchlist/quotes")
async def post_watchlist_quotes_endpoint(request: dict):
    """Retrieve full OHLCV, pricing, market cap, and swing levels via POST body.
    Body: {"watchlist"?: str, "tickers"?: list[str], "live"?: bool}
    """
    wl_name = request.get("watchlist") or request.get("name") or "my_watchlist"
    tickers = request.get("tickers")
    live = bool(request.get("live", False))
    try:
        quotes = await asyncio.to_thread(
            dashboard_api.get_watchlist_quotes_api,
            watchlist=wl_name,
            tickers=tickers,
            live=live,
            settings=_settings,
        )
        return quotes
    except Exception as e:
        logger.exception("Error in post_watchlist_quotes: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/v1/watchlist/create")
async def create_watchlist_endpoint(request: dict):
    """Create a new watchlist. Body: {"name"?: str, "tickers"?: list[str]}"""
    name = request.get("name") or request.get("watchlist") or "my_watchlist"
    tickers = request.get("tickers") or []
    try:
        result = await asyncio.to_thread(watchlists_mod.create_watchlist, name=name, settings=_settings)
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "Failed to create watchlist"))
        for t in tickers:
            await asyncio.to_thread(watchlists_mod.add_to_watchlist, name=name, ticker=t, settings=_settings)
        saved = await asyncio.to_thread(watchlists_mod.get_watchlist, name=name, settings=_settings)
        return {"success": True, "name": name, "count": len(saved), "tickers": saved, "watchlist": saved}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error creating watchlist: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/v1/watchlist/rename")
async def rename_watchlist_endpoint(request: dict):
    """Rename a watchlist. Body: {"name": str, "new_name": str} or {"old_name": str, "new_name": str}"""
    name = request.get("name") or request.get("old_name", "")
    new_name = request.get("new_name", "")
    try:
        result = await asyncio.to_thread(dashboard_api.rename_watchlist_api, name=name, new_name=new_name)
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "Failed to rename watchlist"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error renaming watchlist: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/v1/watchlist/delete")
async def delete_watchlist_post_endpoint(request: dict):
    """Delete a watchlist. Body: {"name": str} or {"watchlist": str}"""
    name = request.get("name") or request.get("watchlist", "")
    try:
        result = await asyncio.to_thread(dashboard_api.delete_watchlist_api, name=name)
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "Failed to delete watchlist"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error deleting watchlist: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/v1/watchlist/add")
async def add_watchlist_ticker_endpoint(
    request: Request,
    ticker: str | None = Query(None, description="Ticker symbol"),
    name: str | None = Query(None, description="Watchlist name"),
):
    """Add a ticker to a named watchlist. Accepts JSON body or query params."""
    body_data = {}
    try:
        body_data = await request.json()
    except Exception:
        pass
    final_ticker = (body_data.get("ticker") if isinstance(body_data, dict) else None) or ticker or ""
    final_name = (
        (body_data.get("name") or body_data.get("watchlist") if isinstance(body_data, dict) else None)
        or name
        or "my_watchlist"
    )
    if not final_ticker:
        raise HTTPException(status_code=400, detail="Ticker is required")
    try:
        result = await asyncio.to_thread(dashboard_api.add_to_watchlist, ticker=final_ticker, name=final_name)
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "Failed to add ticker to watchlist"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error adding to watchlist: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/v1/watchlist/remove")
async def remove_watchlist_ticker_endpoint(
    request: Request,
    ticker: str | None = Query(None, description="Ticker symbol"),
    name: str | None = Query(None, description="Watchlist name"),
):
    """Remove a ticker from a named watchlist. Accepts JSON body or query params."""
    body_data = {}
    try:
        body_data = await request.json()
    except Exception:
        pass
    final_ticker = (body_data.get("ticker") if isinstance(body_data, dict) else None) or ticker or ""
    final_name = (
        (body_data.get("name") or body_data.get("watchlist") if isinstance(body_data, dict) else None)
        or name
        or "my_watchlist"
    )
    if not final_ticker:
        raise HTTPException(status_code=400, detail="Ticker is required")
    try:
        result = await asyncio.to_thread(dashboard_api.remove_from_watchlist, ticker=final_ticker, name=final_name)
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "Failed to remove ticker from watchlist"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error removing from watchlist: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/v1/watchlist")
async def get_watchlist_query_endpoint(
    name: str = Query("my_watchlist", description="Watchlist name (defaults to my_watchlist)"),
):
    """Get a named watchlist or universe from the SQLite DB / universe files."""
    from earnings_engine.data.universe import get_universe as fetch_universe_tickers
    try:
        tickers = await asyncio.to_thread(watchlists_mod.get_watchlist, name=name, settings=_settings)
        if not tickers:
            tickers = await asyncio.to_thread(fetch_universe_tickers, name, _settings)
        return {"name": name, "tickers": tickers or [], "count": len(tickers or [])}
    except Exception as e:
        logger.exception("Error in get_watchlist: %s", e)
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
    """Retrieve tickers within a specific watchlist or universe."""
    from earnings_engine.data.universe import get_universe as fetch_universe_tickers
    try:
        tickers = await asyncio.to_thread(watchlists_mod.get_watchlist, name=name, settings=_settings)
        if not tickers:
            tickers = await asyncio.to_thread(fetch_universe_tickers, name, _settings)
        return {"name": name, "count": len(tickers or []), "tickers": tickers or []}
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
