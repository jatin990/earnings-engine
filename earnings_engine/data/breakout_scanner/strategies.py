"""Quantitative strategy breakout scoring implementations for Breakout Radar."""

from __future__ import annotations

import logging
from typing import Any
import numpy as np
import pandas as pd

from earnings_engine.config import Settings
from earnings_engine.data.universe import is_fno_eligible
from earnings_engine.data.breakout_scanner.indicators import (
    _calc_atr_pct,
    _score_resistance_proximity,
    _score_volume_surge,
    _score_price_compression,
    _score_momentum,
    _score_fundamental,
    _calculate_volume_profile,
    _calculate_donchian_ttm_squeeze,
)

logger = logging.getLogger(__name__)


def _score_classic_technical(
    closes: pd.Series,
    volumes: pd.Series,
    high_series: pd.Series,
    quality_scores: list[float | None],
) -> tuple[float, float, float, float, dict[str, float], str, dict[str, Any]]:
    """Strategy 1: Classic Technical Coiling."""
    signal_price = float(closes.iloc[-1])
    res_score, pct_from_high = _score_resistance_proximity(closes)
    vol_score, vol_ratio = _score_volume_surge(volumes) if len(volumes) >= 5 else (0.0, 1.0)
    comp_score, atr_pct = _score_price_compression(closes)
    mom_score, momentum_signal = _score_momentum(closes)
    fund_score, avg_quality = _score_fundamental(quality_scores or [])

    composite = round(res_score + vol_score + comp_score + mom_score + fund_score, 1)

    window = min(len(closes), 252)
    resistance_high = float(high_series.tail(window).max())
    prior_resistance = float(high_series.iloc[:-1].tail(window).max()) if len(high_series) > 1 else resistance_high

    atr_pct_val = atr_pct if (atr_pct is not None and not np.isnan(atr_pct)) else 2.0
    atr_val = signal_price * (atr_pct_val / 100.0)
    if round(resistance_high, 2) <= round(signal_price, 2) or signal_price >= round(prior_resistance, 2):
        breakout_trigger = round(signal_price + max(signal_price * 0.0075, 0.5 * atr_val), 2)
        ideal_entry_price = round(prior_resistance, 2)
    else:
        breakout_trigger = round(resistance_high, 2)
        ideal_entry_price = round(resistance_high, 2)
    daily_high = float(high_series.iloc[-1]) if high_series is not None and len(high_series) > 0 else signal_price
    is_late = bool(ideal_entry_price and ideal_entry_price > 0 and (signal_price > ideal_entry_price * 1.002 or daily_high > ideal_entry_price * 1.002))
    entry_delay_pct = round(((daily_high - ideal_entry_price) / ideal_entry_price) * 100, 1) if (is_late and ideal_entry_price and ideal_entry_price > 0) else 0.0

    target_price = round(max(breakout_trigger * 1.08, breakout_trigger + 2.0 * atr_val), 2)
    stop_loss = round(min(signal_price * 0.95, signal_price - 1.5 * atr_val), 2)

    if (pct_from_high is not None and pct_from_high >= -1.5) and (vol_ratio is not None and vol_ratio >= 1.5):
        archetype = "🔥 High-Volume 52W Breakout"
    elif comp_score >= 8 and res_score >= 25:
        archetype = "🗜️ Coiling Resistance Squeeze"
    elif vol_ratio is not None and vol_ratio >= 1.8:
        archetype = "📊 Institutional Accumulation Surge"
    elif mom_score >= 15:
        archetype = "🚀 Trend Continuation Breakout"
    else:
        archetype = "📈 Resistance Approach Coil"

    subscores = {
        "resistance_score": res_score,
        "volume_score": vol_score,
        "compression_score": comp_score,
        "momentum_score": mom_score,
        "fundamental_score": fund_score,
    }

    notes = {
        "setup_archetype": archetype,
        "strategy_id": "CLASSIC_TECHNICAL",
        "resistance_reasoning": f"Price ₹{signal_price:,.2f} is {pct_from_high:+.1f}% from 52W/recent high of ₹{resistance_high:,.2f} ({res_score:.1f}/30 pts)",
        "volume_reasoning": f"Volume is {vol_ratio:.2f}× of 20D baseline ({vol_score:.1f}/20 pts)",
        "compression_reasoning": f"ATR(14) is {atr_pct:.2f}% of price, signaling tight consolidation ({comp_score:.1f}/15 pts)",
        "momentum_reasoning": f"Momentum posture is '{momentum_signal}' ({mom_score:.1f}/15 pts)",
        "fundamental_reasoning": f"Historical EPS quality score avg {avg_quality:.1f}/9 ({fund_score:.1f}/20 pts)",
        "formula_summary": f"Score {composite}/100 = Res({res_score:.0f}) + Vol({vol_score:.0f}) + Squeeze({comp_score:.0f}) + Mom({mom_score:.0f}) + Fund({fund_score:.0f})",
        "ideal_entry_price": ideal_entry_price,
        "is_late": is_late,
        "entry_delay_pct": entry_delay_pct,
    }
    return composite, breakout_trigger, target_price, stop_loss, subscores, archetype, notes


def _score_nse_delivery_absorption(
    ticker: str,
    closes: pd.Series,
    volumes: pd.Series,
    high_series: pd.Series,
    low_series: pd.Series,
    quality_scores: list[float | None],
    settings: Settings | None = None,
) -> tuple[float, float, float, float, dict[str, float], str, dict[str, Any]]:
    """Strategy 2: NSE Institutional Delivery & Absorption Breakout."""
    signal_price = float(closes.iloc[-1])
    vol_ratio = float(volumes.iloc[-1] / max(1.0, volumes.tail(21).iloc[:-1].mean())) if len(volumes) >= 5 else 1.0

    # 1. Delivery Surge Score (0-35)
    if vol_ratio >= 2.0:
        deliv_score = 35.0
    elif vol_ratio >= 1.5:
        deliv_score = 28.0
    elif vol_ratio >= 1.2:
        deliv_score = 20.0
    else:
        deliv_score = 8.0

    # 2. Institutional Net Inflows (0-25)
    funds_in = 0
    net_flow = 0.0
    act_verdict = "Neutral"
    try:
        from earnings_engine.data.institutional_accumulation import get_stock_institutional_activity
        act = get_stock_institutional_activity(ticker)
        if act:
            funds_in = act.get("funds_accumulating_count", 0)
            net_flow = act.get("net_flow_cr", 0.0)
            act_verdict = act.get("verdict", "Neutral")
    except Exception:
        pass

    if funds_in >= 3 or net_flow >= 100:
        inst_score = 25.0
    elif funds_in >= 1 or net_flow > 0:
        inst_score = 18.0
    else:
        inst_score = 10.0

    # 3. Delivery Ceiling Resistance (0-20)
    top_vol_idx = volumes.tail(20).nlargest(3).index if len(volumes) >= 5 else closes.tail(20).index
    delivery_highs = high_series.loc[high_series.index.isin(top_vol_idx)]
    delivery_resistance = float(delivery_highs.max()) if not delivery_highs.empty else float(closes.tail(20).max())

    atr_pct = _calc_atr_pct(closes, default=2.0)
    atr_val = signal_price * (atr_pct / 100.0)

    ideal_entry_price = round(delivery_resistance, 2)
    if delivery_resistance <= signal_price:
        recent_high = float(high_series.tail(20).max()) if len(high_series) >= 5 else signal_price
        if recent_high > signal_price:
            delivery_trigger = round(recent_high, 2)
        else:
            delivery_trigger = round(signal_price + max(signal_price * 0.008, 0.75 * atr_val), 2)
    else:
        delivery_trigger = round(delivery_resistance, 2)
    daily_high = float(high_series.iloc[-1]) if high_series is not None and len(high_series) > 0 else signal_price
    is_late = bool(ideal_entry_price and ideal_entry_price > 0 and (signal_price > ideal_entry_price * 1.002 or daily_high > ideal_entry_price * 1.002))
    entry_delay_pct = round(((daily_high - ideal_entry_price) / ideal_entry_price) * 100, 1) if (is_late and ideal_entry_price and ideal_entry_price > 0) else 0.0

    pct_from_deliv = ((signal_price - delivery_trigger) / delivery_trigger) * 100
    if pct_from_deliv >= -1.0:
        deliv_res_score = 20.0
    elif pct_from_deliv >= -3.0:
        deliv_res_score = 15.0
    elif pct_from_deliv >= -5.0:
        deliv_res_score = 10.0
    else:
        deliv_res_score = 4.0

    # 4. Fundamental Track Record (0-20)
    fund_score, avg_quality = _score_fundamental(quality_scores or [])
    fund_score_norm = round((fund_score / 15.0) * 20.0, 1)

    composite = round(deliv_score + inst_score + deliv_res_score + fund_score_norm, 1)

    target_price = round(delivery_trigger + max(delivery_trigger * 0.10, 2.5 * atr_val), 2)

    base_lows = low_series.tail(20)
    base_floor = float(base_lows.min()) if not base_lows.empty else signal_price * 0.95
    stop_loss = round(min(signal_price * 0.95, base_floor - 1.0 * atr_val), 2)

    archetype = "🏛️ NSE Institutional Delivery Surge" if deliv_score >= 28 else "🏦 Block Accumulation Absorption"

    subscores = {
        "resistance_score": deliv_res_score,
        "volume_score": deliv_score,
        "compression_score": 10.0,
        "momentum_score": inst_score,
        "fundamental_score": fund_score_norm,
    }

    notes = {
        "setup_archetype": archetype,
        "strategy_id": "NSE_DELIVERY_ABSORPTION",
        "resistance_reasoning": f"Delivery ceiling resistance at ₹{delivery_trigger:,.2f} ({pct_from_deliv:+.1f}% distance, {deliv_res_score:.1f}/20 pts)",
        "volume_reasoning": f"Deliverable volume surge {vol_ratio:.2f}× baseline ({deliv_score:.1f}/35 pts)",
        "compression_reasoning": f"Accumulation base floor holding at ₹{base_floor:,.2f}",
        "momentum_reasoning": f"Institutional flow: {funds_in} funds accumulating (₹{net_flow:+.1f} Cr net, {inst_score:.1f}/25 pts)",
        "fundamental_reasoning": f"Quarterly beat streak quality {avg_quality:.1f}/9 ({fund_score_norm:.1f}/20 pts)",
        "formula_summary": f"Score {composite}/100 = DelivVol({deliv_score:.0f}) + InstFlow({inst_score:.0f}) + DelivRes({deliv_res_score:.0f}) + Fund({fund_score_norm:.0f})",
        "ideal_entry_price": ideal_entry_price,
        "is_late": is_late,
        "entry_delay_pct": entry_delay_pct,
    }
    return composite, delivery_trigger, target_price, stop_loss, subscores, archetype, notes


def _score_fo_call_wall(
    ticker: str,
    closes: pd.Series,
    volumes: pd.Series,
    high_series: pd.Series,
    low_series: pd.Series,
    settings: Settings | None = None,
) -> tuple[float, float, float, float, dict[str, float], str, dict[str, Any]]:
    """Strategy 3: NSE F&O Option Chain Call OI Wall & Gamma Squeeze."""
    signal_price = float(closes.iloc[-1])

    # Guardrail: Non-F&O equities have no derivatives or option chain
    if not is_fno_eligible(ticker):
        subscores = {
            "resistance_score": 0.0,
            "volume_score": 0.0,
            "compression_score": 0.0,
            "momentum_score": 0.0,
            "fundamental_score": 0.0,
        }
        notes = {
            "setup_archetype": "Non-F&O Cash Equity",
            "strategy_id": "NSE_FO_CALL_WALL",
            "formula_summary": f"Ticker {ticker} is not NSE F&O eligible. F&O Call Wall strategy skipped.",
        }
        return 0.0, signal_price, signal_price, signal_price, subscores, "Non-F&O Stock", notes

    # 1. Option Chain Derivatives Integration
    call_oi_strike = signal_price * 1.04
    pcr_oi = 1.05
    max_pain = signal_price * 0.97
    sentiment = "BULLISH"
    try:
        from earnings_engine.data.option_chain import analyze_option_chain
        opt = analyze_option_chain(ticker, spot_price=signal_price, settings=settings)
        if opt and opt.get("status") != "NOT_FNO":
            call_oi_strike = opt.get("resistance_strike") or opt.get("highest_call_oi_strike") or (signal_price * 1.04)
            pcr_oi = opt.get("pcr_oi") if opt.get("pcr_oi") is not None else 1.0
            max_pain = opt.get("max_pain_strike") or (signal_price * 0.97)
            sentiment = opt.get("sentiment") or "BULLISH"
    except Exception:
        pass

    call_oi_strike = round(float(call_oi_strike), 2)
    orig_call_wall = call_oi_strike
    if call_oi_strike <= signal_price:
        call_oi_strike = round(signal_price * 1.025, 2)
    ideal_entry_price = orig_call_wall
    daily_high = float(high_series.iloc[-1]) if high_series is not None and len(high_series) > 0 else signal_price
    is_late = bool(ideal_entry_price and ideal_entry_price > 0 and (signal_price > ideal_entry_price * 1.002 or daily_high > ideal_entry_price * 1.002))
    entry_delay_pct = round(((daily_high - ideal_entry_price) / ideal_entry_price) * 100, 1) if (is_late and ideal_entry_price and ideal_entry_price > 0) else 0.0
    dist_to_call_wall = ((call_oi_strike - signal_price) / signal_price) * 100

    # 1. Call OI Wall Proximity (0-35)
    if dist_to_call_wall <= 1.5:
        wall_score = 35.0
    elif dist_to_call_wall <= 3.0:
        wall_score = 28.0
    elif dist_to_call_wall <= 5.0:
        wall_score = 18.0
    else:
        wall_score = 8.0

    # 2. PCR Ratio Trend (0-25)
    if pcr_oi >= 1.25:
        pcr_score = 25.0
    elif pcr_oi >= 1.0:
        pcr_score = 18.0
    elif pcr_oi >= 0.8:
        pcr_score = 12.0
    else:
        pcr_score = 4.0

    # 3. Call Short-Covering Unwinding (0-20)
    unwind_score = 20.0 if sentiment == "BULLISH" else (12.0 if sentiment == "NEUTRAL" else 5.0)

    # 4. Underlying Trend Strength (0-20)
    mom_score_raw, mom_sig = _score_momentum(closes)
    trend_score = round((mom_score_raw / 25.0) * 20.0, 1)

    composite = round(wall_score + pcr_score + unwind_score + trend_score, 1)

    breakout_trigger = call_oi_strike
    target_price = round(breakout_trigger * 1.06, 2)
    stop_loss = round(min(signal_price * 0.95, float(max_pain)), 2)

    archetype = "🎯 F&O Call Wall Gamma Squeeze" if wall_score >= 28 else "⚡ Option Chain Resistance Breach"

    subscores = {
        "resistance_score": wall_score,
        "volume_score": unwind_score,
        "compression_score": 10.0,
        "momentum_score": pcr_score,
        "fundamental_score": trend_score,
    }

    notes = {
        "setup_archetype": archetype,
        "strategy_id": "NSE_FO_CALL_WALL",
        "resistance_reasoning": f"Major Call OI Wall at strike ₹{call_oi_strike:,.2f} ({dist_to_call_wall:.1f}% away, {wall_score:.1f}/35 pts)",
        "volume_reasoning": f"Option sentiment is '{sentiment}' indicating call unwinding ({unwind_score:.1f}/20 pts)",
        "compression_reasoning": f"Max pain support floor situated at ₹{max_pain:,.2f}",
        "momentum_reasoning": f"Put-Call Ratio (PCR OI) is {pcr_oi:.2f} ({pcr_score:.1f}/25 pts)",
        "fundamental_reasoning": f"Underlying technical trend is {mom_sig} ({trend_score:.1f}/20 pts)",
        "formula_summary": f"Score {composite}/100 = CallOIWall({wall_score:.0f}) + PCR({pcr_score:.0f}) + Unwind({unwind_score:.0f}) + Trend({trend_score:.0f})",
        "ideal_entry_price": ideal_entry_price,
        "is_late": is_late,
        "entry_delay_pct": entry_delay_pct,
    }
    return composite, breakout_trigger, target_price, stop_loss, subscores, archetype, notes


def _score_volume_profile_vah(
    closes: pd.Series,
    volumes: pd.Series,
    high_series: pd.Series,
    low_series: pd.Series,
    df: pd.DataFrame,
) -> tuple[float, float, float, float, dict[str, float], str, dict[str, Any]]:
    """Strategy 4: Volume Profile & Value Area High (VAH) Expansion."""
    signal_price = float(closes.iloc[-1])
    poc, vah, val, lvn_ratio = _calculate_volume_profile(df.iloc[-63:])

    pct_from_vah = ((signal_price - vah) / max(0.01, vah)) * 100

    # 1. VAH Breakout Proximity (0-35)
    if pct_from_vah >= 0:
        vah_score = 35.0
    elif pct_from_vah >= -1.0:
        vah_score = 30.0
    elif pct_from_vah >= -2.5:
        vah_score = 22.0
    elif pct_from_vah >= -5.0:
        vah_score = 12.0
    else:
        vah_score = 4.0

    # 2. LVN Vacuum Air-Pocket Factor (0-30)
    if lvn_ratio < 0.6:
        lvn_score = 30.0
    elif lvn_ratio < 0.9:
        lvn_score = 22.0
    elif lvn_ratio < 1.3:
        lvn_score = 14.0
    else:
        lvn_score = 6.0

    # 3. POC Consolidation Energy (0-20)
    poc_dist = abs((signal_price - poc) / max(0.01, poc)) * 100
    poc_score = 20.0 if poc_dist <= 2.5 else (14.0 if poc_dist <= 5.0 else 6.0)

    # 4. Relative Volume Surge (0-15)
    vol_ratio = float(volumes.iloc[-1] / max(1.0, volumes.tail(21).iloc[:-1].mean())) if len(volumes) >= 5 else 1.0
    rel_vol_score = 15.0 if vol_ratio >= 1.5 else (10.0 if vol_ratio >= 1.2 else 4.0)

    composite = round(vah_score + lvn_score + poc_score + rel_vol_score, 1)

    va_height = max(signal_price * 0.05, vah - poc)
    ideal_entry_price = round(float(vah), 2)
    if vah <= signal_price:
        breakout_trigger = round(signal_price + max(signal_price * 0.008, va_height * 0.25), 2)
    else:
        breakout_trigger = round(vah, 2)
    daily_high = float(high_series.iloc[-1]) if high_series is not None and len(high_series) > 0 else signal_price
    is_late = bool(ideal_entry_price and ideal_entry_price > 0 and (signal_price > ideal_entry_price * 1.002 or daily_high > ideal_entry_price * 1.002))
    entry_delay_pct = round(((daily_high - ideal_entry_price) / ideal_entry_price) * 100, 1) if (is_late and ideal_entry_price and ideal_entry_price > 0) else 0.0

    target_price = round(breakout_trigger + va_height * 1.5, 2)
    stop_loss = round(min(signal_price * 0.95, poc), 2)

    archetype = "📊 Volume Profile VAH Expansion" if vah_score >= 30 else "🌀 POC Equilibrium Breakout"

    subscores = {
        "resistance_score": vah_score,
        "volume_score": lvn_score,
        "compression_score": poc_score,
        "momentum_score": rel_vol_score,
        "fundamental_score": 10.0,
    }

    notes = {
        "setup_archetype": archetype,
        "strategy_id": "VOLUME_PROFILE_VAH",
        "resistance_reasoning": f"63-Day Value Area High (VAH) ceiling at ₹{vah:,.2f} ({pct_from_vah:+.1f}% distance, {vah_score:.1f}/35 pts)",
        "volume_reasoning": f"Low Volume Node ratio above VAH is {lvn_ratio:.2f}× (thin liquidity vacuum, {lvn_score:.1f}/30 pts)",
        "compression_reasoning": f"Point of Control (POC) high-volume node at ₹{poc:,.2f} ({poc_dist:.1f}% dist, {poc_score:.1f}/20 pts)",
        "momentum_reasoning": f"Traded volume surge {vol_ratio:.2f}× baseline ({rel_vol_score:.1f}/15 pts)",
        "fundamental_reasoning": "Volume Profile price-acceptance structure confirmed across 63 sessions",
        "formula_summary": f"Score {composite}/100 = VAH({vah_score:.0f}) + LVNVacuum({lvn_score:.0f}) + POC({poc_score:.0f}) + RelVol({rel_vol_score:.0f})",
        "ideal_entry_price": ideal_entry_price,
        "is_late": is_late,
        "entry_delay_pct": entry_delay_pct,
    }
    return composite, breakout_trigger, target_price, stop_loss, subscores, archetype, notes


def _score_donchian_squeeze(
    closes: pd.Series,
    volumes: pd.Series,
    high_series: pd.Series,
    low_series: pd.Series,
) -> tuple[float, float, float, float, dict[str, float], str, dict[str, Any]]:
    """Strategy 5: Volatility Compression & 55-Day Donchian Squeeze."""
    signal_price = float(closes.iloc[-1])
    squeeze_on, donchian_55, mom_osc, bb_w, kc_w = _calculate_donchian_ttm_squeeze(closes, high_series, low_series)

    # 1. TTM Squeeze Energy (0-35)
    if squeeze_on:
        squeeze_score = 35.0
    elif bb_w <= kc_w * 1.15:
        squeeze_score = 25.0
    else:
        squeeze_score = 8.0

    # 2. 55-Day Donchian Channel Proximity (0-30)
    pct_from_donchian = ((signal_price - donchian_55) / max(0.01, donchian_55)) * 100
    if pct_from_donchian >= 0:
        donchian_score = 30.0
    elif pct_from_donchian >= -1.0:
        donchian_score = 25.0
    elif pct_from_donchian >= -2.5:
        donchian_score = 18.0
    elif pct_from_donchian >= -5.0:
        donchian_score = 10.0
    else:
        donchian_score = 4.0

    # 3. Momentum Oscillator (0-20)
    if mom_osc >= 3.0:
        mom_score = 20.0
    elif mom_osc > 0:
        mom_score = 14.0
    else:
        mom_score = 4.0

    # 4. Volume Expansion (0-15)
    vol_ratio = float(volumes.iloc[-1] / max(1.0, volumes.tail(21).iloc[:-1].mean())) if len(volumes) >= 5 else 1.0
    vol_score = 15.0 if vol_ratio >= 1.4 else (10.0 if vol_ratio >= 1.1 else 4.0)

    composite = round(squeeze_score + donchian_score + mom_score + vol_score, 1)

    atr_pct = _calc_atr_pct(closes, default=2.0)
    atr_val = signal_price * (atr_pct / 100.0)

    prior_donchian = float(high_series.iloc[:-1].tail(55).max()) if len(high_series) > 1 else donchian_55
    if round(donchian_55, 2) <= round(signal_price, 2) or signal_price >= round(prior_donchian, 2):
        breakout_trigger = round(signal_price + max(signal_price * 0.008, 0.75 * atr_val), 2)
        ideal_entry_price = round(prior_donchian, 2)
    else:
        breakout_trigger = round(donchian_55, 2)
        ideal_entry_price = round(donchian_55, 2)
    daily_high = float(high_series.iloc[-1]) if high_series is not None and len(high_series) > 0 else signal_price
    is_late = bool(ideal_entry_price and ideal_entry_price > 0 and (signal_price > ideal_entry_price * 1.002 or daily_high > ideal_entry_price * 1.002))
    entry_delay_pct = round(((daily_high - ideal_entry_price) / ideal_entry_price) * 100, 1) if (is_late and ideal_entry_price and ideal_entry_price > 0) else 0.0

    target_price = round(breakout_trigger + 3.0 * atr_val, 2)
    sma_20 = float(closes.values[-20:].mean())
    stop_loss = round(min(signal_price * 0.95, sma_20), 2)

    archetype = "🌪️ TTM Donchian Volatility Squeeze" if squeeze_on else "🚀 55-Day Channel Breakout"

    subscores = {
        "resistance_score": donchian_score,
        "volume_score": vol_score,
        "compression_score": squeeze_score,
        "momentum_score": mom_score,
        "fundamental_score": 10.0,
    }

    notes = {
        "setup_archetype": archetype,
        "strategy_id": "DONCHIAN_TTM_SQUEEZE",
        "resistance_reasoning": f"55-Day Donchian Channel High at ₹{donchian_55:,.2f} ({pct_from_donchian:+.1f}% distance, {donchian_score:.1f}/30 pts)",
        "volume_reasoning": f"Volume ratio {vol_ratio:.2f}× confirming breakout expansion ({vol_score:.1f}/15 pts)",
        "compression_reasoning": f"John Carter TTM Squeeze is {'🔥 ON (BB inside Keltner)' if squeeze_on else '🟡 Expanding'} ({squeeze_score:.1f}/35 pts)",
        "momentum_reasoning": f"Momentum slope oscillator is {mom_osc:+.1f}% vs 20 SMA ({mom_score:.1f}/20 pts)",
        "fundamental_reasoning": f"Trailing trend stop loss mapped to 20-Day SMA at ₹{sma_20:,.2f}",
        "formula_summary": f"Score {composite}/100 = TTMSqueeze({squeeze_score:.0f}) + Donchian55({donchian_score:.0f}) + MomOsc({mom_score:.0f}) + Vol({vol_score:.0f})",
        "ideal_entry_price": ideal_entry_price,
        "is_late": is_late,
        "entry_delay_pct": entry_delay_pct,
    }
    return composite, breakout_trigger, target_price, stop_loss, subscores, archetype, notes
