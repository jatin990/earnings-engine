"""Tests for Pre-Market Setups and Overnight SEBI Filings Radar."""

import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from earnings_engine.api.server import app
from earnings_engine.data.pre_market_setups import (
    is_in_overnight_window,
    score_premarket_setup,
    get_premarket_setups,
    parse_to_ist,
)


@pytest.fixture
def client():
    return TestClient(app)


def test_overnight_window_calculation():
    # 1. Evening filing at 19:45 IST (14:15 UTC) -> Should match standard_6pm & full_post_market
    pub_evening = "2026-08-27T14:15:00Z"
    is_match, phase, desc = is_in_overnight_window(pub_evening, window_mode="standard_6pm")
    assert is_match is True
    assert phase == "EVENING_FILING"
    assert "After 6 PM" in desc

    # 2. Post-close filing at 16:30 IST (11:00 UTC) -> Not standard_6pm, but matches full_post_market
    pub_postclose = "2026-08-27T11:00:00Z"
    is_match_std, phase_std, _ = is_in_overnight_window(pub_postclose, window_mode="standard_6pm")
    assert is_match_std is False

    is_match_full, phase_full, desc_full = is_in_overnight_window(pub_postclose, window_mode="full_post_market")
    assert is_match_full is True
    assert phase_full == "POST_CLOSE"
    assert "Post-Close" in desc_full

    # 3. Early morning filing at 07:15 IST (01:45 UTC) -> Matches standard_6pm, full_post_market, and early_morning
    pub_morning = "2026-08-28T01:45:00Z"
    is_match_morn, phase_morn, desc_morn = is_in_overnight_window(pub_morning, window_mode="standard_6pm")
    assert is_match_morn is True
    assert phase_morn == "PRE_OPEN"
    assert "Pre-Market Open" in desc_morn

    is_match_early, _, _ = is_in_overnight_window(pub_morning, window_mode="early_morning")
    assert is_match_early is True

    # 4. Intraday headline at 12:30 IST (07:00 UTC) -> Should NOT match premarket overnight window
    pub_intraday = "2026-08-28T07:00:00Z"
    is_match_intra, phase_intra, _ = is_in_overnight_window(pub_intraday, window_mode="standard_6pm")
    assert is_match_intra is False
    assert phase_intra == "INTRADAY"


def test_score_premarket_setup_bullish_order_win():
    item = {
        "title": "Larsen & Toubro secures mega Rs 5,000 crore order from Middle East",
        "summary": "SEBI disclosure regarding major international defense contract win",
        "category": "Order Wins & Contracts",
        "direction": "BULLISH",
        "impact_score": 88,
    }
    prev_close = 3500.0

    scored = score_premarket_setup(item, prev_close=prev_close)
    assert scored is not None
    assert "ORDER_WIN" in scored["source_code"] or "SEBI" in scored["source_code"]
    assert scored["action_code"] == "STRONG_GAP_UP"
    assert scored["est_gap_min_pct"] > 0
    assert scored["est_open_price"] > prev_close
    assert scored["premarket_trigger"] > prev_close
    assert scored["target_1"] > scored["est_open_price"]
    assert scored["stop_loss"] < prev_close


def test_score_premarket_setup_bearish_warning():
    item = {
        "title": "USFDA issues warning letter for Goa facility following inspection",
        "summary": "Company receives 483 observations from regulator",
        "category": "Regulatory, Approvals & Policy",
        "direction": "BEARISH",
        "impact_score": 80,
    }
    prev_close = 800.0

    scored = score_premarket_setup(item, prev_close=prev_close)
    assert scored is not None
    assert scored["action_code"] == "RISK_GAP_DOWN"
    assert scored["est_gap_max_pct"] < 0
    assert scored["est_open_price"] < prev_close
    assert scored["stop_loss"] > prev_close


def test_get_premarket_setups_function():
    res = get_premarket_setups(window_mode="all_recent", days_lookback=14, limit=20)
    assert res is not None
    assert res["success"] is True
    assert "summary" in res
    assert "total_overnight_setups" in res["summary"]
    assert isinstance(res["items"], list)


def test_premarket_api_endpoints(client):
    # Test GET /api/v1/premarket/setups
    res = client.get("/api/v1/premarket/setups?window=all_recent&limit=20")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert "items" in data
    assert "summary" in data

    # Test GET /api/v1/premarket/summary
    res_sum = client.get("/api/v1/premarket/summary?window=all_recent")
    assert res_sum.status_code == 200
    data_sum = res_sum.json()
    assert data_sum["success"] is True
    assert "summary" in data_sum

    # Test POST /api/v1/premarket/scan
    res_scan = client.post("/api/v1/premarket/scan")
    assert res_scan.status_code == 200
    assert res_scan.json()["success"] is True
