"""Unit tests for the rate limit tracking and API quota engine."""
import pytest
from starlette.testclient import TestClient

from earnings_engine.rate_limits import (
    DOWNSTREAM_CRITERIA,
    RateLimitTracker,
    get_ratelimits_summary,
    record_request,
    update_openrouter_headers,
)
from earnings_engine.api.server import app


def test_rate_limit_tracker_sliding_windows():
    tracker = RateLimitTracker()
    tracker._request_timestamps.clear()

    # Record requests for openrouter
    tracker.record_request("openrouter")
    tracker.record_request("openrouter")
    tracker.record_request("yfinance")

    summary = tracker.get_downstream_summary()
    assert "openrouter" in summary["downstreams"]
    assert "yfinance" in summary["downstreams"]
    assert "nse" in summary["downstreams"]
    assert "jugaad_data" in summary["downstreams"]
    assert "bse" in summary["downstreams"]
    assert "gemini" in summary["downstreams"]

    op = summary["downstreams"]["openrouter"]
    assert op["timeframes"]["1m"]["current"] == 2
    assert op["timeframes"]["1h"]["current"] == 2
    assert op["timeframes"]["24h"]["current"] == 2
    assert op["timeframes"]["24h"]["allowed"] == 200
    assert op["timeframes"]["24h"]["remaining"] == 198
    assert op["status"] == "normal"

    yf = summary["downstreams"]["yfinance"]
    assert yf["timeframes"]["1m"]["current"] == 1
    assert yf["timeframes"]["24h"]["allowed"] == 5000

    jg = summary["downstreams"]["jugaad_data"]
    assert jg["service_name"] == "Jugaad Data (NSE Bhavcopy & F&O)"
    assert jg["timeframes"]["24h"]["allowed"] == 1500


def test_openrouter_headers_updating():
    tracker = RateLimitTracker()
    tracker.update_openrouter_headers({
        "x-ratelimit-limit": "20",
        "x-ratelimit-remaining": "18",
        "x-ratelimit-reset": "10.5",
    })

    summary = tracker.get_downstream_summary()
    headers = summary["downstreams"]["openrouter"]["openrouter_live_headers"]
    assert headers["limit"] == 20
    assert headers["remaining"] == 18
    assert headers["reset"] == 10.5


def test_ratelimits_api_endpoint():
    client = TestClient(app)
    response = client.get("/api/v1/config/ratelimits")
    assert response.status_code == 200
    data = response.json()
    assert "downstreams" in data
    assert "openrouter_counter" in data
    assert "openrouter" in data["downstreams"]
    assert "yfinance" in data["downstreams"]
    assert "nse" in data["downstreams"]
    assert "jugaad_data" in data["downstreams"]
    assert "bse" in data["downstreams"]
    assert "gemini" in data["downstreams"]

    # Check top counter format
    counter = data["openrouter_counter"]
    assert "current_24h" in counter
    assert "allowed_24h" in counter
    assert "remaining_24h" in counter


def test_service_aliases_normalization():
    tracker = RateLimitTracker()
    tracker._request_timestamps.clear()

    # Record using various alias variations
    tracker.record_request("nse_direct")
    tracker.record_request("nselib_derivatives")
    tracker.record_request("nse_options")
    tracker.record_request("yf")
    tracker.record_request("yahoo_finance")
    tracker.record_request("google_gemini")
    tracker.record_request("jugaad-data")
    tracker.record_request("bse_india")

    summary = tracker.get_downstream_summary()

    # NSE should have received 3 requests
    assert summary["downstreams"]["nse"]["timeframes"]["1m"]["current"] == 3
    assert summary["downstreams"]["nse"]["timeframes"]["24h"]["current"] == 3

    # YFinance should have received 2 requests
    assert summary["downstreams"]["yfinance"]["timeframes"]["1m"]["current"] == 2

    # Gemini should have received 1 request
    assert summary["downstreams"]["gemini"]["timeframes"]["1m"]["current"] == 1

    # Jugaad Data should have received 1 request
    assert summary["downstreams"]["jugaad_data"]["timeframes"]["1m"]["current"] == 1

    # BSE should have received 1 request
    assert summary["downstreams"]["bse"]["timeframes"]["1m"]["current"] == 1

