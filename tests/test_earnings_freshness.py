"""Tests for Watchlist Earnings Freshness Tracking and On-Demand Batch Refresh."""
import pandas as pd
import pytest
from starlette.testclient import TestClient

from earnings_engine.api.server import app
from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection
from earnings_engine.data.earnings import (
    get_watchlist_earnings_freshness,
    refresh_watchlist_earnings,
)
from earnings_engine.data.watchlists import add_to_watchlist


from earnings_engine.data.migrations import apply_migrations


@pytest.fixture
def clean_test_watchlist(temp_settings):
    apply_migrations(temp_settings)
    wl_name = "test_freshness_wl"
    # Populate a couple test tickers
    add_to_watchlist(wl_name, "TEST_TICKER_A.NS", temp_settings)
    add_to_watchlist(wl_name, "TEST_TICKER_B.NS", temp_settings)

    # Set mock fetch timestamp
    conn = get_db_connection(temp_settings)
    with conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO tickers (ticker, earnings_fetched_at, last_updated)
            VALUES ('TEST_TICKER_A.NS', '2026-08-20 10:00:00', '2026-08-20 10:00:00'),
                   ('TEST_TICKER_B.NS', '2026-08-22 15:30:00', '2026-08-22 15:30:00')
            """
        )
    return wl_name


def test_watchlist_earnings_freshness_calculation(temp_settings, clean_test_watchlist):
    freshness = get_watchlist_earnings_freshness(clean_test_watchlist, settings=temp_settings)
    assert freshness["watchlist"] == clean_test_watchlist
    assert freshness["total_tickers"] == 2
    assert freshness["cached_tickers"] == 2
    assert freshness["last_updated"] == "2026-08-22 15:30:00"
    assert freshness["oldest_updated"] == "2026-08-20 10:00:00"
    assert freshness["status"] in ("WARM", "STALE", "FRESH")


def test_empty_watchlist_freshness(temp_settings):
    freshness = get_watchlist_earnings_freshness("empty_wl_xyz", settings=temp_settings)
    assert freshness["total_tickers"] == 0
    assert freshness["cached_tickers"] == 0
    assert freshness["status"] == "EMPTY"


def test_refresh_watchlist_api_endpoints(temp_settings, clean_test_watchlist):
    client = TestClient(app)

    # 1. Query freshness endpoint
    resp = client.get(f"/api/v1/earnings/freshness?watchlist={clean_test_watchlist}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["watchlist"] == clean_test_watchlist
    assert data["total_tickers"] >= 0

    # 2. Query freshness with explicit tickers
    resp_tickers = client.get("/api/v1/earnings/freshness?tickers=TEST_TICKER_A.NS,TEST_TICKER_B.NS")
    assert resp_tickers.status_code == 200
    data_tickers = resp_tickers.json()
    assert data_tickers["total_tickers"] == 2

    # 3. Query global universe freshness (watchlist=None or ALL)
    resp_global = client.get("/api/v1/earnings/freshness")
    assert resp_global.status_code == 200
    data_global = resp_global.json()
    assert data_global["total_tickers"] >= 2
    assert data_global["cached_tickers"] >= 2
    assert data_global["relative_time"] != "No tickers in universe"


def test_universe_freshness_resolution(temp_settings):
    # Test standard universes (NSE_TOP, IN, NSE_ALL)
    for u in ("NSE_TOP", "IN", "NSE_ALL"):
        fresh = get_watchlist_earnings_freshness(u, settings=temp_settings)
        assert fresh["total_tickers"] > 0
        assert fresh["relative_time"] != "No tickers in watchlist"


def test_earnings_refresh_rule_7_days_and_missing(temp_settings):
    """Verify earnings refresh ONLY happens if next date is missing or within next 7 days."""
    from earnings_engine.data.earnings import _is_fresh
    apply_migrations(temp_settings)
    conn = get_db_connection(temp_settings)

    today = pd.Timestamp.today().normalize()
    date_in_3d = (today + pd.Timedelta(days=3)).strftime("%Y-%m-%d")
    date_in_15d = (today + pd.Timedelta(days=15)).strftime("%Y-%m-%d")
    past_date = (today - pd.Timedelta(days=20)).strftime("%Y-%m-%d")

    # Case 1: Ticker with NO upcoming earnings date -> NOT fresh (must refresh)
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO tickers (ticker, earnings_fetched_at) VALUES ('NO_UPCOMING.NS', '2026-08-01 10:00:00')"
        )
        conn.execute(
            "INSERT OR REPLACE INTO earnings_history (ticker, earnings_date, eps_reported) VALUES ('NO_UPCOMING.NS', ?, 10.0)",
            (past_date,),
        )
    assert _is_fresh("NO_UPCOMING.NS", temp_settings) is False

    # Case 2: Ticker with next earnings date 3 days away (<= 7 days) and fetched 3 days ago -> NOT fresh (must refresh)
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO tickers (ticker, earnings_fetched_at) VALUES ('UPCOMING_3D.NS', '2026-08-20 10:00:00')"
        )
        conn.execute(
            "INSERT OR REPLACE INTO earnings_history (ticker, earnings_date) VALUES ('UPCOMING_3D.NS', ?)",
            (date_in_3d,),
        )
    assert _is_fresh("UPCOMING_3D.NS", temp_settings) is False

    # Case 3: Ticker with next earnings date 15 days away (> 7 days) -> IS fresh (NO refresh needed!)
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO tickers (ticker, earnings_fetched_at) VALUES ('UPCOMING_15D.NS', '2026-08-01 10:00:00')"
        )
        conn.execute(
            "INSERT OR REPLACE INTO earnings_history (ticker, earnings_date) VALUES ('UPCOMING_15D.NS', ?)",
            (date_in_15d,),
        )
    assert _is_fresh("UPCOMING_15D.NS", temp_settings) is True




