"""Dedicated stock intelligence, factor evaluation, recalculation, and audit log routes."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from earnings_engine.api.dependencies import (
    _settings,
    get_template_env,
    CalculateEpsRequest,
)
from earnings_engine.api import stock_api, recalculate_api
from earnings_engine.logging_utils import get_logger

logger = get_logger("earnings_engine.api.routers.stocks")

router = APIRouter(tags=["Stock Intelligence & Factors"])


@router.get("/stock/{ticker}", tags=["UI"], response_class=HTMLResponse)
async def serve_stock_detail(ticker: str):
    """Serve the dedicated Stock Detail & AI Consensus Engine page."""
    try:
        env = get_template_env()
        template = env.get_template("stock_detail.html")
        html = template.render(ticker=ticker.upper())
        return HTMLResponse(html)
    except Exception as exc:
        return HTMLResponse(
            f"<html><body><h1>Stock Detail render error</h1><p>{exc}</p></body></html>",
            status_code=500,
        )


@router.get("/api/v1/stock/{ticker}/overview")
async def get_stock_overview_endpoint(ticker: str):
    """Return full stock overview including live quote, metrics, and EPS history."""
    try:
        return await asyncio.to_thread(stock_api.get_stock_overview, ticker=ticker.upper(), settings=_settings)
    except Exception as e:
        logger.exception("Error in get_stock_overview for %s: %s", ticker, e)
        raise HTTPException(status_code=500, detail=f"Error fetching stock overview: {str(e)}")


@router.get("/api/v1/stock/{ticker}/factor-evaluation")
async def get_stock_factor_evaluation_endpoint(ticker: str):
    """Return factor evaluation score breakdown for a stock."""
    try:
        return await asyncio.to_thread(stock_api.get_stock_factor_evaluation, ticker=ticker.upper(), settings=_settings)
    except Exception as e:
        logger.exception("Error in get_stock_factor_evaluation for %s: %s", ticker, e)
        raise HTTPException(status_code=500, detail=f"Error fetching factor evaluation: {str(e)}")


@router.get("/api/v1/stock/{ticker}/notes")
async def get_stock_notes_endpoint(ticker: str):
    """Return consolidated AI intelligence notes for a stock."""
    try:
        return await asyncio.to_thread(stock_api.get_stock_intelligence_note, ticker=ticker.upper(), settings=_settings)
    except Exception as e:
        logger.exception("Error in get_stock_notes for %s: %s", ticker, e)
        raise HTTPException(status_code=500, detail=f"Error fetching notes: {str(e)}")


@router.post("/api/v1/stock/{ticker}/calculate-eps")
async def calculate_eps_endpoint(ticker: str, req: CalculateEpsRequest):
    """Calculate and derive EPS estimate, reported values, surprise %, and quality score."""
    try:
        return await asyncio.to_thread(
            stock_api.calculate_or_fetch_eps,
            ticker=ticker.upper(),
            earnings_date=req.earnings_date,
            override_estimate=req.override_estimate,
            override_reported=req.override_reported,
            settings=_settings,
        )
    except Exception as e:
        logger.exception("Error in calculate_eps for %s: %s", ticker, e)
        raise HTTPException(status_code=500, detail=f"Error calculating EPS: {str(e)}")


@router.get("/api/v1/stock/{ticker}/quarterly-financials")
async def get_quarterly_financials_endpoint(ticker: str):
    """Return trailing quarterly income statements and balance sheet metrics."""
    try:
        return await stock_api.get_quarterly_financials(ticker=ticker, settings=_settings)
    except Exception as e:
        logger.exception("Error in get_quarterly_financials for %s: %s", ticker, e)
        raise HTTPException(status_code=500, detail=f"Error fetching financials: {str(e)}")


@router.get("/api/v1/stock/{ticker}/factors")
async def get_stock_factors_endpoint(ticker: str):
    """Return 6-pillar factor evaluation (Quality, Momentum, Valuation, Catalyst, Volatility, Sentiment)."""
    try:
        return await stock_api.get_stock_factor_scores(ticker=ticker, settings=_settings)
    except Exception as e:
        logger.exception("Error in get_stock_factors for %s: %s", ticker, e)
        raise HTTPException(status_code=500, detail=f"Error fetching factor scores: {str(e)}")


@router.post("/api/v1/stock/{ticker}/factors/evaluate")
async def evaluate_stock_factors_endpoint(ticker: str, request: dict | None = None):
    """Trigger fresh evaluation of standardized factor weights for a stock."""
    try:
        return await stock_api.evaluate_stock_factors(ticker=ticker, settings=_settings)
    except Exception as e:
        logger.exception("Error in evaluate_stock_factors for %s: %s", ticker, e)
        raise HTTPException(status_code=500, detail=f"Error evaluating factors: {str(e)}")


@router.get("/api/v1/stock/{ticker}/recalculated-preview")
async def get_recalculated_preview_endpoint(ticker: str):
    """Preview newly computed metrics vs existing cached metrics for a stock."""
    try:
        return await recalculate_api.preview_recalculated_metrics(ticker=ticker, settings=_settings)
    except Exception as e:
        logger.exception("Error in get_recalculated_preview for %s: %s", ticker, e)
        raise HTTPException(status_code=500, detail=f"Error previewing metrics: {str(e)}")


@router.post("/api/v1/ticker/recalculate")
async def recalculate_ticker_metrics_endpoint(
    ticker: str = Query(..., description="Stock ticker symbol to refresh and recalculate"),
):
    """Force refresh earnings date, prices, recalculate technical/quality metrics, and log audit trail."""
    try:
        res = await asyncio.to_thread(
            recalculate_api.recalculate_ticker_metrics,
            ticker=ticker.upper(),
            settings=_settings,
        )
        return res
    except Exception as e:
        logger.exception("Error in recalculate_ticker_metrics: %s", e)
        raise HTTPException(status_code=500, detail=f"Recalculation error: {str(e)}")


@router.get("/api/v1/ticker/audit-log")
async def get_ticker_audit_log_endpoint(
    ticker: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    """Retrieve audit log of recalculated fields and changes."""
    try:
        from earnings_engine.data.ticker_audit import get_audit_history
        result = await asyncio.to_thread(
            get_audit_history,
            ticker=ticker,
            limit=limit,
            settings=_settings,
        )
        return result
    except Exception as e:
        logger.exception("Error in get_ticker_audit_log: %s", e)
        raise HTTPException(status_code=500, detail=f"Audit log error: {str(e)}")


@router.post("/api/v1/ticker/audit-log/resolve")
async def resolve_audit_log_endpoint(request: dict):
    """Mark an audit log entry as resolved or confirmed."""
    try:
        entry_id = request.get("id")
        resolution_notes = request.get("resolution_notes", "")
        return await recalculate_api.resolve_audit_log_entry(
            entry_id=entry_id,
            resolution_notes=resolution_notes,
            settings=_settings,
        )
    except Exception as e:
        logger.exception("Error in resolve_audit_log_entry: %s", e)
        raise HTTPException(status_code=500, detail=f"Audit resolve error: {str(e)}")
