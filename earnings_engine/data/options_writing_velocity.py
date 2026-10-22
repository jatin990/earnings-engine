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


def _fmt_indian_qty(num: int | float) -> str:
    """Format quantity into Indian Cr, L, or k."""
    n = abs(num)
    sign = "+" if num > 0 else ("-" if num < 0 else "")
    if n >= 10000000:
        return f"{sign}{n / 10000000:.2f} Cr"
    if n >= 100000:
        return f"{sign}{n / 100000:.2f} L"
    if n >= 1000:
        return f"{sign}{n / 1000:.1f} k"
    return f"{sign}{int(n)}"


def derive_multi_timeframe_oi(
    symbol: str,
    current_call_oi: int,
    current_put_oi: int,
    strikes: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compute multi-timeframe Call vs Put Open Interest metrics across Today, 15m, and 5m."""
    clean_sym = symbol.strip().upper().replace(".NS", "")
    now = time.time()
    now_time = datetime.now().strftime("%H:%M")

    # Track current snapshot
    track_oi_snapshot(clean_sym, current_call_oi, current_put_oi, strikes)
    history = _OI_SNAPSHOT_CACHE.get(clean_sym, [])

    # 1. Total Positions (Two Bars: Calls vs Puts)
    tot_oi = max(current_call_oi + current_put_oi, 1)
    tot_call_pct = round((current_call_oi / tot_oi) * 100, 1)
    tot_put_pct = round((current_put_oi / tot_oi) * 100, 1)

    total_positions = {
        "call_oi": current_call_oi,
        "put_oi": current_put_oi,
        "call_pct": tot_call_pct,
        "put_pct": tot_put_pct,
        "call_oi_formatted": _fmt_indian_qty(current_call_oi).lstrip("+"),
        "put_oi_formatted": _fmt_indian_qty(current_put_oi).lstrip("+"),
    }

    # 2. Today (Full Session) Intraday Aggregation
    today_ce_chg = sum(int(s.get("ce_change_oi") or 0) for s in strikes)
    today_pe_chg = sum(int(s.get("pe_change_oi") or 0) for s in strikes)

    call_base_today = max(current_call_oi - today_ce_chg, 1)
    put_base_today = max(current_put_oi - today_pe_chg, 1)
    call_today_pct_chg = round((today_ce_chg / call_base_today) * 100, 1)
    put_today_pct_chg = round((today_pe_chg / put_base_today) * 100, 1)

    today_sent, today_badge, today_theme = _classify_writing_sentiment(today_ce_chg, today_pe_chg)

    today_metric = {
        "call_oi": current_call_oi,
        "put_oi": current_put_oi,
        "call_pct": tot_call_pct,
        "put_pct": tot_put_pct,
        "call_chg": today_ce_chg,
        "put_chg": today_pe_chg,
        "call_pct_chg": call_today_pct_chg,
        "put_pct_chg": put_today_pct_chg,
        "sentiment": today_sent,
        "badge": today_badge,
        "theme": today_theme,
    }

    # Helper to calculate delta from target seconds ago and extract base snapshot
    def _get_rolling_snapshot(target_sec_ago: float) -> tuple[int, int, dict[str, Any] | None]:
        if len(history) < 2:
            factor = min(target_sec_ago / 22500.0, 1.0)
            return int(today_ce_chg * factor), int(today_pe_chg * factor), None

        target_time = now - target_sec_ago
        base_snap = history[0]
        for snap in history:
            if snap["timestamp"] <= target_time:
                base_snap = snap
            else:
                break

        curr_snap = history[-1]
        c_delta = curr_snap["call_oi"] - base_snap["call_oi"]
        p_delta = curr_snap["put_oi"] - base_snap["put_oi"]

        if c_delta == 0 and p_delta == 0 and len(history) <= 3:
            factor = min(target_sec_ago / 22500.0, 1.0)
            return int(today_ce_chg * factor), int(today_pe_chg * factor), base_snap

        return c_delta, p_delta, base_snap

    # 3. 15-Minute Velocity (900 seconds)
    c_15m, p_15m, snap_15m = _get_rolling_snapshot(900.0)
    abs_15m = max(abs(c_15m) + abs(p_15m), 1)
    sent_15m, badge_15m, theme_15m = _classify_writing_sentiment(c_15m, p_15m)

    call_base_15m = max(current_call_oi - c_15m, 1)
    put_base_15m = max(current_put_oi - p_15m, 1)
    call_15m_pct_chg = round((c_15m / call_base_15m) * 100, 1)
    put_15m_pct_chg = round((p_15m / put_base_15m) * 100, 1)

    tf_15m = {
        "call_chg": c_15m,
        "put_chg": p_15m,
        "call_pct_chg": call_15m_pct_chg,
        "put_pct_chg": put_15m_pct_chg,
        "call_pct": round((abs(c_15m) / abs_15m) * 100, 1) if abs_15m > 0 else 50.0,
        "put_pct": round((abs(p_15m) / abs_15m) * 100, 1) if abs_15m > 0 else 50.0,
        "sentiment": sent_15m,
        "badge": badge_15m,
        "theme": theme_15m,
    }

    # 4. 5-Minute Burst (300 seconds)
    c_5m, p_5m, snap_5m = _get_rolling_snapshot(300.0)
    abs_5m = max(abs(c_5m) + abs(p_5m), 1)
    sent_5m, badge_5m, theme_5m = _classify_writing_sentiment(c_5m, p_5m)

    call_base_5m = max(current_call_oi - c_5m, 1)
    put_base_5m = max(current_put_oi - p_5m, 1)
    call_5m_pct_chg = round((c_5m / call_base_5m) * 100, 1)
    put_5m_pct_chg = round((p_5m / put_base_5m) * 100, 1)

    tf_5m = {
        "call_chg": c_5m,
        "put_chg": p_5m,
        "call_pct_chg": call_5m_pct_chg,
        "put_pct_chg": put_5m_pct_chg,
        "call_pct": round((abs(c_5m) / abs_5m) * 100, 1) if abs_5m > 0 else 50.0,
        "put_pct": round((abs(p_5m) / abs_5m) * 100, 1) if abs_5m > 0 else 50.0,
        "sentiment": sent_5m,
        "badge": badge_5m,
        "theme": theme_5m,
    }

    # 5. Enrich strikes with strike-level 15m change
    base_strikes_15m = snap_15m.get("strikes", {}) if snap_15m else {}
    for s in strikes:
        stk = float(s.get("strike", 0.0))
        if stk in base_strikes_15m:
            s["ce_change_15m"] = int(s.get("ce_oi", 0) or 0) - int(base_strikes_15m[stk].get("ce_oi", 0) or 0)
            s["pe_change_15m"] = int(s.get("pe_oi", 0) or 0) - int(base_strikes_15m[stk].get("pe_oi", 0) or 0)
        else:
            # Fallback: ~4% (15m/375m) of session change
            s["ce_change_15m"] = int((int(s.get("ce_change_oi", 0) or 0)) * (15.0 / 375.0))
            s["pe_change_15m"] = int((int(s.get("pe_change_oi", 0) or 0)) * (15.0 / 375.0))

    # 6. PCR (OI) & 15m Delta
    curr_pcr = round(current_put_oi / max(current_call_oi, 1), 2)
    if snap_15m and snap_15m.get("call_oi", 0) > 0:
        base_pcr = round(snap_15m["put_oi"] / max(snap_15m["call_oi"], 1), 2)
        pcr_15m_delta = round(curr_pcr - base_pcr, 2)
    else:
        pcr_15m_delta = 0.0

    # 7. Identify hot strike and form dynamic institutional summary alert
    lead_ce = max(strikes, key=lambda s: int(s.get("ce_change_15m") or 0), default=None) if strikes else None
    lead_pe = max(strikes, key=lambda s: int(s.get("pe_change_15m") or 0), default=None) if strikes else None

    if sent_15m == "CALL WRITING" or (c_15m > p_15m and c_15m > 0):
        lead_stk = int(lead_ce["strike"]) if lead_ce else 0
        lead_chg = int(lead_ce.get("ce_change_15m") or 0) if lead_ce else 0
        chg_str = f"+{call_15m_pct_chg:.1f}%" if call_15m_pct_chg >= 0 else f"{call_15m_pct_chg:.1f}%"
        alert_text = (
            f"{now_time} {clean_sym} Call OI {chg_str} in 15 min: {_fmt_indian_qty(c_15m)} contracts, "
            f"most at {lead_stk:,} CE ({_fmt_indian_qty(lead_chg)}): Call writing, a bearish lean, PCR {curr_pcr:.2f}"
        )
        alert_bias = "BEARISH"
    elif sent_15m == "PUT WRITING" or (p_15m > c_15m and p_15m > 0):
        lead_stk = int(lead_pe["strike"]) if lead_pe else 0
        lead_chg = int(lead_pe.get("pe_change_15m") or 0) if lead_pe else 0
        chg_str = f"+{put_15m_pct_chg:.1f}%" if put_15m_pct_chg >= 0 else f"{put_15m_pct_chg:.1f}%"
        alert_text = (
            f"{now_time} {clean_sym} Put OI {chg_str} in 15 min: {_fmt_indian_qty(p_15m)} contracts, "
            f"most at {lead_stk:,} PE ({_fmt_indian_qty(lead_chg)}): Put writing, a bullish lean, PCR {curr_pcr:.2f}"
        )
        alert_bias = "BULLISH"
    else:
        alert_text = (
            f"{now_time} {clean_sym} OI balanced in 15 min: CE {_fmt_indian_qty(c_15m)}, "
            f"PE {_fmt_indian_qty(p_15m)}, two-way positioning, PCR {curr_pcr:.2f}"
        )
        alert_bias = "NEUTRAL"

    summary_alert = {
        "time": now_time,
        "text": alert_text,
        "bias": alert_bias,
        "pcr_oi": curr_pcr,
        "pcr_15m_delta": pcr_15m_delta,
    }

    return {
        "total_positions": total_positions,
        "today": today_metric,
        "tf_15m": tf_15m,
        "tf_5m": tf_5m,
        "summary_alert": summary_alert,
    }
