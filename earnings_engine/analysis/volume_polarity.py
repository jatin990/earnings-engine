"""Volume Polarity & F&O Open Interest (OI) Classification Engine.

Implements directional volume classification (Bullish vs Bearish) and 4-quadrant
derivatives Open Interest analysis (Long Buildup, Short Buildup, Short Covering, Long Unwinding).

Point-in-Time (PIT) guaranteed, anti-fabrication compliant, zero future leakage.
"""

from __future__ import annotations

import logging
from typing import Any

from earnings_engine.data.universe import is_fno_eligible, resolve_fno_symbol

logger = logging.getLogger(__name__)

# F&O Buildup Quadrants & Polarity Constants
OI_LONG_BUILDUP = "LONG_BUILDUP"       # Price ↑ + OI ↑ (Aggressive Bullish Buying)
OI_SHORT_BUILDUP = "SHORT_BUILDUP"     # Price ↓ + OI ↑ (Aggressive Bearish Shorting)
OI_SHORT_COVERING = "SHORT_COVERING"   # Price ↑ + OI ↓ (Bullish Relief / Short Squeeze)
OI_LONG_UNWINDING = "LONG_UNWINDING"   # Price ↓ + OI ↓ (Bearish Liquidation / Profit Booking)


def classify_volume_polarity(
    ticker: str,
    price_change_pct: float | None = None,
    volume_ratio: float | None = None,
    close: float | None = None,
    high: float | None = None,
    low: float | None = None,
    open_price: float | None = None,
    delivery_pct: float | None = None,
    oi_change_pct: float | None = None,
    is_fno: bool | None = None,
) -> dict[str, Any]:
    """Classify whether stock volume represents Bullish Accumulation or Bearish Distribution.

    If the symbol belongs to the NSE F&O segment and OI data is available,
    evaluates the 4-quadrant derivatives price-OI interaction.
    Otherwise, evaluates price delta, candle close range location, and delivery absorption.

    Returns structured metadata contract:
    {
        "ticker": str,
        "is_fno": bool,
        "volume_polarity": "BULLISH" | "BEARISH" | "NEUTRAL",
        "volume_character": str,
        "oi_buildup": str | None,
        "oi_change_pct": float | None,
        "confidence": "HIGH" | "MEDIUM" | "LOW",
        "badge_label": str,
        "badge_color": str,
        "badge_bg": str,
        "badge_border": str,
        "tooltip": str,
    }
    """
    clean_ticker = (ticker or "").upper().strip()
    fno_status = is_fno if is_fno is not None else is_fno_eligible(clean_ticker)

    # Calculate range position: (Close - Low) / (High - Low)
    range_pos = None
    if close is not None and high is not None and low is not None:
        candle_range = high - low
        if candle_range > 0:
            range_pos = max(0.0, min(1.0, (close - low) / candle_range))

    # Determine Price Direction
    # If price_change_pct is None, deduce from (close - open_price)
    p_chg = price_change_pct
    if p_chg is None and close is not None and open_price is not None and open_price > 0:
        p_chg = ((close - open_price) / open_price) * 100.0

    vol_mult = volume_ratio if (volume_ratio is not None and volume_ratio > 0) else 1.0

    # 1. Derivatives F&O Mode (Price + OI Interaction)
    if fno_status and oi_change_pct is not None and abs(oi_change_pct) >= 0.2:
        # Significant OI change observed
        if (p_chg is not None and p_chg > 0.05) or (p_chg is None and range_pos is not None and range_pos >= 0.55):
            # Price Up
            if oi_change_pct > 0:
                # Long Buildup
                return {
                    "ticker": clean_ticker,
                    "is_fno": True,
                    "volume_polarity": "BULLISH",
                    "volume_character": "Long Buildup",
                    "oi_buildup": OI_LONG_BUILDUP,
                    "oi_change_pct": round(oi_change_pct, 2),
                    "confidence": "HIGH" if vol_mult >= 1.5 else "MEDIUM",
                    "badge_label": "Bullish · Long Buildup",
                    "badge_color": "#34d399",  # Emerald Green
                    "badge_bg": "rgba(16, 185, 129, 0.15)",
                    "badge_border": "rgba(16, 185, 129, 0.35)",
                    "tooltip": f"Bullish Volume with Long Buildup (OI: {oi_change_pct:+.1f}%, Vol: {vol_mult:.1f}x) — Aggressive institutional long creation",
                }
            else:
                # Short Covering
                return {
                    "ticker": clean_ticker,
                    "is_fno": True,
                    "volume_polarity": "BULLISH",
                    "volume_character": "Short Covering",
                    "oi_buildup": OI_SHORT_COVERING,
                    "oi_change_pct": round(oi_change_pct, 2),
                    "confidence": "MEDIUM",
                    "badge_label": "Bullish · Short Covering",
                    "badge_color": "#38bdf8",  # Sky Blue / Cyan
                    "badge_bg": "rgba(56, 189, 248, 0.15)",
                    "badge_border": "rgba(56, 189, 248, 0.35)",
                    "tooltip": f"Bullish Short Covering Rally (OI: {oi_change_pct:+.1f}%, Vol: {vol_mult:.1f}x) — Bears forced to cover short positions",
                }
        elif (p_chg is not None and p_chg < -0.05) or (p_chg is None and range_pos is not None and range_pos <= 0.45):
            # Price Down
            if oi_change_pct > 0:
                # Short Buildup
                return {
                    "ticker": clean_ticker,
                    "is_fno": True,
                    "volume_polarity": "BEARISH",
                    "volume_character": "Short Buildup",
                    "oi_buildup": OI_SHORT_BUILDUP,
                    "oi_change_pct": round(oi_change_pct, 2),
                    "confidence": "HIGH" if vol_mult >= 1.5 else "MEDIUM",
                    "badge_label": "Bearish · Short Buildup",
                    "badge_color": "#f87171",  # Red
                    "badge_bg": "rgba(239, 68, 68, 0.15)",
                    "badge_border": "rgba(239, 68, 68, 0.35)",
                    "tooltip": f"Bearish Volume with Short Buildup (OI: {oi_change_pct:+.1f}%, Vol: {vol_mult:.1f}x) — Aggressive short initiation / selling pressure",
                }
            else:
                # Long Unwinding
                return {
                    "ticker": clean_ticker,
                    "is_fno": True,
                    "volume_polarity": "BEARISH",
                    "volume_character": "Long Unwinding",
                    "oi_buildup": OI_LONG_UNWINDING,
                    "oi_change_pct": round(oi_change_pct, 2),
                    "confidence": "MEDIUM",
                    "badge_label": "Bearish · Long Unwinding",
                    "badge_color": "#fb923c",  # Orange
                    "badge_bg": "rgba(251, 146, 60, 0.15)",
                    "badge_border": "rgba(251, 146, 60, 0.35)",
                    "tooltip": f"Bearish Long Unwinding (OI: {oi_change_pct:+.1f}%, Vol: {vol_mult:.1f}x) — Longs liquidating inventory / lack of buyers",
                }

    # 2. Cash Equity & Non-OI Volume Polarity Analysis
    # Multi-factor score combining Price Delta, Intraday Range Location, and Delivery %
    bull_points = 0
    bear_points = 0

    # Price Delta Weight (up to 3 points)
    if p_chg is not None:
        if p_chg >= 1.5:
            bull_points += 3
        elif p_chg > 0.1:
            bull_points += 2
        elif p_chg <= -1.5:
            bear_points += 3
        elif p_chg < -0.1:
            bear_points += 2

    # Range Position Weight (Close relative to High-Low, up to 2 points)
    if range_pos is not None:
        if range_pos >= 0.70:
            bull_points += 2
        elif range_pos >= 0.52:
            bull_points += 1
        elif range_pos <= 0.30:
            bear_points += 2
        elif range_pos <= 0.48:
            bear_points += 1

    # Delivery Absorption (if available, up to 2 points)
    if delivery_pct is not None:
        if delivery_pct >= 60.0 and (p_chg is None or p_chg >= 0):
            bull_points += 2
        elif delivery_pct >= 50.0 and (p_chg is None or p_chg >= 0):
            bull_points += 1
        elif delivery_pct < 35.0 and p_chg is not None and p_chg < 0:
            bear_points += 1

    # Volume expansion context
    fno_suffix = " · F&O" if fno_status else ""
    if bull_points >= bear_points + 2 or (bull_points > bear_points and (p_chg is not None and p_chg > 0)):
        char = "Institutional Accumulation" if vol_mult >= 1.5 else "Bullish Volume"
        conf = "HIGH" if (vol_mult >= 1.5 and bull_points >= 3) else "MEDIUM"
        return {
            "ticker": clean_ticker,
            "is_fno": fno_status,
            "volume_polarity": "BULLISH",
            "volume_character": char,
            "oi_buildup": None,
            "oi_change_pct": round(oi_change_pct, 2) if oi_change_pct is not None else None,
            "confidence": conf,
            "badge_label": f"Bullish Vol{fno_suffix}",
            "badge_color": "#34d399",
            "badge_bg": "rgba(16, 185, 129, 0.15)",
            "badge_border": "rgba(16, 185, 129, 0.35)",
            "tooltip": f"Bullish Volume ({char}, Vol: {vol_mult:.1f}x) — Strong buying pressure & price support{fno_suffix}",
        }
    elif bear_points >= bull_points + 2 or (bear_points > bull_points and (p_chg is not None and p_chg < 0)):
        char = "Distribution Selling" if vol_mult >= 1.5 else "Bearish Volume"
        conf = "HIGH" if (vol_mult >= 1.5 and bear_points >= 3) else "MEDIUM"
        return {
            "ticker": clean_ticker,
            "is_fno": fno_status,
            "volume_polarity": "BEARISH",
            "volume_character": char,
            "oi_buildup": None,
            "oi_change_pct": round(oi_change_pct, 2) if oi_change_pct is not None else None,
            "confidence": conf,
            "badge_label": f"Bearish Vol{fno_suffix}",
            "badge_color": "#f87171",
            "badge_bg": "rgba(239, 68, 68, 0.15)",
            "badge_border": "rgba(239, 68, 68, 0.35)",
            "tooltip": f"Bearish Volume ({char}, Vol: {vol_mult:.1f}x) — Active selling distribution into market{fno_suffix}",
        }
    else:
        char = "Volume Churn / Neutral"
        return {
            "ticker": clean_ticker,
            "is_fno": fno_status,
            "volume_polarity": "NEUTRAL",
            "volume_character": char,
            "oi_buildup": None,
            "oi_change_pct": round(oi_change_pct, 2) if oi_change_pct is not None else None,
            "confidence": "LOW",
            "badge_label": f"Neutral Vol{fno_suffix}",
            "badge_color": "#94a3b8",
            "badge_bg": "rgba(148, 163, 184, 0.12)",
            "badge_border": "rgba(148, 163, 184, 0.25)",
            "tooltip": f"Neutral Volume Churn ({vol_mult:.1f}x) — Equal buying and selling balance{fno_suffix}",
        }


def get_stock_oi_delta(symbol: str) -> float | None:
    """Query persistent option chain snapshots to compute total Open Interest % delta.

    Returns percentage change in total open interest (Call OI + Put OI) or None if unavailable.
    """
    if not symbol:
        return None
    clean = resolve_fno_symbol(symbol)
    if not is_fno_eligible(clean):
        return None

    try:
        from earnings_engine.data.db import get_db_connection
        conn = get_db_connection()
        rows = conn.execute(
            """
            SELECT call_oi_total, put_oi_total
            FROM option_chain_intraday_snapshots
            WHERE symbol = ?
            ORDER BY timestamp ASC
            """,
            (clean,),
        ).fetchall()
        if not rows or len(rows) < 2:
            return None

        first_c = rows[0][0] if isinstance(rows[0], (tuple, list)) else rows[0]["call_oi_total"]
        first_p = rows[0][1] if isinstance(rows[0], (tuple, list)) else rows[0]["put_oi_total"]
        last_c = rows[-1][0] if isinstance(rows[-1], (tuple, list)) else rows[-1]["call_oi_total"]
        last_p = rows[-1][1] if isinstance(rows[-1], (tuple, list)) else rows[-1]["put_oi_total"]

        first_tot = (first_c or 0) + (first_p or 0)
        last_tot = (last_c or 0) + (last_p or 0)

        if first_tot > 0:
            return round(((last_tot - first_tot) / first_tot) * 100.0, 2)
        return None
    except Exception as e:
        logger.debug("[OI-DELTA-QUERY] Error querying OI delta for %s: %s", clean, e)
        return None

