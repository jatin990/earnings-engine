from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from earnings_engine.api.server import app
from earnings_engine.api.stock_api import get_stock_overview


@pytest.fixture
def client():
    return TestClient(app)


def test_stock_overview_data_structure():
    data = get_stock_overview("TCS.NS")
    assert data["ticker"] == "TCS.NS"
    assert "profile" in data
    assert "quote" in data
    assert "technical" in data
    assert "factor_evaluation" in data
    assert "listing_date" in data["profile"]
    assert "trading_days_count" in data["profile"]
    assert "is_new_listing" in data["profile"]


def test_stock_page_html_endpoint(client):
    res = client.get("/stock/TCS.NS")
    assert res.status_code == 200
    assert "TCS.NS" in res.text
    assert "valListingDate" in res.text
    assert "cardAICommandCenter" in res.text
    assert "btnFetchNewsDelta" in res.text


def test_stock_api_endpoint(client):
    res = client.get("/api/v1/stock/TCS.NS/overview")
    assert res.status_code == 200
    json_data = res.json()
    assert json_data["ticker"] == "TCS.NS"
    assert "factor_evaluation" in json_data
    assert "pillars" in json_data["factor_evaluation"]


def test_watchlist_add_and_remove_endpoints(client):
    # Test adding to watchlist via query parameter
    res_add = client.post("/api/v1/watchlist/add?ticker=TCS.NS")
    assert res_add.status_code == 200
    assert res_add.json().get("success") is True

    # Test removing from watchlist via json body
    res_rem = client.post("/api/v1/watchlist/remove", json={"ticker": "TCS.NS"})
    assert res_rem.status_code == 200
    assert res_rem.json().get("success") is True


def test_kronos_predict_endpoint(client):
    res = client.post("/api/v1/kronos/predict/TCS.NS")
    assert res.status_code == 200
    json_data = res.json()
    assert "success" in json_data


def test_local_models_endpoint(client):
    res = client.get("/api/v1/consensus/local-models?host=http%3A%2F%2Flocalhost%3A11434")
    assert res.status_code == 200
    data = res.json()
    assert data.get("success") is True
    assert "status" in data
    assert "models" in data
