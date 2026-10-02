"""API tests for Commodities Hub FastAPI endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from earnings_engine.api.server import app


@pytest.fixture
def client():
    return TestClient(app)


def test_get_commodities_symbols_endpoint(client):
    resp = client.get("/api/v1/commodities/symbols")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "symbols" in data
    assert len(data["symbols"]) >= 5
    ids = [s["symbol"] for s in data["symbols"]]
    assert "GOLD" in ids
    assert "SILVER" in ids


def test_get_commodities_chart_intelligence_endpoint(client):
    resp = client.get("/api/v1/commodities/chart-intelligence?symbol=GOLD&interval=5m&period=5d")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["symbol"] == "GOLD"
    assert "candles" in data
    assert "indicators" in data
    assert "tactical_hud" in data
    assert "where_to_buy" in data["tactical_hud"]
    assert "where_to_sell" in data["tactical_hud"]
