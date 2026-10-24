"""Reports rendering package: dashboard, predictions, upcoming results, and layout builders."""

from __future__ import annotations

from earnings_engine.reports.render_pkg.formatters import (
    _build_card_sections,
    _fmt_num,
    _fmt_prediction,
    _pred_float,
    _style_direction,
)
from earnings_engine.reports.render_pkg.helpers import (
    _fmt,
    _fmt_hl_pair,
    _fmt_pct_only,
    _fmt_quarter_week_hl,
    _to_float,
    build_stock_popup_html,
)
from earnings_engine.reports.render_pkg.report_engine import (
    LARGE_CAP_THRESHOLD,
    OUTPUT_DIR,
    TEMPLATES_DIR,
    _load_template,
    _render_template,
    build_upcoming_results_fragments,
    render_dashboard,
    render_predictions,
    render_upcoming_results_report,
)
from earnings_engine.reports.render_pkg.row_builder import build_result_row
from earnings_engine.reports.render_pkg.scoring import _safe_float, compute_buy_indicator
from earnings_engine.reports.render_pkg.table_builders import (
    _DAY_COLORS,
    _assign_day_classes,
    _build_cap_section,
    _build_day_legend,
    _build_day_section,
    _build_ledger_table,
    _popup_id,
    _popup_metric,
    _popup_section,
    _sort_per_day,
)
from earnings_engine.reports.render_pkg.tags import (
    build_institutional_tags,
    render_institutional_tags_html,
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
