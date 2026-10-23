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
from earnings_engine.data.options_alerts_engine import generate_derivatives_alerts
from earnings_engine.data.options_chart_engine import get_intraday_structure_summary
from earnings_engine.data.options_market_compass import calculate_market_compass
from earnings_engine.data.options_writing_velocity import derive_multi_timeframe_oi
from earnings_engine.data.providers.provider_manager import get_data_manager
from earnings_engine.data.universe import is_fno_eligible, resolve_fno_symbol

logger = logging.getLogger("earnings_engine.data.option_chain")

_NON_FNO_SYMBOLS: set[str] = set()
_OPTION_CHAIN_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_CACHE_TTL_SECONDS = 15.0  # 15 seconds continuous rolling cache

# Rolling Open Interest & Writing Velocity Cache: symbol -> list of (timestamp_epoch, call_oi, put_oi, dict_strike_oi)
_OI_SNAPSHOT_CACHE: dict[str, list[dict[str, Any]]] = {}
_MAX_OI_SNAPSHOTS = 120  # Keep up to ~2 hours of 1-minute resolution or full day snapshots


def _resolve_vix_profile(settings: Settings | None = None) -> dict[str, Any]:
    """Retrieve live India VIX quote with 1D delta % and volatility regime classification."""
    settings = settings or Settings()
    vix_val = 14.5
    vix_change_pct = 0.0

    try:
        from earnings_engine.data.prices import fetch_batch_live_quotes, load_prices
        live_quotes = fetch_batch_live_quotes(["^INDIAVIX"], settings=settings, sync_db=False)
        vix_entry = live_quotes.get("^INDIAVIX")
        if vix_entry and vix_entry.get("current_price") and float(vix_entry["current_price"]) > 0:
            vix_val = float(vix_entry["current_price"])
            vix_change_pct = float(vix_entry.get("change_pct", 0.0) or 0.0)
        else:
            hist = load_prices("^INDIAVIX", settings)
            if hist is not None and not hist.empty and "close" in hist.columns:
                closes = hist["close"].dropna().values
                if len(closes) > 0 and float(closes[-1]) > 0:
                    vix_val = float(closes[-1])
                    if len(closes) >= 2 and float(closes[-2]) > 0:
                        vix_change_pct = float(((vix_val - closes[-2]) / closes[-2]) * 100.0)
    except Exception as e:
        logger.debug("[OPTION-CHAIN] Could not retrieve live VIX: %s", e)

    if vix_val < 13.0:
        vix_regime = "LOW_VOL"
    elif vix_val <= 17.0:
        vix_regime = "NORMAL_VOL"
    elif vix_val <= 22.0:
        vix_regime = "ELEVATED_VOL"
    else:
        vix_regime = "HIGH_VOL"

    return {
        "vix_value": round(vix_val, 2),
        "vix_change_pct": round(vix_change_pct, 2),
        "vix_regime": vix_regime,
    }



def _build_unavailable_subtab_summary(message: str = "No equity derivatives listed for this symbol.") -> dict[str, Any]:
    return {
        "gamma_regime": "NEUTRAL",
        "market_texture": "Non-FNO Cash Equity",
        "texture_badge": "N/A",
        "texture_theme": "zinc",
        "narrative": message,
        "expected_range": {"support": None, "resistance": None, "spread_points": 0, "spread_pct": 0, "range_display": "--"},
        "action_type": "UNAVAILABLE",
        "action_badge": "NO DERIVATIVES",
        "action_theme": "zinc",
        "action_headline": "No F&O Options Data Available",
        "action_details": "Cash market equity without exchange-traded options chain.",
        "buy_level": None,
        "sell_level": None,
        "gamma_flip_strike": None,
        "max_pain_strike": None,
        "pivot_1_label": "Pivot 1",
        "pivot_1_val": "--",
        "pivot_2_label": "Pivot 2",
        "pivot_2_val": "--",
        "support_label": "SUPPORT",
        "resistance_label": "RESISTANCE",
    }


def _resolve_spot_price(clean_symbol: str, spot_price: float | None, settings: Settings | None = None) -> float:
    """Resolve spot price from local price_history database first before hitting network quote."""
    if spot_price is not None and spot_price > 0:
        return float(spot_price)

    # 1. Try local price_history cache
    try:
        from earnings_engine.data.prices import load_prices
        settings = settings or Settings()
        lookup_sym = "^BSESN" if clean_symbol in ("SENSEX", "BSESENSEX", "^BSESN") else clean_symbol
        pdf = load_prices(lookup_sym, settings)
        if (pdf is None or pdf.empty) and not clean_symbol.endswith(".NS") and lookup_sym == clean_symbol:
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
        lookup_sym = "^BSESN" if clean_symbol in ("SENSEX", "BSESENSEX", "^BSESN") else clean_symbol
        q = mgr.fetch_quote(lookup_sym)
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
            "message": f"{clean_symbol} is not eligible for NSE/BSE Equity Derivatives (F&O). Cash market only.",
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
            "gex_summary": _build_unavailable_subtab_summary("No equity derivatives listed for this symbol."),
            "oi_summary": _build_unavailable_subtab_summary("No equity derivatives listed for this symbol."),
            "net_delta_summary": _build_unavailable_subtab_summary("No equity derivatives listed for this symbol."),
            "iv_summary": _build_unavailable_subtab_summary("No equity derivatives listed for this symbol."),
            "subtab_summaries": {
                "gex": _build_unavailable_subtab_summary("No equity derivatives listed for this symbol."),
                "oi": _build_unavailable_subtab_summary("No equity derivatives listed for this symbol."),
                "net_delta": _build_unavailable_subtab_summary("No equity derivatives listed for this symbol."),
                "iv": _build_unavailable_subtab_summary("No equity derivatives listed for this symbol."),
            },
        }
        _OPTION_CHAIN_CACHE[cache_key] = (now, res)
        return res

    spot_price = _resolve_spot_price(clean_symbol, spot_price, settings)
    vix_data = _resolve_vix_profile(settings)

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
                "vix": vix_data.get("vix_value"),
                "vix_profile": vix_data,
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
            "vix": vix_data.get("vix_value"),
            "vix_profile": vix_data,
            "gex_summary": _build_unavailable_subtab_summary("Live NSE option chain unreachable and no archival snapshot found for this symbol."),
            "oi_summary": _build_unavailable_subtab_summary("Live NSE option chain unreachable and no archival snapshot found for this symbol."),
            "net_delta_summary": _build_unavailable_subtab_summary("Live NSE option chain unreachable and no archival snapshot found for this symbol."),
            "iv_summary": _build_unavailable_subtab_summary("Live NSE option chain unreachable and no archival snapshot found for this symbol."),
            "subtab_summaries": {
                "gex": _build_unavailable_subtab_summary("Live NSE option chain unreachable and no archival snapshot found for this symbol."),
                "oi": _build_unavailable_subtab_summary("Live NSE option chain unreachable and no archival snapshot found for this symbol."),
                "net_delta": _build_unavailable_subtab_summary("Live NSE option chain unreachable and no archival snapshot found for this symbol."),
                "iv": _build_unavailable_subtab_summary("Live NSE option chain unreachable and no archival snapshot found for this symbol."),
            },
        }
        _OPTION_CHAIN_CACHE[cache_key] = (now, res)
        return res

    res = _calculate_option_metrics_from_records(
        symbol=clean_symbol,
        records=records,
        spot_price=spot_price,
        strike_range=strike_range,
        vix_data=vix_data,
    )
    res["spot_price"] = spot_price
    res["expiries"] = expiries
    res["selected_expiry"] = selected_expiry
    res["timestamp"] = raw_chain.get("timestamp") or datetime.now().isoformat()
    res["vix"] = vix_data.get("vix_value")
    res["vix_profile"] = vix_data
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
                "cum_net_gex": enr.get("cum_net_gex", 0.0),
                "net_oi_delta": enr.get("net_oi_delta", 0),
            })

    vix_profile = vix_data or _resolve_vix_profile()

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

    expected_move_dict = {
        "straddle_price": gamma_profile_data.get("atm_straddle_price"),
        "range_1sigma": gamma_profile_data.get("atm_straddle_price"),
        "upper_1sigma": gamma_profile_data.get("expected_move_upper"),
        "lower_1sigma": gamma_profile_data.get("expected_move_lower"),
        "upper_2sigma": gamma_profile_data.get("expected_move_2sigma_upper"),
        "lower_2sigma": gamma_profile_data.get("expected_move_2sigma_lower"),
    }

    gex_summary = derive_gex_action_summary(
        spot_price=current_spot,
        gamma_profile=gamma_profile_data,
        call_wall=high_call_strike,
        put_wall=high_put_strike,
        max_pain=max_pain,
        expected_move=expected_move_dict,
        pcr_oi=pcr_oi,
        sentiment=sentiment,
    )

    oi_summary = derive_oi_action_summary(
        spot_price=current_spot,
        call_wall=high_call_strike,
        put_wall=high_put_strike,
        max_pain=max_pain,
        pcr_oi=pcr_oi,
        pcr_volume=pcr_vol,
        sentiment=sentiment,
        call_oi_total=int(call_oi),
        put_oi_total=int(put_oi),
    )

    net_delta_summary = derive_net_delta_action_summary(
        spot_price=current_spot,
        records=formatted_strikes,
        call_wall=high_call_strike,
        put_wall=high_put_strike,
    )

    iv_summary = derive_iv_action_summary(
        spot_price=current_spot,
        records=formatted_strikes,
        vix_data=vix_profile,
        expected_move=expected_move_dict,
    )

    subtab_summaries = {
        "gex": gex_summary,
        "oi": oi_summary,
        "net_delta": net_delta_summary,
        "iv": iv_summary,
    }

    # Derive Multi-Timeframe Call vs Put Writing Velocity & Sentiment
    oi_timeframes = derive_multi_timeframe_oi(
        symbol=symbol,
        current_call_oi=int(call_oi),
        current_put_oi=int(put_oi),
        strikes=formatted_strikes,
    )

    # Extract Intraday SMC & VWAP Technical Structure
    chart_intel = get_intraday_structure_summary(symbol=symbol, interval="5m")

    # 8-Factor Confluence Market Compass Model
    market_compass = calculate_market_compass(
        symbol=symbol,
        spot_price=current_spot,
        pcr_oi=pcr_oi,
        pcr_volume=pcr_vol,
        call_wall=high_call_strike,
        put_wall=high_put_strike,
        max_pain=max_pain,
        gamma_profile=gamma_profile_data,
        oi_timeframes=oi_timeframes,
        chart_intel=chart_intel,
        vix_data=vix_profile,
    )

    # Real-time Institutional Flow and Flow Accumulation Alerts
    institutional_alerts = generate_derivatives_alerts(
        symbol=symbol,
        spot_price=current_spot,
        call_wall=high_call_strike,
        put_wall=high_put_strike,
        max_pain=max_pain,
        pcr_oi=pcr_oi,
        oi_timeframes=oi_timeframes,
        gamma_profile=gamma_profile_data,
        strikes=formatted_strikes,
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
        "total_net_gex": gamma_profile_data.get("net_gex", 0.0),
        "gamma_flip_strike": gamma_profile_data.get("gamma_flip_strike"),
        "gamma_regime": gamma_profile_data.get("gamma_regime"),
        "gamma_regime_label": gamma_profile_data.get("gamma_regime_label"),
        "expected_move": expected_move_dict,
        "gex_summary": gex_summary,
        "oi_summary": oi_summary,
        "net_delta_summary": net_delta_summary,
        "iv_summary": iv_summary,
        "subtab_summaries": subtab_summaries,
        "oi_timeframes": oi_timeframes,
        "market_compass": market_compass,
        "institutional_alerts": institutional_alerts,
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
            "cum_net_gex": round(cumulative_gex, 2),
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


def derive_gex_action_summary(
    spot_price: float,
    gamma_profile: dict[str, Any] | None,
    call_wall: float | None,
    put_wall: float | None,
    max_pain: float | None,
    expected_move: dict[str, Any] | None = None,
    pcr_oi: float | None = None,
    sentiment: str | None = None,
) -> dict[str, Any]:
    """Derive institutional GEX header intelligence: market texture, expected range, and tactical action directives."""
    gp = gamma_profile or {}
    em = expected_move or {}
    gamma_regime = gp.get("gamma_regime", "NEUTRAL")
    net_gex = float(gp.get("net_gex") or 0.0)
    flip_strike = gp.get("gamma_flip_strike")
    if flip_strike is not None:
        try:
            flip_strike = float(flip_strike)
        except (ValueError, TypeError):
            flip_strike = None

    mp_val = float(max_pain) if max_pain else spot_price
    c_wall = float(call_wall) if call_wall else None
    p_wall = float(put_wall) if put_wall else None

    em_lower = float(em["lower_1sigma"]) if em.get("lower_1sigma") is not None else None
    em_upper = float(em["upper_1sigma"]) if em.get("upper_1sigma") is not None else None

    # Resolve range bounds (Put Wall Support to Call Wall Resistance)
    range_support = p_wall if p_wall else (em_lower or round(spot_price * 0.985, 1))
    range_resistance = c_wall if c_wall else (em_upper or round(spot_price * 1.015, 1))
    if range_support > range_resistance:
        range_support, range_resistance = range_resistance, range_support

    spread_pts = round(range_resistance - range_support, 1)
    spread_pct = round((spread_pts / spot_price * 100), 2) if spot_price > 0 else 0.0

    # 1. Market Texture & Dealer Mechanics Narrative
    if gamma_regime == "POSITIVE_GAMMA":
        texture = "Range-Bound & Mean-Reverting (Vol Dampening)"
        texture_badge = "🛡️ POSITIVE GAMMA (Vol Dampening)"
        texture_theme = "emerald"
        narrative = (
            f"Dealers are net long gamma (+₹{net_gex:.1f}L). Dealer delta-hedging dampens intraday volatility "
            f"(selling into rallies, buying dips). Price tends to pin and mean-revert toward Max Pain (₹{mp_val:,.0f}). "
            f"Range extremes offer high mean-reversion probability; breakout chasing has low follow-through."
        )
    elif gamma_regime == "NEGATIVE_GAMMA":
        texture = "Volatile & Directional (Gamma Squeeze / Expansion)"
        texture_badge = "⚡ NEGATIVE GAMMA (Vol Acceleration)"
        texture_theme = "rose"
        narrative = (
            f"Dealers are net short gamma (-₹{abs(net_gex):.1f}L). Dealer hedging accelerates market moves "
            f"(selling as price drops, buying as price rallies). Elevated velocity and breakout probability. "
            f"Avoid counter-trend fading; strike walls can easily blow out."
        )
    else:
        texture = "Balanced / Neutral (Consolidation Zone)"
        texture_badge = "⚖️ NEUTRAL GAMMA"
        texture_theme = "amber"
        narrative = (
            "Dealer gamma exposure is balanced near zero. Order flow and macro catalysts dictate direction "
            f"within key derivatives barriers (Support ₹{range_support:,.0f} / Resistance ₹{range_resistance:,.0f})."
        )

    # 2. Tactical Action Directive: Buy, Sell, or Buy Support X and Sell Resistance Y
    dist_to_support = (spot_price - range_support) / spot_price if spot_price > 0 else 0.0
    dist_to_resistance = (range_resistance - spot_price) / spot_price if spot_price > 0 else 0.0

    if gamma_regime == "POSITIVE_GAMMA":
        # In positive gamma, mean-reversion is queen
        if dist_to_support <= 0.004:
            # Spot right at or below Put Wall Support
            action_type = "TACTICAL_BUY"
            action_badge = "TACTICAL BUY ZONE"
            action_theme = "emerald"
            buy_level = range_support
            sell_level = range_resistance
            action_headline = f"BUY AT SUPPORT ₹{range_support:,.0f} (PUT WALL)"
            action_details = (
                f"Spot (₹{spot_price:,.0f}) is testing high-conviction Put Wall support at ₹{range_support:,.0f}. "
                f"Dealers long gamma will actively defend this zone. Accumulate with invalidation stop below ₹{range_support * 0.995:,.0f}, "
                f"targeting Call Wall resistance at ₹{range_resistance:,.0f}."
            )
        elif dist_to_resistance <= 0.004:
            # Spot right at or above Call Wall Resistance
            action_type = "TACTICAL_SELL"
            action_badge = "TACTICAL SELL / PROFIT ZONE"
            action_theme = "rose"
            buy_level = range_support
            sell_level = range_resistance
            action_headline = f"SELL / TAKE PROFIT AT RESISTANCE ₹{range_resistance:,.0f} (CALL WALL)"
            action_details = (
                f"Spot (₹{spot_price:,.0f}) is testing heavy Call Wall resistance at ₹{range_resistance:,.0f}. "
                f"Dealers long gamma will aggressively sell into strength to hedge. Book profits or initiate fade shorts "
                f"with stop above ₹{range_resistance * 1.005:,.0f}, targeting Put Wall at ₹{range_support:,.0f}."
            )
        else:
            # Spot in middle: Play the range
            action_type = "BUY_SUPPORT_SELL_RESISTANCE"
            action_badge = "RANGE FADE"
            action_theme = "indigo"
            buy_level = range_support
            sell_level = range_resistance
            action_headline = f"BUY ON SUPPORT ₹{range_support:,.0f} & SELL AT RESISTANCE ₹{range_resistance:,.0f}"
            action_details = (
                f"Market is range-bound inside positive gamma boundaries. Do not chase breakouts. "
                f"Buy dips near Put Wall support (₹{range_support:,.0f}) and sell / take profits on rallies near Call Wall resistance (₹{range_resistance:,.0f})."
            )

    elif gamma_regime == "NEGATIVE_GAMMA":
        pivot_level = flip_strike if flip_strike else range_resistance
        if spot_price >= (pivot_level * 0.998):
            # Bullish trend expansion / short squeeze
            action_type = "BUY_BREAKOUT_MOMENTUM"
            action_badge = "MOMENTUM BUY"
            action_theme = "emerald"
            buy_level = spot_price
            sell_level = em_upper or (range_resistance * 1.01)
            action_headline = f"BUY MOMENTUM / BREAKOUT ABOVE ₹{range_resistance:,.0f}"
            action_details = (
                f"Spot (₹{spot_price:,.0f}) is in negative gamma acceleration zone above Gamma Flip (₹{pivot_level:,.0f}). "
                f"Dealers must chase price by buying futures as index climbs. Ride bullish momentum with trailing stop below "
                f"₹{spot_price * 0.994:,.0f}; do NOT short Call Wall at ₹{range_resistance:,.0f}."
            )
        else:
            # Bearish trend acceleration / liquidation
            action_type = "SELL_BREAKDOWN_MOMENTUM"
            action_badge = "SELL RALLIES / SHORT"
            action_theme = "rose"
            buy_level = em_lower or (range_support * 0.99)
            sell_level = range_resistance
            action_headline = f"SELL RALLIES / BREAKDOWN BELOW ₹{range_support:,.0f}"
            action_details = (
                f"Spot (₹{spot_price:,.0f}) is in negative gamma territory below Gamma Flip (₹{pivot_level:,.0f}). "
                f"Dealers are forced sellers into downticks. Sell pullbacks into resistance; Put Wall support at "
                f"₹{range_support:,.0f} is vulnerable to cascading breakdown."
            )

    else:
        # Neutral Gamma
        action_type = "BUY_SUPPORT_SELL_RESISTANCE"
        action_badge = "CONSOLIDATION FADE"
        action_theme = "amber"
        buy_level = range_support
        sell_level = range_resistance
        action_headline = f"BUY ON SUPPORT ₹{range_support:,.0f} & SELL AT RESISTANCE ₹{range_resistance:,.0f}"
        action_details = (
            f"Neutral gamma inventory indicates consolidation. Accumulate on pullbacks toward Put Wall support "
            f"at ₹{range_support:,.0f} (SL: ₹{range_support * 0.994:,.0f}) and take profits at Call Wall resistance at ₹{range_resistance:,.0f}."
        )

    return {
        "gamma_regime": gamma_regime,
        "market_texture": texture,
        "texture_badge": texture_badge,
        "texture_theme": texture_theme,
        "narrative": narrative,
        "expected_range": {
            "support": range_support,
            "resistance": range_resistance,
            "lower_1sigma": em_lower,
            "upper_1sigma": em_upper,
            "spread_points": spread_pts,
            "spread_pct": spread_pct,
            "range_display": f"₹{range_support:,.0f} – ₹{range_resistance:,.0f}",
        },
        "action_type": action_type,
        "action_badge": action_badge,
        "action_theme": action_theme,
        "action_headline": action_headline,
        "action_details": action_details,
        "buy_level": buy_level,
        "sell_level": sell_level,
        "gamma_flip_strike": flip_strike,
        "max_pain_strike": mp_val,
        "pivot_1_label": "±1σ Move",
        "pivot_1_val": f"₹{em_lower:,.0f} – ₹{em_upper:,.0f}" if (em_lower and em_upper) else "--",
        "pivot_2_label": "Gamma Flip",
        "pivot_2_val": f"₹{flip_strike:,.0f}" if flip_strike else "--",
        "support_label": "SUPPORT (PUT WALL)",
        "resistance_label": "RESISTANCE (CALL WALL)",
    }


def derive_oi_action_summary(
    spot_price: float,
    call_wall: float | None,
    put_wall: float | None,
    max_pain: float | None,
    pcr_oi: float | None = None,
    pcr_volume: float | None = None,
    sentiment: str | None = None,
    call_oi_total: int = 0,
    put_oi_total: int = 0,
) -> dict[str, Any]:
    """Derive Open Interest (OI) & ΔOI header intelligence: writer accumulation, structural barriers, and execution directives."""
    mp_val = float(max_pain) if max_pain else spot_price
    c_wall = float(call_wall) if call_wall else round(spot_price * 1.015, 1)
    p_wall = float(put_wall) if put_wall else round(spot_price * 0.985, 1)

    range_support = p_wall
    range_resistance = c_wall
    if range_support > range_resistance:
        range_support, range_resistance = range_resistance, range_support

    spread_pts = round(range_resistance - range_support, 1)
    spread_pct = round((spread_pts / spot_price * 100), 2) if spot_price > 0 else 0.0

    pcr_val = float(pcr_oi) if pcr_oi is not None else 1.0
    sent = sentiment or ("BULLISH" if pcr_val >= 1.2 else ("BEARISH" if pcr_val <= 0.8 else "NEUTRAL"))

    # 1. Market Texture & Writer Mechanics
    if pcr_val >= 1.2 or sent == "BULLISH":
        texture = "Bullish Put Writing Dominance (Support Floor Locked)"
        texture_badge = f"🟢 BULLISH OI (PCR {pcr_val:.2f})"
        texture_theme = "emerald"
        narrative = (
            f"Put writers heavily outweigh call writers with total Put OI of {put_oi_total:,} vs Call OI of {call_oi_total:,} "
            f"(PCR {pcr_val:.2f}). Heavy institutional put writing builds an immovable demand floor at Put Wall (₹{range_support:,.0f}). "
            f"Downside drops into support offer high-conviction accumulation entries."
        )
    elif pcr_val <= 0.8 or sent == "BEARISH":
        texture = "Bearish Call Writing Dominance (Overhead Supply Ceiling)"
        texture_badge = f"🔴 BEARISH OI (PCR {pcr_val:.2f})"
        texture_theme = "rose"
        narrative = (
            f"Call writers dominate the ladder with total Call OI of {call_oi_total:,} vs Put OI of {put_oi_total:,} "
            f"(PCR {pcr_val:.2f}). A massive supply ceiling is locked at Call Wall (₹{range_resistance:,.0f}). "
            f"Rallies into overhead resistance face heavy institutional selling and distribution."
        )
    else:
        texture = "Balanced Open Interest Equilibrium (Two-Way Distribution)"
        texture_badge = f"⚖️ BALANCED OI (PCR {pcr_val:.2f})"
        texture_theme = "amber"
        narrative = (
            f"Option writing inventory is evenly distributed across calls and puts (PCR {pcr_val:.2f}). "
            f"Price is bounded between institutional Put Wall support at ₹{range_support:,.0f} and Call Wall resistance at ₹{range_resistance:,.0f}, "
            f"with Max Pain pinning gravity at ₹{mp_val:,.0f}."
        )

    # 2. Tactical Action Directive
    dist_to_support = (spot_price - range_support) / spot_price if spot_price > 0 else 0.0
    dist_to_resistance = (range_resistance - spot_price) / spot_price if spot_price > 0 else 0.0

    if pcr_val >= 1.2 or sent == "BULLISH":
        if dist_to_support <= 0.005:
            action_type = "TACTICAL_BUY"
            action_badge = "BUY AT SUPPORT"
            action_theme = "emerald"
            buy_level = range_support
            sell_level = range_resistance
            action_headline = f"BUY AT SUPPORT ₹{range_support:,.0f} (PUT WALL ACCUMULATION)"
            action_details = (
                f"Spot (₹{spot_price:,.0f}) is testing high-density Put writing support at ₹{range_support:,.0f}. "
                f"Writers are defending their premiums. Accumulate with invalidation stop below ₹{range_support * 0.995:,.0f}, "
                f"targeting Call Wall resistance at ₹{range_resistance:,.0f}."
            )
        else:
            action_type = "BUY_DIPS"
            action_badge = "BUY THE DIP"
            action_theme = "emerald"
            buy_level = range_support
            sell_level = range_resistance
            action_headline = f"BUY DIPS TOWARD ₹{range_support:,.0f} & TARGET ₹{range_resistance:,.0f}"
            action_details = (
                f"Bullish open interest structure favors buying pullbacks. Accumulate on dips toward Put Wall support "
                f"at ₹{range_support:,.0f} (SL: ₹{range_support * 0.995:,.0f}) and take profits at Call Wall resistance at ₹{range_resistance:,.0f}."
            )
    elif pcr_val <= 0.8 or sent == "BEARISH":
        if dist_to_resistance <= 0.005:
            action_type = "TACTICAL_SELL"
            action_badge = "SELL AT RESISTANCE"
            action_theme = "rose"
            buy_level = range_support
            sell_level = range_resistance
            action_headline = f"SELL / SHORT AT RESISTANCE ₹{range_resistance:,.0f} (CALL WALL CEILING)"
            action_details = (
                f"Spot (₹{spot_price:,.0f}) is testing heavy Call writing supply at ₹{range_resistance:,.0f}. "
                f"Overhead absorption is high. Initiate fade shorts or exit longs with stop above ₹{range_resistance * 1.005:,.0f}, "
                f"targeting Put Wall at ₹{range_support:,.0f}."
            )
        else:
            action_type = "SELL_RALLIES"
            action_badge = "FADE RALLIES"
            action_theme = "rose"
            buy_level = range_support
            sell_level = range_resistance
            action_headline = f"SELL RALLIES TOWARD ₹{range_resistance:,.0f} & TARGET ₹{range_support:,.0f}"
            action_details = (
                f"Bearish call writing overhang caps upside. Sell or hedge into counter-trend bounces approaching "
                f"Call Wall at ₹{range_resistance:,.0f}; downside targets Put Wall support at ₹{range_support:,.0f}."
            )
    else:
        action_type = "BUY_SUPPORT_SELL_RESISTANCE"
        action_badge = "RANGE FADE"
        action_theme = "indigo"
        buy_level = range_support
        sell_level = range_resistance
        action_headline = f"BUY ON SUPPORT ₹{range_support:,.0f} & SELL AT RESISTANCE ₹{range_resistance:,.0f}"
        action_details = (
            f"Balanced OI distribution dictates pure range trading. Buy pullbacks at Put Wall support (₹{range_support:,.0f}) "
            f"and take profits / sell rallies at Call Wall resistance (₹{range_resistance:,.0f})."
        )

    return {
        "gamma_regime": "NEUTRAL",
        "market_texture": texture,
        "texture_badge": texture_badge,
        "texture_theme": texture_theme,
        "narrative": narrative,
        "expected_range": {
            "support": range_support,
            "resistance": range_resistance,
            "spread_points": spread_pts,
            "spread_pct": spread_pct,
            "range_display": f"₹{range_support:,.0f} – ₹{range_resistance:,.0f}",
        },
        "action_type": action_type,
        "action_badge": action_badge,
        "action_theme": action_theme,
        "action_headline": action_headline,
        "action_details": action_details,
        "buy_level": buy_level,
        "sell_level": sell_level,
        "pivot_1_label": "Max Pain Strike",
        "pivot_1_val": f"₹{mp_val:,.0f}",
        "pivot_2_label": "PCR (OI / Vol)",
        "pivot_2_val": f"{pcr_val:.2f} / {pcr_volume:.2f}" if pcr_volume is not None else f"{pcr_val:.2f}",
        "support_label": "SUPPORT (PUT WALL)",
        "resistance_label": "RESISTANCE (CALL WALL)",
    }


def derive_net_delta_action_summary(
    spot_price: float,
    records: list[dict[str, Any]],
    call_wall: float | None = None,
    put_wall: float | None = None,
) -> dict[str, Any]:
    """Derive Net OI Delta header intelligence: strike-by-strike writer velocity, flow builds, and dynamic barriers."""
    c_wall = float(call_wall) if call_wall else round(spot_price * 1.015, 1)
    p_wall = float(put_wall) if put_wall else round(spot_price * 0.985, 1)

    peak_put_build_strike = None
    peak_put_build_val = 0
    peak_call_build_strike = None
    peak_call_build_val = 0
    total_net_delta = 0

    for r in records or []:
        stk = float(r.get("strike") or r.get("strikePrice") or 0.0)
        if stk <= 0:
            continue
        pe_change = int(r.get("pe_change_oi") or 0)
        ce_change = int(r.get("ce_change_oi") or 0)
        delta_net = int(r.get("net_oi_delta") or (pe_change - ce_change))
        total_net_delta += delta_net

        if delta_net > peak_put_build_val:
            peak_put_build_val = delta_net
            peak_put_build_strike = stk
        elif delta_net < peak_call_build_val:
            peak_call_build_val = delta_net
            peak_call_build_strike = stk

    dyn_support = peak_put_build_strike or p_wall
    dyn_resistance = peak_call_build_strike or c_wall
    if dyn_support > dyn_resistance:
        dyn_support, dyn_resistance = dyn_resistance, dyn_support

    spread_pts = round(dyn_resistance - dyn_support, 1)
    spread_pct = round((spread_pts / spot_price * 100), 2) if spot_price > 0 else 0.0

    # 1. Market Texture & Intraday Velocity
    if total_net_delta > 5000:
        texture = "Aggressive Put Writer Accumulation (Dynamic Support Building)"
        texture_badge = f"🟢 NET PUT BUILD (+{total_net_delta:,})"
        texture_theme = "emerald"
        narrative = (
            f"Option writers are heavily writing put options today (Net Delta: +{total_net_delta:,} contracts). "
            f"Strongest intraday accumulation is concentrated at strike ₹{dyn_support:,.0f} (+{peak_put_build_val:,} net PE contracts), "
            f"fortifying dynamic support and reducing breakdown risk."
        )
        action_type = "BUY_ON_ACCUMULATION"
        action_badge = "BUY AT ACCUMULATION"
        action_theme = "emerald"
        action_headline = f"BUY ON SUPPORT ₹{dyn_support:,.0f} (INTRADAY PUT INFLOW)"
        action_details = (
            f"Intraday put writers are actively defending strike ₹{dyn_support:,.0f}. Accumulate on intraday dips "
            f"toward ₹{dyn_support:,.0f} with invalidation stop below ₹{dyn_support * 0.995:,.0f}, targeting ₹{dyn_resistance:,.0f}."
        )
    elif total_net_delta < -5000:
        texture = "Aggressive Call Writer Supply (Dynamic Overhead Cap Building)"
        texture_badge = f"🔴 NET CALL BUILD ({total_net_delta:,})"
        texture_theme = "rose"
        narrative = (
            f"Option writers are aggressively shorting call options today (Net Delta: {total_net_delta:,} contracts). "
            f"Heavy intraday supply is concentrated at strike ₹{dyn_resistance:,.0f} ({peak_call_build_val:,} net CE contracts), "
            f"building an intraday supply ceiling and restricting upside expansion."
        )
        action_type = "SELL_ON_SUPPLY"
        action_badge = "SELL AT SUPPLY"
        action_theme = "rose"
        action_headline = f"SELL AT RESISTANCE ₹{dyn_resistance:,.0f} (INTRADAY CALL OVERHANG)"
        action_details = (
            f"Intraday call writers have stacked heavy contracts at ₹{dyn_resistance:,.0f}. Sell into intraday rallies "
            f"approaching ₹{dyn_resistance:,.0f} with stop above ₹{dyn_resistance * 1.005:,.0f}, targeting pullbacks to ₹{dyn_support:,.0f}."
        )
    else:
        texture = "Balanced Intraday Writer Flow (Two-Way Position Building)"
        texture_badge = f"⚖️ BALANCED DELTA ({total_net_delta:+,})"
        texture_theme = "amber"
        narrative = (
            f"Intraday net writer flow is evenly matched across calls and puts ({total_net_delta:+,} contracts). "
            f"Intraday support is anchored at ₹{dyn_support:,.0f} and supply resistance at ₹{dyn_resistance:,.0f}."
        )
        action_type = "BUY_SUPPORT_SELL_RESISTANCE"
        action_badge = "RANGE FADE"
        action_theme = "indigo"
        action_headline = f"BUY ON SUPPORT ₹{dyn_support:,.0f} & SELL AT RESISTANCE ₹{dyn_resistance:,.0f}"
        action_details = (
            f"Trade the intraday flow boundaries: Buy on support near dynamic put build at ₹{dyn_support:,.0f} "
            f"and take profits / sell rallies approaching dynamic call build at ₹{dyn_resistance:,.0f}."
        )

    return {
        "gamma_regime": "NEUTRAL",
        "market_texture": texture,
        "texture_badge": texture_badge,
        "texture_theme": texture_theme,
        "narrative": narrative,
        "expected_range": {
            "support": dyn_support,
            "resistance": dyn_resistance,
            "spread_points": spread_pts,
            "spread_pct": spread_pct,
            "range_display": f"₹{dyn_support:,.0f} – ₹{dyn_resistance:,.0f}",
        },
        "action_type": action_type,
        "action_badge": action_badge,
        "action_theme": action_theme,
        "action_headline": action_headline,
        "action_details": action_details,
        "buy_level": dyn_support,
        "sell_level": dyn_resistance,
        "pivot_1_label": "Peak Put Build",
        "pivot_1_val": f"₹{dyn_support:,.0f}" if dyn_support else "--",
        "pivot_2_label": "Peak Call Build",
        "pivot_2_val": f"₹{dyn_resistance:,.0f}" if dyn_resistance else "--",
        "support_label": "INTRADAY SUPPORT BUILD",
        "resistance_label": "INTRADAY RESISTANCE BUILD",
    }


def derive_iv_action_summary(
    spot_price: float,
    records: list[dict[str, Any]],
    vix_data: dict[str, Any] | None = None,
    expected_move: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Derive Implied Volatility (IV) Skew & Statistical Range intelligence: fear/greed asymmetry and ±1σ channels."""
    em = expected_move or {}
    lower_1s = float(em["lower_1sigma"]) if em.get("lower_1sigma") is not None else round(spot_price * 0.985, 1)
    upper_1s = float(em["upper_1sigma"]) if em.get("upper_1sigma") is not None else round(spot_price * 1.015, 1)

    spread_pts = round(upper_1s - lower_1s, 1)
    spread_pct = round((spread_pts / spot_price * 100), 2) if spot_price > 0 else 0.0

    # Extract ATM IV and Skew (OTM Put IV vs OTM Call IV)
    atm_iv = 14.0
    otm_put_ivs = []
    otm_call_ivs = []
    min_dist = float("inf")

    for r in records or []:
        stk = float(r.get("strike") or r.get("strikePrice") or 0.0)
        if stk <= 0:
            continue
        c_iv = float(r.get("ce_iv") or 0.0)
        p_iv = float(r.get("pe_iv") or 0.0)

        dist = abs(stk - spot_price)
        if dist < min_dist and (c_iv > 0 or p_iv > 0):
            min_dist = dist
            atm_iv = round((c_iv + p_iv) / 2.0 if (c_iv > 0 and p_iv > 0) else (c_iv or p_iv), 1)

        # Collect OTM strikes within 1-3% range
        pct_diff = (stk - spot_price) / spot_price if spot_price > 0 else 0.0
        if -0.03 <= pct_diff <= -0.008 and p_iv > 0:
            otm_put_ivs.append(p_iv)
        elif 0.008 <= pct_diff <= 0.03 and c_iv > 0:
            otm_call_ivs.append(c_iv)

    avg_put_iv = sum(otm_put_ivs) / len(otm_put_ivs) if otm_put_ivs else atm_iv
    avg_call_iv = sum(otm_call_ivs) / len(otm_call_ivs) if otm_call_ivs else atm_iv
    iv_skew = round(avg_put_iv - avg_call_iv, 2)

    vix_val = float(vix_data.get("vix_value") or 13.5) if vix_data else 13.5

    # 1. Market Texture & Volatility Smile
    if iv_skew >= 1.5:
        texture = "Elevated Put Skew (Downside Crash Fear Priced In)"
        texture_badge = f"⚠️ PUT SKEW ELEVATED (+{iv_skew:.1f}%)"
        texture_theme = "amber"
        narrative = (
            f"OTM Put IV exceeds Call IV by +{iv_skew:.1f}% (ATM IV: {atm_iv:.1f}%, India VIX: {vix_val:.1f}). "
            f"Institutional participants are paying a heavy premium for downside tail-risk crash protection. "
            f"High put premium inflates credit spreads; favor bull put credit spreads on dips over naked call buying."
        )
    elif iv_skew <= -1.0:
        texture = "Call Skew Expansion (Upside Greed / FOMO Squeeze Priced In)"
        texture_badge = f"🚀 CALL SKEW EXPANSION ({iv_skew:.1f}%)"
        texture_theme = "emerald"
        narrative = (
            f"OTM Call IV is trading at an unusual premium over Puts ({iv_skew:.1f}% skew, ATM IV: {atm_iv:.1f}%). "
            f"Market participants are aggressively bidding up upside calls for momentum breakouts and short-covering squeezes."
        )
    else:
        texture = "Balanced Volatility Smile (Normal Dispersion Expectations)"
        texture_badge = f"📈 BALANCED IV SKEW ({iv_skew:+.1f}%)"
        texture_theme = "indigo"
        narrative = (
            f"Implied volatility smile is symmetrical across calls and puts (ATM IV: {atm_iv:.1f}%, India VIX: {vix_val:.1f}). "
            f"Market is pricing orderly statistical dispersion within the ±1σ statistical expected move channel."
        )

    # 2. Tactical Action Directive based on Statistical Range
    if atm_iv >= 18.0 or vix_val >= 16.5:
        action_type = "SELL_HIGH_IV_CREDIT_SPREADS"
        action_badge = "SELL HIGH VOLATILITY"
        action_theme = "emerald"
        action_headline = f"BUY ON SUPPORT ₹{lower_1s:,.0f} & SELL AT RESISTANCE ₹{upper_1s:,.0f} (HARVEST HIGH IV)"
        action_details = (
            f"Elevated IV (ATM {atm_iv:.1f}%) inflates option premiums. Price has a 68.2% statistical probability of remaining "
            f"inside ±1σ bounds (₹{lower_1s:,.0f} – ₹{upper_1s:,.0f}). Sell out-of-the-money credit spreads to harvest rapid theta decay."
        )
    else:
        action_type = "BUY_SUPPORT_SELL_RESISTANCE"
        action_badge = "STATISTICAL ±1σ CHANNEL"
        action_theme = "indigo"
        action_headline = f"BUY ON SUPPORT ₹{lower_1s:,.0f} & SELL AT RESISTANCE ₹{upper_1s:,.0f}"
        action_details = (
            f"Statistical 1-sigma bounds define the standard institutional trading band (₹{lower_1s:,.0f} to ₹{upper_1s:,.0f}). "
            f"Buy pullbacks into 1σ statistical support (₹{lower_1s:,.0f}) and take profits approaching 1σ resistance (₹{upper_1s:,.0f})."
        )

    return {
        "gamma_regime": "NEUTRAL",
        "market_texture": texture,
        "texture_badge": texture_badge,
        "texture_theme": texture_theme,
        "narrative": narrative,
        "expected_range": {
            "support": lower_1s,
            "resistance": upper_1s,
            "lower_1sigma": lower_1s,
            "upper_1sigma": upper_1s,
            "spread_points": spread_pts,
            "spread_pct": spread_pct,
            "range_display": f"₹{lower_1s:,.0f} – ₹{upper_1s:,.0f}",
        },
        "action_type": action_type,
        "action_badge": action_badge,
        "action_theme": action_theme,
        "action_headline": action_headline,
        "action_details": action_details,
        "buy_level": lower_1s,
        "sell_level": upper_1s,
        "pivot_1_label": "ATM IV",
        "pivot_1_val": f"{atm_iv:.1f}%",
        "pivot_2_label": "IV Skew (PE-CE)",
        "pivot_2_val": f"{iv_skew:+.1f}%",
        "support_label": "STATISTICAL SUPPORT (-1σ)",
        "resistance_label": "STATISTICAL RESISTANCE (+1σ)",
    }


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




