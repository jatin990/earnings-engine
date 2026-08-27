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
    universe: str | None = Query(None, description="Universe or watchlist to screen (e.g. nifty_50, nse_top, nse_large_cap, us_top, all)"),
    min_beat_pct: float = Query(0.0, description="Minimum prior EPS surprise percentage"),
    min_week_high_pct: float = Query(2.5, description="Minimum post-earnings week peak high percentage"),
    limit: int = Query(50, ge=1, le=150, description="Max candidates to return"),
    verdict: str | None = Query(None, description="Filter by AI repeat verdict (e.g. STRONG_REPEAT_BEAT, MODERATE_BEAT)"),
):
    """Screen for companies that had stellar past earnings beats & week highs, with AI continuity forecasts."""
    try:
        candidates = await asyncio.to_thread(
            repeaters_mod.scan_quarter_repeaters,
            settings=_settings,
            universe=universe,
            min_beat_pct=min_beat_pct,
            min_week_high_pct=min_week_high_pct,
            limit=limit,
        )
        if verdict:
            candidates = [c for c in candidates if c.get("ai_verdict") == verdict]

        total_screened = len(candidates)
        avg_beat = round(sum(c.get("prior_surprise_pct", 0) for c in candidates) / total_screened, 1) if total_screened else 0.0
        top_conviction = max(candidates, key=lambda x: x.get("conviction_score", 0)) if candidates else None

        # Determine dominant industry buzz
        buzz_counts: dict[str, int] = {}
        for c in candidates:
            b = c.get("industry_buzz", "Neutral")
            buzz_counts[b] = buzz_counts.get(b, 0) + 1
        dominant_buzz = max(buzz_counts.items(), key=lambda x: x[1])[0] if buzz_counts else "Stable"

        return {
            "success": True,
            "count": total_screened,
            "universe": universe or "ALL",
            "summary": {
                "total_screened": total_screened,
                "avg_prior_beat_pct": avg_beat,
                "top_pick_ticker": top_conviction.get("ticker") if top_conviction else "—",
                "top_pick_score": top_conviction.get("conviction_score") if top_conviction else 0,
                "dominant_industry_buzz": dominant_buzz,
            },
            "candidates": candidates,
            "repeaters": candidates,
        }
    except Exception as e:
        logger.exception("Error in get_quarter_repeaters: %s", e)
        raise HTTPException(status_code=500, detail=f"Error fetching quarter repeaters: {str(e)}")


@router.get("/api/v1/earnings-radar/repeaters/forecast/{ticker}")
@router.post("/api/v1/earnings-radar/repeaters/forecast/{ticker}")
async def get_quarter_repeater_forecast(
    ticker: str,
    model_name: str | None = Query(None, description="Specific local Ollama or OpenRouter model"),
    provider: str = Query("auto", description="Inference provider: 'auto', 'ollama', or 'openrouter'"),
):
    """Run on-demand AI Forward reasoning for upcoming quarter earnings continuity for a single ticker."""
    sym = ticker.strip().upper()
    try:
        forecast = await asyncio.to_thread(
            repeaters_mod.generate_ai_repeater_forecast,
            sym,
            settings=_settings,
            model_name=model_name,
            provider=provider,
        )
        return {
            "success": True,
            "ticker": sym,
            "forecast": forecast,
            **(forecast or {}),
        }
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
