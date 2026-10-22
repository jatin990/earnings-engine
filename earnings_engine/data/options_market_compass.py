"""Market Compass Quantitative Confluence Engine.

Combines 8 orthogonal derivatives & price action factors into a normalized
[-100, +100] market regime score and confidence metric:
1. Option Writing Flow (25%)
2. PCR (OI) & Momentum (10%)
3. Support vs Resistance Walls (10%)
4. Futures Build-up / Unwinding (15%)
5. Price vs Session VWAP (8%)
6. Smart Money Concepts / ICT Structure (20%)
7. Volatility Skew & VIX (5%)
8. Order Book / Market Depth Imbalance (7%)
"""

from __future__ import annotations

import math
from typing import Any


def calculate_market_compass(
    symbol: str,
    spot_price: float,
    pcr_oi: float,
    pcr_volume: float,
    call_wall: float | None,
    put_wall: float | None,
    max_pain: float | None,
    gamma_profile: dict[str, Any] | None,
    oi_timeframes: dict[str, Any] | None,
    chart_intel: dict[str, Any] | None,
    vix_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Calculate the 8-Factor Market Compass Confluence score, regime verdict, and factor breakdown."""
    gp = gamma_profile or {}
    tf = oi_timeframes or {}
    ci = chart_intel or {}
    vix = vix_data or {}

    factors: list[dict[str, Any]] = []

    # 1. Option Writing Flow (Weight: 25%)
    today_oi = tf.get("today", {})
    c_chg = float(today_oi.get("call_chg") or 0.0)
    p_chg = float(today_oi.get("put_chg") or 0.0)
    tot_chg = abs(c_chg) + abs(p_chg)

    if tot_chg > 0:
        raw_flow = (p_chg - c_chg) / tot_chg  # Range [-1.0, 1.0]
        flow_score = round(max(min(raw_flow * 100.0, 100.0), -100.0), 1)
    else:
        flow_score = 0.0

    if flow_score >= 25:
        flow_bias = "BULLISH"
        ratio = round(p_chg / max(c_chg, 1), 1) if c_chg > 0 else 2.5
        flow_detail = f"Aggressive Put Writing ({ratio}x Call Writing)"
    elif flow_score <= -25:
        flow_bias = "BEARISH"
        ratio = round(c_chg / max(p_chg, 1), 1) if p_chg > 0 else 2.5
        flow_detail = f"Aggressive Call Writing ({ratio}x Put Writing)"
    else:
        flow_bias = "NEUTRAL"
        flow_detail = "Balanced two-way writing inventory"

    factors.append({
        "name": "Option Writing Flow",
        "weight": 25,
        "score": flow_score,
        "bias": flow_bias,
        "detail": flow_detail,
    })

    # 2. PCR (OI) & Momentum (Weight: 10%)
    pcr = float(pcr_oi or 1.0)
    # Baseline 1.0; 0.6 -> -100, 1.4 -> +100
    pcr_score = round(max(min(((pcr - 1.0) / 0.4) * 100.0, 100.0), -100.0), 1)
    if pcr >= 1.2:
        pcr_bias = "BULLISH"
        pcr_detail = f"Strong floor support (PCR {pcr:.2f})"
    elif pcr <= 0.8:
        pcr_bias = "BEARISH"
        pcr_detail = f"Heavy call buildup (PCR {pcr:.2f})"
    else:
        pcr_bias = "NEUTRAL"
        pcr_detail = f"Neutral equilibrium (PCR {pcr:.2f})"

    factors.append({
        "name": "PCR (OI)",
        "weight": 10,
        "score": pcr_score,
        "bias": pcr_bias,
        "detail": pcr_detail,
    })

    # 3. Support vs Resistance Walls (Weight: 10%)
    c_w = float(call_wall) if call_wall else spot_price * 1.02
    p_w = float(put_wall) if put_wall else spot_price * 0.98

    dist_put = (spot_price - p_w) if spot_price >= p_w else (spot_price - p_w) * 2
    dist_call = (c_w - spot_price) if c_w >= spot_price else (c_w - spot_price) * 2
    wall_spread = max(c_w - p_w, 1.0)

    # Positive if closer to Call Wall (breakout pressure) or comfortably above Put Wall
    wall_norm = (dist_put - dist_call) / wall_spread
    wall_score = round(max(min(wall_norm * 80.0, 100.0), -100.0), 1)
    if wall_score >= 15:
        wall_bias = "BULLISH"
        wall_detail = f"Trading well above Put Wall (₹{int(p_w):,})"
    elif wall_score <= -15:
        wall_bias = "BEARISH"
        wall_detail = f"Pressured below Call Wall (₹{int(c_w):,})"
    else:
        wall_bias = "NEUTRAL"
        wall_detail = f"Midway between ₹{int(p_w):,} and ₹{int(c_w):,}"

    factors.append({
        "name": "Support vs Resistance",
        "weight": 10,
        "score": wall_score,
        "bias": wall_bias,
        "detail": wall_detail,
    })

    # 4. Futures Build-up / Unwinding (Weight: 15%)
    pcr_vol = float(pcr_volume or 1.0)
    gamma_regime = gp.get("gamma_regime", "NEUTRAL")

    if flow_bias == "BULLISH" and pcr_vol >= 1.05:
        fut_score = 75.0
        fut_bias = "BULLISH"
        fut_detail = "Long Buildup with volume expansion"
    elif flow_bias == "BEARISH" and pcr_vol <= 0.95:
        fut_score = -75.0
        fut_bias = "BEARISH"
        fut_detail = "Short Buildup with aggressive put buying"
    elif gamma_regime == "POSITIVE_GAMMA":
        fut_score = 20.0
        fut_bias = "NEUTRAL"
        fut_detail = "Order flow absorbing in Positive Gamma"
    else:
        fut_score = -20.0
        fut_bias = "NEUTRAL"
        fut_detail = "Two-way rotational positioning"

    factors.append({
        "name": "Futures Build-up",
        "weight": 15,
        "score": fut_score,
        "bias": fut_bias,
        "detail": fut_detail,
    })

    # 5. Price vs Session VWAP (Weight: 8%)
    vwap_dist = float(ci.get("vwap_dist_pct") or 0.0)
    # ±0.8% distance = ±100 score
    vwap_score = round(max(min((vwap_dist / 0.8) * 100.0, 100.0), -100.0), 1)
    if vwap_dist >= 0.15:
        vwap_bias = "BULLISH"
        vwap_detail = f"+{vwap_dist:.2f}% above Session VWAP"
    elif vwap_dist <= -0.15:
        vwap_bias = "BEARISH"
        vwap_detail = f"{vwap_dist:.2f}% below Session VWAP"
    else:
        vwap_bias = "NEUTRAL"
        vwap_detail = f"At Session VWAP equilibrium ({vwap_dist:+.2f}%)"

    factors.append({
        "name": "Price vs VWAP",
        "weight": 8,
        "score": vwap_score,
        "bias": vwap_bias,
        "detail": vwap_detail,
    })

    # 6. Smart Money Concepts / ICT Structure (Weight: 20%)
    smc_bias = ci.get("smc_bias", "NEUTRAL")
    orb_status = ci.get("orb_status", "INSIDE_RANGE")

    smc_score = 0.0
    if smc_bias == "BULLISH":
        smc_score += 45.0
    elif smc_bias == "BEARISH":
        smc_score -= 45.0

    if orb_status == "BREAKOUT_BULLISH":
        smc_score += 45.0
    elif orb_status == "BREAKDOWN_BEARISH":
        smc_score -= 45.0

    smc_score = round(max(min(smc_score, 100.0), -100.0), 1)
    if smc_score >= 25:
        smc_final_bias = "BULLISH"
        smc_detail = "Bullish Order Block & Range Expansion held"
    elif smc_score <= -25:
        smc_final_bias = "BEARISH"
        smc_detail = "Bearish Supply Block & Range Breakdown active"
    else:
        smc_final_bias = "NEUTRAL"
        smc_detail = "Consolidating within opening range structure"

    factors.append({
        "name": "SMC / ICT Structure",
        "weight": 20,
        "score": smc_score,
        "bias": smc_final_bias,
        "detail": smc_detail,
    })

    # 7. Volatility Skew & VIX (Weight: 5%)
    vix_val = float(vix.get("vix_value") or 13.5)
    vix_chg = float(vix.get("vix_change_pct") or 0.0)

    # Subdued VIX with negative change is favorable for rally/stability (+score)
    # Surging VIX indicates downside panic (-score)
    vix_score = round(max(min(-vix_chg * 15.0, 100.0), -100.0), 1)
    if vix_chg <= -1.5:
        vix_bias = "BULLISH"
        vix_detail = f"VIX contracting ({vix_val:.1f}, {vix_chg:+.1f}%)"
    elif vix_chg >= 1.5:
        vix_bias = "BEARISH"
        vix_detail = f"VIX elevated / spiking ({vix_val:.1f}, {vix_chg:+.1f}%)"
    else:
        vix_bias = "NEUTRAL"
        vix_detail = f"VIX normal ({vix_val:.1f}, {vix_chg:+.1f}%)"

    factors.append({
        "name": "Volatility Skew",
        "weight": 5,
        "score": vix_score,
        "bias": vix_bias,
        "detail": vix_detail,
    })

    # 8. Order Book / Market Depth Pressure (Weight: 7%)
    # Approximated from Call vs Put volume execution ratio
    depth_score = round(max(min(((pcr_vol - 1.0) / 0.5) * 80.0, 100.0), -100.0), 1)
    if depth_score >= 20:
        depth_bias = "BULLISH"
        depth_detail = f"Aggressive Bid absorption (PCR Vol {pcr_vol:.2f})"
    elif depth_score <= -20:
        depth_bias = "BEARISH"
        depth_detail = f"Supply pressure on Ask ladder (PCR Vol {pcr_vol:.2f})"
    else:
        depth_bias = "NEUTRAL"
        depth_detail = "Balanced Bid/Ask book depth"

    factors.append({
        "name": "Order Book Pressure",
        "weight": 7,
        "score": depth_score,
        "bias": depth_bias,
        "detail": depth_detail,
    })

    # Weighted Composite Score
    composite_score = sum((f["score"] * f["weight"]) / 100.0 for f in factors)
    composite_score = round(max(min(composite_score, 100.0), -100.0), 1)

    # Regime Verdict & Confidence
    abs_score = abs(composite_score)
    confidence_pct = int(min(max(55 + (abs_score * 0.42), 55), 96))

    if composite_score >= 40:
        sentiment = "STRONG_BULLISH"
        verdict = "Bullish Confluence — Aggressive Put Writing"
        theme = "emerald"
    elif composite_score >= 15:
        sentiment = "BULLISH"
        verdict = "Mild Bullish Bias — Support Accumulation"
        theme = "emerald"
    elif composite_score <= -40:
        sentiment = "STRONG_BEARISH"
        verdict = "Bearish Confluence — Heavy Call Writing"
        theme = "rose"
    elif composite_score <= -15:
        sentiment = "BEARISH"
        verdict = "Mild Bearish Bias — Overhead Supply Pressure"
        theme = "rose"
    else:
        sentiment = "NEUTRAL"
        verdict = "Neutral Equilibrium — Max Pain Pin"
        theme = "amber"

    return {
        "score": composite_score,
        "sentiment": sentiment,
        "confidence_pct": confidence_pct,
        "verdict": verdict,
        "theme": theme,
        "factors": factors,
    }
