import pytest
from starlette.testclient import TestClient
from earnings_engine.api.server import app
from earnings_engine.api import stock_api
from earnings_engine.config import Settings


@pytest.fixture
def client():
    return TestClient(app)


def test_get_stock_quote_direct():
    settings = Settings()
    res = stock_api.get_stock_quote("RELIANCE.NS", settings=settings)
    assert res["success"] is True
    assert res["ticker"] == "RELIANCE.NS"
    assert "profile" in res
    assert "quote" in res
    assert res["profile"]["currency"] == "₹"


def test_get_stock_technicals_direct():
    settings = Settings()
    res = stock_api.get_stock_technicals("RELIANCE.NS", settings=settings)
    assert res["success"] is True
    assert res["ticker"] == "RELIANCE.NS"
    assert "technical" in res
    assert "swing_range_20d" in res["technical"]
    assert "rsi" in res["technical"]
    assert "rsi_14" in res["technical"]


def test_get_stock_earnings_direct():
    settings = Settings()
    res = stock_api.get_stock_earnings("RELIANCE.NS", settings=settings)
    assert res["success"] is True
    assert res["ticker"] == "RELIANCE.NS"
    assert "earnings_history" in res
    assert "streak" in res
    assert isinstance(res["earnings_history"], list)


def test_get_stock_consensus_direct():
    settings = Settings()
    res = stock_api.get_stock_consensus("RELIANCE.NS", settings=settings)
    assert res["success"] is True
    assert res["ticker"] == "RELIANCE.NS"
    assert "consensus" in res


def test_get_stock_kronos_direct():
    settings = Settings()
    res = stock_api.get_stock_kronos("RELIANCE.NS", settings=settings)
    assert res["success"] is True
    assert res["ticker"] == "RELIANCE.NS"
    assert "kronos" in res


def test_get_stock_institutional_direct():
    settings = Settings()
    res = stock_api.get_stock_institutional("RELIANCE.NS", settings=settings)
    assert res["success"] is True
    assert res["ticker"] == "RELIANCE.NS"
    assert "institutional" in res


def test_get_stock_catalysts_direct():
    settings = Settings()
    res = stock_api.get_stock_catalysts("RELIANCE.NS", settings=settings)
    assert res["success"] is True
    assert res["ticker"] == "RELIANCE.NS"
    assert "catalysts" in res
    assert isinstance(res["catalysts"], list)


def test_get_stock_overview_composite():
    settings = Settings()
    res = stock_api.get_stock_overview("RELIANCE.NS", settings=settings)
    assert res["success"] is True
    assert res["ticker"] == "RELIANCE.NS"
    assert "profile" in res
    assert "quote" in res
    assert "technical" in res
    assert "earnings_history" in res


def test_stock_micro_endpoints(client):
    endpoints = [
        "/api/v1/stock/RELIANCE.NS/quote",
        "/api/v1/stock/RELIANCE.NS/technicals",
        "/api/v1/stock/RELIANCE.NS/earnings",
        "/api/v1/stock/RELIANCE.NS/consensus",
        "/api/v1/stock/RELIANCE.NS/kronos",
        "/api/v1/stock/RELIANCE.NS/institutional",
        "/api/v1/stock/RELIANCE.NS/catalysts",
        "/api/v1/stock/RELIANCE.NS/overview",
    ]
    for ep in endpoints:
        resp = client.get(ep)
        assert resp.status_code == 200, f"Endpoint {ep} failed with status {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data.get("success") is True
