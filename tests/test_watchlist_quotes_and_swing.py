import pytest
from earnings_engine.config import Settings
from earnings_engine.api.dashboard_api import get_watchlist_quotes_api, get_swing_range_api
from fastapi.testclient import TestClient
from earnings_engine.api.server import app

client = TestClient(app)

def test_watchlist_quotes_api_cached():
    """Verify watchlist quotes API loads from cached data quickly with live=False."""
    settings = Settings()
    # Test with sample ticker
    res = get_watchlist_quotes_api(watchlist="test_wl", tickers=["TCS.NS"], live=False, settings=settings)
    assert res["success"] is True
    assert "items" in res
    assert len(res["items"]) == 1
    item = res["items"][0]
    assert item["ticker"] == "TCS.NS"
    assert "support" in item
    assert "resistance" in item


def test_swing_range_auto_detect_api():
    """Verify POST /api/v1/swing-range/auto-detect returns detected swing levels."""
    response = client.post("/api/v1/swing-range/auto-detect", json={"ticker": "TCS.NS", "watchlist": "ALL"})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["ticker"] == "TCS.NS"
    assert "auto_range" in data or "range" in data


def test_watchlist_quotes_endpoint():
    """Verify GET /api/v1/watchlist/quotes returns items with swing range and market metrics."""
    response = client.get("/api/v1/watchlist/quotes?tickers=TCS.NS&live=false")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert len(data["items"]) == 1
    assert data["items"][0]["ticker"] == "TCS.NS"
