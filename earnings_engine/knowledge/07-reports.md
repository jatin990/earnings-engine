# 07 — Reports

> Related: [06-dataset-predict](06-dataset-predict.md) → [09-cli-config](09-cli-config.md)

## `reports/checker.py`
**Purpose:** Report checker subworkflow — verifies every field in a generated report against the database.

**Functions:**
- `check_report_frame(df, settings=None) -> CheckResult` — verify each field in an enriched report DataFrame against the database / recomputation from raw prices/earnings.
- `check_report_csv(csv_path, settings=None) -> CheckResult` — load a report CSV and run the checker.
- `CheckResult` / `Inconsistency` dataclasses — counts + per-field mismatch records.

**Field→source mapping:** cached fields (`market_cap`, `current_price`, `week_change`, `pct_from_52w_high/low`, `thirty_day_return_pct`, `earnings_week_move_pct`, `week_high/low`) are compared against the `ticker_metrics`/`ticker_market_cap` tables; price-derived fields are recomputed from `load_prices()`; earnings-derived fields from `load_earnings()`. Empty report fields are re-verified against the raw source to confirm they are genuinely empty (not a bug).

**Cache-versioning:** when `upcoming-results` generates a report, it also writes a `.cache.json` sidecar capturing the earnings max date, price-metrics as_of_date, and market-cap fetch timestamp per ticker. The checker reads this sidecar and flags `earnings_cache` / `price_metrics_cache` inconsistencies if the underlying cache changed between report generation and checking (stale report detection).

**Entry points:** `--check` flag on `upcoming-results`; standalone `check-report --csv <path>` CLI command.

## `reports/render.py`
**Templates:** Loaded from `earnings_engine/reports/templates/` via `_load_template()` with in-memory caching. Placeholders substituted via `_render_template(name, **values)` using simple string replacement.

**Template files:**
- `predictions_page.html` — predictions report page
- `earnings_report_page.html` — earnings watch report page (CSS + ledger table header)
- `card.html` — per-stock card with metrics, quality rating, take
- `result_row.html` — single table row for ledger
- `dashboard.html` — interactive dashboard (Results, Swing, Kronos, Watchlist tabs)

**Per-day color grouping + ranking helpers:**
- `_DAY_COLORS` — 8-color dark-theme palette (blue, green, amber, pink, purple, orange, teal, red; cycles after 8 days)
- `_assign_day_classes(enriched) -> dict[str, str]` — maps each distinct `earnings_date` (YYYY-MM-DD) to a CSS class `day-0`..`day-7`
- `_build_day_legend(day_classes) -> str` — HTML legend strip with date→color chips
- `_sort_per_day(enriched) -> pd.DataFrame` — groups rows by `earnings_date`, sorts each day's sublist best→worst by momentum (`thirty_day_return_pct + earnings_week_move_pct`), tie-broken by `prev_3q_earnings_score` then `market_cap`

**Functions:**
- `render_predictions(preds, name="predictions") -> tuple[Path, Path]` — CSV + HTML
- `render_dashboard(html_path=None) -> Path` — render interactive dashboard
- `render_upcoming_results_report(enriched, csv_path=None, html_path=None) -> Path` — applies per-day sorting + color grouping, renders ledger + cards with `{day_class}` tinting and a `{day_legend}` header

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