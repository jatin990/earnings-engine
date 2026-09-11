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
from earnings_engine.data.db import get_db_connection, is_turso_enabled, _cache_path
from earnings_engine.logging_utils import get_logger

logger = get_logger("earnings_engine.data.industry")

INDUSTRY_MAX_AGE_DAYS = 30


_MIGRATIONS_APPLIED: set[str] = set()


def _connect(settings: Settings) -> Any:
    """Connect to the shared database and ensure all schema tables exist."""
    settings.ensure_dirs()
    try:
        db_key = str(_cache_path(settings))
    except Exception:
        db_key = str(getattr(settings, "db_path", "") or getattr(settings, "database_url", "") or "default")
    if db_key not in _MIGRATIONS_APPLIED:
        from earnings_engine.data.migrations import apply_migrations
        apply_migrations(settings)
        _MIGRATIONS_APPLIED.add(db_key)
    connection = get_db_connection(settings)
    return connection


def _is_fresh(ticker: str, settings: Settings) -> bool:
    """Check if industry classification is fresh in SQLite for the given ticker."""
    fresh_set = get_fresh_industry_tickers([ticker], settings)
    return ticker.strip().upper() in fresh_set


def get_fresh_industry_tickers(tickers: list[str], settings: Settings) -> set[str]:
    """Check which tickers have fresh industry classification in SQLite in batch."""
    if not tickers:
        return set()

    cleaned = [t.strip().upper() for t in tickers if t and t.strip()]
    unique_tickers = list(dict.fromkeys(cleaned))
    fresh: set[str] = set()
    now = pd.Timestamp.now()

    chunk_size = 200
    with _connect(settings) as connection:
        for i in range(0, len(unique_tickers), chunk_size):
            chunk = unique_tickers[i : i + chunk_size]
            placeholders = ",".join("?" for _ in chunk)
            rows = connection.execute(
                f"SELECT ticker, last_updated FROM tickers "
                f"WHERE ticker IN ({placeholders}) AND industry IS NOT NULL",
                chunk,
            ).fetchall()
            for r in rows:
                if r[1]:
                    fetched_at = pd.Timestamp(r[1])
                    age_days = (now - fetched_at).total_seconds() / 86400
                    if age_days <= INDUSTRY_MAX_AGE_DAYS:
                        fresh.add(r[0].strip().upper())

    return fresh


def _store_batch(items: list[tuple[str, str | None, str | None]], settings: Settings) -> None:
    """Store (or refresh) the industry classification for multiple tickers in batch."""
    if not items:
        return
    now = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    params = [(ticker, ind, sec, now) for ticker, ind, sec in items]
    with _connect(settings) as connection:
        connection.executemany(
            """
            INSERT INTO tickers (ticker, industry, sector, last_updated)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(ticker) DO UPDATE SET
                industry = excluded.industry,
                sector = excluded.sector,
                last_updated = excluded.last_updated
            """,
            params,
        )
        if hasattr(connection, "commit"):
            connection.commit()


def _store(ticker: str, industry: str | None, sector: str | None, settings: Settings) -> None:
    """Store (or refresh) the industry classification for a ticker."""
    _store_batch([(ticker, industry, sector)], settings)


def _fetch_for_ticker(ticker: str) -> tuple[str, str | None, str | None]:
    """Fetch (ticker, industry, sector) from yfinance .info, or (ticker, None, None)."""
    try:
        from earnings_engine.rate_limits import record_request
        try:
            record_request("yfinance")
        except Exception:
            pass
        info = yf.Ticker(ticker).info or {}
        industry = info.get("industry")
        sector = info.get("sector")
        return (ticker, industry, sector)
    except Exception:
        return (ticker, None, None)


def load_industry(ticker: str, settings: Settings) -> str | None:
    """Load the cached industry for a single ticker (None if not in SQLite)."""
    with _connect(settings) as connection:
        row = connection.execute(
            "SELECT industry, sector FROM tickers WHERE ticker = ?",
            (ticker,),
        ).fetchone()
    if not row or not (row[0] or row[1]):
        return None
    return row[0] or row[1]


def load_industry_map(tickers: list[str], settings: Settings) -> dict[str, str]:
    """Return {ticker: industry} for the requested tickers using cached rows only.

    Tickers with no cached row are simply absent from the returned dict (no fetch).
    """
    if not tickers:
        return {}

    cleaned = [t.strip().upper() for t in tickers if t and t.strip()]
    unique_tickers = list(dict.fromkeys(cleaned))

    result: dict[str, str] = {}
    CHUNK_SIZE = 200
    with _connect(settings) as connection:
        for i in range(0, len(unique_tickers), CHUNK_SIZE):
            chunk = unique_tickers[i : i + CHUNK_SIZE]
            placeholders = ",".join("?" for _ in chunk)
            rows = connection.execute(
                f"SELECT ticker, industry, sector FROM tickers WHERE ticker IN ({placeholders})",
                chunk,
            ).fetchall()
            if not rows:
                try:
                    rows = connection.execute(
                        f"SELECT ticker, industry, sector FROM ticker_industry WHERE ticker IN ({placeholders})",
                        chunk,
                    ).fetchall()
                except Exception:
                    rows = []

            for r in rows:
                ind = r[1] or r[2]
                if ind:
                    result[r[0].strip().upper()] = ind

    return result


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

    # Filter out tickers with fresh cache in batch (when not forcing)
    tickers_to_fetch: list[str] = []
    cached_hits = 0
    fresh_set = set() if force else get_fresh_industry_tickers(tickers, settings)
    for ticker in tickers:
        sym = ticker.strip().upper()
        if sym in fresh_set:
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

        batch_to_store: list[tuple[str, str | None, str | None]] = []
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_ticker = {
                executor.submit(_fetch_for_ticker, ticker): ticker for ticker in batch
            }
            for future in as_completed(future_to_ticker):
                ticker, industry, sector = future.result()
                processed += 1
                if industry or sector:
                    batch_to_store.append((ticker, industry, sector))
                    results[ticker] = 1
                else:
                    results[ticker] = 0

        if batch_to_store:
            _store_batch(batch_to_store, settings)

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
