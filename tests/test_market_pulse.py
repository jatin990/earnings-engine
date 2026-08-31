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

    # Check Institutional Flows & Past 7 Days / 30 Days History & Delta Persistence
    inst = data["institutional_flows"]
    assert "fii_net_cr" in inst
    assert "dii_net_cr" in inst
    assert "total_net_cr" in inst
    assert "fii_7d_total_cr" in inst
    assert "dii_7d_total_cr" in inst
    assert "total_7d_total_cr" in inst
    assert "fii_30d_total_cr" in inst
    assert "dii_30d_total_cr" in inst
    assert "total_30d_total_cr" in inst
    assert "history_7d" in inst
    assert len(inst["history_7d"]) == 7
    assert "history_extended" in inst
    assert len(inst["history_extended"]) >= 7
    for row in inst["history_extended"]:
        assert "date" in row
        assert "day_label" in row
        assert "fii_net_cr" in row
        assert "dii_net_cr" in row
        assert "total_net_cr" in row
        assert "stance" in row

    # Subsequent call should fetch delta from DB seamlessly
    data2 = get_market_pulse_data(force_refresh=True)
    inst2 = data2["institutional_flows"]
    assert len(inst2["history_extended"]) >= 7

    # Check Prediction
    pred = data["prediction"]
    assert "regime" in pred
    assert "bias" in pred
    assert "commentary" in pred

    # Check Sectors
    sectors = data["sectors"]
    assert len(sectors) >= 5

    # Check Participant Derivatives Open Interest (OI) & 7-Day Matrix
    oi = data["participant_oi"]
    assert "participants" in oi
    assert len(oi["participants"]) >= 4
    for p in oi["participants"]:
        assert "participant" in p
        assert "category_label" in p
        assert "futures_long" in p
        assert "futures_short" in p
        assert "calls_long" in p
        assert "puts_long" in p
        assert "net_contracts" in p
        assert "long_short_ratio" in p
        assert "stance" in p

    assert "history_7d" in oi
    assert len(oi["history_7d"]) >= 5
    for h in oi["history_7d"]:
        assert "date" in h
        assert "session_label" in h
        assert "fii_net_contracts" in h
        assert "dii_net_contracts" in h
        assert "pro_net_contracts" in h
        assert "client_net_contracts" in h
        assert "fii_long_short_ratio" in h

    assert "regime_verdict" in oi
    assert "commentary" in oi


def test_market_pulse_api_endpoint(client):
    res = client.get("/api/v1/market/pulse")
    assert res.status_code == 200
    payload = res.json()
    assert payload["success"] is True
    inst = payload["institutional_flows"]
    assert "history_7d" in inst
    assert len(inst["history_7d"]) >= 5
    assert "history_extended" in inst
    assert len(inst["history_extended"]) >= 5
    assert "participant_oi" in payload
    assert len(payload["participant_oi"]["history_7d"]) >= 5
    assert "fear_and_greed" in payload
    assert "prediction" in payload


def test_participant_oi_dedicated_endpoint(client):
    res = client.get("/api/v1/market-pulse/participant-oi")
    assert res.status_code == 200
    payload = res.json()
    assert payload["success"] is True
    assert "participant_oi" in payload
    oi = payload["participant_oi"]
    assert "participants" in oi
    assert len(oi["participants"]) >= 4
    assert "history_7d" in oi
    assert len(oi["history_7d"]) >= 5
    assert "regime_verdict" in oi


def test_institutional_flows_dedicated_endpoint(client):
    res = client.get("/api/v1/market-pulse/institutional-flows")
    assert res.status_code == 200
    payload = res.json()
    assert payload["success"] is True
    assert "liquidity" in payload
    liq = payload["liquidity"]
    assert "history_7d" in liq
    assert len(liq["history_7d"]) >= 5
    assert "fii_net_cr" in liq
    assert "dii_net_cr" in liq

