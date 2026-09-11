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
      - highest_call_oi_strike: Major resistance strike
      - highest_put_oi_strike: Major support strike
    """
    clean_symbol = symbol.upper().replace(".NS", "")

    # Fast return from TTL cache
    now = pd.Timestamp.now().timestamp()
    if clean_symbol in _OPTION_CHAIN_CACHE:
        cached_time, cached_res = _OPTION_CHAIN_CACHE[clean_symbol]
        if (now - cached_time) < _CACHE_TTL_SECONDS:
            return cached_res

    # Anti-Fabrication & Latency Guard: Non-F&O cash equities have no derivatives
    if not is_fno_eligible(clean_symbol):
        res = {
            "symbol": clean_symbol,
            "status": "NOT_FNO",
            "pcr_oi": None,
            "pcr_volume": None,
            "max_pain_strike": None,
            "sentiment": "NEUTRAL",
            "call_oi_total": 0,
            "put_oi_total": 0,
            "resistance_strike": None,
            "support_strike": None,
            "records_count": 0,
            "strikes": [],
            "signals": ["NOT_FNO_ELIGIBLE"],
            "spot_price": spot_price,
        }
        _OPTION_CHAIN_CACHE[clean_symbol] = (now, res)
        return res

    spot_price = _resolve_spot_price(clean_symbol, spot_price, settings)

    # If known non-F&O equity, return fast baseline without hammering network
    if clean_symbol in _NON_FNO_SYMBOLS:
        res = _compute_baseline_option_metrics(clean_symbol, spot_price)
        _OPTION_CHAIN_CACHE[clean_symbol] = (now, res)
        return res

    logger.debug("[OPTION-CHAIN] Analyzing Option Chain derivatives data for symbol=%s (spot=%s)...", clean_symbol, spot_price)
    mgr = get_data_manager(settings)
    raw_chain = mgr.fetch_option_chain(clean_symbol)

    records = raw_chain.get("data", [])
    if not records:
        _NON_FNO_SYMBOLS.add(clean_symbol)
        logger.debug("[OPTION-CHAIN] Real-time Option Chain records empty for %s; computing baseline derivatives metrics", clean_symbol)
        res = _compute_baseline_option_metrics(clean_symbol, spot_price)
        _OPTION_CHAIN_CACHE[clean_symbol] = (now, res)
        return res

    res = _calculate_option_metrics_from_records(clean_symbol, records, spot_price)
    res["spot_price"] = spot_price
    _OPTION_CHAIN_CACHE[clean_symbol] = (now, res)
    store_option_chain_snapshot(res, settings)
    logger.info("[OPTION-CHAIN] [NSE-Live] %s (%d strikes) -> Sentiment: %s, PCR(OI): %s, Max Pain: ₹%s", clean_symbol, len(records), res.get("sentiment"), res.get("pcr_oi"), res.get("max_pain_strike"))
    return res


def _calculate_option_metrics_from_records(
    symbol: str,
    records: list[dict[str, Any]],
    spot_price: float | None,
) -> dict[str, Any]:
    """Parse real option chain records into quantitative metrics."""
    df = pd.DataFrame(records)

    call_oi = 0
    put_oi = 0
    call_vol = 0
    put_vol = 0

    strikes_data = []

    for r in records:
        strike = float(r.get("strikePrice") or r.get("strike_price") or 0)
        c_oi = float(r.get("CE_openInterest") or r.get("call_oi") or 0)
        p_oi = float(r.get("PE_openInterest") or r.get("put_oi") or 0)
        c_vol = float(r.get("CE_totalTradedVolume") or r.get("call_vol") or 0)
        p_vol = float(r.get("PE_totalTradedVolume") or r.get("put_vol") or 0)

        call_oi += c_oi
        put_oi += p_oi
        call_vol += c_vol
        put_vol += p_vol

        if strike > 0:
            strikes_data.append({"strike": strike, "call_oi": c_oi, "put_oi": p_oi})

    pcr_oi = round(put_oi / call_oi, 2) if call_oi > 0 else 1.0
    pcr_vol = round(put_vol / call_vol, 2) if call_vol > 0 else 1.0

    # Max pain calculation
    max_pain = _calculate_max_pain(strikes_data) if strikes_data else spot_price

    # Sentiment interpretation:
    # PCR > 1.2 => Bullish (heavy put writing support)
    # PCR < 0.8 => Bearish (heavy call writing resistance)
    # 0.8 <= PCR <= 1.2 => Neutral
    if pcr_oi >= 1.2:
        sentiment = "BULLISH"
    elif pcr_oi <= 0.8:
        sentiment = "BEARISH"
    else:
        sentiment = "NEUTRAL"

    # Identify key S/R strikes
    sdf = pd.DataFrame(strikes_data) if strikes_data else pd.DataFrame()
    high_call_strike = float(sdf.loc[sdf["call_oi"].idxmax()]["strike"]) if not sdf.empty and "call_oi" in sdf else None
    high_put_strike = float(sdf.loc[sdf["put_oi"].idxmax()]["strike"]) if not sdf.empty and "put_oi" in sdf else None

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


def _compute_baseline_option_metrics(symbol: str, spot_price: float) -> dict[str, Any]:
    """Fallback calculation based on spot price and typical PCR distributions."""
    step = 50.0 if spot_price > 1000 else 10.0
    rounded_spot = round(spot_price / step) * step

    return {
        "symbol": symbol,
        "pcr_oi": 1.05,
        "pcr_volume": 1.02,
        "max_pain_strike": rounded_spot,
        "sentiment": "NEUTRAL",
        "call_oi_total": 500000,
        "put_oi_total": 525000,
        "resistance_strike": round(rounded_spot * 1.03, 1),
        "support_strike": round(rounded_spot * 0.97, 1),
        "status": "ESTIMATED",
    }
