"""Ticker universes for supported markets, backed by shared SQLite database."""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection, is_turso_enabled, _cache_path as _prices_cache_path

UNIVERSE_DIR = Path(__file__).resolve().parent / "universes"
NSE_ALL_MAX_AGE_DAYS = 40
NSE_LARGE_CAP_MIN_CR = 1000  # 1000 crore = 10,000,000,000 rupees
MARKET_CAP_MAX_AGE_DAYS = 15  # same as earnings cache freshness

logger = logging.getLogger("earnings_engine.data.universe")

_SEED_NSE_TOP = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "ICICIBANK.NS", "INFY.NS",
    "BHARTIARTL.NS", "KOTAKBANK.NS", "SBIN.NS", "LT.NS", "AXISBANK.NS",
    "HINDUNILVR.NS", "ITC.NS", "ASIANPAINT.NS", "MARUTI.NS", "SUNPHARMA.NS",
    "NTPC.NS", "ULTRACEMCO.NS", "POWERGRID.NS", "ONGC.NS", "JSWSTEEL.NS",
    "TATASTEEL.NS", "M&M.NS", "WIPRO.NS", "TECHM.NS", "HCLTECH.NS",
    "BAJAJ-AUTO.NS", "TITAN.NS", "ADANIPORTS.NS", "HEROMOTOCO.NS", "INDUSINDBK.NS",
    "EICHERMOT.NS", "DIVISLAB.NS", "DRREDDY.NS", "CIPLA.NS", "NESTLEIND.NS",
    "GRASIM.NS", "BEL.NS", "IOC.NS", "BPCL.NS", "COALINDIA.NS",
    "BANKBARODA.NS", "PNB.NS", "SHREECEM.NS", "ETERNAL.NS",
]

_SEED_US_TOP = [
    "AAPL", "MSFT", "AMZN", "NVDA", "GOOGL", "META", "TSLA", "BRK-B", "LLY",
    "AVGO", "AMD", "COST", "PEP", "ADBE", "NFLX", "CRM", "INTC", "QCOM",
    "TXN", "AMGN", "WMT", "DIS", "ISRG", "INTU", "PYPL", "MRNA", "SPGI",
    "CSCO", "CMCSA", "NOW", "CAT", "ADP", "CSX", "GE", "SHOP", "PLTR",
    "CME", "VRTX", "ON", "ROKU", "PANW", "SBUX", "SQ", "UBER", "MELI",
]


# ---------------------------------------------------------------------------
# SQLite connection & schema
# ---------------------------------------------------------------------------

def _db_path(settings: Settings | None = None) -> Path:
    """Use the same SQLite database as prices."""
    if settings is None:
        settings = Settings()
    return _prices_cache_path(settings)


def _connect(settings: Settings | None = None) -> Any:
    """Connect to database and ensure universe tables and initial seeds exist."""
    if settings is None:
        settings = Settings()
    settings.ensure_dirs()
    from earnings_engine.data.migrations import apply_migrations
    apply_migrations(settings)
    conn = get_db_connection(settings)

    # Seed IN and US if universes table has no rows
    count = conn.execute("SELECT count(*) FROM universes").fetchone()[0]
    if count == 0:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for t in _SEED_NSE_TOP:
            conn.execute(
                "INSERT OR IGNORE INTO universes (universe_name, ticker, updated_at) VALUES (?, ?, ?)",
                ("IN", t, now),
            )
            conn.execute(
                "INSERT OR IGNORE INTO universes (universe_name, ticker, updated_at) VALUES (?, ?, ?)",
                ("nse_top", t, now),
            )
        for t in _SEED_US_TOP:
            conn.execute(
                "INSERT OR IGNORE INTO universes (universe_name, ticker, updated_at) VALUES (?, ?, ?)",
                ("US", t, now),
            )
            conn.execute(
                "INSERT OR IGNORE INTO universes (universe_name, ticker, updated_at) VALUES (?, ?, ?)",
                ("us_top", t, now),
            )

        # Also import any existing text files in universes directory if present
        if UNIVERSE_DIR.exists():
            for f in UNIVERSE_DIR.glob("*.txt"):
                name = f.stem
                if name.startswith("my_watchlist"):
                    continue
                try:
                    lines = [line.strip() for line in f.read_text(encoding="utf-8").splitlines() if line.strip() and not line.strip().startswith("#")]
                    for t in lines:
                        conn.execute(
                            "INSERT OR IGNORE INTO universes (universe_name, ticker, updated_at) VALUES (?, ?, ?)",
                            (name, t, now),
                        )
                except Exception:
                    pass
        conn.commit()

    # Auto-migrate rebranded/renamed symbols (e.g. ZOMATO.NS -> ETERNAL.NS)
    try:
        conn.execute("UPDATE universes SET ticker = 'ETERNAL.NS' WHERE ticker = 'ZOMATO.NS'")
        conn.commit()
    except Exception:
        pass

    return conn


# Backward-compatible alias
_connect_market_cap = _connect


# ---------------------------------------------------------------------------
# Market cap caching
# ---------------------------------------------------------------------------

def is_market_cap_fresh(ticker: str, settings: Settings | None = None) -> bool:
    """Check if market cap data is fresh in SQLite for the given ticker."""
    with _connect(settings) as connection:
        row = connection.execute(
            "SELECT market_cap_updated_at FROM tickers WHERE ticker = ?",
            (ticker,),
        ).fetchone()
        if not row or not row[0]:
            try:
                row = connection.execute(
                    "SELECT fetched_at FROM ticker_market_cap WHERE ticker = ?",
                    (ticker,),
                ).fetchone()
            except Exception:
                row = None
    if not row or not row[0]:
        return False
    fetched_at = pd.Timestamp(row[0])
    age_days = (pd.Timestamp.now() - fetched_at).total_seconds() / 86400
    return age_days <= MARKET_CAP_MAX_AGE_DAYS


def store_market_cap(ticker: str, market_cap: float | None, settings: Settings | None = None) -> None:
    """Store market cap for a ticker in SQLite."""
    now = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    with _connect(settings) as connection:
        # Upsert into unified tickers master table
        connection.execute(
            """
            INSERT INTO tickers (ticker, market_cap, market_cap_updated_at, last_updated)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(ticker) DO UPDATE SET
                market_cap = excluded.market_cap,
                market_cap_updated_at = excluded.market_cap_updated_at,
                last_updated = excluded.last_updated
            """,
            (ticker, market_cap, now, now),
        )
        # Also maintain legacy ticker_market_cap for backward compatibility
        try:
            connection.execute(
                "INSERT OR REPLACE INTO ticker_market_cap (ticker, market_cap, fetched_at) VALUES (?, ?, ?)",
                (ticker, market_cap, now),
            )
        except Exception:
            pass
        connection.commit()


def load_market_cap(ticker: str, settings: Settings | None = None) -> float | None:
    """Load market cap for a ticker from SQLite cache."""
    with _connect(settings) as connection:
        row = connection.execute(
            "SELECT market_cap FROM tickers WHERE ticker = ?",
            (ticker,),
        ).fetchone()
        if row and row[0] is not None:
            return float(row[0])
        try:
            legacy_row = connection.execute(
                "SELECT market_cap FROM ticker_market_cap WHERE ticker = ?",
                (ticker,),
            ).fetchone()
            return float(legacy_row[0]) if legacy_row and legacy_row[0] is not None else None
        except Exception:
            return None


def load_all_market_caps(settings: Settings | None = None) -> dict[str, float]:
    """Load all market caps from SQLite cache. Returns {ticker: market_cap}."""
    with _connect(settings) as connection:
        rows = connection.execute(
            "SELECT ticker, market_cap FROM tickers WHERE market_cap IS NOT NULL"
        ).fetchall()
        if not rows:
            try:
                rows = connection.execute(
                    "SELECT ticker, market_cap FROM ticker_market_cap WHERE market_cap IS NOT NULL"
                ).fetchall()
            except Exception:
                rows = []
    return {row[0]: float(row[1]) for row in rows if row[1] is not None}


# ---------------------------------------------------------------------------
# Universe CRUD (SQLite)
# ---------------------------------------------------------------------------

def is_universe_fresh(name: str, max_age_days: int = NSE_ALL_MAX_AGE_DAYS, settings: Settings | None = None) -> bool:
    """Check if a dynamic universe is fresh in SQLite."""
    with _connect(settings) as connection:
        row = connection.execute(
            "SELECT fetched_at FROM universe_freshness WHERE LOWER(universe_name) = LOWER(?)",
            (name,),
        ).fetchone()
    if not row:
        return False
    fetched_at = pd.Timestamp(row[0])
    age_days = (pd.Timestamp.now() - fetched_at).total_seconds() / 86400
    return age_days <= max_age_days


def store_universe(name: str, tickers: list[str], settings: Settings | None = None) -> None:
    """Store/replace an entire universe in SQLite."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    clean_name = name.strip()
    with _connect(settings) as connection:
        connection.execute("DELETE FROM universes WHERE LOWER(universe_name) = LOWER(?)", (clean_name,))
        for t in tickers:
            t = t.strip().upper()
            if t:
                connection.execute(
                    "INSERT OR REPLACE INTO universes (universe_name, ticker, updated_at) VALUES (?, ?, ?)",
                    (clean_name.lower(), t, now),
                )
        connection.execute(
            "INSERT OR REPLACE INTO universe_freshness (universe_name, fetched_at) VALUES (?, ?)",
            (clean_name.lower(), now),
        )
        connection.commit()


def add_to_universe(name: str, ticker: str, settings: Settings | None = None) -> bool:
    """Add a ticker to a universe in SQLite."""
    ticker = ticker.strip().upper()
    if not ticker:
        return False
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _connect(settings) as connection:
        connection.execute(
            "INSERT OR REPLACE INTO universes (universe_name, ticker, updated_at) VALUES (?, ?, ?)",
            (name, ticker, now),
        )
        connection.commit()
    return True


def remove_from_universe(name: str, ticker: str, settings: Settings | None = None) -> bool:
    """Remove a ticker from a universe in SQLite."""
    ticker = ticker.strip().upper()
    if not ticker:
        return False
    with _connect(settings) as connection:
        cursor = connection.execute(
            "DELETE FROM universes WHERE universe_name = ? AND ticker = ?",
            (name, ticker),
        )
        connection.commit()
        return cursor.rowcount > 0


def list_universes(settings: Settings | None = None) -> list[dict[str, Any]]:
    """List all available universes from SQLite."""
    with _connect(settings) as connection:
        rows = connection.execute(
            "SELECT universe_name, count(ticker), max(updated_at) FROM universes GROUP BY universe_name ORDER BY universe_name ASC"
        ).fetchall()
    return [
        {"name": row[0], "tickers_count": row[1], "updated_at": row[2]}
        for row in rows
    ]


def get_universe(name: str, settings: Settings | None = None) -> list[str]:
    """Get tickers in a universe from SQLite."""
    clean_name = name.lower().strip()
    with _connect(settings) as connection:
        rows = connection.execute(
            "SELECT ticker FROM universes WHERE LOWER(universe_name) = ? ORDER BY rowid ASC",
            (clean_name,),
        ).fetchall()
        if rows:
            return [row[0] for row in rows]

    # Fallback to seed universes if not populated
    if clean_name in ("nse_top", "in", "nse"):
        return list(_SEED_NSE_TOP)
    elif clean_name in ("us_top", "us"):
        return list(_SEED_US_TOP)

    return []


UNIVERSE_METADATA: dict[str, dict[str, Any]] = {
    "nse_top": {
        "name": "nse_top",
        "display_name": "🇮🇳 NSE Top 50 (NIFTY 50 Bluechips)",
        "market": "IN",
        "type": "universe",
        "is_builtin": True,
        "is_under_100": True,
        "summary": "Top liquid blue-chip Indian large-cap stocks listed on the National Stock Exchange of India (NSE).",
        "explanation": "Includes benchmark NIFTY 50 market leaders (Reliance, TCS, HDFC Bank, Infosys, ICICI Bank, Bharti Airtel, etc.) representing India's highest market capitalization and volume leaders across banking, IT, energy, consumer, and pharma.",
        "selection_criteria": "Top 50 high-volume, highly-liquid large-cap equities on the NSE.",
    },
    "in": {
        "name": "in",
        "display_name": "🇮🇳 All Indian Equities (NSE Core)",
        "market": "IN",
        "type": "universe",
        "is_builtin": True,
        "is_under_100": True,
        "summary": "Core Indian universe covering all primary tracked equities on the NSE.",
        "explanation": "Primary Indian market universe used for earnings forecasts, volatility tracking, and swing range identification.",
        "selection_criteria": "Core Indian stocks listed on NSE with active price histories.",
    },
    "us_top": {
        "name": "us_top",
        "display_name": "🇺🇸 US Top 50 (Mega-Cap Tech & S&P 500 Leaders)",
        "market": "US",
        "type": "universe",
        "is_builtin": True,
        "is_under_100": True,
        "summary": "Curated top 50 mega-cap US equities across NASDAQ & NYSE.",
        "explanation": "Features Magnificent Seven leaders (AAPL, MSFT, NVDA, AMZN, GOOGL, META, TSLA) and core S&P 500 blue-chips with deepest options liquidity and high institutional earnings coverage.",
        "selection_criteria": "Top 50 US mega-cap companies by liquidity and market cap.",
    },
    "us": {
        "name": "us",
        "display_name": "🇺🇸 All US Equities (Core S&P/NASDAQ)",
        "market": "US",
        "type": "universe",
        "is_builtin": True,
        "is_under_100": True,
        "summary": "Core US universe covering key US market equities.",
        "explanation": "Primary US market universe used for quarterly earnings cycle tracking and macroeconomic catalysts.",
        "selection_criteria": "Key US traded stocks on NYSE/NASDAQ.",
    },
    "nse_large_cap": {
        "name": "nse_large_cap",
        "display_name": "🇮🇳 NSE Large Cap (>₹1,000 Cr)",
        "market": "IN",
        "type": "universe",
        "is_builtin": True,
        "is_under_100": False,
        "summary": "All Indian companies on the NSE with market capitalization exceeding ₹1,000 Crore (₹10 Billion INR).",
        "explanation": "Sourced and refreshed via live market cap data to isolate institutional-grade large and mid-to-large cap companies.",
        "selection_criteria": "Market Cap > ₹1,000 Crore on NSE.",
    },
    "nse_all": {
        "name": "nse_all",
        "display_name": "🇮🇳 NSE Broad Universe (All Listed Equities)",
        "market": "IN",
        "type": "universe",
        "is_builtin": True,
        "is_under_100": False,
        "summary": "Comprehensive universe of all active equity symbols traded on the National Stock Exchange of India.",
        "explanation": "Dynamically fetched from the official NSE stock directory via nsetools, covering over 1,000 active tickers across all sectors.",
        "selection_criteria": "All active traded equity tickers on NSE.",
    },
}


def get_universe_details(settings: Settings | None = None) -> list[dict[str, Any]]:
    """Return all built-in universes with their full ticker lists, metadata, and explanations."""
    universe_names = ["nse_top", "us_top", "nse_large_cap", "nse_all"]
    # Also inspect any other universes in SQLite
    for u in list_universes(settings):
        uname = u["name"].lower()
        if uname not in universe_names and uname not in ("in", "us"):
            universe_names.append(uname)

    out: list[dict[str, Any]] = []
    for uname in universe_names:
        tickers = get_universe(uname, settings)
        if not tickers and uname in ("nse_top", "in"):
            tickers = list(_SEED_NSE_TOP)
        elif not tickers and uname in ("us_top", "us"):
            tickers = list(_SEED_US_TOP)

        meta = UNIVERSE_METADATA.get(uname, {
            "name": uname,
            "display_name": uname.replace("_", " ").title(),
            "market": "IN" if any(t.endswith(".NS") for t in tickers) else "US",
            "type": "universe",
            "is_builtin": True,
            "is_under_100": len(tickers) <= 100,
            "summary": f"Universe containing {len(tickers)} symbols.",
            "explanation": f"Universe '{uname}' stored in the database.",
            "selection_criteria": "Custom universe.",
        })

        count = len(tickers)
        item = {
            **meta,
            "tickers": tickers,
            "count": count,
            "is_under_100": count <= 100,
        }
        out.append(item)
    return out


# ---------------------------------------------------------------------------
# NSE ALL and NSE Large Cap (SQLite Backed)
# ---------------------------------------------------------------------------

def _fetch_nse_all_from_nsetools() -> list[str]:
    """Fetch all NSE stock codes from nsetools and append .NS suffix for yfinance."""
    from nsetools import Nse

    nse = Nse()
    codes = nse.get_stock_codes()
    if not codes:
        return []
    return [f"{code}.NS" for code in codes if code]


def load_nse_all(force_refresh: bool = False, settings: Settings | None = None) -> list[str]:
    """Load all NSE stocks from SQLite, refreshing from nsetools if stale or forced."""
    if not force_refresh and is_universe_fresh("NSE_ALL", NSE_ALL_MAX_AGE_DAYS, settings):
        tickers = get_universe("NSE_ALL", settings)
        if tickers:
            logger.debug("loaded cached NSE_ALL from SQLite (%s tickers)", len(tickers))
            return tickers

    logger.info("refreshing NSE_ALL from nsetools")
    try:
        tickers = _fetch_nse_all_from_nsetools()
        if not tickers:
            logger.warning("nsetools returned empty list, falling back to SQLite cache")
            return get_universe("NSE_ALL", settings)
        store_universe("NSE_ALL", tickers, settings)
        logger.info("NSE_ALL refreshed with %s tickers in SQLite", len(tickers))
        return tickers
    except Exception as e:
        logger.warning("nsetools fetch failed: %s, falling back to SQLite cache", e)
        return get_universe("NSE_ALL", settings)


def _fetch_market_cap_for_ticker(ticker: str) -> tuple[str, float | None]:
    """Fetch market cap for a single ticker from yfinance."""
    import yfinance as yf

    if is_market_cap_fresh(ticker):
        cached = load_market_cap(ticker)
        return (ticker, cached)

    try:
        try:
            from earnings_engine.rate_limits import record_request
            record_request("yfinance")
        except Exception:
            pass
        info = yf.Ticker(ticker).fast_info or {}
        market_cap = info.get("market_cap")
        if market_cap is None:
            info = yf.Ticker(ticker).info or {}
            market_cap = info.get("marketCap")
        store_market_cap(ticker, market_cap)
        return (ticker, market_cap)
    except Exception:
        return (ticker, None)


def _fetch_nse_large_cap_from_yfinance(settings: Settings | None = None) -> list[str]:
    """Fetch market cap for all NSE tickers and filter to those > 1000cr."""
    import time
    from concurrent.futures import ThreadPoolExecutor, as_completed

    all_tickers = load_nse_all(settings=settings)
    if not all_tickers:
        return []

    min_market_cap = NSE_LARGE_CAP_MIN_CR * 1e7
    large_cap_tickers: list[str] = []
    total = len(all_tickers)
    batch_size = 50
    processed = 0

    logger.info("fetching market cap for %s tickers in batches of %s", total, batch_size)

    for i in range(0, total, batch_size):
        batch = all_tickers[i:i + batch_size]
        batch_num = i // batch_size + 1
        total_batches = (total + batch_size - 1) // batch_size

        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_ticker = {
                executor.submit(_fetch_market_cap_for_ticker, ticker): ticker
                for ticker in batch
            }
            for future in as_completed(future_to_ticker):
                ticker, market_cap = future.result()
                processed += 1
                if market_cap and market_cap > min_market_cap:
                    large_cap_tickers.append(ticker)

        logger.info("market cap batch %s/%s complete: %s/%s tickers, %s large cap",
                    batch_num, total_batches, processed, total, len(large_cap_tickers))

        if i + batch_size < total:
            time.sleep(2)

    return large_cap_tickers


def load_nse_large_cap(force_refresh: bool = False, settings: Settings | None = None) -> list[str]:
    """Load NSE stocks with market cap > 1000cr from SQLite, refreshing from yfinance if stale."""
    if not force_refresh and is_universe_fresh("NSE_LARGE_CAP", NSE_ALL_MAX_AGE_DAYS, settings):
        tickers = get_universe("NSE_LARGE_CAP", settings)
        if tickers:
            logger.debug("loaded cached NSE_LARGE_CAP from SQLite (%s tickers)", len(tickers))
            return tickers

    logger.info("refreshing NSE_LARGE_CAP from yfinance")
    try:
        tickers = _fetch_nse_large_cap_from_yfinance(settings)
        if not tickers:
            logger.warning("yfinance returned empty list, falling back to SQLite cache")
            return get_universe("NSE_LARGE_CAP", settings)
        store_universe("NSE_LARGE_CAP", tickers, settings)
        logger.info("NSE_LARGE_CAP refreshed with %s tickers in SQLite", len(tickers))
        return tickers
    except Exception as e:
        logger.warning("yfinance fetch failed: %s, falling back to SQLite cache", e)
        return get_universe("NSE_LARGE_CAP", settings)


# ---------------------------------------------------------------------------
# Public Load APIs
# ---------------------------------------------------------------------------

def load_universe(market: str, settings: Settings | None = None) -> list[str]:
    """Load the configured ticker universe for one market from SQLite."""
    market_key = market.upper()
    if market_key in {"IN", "NSE_TOP"}:
        res = get_universe("IN", settings) or get_universe("nse_top", settings)
        return res or list(_SEED_NSE_TOP)
    if market_key in {"US", "US_TOP"}:
        res = get_universe("US", settings) or get_universe("us_top", settings)
        return res or list(_SEED_US_TOP)
    if market_key == "NSE_ALL":
        return load_nse_all(settings=settings)
    if market_key == "NSE_LARGE_CAP":
        return load_nse_large_cap(settings=settings)

    # Custom universe from SQLite
    res = get_universe(market, settings) or get_universe(market_key, settings)
    if res:
        return res

    raise ValueError(f"Unsupported market: {market}")


def load_universe_from_file(path: str | Path) -> list[str]:
    """Load tickers from a plain-text file (legacy helper)."""
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Universe file not found: {file_path}")
    return [line.strip() for line in file_path.read_text(encoding="utf-8").splitlines() if line.strip() and not line.strip().startswith("#")]


def ingest_market_caps(tickers: list[str], force: bool = False, settings: Settings | None = None) -> dict[str, int]:
    """Fetch and cache market cap for the requested tickers in SQLite."""
    import time
    from concurrent.futures import ThreadPoolExecutor, as_completed

    results: dict[str, int] = {}
    total = len(tickers)
    batch_size = 50
    processed = 0
    cached_hits = 0

    if not force:
        for ticker in tickers:
            if is_market_cap_fresh(ticker, settings):
                cached_hits += 1
        if cached_hits == total:
            logger.info("market cap cache hit for all %s tickers, skipping fetch", total)
            return {t: 1 for t in tickers}

    logger.info("ingesting market cap for %s tickers (%s cached, %s to fetch)",
                total, cached_hits, total - cached_hits)

    tickers_to_fetch: list[str] = []
    for ticker in tickers:
        if not force and is_market_cap_fresh(ticker, settings):
            results[ticker] = 1
            processed += 1
        else:
            tickers_to_fetch.append(ticker)

    fetch_total = len(tickers_to_fetch)
    for i in range(0, fetch_total, batch_size):
        batch = tickers_to_fetch[i:i + batch_size]
        batch_num = i // batch_size + 1
        total_batches = (fetch_total + batch_size - 1) // batch_size

        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_ticker = {
                executor.submit(_fetch_market_cap_for_ticker, ticker): ticker
                for ticker in batch
            }
            for future in as_completed(future_to_ticker):
                ticker, market_cap = future.result()
                processed += 1
                results[ticker] = 1 if market_cap is not None else 0

        logger.info("market cap ingest batch %s/%s complete: %s/%s tickers processed",
                    batch_num, total_batches, processed, total)

        if i + batch_size < total:
            time.sleep(2)

    ok = sum(1 for v in results.values() if v > 0)
    logger.info("market cap ingest complete: %s/%s tickers with data", ok, total)
    return results


def load_universe_from_file(
    name_or_path: str | Path,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """Load tickers from a watchlist, universe, or file path, returning list of dicts with 'ticker' key."""
    settings = settings or Settings()
    clean_name = str(name_or_path).replace(".txt", "").strip()

    from earnings_engine.data.watchlists import get_watchlist
    tickers = get_watchlist(clean_name, settings)
    if not tickers:
        tickers = get_universe(clean_name, settings)

    if not tickers and Path(name_or_path).exists():
        try:
            with open(name_or_path, "r", encoding="utf-8") as f:
                tickers = [line.strip().upper() for line in f if line.strip() and not line.startswith("#")]
        except Exception:
            pass

    if not tickers:
        tickers = list(_SEED_NSE_TOP)

    return [{"ticker": t} for t in tickers]


def load_all(settings: Settings | None = None) -> list[str]:
    """Return the combined universe across supported markets from SQLite."""
    return load_universe("IN", settings) + load_universe("US", settings)
