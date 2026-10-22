"""Algorithmic Institutional Flow & Alert Generator for Derivatives.

Detects unusual open interest surges, wall shifts, aggressive put writing,
and key level breaks in real time.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any


def generate_derivatives_alerts(
    symbol: str,
    spot_price: float,
    call_wall: float | None,
    put_wall: float | None,
    max_pain: float | None,
    pcr_oi: float,
    oi_timeframes: dict[str, Any] | None,
    gamma_profile: dict[str, Any] | None,
    strikes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Generate timestamped institutional flow alerts and setup signals."""
    alerts: list[dict[str, Any]] = []
    now_str = datetime.now().strftime("%H:%M IST")

    tf = oi_timeframes or {}
    gp = gamma_profile or {}

    today = tf.get("today", {})
    tf_15m = tf.get("tf_15m", {})
    tf_5m = tf.get("tf_5m", {})

    # 1. 15m Writing Surge Alert
    p_15m = int(tf_15m.get("put_chg") or 0)
    c_15m = int(tf_15m.get("call_chg") or 0)

    if p_15m >= 75000 and (c_15m <= 0 or p_15m > c_15m * 1.5):
        alerts.append({
            "time": now_str,
            "level": "SUCCESS",
            "type": "PUT_WRITING_SURGE",
            "title": "Institutional Put Writing Surge (15m)",
            "text": f"Aggressive Put Writing detected (+{p_15m:,} contracts in 15m) locking support at Put Wall (₹{int(put_wall or spot_price):,}).",
        })
    elif c_15m >= 75000 and (p_15m <= 0 or c_15m > p_15m * 1.5):
        alerts.append({
            "time": now_str,
            "level": "WARNING",
            "type": "CALL_WRITING_SURGE",
            "title": "Institutional Call Writing Surge (15m)",
            "text": f"Heavy Call Writing detected (+{c_15m:,} contracts in 15m) cementing overhead ceiling at Call Wall (₹{int(call_wall or spot_price):,}).",
        })

    # 2. Strike-Specific Hot Writing Detection
    if strikes:
        def _get_chg(s: dict[str, Any], key_primary: str, key_fallback: str) -> int:
            return int(s.get(key_primary) if s.get(key_primary) is not None else (s.get(key_fallback) or 0))

        # Find strike with highest PE change and CE change
        max_pe_chg = max(strikes, key=lambda s: _get_chg(s, "pe_change_oi", "pe_chg_oi"))
        max_ce_chg = max(strikes, key=lambda s: _get_chg(s, "ce_change_oi", "ce_chg_oi"))

        pe_chg_val = _get_chg(max_pe_chg, "pe_change_oi", "pe_chg_oi")
        ce_chg_val = _get_chg(max_ce_chg, "ce_change_oi", "ce_chg_oi")

        if pe_chg_val > 10000:
            alerts.append({
                "time": now_str,
                "level": "INFO",
                "type": "STRIKE_PUT_BUILDUP",
                "title": f"Massive Put Accumulation @ ₹{int(max_pe_chg['strike']):,}",
                "text": f"+{pe_chg_val:,} contracts added today at ₹{int(max_pe_chg['strike']):,} PE. Institutional floor established.",
            })

        if ce_chg_val > 10000:
            alerts.append({
                "time": now_str,
                "level": "WARNING",
                "type": "STRIKE_CALL_BUILDUP",
                "title": f"Massive Call Accumulation @ ₹{int(max_ce_chg['strike']):,}",
                "text": f"+{ce_chg_val:,} contracts added today at ₹{int(max_ce_chg['strike']):,} CE. Institutional resistance established.",
            })

    # 3. PCR Floor / Ceiling Alert
    if pcr_oi >= 1.35:
        alerts.append({
            "time": now_str,
            "level": "SUCCESS",
            "type": "PCR_BULLISH_EXTREME",
            "title": f"Bullish Sentiment High (PCR {pcr_oi:.2f})",
            "text": f"Put-to-Call OI ratio is heavily skewed in favor of bulls ({pcr_oi:.2f}). Sellers heavily defending puts.",
        })
    elif pcr_oi <= 0.70:
        alerts.append({
            "time": now_str,
            "level": "DANGER",
            "type": "PCR_BEARISH_EXTREME",
            "title": f"Bearish Sentiment High (PCR {pcr_oi:.2f})",
            "text": f"Call writers heavily dominate the strike tree ({pcr_oi:.2f}). Rallies face heavy overhead distribution.",
        })

    # 4. Dealer Gamma Positioning
    gamma_regime = gp.get("gamma_regime") or gp.get("regime")
    flip = gp.get("gamma_flip_strike")
    if gamma_regime and "POSITIVE" in str(gamma_regime).upper():
        alerts.append({
            "time": now_str,
            "level": "INFO",
            "type": "GAMMA_VOL_DAMPENING",
            "title": "Positive Gamma Inventory",
            "text": f"Dealer gamma is positive. Mean-reversion expected toward Max Pain (₹{int(max_pain or spot_price):,}); volatility dampened.",
        })
    elif gamma_regime and "NEGATIVE" in str(gamma_regime).upper() and flip:
        alerts.append({
            "time": now_str,
            "level": "WARNING",
            "type": "GAMMA_VOL_ACCELERATION",
            "title": f"Negative Gamma Regime below ₹{int(flip):,}",
            "text": f"Dealers are net short gamma. High probability of violent breakout moves / gamma expansion.",
        })

    return alerts[:6]
