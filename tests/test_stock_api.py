import pytest
from starlette.testclient import TestClient

from earnings_engine.config import Settings
from earnings_engine.api.server import app
from earnings_engine.api.stock_api import get_stock_overview


@pytest.fixture
def client():
    return TestClient(app)


def test_get_stock_overview_direct():
    settings = Settings()
    res = get_stock_overview("RELIANCE.NS", settings)
    assert res["success"] is True
    assert res["ticker"] == "RELIANCE.NS"
    assert "profile" in res
    assert "quote" in res
    assert "technical" in res
    assert "earnings_history" in res
    assert "consensus" in res
    assert "catalysts" in res


def test_stock_detail_html_endpoint(client):
    response = client.get("/stock/RELIANCE.NS")
    assert response.status_code == 200
    assert "RELIANCE.NS" in response.text
    assert "Stock Intelligence & AI Consensus" in response.text


def test_stock_overview_json_endpoint(client):
    response = client.get("/api/v1/stock/RELIANCE.NS/overview")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["ticker"] == "RELIANCE.NS"
    assert "profile" in data
    assert "quote" in data
