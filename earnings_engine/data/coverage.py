"""Data coverage reporting for the earnings-engine UI.

Runs a single SQL query over the shared prices SQLite database to report
per-ticker price/earnings data ranges, row counts, and freshness. The result
is filtered to a requested ticker list so the dashboard can show coverage
for any universe (IN, US, NSE_ALL, NSE_LARGE_CAP, watchlist, etc.).
"""

from __future__ import annotations

import sqlite3
from typing import Any

from earnings_engine.config import Settings
from earnings_engine.data.prices import _cache_path


def get_data_coverage(tickers: list[str], settings: Settings | None = None) -> dict[str, Any]:
    """Return per-ticker data coverage for the requested ticker list.

    Runs a single SQL query with LEFT JOINs across ``price_history``,
    ``earnings_history`` and ``earnings_freshness`` grouped by ticker, then
    filters to the requested tickers.

    The result contains:

    - ``total``: number of requested tickers
    - ``with_prices``: how many of those have price rows
    - ``with_earnings``: how many of those have earnings rows
    - ``rows``: one entry per ticker with:
        - ``ticker``
        - ``price_start`` / ``price_end`` / ``price_rows``
        - ``earnings_start`` / ``earnings_end`` / ``earnings_rows`` (across all sources)
        - ``has_prices`` / ``has_earnings``
        - ``listing_date`` (price_history MIN(date), used as a listing-date proxy)
        - ``earnings_fresh`` (from earnings_freshness)
    """
    settings = settings or Settings()
    db_path = _cache_path(settings)
    total = len(tickers)

    if not db_path.exists() or not tickers:
        return {
            "total": total,
            "with_prices": 0,
            "with_earnings": 0,
            "rows": [],
        }

    placeholders = ",".join("?" for _ in tickers)

    # Per-ticker stats from price_history + earnings_history, plus freshness.
    query = f"""
        SELECT
            p.ticker,
            p.price_start,
            p.price_end,
            p.price_rows,
            e.earnings_start,
            e.earnings_end,
            e.earnings_rows,
            CASE WHEN p.ticker IS NOT NULL THEN 1 ELSE 0 END AS has_prices,
            CASE WHEN e.earnings_rows IS NOT NULL THEN 1 ELSE 0 END AS has_earnings,
            p.price_start AS listing_date,
            CASE WHEN f.ticker IS NOT NULL THEN 1 ELSE 0 END AS earnings_fresh
        FROM (
            SELECT ticker, MIN(date) AS price_start, MAX(date) AS price_end,
                   COUNT(*) AS price_rows
            FROM price_history
            WHERE ticker IN ({placeholders})
            GROUP BY ticker
        ) p
        LEFT JOIN (
            SELECT ticker, MIN(earnings_date) AS earnings_start,
                   MAX(earnings_date) AS earnings_end, COUNT(*) AS earnings_rows
            FROM earnings_history
            WHERE ticker IN ({placeholders})
            GROUP BY ticker
        ) e ON e.ticker = p.ticker
        LEFT JOIN earnings_freshness f ON f.ticker = p.ticker
    WHERE p.ticker IS NOT NULL
    """

    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute(query, tickers + tickers)
        rows = cur.fetchall()
    except sqlite3.Error:
        return {
            "total": total,
            "with_prices": 0,
            "with_earnings": 0,
            "rows": [],
        }
    finally:
        conn.close()

    by_ticker: dict[str, Any] = {}
    for (
        ticker, price_start, price_end, price_rows,
        earnings_start, earnings_end, earnings_rows,
        has_prices, has_earnings, listing_date, earnings_fresh,
    ) in rows:
        by_ticker[ticker] = {
            "ticker": ticker,
            "price_start": price_start,
            "price_end": price_end,
            "price_rows": price_rows,
            "earnings_start": earnings_start,
            "earnings_end": earnings_end,
            "earnings_rows": earnings_rows if earnings_rows is not None else 0,
            "has_prices": bool(has_prices),
            "has_earnings": bool(has_earnings),
            "listing_date": listing_date,
            "earnings_fresh": bool(earnings_fresh),
        }

    # Preserve requested order, filling in tickers with no data at all.
    result_rows = []
    for ticker in tickers:
        result_rows.append(by_ticker.get(ticker, {
            "ticker": ticker,
            "price_start": None,
            "price_end": None,
            "price_rows": 0,
            "earnings_start": None,
            "earnings_end": None,
            "earnings_rows": 0,
            "has_prices": False,
            "has_earnings": False,
            "listing_date": None,
            "earnings_fresh": False,
        }))

    return {
        "total": total,
        "with_prices": sum(1 for r in result_rows if r["has_prices"]),
        "with_earnings": sum(1 for r in result_rows if r["has_earnings"]),
        "rows": result_rows,
    }