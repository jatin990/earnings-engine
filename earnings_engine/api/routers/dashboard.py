"""Dashboard aggregation, upcoming earnings results, and market analytics routes."""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse

from earnings_engine.api.dependencies import (
    _get_current_session,
    _require_master_role,
    _resolve_session,
    _settings,
    get_template_env,
)
from earnings_engine.api import dashboard_api
from earnings_engine.data.crypto import has_private_key
from earnings_engine.logging_utils import get_logger

logger = get_logger("earnings_engine.api.routers.dashboard")

router = APIRouter(tags=["Dashboard & Results Hub"])


@router.get("/dashboard", tags=["UI"], response_class=HTMLResponse)
async def serve_dashboard():
    """Serve the interactive dashboard page."""
    try:
        env = get_template_env()
        has_key = has_private_key()
        template = env.get_template("dashboard.html")
        html = template.render(has_diagnostics_key=has_key, has_tracker_key=has_key)
        return HTMLResponse(html)
    except Exception as exc:
        return HTMLResponse(
            f"<html><body><h1>Dashboard render error</h1><p>{exc}</p></body></html>",
            status_code=500,
        )


@router.get("/api/v1/dashboard/overview")
async def dashboard_overview():
    """Return aggregated KPI cards, market regime metrics, and summary data."""
    try:
        return await asyncio.to_thread(dashboard_api.get_results_report_components)
    except Exception as e:
        logger.exception("Error in dashboard_overview: %s", e)
        raise HTTPException(status_code=500, detail=f"Error fetching dashboard overview: {str(e)}")


@router.get("/api/v1/dashboard/results")
@router.get("/api/v1/upcoming-earnings")
async def dashboard_results(
    market: str = Query("ALL", description="Market universe (ALL, IN, NSE_ALL, US, etc.)"),
    days: int = Query(14, description="Look-ahead window in days", ge=1, le=90),
    past_days: int = Query(60, description="Past window in days for historical results", ge=0, le=180),
    start_date: str | None = Query(None, description="Optional anchor start date (YYYY-MM-DD)"),
    request: Request = None,
):
    """Return enriched upcoming and recent earnings results."""
    token = getattr(request.state, "cancellation_token", None) if request else None
    try:
        results = await asyncio.to_thread(
            dashboard_api.get_upcoming_results,
            days=days,
            market=market,
            past_days=past_days,
            start_date=start_date,
        )
        return results
    except asyncio.CancelledError:
        logger.info("Request /api/v1/dashboard/results cancelled by client.")
        return JSONResponse(status_code=499, content={"cancelled": True})
    except Exception as e:
        logger.exception("Error in dashboard_results: %s", e)
        raise HTTPException(status_code=500, detail=f"Error fetching upcoming results: {str(e)}")


@router.get("/api/v1/dashboard/results/month-summary")
async def dashboard_results_month_summary(
    market: str = Query("ALL", description="Market universe"),
    days: int = Query(90, description="Look-ahead window in days", ge=1, le=180),
    past_days: int = Query(60, description="Past lookback window in days", ge=0, le=180),
):
    """Aggregated month-by-month results summary count."""
    try:
        return await asyncio.to_thread(
            dashboard_api.get_month_filter_report_components,
            days=days,
            market=market,
            past_days=past_days,
        )
    except Exception as e:
        logger.exception("Error in month summary: %s", e)
        raise HTTPException(status_code=500, detail=f"Error fetching month summary: {str(e)}")


@router.get("/api/v1/dashboard/results/report")
async def dashboard_results_report(
    market: str = Query("ALL", description="Market universe"),
    days: int = Query(14, description="Look-ahead window in days", ge=1, le=90),
):
    """Retrieve rendered report components for upcoming results."""
    try:
        return await asyncio.to_thread(
            dashboard_api.get_results_report_components,
            days=days,
            market=market,
        )
    except Exception as e:
        logger.exception("Error in dashboard_results_report: %s", e)
        raise HTTPException(status_code=500, detail=f"Error generating report components: {str(e)}")


@router.get("/api/v1/dashboard/results/summarize")
async def dashboard_results_summarize(
    market: str = Query("ALL", description="Market universe"),
    days: int = Query(14, description="Look-ahead window in days", ge=1, le=90),
):
    """Summary metrics (total events, beat rates, top picks) for upcoming earnings window."""
    try:
        return await asyncio.to_thread(
            dashboard_api.get_event_dataset_summary,
        )
    except Exception as e:
        logger.exception("Error in dashboard_results_summarize: %s", e)
        raise HTTPException(status_code=500, detail=f"Error summarizing results: {str(e)}")


@router.get("/api/v1/dashboard/recent-results")
async def dashboard_recent_results(
    days: int = Query(30, description="Past window in days", ge=1, le=90),
    market: str = Query("NSE_ALL", description="Market universe"),
):
    """Past earnings results with price reaction returns."""
    try:
        return await asyncio.to_thread(
            dashboard_api.get_recent_results_api,
            market=market,
        )
    except Exception as e:
        logger.exception("Error in recent results: %s", e)
        raise HTTPException(status_code=500, detail=f"Error fetching recent results: {str(e)}")


@router.get("/api/v1/dashboard/recent-results/verdict")
async def dashboard_recent_results_verdict(
    ticker: str = Query(..., description="Stock ticker symbol"),
    earnings_date: str = Query(..., description="Earnings date (YYYY-MM-DD)"),
):
    """AI verdict and analysis notes for a specific past earnings announcement."""
    try:
        return await asyncio.to_thread(
            dashboard_api.get_recent_results_verdict_api,
            market=ticker,
        )
    except Exception as e:
        logger.exception("Error in recent results verdict: %s", e)
        raise HTTPException(status_code=500, detail=f"Error fetching recent results verdict: {str(e)}")


@router.get("/api/v1/dashboard/month-filter")
async def dashboard_month_filter(
    year: int | None = Query(None, description="Year (e.g. 2026)"),
    month: int | None = Query(None, description="Month (1-12)"),
    market: str | None = Query(None, description="Market universe"),
    days: int = Query(60, description="Window in days"),
    past_days: int = Query(60, description="Past lookback in days"),
    force_sync: bool = Query(False, description="Force live delta sync"),
    request: Request = None,
):
    """Monthly calendar results distribution with consensus badges."""
    try:
        effective_force_sync = force_sync
        if force_sync and request:
            session = getattr(request.state, "session", None) or _resolve_session(request)
            if session:
                role = session.get("role", "friend")
                scopes = set(session.get("scopes", []) + session.get("allowed_routes", []))
                if not (role in ("owner", "master") or "admin" in scopes or "*" in scopes):
                    effective_force_sync = False

        return await asyncio.to_thread(
            dashboard_api.get_month_filter_report_components,
            days=days,
            market=market,
            past_days=past_days,
            force_sync=effective_force_sync,
        )
    except Exception as e:
        logger.exception("Error in dashboard_month_filter: %s", e)
        raise HTTPException(status_code=500, detail=f"Error fetching month filter report: {str(e)}")


@router.post("/api/v1/dashboard/month-filter/sync")
async def dashboard_month_filter_sync(
    market: str | None = Query(None, description="Market universe"),
    request: Request = None,
):
    """Force present-day delta fetch and refresh precalculated Month Filter report."""
    _require_master_role(request)
    try:
        return await asyncio.to_thread(
            dashboard_api.get_month_filter_report_components,
            days=60,
            market=market,
            past_days=60,
            force_sync=True,
        )
    except Exception as e:
        logger.exception("Error in dashboard_month_filter_sync: %s", e)
        raise HTTPException(status_code=500, detail=f"Error syncing month filter report: {str(e)}")


@router.get("/api/v1/dashboard/data-coverage")
async def dashboard_data_coverage():
    """Retrieve coverage matrix for prices, earnings history, and fundamental market caps."""
    try:
        return await asyncio.to_thread(dashboard_api.get_data_coverage, market=None)
    except Exception as e:
        logger.exception("Error in data coverage: %s", e)
        raise HTTPException(status_code=500, detail=f"Error fetching data coverage: {str(e)}")


@router.get("/api/v1/dashboard/industries")
async def dashboard_industries(
    market: str | None = Query(None, description="Market universe"),
    days: int = Query(14, description="Look-ahead window in days", ge=1, le=90),
):
    """Sector returns and industry movements."""
    try:
        return await asyncio.to_thread(dashboard_api.get_industry_moves, market=market, lookback_days=days)
    except Exception as e:
        logger.exception("Error in dashboard_industries: %s", e)
        raise HTTPException(status_code=500, detail=f"Error fetching industry moves: {str(e)}")


@router.post("/api/v1/dashboard/industries/classify")
async def dashboard_industries_classify(request: dict | None = None):
    """Trigger background batch classification of unclassified stock industries."""
    limit = int((request or {}).get("limit", 50))
    try:
        return await asyncio.to_thread(dashboard_api.classify_industries_api, market=market)
    except Exception as e:
        logger.exception("Error in industry classify: %s", e)
        raise HTTPException(status_code=500, detail=f"Error classifying industries: {str(e)}")


@router.get("/api/v1/dashboard/patterns")
async def dashboard_patterns(market: str = Query("ALL", description="Market universe")):
    """Candlestick and chart patterns identified across universe."""
    try:
        return await asyncio.to_thread(dashboard_api.get_patterns_api, market=market)
    except Exception as e:
        logger.exception("Error in patterns: %s", e)
        raise HTTPException(status_code=500, detail=f"Error fetching patterns: {str(e)}")


@router.get("/api/v1/dashboard/buydip/today")
async def dashboard_buydip_today():
    """Companies declaring results today."""
    try:
        return dashboard_api.get_buydip_today_api()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching today results: {str(e)}")


@router.get("/api/v1/dashboard/buydip/yesterday")
async def dashboard_buydip_yesterday():
    """Yesterday's results with price action, sorted by biggest % declines."""
    try:
        return dashboard_api.get_buydip_yesterday_api()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching yesterday results: {str(e)}")


@router.post("/api/v1/dashboard/refresh")
async def dashboard_refresh(request: dict | None = None):
    """Trigger full dataset refresh in background."""
    market = (request or {}).get("market", "ALL")
    try:
        task_result = await asyncio.to_thread(dashboard_api.refresh_data, market=market)
        return {"success": True, "message": "Dataset refresh triggered", **task_result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error triggering refresh: {str(e)}")


@router.get("/api/v1/dashboard/refresh-status")
@router.get("/api/v1/dashboard/tab-refresh-status")
async def dashboard_refresh_status(task_id: str | None = Query(None)):
    """Check status of active background refresh task."""
    try:
        return dashboard_api.get_refresh_status(task_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error checking refresh status: {str(e)}")


@router.post("/api/v1/dashboard/predict/run")
async def dashboard_predict_run(request: dict | None = None):
    """Run LightGBM upcoming earnings prediction pipeline on demand."""
    market = (request or {}).get("market", "ALL")
    days = int((request or {}).get("days", 14))
    try:
        from earnings_engine.predict import predict_upcoming_from_db
        scored = await asyncio.to_thread(predict_upcoming_from_db, market=market, days=days, settings=_settings)
        return {"success": True, "scored_count": len(scored) if hasattr(scored, "__len__") else 0}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Prediction run failed: {str(e)}")


@router.get("/api/v1/market/pulse")
async def api_get_market_pulse(
    force_refresh: bool = Query(False, description="Force refresh cache"),
):
    """Retrieve full macro market pulse, fear & greed index, VIX, prediction, and sector heatmap."""
    try:
        from earnings_engine.data.market_pulse import get_market_pulse_data
        return await asyncio.to_thread(get_market_pulse_data, settings=_settings, force_refresh=force_refresh)
    except Exception as e:
        logger.exception("Error in api_get_market_pulse: %s", e)
        raise HTTPException(status_code=500, detail=f"Error retrieving market pulse: {e}")


@router.get("/api/v1/earnings/freshness")
async def get_earnings_freshness(
    watchlist: str | None = Query(None, description="Watchlist name or universe"),
    tickers: str | None = Query(None, description="Comma-separated list of tickers"),
):
    """Return data ingestion timestamps and cache freshness for a watchlist or market universe."""
    ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()] if tickers else None
    try:
        from earnings_engine.data.earnings import get_watchlist_earnings_freshness
        freshness = await asyncio.to_thread(
            get_watchlist_earnings_freshness,
            watchlist_name=watchlist,
            tickers=ticker_list,
            settings=_settings,
        )
        return {"success": True, **(freshness or {})}
    except Exception as e:
        logger.exception("Error in get_earnings_freshness: %s", e)
        raise HTTPException(status_code=500, detail=f"Error checking freshness: {str(e)}")


@router.get("/api/v1/dashboard/ai-forecast/latest")
async def dashboard_ai_forecast_latest():
    """Get the latest cached multi-modal AI prediction for all tracked stocks."""
    try:
        return await asyncio.to_thread(dashboard_api.get_latest_ai_forecasts_api)
    except Exception as e:
        logger.exception("Error in dashboard_ai_forecast_latest: %s", e)
        raise HTTPException(status_code=500, detail=f"Error fetching AI forecasts: {str(e)}")


@router.get("/api/v1/dashboard/ai-forecast/news/{ticker}")
async def dashboard_ai_forecast_news(
    ticker: str,
    limit: int = Query(10, description="Max number of news articles to fetch"),
):
    """Fetch real-time financial news, world event topics, and sentiment scores for a stock."""
    try:
        return await asyncio.to_thread(dashboard_api.get_ticker_news_api, ticker=ticker, limit=limit)
    except Exception as e:
        logger.exception("Error in dashboard_ai_forecast_news for %s: %s", ticker, e)
        raise HTTPException(status_code=500, detail=f"Error fetching news for {ticker}: {str(e)}")


@router.post("/api/v1/dashboard/ai-forecast/run")
async def dashboard_ai_forecast_run(request: dict):
    """Run on-demand multi-modal AI prediction synthesizing news, world events, volume, price action, and swing levels."""
    try:
        ticker = request.get("ticker")
        tickers = request.get("tickers")
        timeframe_days = int(request.get("timeframe_days", 14))
        force = bool(request.get("force", False))
        if ticker:
            return await asyncio.to_thread(
                dashboard_api.run_ai_forecast_for_ticker_api,
                ticker=ticker,
                timeframe_days=timeframe_days,
                force=force,
            )
        if tickers:
            return await asyncio.to_thread(
                dashboard_api.run_ai_forecast_batch_api,
                tickers=tickers,
                timeframe_days=timeframe_days,
                force=force,
            )
        raise HTTPException(status_code=400, detail="Either 'ticker' or 'tickers' must be provided.")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error running AI forecast: %s", e)
        raise HTTPException(status_code=500, detail=f"Error running AI forecast: {str(e)}")


@router.get("/api/v1/dashboard/kronos/benchmark-ohlcv/{ticker}")
async def dashboard_kronos_benchmark_ohlcv(
    ticker: str,
    run_at: str | None = Query(None, description="Optional specific run_at timestamp"),
    force_refresh: bool = Query(False, description="Force re-fetch of latest prices from providers"),
):
    """Benchmark the 14-day forecasted OHLCV series against realized daily market bars."""
    try:
        from urllib.parse import unquote
        ticker_decoded = unquote(ticker)
        run_at_decoded = unquote(run_at) if run_at else None
        return await asyncio.to_thread(
            dashboard_api.get_kronos_ohlcv_benchmark_api,
            ticker=ticker_decoded,
            run_at=run_at_decoded,
            force_refresh=force_refresh,
        )
    except Exception as e:
        logger.exception("Error in dashboard_kronos_benchmark_ohlcv for %s: %s", ticker, e)
        raise HTTPException(status_code=500, detail=f"Error benchmarking OHLCV series: {str(e)}")


@router.post("/api/v1/dashboard/results/summarize")
async def dashboard_results_summarize(request: dict):
    """Generate an LLM summary for the provided results rows."""
    items = request.get("items")
    try:
        if not items:
            days = request.get("days", 14)
            market = request.get("market")
            items = await asyncio.to_thread(dashboard_api.get_upcoming_results, days=days, market=market)
        if not items:
            return {"success": True, "summary": "No results to summarize.", "model": "none"}
        from earnings_engine.data.market_context import summarize_results_with_llm
        return await asyncio.to_thread(summarize_results_with_llm, items)
    except Exception as e:
        logger.exception("Error summarizing results: %s", e)
        raise HTTPException(status_code=500, detail=f"Error summarizing results: {str(e)}")


@router.post("/api/v1/earnings-radar/repeaters/batch-forecast")
async def batch_forecast_repeaters(
    universe: str | None = Query(None, description="Universe to batch forecast"),
    limit: int = Query(15, ge=1, le=40, description="Max stocks to process in batch"),
):
    """Run background batch AI Forward analysis for top quarter repeat candidates."""
    try:
        from earnings_engine.data import quarter_repeaters as repeaters_mod
        candidates = await asyncio.to_thread(
            repeaters_mod.scan_quarter_repeaters,
            settings=_settings,
            universe=universe,
            limit=limit,
        )
        return {"success": True, "count": len(candidates), "candidates": candidates}
    except Exception as e:
        logger.exception("Error in batch_forecast_repeaters: %s", e)
        raise HTTPException(status_code=500, detail=f"Error batch forecasting repeaters: {str(e)}")


@router.get("/api/v1/market-caps")
async def get_all_market_caps():
    """Get all cached market caps."""
    try:
        from earnings_engine.data.universe import load_all_market_caps
        return await asyncio.to_thread(load_all_market_caps, _settings)
    except Exception as e:
        logger.exception("Error fetching market caps: %s", e)
        raise HTTPException(status_code=500, detail=f"Error fetching market caps: {str(e)}")


@router.get("/api/v1/market-cap/{ticker}")
async def get_single_market_cap(ticker: str):
    """Get cached market cap for a single ticker."""
    try:
        from earnings_engine.data.universe import load_market_cap
        cap = await asyncio.to_thread(load_market_cap, ticker.upper().strip(), _settings)
        return {"ticker": ticker.upper().strip(), "market_cap": cap}
    except Exception as e:
        logger.exception("Error fetching market cap for %s: %s", ticker, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/v1/price-history/{ticker}")
async def get_price_history(
    ticker: str,
    start_date: str | None = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: str | None = Query(None, description="End date (YYYY-MM-DD)"),
    force_refresh: bool = Query(False, description="Force refresh from yfinance"),
):
    """Get OHLCV price history for a ticker."""
    try:
        from earnings_engine.data import prices as prices_mod
        df = await asyncio.to_thread(prices_mod.fetch_prices, ticker, _settings, force=force_refresh)
        if df.empty:
            return []
        if start_date:
            df = df[df.index >= start_date]
        if end_date:
            df = df[df.index <= end_date]
        records = []
        for dt, row in df.iterrows():
            records.append({
                "date": dt.strftime("%Y-%m-%d") if hasattr(dt, "strftime") else str(dt),
                "open": float(row.get("open", 0.0)),
                "high": float(row.get("high", 0.0)),
                "low": float(row.get("low", 0.0)),
                "close": float(row.get("close", 0.0)),
                "volume": int(row.get("volume", 0)),
            })
        return records
    except Exception as e:
        logger.exception("Error fetching price history for %s: %s", ticker, e)
        raise HTTPException(status_code=500, detail=f"Error fetching price history: {str(e)}")


@router.post("/api/v1/market/recent-additions/sync-watchlist")
async def api_sync_recent_addition_to_watchlist(
    ticker: str = Query(..., description="Stock ticker symbol (e.g. SHIPROCKET.NS)"),
    watchlist: str = Query("my_watchlist", description="Target watchlist name"),
):
    """One-click addition of a newly listed stock to a watchlist."""
    try:
        from earnings_engine.api.stock_api import sync_recent_additions_to_watchlist
        return await asyncio.to_thread(sync_recent_additions_to_watchlist, ticker=ticker, watchlist_name=watchlist, settings=_settings)
    except Exception as e:
        logger.exception("Error syncing recent addition to watchlist: %s", e)
        raise HTTPException(status_code=500, detail=f"Error adding ticker to watchlist: {str(e)}")


@router.post("/api/v1/earnings/refresh-watchlist")
async def refresh_watchlist_earnings(request: dict | None = None):
    """Refresh earnings calendar dates for a watchlist."""
    watchlist = (request or {}).get("watchlist") or (request or {}).get("name", "DEFAULT")
    tickers = (request or {}).get("tickers")
    try:
        from earnings_engine.data import earnings as earnings_mod
        return await asyncio.to_thread(
            earnings_mod.refresh_watchlist_earnings,
            watchlist_name=watchlist,
            tickers=tickers,
            settings=_settings,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error refreshing watchlist earnings: {str(e)}")


@router.post("/api/v1/dashboard/earnings/incremental")
async def run_incremental_earnings_ingest(request: dict | None = None):
    """Run fast incremental ingestion for missing earnings dates."""
    market = (request or {}).get("market", "NSE_ALL")
    try:
        return await asyncio.to_thread(dashboard_api.ingest_earnings_incremental_api, market=market)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Incremental ingestion failed: {str(e)}")


@router.get("/api/v1/earnings-history/{ticker}")
async def get_earnings_history_endpoint(ticker: str):
    """Return historical earnings dates and reported EPS for a ticker."""
    try:
        from earnings_engine.data.earnings import load_earnings
        df = await asyncio.to_thread(load_earnings, ticker, settings=_settings)
        rows = df.to_dict(orient="records") if not df.empty else []
        return {"success": True, "ticker": ticker, "count": len(rows), "earnings": rows}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error loading earnings history: {str(e)}")


@router.get("/api/v1/market-context/{ticker}")
async def get_market_context_endpoint(ticker: str):
    """Return 52W range position, week high/low around earnings for a ticker."""
    try:
        from earnings_engine.data.market_context import get_market_context_for_ticker
        ctx = await asyncio.to_thread(get_market_context_for_ticker, ticker, settings=_settings)
        return {"success": True, "ticker": ticker, **(ctx or {})}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching market context: {str(e)}")
