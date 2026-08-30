"""News Catalysts, Order Wins, Regulatory Filings, and Impact Scoring Routes."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Query

from earnings_engine.api.dependencies import _settings
from earnings_engine.data.catalysts_news import (
    get_catalyst_summary_stats,
    get_recent_news_activity,
    get_short_term_catalysts,
    scan_watchlist_catalysts,
)
from earnings_engine.data.news_outcomes import (
    evaluate_all_catalyst_outcomes,
    get_verified_catalyst_outcomes,
    compute_news_trade_metrics,
)
from earnings_engine.logging_utils import get_logger

logger = get_logger("earnings_engine.api.routers.news")

router = APIRouter(tags=["News Catalysts & Filings"])


@router.get("/api/v1/news/catalysts")
@router.get("/api/v1/catalysts")
async def get_news_catalysts_endpoint(
    market: str | None = Query(None),
    watchlist: str | None = Query(None),
    universe: str | None = Query(None),
    watchlist_or_universe: str | None = Query(None),
    category: str | None = Query(None),
    impact: str | None = Query(None),
    impact_level: str | None = Query(None),
    min_impact: int | None = Query(None),
    direction: str | None = Query(None),
    search: str | None = Query(None),
    days: int = Query(14, ge=0, le=365, description="Lookback window in days (1, 3, 7, 14, 30, 0 for all)"),
    limit: int = Query(100, ge=1, le=500),
):
    """Retrieve structured news catalysts (order wins, expansions, regulatory approvals)."""
    try:
        effective_market = watchlist_or_universe or universe or watchlist or market or "ALL"
        effective_impact = impact_level or impact
        if not effective_impact and min_impact is not None:
            if min_impact >= 75:
                effective_impact = "HIGH"
            elif min_impact >= 50:
                effective_impact = "MEDIUM+"

        items = await asyncio.to_thread(
            get_short_term_catalysts,
            watchlist_or_universe=effective_market,
            impact_filter=effective_impact,
            category_filter=category,
            direction_filter=direction,
            search_query=search,
            days=days,
            limit=limit,
            settings=_settings,
        )
        return {"success": True, "count": len(items), "catalysts": items}
    except Exception as e:
        logger.exception("Error in get_news_catalysts: %s", e)
        raise HTTPException(status_code=500, detail=f"Error fetching catalysts: {str(e)}")


@router.get("/api/v1/news/catalyst/{catalyst_id}")
async def get_single_news_catalyst_endpoint(catalyst_id: int):
    """Retrieve complete verified catalyst record with raw OmniRouter AI telemetry."""
    try:
        from earnings_engine.data.db import _connect
        import sqlite3
        with _connect(_settings) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM news_catalysts WHERE id = ?", (catalyst_id,)).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Catalyst record not found")
            return {"success": True, "catalyst": dict(row)}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error fetching single catalyst %s: %s", catalyst_id, e)
        raise HTTPException(status_code=500, detail=f"Error fetching catalyst: {str(e)}")


@router.get("/api/v1/news/catalyst-stats")
async def get_news_catalyst_stats(
    watchlist_or_universe: str | None = Query(None),
    watchlist: str | None = Query(None),
    universe: str | None = Query(None),
    market: str | None = Query(None),
    days: int = Query(14, ge=0, le=365),
):
    """Retrieve aggregated counts and category distribution of news catalysts."""
    try:
        effective_market = watchlist_or_universe or universe or watchlist or market or "ALL"
        stats = await asyncio.to_thread(
            get_catalyst_summary_stats,
            watchlist_or_universe=effective_market,
            days=days,
            settings=_settings,
        )
        return {"success": True, "stats": stats, **(stats or {})}
    except Exception as e:
        logger.exception("Error in get_news_catalyst_stats: %s", e)
        raise HTTPException(status_code=500, detail=f"Error fetching catalyst stats: {str(e)}")


@router.get("/api/v1/news/outcomes")
@router.get("/api/v1/catalysts/outcomes")
async def get_news_outcomes_endpoint(
    category: str | None = Query(None),
    direction: str | None = Query(None),
    status: str | None = Query(None),
    predicted_met: bool | None = Query(None),
    verified_only: bool = Query(False),
    search: str | None = Query(None),
    sort_by: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    """Retrieve post-catalyst market reaction performance auditing."""
    try:
        effective_status = "VERIFIED" if verified_only else status
        outcomes = await asyncio.to_thread(
            get_verified_catalyst_outcomes,
            category=category,
            direction=direction,
            status=effective_status,
            search_query=search,
            sort_by=sort_by,
            limit=limit,
            settings=_settings,
        )
        if predicted_met is not None:
            outcomes = [o for o in outcomes if bool(o.get("predicted_met")) == predicted_met]
        return {"success": True, "count": len(outcomes), "outcomes": outcomes}
    except Exception as e:
        logger.exception("Error in get_news_outcomes: %s", e)
        raise HTTPException(status_code=500, detail=f"Error fetching outcomes: {str(e)}")


@router.post("/api/v1/news/outcomes/evaluate")
async def evaluate_news_outcomes_endpoint(request: dict | None = None):
    """Trigger forward return calculation and verification for pending catalysts."""
    force = bool((request or {}).get("force", False))
    try:
        res = await asyncio.to_thread(evaluate_all_catalyst_outcomes, settings=_settings, force=force)
        return {"success": True, **res}
    except Exception as e:
        logger.exception("Error evaluating news outcomes: %s", e)
        raise HTTPException(status_code=500, detail=f"Error evaluating outcomes: {str(e)}")


@router.get("/api/v1/news/trade-metrics")
async def get_news_trade_metrics_endpoint(
    category: str | None = Query(None),
    min_impact: int = Query(0, ge=0),
):
    """Quantitative trade-readiness KPIs across news catalysts (Win Rate, Profit Factor, Expectancy)."""
    try:
        metrics = await asyncio.to_thread(
            compute_news_trade_metrics,
            settings=_settings,
            category=category,
            min_impact=min_impact,
        )
        return {"success": True, "metrics": metrics, **(metrics or {})}
    except Exception as e:
        logger.exception("Error in get_news_trade_metrics: %s", e)
        raise HTTPException(status_code=500, detail=f"Error fetching trade metrics: {str(e)}")


@router.post("/api/v1/news/scan")
async def run_news_scan_endpoint(request: dict | None = None):
    """Trigger background news and corporate filing ingestion scan."""
    watchlist = (request or {}).get("watchlist") or (request or {}).get("market")
    force = bool((request or {}).get("force", False))
    try:
        res = await asyncio.to_thread(scan_watchlist_catalysts, watchlist_name=watchlist, force=force, settings=_settings)
        return {"success": True, **res}
    except Exception as e:
        logger.exception("Error in run_news_scan: %s", e)
        raise HTTPException(status_code=500, detail=f"News scan failed: {str(e)}")


@router.get("/api/v1/news/activity")
async def get_news_activity_stream(limit: int = Query(50, ge=1, le=200)):
    """Retrieve real-time live activity stream of breaking market filings."""
    try:
        activity = await asyncio.to_thread(get_recent_news_activity, limit=limit, settings=_settings)
        return {"success": True, "count": len(activity), "activity": activity}
    except Exception as e:
        logger.exception("Error in get_news_activity_stream: %s", e)
        raise HTTPException(status_code=500, detail=f"Error fetching activity stream: {str(e)}")


@router.get("/api/v1/omniroute/status")
async def get_omniroute_status_endpoint():
    """Probe and return the real-time health and status of the diegosouzapw/OmniRoute gateway."""
    try:
        from earnings_engine.data.omniroute_client import OmniRouteClient
        client = OmniRouteClient(settings=_settings)
        health = await asyncio.to_thread(client.probe_health)
        return {"success": True, "gateway": "diegosouzapw/OmniRoute", **health}
    except Exception as e:
        logger.exception("Error probing OmniRoute status: %s", e)
        return {
            "success": False,
            "gateway": "diegosouzapw/OmniRoute",
            "status": "offline",
            "error": str(e),
        }


@router.post("/api/v1/omniroute/analyze")
async def analyze_with_omniroute_endpoint(payload: dict):
    """Directly execute AI news analysis for any corporate headline using diegosouzapw/OmniRoute."""
    try:
        from earnings_engine.data.omniroute_client import OmniRouteClient
        client = OmniRouteClient(settings=_settings)
        result = await asyncio.to_thread(
            client.analyze_catalyst,
            item=payload,
            preferred_model=payload.get("model"),
        )
        return {"success": True, "analysis": result, **result}
    except Exception as e:
        logger.exception("Error executing OmniRoute analysis: %s", e)
        raise HTTPException(status_code=500, detail=f"OmniRoute analysis error: {str(e)}")


@router.post("/api/v1/news/analyze-ondemand")
async def analyze_news_ondemand_endpoint(payload: dict):
    """Execute on-demand AI analysis for a single news item and persist structured output atomically."""
    ticker = payload.get("ticker", "").strip().upper()
    title = payload.get("title", "").strip()
    model = payload.get("model")
    raw_item = payload.get("item")
    if not ticker or not title:
        raise HTTPException(status_code=400, detail="Missing required fields: ticker and title")

    try:
        from earnings_engine.data.news_pipeline import analyze_news_item_ondemand
        result = await asyncio.to_thread(
            analyze_news_item_ondemand,
            ticker=ticker,
            title=title,
            settings=_settings,
            model=model,
            raw_item=raw_item,
        )
        return {"success": True, "catalyst": result, **result}
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        logger.exception("Error during on-demand news analysis for %s (%s): %s", ticker, title[:30], e)
        raise HTTPException(status_code=500, detail=f"AI analysis failed: {str(e)}")


@router.post("/api/v1/news/analyze-batch")
async def analyze_news_batch_endpoint(payload: dict):
    """Execute on-demand AI analysis for a batch of multi-selected news items."""
    items = payload.get("items", [])
    model = payload.get("model")
    if not items or not isinstance(items, list):
        raise HTTPException(status_code=400, detail="Missing or invalid 'items' list in payload")

    try:
        from earnings_engine.data.news_pipeline import analyze_news_batch_ondemand
        results = await asyncio.to_thread(
            analyze_news_batch_ondemand,
            items=items,
            settings=_settings,
            model=model,
        )
        return {"success": True, "count": len(results), "catalysts": results}
    except Exception as e:
        logger.exception("Error during batch news analysis: %s", e)
        raise HTTPException(status_code=500, detail=f"Batch AI analysis failed: {str(e)}")


