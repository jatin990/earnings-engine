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


def test_fetch_live_quote_and_overview(client):
    from earnings_engine.data.prices import fetch_live_quote
    settings = Settings()
    q = fetch_live_quote("SUNPHARMA.NS", settings=settings, sync_db=True)
    assert q["ticker"] == "SUNPHARMA.NS"
    assert q["current_price"] is not None
    assert q["current_price"] > 0
    assert "is_live" in q

    overview = get_stock_overview("SUNPHARMA.NS", settings)
    assert overview["success"] is True
    assert overview["quote"]["current_price"] is not None
    assert overview["quote"]["current_price"] > 0


def test_consensus_context_uses_live_data():
    from earnings_engine.consensus.context_builder import build_context, context_to_prompt
    settings = Settings()
    ctx = build_context("SUNPHARMA.NS", timeframe_days=14, settings=settings, fetch_live=True)
    assert ctx["ticker"] == "SUNPHARMA.NS"
    assert "price_action" in ctx
    assert ctx["price_action"].get("current_price") is not None
    assert ctx["price_action"]["current_price"] > 0

    prompt = context_to_prompt(ctx)
    assert "SUNPHARMA.NS" in prompt
    assert "Live Real-Time" in prompt or "Price" in prompt


def test_get_stock_earnings_endpoint_returns_quarterly_financials(client):
    response = client.get("/api/v1/stock/RELIANCE.NS/earnings")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["ticker"] == "RELIANCE.NS"
    assert "earnings_history" in data
    assert "quarterly_financials" in data
    assert isinstance(data["quarterly_financials"], list)
    if data["quarterly_financials"]:
        first = data["quarterly_financials"][0]
        for k in ["quarter", "revenue_cr", "ebitda_cr", "ebitda_margin_pct"]:
            assert k in first



