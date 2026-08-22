# Implementation Plan

[Overview]
A new "Data Coverage" dashboard tab showing per-stock price/earnings data ranges and row counts, filterable by universe, plus an incremental earnings-fetch feature that only fetches missing earnings using listing dates derived from price history.

The dashboard currently has tabs for Results, Swing, Kronos, Watchlist, and Playground, but no way to see which stocks have price/earnings data cached, what date ranges are covered, or how many rows exist. This makes it hard to identify data gaps before running predictions or building datasets. The incremental earnings fetch solves the problem of re-downloading all 2,390 tickers' earnings when most are already cached — only tickers with missing or stale earnings are fetched, using the first price-history date as a listing-date proxy (since yfinance's `firstTradeDateEpochUtc` is None for NSE stocks).

[Types]
No new Python type system changes; the feature uses existing dict/list return patterns matching the dashboard_api conventions.

New API response shape for data coverage:
```python
# GET /api/v1/dashboard/data-coverage?market=NSE_ALL
{
  "total": 2396,
  "with_prices": 2396,
  "with_earnings": 1165,
  "rows": [
    {
      "ticker": "RELIANCE.NS",
      "price_start": "2015-01-01",
      "price_end": "2026-07-31",
      "price_rows": 2861,
      "earnings_start": "2013-05-30",
      "earnings_end": "2026-10-15",
      "earnings_rows": 24,
      "has_prices": true,
      "has_earnings": true,
      "listing_date": "2015-01-01",  # derived from price_history MIN(date)
      "earnings_fresh": true,        # from earnings_freshness table
    },
    ...
  ]
}
```

New API response for incremental earnings fetch:
```python
# POST /api/v1/dashboard/earnings/incremental
{
  "success": true,
  "total": 2396,
  "already_cached": 1165,
  "fetched": 800,
  "skipped_no_listing": 431,
  "errors": 0,
}
```

[Files]
New and modified files for the Data Coverage tab and incremental earnings fetch.

- **New**: `earnings_engine/data/coverage.py` — SQLite queries for per-ticker data coverage stats (price/earnings date ranges, row counts, listing dates)
- **Modified**: `earnings_engine/api/dashboard_api.py` — add `get_data_coverage()` and `ingest_earnings_incremental()` functions
- **Modified**: `earnings_engine/api/server.py` — add `GET /api/v1/dashboard/data-coverage` and `POST /api/v1/dashboard/earnings/incremental` endpoints
- **Modified**: `earnings_engine/reports/templates/dashboard.html` — add "📋 Data Coverage" tab with filterable table + "Fetch Missing Earnings" button
- **Modified**: `earnings_engine/data/earnings.py` — add `ingest_earnings_incremental()` function that only fetches for tickers missing earnings
- **Modified**: `earnings_engine/cli.py` — add `--incremental` flag to `ingest` command for earnings-only-missing fetch
- **New**: `tests/test_coverage.py` — tests for data coverage queries and incremental earnings fetch

[Functions]
New and modified functions.

- **New**: `get_data_coverage(tickers: list[str], settings: Settings) -> dict` in `earnings_engine/data/coverage.py`
  - Runs a single SQL JOIN query across `price_history` and `earnings_history` grouped by ticker
  - Returns per-ticker: price_start, price_end, price_rows, earnings_start, earnings_end, earnings_rows, listing_date (from price_history MIN(date)), earnings_fresh (from earnings_freshness)
  - Filters to the requested ticker list (universe-filtered)

- **New**: `ingest_earnings_incremental(tickers: list[str], settings: Settings) -> dict` in `earnings_engine/data/earnings.py`
  - Identifies tickers with NO earnings rows in `earnings_history`
  - For those, checks `price_history` for a listing date (MIN(date)) — skips tickers with no price history or listed < 90 days ago (too new for earnings)
  - Only fetches earnings for tickers that should have earnings but don't
  - Returns `{total, already_cached, fetched, skipped_no_listing, errors}`

- **New**: `get_data_coverage(market: str | None = None) -> dict` in `earnings_engine/api/dashboard_api.py`
  - Resolves tickers via `_resolve_tickers(market)`
  - Calls `coverage.get_data_coverage(tickers, settings)`
  - Returns the coverage dict for the API endpoint

- **New**: `ingest_earnings_incremental_api(market: str | None = None) -> dict` in `earnings_engine/api/dashboard_api.py`
  - Resolves tickers via `_resolve_tickers(market)`
  - Calls `earnings_mod.ingest_earnings_incremental(tickers, settings)`
  - Returns the result dict for the API endpoint

- **Modified**: `ingest` command in `earnings_engine/cli.py`
  - Add `--incremental` flag: when set with `--earnings`, only fetches tickers missing earnings data (calls `ingest_earnings_incremental` instead of `ingest_earnings`)

[Classes]
No new classes. All changes are function-level additions to existing modules.

[Dependencies]
No new dependencies. Uses existing SQLite, FastAPI, and yfinance infrastructure.

[Testing]
Test file: `tests/test_coverage.py`

- `test_get_data_coverage_returns_per_ticker_stats` — verifies price/earnings date ranges and row counts for a mock SQLite DB
- `test_get_data_coverage_filters_by_ticker_list` — verifies only requested tickers are returned
- `test_ingest_earnings_incremental_skips_cached` — verifies tickers with existing earnings are not re-fetched
- `test_ingest_earnings_incremental_skips_no_listing` — verifies tickers with no price history or listed < 90 days are skipped
- `test_ingest_earnings_incremental_fetches_missing` — verifies tickers missing earnings are fetched
- `test_data_coverage_api_endpoint` — verifies the API endpoint returns the correct shape

Existing tests should not be affected since all changes are additive (new functions, new endpoints, new tab).

[Implementation Order]
1. Create `earnings_engine/data/coverage.py` with `get_data_coverage()` SQL query function
2. Add `ingest_earnings_incremental()` to `earnings_engine/data/earnings.py`
3. Add `get_data_coverage()` and `ingest_earnings_incremental_api()` to `earnings_engine/api/dashboard_api.py`
4. Add API endpoints to `earnings_engine/api/server.py`
5. Add `--incremental` flag to `ingest` CLI command in `earnings_engine/cli.py`
6. Add "Data Coverage" tab to `earnings_engine/reports/templates/dashboard.html`
7. Create `tests/test_coverage.py` and verify all tests pass
8. Run full test suite to confirm no regressions