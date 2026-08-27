"""Multi-Model AI Consensus Engine, Local Model Detection, and Prediction Routing."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import os
from typing import Any
import requests

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from earnings_engine.api.dependencies import (
    _settings,
    ConsensusPredictRequest,
    ConsensusSettleRequest,
)
from earnings_engine.consensus.aggregator import (
    aggregate_predictions,
)
from earnings_engine.consensus.context_builder import build_context
from earnings_engine.consensus.model_runner import DEFAULT_MODELS, run_consensus_models
from earnings_engine.consensus.settlement import settle_pending_predictions
from earnings_engine.consensus.storage import (
    get_accuracy_stats,
    get_prediction_by_id,
    get_predictions,
    save_prediction,
)
from earnings_engine.logging_utils import get_logger
from earnings_engine.rate_limits import (
    AVAILABLE_AI_MODELS,
    get_models_rate_limits,
    is_rate_limited,
)

logger = get_logger("earnings_engine.api.routers.consensus")

router = APIRouter(tags=["AI Consensus Engine"])

_CACHED_LOCAL_MODELS: dict[str, Any] = {}


def _scan_and_cache_local_models(host: str | None = None) -> dict[str, Any]:
    """Scan running local model endpoints (Ollama / LM Studio) and cache the result."""
    ollama_host = (host or os.getenv("LOCAL_LLM_URL") or os.getenv("OLLAMA_HOST") or "http://localhost:11434").rstrip("/")
    models = []
    status = "offline"
    try:
        resp = requests.get(f"{ollama_host}/api/tags", timeout=1.5)
        if resp.status_code == 200:
            status = "online"
            data = resp.json()
            for m in data.get("models", []):
                models.append({
                    "name": m.get("name"),
                    "size": m.get("size"),
                    "modified_at": m.get("modified_at"),
                    "provider": "ollama",
                })
    except Exception:
        pass

    if not models:
        try:
            resp = requests.get(f"{ollama_host}/v1/models", timeout=1.5)
            if resp.status_code == 200:
                status = "online"
                data = resp.json()
                for m in data.get("data", []):
                    models.append({
                        "name": m.get("id"),
                        "provider": "openai-compatible",
                    })
        except Exception:
            pass

    if not models:
        models = [
            {"name": "deepseek-r1:8b", "provider": "ollama", "recommended": True},
            {"name": "deepseek-r1:14b", "provider": "ollama"},
            {"name": "llama3.2:3b", "provider": "ollama"},
            {"name": "llama3.1:8b", "provider": "ollama"},
            {"name": "qwen2.5:7b", "provider": "ollama"},
            {"name": "mistral:7b", "provider": "ollama"},
        ]

    result = {
        "success": True,
        "status": status,
        "host": ollama_host,
        "models": models,
        "default_model": os.getenv("OLLAMA_MODEL", "deepseek-r1:8b"),
        "scanned_at": datetime.now(timezone.utc).isoformat(),
    }
    global _CACHED_LOCAL_MODELS
    if not host or host == ollama_host:
        _CACHED_LOCAL_MODELS = result
    logger.info("[LOCAL-MODELS] Scanned %s (status: %s, models: %d)", ollama_host, status, len(models))
    return result


@router.get("/api/v1/consensus/models")
async def get_consensus_models():
    """Return available AI models, their display metadata, and live rate limit quotas."""
    try:
        from earnings_engine.rate_limits import get_ratelimits_summary
        models = get_models_rate_limits()
        return {
            "success": True,
            "models": models,
            "default_models": DEFAULT_MODELS,
            "rate_limits": get_ratelimits_summary(_settings),
        }
    except Exception as e:
        logger.exception("Error fetching consensus models: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/v1/consensus/local-models")
@router.get("/api/v1/local-models")
async def get_local_models(
    host: str | None = Query(None, description="Optional custom Ollama host to probe"),
    force_scan: bool = Query(False, description="Bypass cache and perform active network probe"),
):
    """Return locally available models detected on Ollama / LM Studio."""
    global _CACHED_LOCAL_MODELS
    if force_scan or not _CACHED_LOCAL_MODELS or (host and host != _CACHED_LOCAL_MODELS.get("host")):
        return await asyncio.to_thread(_scan_and_cache_local_models, host)
    return _CACHED_LOCAL_MODELS


@router.get("/api/v1/consensus/accuracy-stats")
async def get_consensus_accuracy_stats(
    market: str = Query("ALL", description="Market universe filter"),
    days: int = Query(90, description="Settled lookback days", ge=1, le=365),
):
    """Retrieve historical accuracy, hit rate, and Brier score across all models."""
    try:
        stats = await asyncio.to_thread(get_accuracy_stats, settings=_settings)
        return {"success": True, **(stats or {})}
    except Exception as e:
        logger.exception("Error in get_consensus_accuracy_stats: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/v1/consensus/settle")
async def settle_consensus_predictions(req: ConsensusSettleRequest = ConsensusSettleRequest()):
    """Settle past consensus predictions against actual post-earnings price reactions."""
    try:
        res = await asyncio.to_thread(settle_pending_predictions, settings=_settings, as_of_date=req.as_of_date)
        return res
    except Exception as e:
        logger.exception("Error in settle_consensus_predictions: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/v1/consensus/audit")
async def get_consensus_audit_records(
    ticker: str | None = Query(None, description="Optional ticker symbol filter"),
    status: str | None = Query(None, description="Status filter (SETTLED, PENDING)"),
    limit: int = Query(50, ge=1, le=5000),
):
    """Historical audit of consensus predictions including settlement outcomes and failure analyses."""
    try:
        from earnings_engine.consensus import storage
        preds = await asyncio.to_thread(
            storage.get_predictions,
            settings=_settings,
            ticker=ticker.upper().strip() if ticker else None,
            status=status,
            limit=limit,
        )
        return {"success": True, "count": len(preds), "audit_records": preds}
    except Exception as e:
        logger.exception("Error in get_consensus_audit_records: %s", e)
        raise HTTPException(status_code=500, detail=f"Error fetching consensus audit records: {str(e)}")


@router.get("/api/v1/consensus/latest")
async def get_latest_consensus_predictions(limit: int = Query(20, ge=1, le=5000)):
    """Retrieve recent consensus predictions."""
    try:
        preds = await asyncio.to_thread(get_predictions, settings=_settings, limit=limit)
        return {"success": True, "count": len(preds), "predictions": preds}
    except Exception as e:
        logger.exception("Error fetching latest predictions: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/v1/consensus/{prediction_id}")
async def get_consensus_prediction_by_id(prediction_id: int):
    """Retrieve a specific consensus prediction by ID."""
    try:
        pred = await asyncio.to_thread(get_prediction_by_id, prediction_id=prediction_id, settings=_settings)
        if not pred:
            raise HTTPException(status_code=404, detail="Prediction not found")
        return {"success": True, "prediction": pred}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error fetching prediction #%d: %s", prediction_id, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/v1/consensus/prediction")
async def get_cached_consensus_prediction(
    ticker: str = Query(..., description="Stock ticker symbol (e.g. TCS.NS)"),
    event_date: str | None = Query(None, description="Optional earnings event date (YYYY-MM-DD)"),
):
    """Retrieve cached consensus prediction if present."""
    try:
        preds = await asyncio.to_thread(get_predictions, settings=_settings, ticker=ticker.upper().strip(), limit=1)
        if not preds:
            return {"found": False, "prediction": None}
        return {"found": True, "prediction": preds[0]}
    except Exception as e:
        logger.exception("Error fetching cached prediction for %s: %s", ticker, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/v1/consensus/predict")
async def run_consensus_predict(req: ConsensusPredictRequest):
    """Execute live multi-model AI consensus reasoning workflow."""
    from earnings_engine.consensus import context_builder, model_runner, aggregator, storage
    from earnings_engine.rate_limits import get_models_rate_limits, get_ratelimits_summary

    target_tickers: list[str] = []
    if req.ticker:
        target_tickers.append(req.ticker.strip().upper())
    if req.tickers:
        for t in req.tickers:
            if t and t.strip().upper() not in target_tickers:
                target_tickers.append(t.strip().upper())

    if not target_tickers:
        raise HTTPException(status_code=400, detail="Must provide at least one ticker symbol.")

    results: list[dict[str, Any]] = []
    for ticker in target_tickers:
        try:
            if not req.force_refresh and not req.force:
                cached_preds = await asyncio.to_thread(storage.get_predictions, settings=_settings, ticker=ticker, limit=1)
                if cached_preds:
                    latest = cached_preds[0]
                    created_at_str = latest.get("created_at") or ""
                    is_usable_cache = False
                    try:
                        created_dt = datetime.fromisoformat(created_at_str)
                        age_secs = (datetime.now() - created_dt).total_seconds()
                        if age_secs < 86400 or latest.get("settlement_status") == "PENDING":
                            is_usable_cache = True
                    except Exception:
                        is_usable_cache = bool(latest.get("consensus_direction"))

                    if is_usable_cache:
                        logger.info("[CONSENSUS-CACHE] Returning cached prediction for %s (id=%s, direction=%s)",
                                    ticker, latest.get("id"), latest.get("consensus_direction"))
                        results.append(latest)
                        continue

            ctx = await asyncio.to_thread(context_builder.build_context, ticker=ticker, timeframe_days=req.timeframe_days, settings=_settings)
            as_of_price = ctx.get("price_action", {}).get("current_price") or ctx.get("current_price", 0.0)
            if not as_of_price or as_of_price <= 0:
                try:
                    import yfinance as yf
                    info = yf.Ticker(ticker).fast_info
                    as_of_price = float(info.last_price or 0.0)
                except Exception:
                    pass

            model_outputs = await asyncio.to_thread(
                model_runner.run_consensus_models,
                context=ctx,
                models=req.models,
                local_url=req.local_model_url,
            )

            # If running a single model (or subset), merge with previous model outputs to keep 4-model matrix updated
            if req.models and len(req.models) < len(model_runner.DEFAULT_MODELS):
                cached_preds = await asyncio.to_thread(storage.get_predictions, settings=_settings, ticker=ticker, limit=1)
                if cached_preds:
                    prev_models = cached_preds[0].get("models_breakdown", [])
                    new_ids = {m.get("model_id") for m in model_outputs}
                    new_names = {m.get("model_name") for m in model_outputs}
                    merged = [
                        m for m in prev_models
                        if m.get("model_id") not in new_ids and m.get("model_name") not in new_names
                    ]
                    merged.extend(model_outputs)
                    model_outputs = merged

            consensus = aggregator.aggregate_predictions(
                model_results=model_outputs,
                ticker=ticker,
                as_of_price=as_of_price,
                timeframe_days=req.timeframe_days,
            )

            eval_date = (datetime.now() + timedelta(days=req.timeframe_days)).strftime("%Y-%m-%d")
            pred_id = await asyncio.to_thread(storage.save_prediction, consensus, evaluation_date=eval_date, settings=_settings)
            consensus["id"] = pred_id
            consensus["evaluation_date"] = eval_date
            results.append(consensus)
        except Exception as e:
            logger.error("[CONSENSUS-API] Error predicting for %s: %s", ticker, e)
            results.append({"ticker": ticker, "error": str(e)})

    return {
        "success": True,
        "count": len(results),
        "prediction": results[0] if results else None,
        "predictions": results,
        "results": results,
        "models": get_models_rate_limits(),
        "rate_limits": get_ratelimits_summary(_settings),
    }


@router.post("/api/v1/consensus/run/{ticker}")
@router.get("/api/v1/consensus/run/{ticker}")
async def run_consensus_for_ticker_path(
    ticker: str,
    force: bool = Query(True),
    timeframe_days: int = Query(14),
):
    """Execute consensus prediction for a specific ticker path parameter."""
    req = ConsensusPredictRequest(ticker=ticker, force=force, timeframe_days=timeframe_days)
    return await run_consensus_predict(req)
