import io
import pytest
from fastapi.testclient import TestClient
from earnings_engine.api.server import app
from earnings_engine.data.auth import create_session_token
from earnings_engine.data.zepto_db import (
    save_attendance_batch,
    get_attendance_summary,
    get_attendance_records,
)

@pytest.fixture
def auth_client():
    c = TestClient(app)
    token = create_session_token(
        user_id="usr_owner",
        role="owner",
        email="owner@nexus.local",
        name="Nexus Owner",
        scopes=["*"],
    )
    c.cookies.set("nexus_session", token)
    return c

def test_attendance_summary_endpoint(auth_client):
    resp = auth_client.get("/api/v1/zepto/attendance/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert "status_distribution" in data
    assert "role_breakdown" in data
    assert "daily_trend" in data

def test_attendance_records_endpoint(auth_client):
    # Seed a record
    save_attendance_batch({
        "store_name": "JMU-Sainik Colony",
        "file_name": "api_test.xlsx",
        "start_date": "2026-09-01",
        "end_date": "2026-09-01",
        "total_records": 1,
        "total_employees": 1,
        "records": [{
            "employee_id": "EMP_API_TEST",
            "employee_name": "API Test User",
            "designation": "FR_Packer",
            "shift_date": "2026-09-01",
            "status": "PRESENT",
            "work_duration_mins": 480,
        }],
    })

    resp = auth_client.get("/api/v1/zepto/attendance/records?employee_id=EMP_API_TEST")
    assert resp.status_code == 200
    data = resp.json()
    assert "records" in data
    assert len(data["records"]) >= 1
    assert data["records"][0]["employee_id"] == "EMP_API_TEST"

def test_attendance_imports_and_delete_endpoint(auth_client):
    resp = auth_client.get("/api/v1/zepto/attendance/imports")
    assert resp.status_code == 200
    data = resp.json()
    assert "imports" in data
    if data["imports"]:
        imp_id = data["imports"][0]["id"]
        del_resp = auth_client.delete(f"/api/v1/zepto/attendance/imports/{imp_id}")
        assert del_resp.status_code == 200
        assert del_resp.json()["status"] == "success"

def test_attendance_upload_real_sample_if_present(auth_client):
    import os
    sample_path = r"C:\Users\91700\Downloads\JMU-Sainik_Colony-Attendance-report-8165178.xlsx"
    if not os.path.exists(sample_path):
        pytest.skip("Sample excel not present on this machine")

    with open(sample_path, "rb") as f:
        file_bytes = f.read()

    files = {"file": ("JMU-Sainik_Colony-Attendance-report-8165178.xlsx", file_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    resp = auth_client.post("/api/v1/zepto/attendance/upload", files=files)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["store_name"] == "JMU-Sainik Colony"
    assert data["total_records"] == 406
    assert data["total_employees"] == 26
