"""CSV + HTML report rendering for predictions and backtests.

Output goes to reports/output/ (gitignored). HTML page templates live in
earnings_engine/reports/templates/ as standalone .html files with {placeholder}
tokens. Placeholders are substituted via simple string replacement so the
templates can contain clean CSS without brace escaping.
"""

from __future__ import annotations

import html
from datetime import datetime
from pathlib import Path
from typing import Any

import re
from jinja2 import Environment, FileSystemLoader
import pandas as pd

from earnings_engine.config import PROJECT_ROOT

OUTPUT_DIR = PROJECT_ROOT / "reports" / "output"
TEMPLATES_DIR = Path(__file__).parent / "templates"

_TEMPLATE_CACHE: dict[str, str] = {}

# Large cap threshold: 1000 crore rupees = 1e10 rupees
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
    html = _load_template(name)
    for key, value in values.items():
        html = html.replace("{" + key + "}", str(value))
    return html


def _style_direction(val: str) -> str:
    cls = "up" if val == "UP" else "down"
    return f'<span class="{cls}">{val}</span>'


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
    html = template.render(has_diagnostics_key=has_key, has_tracker_key=has_key)

    import re
    js_path = TEMPLATES_DIR.parent.parent / "ui" / "js" / "dashboard.js"
    if js_path.exists():
        js_content = js_path.read_text(encoding="utf-8")
        html = re.sub(
            r'<script src="/static/js/dashboard\.js[^"]*"></script>',
            lambda m: f"<!-- dashboard.js inline -->\n<script>\n{js_content}\n</script>",
            html,
        )

    html_path.write_text(html, encoding="utf-8")
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
    html = _render_template(
        "predictions_page.html",
        title="Upcoming Earnings — Direction Predictions",
        generated=datetime.now().strftime("%Y-%m-%d %H:%M"),
        subtitle=f"model: {model} · trained on {n_train} labeled events · {len(preds)} upcoming",
        table=table,
        note=("Research output, not financial advice. Direction = predicted sign of the "
              "close(T−1)→close(T+1) move around the announcement. Confidence is the "
              "calibrated model probability; consider acting only above your backtested threshold."),
    )
    html_path.write_text(html, encoding="utf-8")
    return csv_path, html_path


# Dark-theme-friendly palette for per-day color grouping (cycles after 8 days).
_DAY_COLORS = [
    "#38bdf8",  # sky blue
    "#10b981",  # emerald green
    "#f59e0b",  # amber
    "#06b6d4",  # cyan
    "#6366f1",  # indigo
    "#f97316",  # orange
    "#14b8a6",  # teal
    "#f43f5e",  # rose
]


def _assign_day_classes(enriched: pd.DataFrame) -> dict[str, str]:
    """Assign a CSS class (day-0..day-7) to each distinct earnings_date.

    Returns a dict mapping the YYYY-MM-DD string -> CSS class name.
    """
    dates = sorted(enriched["earnings_date"].dropna().unique())
    return {
        pd.Timestamp(d).strftime("%Y-%m-%d"): f"day-{i % len(_DAY_COLORS)}"
        for i, d in enumerate(dates)
    }


def _build_day_legend(day_classes: dict[str, str]) -> str:
    """Build the interactive HTML legend strip showing date -> color chips with multi-select support."""
    if not day_classes:
        return ""
    chips: list[str] = [
        '<button type="button" class="day-chip day-chip-all active" onclick="app.toggleDateFilter(\'ALL\', event)" title="Show all dates">🌐 All Dates</button>'
    ]
    for date_str, cls in day_classes.items():
        color = _DAY_COLORS[int(cls.split("-")[1]) % len(_DAY_COLORS)]
        chips.append(
            f'<button type="button" class="day-chip" data-date="{date_str}" onclick="app.toggleDateFilter(\'{date_str}\', event)" title="Filter {date_str} (Click: single date, Ctrl/Cmd+Click: multi-select)">'
            f'<span class="swatch" style="background:{color}"></span>{date_str}'
            f'</button>'
        )
    return f'<div class="day-legend" id="resultsDateLegendBar">{"".join(chips)}</div>'


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


def _sort_per_day(enriched: pd.DataFrame) -> pd.DataFrame:
    """Group rows by earnings_date, sort each day's sublist best→worst.

    Ranking (momentum is the PRIMARY driver, per user preference):
      1. momentum = thirty_day_return_pct + earnings_week_move_pct
      2. tie-break: Kronos 14D return (bullish model signal)
      3. tie-break: GBM direction (UP=+1, DOWN=-1) × confidence
      4. tie-break: prev_3q_earnings_score
      5. tie-break: market_cap
    """
    if enriched.empty:
        return enriched

    def _rank_key(row: pd.Series) -> tuple[float, float, float, float, float]:
        thirty = float(row.get("thirty_day_return_pct")) if pd.notna(row.get("thirty_day_return_pct")) else 0.0
        week = float(row.get("earnings_week_move_pct")) if pd.notna(row.get("earnings_week_move_pct")) else 0.0
        momentum = thirty + week

        # Kronos 14D return as a tie-breaker (higher = better).
        kronos_ret = _pred_float(row.get("kronos_14d"), "return_pct")

        # GBM direction × confidence as a tie-breaker (UP=+1, DOWN=-1).
        gbm = row.get("gbm_prediction")
        gbm_score = 0.0
        if isinstance(gbm, dict):
            direction = gbm.get("direction")
            conf = gbm.get("confidence")
            if direction in ("UP", "DOWN") and conf is not None:
                try:
                    gbm_score = (1.0 if direction == "UP" else -1.0) * float(conf)
                except (TypeError, ValueError):
                    gbm_score = 0.0

        quality = float(row.get("prev_3q_earnings_score")) if pd.notna(row.get("prev_3q_earnings_score")) else 0.0
        mcap = float(row.get("market_cap")) if pd.notna(row.get("market_cap")) else 0.0
        # Higher is better for all → sort descending.
        return (momentum, kronos_ret, gbm_score, quality, mcap)

    parts: list[pd.DataFrame] = []
    for date_val in sorted(enriched["earnings_date"].dropna().unique()):
        day_df = enriched[enriched["earnings_date"] == date_val].copy()
        day_df["_rank"] = day_df.apply(_rank_key, axis=1)
        day_df = day_df.sort_values("_rank", ascending=False).drop(columns="_rank")
        parts.append(day_df)
    # Rows with no earnings_date go at the end (unchanged order)
    no_date = enriched[enriched["earnings_date"].isna()]
    if not no_date.empty:
        parts.append(no_date)
    return pd.concat(parts, ignore_index=True)


def _fmt_prediction(value: object, kind: str = "kronos",
                    ticker: str = "", on_demand: bool = False) -> str:
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


def _build_ledger_table(rows: list[str], day_class: str = "") -> str:
    """Build a compact next-gen interactive operations table HTML with grouped headers."""
    if not rows:
        return ""
    return (
        '<div class="table-wrapper">'
        '<table class="results-table">'
        "<thead>"
        '<tr class="header-group-row" style="background:#090b12;border-bottom:1px solid rgba(255,255,255,0.1);font-size:0.68rem;text-transform:uppercase;letter-spacing:0.04em;">'
        '<th colspan="2" style="text-align:left;color:#94a3b8;padding:0.35rem 0.5rem;border-right:1px solid rgba(255,255,255,0.06);">🏢 Stock & Catalyst</th>'
        '<th colspan="5" style="text-align:center;color:#38bdf8;padding:0.35rem 0.5rem;border-right:1px solid rgba(255,255,255,0.06);">⚡ Live Market & Momentum</th>'
        '<th colspan="4" style="text-align:center;color:#34d399;padding:0.35rem 0.5rem;border-right:1px solid rgba(255,255,255,0.06);">📐 Technical Price Structure</th>'
        '<th colspan="4" style="text-align:center;color:#c084fc;padding:0.35rem 0.5rem;border-right:1px solid rgba(255,255,255,0.06);">🎯 Historical Quality & AI</th>'
        '<th style="text-align:center;color:#fbbf24;padding:0.35rem 0.5rem;">⚡ Controls</th>'
        "</tr>"
        "<tr>"
        '<th onclick="app.sortResultsTable(this, 0, \'text\')" title="Sort by Stock Symbol">Stock</th>'
        '<th onclick="app.sortResultsTable(this, 1, \'date\')" title="Sort by Announcement Date">Result Date</th>'
        '<th onclick="app.sortResultsTable(this, 2, \'num\')" title="Sort by Market Cap">Mkt Cap</th>'
        '<th onclick="app.sortResultsTable(this, 3, \'num\')" title="Sort by Current Price">Price</th>'
        '<th onclick="app.sortResultsTable(this, 4, \'num\')" title="Sort by 3-Day Return">3D Ret</th>'
        '<th onclick="app.sortResultsTable(this, 5, \'num\')" title="Sort by 7-Day Return">7D Ret</th>'
        '<th onclick="app.sortResultsTable(this, 6, \'num\')" title="Sort by 30-Day Pre-Event Momentum">30D Ret</th>'
        '<th onclick="app.sortResultsTable(this, 7, \'text\')" title="Price Channel Structure (Support ⟵ Current ⟶ Resistance)">Support / Resistance</th>'
        '<th onclick="app.sortResultsTable(this, 8, \'num\')" title="Channel Position % (0%=Support, 100%=Resistance)">Range Pos</th>'
        '<th onclick="app.sortResultsTable(this, 9, \'text\')" title="52-Week High/Low Distance">52W H/L</th>'
        '<th onclick="app.sortResultsTable(this, 10, \'text\')" title="Q1 Week Move">Q1 Wk H/L</th>'
        '<th onclick="app.sortResultsTable(this, 11, \'text\')" title="Quality Scores (Q1 | Q2 | Q3)">Quality</th>'
        '<th onclick="app.sortResultsTable(this, 12, \'num\')" title="Previous 3Q Average Score">3Q Avg</th>'
        '<th onclick="app.sortResultsTable(this, 13, \'text\')" title="Kronos 14-Day AI Forecast">Kronos 14D</th>'
        '<th onclick="app.sortResultsTable(this, 14, \'text\')" style="text-align:center;" title="4-Model AI Consensus Forecast">AI Consensus</th>'
        '<th style="text-align:center;">Actions</th>'
        "</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        "</table></div>"
    )



def _popup_id(ticker: str) -> str:
    """Sanitize a ticker for use as a DOM element id."""
    return re.sub(r"[^a-zA-Z0-9]", "_", str(ticker))


def _popup_metric(label: str, value: str) -> str:
    """A single metric cell for the popup metrics grid."""
    return (
        '<div class="metric">'
        '<span>' + label + '</span>'
        '<strong>' + value + '</strong>'
        '</div>'
    )


def _popup_section(title: str, cls: str, body: str) -> str:
    """A titled section inside the popup body."""
    return (
        '<div class="popup-section ' + cls + '">'
        '<div class="popup-section-title">' + title + '</div>'
        + body
        + '</div>'
    )


def _fmt_num(v: object) -> str:
    """Format a number nicely, or em-dash when missing."""
    if v is None:
        return "\u2014"
    try:
        fv = float(v)
        if fv != fv:  # NaN
            return "\u2014"
        return f"{fv:,.2f}"
    except (TypeError, ValueError):
        s = str(v).strip()
        return s if s else "\u2014"


def _build_cap_section(title: str, badge_cls: str, rows: list[str] | dict[str, list[str]]) -> str:
    """Build a collapsible cap-category section (large/small) with industry sub-grouping."""
    if not rows:
        return ""
    
    # Support both flat list of row htmls or dict of {industry: [row_html, ...]}
    if isinstance(rows, list):
        count = len(rows)
        if not count:
            return ""
        return (
            f'<details class="cap-section" open>'
            f'<summary><span class="{badge_cls}">{title}</span>'
            f'<span class="cap-count">{count} stock{"s" if count != 1 else ""}</span>'
            f'<span class="chevron">▾</span></summary>'
            f'<div class="cap-section-body">{_build_ledger_table(rows)}</div>'
            f'</details>'
        )

    # Dict of {industry_name: [row_html, ...]}
    total_count = sum(len(r) for r in rows.values())
    if not total_count:
        return ""
    
    industry_blocks = []
    for ind_name in sorted(rows.keys()):
        ind_rows = rows[ind_name]
        if not ind_rows:
            continue
        ind_count = len(ind_rows)
        industry_blocks.append(
            f'<div class="industry-subgroup" style="margin: 0.5rem 0 0.75rem 0; padding: 0.4rem 0.6rem; background: rgba(255,255,255,0.02); border-radius: 0.4rem; border: 1px solid rgba(255,255,255,0.05);">'
            f'<div style="font-size: 0.78rem; font-weight: 700; color: #a7f3d0; margin-bottom: 0.35rem; display: flex; align-items: center; gap: 0.4rem;">'
            f'<span>🏭 Industry: {ind_name}</span>'
            f'<span style="background: rgba(16,185,129,0.2); color: #34d399; padding: 0.05rem 0.4rem; border-radius: 9999px; font-size: 0.7rem; font-weight: 700;">{ind_count}</span>'
            f'</div>'
            f'{_build_ledger_table(ind_rows)}'
            f'</div>'
        )

    return (
        f'<details class="cap-section" open>'
        f'<summary><span class="{badge_cls}">{title}</span>'
        f'<span class="cap-count">{total_count} stock{"s" if total_count != 1 else ""} ({len(rows)} industries)</span>'
        f'<span class="chevron">▾</span></summary>'
        f'<div class="cap-section-body">{"".join(industry_blocks)}</div>'
        f'</details>'
    )


def _build_day_section(date_str: str, day_class: str, color: str,
                        large_rows: list[str] | dict[str, list[str]],
                        small_rows: list[str] | dict[str, list[str]]) -> str:
    """Build a collapsible day section with large/small cap and industry subsections."""
    total_large = sum(len(r) for r in large_rows.values()) if isinstance(large_rows, dict) else len(large_rows)
    total_small = sum(len(r) for r in small_rows.values()) if isinstance(small_rows, dict) else len(small_rows)
    total = total_large + total_small
    
    body = []
    large_section = _build_cap_section("Large Cap (>1000 Cr)", "cap-badge-large", large_rows)
    small_section = _build_cap_section("Small Cap (≤1000 Cr)", "cap-badge-small", small_rows)
    if large_section:
        body.append(large_section)
    if small_section:
        body.append(small_section)
    return (
        f'<details class="day-section" data-date="{date_str}" id="day-sec-{date_str}" open>'
        f'<summary><span class="day-dot" style="background:{color}"></span>{date_str}'
        f'<span class="day-count">{total} stock{"s" if total != 1 else ""}</span>'
        f'<span class="chevron">▾</span></summary>'
        f'<div class="day-section-body">{"".join(body)}</div>'
        f'</details>'
    )


def build_upcoming_results_fragments(enriched: pd.DataFrame,
                                     on_demand: bool = False) -> dict[str, str]:
    """Build the HTML fragments (day legend, day sections, popups) for the report.

    Returns a dict with ``day_legend``, ``day_sections`` and ``popups`` keys so
    callers (e.g. the dashboard API) can inject the exact report layout without
    writing a file.
    """
    # Merge the same stock across multiple earnings events (normalize .NS/.BO
    # suffixes for the comparison).  Each ticker appears once, but the Result
    # Date column shows BOTH the nse and yfinance dates with their source labels.
    enriched = enriched.copy()
    enriched["_ticker_key"] = enriched["ticker"].astype(str).str.replace(r"\.(NS|BO)$", "", regex=True)
    enriched = enriched.sort_values("earnings_date", na_position="last")

    # Merge each ticker's rows into one, combining all (date, source) pairs.
    merged_rows: list[pd.Series] = []
    for _, group in enriched.groupby("_ticker_key", sort=False):
        rep = group.iloc[0].copy()
        parts = []
        for _, r in group.iterrows():
            d = r.get("earnings_date")
            if pd.notna(d):
                d_str = pd.Timestamp(d).strftime("%Y-%m-%d")
            else:
                d_str = "\u2014"
            src = str(r.get("source", "yfinance")).lower()
            parts.append(f"{d_str} ({src})")
        rep["earnings_date_display"] = " / ".join(parts)
        merged_rows.append(rep)
    enriched = pd.DataFrame(merged_rows).drop(columns="_ticker_key")

    # Per-day color grouping + best-to-worst ranking within each day.  Runs
    # AFTER the merge so the Kronos/GBM prediction dicts are available to the
    # rank key (momentum primary, model signals as tie-breakers).
    enriched = _sort_per_day(enriched)

    day_classes = _assign_day_classes(enriched)
    day_legend = _build_day_legend(day_classes)

    # Load latest consensus predictions for all tickers
    try:
        from earnings_engine.consensus import storage as consensus_storage
        latest_consensus_preds = {p["ticker"]: p for p in consensus_storage.get_predictions(limit=1000)}
    except Exception:
        latest_consensus_preds = {}

    # Group rows by day, then by cap category
    day_groups: dict[str, dict[str, list]] = {}
    for _, row in enriched.iterrows():
        ticker = str(row.get("ticker", ""))
        company_name = str(row.get("company_name", "")) or ticker
        earnings_date = row.get("earnings_date")
        if pd.notna(earnings_date):
            earnings_text = pd.Timestamp(earnings_date).strftime("%Y-%m-%d")
        else:
            earnings_text = "—"
        # Combined date+source display (e.g. "2026-08-04 (nse) / 2026-08-04 (yfinance)")
        earnings_date_display = str(row.get("earnings_date_display", "")) or earnings_text

        def _fmt(v: object, suffix: str = "", signed: bool = False) -> str:
            if pd.isna(v):
                return "—"
            if isinstance(v, (int, float)):
                value = float(v)
                prefix = "+" if signed and value > 0 else "" if signed else ""
                if suffix == "%":
                    return f"{prefix}{value:.2f}%"
                if suffix == "Cr":
                    # market_cap is in rupees; 1 crore = 10,000,000 rupees
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

        def _fmt_quarter_week_hl(high_pct: object, high_price: object, low_pct: object, low_price: object,
                                  high_date: object = None, low_date: object = None, price_7d: object = None,
                                  earnings_date: object = None, ticker: str = "", ai_summary: object = None) -> str:
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
            
            # Add 7-day price if available, or Live Day label if recent
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

            # Add the quarter's earnings date if available (e.g. "earn Jan 15")
            if _is_valid_date(earnings_date):
                earned = pd.Timestamp(earnings_date).strftime("%b %d")
                parts.append(f"earn {earned}")

            extra = "<br>" + "<br>".join(parts) if parts else ""
            content = f"{base}{extra}"
            if summary_title:
                return f'<div class="q-week-hl-wrap" title="{summary_title}" style="cursor:help;border-bottom:1px dotted rgba(56,189,248,0.3);">{content}</div>'
            return content

        market_cap = _fmt(row.get("market_cap"), suffix="Cr")
        current_price = _fmt(row.get("current_price"))
        three_day_return = _fmt(row.get("three_day_return_pct"), "%", signed=True)
        seven_day_return = _fmt(row.get("seven_day_return_pct"), "%", signed=True)
        thirty_day_return = _fmt(row.get("thirty_day_return_pct"), "%", signed=True)
        week_change = _fmt(row.get("earnings_week_move_pct"), "%", signed=True)
        eps_estimate = _fmt(row.get("eps_estimate"))
        eps_reported = _fmt(row.get("eps_reported"))
        surprise_pct = _fmt(row.get("surprise_pct"), "%", signed=True)
        pct_from_52w_high_low = _fmt_hl_pair(row.get("pct_from_52w_high"), row.get("week_high"),
                                              row.get("pct_from_52w_low"), row.get("week_low"))
        earnings_week_move = _fmt(row.get("earnings_week_move_pct"), "%", signed=True)

        # Structure metrics
        next_resistance = _fmt(row.get("next_resistance"))
        current_support = _fmt(row.get("current_support"))
        channel_pos_val = row.get("channel_position_pct")
        if channel_pos_val is not None and not pd.isna(channel_pos_val):
            chan_pos_num = float(channel_pos_val)
            chan_pos_num = max(0.0, min(100.0, chan_pos_num))
            chan_pos_label = f"{chan_pos_num:.0f}%"
        else:
            chan_pos_num = 50.0
            chan_pos_label = "—"

        # Check if stock has results in +-3 days for live visual styling
        is_near_results = False
        ed_val = row.get("earnings_date")
        if pd.notna(ed_val):
            try:
                days_diff = (pd.Timestamp(ed_val).normalize() - pd.Timestamp.today().normalize()).days
                is_near_results = abs(days_diff) <= 3
            except Exception:
                is_near_results = False

        # Build visual Support / Resistance mini-range bar
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
        
        # Per-quarter week high/low (±4 business days around each earnings date).
        # The earnings date for each quarter is shown so the reader knows WHICH
        # quarter the signal belongs to (Q1 = most recent).
        q1_ai_note = row.get("q1_ai_summary") if "q1_ai_summary" in row.index else None
        q2_ai_note = row.get("q2_ai_summary") if "q2_ai_summary" in row.index else None
        q3_ai_note = row.get("q3_ai_summary") if "q3_ai_summary" in row.index else None

        q1_week_hl = _fmt_quarter_week_hl(row.get("q1_week_high_pct"), row.get("q1_week_high_price"),
                                           row.get("q1_week_low_pct"), row.get("q1_week_low_price"),
                                           row.get("q1_week_high_date"), row.get("q1_week_low_date"),
                                           row.get("q1_price_7d"), row.get("q1_earnings_date"),
                                           ticker=ticker, ai_summary=q1_ai_note)
        q2_week_hl = _fmt_quarter_week_hl(row.get("q2_week_high_pct"), row.get("q2_week_high_price"),
                                           row.get("q2_week_low_pct"), row.get("q2_week_low_price"),
                                           row.get("q2_week_high_date"), row.get("q2_week_low_date"),
                                           row.get("q2_price_7d"), row.get("q2_earnings_date"),
                                           ticker=ticker, ai_summary=q2_ai_note)
        q3_week_hl = _fmt_quarter_week_hl(row.get("q3_week_high_pct"), row.get("q3_week_high_price"),
                                           row.get("q3_week_low_pct"), row.get("q3_week_low_price"),
                                           row.get("q3_week_high_date"), row.get("q3_week_low_date"),
                                           row.get("q3_price_7d"), row.get("q3_earnings_date"),
                                           ticker=ticker, ai_summary=q3_ai_note)
        
        prev_quarter_score = _fmt(row.get("prev_quarter_earnings_score"), suffix="/9")
        prev_3q_score = _fmt(row.get("prev_3q_earnings_score"), suffix="/9")
        q1_score = _fmt(row.get("q1_earnings_score"), suffix="/9")
        q2_score = _fmt(row.get("q2_earnings_score"), suffix="/9")
        q3_score = _fmt(row.get("q3_earnings_score"), suffix="/9")
        next_resistance = _fmt(row.get("next_resistance"))
        current_support = _fmt(row.get("current_support"))

        # Kronos 14-day prediction
        kronos_pred = row.get("kronos_14d") if "kronos_14d" in row.index else None
        kronos_14d = _fmt_prediction(kronos_pred, kind="kronos", ticker=ticker, on_demand=on_demand)

        # GBM earnings prediction
        gbm_pred = row.get("gbm_prediction") if "gbm_prediction" in row.index else None
        gbm_prediction = _fmt_prediction(gbm_pred, kind="gbm", ticker=ticker, on_demand=on_demand)

        thirty_day_return_value = _to_float(row.get("thirty_day_return_pct"))
        earnings_week_move_value = _to_float(row.get("earnings_week_move_pct"))
        signal = "Bullish" if thirty_day_return_value > 0 else "Mixed"
        badge_class = "badge-bullish" if signal == "Bullish" else "badge-neutral"
        if thirty_day_return_value > 3 and earnings_week_move_value > 2:
            setup_signal = "Constructive"
        elif thirty_day_return_value > 0 or earnings_week_move_value > 0:
            setup_signal = "Improving"
        else:
            setup_signal = "Cautious"

        reward_potential = "High" if thirty_day_return_value > 5 else "Medium" if thirty_day_return_value > 0 else "Low"
        support_value = _to_float(row.get("current_support"))
        resistance_value = _to_float(row.get("next_resistance"))
        risk_buffer = "Wide" if support_value and resistance_value and (resistance_value - support_value) > 10 else "Tight"
        if thirty_day_return_value > 0 and earnings_week_move_value > 0:
            momentum_bias = "Positive"
            breakout_context = "Momentum is leading into the print"
        elif thirty_day_return_value < 0 and earnings_week_move_value < 0:
            momentum_bias = "Negative"
            breakout_context = "Momentum is fading ahead of the event"
        else:
            momentum_bias = "Neutral"
            breakout_context = "Range-bound setup ahead of results"

        earnings_data = []
        for col in ["eps_estimate", "eps_reported", "surprise_pct", "earnings_date"]:
            if col in row.index and pd.notna(row.get(col)):
                if col == "earnings_date":
                    earnings_data.append(f"result date: {earnings_text}")
                elif col == "surprise_pct":
                    earnings_data.append(f"surprise: {float(row[col]):.2f}%")
                else:
                    earnings_data.append(f"{col}: {row[col]}")
        earnings_text_items = "; ".join(earnings_data) if earnings_data else "no additional earnings data available"

        quality_score_desc = "Quality is scored on a 1–9 scale from recent earnings surprises, where higher values mean stronger recent print quality."
        momentum_desc = "Momentum is derived from the cached price history using the 30-day return and the week-ahead move around the earnings window."
        if thirty_day_return_value > 0 and earnings_week_move_value > 0:
            take = (
                f"{ticker} is heading into {earnings_text} with a constructive setup: the 30D return is {thirty_day_return} and the 1W move is {earnings_week_move}. "
                f"{quality_score_desc} Recent quality is {prev_quarter_score}/{prev_3q_score}, and the risk/reward backdrop is shaped by support near {current_support} and resistance around {next_resistance}. "
                f"{momentum_desc} Earnings details: {earnings_text_items}."
            )
        elif abs(thirty_day_return_value) > 3:
            take = (
                f"{ticker} reaches {earnings_text} with a more dramatic backdrop: the stock has moved {thirty_day_return} over the last month, with a support/resistance profile around {current_support}/{next_resistance}. "
                f"Recent quality remains {prev_quarter_score}/{prev_3q_score}, so traders should watch whether the move is backed by stronger earnings quality or just short-term momentum. "
                f"Earnings details: {earnings_text_items}."
            )
        else:
            take = (
                f"{ticker} enters {earnings_text} with a balanced profile: the 1W move is {earnings_week_move} and the 30D return is {thirty_day_return}. "
                f"Support is near {current_support} and resistance around {next_resistance}, while recent quality remains {prev_quarter_score}/{prev_3q_score}. "
                f"This is the kind of setup that rewards patience and a close look at the earnings details: {earnings_text_items}."
            )

        day_class = day_classes.get(earnings_text, "")

        # Build formatted values dict for card sections
        fmt = {
            "market_cap": market_cap,
            "current_price": current_price,
            "pct_from_52w_high_low": pct_from_52w_high_low,
            "thirty_day_return": thirty_day_return,
            "eps_estimate": eps_estimate,
            "eps_reported": eps_reported,
            "surprise_pct": surprise_pct,
            "q1_week_hl": q1_week_hl,
            "q2_week_hl": q2_week_hl,
            "q3_week_hl": q3_week_hl,
            "earnings_week_move": earnings_week_move,
            "q1_score": q1_score,
            "q2_score": q2_score,
            "q3_score": q3_score,
            "prev_3q_score": prev_3q_score,
            "setup_signal": setup_signal,
            "momentum_bias": momentum_bias,
            "reward_potential": reward_potential,
            "risk_buffer": risk_buffer,
            "next_resistance": next_resistance,
            "current_support": current_support,
            "take": take,
        }

        # Build per-stock popup (Kronos + GBM + Ollama + Setup) shown on click.
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
            kp.append(_popup_metric("Trend", str(kronos_dict.get("trend", "\u2014"))))
            kp.append(_popup_metric("Support", _fmt_num(kronos_dict.get("support"))))
            kp.append(_popup_metric("Resistance", _fmt_num(kronos_dict.get("resistance"))))
            popup_sections.append(_popup_section(
                "\U0001f916 Kronos 14-Day Forecast", "src-kronos",
                '<div class="popup-metrics">' + "".join(kp) + '</div>',
            ))

        # \U0001f4ca GBM Earnings Prediction (source of truth: gbm_prediction column)
        if gbm_dict.get("direction") not in (None, "?"):
            dcls = "pred-bullish" if gbm_dict.get("direction") == "UP" else "pred-bearish"
            conf = gbm_dict.get("confidence")
            conf_str = f"{conf:.0%}" if conf is not None else "\u2014"
            gp = _popup_metric("Direction", '<span class="' + dcls + '">' + str(gbm_dict.get("direction")) + " " + conf_str + '</span>')
            pu = gbm_dict.get("p_up")
            gp += _popup_metric("Probability Up", f"{pu:.0%}" if pu is not None else "\u2014")
            gp += _popup_metric("Earnings Date", str(gbm_dict.get("earnings_date", "\u2014")))
            gp += _popup_metric("Train Events", str(gbm_dict.get("train_events", "\u2014")))
            popup_sections.append(_popup_section(
                "\U0001f4ca GBM Earnings Prediction", "src-gbm",
                '<div class="popup-metrics">' + gp + '</div>',
            ))

        # \U0001f9e0 Ollama Analysis
        if kronos_dict.get("explanation"):
            popup_sections.append(_popup_section(
                "\U0001f9e0 Ollama Analysis", "src-ollama",
                '<div class="popup-text">' + str(kronos_dict.get("explanation")) + '</div>',
            ))

        # \U0001f4c8 Setup, Quality & Momentum (reuse existing card content)
        setup_html = _build_card_sections(row, fmt)
        if setup_html:
            popup_sections.append(_popup_section(
                "\U0001f4c8 Setup, Quality & Momentum", "src-setup", setup_html,
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
        popup_html = _render_template("popup.html", **popup_values)

        # AI Consensus Badge
        pred = latest_consensus_preds.get(ticker)
        if pred and pred.get("consensus_direction"):
            dir_str = str(pred["consensus_direction"]).upper()
            is_bull = "BULL" in dir_str
            is_bear = "BEAR" in dir_str
            dir_color = "#34d399" if is_bull else ("#f87171" if is_bear else "#fbbf24")
            dir_bg = "rgba(16,185,129,0.12)" if is_bull else ("rgba(239,68,68,0.12)" if is_bear else "rgba(251,191,36,0.12)")
            ret_val = pred.get("consensus_return_pct")
            ret_disp = f" ({'+' if ret_val > 0 else ''}{ret_val:.1f}%)" if ret_val is not None else ""
            clean_dom_id = "consensus-cell-" + re.sub(r"[^A-Za-z0-9]", "_", ticker)
            consensus_badge = (
                f'<div id="{clean_dom_id}" style="display:inline-flex;align-items:center;gap:0.25rem;">'
                f'<span class="signal-badge" style="background:{dir_bg};color:{dir_color};border:1px solid {dir_color}44;font-size:0.68rem;padding:0.12rem 0.45rem;font-weight:700;cursor:pointer;line-height:1.2;" '
                f'onclick="event.stopPropagation(); app.openAiDetails(\'ALL\', \'{ticker}\', event)" '
                f'title="DeepSeek-R1, Llama-3.3, Qwen-2.5, Mistral: {dir_str}{ret_disp}">'
                f'{dir_str}{ret_disp}'
                f'</span>'
                f'<button type="button" class="btn-micro btn-micro-neutral" onclick="event.stopPropagation(); app.runConsensusForTicker(\'{ticker}\', this)" '
                f'title="Re-run 4-Model AI Consensus for {ticker}">Re-run</button>'
                f'</div>'
            )
        else:
            clean_dom_id = "consensus-cell-" + re.sub(r"[^A-Za-z0-9]", "_", ticker)
            consensus_badge = (
                f'<div id="{clean_dom_id}">'
                f'<button type="button" class="btn-micro btn-micro-neutral" onclick="event.stopPropagation(); app.runConsensusForTicker(\'{ticker}\', this)" '
                f'title="Run DeepSeek-R1, Llama-3.3, Qwen-2.5, Mistral consensus for {ticker}">Consensus</button>'
                f'</div>'
            )
        # Result Sequence Badge (🌟 1st Result Debut, 🌱 2nd Result, 🌿 3rd Result)
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

        # Result Declaration / Confirmation Status Badge
        status_badge = ""
        eps_rep = row.get("eps_reported")
        surp = row.get("surprise_pct")
        ed_val = row.get("earnings_date")
        src = str(row.get("source", "")).lower()
        if eps_rep is not None and not pd.isna(eps_rep):
            status_badge = '<span class="signal-badge" style="background:rgba(16,185,129,0.15);color:#34d399;border:1px solid rgba(16,185,129,0.3);font-size:0.62rem;padding:0.08rem 0.35rem;border-radius:4px;font-weight:700;margin-left:0.25rem;" title="Official Financial Results Declared">✅ Declared</span>'
        elif src == "nse":
            status_badge = '<span class="signal-badge" style="background:rgba(147,51,234,0.15);color:#c084fc;border:1px solid rgba(147,51,234,0.3);font-size:0.62rem;padding:0.08rem 0.35rem;border-radius:4px;font-weight:700;margin-left:0.25rem;" title="NSE Corporate Board Meeting Notice">🏛️ Board Meeting</span>'
        elif pd.notna(ed_val) and pd.Timestamp(ed_val) < pd.Timestamp.today().normalize() and (eps_rep is None or pd.isna(eps_rep)) and (surp is None or pd.isna(surp)):
            status_badge = '<span class="signal-badge" style="background:rgba(239,68,68,0.12);color:#fca5a5;border:1px solid rgba(239,68,68,0.3);font-size:0.62rem;padding:0.08rem 0.35rem;border-radius:4px;font-weight:700;margin-left:0.25rem;" title="Tentative / Estimated Date - Official Results Not Yet Filed">⏳ Unconfirmed</span>'

        full_badges = (seq_badge_html + " " + status_badge).strip() if (seq_badge_html or status_badge) else ""

        row_values = {
            "ticker": ticker,
            "row_ticker_id": re.sub(r"[^a-zA-Z0-9]", "_", ticker),
            "company_name": company_name,
            "result_sequence_badge_html": full_badges,
            "earnings_date": earnings_date_display,
            "day_class": day_class,
            "market_cap": market_cap,
            "current_price": current_price,
            "is_near_results_cls": "live-near-results" if is_near_results else "",
            "live_dot_html": '<span class="live-pulse-dot" style="display:inline-block;width:7px;height:7px;border-radius:50%;background:#10b981;box-shadow:0 0 8px #10b981;margin-right:0.35rem;" title="Live Active Session (±3D Results Window)"></span>' if is_near_results else '',
            "three_day_return": three_day_return,
            "seven_day_return": seven_day_return,
            "thirty_day_return": thirty_day_return,
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
            # Plain-text version used as data-quality attribute for JS sorting and test assertions
            "quality_scores_plain": f"{q1_score} | {q2_score} | {q3_score}",
            "prev_3q_score": prev_3q_score,
            "next_resistance": next_resistance,
            "current_support": current_support,
            "kronos_14d": kronos_14d,
            "gbm_prediction": gbm_prediction,
            "consensus_badge": consensus_badge,
        }
        row_html = _render_template("result_row.html", **row_values)

        # Determine cap category: large cap > 1000 Cr (1e10 rupees)
        mcap_value = _to_float(row.get("market_cap"))
        is_large = mcap_value > LARGE_CAP_THRESHOLD

        # Load industry mapping for ticker
        try:
            from earnings_engine.config import Settings
            from earnings_engine.data.industry import load_industry
            ind_val = load_industry(ticker, Settings())
        except Exception:
            ind_val = None
        industry_name = ind_val or row.get("industry") or row.get("sector") or "General / Multi-Sector"

        # Group by day -> cap -> industry
        if earnings_text not in day_groups:
            day_groups[earnings_text] = {
                "large_by_ind": {},
                "large_popups": [],
                "small_by_ind": {},
                "small_popups": [],
            }
        group = day_groups[earnings_text]
        if is_large:
            if industry_name not in group["large_by_ind"]:
                group["large_by_ind"][industry_name] = []
            group["large_by_ind"][industry_name].append(row_html)
            group["large_popups"].append(popup_html)
        else:
            if industry_name not in group["small_by_ind"]:
                group["small_by_ind"][industry_name] = []
            group["small_by_ind"][industry_name].append(row_html)
            group["small_popups"].append(popup_html)

    # Build day sections with metadata
    day_sections: list[str] = []
    day_sections_meta: list[dict[str, Any]] = []
    months_map: dict[str, dict[str, Any]] = {}
    today_dt = pd.Timestamp.today().normalize()
    current_month_key = today_dt.strftime("%Y-%m")

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

        # Parse date and month
        try:
            date_obj = pd.Timestamp(date_str)
            m_key = date_obj.strftime("%Y-%m")
            m_label = date_obj.strftime("%b %Y")
        except Exception:
            m_key = "other"
            m_label = "Other"

        stocks_count = sum(len(r) for r in group["large_by_ind"].values()) + sum(len(r) for r in group["small_by_ind"].values())
        day_sections_meta.append({
            "date": date_str,
            "month_key": m_key,
            "month_label": m_label,
            "stocks_count": stocks_count,
            "html": section_html,
        })

        if m_key not in months_map:
            is_cur = (m_key == current_month_key)
            is_past = (m_key < current_month_key)
            months_map[m_key] = {
                "month_key": m_key,
                "month_label": m_label,
                "stocks_count": 0,
                "dates_count": 0,
                "is_current": is_cur,
                "is_past": is_past,
            }
        months_map[m_key]["stocks_count"] += stocks_count
        months_map[m_key]["dates_count"] += 1

    months_list = [months_map[k] for k in sorted(months_map.keys())]

    popups_html = "".join(
        "".join(g["large_popups"]) + "".join(g["small_popups"])
        for g in day_groups.values()
    )

    return {
        "day_legend": day_legend,
        "day_sections": "\n".join(day_sections) if day_sections else "<p>No upcoming earnings data.</p>",
        "day_sections_list": day_sections,
        "day_sections_meta": day_sections_meta,
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
    html = _render_template(
        "earnings_report_page.html",
        day_legend=fragments["day_legend"],
        day_sections=fragments["day_sections"],
        popups=fragments["popups"],
    )
    html_path.write_text(html, encoding="utf-8")
    return html_path
