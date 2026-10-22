"""Institutional Option Writing Velocity & Rolling OI Snapshot Cache.

Tracks rolling multi-timeframe Open Interest (Today, 15m velocity, 5m burst)
and classifies institutional writing flow (Put Writing vs Call Writing).
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

# Rolling Open Interest & Writing Velocity Cache: symbol -> list of dict snapshots
# Each snapshot: {"timestamp": float, "call_oi": int, "put_oi": int, "strikes": dict}
_OI_SNAPSHOT_CACHE: dict[str, list[dict[str, Any]]] = {}
_MAX_OI_SNAPSHOTS = 120  # Keep up to 2 hours of snapshots


def track_oi_snapshot(
    symbol: str,
    total_call_oi: int,
    total_put_oi: int,
    strikes: list[dict[str, Any]],
) -> None:
    """Store timestamped snapshot into the in-memory rolling ring buffer."""
    clean_sym = symbol.strip().upper().replace(".NS", "")
    now = time.time()

    strike_map = {}
    for s in strikes or []:
        stk = float(s.get("strike", 0.0))
        if stk > 0:
            strike_map[stk] = {
                "ce_oi": int(s.get("ce_oi") or 0),
                "pe_oi": int(s.get("pe_oi") or 0),
                "ce_chg": int(s.get("ce_change_oi") or 0),
                "pe_chg": int(s.get("pe_change_oi") or 0),
            }

    if clean_sym not in _OI_SNAPSHOT_CACHE:
        _OI_SNAPSHOT_CACHE[clean_sym] = []

    history = _OI_SNAPSHOT_CACHE[clean_sym]
    # Deduplicate if called within 5 seconds
    if history and (now - history[-1]["timestamp"]) < 5.0:
        history[-1] = {
            "timestamp": now,
            "call_oi": total_call_oi,
            "put_oi": total_put_oi,
            "strikes": strike_map,
        }
    else:
        history.append({
            "timestamp": now,
            "call_oi": total_call_oi,
            "put_oi": total_put_oi,
            "strikes": strike_map,
        })

    # Trim to max window
    if len(history) > _MAX_OI_SNAPSHOTS:
        _OI_SNAPSHOT_CACHE[clean_sym] = history[-_MAX_OI_SNAPSHOTS:]


def _classify_writing_sentiment(call_delta: int, put_delta: int) -> tuple[str, str, str]:
    """Classify writing flow into institutional sentiment, status badge, and theme color."""
    tot_abs = abs(call_delta) + abs(put_delta)
    if tot_abs == 0:
        return "NEUTRAL", "BALANCED", "amber"

    # Put Writing Dominance (Bullish floor defense)
    if put_delta > 0 and (call_delta <= 0 or put_delta >= call_delta * 1.25):
        ratio = round(put_delta / max(call_delta, 1), 1) if call_delta > 0 else 2.5
        return "PUT WRITING", f"PUT WRITING ({ratio}x)", "emerald"

    # Call Writing Dominance (Bearish ceiling cap)
    if call_delta > 0 and (put_delta <= 0 or call_delta >= put_delta * 1.25):
        ratio = round(call_delta / max(put_delta, 1), 1) if put_delta > 0 else 2.5
        return "CALL WRITING", f"CALL WRITING ({ratio}x)", "rose"

    # Both unwinding (Short covering or long liquidation)
    if call_delta < 0 and put_delta < 0:
        if abs(call_delta) > abs(put_delta):
            return "SHORT COVERING", "CE UNWINDING", "sky"
        else:
            return "LONG UNWINDING", "PE UNWINDING", "rose"

    # Balanced two-way positioning
    return "BALANCED", "TWO-WAY FLOW", "amber"


def derive_multi_timeframe_oi(
    symbol: str,
    current_call_oi: int,
    current_put_oi: int,
    strikes: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compute multi-timeframe Call vs Put Open Interest metrics across Today, 15m, and 5m."""
    clean_sym = symbol.strip().upper().replace(".NS", "")
    now = time.time()

    # Track current snapshot
    track_oi_snapshot(clean_sym, current_call_oi, current_put_oi, strikes)
    history = _OI_SNAPSHOT_CACHE.get(clean_sym, [])

    # 1. Today (Full Session) Intraday Aggregation
    today_ce_chg = sum(int(s.get("ce_change_oi") or 0) for s in strikes)
    today_pe_chg = sum(int(s.get("pe_change_oi") or 0) for s in strikes)

    tot_today_oi = max(current_call_oi + current_put_oi, 1)
    today_call_pct = round((current_call_oi / tot_today_oi) * 100, 1)
    today_put_pct = round((current_put_oi / tot_today_oi) * 100, 1)

    today_sent, today_badge, today_theme = _classify_writing_sentiment(today_ce_chg, today_pe_chg)

    today_metric = {
        "call_oi": current_call_oi,
        "put_oi": current_put_oi,
        "call_pct": today_call_pct,
        "put_pct": today_put_pct,
        "call_chg": today_ce_chg,
        "put_chg": today_pe_chg,
        "sentiment": today_sent,
        "badge": today_badge,
        "theme": today_theme,
    }

    # Helper to calculate delta from target seconds ago
    def _get_rolling_delta(target_sec_ago: float) -> tuple[int, int]:
        if len(history) < 2:
            # Fallback estimation proportional to intraday rate if only single snapshot
            factor = min(target_sec_ago / 22500.0, 1.0)  # ~375 min session
            return int(today_ce_chg * factor), int(today_pe_chg * factor)

        target_time = now - target_sec_ago
        # Find closest snapshot at or before target_time
        base_snap = history[0]
        for snap in history:
            if snap["timestamp"] <= target_time:
                base_snap = snap
            else:
                break

        curr_snap = history[-1]
        c_delta = curr_snap["call_oi"] - base_snap["call_oi"]
        p_delta = curr_snap["put_oi"] - base_snap["put_oi"]

        # If zero elapsed time delta recorded yet, fall back to proportional fraction
        if c_delta == 0 and p_delta == 0 and len(history) <= 3:
            factor = min(target_sec_ago / 22500.0, 1.0)
            return int(today_ce_chg * factor), int(today_pe_chg * factor)

        return c_delta, p_delta

    # 2. 15-Minute Velocity (900 seconds)
    c_15m, p_15m = _get_rolling_delta(900.0)
    abs_15m = max(abs(c_15m) + abs(p_15m), 1)
    sent_15m, badge_15m, theme_15m = _classify_writing_sentiment(c_15m, p_15m)

    tf_15m = {
        "call_chg": c_15m,
        "put_chg": p_15m,
        "call_pct": round((abs(c_15m) / abs_15m) * 100, 1) if abs_15m > 0 else 50.0,
        "put_pct": round((abs(p_15m) / abs_15m) * 100, 1) if abs_15m > 0 else 50.0,
        "sentiment": sent_15m,
        "badge": badge_15m,
        "theme": theme_15m,
    }

    # 3. 5-Minute Burst (300 seconds)
    c_5m, p_5m = _get_rolling_delta(300.0)
    abs_5m = max(abs(c_5m) + abs(p_5m), 1)
    sent_5m, badge_5m, theme_5m = _classify_writing_sentiment(c_5m, p_5m)

    tf_5m = {
        "call_chg": c_5m,
        "put_chg": p_5m,
        "call_pct": round((abs(c_5m) / abs_5m) * 100, 1) if abs_5m > 0 else 50.0,
        "put_pct": round((abs(p_5m) / abs_5m) * 100, 1) if abs_5m > 0 else 50.0,
        "sentiment": sent_5m,
        "badge": badge_5m,
        "theme": theme_5m,
    }

    return {
        "today": today_metric,
        "tf_15m": tf_15m,
        "tf_5m": tf_5m,
    }
