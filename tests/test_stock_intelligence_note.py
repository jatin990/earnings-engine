"""Tests for the Universal Stock Intelligence Note aggregator and API endpoints."""

import pytest
from starlette.testclient import TestClient

from earnings_engine.config import Settings
from earnings_engine.api.server import app
from earnings_engine.api.stock_api import get_stock_intelligence_note


@pytest.fixture
def client():
    return TestClient(app)


def test_get_stock_intelligence_note_structure():
    settings = Settings()
    # Test with a known or fallback ticker
    res = get_stock_intelligence_note("BAJAJ-AUTO.NS", settings=settings)
    assert res["success"] is True
    assert res["ticker"] == "BAJAJ-AUTO.NS"
    assert "price_reaction" in res
    assert "swing_structure" in res
    assert "ai_thesis" in res
    assert "price_action_explanation" in res["price_reaction"]
    assert "support_level" in res["swing_structure"]
    assert "resistance_level" in res["swing_structure"]
    assert "thesis" in res["ai_thesis"]
    assert "growth_drivers" in res["ai_thesis"]
    assert "risk_factors" in res["ai_thesis"]
    assert isinstance(res["news_catalysts"], list)
    assert isinstance(res["beat_history"], list)


def test_api_stock_intelligence_note_endpoints(client):
    res = client.get("/api/v1/stock/BAJAJ-AUTO.NS/intelligence-note")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["ticker"] == "BAJAJ-AUTO.NS"
    assert "price_reaction" in data
    assert "swing_structure" in data
    assert "ai_thesis" in data

    # Test POST with model parameters
    post_res = client.post("/api/v1/stock/BAJAJ-AUTO.NS/intelligence-note?model_name=llama3.2:3b&provider=ollama")
    assert post_res.status_code == 200
    post_data = post_res.json()
    assert post_data["success"] is True
    assert "thesis" in post_data["ai_thesis"]
