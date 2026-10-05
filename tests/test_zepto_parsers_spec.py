"""
Comprehensive Spec-by-Example Test Suite for Zepto Dark Store Excel Reports.
Tests deterministic ingestion, multi-sheet extraction, column aliasing, serial date conversion,
and entity mapping for all 4 operational reports:
1. Attendance Muster Report
2. DQ Loss Report
3. Shrinkage Report (Inhouse DOD + MTD Summary)
4. Store Metric Summary & Manpower Utilization (Packer_Thor_Raw)
"""

import io
import zipfile
import xml.etree.ElementTree as ET
import pytest
from datetime import datetime

from earnings_engine.data.zepto_attendance_parser import (
    parse_zepto_attendance_excel,
    excel_date_to_iso,
    normalize_muster_status,
)
from earnings_engine.data.zepto_parsers import (
    parse_zepto_loss_shrinkage_excel,
    parse_zepto_store_metrics_excel,
    _extract_xlsx_sheets_native,
)
from earnings_engine.data.zepto_db import (
    save_attendance_batch,
    save_loss_records_batch,
    save_manpower_utilization_batch,
    get_attendance_records,
    get_attendance_summary,
    get_loss_summary,
    get_manpower_utilization_summary,
    get_zepto_dashboard_analytics,
)
from earnings_engine.config import Settings


def _create_mock_xlsx(sheets: dict[str, list[list[str]]]) -> bytes:
    """
    Construct an in-memory valid OpenXML (.xlsx) zip archive from sheet matrix dictionaries.
    Uses zero external dependencies.
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        # 1. [Content_Types].xml
        content_types = ET.Element("Types", xmlns="http://schemas.openxmlformats.org/package/2006/content-types")
        ET.SubElement(content_types, "Default", Extension="rels", ContentType="application/vnd.openxmlformats-package.relationships+xml")
        ET.SubElement(content_types, "Default", Extension="xml", ContentType="application/xml")
        ET.SubElement(content_types, "Override", PartName="/xl/workbook.xml", ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml")
        ET.SubElement(content_types, "Override", PartName="/xl/sharedStrings.xml", ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml")
        for idx in range(1, len(sheets) + 1):
            ET.SubElement(content_types, "Override", PartName=f"/xl/worksheets/sheet{idx}.xml", ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml")
        z.writestr("[Content_Types].xml", ET.tostring(content_types, encoding="utf-8", xml_declaration=True))

        # 2. _rels/.rels
        root_rels = ET.Element("Relationships", xmlns="http://schemas.openxmlformats.org/package/2006/relationships")
        ET.SubElement(root_rels, "Relationship", Id="rId1", Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument", Target="xl/workbook.xml")
        z.writestr("_rels/.rels", ET.tostring(root_rels, encoding="utf-8", xml_declaration=True))

        # 3. xl/_rels/workbook.xml.rels
        wb_rels = ET.Element("Relationships", xmlns="http://schemas.openxmlformats.org/package/2006/relationships")
        for idx in range(1, len(sheets) + 1):
            ET.SubElement(wb_rels, "Relationship", Id=f"rId{idx}", Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet", Target=f"worksheets/sheet{idx}.xml")
        ET.SubElement(wb_rels, "Relationship", Id=f"rId{len(sheets)+1}", Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings", Target="sharedStrings.xml")
        z.writestr("xl/_rels/workbook.xml.rels", ET.tostring(wb_rels, encoding="utf-8", xml_declaration=True))

        # 4. Shared Strings & Worksheets
        shared_strings = []
        string_map = {}

        def get_string_idx(s: str) -> int:
            if s not in string_map:
                string_map[s] = len(shared_strings)
                shared_strings.append(s)
            return string_map[s]

        # 5. xl/workbook.xml
        wb_elem = ET.Element("workbook", xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main")
        sheets_elem = ET.SubElement(wb_elem, "sheets")

        for idx, (sheet_name, matrix) in enumerate(sheets.items(), start=1):
            ET.SubElement(sheets_elem, "sheet", name=sheet_name, sheetId=str(idx), attrib={"{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id": f"rId{idx}"})

            # Build worksheet xml
            ws_elem = ET.Element("worksheet", xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main")
            sheet_data = ET.SubElement(ws_elem, "sheetData")

            for r_idx, row in enumerate(matrix, start=1):
                row_elem = ET.SubElement(sheet_data, "row", r=str(r_idx))
                for c_idx, cell_val in enumerate(row):
                    col_letter = chr(ord('A') + c_idx) if c_idx < 26 else f"A{chr(ord('A') + c_idx - 26)}"
                    cell_ref = f"{col_letter}{r_idx}"
                    c_elem = ET.SubElement(row_elem, "c", r=cell_ref)
                    val_str = str(cell_val)
                    if val_str:
                        s_idx = get_string_idx(val_str)
                        c_elem.set("t", "s")
                        v_elem = ET.SubElement(c_elem, "v")
                        v_elem.text = str(s_idx)

            z.writestr(f"xl/worksheets/sheet{idx}.xml", ET.tostring(ws_elem, encoding="utf-8", xml_declaration=True))

        z.writestr("xl/workbook.xml", ET.tostring(wb_elem, encoding="utf-8", xml_declaration=True))

        # 6. Write sharedStrings.xml
        sst_elem = ET.Element("sst", xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main", count=str(len(shared_strings)), uniqueCount=str(len(shared_strings)))
        for s in shared_strings:
            si_elem = ET.SubElement(sst_elem, "si")
            t_elem = ET.SubElement(si_elem, "t")
            t_elem.text = s
        z.writestr("xl/sharedStrings.xml", ET.tostring(sst_elem, encoding="utf-8", xml_declaration=True))

    buf.seek(0)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# 1. Spec Test: Attendance Muster Report
# ---------------------------------------------------------------------------

def test_attendance_report_spec():
    """
    Given exact header and sample rows from JMU-Sainik_Colony-Attendance-report:
    [store_name, scheduled_date, full_name, employee_code, DOJ, current_role_name, user_status, muster_status]
    Assert correct parsing of date serials, status normalization, and store metadata.
    """
    header = ["store_name", "scheduled_date", "full_name", "employee_code", "DOJ", "current_role_name", "user_status", "muster_status"]
    row_1 = ["JMU-Sainik Colony", "46276", "Ashish Sharma", "10469614", "46000", "PACKER", "ACTIVE", "P"]
    row_2 = ["JMU-Sainik Colony", "46276", "Rohit Kumar", "10469615", "46010", "PICKER", "ACTIVE", "A"]
    row_3 = ["JMU-Sainik Colony", "46276", "Vikas Singh", "10469616", "46020", "SHIFT_INCHARGE", "ACTIVE", "WO"]

    xlsx_bytes = _create_mock_xlsx({"Attendance": [header, row_1, row_2, row_3]})
    result = parse_zepto_attendance_excel(xlsx_bytes, file_name="JMU-Sainik_Colony-Attendance-report-8165178.xlsx")

    assert result["store_name"] == "JMU-Sainik Colony"
    assert result["total_records"] == 3
    assert result["total_employees"] == 3
    assert result["start_date"] == "2026-09-11"  # Excel serial 46276
    assert result["end_date"] == "2026-09-11"

    # Status counts & Attendance Rate
    # Rate = Present / (Present + Absent + HalfDay) = 1 / (1 + 1 + 0) = 50.0%
    assert result["summary"]["present_count"] == 1
    assert result["summary"]["absent_count"] == 1
    assert result["summary"]["week_off_count"] == 1
    assert result["summary"]["attendance_rate_pct"] == 50.0

    # Record Level Assertions
    rec_0 = result["records"][0]
    assert rec_0["employee_id"] == "10469614"
    assert rec_0["employee_name"] == "Ashish Sharma"
    assert rec_0["designation"] == "PACKER"
    assert rec_0["shift_date"] == "2026-09-11"
    assert rec_0["status"] == "PRESENT"
    assert rec_0["user_status"] == "ACTIVE"


# ---------------------------------------------------------------------------
# 2. Spec Test: DQ Loss Report
# ---------------------------------------------------------------------------

def test_dq_loss_report_spec():
    """
    Given exact header and sample rows from JMU-Sainik_Colony-DQ_Loss-report:
    [crtdate, store_name, sku_id, sku_name, category, SubCategory, dq_value, dq]
    Assert correct mapping into zepto_loss_records schema with DQ_LOSS classification.
    """
    header = ["crtdate", "store_name", "sku_id", "sku_name", "category", "SubCategory", "dq_value", "dq"]
    row_1 = ["46282", "JMU-Sainik Colony", "114639", "Epigamia Greek Yogurt Mango 90g", "Dairy", "Yogurt", "160.0", "2"]
    row_2 = ["46282", "JMU-Sainik Colony", "108920", "Fresho Tomato Hybrid 1kg", "Fruits & Vegetables", "Vegetables", "45.5", "1"]

    xlsx_bytes = _create_mock_xlsx({"DQ_Details": [header, row_1, row_2]})
    result = parse_zepto_loss_shrinkage_excel(xlsx_bytes, file_name="JMU-Sainik_Colony-DQ_Loss-report-6061685.xlsx")

    assert result["store_name"] == "JMU-Sainik Colony"
    assert result["total_records"] == 2
    assert result["total_amount"] == 205.5  # 160.0 + 45.5
    assert result["total_units"] == 3       # 2 + 1
    assert result["loss_type"] == "DQ_LOSS"

    rec_0 = result["records"][0]
    assert rec_0["loss_type"] == "DQ_LOSS"
    assert rec_0["sku_id"] == "114639"
    assert rec_0["item_name"] == "Epigamia Greek Yogurt Mango 90g"
    assert rec_0["category"] == "DAIRY"
    assert rec_0["amount"] == 160.0
    assert rec_0["sku_count"] == 2
    assert rec_0["record_date"] == "2026-09-17"  # Excel serial 46282


# ---------------------------------------------------------------------------
# 3. Spec Test: Shrinkage Report (Inhouse DOD + MTD Summary)
# ---------------------------------------------------------------------------

def test_shrinkage_report_spec():
    """
    Given exact header and sample rows from JMU-Sainik_Colony-Shrinkage-report:
    Multi-sheet workbook containing Inhouse_DOD (21 cols) and MTD_Summary (32 cols).
    Assert correct extraction of inhouse net damage, RTO loss, short pick, and FCC amounts.
    """
    inhouse_dod_header = [
        "date", "store_name", "city", "sku_name", "rto", "adjustment", "fcc",
        "short_pick", "others", "inhouse_net", "rto_amount", "adjustment_amount",
        "fcc_amount", "short_pick_amount", "others_amount", "inhouse_net_amount",
        "sku_id", "category", "sub_category", "level_3_category", "_____dp_update_ts"
    ]
    row_1 = [
        "46282", "JMU-Sainik Colony", "Jammu", "Amul Salted Butter 500g", "0", "0", "0",
        "1", "0", "1", "0.0", "0.0",
        "0.0", "275.0", "0.0", "275.0",
        "100234", "Dairy", "Butter", "Salted Butter", "2026-09-17T04:00:00"
    ]
    row_2 = [
        "46282", "JMU-Sainik Colony", "Jammu", "Tata Salt 1kg", "2", "0", "0",
        "0", "0", "2", "56.0", "0.0",
        "0.0", "0.0", "0.0", "56.0",
        "100555", "Staples", "Salt & Sugar", "Iodized Salt", "2026-09-17T04:00:00"
    ]

    xlsx_bytes = _create_mock_xlsx({"Inhouse_DOD": [inhouse_dod_header, row_1, row_2]})
    result = parse_zepto_loss_shrinkage_excel(xlsx_bytes, file_name="JMU-Sainik_Colony-Shrinkage-report-1053281.xlsx")

    assert result["store_name"] == "JMU-Sainik Colony"
    assert result["total_records"] == 2
    assert result["total_amount"] == 331.0  # 275.0 + 56.0
    assert result["total_units"] == 3       # 1 + 2
    assert result["loss_type"] == "SHRINKAGE"

    rec_0 = result["records"][0]
    assert rec_0["sku_id"] == "100234"
    assert rec_0["item_name"] == "Amul Salted Butter 500g"
    assert rec_0["category"] == "DAIRY"
    assert rec_0["amount"] == 275.0
    assert rec_0["sku_count"] == 1
    assert rec_0["record_date"] == "2026-09-17"


def test_negative_shrinkage_and_surplus_reconciliation_spec():
    """
    Verify that negative shrinkage values (inventory cycle count surpluses, stock found reconciliations,
    accounting formatted negative numbers '(275.0)' or '-275.0') are correctly extracted and aggregated as net shrinkage.
    """
    inhouse_dod_header = [
        "date", "store_name", "city", "sku_name", "rto", "adjustment", "fcc",
        "short_pick", "others", "inhouse_net", "rto_amount", "adjustment_amount",
        "fcc_amount", "short_pick_amount", "others_amount", "inhouse_net_amount",
        "sku_id", "category", "sub_category", "level_3_category", "_____dp_update_ts"
    ]
    # Row 1: Loss of 500.0
    row_loss = [
        "46282", "JMU-Sainik Colony", "Jammu", "Cadbury Dairy Milk 150g", "0", "0", "0",
        "2", "0", "2", "0.0", "0.0",
        "0.0", "500.0", "0.0", "500.0",
        "100999", "Chocolates", "Bars", "Milk Chocolate", "2026-09-17T04:00:00"
    ]
    # Row 2: Negative shrinkage (Surplus stock found: adjustment_amount = -200.0, inhouse_net_amount = -200.0)
    row_surplus = [
        "46282", "JMU-Sainik Colony", "Jammu", "Amul Salted Butter 500g", "0", "-1", "0",
        "0", "0", "-1", "0.0", "-200.0",
        "0.0", "0.0", "0.0", "-200.0",
        "100234", "Dairy", "Butter", "Salted Butter", "2026-09-17T04:00:00"
    ]
    # Row 3: Accounting parentheses formatted negative amount e.g. "(100.0)"
    row_paren_surplus = [
        "46282", "JMU-Sainik Colony", "Jammu", "Fortune Oil 1L", "0", "-1", "0",
        "0", "0", "-1", "0.0", "(100.0)",
        "0.0", "0.0", "0.0", "(100.0)",
        "100333", "Staples", "Edible Oil", "Mustard Oil", "2026-09-17T04:00:00"
    ]

    xlsx_bytes = _create_mock_xlsx({"Inhouse_DOD": [inhouse_dod_header, row_loss, row_surplus, row_paren_surplus]})
    result = parse_zepto_loss_shrinkage_excel(xlsx_bytes, file_name="JMU-Sainik_Colony-Shrinkage-report.xlsx")

    assert result["total_records"] == 3
    # Net shrinkage: 500.0 + (-200.0) + (-100.0) = 200.0
    assert result["total_amount"] == 200.0
    assert result["records"][1]["amount"] == -200.0
    assert result["records"][1]["sku_count"] == -1
    assert result["records"][2]["amount"] == -100.0

    # Test DAL save and get_loss_summary integration
    settings = Settings()
    save_res = save_loss_records_batch(result["records"], settings=settings)
    assert save_res == 3

    summary = get_loss_summary(month="2026-09", store_name="JMU-Sainik Colony", settings=settings)
    assert any(c["category"] == "DAIRY" and c["shrinkage_amount"] < 0 for c in summary["category_breakdown"])



# ---------------------------------------------------------------------------
# 4. Spec Test: Store Metric Summary & Manpower Utilization (Packer_Thor_Raw)
# ---------------------------------------------------------------------------

def test_store_metric_summary_and_manpower_spec():
    """
    Given exact header and sample row from JMU-Sainik_Colony-Store Metric Summary D-1 & MTD-report:
    Multi-sheet workbook containing Packer_Thor_Raw (44 columns).
    Assert:
    - Extraction of granular worker utilization records for zepto_manpower_utilization.
    - Store-level rollup aggregation for zepto_store_metrics (Total Inbound/Outbound hours, Average IPP).
    """
    packer_thor_header = [
        "Scheduled_date", "Packer_id", "Employee_id", "Employee_code", "Emp_Name",
        "Employee_doj", "Emplyoee_role", "Store_id", "Store_name", "Store_city",
        "Attendence_status", "Packman_punch_in_time", "Thor_punch_in_time",
        "Packman_punch_out_time", "Packman_work_hour", "Thor_work_hour", "IB_work_hour",
        "IB_inventory_work_hour", "IB_return_work_hour", "IB_other_work_hour", "OB_hour",
        "Break_hour", "Idle_hour", "Day_ob_order_handled", "Day_ob_order_packed_qty",
        "Day_ob_packed_time", "Day_ob_ipp", "Day_ib_packed_qty", "Day_ib_packed_time",
        "Day_ib_ipp", "Day_task_completed", "Day_task_assigned", "Day_task_adherence",
        "MTD_orders_handled", "MTD_packed_qty", "MTD_packed_time", "MTD_OB_IPP",
        "MTD_ib_packed_qty", "MTD_ib_packed_time", "MTD_IB_IPP", "MTD_task_completed",
        "MTD_task_assigned", "MTD_task_adherence", "_____dp_update_ts"
    ]
    row_1 = [
        "46282", "P101", "EMP001", "10469614", "Ashish Sharma",
        "46000", "PACKER", "c7c7f1a0-1234-5678-9abc-def012345678", "JMU-Sainik Colony", "Jammu",
        "P", "06:00:00", "06:02:00",
        "14:30:00", "8.5", "8.3", "1.5",
        "1.0", "0.5", "0.0", "6.5",
        "0.5", "0.3", "45", "180",
        "5.0", "36.0", "20", "1.0",
        "20.0", "40", "42", "95.2%",
        "500", "2100", "60.0", "35.0",
        "250", "15.0", "16.7", "480",
        "500", "96.0%", "2026-09-17T04:00:00"
    ]
    row_2 = [
        "46282", "P102", "EMP002", "10469615", "Rohit Kumar",
        "46010", "PACKER", "c7c7f1a0-1234-5678-9abc-def012345678", "JMU-Sainik Colony", "Jammu",
        "P", "14:00:00", "14:05:00",
        "22:30:00", "8.5", "8.2", "2.0",
        "1.5", "0.5", "0.0", "6.0",
        "0.5", "0.2", "55", "220",
        "5.5", "40.0", "15", "0.8",
        "18.75", "50", "50", "100.0%",
        "600", "2500", "70.0", "35.7",
        "300", "18.0", "16.7", "580",
        "600", "96.7%", "2026-09-17T04:00:00"
    ]

    xlsx_bytes = _create_mock_xlsx({"Packer_Thor_Raw": [packer_thor_header, row_1, row_2]})
    result = parse_zepto_store_metrics_excel(xlsx_bytes, file_name="JMU-Sainik_Colony-Store Metric Summary D-1 & MTD-report.xlsx")

    # Store Metadata
    assert result["store_name"] == "JMU-Sainik Colony"
    assert result["total_records"] == 1
    assert result["total_worker_records"] == 2

    # Store Aggregate Rollup
    metrics = result["records"][0]
    assert metrics["metric_date"] == "2026-09-17"
    assert metrics["inbound_hours"] == 3.5    # 1.5 + 2.0
    assert metrics["outbound_hours"] == 12.5  # 6.5 + 6.0
    assert metrics["order_count"] == 100      # 45 + 55
    assert metrics["packer_ipp"] == 38.0      # Average of 36.0 and 40.0

    # Worker Utilization Records
    util_records = result["worker_records"]
    assert len(util_records) == 2

    worker_1 = util_records[0]
    assert worker_1["employee_id"] == "10469614"
    assert worker_1["employee_name"] == "Ashish Sharma"
    assert worker_1["role"] == "PACKER"
    assert worker_1["punch_in"] == "06:00:00"
    assert worker_1["punch_out"] == "14:30:00"
    assert worker_1["thor_work_hours"] == 8.3
    assert worker_1["ob_work_hours"] == 6.5
    assert worker_1["ib_work_hours"] == 1.5
    assert worker_1["idle_hours"] == 0.3
    assert worker_1["day_orders_handled"] == 45
    assert worker_1["items_picked"] == 180
    assert worker_1["ipp"] == 36.0
    assert worker_1["adherence_pct"] == 95.2


# ---------------------------------------------------------------------------
# 5. End-to-End DAL Batch Ingestion & Dashboard Reconciliation
# ---------------------------------------------------------------------------

def test_e2e_dal_batch_ingestion_and_analytics():
    """
    Verify that parsed entities from all 4 reports can be stored into SQLite via batch DAL
    helpers and queried through get_zepto_dashboard_analytics.
    """
    settings = Settings()

    # 1. Ingest Attendance
    att_header = ["store_name", "scheduled_date", "full_name", "employee_code", "DOJ", "current_role_name", "user_status", "muster_status"]
    att_row = ["JMU-Sainik Colony", "2026-09-17", "Ashish Sharma", "10469614", "2026-01-01", "PACKER", "ACTIVE", "P"]
    att_parsed = parse_zepto_attendance_excel(
        _create_mock_xlsx({"Attendance": [att_header, att_row]}),
        file_name="JMU-Sainik_Colony-Attendance-report.xlsx"
    )
    save_res = save_attendance_batch(att_parsed, source="TEST_FIXTURE", settings=settings)
    assert save_res["status"] == "success"

    # 2. Ingest Loss Records
    loss_header = ["crtdate", "store_name", "sku_id", "sku_name", "category", "SubCategory", "dq_value", "dq"]
    loss_row = ["2026-09-17", "JMU-Sainik Colony", "114639", "Epigamia Greek Yogurt", "Dairy", "Yogurt", "160.0", "2"]
    loss_parsed = parse_zepto_loss_shrinkage_excel(_create_mock_xlsx({"DQ_Details": [loss_header, loss_row]}))
    saved_loss_cnt = save_loss_records_batch(loss_parsed["records"], settings=settings)
    assert saved_loss_cnt == 1

    # 3. Ingest Manpower Utilization (with punch times for cross-table sync)
    worker_rec = [{
        "store_name": "JMU-Sainik Colony",
        "util_date": "2026-09-17",
        "employee_id": "10469614",
        "employee_name": "Ashish Sharma",
        "role": "PACKER",
        "punch_in": "06:00:00",
        "punch_out": "14:30:00",
        "thor_work_hours": 8.5,
        "items_picked": 180,
        "active_pick_hours": 6.5,
        "idle_hours": 0.3,
        "ipp": 27.7,
        "flex_labor_cost": 0.0,
    }]
    saved_manpower_cnt = save_manpower_utilization_batch(worker_rec, settings=settings)
    assert saved_manpower_cnt == 1

    # Verify cross-table attendance enrichment
    records = get_attendance_records(store_name="JMU-Sainik Colony", employee_id="10469614", year_month="2026-09", settings=settings)
    assert len(records) >= 1
    matched_att = next(r for r in records if r["employee_id"] == "10469614" and r["shift_date"] == "2026-09-17")
    assert matched_att["punch_in"] == "06:00:00"
    assert matched_att["punch_out"] == "14:30:00"
    assert matched_att["work_duration_mins"] == 510

    # 4. Verify Unified Analytics
    analytics = get_zepto_dashboard_analytics(month="2026-09", store_name="JMU-Sainik Colony", settings=settings)
    assert "mom_trends" in analytics
    assert "dod_metrics" in analytics
    assert len(analytics["mom_trends"]) > 0
