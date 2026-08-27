"""Quarter Repeater Seasonality Scanner and Forecast Routes."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Query

from earnings_engine.api.dependencies import _settings
from earnings_engine.data import quarter_repeaters as repeaters_mod
from earnings_engine.logging_utils import get_logger

logger = get_logger("earnings_engine.api.routers.repeaters")

router = APIRouter(tags=["Quarter Repeaters & Seasonality"])


@router.get("/api/v1/earnings-radar/repeaters")
async def get_quarter_repeaters(
    universe: str | None = Query(None, description="Universe filter (None = all)"),
    min_beat_rate: float = Query(0.0, ge=0.0, le=1.0),
    limit: int = Query(60, ge=1, le=200),
):
    """Retrieve recurring seasonal quarter repeater candidates."""
    try:
        repeaters = await asyncio.to_thread(
            repeaters_mod.scan_quarter_repeaters,
            settings=_settings,
            universe=universe,
            min_beat_pct=min_beat_rate,
            limit=limit,
        )
        return {"success": True, "count": len(repeaters), "repeaters": repeaters}
    except Exception as e:
        logger.exception("Error in get_quarter_repeaters: %s", e)
        raise HTTPException(status_code=500, detail=f"Error fetching quarter repeaters: {str(e)}")


@router.get("/api/v1/earnings-radar/repeaters/forecast/{ticker}")
@router.post("/api/v1/earnings-radar/repeaters/forecast/{ticker}")
async def get_quarter_repeater_forecast(ticker: str):
    """Retrieve seasonal cyclical trajectory and historical repeat pattern for a specific ticker."""
    try:
        forecast = await asyncio.to_thread(repeaters_mod.get_cached_repeater_prediction, ticker=ticker, settings=_settings)
        return {"success": True, "ticker": ticker, **(forecast or {"message": "No forecast cached for this ticker"})}
    except Exception as e:
        logger.exception("Error in get_quarter_repeater_forecast for %s: %s", ticker, e)
        raise HTTPException(status_code=500, detail=f"Error fetching repeater forecast: {str(e)}")


@router.post("/api/v1/earnings-radar/repeaters/scan")
async def run_quarter_repeaters_scan(request: dict | None = None):
    """Trigger background computation of quarter repeaters."""
    universe = (request or {}).get("universe") or (request or {}).get("market")
    try:
        results = await asyncio.to_thread(repeaters_mod.scan_quarter_repeaters, settings=_settings, universe=universe)
        count = len(results) if results else 0
        return {"success": True, "detected_count": count, "message": f"Quarter repeaters scan complete. Found {count} candidates."}
    except Exception as e:
        logger.exception("Error in run_quarter_repeaters_scan: %s", e)
        raise HTTPException(status_code=500, detail=f"Quarter repeaters scan failed: {str(e)}")


@router.post("/api/v1/earnings-radar/repeaters/generate/{ticker}")
async def generate_ai_repeater_forecast(ticker: str, request: dict | None = None):
    """Generate AI-powered seasonal forecast for a specific ticker."""
    try:
        forecast = await asyncio.to_thread(repeaters_mod.generate_ai_repeater_forecast, ticker=ticker, settings=_settings)
        return {"success": True, "ticker": ticker, **(forecast or {})}
    except Exception as e:
        logger.exception("Error in generate_ai_repeater_forecast for %s: %s", ticker, e)
        raise HTTPException(status_code=500, detail=f"AI repeater forecast failed: {str(e)}")
