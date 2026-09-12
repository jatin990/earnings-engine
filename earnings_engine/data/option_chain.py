"""Option Chain analytics & sentiment scoring.

Calculates key derivatives metrics for catalyst and earnings prediction:
- Put-Call Ratio (PCR - Volume & OI based)
- Max Pain strike price (the strike where option sellers profit most)
- ATM Implied Volatility (IV) & estimated earnings move
- Option OI concentration and buildup analysis
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from earnings_engine.config import Settings
from earnings_engine.data.providers.provider_manager import get_data_manager
from earnings_engine.data.universe import is_fno_eligible

logger = logging.getLogger("earnings_engine.data.option_chain")

_NON_FNO_SYMBOLS: set[str] = set()
_OPTION_CHAIN_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_CACHE_TTL_SECONDS = 900.0  # 15 minutes


def _resolve_spot_price(clean_symbol: str, spot_price: float | None, settings: Settings | None = None) -> float:
    """Resolve spot price from local price_history database first before hitting network quote."""
    if spot_price is not None and spot_price > 0:
        return float(spot_price)

    # 1. Try local price_history cache
    try:
        from earnings_engine.data.prices import load_prices
        settings = settings or Settings()
        pdf = load_prices(clean_symbol, settings)
        if pdf is not None and not pdf.empty and "close" in pdf.columns:
            last_close = float(pdf["close"].dropna().iloc[-1])
            if last_close > 0:
                return last_close
    except Exception:
        pass

    # 2. Fallback to live quote
    try:
        mgr = get_data_manager(settings)
        q = mgr.fetch_quote(clean_symbol)
        p = float(q.get("price") or 0)
        if p > 0:
            return p
    except Exception:
        pass

    return 100.0


def store_option_chain_snapshot(data: dict[str, Any], settings: Settings | None = None) -> bool:
    """Persist an Option Chain snapshot record into SQLite option_chain_history."""
    if not data or not data.get("symbol"):
        return False

    settings = settings or Settings()
    from earnings_engine.data.db import get_db_connection
    from earnings_engine.data.migrations import apply_migrations

    try:
        apply_migrations(settings)
        conn = get_db_connection(settings)
        now_dt = datetime.now()
        as_of_date = data.get("as_of_date") or now_dt.strftime("%Y-%m-%d")
        created_at = now_dt.isoformat()
        sym = str(data.get("symbol")).upper().replace(".NS", "")

        conn.execute(
            """
            INSERT INTO option_chain_history (
                symbol, as_of_date, spot_price, pcr_oi, pcr_volume,
                max_pain_strike, sentiment, call_oi_total, put_oi_total,
                resistance_strike, support_strike, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, as_of_date) DO UPDATE SET
                spot_price = excluded.spot_price,
                pcr_oi = excluded.pcr_oi,
                pcr_volume = excluded.pcr_volume,
                max_pain_strike = excluded.max_pain_strike,
                sentiment = excluded.sentiment,
                call_oi_total = excluded.call_oi_total,
                put_oi_total = excluded.put_oi_total,
                resistance_strike = excluded.resistance_strike,
                support_strike = excluded.support_strike,
                created_at = excluded.created_at
            """,
            (
                sym,
                as_of_date,
                data.get("spot_price"),
                data.get("pcr_oi"),
                data.get("pcr_volume"),
                data.get("max_pain_strike"),
                data.get("sentiment"),
                data.get("call_oi_total"),
                data.get("put_oi_total"),
                data.get("resistance_strike"),
                data.get("support_strike"),
                created_at,
            ),
        )
        conn.commit()
        return True
    except Exception as e:
        logger.debug("[OPTION-CHAIN-DB] Could not persist snapshot for %s: %s", data.get("symbol"), e)
        return False


def get_option_chain_history(symbol: str, limit: int = 30, settings: Settings | None = None) -> list[dict[str, Any]]:
    """Retrieve historical Option Chain snapshots for a symbol."""
    clean_symbol = symbol.upper().replace(".NS", "")
    settings = settings or Settings()
    from earnings_engine.data.db import get_db_connection

    try:
        conn = get_db_connection(settings)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT as_of_date, spot_price, pcr_oi, pcr_volume, max_pain_strike,
                   sentiment, call_oi_total, put_oi_total, resistance_strike, support_strike, created_at
            FROM option_chain_history
            WHERE symbol = ?
            ORDER BY as_of_date DESC
            LIMIT ?
            """,
            (clean_symbol, limit),
        )
        rows = cursor.fetchall()
        cols = [c[0] for c in cursor.description]
        return [dict(zip(cols, r)) for r in rows]
    except Exception as e:
        logger.debug("[OPTION-CHAIN-DB] Could not load history for %s: %s", clean_symbol, e)
        return []


def analyze_option_chain(
    symbol: str,
    spot_price: float | None = None,
    expiry_date: str | None = None,
    strike_range: int | None = 20,
    force_refresh: bool = False,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Retrieve and analyze Option Chain metrics for an equity or index.

    Returns
    -------
    dict with:
      - pcr_oi: Put-Call Ratio based on Open Interest
      - pcr_volume: Put-Call Ratio based on Traded Volume
      - max_pain_strike: Strike price with lowest total loss for option sellers
      - sentiment: 'BULLISH' | 'BEARISH' | 'NEUTRAL'
      - call_oi_total: Total Call Open Interest
      - put_oi_total: Total Put Open Interest
      - resistance_strike: Major resistance strike (highest Call OI)
      - support_strike: Major support strike (highest Put OI)
      - spot_price: Spot underlying price
      - expiries: List of available expiry date strings
      - selected_expiry: Active expiry date
      - strikes: Formatted list of strike dictionaries for table & chart
      - status: 'LIVE' | 'ARCHIVED' | 'NOT_FNO' | 'OFFLINE'
    """
    clean_symbol = symbol.upper().replace(".NS", "")
    cache_key = f"{clean_symbol}:{expiry_date or 'default'}:{strike_range or 'all'}"

    # Fast return from TTL cache unless force_refresh requested
    now = pd.Timestamp.now().timestamp()
    if not force_refresh and cache_key in _OPTION_CHAIN_CACHE:
        cached_time, cached_res = _OPTION_CHAIN_CACHE[cache_key]
        if (now - cached_time) < _CACHE_TTL_SECONDS:
            return cached_res

    # Anti-Fabrication & Latency Guard: Non-F&O cash equities have no derivatives
    if not is_fno_eligible(clean_symbol):
        res = {
            "symbol": clean_symbol,
            "status": "NOT_FNO",
            "message": f"{clean_symbol} is not eligible for NSE Equity Derivatives (F&O). Cash market only.",
            "pcr_oi": None,
            "pcr_volume": None,
            "max_pain_strike": None,
            "sentiment": "NEUTRAL",
            "call_oi_total": 0,
            "put_oi_total": 0,
            "resistance_strike": None,
            "support_strike": None,
            "records_count": 0,
            "expiries": [],
            "selected_expiry": None,
            "strikes": [],
            "signals": ["NOT_FNO_ELIGIBLE"],
            "spot_price": spot_price,
        }
        _OPTION_CHAIN_CACHE[cache_key] = (now, res)
        return res

    spot_price = _resolve_spot_price(clean_symbol, spot_price, settings)

    logger.debug("[OPTION-CHAIN] Fetching Option Chain for symbol=%s (expiry=%s, spot=%s)...", clean_symbol, expiry_date, spot_price)
    mgr = get_data_manager(settings)
    raw_chain = mgr.fetch_option_chain(clean_symbol, expiry_date=expiry_date)

    records = raw_chain.get("data", [])
    expiries = raw_chain.get("expiries", [])
    selected_expiry = raw_chain.get("selected_expiry")
    raw_spot = raw_chain.get("underlying_value")
    if raw_spot and float(raw_spot) > 0:
        spot_price = float(raw_spot)

    if not records:
        logger.info("[OPTION-CHAIN] Real-time Option Chain empty for %s. Checking historical snapshots...", clean_symbol)
        history = get_option_chain_history(clean_symbol, limit=1, settings=settings)
        if history:
            last_snap = history[0]
            res = {
                "symbol": clean_symbol,
                "status": "ARCHIVED",
                "message": f"NSE live option chain unavailable (market closed/offline). Displaying last recorded snapshot from {last_snap.get('as_of_date')}.",
                "spot_price": last_snap.get("spot_price") or spot_price,
                "pcr_oi": last_snap.get("pcr_oi"),
                "pcr_volume": last_snap.get("pcr_volume"),
                "max_pain_strike": last_snap.get("max_pain_strike"),
                "sentiment": last_snap.get("sentiment") or "NEUTRAL",
                "call_oi_total": last_snap.get("call_oi_total") or 0,
                "put_oi_total": last_snap.get("put_oi_total") or 0,
                "resistance_strike": last_snap.get("resistance_strike"),
                "support_strike": last_snap.get("support_strike"),
                "records_count": 0,
                "expiries": expiries,
                "selected_expiry": selected_expiry,
                "strikes": [],
                "as_of_date": last_snap.get("as_of_date"),
                "signals": ["ARCHIVED_SNAPSHOT"],
            }
            _OPTION_CHAIN_CACHE[cache_key] = (now, res)
            return res

        # No live records and no archived snapshot available
        res = {
            "symbol": clean_symbol,
            "status": "OFFLINE",
            "message": "Live NSE option chain unreachable and no archival snapshot found for this symbol.",
            "spot_price": spot_price,
            "pcr_oi": None,
            "pcr_volume": None,
            "max_pain_strike": None,
            "sentiment": "NEUTRAL",
            "call_oi_total": 0,
            "put_oi_total": 0,
            "resistance_strike": None,
            "support_strike": None,
            "records_count": 0,
            "expiries": expiries,
            "selected_expiry": selected_expiry,
            "strikes": [],
            "signals": ["OPTION_CHAIN_UNREACHABLE"],
        }
        _OPTION_CHAIN_CACHE[cache_key] = (now, res)
        return res

    res = _calculate_option_metrics_from_records(
        symbol=clean_symbol,
        records=records,
        spot_price=spot_price,
        strike_range=strike_range,
    )
    res["spot_price"] = spot_price
    res["expiries"] = expiries
    res["selected_expiry"] = selected_expiry
    res["timestamp"] = raw_chain.get("timestamp") or datetime.now().isoformat()
    _OPTION_CHAIN_CACHE[cache_key] = (now, res)
    store_option_chain_snapshot(res, settings)
    logger.info(
        "[OPTION-CHAIN] [NSE-Live] %s (%d strikes, expiry=%s) -> Sentiment: %s, PCR(OI): %s, Max Pain: ₹%s",
        clean_symbol,
        len(res.get("strikes", [])),
        selected_expiry,
        res.get("sentiment"),
        res.get("pcr_oi"),
        res.get("max_pain_strike"),
    )
    return res


def _calculate_option_metrics_from_records(
    symbol: str,
    records: list[dict[str, Any]],
    spot_price: float | None,
    strike_range: int | None = 20,
) -> dict[str, Any]:
    """Parse real option chain records into quantitative metrics and structured strike ladder."""
    call_oi = 0.0
    put_oi = 0.0
    call_vol = 0.0
    put_vol = 0.0

    raw_strikes: list[dict[str, Any]] = []

    for r in records:
        strike = float(r.get("strikePrice") or r.get("strike_price") or 0)
        ce = r.get("CE") if isinstance(r.get("CE"), dict) else {}
        pe = r.get("PE") if isinstance(r.get("PE"), dict) else {}

        c_oi = float(r.get("CE_openInterest") or ce.get("openInterest") or r.get("call_oi") or 0)
        p_oi = float(r.get("PE_openInterest") or pe.get("openInterest") or r.get("put_oi") or 0)
        c_vol = float(r.get("CE_totalTradedVolume") or ce.get("totalTradedVolume") or r.get("call_vol") or 0)
        p_vol = float(r.get("PE_totalTradedVolume") or pe.get("totalTradedVolume") or r.get("put_vol") or 0)

        c_chg_oi = float(r.get("CE_changeinOpenInterest") or ce.get("changeinOpenInterest") or ce.get("pchangeinOpenInterest") or 0)
        p_chg_oi = float(r.get("PE_changeinOpenInterest") or pe.get("changeinOpenInterest") or pe.get("pchangeinOpenInterest") or 0)
        c_pchange_oi = float(ce.get("pchangeinOpenInterest") or 0)
        p_pchange_oi = float(pe.get("pchangeinOpenInterest") or 0)

        c_ltp = float(r.get("CE_lastPrice") or ce.get("lastPrice") or 0)
        p_ltp = float(r.get("PE_lastPrice") or pe.get("lastPrice") or 0)

        c_iv = float(r.get("CE_impliedVolatility") or ce.get("impliedVolatility") or 0)
        p_iv = float(r.get("PE_impliedVolatility") or pe.get("impliedVolatility") or 0)

        call_oi += c_oi
        put_oi += p_oi
        call_vol += c_vol
        put_vol += p_vol

        if strike > 0:
            raw_strikes.append({
                "strike": strike,
                "ce_oi": int(c_oi),
                "ce_change_oi": int(c_chg_oi),
                "ce_pchange_oi": round(c_pchange_oi, 2),
                "ce_ltp": round(c_ltp, 2),
                "ce_iv": round(c_iv, 2),
                "ce_vol": int(c_vol),
                "pe_oi": int(p_oi),
                "pe_change_oi": int(p_chg_oi),
                "pe_pchange_oi": round(p_pchange_oi, 2),
                "pe_ltp": round(p_ltp, 2),
                "pe_iv": round(p_iv, 2),
                "pe_vol": int(p_vol),
                "call_oi": c_oi,
                "put_oi": p_oi,
            })

    # Sort strikes ascending
    raw_strikes.sort(key=lambda x: x["strike"])

    pcr_oi = round(put_oi / call_oi, 2) if call_oi > 0 else 1.0
    pcr_vol = round(put_vol / call_vol, 2) if call_vol > 0 else 1.0

    # Max pain calculation across all strikes
    max_pain = _calculate_max_pain(raw_strikes) if raw_strikes else (spot_price or 0.0)

    # Sentiment interpretation
    if pcr_oi >= 1.2:
        sentiment = "BULLISH"
    elif pcr_oi <= 0.8:
        sentiment = "BEARISH"
    else:
        sentiment = "NEUTRAL"

    # Identify Call Wall (Resistance) and Put Wall (Support)
    sdf = pd.DataFrame(raw_strikes) if raw_strikes else pd.DataFrame()
    high_call_strike = (
        float(sdf.loc[sdf["call_oi"].idxmax()]["strike"])
        if not sdf.empty and "call_oi" in sdf.columns and sdf["call_oi"].max() > 0
        else None
    )
    high_put_strike = (
        float(sdf.loc[sdf["put_oi"].idxmax()]["strike"])
        if not sdf.empty and "put_oi" in sdf.columns and sdf["put_oi"].max() > 0
        else None
    )

    # Find ATM strike
    atm_strike = None
    if raw_strikes and spot_price and spot_price > 0:
        atm_strike = min(raw_strikes, key=lambda x: abs(x["strike"] - spot_price))["strike"]
    elif raw_strikes:
        atm_strike = raw_strikes[len(raw_strikes) // 2]["strike"]

    # Filter to strike_range around ATM if specified
    formatted_strikes: list[dict[str, Any]] = []
    if raw_strikes:
        atm_idx = 0
        for i, s in enumerate(raw_strikes):
            if s["strike"] == atm_strike:
                atm_idx = i
                break

        if strike_range and strike_range > 0 and len(raw_strikes) > (strike_range * 2):
            start_idx = max(0, atm_idx - strike_range)
            end_idx = min(len(raw_strikes), atm_idx + strike_range + 1)
            selected_subset = raw_strikes[start_idx:end_idx]
        else:
            selected_subset = raw_strikes

        current_spot = spot_price or atm_strike or 0.0
        for s in selected_subset:
            stk = s["strike"]
            is_atm = stk == atm_strike
            # CE is In-The-Money when Strike < Spot
            ce_itm = stk < current_spot
            # PE is In-The-Money when Strike > Spot
            pe_itm = stk > current_spot

            formatted_strikes.append({
                "strike": stk,
                "is_atm": is_atm,
                "ce_itm": ce_itm,
                "pe_itm": pe_itm,
                "ce_oi": s["ce_oi"],
                "ce_change_oi": s["ce_change_oi"],
                "ce_pchange_oi": s["ce_pchange_oi"],
                "ce_ltp": s["ce_ltp"],
                "ce_iv": s["ce_iv"],
                "ce_vol": s["ce_vol"],
                "pe_oi": s["pe_oi"],
                "pe_change_oi": s["pe_change_oi"],
                "pe_pchange_oi": s["pe_pchange_oi"],
                "pe_ltp": s["pe_ltp"],
                "pe_iv": s["pe_iv"],
                "pe_vol": s["pe_vol"],
            })

    return {
        "symbol": symbol,
        "pcr_oi": pcr_oi,
        "pcr_volume": pcr_vol,
        "max_pain_strike": max_pain,
        "sentiment": sentiment,
        "call_oi_total": int(call_oi),
        "put_oi_total": int(put_oi),
        "resistance_strike": high_call_strike,
        "support_strike": high_put_strike,
        "atm_strike": atm_strike,
        "records_count": len(formatted_strikes),
        "strikes": formatted_strikes,
        "status": "LIVE",
    }


def _calculate_max_pain(strikes_data: list[dict[str, float]]) -> float:
    """Calculate the strike price where option buyers lose the most money."""
    if not strikes_data:
        return 0.0

    strikes = [d["strike"] for d in strikes_data]
    min_loss = float("inf")
    best_strike = strikes[0]

    for test_strike in strikes:
        total_loss = 0.0
        for d in strikes_data:
            s = d["strike"]
            c_oi = d["call_oi"]
            p_oi = d["put_oi"]

            # Call loss: max(0, test_strike - s) * c_oi
            if test_strike > s:
                total_loss += (test_strike - s) * c_oi

            # Put loss: max(0, s - test_strike) * p_oi
            if s > test_strike:
                total_loss += (s - test_strike) * p_oi

        if total_loss < min_loss:
            min_loss = total_loss
            best_strike = test_strike

    return round(best_strike, 2)
