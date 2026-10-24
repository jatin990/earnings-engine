"""HTML generation helpers for stock rows, badges, and popups."""

from __future__ import annotations

import html
import re
from typing import Any
import pandas as pd

from earnings_engine.reports.render_pkg.formatters import (
    _build_card_sections,
    _fmt_num,
    _fmt_prediction,
)
from earnings_engine.reports.render_pkg.scoring import compute_buy_indicator
from earnings_engine.reports.render_pkg.table_builders import (
    _popup_id,
    _popup_metric,
    _popup_section,
)
from earnings_engine.reports.render_pkg.tags import (
    build_institutional_tags,
    render_institutional_tags_html,
)


def _fmt(v: object, suffix: str = "", signed: bool = False) -> str:
    """Format numeric values with optional suffixes and signs."""
    if pd.isna(v):
        return "—"
    if isinstance(v, (int, float)):
        value = float(v)
        prefix = "+" if signed and value > 0 else "" if signed else ""
        if suffix == "%":
            return f"{prefix}{value:.2f}%"
        if suffix == "Cr":
            return f"{value/1e7:,.1f} Cr"
        if suffix == "/9":
            return f"{value:.0f}/9"
        return f"{prefix}{value:,.2f}"
    return str(v)


def _to_float(v: object, default: float = 0.0) -> float:
    """Safely convert a value to float, handling strings like '4.2%'."""
    if v is None or pd.isna(v):
        return default
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().rstrip("%").replace(",", "")
    try:
        return float(s)
    except ValueError:
        return default


def _fmt_pct_only(v: object) -> str:
    """Format just a percent gap, e.g. '+5.2%'."""
    if pd.isna(v):
        return "—"
    cv = _to_float(v)
    sign = "+" if cv >= 0 else ""
    return f"{sign}{cv:.1f}%"


def _fmt_hl_pair(high_pct: object, high_price: object, low_pct: object, low_price: object) -> str:
    """Format high/low as '+5.2%/+2.3%<br>(1,240/980)'."""
    high_str = _fmt_pct_only(high_pct)
    low_str = _fmt_pct_only(low_pct)
    prices_str = ""
    if not pd.isna(high_price) or not pd.isna(low_price):
        hp = f"{float(high_price):,.0f}" if not pd.isna(high_price) else "—"
        lp = f"{float(low_price):,.0f}" if not pd.isna(low_price) else "—"
        prices_str = f"<br>({hp}/{lp})"
    return f"{high_str}/{low_str}{prices_str}"


def _fmt_quarter_week_hl(
    high_pct: object, high_price: object, low_pct: object, low_price: object,
    high_date: object = None, low_date: object = None, price_7d: object = None,
    earnings_date: object = None, ticker: str = "", ai_summary: object = None,
) -> str:
    """Format quarter week high/low as '+8.7%/+2.3%<br>(8,500/7,800)<br>Jan 18 / Jan 16 | 7D: ₹245' with AI note tooltip."""
    def _is_valid_date(d: object) -> bool:
        if d is None:
            return False
        try:
            return not pd.isna(d)
        except (TypeError, ValueError):
            return False

    summary_title = html.escape(str(ai_summary).strip()) if (ai_summary and not pd.isna(ai_summary) and str(ai_summary).strip()) else ""

    has_high_low = high_pct is not None and not pd.isna(high_pct)
    if not has_high_low:
        if _is_valid_date(earnings_date) and ticker:
            ed_str = pd.Timestamp(earnings_date).strftime("%Y-%m-%d")
            earned = pd.Timestamp(earnings_date).strftime("%b %d")
            title_attr = f' title="{summary_title}"' if summary_title else f' title="Calculate live week move since {earned} print based on current market price"'
            return (
                f'<div class="pred-cell"{title_attr} style="display:inline-flex;flex-direction:column;align-items:center;gap:0.2rem;cursor:help;">'
                f'<button type="button" class="btn-micro btn-micro-primary" '
                f'onclick="event.stopPropagation(); app.calcLiveWeekHL(\'{ticker}\', \'{ed_str}\', this)" '
                f'title="Calculate live week move since {earned} print based on current market price">'
                f'Live H/L</button>'
                f'<span style="font-size:0.65rem;color:var(--text-muted);">earn {earned}</span>'
                f'</div>'
            )
        return "—/—"

    base = _fmt_hl_pair(high_pct, high_price, low_pct, low_price)
    parts: list[str] = []
    if _is_valid_date(high_date) or _is_valid_date(low_date):
        high_d = pd.Timestamp(high_date).strftime("%b %d") if _is_valid_date(high_date) else "—"
        low_d = pd.Timestamp(low_date).strftime("%b %d") if _is_valid_date(low_date) else "—"
        parts.append(f"{high_d} / {low_d}")

    if price_7d is not None and not pd.isna(price_7d):
        if _is_valid_date(earnings_date):
            days_since = (pd.Timestamp.today().normalize() - pd.Timestamp(earnings_date).normalize()).days
            if days_since < 7:
                day_lbl = f"Day {max(1, days_since)}"
                parts.append(f"Live ({day_lbl}): ₹{float(price_7d):,.0f}")
            else:
                parts.append(f"7D: ₹{float(price_7d):,.0f}")
        else:
            parts.append(f"7D: ₹{float(price_7d):,.0f}")

    if _is_valid_date(earnings_date):
        earned = pd.Timestamp(earnings_date).strftime("%b %d")
        parts.append(f"earn {earned}")

    extra = "<br>" + "<br>".join(parts) if parts else ""
    content = f"{base}{extra}"
    if summary_title:
        return f'<div class="q-week-hl-wrap" title="{summary_title}" style="cursor:help;border-bottom:1px dotted rgba(56,189,248,0.3);">{content}</div>'
    return content


def build_stock_popup_html(
    row: pd.Series,
    fmt: dict[str, str],
    ticker: str,
    company_name: str,
    earnings_date_display: str,
    render_template_fn: Any,
) -> str:
    """Render the click popup containing Kronos, GBM, Ollama, and Setup metrics."""
    kronos_pred = row.get("kronos_14d") if "kronos_14d" in row.index else None
    gbm_pred = row.get("gbm_prediction") if "gbm_prediction" in row.index else None
    kronos_dict = kronos_pred if isinstance(kronos_pred, dict) else {}
    gbm_dict = gbm_pred if isinstance(gbm_pred, dict) else {}
    popup_sections: list[str] = []

    # 🤖 Kronos 14-Day Forecast
    if kronos_dict.get("current_price") is not None or kronos_dict.get("return_pct") is not None:
        kp = []
        kp.append(_popup_metric("Current Price", _fmt_num(kronos_dict.get("current_price"))))
        kp.append(_popup_metric("Projected Close", _fmt_num(kronos_dict.get("projected_close"))))
        ret = kronos_dict.get("return_pct")
        if ret is not None:
            ktrend = kronos_dict.get("trend", "Neutral")
            kcls = "pred-bullish" if ktrend == "Bullish" else ("pred-bearish" if ktrend == "Bearish" else "pred-neutral")
            kp.append(_popup_metric("Expected Return", '<span class="' + kcls + '">' + f"{ret:+.1f}%" + '</span>'))
        kp.append(_popup_metric("Trend", str(kronos_dict.get("trend", "—"))))
        kp.append(_popup_metric("Support", _fmt_num(kronos_dict.get("support"))))
        kp.append(_popup_metric("Resistance", _fmt_num(kronos_dict.get("resistance"))))
        popup_sections.append(_popup_section(
            "🤖 Kronos 14-Day Forecast", "src-kronos",
            '<div class="popup-metrics">' + "".join(kp) + '</div>',
        ))

    # 📊 GBM Earnings Prediction
    if gbm_dict.get("direction") not in (None, "?"):
        dcls = "pred-bullish" if gbm_dict.get("direction") == "UP" else "pred-bearish"
        conf = gbm_dict.get("confidence")
        conf_str = f"{conf:.0%}" if conf is not None else "—"
        gp = _popup_metric("Direction", '<span class="' + dcls + '">' + str(gbm_dict.get("direction")) + " " + conf_str + '</span>')
        pu = gbm_dict.get("p_up")
        gp += _popup_metric("Probability Up", f"{pu:.0%}" if pu is not None else "—")
        gp += _popup_metric("Earnings Date", str(gbm_dict.get("earnings_date", "—")))
        gp += _popup_metric("Train Events", str(gbm_dict.get("train_events", "—")))
        popup_sections.append(_popup_section(
            "📊 GBM Earnings Prediction", "src-gbm",
            '<div class="popup-metrics">' + gp + '</div>',
        ))

    # 🧠 Ollama Analysis
    if kronos_dict.get("explanation"):
        popup_sections.append(_popup_section(
            "🧠 Ollama Analysis", "src-ollama",
            '<div class="popup-text">' + str(kronos_dict.get("explanation")) + '</div>',
        ))

    # 📈 Setup, Quality & Momentum
    setup_html = _build_card_sections(row, fmt)
    if setup_html:
        popup_sections.append(_popup_section(
            "📈 Setup, Quality & Momentum", "src-setup", setup_html,
        ))

    popup_values = {
        "popup_id": _popup_id(ticker),
        "company_name": company_name,
        "ticker": ticker,
        "earnings_date": earnings_date_display,
        "source": str(row.get("source", "yfinance")).upper(),
        "popup_sections": "\n".join(popup_sections) if popup_sections
                          else '<div class="popup-text">No prediction data available.</div>',
    }
    return render_template_fn("popup.html", **popup_values)
