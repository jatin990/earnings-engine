"""Tests for Automation Schedules, Scheduler Engine, and Background Job Tracking."""
import pytest
from fastapi.testclient import TestClient
from earnings_engine.api.server import app
from earnings_engine.data.automation_schedules import (
    init_automation_schedules,
    record_job_start,
    record_job_finish,
    append_schedule_log,
    get_all_schedules,
    get_schedule,
    get_schedule_logs,
    create_schedule,
    update_schedule,
    delete_schedule,
)
from earnings_engine.data.scheduler_engine import get_scheduler_engine


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


def test_scheduler_engine_controls_and_crud_apis(client):
    # 1. Test Engine Status API
    res_engine = client.get("/api/v1/automation/engine")
    assert res_engine.status_code == 200
    eng_data = res_engine.json()
    assert "is_running" in eng_data
    assert "total_schedules" in eng_data

    # 2. Test Create Custom Schedule
    custom_job = {
        "job_id": "test_custom_scanner",
        "job_name": "Test Custom Scanner Flow",
        "category": "Scanner",
        "interval_seconds": 120,
        "params_json": '{"universe": "NSE_TOP"}',
        "is_enabled": True,
    }
    res_create = client.post("/api/v1/automation/schedules", json=custom_job)
    assert res_create.status_code == 200
    assert res_create.json()["success"] is True
    assert res_create.json()["schedule"]["job_id"] == "test_custom_scanner"
    assert res_create.json()["schedule"]["interval_seconds"] == 120

    # 3. Test Get Single Schedule
    res_get = client.get("/api/v1/automation/schedules/test_custom_scanner")
    assert res_get.status_code == 200
    assert res_get.json()["schedule"]["job_name"] == "Test Custom Scanner Flow"

    # 4. Test Update Schedule
    update_payload = {
        "job_name": "Updated Custom Scanner",
        "interval_seconds": 600,
    }
    res_update = client.put("/api/v1/automation/schedules/test_custom_scanner", json=update_payload)
    assert res_update.status_code == 200
    assert res_update.json()["schedule"]["job_name"] == "Updated Custom Scanner"
    assert res_update.json()["schedule"]["interval_seconds"] == 600

    # 5. Test Pause & Resume
    res_pause = client.post("/api/v1/automation/schedules/test_custom_scanner/stop")
    assert res_pause.status_code == 200
    assert res_pause.json()["schedule"]["status"] == "paused"

    res_resume = client.post("/api/v1/automation/schedules/test_custom_scanner/start")
    assert res_resume.status_code == 200
    assert res_resume.json()["schedule"]["status"] == "active"

    # 6. Test Logging & Logs Endpoint
    append_schedule_log(
        job_id="test_custom_scanner",
        started_at="2026-08-28T08:00:00Z",
        finished_at="2026-08-28T08:00:02Z",
        duration_s=2.0,
        status="success",
        summary="Test execution completed successfully.",
    )
    res_logs = client.get("/api/v1/automation/logs?job_id=test_custom_scanner")
    assert res_logs.status_code == 200
    logs_data = res_logs.json()
    assert logs_data["success"] is True
    assert len(logs_data["logs"]) >= 1
    assert logs_data["logs"][0]["job_id"] == "test_custom_scanner"
    assert logs_data["logs"][0]["status"] == "success"

    # 7. Test Delete Schedule
    res_del = client.delete("/api/v1/automation/schedules/test_custom_scanner")
    assert res_del.status_code == 200
    assert res_del.json()["success"] is True
    assert get_schedule("test_custom_scanner") is None


def test_sidebar_badges_endpoint(client):
    """Verify dynamic sidebar badge counters for catalysts and breakouts."""
    res = client.get("/api/v1/sidebar/badges")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert "catalysts_count" in data
    assert "breakouts_count" in data
    assert isinstance(data["catalysts_count"], int)
    assert isinstance(data["breakouts_count"], int)


