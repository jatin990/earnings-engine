"""Automated database migration framework for Earnings Engine.

Applies versioned, idempotent schema updates on startup and tracks applied
versions in the `schema_migrations` table.
"""
from __future__ import annotations

from datetime import datetime
from typing import Callable, NamedTuple

from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection
from earnings_engine.logging_utils import get_logger

logger = get_logger("earnings_engine.data.migrations")


class Migration(NamedTuple):
    version: int
    name: str
    up: Callable[[Any], None]


# ---------------------------------------------------------------------------
# Individual Migrations
# ---------------------------------------------------------------------------

def _migration_001_core_schema(conn: Any) -> None:
    """Core tables: earnings_history, price_history, universes, caches."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS earnings_history (
            ticker TEXT NOT NULL,
            earnings_date TEXT NOT NULL,
            eps_estimate REAL,
            eps_reported REAL,
            surprise_pct REAL,
            source TEXT NOT NULL DEFAULT 'yfinance',
            PRIMARY KEY (ticker, earnings_date, source)
        )
    """)
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_earnings_history_ticker ON earnings_history (ticker)")
    except Exception:
        pass

    conn.execute("""
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
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS universes (
            universe_name TEXT NOT NULL,
            ticker TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (universe_name, ticker)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS universe_stocks (
            universe_name TEXT NOT NULL,
            ticker TEXT NOT NULL,
            name TEXT,
            added_at TEXT NOT NULL,
            PRIMARY KEY (universe_name, ticker)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS universe_freshness (
            universe_name TEXT PRIMARY KEY,
            fetched_at TEXT NOT NULL,
            stock_count INTEGER NOT NULL DEFAULT 0
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS earnings_freshness (
            market TEXT PRIMARY KEY,
            fetched_at TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS earnings_fetch_log (
            ticker TEXT PRIMARY KEY,
            fetched_at TEXT NOT NULL,
            status TEXT NOT NULL,
            row_count INTEGER NOT NULL DEFAULT 0
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS price_fetch_log (
            ticker TEXT PRIMARY KEY,
            fetched_at TEXT NOT NULL,
            status TEXT NOT NULL,
            row_count INTEGER NOT NULL DEFAULT 0
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS earnings_month_cache (
            cache_key TEXT PRIMARY KEY,
            cached_at TEXT NOT NULL,
            data_json TEXT NOT NULL
        )
    """)


def _migration_002_swing_ranges(conn: Any) -> None:
    """Swing trading ranges and cycle detection tables."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS swing_ranges (
            watchlist TEXT NOT NULL,
            ticker TEXT NOT NULL,
            lower_bound REAL NOT NULL,
            upper_bound REAL NOT NULL,
            source TEXT NOT NULL DEFAULT 'auto',
            cycles INTEGER,
            avg_cycle_days REAL,
            last_updated TEXT NOT NULL,
            PRIMARY KEY (watchlist, ticker)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_swing_ranges_lookup ON swing_ranges (watchlist, ticker)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_swing_ranges_ticker ON swing_ranges (ticker)")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS swing_cycle_history (
            watchlist TEXT NOT NULL,
            ticker TEXT NOT NULL,
            cycle_idx INTEGER NOT NULL,
            cycle_start TEXT NOT NULL,
            cycle_end TEXT NOT NULL,
            duration_days INTEGER NOT NULL,
            lower_bound REAL,
            upper_bound REAL,
            PRIMARY KEY (watchlist, ticker, cycle_idx)
        )
    """)


def _migration_003_multimodal_ai(conn: Any) -> None:
    """Multi-modal AI synthesis and news sentiment tables."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ai_news_predictions (
            ticker TEXT NOT NULL,
            run_at TEXT NOT NULL,
            current_price REAL,
            ai_signal TEXT,
            sentiment_score REAL,
            confidence REAL,
            volume_status TEXT,
            volume_ratio REAL,
            catalysts TEXT,
            risk_factors TEXT,
            thesis TEXT,
            news_count INTEGER,
            payload TEXT,
            PRIMARY KEY (ticker, run_at)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ai_news_ticker ON ai_news_predictions (ticker)")


def _migration_004_ticker_audit(conn: Any) -> None:
    """Audit logging table for on-demand ticker recalculations."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ticker_audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            refreshed_at TEXT NOT NULL,
            has_changes INTEGER NOT NULL DEFAULT 0,
            changes_summary TEXT NOT NULL,
            previous_values TEXT,
            updated_values TEXT,
            diff_json TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_ticker_time ON ticker_audit_log (ticker, refreshed_at DESC)")


def _migration_005_unified_tickers(conn: Any) -> None:
    """Unified master table consolidating ticker_names, ticker_industry, ticker_market_cap, ticker_metrics."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tickers (
            ticker TEXT PRIMARY KEY,
            name TEXT,
            industry TEXT,
            sector TEXT,
            market_cap REAL,
            market_cap_updated_at TEXT,
            metrics TEXT,
            metrics_as_of_date TEXT,
            last_updated TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tickers_industry ON tickers (industry)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tickers_market_cap ON tickers (market_cap)")

    # Migrate data from legacy ticker_names if table exists
    try:
        conn.execute("""
            INSERT INTO tickers (ticker, name, last_updated)
            SELECT ticker, name, DATETIME('now') FROM ticker_names
            WHERE TRUE
            ON CONFLICT(ticker) DO UPDATE SET
                name = COALESCE(excluded.name, tickers.name)
        """)
    except Exception:
        pass

    # Migrate data from legacy ticker_industry if table exists
    try:
        conn.execute("""
            INSERT INTO tickers (ticker, industry, sector, last_updated)
            SELECT ticker, industry, sector, DATETIME('now') FROM ticker_industry
            WHERE TRUE
            ON CONFLICT(ticker) DO UPDATE SET
                industry = COALESCE(excluded.industry, tickers.industry),
                sector = COALESCE(excluded.sector, tickers.sector)
        """)
    except Exception:
        pass

    # Migrate data from legacy ticker_market_cap if table exists
    try:
        conn.execute("""
            INSERT INTO tickers (ticker, market_cap, market_cap_updated_at, last_updated)
            SELECT ticker, market_cap, fetched_at, DATETIME('now') FROM ticker_market_cap
            WHERE TRUE
            ON CONFLICT(ticker) DO UPDATE SET
                market_cap = COALESCE(excluded.market_cap, tickers.market_cap),
                market_cap_updated_at = COALESCE(excluded.market_cap_updated_at, tickers.market_cap_updated_at)
        """)
    except Exception:
        pass

    # Migrate data from legacy ticker_metrics if table exists
    try:
        conn.execute("""
            INSERT INTO tickers (ticker, metrics, metrics_as_of_date, last_updated)
            SELECT ticker, metrics, as_of_date, DATETIME('now') FROM ticker_metrics
            WHERE TRUE
            ON CONFLICT(ticker) DO UPDATE SET
                metrics = COALESCE(excluded.metrics, tickers.metrics),
                metrics_as_of_date = COALESCE(excluded.metrics_as_of_date, tickers.metrics_as_of_date)
        """)
    except Exception:
        pass


def _migration_006_drop_legacy_ticker_tables(conn: Any) -> None:
    """Drop legacy ticker tables consolidated into unified tickers master table."""
    legacy_tables = [
        "ticker_names",
        "market_caps",
        "ticker_market_cap",
        "ticker_metrics",
        "ticker_industries",
        "ticker_industry",
    ]
    for tbl in legacy_tables:
        try:
            conn.execute(f"DROP TABLE IF EXISTS {tbl}")
        except Exception:
            pass


def _migration_007_consolidate_earnings_and_freshness(conn: Any) -> None:
    """Deduplicate earnings_history to (ticker, earnings_date) and consolidate freshness into tickers."""
    # 1. Add freshness columns to master tickers table
    for col in ("earnings_fetched_at", "prices_fetched_at"):
        try:
            conn.execute(f"ALTER TABLE tickers ADD COLUMN {col} TEXT")
        except Exception:
            pass

    # 2. Migrate existing freshness records into tickers
    try:
        conn.execute("""
            INSERT INTO tickers (ticker, earnings_fetched_at, last_updated)
            SELECT ticker, fetched_at, DATETIME('now') FROM earnings_freshness
            WHERE TRUE
            ON CONFLICT(ticker) DO UPDATE SET
                earnings_fetched_at = COALESCE(excluded.earnings_fetched_at, tickers.earnings_fetched_at)
        """)
    except Exception:
        pass

    try:
        conn.execute("""
            INSERT INTO tickers (ticker, prices_fetched_at, last_updated)
            SELECT ticker, fetched_at, DATETIME('now') FROM price_fetch_log
            WHERE TRUE
            ON CONFLICT(ticker) DO UPDATE SET
                prices_fetched_at = COALESCE(excluded.prices_fetched_at, tickers.prices_fetched_at)
        """)
    except Exception:
        pass

    # 3. Deduplicate and rebuild earnings_history with PK (ticker, earnings_date)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS earnings_history_new (
            ticker TEXT NOT NULL,
            earnings_date TEXT NOT NULL,
            eps_estimate REAL,
            eps_reported REAL,
            surprise_pct REAL,
            source TEXT NOT NULL DEFAULT 'yfinance',
            PRIMARY KEY (ticker, earnings_date)
        )
    """)

    try:
        conn.execute("""
            INSERT INTO earnings_history_new (ticker, earnings_date, eps_estimate, eps_reported, surprise_pct, source)
            SELECT 
                ticker,
                earnings_date,
                MAX(eps_estimate) as eps_estimate,
                MAX(eps_reported) as eps_reported,
                MAX(surprise_pct) as surprise_pct,
                MAX(source) as source
            FROM earnings_history
            GROUP BY ticker, earnings_date
            ON CONFLICT(ticker, earnings_date) DO UPDATE SET
                eps_estimate = COALESCE(excluded.eps_estimate, earnings_history_new.eps_estimate),
                eps_reported = COALESCE(excluded.eps_reported, earnings_history_new.eps_reported),
                surprise_pct = COALESCE(excluded.surprise_pct, earnings_history_new.surprise_pct)
        """)
        conn.execute("DROP TABLE earnings_history")
        conn.execute("ALTER TABLE earnings_history_new RENAME TO earnings_history")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_earnings_history_date ON earnings_history (earnings_date)")
    except Exception:
        pass

    # 4. Drop obsolete tables
    for tbl in ("earnings_freshness", "price_fetch_log", "universe_stocks"):
        try:
            conn.execute(f"DROP TABLE IF EXISTS {tbl}")
        except Exception:
            pass


# Migration Registry (ordered by version)
MIGRATIONS: list[Migration] = [
    Migration(1, "001_core_schema", _migration_001_core_schema),
    Migration(2, "002_swing_ranges", _migration_002_swing_ranges),
    Migration(3, "003_multimodal_ai", _migration_003_multimodal_ai),
    Migration(4, "004_ticker_audit", _migration_004_ticker_audit),
    Migration(5, "005_unified_tickers", _migration_005_unified_tickers),
    Migration(6, "006_drop_legacy_ticker_tables", _migration_006_drop_legacy_ticker_tables),
    Migration(7, "007_consolidate_earnings_and_freshness", _migration_007_consolidate_earnings_and_freshness),
]


def apply_migrations(settings: Settings | None = None) -> list[str]:
    """Execute all pending database migrations in order."""
    settings = settings or Settings()
    conn = get_db_connection(settings)

    # 1. Ensure migrations ledger exists
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TEXT NOT NULL
            )
        """)
        conn.commit()

    # 2. Get set of already applied migration versions
    with conn:
        applied_rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
        applied_versions = {r[0] for r in applied_rows}

        # Auto-baseline: if schema_migrations was just created on an existing database
        # that already contains core tables (price_history), baseline migrations 1-4
        if not applied_versions:
            try:
                check_row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='price_history'").fetchone()
                if check_row:
                    now_str = datetime.now().isoformat(timespec="seconds")
                    for v, n in [(1, "001_core_schema"), (2, "002_swing_ranges"), (3, "003_multimodal_ai"), (4, "004_ticker_audit")]:
                        conn.execute("INSERT OR IGNORE INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)", (v, n, now_str))
                    conn.commit()
                    applied_versions.update({1, 2, 3, 4})
            except Exception:
                pass

    applied_names: list[str] = []

    for migration in MIGRATIONS:
        if migration.version in applied_versions:
            continue

        logger.info("Applying database migration %d: %s...", migration.version, migration.name)
        now_str = datetime.now().isoformat(timespec="seconds")
        try:
            with conn:
                migration.up(conn)
                conn.execute(
                    "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
                    (migration.version, migration.name, now_str),
                )
                conn.commit()
            applied_names.append(migration.name)
            logger.info("✅ Migration %s applied successfully.", migration.name)
        except Exception as e:
            logger.warning("Migration %s encountered error: %s (recording as baseline)", migration.name, e)
            try:
                with conn:
                    conn.execute(
                        "INSERT OR IGNORE INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
                        (migration.version, migration.name, now_str),
                    )
                    conn.commit()
            except Exception:
                pass

    return applied_names
