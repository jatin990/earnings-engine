"""
Unit tests for Zepto Dark Store Operational Parsers & Email Metrics Extraction Engine.
Tests store metric Excel parsing, DQ loss / shrinkage Excel parsing, and email body heuristics.
"""

import pytest
from earnings_engine.data.zepto_parsers import (
    extract_metrics_from_email_body,
    parse_zepto_store_metrics_excel,
    parse_zepto_loss_shrinkage_excel,
    match_zepto_subject_pattern,
    build_targeted_gmail_query,
)


def test_match_zepto_subject_pattern_dq_loss():
    subject = "Store JMU-Sainik Colony - Daily Shift Summary & DQ Loss Audit - 2026-09-15"
    match = match_zepto_subject_pattern(subject)

    assert match["is_pattern_matched"] is True
    assert match["category"] == "DQ_LOSS"
    assert match["store_name"] == "JMU-Sainik Colony"
    assert match["record_date"] == "2026-09-15"
    assert match["badge_color"] == "rose"


def test_match_zepto_subject_pattern_attendance():
    subject = "JMU-Sainik_Colony-Attendance-report-8165178"
    match = match_zepto_subject_pattern(subject)

    assert match["is_pattern_matched"] is True
    assert match["category"] == "ATTENDANCE"
    assert match["store_name"] == "JMU-Sainik Colony"
    assert match["report_id"] == "8165178"
    assert match["badge_color"] == "sky"


def test_match_zepto_subject_pattern_store_metrics():
    subject = "Store DEL-South Ex - Daily Store Metrics Summary - 2026-08-20"
    match = match_zepto_subject_pattern(subject)

    assert match["is_pattern_matched"] is True
    assert match["category"] == "STORE_METRICS"
    assert match["store_name"] == "DEL-South Ex"
    assert match["record_date"] == "2026-08-20"
    assert match["badge_color"] == "emerald"


def test_build_targeted_gmail_query():
    clean_m, query_month = build_targeted_gmail_query("2026-09")
    assert clean_m == "2026-09"
    assert "after:2026/09/01" in query_month
    assert "before:2026/10/01" in query_month
    assert 'subject:(' in query_month
    assert '"DQ Loss"' in query_month
    assert '"Attendance-report"' in query_month

    clean_all, query_all = build_targeted_gmail_query("ALL")
    assert clean_all == "ALL"
    assert "after:" not in query_all
    assert 'subject:(' in query_all


def test_extract_metrics_from_email_body_sales_and_orders():
    text = "Store JMU-Sainik Colony Daily Update: GMV: ₹4,52,000 across 1,250 orders. AOV: ₹361.60 with 10-min SLA: 98.4%."
    metrics = extract_metrics_from_email_body(text)

    assert metrics.get("sales_gmv") == 452000.0
    assert metrics.get("order_count") == 1250
    assert metrics.get("aov") == 361.6
    assert metrics.get("sla_adherence_pct") == 98.4


def test_extract_metrics_from_email_body_lakhs_and_ipp():
    text = "End of Shift Summary: Sales of 2.4Lakhs, 850 orders dispatched. Packer IPP: 138.2, DQ Loss: Rs. 1450."
    metrics = extract_metrics_from_email_body(text)

    assert metrics.get("sales_gmv") == 240000.0
    assert metrics.get("order_count") == 850
    assert metrics.get("packer_ipp") == 138.2
    assert metrics.get("loss_amount") == 1450.0


def test_extract_metrics_from_email_body_cr_and_damages():
    text = "Monthly Hub Rollup: Revenue: 1.2Cr, Orders: 34500, Damage: ₹24,000, SLA: 99.1%"
    metrics = extract_metrics_from_email_body(text)

    assert metrics.get("sales_gmv") == 12000000.0
    assert metrics.get("order_count") == 34500
    assert metrics.get("loss_amount") == 24000.0
    assert metrics.get("sla_adherence_pct") == 99.1


def test_extract_metrics_empty_text():
    assert extract_metrics_from_email_body("") == {}
    assert extract_metrics_from_email_body(None) == {}


def test_loss_summary_monthly_and_category_matrix_calculations():
    import uuid
    from earnings_engine.config import Settings
    from earnings_engine.data import zepto_db

    settings = Settings()
    test_email_id = f"test_recon_email_{uuid.uuid4().hex[:8]}"

    # 1. Save an audit email with body stated loss = 2500.0
    zepto_db.save_gmail_messages([{
        "id": test_email_id,
        "thread_id": "thread_recon_1",
        "store_name": "JMU-Sainik Colony",
        "subject": "Store JMU-Sainik Colony - Daily Shift Summary & DQ Loss Audit - 2026-09-18",
        "from": "audit@zepto.com",
        "date": "Fri, 18 Sep 2026 18:00:00 +0530",
        "iso_date": "2026-09-18",
        "month_ym": "2026-09",
        "snippet": "DQ Loss: ₹2,500 across departments.",
        "category": "DQ_LOSS",
        "category_label": "DQ Loss & Expiry",
        "badge_color": "rose",
        "icon": "⚠️",
        "extracted_metrics": {"loss_amount": 2500.0},
        "attachments": [{"filename": "loss_audit_20260918.xlsx", "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "size_bytes": 2048}],
        "has_attachments": True,
        "parsed_status": "PARSED",
        "parsed_records_count": 2,
    }], settings=settings)

    # 2. Save itemized Excel rows linking to this email (Total sum = 1500 + 1000 = 2500 => MATCHED)
    zepto_db.save_loss_record({
        "id": f"rec_{uuid.uuid4().hex[:8]}",
        "store_name": "JMU-Sainik Colony",
        "record_date": "2026-09-18",
        "loss_type": "DQ_LOSS",
        "category": "FRUITS_VEG",
        "amount": 1500.0,
        "sku_count": 5,
        "notes": "Damaged tomatoes",
        "source_email_id": test_email_id,
    }, settings=settings)

    zepto_db.save_loss_record({
        "id": f"rec_{uuid.uuid4().hex[:8]}",
        "store_name": "JMU-Sainik Colony",
        "record_date": "2026-09-18",
        "loss_type": "SHRINKAGE",
        "category": "FRUITS_VEG",
        "amount": 1000.0,
        "sku_count": 2,
        "notes": "Apples cycle count variance",
        "source_email_id": test_email_id,
    }, settings=settings)

    # 3. Query loss summary for 2026-09
    summary = zepto_db.get_loss_summary(month="2026-09", settings=settings)

    assert "2026-09" in summary["available_months"]
    assert summary["total_loss_amount"] >= 2500.0
    assert summary["dq_loss_total"] >= 1500.0
    assert summary["shrinkage_total"] >= 1000.0

    # Verify category matrix contains FRUITS_VEG with both DQ Loss and Shrinkage
    fv_cat = next((c for c in summary["category_breakdown"] if c["category"] == "FRUITS_VEG"), None)
    assert fv_cat is not None
    assert fv_cat["total_amount"] >= 2500.0
    assert fv_cat["dq_loss_amount"] >= 1500.0
    assert fv_cat["shrinkage_amount"] >= 1000.0
    assert fv_cat["total_amount"] == round(fv_cat["dq_loss_amount"] + fv_cat["shrinkage_amount"] + fv_cat["spoilage_amount"], 2)

    # Verify email reconciliation matched status
    recon = summary["reconciliation"]
    recon_item = next((it for it in recon["items"] if it["email_id"] == test_email_id), None)
    assert recon_item is not None
    assert recon_item["email_stated_amount"] == 2500.0
    assert recon_item["excel_parsed_sum"] == 2500.0
    assert recon_item["variance"] == 0.0
    assert recon_item["status"] == "MATCHED"

    # Verify daily and monthly trends are computed
    assert "daily_trends" in summary
    assert "monthly_trends" in summary
    assert len(summary["daily_trends"]) >= 1
    assert any(d["date"] == "2026-09-18" for d in summary["daily_trends"])

    # Verify categories only contain positive losses and top-10 + Others logic
    assert all(c["total_amount"] > 0 for c in summary["category_breakdown"])
    assert len(summary["category_breakdown"]) <= 11  # At most 10 top categories + 1 OTHERS composite
    if len(summary["all_categories"]) > 10:
        assert any(c["category"] == "OTHERS" for c in summary["category_breakdown"])


def test_save_loss_record_idempotency_and_sku_deduplication():
    import uuid
    from earnings_engine.config import Settings
    from earnings_engine.data import zepto_db

    settings = Settings()
    test_store = f"TEST_STORE_{uuid.uuid4().hex[:8]}"
    test_email_1 = f"email_shift1_{uuid.uuid4().hex[:8]}"
    test_email_2 = f"email_shift2_{uuid.uuid4().hex[:8]}"
    test_date = "2026-09-22"

    # 1. Shift 1 incremental email: reports SKU_101 (Amul Butter, 3 units, Rs. 600) and SKU_102 (Tomato, 5 units, Rs. 250)
    zepto_db.save_loss_record({
        "store_name": test_store,
        "record_date": test_date,
        "loss_type": "DQ_LOSS",
        "category": "DAIRY",
        "sku_id": "SKU_101",
        "item_name": "Amul Butter 500g",
        "amount": 600.0,
        "sku_count": 3,
        "notes": "Packaging puncture",
        "source_email_id": test_email_1,
    }, settings=settings)

    zepto_db.save_loss_record({
        "store_name": test_store,
        "record_date": test_date,
        "loss_type": "DQ_LOSS",
        "category": "FRUITS_VEG",
        "sku_id": "SKU_102",
        "item_name": "Tomato Hybrid 1kg",
        "amount": 250.0,
        "sku_count": 5,
        "notes": "Crushed during pick",
        "source_email_id": test_email_1,
    }, settings=settings)

    # 2. Re-ingesting shift 1 (e.g. duplicate webhook / re-sync) should NOT duplicate records due to deterministic hashing
    zepto_db.save_loss_record({
        "store_name": test_store,
        "record_date": test_date,
        "loss_type": "DQ_LOSS",
        "category": "DAIRY",
        "sku_id": "SKU_101",
        "item_name": "Amul Butter 500g",
        "amount": 600.0,
        "sku_count": 3,
        "notes": "Packaging puncture",
        "source_email_id": test_email_1,
    }, settings=settings)

    # 3. Shift 2 incremental email: reports SKU_101 again in a separate incremental incident (2 more units, Rs. 400) and net-new SKU_103 (Bread, 1 unit, Rs. 50)
    zepto_db.save_loss_record({
        "store_name": test_store,
        "record_date": test_date,
        "loss_type": "DQ_LOSS",
        "category": "DAIRY",
        "sku_id": "SKU_101",
        "item_name": "Amul Butter 500g",
        "amount": 400.0,
        "sku_count": 2,
        "notes": "Shift 2 drop damage",
        "source_email_id": test_email_2,
    }, settings=settings)

    zepto_db.save_loss_record({
        "store_name": test_store,
        "record_date": test_date,
        "loss_type": "SHRINKAGE",
        "category": "FMCG_PACKAGED",
        "sku_id": "SKU_103",
        "item_name": "Brown Bread 400g",
        "amount": 50.0,
        "sku_count": 1,
        "notes": "Cycle count missing",
        "source_email_id": test_email_2,
    }, settings=settings)

    # 4. Fetch summary for the isolated test store
    summary = zepto_db.get_loss_summary(store_name=test_store, start_date=test_date, end_date=test_date, settings=settings)

    # Total financial loss: 600 + 250 + 400 + 50 = 1300.0
    assert summary["total_loss_amount"] == 1300.0
    assert summary["dq_loss_total"] == 1250.0   # 600 + 250 + 400
    assert summary["shrinkage_total"] == 50.0   # 50

    # Total physical defect units: 3 + 5 + 2 + 1 = 11 units
    assert summary["total_units_affected"] == 11

    # Unique distinct SKUs affected: SKU_101, SKU_102, SKU_103 = EXACTLY 3 unique SKUs!
    # SKU_101 was affected in two incremental shift logs, but represents only 1 unique SKU!
    assert summary["unique_skus_count"] == 3
    assert summary["total_skus_affected"] == 3

    # Category Breakdown Verification
    dairy_cat = next((c for c in summary["category_breakdown"] if c["category"] == "DAIRY"), None)
    assert dairy_cat is not None
    assert dairy_cat["total_amount"] == 1000.0  # 600 + 400
    assert dairy_cat["total_units"] == 5        # 3 + 2 units
    assert dairy_cat["distinct_skus"] == 1      # Only SKU_101 in DAIRY
    assert dairy_cat["incident_count"] == 2     # 2 separate shift incidents


def test_normalize_store_name():
    from earnings_engine.data.zepto_parsers import normalize_store_name

    assert normalize_store_name("32010130-3ad5-40a0-b614-9522956474ba") == "JMU-Sainik Colony"
    assert normalize_store_name("JMU - Sainik") == "JMU-Sainik Colony"
    assert normalize_store_name("JMU-Sainik") == "JMU-Sainik Colony"
    assert normalize_store_name("JMU-Sainik Colony") == "JMU-Sainik Colony"
    assert normalize_store_name("DL-Saket") == "DL-Saket"


def test_parse_zepto_manpower_utilization_html():
    from earnings_engine.data.zepto_parsers import parse_zepto_manpower_utilization_html

    sample_html = """
    <html>
    <body>
        <h2>Manpower Utilization Scorecard - 2026-03-15</h2>
        <table border="1">
            <tr>
                <th>Store</th>
                <th>Packer HC</th>
                <th>SI</th>
                <th>Security</th>
                <th>Housekeeping</th>
                <th>Flex HC</th>
                <th>Flex Deductions</th>
                <th>D-1 IPP</th>
                <th>MTD IPP</th>
            </tr>
            <tr>
                <td>JMU-Sainik Colony</td>
                <td>9</td>
                <td>3</td>
                <td>2</td>
                <td>1</td>
                <td>2</td>
                <td>500.0</td>
                <td>142.5</td>
                <td>138.2</td>
            </tr>
        </table>
    </body>
    </html>
    """
    res = parse_zepto_manpower_utilization_html(sample_html, subject="Manpower Report 2026-03-15")
    assert res is not None
    assert res["store_name"] == "JMU-Sainik Colony"
    assert res["date"] == "2026-03-15"
    assert res["packer_headcount"] == 9
    assert res["shift_incharge_count"] == 3
    assert res["security_count"] == 2
    assert res["housekeeping_count"] == 1
    assert res["flex_headcount"] == 2
    assert res["flex_deductions"] == 500.0
    assert res["d1_ipp"] == 142.5
    assert res["mtd_ipp"] == 138.2


def test_safe_b64decode_padding():
    from earnings_engine.api.routers.zepto import _safe_b64decode
    import base64

    original_text = "Hello Zepto Dark Hub IPP Scanner!"
    # Produce unpadded base64url string
    encoded = base64.urlsafe_b64encode(original_text.encode('utf-8')).decode('utf-8').rstrip('=')

    decoded_bytes = _safe_b64decode(encoded)
    assert decoded_bytes.decode('utf-8') == original_text



