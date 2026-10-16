"""FastAPI REST router for NSE Option Chain & Derivatives Intelligence.

Provides endpoints for:
- Live & historical Option Chain lookup with Max Pain, PCR, Walls, and Strike Ladders
- Multi-day historical Option Chain positioning snapshots from SQLite
- Supported F&O Symbols (Indices and liquid equities)
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from earnings_engine.api.dependencies import _settings
from earnings_engine.data import option_chain as oc_mod
from earnings_engine.data import options_chart_engine as oce_mod
from earnings_engine.data.db import get_db_connection
from earnings_engine.data.universe import is_fno_eligible, _SEED_NSE_FNO
from earnings_engine.logging_utils import get_logger

logger = get_logger("earnings_engine.api.routers.options")

router = APIRouter(tags=["Option Chain & Derivatives"])


def _get_settings():
    return _settings() if callable(_settings) else _settings


@router.get("/api/v1/options/symbols")
async def get_options_symbols(
    query: str | None = Query(None, description="Optional search filter for symbol"),
) -> dict[str, Any]:
    """Return list of supported NSE F&O indices and high-liquidity symbols."""
    indices = [
        {"symbol": "NIFTY", "name": "NIFTY 50", "type": "INDEX", "is_index": True},
        {"symbol": "BANKNIFTY", "name": "NIFTY BANK", "type": "INDEX", "is_index": True},
        {"symbol": "FINNIFTY", "name": "NIFTY FINANCIAL SERVICES", "type": "INDEX", "is_index": True},
        {"symbol": "MIDCPNIFTY", "name": "NIFTY MIDCAP SELECT", "type": "INDEX", "is_index": True},
        {"symbol": "SENSEX", "name": "BSE SENSEX", "type": "INDEX", "is_index": True, "exchange": "BSE"},
    ]

    popular_equities = [
        {"symbol": "RELIANCE", "name": "Reliance Industries", "type": "EQUITY", "is_index": False},
        {"symbol": "HDFCBANK", "name": "HDFC Bank Ltd.", "type": "EQUITY", "is_index": False},
        {"symbol": "ICICIBANK", "name": "ICICI Bank Ltd.", "type": "EQUITY", "is_index": False},
        {"symbol": "INFY", "name": "Infosys Ltd.", "type": "EQUITY", "is_index": False},
        {"symbol": "TCS", "name": "Tata Consultancy Services", "type": "EQUITY", "is_index": False},
        {"symbol": "SBIN", "name": "State Bank of India", "type": "EQUITY", "is_index": False},
        {"symbol": "BHARTIARTL", "name": "Bharti Airtel Ltd.", "type": "EQUITY", "is_index": False},
        {"symbol": "KOTAKBANK", "name": "Kotak Mahindra Bank", "type": "EQUITY", "is_index": False},
        {"symbol": "LT", "name": "Larsen & Toubro", "type": "EQUITY", "is_index": False},
        {"symbol": "ITC", "name": "ITC Ltd.", "type": "EQUITY", "is_index": False},
        {"symbol": "AXISBANK", "name": "Axis Bank Ltd.", "type": "EQUITY", "is_index": False},
        {"symbol": "TATAMOTORS", "name": "Tata Motors Ltd.", "type": "EQUITY", "is_index": False},
        {"symbol": "BAJFINANCE", "name": "Bajaj Finance Ltd.", "type": "EQUITY", "is_index": False},
        {"symbol": "MARUTI", "name": "Maruti Suzuki India", "type": "EQUITY", "is_index": False},
        {"symbol": "SUNPHARMA", "name": "Sun Pharma Industries", "type": "EQUITY", "is_index": False},
    ]

    # Combine all known F&O symbols
    all_syms = list(indices)
    existing_set = {s["symbol"] for s in all_syms}
    for eq in popular_equities:
        if eq["symbol"] not in existing_set:
            all_syms.append(eq)
            existing_set.add(eq["symbol"])

    # Add remaining from _SEED_NSE_FNO
    for raw in _SEED_NSE_FNO:
        clean = raw.upper().replace(".NS", "").strip()
        if clean not in existing_set:
            all_syms.append({
                "symbol": clean,
                "name": clean,
                "type": "EQUITY",
                "is_index": False,
            })
            existing_set.add(clean)

    if query:
        q = query.strip().upper()
        all_syms = [s for s in all_syms if q in s["symbol"] or q in s["name"].upper()]

    return {
        "success": True,
        "count": len(all_syms),
        "symbols": all_syms,
    }


@router.get("/api/v1/options/history")
async def get_options_history(
    symbol: str = Query(..., description="NSE symbol or index name (e.g., NIFTY, RELIANCE)"),
    limit: int = Query(30, ge=1, le=100, description="Max historical snapshot records"),
) -> dict[str, Any]:
    """Retrieve multi-day recorded Option Chain snapshots from SQLite for trend analysis."""
    clean_symbol = symbol.strip().upper().replace(".NS", "")
    try:
        history = await asyncio.to_thread(
            oc_mod.get_option_chain_history,
            symbol=clean_symbol,
            limit=limit,
            settings=_get_settings(),
        )
        return {
            "success": True,
            "symbol": clean_symbol,
            "count": len(history),
            "history": history,
        }
    except Exception as e:
        logger.exception("Error in get_options_history for %s: %s", clean_symbol, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/v1/options/chain")
async def get_options_chain(
    symbol: str = Query("NIFTY", description="NSE symbol or index (e.g. NIFTY, BANKNIFTY, RELIANCE)"),
    expiry: str | None = Query(None, description="Target expiry date string (e.g. 27-MAR-2025)"),
    strike_range: int | None = Query(20, ge=5, le=50, description="Number of strikes above and below ATM"),
    force_refresh: bool = Query(False, description="Bypass in-memory cache and query live NSE"),
) -> dict[str, Any]:
    """Analyze real-time or latest archival Option Chain for an equity or index."""
    clean_symbol = symbol.strip().upper().replace(".NS", "")

    try:
        analysis = await asyncio.to_thread(
            oc_mod.analyze_option_chain,
            symbol=clean_symbol,
            expiry_date=expiry,
            strike_range=strike_range,
            force_refresh=force_refresh,
            settings=_get_settings(),
        )

        return {
            "success": True,
            "data": analysis,
        }
    except Exception as e:
        logger.exception("Error analyzing option chain for %s: %s", clean_symbol, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/v1/options/chart-intelligence")
async def get_options_chart_intelligence(
    symbol: str = Query("NIFTY", description="NSE symbol or index (e.g. NIFTY, BANKNIFTY, RELIANCE)"),
    interval: str = Query("5m", description="Candle interval (1m, 5m, 15m, 1h, 1d)"),
    period: str = Query("5d", description="Lookback window (e.g. 5d, 1mo, 6mo)"),
    force_refresh: bool = Query(False, description="Bypass cache and refresh live candles"),
    allow_non_fno: bool = Query(False, description="Allow fallback for non-FNO tickers"),
) -> dict[str, Any]:
    """Retrieve full candlestick history, indicators (VWAP, ORB), Order Blocks, and tactical trade plans."""
    clean_symbol = symbol.strip().upper().replace(".NS", "")
    try:
        data = await asyncio.to_thread(
            oce_mod.get_options_chart_intelligence,
            symbol=clean_symbol,
            interval=interval,
            period=period,
            force_refresh=force_refresh,
            allow_non_fno=allow_non_fno,
            settings=_get_settings(),
        )
        return data
    except Exception as e:
        logger.exception("Error in get_options_chart_intelligence for %s: %s", clean_symbol, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/v1/options/setups/history")
async def get_options_setups_history(
    symbol: str | None = Query(None, description="Optional symbol filter (e.g. NIFTY, BANKNIFTY)"),
    outcome: str | None = Query(None, description="Optional outcome filter (ACTIVE, TARGET1_HIT, TARGET2_HIT, STOPPED_OUT)"),
    limit: int = Query(50, ge=1, le=200, description="Max history records to return"),
) -> dict[str, Any]:
    """Retrieve historical tracked algorithmic option setups from SQLite ledger."""
    def _fetch():
        conn = get_db_connection(_get_settings())
        return oc_mod.get_tracked_option_setups(
            conn=conn,
            symbol=symbol,
            outcome=outcome,
            limit=limit,
        )

    try:
        records = await asyncio.to_thread(_fetch)
        return {
            "success": True,
            "count": len(records),
            "symbol": symbol.upper().replace(".NS", "") if symbol else None,
            "outcome": outcome.upper() if outcome else None,
            "setups": records,
        }
    except Exception as e:
        logger.exception("Error in get_options_setups_history: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/v1/options/setups/evaluate")
async def evaluate_options_setups(
    symbol: str = Query("NIFTY", description="Symbol to evaluate active setups for"),
    current_spot: float | None = Query(None, description="Optional current spot price override"),
) -> dict[str, Any]:
    """Evaluate active tracked setups against current spot price and update outcome state machine."""
    clean_symbol = symbol.strip().upper().replace(".NS", "")

    def _eval():
        settings = _get_settings()
        spot = current_spot
        if spot is None or spot <= 0:
            spot = oc_mod._resolve_spot_price(clean_symbol, None, settings)
        if not spot or spot <= 0:
            return []

        conn = get_db_connection(settings)
        return oc_mod.evaluate_tracked_option_setups(
            conn=conn,
            symbol=clean_symbol,
            current_spot=float(spot),
        )

    try:
        updates = await asyncio.to_thread(_eval)
        return {
            "success": True,
            "symbol": clean_symbol,
            "evaluated_count": len(updates),
            "updates": updates,
        }
    except Exception as e:
        logger.exception("Error in evaluate_options_setups for %s: %s", clean_symbol, e)
        raise HTTPException(status_code=500, detail=str(e))


