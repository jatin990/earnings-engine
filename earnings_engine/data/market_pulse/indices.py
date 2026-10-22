"""Indices quotes, historical sparklines, and change calculations."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection
from earnings_engine.data.market_pulse.constants import (
    INDICES_CONFIG,
    _INDICES_CACHE,
    _INDICES_CACHE_TTL,
    _INDICES_LOCK,
)
from earnings_engine.data.market_pulse.timing import is_market_open
from earnings_engine.data.prices import fetch_batch_live_quotes

logger = logging.getLogger(__name__)


def compute_indices_quotes(
    settings: Settings | None = None,
    force_refresh: bool = False,
) -> list[dict[str, Any]]:
    """Retrieve live / latest quote for all configured indices with performance deltas.

    Returns:
        List of dicts containing index symbol, name, price, changes (1D, 7D, 30D),
        and 10-point sparkline array.
    """
    global _INDICES_CACHE
    now_ts = time.time()

    if not force_refresh and "data" in _INDICES_CACHE:
        cached_ts = _INDICES_CACHE.get("ts", 0)
        if (now_ts - cached_ts) < _INDICES_CACHE_TTL:
            return _INDICES_CACHE["data"]
        if not is_market_open(now_ts) and not is_market_open(cached_ts):
            return _INDICES_CACHE["data"]

    settings = settings or Settings()

    # Collect all primary symbols plus alt symbols for batch fetching
    all_symbols: list[str] = []
    for idx in INDICES_CONFIG:
        all_symbols.append(idx["symbol"])
        for alt in idx.get("alt_symbols", []):
            all_symbols.append(alt)

    # Batch fetch live quotes
    batch_quotes = fetch_batch_live_quotes(all_symbols, settings=settings, sync_db=False, force=force_refresh)

    results: list[dict[str, Any]] = []

    conn = get_db_connection(settings)
    try:
        for idx in INDICES_CONFIG:
            sym = idx["symbol"]
            alt_syms = idx.get("alt_symbols", [])
            q = batch_quotes.get(sym)

            # Try alternate symbols if primary returned no quote
            matched_sym = sym
            if not q or not q.get("current_price"):
                for alt in alt_syms:
                    alt_q = batch_quotes.get(alt)
                    if alt_q and alt_q.get("current_price"):
                        q = alt_q
                        matched_sym = alt
                        break

            # If still no quote from batch, check SQLite price_history directly
            if not q or not q.get("current_price"):
                candidate_symbols = [sym] + alt_syms
                placeholders = ",".join("?" for _ in candidate_symbols)
                row = conn.execute(
                    f"SELECT ticker, close, date FROM price_history WHERE ticker IN ({placeholders}) ORDER BY date DESC LIMIT 1",
                    candidate_symbols,
                ).fetchone()
                if row:
                    q = {
                        "ticker": row[0],
                        "current_price": float(row[1]),
                        "change_pct": 0.0,
                        "change_amount": 0.0,
                        "timestamp": row[2],
                        "source": "db_history",
                    }
                    matched_sym = row[0]

            price = q.get("current_price", 0.0) if q else 0.0
            change_1d_pct = q.get("change_pct", 0.0) if q else 0.0
            change_1d_pts = q.get("change_amount", 0.0) if q else 0.0

            # Compute historical 7D, 30D, and 10-point sparkline from price_history
            sparkline: list[float] = []
            change_7d_pct = 0.0
            change_30d_pct = 0.0

            try:
                candidate_symbols = [sym, matched_sym] + alt_syms
                # Deduplicate while preserving order
                seen: set[str] = set()
                cand_unique: list[str] = []
                for s in candidate_symbols:
                    if s not in seen:
                        seen.add(s)
                        cand_unique.append(s)

                placeholders = ",".join("?" for _ in cand_unique)
                hist_rows = conn.execute(
                    f"SELECT close, date FROM price_history WHERE ticker IN ({placeholders}) ORDER BY date DESC LIMIT 35",
                    cand_unique,
                ).fetchall()

                if hist_rows:
                    closes = [float(r[0]) for r in hist_rows if r[0] is not None]
                    if closes:
                        # Sparkline: up to 10 points in chronological order
                        sample_step = max(1, len(closes) // 10)
                        sample_closes = closes[::sample_step][:10]
                        sample_closes.reverse()
                        sparkline = sample_closes

                        # If live price exists and is different from latest close, append it
                        if price > 0 and (not sparkline or sparkline[-1] != price):
                            sparkline.append(price)
                            if len(sparkline) > 10:
                                sparkline.pop(0)

                        latest_close = closes[0]
                        if len(closes) >= 5 and closes[4] > 0:
                            change_7d_pct = round(((latest_close - closes[4]) / closes[4]) * 100, 2)
                        if len(closes) >= 20 and closes[19] > 0:
                            change_30d_pct = round(((latest_close - closes[19]) / closes[19]) * 100, 2)
            except Exception as e:
                logger.debug("Failed computing sparkline for %s: %s", sym, e)

            # Determine badge styling
            if change_1d_pct > 0:
                badge_color = "emerald"
                trend = "up"
            elif change_1d_pct < 0:
                badge_color = "rose"
                trend = "down"
            else:
                badge_color = "neutral"
                trend = "flat"

            as_of_val = q.get("timestamp") if q else None
            if not as_of_val:
                as_of_val = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

            # Determine freshness
            freshness = "Live" if is_market_open(now_ts) else "EOD"

            results.append({
                "name": idx["name"],
                "symbol": sym,
                "category": idx.get("category", ""),
                "type": idx["type"],
                "weight": idx.get("weight", 0.0),
                "base": idx.get("base", 0.0),
                "price": round(price, 2) if price else 0.0,
                "current_price": round(price, 2) if price else 0.0,
                "change_1d_pct": round(change_1d_pct, 2) if change_1d_pct else 0.0,
                "change_pct": round(change_1d_pct, 2) if change_1d_pct else 0.0,
                "change_1d_pts": round(change_1d_pts, 2) if change_1d_pts else 0.0,
                "change_amount": round(change_1d_pts, 2) if change_1d_pts else 0.0,
                "change_7d_pct": round(change_7d_pct, 2) if change_7d_pct else 0.0,
                "change_7d": round(change_7d_pct, 2) if change_7d_pct else 0.0,
                "change_30d_pct": round(change_30d_pct, 2) if change_30d_pct else 0.0,
                "change_30d": round(change_30d_pct, 2) if change_30d_pct else 0.0,
                "sparkline": sparkline,
                "trend": trend,
                "badge_color": badge_color,
                "as_of": as_of_val,
                "freshness": freshness,
            })
    finally:
        try:
            conn.close()
        except Exception:
            pass

    with _INDICES_LOCK:
        _INDICES_CACHE = {"ts": now_ts, "data": results}

    return results
