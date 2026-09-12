"""Integration and unit tests for IPO Detail API endpoints and stock API integration."""

from __future__ import annotations

import pytest
from datetime import datetime, timedelta
from fastapi.testclient import TestClient

from earnings_engine.api.server import app
from earnings_engine.api import stock_api
from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection
from earnings_engine.data.migrations import apply_migrations


@pytest.fixture
def client():
    return TestClient(app)


def test_get_ipo_stock_detail_direct():
    """Verify stock_api.get_ipo_stock_detail delegates properly and returns expected structure."""
    settings = Settings()
    res = stock_api.get_ipo_stock_detail("TATATECH.NS", settings=settings)
    assert isinstance(res, dict)
    assert res.get("success") is True
    assert res.get("ticker") == "TATATECH.NS"
    assert "technical" in res
    assert "earnings_lifecycle" in res
    assert "institutional" in res


def test_get_ipo_stock_detail_direct_empty():
    """Verify stock_api.get_ipo_stock_detail handles empty/invalid ticker cleanly."""
    settings = Settings()
    res = stock_api.get_ipo_stock_detail("", settings=settings)
    assert isinstance(res, dict)
    assert res.get("success") is False
    assert "error" in res


def test_api_get_ipo_detail_success(client):
    """Verify GET /api/v1/market/ipo-detail/{ticker} returns 200 and required contract keys."""
    response = client.get("/api/v1/market/ipo-detail/TATATECH.NS")
    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    assert data["ticker"] == "TATATECH.NS"
    assert "technical" in data
    assert "earnings_lifecycle" in data
    assert "institutional" in data

    # Verify structural integrity of sub-dictionaries
    assert "listing_day" in data["technical"]
    assert "cmp" in data["technical"]
    assert "past_earnings_count" in data["earnings_lifecycle"]
    assert "result_sequence" in data["earnings_lifecycle"]
    assert "mutual_funds" in data["institutional"]


def test_api_get_ipo_detail_lowercase_normalized(client):
    """Verify lowercase ticker without .NS suffix is normalized to uppercase .NS."""
    response = client.get("/api/v1/market/ipo-detail/tatatech")
    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    assert data["ticker"] == "TATATECH.NS"
    assert data["raw_symbol"] == "TATATECH"


def test_api_get_ipo_detail_empty_or_whitespace(client):
    """Verify endpoint handles whitespace/empty ticker edge case gracefully."""
    response = client.get("/api/v1/market/ipo-detail/%20")
    assert response.status_code == 200
    data = response.json()

    assert data["success"] is False
    assert "Ticker cannot be empty" in data.get("error", "")


def test_api_get_ipo_detail_mocked_integration(client, monkeypatch):
    """Verify full end-to-end payload assembly with price history, earnings, and institutional backing."""
    settings = Settings()
    apply_migrations(settings)
    conn = get_db_connection(settings)

    test_ticker = "TEST_API_IPO.NS"
    now = datetime.now()

    # Seed price history
    for i in range(15):
        d_str = (now - timedelta(days=20 - i)).strftime("%Y-%m-%d")
        close_p = 150.0 + (i * 3.0)
        conn.execute(
            "INSERT OR REPLACE INTO price_history (ticker, date, open, high, low, close, volume) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (test_ticker, d_str, close_p - 1.0, close_p + 2.0, close_p - 2.0, close_p, 10000 + i * 500),
        )

    # Seed earnings history
    conn.execute(
        "INSERT OR REPLACE INTO earnings_history (ticker, earnings_date, eps_reported, eps_estimate, surprise_pct, source) VALUES (?, ?, ?, ?, ?, ?)",
        (test_ticker, "2026-07-20", 3.2, 3.0, 6.67, "nse"),
    )

    # Seed institutional holdings
    conn.execute(
        """
        INSERT OR REPLACE INTO institutional_holdings
        (id, ticker, fund_name, fund_type, quarter, shares_held, stake_pct, holding_value_cr, action, reported_date, created_at)
        VALUES (888801, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (test_ticker, "Kotak Emerging Equity Fund", "Mutual Fund (DII)", "Q1 FY27", 120000, 1.25, 15.2, "BUY", "2026-08-15", now.isoformat()),
    )
    if hasattr(conn, "commit"):
        conn.commit()

    try:
        response = client.get(f"/api/v1/market/ipo-detail/{test_ticker}")
        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        assert data["ticker"] == test_ticker
        assert data["technical"]["cmp"] is not None
        assert data["earnings_lifecycle"]["past_earnings_count"] >= 1
        assert data["institutional"]["mutual_funds_count"] >= 1
        assert any(mf["fund_name"] == "Kotak Emerging Equity Fund" for mf in data["institutional"]["mutual_funds"])
    finally:
        # Clean up seeded test records
        conn.execute("DELETE FROM price_history WHERE ticker = ?", (test_ticker,))
        conn.execute("DELETE FROM earnings_history WHERE ticker = ?", (test_ticker,))
        conn.execute("DELETE FROM institutional_holdings WHERE ticker = ?", (test_ticker,))
        if hasattr(conn, "commit"):
            conn.commit()
