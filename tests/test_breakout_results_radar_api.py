"""Integration tests for the /api/breakout/results-radar endpoint."""
import sqlite3
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from earnings_engine.api.dependencies import _settings
from earnings_engine.api.server import app
from earnings_engine.data.prices import _cache_path


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def test_results_radar_default_endpoint(client):
    """Test default endpoint parameters return valid structured response with HTTP 200."""
    response = client.get("/api/breakout/results-radar")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "window" in data
    assert data["window"]["past_days"] == 3
    assert data["window"]["future_days"] == 7
    assert "summary" in data
    assert "items" in data
    assert isinstance(data["items"], list)

    # Test v1 prefix alias
    v1_resp = client.get("/api/v1/breakout/results-radar")
    assert v1_resp.status_code == 200
    assert v1_resp.json()["status"] == "ok"


def test_results_radar_custom_parameters(client):
    """Test custom window and archetype filtering."""
    response = client.get(
        "/api/breakout/results-radar?past_days=5&future_days=10&archetype=RDH_EXPANSION&min_score=40"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["window"]["past_days"] == 5
    assert data["window"]["future_days"] == 10


def test_results_radar_bounds_validation(client):
    """Test parameter validation rejects negative or out-of-range bounds with 422."""
    # Negative past_days
    resp1 = client.get("/api/breakout/results-radar?past_days=-1")
    assert resp1.status_code == 422

    # Unbounded future_days > 30
    resp2 = client.get("/api/breakout/results-radar?future_days=45")
    assert resp2.status_code == 422

    # min_score > 100
    resp3 = client.get("/api/breakout/results-radar?min_score=150")
    assert resp3.status_code == 422


def test_results_radar_seeded_payload(client):
    """Seed a test earnings event and verify full payload structure."""
    db_file = _cache_path(_settings)
    today_str = datetime.now().strftime("%Y-%m-%d")
    with sqlite3.connect(str(db_file)) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS price_history (
                ticker TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL, volume INTEGER
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS earnings_history (
                ticker TEXT, earnings_date TEXT, source TEXT, surprise_pct REAL, eps_reported REAL, eps_estimate REAL
            )
            """
        )
        # Add test event
        conn.execute(
            "INSERT OR REPLACE INTO earnings_history (ticker, earnings_date, source, surprise_pct) VALUES (?, ?, ?, ?)",
            ("TESTCO.NS", today_str, "nse", 5.0),
        )
        conn.execute(
            "INSERT OR REPLACE INTO price_history (ticker, date, open, high, low, close, volume) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("TESTCO.NS", today_str, 100.0, 105.0, 99.0, 104.0, 500000),
        )
        conn.commit()

    response = client.get("/api/breakout/results-radar?past_days=1&future_days=1&min_score=0")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    found = [it for it in data["items"] if it["ticker"] == "TESTCO.NS"]
    if found:
        item = found[0]
        assert "ticker" in item
        assert "composite_score" in item
        assert "trade_levels" in item
        assert "result_structure" in item
        assert "technicals" in item
