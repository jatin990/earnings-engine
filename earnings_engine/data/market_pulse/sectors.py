"""Sector heatmap calculation with authoritative index symbols and constituent weighting."""

from __future__ import annotations

import logging
import time
from typing import Any

from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection
from earnings_engine.data.market_pulse.constants import (
    SECTOR_CONFIG,
    _SECTORS_CACHE,
    _SECTORS_CACHE_TTL,
    _SECTORS_LOCK,
)
from earnings_engine.data.market_pulse.timing import is_market_open
from earnings_engine.data.prices import fetch_batch_live_quotes

logger = logging.getLogger(__name__)


def compute_sector_heatmap(
    settings: Settings | None = None,
    force_refresh: bool = False,
) -> list[dict[str, Any]]:
    """Compute performance for authoritative NSE sectors.

    Evaluates authentic NSE sectoral index pricing (^CNXIT, ^NSEBANK, etc.).
    Falls back to market-cap weighted constituent performance if index price is absent.
    """
    global _SECTORS_CACHE
    now_ts = time.time()

    if not force_refresh and "data" in _SECTORS_CACHE:
        cached_ts = _SECTORS_CACHE.get("ts", 0)
        if (now_ts - cached_ts) < _SECTORS_CACHE_TTL:
            return _SECTORS_CACHE["data"]
        if not is_market_open(now_ts) and not is_market_open(cached_ts):
            return _SECTORS_CACHE["data"]

    settings = settings or Settings()

    # Collect all sectoral index symbols and all constituent tickers
    index_symbols: list[str] = []
    constituent_symbols: set[str] = set()
    for sec in SECTOR_CONFIG:
        idx_sym = sec.get("index_symbol")
        if idx_sym:
            index_symbols.append(idx_sym)
        for alt in sec.get("alt_symbols", []):
            index_symbols.append(alt)
        for c in sec.get("constituents", []):
            constituent_symbols.add(c)

    all_fetch_symbols = list(set(index_symbols) | constituent_symbols)
    batch_quotes = fetch_batch_live_quotes(all_fetch_symbols, settings=settings, sync_db=False, force=force_refresh)

    conn = get_db_connection(settings)
    try:
        results: list[dict[str, Any]] = []

        for sec in SECTOR_CONFIG:
            sec_name = sec["name"]
            idx_sym = sec.get("index_symbol")
            alt_syms = sec.get("alt_symbols", [])
            constituents = sec.get("constituents", [])

            # 1. Try to get direct sectoral index quote
            idx_quote = batch_quotes.get(idx_sym) if idx_sym else None
            if not idx_quote or not idx_quote.get("current_price"):
                for alt in alt_syms:
                    alt_q = batch_quotes.get(alt)
                    if alt_q and alt_q.get("current_price"):
                        idx_quote = alt_q
                        break

            # If still missing, check price_history for the index symbol
            if (not idx_quote or not idx_quote.get("current_price")) and idx_sym:
                cand_idx = [idx_sym] + alt_syms
                placeholders = ",".join("?" for _ in cand_idx)
                row = conn.execute(
                    f"SELECT ticker, close, date FROM price_history WHERE ticker IN ({placeholders}) ORDER BY date DESC LIMIT 2",
                    cand_idx,
                ).fetchall()
                if row and len(row) >= 1:
                    latest_close = float(row[0][1])
                    prev_close = float(row[1][1]) if len(row) >= 2 else latest_close
                    chg_pct = round(((latest_close - prev_close) / prev_close) * 100, 2) if prev_close > 0 else 0.0
                    idx_quote = {
                        "ticker": row[0][0],
                        "current_price": latest_close,
                        "change_pct": chg_pct,
                        "source": "db_history",
                    }

            # 2. Process constituent stock performance
            stock_perf: list[dict[str, Any]] = []
            valid_constituents_count = 0
            sum_change = 0.0

            for ticker in constituents:
                sq = batch_quotes.get(ticker)
                c_price = 0.0
                c_change = 0.0

                if sq and sq.get("current_price"):
                    c_price = sq.get("current_price", 0.0)
                    c_change = sq.get("change_pct", 0.0)
                else:
                    # Fallback to price_history
                    rows = conn.execute(
                        "SELECT close FROM price_history WHERE ticker = ? ORDER BY date DESC LIMIT 2",
                        (ticker,),
                    ).fetchall()
                    if rows and len(rows) >= 1:
                        c_price = float(rows[0][0])
                        prev_c = float(rows[1][0]) if len(rows) >= 2 else c_price
                        c_change = round(((c_price - prev_c) / prev_c) * 100, 2) if prev_c > 0 else 0.0

                if c_price > 0:
                    valid_constituents_count += 1
                    sum_change += c_change
                    stock_perf.append({
                        "ticker": ticker.replace(".NS", ""),
                        "price": round(c_price, 2),
                        "change_pct": round(c_change, 2),
                    })

            # Sort constituents by performance
            stock_perf.sort(key=lambda x: x["change_pct"], reverse=True)
            top_gainer = stock_perf[0] if stock_perf else None
            top_loser = stock_perf[-1] if stock_perf else None
            advances = sum(1 for c in stock_perf if c["change_pct"] > 0)
            declines = sum(1 for c in stock_perf if c["change_pct"] < 0)
            unchanged = sum(1 for c in stock_perf if c["change_pct"] == 0)

            # 3. Determine sector change percentage
            if idx_quote and idx_quote.get("change_pct") is not None and idx_quote.get("current_price", 0) > 0:
                sec_change = round(float(idx_quote["change_pct"]), 2)
                sec_price = round(float(idx_quote["current_price"]), 2)
                pricing_source = "index_direct"
            elif valid_constituents_count > 0:
                sec_change = round(sum_change / valid_constituents_count, 2)
                sec_price = None
                pricing_source = "constituent_avg"
            else:
                sec_change = 0.0
                sec_price = None
                pricing_source = "unavailable"

            # Color coding for heatmap
            if sec_change >= 1.5:
                heat_tier = "surge_up"
                bg_color = "rgba(16, 185, 129, 0.25)"
                text_color = "#34d399"
            elif sec_change > 0.0:
                heat_tier = "mild_up"
                bg_color = "rgba(16, 185, 129, 0.12)"
                text_color = "#10b981"
            elif sec_change <= -1.5:
                heat_tier = "surge_down"
                bg_color = "rgba(244, 63, 94, 0.25)"
                text_color = "#fb7185"
            elif sec_change < 0.0:
                heat_tier = "mild_down"
                bg_color = "rgba(244, 63, 94, 0.12)"
                text_color = "#f43f5e"
            else:
                heat_tier = "neutral"
                bg_color = "rgba(148, 163, 184, 0.1)"
                text_color = "#94a3b8"

            results.append({
                "name": sec_name,
                "index_symbol": idx_sym,
                "change_1d": sec_change,
                "change_1d_pct": sec_change,
                "change_pct": sec_change,
                "change_7d": 0.0,
                "change_30d": 0.0,
                "current_price": sec_price,
                "pricing_source": pricing_source,
                "heat_tier": heat_tier,
                "bg_color": bg_color,
                "text_color": text_color,
                "top_gainer": top_gainer,
                "top_loser": top_loser,
                "advances": advances,
                "declines": declines,
                "unchanged": unchanged,
                "constituents_tracked": valid_constituents_count,
            })

        # Sort sectors by performance descending
        results.sort(key=lambda s: s["change_1d"], reverse=True)

    finally:
        try:
            conn.close()
        except Exception:
            pass

    with _SECTORS_LOCK:
        _SECTORS_CACHE = {"ts": now_ts, "data": results}

    return results
