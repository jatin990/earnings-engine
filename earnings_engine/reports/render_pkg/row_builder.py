"""Row HTML and metric calculation builder for results table."""

from __future__ import annotations

import html
import re
from typing import Any
import pandas as pd

from earnings_engine.analysis.volume_polarity import (
    classify_volume_polarity,
    get_stock_oi_delta,
)
from earnings_engine.reports.render_pkg.formatters import _fmt_prediction
from earnings_engine.reports.render_pkg.helpers import (
    _fmt,
    _to_float,
    _fmt_hl_pair,
    _fmt_quarter_week_hl,
    build_stock_popup_html,
)
from earnings_engine.reports.render_pkg.scoring import compute_buy_indicator
from earnings_engine.reports.render_pkg.tags import (
    build_institutional_tags,
    render_institutional_tags_html,
)

LARGE_CAP_THRESHOLD = 1e10


def build_result_row(
    row: pd.Series,
    day_classes: dict[str, str],
    latest_consensus_preds: dict[str, Any],
    on_demand: bool,
    render_template_fn: Any,
) -> dict[str, Any]:
    """Process a single stock row, build its HTML table row and click popup."""
    ticker = str(row.get("ticker", ""))
    company_name = str(row.get("company_name", "")) or ticker
    earnings_date = row.get("earnings_date")
    if pd.notna(earnings_date):
        earnings_text = pd.Timestamp(earnings_date).strftime("%Y-%m-%d")
    else:
        earnings_text = "—"
    earnings_date_display = str(row.get("earnings_date_display", "")) or earnings_text

    market_cap = _fmt(row.get("market_cap"), suffix="Cr")
    current_price = _fmt(row.get("current_price"))
    three_day_return = _fmt(row.get("three_day_return_pct"), "%", signed=True)
    seven_day_return = _fmt(row.get("seven_day_return_pct"), "%", signed=True)
    thirty_day_return = _fmt(row.get("thirty_day_return_pct"), "%", signed=True)
    week_change = _fmt(row.get("earnings_week_move_pct"), "%", signed=True)
    eps_estimate = _fmt(row.get("eps_estimate"))
    eps_reported = _fmt(row.get("eps_reported"))
    surprise_pct = _fmt(row.get("surprise_pct"), "%", signed=True)
    pct_from_52w_high_low = _fmt_hl_pair(
        row.get("pct_from_52w_high"), row.get("week_high"),
        row.get("pct_from_52w_low"), row.get("week_low"),
    )
    earnings_week_move = _fmt(row.get("earnings_week_move_pct"), "%", signed=True)

    next_resistance = _fmt(row.get("next_resistance"))
    current_support = _fmt(row.get("current_support"))
    channel_pos_val = row.get("channel_position_pct")
    if channel_pos_val is not None and not pd.isna(channel_pos_val):
        chan_pos_num = max(0.0, min(100.0, float(channel_pos_val)))
        chan_pos_label = f"{chan_pos_num:.0f}%"
    else:
        chan_pos_num = 50.0
        chan_pos_label = "—"

    rel_vol_val = row.get("rel_vol_5d_vs_63d")
    ret_for_polarity = _to_float(row.get("three_day_return_pct"))
    if ret_for_polarity is None:
        ret_for_polarity = _to_float(row.get("seven_day_return_pct"))

    vol_oi_delta = get_stock_oi_delta(ticker)

    cur_p_val = _to_float(row.get("current_price"))
    sup_val = _to_float(row.get("current_support"))
    res_val = _to_float(row.get("next_resistance"))

    vol_polarity_meta = classify_volume_polarity(
        ticker=ticker,
        price_change_pct=ret_for_polarity,
        volume_ratio=float(rel_vol_val) if (rel_vol_val is not None and not pd.isna(rel_vol_val)) else 1.0,
        close=cur_p_val,
        high=res_val,
        low=sup_val,
        oi_change_pct=vol_oi_delta,
    )

    row_vol_polarity = vol_polarity_meta.get("volume_polarity", "NEUTRAL")
    row_oi_buildup = vol_polarity_meta.get("oi_buildup") or ""
    row_is_fno = "true" if vol_polarity_meta.get("is_fno") else "false"

    if rel_vol_val is not None and not pd.isna(rel_vol_val):
        rv_num = float(rel_vol_val)
        b_color = vol_polarity_meta.get("badge_color", "#38bdf8")
        b_bg = vol_polarity_meta.get("badge_bg", "rgba(56,189,248,0.12)")
        b_border = vol_polarity_meta.get("badge_border", "rgba(56,189,248,0.3)")
        b_label = vol_polarity_meta.get("badge_label", "")
        b_tip = vol_polarity_meta.get("tooltip", f"Volume Surge: {rv_num:.1f}x 63D baseline")

        # Pill styling incorporates polarity
        pol_indicator = "▲" if row_vol_polarity == "BULLISH" else ("▼" if row_vol_polarity == "BEARISH" else "●")
        if rv_num >= 2.0:
            rel_vol_html = (
                f'<span class="vol-pill-badge" style="color:{b_color};font-weight:700;background:{b_bg};border:1px solid {b_border};padding:0.08rem 0.38rem;border-radius:4px;display:inline-flex;align-items:center;gap:0.25rem;" title="{b_tip}">'
                f'<span>⚡ {rv_num:.1f}x</span>'
                f'<span style="font-size:0.6rem;opacity:0.9;">{pol_indicator} {b_label}</span>'
                f'</span>'
            )
        elif rv_num >= 1.2:
            rel_vol_html = (
                f'<span class="vol-pill-badge" style="color:{b_color};font-weight:600;background:{b_bg};border:1px solid {b_border};padding:0.06rem 0.32rem;border-radius:4px;display:inline-flex;align-items:center;gap:0.2rem;" title="{b_tip}">'
                f'<span>{rv_num:.1f}x</span>'
                f'<span style="font-size:0.58rem;opacity:0.85;">{pol_indicator}</span>'
                f'</span>'
            )
        elif rv_num <= 0.7:
            rel_vol_html = f'<span style="color:#94a3b8;opacity:0.85;" title="Low Volume: 5D Avg Vol is {rv_num:.1f}x baseline">{rv_num:.1f}x</span>'
        else:
            rel_vol_html = (
                f'<span style="color:{b_color};font-size:0.74rem;" title="{b_tip}">'
                f'{rv_num:.1f}x <span style="font-size:0.6rem;opacity:0.8;">{pol_indicator}</span>'
                f'</span>'
            )
        rel_vol_plain = f"{rv_num:.2f}"
    else:
        rel_vol_html = '<span style="color:#64748b;">—</span>'
        rel_vol_plain = "0"

    beat_rate_val = row.get("beat_rate_pct")
    beat_count = row.get("beat_count", 0)
    total_hq = row.get("total_historical_quarters", 0)
    if beat_rate_val is not None and not pd.isna(beat_rate_val) and total_hq > 0:
        br_num = float(beat_rate_val)
        if br_num >= 75.0:
            br_color = "#34d399"
            br_bg = "rgba(16,185,129,0.12)"
            br_border = "rgba(16,185,129,0.3)"
        elif br_num >= 50.0:
            br_color = "#38bdf8"
            br_bg = "rgba(56,189,248,0.12)"
            br_border = "rgba(56,189,248,0.3)"
        else:
            br_color = "#f87171"
            br_bg = "rgba(239,68,68,0.12)"
            br_border = "rgba(239,68,68,0.3)"
        beat_rate_html = f'<span class="signal-badge" style="background:{br_bg};color:{br_color};border:1px solid {br_border};font-size:0.7rem;padding:0.06rem 0.35rem;border-radius:4px;font-weight:700;" title="Historical Beat Rate: {beat_count}/{total_hq} declared quarters beat estimates">{br_num:.0f}% <span style="font-size:0.58rem;opacity:0.85;">({beat_count}/{total_hq})</span></span>'
        beat_rate_plain = f"{br_num:.0f}"
    else:
        beat_rate_html = '<span style="color:#64748b;">—</span>'
        beat_rate_plain = "0"

    is_near_results = False
    ed_val = row.get("earnings_date")
    if pd.notna(ed_val):
        try:
            days_diff = (pd.Timestamp(ed_val).normalize() - pd.Timestamp.today().normalize()).days
            is_near_results = abs(days_diff) <= 3
        except Exception:
            is_near_results = False

    sup_f = _to_float(row.get("current_support"))
    res_f = _to_float(row.get("next_resistance"))
    cur_p = _to_float(row.get("current_price"))
    if sup_f and res_f and res_f > sup_f and cur_p:
        dist_sup = ((cur_p - sup_f) / cur_p) * 100.0
        dist_res = ((res_f - cur_p) / cur_p) * 100.0
        range_bar_html = (
            f'<div class="sr-structure-cell" style="display:flex;flex-direction:column;gap:0.18rem;min-width:130px;" title="Support: ₹{sup_f:,.1f} (-{dist_sup:.1f}%) | Resistance: ₹{res_f:,.1f} (+{dist_res:.1f}%)">'
            f'<div style="display:flex;justify-content:space-between;font-size:0.65rem;font-family:var(--font-mono);line-height:1;">'
            f'<span style="color:#34d399;font-weight:600;">₹{sup_f:,.0f}</span>'
            f'<span style="color:#f87171;font-weight:600;">₹{res_f:,.0f}</span>'
            f'</div>'
            f'<div style="position:relative;height:5px;background:rgba(255,255,255,0.08);border-radius:9999px;overflow:hidden;">'
            f'<div style="position:absolute;left:0;top:0;height:100%;width:{chan_pos_num:.0f}%;background:linear-gradient(90deg, #10b981, #38bdf8, #f87171);border-radius:9999px;"></div>'
            f'</div>'
            f'<div style="display:flex;justify-content:space-between;font-size:0.62rem;color:#94a3b8;">'
            f'<span>-{dist_sup:.1f}%</span>'
            f'<span style="color:#e2e8f0;font-weight:700;">{chan_pos_label}</span>'
            f'<span>+{dist_res:.1f}%</span>'
            f'</div>'
            f'</div>'
        )
    else:
        range_bar_html = (
            f'<div style="font-size:0.72rem;color:#94a3b8;font-family:var(--font-mono);">'
            f'S: <span style="color:#34d399;">{current_support}</span> | R: <span style="color:#f87171;">{next_resistance}</span>'
            f'</div>'
        )

    q1_ai_note = row.get("q1_ai_summary") if "q1_ai_summary" in row.index else None
    q2_ai_note = row.get("q2_ai_summary") if "q2_ai_summary" in row.index else None
    q3_ai_note = row.get("q3_ai_summary") if "q3_ai_summary" in row.index else None

    q1_week_hl = _fmt_quarter_week_hl(
        row.get("q1_week_high_pct"), row.get("q1_week_high_price"),
        row.get("q1_week_low_pct"), row.get("q1_week_low_price"),
        row.get("q1_week_high_date"), row.get("q1_week_low_date"),
        row.get("q1_price_7d"), row.get("q1_earnings_date"),
        ticker=ticker, ai_summary=q1_ai_note,
    )
    q2_week_hl = _fmt_quarter_week_hl(
        row.get("q2_week_high_pct"), row.get("q2_week_high_price"),
        row.get("q2_week_low_pct"), row.get("q2_week_low_price"),
        row.get("q2_week_high_date"), row.get("q2_week_low_date"),
        row.get("q2_price_7d"), row.get("q2_earnings_date"),
        ticker=ticker, ai_summary=q2_ai_note,
    )
    q3_week_hl = _fmt_quarter_week_hl(
        row.get("q3_week_high_pct"), row.get("q3_week_high_price"),
        row.get("q3_week_low_pct"), row.get("q3_week_low_price"),
        row.get("q3_week_high_date"), row.get("q3_week_low_date"),
        row.get("q3_price_7d"), row.get("q3_earnings_date"),
        ticker=ticker, ai_summary=q3_ai_note,
    )

    prev_quarter_score = _fmt(row.get("prev_quarter_earnings_score"), suffix="/9")
    prev_3q_score = _fmt(row.get("prev_3q_earnings_score"), suffix="/9")
    q1_score = _fmt(row.get("q1_earnings_score"), suffix="/9")
    q2_score = _fmt(row.get("q2_earnings_score"), suffix="/9")
    q3_score = _fmt(row.get("q3_earnings_score"), suffix="/9")

    kronos_pred = row.get("kronos_14d") if "kronos_14d" in row.index else None
    kronos_14d = _fmt_prediction(kronos_pred, kind="kronos", ticker=ticker, on_demand=on_demand)
    gbm_pred = row.get("gbm_prediction") if "gbm_prediction" in row.index else None
    gbm_prediction = _fmt_prediction(gbm_pred, kind="gbm", ticker=ticker, on_demand=on_demand)

    thirty_day_return_value = _to_float(row.get("thirty_day_return_pct"))
    earnings_week_move_value = _to_float(row.get("earnings_week_move_pct"))
    setup_signal = "Constructive" if (thirty_day_return_value > 3 and earnings_week_move_value > 2) else ("Improving" if (thirty_day_return_value > 0 or earnings_week_move_value > 0) else "Cautious")
    reward_potential = "High" if thirty_day_return_value > 5 else ("Medium" if thirty_day_return_value > 0 else "Low")
    support_value = _to_float(row.get("current_support"))
    resistance_value = _to_float(row.get("next_resistance"))
    risk_buffer = "Wide" if support_value and resistance_value and (resistance_value - support_value) > 10 else "Tight"
    momentum_bias = "Positive" if (thirty_day_return_value > 0 and earnings_week_move_value > 0) else ("Negative" if (thirty_day_return_value < 0 and earnings_week_move_value < 0) else "Neutral")

    take = f"{ticker} enters {earnings_text} with 30D return {thirty_day_return} and 1W move {earnings_week_move}. Support near {current_support}, resistance around {next_resistance}."

    fmt = {
        "market_cap": market_cap, "current_price": current_price,
        "pct_from_52w_high_low": pct_from_52w_high_low, "thirty_day_return": thirty_day_return,
        "eps_estimate": eps_estimate, "eps_reported": eps_reported, "surprise_pct": surprise_pct,
        "q1_week_hl": q1_week_hl, "q2_week_hl": q2_week_hl, "q3_week_hl": q3_week_hl,
        "earnings_week_move": earnings_week_move, "q1_score": q1_score, "q2_score": q2_score,
        "q3_score": q3_score, "prev_3q_score": prev_3q_score, "setup_signal": setup_signal,
        "momentum_bias": momentum_bias, "reward_potential": reward_potential, "risk_buffer": risk_buffer,
        "next_resistance": next_resistance, "current_support": current_support, "take": take,
    }

    popup_html = build_stock_popup_html(
        row=row, fmt=fmt, ticker=ticker, company_name=company_name,
        earnings_date_display=earnings_date_display, render_template_fn=render_template_fn,
    )

    pred = latest_consensus_preds.get(ticker)
    clean_dom_id = "consensus-cell-" + re.sub(r"[^A-Za-z0-9]", "_", ticker)
    if pred and pred.get("consensus_direction"):
        dir_str = str(pred["consensus_direction"]).upper()
        is_bull = "BULL" in dir_str
        is_bear = "BEAR" in dir_str
        dir_color = "#34d399" if is_bull else ("#f87171" if is_bear else "#fbbf24")
        dir_bg = "rgba(16,185,129,0.12)" if is_bull else ("rgba(239,68,68,0.12)" if is_bear else "rgba(251,191,36,0.12)")
        ret_val = pred.get("consensus_return_pct")
        ret_disp = f" ({'+' if ret_val > 0 else ''}{ret_val:.1f}%)" if ret_val is not None else ""
        consensus_badge = (
            f'<div id="{clean_dom_id}" style="display:inline-flex;align-items:center;gap:0.25rem;">'
            f'<span class="signal-badge" style="background:{dir_bg};color:{dir_color};border:1px solid {dir_color}44;font-size:0.68rem;padding:0.12rem 0.45rem;font-weight:700;cursor:pointer;line-height:1.2;" '
            f'onclick="event.stopPropagation(); app.openAiDetails(\'ALL\', \'{ticker}\', event)" '
            f'title="DeepSeek-R1, Llama-3.3, Qwen-2.5, Mistral: {dir_str}{ret_disp}">'
            f'{dir_str}{ret_disp}</span>'
            f'<button type="button" class="btn-micro btn-micro-neutral" onclick="event.stopPropagation(); app.runConsensusForTicker(\'{ticker}\', this)" '
            f'title="Re-run 4-Model AI Consensus for {ticker}">Re-run</button>'
            f'</div>'
        )
    else:
        consensus_badge = (
            f'<div id="{clean_dom_id}">'
            f'<button type="button" class="btn-micro btn-micro-neutral" onclick="event.stopPropagation(); app.runConsensusForTicker(\'{ticker}\', this)" '
            f'title="Run DeepSeek-R1, Llama-3.3, Qwen-2.5, Mistral consensus for {ticker}">Consensus</button>'
            f'</div>'
        )

    seq_num = row.get("result_sequence_number")
    is_debut = row.get("is_debut_result", False)
    if seq_num == 1 or is_debut:
        seq_badge_html = '<span class="signal-badge" style="background:rgba(245,158,11,0.2);color:#fbbf24;border:1px solid rgba(245,158,11,0.4);font-size:0.62rem;padding:0.08rem 0.35rem;border-radius:4px;font-weight:700;margin-left:0.3rem;" title="1st Post-IPO Debut Earnings Report">🌟 1st Result</span>'
    elif seq_num == 2:
        seq_badge_html = '<span class="signal-badge" style="background:rgba(16,185,129,0.2);color:#34d399;border:1px solid rgba(16,185,129,0.4);font-size:0.62rem;padding:0.08rem 0.35rem;border-radius:4px;font-weight:700;margin-left:0.3rem;" title="2nd Public Company Earnings Report">🌱 2nd Result</span>'
    elif seq_num == 3:
        seq_badge_html = '<span class="signal-badge" style="background:rgba(56,189,248,0.2);color:#38bdf8;border:1px solid rgba(56,189,248,0.4);font-size:0.62rem;padding:0.08rem 0.35rem;border-radius:4px;font-weight:700;margin-left:0.3rem;" title="3rd Public Company Earnings Report">🌿 3rd Result</span>'
    else:
        seq_badge_html = ""

    status_badge = ""
    eps_rep = row.get("eps_reported")
    surp = row.get("surprise_pct")
    src = str(row.get("source", "")).lower()
    exch_src = str(row.get("exchange_source", "") or "").upper()
    conf_status = str(row.get("confirmation_status", "") or "").upper()
    bm_purpose = str(row.get("board_meeting_purpose", "") or "")
    is_future = pd.notna(ed_val) and pd.Timestamp(ed_val).normalize() > pd.Timestamp.today().normalize()
    is_official = exch_src in ("NSE", "BSE") or "nse" in src or "bse" in src or conf_status == "CONFIRMED"

    if is_future:
        if is_official:
            badge_title = f"Official {exch_src or 'Exchange'} Board Meeting Notice" + (f": {bm_purpose}" if bm_purpose else "")
            status_badge = f'<span class="signal-badge" style="background:rgba(147,51,234,0.15);color:#c084fc;border:1px solid rgba(147,51,234,0.3);font-size:0.62rem;padding:0.08rem 0.35rem;border-radius:4px;font-weight:700;margin-left:0.25rem;" title="{badge_title}">🏛️ {exch_src or "Board Meeting"}</span>'
        else:
            status_badge = '<span class="signal-badge" style="background:rgba(239,68,68,0.12);color:#fca5a5;border:1px solid rgba(239,68,68,0.3);font-size:0.62rem;padding:0.08rem 0.35rem;border-radius:4px;font-weight:700;margin-left:0.25rem;" title="Tentative / Estimated Date - Official Results Not Yet Filed">⏳ Unconfirmed</span>'
    elif eps_rep is not None and not pd.isna(eps_rep):
        status_badge = '<span class="signal-badge" style="background:rgba(16,185,129,0.15);color:#34d399;border:1px solid rgba(16,185,129,0.3);font-size:0.62rem;padding:0.08rem 0.35rem;border-radius:4px;font-weight:700;margin-left:0.25rem;" title="Official Financial Results Declared">✅ Declared</span>'
    elif is_official:
        status_badge = f'<span class="signal-badge" style="background:rgba(147,51,234,0.15);color:#c084fc;border:1px solid rgba(147,51,234,0.3);font-size:0.62rem;padding:0.08rem 0.35rem;border-radius:4px;font-weight:700;margin-left:0.25rem;" title="Official Corporate Board Meeting Notice ({exch_src or "NSE/BSE"})">🏛️ {exch_src or "Board Meeting"}</span>'
    elif pd.notna(ed_val) and pd.Timestamp(ed_val) < pd.Timestamp.today().normalize() and (eps_rep is None or pd.isna(eps_rep)) and (surp is None or pd.isna(surp)):
        status_badge = '<span class="signal-badge" style="background:rgba(239,68,68,0.12);color:#fca5a5;border:1px solid rgba(239,68,68,0.3);font-size:0.62rem;padding:0.08rem 0.35rem;border-radius:4px;font-weight:700;margin-left:0.25rem;" title="Tentative / Estimated Date - Official Results Not Yet Filed">⏳ Unconfirmed</span>'

    full_badges = (seq_badge_html + " " + status_badge).strip() if (seq_badge_html or status_badge) else ""

    relative_date_badge_html = ""
    if pd.notna(ed_val):
        try:
            days_diff = (pd.Timestamp(ed_val).normalize() - pd.Timestamp.today().normalize()).days
            if days_diff == 0:
                relative_date_badge_html = '<span class="signal-badge" style="background:rgba(56,189,248,0.15);color:#38bdf8;border:1px solid rgba(56,189,248,0.3);font-size:0.62rem;padding:0.04rem 0.25rem;border-radius:3px;font-weight:700;">Today</span>'
            elif days_diff == 1:
                relative_date_badge_html = '<span style="font-size:0.65rem;color:#38bdf8;font-weight:600;">Tomorrow</span>'
            elif days_diff > 1:
                relative_date_badge_html = f'<span style="font-size:0.65rem;color:#94a3b8;">In {days_diff}d</span>'
            elif days_diff == -1:
                relative_date_badge_html = '<span style="font-size:0.65rem;color:#94a3b8;">Yesterday</span>'
            else:
                relative_date_badge_html = f'<span style="font-size:0.65rem;color:#64748b;">{abs(days_diff)}d ago</span>'
        except Exception:
            relative_date_badge_html = ""

    surp_f = _to_float(surp) if (surp is not None and not pd.isna(surp)) else None
    if surp_f is not None:
        surp_c = "#34d399" if surp_f > 0 else ("#f87171" if surp_f < 0 else "#94a3b8")
        surp_txt = f"{'+' if surp_f > 0 else ''}{surp_f:.1f}%"
        surp_badge = f' <span style="font-size:0.62rem;color:{surp_c};font-weight:700;">({surp_txt})</span>'
        eps_surprise_pct = f'<span style="color:{surp_c};font-weight:600;">{surp_txt}</span>'
    else:
        surp_badge = ""
        eps_surprise_pct = '<span style="color:#64748b;">—</span>'

    eps_estimates_html = (
        f'<div style="display:flex;flex-direction:column;gap:0.1rem;" title="Consensus EPS Estimate: {eps_estimate} | Reported EPS: {eps_reported} | Surprise: {surprise_pct}">'
        f'<div style="display:flex;align-items:center;gap:0.25rem;justify-content:space-between;">'
        f'<span style="font-size:0.65rem;color:#64748b;">Est:</span><span style="color:#f8fafc;font-weight:600;">{eps_estimate}</span>'
        f'</div>'
        f'<div style="display:flex;align-items:center;gap:0.25rem;justify-content:space-between;">'
        f'<span style="font-size:0.65rem;color:#64748b;">Rep:</span><span style="color:#cbd5e1;font-weight:500;">{eps_reported}{surp_badge}</span>'
        f'</div></div>'
    )

    past_results_html = (
        f'<div style="display:flex;flex-direction:column;gap:0.12rem;" title="Beat Rate: {beat_rate_plain}% | 3Q Quality: {q1_score} | {q2_score} | {q3_score} (Avg {prev_3q_score})">'
        f'<div style="display:flex;align-items:center;gap:0.25rem;justify-content:space-between;">'
        f'<span style="font-size:0.65rem;color:#64748b;">Beats:</span>{beat_rate_html}'
        f'</div>'
        f'<div style="display:flex;align-items:center;gap:0.25rem;justify-content:space-between;">'
        f'<span style="font-size:0.65rem;color:#64748b;">3Q:</span>'
        f'<span style="font-size:0.68rem;color:#38bdf8;font-weight:600;">{q1_score} | {q2_score} | {q3_score}</span>'
        f'</div></div>'
    )

    r7_f = _to_float(row.get("seven_day_return_pct")) if pd.notna(row.get("seven_day_return_pct")) else None
    r30_f = _to_float(row.get("thirty_day_return_pct")) if pd.notna(row.get("thirty_day_return_pct")) else None
    c7 = "#34d399" if (r7_f is not None and r7_f > 0) else ("#f87171" if (r7_f is not None and r7_f < 0) else "#94a3b8")
    c30 = "#34d399" if (r30_f is not None and r30_f > 0) else ("#f87171" if (r30_f is not None and r30_f < 0) else "#94a3b8")
    txt7 = f"{'+' if r7_f > 0 else ''}{r7_f:.1f}%" if r7_f is not None else "—"
    txt30 = f"{'+' if r30_f > 0 else ''}{r30_f:.1f}%" if r30_f is not None else "—"

    returns_consolidated_html = (
        f'<div style="display:flex;flex-direction:column;gap:0.1rem;" title="7D Return: {txt7} | 30D Return: {txt30} | 3D: {three_day_return}">'
        f'<div style="display:flex;align-items:center;gap:0.35rem;justify-content:space-between;">'
        f'<span style="font-size:0.66rem;color:#64748b;">7D:</span><span style="color:{c7};font-weight:600;">{txt7}</span>'
        f'</div>'
        f'<div style="display:flex;align-items:center;gap:0.35rem;justify-content:space-between;">'
        f'<span style="font-size:0.66rem;color:#64748b;">30D:</span><span style="color:{c30};font-weight:600;">{txt30}</span>'
        f'</div></div>'
    )

    tech_setup = row.get("technical_setup")
    if not isinstance(tech_setup, dict):
        try:
            from earnings_engine.data.market_context import classify_technical_setup
            tech_setup = classify_technical_setup(
                current_price=_to_float(row.get("current_price")),
                current_support=_to_float(row.get("current_support")),
                next_resistance=_to_float(row.get("next_resistance")),
                dist_to_support_pct=_to_float(row.get("dist_to_support_pct")),
                dist_to_resistance_pct=_to_float(row.get("dist_to_resistance_pct")),
                rel_vol_5d_vs_63d=_to_float(row.get("rel_vol_5d_vs_63d")),
                seven_day_return_pct=r7_f,
                thirty_day_return_pct=r30_f,
                three_day_return_pct=_to_float(row.get("three_day_return_pct")),
                channel_position_pct=_to_float(row.get("channel_position_pct")),
                pct_from_52w_high=_to_float(row.get("pct_from_52w_high")),
            )
        except Exception:
            tech_setup = {"label": "🎯 Range Base", "badge_color": "#38bdf8", "badge_bg": "rgba(56,189,248,0.12)", "badge_border": "rgba(56,189,248,0.3)", "description": "Trading in normal consolidation structure."}

    ts_label = tech_setup.get("label", "🎯 Range Base")
    ts_color = tech_setup.get("badge_color", "#38bdf8")
    ts_bg = tech_setup.get("badge_bg", "rgba(56,189,248,0.12)")
    ts_border = tech_setup.get("badge_border", "rgba(56,189,248,0.3)")
    ts_desc = html.escape(str(tech_setup.get("description", "")))
    technical_setup_badge_html = f'<span class="signal-badge" style="background:{ts_bg};color:{ts_color};border:1px solid {ts_border};font-size:0.68rem;padding:0.12rem 0.45rem;border-radius:4px;font-weight:600;white-space:nowrap;" title="{ts_desc}">{ts_label}</span>'

    row_with_setup = row.to_dict() if isinstance(row, pd.Series) else dict(row)
    row_with_setup["technical_setup"] = tech_setup
    buy_res = compute_buy_indicator(row_with_setup, consensus_pred=pred)

    inst_tags = build_institutional_tags(row_with_setup)
    institutional_tags_html = render_institutional_tags_html(inst_tags)

    mcap_value = _to_float(row.get("market_cap"))
    is_large = mcap_value > LARGE_CAP_THRESHOLD
    cap_tier = "large" if is_large else "small"

    try:
        from earnings_engine.config import Settings
        from earnings_engine.data.industry import load_industry
        ind_val = load_industry(ticker, Settings())
    except Exception:
        ind_val = None

    raw_ind = row.get("industry")
    if pd.isna(raw_ind) or not str(raw_ind).strip() or str(raw_ind).lower() in ("nan", "none"):
        raw_ind = None
    raw_sec = row.get("sector")
    if pd.isna(raw_sec) or not str(raw_sec).strip() or str(raw_sec).lower() in ("nan", "none"):
        raw_sec = None
    industry_name = str(ind_val or raw_ind or raw_sec or "General / Multi-Sector")

    row_values = {
        "ticker": ticker,
        "date": earnings_text,
        "cap_tier": cap_tier,
        "industry": html.escape(str(industry_name)),
        "technical_setup_label": html.escape(ts_label),
        "row_ticker_id": re.sub(r"[^a-zA-Z0-9]", "_", ticker),
        "company_name": company_name,
        "result_sequence_badge_html": full_badges,
        "earnings_date": earnings_date_display,
        "relative_date_badge_html": relative_date_badge_html,
        "day_class": day_classes.get(earnings_text, ""),
        "market_cap": market_cap,
        "current_price": current_price,
        "is_near_results_cls": "live-near-results" if is_near_results else "",
        "live_dot_html": '<span class="live-pulse-dot" style="display:inline-block;width:7px;height:7px;border-radius:50%;background:#10b981;box-shadow:0 0 8px #10b981;margin-right:0.35rem;" title="Live Active Session (±3D Results Window)"></span>' if is_near_results else '',
        "three_day_return": three_day_return,
        "seven_day_return": seven_day_return,
        "thirty_day_return": thirty_day_return,
        "eps_estimates_html": eps_estimates_html,
        "eps_surprise_pct": eps_surprise_pct,
        "past_results_html": past_results_html,
        "returns_consolidated_html": returns_consolidated_html,
        "ai_edge_score": consensus_badge,
        "technical_setup_badge_html": technical_setup_badge_html,
        "rel_vol_html": rel_vol_html,
        "rel_vol_plain": rel_vol_plain,
        "vol_polarity": row_vol_polarity.lower(),
        "oi_buildup": row_oi_buildup.lower(),
        "is_fno": row_is_fno,
        "beat_rate_html": beat_rate_html,
        "beat_rate_plain": beat_rate_plain,
        "week_change": week_change,
        "range_bar_html": range_bar_html,
        "channel_position": chan_pos_label,
        "q1_week_hl": q1_week_hl,
        "q2_week_hl": q2_week_hl,
        "q3_week_hl": q3_week_hl,
        "pct_from_52w_high_low": pct_from_52w_high_low,
        "quality_scores": (
            f'<span class="q-score-badge" style="cursor:help;border-bottom:1px dotted rgba(56,189,248,0.6);" title="{html.escape(str(q1_ai_note).strip()) if (q1_ai_note and not pd.isna(q1_ai_note) and str(q1_ai_note).strip()) else f"Q1 Quality Score: {q1_score}"}">{q1_score}</span> | '
            f'<span class="q-score-badge" style="cursor:help;border-bottom:1px dotted rgba(56,189,248,0.6);" title="{html.escape(str(q2_ai_note).strip()) if (q2_ai_note and not pd.isna(q2_ai_note) and str(q2_ai_note).strip()) else f"Q2 Quality Score: {q2_score}"}">{q2_score}</span> | '
            f'<span class="q-score-badge" style="cursor:help;border-bottom:1px dotted rgba(56,189,248,0.6);" title="{html.escape(str(q3_ai_note).strip()) if (q3_ai_note and not pd.isna(q3_ai_note) and str(q3_ai_note).strip()) else f"Q3 Quality Score: {q3_score}"}">{q3_score}</span>'
        ),
        "quality_scores_plain": f"{q1_score} | {q2_score} | {q3_score}",
        "buy_indicator_html": buy_res["badge_html"],
        "buy_score": buy_res["score"],
        "buy_signal": buy_res["signal"],
        "raw_buy_score": str(buy_res["score"]),
        "prev_3q_score": prev_3q_score,
        "next_resistance": next_resistance,
        "current_support": current_support,
        "kronos_14d": kronos_14d,
        "gbm_prediction": gbm_prediction,
        "consensus_badge": consensus_badge,
        "raw_eps_estimate": f"{_to_float(row.get('eps_estimate')):.2f}" if pd.notna(row.get('eps_estimate')) else "",
        "raw_surprise_pct": f"{surp_f:.2f}" if surp_f is not None else "",
        "raw_mcap": f"{mcap_value:.0f}" if mcap_value > 0 else "",
        "raw_price": f"{_to_float(row.get('current_price')):.2f}" if pd.notna(row.get('current_price')) else "",
        "raw_3d": f"{_to_float(row.get('three_day_return_pct')):.2f}" if pd.notna(row.get('three_day_return_pct')) else "",
        "raw_7d": f"{_to_float(row.get('seven_day_return_pct')):.2f}" if pd.notna(row.get('seven_day_return_pct')) else "",
        "raw_30d": f"{_to_float(row.get('thirty_day_return_pct')):.2f}" if pd.notna(row.get('thirty_day_return_pct')) else "",
        "raw_chan_pos": f"{chan_pos_num:.1f}",
        "institutional_tags_html": institutional_tags_html,
    }
    row_html = render_template_fn("result_row.html", **row_values)

    return {
        "ticker": ticker,
        "date_str": earnings_text,
        "is_large": is_large,
        "cap_tier": cap_tier,
        "industry_name": industry_name,
        "row_html": row_html,
        "popup_html": popup_html,
    }
