import os
import pytest
from fastapi.testclient import TestClient
from earnings_engine.api.server import app
from earnings_engine.data.auth import create_session_token
from earnings_engine.data.zepto_attendance_parser import parse_zepto_attendance_excel
from earnings_engine.data.zepto_db import (
    ensure_zepto_schema,
    save_attendance_batch,
    get_attendance_summary,
    get_attendance_records,
)

SAMPLE_EXCEL_PATH = r"C:\Users\91700\Downloads\JMU-Sainik_Colony-Attendance-report-8165178.xlsx"

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

def test_full_e2e_attendance_pipeline(auth_client):
    if not os.path.exists(SAMPLE_EXCEL_PATH):
        pytest.skip("Local sample Excel not present on current runner")

    ensure_zepto_schema()

    # 1. Parse Excel file
    parsed = parse_zepto_attendance_excel(SAMPLE_EXCEL_PATH)
    assert parsed["store_name"] == "JMU-Sainik Colony"
    assert parsed["start_date"] == "2026-08-26"
    assert parsed["end_date"] == "2026-09-29"
    assert parsed["total_records"] == 406
    assert parsed["total_employees"] == 26
    assert parsed["summary"]["present_count"] == 305
    assert parsed["summary"]["week_off_count"] == 41

    # 2. Persist to DB
    saved = save_attendance_batch(parsed, source="E2E_TEST")
    assert saved["status"] == "success"
    assert saved["imported_records"] == 406
    assert saved["total_employees"] == 26

    # 3. Query DB Summary
    summary = get_attendance_summary(store_name="JMU-Sainik Colony")
    assert summary["headcount"] >= 26
    assert summary["total_shifts_scheduled"] >= 406
    assert summary["status_distribution"]["PRESENT"] >= 305
    assert summary["status_distribution"]["WEEK_OFF"] >= 41
    assert summary["status_distribution"]["ABSENT"] >= 47
    assert summary["attendance_rate_pct"] > 80.0

    # Verify role breakdown has expected roles
    roles = {r["role"] for r in summary["role_breakdown"]}
    assert "FR_Packer" in roles
    assert any("Hybrid" in r for r in roles)

    # 4. Verify REST API Summary
    resp_sum = auth_client.get("/api/v1/zepto/attendance/summary?store_name=JMU-Sainik Colony")
    assert resp_sum.status_code == 200
    api_sum = resp_sum.json()
    assert api_sum["headcount"] >= 26
    assert api_sum["status_distribution"]["PRESENT"] >= 305

    # 5. Verify REST API Records with Role Filter
    resp_rec = auth_client.get("/api/v1/zepto/attendance/records?store_name=JMU-Sainik Colony&designation=FR_Packer&limit=50")
    assert resp_rec.status_code == 200
    api_rec = resp_rec.json()
    assert api_rec["count"] > 0
    assert all(r["designation"] == "FR_Packer" for r in api_rec["records"])
