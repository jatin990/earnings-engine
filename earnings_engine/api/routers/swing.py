"""Swing Range Channels, Setups, Cycle Timing, and Strategy Backtesting Routes."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Query

from earnings_engine.api.dependencies import _settings
from earnings_engine.api import dashboard_api
from earnings_engine.data import swing_ranges as swing_mod
from earnings_engine.data import swing_scanner as swing_scanner_mod
from earnings_engine.logging_utils import get_logger

logger = get_logger("earnings_engine.api.routers.swing")

router = APIRouter(tags=["Swing Ranges & Strategy Backtest"])


def _get_settings():
    return _settings() if callable(_settings) else _settings


@router.get("/api/v1/swing-range")
@router.get("/api/v1/dashboard/swing-range")
async def get_swing_range_endpoint(
    watchlist: str = Query("my_watchlist", description="Watchlist name"),
    ticker: str = Query(..., description="Stock ticker symbol"),
):
    """Retrieve support and resistance channel bounds and cycle counts."""
    try:
        rng = await asyncio.to_thread(swing_mod.get_swing_range, watchlist, ticker, settings=_get_settings())
        if not rng:
            return {"success": False, "found": False, "range": None}
        return {"success": True, "found": True, "range": rng}
    except Exception as e:
        logger.exception("Error in get_swing_range: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/v1/swing-ranges/{watchlist}/{ticker}")
async def get_swing_range_by_path(watchlist: str, ticker: str):
    """Retrieve swing range by path parameters."""
    return await get_swing_range_endpoint(watchlist=watchlist, ticker=ticker)


@router.get("/api/v1/swing-range/list")
@router.get("/api/v1/dashboard/swing-range/list")
async def list_swing_ranges_endpoint(
    watchlist: str | None = Query(None, description="Watchlist name filter"),
):
    """List all swing ranges, optionally filtered by watchlist."""
    try:
        ranges = await asyncio.to_thread(swing_mod.list_ranges, watchlist=watchlist, settings=_get_settings())
        return {"success": True, "count": len(ranges), "ranges": ranges}
    except Exception as e:
        logger.exception("Error in list_swing_ranges: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/v1/swing-range")
@router.post("/api/v1/dashboard/swing-range")
@router.post("/api/v1/swing-range/set")
@router.post("/api/v1/swing-ranges/save")
async def set_swing_range_endpoint(request: dict):
    """Set or override manual swing support/resistance bounds."""
    watchlist = request.get("watchlist", "my_watchlist")
    ticker = request.get("ticker")
    lower = request.get("lower") if request.get("lower") is not None else request.get("support")
    upper = request.get("upper") if request.get("upper") is not None else request.get("resistance")
    cycles = request.get("cycles")
    
    if not ticker or lower is None or upper is None:
        raise HTTPException(status_code=400, detail="ticker, lower/support, and upper/resistance are required")
    try:
        saved = await asyncio.to_thread(
            swing_mod.set_user_range,
            watchlist=watchlist,
            ticker=ticker,
            lower=float(lower),
            upper=float(upper),
            cycles=int(cycles) if cycles is not None else None,
            settings=_get_settings(),
        )
        return {"success": True, "range": saved, **saved}
    except Exception as e:
        logger.exception("Error saving swing range: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/api/v1/swing-range")
@router.delete("/api/v1/dashboard/swing-range")
async def delete_swing_range_endpoint(
    watchlist: str = Query("my_watchlist"),
    ticker: str = Query(...),
):
    """Delete manual swing range override to revert to automated channel detection."""
    try:
        await asyncio.to_thread(swing_mod.clear_user_range, watchlist, ticker, settings=_get_settings())
        return {"success": True, "deleted": True, "range": None}
    except Exception as e:
        logger.exception("Error deleting swing range: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/v1/swing-range/auto-detect")
@router.post("/api/v1/dashboard/swing-range/auto-detect")
async def auto_detect_swing_range_endpoint(request: dict):
    """Trigger automated swing range detection for a ticker."""
    ticker = request.get("ticker")
    watchlist = request.get("watchlist", "my_watchlist")
    if not ticker:
        raise HTTPException(status_code=400, detail="ticker is required")
    try:
        res = await asyncio.to_thread(dashboard_api.get_swing_range_api, watchlist=watchlist, ticker=ticker)
        return {"success": True, **(res or {})}
    except Exception as e:
        logger.exception("Error auto-detecting swing range for %s: %s", ticker, e)
        raise HTTPException(status_code=500, detail=f"Auto detection failed: {str(e)}")


@router.post("/api/v1/swing-range/calculate")
@router.post("/api/v1/dashboard/swing-range/calculate")
async def calculate_swing_range_endpoint(request: dict):
    """Calculate support/resistance trading range across selected quantitative methods."""
    ticker = request.get("ticker")
    method = request.get("method", "20d")
    watchlist = request.get("watchlist", "ALL")
    if not ticker:
        raise HTTPException(status_code=400, detail="ticker is required")
    try:
        res = await asyncio.to_thread(
            dashboard_api.calculate_trading_range_api,
            ticker=ticker,
            method=method,
            watchlist=watchlist,
        )
        return res
    except Exception as e:
        logger.exception("Error calculating trading range for %s: %s", ticker, e)
        raise HTTPException(status_code=500, detail=f"Range calculation failed: {str(e)}")


@router.post("/api/v1/swing-ranges/auto-detect/{ticker}")
@router.post("/api/v1/swing-ranges/auto-detect/{watchlist}/{ticker}")
async def auto_detect_swing_range_path(ticker: str, watchlist: str = "my_watchlist"):
    """Trigger automated swing range detection by path parameter."""
    return await auto_detect_swing_range_endpoint({"ticker": ticker, "watchlist": watchlist})


@router.post("/api/v1/swing-ranges/calculate/{ticker}")
@router.post("/api/v1/swing-ranges/calculate/{watchlist}/{ticker}")
async def calculate_swing_range_path(ticker: str, watchlist: str = "ALL", method: str = Query("20d")):
    """Trigger trading range calculation by path parameter."""
    return await calculate_swing_range_endpoint({"ticker": ticker, "watchlist": watchlist, "method": method})


@router.get("/api/v1/dashboard/swing/status")
@router.get("/api/v1/swing/status")
async def get_swing_status_endpoint(
    universe: str | None = Query(None, description="Universe / Watchlist filter"),
):
    """Return status summary of tiered swing scanner (Hot/Warm counts, scan intervals)."""
    try:
        status = await asyncio.to_thread(swing_scanner_mod.get_scan_status, universe=universe)
        return status
    except Exception as e:
        logger.exception("Error in get_swing_status: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/v1/dashboard/swing/scan")
@router.post("/api/v1/swing/scan")
async def run_swing_scan_endpoint(request: dict | None = None):
    """Trigger an on-demand scan of the swing universe."""
    universe = (request or {}).get("universe", "ALL")
    try:
        candidates = await asyncio.to_thread(swing_scanner_mod.run_cold_scan, _get_settings(), universe=universe)
        return {
            "success": True,
            "candidates_count": len(candidates),
            "candidates": candidates[:50],
        }
    except Exception as e:
        logger.exception("Error triggering swing scan: %s", e)
        raise HTTPException(status_code=500, detail=f"Swing scan failed: {str(e)}")


@router.get("/api/v1/dashboard/swing")
@router.get("/api/v1/dashboard/swing/setups")
async def get_swing_setups_endpoint(
    market: str | None = Query(None, description="Market universe filter"),
    limit: int = Query(50, ge=1, le=200),
):
    """Retrieve active swing setups with channel bounds, risk/reward, and cycle indicators."""
    try:
        # First try fast retrieval from tiered swing_scanner cache
        cached = await asyncio.to_thread(
            swing_scanner_mod.get_cached_swing_results,
            universe=market,
            settings=_get_settings(),
        )
        if cached:
            return cached[:limit]

        # Fallback to dashboard_api calculation if scanner cache is cold
        setups = await asyncio.to_thread(dashboard_api.get_swing_setups, market=market, limit=limit)
        return setups
    except Exception as e:
        logger.exception("Error in get_swing_setups: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/v1/swing-range/cycles")
@router.get("/api/v1/swing-range/history")
@router.get("/api/v1/dashboard/swing-range/history")
async def get_swing_cycle_history_endpoint(
    watchlist: str = Query("my_watchlist", description="Watchlist name"),
    ticker: str = Query(..., description="Stock ticker symbol"),
):
    """Return historical swing cycle data for a specific ticker."""
    try:
        cycles = await asyncio.to_thread(swing_mod.get_cycle_history, watchlist, ticker, settings=_get_settings())
        return {"success": True, "count": len(cycles), "cycles": cycles}
    except Exception as e:
        logger.exception("Error in get_swing_cycle_history: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/v1/backtest/stats")
async def get_backtest_stats_endpoint():
    """Return walk-forward backtest summary from the event dataset."""
    try:
        from earnings_engine.data.strategy_auditor import get_strategy_performance_summary
        stats = await asyncio.to_thread(get_strategy_performance_summary, settings=_get_settings())
        return {"success": True, "stats": stats}
    except Exception as e:
        logger.exception("Error in get_backtest_stats: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/v1/backtest/latest")
@router.get("/api/v1/backtest/swing/latest")
async def get_latest_backtest_endpoint():
    """Retrieve the most recent strategy audit records."""
    try:
        from earnings_engine.data.strategy_auditor import load_predictions
        records = await asyncio.to_thread(load_predictions, limit=50, settings=_get_settings())
        return {"success": True, "count": len(records) if records else 0, "records": records or []}
    except Exception as e:
        logger.exception("Error in get_latest_backtest: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/v1/backtest/run")
@router.post("/api/v1/backtest/swing/run")
async def run_custom_backtest_endpoint(request: dict):
    """Execute on-demand walk-forward backtesting with custom thresholds."""
    model_name = request.get("model", "gbm")
    threshold = float(request.get("threshold", 0.50))
    cost = float(request.get("cost_per_trade", 0.001))
    try:
        from earnings_engine.backtest.engine import run_backtest, BacktestConfig
        from earnings_engine.dataset import load_dataset
        from earnings_engine.models.registry import make_model

        dataset = await asyncio.to_thread(load_dataset)
        m = make_model(model_name)
        cfg = BacktestConfig(threshold=threshold, cost_per_trade=cost)
        result = await asyncio.to_thread(run_backtest, dataset=dataset, model=m, cfg=cfg)
        return {"success": True, "metrics": result.metrics if hasattr(result, "metrics") else {}}
    except Exception as e:
        logger.exception("Backtest run failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
