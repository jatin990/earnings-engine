import os
import pytest
from earnings_engine.data.zepto_attendance_parser import (
    parse_zepto_attendance_excel,
    excel_date_to_iso,
    normalize_muster_status,
)

SAMPLE_EXCEL_PATH = r"C:\Users\91700\Downloads\JMU-Sainik_Colony-Attendance-report-8165178.xlsx"

def test_excel_date_to_iso():
    assert excel_date_to_iso(46294) == "2026-09-29"
    assert excel_date_to_iso("2026-09-29") == "2026-09-29"
    assert excel_date_to_iso(46260) == "2026-08-26"
    assert excel_date_to_iso("26-08-2026") == "2026-08-26"

def test_normalize_muster_status():
    assert normalize_muster_status("P") == "PRESENT"
    assert normalize_muster_status("A") == "ABSENT"
    assert normalize_muster_status("A-R") == "ABSENT"
    assert normalize_muster_status("WO") == "WEEK_OFF"
    assert normalize_muster_status("HD") == "HALF_DAY"
    assert normalize_muster_status("F") == "HOLIDAY"
    assert normalize_muster_status("MIS") == "ABSENT"

def test_parse_real_sample_if_available():
    if not os.path.exists(SAMPLE_EXCEL_PATH):
        pytest.skip("Local sample Excel not present on current runner")

    result = parse_zepto_attendance_excel(SAMPLE_EXCEL_PATH)
    assert result["store_name"] == "JMU-Sainik Colony"
    assert result["start_date"] == "2026-08-26"
    assert result["end_date"] == "2026-09-29"
    assert result["total_records"] == 406
    assert result["total_employees"] == 26
    assert len(result["records"]) == 406

    summary = result["summary"]
    assert summary["present_count"] == 305
    assert summary["absent_count"] >= 47
    assert summary["week_off_count"] == 41
    assert summary["attendance_rate_pct"] > 80.0
