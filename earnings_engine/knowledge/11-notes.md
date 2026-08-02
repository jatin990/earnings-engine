# 11 — Implementation Notes

> Related: [10-data-flow](10-data-flow.md) → [12-tests](12-tests.md)

## 6.1 Point-in-Time Guarantee
All features use only data available **strictly before** the event:
- `asof_date` = last trading day before earnings
- `compute_price_features()` filters `prices.loc[prices.index <= asof_date]`
- `compute_earnings_features()` uses only `earnings_date < current` events
- Backtest folds cut by `earnings_date < fold_start`

## 6.2 Cache Freshness
- Prices: `_is_fresh()` checks if ticker has any rows in SQLite
- Earnings: `_is_fresh()` checks `earnings_freshness` table for `fetched_at` ≤ `cache_max_age_days` (default 1 day)
- Market cap: `is_market_cap_fresh()` checks `ticker_market_cap` table for `fetched_at` ≤ 1 day
- NSE_ALL list: 7-day freshness via file mtime
- NSE_LARGE_CAP list: 7-day freshness via file mtime
- `--force` flag bypasses all freshness checks

## 6.3 Multithreaded Ingestion
All three ingest functions use the same pattern:
- `ThreadPoolExecutor` with 10 workers
- Batched in groups of 50
- 2-second delay between batches (to avoid yfinance rate limits)
- Skips tickers with fresh cache (unless `--force`)
- Progress logging after each batch

## 6.4 yfinance Quirks
- NSE tickers need `.NS` suffix; `market_of()` infers from suffix
- `get_earnings_dates(limit=60)` may return None/empty → empty DataFrame cached
- `fast_info` tried first, falls back to `.info` for market cap/price/52w high-low
- Download failures are logged but don't crash ingestion
- Duplicate earnings dates from yfinance are deduplicated before SQLite insert

## 6.5 HTML Templates
- Located in `earnings_engine/reports/templates/`
- Use `{placeholder}` tokens (not Python `str.format()` to avoid CSS brace conflicts)
- Substituted via `_render_template()` using `str.replace()`
- Cached in `_TEMPLATE_CACHE` dict per process

## 6.6 Quality Rating Scale (1-9)
Computed by `_score_previous_earnings()`:
- Each quarter is scored individually via `_score_surprise()` from its own EPS surprise %
- 3Q score = average of individual quarter scores (never exceeds max individual score)
- 7-9 = strong beats, 5-6 = in line, 3-4 = missed estimates
- Used for both 1Q (lookback=1) and 3Q (lookback=3) scores

## 6.7 Week High/Low in Reports
- Per-quarter week high/low: `q1_week_high_pct`, `q1_week_low_pct`, `q1_week_high_price`, `q1_week_low_price`, etc.
- Each computed by `_week_high_low_around()` in `market_context.py` for the respective quarter's earnings date (±4 business days)
- Displayed as 2-line format in cards and ledger table:
  - Line 1: percentages with slash (e.g., `+8.7%/+0.0%`)
  - Line 2: prices in parentheses with slash (e.g., `(8,500/7,800)`)
- Uses `_fmt_hl_pair()` helper in render.py

## 6.8 52W Gap Formatting
- Shows percentages on line 1 and prices on line 2:
  - Line 1: `+0.4%/+42.9%`
  - Line 2: `(8,090/5,636)`
- Uses `_fmt_hl_pair()` in render.py (replaces old `_fmt_pct_with_price()`)
- Zero values display as `0.0%` (no `+` sign for zero)

## 6.9 EPS Data in Reports
- `eps_estimate`, `eps_reported`, `surprise_pct` are extracted from the most recent earnings event in `enrich_upcoming_results()`
- Displayed in the "Stock & Price Info" section of `card.html` as:
  - EPS Estimate: the expected EPS
  - EPS Reported: the actual reported EPS
  - Surprise: the surprise % (signed, e.g., `+12.5%`)