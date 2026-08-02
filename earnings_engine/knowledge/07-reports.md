# 07 — Reports

> Related: [06-dataset-predict](06-dataset-predict.md) → [09-cli-config](09-cli-config.md)

## `reports/render.py`
**Templates:** Loaded from `earnings_engine/reports/templates/` via `_load_template()` with in-memory caching. Placeholders substituted via `_render_template(name, **values)` using simple string replacement.

**Template files:**
- `predictions_page.html` — predictions report page
- `earnings_report_page.html` — earnings watch report page (CSS + ledger table header)
- `card.html` — per-stock card with metrics, quality rating, take
- `result_row.html` — single table row for ledger
- `dashboard.html` — interactive dashboard (Results, Swing, Kronos, Watchlist tabs)

**Functions:**
- `render_predictions(preds, name="predictions") -> tuple[Path, Path]` — CSV + HTML
- `render_dashboard(html_path=None) -> Path` — render interactive dashboard
- `render_upcoming_results_report(enriched, csv_path=None, html_path=None) -> Path`

**Formatting helpers (inside `render_upcoming_results_report`):**
- `_fmt(v, suffix="", signed=False) -> str` — format numbers with optional `%`/`Cr` suffix and `+` sign
- `_to_float(v, default=0.0) -> float` — safe conversion handling strings like `"4.2%"`
- `_fmt_pct_only(v) -> str` — format just a percent gap, e.g. `+5.2%`
- `_fmt_hl_pair(high_pct, high_price, low_pct, low_price) -> str` — format high/low as `+5.2%/+2.3%<br>(1,240/980)` (percentages line 1, prices line 2)
- `_fmt_quarter_week_hl(high_pct, high_price, low_pct, low_price) -> str` — alias for `_fmt_hl_pair`, used for per-quarter week high/low

## `dashboard.html` (Kronos + Watchlist features)
- **Kronos tab:** Latest/Audit sub-tabs. Latest = most recent prediction per ticker; Audit = full history (default limit 200) with sortable columns (ticker, run_at, return_pct) and live price delta (Δ ₹ and Δ %) fetched from `/api/v1/market-context/{ticker}` (null/NaN shown as "—").
- **Watchlist tab:** "New Watchlist" input + create button calling `POST /api/v1/universe/create` then reloading universe files.
- **Results tab:** shows result count in header `(N in next D days)`.