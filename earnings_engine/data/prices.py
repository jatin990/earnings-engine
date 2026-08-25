"""SQLite-backed price data access and ingestion."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import yfinance as yf

import os
import shutil

from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection, is_turso_enabled, _cache_path
from earnings_engine.logging_utils import get_logger

logger = get_logger("earnings_engine.data.prices")

COLUMNS = ["open", "high", "low", "close", "volume"]

_PRICE_DF_MEMORY_CACHE: dict[str, tuple[float, pd.DataFrame]] = {}
_PRICE_CACHE_LOCK = threading.Lock()
_PRICE_CACHE_TTL_SECONDS = 120.0


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
    if not is_turso_enabled():
        path = _cache_path(settings)
        if not path.exists():
            return False

    with _connect(settings) as connection:
        row = connection.execute(
            "SELECT COUNT(*) FROM price_history WHERE ticker = ?",
            (ticker,),
        ).fetchone()

    return bool(row and row[0])


def _last_cached_date(ticker: str, settings: Settings) -> pd.Timestamp | None:
    """Return the most recent date for a ticker already in the price cache.

    Returns ``None`` if the ticker has no cached rows.
    """
    if not is_turso_enabled():
        path = _cache_path(settings)
        if not path.exists():
            return None

    with _connect(settings) as connection:
        row = connection.execute(
            "SELECT MAX(date) FROM price_history WHERE ticker = ?",
            (ticker,),
        ).fetchone()

    if not row or not row[0]:
        return None
    return pd.Timestamp(row[0])


def _mark_fetched(ticker: str, settings: Settings) -> None:
    """Record the moment this ticker's prices were last written to the cache."""
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
            (ticker, now_str, now_str),
        )
        connection.commit()


def _fetch_log_time(ticker: str, settings: Settings) -> datetime | None:
    """Return the last-fetched timestamp for a ticker (None if never logged)."""
    with _connect(settings) as connection:
        row = connection.execute(
            "SELECT prices_fetched_at FROM tickers WHERE ticker = ?", (ticker,)
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
    market has already closed for the day (prices are settled), or when there is
    no recorded fetch stamp (legacy/seeded rows) — the last case preserves the
    original behaviour so existing callers/tests keep working.
    """
    fetched = _fetch_log_time(ticker, settings)
    if fetched is None:
        # No stamp recorded (e.g. rows seeded directly) -> treat as usable.
        return True
    now = datetime.now()
    if (now - fetched).total_seconds() <= ttl_minutes * 60:
        return True
    if now.hour >= MARKET_CLOSE_HOUR:
        return True
    return False


def _write_prices(ticker: str, settings: Settings, df: pd.DataFrame) -> None:
    if df.empty:
        return

    rows = []
    for stamp, row in df.iterrows():
        date_value = pd.Timestamp(stamp).strftime("%Y-%m-%d")
        rows.append(
            (
                ticker,
                date_value,
                float(row.get("open")) if pd.notna(row.get("open")) else None,
                float(row.get("high")) if pd.notna(row.get("high")) else None,
                float(row.get("low")) if pd.notna(row.get("low")) else None,
                float(row.get("close")) if pd.notna(row.get("close")) else None,
                float(row.get("volume")) if pd.notna(row.get("volume")) else None,
            )
        )

    with _connect(settings) as connection:
        connection.execute("DELETE FROM price_history WHERE ticker = ?", (ticker,))
        connection.executemany(
            "INSERT INTO price_history (ticker, date, open, high, low, close, volume) VALUES (?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        connection.commit()
    _mark_fetched(ticker, settings)


def _merge_prices(ticker: str, settings: Settings, df: pd.DataFrame) -> None:
    """Upsert new price rows into the cache, preserving existing history.

    Unlike ``_write_prices`` (which deletes the ticker's rows first), this
    INSERT OR REPLACE merges the downloaded delta with what is already cached,
    so a refreshed ticker keeps its full history while only the new dates are
    written.  Primary key is ``(ticker, date)`` so existing rows are replaced
    in place with the same authoritative values.
    """
    if df.empty:
        return

    rows = []
    for stamp, row in df.iterrows():
        date_value = pd.Timestamp(stamp).strftime("%Y-%m-%d")
        rows.append(
            (
                ticker,
                date_value,
                float(row.get("open")) if pd.notna(row.get("open")) else None,
                float(row.get("high")) if pd.notna(row.get("high")) else None,
                float(row.get("low")) if pd.notna(row.get("low")) else None,
                float(row.get("close")) if pd.notna(row.get("close")) else None,
                float(row.get("volume")) if pd.notna(row.get("volume")) else None,
            )
        )

    with _connect(settings) as connection:
        connection.executemany(
            "INSERT OR REPLACE INTO price_history (ticker, date, open, high, low, close, volume) VALUES (?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        connection.commit()
    _mark_fetched(ticker, settings)


KNOWN_TICKER_ALIASES: dict[str, str] = {
    "STERLITE.NS": "STLTECH.NS",
    "ZOMATO.NS": "ETERNAL.NS",
    "MINDTREE.NS": "LTIM.NS",
    "LTI.NS": "LTIM.NS",
    "CADILAHC.NS": "ZYDUSLIFE.NS",
    "HEXAWARE.NS": "HEXT.NS",
    "DHFL.NS": "PIRAMALFIN.NS",
}


def fetch_prices(ticker: str, settings: Settings, force: bool = False) -> pd.DataFrame:
    """Fetch prices from yfinance or load from SQLite.

    A 10-minute fetch cache (see ``prices_recent_enough``) prevents redundant
    yfinance hits during live scans: prices fetched within the TTL, or any time
    after the market closes, are reused without re-downloading.
    """
    sym = ticker.strip().upper()
    if not force:
        cached_df = load_prices(sym, settings)
        if not cached_df.empty and prices_recent_enough(sym, settings):
            logger.debug("[DATA-CACHE] [prices] Reusing cached price history for ticker=%s (within TTL)", sym)
            return cached_df

    clear_price_df_cache(sym)

    # Resolve alias if ticker is known to be renamed/rebranded
    fetch_symbol = KNOWN_TICKER_ALIASES.get(sym, sym)

    # Delta fetch: only download the dates we're missing. A 5-day overlap
    # buffer means a prior day's interrupted/partial write is corrected by the
    # fresh yfinance data (yfinance returns enough rows for the overlap).
    start = settings.history_start
    last_cached = _last_cached_date(sym, settings)
    if last_cached is not None:
        overlap = pd.Timedelta(days=5)
        start = (last_cached - overlap).strftime("%Y-%m-%d")
        logger.info(
            "[DATA-FETCH] [yfinance] Downloading price delta for ticker=%s (%s) from=%s (last cached: %s)",
            sym, fetch_symbol, start, last_cached.date(),
        )
    else:
        logger.info("[DATA-FETCH] [yfinance] Downloading full historical prices for ticker=%s (%s) from=%s", sym, fetch_symbol, start)

    from earnings_engine.data.providers.provider_manager import get_data_manager

    mgr = get_data_manager(settings)
    raw = mgr.fetch_ohlcv(ticker=fetch_symbol, start_date=start)
    try:
        from earnings_engine.rate_limits import record_request
        record_request("yfinance")
    except Exception:
        pass

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
    logger.info("[DATA-FETCH] Successfully normalized %d price rows for ticker=%s", len(df), sym)
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


def load_prices_batch(tickers: list[str], settings: Settings) -> dict[str, pd.DataFrame]:
    """Load price DataFrames for multiple tickers in a single batched database query with in-memory caching."""
    if not tickers:
        return {}

    cleaned = [t.strip().upper() for t in tickers if t and t.strip()]
    unique_tickers = list(dict.fromkeys(cleaned))
    result: dict[str, pd.DataFrame] = {}
    missing: list[str] = []

    for t in unique_tickers:
        cached = get_cached_price_df(t)
        if cached is not None:
            result[t] = cached
        else:
            missing.append(t)

    if not missing:
        return result

    CHUNK_SIZE = 200
    with _connect(settings) as connection:
        for i in range(0, len(missing), CHUNK_SIZE):
            chunk = missing[i : i + CHUNK_SIZE]
            placeholders = ",".join("?" for _ in chunk)
            rows = connection.execute(
                f"SELECT ticker, date, open, high, low, close, volume FROM price_history WHERE ticker IN ({placeholders}) ORDER BY ticker, date ASC",
                chunk,
            ).fetchall()

            grouped: dict[str, list[Any]] = {sym: [] for sym in chunk}
            for r in rows:
                grouped[r[0]].append((r[1], r[2], r[3], r[4], r[5], r[6]))

            for sym, row_list in grouped.items():
                if not row_list:
                    empty_df = _empty_frame()
                    result[sym] = empty_df
                    set_cached_price_df(sym, empty_df)
                else:
                    frame = pd.DataFrame(row_list, columns=["date", *COLUMNS])
                    frame["date"] = pd.to_datetime(frame["date"])
                    frame = frame.set_index("date")
                    for col in COLUMNS:
                        frame[col] = pd.to_numeric(frame[col], errors="coerce")
                    frame = frame.astype({"volume": "Int64"}, errors="ignore")
                    frame.index.name = "date"
                    result[sym] = frame
                    set_cached_price_df(sym, frame)

    return result


def load_prices(ticker: str, settings: Settings) -> pd.DataFrame:
    """Load prices from in-memory cache or SQLite if present."""
    if not ticker:
        return _empty_frame()
    sym = ticker.strip().upper()
    cached = get_cached_price_df(sym)
    if cached is not None:
        return cached
    res = load_prices_batch([sym], settings)
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
    as_of_date_value = as_of_date or pd.Timestamp.now().strftime("%Y-%m-%d")
    with _connect(settings) as connection:
        row = connection.execute(
            "SELECT metrics FROM tickers WHERE ticker = ? AND metrics_as_of_date = ?",
            (ticker, as_of_date_value),
        ).fetchone()

    if not row or not row[0]:
        return None
    return json.loads(row[0]) if isinstance(row[0], str) else row[0]


def _fetch_prices_for_ticker(args: tuple[str, Settings, bool]) -> tuple[str, int]:
    """Fetch prices for a single ticker. Returns (ticker, row_count)."""
    ticker, settings, force = args
    try:
        df = fetch_prices(ticker, settings, force=force)
        return (ticker, int(len(df)))
    except Exception:
        return (ticker, 0)


def ingest_prices(tickers: list[str], settings: Settings, force: bool = False) -> dict[str, int]:
    """Download or refresh cached price data for the requested tickers.

    Uses ThreadPoolExecutor with 10 workers, batched in groups of 50 with
    2-second delays between batches to avoid yfinance rate limits.
    Skips tickers with fresh cache unless force=True.
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

    logger.info("ingesting prices for %s tickers (%s cached, %s to fetch)",
                total, cached_hits, len(tickers_to_fetch))

    fetch_total = len(tickers_to_fetch)
    max_workers = max(1, getattr(settings, "price_fetch_workers", 10))
    for i in range(0, fetch_total, batch_size):
        batch = tickers_to_fetch[i:i + batch_size]
        batch_num = i // batch_size + 1
        total_batches = (fetch_total + batch_size - 1) // batch_size

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_ticker = {
                executor.submit(_fetch_prices_for_ticker, (ticker, settings, force)): ticker
                for ticker in batch
            }
            for future in as_completed(future_to_ticker):
                ticker, count = future.result()
                processed += 1
                results[ticker] = count

        logger.info("prices ingest batch %s/%s complete: %s/%s tickers processed",
                    batch_num, total_batches, processed, total)

        # Wait 2 seconds between batches (skip after last batch)
        if i + batch_size < fetch_total:
            time.sleep(2)

    ok = sum(1 for v in results.values() if v > 0)
    logger.info("prices ingest complete: %s/%s tickers with data", ok, total)
    return results


def fetch_live_quote(ticker: str, settings: Settings | None = None, sync_db: bool = True) -> dict[str, Any]:
    """Fetch authoritative live real-time market quote for a single ticker.

    Uses yfinance fast_info attribute access with fallbacks to intraday / daily
    history bars. If sync_db=True and a valid price is obtained, upserts today's
    live bar into price_history and updates tickers.market_cap so that all
    downstream technical analysis (RSI, EMAs, 52W range, swing channels, and
    AI consensus prompts) immediately run on real-time data.
    """
    settings = settings or Settings()
    sym = ticker.strip().upper()
    fetch_sym = KNOWN_TICKER_ALIASES.get(sym, sym)

    quote: dict[str, Any] = {
        "ticker": sym,
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

    try:
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

    except Exception as e:
        logger.debug("[LIVE-QUOTE] Failed fetching live quote for %s: %s", sym, e)

    if last_p is not None and last_p > 0:
        quote["current_price"] = round(float(last_p), 2)
        quote["is_live"] = True
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

        # Sync with SQLite cache
        if sync_db:
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

    return quote

