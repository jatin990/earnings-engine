"""Tests for Top Swingers ranking, cycle count and cycle time indicators, and API endpoints."""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from earnings_engine.api.server import app
from earnings_engine.config import Settings
from earnings_engine.data import swing_scanner as swing_scanner_mod


@pytest.fixture(autouse=True)
def setup_test_environment(tmp_path):
    swing_scanner_mod._cached_swing_results = None
    swing_scanner_mod._cached_swing_tier_map = None
    yield
    swing_scanner_mod._cached_swing_results = None
    swing_scanner_mod._cached_swing_tier_map = None


def test_get_top_swingers_calculation(monkeypatch):
    """Verify top swingers ranking algorithm prioritizes high cycles, sweet-spot duration and spreads."""
    mock_candidates = [
        {
            "ticker": "HIGH_CYC.NS",
            "tier": "HOT",
            "current_price": 100.0,
            "current_support": 98.0,
            "next_resistance": 120.0,
            "cycles": 4,
            "avg_cycle_days": 18.5,
            "spread_pct": 22.4,
            "dist_to_support_pct": 2.0,
            "composite_score": 85.0,
        },
        {
            "ticker": "LOW_CYC.NS",
            "tier": "WARM",
            "current_price": 500.0,
            "current_support": 450.0,
            "next_resistance": 520.0,
            "cycles": 1,
            "avg_cycle_days": 45.0,
            "spread_pct": 15.5,
            "dist_to_support_pct": 11.1,
            "composite_score": 60.0,
        },
        {
            "ticker": "ZERO_CYC.NS",
            "tier": "COLD",
            "current_price": 200.0,
            "current_support": 190.0,
            "next_resistance": 205.0,
            "cycles": 0,
            "avg_cycle_days": 0.0,
            "spread_pct": 7.8,
            "dist_to_support_pct": 5.2,
            "composite_score": 25.0,
        }
    ]

    monkeypatch.setattr(swing_scanner_mod, "get_cached_swing_results", lambda **kw: mock_candidates)

    top = swing_scanner_mod.get_top_swingers(min_cycles=1, limit=10)
    assert len(top) == 2  # ZERO_CYC filtered out due to cycles < 1 and comp_score < 40
    assert top[0]["ticker"] == "HIGH_CYC.NS"
    assert top[0]["cycles"] == 4
    assert top[0]["avg_cycle_days"] == 18.5
    assert top[0]["cycle_count_display"] == "4 Cycles"
    assert "~18.5d / cycle" in top[0]["cycle_time_display"]
    assert top[0]["cycle_health"] == "High Frequency"
    assert top[0]["timeframe_baseline"] == "90D Channel Rhythm"
    assert top[0]["swing_rank_score"] > top[1]["swing_rank_score"]


def test_top_swingers_api_endpoints(monkeypatch):
    """Verify REST API endpoints for top swingers return valid payloads."""
    client = TestClient(app)

    mock_candidates = [
        {
            "ticker": "TCS.NS",
            "tier": "HOT",
            "current_price": 4000.0,
            "current_support": 3950.0,
            "next_resistance": 4400.0,
            "cycles": 3,
            "avg_cycle_days": 21.0,
            "spread_pct": 11.4,
            "dist_to_support_pct": 1.2,
            "composite_score": 78.0,
        }
    ]
    monkeypatch.setattr(swing_scanner_mod, "get_cached_swing_results", lambda **kw: mock_candidates)

    resp1 = client.get("/api/v1/dashboard/swing/top-swingers?min_cycles=1&limit=10")
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert isinstance(data1, list)
    assert len(data1) == 1
    assert data1[0]["ticker"] == "TCS.NS"
    assert data1[0]["cycles"] == 3

    resp2 = client.get("/api/v1/swing/top-swingers?min_cycles=1&limit=10")
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert isinstance(data2, list)
    assert len(data2) == 1
    assert data2[0]["ticker"] == "TCS.NS"


def test_swing_endpoint_fail_safe_recovery(monkeypatch):
    """Ensure /api/v1/dashboard/swing never crashes with 500 error on cold start or fallback failure."""
    client = TestClient(app)

    # Simulate empty scanner cache and error in dynamic dashboard_api
    monkeypatch.setattr(swing_scanner_mod, "get_cached_swing_results", lambda **kw: [])
    from earnings_engine.api import dashboard_api

    def raise_error(*args, **kwargs):
        raise RuntimeError("Simulated network timeout")

    monkeypatch.setattr(dashboard_api, "get_swing_setups", raise_error)

    resp = client.get("/api/v1/dashboard/swing?limit=50")
    assert resp.status_code == 200
    assert resp.json() == []
