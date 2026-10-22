"""Five-pillar algorithmic next-day market playbook and volatility corridor engine."""

from __future__ import annotations

import logging
import math
from typing import Any

from earnings_engine.config import Settings

logger = logging.getLogger(__name__)


def compute_next_day_market_playbook(
    settings: Settings | None = None,
    indices_data: list[dict[str, Any]] | None = None,
    liquidity: dict[str, Any] | None = None,
    participant_oi: dict[str, Any] | None = None,
    sentiment_data: dict[str, Any] | None = None,
    sectors: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Synthesize complete actionable Next-Day Market Playbook.

    Operates across five core quantitative pillars:
      Pillar 1: Derivatives Open Interest (Index Futures Long % and L/S Ratio)
      Pillar 2: Institutional Cash Liquidity (FII/DII Net Flow & 7D Total)
      Pillar 3: Volatility & Corridor (India VIX level and 1-Sigma daily expected range)
      Pillar 4: Market Breadth (% Stocks > 20-DMA and Advance/Decline ratio)
      Pillar 5: Price Momentum & Index Moving Averages
    """
    indices_data = indices_data or []
    liquidity = liquidity or {}
    participant_oi = participant_oi or {}
    sentiment_data = sentiment_data or {}
    sectors = sectors or []

    # 1. Extract Core Index Prices & Volatility Levels
    nifty = next((idx for idx in indices_data if idx["symbol"] == "^NSEI"), None)
    bank_nifty = next((idx for idx in indices_data if idx["symbol"] == "^NSEBANK"), None)
    vix = next((idx for idx in indices_data if idx["symbol"] == "^INDIAVIX"), None)

    nifty_spot = float(nifty.get("price") or 24500.0) if nifty else 24500.0
    bank_spot = float(bank_nifty.get("price") or 52000.0) if bank_nifty else 52000.0
    vix_level = float(vix.get("price") or sentiment_data.get("vix_level") or 14.0)

    # 2. Compute 1-Day Expected Move Corridor using 1-Sigma and 2-Sigma Volatility
    # Formula: Expected Daily Vol = VIX / sqrt(252) ~= VIX / 15.8745
    daily_vol_pct = (vix_level / math.sqrt(252))
    expected_1d_move_pct = round(daily_vol_pct, 2)
    expected_1d_move_pts = round(nifty_spot * (daily_vol_pct / 100.0), 0)

    # 1-Sigma (68.2% Probability Band)
    upper_band_1sigma = round(nifty_spot + expected_1d_move_pts, 0)
    lower_band_1sigma = round(nifty_spot - expected_1d_move_pts, 0)

    # 2-Sigma (95.4% Probability Band)
    upper_band_2sigma = round(nifty_spot + (2 * expected_1d_move_pts), 0)
    lower_band_2sigma = round(nifty_spot - (2 * expected_1d_move_pts), 0)

    # 3. Compute Confluence Pillar Scores
    score_p1_derivatives = 0.0
    score_p2_liquidity = 0.0
    score_p3_volatility = 0.0
    score_p4_breadth = 0.0
    score_p5_momentum = 0.0

    # Pillar 1: Derivatives Open Interest (Max +/- 25)
    fii_data = next((p for p in participant_oi.get("participants", []) if p.get("participant") == "FII" or p.get("type") == "FII"), None)
    client_data = next((p for p in participant_oi.get("participants", []) if p.get("participant") == "CLIENT" or p.get("type") == "CLIENT"), None)

    fii_ls = float(fii_data.get("future_index_ls_ratio", 1.0)) if fii_data else 1.0
    client_ls = float(client_data.get("future_index_ls_ratio", 1.0)) if client_data else 1.0
    fii_long_pct = float(fii_data.get("future_index_long_pct", 50.0)) if fii_data else 50.0

    if fii_long_pct >= 65.0:
        score_p1_derivatives += 20.0
    elif fii_long_pct >= 52.0:
        score_p1_derivatives += 10.0
    elif fii_long_pct <= 35.0:
        score_p1_derivatives -= 20.0
    elif fii_long_pct <= 48.0:
        score_p1_derivatives -= 10.0

    # Smart Money vs Retail contrarian delta
    div_status = participant_oi.get("divergence_code", "BALANCED")
    if div_status == "SHORT_SQUEEZE_EXPANSION":
        score_p1_derivatives += 5.0
    elif div_status == "BEAR_TRAP_RISK":
        score_p1_derivatives -= 5.0

    score_p1_derivatives = max(-25.0, min(25.0, score_p1_derivatives))

    # Pillar 2: Cash Liquidity (Max +/- 25)
    fii_net = float(liquidity.get("fii_net_cr", 0.0))
    dii_net = float(liquidity.get("dii_net_cr", 0.0))
    fii_7d = float(liquidity.get("fii_7d_total", 0.0))
    combined_net = fii_net + dii_net

    if combined_net > 1500.0:
        score_p2_liquidity += 15.0
    elif combined_net > 300.0:
        score_p2_liquidity += 8.0
    elif combined_net < -1500.0:
        score_p2_liquidity -= 15.0
    elif combined_net < -300.0:
        score_p2_liquidity -= 8.0

    if fii_7d > 3000.0:
        score_p2_liquidity += 10.0
    elif fii_7d < -3000.0:
        score_p2_liquidity -= 10.0

    score_p2_liquidity = max(-25.0, min(25.0, score_p2_liquidity))

    # Pillar 3: Volatility & VIX (Max +/- 15)
    nifty_1d_pct = float(nifty.get("change_1d_pct", 0.0)) if nifty else 0.0
    if vix_level < 12.5:
        score_p3_volatility += 10.0
    elif vix_level < 15.5:
        score_p3_volatility += 5.0
    elif vix_level > 21.0:
        score_p3_volatility -= 15.0
    elif vix_level > 17.5:
        score_p3_volatility -= 8.0

    score_p3_volatility = max(-15.0, min(15.0, score_p3_volatility))

    # Pillar 4: Market Breadth (Max +/- 20)
    breadth = sentiment_data.get("breadth", {})
    pct_20dma = float(breadth.get("pct_above_20dma", 50.0))
    ad_ratio = float(breadth.get("advance_decline_ratio", 1.0))

    if pct_20dma >= 65.0:
        score_p4_breadth += 12.0
    elif pct_20dma >= 50.0:
        score_p4_breadth += 6.0
    elif pct_20dma <= 30.0:
        score_p4_breadth -= 12.0
    else:
        score_p4_breadth -= 6.0

    if ad_ratio >= 1.5:
        score_p4_breadth += 8.0
    elif ad_ratio >= 1.0:
        score_p4_breadth += 3.0
    elif ad_ratio <= 0.67:
        score_p4_breadth -= 8.0
    else:
        score_p4_breadth -= 3.0

    score_p4_breadth = max(-20.0, min(20.0, score_p4_breadth))

    # Pillar 5: Technical Momentum & Fear/Greed (Max +/- 15)
    fg_score = float(sentiment_data.get("fear_greed_score", 50.0))
    if nifty_1d_pct > 0.8:
        score_p5_momentum += 8.0
    elif nifty_1d_pct > 0.2:
        score_p5_momentum += 4.0
    elif nifty_1d_pct < -0.8:
        score_p5_momentum -= 8.0
    elif nifty_1d_pct < -0.2:
        score_p5_momentum -= 4.0

    if fg_score > 65.0:
        score_p5_momentum += 7.0
    elif fg_score > 50.0:
        score_p5_momentum += 3.0
    elif fg_score < 35.0:
        score_p5_momentum -= 7.0
    else:
        score_p5_momentum -= 3.0

    score_p5_momentum = max(-15.0, min(15.0, score_p5_momentum))

    # Total Confluence Score (-100 to +100)
    total_confluence_score = round(
        score_p1_derivatives + score_p2_liquidity + score_p3_volatility + score_p4_breadth + score_p5_momentum,
        1,
    )
    total_confluence_score = max(-100.0, min(100.0, total_confluence_score))

    # 4. Determine Directional Market Bias & Playbook Strategy
    if total_confluence_score >= 45.0:
        bias_code = "STRONG_BULLISH"
        bias_badge = "🚀 Aggressive Bullish Momentum"
        bias_color = "emerald"
        headline = "Institutional Long Build-up Driving Trend Expansion"
        theta_env = "FAVORABLE_FOR_OPTION_BUYING"
        primary_action = f"Aggressive dip buying into VWAP / 15-min support ({lower_band_1sigma:,.0f}). Ride momentum toward {upper_band_1sigma:,.0f}."
        option_strategy = f"Bull Call Spread ({math.floor(nifty_spot / 100) * 100} CE Buy / {math.ceil(upper_band_1sigma / 100) * 100} CE Sell) or ATM Call Debit Spreads."
        invalidation = f"15-minute close below 1-Sigma Support ({lower_band_1sigma:,.0f}) invalidates immediate breakout thesis."
    elif total_confluence_score >= 15.0:
        bias_code = "MILD_BULLISH"
        bias_badge = "🟢 Buy on Dips / Bullish Drift"
        bias_color = "teal"
        headline = "Supportive Institutional Liquidity with Mild Upward Bias"
        theta_env = "FAVORABLE_FOR_OPTION_SELLING"
        primary_action = f"Buy morning pullbacks near {lower_band_1sigma:,.0f} support. Take partial profits at upper corridor {upper_band_1sigma:,.0f}."
        option_strategy = f"OTM Put Credit Spread (Sell {math.floor(lower_band_1sigma / 100) * 100} PE / Buy {math.floor((lower_band_1sigma - 200) / 100) * 100} PE) to capture theta decay."
        invalidation = f"Daily breakdown below {lower_band_1sigma:,.0f} shifts stance to neutral range-bound."
    elif total_confluence_score >= -15.0:
        bias_code = "NEUTRAL_RANGEBOUND"
        bias_badge = "⚖️ Neutral / Range-Bound Compression"
        bias_color = "amber"
        headline = "Volatility Compression & Institutional Corridor Pinning"
        theta_env = "FAVORABLE_FOR_OPTION_SELLING"
        primary_action = f"Fade extremes: Sell call spreads near {upper_band_1sigma:,.0f}, sell put spreads near {lower_band_1sigma:,.0f}."
        option_strategy = f"Iron Condor / Short Strangle bounded by {lower_band_1sigma:,.0f} PE and {upper_band_1sigma:,.0f} CE strikes."
        invalidation = f"Sustained 30-minute breakout outside {lower_band_1sigma:,.0f} - {upper_band_1sigma:,.0f} triggers delta-neutral stop."
    elif total_confluence_score >= -45.0:
        bias_code = "SELL_ON_RISE"
        bias_badge = "🟠 Sell on Rallies / Overhead Supply"
        bias_color = "orange"
        headline = "Smart Money Hedging & Bearish Overhead Supply"
        theta_env = "FAVORABLE_FOR_OPTION_SELLING"
        primary_action = f"Fade morning gap-ups into {upper_band_1sigma:,.0f} resistance. Look for reversal confirmation on 5-min VWAP breakdown."
        option_strategy = f"Bear Call Spread (Sell {math.ceil(upper_band_1sigma / 100) * 100} CE / Buy {math.ceil((upper_band_1sigma + 200) / 100) * 100} CE) or OTM Put Debit Spread."
        invalidation = f"Decisive 15-minute close above {upper_band_1sigma:,.0f} forces immediate short hedge exit."
    else:
        bias_code = "HIGH_RISK_DEFENSIVE"
        bias_badge = "🔴 High-Risk Defensive / Bearish Breakdown"
        bias_color = "rose"
        headline = "Institutional Distribution & Elevated Downside Volatility"
        theta_env = "FAVORABLE_FOR_OPTION_BUYING"
        primary_action = f"Capital preservation mode. Avoid blind dip-buying. Short bounces toward {nifty_spot:,.0f} targeting {lower_band_2sigma:,.0f}."
        option_strategy = f"Long Put Debit Spread (Buy {math.ceil(nifty_spot / 100) * 100} PE / Sell {math.floor(lower_band_1sigma / 100) * 100} PE) or Long VIX hedges."
        invalidation = f"Reclaim and hourly close above {upper_band_1sigma:,.0f} aborts defensive posture."

    # 5. Extract Top Focus Sectors
    focus_sectors: list[str] = []
    sorted_sectors = sorted(sectors, key=lambda s: float(s.get("change_1d") or 0.0), reverse=True)
    for s in sorted_sectors[:3]:
        name = s.get("name", "").replace("Nifty ", "")
        chg = s.get("change_1d", 0.0)
        focus_sectors.append(f"{name} ({chg:+.1f}%)")

    # 6. Assemble Final Playbook Payload
    div_trap_score = participant_oi.get("divergence_trap_score", 45)
    div_trap_label = "High" if div_trap_score > 60 else "Moderate" if div_trap_score > 35 else "Low"
    div_warning = participant_oi.get("divergence_warning", "Positioning is balanced.")
    div_badge_text = participant_oi.get("divergence_badge", "⚖️ Balanced Positioning")
    div_delta = round(fii_ls - client_ls, 2)
    theta_label = "🟢 Favorable for Option Selling / Theta Capture" if theta_env == "FAVORABLE_FOR_OPTION_SELLING" else "🔥 Favorable for Option Buying / Delta Momentum"

    divergence_payload = {
        "status": div_status,
        "badge": div_badge_text,
        "trap_risk_score": div_trap_score,
        "trap_risk_label": div_trap_label,
        "trap_warning": div_warning,
        "warning": div_warning,
        "fii_ls": fii_ls,
        "client_ls": client_ls,
        "fii_ls_ratio": fii_ls,
        "client_ls_ratio": client_ls,
        "divergence_delta": div_delta,
    }

    return {
        "bias": bias_code,
        "bias_label": bias_badge,
        "bias_badge": bias_badge,
        "bias_color": bias_color,
        "confluence_score": total_confluence_score,
        "pillar_scores": {
            "derivatives_oi": round(score_p1_derivatives, 1),
            "cash_liquidity": round(score_p2_liquidity, 1),
            "volatility_vix": round(score_p3_volatility, 1),
            "market_breadth": round(score_p4_breadth, 1),
            "price_momentum": round(score_p5_momentum, 1),
        },
        "headline": headline,
        "nifty_spot": nifty_spot,
        "bank_spot": bank_spot,
        "vix_level": vix_level,
        "expected_1d_range_pct": expected_1d_move_pct,
        "expected_1d_range_pts": expected_1d_move_pts,
        "expected_1d_move_pct": expected_1d_move_pct,
        "expected_1d_move_pts": expected_1d_move_pts,
        "corridor": {
            "upper_band_1sigma": upper_band_1sigma,
            "lower_band_1sigma": lower_band_1sigma,
            "upper_band_2sigma": upper_band_2sigma,
            "lower_band_2sigma": lower_band_2sigma,
            "upper_1sigma": upper_band_1sigma,
            "lower_1sigma": lower_band_1sigma,
            "upper_2sigma": upper_band_2sigma,
            "lower_2sigma": lower_band_2sigma,
            "expected_1d_range_pct": expected_1d_move_pct,
            "expected_1d_range_pts": expected_1d_move_pts,
            "expected_1d_move_pct": expected_1d_move_pct,
            "expected_1d_move_pts": expected_1d_move_pts,
            "confidence_68pct": f"{lower_band_1sigma:,.0f} - {upper_band_1sigma:,.0f}",
            "confidence_95pct": f"{lower_band_2sigma:,.0f} - {upper_band_2sigma:,.0f}",
        },
        "divergence": divergence_payload,
        "smart_money_vs_retail": divergence_payload,
        "actionable_rules": [
            f"🎯 Primary Execution: {primary_action}",
            f"⚡ Options / Derivatives Tactic: {option_strategy}",
            f"🛑 Invalidation & Stop Rule: {invalidation}",
        ],
        "theta_decay_environment": theta_env,
        "theta_environment": theta_label,
        "theta_env_label": theta_label,
        "focus_sectors": focus_sectors,
    }
