"""Dashboard aggregation, upcoming earnings results, and market analytics routes."""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
import math
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
import pandas as pd

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
    """Get dashboard overview: dataset summary + refresh status + watchlist."""
    try:
        from earnings_engine.api.dashboard_api import (
            get_event_dataset_summary,
            get_refresh_status,
            get_watchlist,
            get_universe_files,
        )
        dataset_summary = await asyncio.to_thread(get_event_dataset_summary)
        refresh_status = await asyncio.to_thread(get_refresh_status)
        watchlist = await asyncio.to_thread(get_watchlist)
        universe_files = await asyncio.to_thread(get_universe_files)
        return {
            "dataset": dataset_summary,
            "refresh_status": refresh_status,
            "watchlist": watchlist,
            "universe_files": universe_files,
        }
    except Exception as e:
        logger.exception("Error in dashboard_overview: %s", e)
        raise HTTPException(status_code=500, detail=f"Error fetching dashboard overview: {str(e)}")


@router.get("/api/v1/dashboard/results")
@router.get("/api/v1/upcoming-earnings")
async def dashboard_results(
    market: str = Query("ALL", description="Market universe (ALL, IN, NSE_ALL, US, etc.)"),
    tickers: str | None = Query(None, description="Comma-separated ticker list"),
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
    except (RuntimeError, asyncio.CancelledError) as e:
        if "shutdown" in str(e).lower() or isinstance(e, asyncio.CancelledError):
            logger.debug("[DASHBOARD] Month summary request interrupted during server shutdown.")
            return {"success": False, "months": [], "message": "Server shutting down"}
        logger.exception("Error in month summary: %s", e)
        raise HTTPException(status_code=500, detail=f"Error fetching month summary: {str(e)}")
    except Exception as e:
        logger.exception("Error in month summary: %s", e)
        raise HTTPException(status_code=500, detail=f"Error fetching month summary: {str(e)}")


@router.get("/api/v1/dashboard/results/report")
async def dashboard_results_report(
    days: int = Query(7, description="Look-ahead window in days", ge=0, le=180),
    past_days: int = Query(4, description="Look-back window in days", ge=0, le=180),
    market: str | None = Query(None, description="Market universe (IN, US, NSE_ALL, NSE_LARGE_CAP)"),
    start_date: str | None = Query(None, description="Explicit start date YYYY-MM-DD"),
):
    """Retrieve rendered report components for upcoming results."""
    try:
        return await asyncio.to_thread(
            dashboard_api.get_results_report_components,
            days=days,
            market=market,
            past_days=past_days,
            start_date=start_date,
        )
    except Exception as e:
        logger.exception("Error in dashboard_results_report: %s", e)
        raise HTTPException(status_code=500, detail=f"Error generating report components: {str(e)}")


@router.post("/api/v1/dashboard/results/sync-calendar")
async def dashboard_results_sync_calendar(
    market: str = Query("ALL", description="Market universe (ALL, IN, NSE_ALL, US, etc.)"),
    days: int = Query(60, description="Look-ahead calendar window in days", ge=1, le=180),
):
    """Force re-fetch of corporate earnings calendar announcements from official sources."""
    try:
        res = await asyncio.to_thread(
            dashboard_api.sync_results_calendar,
            days=days,
            market=market,
        )
        return res
    except Exception as e:
        logger.exception("Error in dashboard_results_sync_calendar: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to sync results calendar: {str(e)}")


@router.post("/api/v1/dashboard/results/recalculate-prices")
async def dashboard_results_recalculate_prices(
    market: str = Query("ALL", description="Market universe (ALL, IN, NSE_ALL, US, etc.)"),
    days: int = Query(60, description="Look-ahead window in days", ge=1, le=180),
    past_days: int = Query(60, description="Look-back window in days", ge=0, le=180),
):
    """Force re-fetch of price bars and recalculate technical support/resistance levels."""
    try:
        res = await asyncio.to_thread(
            dashboard_api.recalculate_results_prices,
            days=days,
            market=market,
        )
        return res
    except Exception as e:
        logger.exception("Error in dashboard_results_recalculate_prices: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to recalculate prices: {str(e)}")


@router.get("/api/v1/dashboard/results/refresh-price")
async def dashboard_results_refresh_price(
    ticker: str = Query(..., description="Stock ticker symbol"),
):
    """Refresh live market price snapshot for a single ticker in Results Ledger."""
    from earnings_engine.data import prices as prices_mod
    from earnings_engine.data.universe import load_market_cap

    sym = ticker.strip().upper()
    if not sym:
        raise HTTPException(status_code=400, detail="Ticker cannot be empty")

    try:
        quote = await asyncio.to_thread(prices_mod.fetch_live_quote, sym, force=True, settings=_settings)
        cur_price = quote.get("current_price")
        if cur_price is None:
            df = await asyncio.to_thread(prices_mod.load_prices, sym, _settings)
            if not df.empty and "close" in df.columns:
                closes = df["close"].dropna()
                if not closes.empty:
                    cur_price = float(closes.iloc[-1])

        mcap = quote.get("market_cap")
        if mcap is None:
            mcap = await asyncio.to_thread(load_market_cap, sym, _settings)

        formatted_price = f"{float(cur_price):,.2f}" if cur_price is not None else "—"
        if mcap is not None and float(mcap) > 0:
            formatted_mcap = f"{float(mcap) / 1e7:,.1f} Cr" if sym.endswith(".NS") else f"${float(mcap) / 1e9:,.2f}B"
        else:
            formatted_mcap = "—"

        return {
            "success": True,
            "ticker": sym,
            "metrics": {
                "current_price": formatted_price,
                "raw_price": round(float(cur_price), 2) if cur_price is not None else None,
                "market_cap": formatted_mcap,
                "raw_mcap": round(float(mcap), 0) if mcap is not None else None,
                "previous_close": quote.get("previous_close"),
                "day_change": quote.get("day_change"),
                "day_change_pct": quote.get("day_change_pct"),
                "week_52_high": quote.get("week_52_high"),
                "week_52_low": quote.get("week_52_low"),
            },
            "quote": quote,
        }
    except Exception as e:
        logger.exception("Error in dashboard_results_refresh_price for %s: %s", sym, e)
        raise HTTPException(status_code=500, detail=f"Failed to refresh price for {sym}: {str(e)}")


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
    correction_pct: float = Query(15.0, description="Min drop % from high"),
    drop_pct: float = Query(2.0, description="Reaction drop %"),
    start_date: str | None = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: str | None = Query(None, description="End date (YYYY-MM-DD)"),
):
    """Past earnings results with price reaction returns."""
    try:
        return await asyncio.to_thread(
            dashboard_api.get_recent_results_api,
            market=market,
            correction_pct=correction_pct,
            drop_pct=drop_pct,
            start_date=start_date,
            end_date=end_date,
        )
    except Exception as e:
        logger.exception("Error in recent results: %s", e)
        raise HTTPException(status_code=500, detail=f"Error fetching recent results: {str(e)}")


@router.get("/api/v1/dashboard/recent-results/verdict")
async def dashboard_recent_results_verdict(
    ticker: str | None = Query(None, description="Stock ticker symbol"),
    earnings_date: str | None = Query(None, description="Earnings date (YYYY-MM-DD)"),
    market: str | None = Query(None, description="Market universe or ticker"),
    start_date: str | None = Query(None, description="Start date"),
    end_date: str | None = Query(None, description="End date"),
):
    """AI verdict and analysis notes for a specific past earnings announcement."""
    target_ticker = ticker or market
    try:
        return await asyncio.to_thread(
            dashboard_api.get_recent_results_verdict_api,
            market=target_ticker,
            start_date=start_date,
            end_date=end_date,
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
async def dashboard_data_coverage(
    market: str | None = Query("ALL", description="Market universe"),
):
    """Retrieve coverage matrix for prices, earnings history, and fundamental market caps."""
    try:
        return await asyncio.to_thread(dashboard_api.get_data_coverage, market=market)
    except Exception as e:
        logger.exception("Error in data coverage: %s", e)
        raise HTTPException(status_code=500, detail=f"Error fetching data coverage: {str(e)}")


@router.get("/api/v1/dashboard/industries")
async def dashboard_industries(
    market: str | None = Query(None, description="Market universe"),
    days: int = Query(14, description="Look-ahead window in days", ge=1, le=90),
    lookback_days: int | None = Query(None, description="Lookback window alias for days"),
):
    """Sector returns and industry movements."""
    effective_days = lookback_days or days
    try:
        return await asyncio.to_thread(dashboard_api.get_industry_moves, market=market, lookback_days=effective_days)
    except Exception as e:
        logger.exception("Error in dashboard_industries: %s", e)
        raise HTTPException(status_code=500, detail=f"Error fetching industry moves: {str(e)}")


@router.post("/api/v1/dashboard/industries/classify")
async def dashboard_industries_classify(request: dict | None = None):
    """Trigger background batch classification of unclassified stock industries."""
    limit = int((request or {}).get("limit", 50))
    market = (request or {}).get("market")
    try:
        return await asyncio.to_thread(dashboard_api.classify_industries_api, limit=limit, market=market)
    except Exception as e:
        logger.exception("Error in industry classify: %s", e)
        raise HTTPException(status_code=500, detail=f"Error classifying industries: {str(e)}")


@router.get("/api/v1/dashboard/patterns")
async def dashboard_patterns(
    market: str = Query("ALL", description="Market universe"),
    start_date: str | None = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: str | None = Query(None, description="End date (YYYY-MM-DD)"),
):
    """Candlestick and chart patterns identified across universe."""
    try:
        return await asyncio.to_thread(dashboard_api.get_patterns_api, market=market, start_date=start_date, end_date=end_date)
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
@router.get("/api/v1/dashboard/market-pulse")
@router.get("/api/v1/market-pulse")
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


@router.get("/api/v1/market-pulse/indices")
@router.get("/api/v1/indices/quotes")
async def api_get_indices_quotes(
    force_refresh: bool = Query(False, description="Force refresh cache"),
):
    """Retrieve batch price quotes and 1D/7D/30D returns for major benchmark and sectoral indices."""
    try:
        from earnings_engine.data.market_pulse import compute_indices_quotes
        indices = await asyncio.to_thread(compute_indices_quotes, settings=_settings, force_refresh=force_refresh)
        return {"success": True, "count": len(indices), "indices": indices}
    except Exception as e:
        logger.exception("Error in api_get_indices_quotes: %s", e)
        raise HTTPException(status_code=500, detail=f"Error retrieving index quotes: {e}")


@router.get("/api/v1/market-pulse/sectors")
async def api_get_sector_heatmap(
    force_refresh: bool = Query(False, description="Force refresh cache"),
):
    """Retrieve Sectoral Heatmap using authoritative NSE index prices with constituent breadth."""
    try:
        from earnings_engine.data.market_pulse import compute_sector_heatmap
        sectors = await asyncio.to_thread(compute_sector_heatmap, settings=_settings, force_refresh=force_refresh)
        return {"success": True, "count": len(sectors), "sectors": sectors}
    except Exception as e:
        logger.exception("Error in api_get_sector_heatmap: %s", e)
        raise HTTPException(status_code=500, detail=f"Error retrieving sector heatmap: {e}")


@router.get("/api/v1/market-pulse/liquidity")
@router.get("/api/v1/market-pulse/institutional-flows")
@router.get("/api/v1/liquidity/overview")
async def api_get_net_cash_liquidity(
    force_refresh: bool = Query(False, description="Force refresh cache"),
):
    """Retrieve Net Cash Liquidity, FII vs DII breakdown, 7D/30D cumulative flows and regime."""
    try:
        from earnings_engine.data.market_pulse import compute_net_cash_liquidity
        liquidity = await asyncio.to_thread(compute_net_cash_liquidity, settings=_settings, force_refresh=force_refresh)
        return {"success": True, "liquidity": liquidity}
    except Exception as e:
        logger.exception("Error in api_get_net_cash_liquidity: %s", e)
        raise HTTPException(status_code=500, detail=f"Error retrieving liquidity data: {e}")


@router.get("/api/v1/market-pulse/sentiment")
@router.get("/api/v1/market_pulse/sentiment")
async def api_get_market_sentiment_matrix(
    force_refresh: bool = Query(False, description="Force refresh cache"),
):
    """Retrieve Fear & Greed score, Market Breadth, Volatility Matrix, and 30D macro time-series."""
    try:
        from earnings_engine.data.market_pulse import compute_market_sentiment_matrix
        sentiment = await asyncio.to_thread(compute_market_sentiment_matrix, settings=_settings, force_refresh=force_refresh)
        return {"success": True, "sentiment": sentiment}
    except Exception as e:
        logger.exception("Error in api_get_market_sentiment_matrix: %s", e)
        raise HTTPException(status_code=500, detail=f"Error retrieving market sentiment: {e}")


@router.get("/api/v1/market-pulse/participant-oi")
@router.get("/api/v1/market_pulse/participant_oi")
async def api_get_participant_oi(
    force_refresh: bool = Query(False, description="Force refresh cache"),
):
    """Retrieve Participant Derivatives Open Interest (OI) & Long/Short positioning breakdown."""
    try:
        from earnings_engine.data.market_pulse import compute_participant_oi_matrix
        oi_data = await asyncio.to_thread(compute_participant_oi_matrix, settings=_settings, force_refresh=force_refresh)
        return {"success": True, "participant_oi": oi_data}
    except Exception as e:
        logger.exception("Error in api_get_participant_oi: %s", e)
        raise HTTPException(status_code=500, detail=f"Error retrieving participant OI data: {e}")


@router.get("/api/v1/market-pulse/playbook")
@router.get("/api/v1/market_pulse/playbook")
@router.get("/api/v1/market/playbook")
async def api_get_market_playbook(
    force_refresh: bool = Query(False, description="Force refresh cache"),
):
    """Retrieve Algorithmic Next-Day Actionable Market Playbook & Volatility Corridor."""
    try:
        from earnings_engine.data.market_pulse import get_market_pulse_data
        pulse = await asyncio.to_thread(get_market_pulse_data, settings=_settings, force_refresh=force_refresh)
        return {
            "success": True,
            "playbook": pulse.get("next_day_playbook", {}),
            "participant_oi": pulse.get("participant_oi", {}),
            "volatility": pulse.get("volatility", {}),
        }
    except Exception as e:
        logger.exception("Error in api_get_market_playbook: %s", e)
        raise HTTPException(status_code=500, detail=f"Error retrieving market playbook: {e}")


@router.get("/api/v1/market-pulse/glossary")
@router.get("/api/v1/market_pulse/glossary")
@router.get("/api/v1/market/glossary")
async def api_get_metric_glossary():
    """Retrieve structured Metric Glossary & Educational Trading Guide."""
    try:
        from earnings_engine.data.market_pulse import get_metric_glossary
        glossary = await asyncio.to_thread(get_metric_glossary)
        return {"success": True, "glossary": glossary}
    except Exception as e:
        logger.exception("Error in api_get_metric_glossary: %s", e)
        raise HTTPException(status_code=500, detail=f"Error retrieving metric glossary: {e}")
@router.get("/api/v1/dashboard/market-macro")
async def api_get_market_macro():
    """Retrieve concise market sentiment and volatility regime summary."""
    try:
        from earnings_engine.data.cross_strategy import get_market_macro_summary
        return await asyncio.to_thread(get_market_macro_summary, settings=_settings)
    except Exception as e:
        logger.exception("Error in api_get_market_macro: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/v1/dashboard/cross-intelligence/{ticker}")
async def api_get_stock_cross_intelligence(ticker: str):
    """Retrieve cross-module synergy (Breakout + Swing + AI Consensus + News) for a stock."""
    try:
        from earnings_engine.data.cross_strategy import get_stock_confluence
        return await asyncio.to_thread(get_stock_confluence, ticker=ticker, settings=_settings)
    except Exception as e:
        logger.exception("Error in api_get_stock_cross_intelligence for %s: %s", ticker, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/v1/dashboard/confluence")
@router.get("/api/v1/breakout-radar/confluence")
@router.get("/api/v1/confluence-radar")
async def api_get_confluence_setups(
    min_level: int = Query(1, ge=0, le=3, description="Minimum confluence tier (0: All, 1: Single, 2: Dual, 3: Triple)"),
    limit: int = Query(30, ge=1, le=100),
):
    """Retrieve top cross-module confluence setups across all active scanners from pre-computed scheduled database."""
    try:
        from earnings_engine.data.cross_strategy import load_confluence_radar_from_db
        confluence_list = await asyncio.to_thread(
            load_confluence_radar_from_db,
            min_level=min_level,
            limit=limit,
            settings=_settings,
        )
        return {
            "success": True,
            "count": len(confluence_list),
            "setups": confluence_list,
        }
    except Exception as e:
        logger.exception("Error in api_get_confluence_setups: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


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
        swing_support = request.get("swing_support")
        swing_resistance = request.get("swing_resistance")
        watchlist = request.get("watchlist", "ALL")
        if ticker:
            return await asyncio.to_thread(
                dashboard_api.run_ai_forecast_api,
                ticker=ticker,
                swing_support=swing_support,
                swing_resistance=swing_resistance,
                timeframe_days=timeframe_days,
                force=force,
            )
        if tickers:
            return await asyncio.to_thread(
                dashboard_api.run_ai_forecasts_batch_api,
                tickers=tickers,
                watchlist=watchlist,
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
async def get_single_market_cap(
    ticker: str,
    force_refresh: bool = Query(False, description="Force refresh from yfinance"),
):
    """Get cached market cap for a single ticker."""
    try:
        from earnings_engine.data.universe import load_market_cap
        cap = await asyncio.to_thread(load_market_cap, ticker.upper().strip(), _settings, force_refresh=force_refresh)
        return {"ticker": ticker.upper().strip(), "market_cap": cap}
    except Exception as e:
        logger.exception("Error fetching market cap for %s: %s", ticker, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/v1/price-history/{ticker}")
@router.get("/api/v1/stock/{ticker}/price-history")
async def get_price_history(
    ticker: str,
    start_date: str | None = Query(default=None, description="Start date (YYYY-MM-DD)"),
    end_date: str | None = Query(default=None, description="End date (YYYY-MM-DD)"),
    force_refresh: bool = Query(default=False, description="Force refresh from yfinance"),
):
    """Get OHLCV price history for a ticker with strict NaN and zero-value safety."""
    try:
        from urllib.parse import unquote
        import math
        clean_ticker = unquote(ticker).strip()
        force_val = force_refresh if isinstance(force_refresh, bool) else False
        from earnings_engine.data import prices as prices_mod
        df = await asyncio.to_thread(prices_mod.fetch_prices, clean_ticker, _settings, force=force_val)
        if df is None or df.empty:
            return []
        if isinstance(start_date, str) and start_date.strip():
            df = df[df.index >= start_date.strip()]
        if isinstance(end_date, str) and end_date.strip():
            df = df[df.index <= end_date.strip()]

        records = []
        for dt, row in df.iterrows():
            try:
                c_raw = row.get("close")
                if c_raw is None or pd.isna(c_raw):
                    continue
                c = float(c_raw)
                if math.isnan(c) or math.isinf(c) or c <= 0:
                    continue

                o_raw = row.get("open")
                o = float(o_raw) if o_raw is not None and not pd.isna(o_raw) else c
                if math.isnan(o) or math.isinf(o) or o <= 0:
                    o = c

                h_raw = row.get("high")
                h = float(h_raw) if h_raw is not None and not pd.isna(h_raw) else max(o, c)
                if math.isnan(h) or math.isinf(h) or h <= 0:
                    h = max(o, c)

                l_raw = row.get("low")
                l = float(l_raw) if l_raw is not None and not pd.isna(l_raw) else min(o, c)
                if math.isnan(l) or math.isinf(l) or l <= 0:
                    l = min(o, c)

                v_raw = row.get("volume", 0)
                if v_raw is not None and not pd.isna(v_raw):
                    try:
                        v_flt = float(v_raw)
                        v = int(v_flt) if not (math.isnan(v_flt) or math.isinf(v_flt)) else 0
                    except (ValueError, TypeError):
                        v = 0
                else:
                    v = 0

                records.append({
                    "date": dt.strftime("%Y-%m-%d") if hasattr(dt, "strftime") else str(dt),
                    "open": round(o, 2),
                    "high": round(h, 2),
                    "low": round(l, 2),
                    "close": round(c, 2),
                    "volume": max(0, v),
                })
            except Exception:
                continue
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
async def get_earnings_history_endpoint(
    ticker: str,
    force_refresh: bool = Query(False, description="Force refresh from source"),
):
    """Return historical earnings dates and reported EPS for a ticker."""
    try:
        from earnings_engine.data.earnings import load_earnings
        df = await asyncio.to_thread(load_earnings, ticker, settings=_settings, force=force_refresh)
        rows = df.to_dict(orient="records") if not df.empty else []
        return {"success": True, "ticker": ticker, "count": len(rows), "earnings": rows}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error loading earnings history: {str(e)}")


@router.get("/api/v1/market-context/{ticker}")
async def get_market_context_endpoint(
    ticker: str,
    live: bool = Query(True, description="Fetch live price and bounds"),
):
    """Return 52W range position, week high/low around earnings for a ticker."""
    try:
        from earnings_engine.data.market_context import get_market_context_for_ticker
        ctx = await asyncio.to_thread(get_market_context_for_ticker, ticker, settings=_settings, live=live)
        return {"success": True, "ticker": ticker, **(ctx or {})}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching market context: {str(e)}")
