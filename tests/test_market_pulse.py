from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from earnings_engine.api.server import app
from earnings_engine.data.market_pulse import get_market_pulse_data


@pytest.fixture
def client():
    return TestClient(app)


def test_market_pulse_data_structure():
    data = get_market_pulse_data(force_refresh=True)
    assert data["success"] is True
    assert "indices" in data
    assert len(data["indices"]) >= 5
    
    # Check indices fields
    syms = [x["symbol"] for x in data["indices"]]
    assert "^NSEI" in syms
    assert "^INDIAVIX" in syms

    # Check Fear and Greed
    fg = data["fear_and_greed"]
    assert 0.0 <= fg["score"] <= 100.0
    assert "label" in fg
    assert "vix_factor" in fg

    # Check Volatility
    vol = data["volatility"]
    assert "vix_level" in vol
    assert "regime" in vol

    # Check Market Breadth
    breadth = data["breadth"]
    assert breadth["advances"] >= 0
    assert breadth["declines"] >= 0

    # Check Institutional Flows
    inst = data["institutional_flows"]
    assert "fii_net_cr" in inst
    assert "dii_net_cr" in inst

    # Check Prediction
    pred = data["prediction"]
    assert "regime" in pred
    assert "bias" in pred
    assert "commentary" in pred

    # Check Sectors
    sectors = data["sectors"]
    assert len(sectors) >= 5


def test_market_pulse_api_endpoint(client):
    res = client.get("/api/v1/market/pulse")
    assert res.status_code == 200
    json_data = res.json()
    assert json_data["success"] is True
    assert "fear_and_greed" in json_data
    assert "prediction" in json_data
