"""Core report generation engines for upcoming results, predictions, and dashboard."""

from __future__ import annotations

import html
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader
import pandas as pd

from earnings_engine.config import PROJECT_ROOT
from earnings_engine.reports.render_pkg.formatters import _style_direction
from earnings_engine.reports.render_pkg.row_builder import build_result_row
from earnings_engine.reports.render_pkg.table_builders import (
    _DAY_COLORS,
    _assign_day_classes,
    _build_day_legend,
    _build_day_section,
    _sort_per_day,
)

OUTPUT_DIR = PROJECT_ROOT / "reports" / "output"
TEMPLATES_DIR = PROJECT_ROOT / "earnings_engine" / "reports" / "templates"

_TEMPLATE_CACHE: dict[str, str] = {}
LARGE_CAP_THRESHOLD = 1e10

_JINJA_ENV = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=True,
)


def _load_template(name: str) -> str:
    """Load an HTML template from the templates directory, cached in memory."""
    if name not in _TEMPLATE_CACHE:
        _TEMPLATE_CACHE[name] = (TEMPLATES_DIR / name).read_text(encoding="utf-8")
    return _TEMPLATE_CACHE[name]


def _render_template(name: str, **values: object) -> str:
    """Substitute {placeholder} tokens in a template file via plain replacement."""
    html_content = _load_template(name)
    for key, value in values.items():
        html_content = html_content.replace("{" + key + "}", str(value))
    return html_content


def render_dashboard(html_path: Path | None = None) -> Path:
    """Render the interactive dashboard for exploring ticker data."""
    if html_path is None:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        html_path = OUTPUT_DIR / "dashboard.html"

    try:
        from earnings_engine.data.crypto import has_private_key
        has_key = has_private_key()
    except Exception:
        has_key = False
    template = _JINJA_ENV.get_template("dashboard.html")
    html_content = template.render(has_diagnostics_key=has_key, has_tracker_key=has_key)

    js_path = TEMPLATES_DIR.parent.parent / "ui" / "js" / "dashboard.js"
    if js_path.exists():
        js_content = js_path.read_text(encoding="utf-8")
        html_content = re.sub(
            r'<script src="/static/js/dashboard\.js[^"]*"></script>',
            lambda m: f"<!-- dashboard.js inline -->\n<script>\n{js_content}\n</script>",
            html_content,
        )

    html_path.write_text(html_content, encoding="utf-8")
    return html_path


def render_predictions(preds: pd.DataFrame, name: str = "predictions") -> tuple[Path, Path]:
    """Write CSV + HTML for a predictions frame. Returns (csv_path, html_path)."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d")
    csv_path = OUTPUT_DIR / f"{name}-{stamp}.csv"
    html_path = OUTPUT_DIR / f"{name}-{stamp}.html"

    preds.to_csv(csv_path, index=False)

    show = preds.copy()
    show["earnings_date"] = show["earnings_date"].dt.date
    show["asof_date"] = show["asof_date"].dt.date
    show["p_up"] = show["p_up"].map("{:.1%}".format)
    show["confidence"] = show["confidence"].map("{:.1%}".format)
    show["direction"] = show["direction"].map(_style_direction)
    cols = ["ticker", "market", "earnings_date", "direction", "confidence", "p_up",
            "n_past_events", "asof_date"]
    table = show[cols].to_html(index=False, escape=False, border=0)

    model = preds["model"].iloc[0] if len(preds) else "?"
    n_train = preds["train_events"].iloc[0] if len(preds) else 0
    html_rendered = _render_template(
        "predictions_page.html",
        title="Upcoming Earnings — Direction Predictions",
        generated=datetime.now().strftime("%Y-%m-%d %H:%M"),
        subtitle=f"model: {model} · trained on {n_train} labeled events · {len(preds)} upcoming",
        table=table,
        note=("Research output, not financial advice. Direction = predicted sign of the "
              "close(T−1)→close(T+1) move around the announcement. Confidence is the "
              "calibrated model probability; consider acting only above your backtested threshold."),
    )
    html_path.write_text(html_rendered, encoding="utf-8")
    return csv_path, html_path


def build_upcoming_results_fragments(enriched: pd.DataFrame, on_demand: bool = False) -> dict[str, Any]:
    """Build the HTML fragments (day legend, day sections, popups) for the report."""
    enriched = enriched.copy()
    enriched["_ticker_key"] = enriched["ticker"].astype(str).str.replace(r"\.(NS|BO)$", "", regex=True)
    enriched = enriched.sort_values("earnings_date", na_position="last")

    merged_rows: list[pd.Series] = []
    for _, group in enriched.groupby("_ticker_key", sort=False):
        rep = group.iloc[0].copy()
        parts = []
        for _, r in group.iterrows():
            d = r.get("earnings_date")
            d_str = pd.Timestamp(d).strftime("%Y-%m-%d") if pd.notna(d) else "—"
            src = str(r.get("source", "yfinance")).lower()
            parts.append(f"{d_str} ({src})")
        rep["earnings_date_display"] = " / ".join(parts)
        merged_rows.append(rep)
    enriched = pd.DataFrame(merged_rows).drop(columns="_ticker_key")
    enriched = _sort_per_day(enriched)

    day_classes = _assign_day_classes(enriched)
    day_legend = _build_day_legend(day_classes)

    try:
        from earnings_engine.consensus import storage as consensus_storage
        latest_consensus_preds = {p["ticker"]: p for p in consensus_storage.get_predictions(limit=1000)}
    except Exception:
        latest_consensus_preds = {}

    day_groups: dict[str, dict[str, Any]] = {}
    for _, row in enriched.iterrows():
        built = build_result_row(
            row=row,
            day_classes=day_classes,
            latest_consensus_preds=latest_consensus_preds,
            on_demand=on_demand,
            render_template_fn=_render_template,
        )
        date_str = built["date_str"]
        if date_str not in day_groups:
            try:
                d_label = pd.Timestamp(date_str).strftime("%A, %b %d, %Y")
                diff = (pd.Timestamp(date_str).normalize() - pd.Timestamp.today().normalize()).days
                d_rel = "Today" if diff == 0 else ("Tomorrow" if diff == 1 else (f"In {diff}d" if diff > 1 else (f"{abs(diff)}d ago" if diff < -1 else "Yesterday")))
            except Exception:
                d_label = date_str
                d_rel = ""
            day_groups[date_str] = {
                "large_by_ind": {},
                "large_popups": [],
                "small_by_ind": {},
                "small_popups": [],
                "stocks": [],
                "day_label": d_label,
                "day_relative": d_rel,
            }
        grp = day_groups[date_str]
        grp["stocks"].append({
            "ticker": built["ticker"],
            "industry": built["industry_name"],
            "cap_tier": built["cap_tier"],
            "row_html": built["row_html"],
        })
        if built["is_large"]:
            grp["large_by_ind"].setdefault(built["industry_name"], []).append(built["row_html"])
            grp["large_popups"].append(built["popup_html"])
        else:
            grp["small_by_ind"].setdefault(built["industry_name"], []).append(built["row_html"])
            grp["small_popups"].append(built["popup_html"])

    day_sections: list[str] = []
    day_sections_meta: list[dict[str, Any]] = []
    sections_list: list[dict[str, Any]] = []
    months_map: dict[str, dict[str, Any]] = {}
    current_month_key = pd.Timestamp.today().normalize().strftime("%Y-%m")

    for date_str in sorted(day_groups.keys()):
        group = day_groups[date_str]
        day_class = day_classes.get(date_str, "")
        color = _DAY_COLORS[int(day_class.split("-")[1]) % len(_DAY_COLORS)] if day_class else "#94a3b8"
        section_html = _build_day_section(
            date_str, day_class, color,
            group["large_by_ind"],
            group["small_by_ind"],
        )
        day_sections.append(section_html)

        try:
            date_obj = pd.Timestamp(date_str)
            m_key = date_obj.strftime("%Y-%m")
            m_label = date_obj.strftime("%b %Y")
        except Exception:
            m_key = "other"
            m_label = "Other"

        stocks_count = sum(len(r) for r in group["large_by_ind"].values()) + sum(len(r) for r in group["small_by_ind"].values())
        day_sections_meta.append({
            "date": date_str, "month_key": m_key, "month_label": m_label,
            "stocks_count": stocks_count, "html": section_html,
        })
        sections_list.append({
            "date": date_str,
            "day_label": group.get("day_label") or date_str,
            "day_relative": group.get("day_relative") or "",
            "stocks": group.get("stocks", []),
        })

        if m_key not in months_map:
            months_map[m_key] = {
                "month_key": m_key, "month_label": m_label,
                "stocks_count": 0, "dates_count": 0,
                "is_current": (m_key == current_month_key),
                "is_past": (m_key < current_month_key),
            }
        months_map[m_key]["stocks_count"] += stocks_count
        months_map[m_key]["dates_count"] += 1

    months_list = [months_map[k] for k in sorted(months_map.keys())]
    popups_html = "".join("".join(g["large_popups"]) + "".join(g["small_popups"]) for g in day_groups.values())

    return {
        "day_legend": day_legend,
        "day_sections": "\n".join(day_sections) if day_sections else "<p>No upcoming earnings data.</p>",
        "day_sections_list": day_sections,
        "day_sections_meta": day_sections_meta,
        "sections": sections_list,
        "months": months_list,
        "total_stocks": sum(m["stocks_count"] for m in months_list),
        "popups": popups_html,
    }


def render_upcoming_results_report(enriched: pd.DataFrame, csv_path: Path | None = None,
                                    html_path: Path | None = None) -> Path:
    """Render a polished HTML report for upcoming-results data."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if html_path is None:
        stamp = datetime.now().strftime("%Y-%m-%d")
        html_path = OUTPUT_DIR / f"upcoming-results-{stamp}.html"
    if csv_path is None:
        csv_path = html_path.with_suffix(".csv")

    fragments = build_upcoming_results_fragments(enriched)
    html_content = _render_template(
        "earnings_report_page.html",
        day_legend=fragments["day_legend"],
        day_sections=fragments["day_sections"],
        popups=fragments["popups"],
    )
    html_path.write_text(html_content, encoding="utf-8")
    return html_path
