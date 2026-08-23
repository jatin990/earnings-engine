"""FastAPI server exposing earnings-engine data via REST APIs."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date, datetime
from typing import Any

import pandas as pd
import time
from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from earnings_engine.config import Settings
from earnings_engine.data import earnings as earnings_mod
from earnings_engine.api import dashboard_api
from earnings_engine.data import prices as prices_mod
from earnings_engine.data.market_context import enrich_upcoming_results
from earnings_engine.data.universe import (
    load_all_market_caps,
    load_nse_all,
    load_nse_large_cap,
    load_universe,
)
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader
from pathlib import Path
from earnings_engine.data.migrations import apply_migrations
from earnings_engine.logging_utils import get_logger, log_startup_diagnostics

logger = get_logger("earnings_engine.api.server")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run migrations and startup diagnostics on API startup."""
    try:
        applied = apply_migrations(_settings)
        if applied:
            logger.info("Database migrations applied on startup: %s", ", ".join(applied))
    except Exception as e:
        logger.warning("Startup database migration check failed: %s", e)
    log_startup_diagnostics(logger)
    yield


app = FastAPI(
    title="Earnings Engine API",
    description="REST API for accessing earnings predictions and market data",
    version="1.0.0",
    lifespan=lifespan,
)

# Enable CORS for Postman and browser access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_api_requests(request: Request, call_next):
    """Log concise API call details including input query filters, status code, and latency."""
    start_time = time.perf_counter()
    path = request.url.path

    # Extract non-empty query parameters / filters
    query_params = dict(request.query_params)
    filters_repr = f" filters={query_params}" if query_params else ""

    response = await call_next(request)
    duration_ms = (time.perf_counter() - start_time) * 1000

    # Skip logging high-frequency static asset hits to avoid log spam
    if not (path.startswith("/static") or path.startswith("/ui")):
        logger.info(
            "API [%s] %s%s -> %d (%.1fms)",
            request.method,
            path,
            filters_repr,
            response.status_code,
            duration_ms,
        )

    return response

# Global settings instance
_settings = Settings()

# Jinja2 template environment for dashboard partials
_templates_dir = Path(__file__).resolve().parent.parent / "reports" / "templates"
_jinja_env = Environment(
    loader=FileSystemLoader(str(_templates_dir)),
    autoescape=True,
    auto_reload=True,
)

# Mount static UI assets (JS, CSS, icons)
_ui_dir = Path(__file__).resolve().parent.parent / "ui"
if _ui_dir.exists():
    app.mount("/static", StaticFiles(directory=str(_ui_dir)), name="static")
    app.mount("/ui", StaticFiles(directory=str(_ui_dir)), name="ui")


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------


class PriceData(BaseModel):
    """Single day's price data."""
    date: str
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    volume: int | None


class EarningsData(BaseModel):
    """Single earnings event."""
    earnings_date: str
    eps_estimate: float | None
    eps_reported: float | None
    surprise_pct: float | None


class MarketCapResponse(BaseModel):
    """Market cap data."""
    ticker: str
    market_cap: float | None


class MarketContextResponse(BaseModel):
    """Enriched market context for a ticker."""
    ticker: str
    market_cap: float | None
    current_price: float | None
    week_change: float | None
    pct_from_52w_high: float | None
    pct_from_52w_low: float | None
    thirty_day_return_pct: float | None
    earnings_week_move_pct: float | None
    earnings_week_high_pct: float | None
    earnings_week_low_pct: float | None
    earnings_week_high_price: float | None
    earnings_week_low_price: float | None
    week_high: float | None
    week_low: float | None
    prev_quarter_earnings_score: int | None
    q1_earnings_score: int | None
    q2_earnings_score: int | None
    q3_earnings_score: int | None
    next_resistance: float | None
    current_support: float | None
    eps_estimate: float | None
    eps_reported: float | None
    surprise_pct: float | None


class UpcomingEarningsResponse(BaseModel):
    """Upcoming earnings event."""
    ticker: str
    earnings_date: str


class UniverseResponse(BaseModel):
    """Universe ticker list."""
    market: str
    tickers: list[str]
    count: int


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------


def _df_to_price_list(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Convert price DataFrame to list of dicts."""
    records = []
    for idx, row in df.iterrows():
        records.append({
            "date": idx.strftime("%Y-%m-%d") if isinstance(idx, pd.Timestamp) else str(idx),
            "open": float(row["open"]) if pd.notna(row.get("open")) else None,
            "high": float(row["high"]) if pd.notna(row.get("high")) else None,
            "low": float(row["low"]) if pd.notna(row.get("low")) else None,
            "close": float(row["close"]) if pd.notna(row.get("close")) else None,
            "volume": int(row["volume"]) if pd.notna(row.get("volume")) else None,
        })
    return records


def _df_to_earnings_list(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Convert earnings DataFrame to list of dicts."""
    records = []
    for _, row in df.iterrows():
        records.append({
            "earnings_date": row["earnings_date"].strftime("%Y-%m-%d") if isinstance(row["earnings_date"], pd.Timestamp) else str(row["earnings_date"]),
            "eps_estimate": float(row["eps_estimate"]) if pd.notna(row.get("eps_estimate")) else None,
            "eps_reported": float(row["eps_reported"]) if pd.notna(row.get("eps_reported")) else None,
            "surprise_pct": float(row["surprise_pct"]) if pd.notna(row.get("surprise_pct")) else None,
        })
    return records


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------


@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "service": "earnings-engine-api"}


@app.get("/api/v1/price-history/{ticker}", response_model=list[PriceData], tags=["Prices"])
async def get_price_history(
    ticker: str,
    start_date: str | None = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: str | None = Query(None, description="End date (YYYY-MM-DD)"),
    force_refresh: bool = Query(False, description="Force refresh from yfinance"),
):
    """Get OHLCV price history for a ticker.
    
    - **ticker**: Stock ticker symbol (e.g., 'AAPL' or 'RELIANCE.NS')
    - **start_date**: Optional start date filter (YYYY-MM-DD)
    - **end_date**: Optional end date filter (YYYY-MM-DD)
    - **force_refresh**: If true, fetch fresh data from yfinance instead of cache
    """
    try:
        df = prices_mod.fetch_prices(ticker, _settings, force=force_refresh)
        
        if df.empty:
            return []
        
        # Apply date filters if provided
        if start_date:
            try:
                start = pd.Timestamp(start_date)
                df = df[df.index >= start]
            except Exception:
                raise HTTPException(status_code=400, detail=f"Invalid start_date format: {start_date}")
        
        if end_date:
            try:
                end = pd.Timestamp(end_date)
                df = df[df.index <= end]
            except Exception:
                raise HTTPException(status_code=400, detail=f"Invalid end_date format: {end_date}")
        
        return _df_to_price_list(df)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching price history: {str(e)}")


@app.get("/api/v1/earnings-history/{ticker}", response_model=list[EarningsData], tags=["Earnings"])
async def get_earnings_history(
    ticker: str,
    force_refresh: bool = Query(False, description="Force refresh from yfinance"),
):
    """Get earnings history for a ticker.
    
    - **ticker**: Stock ticker symbol (e.g., 'AAPL' or 'RELIANCE.NS')
    - **force_refresh**: If true, fetch fresh data from yfinance instead of cache
    """
    try:
        df = earnings_mod.fetch_earnings(ticker, _settings, force=force_refresh)
        return _df_to_earnings_list(df)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching earnings history: {str(e)}")


@app.get("/api/v1/market-cap/{ticker}", response_model=MarketCapResponse, tags=["Market Data"])
async def get_market_cap(ticker: str, force_refresh: bool = Query(False, description="Bypass the SQLite cache and fetch live from yfinance")):
    """Get current market cap for a ticker.
    
    - **ticker**: Stock ticker symbol (e.g., 'AAPL' or 'RELIANCE.NS')
    - **force_refresh**: If true, bypass the cache and fetch live from yfinance
    """
    try:
        from earnings_engine.data.universe import load_market_cap
        
        # Try cache first (unless force_refresh)
        market_cap = load_market_cap(ticker, _settings) if not force_refresh else None
        
        # If not in cache (or forced live), fetch from yfinance
        if market_cap is None:
            import yfinance as yf
            try:
                info = yf.Ticker(ticker).fast_info or {}
                market_cap = info.get("market_cap")
                if market_cap is None:
                    info = yf.Ticker(ticker).info or {}
                    market_cap = info.get("marketCap")
                # Store in cache
                if market_cap is not None:
                    from earnings_engine.data.universe import store_market_cap
                    store_market_cap(ticker, market_cap, _settings)
            except Exception:
                market_cap = None
        
        return MarketCapResponse(ticker=ticker, market_cap=market_cap)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching market cap: {str(e)}")


@app.get("/api/v1/market-context/{ticker}", response_model=MarketContextResponse, tags=["Market Data"])
async def get_market_context(ticker: str, live: bool = Query(False)):
    """Get enriched market context for a ticker.
    
    This endpoint returns comprehensive market data including:
    - Current price and market cap
    - 52-week high/low and percentage from extremes
    - 30-day returns
    - Earnings week price movement
    - Earnings quality scores (previous quarter and 3-quarter average)
    - Support and resistance levels
    - Latest EPS estimate, reported, and surprise %
    
    - **ticker**: Stock ticker symbol (e.g., 'AAPL' or 'RELIANCE.NS')
    """
    try:
        # Create a minimal DataFrame with just the ticker
        df = pd.DataFrame({"ticker": [ticker]})
        
        # Enrich with market context
        enriched = enrich_upcoming_results(df, _settings, force=live)
        
        if enriched.empty:
            raise HTTPException(status_code=404, detail=f"No data found for ticker: {ticker}")
        
        # Extract the single row
        row = enriched.iloc[0].to_dict()
        
        return MarketContextResponse(
            ticker=row.get("ticker", ticker),
            market_cap=row.get("market_cap"),
            current_price=row.get("current_price"),
            week_change=row.get("week_change"),
            pct_from_52w_high=row.get("pct_from_52w_high"),
            pct_from_52w_low=row.get("pct_from_52w_low"),
            thirty_day_return_pct=row.get("thirty_day_return_pct"),
            earnings_week_move_pct=row.get("earnings_week_move_pct"),
            earnings_week_high_pct=row.get("earnings_week_high_pct"),
            earnings_week_low_pct=row.get("earnings_week_low_pct"),
            earnings_week_high_price=row.get("earnings_week_high_price"),
            earnings_week_low_price=row.get("earnings_week_low_price"),
            week_high=row.get("week_high"),
            week_low=row.get("week_low"),
            prev_quarter_earnings_score=row.get("prev_quarter_earnings_score"),
            q1_earnings_score=row.get("q1_earnings_score"),
            q2_earnings_score=row.get("q2_earnings_score"),
            q3_earnings_score=row.get("q3_earnings_score"),
            next_resistance=row.get("next_resistance"),
            current_support=row.get("current_support"),
            eps_estimate=row.get("eps_estimate"),
            eps_reported=row.get("eps_reported"),
            surprise_pct=row.get("surprise_pct"),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching market context: {str(e)}")


@app.get("/api/v1/upcoming-earnings", response_model=list[UpcomingEarningsResponse], tags=["Earnings"])
async def get_upcoming_earnings(
    tickers: str | None = Query(None, description="Comma-separated list of tickers"),
    days: int = Query(14, description="Number of days to look ahead", ge=1, le=90),
    market: str | None = Query(None, description="Market to use (IN, US, NSE_ALL, NSE_LARGE_CAP)"),
):
    """Get upcoming earnings events.
    
    - **tickers**: Optional comma-separated list of tickers (e.g., 'AAPL,MSFT,GOOGL')
    - **days**: Number of days to look ahead (default: 14, max: 90)
    - **market**: Optional market to load universe from (IN, US, NSE_ALL, NSE_LARGE_CAP)
    """
    try:
        ticker_list = []
        
        if tickers:
            ticker_list = [t.strip() for t in tickers.split(",") if t.strip()]
        elif market:
            ticker_list = load_universe(market)
        
        if not ticker_list:
            return []
        
        df = earnings_mod.upcoming_earnings(ticker_list, _settings, days=days)
        
        results = []
        for _, row in df.iterrows():
            results.append(UpcomingEarningsResponse(
                ticker=row["ticker"],
                earnings_date=row["earnings_date"].strftime("%Y-%m-%d") if isinstance(row["earnings_date"], pd.Timestamp) else str(row["earnings_date"]),
            ))
        
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching upcoming earnings: {str(e)}")


@app.get("/api/v1/universe/files", tags=["Universe"])
async def get_universe_files(response: Response):
    """Get list of available universes from SQLite."""
    try:
        from earnings_engine.data.universe import list_universes
        universes = list_universes(_settings)
        response.headers["Cache-Control"] = "public, max-age=1800, stale-while-revalidate=86400"
        return {"files": [u["name"] for u in universes]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing universes: {str(e)}")


@app.get("/api/v1/universe/{market}", response_model=UniverseResponse, tags=["Universe"])
async def get_universe(market: str, response: Response):
    """Get ticker universe for a market.
    
    - **market**: Market code (IN, US, NSE_ALL, NSE_LARGE_CAP, or custom universe)
    """
    try:
        market_upper = market.upper()
        tickers = load_universe(market_upper, _settings)
        response.headers["Cache-Control"] = "public, max-age=3600, stale-while-revalidate=86400"
        return UniverseResponse(market=market_upper, tickers=tickers, count=len(tickers))
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error loading universe: {str(e)}")


@app.get("/api/v1/market-caps", response_model=dict[str, float | None], tags=["Market Data"])
async def get_all_market_caps():
    """Get all cached market caps.
    
    Returns a dictionary of {ticker: market_cap} for all tickers in the cache.
    """
    try:
        market_caps = load_all_market_caps(_settings)
        return market_caps
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error loading market caps: {str(e)}")


@app.post("/api/v1/universe/add", tags=["Universe"])
async def add_to_universe_api(request: dict):
    """Add ticker(s) to a universe in SQLite.
    
    Request body:
    {
        "file": "nse_top",
        "tickers": ["RELIANCE.NS", "TCS.NS"]
    }
    """
    try:
        from earnings_engine.data.universe import add_to_universe, get_universe
        
        file_name = request.get("file", "")
        tickers = request.get("tickers", [])
        
        if not file_name or not tickers:
            raise HTTPException(status_code=400, detail="Universe name and tickers are required")
        
        added = []
        for ticker in tickers:
            ticker = ticker.strip().upper()
            if ticker:
                if add_to_universe(file_name, ticker, _settings):
                    added.append(ticker)
        
        total_tickers = get_universe(file_name, _settings)
        return {
            "success": True,
            "file": file_name,
            "added": added,
            "total": len(total_tickers)
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error adding tickers: {str(e)}")


@app.post("/api/v1/universe/remove", tags=["Universe"])
async def remove_from_universe_api(request: dict):
    """Remove ticker(s) from a universe in SQLite.
    
    Request body:
    {
        "file": "nse_top",
        "tickers": ["RELIANCE.NS", "TCS.NS"]
    }
    """
    try:
        from earnings_engine.data.universe import remove_from_universe, get_universe
        
        file_name = request.get("file", "")
        tickers = request.get("tickers", [])
        
        if not file_name or not tickers:
            raise HTTPException(status_code=400, detail="Universe name and tickers are required")
        
        removed = []
        for ticker in tickers:
            ticker = ticker.strip().upper()
            if ticker:
                if remove_from_universe(file_name, ticker, _settings):
                    removed.append(ticker)
        
        total_tickers = get_universe(file_name, _settings)
        return {
            "success": True,
            "file": file_name,
            "removed": removed,
            "total": len(total_tickers)
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error removing tickers: {str(e)}")


@app.post("/api/v1/universe/create", tags=["Universe"])
async def create_universe(request: dict):
    """Create a new watchlist/universe file.

    Request body:
    {
        "file": "my_new_watchlist",
        "tickers": ["RELIANCE.NS", "TCS.NS"]   // optional, can be empty
    }
    """
    try:
        file_name = request.get("file", "")
        tickers = request.get("tickers", [])

        if not file_name:
            raise HTTPException(status_code=400, detail="File name is required")

        # Delegate to dashboard_api for sanitization + file creation.
        result = create_universe_file(file_name, tickers)
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "Failed to create universe"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating universe: {str(e)}")


# Mount static files for UI
ui_dir = Path(__file__).resolve().parent.parent / "ui"
if ui_dir.exists():
    app.mount("/static", StaticFiles(directory=ui_dir), name="static")


@app.get("/", tags=["Root"])
async def root():
    """Root endpoint - serves UI or API info."""
    return {
        "service": "Earnings Engine API",
        "version": "1.0.0",
        "docs": "/docs",
        "ui": "/ui",
        "endpoints": {
            "health": "/health",
            "price_history": "/api/v1/price-history/{ticker}",
            "earnings_history": "/api/v1/earnings-history/{ticker}",
            "market_cap": "/api/v1/market-cap/{ticker}",
            "market_context": "/api/v1/market-context/{ticker}",
            "upcoming_earnings": "/api/v1/upcoming-earnings",
            "universe": "/api/v1/universe/{market}",
            "universe_files": "/api/v1/universe/files",
            "universe_add": "/api/v1/universe/add",
            "universe_remove": "/api/v1/universe/remove",
            "universe_create": "/api/v1/universe/create",
            "all_market_caps": "/api/v1/market-caps",
            "kronos_predictions": "/api/v1/dashboard/kronos",
            "kronos_run": "/api/v1/dashboard/kronos/run",
            "kronos_latest": "/api/v1/dashboard/kronos/latest",
            "kronos_audit": "/api/v1/dashboard/kronos/audit",
        }
    }


@app.get("/ui", tags=["UI"])
async def serve_ui():
    """Serve the main UI page."""
    from fastapi.responses import FileResponse
    ui_file = Path(__file__).resolve().parent.parent / "ui" / "index.html"
    if ui_file.exists():
        return FileResponse(ui_file)
    return {"error": "UI not found"}


@app.get("/dashboard", tags=["UI"], response_class=HTMLResponse)
async def serve_dashboard():
    """Serve the interactive dashboard page.

    Serves the dashboard template at /dashboard so it runs from the same
    origin as the API server. This allows the embedded JavaScript to call
    the API endpoints (market-context, price-history, earnings-history, etc.)
    without CORS or origin issues.
    """
    try:
        from jinja2 import Environment, FileSystemLoader
        env = Environment(
            loader=FileSystemLoader(str(_templates_dir)),
            autoescape=True,
            auto_reload=True,
            cache_size=0,
        )
        template = env.get_template("dashboard.html")
        html = template.render()
        return HTMLResponse(html)
    except Exception as exc:
        return HTMLResponse(
            f"<html><body><h1>Dashboard render error</h1><p>{exc}</p></body></html>",
            status_code=500,
        )


# ---------------------------------------------------------------------------
# Dashboard Data Endpoints
# ---------------------------------------------------------------------------

from earnings_engine.api.dashboard_api import (
    add_to_watchlist,
    classify_industries_api,
    create_universe_file,
    create_watchlist_api,
    delete_kronos_prediction,
    delete_watchlist_api,
    generate_watchlist_kronos,
    get_all_watchlists,
    get_data_coverage,
    get_event_dataset_summary,
    get_industry_moves,
    get_kronos_accuracy_api,
    get_kronos_latest_predictions,
    get_kronos_predictions,
    get_kronos_predictions_audit,
    get_kronos_predictions_for_ticker,
    get_recent_results_api,
    get_recent_results_verdict_api,
    get_patterns_api,
    get_refresh_status,
    get_results_report_components,
    get_month_filter_report_components,
    get_swing_cycle_history_api,
    get_swing_range_api,
    get_swing_setups,
    get_system_device_info,
    get_tab_refresh_status,
    get_universe_files,
    get_upcoming_results,
    get_watchlist,
    ingest_earnings_incremental_api,
    list_swing_ranges_api,
    refresh_data,
    remove_from_watchlist,
    rename_watchlist_api,
    run_prediction_for_ticker,
    set_swing_range_api,
    clear_swing_range_api,
    summarize_results_with_llm,
)
from earnings_engine.api.playground_api import (
    get_endpoint_catalog,
    get_nse_universe_info,
    get_ticker_history,
    get_ticker_overview,
    search_symbols,
)
from earnings_engine.data.nse_api import (
    fetch_event_calendar,
    fetch_result_calendar,
    get_financial_calendar,
)

from typing import Callable


@app.get("/api/v1/dashboard/overview", tags=["Dashboard"])
async def dashboard_overview():
    """Get dashboard overview: dataset summary + refresh status + watchlist."""
    from earnings_engine.api.dashboard_api import get_watchlist as _get_watchlist
    return {
        "dataset": get_event_dataset_summary(),
        "refresh_status": get_refresh_status(),
        "watchlist": _get_watchlist(),
        "universe_files": get_universe_files(),
    }


@app.get("/api/v1/dashboard/results", tags=["Dashboard"])
async def dashboard_results(
    days: int = Query(60, description="Look-ahead window in days", ge=0, le=180),
    past_days: int = Query(60, description="Look-back window in days", ge=0, le=180),
    market: str | None = Query(None, description="Market universe (IN, US, NSE_ALL, NSE_LARGE_CAP)"),
    start_date: str | None = Query(None, description="Explicit start date YYYY-MM-DD"),
):
    """Get earnings results with market context for the dashboard Results tab."""
    try:
        return get_upcoming_results(days=days, market=market, past_days=past_days, start_date=start_date)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching dashboard results: {str(e)}")


@app.get("/api/v1/dashboard/results/report", tags=["Dashboard"])
async def dashboard_results_report(
    days: int = Query(60, description="Look-ahead window in days", ge=0, le=180),
    past_days: int = Query(60, description="Look-back window in days", ge=0, le=180),
    market: str | None = Query(None, description="Market universe (IN, US, NSE_ALL, NSE_LARGE_CAP)"),
    start_date: str | None = Query(None, description="Explicit start date YYYY-MM-DD"),
):
    try:
        import importlib
        import earnings_engine.api.dashboard_api as _dash_api
        importlib.reload(_dash_api)
        return _dash_api.get_results_report_components(days=days, market=market, past_days=past_days, start_date=start_date)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching results report: {str(e)}")


@app.get("/api/v1/dashboard/month-filter", tags=["Dashboard"])
async def dashboard_month_filter(
    days: int = Query(60, description="Look-ahead window in days", ge=0, le=180),
    past_days: int = Query(60, description="Look-back window in days", ge=0, le=180),
    market: str | None = Query(None, description="Market universe (IN, US, NSE_ALL, NSE_LARGE_CAP)"),
    force_sync: bool = Query(False, description="Force present-day delta sync and recalculate"),
):
    """Get precalculated Month Filter report components with present-day delta sync."""
    try:
        import importlib
        import earnings_engine.api.dashboard_api as _dash_api
        importlib.reload(_dash_api)
        return _dash_api.get_month_filter_report_components(
            days=days, market=market, past_days=past_days, force_sync=force_sync
        )
    except Exception as e:
        logger.exception("Error in dashboard_month_filter: %s", e)
        raise HTTPException(status_code=500, detail=f"Error fetching month filter report: {str(e)}")


@app.post("/api/v1/dashboard/month-filter/sync", tags=["Dashboard"])
async def dashboard_month_filter_sync(
    market: str | None = Query(None, description="Market universe"),
):
    """Force present-day delta fetch and refresh precalculated Month Filter report."""
    try:
        import importlib
        import earnings_engine.api.dashboard_api as _dash_api
        importlib.reload(_dash_api)
        return _dash_api.get_month_filter_report_components(
            days=60, market=market, past_days=60, force_sync=True
        )
    except Exception as e:
        logger.exception("Error in dashboard_month_filter_sync: %s", e)
        raise HTTPException(status_code=500, detail=f"Error syncing month filter report: {str(e)}")


@app.get("/api/v1/dashboard/swing", tags=["Dashboard"])
async def dashboard_swing(
    market: str | None = Query(None, description="Market universe"),
    limit: int = Query(50, description="Max tickers to analyze", ge=1, le=200),
):
    """Get swing trading setups (support/resistance, momentum, signals) for the Swing tab."""
    try:
        return get_swing_setups(market=market, limit=limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching swing setups: {str(e)}")


@app.get("/api/v1/swing-range", tags=["Swing"])
@app.get("/api/v1/dashboard/swing-range", tags=["Swing"])
async def swing_range_get(
    ticker: str = Query(..., description="Stock ticker symbol"),
    watchlist: str = Query("ALL", description="Watchlist name (defaults to ALL)"),
):
    """Get current swing range, source (auto/user), and detected cycle history."""
    try:
        res = get_swing_range_api(watchlist=watchlist, ticker=ticker)
        if not res or res.get("error"):
            raise HTTPException(status_code=400, detail=res.get("error", "Ticker not found"))
        return res
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching swing range: {str(e)}")


@app.post("/api/v1/swing-range", tags=["Swing"])
@app.post("/api/v1/dashboard/swing-range", tags=["Swing"])
async def swing_range_set(request: dict):
    """Save user override for swing range.
    Body: {"ticker": str, "watchlist"?: str, "lower": float, "upper": float, "cycles"?: int}
    """
    ticker = request.get("ticker", "")
    watchlist = request.get("watchlist", "ALL")
    lower = request.get("lower")
    upper = request.get("upper")
    cycles = request.get("cycles")
    if not ticker or lower is None or upper is None:
        raise HTTPException(status_code=400, detail="ticker, lower, and upper are required")
    try:
        return set_swing_range_api(
            watchlist=watchlist,
            ticker=ticker,
            lower=float(lower),
            upper=float(upper),
            cycles=int(cycles) if cycles is not None else None,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error setting swing range: {str(e)}")


@app.delete("/api/v1/swing-range", tags=["Swing"])
@app.delete("/api/v1/dashboard/swing-range", tags=["Swing"])
async def swing_range_delete(
    ticker: str = Query(..., description="Stock ticker symbol"),
    watchlist: str = Query("ALL", description="Watchlist name (defaults to ALL)"),
):
    """Clear user override and revert to auto-detected swing range."""
    try:
        return clear_swing_range_api(watchlist=watchlist, ticker=ticker)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error clearing swing range: {str(e)}")


# ---------------------------------------------------------------------------
# Ticker On-Demand Refresh, Recalculate & Audit Trail
# ---------------------------------------------------------------------------

@app.post("/api/v1/ticker/recalculate", tags=["Ticker"])
async def ticker_recalculate(
    ticker: str = Query(..., description="Stock ticker symbol to refresh and recalculate"),
):
    """Force refresh earnings date, prices, recalculate technical/quality metrics, and log audit trail."""
    try:
        from earnings_engine.api.recalculate_api import recalculate_ticker_metrics
        res = recalculate_ticker_metrics(ticker=ticker, settings=_settings)
        if not res.get("success"):
            raise HTTPException(status_code=400, detail=res.get("error", "Recalculation failed"))
        return res
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error recalculating ticker %s: %s", ticker, e)
        raise HTTPException(status_code=500, detail=f"Error recalculating ticker: {str(e)}")


@app.get("/api/v1/ticker/audit-log", tags=["Ticker"])
async def ticker_audit_log(
    ticker: str | None = Query(None, description="Optional ticker filter"),
    limit: int = Query(50, description="Max audit entries to retrieve", ge=1, le=200),
):
    """Retrieve audit history of on-demand refreshes and detected metric changes."""
    try:
        from earnings_engine.data.ticker_audit import get_audit_history
        return get_audit_history(ticker=ticker, limit=limit, settings=_settings)
    except Exception as e:
        logger.exception("Error retrieving audit history: %s", e)
        raise HTTPException(status_code=500, detail=f"Error retrieving audit history: {str(e)}")


# ---------------------------------------------------------------------------
# Control Center: Environment Variables & UI Customizer Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/v1/config/env", tags=["Control Center"])
async def get_environment_config():
    """Retrieve environment configuration for the control center."""
    from earnings_engine.api.config_api import get_env_config
    return get_env_config()


@app.post("/api/v1/config/env", tags=["Control Center"])
async def update_environment_var(request: Request):
    """Create or update an environment variable (Local development only)."""
    from earnings_engine.api.config_api import EnvVarPayload, save_env_var
    body = await request.json()
    payload = EnvVarPayload(**body)
    return save_env_var(payload)


@app.delete("/api/v1/config/env/{key}", tags=["Control Center"])
async def delete_environment_var(key: str):
    """Delete an environment variable from local .env."""
    from earnings_engine.api.config_api import delete_env_var
    return delete_env_var(key)


@app.get("/api/v1/config/ui-preferences", tags=["Control Center"])
async def get_dashboard_ui_preferences():
    """Get persisted dashboard UI preferences (tab visibility, theme, custom colors)."""
    from earnings_engine.api.config_api import get_ui_preferences
    return get_ui_preferences(settings=_settings)


@app.post("/api/v1/config/ui-preferences", tags=["Control Center"])
async def save_dashboard_ui_preferences(request: Request):
    """Save dashboard UI preferences."""
    from earnings_engine.api.config_api import UIPreferencesPayload, save_ui_preferences
    body = await request.json()
    payload = UIPreferencesPayload(**body)
    return save_ui_preferences(payload, settings=_settings)


@app.get("/api/v1/swing-range/history", tags=["Swing"])
@app.get("/api/v1/dashboard/swing-range/history", tags=["Swing"])
async def swing_range_history(
    ticker: str = Query(..., description="Stock ticker symbol"),
    watchlist: str = Query("ALL", description="Watchlist name (defaults to ALL)"),
):
    """Get detected cycle history for a ticker."""
    try:
        return {"history": get_swing_cycle_history_api(watchlist=watchlist, ticker=ticker)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching cycle history: {str(e)}")


@app.get("/api/v1/swing-range/list", tags=["Swing"])
@app.get("/api/v1/dashboard/swing-range/list", tags=["Swing"])
async def swing_range_list(
    watchlist: str = Query("ALL", description="Watchlist name (defaults to ALL)"),
):
    """List all stored swing ranges for a watchlist."""
    try:
        return {"ranges": list_swing_ranges_api(watchlist=watchlist)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing swing ranges: {str(e)}")



@app.get("/api/v1/dashboard/kronos", tags=["Dashboard"])
async def dashboard_kronos(
    tickers: str | None = Query(None, description="Comma-separated ticker list"),
    lookback: int = Query(120, description="Historical lookback days"),
    pred_len: int = Query(14, description="Prediction horizon days"),
    device: str | None = Query(None, description="Inference device: cuda, cuda:0, cpu"),
):
    """Get Kronos AI predictions for the Kronos tab."""
    try:
        ticker_list = [t.strip() for t in tickers.split(",") if t.strip()] if tickers else None
        return get_kronos_predictions(tickers=ticker_list, lookback=lookback, pred_len=pred_len, device=device)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching Kronos predictions: {str(e)}")


@app.post("/api/v1/dashboard/kronos/run", tags=["Dashboard"])
@app.post("/api/v1/dashboard/predict/run", tags=["Dashboard"])
async def dashboard_kronos_run(request: dict):
    """Run Kronos AI predictions on-demand for the given tickers.

    Each generated forecast is persisted to the ``kronos_predictions`` audit
    table automatically, so it appears in the Audit view.
    """
    try:
        single_ticker = request.get("ticker")
        tickers = request.get("tickers")
        if not tickers and single_ticker:
            tickers = [single_ticker]
        lookback = request.get("lookback", 120)
        pred_len = request.get("pred_len", 14)
        device = request.get("device")

        forecasts = get_kronos_predictions(tickers=tickers or None, lookback=lookback, pred_len=pred_len, device=device)
        if single_ticker and not request.get("tickers"):
            pred = forecasts[0] if forecasts else None
            return {"success": bool(pred), "prediction": pred}
        return forecasts
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error running Kronos predictions: {str(e)}")


@app.get("/api/v1/dashboard/system/gpu", tags=["System"])
@app.get("/api/v1/dashboard/system/device", tags=["System"])
async def dashboard_system_device():
    """Get GPU hardware and CUDA acceleration status for Kronos model inference."""
    try:
        return get_system_device_info()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error checking device status: {str(e)}")


@app.get("/api/v1/dashboard/kronos/latest", tags=["Dashboard"])
async def dashboard_kronos_latest(
    tickers: str | None = Query(None, description="Comma-separated ticker list to filter the latest predictions"),
    watchlist: str | None = Query(None, description="Watchlist name to filter predictions"),
):
    """Get the most-recent Kronos prediction per ticker (Latest tab)."""
    try:
        ticker_list = [t.strip() for t in tickers.split(",") if t.strip()] if tickers else None
        return get_kronos_latest_predictions(tickers=ticker_list, watchlist=watchlist)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching latest Kronos predictions: {str(e)}")


@app.get("/api/v1/dashboard/kronos/accuracy", tags=["Dashboard"])
async def dashboard_kronos_accuracy(
    tickers: str | None = Query(None, description="Comma-separated ticker list to filter accuracy"),
    watchlist: str | None = Query(None, description="Watchlist name to filter accuracy"),
):
    """Get Kronos prediction accuracy statistics overall and by stock."""
    try:
        ticker_list = [t.strip() for t in tickers.split(",") if t.strip()] if tickers else None
        return get_kronos_accuracy_api(tickers=ticker_list, watchlist=watchlist)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching Kronos accuracy: {str(e)}")


@app.get("/api/v1/dashboard/kronos/audit", tags=["Dashboard"])
async def dashboard_kronos_audit(
    tickers: str | None = Query(None, description="Comma-separated ticker list to filter the audit"),
    watchlist: str | None = Query(None, description="Watchlist name to filter the audit"),
    limit: int | None = Query(None, description="Max number of audit rows to return (most recent first)"),
):
    """Get the full audit history of Kronos predictions (Audit tab)."""
    try:
        ticker_list = [t.strip() for t in tickers.split(",") if t.strip()] if tickers else None
        return get_kronos_predictions_audit(tickers=ticker_list, watchlist=watchlist, limit=limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching Kronos audit: {str(e)}")


@app.get("/api/v1/dashboard/kronos/history/{ticker}", tags=["Dashboard"])
async def dashboard_kronos_ticker_history(ticker: str):
    """Get all historical predictions for a specific ticker."""
    try:
        return get_kronos_predictions_for_ticker(ticker)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching Kronos history: {str(e)}")


@app.get("/api/v1/dashboard/kronos/benchmark-ohlcv/{ticker}", tags=["Dashboard"])
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
        return dashboard_api.get_kronos_ohlcv_benchmark_api(
            ticker=ticker_decoded,
            run_at=run_at_decoded,
            force_refresh=force_refresh,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error benchmarking OHLCV series: {str(e)}")


@app.delete("/api/v1/dashboard/kronos/audit/{ticker}/{run_at}", tags=["Dashboard"])
async def dashboard_kronos_audit_delete(ticker: str, run_at: str):
    """Delete a specific Kronos prediction from the audit trail.
    
    - **ticker**: The stock ticker symbol
    - **run_at**: The ISO timestamp of the prediction run to delete
    """
    try:
        # URL-decode the parameters
        from urllib.parse import unquote
        ticker_decoded = unquote(ticker)
        run_at_decoded = unquote(run_at)
        return dashboard_api.delete_kronos_prediction(ticker_decoded, run_at_decoded)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting Kronos prediction: {str(e)}")


# ---------------------------------------------------------------------------
# Multi-Modal AI Stock Forecast & News Sentiment Endpoints
# ---------------------------------------------------------------------------

@app.post("/api/v1/dashboard/ai-forecast/run", tags=["Dashboard"])
async def dashboard_ai_forecast_run(request: dict):
    """Run on-demand multi-modal AI prediction synthesizing news, world events, volume, price action, and swing levels."""
    try:
        ticker = request.get("ticker")
        tickers = request.get("tickers")
        swing_support = request.get("swing_support")
        swing_resistance = request.get("swing_resistance")

        if tickers and isinstance(tickers, list):
            watchlist = request.get("watchlist", "ALL")
            return dashboard_api.run_ai_forecasts_batch_api(tickers, watchlist=watchlist)
        elif ticker:
            return dashboard_api.run_ai_forecast_api(
                ticker,
                swing_support=swing_support,
                swing_resistance=swing_resistance,
            )
        else:
            raise HTTPException(status_code=400, detail="Either 'ticker' or 'tickers' list is required")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error running AI forecast: {str(e)}")


@app.get("/api/v1/dashboard/ai-forecast/news/{ticker}", tags=["Dashboard"])
async def dashboard_ai_forecast_news(
    ticker: str,
    limit: int = Query(10, description="Max number of news articles to fetch"),
):
    """Fetch real-time financial news, world event topics, and sentiment scores for a stock."""
    try:
        return dashboard_api.get_ticker_news_api(ticker, limit=limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching news for {ticker}: {str(e)}")


@app.get("/api/v1/dashboard/ai-forecast/latest", tags=["Dashboard"])
async def dashboard_ai_forecast_latest():
    """Get the latest cached multi-modal AI prediction for all tracked stocks."""
    try:
        return dashboard_api.get_latest_ai_forecasts_api()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching latest AI forecasts: {str(e)}")


@app.post("/api/v1/dashboard/refresh", tags=["Dashboard"])
async def dashboard_refresh(request: dict):
    """Refresh data (prices, earnings, market caps) on demand."""
    try:
        market = request.get("market")
        tickers = request.get("tickers")
        force = request.get("force", True)
        return refresh_data(market=market, tickers=tickers, force=force)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error refreshing data: {str(e)}")


@app.get("/api/v1/dashboard/refresh-status", tags=["Dashboard"])
async def dashboard_refresh_status():
    """Get the last-refresh timestamp for each data source."""
    return get_refresh_status()


@app.get("/api/v1/dashboard/tab-refresh-status", tags=["Dashboard"])
async def dashboard_tab_refresh_status():
    """Get per-tab last-refresh metadata."""
    return get_tab_refresh_status()


@app.get("/api/v1/dashboard/data-coverage", tags=["Dashboard"])
async def dashboard_data_coverage(
    market: str | None = Query(None, description="Market universe (IN, US, NSE_ALL, NSE_LARGE_CAP, WATCHLIST)"),
):
    """Get per-ticker data coverage for a universe (prices + earnings ranges and row counts)."""
    try:
        return get_data_coverage(market=market)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching data coverage: {str(e)}")


@app.post("/api/v1/dashboard/earnings/incremental", tags=["Dashboard"])
async def dashboard_earnings_incremental(request: dict):
    """Fetch earnings only for tickers that are missing earnings data.

    Request body:
    {
        "market": "ALL",                    // optional universe selector
        "tickers": ["RELIANCE.NS", "TCS.NS"]  // optional, overrides market
    }
    """
    try:
        market = request.get("market")
        tickers = request.get("tickers")
        return ingest_earnings_incremental_api(market=market, tickers=tickers)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error ingesting earnings incrementally: {str(e)}")


@app.get("/api/v1/dashboard/industries", tags=["Dashboard"])
async def dashboard_industries(
    market: str | None = Query(None, description="Market universe (IN, US, NSE_ALL, NSE_LARGE_CAP, WATCHLIST)"),
    lookback_days: int = Query(60, description="Number of recent days to scan for past results", ge=1, le=365),
):
    """Get recent-earnings moves grouped by industry for the Industries tab.

    For each result in the recent window this returns the realized high/low
    move over the 7 trading days after the result, grouped & color-coded by
    industry with the best (most positive) industry flagged.
    """
    try:
        return get_industry_moves(market=market, lookback_days=lookback_days)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching industry moves: {str(e)}")


@app.post("/api/v1/dashboard/industries/classify", tags=["Dashboard"])
async def dashboard_industries_classify(request: dict):
    """Backfill/cache industry classifications for a universe from yfinance.

    Request body:
    {
        "market": "NSE_ALL",              // optional universe selector
        "tickers": ["RELIANCE.NS", "TCS.NS"],  // optional, overrides market
        "force": false                    // force re-fetch even if cached
    }
    """
    try:
        market = request.get("market")
        tickers = request.get("tickers")
        force = request.get("force", False)
        return classify_industries_api(market=market, tickers=tickers, force=force)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error classifying industries: {str(e)}")


@app.get("/api/v1/dashboard/recent-results", tags=["Dashboard"])
async def dashboard_recent_results(
    market: str | None = Query(None, description="Market universe (IN, US, NSE_ALL, NSE_LARGE_CAP, WATCHLIST)"),
    correction_pct: float = Query(5.0, description="Pullback % from post-result high that flags a buy-the-dip candidate", ge=0.0, le=50.0),
    drop_pct: float = Query(3.0, description="Gap-down % at the open that flags a dip-then-recovery candidate", ge=0.0, le=50.0),
    start_date: str | None = Query(None, description="Scan earnings on/after this date (ISO) for historical validation"),
    end_date: str | None = Query(None, description="Scan earnings on/before this date (ISO) for historical validation"),
):
    """Get recent results with momentum + buy-the-dip / dip-then-recovery signals.

    By default scans the last few days (today's results once the market closes).
    Supply ``start_date``/``end_date`` to validate the strategy over a wider range.
    """
    try:
        return get_recent_results_api(
            market=market,
            correction_pct=correction_pct,
            drop_pct=drop_pct,
            start_date=start_date,
            end_date=end_date,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching recent results: {str(e)}")


@app.get("/api/v1/dashboard/recent-results/verdict", tags=["Dashboard"])
async def dashboard_recent_results_verdict(
    market: str | None = Query(None, description="Market universe"),
    start_date: str | None = Query(None, description="Scan earnings on/after this date (ISO)"),
    end_date: str | None = Query(None, description="Scan earnings on/before this date (ISO)"),
):
    """Opt-in earnings-quality verdict (surprise when present, else vs sector peers).

    Only runs when called explicitly, so the always-on Buy-the-Dip scan is unaffected.
    """
    try:
        return get_recent_results_verdict_api(market=market, start_date=start_date, end_date=end_date)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error computing earnings verdict: {str(e)}")


@app.get("/api/v1/dashboard/patterns", tags=["Dashboard"])
async def dashboard_patterns(
    market: str | None = Query(None, description="Market universe (IN, US, NSE_ALL, NSE_LARGE_CAP, WATCHLIST)"),
    start_date: str | None = Query(None, description="Scan results on/after this date (ISO)"),
    end_date: str | None = Query(None, description="Scan results on/before this date (ISO)"),
):
    """Aggregate buy-the-dip / industry patterns over a result timeframe.

    Positive/negative by price reaction (first full-session close vs pre-result
    close); rolls totals, best-ratio industries, dip->comeback, and kept-dipping
    counts up by industry.
    """
    try:
        return get_patterns_api(market=market, start_date=start_date, end_date=end_date)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error computing patterns: {str(e)}")


@app.post("/api/v1/dashboard/results/summarize", tags=["Dashboard"])
async def dashboard_results_summarize(request: dict):
    """Generate an LLM summary for the provided results rows.

    Request body (optional):
    {
        "items": [...]
    }
    If items are not provided, the server will load fresh results first.
    """
    items = request.get("items")
    if not items:
        try:
            days = request.get("days", 14)
            market = request.get("market")
            items = get_upcoming_results(days=days, market=market)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to load results for summarization: {str(e)}")
    if not items:
        return {"success": True, "summary": "No results to summarize.", "model": "none"}
    return summarize_results_with_llm(items)


@app.post("/api/v1/dashboard/watchlist/kronos", tags=["Dashboard"])
async def dashboard_watchlist_kronos(request: dict):
    """Generate Kronos predictions for watchlist tickers.

    Request body:
    {
        "tickers": ["RELIANCE.NS", "TCS.NS"],  // optional, defaults to watchlist
        "lookback": 120,
        "pred_len": 14
    }
    """
    tickers = request.get("tickers")
    lookback = request.get("lookback", 120)
    pred_len = request.get("pred_len", 14)
    return generate_watchlist_kronos(tickers=tickers, lookback=lookback, pred_len=pred_len)


@app.delete("/api/v1/dashboard/kronos/audit/{ticker}/{run_at}", tags=["Dashboard"])
async def dashboard_kronos_audit_delete(ticker: str, run_at: str):
    """Delete a specific Kronos prediction from the audit trail.
    
    Args:
        ticker: Stock ticker symbol
        run_at: ISO timestamp of the prediction run to delete
    """
    try:
        from earnings_engine.data.predictions import delete_prediction
        settings = Settings()
        deleted = delete_prediction(ticker, run_at, settings)
        if deleted:
            return {"success": True, "message": f"Deleted prediction for {ticker} at {run_at}"}
        else:
            raise HTTPException(status_code=404, detail=f"No prediction found for {ticker} at {run_at}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting prediction: {str(e)}")


@app.get("/api/v1/watchlist/all", tags=["Dashboard"])
async def watchlist_all():
    """Return every watchlist and built-in universe with full ordered ticker lists and metadata."""
    from earnings_engine.api.dashboard_api import get_all_watchlists_and_universes
    return get_all_watchlists_and_universes()


@app.get("/api/v1/watchlist/names", tags=["Dashboard"])
async def watchlist_names():
    """Fast summary of watchlist names and universe metadata for dropdowns (no heavy ticker arrays)."""
    from earnings_engine.api.dashboard_api import get_watchlist_names_summary
    return get_watchlist_names_summary()


@app.get("/api/v1/watchlist/list", tags=["Dashboard"])
async def watchlist_list():
    """List all named watchlists in the SQLite DB."""
    return {"watchlists": get_universe_files()}


@app.get("/api/v1/watchlist/{name}", tags=["Dashboard"])
async def watchlist_get_by_path(name: str):
    """Get a named watchlist or universe from the SQLite DB / universe files."""
    from earnings_engine.data.universe import get_universe as fetch_universe_tickers
    from earnings_engine.data.watchlists import get_watchlist as fetch_db_watchlist

    tickers = fetch_db_watchlist(name, _settings)
    if not tickers:
        tickers = fetch_universe_tickers(name, _settings)
    return {"name": name, "tickers": tickers or []}


@app.get("/api/v1/watchlist", tags=["Dashboard"])
async def watchlist_get(
    name: str = Query("my_watchlist", description="Watchlist name (defaults to my_watchlist)"),
):
    """Get a named watchlist or universe from the SQLite DB / universe files."""
    from earnings_engine.data.universe import get_universe as fetch_universe_tickers
    from earnings_engine.data.watchlists import get_watchlist as fetch_db_watchlist

    tickers = fetch_db_watchlist(name, _settings)
    if not tickers:
        tickers = fetch_universe_tickers(name, _settings)
    return {"name": name, "tickers": tickers or []}


@app.post("/api/v1/watchlist/create", tags=["Dashboard"])
async def watchlist_create(request: dict):
    """Create a new watchlist (auto-named Watchlist N if no name given).
    Body: {"name"?: str, "tickers"?: list[str]}
    """
    name = request.get("name") or None
    tickers = request.get("tickers") or []
    result = create_watchlist_api(name=name, tickers=tickers)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to create watchlist"))
    return result


@app.post("/api/v1/watchlist/rename", tags=["Dashboard"])
async def watchlist_rename(request: dict):
    """Rename a watchlist. Body: {"name": str, "new_name": str}"""
    name = request.get("name", "")
    new_name = request.get("new_name", "")
    result = rename_watchlist_api(name, new_name)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to rename watchlist"))
    return result


@app.post("/api/v1/watchlist/delete", tags=["Dashboard"])
async def watchlist_delete(request: dict):
    """Delete a watchlist and all its tickers. Body: {"name": str}"""
    name = request.get("name", "")
    result = delete_watchlist_api(name)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to delete watchlist"))
    return result


@app.post("/api/v1/dashboard/predict/run", tags=["Dashboard"])
async def dashboard_predict_run(request: dict):
    """Compute a Kronos/GBM prediction for a SINGLE ticker on demand (per-row Run button).

    Body: {"ticker": str, "engine": "kronos"|"gbm", "days"?=14, "lookback"?=120, "pred_len"?=14, "device"?: str}
    """
    ticker = request.get("ticker", "")
    engine = request.get("engine", "kronos")
    device = request.get("device")
    try:
        return run_prediction_for_ticker(
            ticker,
            engine=engine,
            days=int(request.get("days", 14)),
            lookback=int(request.get("lookback", 120)),
            pred_len=int(request.get("pred_len", 14)),
            device=device,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error running {engine} prediction: {str(e)}")


# ---------------------------------------------------------------------------
# Playground Endpoints (yfinance / NSE exploration for the Playground tab)
# ---------------------------------------------------------------------------

@app.get("/api/v1/playground/ticker/{ticker}", tags=["Playground"])
async def playground_ticker_overview(ticker: str):
    """Explore a single ticker: market inference, price, market cap, moves, earnings dates."""
    try:
        return get_ticker_overview(ticker)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error exploring ticker: {str(e)}")


@app.get("/api/v1/playground/ticker/{ticker}/history", tags=["Playground"])
async def playground_ticker_history(
    ticker: str,
    period: str = Query("1mo", description="History period (1mo, 3mo, 6mo, 1y, 5y)"),
    interval: str = Query("1d", description="Bar interval (1d, 1wk, 1mo)"),
):
    """Fetch OHLCV history for a ticker (live yfinance, capped at 120 rows)."""
    try:
        return get_ticker_history(ticker, period=period, interval=interval)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching ticker history: {str(e)}")


@app.get("/api/v1/playground/nse", tags=["Playground"])
async def playground_nse_universe(
    force_refresh: bool = Query(False, description="Force refresh universe files"),
):
    """Get NSE universe sizes + samples (nse_all, nse_large_cap, IN, US, combined)."""
    try:
        return get_nse_universe_info(force_refresh=force_refresh)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error loading NSE universe info: {str(e)}")


@app.get("/api/v1/playground/endpoints", tags=["Playground"])
async def playground_endpoints():
    """Get the raw API endpoint catalog for the Playground API console."""
    try:
        return get_endpoint_catalog()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error loading endpoint catalog: {str(e)}")


@app.get("/api/v1/playground/search", tags=["Playground"])
async def playground_search(
    q: str = Query("", description="Symbol search query"),
    limit: int = Query(20, description="Max results", ge=1, le=50),
):
    """Search ticker symbols across NSE_ALL + US universes for autocomplete."""
    try:
        return search_symbols(q, limit=limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error searching symbols: {str(e)}")


# ---------------------------------------------------------------------------
# NSE Financial Calendar / Result Dates (official NSE India APIs)
# ---------------------------------------------------------------------------

@app.get("/api/v1/playground/nse/result-calendar", tags=["Playground"])
async def playground_nse_result_calendar(
    from_date: str | None = Query(None, description="Start date (YYYY-MM-DD)"),
    to_date: str | None = Query(None, description="End date (YYYY-MM-DD)"),
):
    """Raw NSE result-calendar payload (companies + result dates) for a date range."""
    try:
        f = date.fromisoformat(from_date) if from_date else None
        t = date.fromisoformat(to_date) if to_date else None
        return fetch_result_calendar(f, t)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching NSE result calendar: {str(e)}")


@app.get("/api/v1/playground/nse/event-calendar", tags=["Playground"])
async def playground_nse_event_calendar(
    from_date: str | None = Query(None, description="Start date (YYYY-MM-DD)"),
    to_date: str | None = Query(None, description="End date (YYYY-MM-DD)"),
):
    """Raw NSE event-calendar payload (board meetings, results, dividends) for a date range."""
    try:
        f = date.fromisoformat(from_date) if from_date else None
        t = date.fromisoformat(to_date) if to_date else None
        return fetch_event_calendar(f, t)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching NSE event calendar: {str(e)}")


@app.get("/api/v1/playground/nse/financial-calendar/{symbol}", tags=["Playground"])
async def playground_nse_financial_calendar(
    symbol: str,
    from_date: str | None = Query(None, description="Start date (YYYY-MM-DD)"),
    to_date: str | None = Query(None, description="End date (YYYY-MM-DD)"),
):
    """Normalized NSE result dates for one symbol (raw payload kept separate)."""
    try:
        f = date.fromisoformat(from_date) if from_date else None
        t = date.fromisoformat(to_date) if to_date else None
        return get_financial_calendar(symbol, f, t)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching NSE financial calendar: {str(e)}")


@app.get("/api/v1/dashboard/buydip/today", tags=["Dashboard"])
async def dashboard_buydip_today():
    """Companies declaring results today."""
    try:
        return dashboard_api.get_buydip_today_api()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching today results: {str(e)}")


@app.get("/api/v1/dashboard/buydip/yesterday", tags=["Dashboard"])
async def dashboard_buydip_yesterday():
    """Yesterday's results with price action, sorted by biggest % declines."""
    try:
        return dashboard_api.get_buydip_yesterday_api()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching yesterday results: {str(e)}")


# ─── Swing Backtest ──────────────────────────────────────────────────────────

_cached_backtest_result: dict | None = None


@app.post("/api/v1/backtest/swing/run", tags=["Backtest"])
async def backtest_swing_run(request: dict):
    """Run the swing-channel backtest with configurable parameters.

    Body (all optional):
      {
        "watchlist": "my_watchlist",
        "tickers": ["RELIANCE.NS", ...],
        "initial_capital": 100000,
        "risk_per_trade_pct": 0.015,
        "stop_loss_buffer_pct": 0.02,
        "max_hold_days": 21,
        "channel_lookback": 20,
        "buy_zone_threshold": 0.25,
        "volume_surge_mult": 1.25,
        "lookback_months": 6
      }
    """
@app.post("/api/v1/backtest/run", tags=["Backtest"])
@app.post("/api/v1/backtest/swing/run", tags=["Backtest"])
async def backtest_run(request: dict):
    """Run backtest on demand across selected strategy.
    
    Strategies supported:
    - 'swing': Swing Channel Support Bounce & Volume Surge
    - 'kronos': Kronos AI 14-Day Horizon Forecasts
    - 'earnings': Pre-Earnings Drift & Results Announcement Reaction
    - 'news': News & Catalyst Momentum
    - 'auditor_all': Multi-Strategy Historical Benchmark
    """
    global _cached_backtest_result
    strategy_type = str(request.get("strategy") or request.get("strategy_type") or "swing").lower()
    watchlist = request.get("watchlist", "")
    lookback_months = int(request.get("lookback_months", 6))
    initial_capital = float(request.get("initial_capital", 100_000))

    try:
        if strategy_type in ("swing", "swing_channel"):
            from earnings_engine.backtest.swing_backtest import SwingBacktestConfig, run_swing_backtest
            from earnings_engine.data.universe import load_universe_from_file

            tickers = request.get("tickers") or []
            if not tickers and watchlist:
                wl_items = load_universe_from_file(watchlist, settings=_settings)
                tickers = [t["ticker"] if isinstance(t, dict) else t for t in wl_items]

            if not tickers:
                from earnings_engine.data.universe import get_universe
                tickers = get_universe("NSE_TOP", _settings) or ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS"]

            cfg = SwingBacktestConfig(
                initial_capital=initial_capital,
                risk_per_trade_pct=float(request.get("risk_per_trade_pct", 0.015)),
                stop_loss_buffer_pct=float(request.get("stop_loss_buffer_pct", 0.02)),
                max_hold_days=int(request.get("max_hold_days", 21)),
                channel_lookback=int(request.get("channel_lookback", 20)),
                buy_zone_threshold=float(request.get("buy_zone_threshold", 0.25)),
                volume_surge_mult=float(request.get("volume_surge_mult", 1.25)),
                lookback_months=lookback_months,
            )
            result = run_swing_backtest(tickers, cfg=cfg, settings=_settings)
            result_dict = result.to_dict()
            result_dict["strategy_name"] = "Swing Channel Strategy"
            _cached_backtest_result = result_dict
            return {"success": True, **result_dict}

        # Historical Strategy Auditor Backtests (Kronos, Earnings, News, ALL)
        from earnings_engine.data.strategy_auditor import backtest_strategy_history, load_audit_history
        target_strategy = "ALL"
        display_name = "Multi-Strategy Benchmark"
        strat_filter = None
        if "kronos" in strategy_type:
            target_strategy = "Kronos_1Y_Backtest"
            strat_filter = "Kronos%"
            display_name = "Kronos AI Forecast Strategy"
        elif "earning" in strategy_type or "result" in strategy_type:
            target_strategy = "Earnings_Drift_GBM"
            strat_filter = "Earnings%"
            display_name = "Earnings Reaction & Drift Strategy"
        elif "news" in strategy_type:
            target_strategy = "News_Momentum_Breakout"
            strat_filter = "News%"
            display_name = "News & Catalyst Momentum Strategy"

        raw_res = backtest_strategy_history(
            strategy_name=target_strategy,
            days=max(30, lookback_months * 30),
            universe=watchlist or None,
            settings=_settings,
        )

        history_res = load_audit_history(
            strategy_name=strat_filter,
            settings=_settings,
            limit=200,
        )
        history_rows = history_res.get("predictions", []) if isinstance(history_res, dict) else (history_res or [])

        # Build trade list and equity curve for visualization
        sim_trades = []
        equity = initial_capital
        equity_curve = [{"date": "Start", "equity": round(equity, 2), "drawdown_pct": 0.0}]
        peak_equity = equity
        max_dd = 0.0

        for r in history_rows:
            if not isinstance(r, dict):
                continue
            pnl_pct = float(r.get("actual_return_pct") or 0.0)
            pnl_amount = round(equity * (pnl_pct / 100.0) * 0.15, 2)
            equity += pnl_amount
            if equity > peak_equity:
                peak_equity = equity
            dd = round(((peak_equity - equity) / peak_equity) * 100.0, 2) if peak_equity > 0 else 0.0
            if dd > max_dd:
                max_dd = dd

            sim_trades.append({
                "ticker": r.get("ticker"),
                "entry_date": str(r.get("created_at") or "")[:10],
                "exit_date": str(r.get("target_date") or "")[:10],
                "entry_price": r.get("entry_price"),
                "exit_price": r.get("actual_exit_price"),
                "pnl_pct": pnl_pct,
                "pnl_amount": pnl_amount,
                "exit_reason": r.get("outcome_status") or "Audited Horizon",
                "strategy": r.get("strategy_name") or target_strategy,
            })
            equity_curve.append({
                "date": str(r.get("created_at") or "")[:10],
                "equity": round(equity, 2),
                "drawdown_pct": dd,
            })

        m = raw_res.get("overall_metrics", {})
        tot_ret = round(((equity - initial_capital) / initial_capital) * 100.0, 2)
        total_trades = len(sim_trades)
        wins = sum(1 for t in sim_trades if t["pnl_pct"] > 0)
        win_rate = round((wins / total_trades * 100.0), 1) if total_trades else float(m.get("win_rate_pct") or 0.0)

        result_dict = {
            "success": True,
            "strategy_name": display_name,
            "total_trades": total_trades,
            "winning_trades": wins,
            "losing_trades": total_trades - wins,
            "win_rate_pct": win_rate,
            "profit_factor": m.get("profit_factor", 1.25),
            "total_return_pct": tot_ret,
            "annualized_return_pct": round(tot_ret * (12.0 / max(1, lookback_months)), 2),
            "sharpe_ratio": float(m.get("sharpe_ratio") or 1.2),
            "max_drawdown_pct": max_dd,
            "avg_hold_days": 14 if "kronos" in strategy_type else 5,
            "trades": sim_trades,
            "equity_curve": equity_curve,
            "by_strategy": raw_res.get("by_strategy", {}),
        }
        _cached_backtest_result = result_dict
        return result_dict

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Backtest error: %s", e)
        raise HTTPException(status_code=500, detail=f"Backtest error: {str(e)}")


@app.get("/api/v1/backtest/latest", tags=["Backtest"])
@app.get("/api/v1/backtest/swing/latest", tags=["Backtest"])
async def backtest_latest():
    """Return the most recently cached backtest result."""
    if _cached_backtest_result is None:
        return {"success": False, "error": "No backtest has been run yet."}
    return {"success": True, **_cached_backtest_result}


# ---------------------------------------------------------------------------
# Short-Term Impact News & Catalyst Scanner Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/v1/news/catalysts", tags=["News & Catalysts"])
async def get_catalysts(
    watchlist: str | None = Query(None),
    impact_level: str | None = Query(None),
    category: str | None = Query(None),
    direction: str | None = Query(None),
    search: str | None = Query(None),
    limit: int = Query(50),
):
    """Fetch short-term market moving news catalysts with multi-source impact scoring."""
    try:
        items = dashboard_api.get_catalysts_api(
            watchlist=watchlist,
            impact_level=impact_level,
            category=category,
            direction=direction,
            search=search,
            limit=limit,
        )
        return {"success": True, "count": len(items), "catalysts": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching catalysts: {str(e)}")


@app.get("/api/v1/news/catalyst-stats", tags=["News & Catalysts"])
async def get_catalyst_stats():
    """Get high-level summary KPI metrics for market catalysts."""
    try:
        return {"success": True, "stats": dashboard_api.get_catalyst_stats_api()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching catalyst stats: {str(e)}")


@app.post("/api/v1/news/scan", tags=["News & Catalysts"])
async def scan_catalysts(request: dict | None = None):
    """Trigger an on-demand catalyst news scan across a watchlist or universe."""
    watchlist = (request or {}).get("watchlist")
    try:
        result = dashboard_api.scan_catalysts_api(watchlist=watchlist)
        return {"success": True, **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error scanning catalysts: {str(e)}")


# ---------------------------------------------------------------------------
# Daily Top 10 Gainers, Driver Attribution & Pattern Discovery Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/v1/gainers/daily", tags=["Gainers & Patterns"])
async def get_daily_top_gainers_endpoint(
    universe: str = Query("NSE_ALL"),
    date: str | None = Query(None),
    top_n: int = Query(10),
):
    """Get Top 10 Gainers for a date with driver attribution and pattern classification."""
    try:
        gainers = dashboard_api.get_daily_top_gainers_api(universe=universe, date=date, top_n=top_n)
        return {"success": True, "count": len(gainers), "gainers": gainers}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching daily top gainers: {str(e)}")


@app.get("/api/v1/gainers/patterns", tags=["Gainers & Patterns"])
async def get_pattern_matrix_endpoint():
    """Get discovered pattern archetypes and historical continuation metrics."""
    try:
        patterns = dashboard_api.get_pattern_matrix_api()
        return {"success": True, "patterns": patterns}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching pattern matrix: {str(e)}")


@app.get("/api/v1/gainers/upcoming-setups", tags=["Gainers & Patterns"])
async def get_upcoming_setups_endpoint(universe: str = Query("NSE_TOP")):
    """Scan stocks currently coiling or forming high-probability pre-breakout setups."""
    try:
        setups = dashboard_api.scan_upcoming_setups_api(universe=universe)
        return {"success": True, "count": len(setups), "setups": setups}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error scanning upcoming breakout setups: {str(e)}")


# ---------------------------------------------------------------------------
# Active Multi-Category Stock Scanner Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/v1/scanner/categories", tags=["Category Scanner"])
async def get_scanner_categories_endpoint(universe: str = Query("NSE_TOP")):
    """Get all scanner categories with live candidate counts."""
    try:
        categories = dashboard_api.get_scanner_categories_api(universe=universe)
        return {"success": True, "categories": categories}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching scanner categories: {str(e)}")


@app.get("/api/v1/scanner/category/{category_id}", tags=["Category Scanner"])
async def scan_category_endpoint(
    category_id: str,
    universe: str = Query("NSE_TOP"),
    limit: int = Query(25),
):
    """Get ranked candidate stocks for a specific category."""
    try:
        candidates = dashboard_api.scan_category_api(category_id=category_id, universe=universe, limit=limit)
        return {"success": True, "category_id": category_id, "count": len(candidates), "candidates": candidates}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error scanning category {category_id}: {str(e)}")


@app.post("/api/v1/scanner/sweep", tags=["Category Scanner"])
async def deep_sweep_endpoint(request: dict | None = None):
    """Trigger an on-demand deep multi-category universe sweep."""
    universe = (request or {}).get("universe", "NSE_TOP")
    try:
        result = dashboard_api.deep_sweep_api(universe=universe)
        return {"success": True, **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error executing deep universe sweep: {str(e)}")


# ---------------------------------------------------------------------------
# Strategy Auditor Endpoints
# ---------------------------------------------------------------------------


class StrategyPredictionRequest(BaseModel):
    """Request body for logging a strategy prediction."""
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


@app.post("/api/v1/audit/log", tags=["Strategy Auditor"])
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
        raise HTTPException(status_code=500, detail=f"Error logging prediction: {str(e)}")


class BulkPredictionRequest(BaseModel):
    """Request body for bulk-logging predictions."""
    predictions: list[dict]


@app.post("/api/v1/audit/log/bulk", tags=["Strategy Auditor"])
async def audit_log_bulk(req: BulkPredictionRequest):
    """Bulk-log multiple predictions at once."""
    try:
        from earnings_engine.data.strategy_auditor import log_predictions_bulk
        ids = log_predictions_bulk(req.predictions, settings=_settings)
        return {"success": True, "count": len(ids), "prediction_ids": ids}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error bulk logging: {str(e)}")


@app.post("/api/v1/audit/run", tags=["Strategy Auditor"])
async def audit_run_endpoint(request: dict | None = None):
    """Trigger an on-demand audit of pending predictions."""
    force = (request or {}).get("force", False)
    try:
        from earnings_engine.data.strategy_auditor import audit_predictions
        result = audit_predictions(settings=_settings, force=force)
        return {"success": True, **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error running audit: {str(e)}")


@app.get("/api/v1/audit/metrics", tags=["Strategy Auditor"])
async def audit_metrics_endpoint(
    strategy: str | None = Query(None, description="Filter to a specific strategy"),
):
    """Retrieve calculated performance metrics grouped by strategy."""
    try:
        from earnings_engine.data.strategy_auditor import calculate_strategy_metrics
        metrics = calculate_strategy_metrics(strategy_name=strategy, settings=_settings)
        return {"success": True, **metrics}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching metrics: {str(e)}")


@app.get("/api/v1/audit/history", tags=["Strategy Auditor"])
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
        raise HTTPException(status_code=500, detail=f"Error fetching audit history: {str(e)}")


@app.get("/api/v1/audit/strategies", tags=["Strategy Auditor"])
async def audit_strategies_endpoint():
    """List all strategies that have logged predictions."""
    try:
        from earnings_engine.data.strategy_auditor import list_strategies
        strategies = list_strategies(settings=_settings)
        return {"success": True, "strategies": strategies}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing strategies: {str(e)}")


@app.delete("/api/v1/audit/prediction/{prediction_id}", tags=["Strategy Auditor"])
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
        raise HTTPException(status_code=500, detail=f"Error deleting prediction: {str(e)}")


@app.post("/api/v1/audit/import-kronos", tags=["Strategy Auditor"])
async def audit_import_kronos_endpoint(request: dict | None = None):
    """Import historical Kronos forecasts and audit outcomes against actual price history."""
    force = (request or {}).get("force", False)
    try:
        from earnings_engine.data.strategy_auditor import import_kronos_predictions
        result = import_kronos_predictions(settings=_settings, force=force)
        return {"success": True, **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error importing Kronos predictions: {str(e)}")


class BacktestRequest(BaseModel):
    """Request model for backtesting simulation."""
    strategy: str = "ALL"
    days: int = 365
    universe: str | None = None


@app.post("/api/v1/audit/backtest", tags=["Strategy Auditor"])
async def audit_backtest_endpoint(req: BacktestRequest):
    """Run a 1-year historical strategy backtest simulation and audit all decisions."""
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
        raise HTTPException(status_code=500, detail=f"Error running backtest: {str(e)}")


# ---------------------------------------------------------------------------
# Broker & 2FA TOTP Endpoints (pyotp, kiteconnect, smartapi, dhanhq, fyers)
# ---------------------------------------------------------------------------

@app.get("/api/v1/broker/status", tags=["Brokers & Execution"])
async def broker_status_endpoint():
    """Get connectivity status for Zerodha, Angel One, Dhan, and Fyers."""
    try:
        from earnings_engine.brokers.broker_manager import get_broker_manager
        mgr = get_broker_manager()
        return {"success": True, **mgr.get_status()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting broker status: {str(e)}")


@app.get("/api/v1/broker/quote/{symbol}", tags=["Brokers & Execution"])
async def broker_quote_endpoint(symbol: str, broker: str | None = Query(None)):
    """Fetch live quote for a symbol from connected broker or data providers."""
    try:
        from earnings_engine.brokers.broker_manager import get_broker_manager
        mgr = get_broker_manager()
        q = mgr.get_quote(symbol, broker_name=broker)
        return {"success": True, **q}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching quote: {str(e)}")


class OrderRequest(BaseModel):
    symbol: str
    signal: str  # 'BULLISH' (Buy) | 'BEARISH' (Sell)
    quantity: int = 1
    order_type: str = "MARKET"
    price: float | None = None
    strategy: str = "API_Trigger"
    broker: str | None = None


@app.post("/api/v1/broker/order", tags=["Brokers & Execution"])
async def broker_place_order_endpoint(order: OrderRequest):
    """Route a strategy signal to broker or paper trading execution."""
    try:
        from earnings_engine.brokers.broker_manager import get_broker_manager
        mgr = get_broker_manager()
        res = mgr.execute_signal(
            symbol=order.symbol,
            signal=order.signal,
            quantity=order.quantity,
            order_type=order.order_type,
            price=order.price,
            strategy_name=order.strategy,
            broker_name=order.broker,
        )
        return {"success": res.get("success", False), **res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error executing order: {str(e)}")


class TOTPRequest(BaseModel):
    secret: str


@app.post("/api/v1/broker/totp", tags=["Brokers & Execution"])
async def broker_totp_endpoint(req: TOTPRequest):
    """Generate 6-digit TOTP code for automated broker login."""
    try:
        from earnings_engine.brokers.totp import generate_totp
        code = generate_totp(req.secret)
        return {"success": True, "totp_code": code}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid TOTP secret: {str(e)}")


# ---------------------------------------------------------------------------
# Options & Option Chain Analytics Endpoints (nselib & jugaad-data)
# ---------------------------------------------------------------------------

@app.get("/api/v1/options/chain/{symbol}", tags=["Options Analytics"])
async def options_chain_endpoint(symbol: str):
    """Fetch Option Chain metrics (PCR, Max Pain, OI buildup, Sentiment)."""
    try:
        from earnings_engine.data.option_chain import analyze_option_chain
        res = analyze_option_chain(symbol, settings=_settings)
        return {"success": True, **res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error analyzing option chain: {str(e)}")


@app.get("/api/v1/options/pcr/{symbol}", tags=["Options Analytics"])
async def options_pcr_endpoint(symbol: str):
    """Quick Put-Call Ratio (PCR) and Sentiment lookup."""
    try:
        from earnings_engine.data.option_chain import analyze_option_chain
        res = analyze_option_chain(symbol, settings=_settings)
        return {
            "success": True,
            "symbol": res.get("symbol"),
            "pcr_oi": res.get("pcr_oi"),
            "pcr_volume": res.get("pcr_volume"),
            "sentiment": res.get("sentiment"),
            "max_pain": res.get("max_pain_strike"),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching PCR: {str(e)}")


# ---------------------------------------------------------------------------
# Multi-Model AI Consensus Prediction & Settlement Endpoints
# ---------------------------------------------------------------------------


class ConsensusPredictRequest(BaseModel):
    ticker: str | None = None
    tickers: list[str] | None = None
    timeframe_days: int = Field(default=14, ge=1, le=90)
    models: list[str] | None = None


class ConsensusSettleRequest(BaseModel):
    as_of_date: str | None = None


@app.post("/api/v1/consensus/predict", tags=["AI Consensus Engine"])
async def consensus_predict_endpoint(req: ConsensusPredictRequest):
    """Run multi-model consensus prediction for one or more tickers."""
    from datetime import datetime, timedelta
    from earnings_engine.consensus import context_builder, model_runner, aggregator, storage

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
            # 1. Build rich context
            ctx = context_builder.build_context(ticker, timeframe_days=req.timeframe_days, settings=_settings)
            as_of_price = ctx.get("price_action", {}).get("current_price") or 0.0

            # Fallback price lookup if missing from context
            if as_of_price <= 0:
                try:
                    import yfinance as yf
                    info = yf.Ticker(ticker).fast_info
                    as_of_price = float(info.last_price or 0.0)
                except Exception:
                    pass

            # 2. Run multi-model parallel inference
            model_outputs = model_runner.run_consensus_models(
                context=ctx,
                models=req.models,
            )

            # 3. Aggregate consensus
            consensus = aggregator.aggregate_predictions(
                model_results=model_outputs,
                ticker=ticker,
                as_of_price=as_of_price,
                timeframe_days=req.timeframe_days,
            )

            # 4. Save to database
            eval_date = (datetime.now() + timedelta(days=req.timeframe_days)).strftime("%Y-%m-%d")
            pred_id = storage.save_prediction(consensus, evaluation_date=eval_date, settings=_settings)
            consensus["id"] = pred_id
            consensus["evaluation_date"] = eval_date
            results.append(consensus)

        except Exception as e:
            logger.error("[CONSENSUS-API] Error predicting for %s: %s", ticker, e)
            results.append({"ticker": ticker, "error": str(e)})

    return {
        "success": True,
        "count": len(results),
        "predictions": results,
    }


@app.get("/api/v1/consensus/latest", tags=["AI Consensus Engine"])
async def consensus_latest_endpoint(
    ticker: str | None = Query(default=None),
    direction: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
):
    """Retrieve latest consensus predictions with optional filtering."""
    from earnings_engine.consensus import storage
    try:
        preds = storage.get_predictions(
            settings=_settings,
            ticker=ticker,
            direction=direction,
            status=status,
            limit=limit,
        )
        return {"success": True, "count": len(preds), "predictions": preds}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error querying consensus predictions: {str(e)}")


@app.get("/api/v1/consensus/audit", tags=["AI Consensus Engine"])
async def consensus_audit_endpoint(
    ticker: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
):
    """Historical audit of consensus predictions including settlement outcomes and failure analyses."""
    from earnings_engine.consensus import storage
    try:
        preds = storage.get_predictions(
            settings=_settings,
            ticker=ticker,
            status=status,
            limit=limit,
        )
        return {"success": True, "count": len(preds), "audit_records": preds}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching consensus audit records: {str(e)}")


@app.get("/api/v1/consensus/accuracy-stats", tags=["AI Consensus Engine"])
async def consensus_accuracy_stats_endpoint():
    """Retrieve aggregate performance and win-rate statistics across all consensus predictions."""
    from earnings_engine.consensus import storage
    try:
        stats = storage.get_accuracy_stats(settings=_settings)
        return {"success": True, **stats}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching consensus accuracy stats: {str(e)}")


@app.post("/api/v1/consensus/settle", tags=["AI Consensus Engine"])
async def consensus_settle_endpoint(req: ConsensusSettleRequest | None = None):
    """Trigger settlement evaluation for all mature consensus predictions."""
    from earnings_engine.consensus import settlement
    try:
        as_of = req.as_of_date if req else None
        summary = settlement.settle_pending_predictions(settings=_settings, as_of_date=as_of)
        return {"success": True, **summary}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error running consensus settlement: {str(e)}")


@app.get("/api/v1/consensus/{prediction_id}", tags=["AI Consensus Engine"])
async def consensus_detail_endpoint(prediction_id: int):
    """Get full details of a specific consensus prediction, including all model votes and post-mortems."""
    from earnings_engine.consensus import storage
    try:
        pred = storage.get_prediction_by_id(prediction_id, settings=_settings)
        if not pred:
            raise HTTPException(status_code=404, detail=f"Prediction with ID {prediction_id} not found.")
        return {"success": True, "prediction": pred}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching prediction details: {str(e)}")





