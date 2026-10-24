"""Display formatters and string helpers for report generation."""

from __future__ import annotations

import html
import re
from typing import Any
import pandas as pd


def _style_direction(val: str) -> str:
    """Format direction into HTML span with up/down class."""
    cls = "up" if val == "UP" else "down"
    return f'<span class="{cls}">{val}</span>'


def _pred_float(value: object, key: str, default: float = 0.0) -> float:
    """Safely extract a numeric field from a prediction dict (Kronos/GBM)."""
    if isinstance(value, dict):
        v = value.get(key)
        if v is not None:
            try:
                return float(v)
            except (TypeError, ValueError):
                return default
    return default


def _fmt_num(v: object) -> str:
    """Format a number nicely, or em-dash when missing."""
    if v is None:
        return "—"
    try:
        fv = float(v)
        if fv != fv:  # NaN
            return "—"
        return f"{fv:,.2f}"
    except (TypeError, ValueError):
        s = str(v).strip()
        return s if s else "—"


def _fmt_prediction(
    value: object,
    kind: str = "kronos",
    ticker: str = "",
    on_demand: bool = False,
) -> str:
    """Format a prediction value for display in the ledger.

    kind='kronos': value is a dict with return_pct, trend, support, resistance.
    kind='gbm': value is a dict with direction, confidence, p_up.

    When ``on_demand`` is True and there is no value yet, render a per-row
    "Run" button that computes just that ticker (used by the dashboard Results
    report so Kronos/GBM are NOT computed for the whole universe upfront).
    """
    is_empty = value is None or (isinstance(value, float) and pd.isna(value))
    if is_empty:
        if on_demand and ticker:
            engine = "kronos" if kind == "kronos" else "gbm"
            return (
                f'<span class="pred-cell">'
                f'<button type="button" class="btn-micro btn-micro-neutral pred-run-btn" data-ticker="{ticker}" '
                f'data-engine="{engine}" '
                f'onclick="app.runRowPrediction(\'{ticker}\',\'{engine}\',this)" title="Run {engine.upper()} on-demand">'
                f'Run</button></span>'
            )
        return '<span class="pred-muted">—</span>'
    if isinstance(value, dict):
        if kind == "kronos":
            ret = value.get("return_pct")
            trend = value.get("trend", "Neutral")
            if ret is None:
                return '<span class="pred-muted">—</span>'
            cls = "pred-bullish" if trend == "Bullish" else ("pred-bearish" if trend == "Bearish" else "pred-neutral")
            return f'<span class="{cls}">{ret:+.1f}%</span>'
        elif kind == "gbm":
            direction = value.get("direction", "?")
            confidence = value.get("confidence")
            if direction == "?":
                return '<span class="pred-muted">—</span>'
            cls = "pred-bullish" if direction == "UP" else "pred-bearish"
            conf_str = f"{confidence:.0%}" if confidence is not None else "—"
            return f'<span class="{cls}">{direction} {conf_str}</span>'
    return '<span class="pred-muted">—</span>'


def _build_card_sections(row: pd.Series, fmt: dict[str, str]) -> str:
    """Build the card's inner sections, skipping any section with no values.

    Returns the HTML for all non-empty sections.
    """
    sections: list[str] = []

    # 1. Market Cap, Price, 52W Range, 30D Return
    cap_price = []
    if fmt["market_cap"] != "—":
        cap_price.append(f'<div class="metric"><span>Market Cap</span><strong>{fmt["market_cap"]}</strong></div>')
    if fmt["current_price"] != "—":
        cap_price.append(f'<div class="metric"><span>Price</span><strong>{fmt["current_price"]}</strong></div>')
    if fmt["pct_from_52w_high_low"] != "—":
        cap_price.append(f'<div class="metric"><span>52W H/L</span><strong>{fmt["pct_from_52w_high_low"]}</strong></div>')
    if fmt["thirty_day_return"] != "—":
        cap_price.append(f'<div class="metric"><span>30D Return</span><strong>{fmt["thirty_day_return"]}</strong></div>')
    if cap_price:
        sections.append(
            '<div class="card-section">'
            '<div class="card-title">📊 Valuation & Price Action</div>'
            '<div class="metrics-grid">' + "".join(cap_price) + '</div>'
            '</div>'
        )

    # 2. EPS Surprise
    eps_items = []
    if fmt["eps_estimate"] != "—":
        eps_items.append(f'<div class="metric"><span>EPS Est</span><strong>{fmt["eps_estimate"]}</strong></div>')
    if fmt["eps_reported"] != "—":
        eps_items.append(f'<div class="metric"><span>EPS Act</span><strong>{fmt["eps_reported"]}</strong></div>')
    if fmt["surprise_pct"] != "—":
        eps_items.append(f'<div class="metric"><span>Surprise</span><strong>{fmt["surprise_pct"]}</strong></div>')
    if eps_items:
        sections.append(
            '<div class="card-section">'
            '<div class="card-title">🎯 Earnings Surprise</div>'
            '<div class="metrics-grid">' + "".join(eps_items) + '</div>'
            '</div>'
        )

    # 3. Post-Earnings Drift (Q1, Q2, Q3 + 1W move)
    drift_items = []
    if fmt["q1_week_hl"] != "—":
        drift_items.append(f'<div class="metric"><span>Q1 Move</span><strong>{fmt["q1_week_hl"]}</strong></div>')
    if fmt["q2_week_hl"] != "—":
        drift_items.append(f'<div class="metric"><span>Q2 Move</span><strong>{fmt["q2_week_hl"]}</strong></div>')
    if fmt["q3_week_hl"] != "—":
        drift_items.append(f'<div class="metric"><span>Q3 Move</span><strong>{fmt["q3_week_hl"]}</strong></div>')
    if fmt["earnings_week_move"] != "—":
        drift_items.append(f'<div class="metric"><span>1W Move</span><strong>{fmt["earnings_week_move"]}</strong></div>')
    if drift_items:
        sections.append(
            '<div class="card-section">'
            '<div class="card-title">📈 Post-Earnings Drift (Week of Event)</div>'
            '<div class="metrics-grid">' + "".join(drift_items) + '</div>'
            '</div>'
        )

    # 4. Quality Scores
    score_items = []
    if fmt["q1_score"] != "—":
        score_items.append(f'<div class="metric"><span>Q1</span><strong>{fmt["q1_score"]}</strong></div>')
    if fmt["q2_score"] != "—":
        score_items.append(f'<div class="metric"><span>Q2</span><strong>{fmt["q2_score"]}</strong></div>')
    if fmt["q3_score"] != "—":
        score_items.append(f'<div class="metric"><span>Q3</span><strong>{fmt["q3_score"]}</strong></div>')
    if fmt["prev_3q_score"] != "—":
        score_items.append(f'<div class="metric"><span>3Q Avg</span><strong>{fmt["prev_3q_score"]}</strong></div>')
    if score_items:
        sections.append(
            '<div class="card-section">'
            '<div class="card-title">⭐ Earnings Quality Score (Surprise Factor)</div>'
            '<div class="metrics-grid">' + "".join(score_items) + '</div>'
            '</div>'
        )

    # 5. Technical Levels
    tech_items = []
    if fmt["next_resistance"] != "—":
        tech_items.append(f'<div class="metric"><span>Resistance</span><strong style="color:var(--red);">{fmt["next_resistance"]}</strong></div>')
    if fmt["current_support"] != "—":
        tech_items.append(f'<div class="metric"><span>Support</span><strong style="color:var(--green);">{fmt["current_support"]}</strong></div>')
    if tech_items:
        sections.append(
            '<div class="card-section">'
            '<div class="card-title">🎯 Swing Support & Resistance</div>'
            '<div class="metrics-grid">' + "".join(tech_items) + '</div>'
            '</div>'
        )

    # 6. Analysis / Commentary
    take = fmt.get("take", "")
    if take:
        sections.append(
            '<div class="commentary" style="margin-top: 0.75rem; padding-top: 0.75rem;">'
            '<div class="card-title" style="margin-bottom: 0.4rem; font-size: 0.85rem;">💡 Analysis</div>'
            f'<span style="font-size: 0.8rem; line-height: 1.5;">{take}</span>'
            '</div>'
        )

    return "\n".join(sections)
