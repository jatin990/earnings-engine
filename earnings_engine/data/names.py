"""Persistent ticker → display-name index for name + symbol search.

Company names are not part of the symbol-only universe files.  They are
gathered from two sources and stored in the shared SQLite DB
(``prices.sqlite3``, ``ticker_names`` table):

* **NSE** — the nsetools symbol→name map (one bulk call covers the whole NSE
  listing, so name-based search works across the full ``nse_all`` universe).
* **US / fallback** — the symbol itself is used as the display name initially,
  then enriched lazily from yfinance by ``market_context.enrich_upcoming_results``
  (which already resolves company names at report time).

``search()`` matches BOTH the name and the symbol (case-insensitive substring),
ranking name matches first so the dashboards can offer "search by stock name
primarily" as requested.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from typing import Any

from earnings_engine.config import Settings, market_of
from earnings_engine.data.db import get_db_connection, is_turso_enabled, _cache_path

logger = logging.getLogger("earnings_engine.data.names")

# In-process guard so we only hit nsetools once per process (it is slow / network).
_seeded: bool = False
_migrations_applied: bool = False
_NAME_CACHE: dict[str, str] = {}


def _connect(settings: Settings) -> Any:
    global _migrations_applied
    settings.ensure_dirs()
    if not _migrations_applied:
        try:
            from earnings_engine.data.migrations import apply_migrations
            apply_migrations(settings)
            _migrations_applied = True
        except Exception as e:
            logger.debug("names: apply_migrations skipped/warning: %s", e)
    return get_db_connection(settings)


def get_name(ticker: str, settings: Settings | None = None) -> str | None:
    """Return the stored display name for a ticker, or None."""
    if not ticker:
        return None
    clean_sym = ticker.strip().upper()
    if clean_sym in _NAME_CACHE:
        return _NAME_CACHE[clean_sym]

    settings = settings or Settings()
    try:
        with _connect(settings) as conn:
            row = conn.execute(
                "SELECT name FROM tickers WHERE ticker = ?", (clean_sym,)
            ).fetchone()
        name = row[0] if row and row[0] else None
        if name:
            _NAME_CACHE[clean_sym] = name
        return name
    except Exception as e:
        logger.debug("get_name failed for %s: %s", clean_sym, e)
        return None


def store_name(
    ticker: str,
    name: str,
    source: str = "yfinance",
    settings: Settings | None = None,
) -> str | None:
    """Persist a display name for a ticker in unified tickers master table."""
    settings = settings or Settings()
    ticker = ticker.strip().upper()
    name = (name or "").strip()
    if not ticker or not name:
        return None
    _NAME_CACHE[ticker] = name
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with _connect(settings) as conn:
            conn.execute(
                """
                INSERT INTO tickers (ticker, name, last_updated)
                VALUES (?, ?, ?)
                ON CONFLICT(ticker) DO UPDATE SET
                    name = COALESCE(excluded.name, tickers.name),
                    last_updated = excluded.last_updated
                """,
                (ticker, name, now_str),
            )
            conn.commit()
    except Exception as e:  # never break downstream enrichment on a name write
        logger.warning("store_name failed ticker=%s: %s", ticker, e)
        return None
    return name


def ensure_names(
    tickers: list[str],
    settings: Settings | None = None,
    force: bool = False,
) -> None:
    """Backfill missing display names for the given tickers.

    NSE symbols are populated from the nsetools map (done once per process);
    everything else (US / unlisted) falls back to the symbol-as-name and is
    enriched lazily by yfinance during report enrichment.
    """
    global _seeded
    settings = settings or Settings()
    tickers = [t.strip().upper() for t in tickers if t and t.strip()]
    if not tickers:
        return

    # Missing = not yet in the DB.
    missing: list[str] = []
    if force or not _cache_path(settings).exists():
        missing = tickers
    else:
        try:
            with _connect(settings) as conn:
                rows = conn.execute("SELECT ticker FROM tickers WHERE name IS NOT NULL").fetchall()
            known = {r[0] for r in rows}
            missing = [t for t in tickers if t not in known]
        except Exception:
            missing = tickers

    # US / fallback names come cheaply (symbol-as-name) — store immediately.
    for t in missing:
        if market_of(t) != "IN":
            store_name(t, t, source="symbol", settings=settings)

    nse_missing = [t for t in missing if market_of(t) == "IN"]
    if not nse_missing:
        return
    if _seeded:
        # Already tried nsetools this process; skip the (slow) network call.
        for t in nse_missing:
            store_name(t, t, source="symbol", settings=settings)
        return
    _seeded = True

    nse_map: dict[str, str] = {}
    try:
        from nsetools import Nse  # type: ignore

        nse_map = Nse().get_stock_codes()  # {SYMBOL: "Company Name"}
    except Exception as e:
        logger.warning("names: nsetools index unavailable: %s", e)
        nse_map = {}

    for t in nse_missing:
        sym = t[:-3] if t.endswith((".NS", ".BO")) else t
        name = nse_map.get(sym) if nse_map else None
        if name:
            store_name(t, name, source="nsetools", settings=settings)
        else:
            store_name(t, t, source="symbol", settings=settings)


def search(q: str, limit: int = 20, settings: Settings | None = None) -> list[dict[str, Any]]:
    """Match ``q`` against both name and symbol (case-insensitive substring).

    Returns ``[{symbol, name, market}]`` with name matches ranked before symbol
    matches so name-based search is the primary experience.
    """
    settings = settings or Settings()
    query = (q or "").strip().upper()
    if not query:
        return []
    rows: list[tuple[str, str]] = []
    with _connect(settings) as conn:
        rows = conn.execute("SELECT ticker, name FROM tickers WHERE name IS NOT NULL").fetchall()

    name_hits: list[str] = []
    symbol_hits: list[str] = []
    seen: set[str] = set()
    for ticker, name in rows:
        n = (name or "").upper()
        if query in n:
            if ticker not in seen:
                seen.add(ticker)
                name_hits.append(ticker)
        elif query in ticker:
            if ticker not in seen:
                seen.add(ticker)
                symbol_hits.append(ticker)

    by_ticker = {t: n for t, n in rows}
    results: list[dict[str, Any]] = []
    for t in name_hits + symbol_hits:
        results.append(
            {
                "symbol": t,
                "name": by_ticker.get(t) or t,
                "market": "NSE" if market_of(t) == "IN" else "US",
            }
        )
        if len(results) >= limit:
            break
    return results
