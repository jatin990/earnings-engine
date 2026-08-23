"""Unit tests for the automated database migration system."""
import sqlite3
import pytest

from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection
from earnings_engine.data.migrations import apply_migrations, MIGRATIONS


@pytest.fixture
def test_settings(tmp_path):
    s = Settings()
    s.data_dirs["prices"] = tmp_path
    s.data_dirs["earnings"] = tmp_path
    s.ensure_dirs()
    return s


def test_migrations_apply_all_in_order(test_settings):
    """Test that migrations run sequentially and create schema_migrations records."""
    applied = apply_migrations(test_settings)
    assert len(applied) == len(MIGRATIONS)
    assert "001_core_schema" in applied
    assert "005_unified_tickers" in applied

    conn = get_db_connection(test_settings)
    with conn:
        rows = conn.execute("SELECT version, name FROM schema_migrations ORDER BY version").fetchall()
        assert len(rows) == len(MIGRATIONS)
        assert rows[0][1] == "001_core_schema"
        assert rows[-1][1] == "005_unified_tickers"

        # Verify tables exist
        table_rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        tables = {r[0] for r in table_rows}
        assert "tickers" in tables
        assert "earnings_history" in tables
        assert "price_history" in tables
        assert "swing_ranges" in tables
        assert "ticker_audit_log" in tables


def test_migrations_are_idempotent(test_settings):
    """Running apply_migrations a second time should apply 0 new migrations."""
    apply_migrations(test_settings)
    second_run = apply_migrations(test_settings)
    assert second_run == []


def test_migration_005_migrates_legacy_data(test_settings):
    """Test that existing rows from legacy tables are copied into tickers master table."""
    conn = get_db_connection(test_settings)
    # Manually populate legacy tables
    with conn:
        conn.execute("CREATE TABLE IF NOT EXISTS ticker_names (ticker TEXT PRIMARY KEY, name TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS ticker_industry (ticker TEXT PRIMARY KEY, industry TEXT, sector TEXT, fetched_at TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS ticker_market_cap (ticker TEXT PRIMARY KEY, market_cap REAL, fetched_at TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS ticker_metrics (ticker TEXT, as_of_date TEXT, metrics TEXT, PRIMARY KEY(ticker, as_of_date))")

        conn.execute("INSERT INTO ticker_names VALUES ('INFY.NS', 'Infosys Limited')")
        conn.execute("INSERT INTO ticker_industry VALUES ('INFY.NS', 'IT Services', 'Technology', '2026-08-20')")
        conn.execute("INSERT INTO ticker_market_cap VALUES ('INFY.NS', 750000.0, '2026-08-20')")
        conn.execute("INSERT INTO ticker_metrics VALUES ('INFY.NS', '2026-08-20', '{\"pe\": 25.5}')")
        conn.commit()

    # Now apply migrations
    apply_migrations(test_settings)

    with conn:
        row = conn.execute("SELECT name, industry, sector, market_cap, metrics FROM tickers WHERE ticker = 'INFY.NS'").fetchone()
        assert row is not None
        assert row[0] == "Infosys Limited"
        assert row[1] == "IT Services"
        assert row[2] == "Technology"
        assert row[3] == 750000.0
        assert "25.5" in str(row[4])

    # Test names module integration with tickers table
    from earnings_engine.data.names import get_name, store_name, search
    assert get_name("INFY.NS", test_settings) == "Infosys Limited"
    store_name("TCS.NS", "Tata Consultancy Services", settings=test_settings)
    assert get_name("TCS.NS", test_settings) == "Tata Consultancy Services"
    search_res = search("Tata", settings=test_settings)
    assert any(r["symbol"] == "TCS.NS" for r in search_res)
