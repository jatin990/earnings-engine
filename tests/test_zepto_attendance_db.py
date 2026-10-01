import pytest
from earnings_engine.data.zepto_db import (
    ensure_zepto_schema,
    save_attendance_batch,
    get_attendance_summary,
    get_attendance_records,
    get_attendance_imports,
    delete_attendance_import,
)
from earnings_engine.data.turso_sync import SYNC_TABLES

def test_sync_tables_includes_attendance():
    assert "zepto_attendance_imports" in SYNC_TABLES
    assert "zepto_attendance_records" in SYNC_TABLES

def test_attendance_db_lifecycle():
    ensure_zepto_schema()
    mock_parsed = {
        "store_name": "JMU-Sainik Colony",
        "file_name": "test_muster.xlsx",
        "start_date": "2026-09-01",
        "end_date": "2026-09-02",
        "total_records": 2,
        "total_employees": 1,
        "records": [
            {
                "employee_id": "EMP_TEST_101",
                "employee_name": "Rajesh Kumar",
                "designation": "FR_Packer",
                "shift_date": "2026-09-01",
                "shift_name": "Morning",
                "shift_time": "06:00 - 15:00",
                "punch_in": "06:01:00",
                "punch_out": "15:04:00",
                "work_duration_mins": 543,
                "break_duration_mins": 45,
                "raw_status": "P",
                "status": "PRESENT",
            },
            {
                "employee_id": "EMP_TEST_101",
                "employee_name": "Rajesh Kumar",
                "designation": "FR_Packer",
                "shift_date": "2026-09-02",
                "shift_name": "Morning",
                "shift_time": "06:00 - 15:00",
                "punch_in": "",
                "punch_out": "",
                "work_duration_mins": 0,
                "break_duration_mins": 0,
                "raw_status": "A",
                "status": "ABSENT",
            }
        ],
        "summary": {
            "present_count": 1,
            "absent_count": 1,
            "week_off_count": 0,
            "half_day_count": 0,
            "holiday_count": 0,
            "leave_count": 0,
            "attendance_rate_pct": 50.0,
        },
    }

    result = save_attendance_batch(mock_parsed, source="TEST")
    assert result["imported_records"] == 2
    import_id = result["import_id"]

    # Test summary query
    summary = get_attendance_summary(store_name="JMU-Sainik Colony")
    assert summary["headcount"] >= 1
    assert summary["status_distribution"]["PRESENT"] >= 1
    assert summary["status_distribution"]["ABSENT"] >= 1
    assert any(r["role"] == "FR_Packer" for r in summary["role_breakdown"])
    assert "absenteeism_watchlist" in summary
    assert "role_capacity_summary" in summary
    assert "packers" in summary["role_capacity_summary"]
    assert "leadership" in summary["role_capacity_summary"]
    assert "inbound_quality_nso" in summary["role_capacity_summary"]

    # Test records query with filtering
    records = get_attendance_records(employee_id="EMP_TEST_101")
    assert len(records) == 2
    assert records[0]["employee_name"] == "Rajesh Kumar"

    filtered_records = get_attendance_records(employee_id="EMP_TEST_101", status="PRESENT")
    assert len(filtered_records) == 1
    assert filtered_records[0]["shift_date"] == "2026-09-01"

    # Test imports list
    imports = get_attendance_imports(limit=10)
    assert any(imp["id"] == import_id for imp in imports)

    # Clean up import
    deleted = delete_attendance_import(import_id)
    assert deleted is True
    post_delete_records = get_attendance_records(employee_id="EMP_TEST_101")
    assert len(post_delete_records) == 0
