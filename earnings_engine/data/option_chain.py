"""Option Chain analytics & sentiment scoring.

Calculates key derivatives metrics for catalyst and earnings prediction:
- Put-Call Ratio (PCR - Volume & OI based)
- Max Pain strike price (the strike where option sellers profit most)
- ATM Implied Volatility (IV) & estimated earnings move
- Option OI concentration and buildup analysis
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from earnings_engine.config import Settings
from earnings_engine.data.providers.provider_manager import get_data_manager
from earnings_engine.data.universe import is_fno_eligible, resolve_fno_symbol

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
        if (pdf is None or pdf.empty) and not clean_symbol.endswith(".NS"):
            pdf = load_prices(f"{clean_symbol}.NS", settings)
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
        if not clean_symbol.endswith(".NS"):
            q_ns = mgr.fetch_quote(f"{clean_symbol}.NS")
            p_ns = float(q_ns.get("price") or 0)
            if p_ns > 0:
                return p_ns
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

        if data.get("market_setups") and data.get("spot_price"):
            try:
                save_tracked_option_setups(
                    conn,
                    data["market_setups"],
                    sym,
                    spot_price=float(data["spot_price"]),
                    gamma_profile=data.get("gamma_profile"),
                    vix_profile=data.get("vix_profile"),
                )
            except Exception as se:
                logger.debug("[OPTION-CHAIN-DB] Could not save tracked setups for %s: %s", sym, se)

        if data.get("spot_price"):
            try:
                evaluate_tracked_option_setups(
                    conn,
                    sym,
                    current_spot=float(data["spot_price"]),
                )
            except Exception as ee:
                logger.debug("[OPTION-CHAIN-DB] Could not evaluate tracked setups for %s: %s", sym, ee)

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
    clean_symbol = resolve_fno_symbol(symbol) or symbol.upper().replace(".NS", "").strip()
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
    vix_data: dict | None = None,
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

    # Identify Call Wall (Resistance) and Put Wall (Support) with Direction-Aware Partitioning
    sdf = pd.DataFrame(raw_strikes) if raw_strikes else pd.DataFrame()
    high_call_strike = None
    high_put_strike = None
    pin_strike = None

    if not sdf.empty:
        curr_spot = float(spot_price or 0.0)

        # 1. Global max OI strikes
        global_call_strike = (
            float(sdf.loc[sdf["call_oi"].idxmax()]["strike"])
            if "call_oi" in sdf.columns and sdf["call_oi"].max() > 0
            else None
        )
        global_put_strike = (
            float(sdf.loc[sdf["put_oi"].idxmax()]["strike"])
            if "put_oi" in sdf.columns and sdf["put_oi"].max() > 0
            else None
        )

        # Check for Straddle Pinning Zone (Peak Call OI == Peak Put OI)
        if global_call_strike and global_put_strike and global_call_strike == global_put_strike:
            pin_strike = global_call_strike

        # 2. Direction-Aware Resistance (Strikes >= Spot preferred)
        calls_overhead = sdf[sdf["strike"] >= curr_spot] if curr_spot > 0 else sdf
        if not calls_overhead.empty and "call_oi" in calls_overhead.columns and calls_overhead["call_oi"].max() > 0:
            high_call_strike = float(calls_overhead.loc[calls_overhead["call_oi"].idxmax()]["strike"])
        else:
            high_call_strike = global_call_strike

        # 3. Direction-Aware Support (Strikes <= Spot preferred)
        puts_underfoot = sdf[sdf["strike"] <= curr_spot] if curr_spot > 0 else sdf
        if not puts_underfoot.empty and "put_oi" in puts_underfoot.columns and puts_underfoot["put_oi"].max() > 0:
            high_put_strike = float(puts_underfoot.loc[puts_underfoot["put_oi"].idxmax()]["strike"])
        else:
            high_put_strike = global_put_strike

    # Find ATM strike
    atm_strike = None
    if raw_strikes and spot_price and spot_price > 0:
        atm_strike = min(raw_strikes, key=lambda x: abs(x["strike"] - spot_price))["strike"]
    elif raw_strikes:
        atm_strike = raw_strikes[len(raw_strikes) // 2]["strike"]

    current_spot = spot_price or atm_strike or 0.0
    gamma_profile_data, enriched_raw = calculate_gamma_profile(
        raw_strikes, spot_price=current_spot, dte_days=4.0
    )

    # Map enriched metrics by strike
    enriched_by_strike = {r["strike"]: r for r in enriched_raw}

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

        for s in selected_subset:
            stk = s["strike"]
            is_atm = stk == atm_strike
            # CE is In-The-Money when Strike < Spot
            ce_itm = stk < current_spot
            # PE is In-The-Money when Strike > Spot
            pe_itm = stk > current_spot

            enr = enriched_by_strike.get(stk, {})

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
                "ce_delta": enr.get("ce_delta", 0.0),
                "ce_gamma": enr.get("ce_gamma", 0.0),
                "ce_theta": enr.get("ce_theta", 0.0),
                "ce_vega": enr.get("ce_vega", 0.0),
                "ce_gex": enr.get("ce_gex", 0.0),
                "pe_oi": s["pe_oi"],
                "pe_change_oi": s["pe_change_oi"],
                "pe_pchange_oi": s["pe_pchange_oi"],
                "pe_ltp": s["pe_ltp"],
                "pe_iv": s["pe_iv"],
                "pe_vol": s["pe_vol"],
                "pe_delta": enr.get("pe_delta", 0.0),
                "pe_gamma": enr.get("pe_gamma", 0.0),
                "pe_theta": enr.get("pe_theta", 0.0),
                "pe_vega": enr.get("pe_vega", 0.0),
                "pe_gex": enr.get("pe_gex", 0.0),
                "net_gex": enr.get("net_gex", 0.0),
                "net_oi_delta": enr.get("net_oi_delta", 0),
            })

    vix_profile = vix_data or {
        "vix_value": 13.5,
        "vix_change_pct": 0.0,
        "vix_regime": "NORMAL_VOL",
    }

    setups = derive_market_setups(
        symbol=symbol,
        spot_price=current_spot,
        records=formatted_strikes if formatted_strikes else raw_strikes,
        gamma_profile=gamma_profile_data,
        vix_data=vix_profile,
        max_pain=max_pain,
        call_wall=high_call_strike,
        put_wall=high_put_strike,
    )

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
        "pin_strike": pin_strike,
        "atm_strike": atm_strike,
        "gamma_profile": gamma_profile_data,
        "vix_profile": vix_profile,
        "market_setups": setups,
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


def calculate_bs_greeks(
    spot: float,
    strike: float,
    dte_days: float,
    iv_pct: float,
    is_call: bool,
    r: float = 0.065,
) -> dict[str, float]:
    """Calculate Black-Scholes-Merton option Greeks: Delta, Gamma, Theta, Vega.

    Args:
        spot: Underlying spot price
        strike: Option strike price
        dte_days: Days to expiry (DTE)
        iv_pct: Implied Volatility in percent (e.g. 15.0 for 15%)
        is_call: True for Call option (CE), False for Put option (PE)
        r: Annualized risk-free interest rate (default: 0.065 for India 10Y/Mibor baseline)

    Returns:
        Dict with keys: delta, gamma, theta (per day), vega (per 1% IV)
    """
    if spot <= 0 or strike <= 0:
        return {"delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0}

    # Safe bounds for DTE and IV
    T = max(dte_days, 0.0) / 365.0
    sigma = max(iv_pct, 0.0) / 100.0

    if T <= 1e-6 or sigma <= 1e-4:
        # At expiration or zero volatility: intrinsic delta, zero other Greeks
        if is_call:
            delta = 1.0 if spot > strike else (0.5 if spot == strike else 0.0)
        else:
            delta = -1.0 if spot < strike else (-0.5 if spot == strike else 0.0)
        return {"delta": delta, "gamma": 0.0, "theta": 0.0, "vega": 0.0}

    sqrt_T = math.sqrt(T)
    d1 = (math.log(spot / strike) + (r + 0.5 * sigma**2) * T) / (sigma * sqrt_T)
    d2 = d1 - sigma * sqrt_T

    # Normal CDF and PDF
    def _norm_cdf(x: float) -> float:
        return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

    def _norm_pdf(x: float) -> float:
        return (1.0 / math.sqrt(2.0 * math.pi)) * math.exp(-0.5 * x * x)

    pdf_d1 = _norm_pdf(d1)
    cdf_d1 = _norm_cdf(d1)
    cdf_d2 = _norm_cdf(d2)

    if is_call:
        delta = cdf_d1
        # Theta per calendar day
        theta = (
            -(spot * pdf_d1 * sigma) / (2.0 * sqrt_T)
            - r * strike * math.exp(-r * T) * cdf_d2
        ) / 365.0
    else:
        delta = cdf_d1 - 1.0
        theta = (
            -(spot * pdf_d1 * sigma) / (2.0 * sqrt_T)
            + r * strike * math.exp(-r * T) * _norm_cdf(-d2)
        ) / 365.0

    gamma = pdf_d1 / (spot * sigma * sqrt_T)
    vega = (spot * sqrt_T * pdf_d1 * 0.01)  # per 1% change in IV

    return {
        "delta": round(float(delta), 4),
        "gamma": round(float(gamma), 6),
        "theta": round(float(theta), 2),
        "vega": round(float(vega), 2),
    }


def calculate_gamma_profile(
    records: list[dict[str, Any]],
    spot_price: float,
    dte_days: float = 4.0,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Compute dealer Gamma Exposure (GEX) per strike, Net GEX regime, Gamma Flip, and Expected Move bands.

    Dealer Gamma Positioning Convention:
    - Market makers are net short calls purchased by the public -> Long Dealer Gamma (+GEX)
    - Market makers are net short puts purchased by the public -> Short Dealer Gamma (-GEX)
    - Net GEX = Call GEX + Put GEX
    - Scaled in standard ₹ Lakhs (10^5) per point.
    """
    if not records or spot_price <= 0:
        return {
            "net_gex": 0.0,
            "gamma_regime": "NEUTRAL",
            "gamma_regime_label": "Neutral Gamma",
            "gamma_flip_strike": spot_price,
            "peak_call_gex_strike": spot_price,
            "peak_put_gex_strike": spot_price,
            "atm_straddle_price": 0.0,
            "expected_move_upper": spot_price,
            "expected_move_lower": spot_price,
            "expected_move_2sigma_upper": spot_price,
            "expected_move_2sigma_lower": spot_price,
        }, records

    enriched_records: list[dict[str, Any]] = []
    total_net_gex = 0.0
    max_call_gex = -1e12
    max_call_gex_strike = spot_price
    min_put_gex = 1e12
    min_put_gex_strike = spot_price

    # Find ATM strike
    atm_record = min(records, key=lambda r: abs(float(r.get("strike", 0.0)) - spot_price))
    atm_ce_ltp = float(atm_record.get("ce_ltp") or 0.0)
    atm_pe_ltp = float(atm_record.get("pe_ltp") or 0.0)
    atm_straddle = atm_ce_ltp + atm_pe_ltp

    # Sort records by strike for cumulative GEX tracking
    sorted_records = sorted(records, key=lambda r: float(r.get("strike", 0.0)))

    cumulative_gex = 0.0
    gamma_flip_strike = None
    prev_cum_gex = 0.0
    prev_strike = None

    for r in sorted_records:
        strike = float(r.get("strike", 0.0))
        ce_oi = int(r.get("ce_oi") or 0)
        pe_oi = int(r.get("pe_oi") or 0)
        ce_change_oi = int(r.get("ce_change_oi") or 0)
        pe_change_oi = int(r.get("pe_change_oi") or 0)
        ce_iv = float(r.get("ce_iv") or 14.0)
        pe_iv = float(r.get("pe_iv") or 14.0)

        # Greeks
        ce_greeks = calculate_bs_greeks(spot_price, strike, dte_days, ce_iv, is_call=True)
        pe_greeks = calculate_bs_greeks(spot_price, strike, dte_days, pe_iv, is_call=False)

        # Dealer GEX: Call GEX (+) and Put GEX (-) in standardized Lakhs
        ce_gex = round((ce_oi * ce_greeks["gamma"] * (spot_price**2) * 0.01) / 100000.0, 2)
        pe_gex = round((-pe_oi * pe_greeks["gamma"] * (spot_price**2) * 0.01) / 100000.0, 2)
        net_gex = round(ce_gex + pe_gex, 2)

        total_net_gex += net_gex

        if ce_gex > max_call_gex:
            max_call_gex = ce_gex
            max_call_gex_strike = strike
        if pe_gex < min_put_gex:
            min_put_gex = pe_gex
            min_put_gex_strike = strike

        # Cumulative GEX for Gamma Flip detection
        prev_cum_gex = cumulative_gex
        cumulative_gex += net_gex
        if gamma_flip_strike is None and prev_strike is not None:
            if (prev_cum_gex < 0 and cumulative_gex >= 0) or (prev_cum_gex >= 0 and cumulative_gex < 0):
                gamma_flip_strike = strike

        prev_strike = strike

        enriched = dict(r)
        enriched.update({
            "ce_delta": ce_greeks["delta"],
            "ce_gamma": ce_greeks["gamma"],
            "ce_theta": ce_greeks["theta"],
            "ce_vega": ce_greeks["vega"],
            "ce_gex": ce_gex,
            "pe_delta": pe_greeks["delta"],
            "pe_gamma": pe_greeks["gamma"],
            "pe_theta": pe_greeks["theta"],
            "pe_vega": pe_greeks["vega"],
            "pe_gex": pe_gex,
            "net_gex": net_gex,
            "net_oi_delta": pe_change_oi - ce_change_oi,
        })
        enriched_records.append(enriched)

    if gamma_flip_strike is None:
        gamma_flip_strike = spot_price

    gamma_regime = "POSITIVE_GAMMA" if total_net_gex >= 0 else "NEGATIVE_GAMMA"
    gamma_regime_label = (
        "Positive Gamma (Mean Reverting / Dampened Vol)"
        if total_net_gex >= 0
        else "Negative Gamma (Accelerating Momentum / Breakout Risk)"
    )

    profile = {
        "net_gex": round(total_net_gex, 2),
        "gamma_regime": gamma_regime,
        "gamma_regime_label": gamma_regime_label,
        "gamma_flip_strike": round(gamma_flip_strike, 1),
        "peak_call_gex_strike": round(max_call_gex_strike, 1),
        "peak_put_gex_strike": round(min_put_gex_strike, 1),
        "atm_straddle_price": round(atm_straddle, 2),
        "expected_move_upper": round(spot_price + atm_straddle, 2),
        "expected_move_lower": round(spot_price - atm_straddle, 2),
        "expected_move_2sigma_upper": round(spot_price + 1.85 * atm_straddle, 2),
        "expected_move_2sigma_lower": round(spot_price - 1.85 * atm_straddle, 2),
    }

    return profile, enriched_records


def derive_market_setups(
    symbol: str,
    spot_price: float,
    records: list[dict[str, Any]],
    gamma_profile: dict[str, Any],
    vix_data: dict[str, Any] | None = None,
    max_pain: float | None = None,
    call_wall: float | None = None,
    put_wall: float | None = None,
) -> list[dict[str, Any]]:
    """Generate quantitative options trading setups for major indices.

    Detects:
    1. Gamma Squeeze Breakout (Spot breaking Call Wall in Negative Gamma regime)
    2. Dealer Max Pain Pin (Subdued VIX, Positive Gamma mean reversion to Max Pain)
    3. Put Writer Capitulation (Spot breaking Put Wall with PE covering and surging VIX)
    4. Expected Move 1-Sigma Rejection (Mean reversion fade/bounce off Expected Move bands in Positive Gamma)
    """
    clean_sym = symbol.upper().replace(".NS", "").strip()
    is_major_index = clean_sym in ("NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTY50")
    if not is_major_index or not records or spot_price <= 0:
        return []

    setups: list[dict[str, Any]] = []
    vix_val = float(vix_data.get("vix_value", 13.5)) if vix_data else 13.5
    vix_chg = float(vix_data.get("vix_change_pct", 0.0)) if vix_data else 0.0
    gamma_regime = gamma_profile.get("gamma_regime", "POSITIVE_GAMMA")
    em_upper = float(gamma_profile.get("expected_move_upper", spot_price * 1.01))
    em_lower = float(gamma_profile.get("expected_move_lower", spot_price * 0.99))
    straddle_val = float(gamma_profile.get("atm_straddle_price", spot_price * 0.008))

    # Identify Call Wall and Put Wall if not provided
    if not call_wall:
        c_max = max(records, key=lambda r: int(r.get("ce_oi") or 0))
        call_wall = float(c_max.get("strike", spot_price * 1.02))
    if not put_wall:
        p_max = max(records, key=lambda r: int(r.get("pe_oi") or 0))
        put_wall = float(p_max.get("strike", spot_price * 0.98))
    if not max_pain:
        max_pain = spot_price

    # Find record for call wall and put wall to check delta OI
    call_wall_rec = next((r for r in records if float(r.get("strike", 0.0)) == call_wall), None)
    put_wall_rec = next((r for r in records if float(r.get("strike", 0.0)) == put_wall), None)

    ce_wall_unwinding = bool(call_wall_rec and int(call_wall_rec.get("ce_change_oi") or 0) < 0)
    pe_wall_unwinding = bool(put_wall_rec and int(put_wall_rec.get("pe_change_oi") or 0) < 0)

    # 1. Gamma Squeeze Breakout Setup
    if spot_price >= (call_wall * 0.998) and gamma_regime == "NEGATIVE_GAMMA" and (ce_wall_unwinding or vix_val >= 13.0):
        entry_low = round(call_wall * 0.999, 1)
        entry_high = round(call_wall * 1.003, 1)
        sl = round(call_wall * 0.994, 1)
        tp1 = round(em_upper, 1)
        tp2 = round(em_upper + straddle_val * 0.5, 1)
        setups.append({
            "id": f"gamma-squeeze-{int(call_wall)}",
            "title": f"Gamma Squeeze Breakout above {int(call_wall)}",
            "type": "BREAKOUT",
            "bias": "BULLISH",
            "confidence": 88 if ce_wall_unwinding else 78,
            "entry_zone": f"{entry_low} - {entry_high}",
            "stop_loss": sl,
            "target_1": tp1,
            "target_2": tp2,
            "risk_reward": "1 : 3.2",
            "catalyst": f"Spot testing Call Wall ({int(call_wall)}) in Negative Gamma regime with CE covering and elevated volatility.",
        })

    # 2. Dealer Max Pain Pin Setup
    dist_to_max_pain = abs(spot_price - max_pain) / spot_price
    if gamma_regime == "POSITIVE_GAMMA" and dist_to_max_pain <= 0.008 and vix_val <= 14.5:
        entry_zone = f"{round(spot_price - 20, 1)} - {round(spot_price + 20, 1)}"
        sl = round(max_pain - straddle_val * 0.6 if spot_price >= max_pain else max_pain + straddle_val * 0.6, 1)
        tp1 = round(max_pain, 1)
        tp2 = round(max_pain + (15 if spot_price < max_pain else -15), 1)
        setups.append({
            "id": f"dealer-pin-{int(max_pain)}",
            "title": f"Positive Gamma Expiry Pin at {int(max_pain)}",
            "type": "MEAN_REVERSION",
            "bias": "NEUTRAL",
            "confidence": 85 if dist_to_max_pain <= 0.004 else 75,
            "entry_zone": entry_zone,
            "stop_loss": sl,
            "target_1": tp1,
            "target_2": tp2,
            "risk_reward": "1 : 2.5",
            "catalyst": f"Dealer positive gamma inventory dampens volatility near Max Pain ({int(max_pain)}) under subdued VIX ({vix_val:.1f}).",
        })

    # 3. Put Writer Capitulation Breakdown
    if spot_price <= (put_wall * 1.002) and pe_wall_unwinding and vix_chg >= 2.0:
        entry_low = round(put_wall * 0.997, 1)
        entry_high = round(put_wall * 1.001, 1)
        sl = round(put_wall * 1.005, 1)
        tp1 = round(em_lower, 1)
        tp2 = round(em_lower - straddle_val * 0.5, 1)
        setups.append({
            "id": f"put-capitulation-{int(put_wall)}",
            "title": f"Put Writer Capitulation below {int(put_wall)}",
            "type": "BREAKDOWN",
            "bias": "BEARISH",
            "confidence": 84,
            "entry_zone": f"{entry_low} - {entry_high}",
            "stop_loss": sl,
            "target_1": tp1,
            "target_2": tp2,
            "risk_reward": "1 : 3.0",
            "catalyst": f"Put writers unwinding positions at Put Wall ({int(put_wall)}) with surging volatility.",
        })

    # 4. Expected Move 1-Sigma Rejection
    dist_to_em_upper = abs(spot_price - em_upper) / spot_price
    dist_to_em_lower = abs(spot_price - em_lower) / spot_price
    if gamma_regime == "POSITIVE_GAMMA":
        if dist_to_em_upper <= 0.003:
            setups.append({
                "id": f"straddle-upper-fade-{int(em_upper)}",
                "title": f"Expected Move +1σ Barrier Rejection ({int(em_upper)})",
                "type": "MEAN_REVERSION",
                "bias": "BEARISH",
                "confidence": 76,
                "entry_zone": f"{round(em_upper - 15, 1)} - {round(em_upper + 10, 1)}",
                "stop_loss": round(em_upper + straddle_val * 0.35, 1),
                "target_1": round(spot_price - straddle_val * 0.5, 1),
                "target_2": round(max_pain, 1),
                "risk_reward": "1 : 2.8",
                "catalyst": f"Spot reached +1σ Straddle upper band ({int(em_upper)}) in positive gamma regime — high probability mean reversion fade.",
            })
        elif dist_to_em_lower <= 0.003:
            setups.append({
                "id": f"straddle-lower-bounce-{int(em_lower)}",
                "title": f"Expected Move -1σ Barrier Bounce ({int(em_lower)})",
                "type": "MEAN_REVERSION",
                "bias": "BULLISH",
                "confidence": 76,
                "entry_zone": f"{round(em_lower - 10, 1)} - {round(em_lower + 15, 1)}",
                "stop_loss": round(em_lower - straddle_val * 0.35, 1),
                "target_1": round(spot_price + straddle_val * 0.5, 1),
                "target_2": round(max_pain, 1),
                "risk_reward": "1 : 2.8",
                "catalyst": f"Spot tested -1σ Straddle lower band ({int(em_lower)}) in positive gamma regime — high probability mean reversion bounce.",
            })

    return setups


def save_tracked_option_setups(
    conn: Any,
    setups: list[dict[str, Any]],
    symbol: str,
    spot_price: float,
    gamma_profile: dict[str, Any] | None = None,
    vix_profile: dict[str, Any] | None = None,
) -> int:
    """Save newly identified algorithmic options setups to tracked history ledger with duplicate guard."""
    if not setups or not conn:
        return 0

    now_iso = datetime.now(timezone.utc).isoformat()
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    gamma_regime = (gamma_profile or {}).get("gamma_regime", "NEUTRAL")
    vix_val = (vix_profile or {}).get("vix_value", None)

    saved_count = 0
    clean_sym = symbol.replace(".NS", "").upper()

    for s in setups:
        setup_id = s.get("id")
        if not setup_id:
            continue

        try:
            conn.execute(
                """
                INSERT OR IGNORE INTO options_tracked_setups (
                    symbol, setup_id, setup_title, setup_type, bias,
                    confidence, signal_date, spot_at_signal, entry_zone,
                    stop_loss, target_1, target_2, risk_reward, catalyst,
                    gamma_regime, vix_value, current_spot, realized_pnl_pct,
                    outcome, outcome_label, outcome_badge, scanned_at,
                    created_at, updated_at
                ) VALUES (
                    ?, ?, ?, ?, ?,
                    ?, ?, ?, ?,
                    ?, ?, ?, ?, ?,
                    ?, ?, ?, ?,
                    ?, ?, ?, ?,
                    ?, ?
                )
                """,
                (
                    clean_sym,
                    setup_id,
                    s.get("title", ""),
                    s.get("type", "SETUP"),
                    s.get("bias", "NEUTRAL"),
                    float(s.get("confidence", 0.0)),
                    today_str,
                    float(spot_price),
                    str(s.get("entry_zone", "")),
                    float(s.get("stop_loss", 0.0)),
                    float(s.get("target_1", 0.0)),
                    float(s.get("target_2")) if s.get("target_2") is not None else None,
                    s.get("risk_reward", ""),
                    s.get("catalyst", ""),
                    gamma_regime,
                    float(vix_val) if vix_val is not None else None,
                    float(spot_price),
                    0.0,
                    "ACTIVE",
                    "Active Trade In-Flight",
                    "indigo",
                    now_iso,
                    now_iso,
                    now_iso,
                ),
            )
            saved_count += 1
        except Exception as e:
            logger.warning(f"[save_tracked_option_setups] Error inserting setup {setup_id}: {e}")

    try:
        conn.commit()
    except Exception:
        pass

    return saved_count


def get_tracked_option_setups(
    conn: Any,
    symbol: str | None = None,
    outcome: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Retrieve historical tracked option setups with optional filtering."""
    if not conn:
        return []

    query = "SELECT * FROM options_tracked_setups WHERE 1=1"
    params: list[Any] = []

    if symbol:
        query += " AND symbol = ?"
        params.append(symbol.replace(".NS", "").upper())
    if outcome:
        query += " AND outcome = ?"
        params.append(outcome.upper())

    query += " ORDER BY signal_date DESC, id DESC LIMIT ?"
    params.append(limit)

    try:
        cursor = conn.execute(query, params)
        rows = cursor.fetchall()
        cols = [c[0] for c in cursor.description] if cursor.description else []
        results = []
        for r in rows:
            if hasattr(r, "keys"):
                results.append({k: r[k] for k in r.keys()})
            elif cols and isinstance(r, (tuple, list)):
                results.append(dict(zip(cols, r)))
            else:
                results.append(dict(r))
        return results
    except Exception as e:
        logger.warning(f"[get_tracked_option_setups] Failed to query tracked setups: {e}")
        return []


def evaluate_tracked_option_setups(
    conn: Any,
    symbol: str,
    current_spot: float,
) -> list[dict[str, Any]]:
    """Evaluate active tracked setups against current spot price and update outcome state machine."""
    if not conn or not current_spot or current_spot <= 0:
        return []

    clean_sym = symbol.replace(".NS", "").upper()
    now_iso = datetime.now(timezone.utc).isoformat()

    try:
        cursor = conn.execute(
            "SELECT * FROM options_tracked_setups WHERE symbol = ? AND outcome = 'ACTIVE'",
            (clean_sym,),
        )
        rows = cursor.fetchall()
        cols = [c[0] for c in cursor.description] if cursor.description else []
        active_setups = []
        for r in rows:
            if hasattr(r, "keys"):
                active_setups.append({k: r[k] for k in r.keys()})
            elif cols and isinstance(r, (tuple, list)):
                active_setups.append(dict(zip(cols, r)))
            else:
                active_setups.append(dict(r))
    except Exception as e:
        logger.warning(f"[evaluate_tracked_option_setups] Error fetching active setups: {e}")
        return []

    updated = []
    for row_dict in active_setups:
        setup_id = row_dict["setup_id"]
        bias = row_dict.get("bias", "BULLISH").upper()
        spot_at_sig = float(row_dict.get("spot_at_signal") or current_spot)
        target_1 = float(row_dict.get("target_1") or 0.0)
        target_2 = float(row_dict.get("target_2") or 0.0) if row_dict.get("target_2") else None
        stop_loss = float(row_dict.get("stop_loss") or 0.0)

        # Calculate Spot PnL % based on trade direction bias
        if bias == "BULLISH":
            pnl_pct = round(((current_spot - spot_at_sig) / spot_at_sig) * 100, 2)
            if target_2 and current_spot >= target_2:
                new_outcome = "TARGET2_HIT"
                label = f"Target 2 Hit (+{pnl_pct}%)"
                badge = "emerald"
            elif target_1 and current_spot >= target_1:
                new_outcome = "TARGET1_HIT"
                label = f"Target 1 Hit (+{pnl_pct}%)"
                badge = "emerald"
            elif stop_loss and current_spot <= stop_loss:
                new_outcome = "STOPPED_OUT"
                label = f"Stopped Out ({pnl_pct}%)"
                badge = "rose"
            else:
                new_outcome = "ACTIVE"
                label = f"In Flight ({pnl_pct:+}%)"
                badge = "indigo"
        elif bias == "BEARISH":
            pnl_pct = round(((spot_at_sig - current_spot) / spot_at_sig) * 100, 2)
            if target_2 and current_spot <= target_2:
                new_outcome = "TARGET2_HIT"
                label = f"Target 2 Hit (+{pnl_pct}%)"
                badge = "emerald"
            elif target_1 and current_spot <= target_1:
                new_outcome = "TARGET1_HIT"
                label = f"Target 1 Hit (+{pnl_pct}%)"
                badge = "emerald"
            elif stop_loss and current_spot >= stop_loss:
                new_outcome = "STOPPED_OUT"
                label = f"Stopped Out ({pnl_pct}%)"
                badge = "rose"
            else:
                new_outcome = "ACTIVE"
                label = f"In Flight ({pnl_pct:+}%)"
                badge = "indigo"
        else:
            pnl_pct = 0.0
            new_outcome = "ACTIVE"
            label = "Active Neutral Pin"
            badge = "indigo"

        try:
            conn.execute(
                """
                UPDATE options_tracked_setups
                SET current_spot = ?, realized_pnl_pct = ?, outcome = ?,
                    outcome_label = ?, outcome_badge = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    float(current_spot),
                    float(pnl_pct),
                    new_outcome,
                    label,
                    badge,
                    now_iso,
                    row_dict["id"],
                ),
            )
            row_dict["outcome"] = new_outcome
            row_dict["current_spot"] = current_spot
            row_dict["realized_pnl_pct"] = pnl_pct
            row_dict["outcome_label"] = label
            row_dict["outcome_badge"] = badge
            updated.append(row_dict)
        except Exception as e:
            logger.warning(f"[evaluate_tracked_option_setups] Failed to update setup {setup_id}: {e}")

    try:
        conn.commit()
    except Exception:
        pass

    return updated




