"""Price history fetching and return calculation for Institutional Accumulation."""

from __future__ import annotations

import logging
import os
import time
from typing import Any

from earnings_engine.config import Settings
from earnings_engine.data.db import is_server_environment
from earnings_engine.data.db_helpers import normalize_nse_ticker, strip_nse_suffix

logger = logging.getLogger(__name__)

_TICKER_RETURNS_MEMO: dict[str, tuple[float, tuple[float | None, float | None, float | None]]] = {}


def _fetch_price_history(conn: Any, sym: str, limit: int | None = None) -> list[Any]:
    """Fetch (date, close) records for ticker with automatic .NS / bare symbol fallback."""
    limit_clause = f" LIMIT {int(limit)}" if limit is not None else ""
    sql = f"SELECT date, close FROM price_history WHERE ticker = ? ORDER BY date DESC{limit_clause}"
    rows = conn.execute(sql, (sym,)).fetchall()
    if not rows and (sym.endswith(".NS") or sym.endswith(".BO")):
        rows = conn.execute(sql, (strip_nse_suffix(sym),)).fetchall()
    return rows


def _get_ticker_returns(sym: str, conn: Any) -> tuple[float | None, float | None, float | None]:
    """Compute 7-day, 30-day, and 1-year percentage returns directly from price_history with fast memoization."""
    if not sym:
        return None, None, None

    target_sym = normalize_nse_ticker(sym)
    now = time.time()
    if target_sym in _TICKER_RETURNS_MEMO:
        exp, val = _TICKER_RETURNS_MEMO[target_sym]
        if now < exp:
            return val

    try:
        rows = _fetch_price_history(conn, target_sym, limit=260)

        if not rows or len(rows) < 2:
            # Fallback: try on-demand fetch_prices for missing symbols (skip in serverless to prevent blocking timeouts)
            is_serverless = is_server_environment() or os.environ.get("VERCEL") == "1" or os.environ.get("SERVERLESS") == "1"
            if not is_serverless:
                try:
                    from earnings_engine.data.prices import fetch_prices
                    df = fetch_prices(target_sym, force=False)
                    if df is not None and not df.empty and "close" in df.columns:
                        rows = _fetch_price_history(conn, target_sym, limit=260)
                except Exception as e:
                    logger.debug("Failed on-demand fetch_prices in _get_ticker_returns for %s: %s", target_sym, e)

        if not rows or len(rows) < 2:
            _TICKER_RETURNS_MEMO[target_sym] = (now + 600.0, (None, None, None))
            return None, None, None

        latest_close = float(rows[0][1] or 0.0)
        if latest_close <= 0:
            _TICKER_RETURNS_MEMO[target_sym] = (now + 600.0, (None, None, None))
            return None, None, None

        idx_7d = min(5, len(rows) - 1)
        prior_7d = float(rows[idx_7d][1] or 0.0)
        ret_7d = round(((latest_close - prior_7d) / prior_7d) * 100.0, 2) if prior_7d > 0 else None

        idx_30d = min(21, len(rows) - 1)
        prior_30d = float(rows[idx_30d][1] or 0.0)
        ret_30d = round(((latest_close - prior_30d) / prior_30d) * 100.0, 2) if prior_30d > 0 else None

        idx_1y = min(252, len(rows) - 1)
        prior_1y = float(rows[idx_1y][1] or 0.0)
        ret_1y = round(((latest_close - prior_1y) / prior_1y) * 100.0, 2) if prior_1y > 0 else None

        res = (ret_7d, ret_30d, ret_1y)
        _TICKER_RETURNS_MEMO[target_sym] = (now + 600.0, res)
        return res
    except Exception:
        return None, None, None


def _get_ticker_returns_batch(
    symbols: list[str],
    conn: Any = None,
    settings: Settings | None = None,
) -> dict[str, tuple[float | None, float | None, float | None]]:
    """Compute (ret_7d, ret_30d, ret_1y) for multiple tickers in batch with caching."""
    now = time.time()
    results: dict[str, tuple[float | None, float | None, float | None]] = {}
    missing: list[str] = []

    for sym in symbols:
        if not sym:
            continue
        target_sym = normalize_nse_ticker(sym)
        if target_sym in _TICKER_RETURNS_MEMO:
            exp, val = _TICKER_RETURNS_MEMO[target_sym]
            if now < exp:
                results[sym] = val
                results[target_sym] = val
                continue
        missing.append(target_sym)

    if missing:
        from earnings_engine.data.prices import load_prices_batch
        settings = settings or Settings()
        unique_missing = list(set(missing))
        dfs = load_prices_batch(unique_missing, settings=settings, days=400)
        for target_sym in unique_missing:
            df = dfs.get(target_sym)
            if df is None or df.empty or "close" not in df.columns or len(df) < 2:
                if conn:
                    res = _get_ticker_returns(target_sym, conn)
                else:
                    res = (None, None, None)
            else:
                closes = df["close"].dropna().values
                latest_close = float(closes[-1])
                if latest_close <= 0 or len(closes) < 2:
                    res = (None, None, None)
                else:
                    idx_7d = max(0, len(closes) - 1 - min(5, len(closes) - 1))
                    prior_7d = float(closes[idx_7d])
                    ret_7d = round(((latest_close - prior_7d) / prior_7d) * 100.0, 2) if prior_7d > 0 else None

                    idx_30d = max(0, len(closes) - 1 - min(21, len(closes) - 1))
                    prior_30d = float(closes[idx_30d])
                    ret_30d = round(((latest_close - prior_30d) / prior_30d) * 100.0, 2) if prior_30d > 0 else None

                    idx_1y = max(0, len(closes) - 1 - min(252, len(closes) - 1))
                    prior_1y = float(closes[idx_1y])
                    ret_1y = round(((latest_close - prior_1y) / prior_1y) * 100.0, 2) if prior_1y > 0 else None

                    res = (ret_7d, ret_30d, ret_1y)
            _TICKER_RETURNS_MEMO[target_sym] = (now + 600.0, res)
            results[target_sym] = res

    for sym in symbols:
        if not sym:
            continue
        target_sym = normalize_nse_ticker(sym)
        if sym not in results and target_sym in results:
            results[sym] = results[target_sym]

    return results
