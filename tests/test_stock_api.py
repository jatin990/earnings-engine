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


def test_stock_rating_endpoint(client):
    response = client.get("/api/v1/stock/RELIANCE.NS/rating")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["ticker"] == "RELIANCE.NS"
    assert "fundamental" in data
    assert "technical" in data
    assert "composite" in data
    assert "metrics" in data["fundamental"]


def test_recalculate_audit_endpoints(client):
    # Test single ticker audit endpoint
    response = client.get("/api/v1/recalculate/audit/RELIANCE.NS")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "entries" in data

    # Test global ticker audit log endpoint
    response2 = client.get("/api/v1/ticker/audit-log?ticker=RELIANCE.NS&limit=10")
    assert response2.status_code == 200
    data2 = response2.json()
    assert isinstance(data2, list)


def test_live_week_hl_endpoint(client):
    response = client.post("/api/v1/stock/RELIANCE.NS/live-week-hl")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["ticker"] == "RELIANCE.NS"
    assert "high_pct" in data
    assert "low_pct" in data

