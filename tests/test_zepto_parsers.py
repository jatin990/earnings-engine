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

