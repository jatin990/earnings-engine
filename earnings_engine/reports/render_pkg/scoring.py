"""4-pillar quantitative Action/Buy Indicator (0-100 scale)."""

from __future__ import annotations

import html
from typing import Any
import pandas as pd


def _safe_float(v: object, default: float | None = None) -> float | None:
    """Safely convert a value to float, handling percentage strings, commas, or None."""
    if v is None or pd.isna(v):
        return default
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().rstrip("%").replace(",", "")
    try:
        return float(s)
    except ValueError:
        return default


def compute_buy_indicator(row: pd.Series | dict[str, Any], consensus_pred: dict[str, Any] | None = None) -> dict[str, Any]:
    """Compute 4-pillar quantitative Action/Buy Indicator (0-100 scale).

    Pillars:
      1. Technical Setup & S/R Channel Structure (30 pts)
      2. Earnings Track Record & Consistency (25 pts)
      3. Momentum & Volume Expansion (25 pts)
      4. Predictive AI & Quant Edge (20 pts, with dynamic 80-to-100 rescale when uncalculated)

    Signals:
      - STRONG BUY:  Score >= 75
      - BUY:         Score 60 - 74
      - ACCUMULATE:  Score 48 - 59
      - NEUTRAL:     Score 35 - 47
      - AVOID:       Score < 35
    """
    def _get(key: str, default: Any = None) -> Any:
        if isinstance(row, dict):
            return row.get(key, default)
        if isinstance(row, pd.Series):
            if key in row.index and not pd.isna(row.get(key)):
                return row.get(key)
        return default

    # ==========================================
    # Pillar 1: Technical & S/R Structure (30 pts)
    # ==========================================
    chan_pos = _safe_float(_get("channel_position_pct"))
    if chan_pos is not None:
        chan_pos = max(0.0, min(100.0, chan_pos))
        if chan_pos <= 35.0:
            p1_channel = 15.0
        elif chan_pos <= 65.0:
            p1_channel = 10.0
        elif chan_pos <= 80.0:
            p1_channel = 5.0
        else:
            p1_channel = 0.0
    else:
        p1_channel = 8.0

    setup_obj = _get("technical_setup")
    setup_label = ""
    if isinstance(setup_obj, dict):
        setup_label = str(setup_obj.get("label", ""))
    elif setup_obj:
        setup_label = str(setup_obj)
    else:
        setup_label = str(_get("technical_setup_label", ""))

    sl_lower = setup_label.lower()
    high_reward_keywords = ("breakout", "bounce", "cup", "triangle", "flag", "expansion")
    bear_keywords = ("breakdown", "bear", "reversal", "cautious", "distribution")

    if any(k in sl_lower for k in high_reward_keywords):
        p1_setup = 10.0
    elif any(k in sl_lower for k in bear_keywords):
        p1_setup = 1.0
    elif sl_lower:
        p1_setup = 6.0
    else:
        p1_setup = 6.0

    pct_52h = _safe_float(_get("pct_from_52w_high"))
    if pct_52h is not None:
        if pct_52h >= -10.0:
            p1_52w = 5.0
        elif pct_52h >= -25.0:
            p1_52w = 3.0
        else:
            p1_52w = 1.0
    else:
        p1_52w = 2.5

    p1_total = min(30.0, p1_channel + p1_setup + p1_52w)

    # ==========================================
    # Pillar 2: Earnings Track Record (25 pts)
    # ==========================================
    beat_rate = _safe_float(_get("beat_rate_pct"))
    total_hq = _get("total_historical_quarters", 0)
    try:
        total_hq = int(total_hq) if total_hq is not None else 0
    except (TypeError, ValueError):
        total_hq = 0

    if beat_rate is not None and total_hq > 0:
        if beat_rate >= 75.0:
            p2_beats = 15.0
        elif beat_rate >= 50.0:
            p2_beats = 10.0
        elif beat_rate >= 25.0:
            p2_beats = 5.0
        else:
            p2_beats = 0.0
    else:
        p2_beats = 8.0

    q_scores = []
    for k in ("q1_earnings_score", "q2_earnings_score", "q3_earnings_score"):
        qv = _safe_float(_get(k))
        if qv is not None and qv > 0:
            q_scores.append(qv)

    if q_scores:
        avg_q = sum(q_scores) / len(q_scores)
        p2_quality = min(10.0, max(0.0, (avg_q / 9.0) * 10.0))
    else:
        prev_3q = _safe_float(_get("prev_3q_earnings_score"))
        if prev_3q is not None and prev_3q > 0:
            p2_quality = min(10.0, max(0.0, (prev_3q / 9.0) * 10.0))
        else:
            p2_quality = 5.5

    p2_total = min(25.0, p2_beats + p2_quality)

    # ==========================================
    # Pillar 3: Momentum & Volume (25 pts)
    # ==========================================
    r7 = _safe_float(_get("seven_day_return_pct"))
    if r7 is not None:
        if r7 >= 3.0:
            p3_r7 = 7.0
        elif r7 >= 0.0:
            p3_r7 = 5.0
        elif r7 >= -3.0:
            p3_r7 = 3.0
        else:
            p3_r7 = 0.0
    else:
        p3_r7 = 3.0

    r30 = _safe_float(_get("thirty_day_return_pct"))
    if r30 is not None:
        if r30 >= 5.0:
            p3_r30 = 8.0
        elif r30 >= 0.0:
            p3_r30 = 5.0
        elif r30 >= -5.0:
            p3_r30 = 2.0
        else:
            p3_r30 = 0.0
    else:
        p3_r30 = 3.0

    rel_vol = _safe_float(_get("rel_vol_5d_vs_63d"))
    if rel_vol is not None:
        if rel_vol >= 2.0:
            p3_vol = 10.0
        elif rel_vol >= 1.2:
            p3_vol = 7.0
        elif rel_vol >= 0.8:
            p3_vol = 4.0
        else:
            p3_vol = 1.0
    else:
        p3_vol = 4.0

    p3_total = min(25.0, p3_r7 + p3_r30 + p3_vol)

    # ==========================================
    # Pillar 4: Predictive AI & Quant Edge (20 pts)
    # ==========================================
    kronos_data = _get("kronos_14d")
    gbm_data = _get("gbm_prediction")

    has_consensus = bool(consensus_pred and consensus_pred.get("consensus_direction"))
    has_kronos = bool(isinstance(kronos_data, dict) and (kronos_data.get("trend") or kronos_data.get("return_pct") is not None))
    has_gbm = bool(isinstance(gbm_data, dict) and gbm_data.get("direction") not in (None, "?"))

    has_any_ai = has_consensus or has_kronos or has_gbm

    if has_any_ai:
        if has_consensus:
            cdir = str(consensus_pred.get("consensus_direction", "")).upper()
            cret = _safe_float(consensus_pred.get("consensus_return_pct"), 0.0)
            if "BULL" in cdir:
                p4_consensus = 10.0 if (cret and cret > 3.0) else 8.0
            elif "BEAR" in cdir:
                p4_consensus = 0.0
            else:
                p4_consensus = 4.0
        else:
            p4_consensus = 4.0

        if has_kronos:
            ktrend = str(kronos_data.get("trend", "")).upper()
            kret = _safe_float(kronos_data.get("return_pct"), 0.0)
            if "BULL" in ktrend or (kret and kret > 0):
                p4_kronos = 5.0
            elif "BEAR" in ktrend or (kret and kret < -3.0):
                p4_kronos = 0.0
            else:
                p4_kronos = 2.5
        else:
            p4_kronos = 2.5

        if has_gbm:
            gdir = str(gbm_data.get("direction", "")).upper()
            if gdir == "UP":
                p4_gbm = 5.0
            elif gdir == "DOWN":
                p4_gbm = 0.0
            else:
                p4_gbm = 2.5
        else:
            p4_gbm = 2.5

        p4_total = min(20.0, p4_consensus + p4_kronos + p4_gbm)
        raw_score = p1_total + p2_total + p3_total + p4_total
        rescaled = False
    else:
        base_80 = p1_total + p2_total + p3_total
        raw_score = (base_80 / 80.0) * 100.0
        p4_total = 0.0
        rescaled = True

    final_score = int(round(max(0.0, min(100.0, raw_score))))

    if final_score >= 75:
        signal = "STRONG BUY"
        badge_cls = "signal-badge signal-strong-buy"
        bg_col = "rgba(16,185,129,0.18)"
        text_col = "#10b981"
        border_col = "rgba(16,185,129,0.4)"
    elif final_score >= 60:
        signal = "BUY"
        badge_cls = "signal-badge signal-buy"
        bg_col = "rgba(52,211,153,0.14)"
        text_col = "#34d399"
        border_col = "rgba(52,211,153,0.3)"
    elif final_score >= 48:
        signal = "ACCUMULATE"
        badge_cls = "signal-badge signal-accumulate"
        bg_col = "rgba(56,189,248,0.12)"
        text_col = "#38bdf8"
        border_col = "rgba(56,189,248,0.3)"
    elif final_score >= 35:
        signal = "NEUTRAL"
        badge_cls = "signal-badge signal-neutral"
        bg_col = "rgba(148,163,184,0.1)"
        text_col = "#94a3b8"
        border_col = "rgba(148,163,184,0.25)"
    else:
        signal = "AVOID"
        badge_cls = "signal-badge signal-avoid"
        bg_col = "rgba(239,68,68,0.14)"
        text_col = "#f87171"
        border_col = "rgba(239,68,68,0.35)"

    scale_note = " [Dynamic Re-scale: 80pt base]" if rescaled else ""
    tooltip = (
        f"4-Pillar Quantitative Action Signal: {signal} ({final_score}/100)\n"
        f"• S/R & Technical Structure: {p1_total:.1f}/30\n"
        f"• Earnings Beat & Quality: {p2_total:.1f}/25\n"
        f"• Momentum & Vol Surge: {p3_total:.1f}/25\n"
        f"• AI Consensus & Quant Edge: {p4_total:.1f}/20{scale_note}"
    )

    badge_html = (
        f'<span class="{badge_cls}" '
        f'style="background:{bg_col};color:{text_col};border:1px solid {border_col};font-size:0.68rem;padding:0.12rem 0.45rem;border-radius:4px;font-weight:700;letter-spacing:0.02em;white-space:nowrap;display:inline-flex;align-items:center;gap:0.25rem;" '
        f'data-buy-score="{final_score}" data-buy-signal="{signal}" '
        f'title="{html.escape(tooltip)}">'
        f'{signal} <span style="font-size:0.6rem;opacity:0.85;font-family:var(--font-mono);font-weight:600;">{final_score}</span>'
        f'</span>'
    )

    return {
        "score": final_score,
        "signal": signal,
        "badge_class": badge_cls,
        "badge_html": badge_html,
        "pill_color": text_col,
        "tooltip": tooltip,
        "pillars": {
            "technical": p1_total,
            "track_record": p2_total,
            "momentum": p3_total,
            "ai_edge": p4_total,
            "rescaled": rescaled,
        },
    }
