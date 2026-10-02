"""API tests for Commodities Hub FastAPI endpoints."""

from __future__ import annotations

import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

from earnings_engine.api.server import app
from tests.test_commodities_chart_engine import _make_dummy_intraday_df


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


def test_get_commodities_latest_tick_endpoint(client):
    mock_df = _make_dummy_intraday_df(20, 2750.0)
    with patch("earnings_engine.data.commodities_chart_engine.fetch_commodity_candles", return_value=mock_df):
        resp = client.get("/api/v1/commodities/latest-tick?symbol=GOLD&interval=5m")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["symbol"] == "GOLD"
        assert "spot_price" in data
        assert data["spot_price"] > 0
        assert "change_24h" in data
        assert "currency_symbol" in data
        assert "latest_candle" in data


def test_get_commodities_chart_intelligence_endpoint(client):
    mock_df = _make_dummy_intraday_df(60, 2750.0)
    with patch("earnings_engine.data.commodities_chart_engine.fetch_commodity_candles", return_value=mock_df):
        resp = client.get("/api/v1/commodities/chart-intelligence?symbol=GOLD&interval=5m&period=5d")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["symbol"] == "GOLD"
        assert "candles" in data
        assert "indicators" in data
        assert "volume_profile" in data
        assert "liquidity_sweeps" in data
        assert "microstructure" in data
        assert "tactical_hud" in data
        assert "where_to_buy" in data["tactical_hud"]
        assert "where_to_sell" in data["tactical_hud"]
        ind = data["indicators"]
        assert "poc" in ind
        assert "vah" in ind
        assert "val" in ind
        assert "liquidity_sweeps" in ind
        assert "microstructure" in ind
