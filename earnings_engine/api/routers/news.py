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


@router.get("/api/v1/news/feeds-status")
async def get_news_feeds_status():
    """Return all configured news, regulatory, and corporate filing feeds with health & last fetch telemetry."""
    try:
        from earnings_engine.data.news_sources import get_all_feed_metadata
        from earnings_engine.data.catalysts_news import _connect
        import sqlite3

        feeds = get_all_feed_metadata()

        # Query harvester schedule status
        sched_info: dict[str, Any] = {}
        src_stats: dict[str, dict[str, Any]] = {}
        try:
            with _connect(_settings) as conn:
                conn.row_factory = sqlite3.Row
                sched_row = conn.execute(
                    "SELECT * FROM automation_schedules WHERE job_id = ?",
                    ("news_catalyst_harvest",),
                ).fetchone()
                if sched_row:
                    sched_info = dict(sched_row)

                stat_rows = conn.execute(
                    """
                    SELECT source, COUNT(*) as count,
                           MAX(created_at) as last_ingested_at,
                           MAX(published_at) as last_published_at
                    FROM news_catalysts
                    GROUP BY source
                    """
                ).fetchall()
                for r in stat_rows:
                    src_stats[r["source"]] = dict(r)
        except Exception as e:
            logger.debug("Failed querying news feed DB stats: %s", e)

        # Enhance feeds with operational telemetry
        for f in feeds:
            s_key = f.get("source_key")
            stat = src_stats.get(s_key) or {}
            f["last_ingested_at"] = stat.get("last_ingested_at") or sched_info.get("last_run_at")
            f["last_published_at"] = stat.get("last_published_at")
            f["total_ingested_for_source"] = stat.get("count", 0)

        # Count groups
        groups_summary: dict[str, int] = {}
        for f in feeds:
            grp = f.get("group", "Other")
            groups_summary[grp] = groups_summary.get(grp, 0) + 1

        return {
            "success": True,
            "total_feeds": len(feeds),
            "groups_summary": groups_summary,
            "harvester_schedule": {
                "job_id": sched_info.get("job_id"),
                "job_name": sched_info.get("job_name"),
                "last_run_at": sched_info.get("last_run_at"),
                "next_run_at": sched_info.get("next_run_at"),
                "interval_seconds": sched_info.get("interval_seconds", 600),
                "is_enabled": bool(sched_info.get("is_enabled", 1)),
                "last_summary": sched_info.get("last_summary"),
            },
            "feeds": feeds,
        }
    except Exception as e:
        logger.exception("Error in get_news_feeds_status: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed loading feeds status: {str(e)}")


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
async def get_omniroute_status_endpoint(host: str | None = None, api_key: str | None = None):
    """Probe and return the real-time health and status of the diegosouzapw/OmniRoute gateway."""
    try:
        from earnings_engine.data.omniroute_client import OmniRouteClient
        client = OmniRouteClient(settings=_settings)
        health = await asyncio.to_thread(client.probe_health, host=host, api_key=api_key)
        return {"success": True, "gateway": "diegosouzapw/OmniRoute", **health}
    except Exception as e:
        logger.exception("Error probing OmniRoute status: %s", e)
        return {
            "success": False,
            "gateway": "diegosouzapw/OmniRoute",
            "status": "offline",
            "error": str(e),
        }


@router.get("/api/v1/omniroute/models")
async def get_omniroute_models_endpoint(host: str | None = None, api_key: str | None = None):
    """Return available OmniRoute models categorized by reasoning capability (matching local models selector)."""
    try:
        from earnings_engine.data.omniroute_client import OmniRouteClient
        client = OmniRouteClient(settings=_settings)
        models_data = await asyncio.to_thread(client.get_available_models, host=host, api_key=api_key)
        return models_data
    except Exception as e:
        logger.exception("Error fetching OmniRoute models: %s", e)
        return {
            "success": False,
            "error": str(e),
            "models": [],
        }


@router.get("/api/v1/omniroute/setup/{ticker}")
async def get_omniroute_setup_endpoint(ticker: str):
    """Retrieve the latest cached OmniRoute trade setup from the database for a stock."""
    sym = ticker.strip().upper()
    try:
        from earnings_engine.consensus import storage
        preds = await asyncio.to_thread(storage.get_predictions, settings=_settings, ticker=sym, limit=1)
        if not preds:
            return {"success": True, "found": False, "setup": None, "ticker": sym}

        latest = preds[0]
        models_breakdown = latest.get("models_breakdown") or []
        omniroute_model = next(
            (m for m in models_breakdown if "omniroute" in str(m.get("model_id", "")).lower() or "omniroute" in str(m.get("gateway", "")).lower() or "omniroute" in str(m.get("model_name", "")).lower()),
            None
        )

        as_of_p = latest.get("as_of_price") or 0.0
        tgt_p = latest.get("consensus_target_price") or (omniroute_model.get("target_price") if omniroute_model else None)
        sup_p = latest.get("consensus_support") or (omniroute_model.get("support_level") if omniroute_model else None)
        res_p = latest.get("consensus_resistance") or (omniroute_model.get("resistance_level") if omniroute_model else None)
        sl_p = omniroute_model.get("stop_loss_price") if omniroute_model else (round(sup_p * 0.98, 2) if sup_p else None)
        dir_val = omniroute_model.get("direction") if omniroute_model else latest.get("consensus_direction", "BULLISH")
        conf_val = omniroute_model.get("confidence_pct") if omniroute_model else int(latest.get("consensus_strength") or 80)
        rr_val = omniroute_model.get("risk_reward_ratio") if omniroute_model else 2.2

        floor_e = min(as_of_p, sup_p) if as_of_p and sup_p else (sup_p or as_of_p)
        entry_z = f"₹{floor_e:.2f} – ₹{as_of_p:.2f}" if as_of_p and floor_e else "—"

        setup = {
            "ticker": sym,
            "as_of_price": as_of_p,
            "timeframe_days": latest.get("timeframe_days", 14),
            "direction": dir_val,
            "confidence_pct": conf_val,
            "target_price": tgt_p,
            "support_level": sup_p,
            "resistance_level": res_p,
            "stop_loss_price": sl_p,
            "risk_reward_ratio": rr_val,
            "consensus_entry_zone": entry_z,
            "chart_pattern": (omniroute_model.get("chart_pattern") if omniroute_model else None) or "OmniRoute Multi-Model Dynamic Setup",
            "key_drivers": (omniroute_model.get("key_drivers") if omniroute_model else None) or ["Multi-factor consensus alignment", "Volume & momentum confirmation"],
            "primary_risk": (omniroute_model.get("primary_risk") if omniroute_model else None) or "Broader market index volatility",
            "synthesized_thesis": latest.get("synthesized_thesis") or (omniroute_model.get("rationale_summary") if omniroute_model else "OmniRoute quantitative momentum alignment."),
            "recommended_action": (omniroute_model.get("recommended_action") if omniroute_model else None) or ("STRONG BUY" if dir_val == "BULLISH" and conf_val >= 80 else "ACCUMULATE ON DIPS"),
            "ai_model": (omniroute_model.get("model_id") if omniroute_model else "omniroute/deepseek-r1"),
            "ai_model_name": (omniroute_model.get("model_name") if omniroute_model else "OmniRoute-AI"),
            "gateway": (omniroute_model.get("gateway") if omniroute_model else "diegosouzapw/OmniRoute"),
            "created_at": latest.get("created_at"),
            "is_cached": True,
            "raw_response": (omniroute_model.get("raw_response") if omniroute_model else json.dumps(latest, default=str)),
        }

        return {"success": True, "found": True, "setup": setup, "ticker": sym}
    except Exception as e:
        logger.exception("Error loading OmniRoute setup for %s: %s", sym, e)
        return {"success": False, "error": str(e), "setup": None, "ticker": sym}


@router.post("/api/v1/omniroute/setup/{ticker}")
async def generate_omniroute_setup_endpoint(ticker: str, payload: dict | None = None):
    """Generate or re-evaluate an OmniRoute trade setup for a stock and cache it in the database."""
    sym = ticker.strip().upper()
    body = payload or {}
    chosen_model = body.get("model") or body.get("model_id") or "deepseek/deepseek-r1"
    host = body.get("host") or body.get("endpoint")
    api_key = body.get("api_key")
    timeframe_days = int(body.get("timeframe_days") or 14)

    try:
        from earnings_engine.data.omniroute_client import OmniRouteClient
        from earnings_engine.api import stock_api
        from earnings_engine.consensus import storage

        # Fetch live quote and technicals
        quote_res = await asyncio.to_thread(stock_api.get_stock_quote, ticker=sym, settings=_settings)
        tech_res = await asyncio.to_thread(stock_api.get_stock_technicals, ticker=sym, settings=_settings)
        cat_res = await asyncio.to_thread(stock_api.get_stock_catalysts, ticker=sym, settings=_settings)

        price = quote_res.get("quote", {}).get("current_price") or 0.0
        technicals = tech_res.get("technical") or {}
        catalysts = cat_res.get("catalysts") or []

        client = OmniRouteClient(settings=_settings)
        setup = await asyncio.to_thread(
            client.generate_stock_setup,
            ticker=sym,
            as_of_price=price,
            technicals=technicals,
            catalysts=catalysts,
            timeframe_days=timeframe_days,
            model=chosen_model,
            host=host,
            api_key=api_key,
        )

        # Persist into consensus_predictions table
        eval_date = (datetime.now() + timedelta(days=timeframe_days)).strftime("%Y-%m-%d")
        consensus_record = {
            "ticker": sym,
            "as_of_price": price,
            "timeframe_days": timeframe_days,
            "consensus_direction": setup["direction"],
            "consensus_strength": float(setup["confidence_pct"]),
            "consensus_return_pct": round(((setup["target_price"] / price) - 1.0) * 100.0, 2) if price > 0 and setup.get("target_price") else 4.5,
            "consensus_target_price": setup.get("target_price"),
            "consensus_support": setup.get("support_level"),
            "consensus_resistance": setup.get("resistance_level"),
            "model_count": 1,
            "agreement_ratio": 1.0,
            "synthesized_thesis": setup.get("synthesized_thesis"),
            "models_breakdown": [
                {
                    "model_id": setup.get("ai_model"),
                    "model_name": setup.get("ai_model_name"),
                    "direction": setup["direction"],
                    "confidence_pct": setup["confidence_pct"],
                    "target_price": setup.get("target_price"),
                    "support_level": setup.get("support_level"),
                    "resistance_level": setup.get("resistance_level"),
                    "stop_loss_price": setup.get("stop_loss_price"),
                    "risk_reward_ratio": setup.get("risk_reward_ratio"),
                    "chart_pattern": setup.get("chart_pattern"),
                    "key_drivers": setup.get("key_drivers"),
                    "primary_risk": setup.get("primary_risk"),
                    "rationale_summary": setup.get("synthesized_thesis"),
                    "recommended_action": setup.get("recommended_action"),
                    "latency_ms": setup.get("latency_ms"),
                    "tokens_used": setup.get("tokens_used"),
                    "gateway": setup.get("gateway"),
                    "raw_response": setup.get("raw_response"),
                }
            ],
        }

        row_id = await asyncio.to_thread(storage.save_prediction, consensus=consensus_record, evaluation_date=eval_date, settings=_settings)
        setup["prediction_id"] = row_id
        setup["is_cached"] = False

        return {"success": True, "setup": setup, "prediction_id": row_id}
    except Exception as e:
        logger.exception("Error generating OmniRoute setup for %s: %s", sym, e)
        raise HTTPException(status_code=500, detail=f"OmniRoute setup generation failed: {str(e)}")


@router.post("/api/v1/omniroute/analyze")
async def analyze_with_omniroute_endpoint(payload: dict, model: str | None = None):
    """Directly execute AI news analysis for any corporate headline using diegosouzapw/OmniRoute with configurable model."""
    try:
        from earnings_engine.data.omniroute_client import OmniRouteClient
        client = OmniRouteClient(settings=_settings)
        chosen_model = model or payload.get("model") or payload.get("preferred_model")
        result = await asyncio.to_thread(
            client.analyze_catalyst,
            item=payload,
            preferred_model=chosen_model,
        )
        return {"success": True, "analysis": result, **result}
    except Exception as e:
        logger.exception("Error executing OmniRoute analysis: %s", e)
        raise HTTPException(status_code=500, detail=f"OmniRoute analysis error: {str(e)}")


@router.post("/api/v1/news/ai-analyze")
async def analyze_news_ai_endpoint(payload: dict, model: str | None = None):
    """Analyze corporate news headline with configurable AI model and rich market context."""
    try:
        from earnings_engine.data.ai_news_analyzer import analyze_news_catalyst_ai
        chosen_model = model or payload.get("model") or payload.get("preferred_model")
        result = await asyncio.to_thread(
            analyze_news_catalyst_ai,
            item=payload,
            settings=_settings,
            preferred_model=chosen_model,
        )
        return {"success": True, "analysis": result, **result}
    except Exception as e:
        logger.exception("Error executing news AI analysis: %s", e)
        raise HTTPException(status_code=500, detail=f"News AI analysis error: {str(e)}")


@router.post("/api/v1/news/extract-structured")
async def extract_structured_news_endpoint(payload: dict, model: str | None = None):
    """Execute structured, type-safe news extraction returning NewsExtractedData schema with configurable model."""
    try:
        from earnings_engine.data.ai_news_analyzer import extract_structured_news_data
        chosen_model = model or payload.get("model") or payload.get("preferred_model")
        result = await asyncio.to_thread(
            extract_structured_news_data,
            item=payload,
            settings=_settings,
            preferred_model=chosen_model,
        )
        return {
            "success": True,
            "extracted": result.model_dump() if hasattr(result, "model_dump") else result,
            **result.to_db_dict(),
        }
    except Exception as e:
        logger.exception("Error executing structured news extraction: %s", e)
        raise HTTPException(status_code=500, detail=f"Structured extraction error: {str(e)}")


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


