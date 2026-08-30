"""Tests for Breakout Radar Async Non-Blocking Scheduling and Strategy-Attached Tracking."""

from __future__ import annotations

import json
import pytest
from fastapi.testclient import TestClient

from earnings_engine.api.server import app
from earnings_engine.config import Settings
from earnings_engine.data import breakout_scanner as bks
from earnings_engine.data.breakout_scanner import (
    _pool,
    _pool_key,
    _promote,
    _rebuild_candidates,
    save_breakout_pool_to_db,
    load_breakout_pool_from_db,
    get_cached_scan_results,
    BREAKOUT_STRATEGIES,
)
from earnings_engine.data.db import get_db_connection
from earnings_engine.data.migrations import apply_migrations


@pytest.fixture
def client():
    return TestClient(app)


def test_strategy_pool_keys_and_coexistence():
    """Verify that multiple strategy setups for the same ticker coexist without collision."""
    _pool["hot"].clear()
    _pool["warm"].clear()
    _pool["candidates"] = []
    _pool["strategy_pools"] = {}

    ticker = "RELIANCE.NS"

    # 1. Setup in Classic Technical
    res1 = {
        "ticker": ticker,
        "strategy": "CLASSIC_TECHNICAL",
        "composite_score": 85.0,
        "breakout_trigger": 3000.0,
        "signal_price": 2950.0,
        "target_price": 3200.0,
        "stop_loss": 2850.0,
        "setup_archetype": "52W High Coil",
        "pct_from_high": -1.5,
        "volume_ratio": 1.8,
        "tier": "HOT",
    }
    _promote(ticker, res1)

    # 2. Setup in Delivery Absorption
    res2 = {
        "ticker": ticker,
        "strategy": "NSE_DELIVERY_ABSORPTION",
        "composite_score": 82.0,
        "breakout_trigger": 3020.0,
        "signal_price": 2960.0,
        "target_price": 3250.0,
        "stop_loss": 2880.0,
        "setup_archetype": "Institutional Accumulation",
        "pct_from_high": -1.2,
        "volume_ratio": 2.4,
        "tier": "HOT",
    }
    _promote(ticker, res2)

    # 3. Setup in Donchian Squeeze
    res3 = {
        "ticker": ticker,
        "strategy": "DONCHIAN_TTM_SQUEEZE",
        "composite_score": 68.0,
        "breakout_trigger": 3010.0,
        "signal_price": 2955.0,
        "target_price": 3180.0,
        "stop_loss": 2890.0,
        "setup_archetype": "Donchian Breach",
        "pct_from_high": -1.6,
        "volume_ratio": 1.4,
        "tier": "WARM",
    }
    _promote(ticker, res3)

    # All three keys must coexist in the pool
    k1 = f"{ticker}::CLASSIC_TECHNICAL"
    k2 = f"{ticker}::NSE_DELIVERY_ABSORPTION"
    k3 = f"{ticker}::DONCHIAN_TTM_SQUEEZE"

    assert k1 in _pool["hot"] or k1 in _pool["warm"]
    assert k2 in _pool["hot"] or k2 in _pool["warm"]
    assert k3 in _pool["hot"] or k3 in _pool["warm"]

    _rebuild_candidates()

    # Candidates list must contain all 3 independent strategy setups for RELIANCE.NS
    rel_cands = [c for c in _pool["candidates"] if c.get("ticker") == ticker]
    assert len(rel_cands) == 3

    # Per-strategy pools must contain their respective setups
    assert len(_pool["strategy_pools"]["CLASSIC_TECHNICAL"]["candidates"]) >= 1
    assert len(_pool["strategy_pools"]["NSE_DELIVERY_ABSORPTION"]["candidates"]) >= 1
    assert len(_pool["strategy_pools"]["DONCHIAN_TTM_SQUEEZE"]["candidates"]) >= 1


def test_db_persistence_with_strategy_attached():
    """Verify persisting and loading multiple strategy setups for the same stock in SQLite."""
    settings = Settings()
    apply_migrations(settings)

    ticker = "INFY.NS"
    _pool["hot"].clear()
    _pool["warm"].clear()

    res_strat1 = {
        "ticker": ticker,
        "strategy": "VOLUME_PROFILE_VAH",
        "composite_score": 72.0,
        "breakout_trigger": 1900.0,
        "signal_price": 1860.0,
        "target_price": 2050.0,
        "stop_loss": 1780.0,
        "setup_archetype": "VAH Volume Breakout",
        "pct_from_high": -2.0,
        "volume_ratio": 2.1,
        "tier": "WARM",
    }
    res_strat2 = {
        "ticker": ticker,
        "strategy": "NSE_FO_CALL_WALL",
        "composite_score": 79.0,
        "breakout_trigger": 1910.0,
        "signal_price": 1870.0,
        "target_price": 2080.0,
        "stop_loss": 1800.0,
        "setup_archetype": "Call Wall Squeeze",
        "pct_from_high": -1.8,
        "volume_ratio": 2.3,
        "tier": "WARM",
    }

    _promote(ticker, res_strat1)
    _promote(ticker, res_strat2)
    _rebuild_candidates()

    save_breakout_pool_to_db(settings)

    # Clear memory pool and reload from DB
    _pool["hot"].clear()
    _pool["warm"].clear()
    _pool["candidates"] = []

    loaded = load_breakout_pool_from_db(settings)
    assert loaded is True

    infy_cands = [c for c in _pool["candidates"] if c.get("ticker") == ticker]
    strats = {c.get("strategy") for c in infy_cands}
    assert "VOLUME_PROFILE_VAH" in strats
    assert "NSE_FO_CALL_WALL" in strats


def test_async_non_blocking_schedule_endpoints(client):
    """Verify all trigger endpoints return non-blocking scheduled status immediately."""
    # 1. Parallel multi-strategy scan trigger
    resp = client.post("/api/v1/breakout-radar/schedules/parallel-scan", params={"min_score": 35})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["status"] == "scheduled"
    assert "scheduled in the background" in data["message"].lower()

    # 2. Single strategy schedule trigger
    resp2 = client.post("/api/v1/breakout-radar/schedules/breakout_delivery_absorption_scan/trigger")
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["success"] is True
    assert data2["status"] == "scheduled"
    assert "scheduled in the background" in data2["message"].lower()

    # 3. Status polling endpoint
    resp3 = client.get("/api/v1/breakout-radar/status")
    assert resp3.status_code == 200
    data3 = resp3.json()
    assert data3["success"] is True
    assert "status" in data3
    assert "is_scanning" in data3
    assert "hot_count" in data3
    assert "warm_count" in data3
    assert ("candidates_found" in data3 or "candidates_count" in data3)


def test_no_test_or_dummy_records_in_breakout(client):
    """Verify test tickers like TEST_XYZ.NS or MOCK_DUMMY are strictly rejected."""
    resp = client.get("/api/v1/breakout-radar", params={"universe": "all", "min_score": 0})
    assert resp.status_code == 200
    data = resp.json()
    tickers = [c.get("ticker", "") for c in data.get("candidates", [])]
    for t in tickers:
        t_up = str(t).upper()
        assert "TEST" not in t_up
        assert "MOCK" not in t_up
        assert "DUMMY" not in t_up
