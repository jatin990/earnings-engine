"""Dedicated stock intelligence, factor evaluation, recalculation, and audit log routes."""

from __future__ import annotations

import asyncio
import html
import urllib.parse
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


def clean_ticker_param(ticker: str | None) -> str:
    """Normalize a ticker string, decoding URL components and unescaping HTML entities like &amp;."""
    if not ticker:
        return ""
    unquoted = urllib.parse.unquote(str(ticker))
    unescaped = html.unescape(unquoted)
    return unescaped.strip().upper()


@router.get("/stock/{ticker:path}", tags=["UI"], response_class=HTMLResponse)
async def serve_stock_detail(ticker: str):
    """Serve the dedicated Stock Detail & AI Consensus Engine page."""
    sym = clean_ticker_param(ticker)
    try:
        env = get_template_env()
        template = env.get_template("hubs/stock/detail.html")
        html_content = template.render(ticker=sym)
        return HTMLResponse(html_content)
    except Exception as exc:
        return HTMLResponse(
            f"<html><body><h1>Stock Detail render error</h1><p>{exc}</p></body></html>",
            status_code=500,
        )


@router.get("/api/v1/stock/{ticker}/overview")
async def get_stock_overview_endpoint(ticker: str):
    """Return full stock overview including live quote, metrics, and EPS history."""
    sym = clean_ticker_param(ticker)
    try:
        return await asyncio.to_thread(stock_api.get_stock_overview, ticker=sym, settings=_settings)
    except Exception as e:
        logger.exception("Error in get_stock_overview for %s: %s", sym, e)
        raise HTTPException(status_code=500, detail=f"Error fetching stock overview: {str(e)}")


@router.get("/api/v1/stock/{ticker}/quote")
async def get_stock_quote_endpoint(ticker: str):
    """Fast endpoint returning live market quote, 52W levels, and profile metadata."""
    sym = clean_ticker_param(ticker)
    try:
        return await asyncio.to_thread(stock_api.get_stock_quote, ticker=sym, settings=_settings)
    except Exception as e:
        logger.exception("Error in get_stock_quote for %s: %s", sym, e)
        raise HTTPException(status_code=500, detail=f"Error fetching stock quote: {str(e)}")


@router.get("/api/v1/stock/{ticker}/technicals")
async def get_stock_technicals_endpoint(ticker: str):
    """Fast endpoint returning swing range channels, support/resistance, and moving averages."""
    sym = clean_ticker_param(ticker)
    try:
        return await asyncio.to_thread(stock_api.get_stock_technicals, ticker=sym, settings=_settings)
    except Exception as e:
        logger.exception("Error in get_stock_technicals for %s: %s", sym, e)
        raise HTTPException(status_code=500, detail=f"Error fetching technicals: {str(e)}")


@router.get("/api/v1/stock/{ticker}/earnings")
async def get_stock_earnings_endpoint(ticker: str):
    """Fast endpoint returning 12-quarter earnings history, EPS surprises, and week moves."""
    sym = clean_ticker_param(ticker)
    try:
        return await asyncio.to_thread(stock_api.get_stock_earnings, ticker=sym, settings=_settings)
    except Exception as e:
        logger.exception("Error in get_stock_earnings for %s: %s", sym, e)
        raise HTTPException(status_code=500, detail=f"Error fetching earnings: {str(e)}")


@router.get("/api/v1/stock/{ticker}/consensus")
async def get_stock_consensus_endpoint(ticker: str):
    """Fast endpoint returning multi-model AI consensus predictions."""
    sym = clean_ticker_param(ticker)
    try:
        return await asyncio.to_thread(stock_api.get_stock_consensus, ticker=sym, settings=_settings)
    except Exception as e:
        logger.exception("Error in get_stock_consensus for %s: %s", sym, e)
        raise HTTPException(status_code=500, detail=f"Error fetching consensus: {str(e)}")


@router.get("/api/v1/stock/{ticker}/kronos")
async def get_stock_kronos_endpoint(ticker: str):
    """Fast endpoint returning Kronos AI 14-day sequence trajectory forecast."""
    sym = clean_ticker_param(ticker)
    try:
        return await asyncio.to_thread(stock_api.get_stock_kronos, ticker=sym, settings=_settings)
    except Exception as e:
        logger.exception("Error in get_stock_kronos for %s: %s", sym, e)
        raise HTTPException(status_code=500, detail=f"Error fetching Kronos prediction: {str(e)}")


@router.get("/api/v1/stock/{ticker}/institutional")
async def get_stock_institutional_endpoint(ticker: str):
    """Fast endpoint returning institutional flows, shareholding trend, and top holdings."""
    sym = clean_ticker_param(ticker)
    try:
        return await asyncio.to_thread(stock_api.get_stock_institutional, ticker=sym, settings=_settings)
    except Exception as e:
        logger.exception("Error in get_stock_institutional for %s: %s", sym, e)
        raise HTTPException(status_code=500, detail=f"Error fetching institutional flows: {str(e)}")


@router.get("/api/v1/stock/{ticker}/catalysts")
async def get_stock_catalysts_endpoint(ticker: str):
    """Fast endpoint returning short-term news catalysts, impact scores, and sentiment."""
    sym = clean_ticker_param(ticker)
    try:
        return await asyncio.to_thread(stock_api.get_stock_catalysts, ticker=sym, settings=_settings)
    except Exception as e:
        logger.exception("Error in get_stock_catalysts for %s: %s", sym, e)
        raise HTTPException(status_code=500, detail=f"Error fetching news catalysts: {str(e)}")


@router.get("/api/v1/stock/{ticker}/factor-evaluation")
async def get_stock_factor_evaluation_endpoint(ticker: str):
    """Return factor evaluation score breakdown for a stock."""
    sym = clean_ticker_param(ticker)
    try:
        return await asyncio.to_thread(stock_api.get_stock_factor_evaluation, ticker=sym, settings=_settings)
    except Exception as e:
        logger.exception("Error in get_stock_factor_evaluation for %s: %s", sym, e)
        raise HTTPException(status_code=500, detail=f"Error fetching factor evaluation: {str(e)}")


@router.get("/api/v1/stock/{ticker}/notes")
async def get_stock_notes_endpoint(ticker: str, include_ai: bool = Query(False, description="Include the AI forward thesis (slow LLM inference). Defaults to false for a fast core note that the UI lazy-loads the AI thesis into.")):
    """Return consolidated AI intelligence notes for a stock."""
    sym = clean_ticker_param(ticker)
    try:
        return await asyncio.to_thread(stock_api.get_stock_intelligence_note, ticker=sym, settings=_settings, include_ai=include_ai)
    except Exception as e:
        logger.exception("Error in get_stock_notes for %s: %s", sym, e)
        raise HTTPException(status_code=500, detail=f"Error fetching notes: {str(e)}")


@router.get("/api/v1/stock/{ticker}/rating")
async def get_stock_rating_endpoint(ticker: str):
    """Retrieve the industry-benchmarked fundamental rating, technical score, and AI note."""
    sym = clean_ticker_param(ticker)
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
    sym = clean_ticker_param(ticker)
    try:
        res = await asyncio.to_thread(stock_api.refresh_stock_news, sym, _settings)
        if not res.get("success"):
            raise HTTPException(status_code=400, detail=res.get("error", "Failed to refresh news delta"))
        return res
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error in fetch_stock_news for %s: %s", sym, e)
        raise HTTPException(status_code=500, detail=f"Failed to refresh news: {str(e)}")


@router.get("/api/v1/stock/{ticker}/intelligence-note")
@router.post("/api/v1/stock/{ticker}/intelligence-note")
async def get_stock_intelligence_note_endpoint(
    ticker: str,
    model_name: str | None = Query(None, description="Preferred AI model"),
    provider: str | None = Query(None, description="Preferred provider"),
):
    """Return or generate an AI intelligence note for a stock."""
    sym = clean_ticker_param(ticker)
    try:
        return await asyncio.to_thread(
            stock_api.get_stock_intelligence_note,
            ticker=sym,
            model_name=model_name,
            provider=provider,
            settings=_settings,
        )
    except Exception as e:
        logger.exception("Error in stock intelligence note for %s: %s", sym, e)
        raise HTTPException(status_code=500, detail=f"Error with intelligence note: {str(e)}")


@router.post("/api/v1/stock/ratings/batch")
async def get_batch_stock_ratings(request: dict):
    """Compute and return ratings for a list of tickers."""
    tickers = request.get("tickers", [])
    try:
        results = {}
        for t in tickers:
            sym = clean_ticker_param(t)
            results[sym] = stock_api.calculate_stock_rating(ticker=sym, settings=_settings)
        return {"success": True, "ratings": results}
    except Exception as e:
        logger.exception("Error in batch stock ratings: %s", e)
        raise HTTPException(status_code=500, detail=f"Error computing batch ratings: {str(e)}")


@router.post("/api/v1/stock/{ticker}/calculate-eps")
@router.post("/api/v1/earnings/{ticker}/calculate-eps")
async def calculate_eps_endpoint(ticker: str, req: CalculateEpsRequest):
    """Calculate and derive EPS estimate, reported values, surprise %, and quality score."""
    sym = clean_ticker_param(ticker)
    try:
        return await asyncio.to_thread(
            stock_api.calculate_or_fetch_eps,
            ticker=sym,
            earnings_date=req.earnings_date,
            override_estimate=req.override_estimate,
            override_reported=req.override_reported,
            settings=_settings,
        )
    except Exception as e:
        logger.exception("Error in calculate_eps for %s: %s", sym, e)
        raise HTTPException(status_code=500, detail=f"Error calculating EPS: {str(e)}")


@router.post("/api/v1/stock/{ticker}/refresh-earnings-source")
@router.post("/api/v1/earnings/{ticker}/refresh-from-source")
async def refresh_earnings_source_endpoint(ticker: str):
    """Force re-fetch official earnings calendar and reported EPS from authentic sources (yfinance & NSE)."""
    sym = clean_ticker_param(ticker)
    try:
        from earnings_engine.data.earnings import refresh_earnings_from_source
        return await asyncio.to_thread(
            refresh_earnings_from_source,
            ticker=sym,
            settings=_settings,
        )
    except Exception as e:
        logger.exception("Error in refresh_earnings_source for %s: %s", sym, e)
        raise HTTPException(status_code=500, detail=f"Error refreshing earnings from source: {str(e)}")


@router.post("/api/v1/ticker/recalculate")
async def recalculate_ticker_metrics_endpoint(
    ticker: str = Query(..., description="Stock ticker symbol to refresh and recalculate"),
):
    """Force refresh earnings date, prices, recalculate technical/quality metrics, and log audit trail."""
    sym = clean_ticker_param(ticker)
    try:
        res = await asyncio.to_thread(
            recalculate_api.recalculate_ticker_metrics,
            ticker=sym,
            settings=_settings,
        )
        return res
    except Exception as e:
        logger.exception("Error in recalculate_ticker_metrics for %s: %s", sym, e)
        raise HTTPException(status_code=500, detail=f"Recalculation error: {str(e)}")


@router.post("/api/v1/stock/{ticker}/recalculate")
@router.post("/api/v1/recalculate/{ticker}")
async def recalculate_stock_path_endpoint(ticker: str, request: dict | None = None):
    """Force refresh earnings date, prices, recalculate technical/quality metrics for path ticker."""
    sym = clean_ticker_param(ticker)
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
        logger.exception("Error in recalculate_ticker_metrics for %s: %s", sym, e)
        raise HTTPException(status_code=500, detail=f"Recalculation error: {str(e)}")


@router.api_route("/api/v1/stock/{ticker}/live-week-hl", methods=["GET", "POST"])
async def get_live_week_hl_endpoint(ticker: str, earnings_date: str | None = Query(None)):
    """Calculate and return real-time post-earnings week move high/low statistics."""
    sym = clean_ticker_param(ticker)
    try:
        from earnings_engine.api.stock_api import get_live_week_hl
        res = await asyncio.to_thread(get_live_week_hl, sym, earnings_date, _settings)
        if not res.get("success"):
            raise HTTPException(status_code=400, detail=res.get("error", "Failed to calculate live week high/low"))
        return res
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error in live_week_hl for %s: %s", sym, e)
        raise HTTPException(status_code=500, detail=f"Failed to calculate live week high/low: {str(e)}")


@router.post("/api/v1/stock/{ticker}/refresh-prices")
@router.post("/api/v1/stock/{ticker}/hard-refresh-prices")
async def refresh_stock_prices_endpoint(
    ticker: str,
    hard: bool = Query(False, description="Whether to hard-refresh price history for the last 1 year"),
    from_year: int | None = Query(None, description="Starting year for historical prices (e.g. 2025)"),
):
    """Force download latest OHLCV price bars, market cap, and return updated quote & technicals.

    If hard=True or from_year is specified, fetches historical prices for the last 1 year (or specified from_year).
    """
    sym = clean_ticker_param(ticker)
    is_hard = hard or (from_year is not None)
    import pandas as pd
    default_hard_start = (pd.Timestamp.now() - pd.Timedelta(days=365)).strftime("%Y-%m-%d")
    start_dt = f"{from_year}-01-01" if from_year else (default_hard_start if is_hard else None)
    try:
        from earnings_engine.data.prices import ingest_prices, load_prices
        from earnings_engine.data.universe import ingest_market_caps
        await asyncio.to_thread(
            ingest_prices,
            [sym],
            settings=_settings,
            force=True,
            hard_refresh=is_hard,
            start_date=start_dt,
        )
        await asyncio.to_thread(ingest_market_caps, [sym], force=True, settings=_settings)
        overview = await asyncio.to_thread(stock_api.get_stock_overview, ticker=sym, settings=_settings)
        technicals = await asyncio.to_thread(stock_api.get_stock_technicals, ticker=sym, settings=_settings)

        df = await asyncio.to_thread(load_prices, sym, _settings)
        bar_count = len(df) if df is not None and not df.empty else 0
        min_date = df.index.min().strftime("%Y-%m-%d") if bar_count > 0 else "—"
        max_date = df.index.max().strftime("%Y-%m-%d") if bar_count > 0 else "—"

        msg = (
            f"Successfully hard-refreshed {bar_count} price bars from {min_date} to {max_date} for {sym}"
            if is_hard
            else f"Successfully fetched latest price bars and refreshed quote for {sym}"
        )
        return {
            "success": True,
            "ticker": sym,
            "message": msg,
            "hard_refresh": is_hard,
            "start_date": min_date,
            "end_date": max_date,
            "total_bars": bar_count,
            "overview": overview,
            "technicals": technicals,
        }
    except Exception as e:
        logger.exception("Error in refresh_stock_prices for %s: %s", sym, e)
        raise HTTPException(status_code=500, detail=f"Failed to refresh prices: {str(e)}")


@router.post("/api/v1/stock/{ticker}/refresh-institutional")
async def refresh_stock_institutional_endpoint(ticker: str):
    """Force re-derive and calculate institutional activity, fund actions, and amount-based score."""
    sym = clean_ticker_param(ticker)
    try:
        from earnings_engine.data.institutional_accumulation import get_stock_institutional_activity
        data = await asyncio.to_thread(get_stock_institutional_activity, ticker=sym, settings=_settings, force_refresh=True)
        return {
            "success": True,
            "ticker": sym,
            "message": f"Successfully recalculated institutional activity for {sym}",
            "data": data,
        }
    except Exception as e:
        logger.exception("Error in refresh_stock_institutional for %s: %s", sym, e)
        raise HTTPException(status_code=500, detail=f"Failed to refresh institutional data: {str(e)}")


@router.post("/api/v1/stock/{ticker}/recalculate-technicals")
async def recalculate_stock_technicals_endpoint(ticker: str):
    """Recalculate swing ranges, moving averages, and technical indicators for stock."""
    sym = clean_ticker_param(ticker)
    try:
        technicals = await asyncio.to_thread(stock_api.get_stock_technicals, ticker=sym, settings=_settings)
        return {
            "success": True,
            "ticker": sym,
            "message": f"Successfully recalculated technical structure for {sym}",
            "technicals": technicals,
        }
    except Exception as e:
        logger.exception("Error in recalculate_stock_technicals for %s: %s", sym, e)
        raise HTTPException(status_code=500, detail=f"Failed to recalculate technicals: {str(e)}")


@router.post("/api/v1/stock/{ticker}/run-kronos")
async def run_stock_kronos_endpoint(ticker: str):
    """Run on-demand Kronos AI 14-day sequence trajectory forecast."""
    sym = clean_ticker_param(ticker)
    try:
        from earnings_engine.kronos_predictor import predict_single_stock
        forecast = await asyncio.to_thread(predict_single_stock, symbol=sym, settings=_settings)
        return {
            "success": True,
            "ticker": sym,
            "message": f"Successfully generated Kronos 14-day AI forecast for {sym}",
            "kronos": forecast,
        }
    except Exception as e:
        logger.exception("Error running Kronos for %s: %s", sym, e)
        # Fallback to existing latest prediction if model generation encounters GPU/CUDA mismatch
        latest = await asyncio.to_thread(stock_api.get_stock_kronos, ticker=sym, settings=_settings)
        return {
            "success": latest.get("success", False),
            "ticker": sym,
            "warning": f"Live inference notice: {str(e)}. Returned latest cached forecast.",
            "kronos": latest.get("kronos"),
        }



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

