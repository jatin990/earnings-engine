"""Strategy Auditor, Prediction Logging, and Outcome Verification Routes."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from earnings_engine.api.dependencies import _settings
from earnings_engine.logging_utils import get_logger

logger = get_logger("earnings_engine.api.routers.audit")

router = APIRouter(tags=["Strategy Auditor & Outcome Verification"])


class StrategyPredictionRequest(BaseModel):
    ticker: str
    strategy_name: str
    signal: str
    confidence_pct: float | None = None
    entry_price: float | None = None
    expected_return_pct: float | None = None
    holding_horizon: str = "1D"
    target_date: str | None = None
    news_source: str | None = None
    news_headline: str | None = None
    notes: str | None = None


class BulkPredictionRequest(BaseModel):
    predictions: list[dict[str, Any]]


class BacktestRequest(BaseModel):
    strategy: str = "ALL"
    days: int = 365
    universe: str | None = None


@router.post("/api/v1/audit/log")
async def audit_log_prediction(req: StrategyPredictionRequest):
    """Log a new daily stock prediction for a strategy."""
    try:
        from earnings_engine.data.strategy_auditor import log_prediction
        row_id = log_prediction(
            ticker=req.ticker,
            strategy_name=req.strategy_name,
            signal=req.signal,
            settings=_settings,
            confidence_pct=req.confidence_pct,
            entry_price=req.entry_price,
            expected_return_pct=req.expected_return_pct,
            holding_horizon=req.holding_horizon,
            target_date=req.target_date,
            news_source=req.news_source,
            news_headline=req.news_headline,
            notes=req.notes,
        )
        return {"success": True, "prediction_id": row_id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Error logging prediction: %s", e)
        raise HTTPException(status_code=500, detail=f"Error logging prediction: {str(e)}")


@router.post("/api/v1/audit/log/bulk")
async def audit_log_bulk(req: BulkPredictionRequest):
    """Bulk-log multiple predictions at once."""
    try:
        from earnings_engine.data.strategy_auditor import log_predictions_bulk
        ids = log_predictions_bulk(req.predictions, settings=_settings)
        return {"success": True, "count": len(ids), "prediction_ids": ids}
    except Exception as e:
        logger.exception("Error bulk logging: %s", e)
        raise HTTPException(status_code=500, detail=f"Error bulk logging: {str(e)}")


@router.post("/api/v1/audit/run")
async def audit_run_endpoint(request: dict | None = None):
    """Trigger an on-demand audit of pending predictions."""
    force = (request or {}).get("force", False)
    try:
        from earnings_engine.data.strategy_auditor import audit_predictions
        result = audit_predictions(settings=_settings, force=force)
        return {"success": True, **result}
    except Exception as e:
        logger.exception("Error running audit: %s", e)
        raise HTTPException(status_code=500, detail=f"Error running audit: {str(e)}")


@router.get("/api/v1/audit/metrics")
async def audit_metrics_endpoint(
    strategy: str | None = Query(None, description="Filter to a specific strategy"),
):
    """Retrieve calculated performance metrics grouped by strategy."""
    try:
        from earnings_engine.data.strategy_auditor import calculate_strategy_metrics
        metrics = calculate_strategy_metrics(strategy_name=strategy, settings=_settings)
        return {"success": True, **metrics}
    except Exception as e:
        logger.exception("Error fetching metrics: %s", e)
        raise HTTPException(status_code=500, detail=f"Error fetching metrics: {str(e)}")


@router.get("/api/v1/audit/history")
async def audit_history_endpoint(
    strategy: str | None = Query(None),
    ticker: str | None = Query(None),
    status: str | None = Query(None, description="Filter by audit status: WORKED, FAILED, PENDING"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """Fetch paginated prediction + audit history with filtering."""
    try:
        from earnings_engine.data.strategy_auditor import load_audit_history
        result = load_audit_history(
            strategy_name=strategy,
            ticker=ticker,
            status=status,
            limit=limit,
            offset=offset,
            settings=_settings,
        )
        return {"success": True, **result}
    except Exception as e:
        logger.exception("Error fetching audit history: %s", e)
        raise HTTPException(status_code=500, detail=f"Error fetching audit history: {str(e)}")


@router.get("/api/v1/audit/strategies")
async def audit_strategies_endpoint():
    """List all strategies that have logged predictions."""
    try:
        from earnings_engine.data.strategy_auditor import list_strategies
        strategies = list_strategies(settings=_settings)
        return {"success": True, "strategies": strategies}
    except Exception as e:
        logger.exception("Error listing strategies: %s", e)
        raise HTTPException(status_code=500, detail=f"Error listing strategies: {str(e)}")


@router.delete("/api/v1/audit/prediction/{prediction_id}")
async def audit_delete_prediction(prediction_id: int):
    """Delete a prediction and its audit log."""
    try:
        from earnings_engine.data.strategy_auditor import delete_prediction
        deleted = delete_prediction(prediction_id, settings=_settings)
        if not deleted:
            raise HTTPException(status_code=404, detail=f"Prediction #{prediction_id} not found")
        return {"success": True, "deleted": prediction_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error deleting prediction: %s", e)
        raise HTTPException(status_code=500, detail=f"Error deleting prediction: {str(e)}")


@router.post("/api/v1/audit/import-kronos")
async def audit_import_kronos_endpoint(request: dict | None = None):
    """Import historical Kronos forecasts and audit outcomes against actual price history."""
    force = (request or {}).get("force", False)
    try:
        from earnings_engine.data.strategy_auditor import import_kronos_predictions
        result = import_kronos_predictions(settings=_settings, force=force)
        return {"success": True, **result}
    except Exception as e:
        logger.exception("Error importing Kronos predictions: %s", e)
        raise HTTPException(status_code=500, detail=f"Error importing Kronos predictions: {str(e)}")


@router.post("/api/v1/audit/backtest")
async def audit_backtest_endpoint(req: BacktestRequest):
    """Run a historical strategy backtest simulation and audit all decisions."""
    try:
        from earnings_engine.data.strategy_auditor import backtest_strategy_history
        result = backtest_strategy_history(
            strategy_name=req.strategy,
            days=req.days,
            universe=req.universe,
            settings=_settings,
        )
        return {"success": True, **result}
    except Exception as e:
        logger.exception("Error running backtest: %s", e)
        raise HTTPException(status_code=500, detail=f"Error running backtest: {str(e)}")
