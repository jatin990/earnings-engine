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


@router.get("/api/v1/stock/{ticker}/rating")
async def get_stock_rating_endpoint(ticker: str):
    """Retrieve the industry-benchmarked fundamental rating, technical score, and AI note."""
    sym = ticker.upper().strip()
    try:
        from earnings_engine.data.stock_rating import get_stock_rating, recalculate_stock_rating
        rating = await asyncio.to_thread(get_stock_rating, sym, _settings)
        if not rating:
            rating = await asyncio.to_thread(recalculate_stock_rating, sym, _settings, source="auto_on_demand")
        return {"success": True, "ticker": sym, **(rating or {})}
    except Exception as e:
        logger.exception("Error in get_stock_rating for %s: %s", sym, e)
        raise HTTPException(status_code=500, detail=f"Error fetching stock rating: {str(e)}")


@router.api_route("/api/v1/stock/{ticker}/fetch-news", methods=["GET", "POST"])
async def fetch_stock_news_endpoint(ticker: str):
    """Fetch fresh news headlines and corporate announcements delta for a stock."""
    try:
        res = await asyncio.to_thread(stock_api.refresh_stock_news, ticker.upper().strip(), _settings)
        if not res.get("success"):
            raise HTTPException(status_code=400, detail=res.get("error", "Failed to refresh news delta"))
        return res
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error in fetch_stock_news for %s: %s", ticker, e)
        raise HTTPException(status_code=500, detail=f"Failed to refresh news: {str(e)}")


@router.get("/api/v1/stock/{ticker}/intelligence-note")
@router.post("/api/v1/stock/{ticker}/intelligence-note")
async def get_stock_intelligence_note_endpoint(
    ticker: str,
    model_name: str | None = Query(None, description="Preferred AI model"),
    provider: str | None = Query(None, description="Preferred provider"),
):
    """Return or generate an AI intelligence note for a stock."""
    try:
        return await asyncio.to_thread(
            stock_api.get_stock_intelligence_note,
            ticker=ticker.upper(),
            model_name=model_name,
            provider=provider,
            settings=_settings,
        )
    except Exception as e:
        logger.exception("Error in stock intelligence note for %s: %s", ticker, e)
        raise HTTPException(status_code=500, detail=f"Error with intelligence note: {str(e)}")


@router.post("/api/v1/stock/ratings/batch")
async def get_batch_stock_ratings(request: dict):
    """Compute and return ratings for a list of tickers."""
    tickers = request.get("tickers", [])
    try:
        results = {}
        for t in tickers:
            results[t] = stock_api.calculate_stock_rating(ticker=t.upper(), settings=_settings)
        return {"success": True, "ratings": results}
    except Exception as e:
        logger.exception("Error in batch stock ratings: %s", e)
        raise HTTPException(status_code=500, detail=f"Error computing batch ratings: {str(e)}")


@router.post("/api/v1/stock/{ticker}/calculate-eps")
@router.post("/api/v1/earnings/{ticker}/calculate-eps")
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
@router.post("/api/v1/stock/{ticker}/refresh-earnings-source")
@router.post("/api/v1/earnings/{ticker}/refresh-from-source")
async def refresh_earnings_source_endpoint(ticker: str):
    """Force re-fetch official earnings calendar and reported EPS from authentic sources (yfinance & NSE)."""
    try:
        from earnings_engine.data.earnings import refresh_earnings_from_source
        return await asyncio.to_thread(
            refresh_earnings_from_source,
            ticker=ticker.upper(),
            settings=_settings,
        )
    except Exception as e:
        logger.exception("Error in refresh_earnings_source for %s: %s", ticker, e)
        raise HTTPException(status_code=500, detail=f"Error refreshing earnings from source: {str(e)}")


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


@router.post("/api/v1/stock/{ticker}/recalculate")
@router.post("/api/v1/recalculate/{ticker}")
async def recalculate_stock_path_endpoint(ticker: str, request: dict | None = None):
    """Force refresh earnings date, prices, recalculate technical/quality metrics for path ticker."""
    sym = ticker.upper().strip()
    src = (request or {}).get("source", "user_recalculate")
    try:
        from earnings_engine.data.stock_rating import recalculate_stock_rating
        rating_res = await asyncio.to_thread(recalculate_stock_rating, sym, _settings, source=src)
        recalc_res = await asyncio.to_thread(recalculate_api.recalculate_ticker_metrics, sym, _settings)
        combined = {**recalc_res, **(rating_res or {})}
        combined["success"] = True
        combined["ticker"] = sym
        combined["fundamental"] = (rating_res or {}).get("fundamental")
        combined["technical"] = (rating_res or {}).get("technical")
        return combined
    except Exception as e:
        logger.exception("Error in recalculate_ticker_metrics: %s", e)
        raise HTTPException(status_code=500, detail=f"Recalculation error: {str(e)}")


@router.api_route("/api/v1/stock/{ticker}/live-week-hl", methods=["GET", "POST"])
async def get_live_week_hl_endpoint(ticker: str, earnings_date: str | None = Query(None)):
    """Calculate and return real-time post-earnings week move high/low statistics."""
    try:
        from earnings_engine.api.stock_api import get_live_week_hl
        res = await asyncio.to_thread(get_live_week_hl, ticker, earnings_date, _settings)
        if not res.get("success"):
            raise HTTPException(status_code=400, detail=res.get("error", "Failed to calculate live week high/low"))
        return res
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error in live_week_hl for %s: %s", ticker, e)
        raise HTTPException(status_code=500, detail=f"Failed to calculate live week high/low: {str(e)}")


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


@router.get("/api/v1/recalculate/audit")
async def get_recalculate_audit_all_endpoint(
    ticker: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    """Retrieve audit log wrapped with success boolean."""
    try:
        from earnings_engine.data.ticker_audit import get_audit_history
        entries = await asyncio.to_thread(
            get_audit_history,
            ticker=ticker,
            limit=limit,
            settings=_settings,
        )
        return {"success": True, "ticker": ticker, "entries": entries, "history": entries}
    except Exception as e:
        logger.exception("Error in recalculate_audit: %s", e)
        raise HTTPException(status_code=500, detail=f"Audit log error: {str(e)}")


@router.get("/api/v1/recalculate/audit/{ticker}")
async def get_recalculate_audit_path(ticker: str, limit: int = Query(50, ge=1, le=200)):
    """Retrieve audit log of recalculated fields for specific ticker wrapped with success boolean."""
    try:
        from earnings_engine.data.ticker_audit import get_audit_history
        entries = await asyncio.to_thread(
            get_audit_history,
            ticker=ticker,
            limit=limit,
            settings=_settings,
        )
        return {"success": True, "ticker": ticker, "entries": entries, "history": entries}
    except Exception as e:
        logger.exception("Error in get_recalculate_audit for %s: %s", ticker, e)
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
