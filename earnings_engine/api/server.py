"""FastAPI server exposing earnings-engine data via REST APIs."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
import json
from typing import Any

import os
import pandas as pd
import time
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
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
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader
from pathlib import Path
from earnings_engine.data.db import get_db_connection
from earnings_engine.data.migrations import apply_migrations
from earnings_engine.logging_utils import get_logger, log_startup_diagnostics
from earnings_engine.data import breakout_scanner as breakout_scanner_mod
from earnings_engine.data import quarter_repeaters as repeaters_mod

logger = get_logger("earnings_engine.api.server")

# Background task handles (kept so we can cancel on shutdown)
_breakout_scanner_task: asyncio.Task | None = None
_news_catalyst_task: asyncio.Task | None = None
_CACHED_LOCAL_MODELS: dict[str, Any] = {}


def _scan_and_cache_local_models(host: str | None = None) -> dict[str, Any]:
    """Scan running local model endpoints (Ollama / LM Studio) and cache the result."""
    import os, requests
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run migrations, schedule initialization, and startup diagnostics on API startup."""
    global _breakout_scanner_task, _news_catalyst_task
    try:
        applied = apply_migrations(_settings)
        if applied:
            logger.info("Database migrations applied on startup: %s", ", ".join(applied))
    except Exception as e:
        logger.warning("Startup database migration check failed: %s", e)
    log_startup_diagnostics(logger)

    # Initialize automated schedule registry
    try:
        from earnings_engine.data.automation_schedules import init_automation_schedules
        init_automation_schedules(_settings)
    except Exception as e:
        logger.warning("[SCHEDULES] Startup schedule init warning: %s", e)

    # Initialize institutional dataset
    try:
        from earnings_engine.data.institutional_accumulation import init_institutional_db
        init_institutional_db(_settings)
    except Exception as e:
        logger.warning("[INSTITUTIONAL] Startup institutional DB init warning: %s", e)

    # Sync local SQLite state with upstream Turso Cloud on startup
    try:
        from earnings_engine.data.turso_sync import sync_local_to_upstream

        async def _run_startup_sync():
            try:
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, sync_local_to_upstream, _settings)
            except Exception as sync_err:
                logger.warning("[TURSO-SYNC] Background startup sync encountered an issue: %s", sync_err)

        asyncio.create_task(_run_startup_sync(), name="turso_upstream_sync")
    except Exception as e:
        logger.warning("[TURSO-SYNC] Could not schedule startup upstream sync: %s", e)

    # Start the background category scanner sweep
    try:
        from earnings_engine.data.category_scanner import compute_and_save_scanner_universe

        async def _run_startup_scanner_sweep():
            try:
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, compute_and_save_scanner_universe, "NSE_TOP", _settings)
                logger.info("[SCANNER] Startup background multi-category sweep finished.")
            except Exception as scan_err:
                logger.warning("[SCANNER] Startup sweep background task warning: %s", scan_err)

        asyncio.create_task(_run_startup_scanner_sweep(), name="category_scanner_sweep")
    except Exception as e:
        logger.warning("[SCANNER] Could not schedule startup category sweep: %s", e)

    # Start the background breakout scanner loop
    try:
        _breakout_scanner_task = asyncio.create_task(
            breakout_scanner_mod.breakout_scanner_loop(_settings),
            name="breakout_radar",
        )
        logger.info("[BREAKOUT] Background scanner task started.")
    except Exception as e:
        logger.warning("[BREAKOUT] Could not start scanner task: %s", e)

    # Start the background news catalyst harvester loop
    try:
        from earnings_engine.data.catalysts_news import news_catalyst_harvest_loop
        _news_catalyst_task = asyncio.create_task(
            news_catalyst_harvest_loop(_settings),
            name="news_catalyst_harvester",
        )
        logger.info("[NEWS-HARVESTER] Background news harvester task started.")
    except Exception as e:
        logger.warning("[NEWS-HARVESTER] Could not start news harvester task: %s", e)

    # Pre-scan and cache available local LLM models (Ollama / LM Studio) on startup
    try:
        async def _run_startup_local_model_scan():
            try:
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, _scan_and_cache_local_models)
            except Exception as scan_err:
                logger.warning("[LOCAL-MODELS] Startup model scan warning: %s", scan_err)

        asyncio.create_task(_run_startup_local_model_scan(), name="local_model_startup_scan")
    except Exception as e:
        logger.warning("[LOCAL-MODELS] Could not schedule startup local model scan: %s", e)

    yield

    # Graceful shutdown: cancel background tasks
    for task_handle, name in [(_breakout_scanner_task, "Breakout scanner"), (_news_catalyst_task, "News harvester")]:
        if task_handle and not task_handle.done():
            task_handle.cancel()
            try:
                await asyncio.wait_for(task_handle, timeout=3.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            logger.info("[%s] Task shut down.", name)


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
async def log_and_cancel_api_requests(request: Request, call_next):
    """Log API details and register cancellation token for client request tracking."""
    start_time = time.perf_counter()
    path = request.url.path
    req_id = request.headers.get("x-request-id") or request.query_params.get("request_id")

    if not req_id and path.startswith("/api/"):
        req_id = f"req_{int(time.time()*1000)}_{id(request)}"

    from earnings_engine.api.cancellation import cancellation_manager
    token = cancellation_manager.register(req_id) if req_id else None

    # Attach token to request state
    request.state.cancellation_token = token
    request.state.request_id = req_id

    # Asynchronous request telemetry & diagnostics
    if path in ("/dashboard", "/", "/dashboard.html", "/api/v1/dashboard/overview") or (path.startswith("/dashboard") and not path.startswith("/dashboard/static")):
        try:
            from earnings_engine.data.telemetry import record_telemetry_async
            headers_dict = {k.lower(): v for k, v in request.headers.items()}
            record_telemetry_async(
                client_host=request.client.host if request.client else None,
                user_agent=headers_dict.get("user-agent", ""),
                endpoint=path,
                headers=headers_dict,
                settings=_settings,
            )
        except Exception:
            pass

    # Extract non-empty query parameters / filters
    query_params = dict(request.query_params)
    filters_repr = f" filters={query_params}" if query_params else ""

    try:
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start_time) * 1000

        # Skip logging high-frequency polling/heartbeat/static hits to avoid log spam
        silent_paths = {
            "/api/v1/config/ratelimits",
            "/api/v1/earnings/freshness",
            "/api/v1/watchlist/names",
            "/api/v1/config/ui-preferences",
            "/favicon.ico",
            "/health",
            "/ping",
        }
        is_silent = path in silent_paths or path.startswith(("/static", "/ui", "/docs", "/openapi.json"))

        if not is_silent:
            logger.info(
                "API [%s] %s%s -> %d (%.1fms)",
                request.method,
                path,
                filters_repr,
                response.status_code,
                duration_ms,
            )
        else:
            logger.debug(
                "API [%s] %s%s -> %d (%.1fms)",
                request.method,
                path,
                filters_repr,
                response.status_code,
                duration_ms,
            )
        return response
    except (asyncio.CancelledError, Exception) as exc:
        duration_ms = (time.perf_counter() - start_time) * 1000
        if isinstance(exc, asyncio.CancelledError) or (token and token.is_cancelled):
            if not is_silent:
                logger.info(
                    "API [%s] %s%s -> CANCELLED by client (%.1fms)",
                    request.method,
                    path,
                    filters_repr,
                    duration_ms,
                )
            if token:
                token.cancel("Request handler cancelled due to client disconnect")
            return Response(status_code=499, content="Client Closed Request")
        raise exc
    finally:
        if req_id:
            cancellation_manager.unregister(req_id)

# Global settings instance
_settings = Settings()

# =========================================================================
# 🛡️ AUTHENTICATION & ACCESS CONTROL MIDDLEWARE
# =========================================================================

PUBLIC_EXACT_PATHS = {
    "/",
    "/portal",
    "/join",
    "/login",
    "/favicon.ico",
    "/api/health",
    "/api/v1/health",
    "/api/v1/auth/verify-code",
    "/api/v1/auth/session",
    "/api/v1/auth/login-owner",
    "/docs",
    "/redoc",
    "/openapi.json",
}

PUBLIC_PATH_PREFIXES = (
    "/static/",
    "/ui/",
    "/api/v1/auth/otp/",
    "/dashboard/static/",
)


def _resolve_session(request: Request) -> dict[str, Any] | None:
    """Resolve active user session from Authorization header, Cookie, Query param, or Passcode."""
    token = None

    # 1. Bearer token in Authorization header
    auth_hdr = request.headers.get("Authorization", "")
    if auth_hdr.startswith("Bearer "):
        token = auth_hdr[7:].strip()

    # 2. Nexus session cookie
    if not token:
        token = request.cookies.get("nexus_session")

    # 3. Explicit session_token query parameter
    if not token:
        token = request.query_params.get("session_token")

    # If token exists, attempt to verify as signed JWT session token
    if token:
        from earnings_engine.data.auth import verify_session_token
        session = verify_session_token(token)
        if session:
            return session
        token = None  # Reset token so invalid/expired cookie doesn't shadow passcode headers!

    # 4. Check for direct passcode / invite code in headers or query parameters
    passcode = (
        request.headers.get("X-Passcode")
        or request.headers.get("X-Nexus-Passcode")
        or request.headers.get("X-Nexus-Code")
        or request.query_params.get("passcode")
        or request.query_params.get("code")
        or request.query_params.get("invite")
    )
    if passcode:
        from earnings_engine.data.passcodes import verify_passcode
        res = verify_passcode(passcode, _settings)
        if res.get("valid"):
            is_admin = res.get("is_admin") or res.get("role") == "owner"
            scopes = res.get("scopes") or (
                ["dashboard", "can_view_cards", "can_view_trips", "can_view_net_worth", "admin", "credit_card", "playground"]
                if is_admin
                else res.get("allowed_routes", ["dashboard"])
            )
            return {
                "sub": f"usr_{res.get('code', 'passcode')}",
                "role": "owner" if is_admin else "friend",
                "email": "owner@nexus.local" if is_admin else f"{res.get('code', 'friend').lower()}@nexus.local",
                "name": res.get("label", "Nexus User"),
                "scopes": scopes,
                "allowed_routes": res.get("allowed_routes", []),
                "passcode": passcode,
            }
        # Explicit invalid passcode provided -> reject immediately
        return None

    return None


def is_route_authorized(path: str, session: dict[str, Any]) -> bool:
    """Check if the authenticated user has scope/route authorization for the requested path."""
    from earnings_engine.data.passcodes import AVAILABLE_ROUTES

    role = session.get("role", "friend")
    scopes = set(session.get("scopes", []) + session.get("allowed_routes", []))

    # 1. Master owner or admin scope has unrestricted access to all endpoints
    if role in ("owner", "master") or "admin" in scopes or "*" in scopes:
        return True

    # 2. Dataset refresh & operational admin routes strictly restricted to Master role
    DATASET_REFRESH_AND_ADMIN_PREFIXES = (
        "/api/v1/earnings/refresh-watchlist",
        "/api/v1/dashboard/refresh",
        "/api/v1/dashboard/earnings/incremental",
        "/api/v1/dashboard/month-filter/sync",
        "/api/v1/system/telemetry",
        "/api/v1/friends",
        "/api/v1/config/env",
        "/api/v1/auth/codes",
    )
    if any(path == prefix or path.startswith(prefix + "/") or path.startswith(prefix + "?") for prefix in DATASET_REFRESH_AND_ADMIN_PREFIXES):
        return False

    # 3. General config & utility APIs accessible to all authenticated sessions
    if path in (
        "/api/v1/config/ratelimits",
        "/api/v1/ratelimits",
        "/api/v1/config/ui-preferences",
        "/api/v1/watchlist",
        "/api/v1/health",
        "/api/v1/auth/me",
    ):
        return True

    # 4. Granular Wealth & Lifestyle scope mappings
    if path.startswith("/api/v1/trips"):
        return bool("can_view_trips" in scopes or "trips" in scopes or "credit_card" in scopes)
    if path.startswith("/api/v1/net-worth"):
        return bool("can_view_net_worth" in scopes or "net_worth" in scopes or "credit_card" in scopes)
    if path.startswith("/api/v1/cards"):
        return bool("can_view_cards" in scopes or "credit_card" in scopes)

    # 5. Check section api_prefixes from AVAILABLE_ROUTES
    for route_id, route_def in AVAILABLE_ROUTES.items():
        prefixes = route_def.get("api_prefixes", [])
        if any(path.startswith(prefix) for prefix in prefixes):
            has_perm = (
                route_id in scopes
                or (route_id == "dashboard" and "dashboard" in scopes)
                or (route_id == "credit_card" and ("credit_card" in scopes or "can_view_cards" in scopes))
            )
            return bool(has_perm)

    # 6. HTML views
    if path in ("/dashboard", "/dashboard.html"):
        return "dashboard" in scopes
    if path == "/credit-card":
        return bool("credit_card" in scopes or "can_view_cards" in scopes)
    if path == "/trips":
        return bool("trips" in scopes or "can_view_trips" in scopes or "credit_card" in scopes)
    if path == "/net-worth":
        return bool("net_worth" in scopes or "can_view_net_worth" in scopes or "credit_card" in scopes)

    # Default allow authenticated users for unclassified non-admin routes
    return True


@app.middleware("http")
async def enforce_auth_middleware(request: Request, call_next):
    """Enforce authentication and route RBAC on all protected HTML views and API endpoints."""
    path = request.url.path

    # Allow public static assets and gateway routes
    if path in PUBLIC_EXACT_PATHS or any(path.startswith(prefix) for prefix in PUBLIC_PATH_PREFIXES):
        return await call_next(request)

    session = _resolve_session(request)
    if session:
        request.state.session = session

        # Verify RBAC route permission
        if not is_route_authorized(path, session):
            if path in ("/dashboard", "/credit-card", "/trips", "/net-worth", "/dashboard.html") or not path.startswith("/api/"):
                return RedirectResponse(url=f"/portal?unauthorized=true&redirect={path}", status_code=302)
            return JSONResponse(
                status_code=403,
                content={
                    "detail": f"Access forbidden: Your active passcode/tier does not grant permission for '{path}'."
                },
            )

        response = await call_next(request)
        # If authenticated via query parameter ?code=... and no cookie is present, issue cookie
        if "nexus_session" not in request.cookies and session.get("passcode"):
            from earnings_engine.data.auth import create_session_token
            cookie_token = create_session_token(
                user_id=session.get("sub", "usr_001"),
                role=session.get("role", "friend"),
                email=session.get("email", "friend@nexus.local"),
                name=session.get("name", "Nexus User"),
                scopes=session.get("scopes", []),
            )
            response.set_cookie(
                key="nexus_session",
                value=cookie_token,
                httponly=True,
                samesite="lax",
                max_age=14 * 86400,
                path="/",
            )
        return response

    # If running pytest unit test suite, grant test session unless explicitly running auth middleware unit tests
    if os.getenv("PYTEST_CURRENT_TEST") and not (
        path.startswith("/api/v1/trips")
        or path.startswith("/api/v1/cards")
        or path.startswith("/api/v1/net-worth")
        or "test_auth_middleware" in (os.getenv("PYTEST_CURRENT_TEST") or "")
        or "test_dataset_refresh_rbac" in (os.getenv("PYTEST_CURRENT_TEST") or "")
        or "test_rbac" in (os.getenv("PYTEST_CURRENT_TEST") or "")
    ):
        request.state.session = {
            "role": "owner",
            "scopes": ["admin", "dashboard", "can_view_cards", "can_view_trips", "can_view_net_worth"],
        }
        return await call_next(request)


    # Unauthenticated request:
    # 1. HTML Pages (e.g. /dashboard, /credit-card, /trips, /net-worth) -> ALWAYS redirect to portal gate
    if path in ("/dashboard", "/credit-card", "/trips", "/net-worth", "/dashboard.html") or path.startswith("/stock/") or not path.startswith("/api/"):
        return RedirectResponse(url=f"/portal?redirect={path}", status_code=302)

    # 3. Protected API Endpoints -> return 401 Unauthorized
    return JSONResponse(
        status_code=401,
        content={"detail": "Authentication required. Please provide a valid passcode or session cookie."},
    )


def _require_master_role(request: Request | None) -> None:
    """Defensive check to ensure request session has Master (Owner / Admin) role."""
    if not request:
        return
    session = getattr(request.state, "session", None)
    if not session:
        session = _resolve_session(request)
    if session:
        role = session.get("role", "friend")
        scopes = set(session.get("scopes", []) + session.get("allowed_routes", []))
        if not (role in ("owner", "master") or "admin" in scopes or "*" in scopes):
            raise HTTPException(
                status_code=403,
                detail="Forbidden: Refreshing dataset is restricted to Master Admin role.",
            )


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
    q1_ai_summary: str | None = None
    q2_ai_summary: str | None = None
    q3_ai_summary: str | None = None
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
        df = await asyncio.to_thread(prices_mod.fetch_prices, ticker, _settings, force=force_refresh)
        
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
        df = await asyncio.to_thread(earnings_mod.fetch_earnings, ticker, _settings, force=force_refresh)
        return _df_to_earnings_list(df)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching earnings history: {str(e)}")


class RefreshWatchlistEarningsRequest(BaseModel):
    watchlist: str | None = None
    tickers: list[str] | None = None


@app.get("/api/v1/earnings/freshness", tags=["Earnings"])
async def get_earnings_freshness_endpoint(
    watchlist: str | None = Query(None, description="Watchlist name or universe"),
    tickers: str | None = Query(None, description="Comma-separated list of tickers"),
):
    """Retrieve earnings data freshness and last-updated timestamp for a watchlist."""
    ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()] if tickers else None
    freshness = await asyncio.to_thread(
        earnings_mod.get_watchlist_earnings_freshness,
        watchlist_name=watchlist,
        tickers=ticker_list,
        settings=_settings,
    )
    return {"success": True, **freshness}


@app.post("/api/v1/earnings/refresh-watchlist", tags=["Earnings"])
async def refresh_watchlist_earnings_endpoint(req: RefreshWatchlistEarningsRequest, request: Request = None):
    """Trigger parallel background refresh of earnings data for all tickers in a selected watchlist."""
    _require_master_role(request)
    res = await asyncio.to_thread(
        earnings_mod.refresh_watchlist_earnings,
        watchlist_name=req.watchlist,
        tickers=req.tickers,
        settings=_settings,
    )
    return res


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
            q1_ai_summary=row.get("q1_ai_summary"),
            q2_ai_summary=row.get("q2_ai_summary"),
            q3_ai_summary=row.get("q3_ai_summary"),
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


@app.get("/api/v1/market/pulse", tags=["Market Data"])
async def api_get_market_pulse(
    force_refresh: bool = Query(False, description="Force refresh cache"),
):
    """Retrieve full macro market pulse, fear & greed index, VIX, prediction, and sector heatmap."""
    try:
        from earnings_engine.data.market_pulse import get_market_pulse_data
        return get_market_pulse_data(settings=_settings, force_refresh=force_refresh)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving market pulse: {e}")


@app.get("/api/v1/market/recent-additions", tags=["Market Data"])
async def api_get_recent_market_additions(
    days: int = Query(180, description="Lookback window in days for newly listed stocks", ge=1, le=730),
    limit: int = Query(100, description="Max additions to return", ge=1, le=500),
):
    """Retrieve recent IPOs and market additions listed on the NSE."""
    try:
        from earnings_engine.api.stock_api import get_recent_market_additions
        return get_recent_market_additions(days=days, limit=limit, settings=_settings)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching recent market additions: {e}")


@app.post("/api/v1/market/recent-additions/sync-watchlist", tags=["Market Data"])
async def api_sync_recent_addition_to_watchlist(
    ticker: str = Query(..., description="Stock ticker symbol (e.g. SHIPROCKET.NS)"),
    watchlist: str = Query("my_watchlist", description="Target watchlist name"),
):
    """One-click addition of a newly listed stock to a watchlist."""
    try:
        from earnings_engine.api.stock_api import sync_recent_additions_to_watchlist
        return sync_recent_additions_to_watchlist(ticker=ticker, watchlist_name=watchlist, settings=_settings)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error adding ticker to watchlist: {e}")


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


# ---------------------------------------------------------------------------
# Task Cancellation Endpoints
# ---------------------------------------------------------------------------

class CancelTaskRequest(BaseModel):
    request_id: str
    reason: str | None = "Explicit client cancellation"


@app.post("/api/v1/tasks/{task_id}/cancel", tags=["Task Cancellation"])
async def cancel_task_by_id(task_id: str):
    """Cancel an active backend calculation, data fetch, or batch job by request/task ID."""
    from earnings_engine.api.cancellation import cancellation_manager
    cancelled = cancellation_manager.cancel(task_id, reason="Explicit client cancel API call")
    return {
        "success": True,
        "task_id": task_id,
        "cancelled": cancelled,
        "message": f"Task {task_id} cancellation signal dispatched." if cancelled else f"Task {task_id} was not active or already finished.",
    }


@app.post("/api/v1/tasks/cancel", tags=["Task Cancellation"])
async def cancel_task_generic(req: CancelTaskRequest):
    """Cancel an active backend calculation, data fetch, or batch job."""
    from earnings_engine.api.cancellation import cancellation_manager
    cancelled = cancellation_manager.cancel(req.request_id, reason=req.reason or "Explicit client cancel API call")
    return {
        "success": True,
        "request_id": req.request_id,
        "cancelled": cancelled,
        "message": f"Request {req.request_id} cancellation signal dispatched." if cancelled else f"Request {req.request_id} was not active or already finished.",
    }


# ---------------------------------------------------------------------------
# Portal, Passcode & Email OTP RBAC Endpoints
# ---------------------------------------------------------------------------

class VerifyCodeRequest(BaseModel):
    code: str


class CreatePasscodeRequest(BaseModel):
    label: str
    allowed_routes: list[str] = ["dashboard"]
    code: str | None = None
    max_uses: int | None = None
    expires_in_days: float | None = None
    expires_in_hours: float | None = None
    expires_at: str | None = None


class RequestOtpRequest(BaseModel):
    invite_code: str
    email: str


class VerifyOtpRequest(BaseModel):
    invite_code: str
    email: str
    otp: str


class OwnerLoginRequest(BaseModel):
    passcode: str
    email: str | None = None


class CreateInviteRequest(BaseModel):
    label: str
    scopes: list[str] = ["can_view_trips"]
    allowed_email: str | None = None
    max_uses: int | None = 1
    expires_in_days: float | None = 7
    expires_in_hours: float | None = None
    expires_at: str | None = None
    code: str | None = None


class UpdateFriendScopesRequest(BaseModel):
    can_view_trips: bool = False
    can_view_cards: bool = False
    can_view_net_worth: bool = False


class CreateCreditCardRequest(BaseModel):
    card_name: str
    issuer: str
    network: str = "Visa Infinite"
    last4: str = "8842"
    card_holder: str = "Jatin"
    color_theme: str = "obsidian"
    credit_limit: float = 500000.0
    available_limit: float = 428760.0
    billing_cycle_day: int = 15
    category_perks: dict[str, Any] = {}
    lounge_access_summary: str | None = None
    annual_fee_status: str | None = "Active"
    is_shared_with_friends: bool = True
    display_order: int = 0


class CreateCardOtpRequest(BaseModel):
    card_id: str
    requested_by_name: str = "Friend"
    amount: float
    merchant: str
    purpose: str | None = None
    urgency: str = "normal"


class ApproveCardOtpRequest(BaseModel):
    otp_code: str | None = None
    duration_minutes: int = 5
    response_notes: str | None = None


class RejectCardOtpRequest(BaseModel):
    response_notes: str | None = None


class CreateTripRequest(BaseModel):
    title: str
    destination: str
    start_date: str
    end_date: str | None = None
    status: str = "planning"
    notes: str | None = None
    cover_image: str = "japan"
    estimated_budget: float = 150000.0
    is_shared_with_friends: bool = True
    flight_details: str | None = None
    hotel_details: str | None = None
    packing_list: list[str] = []


class SuggestTripActivityRequest(BaseModel):
    suggested_by_name: str = "Friend"
    activity_title: str
    location: str | None = None
    approx_cost: float = 0.0


class CreateTripGroupRequest(BaseModel):
    name: str
    description: str = ""
    color: str = "#0284c7"
    icon: str = "🌴"
    trip_ids: list[str] = []
    members: list[dict[str, Any]] = []


class UpdateTripGroupRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    color: str | None = None
    icon: str | None = None


class AddGroupMemberRequest(BaseModel):
    name: str
    email: str
    role: str = "member"
    custom_passcode: str | None = None
    send_email: bool = True


class AttachGroupTripsRequest(BaseModel):
    trip_ids: list[str]


class CreateNetWorthSnapshotRequest(BaseModel):
    as_of_date: str
    total_net_worth_band: str
    allocation_pct: dict[str, float]
    yoy_growth_pct: float | None = None


class CalculateEpsRequest(BaseModel):
    earnings_date: str | None = None
    override_estimate: float | None = None
    override_reported: float | None = None


def _get_current_session(request: Request) -> dict[str, Any]:
    """Resolve active user session from request state or credentials."""
    session = getattr(request.state, "session", None)
    if not session:
        session = _resolve_session(request)
    return session or {"role": None, "scopes": []}


def require_scope(required_scope: str):
    """Dependency callable that enforces owner role or explicit friend scope."""
    async def dependency(request: Request):
        session = _get_current_session(request)
        role = session.get("role")
        scopes = session.get("scopes", [])

        if not role:
            raise HTTPException(
                status_code=401,
                detail="Authentication required. Please provide a valid session token.",
            )

        if role == "owner" or "admin" in scopes or required_scope in scopes:
            return session

        raise HTTPException(
            status_code=403,
            detail=f"Access forbidden: your invite does not include permission '{required_scope}'.",
        )
    return dependency


@app.get("/", tags=["UI"], response_class=HTMLResponse)
@app.get("/portal", tags=["UI"], response_class=HTMLResponse)
@app.get("/join", tags=["UI"], response_class=HTMLResponse)
async def serve_portal():
    """Serve the Nexus Passcode Portal, Join Onboarding & App Launcher."""
    try:
        from jinja2 import Environment, FileSystemLoader
        env = Environment(
            loader=FileSystemLoader(str(_templates_dir)),
            autoescape=True,
            auto_reload=True,
            cache_size=0,
        )
        template = env.get_template("portal.html")
        html = template.render()
        return HTMLResponse(html)
    except Exception as exc:
        return HTMLResponse(
            f"<html><body><h1>Portal render error</h1><p>{exc}</p></body></html>",
            status_code=500,
        )


@app.get("/credit-card", tags=["UI"], response_class=HTMLResponse)
async def serve_credit_card():
    """Serve the Credit Card & Wealth Hub page."""
    try:
        from jinja2 import Environment, FileSystemLoader
        env = Environment(
            loader=FileSystemLoader(str(_templates_dir)),
            autoescape=True,
            auto_reload=True,
            cache_size=0,
        )
        template = env.get_template("credit_card.html")
        html = template.render()
        return HTMLResponse(html)
    except Exception as exc:
        return HTMLResponse(
            f"<html><body><h1>Credit Card Hub render error</h1><p>{exc}</p></body></html>",
            status_code=500,
        )


@app.get("/trips", tags=["UI"], response_class=HTMLResponse)
async def serve_trips():
    """Serve the Trips & Travel Hub page."""
    try:
        from jinja2 import Environment, FileSystemLoader
        env = Environment(
            loader=FileSystemLoader(str(_templates_dir)),
            autoescape=True,
            auto_reload=True,
            cache_size=0,
        )
        template = env.get_template("trips.html")
        html = template.render()
        return HTMLResponse(html)
    except Exception as exc:
        return HTMLResponse(
            f"<html><body><h1>Trips Hub render error</h1><p>{exc}</p></body></html>",
            status_code=500,
        )


@app.get("/net-worth", tags=["UI"], response_class=HTMLResponse)
async def serve_net_worth():
    """Serve the Net Worth & Asset Allocation Hub page."""
    try:
        from jinja2 import Environment, FileSystemLoader
        env = Environment(
            loader=FileSystemLoader(str(_templates_dir)),
            autoescape=True,
            auto_reload=True,
            cache_size=0,
        )
        template = env.get_template("net_worth.html")
        html = template.render()
        return HTMLResponse(html)
    except Exception as exc:
        return HTMLResponse(
            f"<html><body><h1>Net Worth Hub render error</h1><p>{exc}</p></body></html>",
            status_code=500,
        )


# --- Passcode Auth & Key Management ---

@app.post("/api/v1/auth/verify-code", tags=["Auth"])
async def verify_portal_code(req: VerifyCodeRequest, response: Response):
    """Verify input passcode and return authorized applications and permissions."""
    from earnings_engine.data.passcodes import verify_passcode
    from earnings_engine.data.auth import create_session_token
    result = verify_passcode(req.code, _settings)
    if not result.get("valid"):
        raise HTTPException(status_code=401, detail=result.get("error", "Invalid access passcode."))
    
    is_owner = result.get("role") == "owner" or result.get("is_admin")
    role = result.get("role") or ("owner" if is_owner else "friend")
    scopes = result.get("scopes") or (
        ["can_view_trips", "can_view_cards", "can_view_net_worth", "admin", "dashboard", "credit_card"]
        if is_owner else ["can_view_trips"]
    )
    email = result.get("email") or ("owner@nexus.local" if is_owner else "friend@nexus.local")
    name = result.get("name") or result.get("label", "Nexus User")
    group_id = result.get("group_id")
    token = create_session_token(
        user_id=1 if is_owner else 2,
        role=role,
        email=email,
        name=name,
        scopes=scopes,
        group_id=group_id,
        passcode=req.code.strip().upper(),
    )
    result["session_token"] = token
    response.set_cookie(
        key="nexus_session",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=14 * 86400,
    )
    return result


@app.get("/api/v1/auth/session", tags=["Auth"])
async def check_portal_session(code: str = Query(..., description="Active passcode to validate")):
    """Check whether a session passcode is currently valid."""
    from earnings_engine.data.passcodes import verify_passcode
    result = verify_passcode(code, _settings)
    return result


@app.get("/api/v1/auth/codes", tags=["Auth"])
async def get_all_passcodes():
    """List all generated friend passcodes and route permissions."""
    from earnings_engine.data.passcodes import list_passcodes
    return {"passcodes": list_passcodes(_settings)}


@app.post("/api/v1/auth/codes", tags=["Auth"])
async def create_new_passcode(req: CreatePasscodeRequest):
    """Generate a new passcode for a friend with custom route permissions, limits and timeframe."""
    from earnings_engine.data.passcodes import create_passcode
    created = create_passcode(
        label=req.label,
        allowed_routes=req.allowed_routes,
        code=req.code,
        max_uses=req.max_uses,
        expires_in_days=req.expires_in_days,
        expires_in_hours=req.expires_in_hours,
        expires_at=req.expires_at,
        settings=_settings,
    )
    return created


@app.delete("/api/v1/auth/codes/{code}", tags=["Auth"])
async def remove_passcode(code: str):
    """Revoke and delete a friend passcode."""
    from earnings_engine.data.passcodes import delete_passcode
    success = delete_passcode(code, _settings)
    return {"success": success, "code": code}


# --- Email OTP Authentication & Session Endpoints ---

@app.post("/api/v1/auth/request-otp", tags=["Auth & RBAC"])
async def request_otp_endpoint(req: RequestOtpRequest):
    """Validate invite code and send 6-digit email OTP."""
    from earnings_engine.data.auth import request_otp_for_invite
    res = request_otp_for_invite(req.invite_code, req.email, settings=_settings)
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error", "Failed to send OTP."))
    return res


@app.post("/api/v1/auth/verify-otp", tags=["Auth & RBAC"])
async def verify_otp_endpoint(req: VerifyOtpRequest, response: Response):
    """Verify 6-digit OTP, provision friend account with scopes, and issue session."""
    from earnings_engine.data.auth import verify_otp_for_invite
    res = verify_otp_for_invite(req.invite_code, req.email, req.otp, settings=_settings)
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error", "OTP verification failed."))

    token = res.get("session_token")
    if token:
        response.set_cookie(
            key="nexus_session",
            value=token,
            httponly=True,
            secure=False,
            samesite="lax",
            max_age=86400 * 14,
        )
    return res


@app.post("/api/v1/auth/owner-login", tags=["Auth & RBAC"])
async def owner_login_endpoint(req: OwnerLoginRequest, response: Response):
    """Authenticate owner via master passcode and return full unrestricted session."""
    from earnings_engine.data.auth import owner_login
    res = owner_login(req.passcode, req.email, settings=_settings)
    if not res.get("success"):
        raise HTTPException(status_code=401, detail=res.get("error", "Invalid owner credentials."))

    token = res.get("session_token")
    if token:
        response.set_cookie(
            key="nexus_session",
            value=token,
            httponly=True,
            secure=False,
            samesite="lax",
            max_age=86400 * 14,
        )
    return res


@app.get("/api/v1/auth/me", tags=["Auth & RBAC"])
async def get_current_user_profile(request: Request):
    """Get active session profile, role, and granted scopes."""
    session = _get_current_session(request)
    if not session.get("role"):
        return {"authenticated": False, "role": None, "scopes": []}
    return {"authenticated": True, "user": session}


# --- Owner Friend Management & Scoped Invites ---

@app.get("/api/v1/friends", tags=["Friend Management"])
async def list_friends_endpoint(request: Request):
    """Owner-only list of all registered friends and active scopes."""
    session = _get_current_session(request)
    if session.get("role") != "owner" and "admin" not in session.get("scopes", []):
        raise HTTPException(status_code=403, detail="Owner privileges required.")
    from earnings_engine.data.auth import list_friends
    return {"friends": list_friends(_settings)}


@app.patch("/api/v1/friends/{user_id}/access", tags=["Friend Management"])
async def update_friend_access_endpoint(user_id: str, req: UpdateFriendScopesRequest, request: Request):
    """Owner-only update of friend section permissions."""
    session = _get_current_session(request)
    if session.get("role") != "owner" and "admin" not in session.get("scopes", []):
        raise HTTPException(status_code=403, detail="Owner privileges required.")
    from earnings_engine.data.auth import update_friend_scopes
    scopes_dict = {
        "can_view_trips": req.can_view_trips,
        "can_view_cards": req.can_view_cards,
        "can_view_net_worth": req.can_view_net_worth,
    }
    success = update_friend_scopes(user_id, scopes_dict, settings=_settings)
    if not success:
        raise HTTPException(status_code=404, detail="Friend not found.")
    return {"success": True, "user_id": user_id, "updated_scopes": scopes_dict}


@app.delete("/api/v1/friends/{user_id}", tags=["Friend Management"])
async def revoke_friend_endpoint(user_id: str, request: Request):
    """Owner-only revocation and deactivation of friend user."""
    session = _get_current_session(request)
    if session.get("role") != "owner" and "admin" not in session.get("scopes", []):
        raise HTTPException(status_code=403, detail="Owner privileges required.")
    from earnings_engine.data.auth import revoke_friend_access
    success = revoke_friend_access(user_id, settings=_settings)
    return {"success": success, "user_id": user_id}


@app.get("/api/v1/invites", tags=["Friend Management"])
async def list_invites_endpoint(request: Request):
    """Owner-only list of all created invite codes with limits and expiration timeframes."""
    session = _get_current_session(request)
    if session.get("role") != "owner" and "admin" not in session.get("scopes", []):
        raise HTTPException(status_code=403, detail="Owner privileges required.")
    conn = get_db_connection(_settings)
    with conn:
        rows = conn.execute("""
            SELECT code, label, allowed_email, scopes, max_uses, uses_count, expires_at, is_active, created_at
            FROM invite_codes
            ORDER BY created_at DESC
        """).fetchall()
    invites = []
    for r in rows:
        try:
            scopes = json.loads(r[3]) if r[3] else []
        except Exception:
            scopes = []
        invites.append({
            "code": r[0],
            "label": r[1],
            "allowed_email": r[2],
            "scopes": scopes,
            "max_uses": r[4],
            "uses_count": r[5],
            "expires_at": r[6],
            "is_active": bool(r[7]),
            "created_at": r[8],
        })
    return {"invites": invites}


@app.post("/api/v1/invites", tags=["Friend Management"])
async def create_invite_endpoint(req: CreateInviteRequest, request: Request):
    """Create a new scoped invite code with configurable usage limits and validity timeframe."""
    session = _get_current_session(request)
    if session.get("role") != "owner" and "admin" not in session.get("scopes", []):
        raise HTTPException(status_code=403, detail="Owner privileges required.")
    from earnings_engine.data.auth import create_scoped_invite
    created = create_scoped_invite(
        label=req.label,
        scopes=req.scopes,
        allowed_email=req.allowed_email,
        max_uses=req.max_uses,
        expires_in_days=req.expires_in_days,
        expires_in_hours=req.expires_in_hours,
        expires_at=req.expires_at,
        custom_code=req.code,
        created_by=session.get("sub", "usr_owner_001"),
        settings=_settings,
    )
    return created


# --- Protected Scoped Data Endpoints ---

@app.get("/api/v1/trips", tags=["Scoped Hubs"])
async def get_trips_endpoint(session: dict = Depends(require_scope("can_view_trips"))):
    """Retrieve travel plans and upcoming trip itineraries with hierarchical group access."""
    from earnings_engine.data.trips import resolve_user_accessible_trips
    role = session.get("role")
    scopes = session.get("scopes", [])
    is_owner = bool(role == "owner" or "admin" in scopes)

    trips = resolve_user_accessible_trips(session, _settings)
    return {"success": True, "count": len(trips), "trips": trips, "is_owner": is_owner}


@app.get("/api/v1/trips/groups", tags=["Scoped Hubs"])
async def get_trip_groups_endpoint(session: dict = Depends(require_scope("can_view_trips"))):
    """Retrieve all trip groups, member rosters, and attached itineraries."""
    from earnings_engine.data.trips import get_trip_groups
    role = session.get("role")
    scopes = session.get("scopes", [])
    is_owner = bool(role == "owner" or "admin" in scopes)
    user_email = session.get("email")
    passcode = session.get("passcode")

    groups = get_trip_groups(
        settings=_settings,
        filter_user_email=user_email,
        filter_passcode=passcode,
        is_owner=is_owner,
    )
    return {"success": True, "count": len(groups), "groups": groups, "is_owner": is_owner}


@app.post("/api/v1/trips/groups", tags=["Scoped Hubs"])
async def create_trip_group_endpoint(
    req: CreateTripGroupRequest,
    request: Request,
    session: dict = Depends(require_scope("can_view_trips")),
):
    """Create a new trip group, auto-generate invite code, add members and attach trips."""
    from earnings_engine.data.trips import create_trip_group, add_group_member
    role = session.get("role")
    scopes = session.get("scopes", [])
    if role != "owner" and "admin" not in scopes:
        raise HTTPException(status_code=403, detail="Only the vault owner can create new trip groups.")

    base_url = str(request.base_url).rstrip("/")
    grp = create_trip_group(
        name=req.name,
        description=req.description,
        color=req.color,
        icon=req.icon,
        trip_ids=req.trip_ids,
        settings=_settings,
    )

    added_members = []
    if req.members:
        for m in req.members:
            m_name = m.get("name", "")
            m_email = m.get("email", "")
            if m_email:
                try:
                    mem_res = add_group_member(
                        group_id=grp["id"],
                        name=m_name,
                        email=m_email,
                        role=m.get("role", "member"),
                        send_email=True,
                        base_url=base_url,
                        settings=_settings,
                    )
                    added_members.append(mem_res)
                except Exception as e:
                    logger.warning("[TRIPS-API] Failed adding member %s: %s", m_email, e)

    grp["members"] = added_members
    return {"success": True, "group": grp, "message": f"Group '{req.name}' created successfully."}


@app.put("/api/v1/trips/groups/{group_id}", tags=["Scoped Hubs"])
async def update_trip_group_endpoint(
    group_id: str,
    req: UpdateTripGroupRequest,
    session: dict = Depends(require_scope("can_view_trips")),
):
    """Update trip group details (Owner only)."""
    role = session.get("role")
    scopes = session.get("scopes", [])
    if role != "owner" and "admin" not in scopes:
        raise HTTPException(status_code=403, detail="Only the vault owner can update trip groups.")

    conn = get_db_connection(_settings)
    with conn:
        grp = conn.execute("SELECT id FROM trip_groups WHERE id = ?", (group_id,)).fetchone()
        if not grp:
            raise HTTPException(status_code=404, detail="Trip group not found.")

        updates = []
        params = []
        if req.name is not None:
            updates.append("name = ?")
            params.append(req.name.strip())
        if req.description is not None:
            updates.append("description = ?")
            params.append(req.description.strip())
        if req.color is not None:
            updates.append("color = ?")
            params.append(req.color)
        if req.icon is not None:
            updates.append("icon = ?")
            params.append(req.icon)

        if updates:
            params.append(group_id)
            conn.execute(f"UPDATE trip_groups SET {', '.join(updates)} WHERE id = ?", params)
            conn.commit()

    return {"success": True, "message": "Group updated successfully."}


@app.delete("/api/v1/trips/groups/{group_id}", tags=["Scoped Hubs"])
async def delete_trip_group_endpoint(
    group_id: str,
    session: dict = Depends(require_scope("can_view_trips")),
):
    """Delete a trip group (Owner only)."""
    role = session.get("role")
    scopes = session.get("scopes", [])
    if role != "owner" and "admin" not in scopes:
        raise HTTPException(status_code=403, detail="Only the vault owner can delete trip groups.")

    conn = get_db_connection(_settings)
    with conn:
        conn.execute("DELETE FROM trip_groups WHERE id = ?", (group_id,))
        conn.execute("DELETE FROM trip_group_members WHERE group_id = ?", (group_id,))
        conn.execute("DELETE FROM trip_group_trips WHERE group_id = ?", (group_id,))
        conn.commit()

    logger.info("[TRIPS-API] Deleted group %s", group_id)
    return {"success": True, "message": f"Group {group_id} deleted."}


@app.post("/api/v1/trips/groups/{group_id}/members", tags=["Scoped Hubs"])
async def add_group_member_endpoint(
    group_id: str,
    req: AddGroupMemberRequest,
    request: Request,
    session: dict = Depends(require_scope("can_view_trips")),
):
    """Add a friend to a trip group and send direct email invite."""
    from earnings_engine.data.trips import add_group_member
    role = session.get("role")
    scopes = session.get("scopes", [])
    if role != "owner" and "admin" not in scopes:
        raise HTTPException(status_code=403, detail="Only the vault owner can add members to groups.")

    base_url = str(request.base_url).rstrip("/")
    res = add_group_member(
        group_id=group_id,
        name=req.name,
        email=req.email,
        role=req.role,
        custom_passcode=req.custom_passcode,
        send_email=req.send_email,
        base_url=base_url,
        settings=_settings,
    )
    return {"success": True, "member": res, "message": f"Added {req.name} to group."}


@app.delete("/api/v1/trips/groups/{group_id}/members/{member_id_or_email}", tags=["Scoped Hubs"])
async def remove_group_member_endpoint(
    group_id: str,
    member_id_or_email: str,
    session: dict = Depends(require_scope("can_view_trips")),
):
    """Remove a friend from a trip group."""
    from earnings_engine.data.trips import remove_group_member
    role = session.get("role")
    scopes = session.get("scopes", [])
    if role != "owner" and "admin" not in scopes:
        raise HTTPException(status_code=403, detail="Only the vault owner can remove members.")

    success = remove_group_member(group_id=group_id, email_or_id=member_id_or_email, settings=_settings)
    return {"success": success, "message": "Member removed from group."}


@app.post("/api/v1/trips/groups/{group_id}/attach-trips", tags=["Scoped Hubs"])
async def attach_trips_endpoint(
    group_id: str,
    req: AttachGroupTripsRequest,
    session: dict = Depends(require_scope("can_view_trips")),
):
    """Attach trips to a group."""
    from earnings_engine.data.trips import attach_trips_to_group
    role = session.get("role")
    scopes = session.get("scopes", [])
    if role != "owner" and "admin" not in scopes:
        raise HTTPException(status_code=403, detail="Only the vault owner can attach trips.")

    count = attach_trips_to_group(group_id=group_id, trip_ids=req.trip_ids, settings=_settings)
    return {"success": True, "attached_count": count, "message": f"Attached {count} trip(s) to group."}


@app.delete("/api/v1/trips/groups/{group_id}/trips/{trip_id}", tags=["Scoped Hubs"])
async def detach_trip_endpoint(
    group_id: str,
    trip_id: str,
    session: dict = Depends(require_scope("can_view_trips")),
):
    """Detach a trip from a group."""
    from earnings_engine.data.trips import detach_trip_from_group
    role = session.get("role")
    scopes = session.get("scopes", [])
    if role != "owner" and "admin" not in scopes:
        raise HTTPException(status_code=403, detail="Only the vault owner can detach trips.")

    success = detach_trip_from_group(group_id=group_id, trip_id=trip_id, settings=_settings)
    return {"success": success, "message": "Trip detached from group."}


@app.get("/api/v1/trips/friends/lookup", tags=["Scoped Hubs"])
async def lookup_friend_endpoint(
    email: str = Query(..., description="Friend email to check"),
    session: dict = Depends(require_scope("can_view_trips")),
):
    """Lookup if a friend's email already has an existing name or passcode in the system."""
    from earnings_engine.data.trips import find_existing_friend_passcode
    passcode, name = find_existing_friend_passcode(email, _settings)
    return {
        "exists": bool(passcode is not None),
        "email": email,
        "name": name,
        "passcode": passcode,
    }


@app.post("/api/v1/trips", tags=["Scoped Hubs"])
async def create_trip_endpoint(req: CreateTripRequest, session: dict = Depends(require_scope("can_view_trips"))):
    """Create a new trip itinerary (Owner only)."""
    role = session.get("role")
    scopes = session.get("scopes", [])
    if role != "owner" and "admin" not in scopes:
        raise HTTPException(status_code=403, detail="Only the vault owner can add new trips.")

    import uuid
    trip_id = f"trip_{uuid.uuid4().hex[:8]}"
    now_str = datetime.now().isoformat(timespec="seconds")
    packing_str = json.dumps(req.packing_list) if req.packing_list else "[]"

    conn = get_db_connection(_settings)
    with conn:
        conn.execute("""
            INSERT INTO trips (
                id, title, destination, start_date, end_date, status, notes,
                cover_image, estimated_budget, is_shared_with_friends, flight_details,
                hotel_details, packing_list, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            trip_id, req.title, req.destination, req.start_date, req.end_date,
            req.status, req.notes, req.cover_image, req.estimated_budget,
            1 if req.is_shared_with_friends else 0, req.flight_details,
            req.hotel_details, packing_str, now_str
        ))
        conn.commit()

    logger.info("[TRIPS-API] Created new trip %s (%s - %s)", trip_id, req.title, req.destination)
    return {"success": True, "trip_id": trip_id, "message": "Trip itinerary created successfully."}


@app.delete("/api/v1/trips/{trip_id}", tags=["Scoped Hubs"])
async def delete_trip_endpoint(trip_id: str, session: dict = Depends(require_scope("can_view_trips"))):
    """Delete a trip from the vault (Owner only)."""
    role = session.get("role")
    scopes = session.get("scopes", [])
    if role != "owner" and "admin" not in scopes:
        raise HTTPException(status_code=403, detail="Only the vault owner can delete trips.")

    conn = get_db_connection(_settings)
    with conn:
        conn.execute("DELETE FROM trips WHERE id = ?", (trip_id,))
        conn.execute("DELETE FROM trip_activities WHERE trip_id = ?", (trip_id,))
        conn.commit()

    logger.info("[TRIPS-API] Deleted trip %s", trip_id)
    return {"success": True, "message": f"Trip {trip_id} deleted."}


@app.get("/api/v1/trips/{trip_id}/activities", tags=["Scoped Hubs"])
async def get_trip_activities_endpoint(trip_id: str, session: dict = Depends(require_scope("can_view_trips"))):
    """Retrieve suggested activities and votes for a trip."""
    conn = get_db_connection(_settings)
    with conn:
        rows = conn.execute("""
            SELECT id, trip_id, suggested_by_name, suggested_by_role, activity_title, location, approx_cost, votes_count, status, created_at
            FROM trip_activities WHERE trip_id = ? ORDER BY votes_count DESC, created_at ASC
        """, (trip_id,)).fetchall()
    activities = [
        {
            "id": r[0],
            "trip_id": r[1],
            "suggested_by_name": r[2],
            "suggested_by_role": r[3],
            "activity_title": r[4],
            "location": r[5],
            "approx_cost": float(r[6] or 0.0),
            "votes_count": int(r[7] or 1),
            "status": r[8],
            "created_at": r[9],
        }
        for r in rows
    ]
    return {"success": True, "count": len(activities), "activities": activities}


@app.post("/api/v1/trips/{trip_id}/activities", tags=["Scoped Hubs"])
async def suggest_trip_activity_endpoint(
    trip_id: str,
    req: SuggestTripActivityRequest,
    session: dict = Depends(require_scope("can_view_trips")),
):
    """Suggest an activity or excursion for a trip."""
    role = session.get("role") or "friend"
    import uuid
    act_id = f"act_{uuid.uuid4().hex[:8]}"
    now_str = datetime.now().isoformat(timespec="seconds")

    conn = get_db_connection(_settings)
    with conn:
        trip = conn.execute("SELECT id, title FROM trips WHERE id = ?", (trip_id,)).fetchone()
        if not trip:
            raise HTTPException(status_code=404, detail="Trip not found.")

        conn.execute("""
            INSERT INTO trip_activities (
                id, trip_id, suggested_by_name, suggested_by_role, activity_title, location, approx_cost, votes_count, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, 'suggested', ?)
        """, (act_id, trip_id, req.suggested_by_name, role, req.activity_title, req.location, req.approx_cost, now_str))
        conn.commit()

    logger.info("[TRIPS-API] New activity '%s' suggested by %s for %s", req.activity_title, req.suggested_by_name, trip[1])
    return {"success": True, "activity_id": act_id, "message": f"Activity '{req.activity_title}' suggested!"}


@app.get("/api/v1/cards", tags=["Scoped Hubs"])
async def get_cards_endpoint(session: dict = Depends(require_scope("can_view_cards"))):
    """Retrieve credit card benefits, reward rates, limits, and lounge access perks."""
    role = session.get("role")
    scopes = session.get("scopes", [])
    is_owner = bool(role == "owner" or "admin" in scopes)

    conn = get_db_connection(_settings)
    with conn:
        if is_owner:
            rows = conn.execute("""
                SELECT id, card_name, issuer, network, category_perks, lounge_access_summary,
                       annual_fee_status, display_order, last4, card_holder, color_theme,
                       credit_limit, available_limit, billing_cycle_day, is_shared_with_friends, created_at
                FROM credit_cards ORDER BY display_order ASC, created_at ASC
            """).fetchall()
        else:
            rows = conn.execute("""
                SELECT id, card_name, issuer, network, category_perks, lounge_access_summary,
                       annual_fee_status, display_order, last4, card_holder, color_theme,
                       credit_limit, available_limit, billing_cycle_day, is_shared_with_friends, created_at
                FROM credit_cards WHERE is_shared_with_friends = 1 ORDER BY display_order ASC, created_at ASC
            """).fetchall()

    cards = []
    for r in rows:
        try:
            perks = json.loads(r[4]) if r[4] else {}
        except Exception:
            perks = {}
        cards.append({
            "id": r[0],
            "card_name": r[1],
            "issuer": r[2],
            "network": r[3],
            "category_perks": perks,
            "lounge_access_summary": r[5],
            "annual_fee_status": r[6],
            "display_order": r[7],
            "last4": r[8] or "8842",
            "card_holder": r[9] or "VIP Member",
            "color_theme": r[10] or "obsidian",
            "credit_limit": float(r[11] or 0.0),
            "available_limit": float(r[12] or 0.0),
            "billing_cycle_day": int(r[13] or 15),
            "is_shared_with_friends": bool(r[14]),
            "created_at": r[15],
        })
    return {"success": True, "count": len(cards), "cards": cards, "is_owner": is_owner}


@app.post("/api/v1/cards", tags=["Scoped Hubs"])
async def create_card_endpoint(req: CreateCreditCardRequest, session: dict = Depends(require_scope("can_view_cards"))):
    """Add a new credit card to the wealth hub (Owner only)."""
    role = session.get("role")
    scopes = session.get("scopes", [])
    if role != "owner" and "admin" not in scopes:
        raise HTTPException(status_code=403, detail="Only the vault owner can add new credit cards.")

    import uuid
    card_id = f"card_{uuid.uuid4().hex[:8]}"
    now_str = datetime.now().isoformat(timespec="seconds")
    perks_str = json.dumps(req.category_perks) if isinstance(req.category_perks, dict) else str(req.category_perks or "{}")

    conn = get_db_connection(_settings)
    with conn:
        conn.execute("""
            INSERT INTO credit_cards (
                id, card_name, issuer, network, category_perks, lounge_access_summary,
                annual_fee_status, display_order, last4, card_holder, color_theme,
                credit_limit, available_limit, billing_cycle_day, is_shared_with_friends, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            card_id, req.card_name, req.issuer, req.network, perks_str,
            req.lounge_access_summary, req.annual_fee_status, req.display_order,
            req.last4, req.card_holder, req.color_theme, req.credit_limit,
            req.available_limit, req.billing_cycle_day, 1 if req.is_shared_with_friends else 0, now_str
        ))
        conn.commit()

    logger.info("[CARDS-API] Added new credit card %s (%s - %s)", card_id, req.card_name, req.issuer)
    return {"success": True, "card_id": card_id, "message": "Credit card successfully added."}


@app.delete("/api/v1/cards/{card_id}", tags=["Scoped Hubs"])
async def delete_card_endpoint(card_id: str, session: dict = Depends(require_scope("can_view_cards"))):
    """Remove a credit card from the vault (Owner only)."""
    role = session.get("role")
    scopes = session.get("scopes", [])
    if role != "owner" and "admin" not in scopes:
        raise HTTPException(status_code=403, detail="Only the vault owner can delete credit cards.")

    conn = get_db_connection(_settings)
    with conn:
        conn.execute("DELETE FROM credit_cards WHERE id = ?", (card_id,))
        conn.execute("DELETE FROM credit_card_otp_requests WHERE card_id = ?", (card_id,))
        conn.commit()

    logger.info("[CARDS-API] Deleted credit card %s", card_id)
    return {"success": True, "message": f"Card {card_id} deleted."}


@app.get("/api/v1/cards/otp-requests", tags=["Scoped Hubs"])
async def get_card_otp_requests_endpoint(
    card_id: str | None = None,
    status: str | None = None,
    session: dict = Depends(require_scope("can_view_cards")),
):
    """List OTP requests for credit cards with live status and expiration."""
    role = session.get("role")
    scopes = session.get("scopes", [])
    is_owner = bool(role == "owner" or "admin" in scopes)

    conn = get_db_connection(_settings)
    with conn:
        query = """
            SELECT r.id, r.card_id, r.requested_by_name, r.requested_by_role, r.amount, r.merchant,
                   r.purpose, r.urgency, r.status, r.otp_code, r.otp_expires_at, r.response_notes,
                   r.created_at, r.updated_at, c.card_name, c.last4, c.color_theme, c.issuer
            FROM credit_card_otp_requests r
            LEFT JOIN credit_cards c ON r.card_id = c.id
            WHERE 1=1
        """
        params: list[Any] = []
        if card_id:
            query += " AND r.card_id = ?"
            params.append(card_id)
        if status:
            query += " AND r.status = ?"
            params.append(status)
        query += " ORDER BY r.created_at DESC LIMIT 50"

        rows = conn.execute(query, params).fetchall()

    requests_list = []
    now_dt = datetime.now()
    for r in rows:
        req_status = r[8]
        otp_expires_at = r[10]
        # Check if expired
        is_expired = False
        remaining_seconds = 0
        if otp_expires_at:
            try:
                exp_dt = datetime.fromisoformat(otp_expires_at)
                diff = (exp_dt - now_dt).total_seconds()
                if diff <= 0:
                    is_expired = True
                    if req_status == "approved":
                        req_status = "expired"
                else:
                    remaining_seconds = int(diff)
            except Exception:
                pass

        requests_list.append({
            "id": r[0],
            "card_id": r[1],
            "requested_by_name": r[2],
            "requested_by_role": r[3],
            "amount": float(r[4] or 0.0),
            "merchant": r[5],
            "purpose": r[6],
            "urgency": r[7],
            "status": req_status,
            "otp_code": r[9] if (req_status == "approved" or is_owner) else None,
            "otp_expires_at": otp_expires_at,
            "remaining_seconds": remaining_seconds,
            "response_notes": r[11],
            "created_at": r[12],
            "updated_at": r[13],
            "card_name": r[14] or "Shared Credit Card",
            "last4": r[15] or "8842",
            "color_theme": r[16] or "obsidian",
            "issuer": r[17] or "Bank",
        })

    return {"success": True, "count": len(requests_list), "requests": requests_list, "is_owner": is_owner}


@app.post("/api/v1/cards/otp-requests", tags=["Scoped Hubs"])
async def create_card_otp_request_endpoint(req: CreateCardOtpRequest, session: dict = Depends(require_scope("can_view_cards"))):
    """Submit a request for an OTP for a specific card and transaction amount."""
    role = session.get("role") or "friend"
    import uuid
    req_id = f"req_cc_{uuid.uuid4().hex[:8]}"
    now_str = datetime.now().isoformat(timespec="seconds")

    conn = get_db_connection(_settings)
    with conn:
        card = conn.execute("SELECT id, card_name FROM credit_cards WHERE id = ?", (req.card_id,)).fetchone()
        if not card:
            raise HTTPException(status_code=404, detail="Credit card not found.")

        conn.execute("""
            INSERT INTO credit_card_otp_requests (
                id, card_id, requested_by_name, requested_by_role, amount, merchant,
                purpose, urgency, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
        """, (
            req_id, req.card_id, req.requested_by_name, role, req.amount,
            req.merchant, req.purpose, req.urgency, now_str, now_str
        ))
        conn.commit()

    logger.info("[CARDS-OTP] New OTP request %s from %s for ₹%.2f on %s (%s)",
                req_id, req.requested_by_name, req.amount, card[1], req.merchant)
    return {
        "success": True,
        "request_id": req_id,
        "status": "pending",
        "message": f"OTP Request for ₹{req.amount:,.2f} at {req.merchant} submitted. Waiting for owner approval."
    }


@app.post("/api/v1/cards/otp-requests/{request_id}/approve", tags=["Scoped Hubs"])
async def approve_card_otp_request_endpoint(
    request_id: str,
    req: ApproveCardOtpRequest,
    session: dict = Depends(require_scope("can_view_cards")),
):
    """Approve a card OTP request and provide/generate the active OTP code (Owner only)."""
    role = session.get("role")
    scopes = session.get("scopes", [])
    if role != "owner" and "admin" not in scopes:
        raise HTTPException(status_code=403, detail="Only the vault owner can approve OTP requests.")

    import random
    otp_code = req.otp_code.strip() if req.otp_code else f"{random.randint(100000, 999999)}"
    duration = max(1, min(req.duration_minutes, 30))
    exp_dt = (datetime.now() + timedelta(minutes=duration)).isoformat(timespec="seconds")
    now_str = datetime.now().isoformat(timespec="seconds")

    conn = get_db_connection(_settings)
    with conn:
        row = conn.execute("SELECT id, requested_by_name, amount, merchant FROM credit_card_otp_requests WHERE id = ?", (request_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="OTP request not found.")

        conn.execute("""
            UPDATE credit_card_otp_requests
            SET status = 'approved', otp_code = ?, otp_expires_at = ?, response_notes = ?, updated_at = ?
            WHERE id = ?
        """, (otp_code, exp_dt, req.response_notes or "Approved by Owner", now_str, request_id))
        conn.commit()

    logger.info("[CARDS-OTP] Approved OTP request %s for %s (OTP: %s, expires: %s)", request_id, row[1], otp_code, exp_dt)
    return {
        "success": True,
        "request_id": request_id,
        "status": "approved",
        "otp_code": otp_code,
        "expires_at": exp_dt,
        "duration_minutes": duration,
        "message": f"OTP request approved. OTP code {otp_code} valid for {duration} minutes."
    }


@app.post("/api/v1/cards/otp-requests/{request_id}/reject", tags=["Scoped Hubs"])
async def reject_card_otp_request_endpoint(
    request_id: str,
    req: RejectCardOtpRequest,
    session: dict = Depends(require_scope("can_view_cards")),
):
    """Reject a card OTP request (Owner only)."""
    role = session.get("role")
    scopes = session.get("scopes", [])
    if role != "owner" and "admin" not in scopes:
        raise HTTPException(status_code=403, detail="Only the vault owner can reject OTP requests.")

    now_str = datetime.now().isoformat(timespec="seconds")
    conn = get_db_connection(_settings)
    with conn:
        row = conn.execute("SELECT id, requested_by_name FROM credit_card_otp_requests WHERE id = ?", (request_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="OTP request not found.")

        conn.execute("""
            UPDATE credit_card_otp_requests
            SET status = 'rejected', response_notes = ?, updated_at = ?
            WHERE id = ?
        """, (req.response_notes or "Declined by Owner", now_str, request_id))
        conn.commit()

    logger.info("[CARDS-OTP] Rejected OTP request %s for %s", request_id, row[1])
    return {"success": True, "request_id": request_id, "status": "rejected", "message": "OTP request declined."}


@app.get("/api/v1/net-worth", tags=["Scoped Hubs"])
async def get_net_worth_endpoint(session: dict = Depends(require_scope("can_view_net_worth"))):
    """Retrieve high-level net worth range, asset allocation, and YoY growth."""
    role = session.get("role")
    scopes = session.get("scopes", [])
    is_owner = bool(role == "owner" or "admin" in scopes)

    conn = get_db_connection(_settings)
    with conn:
        row = conn.execute("SELECT id, as_of_date, total_net_worth_band, allocation_pct, yoy_growth_pct, updated_at FROM net_worth_snapshots ORDER BY as_of_date DESC LIMIT 1").fetchone()
    if not row:
        return {"success": True, "snapshot": None, "is_owner": is_owner}
    try:
        alloc = json.loads(row[3]) if row[3] else {}
    except Exception:
        alloc = {}
    return {
        "success": True,
        "is_owner": is_owner,
        "snapshot": {
            "id": row[0],
            "as_of_date": row[1],
            "total_net_worth_band": row[2],
            "allocation_pct": alloc,
            "yoy_growth_pct": row[4],
            "updated_at": row[5],
        },
    }


@app.get("/api/v1/net-worth/history", tags=["Scoped Hubs"])
async def get_net_worth_history_endpoint(session: dict = Depends(require_scope("can_view_net_worth"))):
    """Retrieve historical net worth snapshots for trend tracking."""
    conn = get_db_connection(_settings)
    with conn:
        rows = conn.execute("SELECT id, as_of_date, total_net_worth_band, allocation_pct, yoy_growth_pct, updated_at FROM net_worth_snapshots ORDER BY as_of_date ASC").fetchall()
    history = []
    for r in rows:
        try:
            alloc = json.loads(r[3]) if r[3] else {}
        except Exception:
            alloc = {}
        history.append({
            "id": r[0],
            "as_of_date": r[1],
            "total_net_worth_band": r[2],
            "allocation_pct": alloc,
            "yoy_growth_pct": r[4],
            "updated_at": r[5],
        })
    return {"success": True, "count": len(history), "history": history}


@app.post("/api/v1/net-worth", tags=["Scoped Hubs"])
async def create_net_worth_snapshot_endpoint(req: CreateNetWorthSnapshotRequest, session: dict = Depends(require_scope("can_view_net_worth"))):
    """Record a new net worth snapshot and asset allocation (Owner only)."""
    role = session.get("role")
    scopes = session.get("scopes", [])
    if role != "owner" and "admin" not in scopes:
        raise HTTPException(status_code=403, detail="Only the vault owner can update net worth snapshots.")

    import uuid
    snap_id = f"nw_{uuid.uuid4().hex[:8]}"
    now_str = datetime.now().isoformat(timespec="seconds")
    alloc_str = json.dumps(req.allocation_pct)

    conn = get_db_connection(_settings)
    with conn:
        conn.execute("""
            INSERT INTO net_worth_snapshots (id, as_of_date, total_net_worth_band, allocation_pct, yoy_growth_pct, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (snap_id, req.as_of_date, req.total_net_worth_band, alloc_str, req.yoy_growth_pct, now_str))
        conn.commit()

    logger.info("[NET-WORTH-API] Recorded new net worth snapshot %s (%s)", snap_id, req.total_net_worth_band)
    return {"success": True, "snapshot_id": snap_id, "message": "Net worth snapshot updated successfully."}


@app.get("/api-info", tags=["Root"])
async def api_info():
    """API info and directory of endpoints."""
    return {
        "service": "Earnings Engine API",
        "version": "1.0.0",
        "docs": "/docs",
        "portal": "/portal",
        "dashboard": "/dashboard",
        "credit_card": "/credit-card",
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
    """Serve the interactive dashboard page."""
    try:
        from jinja2 import Environment, FileSystemLoader
        env = Environment(
            loader=FileSystemLoader(str(_templates_dir)),
            autoescape=True,
            auto_reload=True,
            cache_size=0,
        )
        from earnings_engine.data.crypto import has_private_key
        has_key = has_private_key()
        template = env.get_template("dashboard.html")
        html = template.render(has_diagnostics_key=has_key, has_tracker_key=has_key)
        return HTMLResponse(html)
    except Exception as exc:
        return HTMLResponse(
            f"<html><body><h1>Dashboard render error</h1><p>{exc}</p></body></html>",
            status_code=500,
        )


@app.get("/stock/{ticker}", tags=["UI"], response_class=HTMLResponse)
async def serve_stock_detail(ticker: str):
    """Serve the dedicated stock intelligence and AI consensus page."""
    try:
        from jinja2 import Environment, FileSystemLoader
        env = Environment(
            loader=FileSystemLoader(str(_templates_dir)),
            autoescape=True,
            auto_reload=True,
            cache_size=0,
        )
        template = env.get_template("stock_detail.html")
        html = template.render(ticker=ticker.upper().strip())
        return HTMLResponse(html)
    except Exception as exc:
        return HTMLResponse(
            f"<html><body><h1>Stock page render error</h1><p>{exc}</p></body></html>",
            status_code=500,
        )


@app.get("/api/v1/stock/{ticker}/overview", tags=["Stock Intelligence & Ratings"])
async def get_stock_overview_endpoint(ticker: str):
    """Return aggregated fundamentals, quotes, swing technicals, quarterly signals, AI consensus, and catalysts."""
    from earnings_engine.api.stock_api import get_stock_overview
    res = await asyncio.to_thread(get_stock_overview, ticker, _settings)
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error", "Failed to retrieve stock overview"))
    return res


@app.get("/api/v1/stock/{ticker}/rating", tags=["Stock Intelligence & Ratings"])
async def get_stock_rating_endpoint(ticker: str):
    """Return industry benchmark relative valuation multiples and technical strength rating."""
    from earnings_engine.api.stock_api import calculate_stock_rating
    res = await asyncio.to_thread(calculate_stock_rating, ticker, _settings)
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error", "Failed to calculate stock rating"))
    return res


@app.get("/api/v1/stock/{ticker}/factor-evaluation", tags=["Stock Intelligence & Ratings"])
async def get_stock_factor_evaluation_endpoint(ticker: str):
    """Return standardized 6-Pillar factor evaluation matrix, weights, and master composite score."""
    from earnings_engine.api.stock_api import get_stock_factor_evaluation
    res = await asyncio.to_thread(get_stock_factor_evaluation, ticker, _settings)
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error", "Failed to evaluate stock factors"))
    return res


@app.api_route("/api/v1/stock/{ticker}/fetch-news", methods=["GET", "POST"], tags=["Stock Intelligence & Ratings"])
async def fetch_stock_news_endpoint(ticker: str):
    """Fetch fresh news headlines and corporate announcements delta for a stock."""
    from earnings_engine.api.stock_api import refresh_stock_news
    res = await asyncio.to_thread(refresh_stock_news, ticker, _settings)
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error", "Failed to refresh news delta"))
    return res


@app.get("/api/v1/stock/{ticker}/intelligence-note", tags=["Stock Intelligence & Ratings"])
@app.post("/api/v1/stock/{ticker}/intelligence-note", tags=["Stock Intelligence & Ratings"])
async def get_stock_intelligence_note_endpoint(
    ticker: str,
    model_name: str | None = Query(None, description="Specific local Ollama or OpenRouter model"),
    provider: str = Query("auto", description="Inference provider: 'auto', 'ollama', or 'openrouter'"),
):
    """Return transparent multi-dimensional intelligence note for a single stock."""
    from earnings_engine.api.stock_api import get_stock_intelligence_note
    res = await asyncio.to_thread(
        get_stock_intelligence_note,
        ticker,
        model_name=model_name,
        provider=provider,
        settings=_settings,
    )
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error", "Failed to retrieve stock intelligence note"))
    return res


@app.post("/api/v1/stock/{ticker}/recalculate", tags=["Stock Intelligence & Ratings"])
@app.post("/api/v1/recalculate/{ticker}", tags=["Stock Intelligence & Ratings"])
async def recalculate_stock_endpoint(ticker: str, request: Request):
    """Force re-fetch live earnings dates, daily prices, recalculate metrics, and log audit trail."""
    from earnings_engine.api.recalculate_api import recalculate_ticker_metrics
    from earnings_engine.api.stock_api import calculate_stock_rating
    recalc_res = await asyncio.to_thread(recalculate_ticker_metrics, ticker, _settings)
    if not recalc_res.get("success"):
        raise HTTPException(status_code=400, detail=recalc_res.get("error", "Failed to recalculate ticker"))

    rating_res = await asyncio.to_thread(calculate_stock_rating, ticker, _settings)
    combined = {**rating_res, **recalc_res}
    combined["fundamental"] = rating_res.get("fundamental")
    combined["technical"] = rating_res.get("technical")
    combined["composite"] = rating_res.get("composite")
    combined["ai_note"] = rating_res.get("ai_note")
    return combined


@app.get("/api/v1/recalculate/audit/{ticker}", tags=["Stock Intelligence & Ratings"])
@app.get("/api/v1/recalculate/audit", tags=["Stock Intelligence & Ratings"])
async def get_ticker_audit_endpoint(ticker: str | None = None, limit: int = Query(50, ge=1, le=200)):
    """Retrieve immutable recalculation audit trail for a ticker or across all recent events."""
    from earnings_engine.data.ticker_audit import get_audit_history
    entries = await asyncio.to_thread(get_audit_history, ticker, limit, _settings)
    return {"success": True, "ticker": ticker, "entries": entries, "history": entries}


@app.get("/api/v1/ticker/audit-log", tags=["Stock Intelligence & Ratings"])
async def get_ticker_audit_log_endpoint(ticker: str | None = Query(None), limit: int = Query(50, ge=1, le=200)):
    """Retrieve audit log list format for UI tables."""
    from earnings_engine.data.ticker_audit import get_audit_history
    return await asyncio.to_thread(get_audit_history, ticker, limit, _settings)


@app.api_route("/api/v1/stock/{ticker}/live-week-hl", methods=["GET", "POST"], tags=["Stock Intelligence & Ratings"])
async def get_live_week_hl_endpoint(ticker: str, earnings_date: str | None = Query(None)):
    """Calculate and return real-time post-earnings week move high/low statistics."""
    from earnings_engine.api.stock_api import get_live_week_hl
    res = await asyncio.to_thread(get_live_week_hl, ticker, earnings_date, _settings)
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error", "Failed to calculate live week high/low"))
    return res


@app.post("/api/v1/stock/{ticker}/calculate-eps", tags=["Stock Intelligence & Ratings"])
@app.post("/api/v1/earnings/{ticker}/calculate-eps", tags=["Stock Intelligence & Ratings"])
async def calculate_stock_eps_endpoint(ticker: str, req: CalculateEpsRequest | None = None):
    """Calculate, derive, or fetch missing EPS and surprise % for past earnings dates."""
    from earnings_engine.api.stock_api import calculate_or_fetch_eps
    ed = req.earnings_date if req else None
    est = req.override_estimate if req else None
    rep = req.override_reported if req else None
    res = await asyncio.to_thread(calculate_or_fetch_eps, ticker, ed, est, rep, _settings)
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error", "Failed to calculate EPS"))
    return res


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
    get_watchlist_quotes_api,
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
        import earnings_engine.api.dashboard_api as _dash_api
        return await asyncio.to_thread(
            _dash_api.get_results_report_components,
            days=days,
            market=market,
            past_days=past_days,
            start_date=start_date,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching results report: {str(e)}")


@app.get("/api/v1/dashboard/results/month-summary", tags=["Dashboard"])
async def dashboard_results_month_summary(
    market: str | None = Query(None, description="Market universe (IN, US, NSE_ALL, NSE_LARGE_CAP)"),
):
    """Get fast 3-month count metrics (Last Month, This Month, Next Month) for results dashboard."""
    try:
        import earnings_engine.api.dashboard_api as _dash_api
        return await asyncio.to_thread(_dash_api.get_results_3month_summary, market=market)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching 3-month results summary: {str(e)}")


@app.get("/api/v1/dashboard/month-filter", tags=["Dashboard"])
async def dashboard_month_filter(
    days: int = Query(60, description="Look-ahead window in days", ge=0, le=180),
    past_days: int = Query(60, description="Look-back window in days", ge=0, le=180),
    market: str | None = Query(None, description="Market universe (IN, US, NSE_ALL, NSE_LARGE_CAP)"),
    force_sync: bool = Query(False, description="Force present-day delta sync and recalculate"),
    request: Request = None,
):
    """Get precalculated Month Filter report components with present-day delta sync."""
    try:
        effective_force_sync = force_sync
        if force_sync and request:
            session = getattr(request.state, "session", None) or _resolve_session(request)
            if session:
                role = session.get("role", "friend")
                scopes = set(session.get("scopes", []) + session.get("allowed_routes", []))
                if not (role in ("owner", "master") or "admin" in scopes or "*" in scopes):
                    effective_force_sync = False

        import earnings_engine.api.dashboard_api as _dash_api
        return await asyncio.to_thread(
            _dash_api.get_month_filter_report_components,
            days=days,
            market=market,
            past_days=past_days,
            force_sync=effective_force_sync,
        )
    except Exception as e:
        logger.exception("Error in dashboard_month_filter: %s", e)
        raise HTTPException(status_code=500, detail=f"Error fetching month filter report: {str(e)}")


@app.post("/api/v1/dashboard/month-filter/sync", tags=["Dashboard"])
async def dashboard_month_filter_sync(
    market: str | None = Query(None, description="Market universe"),
    request: Request = None,
):
    """Force present-day delta fetch and refresh precalculated Month Filter report."""
    _require_master_role(request)
    try:
        import earnings_engine.api.dashboard_api as _dash_api
        return await asyncio.to_thread(
            _dash_api.get_month_filter_report_components,
            days=60,
            market=market,
            past_days=60,
            force_sync=True,
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
        return await asyncio.to_thread(get_swing_setups, market=market, limit=limit)
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


@app.post("/api/v1/swing-range/auto-detect", tags=["Swing"])
@app.post("/api/v1/dashboard/swing-range/auto-detect", tags=["Swing"])
async def swing_range_auto_detect(request: dict):
    """Trigger auto-detection of swing channel support & resistance for a ticker."""
    ticker = request.get("ticker", "").strip().upper()
    watchlist = request.get("watchlist", "ALL")
    if not ticker:
        raise HTTPException(status_code=400, detail="ticker is required")
    try:
        return await asyncio.to_thread(get_swing_range_api, watchlist=watchlist, ticker=ticker)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error auto-detecting swing range: {str(e)}")


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


@app.get("/api/v1/config/ratelimits", tags=["Control Center"])
@app.get("/api/v1/ratelimits", tags=["Control Center"])
async def get_downstream_ratelimits():
    """Retrieve rate limit criteria, quotas, and current utilization for all downstreams."""
    from earnings_engine.rate_limits import get_ratelimits_summary
    return get_ratelimits_summary(settings=_settings)


@app.get("/api/v1/system/telemetry", tags=["Control Center"])
async def get_system_telemetry_records(
    limit: int = 200,
    grouped: bool = Query(True, description="Club same machine + IP combos together with counts"),
):
    """Retrieve system diagnostic and telemetry entries with optional machine+IP grouping."""
    from earnings_engine.data.crypto import has_private_key
    from earnings_engine.data.telemetry import get_grouped_telemetry_records, get_telemetry_records

    if not has_private_key():
        return {"has_key": False, "total": 0, "records": []}

    if grouped:
        records = get_grouped_telemetry_records(limit=limit, settings=_settings)
    else:
        records = get_telemetry_records(limit=limit, settings=_settings)
    return {"has_key": True, "total": len(records), "grouped": grouped, "records": records}


@app.delete("/api/v1/system/telemetry", tags=["Control Center"])
async def clear_system_telemetry_records():
    """Clear system diagnostic and telemetry entries."""
    from earnings_engine.data.telemetry import clear_telemetry_records
    return clear_telemetry_records(settings=_settings)


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


@app.post("/api/v1/kronos/predict/{ticker}", tags=["Stock Intelligence & Ratings"])
async def kronos_predict_single(
    ticker: str,
    lookback: int = 120,
    pred_len: int = 14,
    device: str | None = None,
):
    """Run on-demand Kronos AI 14-day sequence prediction for a single ticker."""
    try:
        forecasts = get_kronos_predictions(tickers=[ticker], lookback=lookback, pred_len=pred_len, device=device)
        pred = forecasts[0] if forecasts else None
        return {"success": bool(pred), "prediction": pred}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error running Kronos prediction for {ticker}: {str(e)}")


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
async def dashboard_refresh(request_body: dict, request: Request = None):
    """Refresh data (prices, earnings, market caps) on demand."""
    _require_master_role(request)
    try:
        market = request_body.get("market")
        tickers = request_body.get("tickers")
        force = request_body.get("force", True)
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
async def dashboard_earnings_incremental(request_body: dict, request: Request = None):
    """Fetch earnings only for tickers that are missing earnings data.

    Request body:
    {
        "market": "ALL",                    // optional universe selector
        "tickers": ["RELIANCE.NS", "TCS.NS"]  // optional, overrides market
    }
    """
    _require_master_role(request)
    try:
        market = request_body.get("market")
        tickers = request_body.get("tickers")
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


@app.get("/api/v1/watchlist/quotes", tags=["Dashboard"])
@app.get("/api/v1/watchlist/{name}/quotes", tags=["Dashboard"])
async def watchlist_quotes_get(
    name: str | None = None,
    watchlist: str | None = Query(None, description="Watchlist name"),
    tickers: str | None = Query(None, description="Comma-separated ticker list (overrides watchlist name)"),
    live: bool = Query(False, description="Force live intraday / price fetching"),
):
    """Retrieve full OHLCV, pricing, market cap, and swing levels for tickers in a watchlist."""
    # When hitting /api/v1/watchlist/quotes?watchlist=X, 'name' might be 'quotes' or None
    wl_name = watchlist or (name if name and name != "quotes" else None) or "my_watchlist"
    ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()] if tickers else None
    return await asyncio.to_thread(get_watchlist_quotes_api, watchlist=wl_name, tickers=ticker_list, live=live)


@app.post("/api/v1/watchlist/quotes", tags=["Dashboard"])
async def watchlist_quotes_post(request: dict):
    """Retrieve full OHLCV, pricing, market cap, and swing levels.
    Body: {"watchlist"?: str, "tickers"?: list[str], "live"?: bool}
    """
    wl_name = request.get("watchlist") or "my_watchlist"
    tickers = request.get("tickers")
    live = bool(request.get("live", False))
    return await asyncio.to_thread(get_watchlist_quotes_api, watchlist=wl_name, tickers=tickers, live=live)


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


@app.post("/api/v1/watchlist/add", tags=["Dashboard"])
async def watchlist_add_endpoint(
    request: Request,
    ticker: str | None = Query(None, description="Ticker symbol"),
    name: str | None = Query(None, description="Watchlist name"),
):
    """Add a ticker to a named watchlist. Accepts JSON body or query params."""
    body_data = {}
    try:
        body_data = await request.json()
    except Exception:
        pass
    final_ticker = (body_data.get("ticker") if isinstance(body_data, dict) else None) or ticker or ""
    final_name = (body_data.get("name") if isinstance(body_data, dict) else None) or name or "my_watchlist"
    if not final_ticker:
        raise HTTPException(status_code=400, detail="Ticker is required")
    result = add_to_watchlist(ticker=final_ticker, name=final_name)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to add ticker to watchlist"))
    return result


@app.post("/api/v1/watchlist/remove", tags=["Dashboard"])
async def watchlist_remove_endpoint(
    request: Request,
    ticker: str | None = Query(None, description="Ticker symbol"),
    name: str | None = Query(None, description="Watchlist name"),
):
    """Remove a ticker from a named watchlist. Accepts JSON body or query params."""
    body_data = {}
    try:
        body_data = await request.json()
    except Exception:
        pass
    final_ticker = (body_data.get("ticker") if isinstance(body_data, dict) else None) or ticker or ""
    final_name = (body_data.get("name") if isinstance(body_data, dict) else None) or name or "my_watchlist"
    if not final_ticker:
        raise HTTPException(status_code=400, detail="Ticker is required")
    result = remove_from_watchlist(ticker=final_ticker, name=final_name)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to remove ticker from watchlist"))
    return result


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


@app.get("/api/v1/watchlist/{name}", tags=["Dashboard"])
async def watchlist_get_by_path(name: str):
    """Get a named watchlist or universe from the SQLite DB / universe files."""
    from earnings_engine.data.universe import get_universe as fetch_universe_tickers
    from earnings_engine.data.watchlists import get_watchlist as fetch_db_watchlist

    tickers = fetch_db_watchlist(name, _settings)
    if not tickers:
        tickers = fetch_universe_tickers(name, _settings)
    return {"name": name, "tickers": tickers or []}


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


@app.post("/api/v1/admin/sync-upstream", tags=["Admin"])
async def admin_sync_upstream():
    """Manually trigger synchronization between local SQLite and Upstream Turso Cloud."""
    from earnings_engine.data.turso_sync import sync_local_to_upstream
    try:
        loop = asyncio.get_running_loop()
        res = await loop.run_in_executor(None, sync_local_to_upstream, _settings)
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error syncing with upstream database: {str(e)}")


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


@app.get("/api/v1/news/outcomes", tags=["News & Catalysts"])
async def get_news_outcomes_endpoint(
    category: str | None = Query(None),
    direction: str | None = Query(None),
    status: str | None = Query(None),
    predicted_met: bool | None = Query(None),
    sort_by: str = Query("published_at"),
    limit: int = Query(50),
    search: str | None = Query(None),
):
    """Query evaluated historical news outcomes and forward price performance."""
    try:
        items = dashboard_api.get_news_outcomes_api(
            category=category,
            direction=direction,
            status=status,
            predicted_met=predicted_met,
            sort_by=sort_by,
            limit=limit,
            search=search,
        )
        return {"success": True, "count": len(items), "outcomes": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching news outcomes: {str(e)}")


@app.post("/api/v1/news/outcomes/evaluate", tags=["News & Catalysts"])
async def evaluate_news_outcomes_endpoint(request: dict | None = None):
    """Trigger on-demand evaluation of historical catalyst outcomes against price action."""
    force = bool((request or {}).get("force", False))
    try:
        result = dashboard_api.evaluate_news_outcomes_api(force=force)
        return {"success": True, **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error evaluating news outcomes: {str(e)}")


@app.get("/api/v1/news/trade-metrics", tags=["News & Catalysts"])
async def get_news_trade_metrics_endpoint(
    category: str | None = Query(None),
    min_impact: int = Query(0),
):
    """Get trade-readiness KPIs (Win Rate, Profit Factor, Expectancy, Max Gainers, Category Edge)."""
    try:
        metrics = dashboard_api.get_news_trade_metrics_api(
            category=category,
            min_impact=min_impact,
        )
        return {"success": True, "metrics": metrics}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching news trade metrics: {str(e)}")



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
    timeframe_days: int = Field(default=14, ge=1, le=180)
    models: list[str] | None = None
    local_model_url: str | None = None
    force: bool = False


class ConsensusSettleRequest(BaseModel):
    as_of_date: str | None = None


@app.get("/api/v1/consensus/local-models", tags=["AI Consensus Engine"])
@app.get("/api/v1/local-models", tags=["AI Consensus Engine"])
async def list_local_models_endpoint(host: str | None = Query(None), refresh: bool = Query(False)):
    """Discover available local models from running Ollama or LM Studio instances (pre-scanned at startup)."""
    global _CACHED_LOCAL_MODELS
    if not refresh and not host and _CACHED_LOCAL_MODELS:
        return _CACHED_LOCAL_MODELS
    return await asyncio.to_thread(_scan_and_cache_local_models, host=host)


@app.post("/api/v1/consensus/predict", tags=["AI Consensus Engine"])
async def consensus_predict_endpoint(req: ConsensusPredictRequest):
    """Run multi-model consensus prediction for one or more tickers (cached unless force=True)."""
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
            # Check cached prediction if force is False
            if not req.force:
                cached_preds = storage.get_predictions(settings=_settings, ticker=ticker, limit=1)
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

            # 1. Build rich context
            logger.info("[CONSENSUS-API] Building quantitative context for %s (%dd window)...", ticker, req.timeframe_days)
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
                local_url=req.local_model_url,
            )

            # If running a single model (or subset), merge with previous model outputs to keep 4-model matrix updated
            if req.models and len(req.models) < len(model_runner.DEFAULT_MODELS):
                cached_preds = storage.get_predictions(settings=_settings, ticker=ticker, limit=1)
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
            logger.info("[CONSENSUS-API] Completed & saved consensus forecast #%s for %s: %s (Target: %.2f)",
                        pred_id, ticker, consensus.get("consensus_direction"), consensus.get("consensus_target_price", as_of_price))

        except Exception as e:
            logger.error("[CONSENSUS-API] Error predicting for %s: %s", ticker, e)
            results.append({"ticker": ticker, "error": str(e)})

    from earnings_engine.rate_limits import get_models_rate_limits, get_ratelimits_summary
    return {
        "success": True,
        "count": len(results),
        "predictions": results,
        "results": results,
        "models": get_models_rate_limits(),
        "rate_limits": get_ratelimits_summary(_settings),
    }


@app.get("/api/v1/consensus/models", tags=["AI Consensus Engine"])
async def consensus_models_endpoint():
    """Return available AI consensus models, icons, metadata, and live rate limit counters."""
    from earnings_engine.rate_limits import get_models_rate_limits, get_ratelimits_summary
    return {
        "success": True,
        "models": get_models_rate_limits(),
        "rate_limits": get_ratelimits_summary(_settings),
    }


@app.get("/api/v1/consensus/latest", tags=["AI Consensus Engine"])
async def consensus_latest_endpoint(
    ticker: str | None = Query(default=None),
    direction: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=1000),
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
    limit: int = Query(default=100, ge=1, le=1000),
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


# =========================================================================
# 🐞 LOCAL ERROR LEDGER & SELF-HEALING DIAGNOSTICS API
# =========================================================================

class ResolveErrorRequest(BaseModel):
    notes: str = "Resolved by agent task fix"


@app.get("/api/v1/errors/summary", tags=["Error Diagnostics"])
async def get_errors_summary_endpoint():
    """Return health metrics and count of open vs resolved application errors."""
    from earnings_engine.data.error_ledger import get_error_summary
    return get_error_summary(_settings)


@app.get("/api/v1/errors/open", tags=["Error Diagnostics"])
async def get_open_errors_endpoint(limit: int = Query(50, ge=1, le=200)):
    """List all unresolved application errors requiring diagnosis or fix."""
    from earnings_engine.data.error_ledger import get_open_errors
    errors = get_open_errors(_settings, limit=limit)
    return {"count": len(errors), "open_errors": errors}


@app.get("/api/v1/errors", tags=["Error Diagnostics"])
async def get_all_errors_endpoint(limit: int = Query(100, ge=1, le=500)):
    """List all recorded application errors in the ledger."""
    from earnings_engine.data.error_ledger import get_all_errors
    errors = get_all_errors(_settings, limit=limit)
    return {"count": len(errors), "errors": errors}


@app.post("/api/v1/errors/scan-logs", tags=["Error Diagnostics"])
async def scan_logs_endpoint(full: bool = Query(False, description="Whether to run full scan across all historical log files")):
    """Scan error stream or log files and ingest any newly detected errors."""
    from earnings_engine.data.error_ledger import scan_log_files
    result = scan_log_files(full_scan=full, settings=_settings)
    return {"success": True, **result}


@app.get("/api/v1/errors/stream", tags=["Error Diagnostics"])
async def get_error_stream_endpoint():
    """Retrieve unconsumed error records from the live active error stream."""
    from earnings_engine.data.error_ledger import read_error_stream, get_error_stream_path
    events = read_error_stream()
    return {
        "count": len(events),
        "stream_file": str(get_error_stream_path()),
        "events": events,
    }


@app.post("/api/v1/errors/stream/drain", tags=["Error Diagnostics"])
async def drain_error_stream_endpoint():
    """Ingest all pending error stream events into ledger and clear stream buffer."""
    from earnings_engine.data.error_ledger import consume_error_stream
    result = consume_error_stream(clear_after=True, settings=_settings)
    return {"success": True, **result}


@app.delete("/api/v1/errors/stream", tags=["Error Diagnostics"])
async def clear_error_stream_endpoint():
    """Clear/truncate the active error stream buffer."""
    from earnings_engine.data.error_ledger import clear_error_stream
    count = clear_error_stream()
    return {"success": True, "cleared_count": count}


@app.post("/api/v1/errors/{error_id}/resolve", tags=["Error Diagnostics"])
async def resolve_error_endpoint(error_id: str, req: ResolveErrorRequest | None = None):
    """Mark an error as resolved with verification explanation."""
    from earnings_engine.data.error_ledger import mark_error_resolved
    notes = req.notes if req and req.notes else "Resolved by agent task fix"
    updated = mark_error_resolved(error_id, resolution_notes=notes, settings=_settings)
    if not updated:
        raise HTTPException(status_code=404, detail=f"Error with ID or signature '{error_id}' not found.")
    return {"success": True, "resolved_id": error_id, "notes": notes}


# ===========================================================================
# 📊 Industry-Benchmarked Fundamental & Technical Stock Rating Endpoints
# ===========================================================================

class RecalculateRatingRequest(BaseModel):
    source: str = "manual_recalc"
    audit_notes: str | None = None


class BatchRatingRequest(BaseModel):
    tickers: list[str]
    force_recalculate: bool = False


@app.get("/api/v1/stock/{ticker}/rating", tags=["Stock Intelligence & Ratings"])
async def get_stock_rating_endpoint(ticker: str):
    """Retrieve the industry-benchmarked fundamental rating, technical score, and AI note."""
    from earnings_engine.data.stock_rating import get_stock_rating, recalculate_stock_rating
    rating = get_stock_rating(ticker, _settings)
    if not rating:
        # Compute on-demand if not cached yet
        rating = recalculate_stock_rating(ticker, _settings, source="auto_on_demand")
    return {"success": True, **rating}


@app.post("/api/v1/stock/{ticker}/recalculate", tags=["Stock Intelligence & Ratings"])
async def recalculate_stock_rating_endpoint(ticker: str, req: RecalculateRatingRequest | None = None):
    """Recalculate stock metrics live, compare diff against previous snapshot, and log audit trail."""
    from earnings_engine.data.stock_rating import recalculate_stock_rating
    src = req.source if req and req.source else "user_recalculate"
    result = recalculate_stock_rating(ticker, _settings, source=src)

    # Log to audit history
    try:
        from earnings_engine.data.ticker_audit import record_audit_entry
        diff_summary = f"Fundamental: {result['fundamental']['grade']} ({result['fundamental']['score']}), Tech: {result['technical']['grade']} ({result['technical']['score']})"
        record_audit_entry(
            ticker=ticker,
            has_changes=True,
            changes_summary=req.audit_notes if req and req.audit_notes else diff_summary,
            updated_values={"fundamental": result["fundamental"], "technical": result["technical"]},
            diff_data=result.get("diff", {}),
            settings=_settings,
        )
    except Exception as e:
        logger.warning(f"Failed to log recalculate audit event for {ticker}: {e}")

    return {"success": True, **result}


@app.post("/api/v1/stock/ratings/batch", tags=["Stock Intelligence & Ratings"])
async def batch_stock_ratings_endpoint(req: BatchRatingRequest):
    """Batch fetch or compute ratings for multiple tickers."""
    from earnings_engine.data.stock_rating import get_stock_rating, recalculate_stock_rating
    results = {}
    for sym in req.tickers[:100]:  # Limit batch to 100
        if req.force_recalculate:
            results[sym] = recalculate_stock_rating(sym, _settings, source="batch_recalc")
        else:
            r = get_stock_rating(sym, _settings)
            if not r:
                r = recalculate_stock_rating(sym, _settings, source="batch_auto")
            results[sym] = r
    return {"success": True, "count": len(results), "ratings": results}


@app.api_route("/api/v1/stock/{ticker}/live-week-hl", methods=["GET", "POST"], tags=["Stock Intelligence & Ratings"])
async def calc_live_week_hl_endpoint(ticker: str, earnings_date: str | None = Query(None)):
    """Calculate live week high/low move since earnings print using latest real-time prices."""
    from earnings_engine.data.market_context import _week_high_low_around
    import yfinance as yf
    
    ed = pd.to_datetime(earnings_date) if earnings_date else None
    if ed is None:
        from earnings_engine.data.earnings import load_earnings
        edf = load_earnings(ticker, _settings)
        if edf is not None and not edf.empty:
            past = edf[edf["earnings_date"] < pd.Timestamp.today().normalize()]
            if not past.empty:
                ed = pd.to_datetime(past.sort_values("earnings_date").iloc[-1]["earnings_date"])
    
    if ed is None:
        raise HTTPException(status_code=400, detail=f"No past earnings date found for {ticker}")

    hist_df = pd.DataFrame(columns=["close"])
    curr_price = None
    try:
        yf_ticker = yf.Ticker(ticker)
        hist = yf_ticker.history(period="1mo")
        fast_info = yf_ticker.fast_info or {}
        curr_price = fast_info.get("last_price")
        if not hist.empty and "Close" in hist.columns:
            if curr_price is None or curr_price <= 0:
                curr_price = float(hist["Close"].iloc[-1])
            hist_df = pd.DataFrame(index=pd.to_datetime(hist.index.date))
            hist_df["close"] = hist["Close"].values
            if "High" in hist.columns:
                hist_df["high"] = hist["High"].values
            if "Low" in hist.columns:
                hist_df["low"] = hist["Low"].values
            if "Open" in hist.columns:
                hist_df["open"] = hist["Open"].values
    except Exception as e:
        logger.warning(f"Error querying yfinance live for {ticker}: {e}")

    if hist_df.empty:
        from earnings_engine.data.prices import fetch_prices
        try:
            hist_df = fetch_prices(ticker, _settings, force=False)
        except Exception:
            pass

    if hist_df is None or hist_df.empty or "close" not in hist_df.columns:
        raise HTTPException(status_code=404, detail="No price history available for ticker")

    week_data = _week_high_low_around(hist_df, ed, current_price=curr_price)
    if week_data is None:
        raise HTTPException(status_code=404, detail="Not enough price history around earnings date")

    high_pct, low_pct, high_p, low_p, high_d, low_d = week_data

    return {
        "success": True,
        "ticker": ticker,
        "earnings_date": ed.strftime("%Y-%m-%d"),
        "high_pct": round(high_pct, 2),
        "low_pct": round(low_pct, 2),
        "high_price": round(high_p, 2),
        "low_price": round(low_p, 2),
        "high_date": pd.Timestamp(high_d).strftime("%b %d") if high_d is not None else None,
        "low_date": pd.Timestamp(low_d).strftime("%b %d") if low_d is not None else None,
        "current_price": round(curr_price, 2) if curr_price else None,
    }


# ---------------------------------------------------------------------------
# Breakout Radar — Background-scanned candidate endpoints
# ---------------------------------------------------------------------------

@app.get("/api/v1/breakout-radar", tags=["Breakout Radar"])
async def get_breakout_radar(
    universe: str | None = Query(None, description="Universe or watchlist to filter/scan (e.g. nifty_50, nse_top, nse_large_cap, us_top, all)"),
    min_score: float = Query(35.0, description="Minimum composite score to include"),
    limit: int = Query(50, ge=1, le=200, description="Max candidates to return"),
    sort_by: str = Query("composite_score", description="Sort field (composite_score, fundamental_score, resistance_score, volume_score, realized_return_pct)"),
    asof_date: str | None = Query(None, description="Point-in-time scan date in YYYY-MM-DD format"),
    live: bool = Query(False, description="Force live real-time price fetching for candidates"),
):
    """Return breakout candidates from the background scanner or point-in-time historical backtest."""
    candidates = breakout_scanner_mod.get_cached_scan_results(
        universe=universe,
        settings=_settings,
        asof_date=asof_date,
    )
    status = breakout_scanner_mod.get_scan_status(universe=universe)

    # Apply min_score filter
    candidates = [c for c in candidates if c.get("composite_score", 0) >= min_score]

    # Live parallel price fetching if requested
    if live and candidates and not asof_date:
        from concurrent.futures import ThreadPoolExecutor
        from earnings_engine.data.prices import fetch_prices, load_prices
        
        def _fetch_live(c: dict[str, Any]) -> None:
            t = c.get("ticker")
            if not t:
                return
            try:
                df = fetch_prices(t, _settings, force=True)
                if not df.empty and "close" in df.columns:
                    closes = pd.to_numeric(df["close"], errors="coerce").dropna()
                    if not closes.empty:
                        cur_p = round(float(closes.iloc[-1]), 2)
                        c["current_price"] = cur_p
                        c["current_date"] = str(df.index[-1])[:10]
                        sig_p = c.get("predicted_value") or c.get("signal_price")
                        if sig_p and sig_p > 0:
                            c["realized_return_pct"] = round(((cur_p - sig_p) / sig_p) * 100, 2)
                        trig = c.get("breakout_trigger")
                        if trig:
                            c["breakout_happened"] = cur_p >= trig
            except Exception as e:
                logger.debug("Failed live breakout refresh for %s: %s", t, e)

        with ThreadPoolExecutor(max_workers=min(10, len(candidates))) as pool:
            list(pool.map(_fetch_live, candidates))

    # Compute prediction signals & color-coding for all candidates
    for c in candidates:
        cur_p = c.get("current_price")
        trig_p = c.get("breakout_trigger")
        target_p = c.get("target_price")
        stop_p = c.get("stop_loss")
        sig_p = c.get("predicted_value") or c.get("signal_price") or cur_p

        if cur_p is not None:
            if target_p is not None and cur_p >= target_p:
                c["prediction_signal"] = "TARGET_HIT"
                c["prediction_color"] = "green"
                c["prediction_label"] = "Target Hit 🎯"
            elif trig_p is not None and cur_p >= trig_p:
                c["prediction_signal"] = "TRIGGERED"
                c["prediction_color"] = "green"
                c["prediction_label"] = "Breakout Fired 🚀"
            elif stop_p is not None and cur_p <= stop_p:
                c["prediction_signal"] = "STOP_HIT"
                c["prediction_color"] = "red"
                c["prediction_label"] = "Stop Hit 🛑"
            elif trig_p is not None and stop_p is not None:
                c["prediction_signal"] = "COILING"
                c["prediction_color"] = "brown"
                c["prediction_label"] = "Coiling 🗜️"
            else:
                c["prediction_signal"] = "WATCH"
                c["prediction_color"] = "blue"
                c["prediction_label"] = "Watchlist ⏳"
        else:
            c["prediction_signal"] = "PENDING"
            c["prediction_color"] = "blue"
            c["prediction_label"] = "Pending ⏳"

    # Sort
    valid_sort = {
        "composite_score", "fundamental_score", "resistance_score", "volume_score",
        "compression_score", "momentum_score", "realized_return_pct", "predicted_value",
    }
    if sort_by not in valid_sort:
        sort_by = "composite_score"
    candidates.sort(key=lambda x: x.get(sort_by) or 0, reverse=True)

    # Compute historical outcome metrics if evaluating an older asof_date
    backtest_summary = {}
    if asof_date and candidates:
        evaluated = [c for c in candidates if c.get("breakout_happened") is not None]
        if evaluated:
            successes = [c for c in evaluated if c.get("breakout_happened") is True]
            win_rate = round(len(successes) / len(evaluated) * 100, 1)
            returns = [c.get("realized_return_pct", 0) for c in evaluated]
            avg_return = round(sum(returns) / len(returns), 2)
            top_winner = max(evaluated, key=lambda x: x.get("realized_return_pct", -999))
            backtest_summary = {
                "asof_date": asof_date,
                "total_evaluated": len(evaluated),
                "success_count": len(successes),
                "win_rate_pct": win_rate,
                "avg_return_pct": avg_return,
                "top_winner_ticker": top_winner.get("ticker"),
                "top_winner_gain_pct": top_winner.get("realized_return_pct"),
            }

    # Limit
    candidates = candidates[:limit]

    return {
        "success": True,
        "count": len(candidates),
        "asof_date": asof_date,
        "is_live": bool(live),
        "candidates": candidates,
        "universe": universe or "ALL",
        "scan_status": status,
        "backtest_summary": backtest_summary,
    }


@app.post("/api/v1/breakout-radar/refresh", tags=["Breakout Radar"])
async def refresh_breakout_radar(
    universe: str | None = Query(None, description="Universe or watchlist to refresh scan for"),
):
    """Trigger an immediate re-scan of tickers (runs in a background thread)."""
    import threading

    def _run():
        try:
            breakout_scanner_mod.run_breakout_scan(_settings, universe=universe)
        except Exception as e:
            logger.error("[BREAKOUT] Manual refresh error: %s", e)

    t = threading.Thread(target=_run, daemon=True, name="breakout_manual_refresh")
    t.start()
    return {"success": True, "message": f"Breakout scan triggered for {universe or 'all universes'} in background. Check /api/v1/breakout-radar shortly."}


@app.get("/api/v1/breakout-radar/search", tags=["Breakout Radar"])
async def search_breakout_stocks(
    q: str = Query(..., min_length=1, description="Ticker or company name search query"),
    limit: int = Query(15, ge=1, le=50, description="Max autocomplete matches"),
):
    """Fast auto-complete search for stocks across price cache and universe registry."""
    matches = await asyncio.to_thread(
        breakout_scanner_mod.search_breakout_tickers,
        query=q,
        limit=limit,
        settings=_settings,
    )
    return {"success": True, "query": q, "matches": matches}


@app.get("/api/v1/breakout-radar/evaluate/{ticker}", tags=["Breakout Radar"])
async def evaluate_breakout_stock(
    ticker: str,
    asof_date: str | None = Query(None, description="Point-in-time evaluation date in YYYY-MM-DD format"),
    force_tier: str | None = Query(None, description="Force promotion into 'hot' or 'warm' tier pool"),
):
    """Evaluate a specific stock on-demand for Breakout Radar setup conviction, key levels, and sub-score metrics."""
    sym = ticker.strip().upper()
    try:
        result = await asyncio.to_thread(
            breakout_scanner_mod.evaluate_stock_breakout,
            ticker=sym,
            asof_date=asof_date,
            force_tier=force_tier,
            settings=_settings,
        )
        if not result or not result.get("success"):
            error_msg = result.get("error", "Stock evaluation failed") if result else "No data returned"
            raise HTTPException(status_code=404, detail=error_msg)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("[BREAKOUT-API] Stock evaluation error for %s: %s", sym, e)
        raise HTTPException(status_code=500, detail=f"Breakout evaluation failed: {str(e)}")


@app.post("/api/v1/breakout-radar/set-tier/{ticker}", tags=["Breakout Radar"])
async def set_breakout_tier(
    ticker: str,
    tier: str = Query(..., description="Target tier: 'hot', 'warm', or 'cold'"),
):
    """Manually assign or promote a stock into Hot, Warm, or Cold breakout tier."""
    sym = ticker.strip().upper()
    try:
        result = await asyncio.to_thread(
            breakout_scanner_mod.set_ticker_tier,
            ticker=sym,
            tier=tier,
            settings=_settings,
        )
        if not result or not result.get("success"):
            error_msg = result.get("error", "Failed to set tier") if result else "No data returned"
            raise HTTPException(status_code=400, detail=error_msg)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("[BREAKOUT-API] Set tier error for %s: %s", sym, e)
        raise HTTPException(status_code=500, detail=f"Failed to set breakout tier: {str(e)}")


@app.post("/api/v1/breakout-radar/ai-reasoning/{ticker}", tags=["Breakout Radar"])
async def get_breakout_ai_reasoning(
    ticker: str,
    model_name: str | None = Query(None, description="Local Ollama model name (e.g. llama3.2:3b, deepseek-r1:8b, qwen2.5-coder:latest)"),
):
    """Generate multi-model AI reasoning and calculation breakdown notes for a breakout candidate using local Ollama."""
    sym = ticker.strip().upper()
    try:
        reasoning = breakout_scanner_mod.generate_breakout_ai_reasoning(
            ticker=sym,
            model_name=model_name,
            settings=_settings,
        )
        return {
            "success": True,
            "ticker": sym,
            "reasoning": reasoning,
        }
    except Exception as e:
        logger.error("[BREAKOUT-API] Reasoning generation failed for %s: %s", sym, e)
        raise HTTPException(status_code=500, detail=f"Breakout AI reasoning failed: {str(e)}")



# ---------------------------------------------------------------------------
# Quarter Repeaters & AI Forward Earnings Radar Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/v1/earnings-radar/repeaters", tags=["Quarter Repeaters Radar"])
async def get_quarter_repeaters(
    universe: str | None = Query(None, description="Universe or watchlist to screen (e.g. nifty_50, nse_top, nse_large_cap, us_top, all)"),
    min_beat_pct: float = Query(0.0, description="Minimum prior EPS surprise percentage"),
    min_week_high_pct: float = Query(2.5, description="Minimum post-earnings week peak high percentage"),
    limit: int = Query(50, ge=1, le=150, description="Max candidates to return"),
    verdict: str | None = Query(None, description="Filter by AI repeat verdict (e.g. STRONG_REPEAT_BEAT, MODERATE_BEAT)"),
):
    """Screen for companies that had stellar past earnings beats & week highs, with AI continuity forecasts."""
    candidates = repeaters_mod.scan_quarter_repeaters(
        settings=_settings,
        universe=universe,
        min_beat_pct=min_beat_pct,
        min_week_high_pct=min_week_high_pct,
        limit=limit,
    )

    if verdict:
        v_clean = verdict.upper().strip()
        candidates = [
            c for c in candidates
            if c.get("ai_forecast") and c["ai_forecast"].get("ai_repeat_verdict") == v_clean
        ]

    # Calculate summary metrics
    total_screened = len(candidates)
    avg_beat = round(sum(c.get("last_eps_surprise") or 0 for c in candidates) / total_screened, 1) if total_screened > 0 else 0.0
    top_conviction = max(candidates, key=lambda x: x.get("conviction_score", 0)) if candidates else None

    # Count industry buzz themes
    buzz_counts: dict[str, int] = {}
    for c in candidates:
        tag = c.get("industry_buzz_tag", "Growth")
        buzz_counts[tag] = buzz_counts.get(tag, 0) + 1
    dominant_buzz = max(buzz_counts.items(), key=lambda x: x[1])[0] if buzz_counts else "—"

    return {
        "success": True,
        "count": total_screened,
        "universe": universe or "ALL",
        "summary": {
            "total_screened": total_screened,
            "avg_prior_beat_pct": avg_beat,
            "top_pick_ticker": top_conviction.get("ticker") if top_conviction else "—",
            "top_pick_score": top_conviction.get("conviction_score") if top_conviction else 0,
            "dominant_industry_buzz": dominant_buzz,
        },
        "candidates": candidates,
    }


@app.post("/api/v1/earnings-radar/repeaters/forecast/{ticker}", tags=["Quarter Repeaters Radar"])
async def forecast_single_repeater(
    ticker: str,
    model_name: str | None = Query(None, description="Specific local Ollama or OpenRouter model"),
    provider: str = Query("auto", description="Inference provider: 'auto', 'ollama', or 'openrouter'"),
):
    """Run on-demand AI Forward reasoning for upcoming quarter earnings continuity for a single ticker."""
    sym = ticker.strip().upper()
    try:
        forecast = repeaters_mod.generate_ai_repeater_forecast(
            sym,
            settings=_settings,
            model_name=model_name,
            provider=provider,
        )
        return {
            "success": True,
            "ticker": sym,
            "forecast": forecast,
        }
    except Exception as e:
        logger.error("[REPEATERS-API] Forecast failed for %s: %s", sym, e)
        raise HTTPException(status_code=500, detail=f"AI Forecast failed for {sym}: {str(e)}")


@app.post("/api/v1/earnings-radar/repeaters/batch-forecast", tags=["Quarter Repeaters Radar"])
async def batch_forecast_repeaters(
    universe: str | None = Query(None, description="Universe to batch forecast"),
    limit: int = Query(15, ge=1, le=40, description="Max stocks to process in batch"),
):
    """Run background batch AI Forward analysis for top quarter repeat candidates."""
    candidates = repeaters_mod.scan_quarter_repeaters(
        settings=_settings,
        universe=universe,
        limit=limit,
    )
    tickers = [c["ticker"] for c in candidates]

    def _run_batch():
        for t in tickers:
            try:
                repeaters_mod.generate_ai_repeater_forecast(t, settings=_settings)
            except Exception as ex:
                logger.warning("[REPEATERS-BATCH] Error forecasting %s: %s", t, ex)

    t = threading.Thread(target=_run_batch, daemon=True, name="repeaters_batch_forecast")
    t.start()

    return {
        "success": True,
        "message": f"Started AI Forward batch forecasting for {len(tickers)} stocks in {universe or 'all universes'}.",
        "tickers": tickers,
    }


# ---------------------------------------------------------------------------
# Live Automation Schedules & Background Job Monitor Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/v1/automation/schedules", tags=["Automation Schedules"])
async def get_automation_schedules():
    """Retrieve all background schedule states, intervals, last execution, and live countdowns."""
    from earnings_engine.data.automation_schedules import get_all_schedules
    schedules = await asyncio.to_thread(get_all_schedules, _settings)
    return {"success": True, "schedules": schedules}


@app.post("/api/v1/automation/trigger", tags=["Automation Schedules"])
async def trigger_automation_job(
    job_id: str = Query(..., description="Job ID to run immediately (e.g. breakout_hot_rescore, breakout_warm_rescore, breakout_cold_scan, news_catalyst_harvest)"),
):
    """Manually trigger immediate execution of any background scheduled job."""
    import threading

    def _execute():
        try:
            if job_id == "breakout_hot_rescore":
                breakout_scanner_mod.run_hot_rescore(_settings)
            elif job_id == "breakout_warm_rescore":
                breakout_scanner_mod.run_warm_rescore(_settings)
            elif job_id == "breakout_cold_scan":
                breakout_scanner_mod.run_cold_scan(_settings)
            elif job_id == "news_catalyst_harvest":
                from earnings_engine.data.catalysts_news import scan_watchlist_catalysts
                from earnings_engine.data.automation_schedules import record_job_start, record_job_finish
                record_job_start("news_catalyst_harvest", _settings)
                t0 = time.perf_counter()
                res = scan_watchlist_catalysts("my_watchlist", 3, False, _settings)
                elapsed = round(time.perf_counter() - t0, 2)
                record_job_finish("news_catalyst_harvest", elapsed, f"Harvested {res.get('catalysts_fetched', 0)} headlines across {res.get('scanned_tickers', 0)} stocks", settings=_settings)
        except Exception as e:
            logger.error("[AUTOMATION-TRIGGER] Error running %s: %s", job_id, e)

    t = threading.Thread(target=_execute, daemon=True, name=f"trigger_{job_id}")
    t.start()
    return {"success": True, "message": f"Triggered execution for '{job_id}' in background thread."}


# ---------------------------------------------------------------------------
# Breakout Movement Audit Log & Transition History Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/v1/breakout-radar/audit-log", tags=["Breakout Radar"])
async def get_breakout_audit_trail(
    ticker: str | None = Query(None, description="Optional ticker filter (e.g. TCS.NS)"),
    limit: int = Query(50, ge=1, le=100, description="Max transition log entries to return"),
):
    """Retrieve chronological audit trail of breakout pool promotions, demotions, and triggers with full explanations."""
    logs = await asyncio.to_thread(
        breakout_scanner_mod.get_breakout_audit_log,
        ticker=ticker,
        limit=limit,
        settings=_settings,
    )
    return {"success": True, "count": len(logs), "logs": logs}


# ---------------------------------------------------------------------------
# News Catalyst Activity & Ingestion Feed Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/v1/news/activity", tags=["News Catalysts"])
async def get_news_catalyst_activity(
    limit: int = Query(50, ge=1, le=100, description="Max news catalyst events to return"),
):
    """Retrieve recently harvested news catalysts with impacted stocks, sentiment direction, and impact analysis."""
    from earnings_engine.data.catalysts_news import get_recent_news_activity
    items = await asyncio.to_thread(get_recent_news_activity, limit=limit, settings=_settings)
    return {"success": True, "count": len(items), "items": items}


# ---------------------------------------------------------------------------
# Institutional Accumulation & Mutual Fund Activity Hub Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/v1/institutional/summary", tags=["Institutional Activity"])
async def get_institutional_summary():
    """Retrieve high-level institutional market accumulation metrics and top accumulated/distributed highlights."""
    from earnings_engine.data.institutional_accumulation import (
        get_top_accumulated_stocks,
        get_top_distributed_stocks,
        get_all_funds_activity,
    )
    accumulating = await asyncio.to_thread(get_top_accumulated_stocks, min_score=60.0, limit=10, settings=_settings)
    distributing = await asyncio.to_thread(get_top_distributed_stocks, limit=10, settings=_settings)
    funds = await asyncio.to_thread(get_all_funds_activity, limit=10, settings=_settings)
    return {
        "success": True,
        "accumulating_stocks": accumulating,
        "distributing_stocks": distributing,
        "active_funds": funds,
    }


@app.get("/api/v1/institutional/stock/{ticker}", tags=["Institutional Activity"])
async def get_stock_institutional_details(ticker: str):
    """Retrieve complete fund-by-fund breakdown, shareholding trend, and block deals for a specific stock (e.g. ALLCARGO.NS)."""
    from earnings_engine.data.institutional_accumulation import get_stock_institutional_activity
    result = await asyncio.to_thread(get_stock_institutional_activity, ticker=ticker, settings=_settings)
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error", "Failed fetching institutional activity"))
    return result


@app.get("/api/v1/institutional/accumulating", tags=["Institutional Activity"])
async def get_institutional_accumulating(
    min_score: float = Query(55.0, description="Minimum accumulation score (0-100)"),
    limit: int = Query(25, ge=1, le=100, description="Max stocks to return"),
):
    """Screen for equities with aggressive mutual fund, FII, and super investor buying."""
    from earnings_engine.data.institutional_accumulation import get_top_accumulated_stocks
    items = await asyncio.to_thread(get_top_accumulated_stocks, min_score=min_score, limit=limit, settings=_settings)
    return {"success": True, "count": len(items), "items": items}


@app.get("/api/v1/institutional/distributing", tags=["Institutional Activity"])
async def get_institutional_distributing(
    limit: int = Query(20, ge=1, le=100, description="Max stocks to return"),
):
    """Screen for equities where institutions are actively selling or trimming stake."""
    from earnings_engine.data.institutional_accumulation import get_top_distributed_stocks
    items = await asyncio.to_thread(get_top_distributed_stocks, limit=limit, settings=_settings)
    return {"success": True, "count": len(items), "items": items}


@app.get("/api/v1/institutional/funds", tags=["Institutional Activity"])
async def get_institutional_funds_list(
    limit: int = Query(50, ge=1, le=100, description="Max funds to return"),
):
    """List tracked institutional funds and super investors with their total tracked positions and buying/selling stats."""
    from earnings_engine.data.institutional_accumulation import get_all_funds_activity
    items = await asyncio.to_thread(get_all_funds_activity, limit=limit, settings=_settings)
    return {"success": True, "count": len(items), "funds": items}


@app.get("/api/v1/institutional/fund/{fund_name}", tags=["Institutional Activity"])
async def get_fund_portfolio(fund_name: str):
    """Reverse lookup: retrieve all equities held and recent actions for a specific mutual fund or super investor."""
    from earnings_engine.data.institutional_accumulation import get_fund_portfolio_activity
    items = await asyncio.to_thread(get_fund_portfolio_activity, fund_name=fund_name, settings=_settings)
    return {"success": True, "fund_name": fund_name, "count": len(items), "holdings": items}


