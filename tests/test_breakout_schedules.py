"""Unit and integration tests for Multi-Strategy Breakout Scheduler & Parallel Scanning.

Verifies:
1. Schedule registration in DEFAULT_SCHEDULES for all 5 strategies + master parallel sweep.
2. SchedulerEngine handlers and execution dispatch for each strategy.
3. Multi-strategy parallel scan runner (run_multi_strategy_parallel_scan).
4. REST API endpoints for breakout schedules, configuration, and parallel triggers.
"""

import pytest
from fastapi.testclient import TestClient
from earnings_engine.config import Settings
from earnings_engine.api.server import app
from earnings_engine.data.automation_schedules import (
    DEFAULT_SCHEDULES,
    get_all_schedules,
    update_schedule,
)
from earnings_engine.data.scheduler_engine import get_scheduler_engine
from earnings_engine.data.breakout_scanner import run_multi_strategy_parallel_scan


@pytest.fixture
def client():
    return TestClient(app)


def test_default_breakout_schedules_registered():
    """Verify all 5 strategy schedules and master parallel sweep are in DEFAULT_SCHEDULES."""
    job_ids = [s["job_id"] for s in DEFAULT_SCHEDULES]
    
    expected = [
        "breakout_all_strategies_parallel",
        "breakout_cold_scan",
        "breakout_delivery_absorption_scan",
        "breakout_fo_call_wall_scan",
        "breakout_volume_profile_scan",
        "breakout_donchian_squeeze_scan",
    ]
    for exp in expected:
        assert exp in job_ids, f"Expected '{exp}' in DEFAULT_SCHEDULES"


def test_scheduler_engine_has_breakout_handlers():
    """Verify SchedulerEngine has registered handlers for all breakout jobs."""
    engine = get_scheduler_engine()
    
    expected_handlers = [
        "breakout_all_strategies_parallel",
        "breakout_cold_scan",
        "breakout_delivery_absorption_scan",
        "breakout_fo_call_wall_scan",
        "breakout_volume_profile_scan",
        "breakout_donchian_squeeze_scan",
    ]
    for job_id in expected_handlers:
        assert job_id in engine._job_handlers, f"Handler for '{job_id}' not found in SchedulerEngine"


def test_breakout_schedules_api_endpoint(client):
    """Verify GET /api/v1/breakout-radar/schedules returns registered strategy schedules."""
    res = client.get("/api/v1/breakout-radar/schedules")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert "schedules" in data
    
    job_ids = [s["job_id"] for s in data["schedules"]]
    assert "breakout_all_strategies_parallel" in job_ids
    assert "breakout_delivery_absorption_scan" in job_ids
    assert "breakout_fo_call_wall_scan" in job_ids
    assert "breakout_volume_profile_scan" in job_ids
    assert "breakout_donchian_squeeze_scan" in job_ids


def test_breakout_schedule_configuration_endpoint(client):
    """Verify POST /api/v1/breakout-radar/schedules/configure updates schedule interval and status."""
    res = client.post(
        "/api/v1/breakout-radar/schedules/configure",
        params={
            "job_id": "breakout_delivery_absorption_scan",
            "interval_seconds": 1800,
            "is_enabled": True,
            "status": "active",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["schedule"]["interval_seconds"] == 1800
    assert data["schedule"]["status"] == "active"


def test_multi_strategy_parallel_scan_execution(monkeypatch):
    """Verify run_multi_strategy_parallel_scan runs across all 5 strategies concurrently."""
    import earnings_engine.data.breakout_scanner as bks_mod

    def _mock_score(ticker, settings, strategy="CLASSIC_TECHNICAL", use_live_quote=True):
        return {
            "ticker": ticker,
            "strategy": strategy,
            "composite_score": 75.0,
            "breakout_trigger": 1000.0,
            "signal_price": 980.0,
            "target_price": 1100.0,
            "stop_loss": 940.0,
            "setup_archetype": "Parallel Sweep Setup",
            "pct_from_high": -2.0,
            "volume_ratio": 2.0,
            "tier": "HOT",
        }

    monkeypatch.setattr(bks_mod, "_score_single_ticker", _mock_score)

    settings = Settings()
    test_tickers = ["TCS.NS", "INFY.NS", "RELIANCE.NS"]
    res = run_multi_strategy_parallel_scan(settings=settings, tickers=test_tickers, min_score=20.0)
    
    assert res["success"] is True
    assert len(res["strategy_results"]) == 5
    assert "strategy_results" in res
    
    # Check that all 5 strategies reported findings
    for strat in [
        "CLASSIC_TECHNICAL",
        "NSE_DELIVERY_ABSORPTION",
        "NSE_FO_CALL_WALL",
        "VOLUME_PROFILE_VAH",
        "DONCHIAN_TTM_SQUEEZE",
    ]:
        assert strat in res["strategy_results"], f"Missing summary for {strat}"
        assert "candidates_found" in res["strategy_results"][strat]
        assert "elapsed_seconds" in res["strategy_results"][strat]


def test_breakout_parallel_scan_api_endpoint(client, monkeypatch):
    """Verify POST /api/v1/breakout-radar/schedules/parallel-scan executes or dispatches."""
    from earnings_engine.data.scheduler_engine import SchedulerEngine
    monkeypatch.setattr(SchedulerEngine, "dispatch_job", lambda self, job_id, settings=None: True)
    
    # Test background dispatch
    res_bg = client.post("/api/v1/breakout-radar/schedules/parallel-scan?background=true")
    assert res_bg.status_code == 200
    data_bg = res_bg.json()
    assert data_bg["success"] is True
    assert data_bg["job_id"] == "breakout_all_strategies_parallel"


def test_breakout_single_schedule_trigger_api(client, monkeypatch):
    """Verify POST /api/v1/breakout-radar/schedules/{job_id}/trigger executes single strategy."""
    from earnings_engine.data.scheduler_engine import SchedulerEngine
    monkeypatch.setattr(SchedulerEngine, "dispatch_job", lambda self, job_id, settings=None: True)

    res = client.post("/api/v1/breakout-radar/schedules/breakout_volume_profile_scan/trigger")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["job_id"] == "breakout_volume_profile_scan"
