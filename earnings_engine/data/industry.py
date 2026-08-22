"""Industry classification for tickers, cached in SQLite.

Industries come from yfinance's ``.info`` (the ``industry`` key, with ``sector``
fallback) and are cached in the shared prices SQLite database so each ticker
only needs a single network fetch.  The Industries dashboard tab and the
``ingest-industries`` CLI command both use this module.
"""

from __future__ import annotations

import sqlite3

import pandas as pd
import yfinance as yf

from earnings_engine.config import Settings
from earnings_engine.data.prices import _cache_path
from earnings_engine.logging_utils import get_logger

logger = get_logger("earnings_engine.data.industry")

INDUSTRY_MAX_AGE_DAYS = 30


def _connect(settings: Settings) -> sqlite3.Connection:
    """Connect to the shared SQLite database and create the industry table if missing."""
    settings.ensure_dirs()
    connection = sqlite3.connect(str(_cache_path(settings)))
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS ticker_industry (
            ticker TEXT NOT NULL,
            industry TEXT,
            sector TEXT,
            fetched_at TEXT NOT NULL,
            PRIMARY KEY (ticker)
        )
        """
    )
    connection.commit()
    return connection


def _is_fresh(ticker: str, settings: Settings) -> bool:
    """Check if industry classification is fresh in SQLite for the given ticker."""
    with _connect(settings) as connection:
        row = connection.execute(
            "SELECT fetched_at FROM ticker_industry WHERE ticker = ?",
            (ticker,),
        ).fetchone()
    if not row:
        return False
    fetched_at = pd.Timestamp(row[0])
    age_days = (pd.Timestamp.now() - fetched_at).total_seconds() / 86400
    return age_days <= INDUSTRY_MAX_AGE_DAYS


def _store(ticker: str, industry: str | None, sector: str | None, settings: Settings) -> None:
    """Store (or refresh) the industry classification for a ticker."""
    now = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    with _connect(settings) as connection:
        connection.execute(
            "INSERT OR REPLACE INTO ticker_industry (ticker, industry, sector, fetched_at) VALUES (?, ?, ?, ?)",
            (ticker, industry, sector, now),
        )
        connection.commit()


def _fetch_for_ticker(ticker: str) -> tuple[str, str | None, str | None]:
    """Fetch (ticker, industry, sector) from yfinance .info, or (ticker, None, None)."""
    try:
        info = yf.Ticker(ticker).info or {}
        industry = info.get("industry")
        sector = info.get("sector")
        return (ticker, industry, sector)
    except Exception:
        return (ticker, None, None)


def load_industry(ticker: str, settings: Settings) -> str | None:
    """Load the industry for a single ticker from SQLite cache (no fetch)."""
    with _connect(settings) as connection:
        row = connection.execute(
            "SELECT industry, sector FROM ticker_industry WHERE ticker = ?",
            (ticker,),
        ).fetchone()
    if not row:
        return None
    return row[0] or row[1]


def load_industry_map(tickers: list[str], settings: Settings) -> dict[str, str]:
    """Return {ticker: industry} for the requested tickers using cached rows only.

    Tickers with no cached row are simply absent from the returned dict (no fetch).
    """
    if not tickers:
        return {}
    placeholders = ",".join("?" for _ in tickers)
    with _connect(settings) as connection:
        rows = connection.execute(
            f"SELECT ticker, industry, sector FROM ticker_industry WHERE ticker IN ({placeholders})",
            tickers,
        ).fetchall()
    return {row[0]: (row[1] or row[2]) for row in rows}


def ingest_industries(tickers: list[str], settings: Settings, force: bool = False) -> dict[str, int]:
    """Fetch + cache industry classification for the requested tickers.

    Uses ThreadPoolExecutor with 10 workers, batched in groups of 50 with
    2-second delays between batches to avoid yfinance rate limits.
    Skips tickers with fresh cache unless force=True.
    Returns {ticker: 1} for success (classified), {ticker: 0} for failure.
    """
    import time
    from concurrent.futures import ThreadPoolExecutor, as_completed

    results: dict[str, int] = {}
    total = len(tickers)
    batch_size = 50
    processed = 0

    # Filter out tickers with fresh cache (when not forcing)
    tickers_to_fetch: list[str] = []
    cached_hits = 0
    for ticker in tickers:
        if not force and _is_fresh(ticker, settings):
            cached_hits += 1
            results[ticker] = 1
            processed += 1
        else:
            tickers_to_fetch.append(ticker)

    if cached_hits == total:
        logger.info("industry cache hit for all %s tickers, skipping fetch", total)
        return results

    logger.info("ingesting industries for %s tickers (%s cached, %s to fetch)",
                total, cached_hits, len(tickers_to_fetch))

    fetch_total = len(tickers_to_fetch)
    for i in range(0, fetch_total, batch_size):
        batch = tickers_to_fetch[i:i + batch_size]
        batch_num = i // batch_size + 1
        total_batches = (fetch_total + batch_size - 1) // batch_size

        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_ticker = {
                executor.submit(_fetch_for_ticker, ticker): ticker for ticker in batch
            }
            for future in as_completed(future_to_ticker):
                ticker, industry, sector = future.result()
                processed += 1
                if industry or sector:
                    _store(ticker, industry, sector, settings)
                    results[ticker] = 1
                else:
                    results[ticker] = 0

        logger.info("industry ingest batch %s/%s complete: %s/%s tickers processed",
                    batch_num, total_batches, processed, total)

        # Wait 2 seconds between batches (skip after last batch)
        if i + batch_size < fetch_total:
            time.sleep(2)

    ok = sum(1 for v in results.values() if v > 0)
    logger.info("industry ingest complete: %s/%s tickers classified", ok, total)
    return results


def get_industry_map(tickers: list[str], settings: Settings, force: bool = False) -> dict[str, str]:
    """Return {ticker: industry} for all requested tickers, fetching missing ones.

    Cached values are returned immediately; any tickers without a cached row
    are fetched (batched) and cached on the spot.
    """
    result = load_industry_map(tickers, settings)
    missing = [t for t in tickers if t not in result]
    if missing and not force:
        ingest_industries(missing, settings)
        result.update(load_industry_map(missing, settings))
    return result
