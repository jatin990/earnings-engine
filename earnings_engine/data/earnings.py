"""Cached earnings-event data access and ingestion."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd
import yfinance as yf

from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection, is_turso_enabled, _cache_path as _prices_cache_path
from earnings_engine.data.nse_api import fetch_event_calendar
from earnings_engine.logging_utils import get_logger

logger = get_logger("earnings_engine.data.earnings")

COLUMNS = ["earnings_date", "eps_estimate", "eps_reported", "surprise_pct"]


def _db_path(settings: Settings) -> Path:
    """Use the same SQLite database as prices."""
    return _prices_cache_path(settings)


def _connect(settings: Settings) -> Any:
    """Connect to the shared database and create the earnings table if missing."""
    settings.ensure_dirs()
    connection = get_db_connection(settings)

    # Check if the old schema (PK = ticker+earnings_date, no source in PK) exists.
    needs_migration = False
    try:
        schema = connection.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='earnings_history'").fetchone()
        if schema and "source TEXT DEFAULT 'yfinance'" in schema[0] and "PRIMARY KEY (ticker, earnings_date)" in schema[0]:
            needs_migration = True
    except sqlite3.OperationalError:
        pass

    if needs_migration:
        # Migrate from old schema (PK=ticker+earnings_date) to new schema
        # (PK=ticker+earnings_date+source) so both yfinance and nse rows can
        # coexist for the same date.
        connection.execute("ALTER TABLE earnings_history RENAME TO earnings_history_old")
        connection.execute(
            """
            CREATE TABLE earnings_history (
                ticker TEXT NOT NULL,
                earnings_date TEXT NOT NULL,
                eps_estimate REAL,
                eps_reported REAL,
                surprise_pct REAL,
                source TEXT NOT NULL DEFAULT 'yfinance',
                PRIMARY KEY (ticker, earnings_date, source)
            )
            """
        )
        # Copy old rows; rows that were re-tagged as 'nse' by the UPDATE
        # statement get duplicated as both 'yfinance' (with EPS) and 'nse'.
        connection.execute(
            """
            INSERT OR IGNORE INTO earnings_history (ticker, earnings_date, eps_estimate, eps_reported, surprise_pct, source)
            SELECT ticker, earnings_date, eps_estimate, eps_reported, surprise_pct, source FROM earnings_history_old
            """
        )
        # For rows tagged 'nse' that have EPS data, also create a 'yfinance'
        # copy so the yfinance calendar isn't lost.
        connection.execute(
            """
            INSERT OR IGNORE INTO earnings_history (ticker, earnings_date, eps_estimate, eps_reported, surprise_pct, source)
            SELECT ticker, earnings_date, eps_estimate, eps_reported, surprise_pct, 'yfinance'
            FROM earnings_history_old WHERE source = 'nse' AND eps_estimate IS NOT NULL
            """
        )
        connection.execute("DROP TABLE earnings_history_old")
    else:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS earnings_history (
                ticker TEXT NOT NULL,
                earnings_date TEXT NOT NULL,
                eps_estimate REAL,
                eps_reported REAL,
                surprise_pct REAL,
                source TEXT NOT NULL DEFAULT 'yfinance',
                PRIMARY KEY (ticker, earnings_date, source)
            )
            """
        )

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS earnings_freshness (
            ticker TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            PRIMARY KEY (ticker)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS earnings_fetch_log (
            fetch_date TEXT NOT NULL PRIMARY KEY,
            fetched_at TEXT NOT NULL,
            status TEXT NOT NULL,
            events_count INTEGER DEFAULT 0,
            inserted_count INTEGER DEFAULT 0
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS earnings_month_cache (
            cache_key TEXT NOT NULL PRIMARY KEY,
            updated_at TEXT NOT NULL,
            payload_json TEXT NOT NULL
        )
        """
    )
    connection.commit()
    return connection


def _is_fresh(ticker: str, settings: Settings) -> bool:
    """Check if earnings data is fresh in SQLite for the given ticker."""
    with _connect(settings) as connection:
        row = connection.execute(
            "SELECT fetched_at FROM earnings_freshness WHERE ticker = ?",
            (ticker,),
        ).fetchone()
    if not row:
        return False
    fetched_at = pd.Timestamp(row[0])
    age_days = (pd.Timestamp.now() - fetched_at).total_seconds() / 86400
    return age_days <= settings.cache_max_age_days


def _mark_fresh(ticker: str, settings: Settings) -> None:
    """Mark a ticker as freshly fetched in the freshness tracking table."""
    now = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    with _connect(settings) as connection:
        connection.execute(
            "INSERT OR REPLACE INTO earnings_freshness (ticker, fetched_at) VALUES (?, ?)",
            (ticker, now),
        )
        connection.commit()


def _write_earnings(ticker: str, settings: Settings, df: pd.DataFrame) -> None:
    """Write earnings data to SQLite, replacing any existing rows for the ticker."""
    if df.empty:
        return
    # Deduplicate by earnings_date (keep last occurrence) to avoid UNIQUE constraint errors
    df = df.drop_duplicates(subset=["earnings_date"], keep="last")
    rows = []
    for _, row in df.iterrows():
        edate = pd.Timestamp(row["earnings_date"]).strftime("%Y-%m-%d")
        rows.append(
            (
                ticker,
                edate,
                float(row["eps_estimate"]) if pd.notna(row.get("eps_estimate")) else None,
                float(row["eps_reported"]) if pd.notna(row.get("eps_reported")) else None,
                float(row["surprise_pct"]) if pd.notna(row.get("surprise_pct")) else None,
            )
        )
    with _connect(settings) as connection:
        connection.execute("DELETE FROM earnings_history WHERE ticker = ? AND source = 'yfinance'", (ticker,))
        connection.executemany(
            "INSERT OR REPLACE INTO earnings_history (ticker, earnings_date, eps_estimate, eps_reported, surprise_pct, source) VALUES (?, ?, ?, ?, ?, 'yfinance')",
            rows,
        )
        connection.commit()


def _migrate_from_parquet(ticker: str, settings: Settings) -> None:
    """Migrate earnings data from old Parquet cache to SQLite if it exists."""
    old_path = settings.data_dirs["earnings"] / f"{ticker}.parquet"
    if not old_path.exists():
        return
    try:
        df = pd.read_parquet(old_path)
        if not df.empty:
            _write_earnings(ticker, settings, df)
            logger.info("migrated earnings from parquet ticker=%s rows=%s", ticker, len(df))
        old_path.unlink()
    except Exception as e:
        logger.warning("parquet migration failed ticker=%s error=%s", ticker, e)


def fetch_earnings(ticker: str, settings: Settings, force: bool = False) -> pd.DataFrame:
    """Load cached earnings dates or download them when needed."""
    # Migrate from old Parquet cache if it exists
    _migrate_from_parquet(ticker, settings)

    if not force and _is_fresh(ticker, settings):
        logger.info("earnings cache hit ticker=%s", ticker)
        return load_earnings(ticker, settings)

    settings.ensure_dirs()
    try:
        logger.info("downloading earnings ticker=%s", ticker)
        raw = yf.Ticker(ticker).get_earnings_dates(limit=60)
    except Exception:
        raw = None

    if raw is None or (isinstance(raw, pd.DataFrame) and raw.empty):
        df = pd.DataFrame(columns=COLUMNS)
        df["earnings_date"] = pd.Series(dtype="datetime64[ns]")
        _mark_fresh(ticker, settings)
        return df

    frame = raw.copy()
    rename_map = {
        "EPS Estimate": "eps_estimate",
        "Reported EPS": "eps_reported",
        "Surprise(%)": "surprise_pct",
        "eps estimate": "eps_estimate",
        "reported eps": "eps_reported",
        "surprise(%)": "surprise_pct",
        "eps_estimate": "eps_estimate",
        "eps_reported": "eps_reported",
        "surprise_pct": "surprise_pct",
    }
    frame = frame.rename(columns={k: v for k, v in rename_map.items() if k in frame.columns})

    frame.index = pd.to_datetime(frame.index, utc=True)
    frame.index = frame.index.tz_convert(None)
    frame.index = frame.index.normalize()
    frame.index.name = "earnings_date"
    frame = frame.reset_index()

    for col in COLUMNS:
        if col not in frame.columns:
            frame[col] = pd.NA
    frame = frame[COLUMNS].copy()
    logger.info("earnings data normalized ticker=%s rows=%s", ticker, len(frame))
    frame["earnings_date"] = pd.to_datetime(frame["earnings_date"])
    frame = frame.sort_values("earnings_date").reset_index(drop=True)
    _write_earnings(ticker, settings, frame)
    _mark_fresh(ticker, settings)
    return frame


def load_earnings(ticker: str, settings: Settings, source: str | None = None) -> pd.DataFrame:
    """Load earnings dates from SQLite if present.

    If ``source`` is given (``"yfinance"``, ``"nse"``), only rows from that
    source are returned.  ``None`` means all sources (default), with rows
    deduplicated by earnings_date (preferring yfinance rows that have EPS data).
    """
    with _connect(settings) as connection:
        if source is None:
            rows = connection.execute(
                "SELECT earnings_date, eps_estimate, eps_reported, surprise_pct FROM earnings_history WHERE ticker = ? ORDER BY earnings_date",
                (ticker,),
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT earnings_date, eps_estimate, eps_reported, surprise_pct FROM earnings_history WHERE ticker = ? AND source = ? ORDER BY earnings_date",
                (ticker, source),
            ).fetchall()

    if not rows:
        return pd.DataFrame(columns=COLUMNS)

    frame = pd.DataFrame(rows, columns=COLUMNS)
    frame["earnings_date"] = pd.to_datetime(frame["earnings_date"])
    # When loading all sources, the same date may exist as both yfinance (with
    # EPS) and nse (without EPS).  Deduplicate by earnings_date, preferring
    # rows that have EPS data.
    if source is None:
        frame = frame.sort_values(
            "earnings_date", ascending=True
        ).drop_duplicates(
            subset=["earnings_date"], keep="first"
        ).reset_index(drop=True)
    return frame


def upcoming_earnings(tickers: list[str], settings: Settings, days: int = 14,
                      source: str | None = None,
                      start_date: str | None = None) -> pd.DataFrame:
    """List upcoming earnings events in the next N days.

    If ``source`` is given (``"yfinance"``, ``"nse"``), only rows from that
    source are returned.  ``None`` means all sources (default).  When all
    sources are loaded, a ``source`` column is included so the report can show
    which calendar each date came from.  Rows are NOT deduplicated by date —
    if a ticker has the same date from both yfinance and nse, both rows appear.

    The window is ``[start_date, start_date + days)``.  ``start_date`` defaults
    to today, so the default behaviour is unchanged (next ``days`` days).
    """
    if start_date is not None:
        start = pd.Timestamp(start_date).normalize()
    else:
        start = pd.Timestamp.today().normalize()
    end = start + pd.Timedelta(days=days)
    start_str = start.strftime("%Y-%m-%d")
    end_str = end.strftime("%Y-%m-%d")

    # Build a placeholder list for tickers that appear in overlapping universes.
    seen = set()
    unique_tickers = []
    for t in tickers:
        if t not in seen:
            seen.add(t)
            unique_tickers.append(t)

    if not unique_tickers:
        return pd.DataFrame(columns=["ticker", "earnings_date", "source"])

    placeholders = ", ".join(["?"] * len(unique_tickers))
    with _connect(settings) as connection:
        if source is None:
            sql = f"SELECT ticker, earnings_date, source FROM earnings_history WHERE ticker IN ({placeholders}) AND earnings_date >= ? AND earnings_date <= ? ORDER BY earnings_date"
            params = unique_tickers + [start_str, end_str]
        else:
            sql = f"SELECT ticker, earnings_date, source FROM earnings_history WHERE ticker IN ({placeholders}) AND source = ? AND earnings_date >= ? AND earnings_date <= ? ORDER BY earnings_date"
            params = unique_tickers + [source, start_str, end_str]
        rows = connection.execute(sql, params).fetchall()

    if not rows:
        return pd.DataFrame(columns=["ticker", "earnings_date", "source"])

    df = pd.DataFrame(rows, columns=["ticker", "earnings_date", "source"])
    df["earnings_date"] = pd.to_datetime(df["earnings_date"])
    loaded_tickers = df["ticker"].nunique()
    source_label = source if source is not None else "ALL_SOURCES"
    logger.info("[EARNINGS-CACHE] Loaded cached earnings dates for %s/%s tickers (source=%s, window: %s to %s)", loaded_tickers, len(unique_tickers), source_label, start_str, end_str)
    return df.sort_values("earnings_date").reset_index(drop=True)


def _fetch_earnings_for_ticker(args: tuple[str, Settings, bool]) -> tuple[str, int]:
    """Fetch earnings for a single ticker. Returns (ticker, row_count)."""
    ticker, settings, force = args
    try:
        df = fetch_earnings(ticker, settings, force=force)
        return (ticker, int(len(df)))
    except Exception:
        return (ticker, 0)


def ingest_nse_result_calendar(settings: Settings, days: int = 60) -> dict[str, int]:
    """Ingest upcoming result dates from the official NSE event-calendar API.

    One API call covers all NSE stocks.  Result dates are written into the
    shared SQLite ``earnings_history`` table using INSERT OR IGNORE so existing
    historical EPS data from yfinance is preserved — only new result dates are
    added.

    Returns ``{"total": ..., "inserted": ..., "errors": ...}``.
    """
    from datetime import date, timedelta

    today = date.today()
    raw = fetch_event_calendar(today, today + timedelta(days=days))
    if "error" in raw:
        logger.warning("nse event-calendar ingest failed: %s", raw["error"])
        return {"total": 0, "inserted": 0, "errors": 1}

    entries = raw if isinstance(raw, list) else raw.get("data", raw.get("result", []))
    if not isinstance(entries, list):
        logger.warning("nse event-calendar returned unexpected payload type=%s", type(raw).__name__)
        return {"total": 0, "inserted": 0, "errors": 1}

    rows: list[tuple[str, str]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        # Only keep financial-results events (board meetings for results).
        purpose = str(entry.get("purpose", "")).lower()
        if "financial result" not in purpose and "results" not in purpose:
            continue
        sym = str(entry.get("symbol", "")).strip().upper()
        if not sym:
            continue
        # NSE returns bare codes; yfinance needs the .NS suffix.
        if not sym.endswith(".NS"):
            sym = sym + ".NS"
        result_date = entry.get("date") or entry.get("resultDate") or entry.get("bmDate")
        if not result_date:
            continue
        try:
            edate = pd.Timestamp(result_date).strftime("%Y-%m-%d")
        except Exception:
            continue
        rows.append((sym, edate))

    if not rows:
        logger.info("nse result-calendar returned no rows")
        return {"total": 0, "inserted": 0, "errors": 0}

    with _connect(settings) as connection:
        inserted = connection.executemany(
            "INSERT OR IGNORE INTO earnings_history (ticker, earnings_date, source) VALUES (?, ?, 'nse')",
            rows,
        ).rowcount
        connection.commit()

    logger.info("nse result-calendar ingest complete total=%s inserted=%s", len(rows), inserted)
    return {"total": len(rows), "inserted": inserted, "errors": 0}


def ingest_earnings_incremental(tickers: list[str], settings: Settings) -> dict[str, int]:
    """Fetch earnings only for tickers that are missing earnings data.
    
    Identifies tickers with NO earnings rows in earnings_history. For those,
    checks price_history for a listing date (MIN(date)) — skips tickers with
    no price history or listed < 90 days ago (too new for quarterly earnings).
    Only fetches earnings for tickers that should have earnings but don't.
    
    Returns {"total", "already_cached", "fetched", "skipped_no_listing", "errors"}.
    """
    import time
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    if not tickers:
        return {"total": 0, "already_cached": 0, "fetched": 0, "skipped_no_listing": 0, "errors": 0}
    
    total = len(tickers)
    batch_size = 50
    processed = 0
    already_cached = 0
    skipped_no_listing = 0
    errors = 0
    fetched = 0
    
    # Identify tickers that need earnings data
    tickers_to_fetch: list[str] = []
    with _connect(settings) as connection:
        for ticker in tickers:
            # Check if ticker already has earnings
            row = connection.execute(
                "SELECT COUNT(*) FROM earnings_history WHERE ticker = ?",
                (ticker,),
            ).fetchone()
            has_earnings = row and row[0] > 0
            
            if has_earnings:
                already_cached += 1
                processed += 1
                continue
            
            # Check if ticker has price history and get listing date
            price_row = connection.execute(
                "SELECT MIN(date), MAX(date) FROM price_history WHERE ticker = ?",
                (ticker,),
            ).fetchone()
            
            if not price_row or not price_row[0]:
                # No price history at all
                skipped_no_listing += 1
                processed += 1
                logger.info("skipping ticker=%s reason=no_price_history", ticker)
                continue
            
            listing_date = pd.Timestamp(price_row[0])
            age_days = (pd.Timestamp.now() - listing_date).total_seconds() / 86400
            
            if age_days < 90:
                # Too new for quarterly earnings
                skipped_no_listing += 1
                processed += 1
                logger.info("skipping ticker=%s reason=too_new listing_date=%s age_days=%.1f",
                           ticker, listing_date.date(), age_days)
                continue
            
            tickers_to_fetch.append(ticker)
    
    if already_cached == total:
        logger.info("all %s tickers already have earnings cached", total)
        return {"total": total, "already_cached": already_cached, "fetched": 0,
                "skipped_no_listing": 0, "errors": 0}
    
    logger.info("incremental earnings: %s total, %s cached, %s to fetch, %s skipped",
                total, already_cached, len(tickers_to_fetch), skipped_no_listing)
    
    # Fetch earnings for tickers that need it
    fetch_total = len(tickers_to_fetch)
    for i in range(0, fetch_total, batch_size):
        batch = tickers_to_fetch[i:i + batch_size]
        batch_num = i // batch_size + 1
        total_batches = (fetch_total + batch_size - 1) // batch_size
        
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_ticker = {
                executor.submit(_fetch_earnings_for_ticker, (ticker, settings, False)): ticker
                for ticker in batch
            }
            for future in as_completed(future_to_ticker):
                ticker, count = future.result()
                processed += 1
                if count > 0:
                    fetched += 1
                else:
                    errors += 1
        
        logger.info("earnings incremental batch %s/%s complete: %s/%s tickers processed",
                    batch_num, total_batches, processed, total)
        
        # Wait 2 seconds between batches (skip after last batch)
        if i + batch_size < fetch_total:
            time.sleep(2)
    
    logger.info("earnings incremental complete: %s fetched, %s errors, %s skipped_no_listing",
                fetched, errors, skipped_no_listing)
    return {
        "total": total,
        "already_cached": already_cached,
        "fetched": fetched,
        "skipped_no_listing": skipped_no_listing,
        "errors": errors,
    }


def ingest_earnings(tickers: list[str], settings: Settings, force: bool = False) -> dict[str, int]:
    """Download or refresh cached earnings data for the requested tickers.

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
            df = load_earnings(ticker, settings)
            results[ticker] = int(len(df))
            cached_hits += 1
            processed += 1
        else:
            tickers_to_fetch.append(ticker)

    if cached_hits == total:
        logger.info("earnings cache hit for all %s tickers, skipping fetch", total)
        return results

    logger.info("ingesting earnings for %s tickers (%s cached, %s to fetch)",
                total, cached_hits, len(tickers_to_fetch))

    fetch_total = len(tickers_to_fetch)
    for i in range(0, fetch_total, batch_size):
        batch = tickers_to_fetch[i:i + batch_size]
        batch_num = i // batch_size + 1
        total_batches = (fetch_total + batch_size - 1) // batch_size

        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_ticker = {
                executor.submit(_fetch_earnings_for_ticker, (ticker, settings, force)): ticker
                for ticker in batch
            }
            for future in as_completed(future_to_ticker):
                ticker, count = future.result()
                processed += 1
                results[ticker] = count

        logger.info("earnings ingest batch %s/%s complete: %s/%s tickers processed",
                    batch_num, total_batches, processed, total)

        # Wait 2 seconds between batches (skip after last batch)
        if i + batch_size < fetch_total:
            time.sleep(2)

    ok = sum(1 for v in results.values() if v > 0)
    logger.info("earnings ingest complete: %s/%s tickers with data", ok, total)
    return results


def get_fetch_record_status(settings: Settings) -> dict[str, Any]:
    """Get the fetch record status for the present day."""
    import json
    today_str = pd.Timestamp.today().strftime("%Y-%m-%d")
    with _connect(settings) as connection:
        row = connection.execute(
            "SELECT fetch_date, fetched_at, status, events_count, inserted_count FROM earnings_fetch_log WHERE fetch_date = ?",
            (today_str,),
        ).fetchone()
        
        # If no row for today, get latest entry
        if not row:
            row = connection.execute(
                "SELECT fetch_date, fetched_at, status, events_count, inserted_count FROM earnings_fetch_log ORDER BY fetch_date DESC LIMIT 1"
            ).fetchone()

        # Count total upcoming events in database
        total_events = connection.execute(
            "SELECT COUNT(*) FROM earnings_history WHERE earnings_date >= ?",
            (today_str,),
        ).fetchone()[0]

    if not row:
        return {
            "today": today_str,
            "synced_today": False,
            "last_fetched_at": None,
            "status": "NOT_SYNCED",
            "events_count": total_events,
            "inserted_count": 0,
        }

    fetch_date, fetched_at, status, events_count, inserted_count = row
    return {
        "today": today_str,
        "synced_today": (fetch_date == today_str),
        "last_fetched_at": fetched_at,
        "status": status if fetch_date == today_str else "STALE",
        "events_count": max(events_count, total_events),
        "inserted_count": inserted_count,
    }


def sync_present_day_earnings_delta(settings: Settings, force: bool = False) -> dict[str, Any]:
    """Check if earnings calendar for present day is fetched; if missing or stale, fetch delta and update record."""
    today_str = pd.Timestamp.today().strftime("%Y-%m-%d")
    status_info = get_fetch_record_status(settings)

    if not force and status_info.get("synced_today"):
        logger.info("Present day earnings calendar already synced today (%s)", today_str)
        return status_info

    logger.info("Fetching present day earnings delta for date=%s (force=%s)...", today_str, force)
    ingest_res = ingest_nse_result_calendar(settings, days=60)
    now_str = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    inserted = ingest_res.get("inserted", 0)
    total_found = ingest_res.get("total", 0)

    with _connect(settings) as connection:
        total_events = connection.execute(
            "SELECT COUNT(*) FROM earnings_history WHERE earnings_date >= ?",
            (today_str,),
        ).fetchone()[0]

        connection.execute(
            "INSERT OR REPLACE INTO earnings_fetch_log (fetch_date, fetched_at, status, events_count, inserted_count) VALUES (?, ?, ?, ?, ?)",
            (today_str, now_str, "UP_TO_DATE", total_events, inserted),
        )
        connection.commit()

    return {
        "today": today_str,
        "synced_today": True,
        "last_fetched_at": now_str,
        "status": "UP_TO_DATE",
        "events_count": total_events,
        "inserted_count": inserted,
        "total_calendar_events": total_found,
    }


def get_cached_month_filter(settings: Settings, cache_key: str = "ALL") -> dict[str, Any] | None:
    """Retrieve precalculated month filter payload from SQLite cache."""
    import json
    with _connect(settings) as connection:
        row = connection.execute(
            "SELECT payload_json, updated_at FROM earnings_month_cache WHERE cache_key = ?",
            (cache_key,),
        ).fetchone()
    if not row:
        return None
    try:
        data = json.loads(row[0])
        data["_cached_at"] = row[1]
        return data
    except Exception as e:
        logger.warning("Failed to decode cached month filter for key=%s: %s", cache_key, e)
        return None


def set_cached_month_filter(settings: Settings, cache_key: str, payload: dict[str, Any]) -> None:
    """Store precalculated month filter payload into SQLite cache."""
    import json
    now_str = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    payload_str = json.dumps(payload)
    with _connect(settings) as connection:
        connection.execute(
            "INSERT OR REPLACE INTO earnings_month_cache (cache_key, updated_at, payload_json) VALUES (?, ?, ?)",
            (cache_key, now_str, payload_str),
        )
        connection.commit()

