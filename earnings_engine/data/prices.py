"""SQLite-backed price data access and ingestion."""

from __future__ import annotations

import json
import math
import sqlite3
import threading
import time
from datetime import datetime, time as dt_time, timedelta, timezone
from pathlib import Path
from typing import Any

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None  # type: ignore

import pandas as pd
import yfinance as yf

import os
import shutil

from earnings_engine.config import Settings, market_of
from earnings_engine.data.db import get_db_connection, is_turso_enabled, _cache_path
from earnings_engine.data.trading_calendar import (
    is_trading_day,
    is_market_holiday,
    get_latest_completed_trading_day,
    is_indian_market_open,
)
from earnings_engine.logging_utils import get_logger

logger = get_logger("earnings_engine.data.prices")

COLUMNS = ["open", "high", "low", "close", "volume"]

_PRICE_DF_MEMORY_CACHE: dict[str, tuple[float, pd.DataFrame]] = {}
_PRICE_CACHE_LOCK = threading.Lock()
_PRICE_CACHE_TTL_SECONDS = 120.0

_LIVE_QUOTE_MEMORY_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_LIVE_QUOTE_CACHE_LOCK = threading.Lock()


def get_cached_live_quote(
    ticker: str,
    session: dict[str, Any] | None = None,
    ttl_minutes: int = 5,
) -> dict[str, Any] | None:
    """Retrieve in-memory cached live quote if valid according to market session rules."""
    sym = canonical_symbol(ticker)
    now = time.monotonic()
    with _LIVE_QUOTE_CACHE_LOCK:
        item = _LIVE_QUOTE_MEMORY_CACHE.get(sym)
        if not item:
            return None
        ts, quote = item
        if not quote or quote.get("current_price") is None or float(quote.get("current_price") or 0) <= 0:
            return None
        if session is None:
            session = _get_market_session_status(sym)
        is_weekend = session.get("is_weekend", False)
        # On weekends, settled quote for Friday close is valid for the entire weekend once fetched
        if is_weekend:
            return dict(quote)
        # During market hours, enforce ttl_minutes
        if session.get("is_open", False):
            if now - ts <= (ttl_minutes * 60):
                return dict(quote)
            del _LIVE_QUOTE_MEMORY_CACHE[sym]
            return None
        # Closed / pre / post market: valid for 15 minutes
        if now - ts <= (15 * 60):
            return dict(quote)
        del _LIVE_QUOTE_MEMORY_CACHE[sym]
        return None


def set_cached_live_quote(ticker: str, quote: dict[str, Any]) -> None:
    """Store in-memory cached live quote with current monotonic timestamp."""
    if not quote or quote.get("current_price") is None:
        return
    sym = canonical_symbol(ticker)
    now = time.monotonic()
    with _LIVE_QUOTE_CACHE_LOCK:
        _LIVE_QUOTE_MEMORY_CACHE[sym] = (now, dict(quote))


def clear_live_quote_cache(ticker: str | None = None) -> None:
    """Invalidate in-memory live quote cache for a specific ticker or globally."""
    with _LIVE_QUOTE_CACHE_LOCK:
        if ticker:
            _LIVE_QUOTE_MEMORY_CACHE.pop(canonical_symbol(ticker), None)
            _LIVE_QUOTE_MEMORY_CACHE.pop(ticker.strip().upper(), None)
        else:
            _LIVE_QUOTE_MEMORY_CACHE.clear()


def get_cached_price_df(ticker: str) -> pd.DataFrame | None:
    """Retrieve in-memory cached price history DataFrame if within TTL."""
    sym = ticker.strip().upper()
    now = time.monotonic()
    with _PRICE_CACHE_LOCK:
        item = _PRICE_DF_MEMORY_CACHE.get(sym)
        if item:
            ts, df = item
            if now - ts <= _PRICE_CACHE_TTL_SECONDS:
                return df
            del _PRICE_DF_MEMORY_CACHE[sym]
    return None


def set_cached_price_df(ticker: str, df: pd.DataFrame) -> None:
    """Store in-memory cached price history DataFrame with current timestamp."""
    if df is None:
        return
    sym = ticker.strip().upper()
    now = time.monotonic()
    with _PRICE_CACHE_LOCK:
        _PRICE_DF_MEMORY_CACHE[sym] = (now, df)


def clear_price_df_cache(ticker: str | None = None) -> None:
    """Invalidate in-memory price history cache for a specific ticker or globally."""
    with _PRICE_CACHE_LOCK:
        if ticker:
            _PRICE_DF_MEMORY_CACHE.pop(ticker.strip().upper(), None)
        else:
            _PRICE_DF_MEMORY_CACHE.clear()


def _empty_frame() -> pd.DataFrame:
    df = pd.DataFrame(columns=COLUMNS)
    df.index.name = "date"
    return df


def _connect(settings: Settings) -> sqlite3.Connection | Any:
    settings.ensure_dirs()
    from earnings_engine.data.migrations import apply_migrations
    apply_migrations(settings)
    connection = get_db_connection(settings)
    return connection


def _is_fresh(ticker: str, settings: Settings) -> bool:
    sym = canonical_symbol(ticker)
    if not is_turso_enabled():
        path = _cache_path(settings)
        if not path.exists():
            return False

    with _connect(settings) as connection:
        row = connection.execute(
            "SELECT COUNT(*) FROM price_history WHERE ticker = ?",
            (sym,),
        ).fetchone()

    return bool(row and row[0])


def _last_cached_date(ticker: str, settings: Settings) -> pd.Timestamp | None:
    """Return the most recent date for a ticker already in the price cache.

    Returns ``None`` if the ticker has no cached rows.
    """
    sym = canonical_symbol(ticker)
    if not is_turso_enabled():
        path = _cache_path(settings)
        if not path.exists():
            return None

    with _connect(settings) as connection:
        row = connection.execute(
            "SELECT MAX(date) FROM price_history WHERE ticker = ?",
            (sym,),
        ).fetchone()

    if not row or not row[0]:
        return None
    return pd.Timestamp(row[0])


def _mark_fetched(ticker: str, settings: Settings) -> None:
    """Record the moment this ticker's prices were last written to the cache."""
    sym = canonical_symbol(ticker)
    now_str = datetime.now().isoformat(timespec="seconds")
    with _connect(settings) as connection:
        connection.execute(
            """
            INSERT INTO tickers (ticker, prices_fetched_at, last_updated)
            VALUES (?, ?, ?)
            ON CONFLICT(ticker) DO UPDATE SET
                prices_fetched_at = excluded.prices_fetched_at,
                last_updated = excluded.last_updated
            """,
            (sym, now_str, now_str),
        )
        connection.commit()


def _fetch_log_time(ticker: str, settings: Settings) -> datetime | None:
    """Return the last-fetched timestamp for a ticker (None if never logged)."""
    sym = canonical_symbol(ticker)
    with _connect(settings) as connection:
        row = connection.execute(
            "SELECT prices_fetched_at FROM tickers WHERE ticker = ?", (sym,)
        ).fetchone()
    if not row or not row[0]:
        return None
    try:
        return datetime.fromisoformat(row[0])
    except ValueError:
        return None


FETCH_TTL_MINUTES = 10
MARKET_CLOSE_HOUR = 16


def prices_recent_enough(ticker: str, settings: Settings, ttl_minutes: int = FETCH_TTL_MINUTES) -> bool:
    """Return True when cached prices should be reused instead of re-downloading.

    Reuses the cache when the last fetch is under ``ttl_minutes`` old, when the
    market has already closed for the day or it is a weekend (prices are settled),
    or when there is no recorded fetch stamp (legacy/seeded rows).
    """
    sym = canonical_symbol(ticker)
    fetched = _fetch_log_time(sym, settings)
    now = datetime.now()

    # On weekends (Saturday & Sunday), markets are closed and Friday prices are fully settled
    if now.weekday() >= 5:
        session = _get_market_session_status(sym)
        last_trading_date = session.get("last_trading_date")
        last_cached = _last_cached_date(sym, settings)
        if last_cached is not None and last_trading_date:
            try:
                if last_cached.strftime("%Y-%m-%d") >= last_trading_date:
                    return True
            except Exception:
                pass
        if fetched is not None and last_trading_date:
            try:
                fetched_date = fetched.strftime("%Y-%m-%d")
                close_time = session.get("close_time", dt_time(15, 30))
                if fetched_date > last_trading_date or (
                    fetched_date == last_trading_date and fetched.time() >= close_time
                ):
                    return True
            except Exception:
                pass
        return False

    if fetched is None:
        last_cached = _last_cached_date(sym, settings)
        if last_cached is not None:
            # Check if last_cached is within 5 business days
            return (now - last_cached).total_seconds() <= 5 * 86400
        return True

    if (now - fetched).total_seconds() <= ttl_minutes * 60:
        return True
    if now.hour >= MARKET_CLOSE_HOUR:
        return True
    return False


def _sanitize_numeric(val: Any) -> float | None:
    """Safely convert a value to float, returning None if NaN, Inf, or unparseable."""
    if val is None or pd.isna(val):
        return None
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (ValueError, TypeError):
        return None


def _write_prices(ticker: str, settings: Settings, df: pd.DataFrame) -> None:
    """Overwrite cached price rows for a single ticker in SQLite with strict NaN/Null sanitization."""
    if df.empty:
        return

    rows = []
    for stamp, row in df.iterrows():
        ts = pd.Timestamp(stamp)
        if ts.weekday() >= 5:  # Strictly skip weekend non-trading days (Sat/Sun)
            continue
        date_value = ts.strftime("%Y-%m-%d")

        c = _sanitize_numeric(row.get("close"))
        if c is None or c <= 0:
            continue

        o = _sanitize_numeric(row.get("open"))
        h = _sanitize_numeric(row.get("high"))
        l = _sanitize_numeric(row.get("low"))
        v_num = _sanitize_numeric(row.get("volume"))
        v = int(v_num) if v_num is not None and v_num >= 0 else 0

        rows.append(
            (
                ticker,
                date_value,
                o if o is not None else c,
                h if h is not None else max(o or c, c),
                l if l is not None else min(o or c, c),
                c,
                v,
            )
        )

    with _connect(settings) as connection:
        connection.execute("DELETE FROM price_history WHERE ticker = ?", (ticker,))
        if rows:
            connection.executemany(
                "INSERT INTO price_history (ticker, date, open, high, low, close, volume) VALUES (?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
        connection.commit()
    _mark_fetched(ticker, settings)


def _merge_prices(ticker: str, settings: Settings, df: pd.DataFrame) -> None:
    """Upsert new price rows into the cache, preserving existing history with strict NaN/Null sanitization."""
    if df.empty:
        return

    rows = []
    for stamp, row in df.iterrows():
        ts = pd.Timestamp(stamp)
        if ts.weekday() >= 5:  # Strictly skip weekend non-trading days (Sat/Sun)
            continue
        date_value = ts.strftime("%Y-%m-%d")

        c = _sanitize_numeric(row.get("close"))
        if c is None or c <= 0:
            continue

        o = _sanitize_numeric(row.get("open"))
        h = _sanitize_numeric(row.get("high"))
        l = _sanitize_numeric(row.get("low"))
        v_num = _sanitize_numeric(row.get("volume"))
        v = int(v_num) if v_num is not None and v_num >= 0 else 0

        rows.append(
            (
                ticker,
                date_value,
                o if o is not None else c,
                h if h is not None else max(o or c, c),
                l if l is not None else min(o or c, c),
                c,
                v,
            )
        )

    if rows:
        with _connect(settings) as connection:
            connection.executemany(
                "INSERT OR REPLACE INTO price_history (ticker, date, open, high, low, close, volume) VALUES (?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
            connection.commit()
    _mark_fetched(ticker, settings)


KNOWN_TICKER_ALIASES: dict[str, str] = {
    "STERLITE.NS": "STLTECH.NS",
    "STERTECH.NS": "STLTECH.NS",
    "ZOMATO.NS": "ETERNAL.NS",
    "MINDTREE.NS": "LTIM.NS",
    "LTI.NS": "LTIM.NS",
    "CADILAHC.NS": "ZYDUSLIFE.NS",
    "HEXAWARE.NS": "HEXT.NS",
    "DHFL.NS": "PIRAMALFIN.NS",
}


def canonical_symbol(ticker: str) -> str:
    """Return the official/current active NSE trading symbol for rebranded or renamed tickers."""
    sym = (ticker or "").strip().upper()
    return KNOWN_TICKER_ALIASES.get(sym, sym)


def fetch_prices(
    ticker: str,
    settings: Settings,
    force: bool = False,
    start_date: str | None = None,
    hard_refresh: bool = False,
) -> pd.DataFrame:
    """Fetch prices from yfinance or load from SQLite.

    A 10-minute fetch cache (see ``prices_recent_enough``) prevents redundant
    yfinance hits during live scans: prices fetched within the TTL, or any time
    after the market closes, are reused without re-downloading.
    """
    sym = canonical_symbol(ticker)
    fetch_symbol = sym
    if not force and not hard_refresh:
        cached_df = load_prices(sym, settings)
        if not cached_df.empty and prices_recent_enough(sym, settings):
            logger.debug("[DATA-CACHE] [prices] Reusing cached price history for ticker=%s (within TTL)", sym)
            return cached_df

    clear_price_df_cache(sym)

    # Delta fetch: only download the dates we're missing.
    # If hard_refresh=True, we explicitly bypass delta fetch and pull 1 year of history (or custom start_date).
    if hard_refresh:
        start = start_date or (pd.Timestamp.now() - pd.Timedelta(days=365)).strftime("%Y-%m-%d")
        last_cached = None
        logger.debug("[DATA-FETCH] [yfinance] Hard-refreshing 1-year historical prices for ticker=%s (%s) from=%s", sym, fetch_symbol, start)
    else:
        start = start_date or settings.history_start
        last_cached = _last_cached_date(sym, settings)
        if last_cached is not None:
            overlap = pd.Timedelta(days=5)
            start = (last_cached - overlap).strftime("%Y-%m-%d")
            logger.debug(
                "[DATA-FETCH] [yfinance] Downloading price delta for ticker=%s (%s) from=%s (last cached: %s)",
                sym, fetch_symbol, start, last_cached.date(),
            )
        else:
            logger.debug("[DATA-FETCH] [yfinance] Downloading full historical prices for ticker=%s (%s) from=%s", sym, fetch_symbol, start)

    from earnings_engine.data.providers.provider_manager import get_data_manager

    mgr = get_data_manager(settings)
    raw = mgr.fetch_ohlcv(ticker=fetch_symbol, start_date=start)

    if raw is None or raw.empty:
        _mark_fetched(sym, settings)
        logger.warning("[DATA-FETCH] No price data returned for %s; loading from cache", sym)
        return load_prices(sym, settings) if _is_fresh(sym, settings) else _empty_frame()

    df = raw.copy()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [
            col[0].lower() if isinstance(col, tuple) and len(col) >= 1 and isinstance(col[0], str) else str(col)
            for col in df.columns
        ]

    renamed: dict[str, str] = {}
    for col in df.columns:
        if isinstance(col, str) and col.lower() in COLUMNS:
            renamed[col] = col.lower()
    if renamed:
        df = df.rename(columns=renamed)

    missing = [c for c in COLUMNS if c not in df.columns]
    if missing:
        for col in missing:
            df[col] = pd.NA

    df = df[COLUMNS].copy()
    logger.debug("[DATA-FETCH] Successfully normalized %d price rows for ticker=%s", len(df), sym)
    for col in COLUMNS:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["volume"] = df["volume"].astype("Int64")
    df.index = pd.to_datetime(df.index)
    df.index = df.index.tz_localize(None)
    df.index.name = "date"
    df = df.dropna(how="all")

    if last_cached is not None:
        # Merge delta into existing history — do NOT wipe the cache.
        _merge_prices(sym, settings, df)
        clear_price_df_cache(sym)
        return load_prices(sym, settings)

    _write_prices(sym, settings, df)
    set_cached_price_df(sym, df)
    return df


def load_prices_batch(
    tickers: list[str],
    settings: Settings,
    since_date: str | None = None,
    days: int | None = None,
) -> dict[str, pd.DataFrame]:
    """Load price DataFrames for multiple tickers in a single batched database query with in-memory caching."""
    if not tickers:
        return {}

    if days and not since_date:
        since_date = (pd.Timestamp.now() - pd.Timedelta(days=days)).strftime("%Y-%m-%d")

    cleaned = [canonical_symbol(t) for t in tickers if t and t.strip()]
    unique_tickers = list(dict.fromkeys(cleaned))
    result: dict[str, pd.DataFrame] = {}
    missing: list[str] = []

    for t in unique_tickers:
        cached = get_cached_price_df(t)
        if cached is not None:
            if since_date and not cached.empty:
                result[t] = cached.loc[cached.index >= since_date]
            else:
                result[t] = cached
        else:
            missing.append(t)

    if missing:
        CHUNK_SIZE = 200
        with _connect(settings) as connection:
            for i in range(0, len(missing), CHUNK_SIZE):
                chunk = missing[i : i + CHUNK_SIZE]
                placeholders = ",".join("?" for _ in chunk)
                if since_date:
                    query = (
                        f"SELECT ticker, date, open, high, low, close, volume "
                        f"FROM price_history "
                        f"WHERE ticker IN ({placeholders}) AND date >= ? AND close IS NOT NULL AND close > 0 "
                        f"ORDER BY ticker, date ASC"
                    )
                    params = [*chunk, since_date]
                else:
                    query = (
                        f"SELECT ticker, date, open, high, low, close, volume "
                        f"FROM price_history "
                        f"WHERE ticker IN ({placeholders}) AND close IS NOT NULL AND close > 0 "
                        f"ORDER BY ticker, date ASC"
                    )
                    params = chunk
                rows = connection.execute(query, params).fetchall()

                if rows:
                    all_df = pd.DataFrame(rows, columns=["ticker", "date", *COLUMNS])
                    all_df = all_df.dropna(subset=["close"])
                    all_df["date"] = pd.to_datetime(all_df["date"])
                    for col in COLUMNS:
                        all_df[col] = pd.to_numeric(all_df[col], errors="coerce")
                    all_df = all_df[all_df["close"].notna() & (all_df["close"] > 0)]
                    all_df = all_df.astype({"volume": "Int64"}, errors="ignore")
                    for sym, g in all_df.groupby("ticker", sort=False):
                        g = g.drop(columns=["ticker"]).set_index("date")
                        g.index.name = "date"
                        result[sym] = g
                        if not since_date:
                            set_cached_price_df(sym, g)

                for sym in chunk:
                    if sym not in result:
                        empty_df = _empty_frame()
                        result[sym] = empty_df
                        if not since_date:
                            set_cached_price_df(sym, empty_df)

    # Also map any requested original aliases to their canonical result
    for orig in tickers:
        if orig and orig.strip():
            canon = canonical_symbol(orig)
            if canon in result and orig not in result:
                result[orig] = result[canon]

    return result


def ensure_prices_batch(
    tickers: list[str],
    settings: Settings,
    max_workers: int = 10,
    force: bool = False,
) -> dict[str, pd.DataFrame]:
    """Ensure price data exists and is up to date for all tickers, downloading missing in parallel.

    Returns the loaded dictionary of price DataFrames for all requested tickers.
    """
    if not tickers:
        return {}

    cleaned = [canonical_symbol(t) for t in tickers if t and t.strip()]
    unique_tickers = list(dict.fromkeys(cleaned))

    # Identify tickers that need fetching
    to_fetch: list[str] = []
    for t in unique_tickers:
        if force or not _is_fresh(t, settings) or not prices_recent_enough(t, settings):
            to_fetch.append(t)

    if to_fetch:
        from concurrent.futures import ThreadPoolExecutor
        from earnings_engine.logging_utils import BatchProgressLogger
        logger.info("[PRICES-BATCH] Batch fetching latest prices for %d missing/stale tickers", len(to_fetch))
        progress = BatchProgressLogger(
            name="prices_batch",
            total=len(to_fetch),
            unit="tickers",
            milestones=[25, 50, 75, 100],
        )
        with ThreadPoolExecutor(max_workers=min(max_workers, len(to_fetch))) as executor:
            for _ in executor.map(lambda sym: fetch_prices(sym, settings, force=True), to_fetch):
                progress.update(1)
        progress.finish()

    return load_prices_batch(unique_tickers, settings)


def load_prices(
    ticker: str,
    settings: Settings,
    since_date: str | None = None,
    days: int | None = None,
) -> pd.DataFrame:
    """Load prices from in-memory cache or SQLite if present."""
    if not ticker:
        return _empty_frame()
    sym = canonical_symbol(ticker)
    if not since_date and not days:
        cached = get_cached_price_df(sym)
        if cached is not None:
            return cached
    res = load_prices_batch([sym], settings, since_date=since_date, days=days)
    return res.get(sym, _empty_frame())


def store_price_metrics(ticker: str, settings: Settings, metrics: dict[str, Any], as_of_date: str | None = None) -> None:
    """Persist derived metrics for a ticker in the SQLite cache."""
    as_of_date_value = as_of_date or pd.Timestamp.now().strftime("%Y-%m-%d")
    payload = json.dumps(metrics, sort_keys=True, default=str)
    with _connect(settings) as connection:
        # Upsert into unified tickers master table
        connection.execute(
            """
            INSERT INTO tickers (ticker, metrics, metrics_as_of_date, last_updated)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(ticker) DO UPDATE SET
                metrics = excluded.metrics,
                metrics_as_of_date = excluded.metrics_as_of_date,
                last_updated = excluded.last_updated
            """,
            (ticker, payload, as_of_date_value, as_of_date_value),
        )
        connection.commit()


def store_price_metrics_bulk(
    metrics_by_ticker: dict[str, dict[str, Any]],
    settings: Settings,
    as_of_date: str | None = None,
) -> None:
    """Persist derived metrics for multiple tickers in a single atomic batch transaction into unified tickers master table."""
    if not metrics_by_ticker:
        return
    as_of_date_value = as_of_date or pd.Timestamp.now().strftime("%Y-%m-%d")
    master_rows = [
        (ticker, json.dumps(m, sort_keys=True, default=str), as_of_date_value, as_of_date_value)
        for ticker, m in metrics_by_ticker.items()
    ]
    with _connect(settings) as connection:
        connection.executemany(
            """
            INSERT INTO tickers (ticker, metrics, metrics_as_of_date, last_updated)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(ticker) DO UPDATE SET
                metrics = excluded.metrics,
                metrics_as_of_date = excluded.metrics_as_of_date,
                last_updated = excluded.last_updated
            """,
            master_rows,
        )
        connection.commit()


def load_price_metrics(ticker: str, settings: Settings, as_of_date: str | None = None) -> dict[str, Any] | None:
    """Load previously persisted metrics for a ticker and day if they exist from tickers master table."""
    with _connect(settings) as connection:
        if as_of_date:
            row = connection.execute(
                "SELECT metrics FROM tickers WHERE ticker = ? AND metrics_as_of_date = ?",
                (ticker, as_of_date),
            ).fetchone()
        else:
            row = connection.execute(
                "SELECT metrics FROM tickers WHERE ticker = ? AND metrics IS NOT NULL ORDER BY metrics_as_of_date DESC LIMIT 1",
                (ticker,),
            ).fetchone()

    if not row or not row[0]:
        return None
    return json.loads(row[0]) if isinstance(row[0], str) else row[0]


def load_price_metrics_batch(
    tickers: list[str],
    settings: Settings,
    as_of_date: str | None = None,
) -> dict[str, dict[str, Any]]:
    """Load previously persisted metrics for multiple tickers in a batched database query."""
    if not tickers:
        return {}

    cleaned = [t.strip().upper() for t in tickers if t and t.strip()]
    unique_tickers = list(dict.fromkeys(cleaned))
    result: dict[str, dict[str, Any]] = {}

    CHUNK_SIZE = 200
    with _connect(settings) as connection:
        for i in range(0, len(unique_tickers), CHUNK_SIZE):
            chunk = unique_tickers[i : i + CHUNK_SIZE]
            placeholders = ",".join("?" for _ in chunk)
            if as_of_date:
                query = (
                    f"SELECT ticker, metrics FROM tickers "
                    f"WHERE ticker IN ({placeholders}) AND metrics_as_of_date = ? AND metrics IS NOT NULL"
                )
                params = [*chunk, as_of_date]
            else:
                query = (
                    f"SELECT ticker, metrics FROM tickers "
                    f"WHERE ticker IN ({placeholders}) AND metrics IS NOT NULL"
                )
                params = chunk
            rows = connection.execute(query, params).fetchall()
            for r in rows:
                sym = r[0]
                m_raw = r[1]
                if m_raw:
                    try:
                        m_val = json.loads(m_raw) if isinstance(m_raw, str) else m_raw
                        result[sym] = m_val
                    except Exception:
                        pass
    return result


def _fetch_prices_for_ticker(args: tuple[str, Settings, bool, bool, str | None]) -> tuple[str, int]:
    """Fetch prices for a single ticker. Returns (ticker, row_count)."""
    ticker, settings, force, hard_refresh, start_date = args
    try:
        df = fetch_prices(ticker, settings, force=force, hard_refresh=hard_refresh, start_date=start_date)
        return (ticker, int(len(df)))
    except Exception:
        return (ticker, 0)


def ingest_prices(
    tickers: list[str],
    settings: Settings,
    force: bool = False,
    hard_refresh: bool = False,
    start_date: str | None = None,
) -> dict[str, int]:
    """Download or refresh cached price data for the requested tickers.

    Uses ThreadPoolExecutor with 10 workers, batched in groups of 50 with
    2-second delays between batches to avoid yfinance rate limits.
    Skips tickers with fresh cache unless force=True or hard_refresh=True.
    """
    import time
    from concurrent.futures import ThreadPoolExecutor, as_completed

    results: dict[str, int] = {}
    total = len(tickers)
    batch_size = 50
    processed = 0

    # Filter out tickers with fresh cache (when not forcing / hard refreshing)
    tickers_to_fetch: list[str] = []
    cached_hits = 0
    for ticker in tickers:
        if not force and not hard_refresh and _is_fresh(ticker, settings):
            # Load from cache to get row count
            df = load_prices(ticker, settings)
            results[ticker] = int(len(df))
            cached_hits += 1
            processed += 1
        else:
            tickers_to_fetch.append(ticker)

    if cached_hits == total:
        logger.info("prices cache hit for all %s tickers, skipping fetch", total)
        return results

    logger.info("ingesting prices for %s tickers (%s cached, %s to fetch, hard_refresh=%s)",
                total, cached_hits, len(tickers_to_fetch), hard_refresh)

    fetch_total = len(tickers_to_fetch)
    max_workers = max(1, getattr(settings, "price_fetch_workers", 10))
    from earnings_engine.logging_utils import BatchProgressLogger
    progress = BatchProgressLogger(
        name="prices_ingest",
        total=fetch_total,
        unit="tickers",
        milestones=[20, 40, 60, 80, 100],
    )
    for i in range(0, fetch_total, batch_size):
        batch = tickers_to_fetch[i:i + batch_size]
        batch_num = i // batch_size + 1
        total_batches = (fetch_total + batch_size - 1) // batch_size

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_ticker = {
                executor.submit(_fetch_prices_for_ticker, (ticker, settings, force or hard_refresh, hard_refresh, start_date)): ticker
                for ticker in batch
            }
            for future in as_completed(future_to_ticker):
                ticker, count = future.result()
                processed += 1
                results[ticker] = count
                progress.update(1)

        # Wait 2 seconds between batches (skip after last batch)
        if i + batch_size < fetch_total:
            time.sleep(2)

    progress.finish()

    ok = sum(1 for v in results.values() if v > 0)
    logger.info("prices ingest complete: %s/%s tickers with data", ok, total)
    return results


def _get_market_session_status(ticker: str, now_dt: datetime | None = None) -> dict[str, Any]:
    """Determine market session status (open, closed, weekend, holiday, pre/post market) for a ticker.

    NSE equities/indices (.NS, ^NSE*, ^CNX*, ^INDIAVIX) use Asia/Kolkata (IST: 09:15-15:30).
    US equities and other assets use America/New_York (EST/EDT: 09:30-16:00).
    """
    sym = (ticker or "").strip().upper()
    is_india = sym.endswith(".NS") or sym.startswith(("^NSE", "^CNX", "^INDIAVIX"))

    tz = None
    if ZoneInfo is not None:
        try:
            tz = ZoneInfo("Asia/Kolkata" if is_india else "America/New_York")
        except Exception:
            tz = None
    if tz is None:
        if is_india:
            tz = timezone(timedelta(hours=5, minutes=30))
        else:
            tz = timezone(timedelta(hours=-4))  # Approximate US Eastern (EDT)

    if now_dt is not None:
        if now_dt.tzinfo is None:
            now_local = now_dt.replace(tzinfo=timezone.utc).astimezone(tz)
        else:
            now_local = now_dt.astimezone(tz)
    else:
        now_local = datetime.now(tz)

    weekday = now_local.weekday()  # Monday = 0, Sunday = 6
    is_weekend = weekday >= 5
    target_date = now_local.date()

    open_time = dt_time(9, 15) if is_india else dt_time(9, 30)
    close_time = dt_time(15, 30) if is_india else dt_time(16, 0)
    current_time = now_local.time()
    market_date = now_local.strftime("%Y-%m-%d")

    is_open = False
    is_pre_market = False
    is_post_market = False
    is_holiday = False
    session_label = "closed"

    if is_india:
        is_holiday = is_market_holiday(target_date)
        if is_holiday:
            is_open = False
            session_label = "closed"
            last_trading_day_obj = get_latest_completed_trading_day(target_date - timedelta(days=1))
            last_trading_date = last_trading_day_obj.strftime("%Y-%m-%d")
            friday_date = last_trading_date
            friday_close_dt = datetime.combine(last_trading_day_obj, close_time).replace(tzinfo=tz)
        elif is_weekend:
            is_open = False
            session_label = "closed"
            last_trading_day_obj = get_latest_completed_trading_day(target_date)
            last_trading_date = last_trading_day_obj.strftime("%Y-%m-%d")
            friday_date = last_trading_date
            friday_close_dt = datetime.combine(last_trading_day_obj, close_time).replace(tzinfo=tz)
        else:
            # Active trading day
            if current_time < open_time:
                is_pre_market = True
                session_label = "pre_market"
                prev_trading_day = get_latest_completed_trading_day(target_date - timedelta(days=1))
                last_trading_date = prev_trading_day.strftime("%Y-%m-%d")
                friday_date = last_trading_date
                friday_close_dt = datetime.combine(prev_trading_day, close_time).replace(tzinfo=tz)
            elif current_time >= close_time:
                is_post_market = True
                session_label = "post_market"
                last_trading_date = market_date
                friday_date = market_date
                friday_close_dt = datetime.combine(target_date, close_time).replace(tzinfo=tz)
            else:
                is_open = True
                session_label = "regular"
                last_trading_date = market_date
                friday_date = market_date
                friday_close_dt = datetime.combine(target_date, close_time).replace(tzinfo=tz)
    else:
        # Non-Indian / US Market
        if not is_weekend:
            if current_time < open_time:
                is_pre_market = True
                session_label = "pre_market"
            elif current_time >= close_time:
                is_post_market = True
                session_label = "post_market"
            else:
                is_open = True
                session_label = "regular"

        if is_weekend:
            friday_dt = now_local - timedelta(days=weekday - 4)
            friday_date = friday_dt.strftime("%Y-%m-%d")
            last_trading_date = friday_date
            friday_close_dt = friday_dt.replace(hour=close_time.hour, minute=close_time.minute, second=0, microsecond=0)
        elif is_pre_market:
            if weekday == 0:
                prev_dt = now_local - timedelta(days=3)
                friday_dt = prev_dt
            else:
                prev_dt = now_local - timedelta(days=1)
                friday_dt = now_local - timedelta(days=weekday + 3)
            friday_date = friday_dt.strftime("%Y-%m-%d")
            last_trading_date = prev_dt.strftime("%Y-%m-%d")
            friday_close_dt = friday_dt.replace(hour=close_time.hour, minute=close_time.minute, second=0, microsecond=0)
        else:
            friday_dt = now_local - timedelta(days=weekday - 4) if weekday >= 4 else now_local - timedelta(days=weekday + 3)
            friday_date = friday_dt.strftime("%Y-%m-%d")
            last_trading_date = market_date
            friday_close_dt = friday_dt.replace(hour=close_time.hour, minute=close_time.minute, second=0, microsecond=0)

    return {
        "is_open": is_open,
        "is_weekend": is_weekend,
        "is_holiday": is_holiday,
        "session": session_label,
        "is_pre_market": is_pre_market,
        "is_post_market": is_post_market,
        "market_date": market_date,
        "last_trading_date": last_trading_date,
        "friday_date": friday_date,
        "friday_close_dt": friday_close_dt,
        "now_local": now_local,
        "open_time": open_time,
        "close_time": close_time,
    }


get_market_session = _get_market_session_status


def _get_cached_quotes_batch(
    tickers: list[str],
    settings: Settings,
    batch_chunk_size: int = 100,
) -> dict[str, dict[str, Any]]:
    """Batch retrieve the latest 2-day price action and 52W metrics from SQLite price_history and tickers.

    Uses an optimized window CTE query bounded to 252 bars per ticker.
    Chunks requested tickers into chunks of 100 to prevent SQLite variable limits.
    Returns a dict mapping canonical ticker -> aggregated record dictionary.
    """
    if not tickers:
        return {}

    unique_syms = list(dict.fromkeys([canonical_symbol(t) for t in tickers if t]))
    results: dict[str, dict[str, Any]] = {}

    try:
        with _connect(settings) as conn:
            conn.row_factory = sqlite3.Row
            for i in range(0, len(unique_syms), batch_chunk_size):
                chunk = unique_syms[i : i + batch_chunk_size]
                placeholders = ", ".join(["?"] * len(chunk))
                sql = f"""
                    WITH ranked AS (
                        SELECT ticker, date, open, high, low, close, volume,
                               ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY date DESC) as rn
                        FROM price_history
                        WHERE ticker IN ({placeholders})
                    ),
                    filtered AS (
                        SELECT * FROM ranked WHERE rn <= 252
                    )
                    SELECT
                        f.ticker,
                        MAX(CASE WHEN f.rn = 1 THEN f.close END) AS cur_close,
                        MAX(CASE WHEN f.rn = 1 THEN f.open END) AS cur_open,
                        MAX(CASE WHEN f.rn = 1 THEN f.high END) AS cur_high,
                        MAX(CASE WHEN f.rn = 1 THEN f.low END) AS cur_low,
                        MAX(CASE WHEN f.rn = 1 THEN f.volume END) AS cur_vol,
                        MAX(CASE WHEN f.rn = 1 THEN f.date END) AS cur_date,
                        MAX(CASE WHEN f.rn = 2 THEN f.close END) AS prev_close,
                        MAX(f.high) AS w52_high,
                        MIN(f.low) AS w52_low,
                        AVG(f.volume) AS avg_vol,
                        t.market_cap,
                        t.prices_fetched_at
                    FROM filtered f
                    LEFT JOIN tickers t ON f.ticker = t.ticker
                    GROUP BY f.ticker
                """
                rows = conn.execute(sql, chunk).fetchall()
                for r in rows:
                    rec = dict(r)
                    results[rec["ticker"]] = rec
    except Exception as e:
        logger.warning("[CACHE:FAIL] _get_cached_quotes_batch failed: %s", e)

    return results


def _is_cached_quote_fresh(
    cached_record: dict[str, Any],
    session: dict[str, Any],
    ttl_minutes: int = 5,
) -> bool:
    """Evaluate whether a cached quote record can be served without network re-fetch.

    Rules:
    - Must have a valid cur_close > 0.
    - If weekend: Fresh if we have settled price history (cur_close > 0).
    - If post-market: Fresh if today's market date is settled (cur_date == market_date),
      OR if prices_fetched_at occurred after market close today.
      If today's market close has not been fetched yet, it's stale (needs 1 fetch to settle).
    - If pre-market: Fresh if we have settled price history from recent days (cur_date within 4 days).
    - If market is open: Fresh ONLY if prices_fetched_at is within ttl_minutes.
    """
    cur_close = cached_record.get("cur_close")
    if cur_close is None or float(cur_close) <= 0:
        return False

    is_open = session.get("is_open", False)
    is_weekend = session.get("is_weekend", False)
    is_holiday = session.get("is_holiday", False)
    is_post = session.get("is_post_market", False)
    is_pre = session.get("is_pre_market", False)
    market_date = session.get("market_date", "")
    cur_date = cached_record.get("cur_date") or ""

    if is_holiday:
        # On market holidays, settled historical prices from the latest completed trading session are 100% fresh
        return True

    fetched_at_str = cached_record.get("prices_fetched_at")
    fetched_at_dt: datetime | None = None
    if fetched_at_str:
        try:
            fetched_at_dt = datetime.fromisoformat(fetched_at_str.replace("Z", "+00:00"))
        except Exception:
            fetched_at_dt = None

    if is_weekend:
        friday_date = session.get("friday_date") or session.get("last_trading_date")
        friday_close_dt = session.get("friday_close_dt")
        # 1. Price history bar is already settled on or after Friday's date
        if cur_date and friday_date and cur_date >= friday_date:
            return True
        # If cur_date is older than Friday by more than 4 days, SQLite price_history is stale
        if cur_date and friday_date:
            try:
                c_dt = datetime.strptime(cur_date, "%Y-%m-%d").date()
                f_dt = datetime.strptime(friday_date, "%Y-%m-%d").date()
                if (f_dt - c_dt).days > 4:
                    return False
            except Exception:
                pass
        # 2. Or quote was fetched after Friday market close
        if fetched_at_dt:
            if friday_close_dt:
                f_close_cmp = friday_close_dt
                if fetched_at_dt.tzinfo is not None and f_close_cmp.tzinfo is None:
                    f_close_cmp = f_close_cmp.replace(tzinfo=fetched_at_dt.tzinfo)
                elif fetched_at_dt.tzinfo is None and f_close_cmp.tzinfo is not None:
                    f_close_cmp = f_close_cmp.replace(tzinfo=None)
                if fetched_at_dt >= f_close_cmp:
                    return True
            if friday_date:
                try:
                    f_dt = datetime.strptime(friday_date, "%Y-%m-%d").date()
                    if fetched_at_dt.date() > f_dt:  # fetched on Saturday or Sunday
                        return True
                    if fetched_at_dt.date() == f_dt:
                        close_t = session.get("close_time") or dt_time(15, 30)
                        if fetched_at_dt.time() >= close_t:
                            return True
                except Exception:
                    pass
        # Fallback for mock session dicts without friday_date (e.g. legacy test records)
        if not friday_date:
            return True
        return False

    if is_post:
        if cur_date == market_date:
            return True
        close_time = session.get("close_time")
        if fetched_at_dt and close_time:
            try:
                if fetched_at_dt.strftime("%Y-%m-%d") == market_date and fetched_at_dt.time() >= close_time:
                    return True
            except Exception:
                pass
        return False

    if is_pre:
        if cur_date:
            try:
                cd = datetime.strptime(cur_date, "%Y-%m-%d").date()
                md = datetime.strptime(market_date, "%Y-%m-%d").date()
                if (md - cd).days <= 4:
                    return True
            except Exception:
                pass
        return False

    if is_open:
        if not fetched_at_dt:
            return False
        now_dt = datetime.now(fetched_at_dt.tzinfo) if fetched_at_dt.tzinfo else datetime.now()
        age_seconds = (now_dt - fetched_at_dt).total_seconds()
        return -5 <= age_seconds <= (ttl_minutes * 60)

    return True


def calculate_quote_staleness(
    fetched_at_str: str | None,
    session: dict[str, Any],
    live_threshold_minutes: int = 15,
    delayed_threshold_minutes: int = 120,
) -> tuple[str, bool]:
    """Calculate market-aware price delay status and staleness flag.

    Returns:
        tuple[str, bool]: (price_delay_status, is_price_stale)
        status is one of: "LIVE", "DELAYED", "STALE", "MARKET CLOSED"
    """
    is_open = bool(session.get("is_open", False))
    is_weekend = bool(session.get("is_weekend", False))

    if is_weekend:
        return "MARKET CLOSED", False

    if not is_open:
        return "MARKET CLOSED", False

    if not fetched_at_str:
        return "STALE", True

    try:
        clean_str = fetched_at_str.replace("Z", "+00:00")
        fetched_dt = datetime.fromisoformat(clean_str)
        now_dt = datetime.now(fetched_dt.tzinfo) if fetched_dt.tzinfo else datetime.now()
        age_seconds = (now_dt - fetched_dt).total_seconds()

        if age_seconds <= live_threshold_minutes * 60:
            return "LIVE", False
        elif age_seconds <= delayed_threshold_minutes * 60:
            return "DELAYED", False
        else:
            return "STALE", True
    except Exception:
        return "DELAYED", False


def _build_quote_from_cached_record(
    sym: str,
    record: dict[str, Any],
    session: dict[str, Any],
) -> dict[str, Any]:
    """Transform an aggregated SQLite record into the standard 18-key quote dict."""
    last_p = record.get("cur_close")
    prev_c = record.get("prev_close")
    open_p = record.get("cur_open")
    day_h = record.get("cur_high")
    day_l = record.get("cur_low")
    yr_h = record.get("w52_high")
    yr_l = record.get("w52_low")
    vol = record.get("cur_vol")
    avg_vol = record.get("avg_vol")
    mcap = record.get("market_cap")
    fetched_at = record.get("prices_fetched_at")
    last_updated = fetched_at or datetime.now().isoformat()

    price_delay_status, is_price_stale = calculate_quote_staleness(fetched_at, session)

    quote: dict[str, Any] = {
        "ticker": sym,
        "symbol": sym,
        "current_price": round(float(last_p), 2) if last_p is not None else None,
        "previous_close": round(float(prev_c), 2) if prev_c is not None and prev_c > 0 else None,
        "day_change": None,
        "day_change_pct": None,
        "day_open": round(float(open_p), 2) if open_p is not None else None,
        "day_high": round(float(day_h), 2) if day_h is not None else None,
        "day_low": round(float(day_l), 2) if day_l is not None else None,
        "week_52_high": round(float(yr_h), 2) if yr_h is not None else None,
        "week_52_low": round(float(yr_l), 2) if yr_l is not None else None,
        "volume": int(vol) if vol is not None else None,
        "avg_volume": int(avg_vol) if avg_vol is not None else None,
        "market_cap": float(mcap) if mcap is not None else None,
        "currency": "INR" if sym.endswith(".NS") else "USD",
        "is_live": bool(session.get("is_open", False)),
        "last_updated": last_updated,
        "quote_timestamp": last_updated,
        "price_delay_status": price_delay_status,
        "is_price_stale": is_price_stale,
        "pct_from_52w_high": None,
        "pct_from_52w_low": None,
    }

    if quote["current_price"] is not None and quote["previous_close"] is not None:
        quote["day_change"] = round(float(quote["current_price"] - quote["previous_close"]), 2)
        quote["day_change_pct"] = round(float((quote["current_price"] / quote["previous_close"] - 1.0) * 100.0), 2)

    if quote["current_price"] is not None and quote["week_52_high"] and quote["week_52_high"] > 0:
        quote["pct_from_52w_high"] = round((quote["current_price"] / quote["week_52_high"] - 1.0) * 100.0, 2)
    if quote["current_price"] is not None and quote["week_52_low"] and quote["week_52_low"] > 0:
        quote["pct_from_52w_low"] = round((quote["current_price"] / quote["week_52_low"] - 1.0) * 100.0, 2)

    return quote


def fetch_live_quote(
    ticker: str,
    settings: Settings | None = None,
    sync_db: bool = True,
    force: bool = False,
    ttl_minutes: int = 5,
    silent: bool = False,
    now_dt: datetime | None = None,
) -> dict[str, Any]:
    """Fetch authoritative live real-time market quote for a single ticker.

    Uses DB-first TTL caching (default 5 minutes, market-session aware) to prevent
    redundant outbound network requests and conserve downstream API rate limits.
    If force=True, or if cached data is missing or stale, queries Yahoo Finance fast_info
    attribute access with fallbacks to intraday / daily history bars.
    If sync_db=True and a valid price is obtained, upserts today's live bar into
    price_history and updates tickers.market_cap and prices_fetched_at.
    """
    settings = settings or Settings()
    sym = ticker.strip().upper()
    fetch_sym = KNOWN_TICKER_ALIASES.get(sym, sym)
    canonical = canonical_symbol(sym)
    session = _get_market_session_status(sym, now_dt=now_dt)

    # 1. DB-First Freshness Check (serve immediately if fresh in SQLite)
    if not force:
        cached_records = _get_cached_quotes_batch([canonical], settings=settings)
        record = cached_records.get(canonical) or cached_records.get(sym)
        if record and _is_cached_quote_fresh(record, session, ttl_minutes=ttl_minutes):
            logger.debug("[QUOTE:CACHE-HIT] %s served from SQLite (market_open=%s)", sym, session["is_open"])
            return _build_quote_from_cached_record(sym, record, session)

        # Off-market / Holiday / Weekend fallback to settled SQLite prices without outbound network call
        if session.get("is_holiday") or session.get("is_weekend") or not session.get("is_open"):
            if record and record.get("cur_close") and float(record.get("cur_close") or 0) > 0:
                return _build_quote_from_cached_record(sym, record, session)
            try:
                hist_df = load_prices(sym, settings)
                if not hist_df.empty and "close" in hist_df.columns:
                    closes = hist_df["close"].dropna()
                    if len(closes) > 0:
                        last_c = float(closes.iloc[-1])
                        prev_c_val = float(closes.iloc[-2]) if len(closes) >= 2 else last_c
                        chg_pts = round(last_c - prev_c_val, 2)
                        chg_pct = round(((last_c - prev_c_val) / prev_c_val) * 100.0, 2) if prev_c_val > 0 else 0.0
                        return {
                            "ticker": sym,
                            "symbol": sym,
                            "current_price": round(last_c, 2),
                            "previous_close": round(prev_c_val, 2),
                            "day_change": chg_pts,
                            "day_change_pct": chg_pct,
                            "day_open": float(hist_df["open"].iloc[-1]) if "open" in hist_df.columns else last_c,
                            "day_high": float(hist_df["high"].iloc[-1]) if "high" in hist_df.columns else last_c,
                            "day_low": float(hist_df["low"].iloc[-1]) if "low" in hist_df.columns else last_c,
                            "week_52_high": float(hist_df["high"].tail(252).max()) if "high" in hist_df.columns else last_c,
                            "week_52_low": float(hist_df["low"].tail(252).min()) if "low" in hist_df.columns else last_c,
                            "volume": int(hist_df["volume"].iloc[-1]) if "volume" in hist_df.columns else 0,
                            "avg_volume": int(hist_df["volume"].tail(50).mean()) if "volume" in hist_df.columns else 0,
                            "market_cap": None,
                            "currency": "INR" if sym.endswith(".NS") else "USD",
                            "is_live": False,
                            "last_updated": datetime.now().isoformat(),
                            "pct_from_52w_high": 0.0,
                            "pct_from_52w_low": 0.0,
                        }
            except Exception as e:
                logger.debug("[OFF-MARKET:FALLBACK-ERROR] %s: %s", sym, e)
            return {
                "ticker": sym,
                "symbol": sym,
                "current_price": None,
                "previous_close": None,
                "day_change": None,
                "day_change_pct": None,
                "day_open": None,
                "day_high": None,
                "day_low": None,
                "week_52_high": None,
                "week_52_low": None,
                "volume": None,
                "avg_volume": None,
                "market_cap": None,
                "currency": "INR" if sym.endswith(".NS") else "USD",
                "is_live": False,
                "last_updated": datetime.now().isoformat(),
                "pct_from_52w_high": None,
                "pct_from_52w_low": None,
            }

    quote: dict[str, Any] = {
        "ticker": sym,
        "symbol": sym,
        "current_price": None,
        "previous_close": None,
        "day_change": None,
        "day_change_pct": None,
        "day_open": None,
        "day_high": None,
        "day_low": None,
        "week_52_high": None,
        "week_52_low": None,
        "volume": None,
        "avg_volume": None,
        "market_cap": None,
        "currency": "INR" if sym.endswith(".NS") else "USD",
        "is_live": False,
        "last_updated": datetime.now().isoformat(),
        "pct_from_52w_high": None,
        "pct_from_52w_low": None,
    }

    last_p: float | None = None
    prev_c: float | None = None
    open_p: float | None = None
    day_h: float | None = None
    day_l: float | None = None
    yr_h: float | None = None
    yr_l: float | None = None
    vol: float | None = None
    avg_vol: float | None = None
    mcap: float | None = None

    def _get_val(fast_obj: Any, key: str, fallback_keys: tuple[str, ...] = ()) -> Any:
        if fast_obj is None:
            return None
        # Try attribute access first (if not callable)
        val = getattr(fast_obj, key, None)
        if val is not None and not callable(val):
            return val
        # Try dict lookup
        if isinstance(fast_obj, dict):
            if key in fast_obj and fast_obj[key] is not None:
                return fast_obj[key]
            for fb in fallback_keys:
                if fb in fast_obj and fast_obj[fb] is not None:
                    return fast_obj[fb]
        return None

    if not silent:
        logger.info("[YF:REQ] fetch_live_quote(%s via %s, force=%s)", sym, fetch_sym, force)
    t0_quote = time.perf_counter()
    try:
        from earnings_engine.rate_limits import record_request
        try:
            record_request("yfinance")
        except Exception:
            pass
        yf_obj = yf.Ticker(fetch_sym)
        fast = getattr(yf_obj, "fast_info", None)

        if fast:
            last_p = _get_val(fast, "last_price", ("lastPrice", "regularMarketPrice", "currentPrice"))
            prev_c = _get_val(fast, "previous_close", ("regular_market_previous_close", "regularMarketPreviousClose", "prev_close"))
            open_p = _get_val(fast, "open", ("regularMarketOpen", "day_open"))
            day_h = _get_val(fast, "day_high", ("dayHigh", "regularMarketDayHigh"))
            day_l = _get_val(fast, "day_low", ("dayLow", "regularMarketDayLow"))
            yr_h = _get_val(fast, "year_high", ("yearHigh", "fiftyTwoWeekHigh", "week_52_high"))
            yr_l = _get_val(fast, "year_low", ("yearLow", "fiftyTwoWeekLow", "week_52_low"))
            vol = _get_val(fast, "last_volume", ("lastVolume", "regularMarketVolume", "volume"))
            avg_vol = _get_val(fast, "three_month_average_volume", ("threeMonthAverageVolume", "ten_day_average_volume", "tenDayAverageVolume", "avg_volume"))
            mcap = _get_val(fast, "market_cap", ("marketCap", "mcap"))

        # Fallback to history if fast_info gave no last_price
        if last_p is None or last_p <= 0:
            hist = yf_obj.history(period="5d", interval="1d")
            if hist is not None and not hist.empty:
                last_row = hist.iloc[-1]
                last_p = float(last_row.get("Close", 0))
                open_p = float(last_row.get("Open", last_p))
                day_h = float(last_row.get("High", last_p))
                day_l = float(last_row.get("Low", last_p))
                vol = float(last_row.get("Volume", 0))
                if len(hist) >= 2:
                    prev_c = float(hist.iloc[-2].get("Close", 0))

        # Direct Yahoo v8 chart endpoint fallback (rate-limit immune)
        if last_p is None or last_p <= 0:
            import urllib.request
            t0_chart = time.perf_counter()
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{fetch_sym}?interval=1d&range=5d"
            if not silent:
                logger.info("[YF:REQ] Direct chart query: %s", url)
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"}
            )
            try:
                with urllib.request.urlopen(req, timeout=8) as resp:
                    chart_data = json.loads(resp.read().decode())
                    elapsed_ms_c = (time.perf_counter() - t0_chart) * 1000
                    if not silent:
                        logger.info("[YF:RESP] Direct chart query (%s) (%.1fms)", fetch_sym, elapsed_ms_c)
                    if chart_data and "chart" in chart_data and "result" in chart_data["chart"] and chart_data["chart"]["result"]:
                        res_obj = chart_data["chart"]["result"][0]
                        meta = res_obj.get("meta", {})
                        last_p = meta.get("regularMarketPrice")
                        prev_c = meta.get("chartPreviousClose")
                        yr_h = meta.get("fiftyTwoWeekHigh")
                        yr_l = meta.get("fiftyTwoWeekLow")
                        indicators = res_obj.get("indicators", {}).get("quote", [{}])[0]
                        closes = indicators.get("close", [])
                        opens = indicators.get("open", [])
                        highs = indicators.get("high", [])
                        lows = indicators.get("low", [])
                        vols = indicators.get("volume", [])
                        if closes:
                            valid_closes = [c for c in closes if c is not None]
                            if valid_closes:
                                last_p = last_p or valid_closes[-1]
                        if opens and opens[-1] is not None: open_p = opens[-1]
                        if highs and highs[-1] is not None: day_h = highs[-1]
                        if lows and lows[-1] is not None: day_l = lows[-1]
                        if vols and vols[-1] is not None: vol = vols[-1]
            except Exception as chart_err:
                elapsed_ms_c = (time.perf_counter() - t0_chart) * 1000
                if not silent:
                    logger.warning("[YF:FAIL] Direct chart query (%s) failed after %.1fms: %s", fetch_sym, elapsed_ms_c, chart_err)
                else:
                    logger.debug("[YF:FAIL] Direct chart query (%s) failed after %.1fms: %s", fetch_sym, elapsed_ms_c, chart_err)

        elapsed_ms_q = (time.perf_counter() - t0_quote) * 1000
        if not silent:
            if last_p is not None:
                logger.info("[YF:RESP] fetch_live_quote(%s) price=%.2f (%.1fms)", sym, last_p, elapsed_ms_q)
            else:
                logger.info("[YF:RESP] fetch_live_quote(%s) price=None (%.1fms)", sym, elapsed_ms_q)

    except Exception as e:
        elapsed_ms_q = (time.perf_counter() - t0_quote) * 1000
        if not silent:
            logger.warning("[YF:FAIL] fetch_live_quote(%s) failed after %.1fms: %s", sym, elapsed_ms_q, e)
        else:
            logger.debug("[YF:FAIL] fetch_live_quote(%s) failed after %.1fms: %s", sym, elapsed_ms_q, e)

    is_weekend = session.get("is_weekend", False)

    # If yfinance returned identical last_p and prev_c on weekends, or data is missing, anchor to settled trading history
    if last_p is None or prev_c is None or (is_weekend and prev_c is not None and abs(last_p - prev_c) < 0.001):
        try:
            with _connect(settings) as conn:
                p_rows = conn.execute(
                    "SELECT date, close, open, high, low, volume FROM price_history WHERE ticker = ? AND strftime('%w', date) NOT IN ('0', '6') ORDER BY date DESC LIMIT 2",
                    (sym,),
                ).fetchall()
                if p_rows and len(p_rows) >= 1:
                    last_p = last_p or float(p_rows[0][1] or 0.0)
                    if len(p_rows) >= 2:
                        prev_c = float(p_rows[1][1] or 0.0)
        except Exception:
            pass

    if last_p is not None and last_p > 0:
        quote["current_price"] = round(float(last_p), 2)
        quote["is_live"] = bool(session.get("is_open", False))
        now_iso = datetime.now().isoformat()
        quote["last_updated"] = now_iso
        quote["quote_timestamp"] = now_iso
        price_delay_status, is_price_stale = calculate_quote_staleness(now_iso, session)
        quote["price_delay_status"] = price_delay_status
        quote["is_price_stale"] = is_price_stale
        if prev_c is not None and prev_c > 0:
            quote["previous_close"] = round(float(prev_c), 2)
            quote["day_change"] = round(float(last_p - prev_c), 2)
            quote["day_change_pct"] = round(float((last_p / prev_c - 1.0) * 100.0), 2)
        if open_p is not None: quote["day_open"] = round(float(open_p), 2)
        if day_h is not None: quote["day_high"] = round(float(day_h), 2)
        if day_l is not None: quote["day_low"] = round(float(day_l), 2)
        if yr_h is not None: quote["week_52_high"] = round(float(yr_h), 2)
        if yr_l is not None: quote["week_52_low"] = round(float(yr_l), 2)
        if vol is not None: quote["volume"] = int(vol)
        if avg_vol is not None: quote["avg_volume"] = int(avg_vol)
        if mcap is not None: quote["market_cap"] = float(mcap)

        # Distance from 52W high/low
        if quote["week_52_high"] and quote["week_52_high"] > 0:
            quote["pct_from_52w_high"] = round((quote["current_price"] / quote["week_52_high"] - 1.0) * 100.0, 2)
        if quote["week_52_low"] and quote["week_52_low"] > 0:
            quote["pct_from_52w_low"] = round((quote["current_price"] / quote["week_52_low"] - 1.0) * 100.0, 2)

        # Sync with SQLite cache (strictly on business trading days, never on weekends)
        if sync_db and not is_weekend:
            try:
                today_str = datetime.now().strftime("%Y-%m-%d")
                with _connect(settings) as conn:
                    conn.execute(
                        """INSERT INTO price_history (ticker, date, open, high, low, close, volume)
                           VALUES (?, ?, ?, ?, ?, ?, ?)
                           ON CONFLICT(ticker, date) DO UPDATE SET
                               high = MAX(COALESCE(price_history.high, excluded.high), excluded.high),
                               low = MIN(COALESCE(price_history.low, excluded.low), excluded.low),
                               close = excluded.close,
                               volume = COALESCE(excluded.volume, price_history.volume)
                        """,
                        (
                            sym,
                            today_str,
                            open_p if open_p is not None else last_p,
                            day_h if day_h is not None else last_p,
                            day_l if day_l is not None else last_p,
                            last_p,
                            vol if vol is not None else 0,
                        ),
                    )
                    try:
                        conn.execute(
                            "UPDATE tickers SET market_cap = COALESCE(?, market_cap), market_cap_updated_at = ?, last_updated = ? WHERE ticker = ?",
                            (mcap, datetime.now().isoformat(), datetime.now().isoformat(), sym),
                        )
                    except Exception:
                        pass
                    conn.commit()
                clear_price_df_cache(sym)
                _mark_fetched(sym, settings)
            except Exception as e:
                logger.debug("[LIVE-QUOTE] SQLite sync failed for %s: %s", sym, e)
        elif sync_db and is_weekend:
            try:
                if mcap is not None:
                    with _connect(settings) as conn:
                        conn.execute(
                            "UPDATE tickers SET market_cap = COALESCE(?, market_cap), market_cap_updated_at = ?, last_updated = ? WHERE ticker = ?",
                            (mcap, datetime.now().isoformat(), datetime.now().isoformat(), sym),
                        )
                        conn.commit()
                _mark_fetched(sym, settings)
            except Exception as e:
                logger.debug("[LIVE-QUOTE] SQLite weekend sync failed for %s: %s", sym, e)

    return quote


def _fetch_yfinance_batch_quotes(
    tickers: list[str],
    settings: Settings | None = None,
    sync_db: bool = True,
    chunk_size: int = 50,
) -> dict[str, dict[str, Any]]:
    """Fetch live real-time market quotes for multiple tickers in batched HTTP requests.

    Queries Yahoo Finance's multi-ticker endpoint (v7/finance/quote) in chunks of up to
    50 symbols per single HTTP request, avoiding per-stock sequential or thread-pool overhead.
    Optionally persists daily bars into price_history and updates tickers.market_cap and
    prices_fetched_at in single batch SQLite transactions.
    """
    settings = settings or Settings()
    if not tickers:
        return {}

    unique_tickers = list(dict.fromkeys([t.strip().upper() for t in tickers if t]))
    if not unique_tickers:
        return {}

    num_chunks = (len(unique_tickers) + chunk_size - 1) // chunk_size
    logger.info(
        "[BATCH-QUOTES] Fetching live quotes for %d tickers across %d batch chunk(s)",
        len(unique_tickers),
        num_chunks,
    )
    t0_all = time.perf_counter()
    results: dict[str, dict[str, Any]] = {}

    for i in range(0, len(unique_tickers), chunk_size):
        chunk = unique_tickers[i : i + chunk_size]
        ticker_map: dict[str, list[str]] = {}
        fetch_syms: list[str] = []
        for t in chunk:
            sym = canonical_symbol(t)
            ticker_map.setdefault(sym, []).append(t)
            if sym not in fetch_syms:
                fetch_syms.append(sym)

        symbols_param = ",".join(fetch_syms)
        t0 = time.perf_counter()
        raw_items: list[dict[str, Any]] = []
        try:
            yf_data = yf.data.YfData()
            res = yf_data.get_raw_json(
                "https://query1.finance.yahoo.com/v7/finance/quote",
                params={"symbols": symbols_param},
            )
            elapsed_ms = (time.perf_counter() - t0) * 1000
            raw_items = res.get("quoteResponse", {}).get("result", [])
            logger.debug(
                "[BATCH-QUOTES] Chunk fetched quotes for %d symbols in %.1fms (%d results returned)",
                len(chunk),
                elapsed_ms,
                len(raw_items),
            )
        except Exception as e:
            elapsed_ms = (time.perf_counter() - t0) * 1000
            logger.warning(
                "[BATCH-QUOTES] Chunk quote request for %d symbols failed after %.1fms: %s",
                len(chunk),
                elapsed_ms,
                e,
            )
            continue

        valid_sync_items: list[dict[str, Any]] = []
        now_iso = datetime.now().isoformat()

        for item in raw_items:
            ret_sym = (item.get("symbol") or "").strip().upper()
            if not ret_sym:
                continue

            last_p = (
                item.get("regularMarketPrice")
                or item.get("fulldayPrice")
                or item.get("bid")
                or item.get("ask")
                or item.get("postMarketPrice")
                or item.get("preMarketPrice")
            )
            try:
                last_p = float(last_p) if last_p is not None else None
            except (ValueError, TypeError):
                last_p = None

            prev_c = item.get("regularMarketPreviousClose")
            try:
                prev_c = float(prev_c) if prev_c is not None else None
            except (ValueError, TypeError):
                prev_c = None

            open_p = item.get("regularMarketOpen")
            try:
                open_p = float(open_p) if open_p is not None else None
            except (ValueError, TypeError):
                open_p = None

            day_h = item.get("regularMarketDayHigh")
            try:
                day_h = float(day_h) if day_h is not None else None
            except (ValueError, TypeError):
                day_h = None

            day_l = item.get("regularMarketDayLow")
            try:
                day_l = float(day_l) if day_l is not None else None
            except (ValueError, TypeError):
                day_l = None

            yr_h = item.get("fiftyTwoWeekHigh")
            try:
                yr_h = float(yr_h) if yr_h is not None else None
            except (ValueError, TypeError):
                yr_h = None

            yr_l = item.get("fiftyTwoWeekLow")
            try:
                yr_l = float(yr_l) if yr_l is not None else None
            except (ValueError, TypeError):
                yr_l = None

            vol = item.get("regularMarketVolume")
            try:
                vol = int(vol) if vol is not None else None
            except (ValueError, TypeError):
                vol = None

            avg_vol = item.get("averageDailyVolume3Month") or item.get("averageDailyVolume10Day")
            try:
                avg_vol = int(avg_vol) if avg_vol is not None else None
            except (ValueError, TypeError):
                avg_vol = None

            mcap = item.get("marketCap")
            try:
                mcap = float(mcap) if mcap is not None else None
            except (ValueError, TypeError):
                mcap = None

            currency = item.get("currency")
            if not currency:
                currency = "INR" if market_of(ret_sym) == "IN" else "USD"

            session = _get_market_session_status(ret_sym)
            is_weekend = session.get("is_weekend", False)

            # If weekend or data missing/identical, anchor to settled trading history
            if last_p is None or prev_c is None or (is_weekend and prev_c is not None and abs(last_p - prev_c) < 0.001):
                try:
                    with _connect(settings) as conn:
                        p_rows = conn.execute(
                            "SELECT date, close, open, high, low, volume FROM price_history WHERE ticker = ? AND strftime('%w', date) NOT IN ('0', '6') ORDER BY date DESC LIMIT 2",
                            (ret_sym,),
                        ).fetchall()
                        if p_rows and len(p_rows) >= 1:
                            last_p = last_p or float(p_rows[0][1] or 0.0)
                            if len(p_rows) >= 2:
                                prev_c = float(p_rows[1][1] or 0.0)
                except Exception:
                    pass

            if last_p is None or last_p <= 0:
                continue

            price_delay_status, is_price_stale = calculate_quote_staleness(now_iso, session)

            quote: dict[str, Any] = {
                "ticker": ret_sym,
                "current_price": round(float(last_p), 2),
                "previous_close": round(float(prev_c), 2) if prev_c is not None and prev_c > 0 else None,
                "day_change": round(float(last_p - prev_c), 2) if prev_c is not None and prev_c > 0 else None,
                "day_change_pct": round(float((last_p / prev_c - 1.0) * 100.0), 2) if prev_c is not None and prev_c > 0 else None,
                "day_open": round(float(open_p), 2) if open_p is not None else None,
                "day_high": round(float(day_h), 2) if day_h is not None else None,
                "day_low": round(float(day_l), 2) if day_l is not None else None,
                "week_52_high": round(float(yr_h), 2) if yr_h is not None else None,
                "week_52_low": round(float(yr_l), 2) if yr_l is not None else None,
                "volume": int(vol) if vol is not None else None,
                "avg_volume": int(avg_vol) if avg_vol is not None else None,
                "market_cap": float(mcap) if mcap is not None else None,
                "currency": currency,
                "is_live": bool(session.get("is_open", False)),
                "last_updated": now_iso,
                "quote_timestamp": now_iso,
                "price_delay_status": price_delay_status,
                "is_price_stale": is_price_stale,
                "pct_from_52w_high": None,
                "pct_from_52w_low": None,
            }

            if quote["week_52_high"] and quote["week_52_high"] > 0:
                quote["pct_from_52w_high"] = round((quote["current_price"] / quote["week_52_high"] - 1.0) * 100.0, 2)
            if quote["week_52_low"] and quote["week_52_low"] > 0:
                quote["pct_from_52w_low"] = round((quote["current_price"] / quote["week_52_low"] - 1.0) * 100.0, 2)

            mapped_tickers = ticker_map.get(ret_sym, [ret_sym])
            for orig_t in mapped_tickers:
                t_quote = dict(quote)
                t_quote["ticker"] = orig_t
                results[orig_t] = t_quote
            results[ret_sym] = quote

            valid_sync_items.append({
                "sym": ret_sym,
                "last_p": last_p,
                "prev_c": prev_c,
                "open_p": open_p,
                "day_h": day_h,
                "day_l": day_l,
                "vol": vol,
                "mcap": mcap,
                "is_weekend": is_weekend,
            })

        if sync_db and valid_sync_items:
            try:
                today_str = datetime.now().strftime("%Y-%m-%d")
                now_str = datetime.now().isoformat(timespec="seconds")

                price_history_rows = [
                    (
                        item["sym"],
                        today_str,
                        item["open_p"] if item["open_p"] is not None else item["last_p"],
                        item["day_h"] if item["day_h"] is not None else item["last_p"],
                        item["day_l"] if item["day_l"] is not None else item["last_p"],
                        item["last_p"],
                        item["vol"] if item["vol"] is not None else 0,
                    )
                    for item in valid_sync_items
                    if not item["is_weekend"]
                ]

                ticker_rows = [
                    (
                        item["sym"],
                        item["mcap"],
                        now_str if item["mcap"] is not None else None,
                        now_str,
                        now_str,
                    )
                    for item in valid_sync_items
                ]

                with _connect(settings) as conn:
                    if price_history_rows:
                        try:
                            conn.executemany(
                                """INSERT INTO price_history (ticker, date, open, high, low, close, volume)
                                   VALUES (?, ?, ?, ?, ?, ?, ?)
                                   ON CONFLICT(ticker, date) DO UPDATE SET
                                       high = MAX(COALESCE(price_history.high, excluded.high), excluded.high),
                                       low = MIN(COALESCE(price_history.low, excluded.low), excluded.low),
                                       close = excluded.close,
                                       volume = COALESCE(excluded.volume, price_history.volume)
                                """,
                                price_history_rows,
                            )
                        except Exception as e:
                            logger.debug("[BATCH-QUOTES] price_history batch sync error: %s", e)

                    if ticker_rows:
                        try:
                            conn.executemany(
                                """INSERT INTO tickers (ticker, market_cap, market_cap_updated_at, prices_fetched_at, last_updated)
                                   VALUES (?, ?, ?, ?, ?)
                                   ON CONFLICT(ticker) DO UPDATE SET
                                       market_cap = COALESCE(excluded.market_cap, tickers.market_cap),
                                       market_cap_updated_at = CASE WHEN excluded.market_cap IS NOT NULL THEN excluded.market_cap_updated_at ELSE tickers.market_cap_updated_at END,
                                       prices_fetched_at = excluded.prices_fetched_at,
                                       last_updated = excluded.last_updated
                                """,
                                ticker_rows,
                            )
                        except Exception as e:
                            logger.debug("[BATCH-QUOTES] tickers batch sync error: %s", e)

                    conn.commit()

                for item in valid_sync_items:
                    clear_price_df_cache(item["sym"])
            except Exception as sync_err:
                logger.debug("[BATCH-QUOTES] SQLite batch sync failed: %s", sync_err)

    elapsed_all_ms = int((time.perf_counter() - t0_all) * 1000)
    logger.info(
        "[BATCH-QUOTES] Successfully retrieved quotes for %d/%d tickers in %d ms",
        len(results),
        len(unique_tickers),
        elapsed_all_ms,
    )
    return results


def fetch_batch_live_quotes(
    tickers: list[str],
    settings: Settings | None = None,
    sync_db: bool = True,
    max_workers: int = 10,
    force: bool = False,
    ttl_minutes: int = 5,
) -> dict[str, dict[str, Any]]:
    """Fetch live real-time market quotes for multiple tickers in parallel batches.

    Uses DB-first TTL caching: queries SQLite price_history and tickers in a single
    batch query. Fresh tickers within TTL (or settled on weekends/post-market) are
    served immediately (<10ms). Stale tickers are fetched in multi-ticker batches
    via Yahoo Finance quote API (up to 50 tickers per HTTP request), with fallback
    to concurrent individual fetch_live_quote only for missing or failed tickers.
    """
    settings = settings or Settings()
    if not tickers:
        return {}

    unique_tickers = list(dict.fromkeys([t.strip().upper() for t in tickers if t]))
    results: dict[str, dict[str, Any]] = {}
    stale_tickers: list[str] = []

    if not force:
        cached_records = _get_cached_quotes_batch(unique_tickers, settings=settings)
        for t in unique_tickers:
            sym = canonical_symbol(t)
            record = cached_records.get(sym) or cached_records.get(t)
            session = _get_market_session_status(sym)
            if record and _is_cached_quote_fresh(record, session, ttl_minutes=ttl_minutes):
                results[t] = _build_quote_from_cached_record(t, record, session)
            elif (session.get("is_holiday") or session.get("is_weekend") or not session.get("is_open")) and record and record.get("cur_close") and float(record.get("cur_close") or 0) > 0:
                results[t] = _build_quote_from_cached_record(t, record, session)
            else:
                # If off-market and not in batch CTE, attempt quick local price history lookup before falling back to network
                if session.get("is_holiday") or session.get("is_weekend") or not session.get("is_open"):
                    try:
                        hist_df = load_prices(sym, settings)
                        if not hist_df.empty and "close" in hist_df.columns:
                            closes = hist_df["close"].dropna()
                            if len(closes) > 0:
                                last_c = float(closes.iloc[-1])
                                prev_c_val = float(closes.iloc[-2]) if len(closes) >= 2 else last_c
                                results[t] = {
                                    "ticker": t,
                                    "current_price": round(last_c, 2),
                                    "previous_close": round(prev_c_val, 2),
                                    "day_change": round(last_c - prev_c_val, 2),
                                    "day_change_pct": round(((last_c - prev_c_val) / prev_c_val) * 100.0, 2) if prev_c_val > 0 else 0.0,
                                    "volume": int(hist_df["volume"].iloc[-1]) if "volume" in hist_df.columns else 0,
                                    "is_live": False,
                                    "last_updated": datetime.now().isoformat(),
                                }
                                continue
                    except Exception:
                        pass
                stale_tickers.append(t)
    else:
        stale_tickers = list(unique_tickers)

    fresh_count = len(results)
    stale_count = len(stale_tickers)
    logger.info(
        "[BATCH-QUOTES] Cache: %d fresh served from SQLite, %d stale fetched via network",
        fresh_count,
        stale_count,
    )

    if stale_tickers:
        batch_quotes = _fetch_yfinance_batch_quotes(
            stale_tickers, settings=settings, sync_db=sync_db
        )
        for t, q in batch_quotes.items():
            results[t] = q

        missing_tickers = [
            t for t in stale_tickers
            if t not in results or results[t].get("current_price") is None
        ]
        if missing_tickers:
            logger.info(
                "[BATCH-QUOTES] %d/%d tickers fetched in batch; falling back to individual fetch for %d tickers",
                len(stale_tickers) - len(missing_tickers),
                len(stale_tickers),
                len(missing_tickers),
            )
            from concurrent.futures import ThreadPoolExecutor

            def _worker(t: str) -> tuple[str, dict[str, Any]]:
                return t, fetch_live_quote(
                    t, settings=settings, sync_db=sync_db, force=force, ttl_minutes=ttl_minutes, silent=True
                )

            with ThreadPoolExecutor(max_workers=min(max_workers, len(missing_tickers))) as executor:
                for t, q in executor.map(_worker, missing_tickers):
                    results[t] = q
    else:
        logger.debug(
            "[BATCH-QUOTES] All %d tickers served directly from SQLite cache (0 network requests)",
            len(unique_tickers),
        )

    for orig in tickers:
        if orig and orig.strip():
            orig_upper = orig.strip().upper()
            if orig_upper in results and orig not in results:
                results[orig] = results[orig_upper]

    return results


def get_latest_cached_prices(
    tickers: list[str],
    settings: Settings | None = None,
) -> dict[str, dict[str, Any]]:
    """Batch retrieve the latest cached price record for a list of tickers from SQLite price_history.

    Returns a dict mapping ticker -> {ticker, date, open, high, low, close, volume}.
    Uses an indexed MAX(date) self-join to extract the latest bar per ticker in a single fast query.
    """
    settings = settings or Settings()
    if not tickers:
        return {}

    unique_tickers = list(dict.fromkeys([canonical_symbol(t) for t in tickers if t]))
    results: dict[str, dict[str, Any]] = {}

    try:
        with _connect(settings) as conn:
            placeholders = ",".join("?" for _ in unique_tickers)
            query = f"""
                SELECT p.ticker, p.date, p.open, p.high, p.low, p.close, p.volume
                FROM price_history p
                INNER JOIN (
                    SELECT ticker, MAX(date) AS max_date
                    FROM price_history
                    WHERE ticker IN ({placeholders})
                    GROUP BY ticker
                ) m ON p.ticker = m.ticker AND p.date = m.max_date
            """
            rows = conn.execute(query, unique_tickers).fetchall()
            for r in rows:
                sym = r[0]
                close_p = float(r[5]) if r[5] is not None else None
                if close_p is not None:
                    results[sym] = {
                        "ticker": sym,
                        "date": str(r[1]),
                        "open": float(r[2]) if r[2] is not None else None,
                        "high": float(r[3]) if r[3] is not None else None,
                        "low": float(r[4]) if r[4] is not None else None,
                        "close": round(close_p, 2),
                        "volume": int(r[6]) if r[6] is not None else None,
                    }
    except Exception as e:
        logger.debug("[GET-LATEST-PRICES] Error querying price_history: %s", e)

    # Also map any requested original aliases to their canonical result
    for orig in tickers:
        if orig and orig.strip():
            canon = canonical_symbol(orig)
            if canon in results and orig not in results:
                results[orig] = results[canon]

    return results



