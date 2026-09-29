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


def test_market_playbook_dedicated_endpoint(client):
    res = client.get("/api/v1/market-pulse/playbook")
    assert res.status_code == 200
    payload = res.json()
    assert payload["success"] is True
    assert "playbook" in payload
    playbook = payload["playbook"]
    assert "bias" in playbook
    assert "confluence_score" in playbook
    assert "actionable_rules" in playbook
    assert len(playbook["actionable_rules"]) >= 3
    assert "corridor" in playbook
    assert "expected_1d_range_pct" in playbook
    assert "expected_1d_move_pct" in playbook
    assert "expected_1d_range_pts" in playbook
    assert "expected_1d_move_pts" in playbook
    assert "upper_band_1sigma" in playbook["corridor"]
    assert "lower_band_1sigma" in playbook["corridor"]
    assert "upper_1sigma" in playbook["corridor"]
    assert "lower_1sigma" in playbook["corridor"]
    assert "nifty_spot" in playbook
    assert "divergence" in playbook
    assert "smart_money_vs_retail" in playbook
    assert "fii_ls_ratio" in playbook["divergence"]
    assert "client_ls_ratio" in playbook["divergence"]
    assert "trap_risk_score" in playbook["divergence"]
    assert "theta_decay_environment" in playbook
    assert "theta_environment" in playbook


def test_metric_glossary_dedicated_endpoint(client):
    res = client.get("/api/v1/market-pulse/glossary")
    assert res.status_code == 200
    payload = res.json()
    assert payload["success"] is True
    assert "glossary" in payload
    glossary = payload["glossary"]
    assert "categories" in glossary
    cat_ids = [c["id"] for c in glossary["categories"]]
    assert "participant_oi" in cat_ids
    assert "volatility_vix" in cat_ids
    assert "institutional_liquidity" in cat_ids
    assert "market_breadth" in cat_ids
    assert "fear_greed" in cat_ids


def test_fii_dii_release_schedule_states():
    """Verify deterministic FII/DII release schedule calculation across all trading day and weekend regimes."""
    from datetime import datetime, timezone
    from earnings_engine.data.market_pulse import compute_fii_dii_release_schedule

    # Case 1: Weekday before 18:30 IST (e.g. Wednesday 2026-09-30 06:00 UTC = 11:30 IST)
    dt_wed_morning = datetime(2026, 9, 30, 6, 0, 0, tzinfo=timezone.utc)
    sched1 = compute_fii_dii_release_schedule(latest_date_in_db="2026-09-29", now_dt=dt_wed_morning)
    assert sched1["status"] == "pending_today"
    assert "Today ~18:30 IST" in sched1["label"]
    assert sched1["is_today_settled"] is False
    assert sched1["eta_seconds"] > 0

    # Case 2: Weekday after 18:30 IST awaiting settlement (e.g. Wednesday 2026-09-30 13:45 UTC = 19:15 IST, not yet settled)
    dt_wed_evening = datetime(2026, 9, 30, 13, 45, 0, tzinfo=timezone.utc)
    sched2 = compute_fii_dii_release_schedule(latest_date_in_db="2026-09-29", now_dt=dt_wed_evening)
    assert sched2["status"] == "awaiting_settlement"
    assert "Awaiting NSE Release" in sched2["label"]

    # Case 3: Weekday after 18:30 IST already settled (Wednesday settled, next is Thursday)
    sched3 = compute_fii_dii_release_schedule(latest_date_in_db="2026-09-30", now_dt=dt_wed_evening)
    assert sched3["status"] == "settled"
    assert "Thursday ~18:30 IST" in sched3["label"]
    assert sched3["is_today_settled"] is True

    # Case 4: Friday after 18:30 IST settled -> Next is Monday
    dt_fri_evening = datetime(2026, 10, 2, 14, 0, 0, tzinfo=timezone.utc)
    sched4 = compute_fii_dii_release_schedule(latest_date_in_db="2026-10-02", now_dt=dt_fri_evening)
    assert sched4["status"] == "settled"
    assert "Monday ~18:30 IST" in sched4["label"]

    # Case 5: Saturday / Sunday weekend pause -> Next is Monday
    dt_sat = datetime(2026, 10, 3, 10, 0, 0, tzinfo=timezone.utc)
    sched5 = compute_fii_dii_release_schedule(latest_date_in_db="2026-10-02", now_dt=dt_sat)
    assert sched5["status"] == "weekend_pause"
    assert "Monday ~18:30 IST" in sched5["label"]


def test_market_pulse_card_timestamps(client):
    """Verify that liquidity, sentiment, and participant endpoints expose card-level timestamps and arrival metadata."""
    res_liq = client.get("/api/v1/market-pulse/liquidity")
    assert res_liq.status_code == 200
    liq_data = res_liq.json().get("liquidity", {})
    assert "latest_arrived_at_ist" in liq_data
    assert "next_release_schedule" in liq_data
    assert "next_release_countdown" in liq_data
    assert "history_7d" in liq_data
    for row in liq_data["history_7d"]:
        assert "arrived_at_ist" in row

    res_sent = client.get("/api/v1/market-pulse/sentiment?force_refresh=true")
    assert res_sent.status_code == 200
    sent_data = res_sent.json().get("sentiment", {})
    assert "as_of" in sent_data
    assert "as_of_ist" in sent_data
    assert "session_date" in sent_data
    assert "data_freshness" in sent_data

    res_pulse = client.get("/api/v1/market/pulse")
    assert res_pulse.status_code == 200
    pulse_data = res_pulse.json()
    assert "timestamps" in pulse_data
    ts = pulse_data["timestamps"]
    assert "sentiment_as_of" in ts
    assert "sentiment_as_of_ist" in ts
    assert "fii_dii_latest_arrival_ist" in ts
    assert "fii_dii_next_release" in ts





