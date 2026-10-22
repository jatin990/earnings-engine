"""Educational glossary and metric benchmark reference definitions for Market Pulse."""

from __future__ import annotations

from typing import Any


def get_metric_glossary() -> dict[str, Any]:
    """Return educational knowledge base explaining Market Pulse metrics, formulas, and playbook rules."""
    return {
        "categories": [
            {
                "id": "participant_oi",
                "title": "Participant Derivatives OI & Long/Short Matrix",
                "description": "Exchange-reported end-of-day positioning across Foreign Institutions (FII), Domestic Funds (DII), Proprietary Desks (PRO), and Retail Clients across Index Futures, Stock Futures, and Index Options.",
                "metrics": [
                    {
                        "id": "net_contracts",
                        "name": "Net Contracts",
                        "formula": "Net Contracts = Total Long Contracts - Total Short Contracts",
                        "summary": "The absolute net directional exposure held by a participant category. Positive indicates net long bias; negative indicates net short hedge.",
                        "benchmarks": {
                            "bullish": "FII Net Contracts expanding > +50,000 contracts with positive day-over-day delta (Long Build-up).",
                            "bearish": "FII Net Contracts contracting < -50,000 contracts with aggressive short accumulation.",
                            "neutral": "Net contracts oscillating between -20,000 and +20,000 contracts.",
                        },
                        "next_day_playbook": "When FIIs hold deep negative contracts (< -80,000) but spot index stops falling, watch for an explosive short-covering squeeze. Avoid buying naked calls when FIIs are adding heavy short contracts.",
                        "trap_warning": "Do not look at Net Contracts in isolation without checking whether the position is in Index Futures (macro direction) or Options (hedges/volatility).",
                    },
                    {
                        "id": "long_short_ratio",
                        "name": "Long/Short Ratio (L/S Ratio)",
                        "formula": "Long/Short Ratio = Total Long Contracts / Total Short Contracts",
                        "summary": "Measures the proportional balance of bullish versus bearish positions for a participant group. Normalized around 1.00.",
                        "benchmarks": {
                            "overbought": "> 1.25 (Extreme Bullish Concentration - Vulnerable to Long Unwinding)",
                            "neutral": "0.90 to 1.15 (Equilibrium Range)",
                            "oversold": "< 0.85 (Heavy Short Positioning - Prime for Mean-Reversion Squeeze)",
                        },
                        "next_day_playbook": "If FII L/S Ratio drops below 0.70 while retail Client L/S Ratio climbs above 1.30, initiate contrarian bullish reversal setups on intraday breakout confirmation (fading retail panic).",
                        "trap_warning": "An oversold L/S ratio (<0.70) can remain oversold during severe bear markets. Wait for a positive 1-day delta shift before taking counter-trend longs.",
                    },
                    {
                        "id": "oi_delta_regimes",
                        "name": "Open Interest Delta (ΔOI) & 4 Market Regimes",
                        "formula": "ΔOI = Today OI - Yesterday OI (Combined with Price Direction ΔPrice)",
                        "summary": "Classifies participant positioning shifts into 4 institutional execution regimes based on price and volume-OI dynamics.",
                        "benchmarks": {
                            "long_buildup": "Price ↑ + OI ↑ : Fresh aggressive long accumulation. Trend continuation favored.",
                            "short_covering": "Price ↑ + OI ↓ : Bears forced to close shorts. Rapid upward move, often unsustainable without fresh longs.",
                            "short_buildup": "Price ↓ + OI ↑ : Active institutional shorting / hedging. Overhead resistance is strong.",
                            "long_unwinding": "Price ↓ + OI ↓ : Longs taking profit or cutting losses. Lack of buyers; support levels soften.",
                        },
                        "next_day_playbook": "On Long Build-up days, buy opening pullbacks to 15-min VWAP. On Short Build-up days, sell call credit spreads on intraday gap-ups into resistance.",
                        "trap_warning": "Short covering rallies often reverse sharply once the trapped bears have finished exiting. Always check if fresh long build-up follows.",
                    },
                    {
                        "id": "smart_vs_retail_divergence",
                        "name": "Smart Money vs. Retail Contrarian Divergence",
                        "formula": "Smart Money (FII + PRO Net) vs. Retail (CLIENT Net)",
                        "summary": "Institutional desks (FII + Proprietary) consistently dominate retail clients over multi-week horizons. High divergence reveals contrarian trap setups.",
                        "benchmarks": {
                            "bear_trap_risk": "Smart Money is Net Short while Retail is Net Long (Gap-ups are high probability sell-offs).",
                            "short_squeeze_expansion": "Smart Money is Net Long while Retail is Net Short (Pullbacks are aggressive buy zones).",
                            "balanced": "Both cohorts hold balanced or aligned inventory.",
                        },
                        "next_day_playbook": "When Bear Trap Risk is active (Score > 75), sell naked call options or buy put spreads when index tests the +1-Sigma upper volatility corridor in the first 30 minutes.",
                        "trap_warning": "Do not trade contrarian signals blindly against strong global macroeconomic momentum shocks.",
                    },
                ],
            },
            {
                "id": "volatility_vix",
                "title": "India VIX & 1-Day Volatility Corridor",
                "description": "Annualized implied volatility derived from Nifty out-of-the-money option prices, transformed into statistical daily trading boundaries.",
                "metrics": [
                    {
                        "id": "vix_level",
                        "name": "India VIX Level & Regimes",
                        "formula": "Annualized 30-Day Implied Volatility % of Nifty Options",
                        "summary": "Measures market expectations of near-term volatility and perceived risk/fear among market participants.",
                        "benchmarks": {
                            "complacent": "< 12.0 (Low Volatility, Grind-up Environment, Mean Reversion)",
                            "normal": "12.0 to 16.0 (Healthy Trending Environment)",
                            "elevated": "16.0 to 22.0 (High Risk, Sharp Swings, Wide Ranges)",
                            "panic": "> 22.0 (Market Panic / Crash Conditions)",
                        },
                        "next_day_playbook": "When VIX < 13.0, option sellers have strong statistical edge using Iron Condors and Credit Spreads. When VIX spikes > 18.0, switch to Debit Spreads and reduce intraday position sizing by 50%.",
                        "trap_warning": "Very low VIX (<11.0) is not purely bullish—it often precedes explosive volatility breakouts (volatility compression leads to expansion).",
                    },
                    {
                        "id": "expected_1d_corridor",
                        "name": "1-Day Expected Move Corridor (1-Sigma & 2-Sigma)",
                        "formula": "Daily Implied Volatility = VIX / sqrt(252) ~= VIX / 15.8745 | Expected Points = Spot * Daily Vol %",
                        "summary": "Calculates the statistically expected daily trading range for Nifty with 68.2% (1-Sigma) and 95.4% (2-Sigma) confidence intervals.",
                        "benchmarks": {
                            "1_sigma_boundary": "68.2% Probability Range (Upper Resistance / Lower Support)",
                            "2_sigma_boundary": "95.4% Probability Range (Exhaustion Points / Capitulation Reversal Zones)",
                        },
                        "next_day_playbook": "If Nifty opens near the +1-Sigma upper band and stalls with bearish divergence, initiate short hedges targeting VWAP. If price touches the -2-Sigma lower band, look for capitulation hammer candles for mean-reversion bounces.",
                        "trap_warning": "During major earnings seasons or geopolitical events, 1-day moves can exceed 2-Sigma boundaries.",
                    },
                ],
            },
            {
                "id": "institutional_liquidity",
                "title": "Institutional Cash Net Liquidity (FII / DII)",
                "description": "Daily and cumulative net cash market buy/sell values reported by NSE/BSE for Foreign Institutional Investors (FII) and Domestic Institutional Investors (DII).",
                "metrics": [
                    {
                        "id": "fii_dii_cash",
                        "name": "Daily & 7D Net Cash Flows (₹ Crores)",
                        "formula": "Net Flow = Total Buy Value (Cr) - Total Sell Value (Cr)",
                        "summary": "Direct measurement of pure equity delivery buying or liquidations. DII flows represent systematic SIP inflows; FII flows represent global macro allocation.",
                        "benchmarks": {
                            "strong_inflow": "Combined Net > +₹2,000 Cr with FII positive (High institutional demand).",
                            "absorption": "FII Selling absorbed by DII Buying of equal or greater magnitude (Range-bound market).",
                            "liquidation": "FII Selling > -₹3,000 Cr with negative DII participation (Broad market vulnerability).",
                        },
                        "next_day_playbook": "Consistent 3-day positive FII cash accumulation is the strongest precursor to sustained large-cap outperformance. Align stock picks with sectors seeing top institutional delivery.",
                        "trap_warning": "Single-day block deals or rebalancing dates (MSCI/FTSE) can distort 1-day cash flow figures. Always verify 7-day cumulative trend.",
                    },
                ],
            },
            {
                "id": "market_breadth",
                "title": "Market Breadth & Technical Participation",
                "description": "Internal health metrics evaluating participation across the active equity universe.",
                "metrics": [
                    {
                        "id": "dma_breadth",
                        "name": "% Stocks Above 20-DMA & 50-DMA",
                        "formula": "(Number of Universe Stocks > DMA / Total Universe Stocks) * 100%",
                        "summary": "Measures whether market moves are broad-based or driven by a handful of heavyweights.",
                        "benchmarks": {
                            "healthy_expansion": "> 65% of stocks above 20-DMA and 50-DMA.",
                            "divergence_warning": "Index making new highs while % stocks above 20-DMA drops below 45% (Breadth Divergence).",
                            "oversold_reversal": "< 25% of stocks above 20-DMA (Climactic selling nearing exhaustion).",
                        },
                        "next_day_playbook": "When 20-DMA breadth is < 20% and begins ticking upward, initiate swing long positions in high-relative-strength breakout setups.",
                        "trap_warning": "A high index value with weak breadth is a fragile rally prone to sudden sharp corrections.",
                    },
                    {
                        "id": "advance_decline",
                        "name": "Advance / Decline Ratio (A/D Ratio)",
                        "formula": "Advancing Stocks / Declining Stocks",
                        "summary": "Daily ratio of advancing equities to declining equities across the active exchange universe.",
                        "benchmarks": {
                            "breadth_thrust": "> 2.0 (Dominant buying across midcaps and smallcaps).",
                            "neutral": "0.8 to 1.2 (Selective stock picking).",
                            "distribution": "< 0.5 (Widespread selling pressure).",
                        },
                        "next_day_playbook": "If Nifty is flat but A/D ratio is > 2.5, look for high-momentum breakout trades in mid-cap and small-cap leaders.",
                        "trap_warning": "A high A/D ratio on very low volume is often a retail trap.",
                    },
                ],
            },
            {
                "id": "fear_greed",
                "title": "Fear & Greed Index (0 - 100)",
                "description": "Multi-factor composite sentiment model synthesizing Volatility (40%), Momentum (40%), Breadth (10%), and Safe-Haven Demand (10%).",
                "metrics": [
                    {
                        "id": "fg_score",
                        "name": "Fear & Greed Composite Score",
                        "formula": "Weighted Composite (VIX Factor * 0.40 + Momentum * 0.40 + Breadth * 0.10 + SafeHaven * 0.10)",
                        "summary": "Quantifies overall market emotion from Extreme Fear (0) to Extreme Greed (100).",
                        "benchmarks": {
                            "extreme_fear": "0 to 25 (Extreme Pessimism - High reward-to-risk for medium-term accumulation).",
                            "fear": "26 to 45 (Defensive Sentiment).",
                            "neutral": "46 to 55 (Market Equilibrium).",
                            "greed": "56 to 75 (Bullish Optimism).",
                            "extreme_greed": "76 to 100 (Complacency / Euphoria - Tighten stops, avoid FOMO).",
                        },
                        "next_day_playbook": "Extreme Greed (>80) indicates market is vulnerable to unexpected negative catalysts. Extreme Fear (<20) coupled with FII short covering creates explosive upside reversal setups.",
                        "trap_warning": "Extreme Greed can persist for weeks during powerful bull market legs; do not short solely because sentiment is in Greed territory.",
                    },
                ],
            },
        ],
    }
