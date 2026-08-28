"""Playground API console, NSE official calendars, and symbol autocomplete routes."""

from __future__ import annotations

import asyncio
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from earnings_engine.api.dependencies import _settings
from earnings_engine.api.playground_api import (
    get_endpoint_catalog,
    get_nse_universe_info,
    get_ticker_history,
    get_ticker_overview,
    search_symbols,
)
from earnings_engine.data.nse_api import (
    fetch_event_calendar,
    fetch_result_calendar,
    get_financial_calendar,
)
from earnings_engine.logging_utils import get_logger

logger = get_logger("earnings_engine.api.routers.playground")

router = APIRouter(tags=["Playground & Live Exploration"])


@router.get("/api/v1/playground/endpoints")
async def playground_endpoints():
    """Get the raw API endpoint catalog for the Playground API console."""
    try:
        return get_endpoint_catalog()
    except Exception as e:
        logger.exception("Error loading endpoint catalog: %s", e)
        raise HTTPException(status_code=500, detail=f"Error loading endpoint catalog: {str(e)}")


@router.get("/api/v1/playground/search")
async def playground_search(
    q: str = Query("", description="Symbol search query"),
    limit: int = Query(20, description="Max results", ge=1, le=50),
):
    """Search ticker symbols across NSE_ALL + US universes for autocomplete."""
    try:
        return search_symbols(q, limit=limit)
    except Exception as e:
        logger.exception("Error searching symbols: %s", e)
        raise HTTPException(status_code=500, detail=f"Error searching symbols: {str(e)}")


@router.get("/api/v1/playground/ticker/{ticker}")
async def playground_ticker_overview(ticker: str):
    """Explore a single ticker: market inference, price, market cap, moves, earnings dates."""
    try:
        return get_ticker_overview(ticker)
    except Exception as e:
        logger.exception("Error exploring ticker %s: %s", ticker, e)
        raise HTTPException(status_code=500, detail=f"Error exploring ticker: {str(e)}")


@router.get("/api/v1/playground/ticker/{ticker}/history")
async def playground_ticker_history(
    ticker: str,
    period: str = Query("1mo", description="History period (1mo, 3mo, 6mo, 1y, 5y)"),
    interval: str = Query("1d", description="Bar interval (1d, 1wk, 1mo)"),
):
    """Fetch OHLCV history for a ticker (live yfinance, capped at 120 rows)."""
    try:
        return get_ticker_history(ticker, period=period, interval=interval)
    except Exception as e:
        logger.exception("Error fetching ticker history for %s: %s", ticker, e)
        raise HTTPException(status_code=500, detail=f"Error fetching ticker history: {str(e)}")


@router.get("/api/v1/playground/nse")
async def playground_nse_universe(
    force_refresh: bool = Query(False, description="Force refresh universe files"),
):
    """Get NSE universe sizes + samples (nse_all, nse_large_cap, IN, US, combined)."""
    try:
        return get_nse_universe_info(force_refresh=force_refresh)
    except Exception as e:
        logger.exception("Error loading NSE universe info: %s", e)
        raise HTTPException(status_code=500, detail=f"Error loading NSE universe info: {str(e)}")


@router.get("/api/v1/playground/nse/result-calendar")
async def playground_nse_result_calendar(
    from_date: str | None = Query(None, description="Start date (YYYY-MM-DD)"),
    to_date: str | None = Query(None, description="End date (YYYY-MM-DD)"),
):
    """Raw NSE result-calendar payload (companies + result dates) for a date range."""
    try:
        f = date.fromisoformat(from_date) if from_date else None
        t = date.fromisoformat(to_date) if to_date else None
        return fetch_result_calendar(f, t)
    except Exception as e:
        logger.exception("Error fetching NSE result calendar: %s", e)
        raise HTTPException(status_code=500, detail=f"Error fetching NSE result calendar: {str(e)}")


@router.get("/api/v1/playground/nse/event-calendar")
async def playground_nse_event_calendar(
    from_date: str | None = Query(None, description="Start date (YYYY-MM-DD)"),
    to_date: str | None = Query(None, description="End date (YYYY-MM-DD)"),
):
    """Raw NSE event-calendar payload (board meetings, results, dividends) for a date range."""
    try:
        f = date.fromisoformat(from_date) if from_date else None
        t = date.fromisoformat(to_date) if to_date else None
        return fetch_event_calendar(f, t)
    except Exception as e:
        logger.exception("Error fetching NSE event calendar: %s", e)
        raise HTTPException(status_code=500, detail=f"Error fetching NSE event calendar: {str(e)}")


@router.get("/api/v1/playground/nse/financial-calendar/{symbol}")
async def playground_nse_financial_calendar(
    symbol: str,
    from_date: str | None = Query(None, description="Start date (YYYY-MM-DD)"),
    to_date: str | None = Query(None, description="End date (YYYY-MM-DD)"),
):
    """Normalized NSE result dates for one symbol (raw payload kept separate)."""
    try:
        f = date.fromisoformat(from_date) if from_date else None
        t = date.fromisoformat(to_date) if to_date else None
        return get_financial_calendar(symbol, f, t)
    except Exception as e:
        logger.exception("Error fetching NSE financial calendar for %s: %s", symbol, e)
        raise HTTPException(status_code=500, detail=f"Error fetching NSE financial calendar: {str(e)}")


@router.get("/api/v1/playground/api-usage")
async def playground_api_usage():
    """Retrieve tracked API call counts and metrics for yfinance, nse, jugaad_data, and AI models."""
    try:
        from earnings_engine.rate_limits import get_api_usage_summary
        data = await asyncio.to_thread(get_api_usage_summary, _settings)
        return data
    except Exception as e:
        logger.exception("Error fetching playground API usage: %s", e)
        raise HTTPException(status_code=500, detail=f"Error fetching API usage metrics: {str(e)}")

