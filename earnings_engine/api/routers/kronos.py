"""Kronos AI 14-Day Deep Sequence Price Forecasting Routes."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from earnings_engine.api.dependencies import _settings
from earnings_engine.api import dashboard_api
from earnings_engine.data import predictions as predictions_mod
from earnings_engine.kronos_predictor import predict_single_stock
from earnings_engine.logging_utils import get_logger

logger = get_logger("earnings_engine.api.routers.kronos")

router = APIRouter(tags=["Kronos AI Forecasting"])


@router.get("/api/v1/dashboard/kronos")
async def get_dashboard_kronos_predictions(
    ticker: str | None = Query(None, description="Filter by ticker"),
    tickers: str | None = Query(None, description="Comma-separated tickers"),
    lookback: int = Query(60, description="Lookback window in days"),
    pred_len: int = Query(14, description="Forecast length in days"),
    device: str | None = Query(None, description="Compute device (cpu, cuda)"),
):
    """Retrieve cached Kronos predictions."""
    try:
        if ticker:
            return await asyncio.to_thread(
                dashboard_api.get_kronos_predictions_for_ticker,
                ticker=ticker.upper(),
            )
        t_list = [t.strip().upper() for t in tickers.split(",") if t.strip()] if tickers else None
        return await asyncio.to_thread(dashboard_api.get_kronos_latest_predictions, tickers=t_list)
    except Exception as e:
        logger.exception("Error in get_dashboard_kronos_predictions: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/v1/dashboard/kronos/run")
async def run_dashboard_kronos_batch(request: dict | None = None):
    """Run batch Kronos predictions for upcoming earnings or watchlist."""
    market = (request or {}).get("market", "ALL")
    days = int((request or {}).get("days", 14))
    device = (request or {}).get("device", "cpu")
    try:
        from earnings_engine.kronos_predictor import run_batch_kronos
        res = await asyncio.to_thread(run_batch_kronos, market=market, days=days, device=device, settings=_settings)
        return {"success": True, "count": len(res) if hasattr(res, "__len__") else 0, "predictions": res}
    except Exception as e:
        logger.exception("Error in run_dashboard_kronos_batch: %s", e)
        raise HTTPException(status_code=500, detail=f"Batch Kronos run failed: {str(e)}")


@router.post("/api/v1/kronos/predict/{ticker}")
@router.post("/api/v1/kronos/predict")
async def run_kronos_predict_ticker(
    ticker: str | None = None,
    lookback: int = Query(60, description="Lookback window in days"),
    pred_len: int = Query(14, description="Forecast length in days"),
    device: str | None = Query(None, description="Compute device (cpu, cuda)"),
    request: dict | None = None,
):
    """Generate 14-day deep sequence forecast for a single stock."""
    target_ticker = (ticker or (request or {}).get("ticker", "")).upper().strip()
    if not target_ticker:
        raise HTTPException(status_code=400, detail="Ticker symbol is required")
    eff_device = (request or {}).get("device") or device
    try:
        res = await asyncio.to_thread(
            dashboard_api.run_prediction_for_ticker,
            ticker=target_ticker,
            engine="kronos",
            device=eff_device,
        )
        if not res.get("success"):
            raise HTTPException(status_code=400, detail=res.get("error", "Failed to compute Kronos prediction"))
        return res
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error running Kronos for %s: %s", target_ticker, e)
        raise HTTPException(status_code=500, detail=f"Kronos prediction failed: {str(e)}")


@router.get("/api/v1/kronos/prediction")
async def get_cached_kronos_prediction(
    ticker: str = Query(..., description="Stock ticker symbol"),
):
    """Retrieve latest cached Kronos prediction."""
    try:
        pred = await asyncio.to_thread(predictions_mod.load_prediction, ticker, settings=_settings)
        if not pred:
            return {"found": False, "prediction": None}
        return {"found": True, "prediction": pred}
    except Exception as e:
        logger.exception("Error loading Kronos prediction for %s: %s", ticker, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/v1/dashboard/kronos/latest")
async def get_kronos_latest(
    tickers: str | None = Query(None, description="Comma-separated tickers"),
    watchlist: str | None = Query(None, description="Watchlist name"),
):
    """Retrieve latest predictions across the universe."""
    try:
        t_list = [t.strip().upper() for t in tickers.split(",") if t.strip()] if tickers else None
        return await asyncio.to_thread(dashboard_api.get_kronos_latest_predictions, tickers=t_list, watchlist=watchlist)
    except Exception as e:
        logger.exception("Error in get_kronos_latest: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/v1/dashboard/kronos/accuracy")
async def get_kronos_accuracy(
    tickers: str | None = Query(None, description="Comma-separated tickers"),
    watchlist: str | None = Query(None, description="Watchlist name"),
):
    """Retrieve Kronos accuracy tracking and historical validation metrics."""
    try:
        t_list = [t.strip().upper() for t in tickers.split(",") if t.strip()] if tickers else None
        return await asyncio.to_thread(dashboard_api.get_kronos_accuracy_api, tickers=t_list, watchlist=watchlist)
    except Exception as e:
        logger.exception("Error in get_kronos_accuracy: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/v1/dashboard/kronos/audit")
async def get_kronos_audit(
    tickers: str | None = Query(None, description="Comma-separated tickers"),
    watchlist: str | None = Query(None, description="Watchlist name"),
    limit: int = Query(50, description="Max entries to return"),
):
    """Retrieve Kronos predictions audit log."""
    try:
        t_list = [t.strip().upper() for t in tickers.split(",") if t.strip()] if tickers else None
        return await asyncio.to_thread(dashboard_api.get_kronos_predictions_audit, tickers=t_list, watchlist=watchlist, limit=limit)
    except Exception as e:
        logger.exception("Error in get_kronos_audit: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/v1/dashboard/kronos/history/{ticker}")
async def get_kronos_history(ticker: str):
    """Retrieve historical sequence predictions for a specific stock."""
    try:
        return await asyncio.to_thread(dashboard_api.get_kronos_predictions_for_ticker, ticker=ticker.upper())
    except Exception as e:
        logger.exception("Error in get_kronos_history for %s: %s", ticker, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/api/v1/dashboard/kronos/audit/{ticker}/{run_at}")
async def delete_kronos_audit_entry(ticker: str, run_at: str):
    """Delete a specific Kronos sequence forecast from the audit history."""
    try:
        deleted = await asyncio.to_thread(dashboard_api.delete_kronos_prediction, ticker=ticker, run_at=run_at, settings=_settings)
        return {"success": True, "deleted": deleted}
    except Exception as e:
        logger.exception("Error deleting Kronos audit entry: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/v1/dashboard/watchlist/kronos")
async def generate_watchlist_kronos_endpoint(request: dict | None = None):
    """Run batch Kronos predictions on an entire watchlist."""
    device = (request or {}).get("device")
    try:
        res = await asyncio.to_thread(dashboard_api.generate_watchlist_kronos)
        return res
    except Exception as e:
        logger.exception("Error in generate_watchlist_kronos: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
