"""
Tests for Tiered Graduated Swing Scanner Engine (T0: Cold 60m, T1: Warm 15m, T2: Hot 5m),
Scoring, Demotion Protection, and API Endpoints.
"""

import pytest
import sqlite3
import pandas as pd
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from earnings_engine.config import Settings
from earnings_engine.data.swing_scanner import (
    _score_support_proximity,
    _score_channel_quality,
    _score_volume_bounce,
    _score_momentum_compression,
    _score_fundamental_bonus,
    _pool,
    save_swing_pool_to_db,
    load_swing_pool_from_db,
    get_cached_swing_results,
    get_scan_status,
)
from earnings_engine.api.server import app


@pytest.fixture
def temp_db(tmp_path):
    s = Settings()
    s.data_dirs["prices"] = tmp_path
    s.ensure_dirs()
    return s


def test_swing_scoring_components():
    # 1. Proximity: At floor (support 100, price 101, res 125) -> sweet spot ~35 pts
    score, dist_pct, pos_pct, sig = _score_support_proximity(101.0, 100.0, 125.0)
    assert score >= 35.0
    assert dist_pct == 1.0
    assert sig == "Buy Zone"

    # Breakdown: price 95, support 100 -> score 0, Breakdown
    b_score, b_dist, _, b_sig = _score_support_proximity(95.0, 100.0, 125.0)
    assert b_score == 0.0
    assert b_sig == "Breakdown"

    # 2. Channel Quality: 4 cycles, 25% spread, user source -> max 20 pts
    q_score = _score_channel_quality(4, 25.0, "user")
    assert q_score >= 18.0

    # 3. Volume Bounce: 1.5x surge
    vols = pd.Series([1000] * 20 + [1500])
    v_score = _score_volume_bounce(vols)
    assert v_score == 15.0

    # 4. Momentum compression
    closes = pd.Series([100.0 + (i % 2) * 0.5 for i in range(20)])
    m_score = _score_momentum_compression(closes, mom_30d=2.0)
    assert m_score >= 12.0

    # 5. Fundamental bonus: score 8/9
    f_score = _score_fundamental_bonus(8)
    assert f_score >= 10.0


def test_swing_pool_sqlite_persistence(temp_db):
    test_item = {
        "ticker": "RELIANCE.NS",
        "tier": "HOT",
        "company_name": "Reliance Industries Ltd",
        "industry": "Oil & Gas",
        "composite_score": 78.5,
        "proximity_score": 35.0,
        "channel_score": 18.0,
        "volume_score": 15.0,
        "momentum_score": 12.0,
        "fundamental_score": 10.0,
        "current_price": 2850.0,
        "current_support": 2800.0,
        "next_resistance": 3100.0,
        "spread_pct": 10.71,
        "dist_to_support_pct": 1.78,
        "channel_position_pct": 16.6,
        "swing_signal": "Strong Buy",
        "source": "user",
        "cycles": 3,
        "avg_cycle_days": 42.0,
        "thirty_day_return_pct": 1.2,
        "prev_quarter_earnings_score": 8,
        "earnings_date": "2026-09-15",
        "scanned_at": "2026-08-29T10:00:00",
    }

    _pool["hot"]["RELIANCE.NS"] = {"result": test_item, "consecutive_low": 0}
    _pool["warm"].clear()
    _pool["candidates"].clear()

    # Save to SQLite
    save_swing_pool_to_db(temp_db)

    # Clear memory pool
    _pool["hot"].clear()

    # Hydrate back from SQLite
    load_swing_pool_from_db(temp_db)
    assert "RELIANCE.NS" in _pool["hot"]
    assert _pool["hot"]["RELIANCE.NS"]["result"]["tier"] == "HOT"
    assert _pool["hot"]["RELIANCE.NS"]["result"]["composite_score"] == 78.5


def test_swing_cached_query_and_api(temp_db, monkeypatch):
    monkeypatch.setattr("earnings_engine.api.routers.swing._settings", lambda: temp_db)
    from earnings_engine.data.auth import create_session_token
    token = create_session_token(
        user_id="test-admin",
        role="owner",
        email="admin@nexus.local",
        name="Test Admin",
        scopes=["*"],
    )
    client = TestClient(app)
    client.headers.update({
        "Cookie": f"nexus_session={token}",
        "Authorization": f"Bearer {token}",
    })

    # Populate in-memory pool
    _pool["hot"]["TCS.NS"] = {
        "result": {
            "ticker": "TCS.NS",
            "tier": "HOT",
            "composite_score": 85.0,
            "current_price": 4200.0,
            "current_support": 4150.0,
            "next_resistance": 4500.0,
            "spread_pct": 8.43,
            "dist_to_support_pct": 1.2,
            "channel_position_pct": 14.2,
            "swing_signal": "Strong Buy",
            "source": "auto",
            "prev_quarter_earnings_score": 9,
            "thirty_day_return_pct": 2.5,
        },
        "consecutive_low": 0
    }

    from earnings_engine.data.swing_scanner import _rebuild_candidates
    _rebuild_candidates()

    results = get_cached_swing_results(universe="ALL", settings=temp_db)
    assert len(results) >= 1
    assert any(r["ticker"] == "TCS.NS" for r in results)

    status = get_scan_status()
    assert "hot_count" in status
    assert "warm_count" in status

    # Test status endpoint
    res_status = client.get("/api/v1/dashboard/swing/status")
    assert res_status.status_code == 200
    assert "hot_count" in res_status.json()

    # Test swing query endpoint
    res_swing = client.get("/api/v1/dashboard/swing")
    assert res_swing.status_code == 200
    data = res_swing.json()
    assert isinstance(data, list)
