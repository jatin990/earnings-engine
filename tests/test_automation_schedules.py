"""Tests for Automation Schedules and Background Job Tracking."""
import pytest
from fastapi.testclient import TestClient
from earnings_engine.api.server import app
from earnings_engine.data.automation_schedules import (
    init_automation_schedules,
    record_job_start,
    record_job_finish,
    get_all_schedules,
    get_schedule,
)


@pytest.fixture
def client():
    return TestClient(app)


def test_automation_schedules_crud():
    # Initialize default schedules
    init_automation_schedules()

    sched = get_schedule("breakout_hot_rescore")
    assert sched is not None
    assert sched["job_name"] == "⚡ Breakout Hot Rescore"
    assert sched["interval_seconds"] == 60

    # Record job start
    record_job_start("breakout_hot_rescore")
    sched_running = get_schedule("breakout_hot_rescore")
    assert sched_running["status"] == "running"

    # Record job finish
    record_job_finish(
        job_id="breakout_hot_rescore",
        duration_s=1.85,
        summary="Rescored 12 candidates in hot pool",
    )

    sched_after = get_schedule("breakout_hot_rescore")
    assert sched_after["status"] == "active"
    assert sched_after["last_duration_s"] == 1.85
    assert sched_after["last_summary"] == "Rescored 12 candidates in hot pool"
    assert sched_after["seconds_until_next"] is not None
    assert sched_after["seconds_until_next"] <= 60


def test_automation_schedules_api_endpoints(client):
    # GET all schedules
    res = client.get("/api/v1/automation/schedules")
    assert res.status_code == 200
    data = res.json()
    assert "schedules" in data
    assert len(data["schedules"]) >= 4

    job_ids = [s["job_id"] for s in data["schedules"]]
    assert "breakout_hot_rescore" in job_ids
    assert "news_catalyst_harvest" in job_ids

    # POST trigger job
    res_trigger = client.post("/api/v1/automation/trigger?job_id=breakout_hot_rescore")
    assert res_trigger.status_code == 200
    assert res_trigger.json()["success"] is True
    assert "Triggered execution" in res_trigger.json()["message"]
