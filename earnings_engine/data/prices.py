"""SQLite-backed price data access and ingestion."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import yfinance as yf

import os
import shutil

from earnings_engine.config import Settings
from earnings_engine.logging_utils import get_logger

logger = get_logger("earnings_engine.data.prices")

COLUMNS = ["open", "high", "low", "close", "volume"]
DB_FILENAME = os.getenv("EARNINGS_ENGINE_DB_NAME", "money_club.sqlite3")


def _cache_path(settings: Settings) -> Path:
    target_path = settings.data_dirs["prices"] / DB_FILENAME
    if not target_path.exists():
        legacy_path = settings.data_dirs["prices"] / "prices.sqlite3"
        if legacy_path.exists() and legacy_path.stat().st_size > 0:
            try:
                shutil.copy2(legacy_path, target_path)
                logger.info("Migrated legacy prices.sqlite3 to %s", target_path)
            except Exception as exc:
                logger.warning("Could not migrate legacy DB: %s; using legacy", exc)
                return legacy_path
    return target_path


def _empty_frame() -> pd.DataFrame:
    df = pd.DataFrame(columns=COLUMNS)
    df.index.name = "date"
    return df


def _connect(settings: Settings) -> sqlite3.Connection:
    settings.ensure_dirs()
    connection = sqlite3.connect(_cache_path(settings))
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS price_history (
            ticker TEXT NOT NULL,
            date TEXT NOT NULL,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume REAL,
            PRIMARY KEY (ticker, date)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS ticker_metrics (
            ticker TEXT NOT NULL,
            as_of_date TEXT NOT NULL,
            metrics TEXT NOT NULL,
            PRIMARY KEY (ticker, as_of_date)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS price_fetch_log (
            ticker     TEXT PRIMARY KEY,
            fetched_at TEXT NOT NULL
        )
        """
    )
    connection.commit()
    return connection


def _is_fresh(ticker: str, settings: Settings) -> bool:
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
    with _connect(settings) as connection:
        connection.execute(
            "INSERT OR REPLACE INTO price_fetch_log (ticker, fetched_at) VALUES (?, ?)",
            (ticker, datetime.now().isoformat(timespec="seconds")),
        )
        connection.commit()


def _fetch_log_time(ticker: str, settings: Settings) -> datetime | None:
    """Return the last-fetched timestamp for a ticker (None if never logged)."""
    path = _cache_path(settings)
    if not path.exists():
        return None
    with _connect(settings) as connection:
        row = connection.execute(
            "SELECT fetched_at FROM price_fetch_log WHERE ticker = ?", (ticker,)
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
    if not force and _is_fresh(ticker, settings) and prices_recent_enough(ticker, settings):
        return load_prices(ticker, settings)

    # Resolve alias if ticker is known to be renamed/rebranded
    fetch_symbol = KNOWN_TICKER_ALIASES.get(ticker.upper(), ticker)

    # Delta fetch: only download the dates we're missing.  A 5-day overlap
    # buffer means a prior day's interrupted/partial write is corrected by the
    # fresh yfinance data (yfinance returns enough rows for the overlap).
    start = settings.history_start
    last_cached = _last_cached_date(ticker, settings)
    if last_cached is not None:
        overlap = pd.Timedelta(days=5)
        start = (last_cached - overlap).strftime("%Y-%m-%d")
        logger.info(
            "downloading price delta ticker=%s from=%s (last cached %s)",
            fetch_symbol, start, last_cached.date(),
        )
    else:
        logger.info("downloading full prices ticker=%s from=%s", fetch_symbol, start)

    try:
        raw = yf.download(fetch_symbol, start=start, auto_adjust=True, progress=False, threads=False)
    except Exception as exc:
        logger.warning("failed to download prices for ticker=%s (%s): %s", ticker, fetch_symbol, exc)
        raw = None

    if raw is None or raw.empty:
        _mark_fetched(ticker, settings)
        return load_prices(ticker, settings) if _is_fresh(ticker, settings) else _empty_frame()

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
    logger.info("price data normalized ticker=%s rows=%s", ticker, len(df))
    for col in COLUMNS:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["volume"] = df["volume"].astype("Int64")
    df.index = pd.to_datetime(df.index)
    df.index = df.index.tz_localize(None)
    df.index.name = "date"
    df = df.dropna(how="all")

    if last_cached is not None:
        # Merge delta into existing history — do NOT wipe the cache.
        _merge_prices(ticker, settings, df)
        return load_prices(ticker, settings)

    _write_prices(ticker, settings, df)
    return df


def load_prices(ticker: str, settings: Settings) -> pd.DataFrame:
    """Load prices from SQLite if present."""
    with _connect(settings) as connection:
        rows = connection.execute(
            "SELECT date, open, high, low, close, volume FROM price_history WHERE ticker = ? ORDER BY date",
            (ticker,),
        ).fetchall()

    if not rows:
        return _empty_frame()

    frame = pd.DataFrame(rows, columns=["date", *COLUMNS])
    frame["date"] = pd.to_datetime(frame["date"])
    frame = frame.set_index("date")
    for col in COLUMNS:
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    frame = frame.astype({"volume": "Int64"}, errors="ignore")
    frame.index.name = "date"
    return frame


def store_price_metrics(ticker: str, settings: Settings, metrics: dict[str, Any], as_of_date: str | None = None) -> None:
    """Persist derived metrics for a ticker in the SQLite cache."""
    as_of_date_value = as_of_date or pd.Timestamp.now().strftime("%Y-%m-%d")
    payload = json.dumps(metrics, sort_keys=True, default=str)
    with _connect(settings) as connection:
        connection.execute(
            "INSERT OR REPLACE INTO ticker_metrics (ticker, as_of_date, metrics) VALUES (?, ?, ?)",
            (ticker, as_of_date_value, payload),
        )
        connection.commit()


def load_price_metrics(ticker: str, settings: Settings, as_of_date: str | None = None) -> dict[str, Any] | None:
    """Load previously persisted metrics for a ticker and day if they exist."""
    as_of_date_value = as_of_date or pd.Timestamp.now().strftime("%Y-%m-%d")
    with _connect(settings) as connection:
        row = connection.execute(
            "SELECT metrics FROM ticker_metrics WHERE ticker = ? AND as_of_date = ?",
            (ticker, as_of_date_value),
        ).fetchone()

    if not row:
        return None
    return json.loads(row[0])


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
