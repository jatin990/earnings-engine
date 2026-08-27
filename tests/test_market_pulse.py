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

    # Check Institutional Flows & Past 7 Days History
    inst = data["institutional_flows"]
    assert "fii_net_cr" in inst
    assert "dii_net_cr" in inst
    assert "total_net_cr" in inst
    assert "fii_7d_total_cr" in inst
    assert "dii_7d_total_cr" in inst
    assert "total_7d_total_cr" in inst
    assert "history_7d" in inst
    assert len(inst["history_7d"]) == 7
    for row in inst["history_7d"]:
        assert "date" in row
        assert "day_label" in row
        assert "fii_net_cr" in row
        assert "dii_net_cr" in row
        assert "total_net_cr" in row
        assert "stance" in row

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
    payload = res.json()
    assert payload["success"] is True
    inst = payload["institutional_flows"]
    assert "history_7d" in inst
    assert len(inst["history_7d"]) >= 5
    json_data = res.json()
    assert json_data["success"] is True
    assert "fear_and_greed" in json_data
    assert "prediction" in json_data
