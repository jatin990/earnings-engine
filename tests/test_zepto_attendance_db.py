import pytest
from earnings_engine.data.zepto_db import (
    ensure_zepto_schema,
    save_attendance_batch,
    get_attendance_summary,
    get_attendance_records,
    get_attendance_imports,
    delete_attendance_import,
    get_employee_attendance_detail,
    save_store_metrics,
    get_store_metrics_summary,
    save_loss_record,
    get_loss_summary,
    save_manpower_utilization,
    get_manpower_utilization_summary,
)
from earnings_engine.data.turso_sync import SYNC_TABLES

def test_sync_tables_includes_attendance_and_operations():
    assert "zepto_attendance_imports" in SYNC_TABLES
    assert "zepto_attendance_records" in SYNC_TABLES
    assert "zepto_store_metrics" in SYNC_TABLES
    assert "zepto_loss_records" in SYNC_TABLES
    assert "zepto_manpower_utilization" in SYNC_TABLES


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


def test_employee_attendance_drawer_detail_and_operations():
    ensure_zepto_schema()
    mock_parsed = {
        "store_name": "JMU-Sainik Colony",
        "file_name": "test_muster_drawer.xlsx",
        "start_date": "2026-09-01",
        "end_date": "2026-09-03",
        "total_records": 3,
        "total_employees": 1,
        "records": [
            {
                "employee_id": "EMP_DRAWER_99",
                "employee_name": "Amit Sharma",
                "designation": "Picker",
                "shift_date": "2026-09-01",
                "shift_name": "Morning",
                "shift_time": "06:00 - 15:00",
                "punch_in": "06:05:00",
                "punch_out": "15:10:00",
                "work_duration_mins": 545,
                "break_duration_mins": 30,
                "raw_status": "P",
                "status": "PRESENT",
            },
            {
                "employee_id": "EMP_DRAWER_99",
                "employee_name": "Amit Sharma",
                "designation": "Picker",
                "shift_date": "2026-09-02",
                "shift_name": "Morning",
                "shift_time": "06:00 - 15:00",
                "punch_in": "",
                "punch_out": "",
                "work_duration_mins": 0,
                "break_duration_mins": 0,
                "raw_status": "A",
                "status": "ABSENT",
            },
            {
                "employee_id": "EMP_DRAWER_99",
                "employee_name": "Amit Sharma",
                "designation": "Picker",
                "shift_date": "2026-09-03",
                "shift_name": "Morning",
                "shift_time": "06:00 - 15:00",
                "punch_in": "06:00:00",
                "punch_out": "15:00:00",
                "work_duration_mins": 540,
                "break_duration_mins": 30,
                "raw_status": "P",
                "status": "PRESENT",
            },
        ],
        "summary": {
            "present_count": 2,
            "absent_count": 1,
            "week_off_count": 0,
            "half_day_count": 0,
            "holiday_count": 0,
            "leave_count": 0,
            "attendance_rate_pct": 66.7,
        },
    }

    res = save_attendance_batch(mock_parsed, source="TEST")
    imp_id = res["import_id"]

    # 1. Test Employee Drawer Detail DAL
    detail = get_employee_attendance_detail("EMP_DRAWER_99")
    assert detail is not None
    assert detail["employee_name"] == "Amit Sharma"
    assert detail["designation"] == "Picker"
    assert detail["total_shifts"] == 3
    assert detail["present_count"] == 2
    assert detail["absent_count"] == 1
    assert detail["attendance_rate_pct"] > 60.0
    assert len(detail["punch_history"]) == 3
    assert "risk_tier" in detail

    # 2. Test Store Metrics Scorecard DAL
    m_res = save_store_metrics({
        "store_name": "JMU-Sainik Colony",
        "metric_date": "2026-09-29",
        "sales_gmv": 325400.0,
        "order_count": 820,
        "aov": 396.8,
        "inbound_hours": 18.5,
        "outbound_hours": 42.0,
        "packer_ipp": 132.4,
        "sla_adherence_pct": 98.6,
    })
    assert m_res["id"] is not None

    m_summary = get_store_metrics_summary(store_name="JMU-Sainik Colony")
    assert m_summary["total_gmv"] >= 325400.0
    assert m_summary["total_orders"] >= 820
    assert len(m_summary["daily_metrics"]) >= 1

    # 3. Test Loss & Shrinkage DAL
    l_res = save_loss_record({
        "store_name": "JMU-Sainik Colony",
        "record_date": "2026-09-29",
        "loss_type": "DQ_LOSS",
        "category": "FRUITS_VEG",
        "amount": 1420.50,
        "sku_count": 14,
        "notes": "Tomato & greens spoilage",
    })
    assert l_res["id"] is not None

    l_summary = get_loss_summary(store_name="JMU-Sainik Colony")
    assert l_summary["total_loss_amount"] >= 1420.50
    assert "category_breakdown" in l_summary
    assert any(c["category"] == "FRUITS_VEG" for c in l_summary["category_breakdown"])

    # 4. Test Manpower Utilization DAL
    u_res = save_manpower_utilization({
        "store_name": "JMU-Sainik Colony",
        "util_date": "2026-09-29",
        "employee_id": "EMP_DRAWER_99",
        "employee_name": "Amit Sharma",
        "role": "Picker",
        "items_picked": 640,
        "active_pick_hours": 6.5,
        "idle_hours": 1.2,
        "ipp": 98.4,
        "flex_labor_cost": 1200.0,
    })
    assert u_res["id"] is not None

    u_summary = get_manpower_utilization_summary(store_name="JMU-Sainik Colony")
    assert u_summary["total_items_picked"] >= 640
    assert u_summary["avg_ipp"] > 0
    assert len(u_summary["records"]) >= 1

    # Clean up
    delete_attendance_import(imp_id)

