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


def test_hidden_staff_resigned_and_excluded_from_operational_queries():
    import uuid
    from earnings_engine.data import zepto_db

    uid = uuid.uuid4().hex[:6]
    emp_id = f"test_hidden_{uid}"
    emp_name = f"Test Hidden Staff {uid}"

    # Create active employee
    zepto_db.create_employee({
        "id": emp_id,
        "name": emp_name,
        "role": "PICKER",
        "status": "ACTIVE",
    })

    # Add attendance records
    zepto_db.save_attendance_batch({
        "store_name": "JMU-Sainik Colony",
        "file_name": "test_hidden.xlsx",
        "records": [
            {
                "employee_id": emp_id,
                "employee_name": emp_name,
                "designation": "Picker",
                "shift_date": "2026-09-25",
                "status": "PRESENT",
                "work_duration_mins": 480,
            }
        ]
    })

    # Initially employee appears in summary
    summary_before = zepto_db.get_attendance_summary(store_name="JMU-Sainik Colony")
    assert any(s["employee_id"] == emp_id for s in summary_before["staff_roster"])

    # Toggle hidden to 1
    updated = zepto_db.toggle_employee_visibility(emp_id, is_hidden=True)
    assert updated["is_hidden"] == 1
    assert updated["status"] == "RESIGNED"

    # Verify employee is completely excluded from get_attendance_summary
    summary_after = zepto_db.get_attendance_summary(store_name="JMU-Sainik Colony")
    assert not any(s["employee_id"] == emp_id for s in summary_after["staff_roster"])
    assert not any(w["employee_id"] == emp_id for w in summary_after["absenteeism_watchlist"])

    # Verify employee is excluded from get_attendance_records by default
    records = zepto_db.get_attendance_records(store_name="JMU-Sainik Colony")
    assert not any(r["employee_id"] == emp_id for r in records)

    # Verify employee appears in get_employees ONLY when include_hidden=True
    normal_staff = zepto_db.get_employees(include_hidden=False)
    assert not any(e["id"] == emp_id for e in normal_staff)

    hidden_staff = zepto_db.get_employees(include_hidden=True)
    hidden_emp = next((e for e in hidden_staff if e["id"] == emp_id), None)
    assert hidden_emp is not None
    assert hidden_emp["status"] == "RESIGNED"


def test_picker_summary_and_punch_timing_metrics():
    """Test picker role segmentation, MTD whole month averages, and shift duration calculations."""
    import uuid
    from earnings_engine.config import Settings
    from earnings_engine.data import zepto_db
    from earnings_engine.data.zepto_attendance_parser import parse_time_str

    settings = Settings()
    ensure_zepto_schema(settings)
    test_store = f"TEST_PICKER_STORE_{uuid.uuid4().hex[:8]}"

    # Verify fractional day time conversion and formatting
    assert parse_time_str(0.25) == "06:00:00"  # 1/4 day = 6:00 AM
    assert parse_time_str(1.375) == "09:00:00" # 1 day + 9/24 = 9:00 AM
    assert parse_time_str("07:30 PM") == "19:30:00"
    assert parse_time_str("06:15 AM") == "06:15:00"

    # Insert sample records for picker and supervisor across multiple days
    zepto_db.save_attendance_batch({
        "store_name": test_store,
        "file_name": "test_picker_timing.xlsx",
        "records": [
            {
                "employee_id": f"PICKER_001_{uuid.uuid4().hex[:4]}",
                "employee_name": "Rohan Picker",
                "store_name": test_store,
                "shift_date": "2026-09-01",
                "shift_name": "Morning Shift",
                "punch_in": "06:00:00",
                "punch_out": "15:00:00",
                "work_duration_mins": 540,
                "status": "PRESENT",
                "designation": "Picker",
            },
            {
                "employee_id": f"PACKER_002_{uuid.uuid4().hex[:4]}",
                "employee_name": "Suresh Packer",
                "store_name": test_store,
                "shift_date": "2026-09-01",
                "shift_name": "Morning Shift",
                "punch_in": "06:30:00",
                "punch_out": "14:30:00",
                "work_duration_mins": 480,
                "status": "PRESENT",
                "designation": "Packer / Sorter",
            },
            {
                "employee_id": f"SUP_001_{uuid.uuid4().hex[:4]}",
                "employee_name": "Vikram Supervisor",
                "store_name": test_store,
                "shift_date": "2026-09-01",
                "shift_name": "Morning Shift",
                "punch_in": "06:00:00",
                "punch_out": "16:00:00",
                "work_duration_mins": 600,
                "status": "PRESENT",
                "designation": "Shift Incharge",
            },
            {
                "employee_id": f"PICKER_001_{uuid.uuid4().hex[:4]}",
                "employee_name": "Rohan Picker",
                "store_name": test_store,
                "shift_date": "2026-09-02",
                "shift_name": "Morning Shift",
                "punch_in": "06:00:00",
                "punch_out": "14:00:00",
                "work_duration_mins": 480,
                "status": "PRESENT",
                "designation": "Picker",
            },
            {
                "employee_id": f"PACKER_002_{uuid.uuid4().hex[:4]}",
                "employee_name": "Suresh Packer",
                "store_name": test_store,
                "shift_date": "2026-09-02",
                "shift_name": "Morning Shift",
                "punch_in": "",
                "punch_out": "",
                "work_duration_mins": 0,
                "status": "ABSENT",
                "designation": "Packer / Sorter",
            },
        ]
    }, settings=settings)

    summary = zepto_db.get_attendance_summary(year_month="2026-09", store_name=test_store, settings=settings)

    # Validate MTD picker summary
    p_summary = summary.get("picker_summary", {})
    assert p_summary.get("headcount") >= 1
    assert p_summary.get("total_shifts") == 4
    assert p_summary.get("present_shifts") == 3
    assert p_summary.get("absent_shifts") == 1
    assert p_summary.get("operational_days") == 2
    # Avg pickers per operational day: 3 present shifts / 2 days = 1.5
    assert p_summary.get("avg_pickers_per_day") == 1.5
    # Total picker minutes: 540 + 480 + 480 = 1500 mins = 25.0 hours / 3 shifts = 8.3 hours avg
    assert p_summary.get("avg_picker_shift_hours") == 8.3
    assert p_summary.get("total_picker_hours") == 25.0

    # Validate daily trends contain picker breakdown
    daily_trends = summary.get("daily_trend", [])
    day1 = next((d for d in daily_trends if d["date"] == "2026-09-01"), None)
    assert day1 is not None
    assert day1["pickers_present"] == 2
    assert day1["pickers_scheduled"] == 2
    assert day1["pickers_absent"] == 0
    assert day1["pickers_avg_shift_hours"] == 8.5  # (540 + 480) / 60 / 2 = 1020 / 120 = 8.5

    day2 = next((d for d in daily_trends if d["date"] == "2026-09-02"), None)
    assert day2 is not None
    assert day2["pickers_present"] == 1
    assert day2["pickers_scheduled"] == 2
    assert day2["pickers_absent"] == 1
    assert day2["pickers_avg_shift_hours"] == 8.0  # 480 / 60 / 1 = 8.0


def test_expected_monthly_salary_calculations():
    """Test prorated daily rate, payable days, absent deductions, and expected payroll summary."""
    import uuid
    from earnings_engine.config import Settings
    from earnings_engine.data import zepto_db

    settings = Settings()
    ensure_zepto_schema(settings)
    test_store = f"TEST_PAYROLL_STORE_{uuid.uuid4().hex[:8]}"

    picker_id = f"EMP_PAY_PICK_{uuid.uuid4().hex[:4]}"
    incharge_id = f"EMP_PAY_INC_{uuid.uuid4().hex[:4]}"

    # Create employee profiles with explicit roles & baseline salaries
    zepto_db.create_employee({
        "id": picker_id,
        "name": "Ramesh Picker",
        "role": "PICKER",
        "status": "ACTIVE",
        "base_salary_monthly": 14000.0,
    }, settings=settings)

    zepto_db.create_employee({
        "id": incharge_id,
        "name": "Suresh Incharge",
        "role": "SHIFT_INCHARGE",
        "status": "ACTIVE",
        "base_salary_monthly": 20000.0,
    }, settings=settings)

    # Insert attendance records for September (30-day month)
    # Picker: 2 Present, 1 Week-Off, 1 Absent => 3 Payable Days (Daily rate = 14000 / 30 = 466.67)
    # Expected salary = 3 * 466.67 = 1400.01, Absent deduction = 1 * 466.67 = 466.67
    zepto_db.save_attendance_batch({
        "store_name": test_store,
        "file_name": "test_payroll_sep.xlsx",
        "records": [
            {
                "employee_id": picker_id,
                "employee_name": "Ramesh Picker",
                "store_name": test_store,
                "shift_date": "2026-09-01",
                "status": "PRESENT",
                "work_duration_mins": 480,
                "designation": "Picker",
            },
            {
                "employee_id": picker_id,
                "employee_name": "Ramesh Picker",
                "store_name": test_store,
                "shift_date": "2026-09-02",
                "status": "PRESENT",
                "work_duration_mins": 480,
                "designation": "Picker",
            },
            {
                "employee_id": picker_id,
                "employee_name": "Ramesh Picker",
                "store_name": test_store,
                "shift_date": "2026-09-03",
                "status": "WEEK_OFF",
                "work_duration_mins": 0,
                "designation": "Picker",
            },
            {
                "employee_id": picker_id,
                "employee_name": "Ramesh Picker",
                "store_name": test_store,
                "shift_date": "2026-09-04",
                "status": "ABSENT",
                "work_duration_mins": 0,
                "designation": "Picker",
            },
            # Incharge: 1 Present => 1 Payable Day (Daily rate = 20000 / 30 = 666.67)
            # Expected salary = 1 * 666.67 = 666.67
            {
                "employee_id": incharge_id,
                "employee_name": "Suresh Incharge",
                "store_name": test_store,
                "shift_date": "2026-09-01",
                "status": "PRESENT",
                "work_duration_mins": 540,
                "designation": "Shift Incharge",
            },
        ]
    }, settings=settings)

    # 1. Test get_attendance_summary payroll aggregations
    summary = zepto_db.get_attendance_summary(year_month="2026-09", store_name=test_store, settings=settings)
    payroll = summary.get("payroll_summary", {})

    assert payroll["days_in_month"] == 30
    assert payroll["total_payable_days"] == 4.0  # 3 (picker) + 1 (incharge)
    assert payroll["picker_expected_payroll"] == 1400.01
    assert payroll["incharge_expected_payroll"] == 666.67
    assert payroll["total_expected_payroll"] == 2066.68

    # Check staff roster individual payroll fields
    roster_picker = next((s for s in summary["staff_roster"] if s["employee_id"] == picker_id), None)
    assert roster_picker is not None
    assert roster_picker["base_salary_monthly"] == 14000.0
    assert roster_picker["daily_rate"] == 466.67
    assert roster_picker["payable_days"] == 3.0
    assert roster_picker["expected_salary"] == 1400.01
    assert roster_picker["absent_deduction"] == 466.67

    roster_incharge = next((s for s in summary["staff_roster"] if s["employee_id"] == incharge_id), None)
    assert roster_incharge is not None
    assert roster_incharge["base_salary_monthly"] == 20000.0
    assert roster_incharge["daily_rate"] == 666.67
    assert roster_incharge["payable_days"] == 1.0
    assert roster_incharge["expected_salary"] == 666.67

    # 2. Test get_employee_profile_analytics payroll breakdown
    analytics = zepto_db.get_employee_profile_analytics(picker_id, year_month="2026-09", settings=settings)
    assert "payroll_calculation" in analytics
    calc = analytics["payroll_calculation"]
    assert calc["base_salary_monthly"] == 14000.0
    assert calc["days_in_month"] == 30
    assert calc["daily_rate"] == 466.67
    assert calc["present_days"] == 2
    assert calc["week_off_days"] == 1
    assert calc["absent_days"] == 1
    assert calc["payable_days"] == 3.0
    assert calc["absent_deduction"] == 466.67
    assert calc["expected_salary"] == 1400.01
    assert "₹466.67/d" in calc["formula"]

    # Check attendance dict has the payroll fields
    att = analytics["attendance"]
    assert att["expected_salary"] == 1400.01
    assert att["payable_days"] == 3.0
    assert att["daily_rate"] == 466.67
    assert att["absent_deduction"] == 466.67


