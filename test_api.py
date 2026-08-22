"""Test script for the Earnings Engine API."""

import requests
from fastapi.testclient import TestClient

BASE_URL = "http://localhost:8000"

from earnings_engine.api.server import app

client = TestClient(app)


def test_dashboard_endpoint():
    """Test that the /dashboard endpoint serves the interactive HTML dashboard."""
    response = client.get("/dashboard")
    
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    
    content = response.text
    assert "<!DOCTYPE html>" in content
    assert "<title>Earnings Engine Dashboard</title>" in content
    
    # Verify tab-based layout
    assert "tab-results" in content
    assert "tab-swing" in content
    assert "tab-kronos" in content
    assert "tab-watchlist" in content
    
    # Verify widget containers
    assert "tickerSearch" in content
    assert "autocompleteDropdown" in content
    assert "resultsWidgets" in content
    assert "swingWidgets" in content
    assert "kronosWidgets" in content
    assert "watchlistItems" in content

    # Buy-the-Dip enhancements: date range, gap-down threshold, dip-recovery
    # section, and the opt-in earnings-quality (verdict) controls.
    assert "bdStartDate" in content
    assert "bdEndDate" in content
    assert "bdDrop" in content
    assert "bdDipRecovery" in content
    assert "/api/v1/dashboard/recent-results/verdict" in content

    # Patterns tab: market/date controls, industry table, patterns endpoint.
    assert "tab-patterns" in content
    assert "patStartDate" in content
    assert "patIndustries" in content
    assert "/api/v1/dashboard/patterns" in content

    # Verify refresh timestamp with (the global "Refresh Now" button was removed
    # per user request, but per-tab refresh remains)
    assert "lastRefreshed" in content


def test_dashboard_endpoint_calls_apis():
    """Test that the dashboard JS calls the API endpoints."""
    response = client.get("/dashboard")
    content = response.text
    
    # The dashboard should call these API endpoints
    assert "/api/v1/dashboard/overview" in content
    assert "/api/v1/dashboard/results" in content
    assert "/api/v1/dashboard/swing" in content
    assert "/api/v1/dashboard/kronos" in content
    assert "/api/v1/watchlist" in content
    assert "/api/v1/universe/" in content


def test_dashboard_patterns_endpoint():
    """The Patterns endpoint returns the aggregated industry/buy-the-dip shape."""
    response = client.get("/api/v1/dashboard/patterns?market=IN&start_date=2026-08-01&end_date=2026-08-10")
    assert response.status_code == 200
    data = response.json()
    assert "total" in data
    assert "positive" in data and "negative" in data
    assert "best_positive_industry" in data and "best_ratio_industry" in data
    assert "positive_dipped_total" in data and "comeback_50_total" in data and "kept_dipping_total" in data
    assert "industries" in data and "rows" in data


def test_dashboard_overview_endpoint():
    """Test that /api/v1/dashboard/overview returns dataset summary + watchlist."""
    response = client.get("/api/v1/dashboard/overview")
    
    assert response.status_code == 200
    data = response.json()
    
    # Should have dataset info, refresh status, and watchlist
    assert "dataset" in data
    assert "refresh_status" in data
    assert "watchlist" in data
    assert "universe_files" in data


def test_dashboard_results_endpoint():
    """Test that /api/v1/dashboard/results returns enriched results list."""
    response = client.get("/api/v1/dashboard/results?days=14")
    
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_dashboard_swing_endpoint():
    """Test that /api/v1/dashboard/swing returns swing setups list."""
    response = client.get("/api/v1/dashboard/swing?limit=10")
    
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_dashboard_refresh_status_endpoint():
    """Test that /api/v1/dashboard/refresh-status returns refresh timestamps."""
    response = client.get("/api/v1/dashboard/refresh-status")
    
    assert response.status_code == 200
    assert isinstance(response.json(), dict)


def test_watchlist_endpoints():
    """Test watchlist GET/ADD/REMOVE endpoints (server-side via NSE file)."""
    # GET
    response = client.get("/api/v1/watchlist")
    assert response.status_code == 200
    assert "tickers" in response.json()
    
    # ADD a test ticker
    test_ticker = "TEST.NS"
    add_response = client.post("/api/v1/watchlist/add", json={"ticker": test_ticker})
    assert add_response.status_code in (200, 400)  # 400 if already exists
    
    # Verify it's in the list
    get_response = client.get("/api/v1/watchlist")
    assert test_ticker in get_response.json()["tickers"]
    
    # REMOVE the test ticker
    remove_response = client.post("/api/v1/watchlist/remove", json={"ticker": test_ticker})
    assert remove_response.status_code in (200, 400)  # 400 if already removed
    
    # Verify it's gone
    get_response2 = client.get("/api/v1/watchlist")
    assert test_ticker not in get_response2.json()["tickers"]


def test_health():
    """Test health endpoint."""
    print("Testing health endpoint...")
    response = requests.get(f"{BASE_URL}/health")
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}\n")


def test_price_history():
    """Test price history endpoint."""
    print("Testing price history endpoint...")
    response = requests.get(
        f"{BASE_URL}/api/v1/price-history/AAPL",
        params={
            "start_date": "2024-01-01",
            "end_date": "2024-01-31",
        }
    )
    print(f"Status: {response.status_code}")
    data = response.json()
    print(f"Returned {len(data)} records")
    if data:
        print(f"First record: {data[0]}")
        print(f"Last record: {data[-1]}")
    print()


def test_earnings_history():
    """Test earnings history endpoint."""
    print("Testing earnings history endpoint...")
    response = requests.get(f"{BASE_URL}/api/v1/earnings-history/AAPL")
    print(f"Status: {response.status_code}")
    data = response.json()
    print(f"Returned {len(data)} records")
    if data:
        print(f"Most recent: {data[-1]}")
    print()


def test_market_cap():
    """Test market cap endpoint."""
    print("Testing market cap endpoint...")
    response = requests.get(f"{BASE_URL}/api/v1/market-cap/AAPL")
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}\n")


def test_market_context():
    """Test market context endpoint."""
    print("Testing market context endpoint...")
    response = requests.get(f"{BASE_URL}/api/v1/market-context/AAPL")
    print(f"Status: {response.status_code}")
    data = response.json()
    print(f"Ticker: {data.get('ticker')}")
    print(f"Current Price: {data.get('current_price')}")
    print(f"Market Cap: {data.get('market_cap')}")
    print(f"52W High: {data.get('week_high')}")
    print(f"52W Low: {data.get('week_low')}")
    print(f"Prev Quarter Score: {data.get('prev_quarter_earnings_score')}")
    print()


def test_upcoming_earnings():
    """Test upcoming earnings endpoint."""
    print("Testing upcoming earnings endpoint...")
    response = requests.get(
        f"{BASE_URL}/api/v1/upcoming-earnings",
        params={
            "tickers": "AAPL,MSFT,GOOGL",
            "days": 14,
        }
    )
    print(f"Status: {response.status_code}")
    data = response.json()
    print(f"Returned {len(data)} upcoming earnings events")
    print()


def test_universe():
    """Test universe endpoint."""
    print("Testing universe endpoint...")
    response = requests.get(f"{BASE_URL}/api/v1/universe/IN")
    print(f"Status: {response.status_code}")
    data = response.json()
    print(f"Market: {data.get('market')}")
    print(f"Count: {data.get('count')}")
    print(f"Sample tickers: {data.get('tickers', [])[:5]}")
    print()


def test_all_market_caps():
    """Test all market caps endpoint."""
    print("Testing all market caps endpoint...")
    response = requests.get(f"{BASE_URL}/api/v1/market-caps")
    print(f"Status: {response.status_code}")
    data = response.json()
    print(f"Returned {len(data)} market caps")
    if data:
        # Show first 3
        items = list(data.items())[:3]
        for ticker, cap in items:
            print(f"  {ticker}: {cap}")
    print()


if __name__ == "__main__":
    print("=" * 60)
    print("Earnings Engine API Test Suite")
    print("=" * 60)
    print()
    
    try:
        test_health()
        test_price_history()
        test_earnings_history()
        test_market_cap()
        test_market_context()
        test_upcoming_earnings()
        test_universe()
        test_all_market_caps()
        
        print("=" * 60)
        print("All tests completed successfully!")
        print("=" * 60)
    except Exception as e:
        print(f"Error: {e}")
        print("Make sure the API server is running (python run_api.py)")