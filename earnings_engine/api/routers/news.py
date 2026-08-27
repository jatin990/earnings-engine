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
    market: str | None = Query("ALL"),
    watchlist: str | None = Query(None),
    category: str | None = Query(None),
    impact: str | None = Query(None),
    impact_level: str | None = Query(None),
    direction: str | None = Query(None),
    search: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    """Retrieve structured news catalysts (order wins, expansions, regulatory approvals)."""
    try:
        effective_market = watchlist or market
        effective_impact = impact_level or impact
        items = await asyncio.to_thread(
            get_short_term_catalysts,
            watchlist_or_universe=effective_market,
            impact_filter=effective_impact,
            category_filter=category,
            direction_filter=direction,
            search_query=search,
            limit=limit,
            settings=_settings,
        )
        return {"success": True, "count": len(items), "catalysts": items}
    except Exception as e:
        logger.exception("Error in get_news_catalysts: %s", e)
        raise HTTPException(status_code=500, detail=f"Error fetching catalysts: {str(e)}")


@router.get("/api/v1/news/catalyst-stats")
async def get_news_catalyst_stats():
    """Retrieve aggregated counts and category distribution of news catalysts."""
    try:
        stats = await asyncio.to_thread(get_catalyst_summary_stats, settings=_settings)
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
            search=search,
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
