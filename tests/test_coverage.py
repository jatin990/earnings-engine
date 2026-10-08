"""Tests for the Data Coverage tab and incremental earnings ingestion."""

import datetime
import sqlite3

import pytest

from earnings_engine.config import Settings
from earnings_engine.data.coverage import get_data_coverage
from earnings_engine.data import earnings as earnings_mod


@pytest.fixture
def cov_settings(tmp_path):
    """Settings with temp data dirs so tests never touch the real cache."""
    s = Settings()
    s.data_dirs = {"prices": tmp_path / "prices", "earnings": tmp_path / "earnings"}
    s.ensure_dirs()
    return s


def _db_path(settings: Settings):
    from earnings_engine.data.prices import _cache_path
    return _cache_path(settings)


def _seed_db(settings: Settings) -> None:
    """Create the shared SQLite DB with price_history + earnings_history + freshness rows."""
    conn = sqlite3.connect(str(_db_path(settings)))
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS price_history (
            ticker TEXT NOT NULL,
            date TEXT NOT NULL,
            open REAL, high REAL, low REAL, close REAL, volume INTEGER
        )
        """
    )
    conn.execute(
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
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS tickers (
            ticker TEXT PRIMARY KEY,
            company_name TEXT,
            industry TEXT,
            sector TEXT,
            market_cap REAL,
            current_price REAL,
            earnings_fetched_at TEXT,
            prices_fetched_at TEXT,
            last_updated TEXT
        )
        """
    )
    # 3 tickers with prices; 2 of them also have earnings; 1 is fresh.
    for ticker, start in [("A.NS", "2026-01-05"), ("B.NS", "2026-01-05"), ("C.NS", "2026-01-05")]:
        conn.execute(
            "INSERT INTO price_history (ticker, date, close) VALUES (?, ?, ?)",
            (ticker, start, 100.0),
        )
        conn.execute(
            "INSERT INTO price_history (ticker, date, close) VALUES (?, ?, ?)",
            (ticker, "2026-01-06", 101.0),
        )
    conn.execute(
        "INSERT INTO earnings_history (ticker, earnings_date, source) VALUES (?, ?, 'yfinance')",
        ("A.NS", "2026-02-10"),
    )
    conn.execute(
        "INSERT INTO earnings_history (ticker, earnings_date, source) VALUES (?, ?, 'nse')",
        ("A.NS", "2026-02-10"),
    )
    conn.execute(
        "INSERT INTO earnings_history (ticker, earnings_date, source) VALUES (?, ?, 'yfinance')",
        ("B.NS", "2026-02-12"),
    )
    conn.execute(
        "INSERT INTO tickers (ticker, earnings_fetched_at, prices_fetched_at) VALUES (?, ?, ?)",
        ("A.NS", "2026-07-30 10:00:00", "2026-07-30 10:00:00"),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# get_data_coverage (per-ticker stats)
# ---------------------------------------------------------------------------

def test_get_data_coverage_returns_per_ticker_stats(cov_settings):
    """Verifies price/earnings date ranges and row counts for a mock SQLite DB."""
    _seed_db(cov_settings)
    result = get_data_coverage(["A.NS", "B.NS"], cov_settings)

    assert result["total"] == 2
    assert result["with_prices"] == 2
    assert result["with_earnings"] == 2

    rows = {r["ticker"]: r for r in result["rows"]}

    a = rows["A.NS"]
    assert a["has_prices"] is True
    assert a["price_start"] == "2026-01-05"
    assert a["price_end"] == "2026-01-06"
    assert a["price_rows"] == 2
    assert a["has_earnings"] is True
    assert a["earnings_start"] == "2026-02-10"
    assert a["earnings_end"] == "2026-02-10"
    assert a["earnings_rows"] == 2  # yfinance + nse rows for the same date
    assert a["listing_date"] == "2026-01-05"  # price_history MIN(date) proxy
    assert a["earnings_fresh"] is True

    b = rows["B.NS"]
    assert b["has_earnings"] is True
    assert b["earnings_rows"] == 1
    assert b["earnings_start"] == "2026-02-12"
    assert b["earnings_fresh"] is False


def test_get_data_coverage_filters_by_ticker_list(cov_settings):
    """Verifies only requested tickers are returned, in requested order."""
    _seed_db(cov_settings)
    result = get_data_coverage(["C.NS"], cov_settings)

    assert result["total"] == 1
    assert result["with_prices"] == 1
    assert result["with_earnings"] == 0
    assert [r["ticker"] for r in result["rows"]] == ["C.NS"]
    assert result["rows"][0]["has_prices"] is True
    assert result["rows"][0]["has_earnings"] is False
    assert result["rows"][0]["earnings_rows"] == 0


def test_get_data_coverage_unknown_ticker_has_empty_stats(cov_settings):
    """A ticker with no rows at all still appears with zeroed stats."""
    _seed_db(cov_settings)
    result = get_data_coverage(["Z.NS"], cov_settings)
    assert result["total"] == 1
    assert result["with_prices"] == 0
    assert result["with_earnings"] == 0
    r = result["rows"][0]
    assert r["has_prices"] is False
    assert r["has_earnings"] is False
    assert r["price_rows"] == 0
    assert r["listing_date"] is None
    assert r["earnings_fresh"] is False


def test_get_data_coverage_empty_db(cov_settings):
    """Empty/missing DB returns zeroed aggregate counts."""
    result = get_data_coverage(["A.NS", "B.NS"], cov_settings)
    assert result["total"] == 2
    assert result["with_prices"] == 0
    assert result["with_earnings"] == 0
    assert result["rows"] == []


# ---------------------------------------------------------------------------
# ingest_earnings_incremental
# ---------------------------------------------------------------------------

def test_ingest_earnings_incremental_skips_cached(cov_settings, monkeypatch):
    """Tickers with existing earnings are not re-fetched."""
    _seed_db(cov_settings)
    # A.NS already has earnings -> skip; C.NS has prices but no earnings -> fetched.
    monkeypatch.setattr(
        earnings_mod,
        "_fetch_earnings_for_ticker",
        lambda args: (args[0], 4),
    )
    result = earnings_mod.ingest_earnings_incremental(["A.NS", "C.NS"], cov_settings)
    assert result["total"] == 2
    assert result["already_cached"] == 1
    assert result["fetched"] == 1
    assert result["errors"] == 0


def test_ingest_earnings_incremental_skips_no_listing(cov_settings, monkeypatch):
    """Tickers with no price history are skipped (skipped_no_listing)."""
    _seed_db(cov_settings)
    # D.NS has no price rows at all.
    monkeypatch.setattr(
        earnings_mod,
        "_fetch_earnings_for_ticker",
        lambda args: (args[0], 4),
    )
    result = earnings_mod.ingest_earnings_incremental(["D.NS"], cov_settings)
    assert result["total"] == 1
    assert result["skipped_no_listing"] == 1
    assert result["fetched"] == 0


def test_ingest_earnings_incremental_skips_too_new(cov_settings, monkeypatch):
    """Tickers listed < 90 days ago are skipped (too new for quarterly earnings)."""
    _seed_db(cov_settings)
    # Add a ticker whose first price date is recent (< 90 days ago).
    recent_date = (datetime.date.today() - datetime.timedelta(days=30)).isoformat()
    conn = sqlite3.connect(str(_db_path(cov_settings)))
    conn.execute(
        "INSERT INTO price_history (ticker, date, close) VALUES (?, ?, ?)",
        ("NEW.NS", recent_date, 50.0),
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(
        earnings_mod,
        "_fetch_earnings_for_ticker",
        lambda args: (args[0], 4),
    )
    result = earnings_mod.ingest_earnings_incremental(["NEW.NS"], cov_settings)
    assert result["total"] == 1
    assert result["skipped_no_listing"] == 1
    assert result["fetched"] == 0


def test_ingest_earnings_incremental_fetches_missing(cov_settings, monkeypatch):
    """Tickers missing earnings but with a valid listing are fetched."""
    _seed_db(cov_settings)
    # C.NS has prices (listed Jan 2026, > 90 days) but no earnings.
    monkeypatch.setattr(
        earnings_mod,
        "_fetch_earnings_for_ticker",
        lambda args: (args[0], 4),
    )
    result = earnings_mod.ingest_earnings_incremental(["C.NS"], cov_settings)
    assert result["total"] == 1
    assert result["fetched"] == 1
    assert result["already_cached"] == 0
    assert result["errors"] == 0


def test_ingest_earnings_incremental_empty_input(cov_settings):
    """Empty ticker list returns a zeroed summary without errors."""
    result = earnings_mod.ingest_earnings_incremental([], cov_settings)
    assert result == {
        "total": 0,
        "already_cached": 0,
        "fetched": 0,
        "skipped_no_listing": 0,
        "errors": 0,
    }


# ---------------------------------------------------------------------------
# API endpoint
# ---------------------------------------------------------------------------

def test_data_coverage_api_endpoint(cov_settings, monkeypatch):
    """Verifies the API endpoint returns the correct per-ticker shape."""
    from fastapi.testclient import TestClient
    from earnings_engine.api.server import app
    from earnings_engine.api import dashboard_api

    _seed_db(cov_settings)

    # Point the dashboard_api settings resolver at the temp settings so the
    # endpoint queries the seeded temp DB instead of the real one.
    monkeypatch.setattr(dashboard_api, "_settings", lambda: cov_settings)

    client = TestClient(app)
    resp = client.get("/api/v1/dashboard/data-coverage?market=WATCHLIST")
    assert resp.status_code == 200
    data = resp.json()
    assert "rows" in data
    assert isinstance(data["rows"], list)
    # Every row has the full per-ticker shape.
    for row in data["rows"]:
        for key in [
            "ticker", "price_start", "price_end", "price_rows",
            "earnings_start", "earnings_end", "earnings_rows",
            "has_prices", "has_earnings", "listing_date", "earnings_fresh",
        ]:
            assert key in row