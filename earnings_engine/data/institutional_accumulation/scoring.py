"""Scoring algorithms and tier evaluation for Institutional Accumulation."""

from __future__ import annotations

import math


def calculate_institutional_score(
    accumulating_count: int = 0,
    selling_count: int = 0,
    new_buys_count: int = 0,
    net_flow_cr: float = 0.0,
    gross_inflow_cr: float = 0.0,
    gross_outflow_cr: float = 0.0,
    inst_addition_pct: float = 0.0,
    increase_amount_cr: float = 0.0,
    total_inst_amount_cr: float = 0.0,
    *,
    block_deals_net_cr: float = 0.0,
    block_deals_count: int = 0,
    super_investor_count: int = 0,
    super_investor_cr: float = 0.0,
    marquee_amc_count: int = 0,
    marquee_amc_cr: float = 0.0,
    whale_capital_cr: float = 0.0,
) -> tuple[float, str, str]:
    """
    Calculate institutional conviction score (0-100), verdict, and badge.
    Operates across three distinct quantitative tiers:
      Tier 1: Aggregate Macro Flow (100% corporate supply absorption from BSE/NSE shareholding delta and Rupee flow).
      Tier 2: Granular Filing Stream & Block Deals (fund breadth and exchange block deal net capital).
      Tier 3: Whale / Smart Money Conviction (asymmetric conviction booster from Super Investors and Marquee AMCs).
    """
    score = 50.0

    # -------------------------------------------------------------
    # Tier 1: Aggregate Macro Flow (up to +/- 30 points)
    # Measures corporate supply absorption into institutional custody
    # -------------------------------------------------------------
    # 1A: Stake Shift Percentage (inst_addition_pct from shareholding patterns, up to +/- 15 pts)
    if inst_addition_pct > 0:
        score += min(15.0, inst_addition_pct * 4.0)
    elif inst_addition_pct < 0:
        score -= min(15.0, abs(inst_addition_pct) * 4.0)

    # 1B: Macro Rupee Supply Absorption (up to +/- 15 pts)
    macro_flow = increase_amount_cr if increase_amount_cr != 0 else net_flow_cr
    if macro_flow > 0:
        score += min(15.0, math.log10(max(1.0, macro_flow)) * 4.0)
    elif macro_flow < 0:
        score -= min(15.0, math.log10(max(1.0, abs(macro_flow))) * 4.0)

    # -------------------------------------------------------------
    # Tier 2: Granular Filing Stream & Block Deals (up to +/- 25 points)
    # Confirmation across AMFI disclosures and real-time exchange deals
    # -------------------------------------------------------------
    # 2A: Fund Breadth (up to +/- 15 pts)
    if accumulating_count > selling_count:
        score += min(15.0, (accumulating_count - selling_count) * 2.5 + new_buys_count * 2.0)
    elif selling_count > accumulating_count:
        score -= min(15.0, (selling_count - accumulating_count) * 2.5)

    # 2B: Block Deal Net Capital & Velocity (up to +/- 10 pts)
    if block_deals_net_cr > 0:
        blk_boost = math.log10(max(1.0, block_deals_net_cr)) * 3.0 + min(2.0, block_deals_count * 0.5)
        score += min(10.0, blk_boost)
    elif block_deals_net_cr < 0:
        blk_drag = math.log10(max(1.0, abs(block_deals_net_cr))) * 3.0
        score -= min(10.0, blk_drag)

    # -------------------------------------------------------------
    # Tier 3: Whale / Smart Money Conviction (up to +15 points booster)
    # Asymmetric conviction booster activated by Marquee AMCs and Whales
    # -------------------------------------------------------------
    whale_boost = 0.0
    if super_investor_count > 0:
        whale_boost += min(8.0, super_investor_count * 4.0)
    if marquee_amc_count > 0:
        whale_boost += min(6.0, marquee_amc_count * 2.0)
    if whale_capital_cr >= 100.0:
        whale_boost += 3.0
    elif whale_capital_cr >= 25.0:
        whale_boost += 1.5
    score += min(15.0, whale_boost)

    # -------------------------------------------------------------
    # Institutional Scale & Depth Component (up to +5 points)
    # -------------------------------------------------------------
    if total_inst_amount_cr and total_inst_amount_cr > 500.0:
        score += min(5.0, math.log10(total_inst_amount_cr / 500.0) * 2.5)

    score = max(5.0, min(98.0, round(score, 1)))

    if score >= 75.0:
        verdict = "🔥 Aggressive Institutional Accumulation"
        verdict_badge = "emerald"
    elif score >= 58.0:
        verdict = "🟢 Moderate Institutional Accumulation"
        verdict_badge = "green"
    elif score >= 42.0:
        verdict = "⚖️ Stable Institutional Allocation"
        verdict_badge = "amber"
    else:
        verdict = "🔴 Institutional Distribution / Trimming"
        verdict_badge = "rose"

    return score, verdict, verdict_badge


def _classify_market_cap(market_cap_cr: float | None) -> str:
    """Classify market cap in Crores into Large, Mid, Small, or Micro cap."""
    if not market_cap_cr or market_cap_cr <= 0:
        return "Unknown"
    if market_cap_cr >= 20000:
        return "Large Cap"
    elif market_cap_cr >= 5000:
        return "Mid Cap"
    elif market_cap_cr >= 1000:
        return "Small Cap"
    return "Micro Cap"
