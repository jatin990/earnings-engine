"""FastAPI server exposing earnings-engine data via REST APIs."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from earnings_engine.config import Settings
from earnings_engine.data import earnings as earnings_mod
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
from pathlib import Path

app = FastAPI(
    title="Earnings Engine API",
    description="REST API for accessing earnings predictions and market data",
    version="1.0.0",
)

# Enable CORS for Postman and browser access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global settings instance
_settings = Settings()


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
async def get_market_cap(ticker: str):
    """Get current market cap for a ticker.
    
    - **ticker**: Stock ticker symbol (e.g., 'AAPL' or 'RELIANCE.NS')
    """
    try:
        from earnings_engine.data.universe import load_market_cap
        
        # Try cache first
        market_cap = load_market_cap(ticker, _settings)
        
        # If not in cache, fetch from yfinance
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
async def get_market_context(ticker: str):
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
        enriched = enrich_upcoming_results(df, _settings)
        
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
async def get_universe_files():
    """Get list of available universe files."""
    try:
        from pathlib import Path
        universe_dir = Path(__file__).resolve().parent.parent / "data" / "universes"
        files = []
        for f in universe_dir.glob("*.txt"):
            files.append(f.stem)
        return {"files": sorted(files)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing universe files: {str(e)}")


@app.get("/api/v1/universe/{market}", response_model=UniverseResponse, tags=["Universe"])
async def get_universe(market: str):
    """Get ticker universe for a market.
    
    - **market**: Market code (IN, US, NSE_ALL, NSE_LARGE_CAP)
    """
    try:
        market_upper = market.upper()
        if market_upper not in {"IN", "US", "NSE_ALL", "NSE_LARGE_CAP"}:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported market: {market}. Use IN, US, NSE_ALL, or NSE_LARGE_CAP"
            )
        
        tickers = load_universe(market_upper)
        return UniverseResponse(market=market_upper, tickers=tickers, count=len(tickers))
    except HTTPException:
        raise
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
async def add_to_universe(request: dict):
    """Add ticker(s) to a universe file.
    
    Request body:
    {
        "file": "nse_top",
        "tickers": ["RELIANCE.NS", "TCS.NS"]
    }
    """
    try:
        from pathlib import Path
        
        file_name = request.get("file", "")
        tickers = request.get("tickers", [])
        
        if not file_name or not tickers:
            raise HTTPException(status_code=400, detail="File name and tickers are required")
        
        # Validate file name
        universe_dir = Path(__file__).resolve().parent.parent / "data" / "universes"
        file_path = universe_dir / f"{file_name}.txt"
        
        if not file_path.exists():
            raise HTTPException(status_code=404, detail=f"Universe file not found: {file_name}")
        
        # Read existing tickers
        existing = set()
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    existing.add(line)
        
        # Add new tickers
        added = []
        for ticker in tickers:
            ticker = ticker.strip().upper()
            if ticker and ticker not in existing:
                existing.add(ticker)
                added.append(ticker)
        
        # Write back
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(f"# Updated: {pd.Timestamp.now().strftime('%Y-%m-%d')}\n")
            for ticker in sorted(existing):
                f.write(f"{ticker}\n")
        
        return {
            "success": True,
            "file": file_name,
            "added": added,
            "total": len(existing)
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error adding tickers: {str(e)}")


@app.post("/api/v1/universe/remove", tags=["Universe"])
async def remove_from_universe(request: dict):
    """Remove ticker(s) from a universe file.
    
    Request body:
    {
        "file": "nse_top",
        "tickers": ["RELIANCE.NS", "TCS.NS"]
    }
    """
    try:
        from pathlib import Path
        
        file_name = request.get("file", "")
        tickers = request.get("tickers", [])
        
        if not file_name or not tickers:
            raise HTTPException(status_code=400, detail="File name and tickers are required")
        
        # Validate file name
        universe_dir = Path(__file__).resolve().parent.parent / "data" / "universes"
        file_path = universe_dir / f"{file_name}.txt"
        
        if not file_path.exists():
            raise HTTPException(status_code=404, detail=f"Universe file not found: {file_name}")
        
        # Read existing tickers
        existing = set()
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    existing.add(line)
        
        # Remove tickers
        tickers_upper = {t.strip().upper() for t in tickers}
        removed = list(existing.intersection(tickers_upper))
        existing = existing - tickers_upper
        
        # Write back
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(f"# Updated: {pd.Timestamp.now().strftime('%Y-%m-%d')}\n")
            for ticker in sorted(existing):
                f.write(f"{ticker}\n")
        
        return {
            "success": True,
            "file": file_name,
            "removed": removed,
            "total": len(existing)
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
    dashboard_path = Path(__file__).resolve().parent.parent / "reports" / "templates" / "dashboard.html"
    if dashboard_path.exists():
        return HTMLResponse(dashboard_path.read_text(encoding="utf-8"))
    return HTMLResponse(
        "<html><body><h1>Dashboard template not found</h1><p>Run from the repo root.</p></body></html>",
        status_code=404,
    )


# ---------------------------------------------------------------------------
# Dashboard Data Endpoints
# ---------------------------------------------------------------------------

from earnings_engine.api.dashboard_api import (
    add_to_watchlist,
    create_universe_file,
    delete_kronos_prediction,
    generate_watchlist_kronos,
    get_event_dataset_summary,
    get_kronos_latest_predictions,
    get_kronos_predictions,
    get_kronos_predictions_audit,
    get_kronos_predictions_for_ticker,
    get_refresh_status,
    get_swing_setups,
    get_tab_refresh_status,
    get_universe_files,
    get_upcoming_results,
    get_watchlist,
    refresh_data,
    remove_from_watchlist,
    summarize_results_with_llm,
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
    days: int = Query(14, description="Look-ahead window in days", ge=1, le=90),
    market: str | None = Query(None, description="Market universe (IN, US, NSE_ALL, NSE_LARGE_CAP)"),
):
    """Get upcoming earnings results with market context for the dashboard Results tab."""
    try:
        return get_upcoming_results(days=days, market=market)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching dashboard results: {str(e)}")


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


@app.get("/api/v1/dashboard/kronos", tags=["Dashboard"])
async def dashboard_kronos(
    tickers: str | None = Query(None, description="Comma-separated ticker list"),
    lookback: int = Query(120, description="Historical lookback days"),
    pred_len: int = Query(14, description="Prediction horizon days"),
):
    """Get Kronos AI predictions for the Kronos tab."""
    try:
        ticker_list = [t.strip() for t in tickers.split(",") if t.strip()] if tickers else None
        return get_kronos_predictions(tickers=ticker_list, lookback=lookback, pred_len=pred_len)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching Kronos predictions: {str(e)}")


@app.post("/api/v1/dashboard/kronos/run", tags=["Dashboard"])
async def dashboard_kronos_run(request: dict):
    """Run Kronos AI predictions on-demand for the given tickers.

    Each generated forecast is persisted to the ``kronos_predictions`` audit
    table automatically, so it appears in the Audit view.
    """
    try:
        tickers = request.get("tickers", [])
        lookback = request.get("lookback", 120)
        pred_len = request.get("pred_len", 14)
        return get_kronos_predictions(tickers=tickers or None, lookback=lookback, pred_len=pred_len)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error running Kronos predictions: {str(e)}")


@app.get("/api/v1/dashboard/kronos/latest", tags=["Dashboard"])
async def dashboard_kronos_latest(
    tickers: str | None = Query(None, description="Comma-separated ticker list to filter the latest predictions"),
):
    """Get the most-recent Kronos prediction per ticker (Latest tab)."""
    try:
        ticker_list = [t.strip() for t in tickers.split(",") if t.strip()] if tickers else None
        return get_kronos_latest_predictions(tickers=ticker_list)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching latest Kronos predictions: {str(e)}")


@app.get("/api/v1/dashboard/kronos/audit", tags=["Dashboard"])
async def dashboard_kronos_audit(
    tickers: str | None = Query(None, description="Comma-separated ticker list to filter the audit"),
    limit: int | None = Query(None, description="Max number of audit rows to return (most recent first)"),
):
    """Get the full audit history of Kronos predictions (Audit tab)."""
    try:
        ticker_list = [t.strip() for t in tickers.split(",") if t.strip()] if tickers else None
        return get_kronos_predictions_audit(tickers=ticker_list, limit=limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching Kronos audit: {str(e)}")


@app.get("/api/v1/dashboard/kronos/history/{ticker}", tags=["Dashboard"])
async def dashboard_kronos_ticker_history(ticker: str):
    """Get all historical predictions for a specific ticker."""
    try:
        return get_kronos_predictions_for_ticker(ticker)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching Kronos history: {str(e)}")


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
        return delete_kronos_prediction(ticker_decoded, run_at_decoded)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting Kronos prediction: {str(e)}")


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


@app.get("/api/v1/watchlist", tags=["Dashboard"])
async def watchlist_get():
    """Get the current watchlist from the server-side file."""
    return {"tickers": get_watchlist()}


@app.post("/api/v1/watchlist/add", tags=["Dashboard"])
async def watchlist_add(request: dict):
    """Add a ticker to the server-side watchlist file."""
    ticker = request.get("ticker", "")
    result = add_to_watchlist(ticker)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to add ticker"))
    return result


@app.post("/api/v1/watchlist/remove", tags=["Dashboard"])
async def watchlist_remove(request: dict):
    """Remove a ticker from the server-side watchlist file."""
    ticker = request.get("ticker", "")
    result = remove_from_watchlist(ticker)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to remove ticker"))
    return result
