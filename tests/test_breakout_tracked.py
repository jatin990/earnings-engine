"""Unit and integration tests for Breakout Radar Tracked Signals Archive and Sub-Tab API."""

import pytest
from fastapi.testclient import TestClient
from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection
from earnings_engine.data.migrations import apply_migrations
from earnings_engine.data.breakout_scanner import (
    get_tracked_breakouts,
    save_breakout_pool_to_db,
    evaluate_stock_breakout,
)
from earnings_engine.api.server import app


@pytest.fixture(scope="module")
def app_client():
    settings = Settings()
    apply_migrations(settings)
    return TestClient(app)


def test_tracked_breakouts_presets():
    """Test that get_tracked_breakouts correctly handles day presets."""
    settings = Settings()
    apply_migrations(settings)

    # Test preset days
    for preset in [1, 3, 7, 14, 30, "all"]:
        res = get_tracked_breakouts(days=preset, settings=settings)
        assert res["success"] is True
        assert "items" in res
        assert "summary" in res
        assert "total_count" in res
        assert isinstance(res["items"], list)
        assert res["total_count"] >= 0


def test_tracked_breakouts_date_range():
    """Test that get_tracked_breakouts filters by date range."""
    settings = Settings()
    apply_migrations(settings)

    res = get_tracked_breakouts(start_date="2026-08-01", end_date="2026-08-28", settings=settings)
    assert res["success"] is True
    assert res["timeframe"]["start_date"] == "2026-08-01"
    assert res["timeframe"]["end_date"] == "2026-08-28"
    assert isinstance(res["items"], list)


def test_tracked_breakouts_filters():
    """Test filtering by tier and outcome."""
    settings = Settings()
    apply_migrations(settings)

    # Tier filter
    res_hot = get_tracked_breakouts(days=30, tier="HOT", settings=settings)
    assert res_hot["success"] is True
    for item in res_hot["items"]:
        assert item["tier"] == "HOT"

    # Outcome filter
    res_outcome = get_tracked_breakouts(days=30, outcome="TARGET_HIT", settings=settings)
    assert res_outcome["success"] is True
    for item in res_outcome["items"]:
        assert item["outcome"] == "TARGET_HIT"


def test_tracked_breakouts_rest_endpoint(app_client):
    """Test the REST endpoints /api/v1/breakout/tracked and /api/v1/breakout-radar/tracked."""
    resp = app_client.get("/api/v1/breakout/tracked?days=7")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "items" in data
    assert "summary" in data

    resp_alias = app_client.get("/api/v1/breakout-radar/tracked?days=3")
    assert resp_alias.status_code == 200
    data_alias = resp_alias.json()
    assert data_alias["success"] is True

    # Test date range query params
    resp_range = app_client.get("/api/v1/breakout/tracked?start_date=2026-08-01&end_date=2026-08-28&tier=HOT")
    assert resp_range.status_code == 200
    data_range = resp_range.json()
    assert data_range["success"] is True


def test_tracked_breakout_persistence():
    """Test that candidate setups are persisted to breakout_tracked_signals."""
    settings = Settings()
    apply_migrations(settings)

    test_pool = [
        {
            "ticker": "TEST_TRACKED_STOCK.NS",
            "company_name": "Test Tracked Corp",
            "industry": "Software",
            "tier": "HOT",
            "asof_date": "2026-08-28",
            "signal_date": "2026-08-28",
            "signal_price": 500.0,
            "current_price": 500.0,
            "breakout_trigger": 520.0,
            "target_price": 580.0,
            "stop_loss": 470.0,
            "risk_reward_ratio": 2.67,
            "composite_score": 88.5,
            "resistance_score": 38.0,
            "volume_score": 18.0,
            "compression_score": 12.0,
            "momentum_score": 12.0,
            "fundamental_score": 8.5,
            "volume_ratio": 2.1,
            "atr_pct": 2.2,
            "pct_from_high": -1.5,
            "setup_archetype": "🔥 High Conviction Compression Breakout",
            "realized_return_pct": 3.2,
            "max_gain_pct": 5.8,
            "breakout_happened": True,
            "outcome": "TRIGGERED",
            "outcome_label": "Breakout Fired 🚀",
            "outcome_badge": "blue",
            "days_elapsed": 1,
            "calculation_notes": {"test": True},
            "institutional_flow": {},
        }
    ]

    from earnings_engine.data.breakout_scanner import _pool
    _pool["candidates"] = test_pool
    save_breakout_pool_to_db(settings=settings)

    # Verify query
    res = get_tracked_breakouts(days=3, settings=settings)
    matching = [it for it in res["items"] if it["ticker"] == "TEST_TRACKED_STOCK.NS"]
    assert len(matching) >= 1
    assert matching[0]["signal_price"] == 500.0
    assert matching[0]["breakout_trigger"] == 520.0
    assert matching[0]["composite_score"] == 88.5

    # Clean up test row and reset pool
    _pool["candidates"] = []
    conn = get_db_connection(settings)
    conn.execute("DELETE FROM breakout_tracked_signals WHERE ticker = 'TEST_TRACKED_STOCK.NS'")
    conn.commit()
