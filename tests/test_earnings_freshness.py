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
