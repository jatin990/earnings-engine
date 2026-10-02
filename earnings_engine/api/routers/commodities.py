"""FastAPI REST router for Commodities Hub & Smart Money Technical Intelligence.

Provides endpoints for:
- Supported commodity symbols (Precious metals, energy, industrial metals)
- Real-time / intraday candlestick data, VWAP bands, ORB-15, SMC Order Blocks, Pivots, and 3-column tactical trade HUD
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from earnings_engine.api.dependencies import _settings
from earnings_engine.data import commodities_chart_engine as cce_mod
from earnings_engine.logging_utils import get_logger

logger = get_logger("earnings_engine.api.routers.commodities")

router = APIRouter(tags=["Commodities"])


def _get_settings():
    return _settings() if callable(_settings) else _settings


@router.get("/api/v1/commodities/symbols")
async def get_commodity_symbols(
    query: str | None = Query(None, description="Optional filter for commodity symbol or name"),
) -> dict[str, Any]:
    """Return catalog of supported commodity assets with tickers and units."""
    symbols = cce_mod.get_supported_commodity_symbols()
    if query:
        q = query.strip().upper()
        symbols = [s for s in symbols if q in s["symbol"].upper() or q in s["name"].upper() or q in s["category"].upper()]

    return {
        "success": True,
        "count": len(symbols),
        "symbols": symbols,
    }


@router.get("/api/v1/commodities/latest-tick")
async def get_commodity_latest_tick(
    symbol: str = Query("GOLD", description="Commodity symbol (GOLD, SILVER, CRUDEOIL, NATGAS, COPPER, etc.)"),
    interval: str = Query("5m", description="Candle interval (1m, 5m, 15m, 30m, 1h, 1d)"),
) -> dict[str, Any]:
    """Fetch fast real-time tick and current forming candle for incremental chart polling."""
    clean_sym = symbol.strip().upper()
    try:
        data = await asyncio.to_thread(
            cce_mod.get_commodity_latest_tick,
            symbol=clean_sym,
            interval=interval,
            settings=_get_settings(),
        )
        return data
    except Exception as e:
        logger.error("[COMMODITIES-API] Error fetching latest tick for %s: %s", clean_sym, e)
        raise HTTPException(status_code=500, detail=f"Failed to fetch tick for {clean_sym}: {str(e)}")


@router.get("/api/v1/commodities/chart-intelligence")
async def get_commodity_chart_intelligence(
    symbol: str = Query("GOLD", description="Commodity symbol (GOLD, SILVER, CRUDEOIL, NATGAS, COPPER, etc.)"),
    interval: str = Query("5m", description="Candle interval (1m, 5m, 15m, 30m, 1h, 1d)"),
    period: str = Query("5d", description="Lookback window (1d, 5d, 1mo, 3mo, 6mo, 1y)"),
    force_refresh: bool = Query(False, description="Bypass in-memory cache"),
) -> dict[str, Any]:
    """Retrieve full quantitative candlestick payload, indicators, SMC order blocks, and trade HUD."""
    clean_sym = symbol.strip().upper()
    try:
        data = await asyncio.to_thread(
            cce_mod.get_commodity_chart_intelligence,
            symbol=clean_sym,
            interval=interval,
            period=period,
            force_refresh=force_refresh,
            settings=_get_settings(),
        )
        return data
    except Exception as e:
        logger.error("[COMMODITIES-API] Error generating chart intelligence for %s: %s", clean_sym, e)
        raise HTTPException(status_code=500, detail=f"Failed to generate chart intelligence for {clean_sym}: {str(e)}")
