"""HTML table, day grouping, and layout section builders for reports."""

from __future__ import annotations

import html
import re
from typing import Any
import pandas as pd
from earnings_engine.reports.render_pkg.formatters import _pred_float

# Dark-theme-friendly palette for per-day color grouping (cycles after 8 days).
_DAY_COLORS = [
    "#38bdf8",  # sky blue
    "#34d399",  # emerald green
    "#818cf8",  # indigo
    "#f59e0b",  # amber
    "#2dd4bf",  # teal
    "#a78bfa",  # purple
    "#06b6d4",  # cyan
    "#94a3b8",  # slate
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


def _build_ledger_table(rows: list[str], day_class: str = "") -> str:
    """Build a compact next-gen interactive operations table HTML with 13 clean, high-density columns."""
    if not rows:
        return ""
    return (
        '<div class="table-wrapper results-terminal-wrapper">'
        '<table class="results-table results-terminal-table">'
        "<thead>"
        "<tr>"
        '<th onclick="app.sortResultsTable(this, 0, \'text\')" title="Sort by Stock Symbol">Stock</th>'
        '<th onclick="app.sortResultsTable(this, 1, \'date\')" title="Sort by Result Date">Result Date</th>'
        '<th onclick="app.sortResultsTable(this, 2, \'num\')" title="Sort by 4-Pillar Quantitative Action Signal">Signal</th>'
        '<th onclick="app.sortResultsTable(this, 3, \'num\')" title="Sort by Current Price">Price / MCap</th>'
        '<th onclick="app.sortResultsTable(this, 4, \'num\')" title="Sort by Consensus EPS Estimate / Reported">EPS Est</th>'
        '<th onclick="app.sortResultsTable(this, 5, \'num\')" title="Sort by Historical Beat Rate & Quality Track Record">Beat Rate</th>'
        '<th onclick="app.sortResultsTable(this, 6, \'num\')" style="text-align:center;" title="Sort by EPS Surprise %">Surprise %</th>'
        '<th onclick="app.sortResultsTable(this, 7, \'num\')" title="Sort by 7-Day & 30-Day Returns">Returns</th>'
        '<th onclick="app.sortResultsTable(this, 8, \'text\')" style="text-align:center;" title="Sort by Multi-Model AI Consensus">AI Edge</th>'
        '<th onclick="app.sortResultsTable(this, 9, \'text\')" title="Actionable Technical Setup Classifier">Setup</th>'
        '<th onclick="app.sortResultsTable(this, 10, \'text\')" title="Multi-Timeframe Support / Resistance Channel">S/R Structure</th>'
        '<th onclick="app.sortResultsTable(this, 11, \'text\')" title="52-Week High/Low Distance">52W Range</th>'
        '<th onclick="app.sortResultsTable(this, 12, \'num\')" style="text-align:center;" title="Relative Volume (5D vs 63D Surge)">Rel Vol</th>'
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


def _build_cap_section(title: str, badge_cls: str, rows: list[str] | dict[str, list[str]]) -> str:
    """Build a collapsible cap-category section (backward-compatibility helper)."""
    if not rows:
        return ""

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

    total_count = sum(len(r) for r in rows.values())
    if not total_count:
        return ""

    table_rows: list[str] = []
    for ind_name in sorted(rows.keys()):
        ind_rows = rows[ind_name]
        if not ind_rows:
            continue
        safe_ind = str(ind_name) if (ind_name is not None and not pd.isna(ind_name)) else "General / Multi-Sector"
        ind_count = len(ind_rows)
        table_rows.append(
            f'<tr class="table-divider-row industry-subgroup industry-divider-row" data-ind="{html.escape(safe_ind)}">'
            f'<td colspan="13">'
            f'<div class="terminal-ind-divider">'
            f'<span class="ind-pill">🏭 Industry: {html.escape(safe_ind)}</span>'
            f'<span class="ind-badge-count">{ind_count}</span>'
            f'</div>'
            f'</td>'
            f'</tr>'
        )
        table_rows.extend(ind_rows)

    return (
        f'<details class="cap-section" open>'
        f'<summary><span class="{badge_cls}">{title}</span>'
        f'<span class="cap-count">{total_count} stock{"s" if total_count != 1 else ""} ({len(rows)} industries)</span>'
        f'<span class="chevron">▾</span></summary>'
        f'<div class="cap-section-body">{_build_ledger_table(table_rows)}</div>'
        f'</details>'
    )


def _build_day_section(date_str: str, day_class: str, color: str,
                        large_rows: list[str] | dict[str, list[str]],
                        small_rows: list[str] | dict[str, list[str]]) -> str:
    """Build a unified high-density terminal stream for a date."""
    total_large = sum(len(r) for r in large_rows.values()) if isinstance(large_rows, dict) else len(large_rows)
    total_small = sum(len(r) for r in small_rows.values()) if isinstance(small_rows, dict) else len(small_rows)
    total = total_large + total_small

    table_rows: list[str] = []

    def _append_cap_rows(cap_title: str, cap_badge_cls: str, cap_tier: str, cap_icon: str,
                         data: list[str] | dict[str, list[str]]):
        if not data:
            return
        if isinstance(data, list):
            if not data:
                return
            count = len(data)
            table_rows.append(
                f'<tr class="table-divider-row cap-section cap-divider-row" data-cap="{cap_tier}">'
                f'<td colspan="13">'
                f'<div class="terminal-cap-divider">'
                f'<span class="{cap_badge_cls}">{cap_icon} {cap_title}</span>'
                f'<span class="terminal-divider-meta">{count} stock{"s" if count != 1 else ""}</span>'
                f'</div>'
                f'</td>'
                f'</tr>'
            )
            table_rows.extend(data)
            return

        tier_count = sum(len(r) for r in data.values())
        if not tier_count:
            return

        ind_count_total = len([k for k, v in data.items() if v])
        table_rows.append(
            f'<tr class="table-divider-row cap-section cap-divider-row" data-cap="{cap_tier}">'
            f'<td colspan="13">'
            f'<div class="terminal-cap-divider">'
            f'<span class="{cap_badge_cls}">{cap_icon} {cap_title}</span>'
            f'<span class="terminal-divider-meta">{tier_count} stock{"s" if tier_count != 1 else ""} · {ind_count_total} industries</span>'
            f'</div>'
            f'</td>'
            f'</tr>'
        )

        for ind_name in sorted(data.keys()):
            ind_rows = data[ind_name]
            if not ind_rows:
                continue
            safe_ind = str(ind_name) if (ind_name is not None and not pd.isna(ind_name)) else "General / Multi-Sector"
            icount = len(ind_rows)
            table_rows.append(
                f'<tr class="table-divider-row industry-subgroup industry-divider-row" data-cap="{cap_tier}" data-ind="{html.escape(safe_ind)}">'
                f'<td colspan="13">'
                f'<div class="terminal-ind-divider">'
                f'<span class="ind-pill">🏭 Industry: {html.escape(safe_ind)}</span>'
                f'<span class="ind-badge-count">{icount}</span>'
                f'</div>'
                f'</td>'
                f'</tr>'
            )
            table_rows.extend(ind_rows)

    _append_cap_rows("Large Cap (>1000 Cr)", "cap-badge-large", "large", "💎", large_rows)
    _append_cap_rows("Small Cap (≤1000 Cr)", "cap-badge-small", "small", "🌱", small_rows)

    large_pill = f'<span class="day-summary-pill large" title="{total_large} Large Cap Stocks">💎 {total_large} Large</span>' if total_large else ''
    small_pill = f'<span class="day-summary-pill small" title="{total_small} Small Cap Stocks">🌱 {total_small} Small</span>' if total_small else ''

    unified_table = _build_ledger_table(table_rows, day_class=day_class) if table_rows else '<div class="no-stocks-day" style="padding:0.75rem;color:#71717a;font-size:0.75rem;">No stocks scheduled for this date.</div>'

    return (
        f'<details class="day-section" data-date="{date_str}" id="day-sec-{date_str}" open>'
        f'<summary class="day-section-summary">'
        f'<div class="day-summary-left">'
        f'<span class="day-dot" style="background:{color};"></span>'
        f'<span class="day-date-text">{date_str}</span>'
        f'<span class="day-count">{total} stock{"s" if total != 1 else ""}</span>'
        f'</div>'
        f'<div class="day-summary-pills">{large_pill}{small_pill}</div>'
        f'<span class="chevron">▾</span>'
        f'</summary>'
        f'<div class="day-section-body" style="padding: 0;">'
        f'{unified_table}'
        f'</div>'
        f'</details>'
    )
