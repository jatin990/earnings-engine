"""Recent-earnings moves grouped by industry for the Industries dashboard tab.

For every earnings result in the recent window (default: past ~2 months), this
computes the realized high/low move over the 7 trading days after the result
date (relative to the close just before the result), using the SAME shared
helper as the report and the rest of the dashboard.  Rows are then grouped by
industry, sorted best-to-worst within each industry, and a single "best"
industry (most positive outcomes) is identified for highlighting.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from earnings_engine.config import Settings
from earnings_engine.data import industry as industry_mod
from earnings_engine.data import prices as prices_mod
from earnings_engine.data.earnings import _connect as _earnings_connect
from earnings_engine.data.market_context import _week_high_low_around


def _load_recent_earnings(tickers: list[str], settings: Settings, lookback_days: int = 60) -> list[tuple[str, pd.Timestamp]]:
    """Return (ticker, earnings_date) pairs for past results within the window."""
    if not tickers:
        return []
    today = pd.Timestamp.today().normalize()
    start = (today - pd.Timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    end = today.strftime("%Y-%m-%d")
    placeholders = ",".join("?" for _ in tickers)
    with _earnings_connect(settings) as connection:
        rows = connection.execute(
            f"""
            SELECT DISTINCT ticker, earnings_date
            FROM earnings_history
            WHERE ticker IN ({placeholders})
              AND earnings_date >= ? AND earnings_date < ?
            """,
            tickers + [start, end],
        ).fetchall()
    return [(t, pd.Timestamp(d)) for t, d in rows]


def get_recent_earnings_moves(tickers: list[str], settings: Settings, lookback_days: int = 60) -> list[dict[str, Any]]:
    """Return per-result move rows using the shared +7-day high/low helper.

    Each row contains: ticker, earnings_date, high_pct, low_pct, high_price,
    low_price, high_date, low_date.  high/low are the max/min close over the 7
    trading days after the result vs the close just before the result.
    """
    events = _load_recent_earnings(tickers, settings, lookback_days=lookback_days)
    rows: list[dict[str, Any]] = []

    # Load prices once per unique ticker (cached SQLite).
    price_map: dict[str, pd.DataFrame] = {}
    for ticker in sorted({t for t, _ in events}):
        try:
            price_map[ticker] = prices_mod.load_prices(ticker, settings)
        except Exception:
            price_map[ticker] = pd.DataFrame()

    for ticker, edate in events:
        prices = price_map.get(ticker)
        week_data = _week_high_low_around(prices, edate) if prices is not None and not prices.empty else None
        if week_data is None:
            high_pct = low_pct = high_price = low_price = None
            high_date = low_date = None
        else:
            high_pct, low_pct, high_price, low_price, high_date, low_date = week_data
        rows.append({
            "ticker": ticker,
            "earnings_date": edate.strftime("%Y-%m-%d"),
            "high_pct": high_pct,
            "low_pct": low_pct,
            "high_price": high_price,
            "low_price": low_price,
            "high_date": high_date.strftime("%Y-%m-%d") if high_date is not None else None,
            "low_date": low_date.strftime("%Y-%m-%d") if low_date is not None else None,
        })
    return rows


def group_by_industry(moves: list[dict[str, Any]], industry_map: dict[str, str]) -> list[dict[str, Any]]:
    """Group moves by industry and sort each industry best->worst by high_pct.

    Returns a list of dicts, each with: industry, rows (sorted desc by high_pct),
    count, positive_count, avg_high_pct.
    """
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in moves:
        ind = industry_map.get(row["ticker"]) or "Other"
        groups.setdefault(ind, []).append(row)

    result: list[dict[str, Any]] = []
    for ind, ind_rows in groups.items():
        sorted_rows = sorted(
            ind_rows,
            key=lambda r: (r["high_pct"] if r["high_pct"] is not None else float("-inf")),
            reverse=True,
        )
        valid = [r for r in ind_rows if r["high_pct"] is not None]
        positive_count = sum(1 for r in valid if r["high_pct"] > 0)
        avg_high = (sum(r["high_pct"] for r in valid) / len(valid)) if valid else 0.0
        result.append({
            "industry": ind,
            "rows": sorted_rows,
            "count": len(sorted_rows),
            "positive_count": positive_count,
            "avg_high_pct": avg_high,
        })
    return result


def pick_best_industry(groups: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Return the industry group with the most positive outcomes.

    Ties are broken by higher average high move.
    """
    if not groups:
        return None
    return max(
        groups,
        key=lambda g: (g["positive_count"], round(g["avg_high_pct"], 6)),
    )
