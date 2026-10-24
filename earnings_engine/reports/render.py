"""Backwards-compatible facade for earnings report rendering.

Decomposed into earnings_engine.reports.render_pkg submodules:
- scoring.py: Action indicator computation and numeric safeguards.
- tags.py: Institutional tags and badges.
- formatters.py: Prediction direction and card formatters.
- table_builders.py: Ledger tables, day/cap sections, and popups.
- helpers.py: Number/percentage formatting and stock popup builder.
- row_builder.py: Single stock result row processing.
- report_engine.py: Report rendering engines for dashboard, predictions, upcoming results.
"""

from __future__ import annotations

from earnings_engine.reports.render_pkg import (
    LARGE_CAP_THRESHOLD,
    OUTPUT_DIR,
    TEMPLATES_DIR,
    _DAY_COLORS,
    _assign_day_classes,
    _build_cap_section,
    _build_card_sections,
    _build_day_legend,
    _build_day_section,
    _build_ledger_table,
    _fmt,
    _fmt_hl_pair,
    _fmt_num,
    _fmt_pct_only,
    _fmt_prediction,
    _fmt_quarter_week_hl,
    _load_template,
    _popup_id,
    _popup_metric,
    _popup_section,
    _pred_float,
    _render_template,
    _safe_float,
    _sort_per_day,
    _style_direction,
    _to_float,
    build_institutional_tags,
    build_result_row,
    build_stock_popup_html,
    build_upcoming_results_fragments,
    compute_buy_indicator,
    render_dashboard,
    render_institutional_tags_html,
    render_predictions,
    render_upcoming_results_report,
)

__all__ = [
    "OUTPUT_DIR",
    "TEMPLATES_DIR",
    "LARGE_CAP_THRESHOLD",
    "_DAY_COLORS",
    "_load_template",
    "_render_template",
    "render_dashboard",
    "render_predictions",
    "render_upcoming_results_report",
    "build_upcoming_results_fragments",
    "build_result_row",
    "build_stock_popup_html",
    "compute_buy_indicator",
    "_safe_float",
    "build_institutional_tags",
    "render_institutional_tags_html",
    "_style_direction",
    "_pred_float",
    "_fmt_num",
    "_fmt_prediction",
    "_build_card_sections",
    "_assign_day_classes",
    "_build_day_legend",
    "_sort_per_day",
    "_build_ledger_table",
    "_build_cap_section",
    "_build_day_section",
    "_popup_id",
    "_popup_metric",
    "_popup_section",
    "_fmt",
    "_to_float",
    "_fmt_pct_only",
    "_fmt_hl_pair",
    "_fmt_quarter_week_hl",
]
