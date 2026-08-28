"""Tests for downstream API call tracking and playground endpoints."""
import time
from fastapi.testclient import TestClient

from earnings_engine.api.server import app
from earnings_engine.rate_limits import (
    record_request,
    record_generation,
    get_api_usage_summary,
    tracker,
)

client = TestClient(app)


def test_api_usage_tracking_and_summary():
    # Record test calls
    record_request("yfinance", status_code=200)
    record_request("nse", status_code=200)
    record_request("jugaad_data", status_code=200)
    record_request("kronos", status_code=200)
    record_generation("deepseek/deepseek-r1", latency_ms=1200.0, tokens=450, success=True, ticker="TCS.NS")

    # Give async persist a brief moment
    time.sleep(0.1)

    summary = get_api_usage_summary()
    assert summary["success"] is True
    assert "totals" in summary
    assert summary["totals"]["total_calls_all_time"] > 0
    assert summary["totals"]["total_calls_today"] > 0
    assert "downstreams" in summary
    assert "ai_models" in summary

    # Verify downstream services list
    ds_ids = [d["id"] for d in summary["downstreams"]]
    assert "yfinance" in ds_ids
    assert "nse" in ds_ids
    assert "jugaad_data" in ds_ids
    assert "kronos" in ds_ids

    # Verify AI models list
    ai_ids = [m["id"] for m in summary["ai_models"]]
    assert "deepseek/deepseek-r1" in ai_ids


def test_playground_api_usage_endpoint():
    response = client.get("/api/v1/playground/api-usage")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "totals" in data
    assert "downstreams" in data
    assert "ai_models" in data
    assert "as_of" in data
    assert "IST" in data["as_of"]
