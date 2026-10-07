"""Tests for Zepto Dark Store Management Hub."""

from __future__ import annotations

import io
import uuid
import pytest
from fastapi.testclient import TestClient

from earnings_engine.api.server import app
from earnings_engine.config import Settings
from earnings_engine.data import zepto_db
from earnings_engine.data.auth import create_session_token


@pytest.fixture
def client():
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


def test_ensure_schema_and_overview():
    settings = Settings()
    zepto_db.ensure_zepto_schema(settings)
    overview = zepto_db.get_zepto_overview(settings)

    assert "headcount" in overview
    assert "expenses" in overview
    assert "security_capital" in overview
    assert "config" in overview
    assert overview["config"]["partners"]["partner_1"]["name"] == "Jatin Abrol"
    assert overview["config"]["partners"]["partner_2"]["name"] == "Harshiv Bargotra"
    assert overview["headcount"]["active"] >= 0
    assert overview["security_capital"]["target_total"] == 7500000.0
    assert overview["security_capital"]["target_per_partner"] == 3750000.0


def test_employee_crud_and_bonus():
    settings = Settings()
    # Create employee
    emp_data = {
        "name": "Karan Johar",
        "role": "PICKER",
        "phone": "+91 91234 56789",
        "email": "karan.j@darkstore.in",
        "base_salary_monthly": 19000.0,
        "rating": 4.9,
        "status": "ACTIVE",
    }
    emp = zepto_db.create_employee(emp_data, settings)
    assert emp["id"] is not None
    assert emp["name"] == "Karan Johar"
    assert emp["base_salary_monthly"] == 19000.0

    # Add bonus
    updated_emp = zepto_db.add_employee_bonus(emp["id"], 2500.0, notes="Top performance", settings=settings)
    assert updated_emp["current_month_bonus"] >= 2500.0

    # Record MoM salary slip
    sal_data = {
        "year_month": "2026-08",
        "base_amount": 19000.0,
        "bonus_amount": 2500.0,
        "deductions": 0.0,
    }
    sal = zepto_db.record_employee_salary(emp["id"], sal_data, settings)
    assert sal["net_paid"] == 21500.0

    history = zepto_db.get_employee_salaries(emp["id"], settings)
    assert len(history) >= 1
    assert history[0]["net_paid"] == 21500.0

    # Cleanup
    zepto_db.delete_employee(emp["id"], settings)


def test_zepto_hub_renders_gmail_tab(client):
    resp = client.get("/zepto")
    assert resp.status_code == 200
    assert "tabBtn-gmail" in resp.text
    assert "tabContent-gmail" in resp.text
    assert "Store Mailbox Intelligence & Reports Feed" in resp.text
    assert "gmailTableContainer" in resp.text
    assert "gmailEmailsTableBody" in resp.text
    assert "gmailAggregatesDeck" in resp.text
    assert "gmailAggTotalGmv" in resp.text
    assert "gmailTableFooter" in resp.text
    assert "gmailFootMetricsAggregates" in resp.text


def test_classify_zepto_email_categories():
    from earnings_engine.api.routers.zepto import _classify_zepto_email

    # 1. Store Metrics
    c1 = _classify_zepto_email("Store JMU-Sainik Colony - Daily Store Metrics Summary - 2026-09-29", "bot@zepto.com")
    assert c1["category"] == "STORE_METRICS"
    assert c1["badge_color"] == "emerald"
    assert c1["store_name"] == "JMU-Sainik Colony"
    assert c1["record_date"] == "2026-09-29"

    # 2. Attendance
    c2 = _classify_zepto_email("JMU-Sainik_Colony-Attendance-report-8165178", "reports@zepto.com")
    assert c2["category"] == "ATTENDANCE"
    assert c2["badge_color"] == "sky"
    assert c2["store_name"] == "JMU-Sainik Colony"
    assert c2["report_id"] == "8165178"

    # 3. Manpower Utilization
    c3 = _classify_zepto_email("Store JMU-Sainik Colony - Picker IPP - 2026-09-28", "ops@zepto.com")
    assert c3["category"] == "MANPOWER_UTILIZATION"
    assert c3["badge_color"] == "purple"

    # 4. DQ Loss
    c4 = _classify_zepto_email("Store JMU-Sainik Colony - Daily Shift Summary & DQ Loss Audit - 2026-09-27", "audit@zepto.com")
    assert c4["category"] == "DQ_LOSS"
    assert c4["badge_color"] == "rose"
    assert c4["store_name"] == "JMU-Sainik Colony"
    assert c4["record_date"] == "2026-09-27"

    # 5. Shrinkage
    c5 = _classify_zepto_email("Weekly Store Shrinkage & Cycle Count Variance", "audit@zepto.com")
    assert c5["category"] == "SHRINKAGE"
    assert c5["badge_color"] == "amber"

    # 6. Manpower Plan
    c6 = _classify_zepto_email("Monthly Manpower Plan & Target HC Quotas", "hr@zepto.com")
    assert c6["category"] == "MANPOWER_PLAN"
    assert c6["badge_color"] == "indigo"

    # 7. Security Alert
    c7 = _classify_zepto_email("Security alert for linked Google account", "no-reply@accounts.google.com")
    assert c7["category"] == "SECURITY_ALERT"


def test_persisted_emails_local_crud_and_lineage(client):
    settings = Settings()
    # Save a test email with full body and metadata
    test_msg_id = f"test_msg_{uuid.uuid4().hex[:8]}"
    email_entry = {
        "id": test_msg_id,
        "thread_id": "thread_123",
        "store_name": "JMU-Sainik Colony",
        "subject": "Store JMU-Sainik Colony - Daily Shift Summary & DQ Loss Audit - 2026-09-15",
        "from": "audit@zepto.com",
        "date": "Tue, 15 Sep 2026 18:30:00 +0530",
        "iso_date": "2026-07-15",
        "month_ym": "2026-07",
        "internal_date": "9999999999999",
        "snippet": "DQ Loss recorded: Rs 1450 for damaged dairy items.",
        "body_text": "DQ Loss recorded: Rs 1450 for damaged dairy items. Total SKU Count: 3.",
        "body_html": "<p>DQ Loss recorded: Rs 1450 for damaged dairy items.</p>",
        "category": "DQ_LOSS",
        "category_label": "DQ Loss & Expiry",
        "badge_color": "rose",
        "icon": "⚠️",
        "extracted_metrics": {"loss_amount": 1450.0},
        "attachments": [{"filename": "loss_audit_20260915.xlsx", "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "size_bytes": 1024}],
        "has_attachments": True,
        "parsed_status": "PARSED",
        "parsed_records_count": 1,
    }
    zepto_db.save_gmail_messages([email_entry], settings=settings)

    # Persist a linked loss record with source_email_id
    loss_rec = {
        "id": f"loss_{test_msg_id}",
        "store_name": "JMU-Sainik Colony",
        "record_date": "2026-09-15",
        "loss_type": "DQ_LOSS",
        "category": "DAIRY",
        "amount": 1450.0,
        "sku_count": 3,
        "notes": "Damaged milk pouches on dispatch conveyor",
        "source_email_id": test_msg_id,
    }
    zepto_db.save_loss_record(loss_rec, settings=settings)

    # Query single email via DAL
    saved = zepto_db.get_saved_gmail_message_by_id(test_msg_id, settings=settings)
    assert saved is not None
    assert saved["id"] == test_msg_id
    assert saved["store_name"] == "JMU-Sainik Colony"
    assert saved["parsed_status"] == "PARSED"
    assert len(saved["linked_loss_records"]) == 1
    assert saved["linked_loss_records"][0]["amount"] == 1450.0

    # Query via REST API
    res = client.get(f"/api/v1/zepto/gmail/emails?month=2026-07&category=DQ_LOSS")
    assert res.status_code == 200
    res_data = res.json()
    assert res_data["success"] is True
    assert any(e["id"] == test_msg_id for e in res_data["emails"])

    # Query detail endpoint
    res_detail = client.get(f"/api/v1/zepto/gmail/emails/{test_msg_id}")
    assert res_detail.status_code == 200
    detail_data = res_detail.json()
    assert detail_data["email"]["id"] == test_msg_id
    assert len(detail_data["email"]["linked_loss_records"]) >= 1



def test_zepto_hub_renders_attendance_tab(client):
    resp = client.get("/zepto")
    assert resp.status_code == 200
    assert "tabBtn-attendance" in resp.text
    assert "tabContent-attendance" in resp.text
    assert "Daily punch muster, shift adherence, and absenteeism intelligence" in resp.text
    assert "attActiveScopeBadge" in resp.text
    assert "attTableBody" in resp.text



def test_store_expenses_and_spend_per_employee():
    settings = Settings()
    # 1. Claimable expense (Pending)
    exp_data = {
        "title": "Aisle B Barcode Scanners (x4)",
        "category": "EQUIPMENT",
        "amount": 22000.0,
        "incurred_by": "Jatin Abrol",
        "reimbursement_option": "PENDING",
        "notes": "Handheld Zebra scanners (Pending Reimbursement)",
    }
    exp = zepto_db.create_expense(exp_data, settings)
    assert exp["id"] is not None
    assert exp["is_reimbursable"] == 1
    assert exp["is_reimbursed"] == 0

    # 2. Non-claimable direct spend (reimbursement_option = NONE)
    direct_exp_data = {
        "title": "Store Interior Paint",
        "category": "STORE_MAINTENANCE",
        "amount": 8000.0,
        "incurred_by": "Jatin Abrol",
        "reimbursement_option": "NONE",
        "notes": "Direct non-claimable renovation expense",
    }
    direct_exp = zepto_db.create_expense(direct_exp_data, settings)
    assert direct_exp["is_reimbursable"] == 0

    # Filter by category and reimbursement status
    pending_expenses = zepto_db.get_expenses(category="EQUIPMENT", reimbursement_status="PENDING", settings=settings)
    assert any(e["id"] == exp["id"] for e in pending_expenses)
    assert not any(e["id"] == direct_exp["id"] for e in pending_expenses)

    # Filter by NOT_CLAIMABLE
    non_claimable_expenses = zepto_db.get_expenses(reimbursement_status="NOT_CLAIMABLE", settings=settings)
    assert any(e["id"] == direct_exp["id"] for e in non_claimable_expenses)

    # Toggle claimable expense reimbursement to settled
    toggled = zepto_db.toggle_expense_reimbursement(exp["id"], is_reimbursed=1, settings=settings)
    assert toggled["is_reimbursed"] == 1

    reimbursed_expenses = zepto_db.get_expenses(reimbursement_status="REIMBURSED", settings=settings)
    assert any(e["id"] == exp["id"] for e in reimbursed_expenses)

    overview = zepto_db.get_zepto_overview(settings)
    assert overview["expenses"]["spend_per_employee"] > 0
    assert "pending_reimbursement" in overview["expenses"]
    assert "reimbursed_expenses" in overview["expenses"]
    assert "non_reimbursable_expenses" in overview["expenses"]


def test_candidate_hiring_and_one_click_conversion():
    settings = Settings()
    cand_data = {
        "name": "Sneha Gupta",
        "phone": "+91 99887 76655",
        "email": "sneha.g@gmail.com",
        "target_role": "SHIFT_INCHARGE",
        "expected_salary": 32000.0,
        "stage": "SHORTLISTED",
        "rating": 4.8,
        "notes": "Experienced shift lead from Swiggy Instamart",
    }
    cand = zepto_db.create_candidate(cand_data, settings)
    assert cand["id"] is not None

    # One-click conversion to employee
    res = zepto_db.convert_candidate_to_employee(cand["id"], joining_date="2026-09-01", base_salary=32000.0, settings=settings)
    assert res["success"] is True
    assert res["employee_id"] is not None

    # Verify candidate is now HIRED
    cands = zepto_db.get_candidates(stage="HIRED", settings=settings)
    assert any(c["id"] == cand["id"] for c in cands)

    # Verify employee exists
    new_emp = zepto_db.get_employee_by_id(res["employee_id"], settings)
    assert new_emp is not None
    assert new_emp["name"] == "Sneha Gupta"
    assert new_emp["role"] == "SHIFT_INCHARGE"
    assert new_emp["status"] == "ACTIVE"

    # Cleanup
    zepto_db.delete_employee(res["employee_id"], settings)
    zepto_db.delete_candidate(cand["id"], settings)


def test_zepto_security_and_50_50_equity_split():
    settings = Settings()
    tranche_data = {
        "tranche_title": "Capex Deposit Tranche",
        "amount": 500000.0,
        "payment_date": "2026-08-25",
        "partner_name": "Jatin Abrol",
        "payment_mode": "NEFT_RTGS",
        "reference_utr": "HDFC9988776655",
    }
    tranche = zepto_db.create_security_tranche(tranche_data, settings)
    assert tranche["id"] is not None

    # Retrieve single tranche
    single = zepto_db.get_security_tranche_by_id(tranche["id"], settings)
    assert single is not None
    assert single["amount"] == 500000.0

    # Update tranche
    updated = zepto_db.update_security_tranche(
        tranche["id"],
        {
            "tranche_title": "Capex Deposit Tranche (Revised)",
            "amount": 550000.0,
            "reference_utr": "HDFC9988776655_REV",
            "proof_doc_url": "/api/v1/zepto/documents/mock_slip.pdf",
        },
        settings
    )
    assert updated["amount"] == 550000.0
    assert updated["reference_utr"] == "HDFC9988776655_REV"
    assert updated["proof_doc_url"] == "/api/v1/zepto/documents/mock_slip.pdf"

    # Ad-hoc patch proof
    patched = zepto_db.update_security_proof(
        tranche["id"],
        proof_doc_url="/api/v1/zepto/documents/new_slip.pdf",
        reference_utr="HDFC_NEW_UTR",
        settings=settings
    )
    assert patched["proof_doc_url"] == "/api/v1/zepto/documents/new_slip.pdf"
    assert patched["reference_utr"] == "HDFC_NEW_UTR"

    overview = zepto_db.get_zepto_overview(settings)
    sec = overview["security_capital"]
    assert sec["target_total"] == 7500000.0
    assert sec["target_per_partner"] == 3750000.0
    assert sec["partner_1"]["paid"] >= 550000.0
    assert "equalization" in sec

    # Cleanup
    zepto_db.delete_security_tranche(tranche["id"], settings)


def test_zepto_api_endpoints(client):
    # 1. UI Page
    ui_resp = client.get("/zepto")
    assert ui_resp.status_code == 200
    assert "Zepto Dark Store Hub" in ui_resp.text
    assert "tabBtn-utilization" in ui_resp.text
    assert ("tabBtn-loss" in ui_resp.text or "tabBtn-dq-loss" in ui_resp.text)
    assert "tabBtn-scorecard" in ui_resp.text
    assert "tabContent-utilization" in ui_resp.text
    assert ("tabContent-loss" in ui_resp.text or "tabContent-dq-loss" in ui_resp.text)
    assert "tabContent-scorecard" in ui_resp.text
    assert "attEmployeeDrawer" in ui_resp.text

    # 2. Overview API
    overview_resp = client.get("/api/v1/zepto/overview")
    assert overview_resp.status_code == 200
    overview_json = overview_resp.json()
    assert overview_json["success"] is True
    assert "headcount" in overview_json

    # 3. Employees API
    emp_resp = client.get("/api/v1/zepto/employees")
    assert emp_resp.status_code == 200
    assert emp_resp.json()["success"] is True

    # 4. Expenses API & Reimbursement Toggle
    exp_resp = client.get("/api/v1/zepto/expenses")
    assert exp_resp.status_code == 200
    exp_json = exp_resp.json()
    assert exp_json["success"] is True
    assert "reimbursed_total" in exp_json
    assert "pending_total" in exp_json
    if exp_json["items"]:
        first_id = exp_json["items"][0]["id"]
        patch_resp = client.patch(f"/api/v1/zepto/expenses/{first_id}/reimburse", json={"is_reimbursed": 1})
        assert patch_resp.status_code == 200
        assert patch_resp.json()["success"] is True

    # 5. Candidates API
    cand_resp = client.get("/api/v1/zepto/candidates")
    assert cand_resp.status_code == 200
    assert cand_resp.json()["success"] is True

    # 6. Security API (Get, Create, Put, Patch Proof, Delete)
    sec_resp = client.get("/api/v1/zepto/security")
    assert sec_resp.status_code == 200
    assert sec_resp.json()["success"] is True

    post_tranche = client.post(
        "/api/v1/zepto/security",
        json={
            "tranche_title": "Test Capital Tranche",
            "amount": 250000.0,
            "payment_date": "2026-08-28",
            "partner_name": "Harshiv Bargotra",
            "payment_mode": "IMPS",
            "reference_utr": "IMPS88776655",
        }
    )
    assert post_tranche.status_code == 200
    new_t_id = post_tranche.json()["tranche"]["id"]

    # Get single tranche endpoint
    get_single = client.get(f"/api/v1/zepto/security/{new_t_id}")
    assert get_single.status_code == 200
    assert get_single.json()["tranche"]["amount"] == 250000.0

    # Put update tranche endpoint
    put_tranche = client.put(
        f"/api/v1/zepto/security/{new_t_id}",
        json={
            "tranche_title": "Test Capital Tranche (Updated)",
            "amount": 300000.0,
            "payment_date": "2026-08-28",
            "partner_name": "Harshiv Bargotra",
            "payment_mode": "IMPS",
            "reference_utr": "IMPS88776655_EDITED",
            "notes": "Updated by master",
        }
    )
    assert put_tranche.status_code == 200
    assert put_tranche.json()["tranche"]["amount"] == 300000.0

    # Patch transfer slip proof endpoint
    patch_proof = client.patch(
        f"/api/v1/zepto/security/{new_t_id}/proof",
        json={
            "proof_doc_url": "/api/v1/zepto/documents/test_receipt.pdf",
            "reference_utr": "IMPS88776655_FINAL",
        }
    )
    assert patch_proof.status_code == 200
    assert patch_proof.json()["tranche"]["proof_doc_url"] == "/api/v1/zepto/documents/test_receipt.pdf"

    # Delete tranche endpoint
    del_tranche = client.delete(f"/api/v1/zepto/security/{new_t_id}")
    assert del_tranche.status_code == 200

    # 7. Staffing Targets & Base Pay API
    # Ensure default configs are reset
    client.put(
        "/api/v1/zepto/staffing-targets",
        json={
            "role_configs": {
                "PICKER": {"target_count": 9, "base_pay": 14000.0},
                "SHIFT_INCHARGE": {"target_count": 3, "base_pay": 20000.0},
                "SECURITY_GUARD": {"target_count": 2, "base_pay": 16000.0},
                "HOUSEKEEPING": {"target_count": 1, "base_pay": 14000.0},
            }
        }
    )

    target_resp = client.get("/api/v1/zepto/staffing-targets")
    assert target_resp.status_code == 200
    target_json = target_resp.json()
    assert target_json["success"] is True
    assert "targets" in target_json
    assert "base_pays" in target_json
    assert "role_configs" in target_json
    assert "projected_payroll_target" in target_json
    assert target_json["targets"]["PICKER"] >= 1
    assert target_json["base_pays"]["PICKER"] == 14000.0

    # Update targets and base pay via API
    put_resp = client.put(
        "/api/v1/zepto/staffing-targets",
        json={
            "role_configs": {
                "PICKER": {"target_count": 9, "base_pay": 18500.0},
                "SHIFT_INCHARGE": {"target_count": 3, "base_pay": 26000.0},
                "SECURITY_GUARD": {"target_count": 2, "base_pay": 16000.0},
                "HOUSEKEEPING": {"target_count": 1, "base_pay": 14000.0},
            }
        }
    )
    assert put_resp.status_code == 200
    assert put_resp.json()["base_pays"]["PICKER"] == 18500.0
    assert put_resp.json()["base_pays"]["SHIFT_INCHARGE"] == 26000.0

    # Reset back to default base pay
    client.put(
        "/api/v1/zepto/staffing-targets",
        json={
            "role_configs": {
                "PICKER": {"target_count": 9, "base_pay": 14000.0},
                "SHIFT_INCHARGE": {"target_count": 3, "base_pay": 20000.0},
                "SECURITY_GUARD": {"target_count": 2, "base_pay": 16000.0},
                "HOUSEKEEPING": {"target_count": 1, "base_pay": 14000.0},
            }
        }
    )


def test_customizable_staffing_targets_and_base_pay():
    settings = Settings()
    # Reset configs to default at start of test
    zepto_db.update_role_configs(
        {
            "PICKER": {"target_count": 9, "base_pay": 14000.0},
            "SHIFT_INCHARGE": {"target_count": 3, "base_pay": 20000.0},
            "SECURITY_GUARD": {"target_count": 2, "base_pay": 16000.0},
            "HOUSEKEEPING": {"target_count": 1, "base_pay": 14000.0},
        },
        settings,
    )

    # Check default thresholds & base pays
    configs = zepto_db.get_role_configs(settings)
    assert configs["PICKER"]["target_count"] == 9
    assert configs["PICKER"]["base_pay"] == 14000.0
    assert configs["SHIFT_INCHARGE"]["target_count"] == 3
    assert configs["SECURITY_GUARD"]["target_count"] == 2
    assert configs["HOUSEKEEPING"]["target_count"] == 1

    # Customize thresholds and base pay
    updated = zepto_db.update_role_configs(
        {
            "PICKER": {"target_count": 10, "base_pay": 19000.0},
            "SHIFT_INCHARGE": {"target_count": 4, "base_pay": 27000.0},
            "SECURITY_GUARD": {"target_count": 2, "base_pay": 16500.0},
            "HOUSEKEEPING": {"target_count": 1, "base_pay": 14500.0},
        },
        settings
    )
    assert updated["PICKER"]["target_count"] == 10
    assert updated["PICKER"]["base_pay"] == 19000.0
    assert updated["SHIFT_INCHARGE"]["base_pay"] == 27000.0

    # Verify overview capacity & payroll projection calculation
    # Projected payroll: 10*19000 + 4*27000 + 2*16500 + 1*14500 = 190000 + 108000 + 33000 + 14500 = 345500.0
    overview = zepto_db.get_zepto_overview(settings)
    cap = overview["headcount"]["capacity"]
    assert cap["PICKER"]["target"] == 10
    assert cap["PICKER"]["base_pay"] == 19000.0
    assert cap["PICKER"]["projected_role_payroll"] == 190000.0
    assert overview["headcount"]["projected_payroll_target"] == 345500.0

    # Reset back to default
    zepto_db.update_role_configs(
        {
            "PICKER": {"target_count": 9, "base_pay": 14000.0},
            "SHIFT_INCHARGE": {"target_count": 3, "base_pay": 20000.0},
            "SECURITY_GUARD": {"target_count": 2, "base_pay": 16000.0},
            "HOUSEKEEPING": {"target_count": 1, "base_pay": 14000.0},
        },
        settings
    )


def test_document_upload(client):
    file_content = b"%PDF-1.4 Mock Zepto Training Invoice"
    files = {"file": ("mock_receipt.pdf", io.BytesIO(file_content), "application/pdf")}
    upload_resp = client.post("/api/v1/zepto/upload", files=files)
    assert upload_resp.status_code == 200
    data = upload_resp.json()
    assert data["success"] is True
    assert "url" in data

    # Download/preview doc
    saved_filename = data["saved_filename"]
    doc_resp = client.get(f"/api/v1/zepto/documents/{saved_filename}")
    assert doc_resp.status_code == 200
    assert doc_resp.content == file_content


def test_monthly_ratings_and_salary_link(client):
    settings = Settings()
    # 1. Create a test employee
    emp = zepto_db.create_employee({
        "name": "Arjun Rampal",
        "role": "PICKER",
        "base_salary_monthly": 18000.0,
        "rating": 4.8,
        "status": "ACTIVE"
    }, settings)
    emp_id = emp["id"]

    # 2. Record monthly ratings for 2026-07 and 2026-08
    r1 = zepto_db.record_employee_monthly_rating(emp_id, "2026-07", 4.7, "Great attendance", settings)
    assert r1["rating"] == 4.7
    assert r1["year_month"] == "2026-07"

    r2 = zepto_db.record_employee_monthly_rating(emp_id, "2026-08", 4.95, "Flawless picking speed", settings)
    assert r2["rating"] == 4.95

    # 3. Fetch monthly ratings
    ratings = zepto_db.get_employee_monthly_ratings(emp_id, settings)
    assert len(ratings) == 2
    assert ratings[0]["year_month"] == "2026-08"

    # 4. Record salary slip with performance rating
    sal = zepto_db.record_employee_salary(emp_id, {
        "year_month": "2026-08",
        "base_amount": 18000.0,
        "bonus_amount": 1000.0,
        "performance_rating": 4.95,
        "deductions": 0.0,
    }, settings)
    assert sal["performance_rating"] == 4.95
    assert sal["net_paid"] == 19000.0

    # 5. Fetch salaries and verify joined rating
    salaries = zepto_db.get_employee_salaries(emp_id, settings)
    assert len(salaries) >= 1
    assert salaries[0]["performance_rating"] == 4.95
    assert "Flawless picking speed" in salaries[0]["rating_feedback"]

    # 6. Test ratings API
    api_resp = client.post(
        f"/api/v1/zepto/employees/{emp_id}/ratings",
        json={"year_month": "2026-09", "rating": 5.0, "feedback": "Promoted to shift lead candidate"}
    )
    assert api_resp.status_code == 200
    assert api_resp.json()["rating"]["rating"] == 5.0

    get_api_resp = client.get(f"/api/v1/zepto/employees/{emp_id}/ratings")
    assert get_api_resp.status_code == 200
    assert len(get_api_resp.json()["ratings"]) == 3

    # Cleanup
    zepto_db.delete_employee(emp_id, settings)


def test_store_income_and_customizable_partner_split(client):
    settings = Settings()
    # 1. Check default split settings (50% - 50%)
    split = zepto_db.get_income_split_settings(settings)
    assert split["partner_1_share_pct"] == 50.0
    assert split["partner_2_share_pct"] == 50.0

    # 2. Record store income with default 50-50 split
    inc1 = zepto_db.create_store_income({
        "title": "August Order Commission",
        "income_source": "COMMISSION",
        "gross_amount": 200000.0,
        "deductions": 4000.0,
        "income_date": "2026-08-25",
        "year_month": "2026-08",
        "payment_mode": "BANK_TRANSFER",
        "reference_utr": "ZEPTO-COM-AUG-001",
    }, settings)

    assert inc1["net_amount"] == 196000.0
    assert inc1["partner_1_share_pct"] == 50.0
    assert inc1["partner_2_share_pct"] == 50.0
    assert inc1["partner_1_share_amount"] == 98000.0
    assert inc1["partner_2_share_amount"] == 98000.0

    # 3. Update global partner split to 60% Jatin - 40% Harshiv
    updated_split = zepto_db.update_income_split_settings(60.0, 40.0, settings)
    assert updated_split["partner_1_share_pct"] == 60.0
    assert updated_split["partner_2_share_pct"] == 40.0

    # 4. Record new income entry using the new 60-40 default
    inc2 = zepto_db.create_store_income({
        "title": "SLA & Growth Surge Bonus",
        "income_source": "GROWTH_INCENTIVE",
        "gross_amount": 100000.0,
        "deductions": 0.0,
        "income_date": "2026-08-28",
        "year_month": "2026-08",
    }, settings)

    assert inc2["net_amount"] == 100000.0
    assert inc2["partner_1_share_pct"] == 60.0
    assert inc2["partner_2_share_pct"] == 40.0
    assert inc2["partner_1_share_amount"] == 60000.0
    assert inc2["partner_2_share_amount"] == 40000.0

    # 5. Fetch store income list and verify items
    income_res = zepto_db.get_store_income(year_month="2026-08", settings=settings)
    assert len(income_res) >= 2
    assert any(item["id"] == inc1["id"] for item in income_res)
    assert any(item["id"] == inc2["id"] for item in income_res)

    # 6. Test Store Income API endpoints
    # GET /income
    api_inc = client.get("/api/v1/zepto/income?year_month=2026-08")
    assert api_inc.status_code == 200
    inc_json = api_inc.json()
    assert inc_json["total_net"] >= 296000.0
    assert "split_settings" in inc_json
    assert inc_json["split_settings"]["partner_1_share_pct"] == 60.0

    # Update split settings via API (change back to 50-50)
    split_resp = client.post(
        "/api/v1/zepto/income-split-settings",
        json={"partner_1_share_pct": 50.0, "partner_2_share_pct": 50.0}
    )
    assert split_resp.status_code == 200
    assert split_resp.json()["settings"]["partner_1_share_pct"] == 50.0

    # Clean up test records
    zepto_db.delete_store_income(inc1["id"], settings)
    zepto_db.delete_store_income(inc2["id"], settings)


def test_zepto_drawer_and_operations_endpoints(client):
    settings = Settings()
    # 1. Seed attendance record for employee
    mock_batch = {
        "store_name": "JMU-Sainik Colony",
        "file_name": "drawer_test.xlsx",
        "start_date": "2026-09-01",
        "end_date": "2026-09-01",
        "total_records": 1,
        "total_employees": 1,
        "records": [
            {
                "employee_id": "EMP_API_TEST",
                "employee_name": "Simran Kaur",
                "designation": "FR_Packer",
                "shift_date": "2026-09-01",
                "shift_name": "Morning",
                "shift_time": "06:00 - 15:00",
                "punch_in": "06:02:00",
                "punch_out": "15:01:00",
                "work_duration_mins": 539,
                "break_duration_mins": 35,
                "raw_status": "P",
                "status": "PRESENT",
            }
        ],
        "summary": {"present_count": 1, "absent_count": 0, "attendance_rate_pct": 100.0},
    }
    saved_batch = zepto_db.save_attendance_batch(mock_batch, source="TEST", settings=settings)

    # Test Employee Attendance Drawer API
    emp_drawer_resp = client.get("/api/v1/zepto/attendance/employee/EMP_API_TEST")
    assert emp_drawer_resp.status_code == 200
    drawer_json = emp_drawer_resp.json()
    assert drawer_json["success"] is True
    assert drawer_json["detail"]["employee_name"] == "Simran Kaur"
    assert drawer_json["detail"]["total_shifts"] == 1
    assert len(drawer_json["detail"]["punch_history"]) == 1

    # Test 404 for nonexistent employee
    emp_404_resp = client.get("/api/v1/zepto/attendance/employee/NON_EXISTENT_EMP_999")
    assert emp_404_resp.status_code == 404

    # 2. Store Metrics API
    m_post = client.post(
        "/api/v1/zepto/metrics",
        json={
            "store_name": "JMU-Sainik Colony",
            "metric_date": "2026-09-29",
            "sales_gmv": 412000.0,
            "order_count": 950,
            "aov": 433.7,
            "inbound_hours": 20.0,
            "outbound_hours": 45.0,
            "packer_ipp": 140.0,
            "sla_adherence_pct": 99.1,
        },
    )
    assert m_post.status_code == 200
    assert m_post.json()["success"] is True

    m_get = client.get("/api/v1/zepto/metrics/summary?store_name=JMU-Sainik Colony")
    assert m_get.status_code == 200
    m_json = m_get.json()
    assert m_json["success"] is True
    assert m_json["total_gmv"] >= 412000.0
    assert m_json["total_orders"] >= 950

    # 3. Loss & Shrinkage API
    l_post = client.post(
        "/api/v1/zepto/loss",
        json={
            "store_name": "JMU-Sainik Colony",
            "record_date": "2026-09-29",
            "loss_type": "DQ_LOSS",
            "category": "DAIRY",
            "amount": 890.0,
            "sku_count": 8,
            "notes": "Milk crate leakage",
        },
    )
    assert l_post.status_code == 200
    assert l_post.json()["success"] is True

    l_get = client.get("/api/v1/zepto/loss/summary?store_name=JMU-Sainik Colony&month=2026-09")
    assert l_get.status_code == 200
    l_json = l_get.json()
    assert l_json["success"] is True
    assert l_json["total_loss_amount"] >= 890.0
    assert "available_months" in l_json
    assert "reconciliation" in l_json

    # Test Loss Records search endpoint
    rec_get = client.get("/api/v1/zepto/loss/records?store_name=JMU-Sainik Colony&search=Milk")
    assert rec_get.status_code == 200
    rec_json = rec_get.json()
    assert rec_json["success"] is True
    assert rec_json["total_count"] >= 1
    assert any("Milk" in r.get("notes", "") for r in rec_json["records"])

    # 4. Manpower Utilization API
    u_post = client.post(
        "/api/v1/zepto/utilization",
        json={
            "store_name": "JMU-Sainik Colony",
            "util_date": "2026-09-29",
            "employee_id": "EMP_API_TEST",
            "employee_name": "Simran Kaur",
            "role": "FR_Packer",
            "items_picked": 720,
            "active_pick_hours": 7.0,
            "idle_hours": 0.8,
            "ipp": 102.8,
            "flex_labor_cost": 1350.0,
        },
    )
    assert u_post.status_code == 200
    assert u_post.json()["success"] is True

    u_get = client.get("/api/v1/zepto/utilization/summary?store_name=JMU-Sainik Colony")
    assert u_get.status_code == 200
    u_json = u_get.json()
    assert u_json["success"] is True
    assert u_json["total_items_picked"] >= 720

    # Cleanup
    zepto_db.delete_attendance_import(saved_batch["import_id"], settings=settings)


def test_zepto_employee_visibility_and_sync_roster_api(client):
    settings = Settings()
    # 1. Create a test employee and toggle visibility
    emp = zepto_db.create_employee({
        "name": "Test Visibility Staff",
        "role": "PICKER",
        "base_salary_monthly": 18000.0,
        "rating": 4.9,
        "status": "ACTIVE",
    }, settings)
    emp_id = emp["id"]

    try:
        # Patch visibility to hidden
        patch_res = client.patch(f"/api/v1/zepto/employees/{emp_id}/visibility", json={"is_hidden": True})
        assert patch_res.status_code == 200
        assert patch_res.json()["employee"]["is_hidden"] == 1

        # Verify excluded by default
        list_def = client.get("/api/v1/zepto/employees")
        assert list_def.status_code == 200
        items_def = list_def.json()["items"]
        assert not any(e["id"] == emp_id for e in items_def)

        # Verify included when include_hidden=true
        list_all = client.get("/api/v1/zepto/employees?include_hidden=true")
        assert list_all.status_code == 200
        items_all = list_all.json()["items"]
        assert any(e["id"] == emp_id for e in items_all)

        # Unhide
        patch_unhide = client.patch(f"/api/v1/zepto/employees/{emp_id}/visibility", json={"is_hidden": False})
        assert patch_unhide.status_code == 200
        assert patch_unhide.json()["employee"]["is_hidden"] == 0

        # Test sync roster endpoint
        sync_res = client.post("/api/v1/zepto/employees/sync-roster")
        assert sync_res.status_code == 200
        assert sync_res.json()["success"] is True

        # Test purge framed endpoint
        purge_res = client.post("/api/v1/zepto/employees/purge-framed")
        assert purge_res.status_code == 200
        assert purge_res.json()["success"] is True
    finally:
        zepto_db.delete_employee(emp_id, settings)


def test_staff_employee_profile_analytics_drawer(client):
    settings = Settings()
    test_tag = uuid.uuid4().hex[:6]
    emp_name = f"Vikram Rathore {test_tag}"
    # 1. Create a test employee
    emp = zepto_db.create_employee({
        "name": emp_name,
        "role": "PICKER",
        "base_salary_monthly": 18500.0,
        "rating": 4.95,
        "status": "ACTIVE",
    }, settings)
    emp_id = emp["id"]

    # 2. Add attendance batch for Vikram
    mock_batch = {
        "store_name": "JMU-Sainik Colony",
        "file_name": f"vikram_att_{test_tag}.xlsx",
        "start_date": "2026-09-01",
        "end_date": "2026-09-02",
        "total_records": 2,
        "total_employees": 1,
        "records": [
            {
                "employee_id": emp_id,
                "employee_name": emp_name,
                "designation": "PICKER",
                "shift_date": "2026-09-01",
                "shift_name": "Morning Shift",
                "shift_time": "06:00 - 15:00",
                "punch_in": "06:01:00",
                "punch_out": "15:03:00",
                "work_duration_mins": 542,
                "break_duration_mins": 30,
                "raw_status": "P",
                "status": "PRESENT",
            },
            {
                "employee_id": emp_id,
                "employee_name": emp_name,
                "designation": "PICKER",
                "shift_date": "2026-09-02",
                "shift_name": "Morning Shift",
                "shift_time": "06:00 - 15:00",
                "punch_in": "06:00:00",
                "punch_out": "15:00:00",
                "work_duration_mins": 540,
                "break_duration_mins": 30,
                "raw_status": "P",
                "status": "PRESENT",
            },
        ],
        "summary": {"present_count": 2, "absent_count": 0, "attendance_rate_pct": 100.0},
    }
    saved_batch = zepto_db.save_attendance_batch(mock_batch, source="TEST", settings=settings)

    # 3. Add IPP utilization record for Vikram
    zepto_db.save_manpower_utilization({
        "store_name": "JMU-Sainik Colony",
        "util_date": "2026-09-01",
        "employee_id": emp_id,
        "employee_name": emp_name,
        "role": "Picker",
        "items_picked": 840,
        "active_pick_hours": 7.0,
        "idle_hours": 0.5,
        "ipp": 120.0,
    }, settings=settings)

    # 4. Add salary slip & rating
    zepto_db.record_employee_monthly_rating(emp_id, "2026-09", 5.0, "Outstanding warehouse picking", settings)
    zepto_db.record_employee_salary(emp_id, {
        "year_month": "2026-09",
        "base_amount": 18500.0,
        "bonus_amount": 1500.0,
        "deductions": 0.0,
        "performance_rating": 5.0,
    }, settings)

    try:
        # 5. Test Python DAL
        profile = zepto_db.get_employee_profile_analytics(emp_id, year_month="2026-09", settings=settings)
        assert profile is not None
        assert profile["employee"]["name"] == emp_name
        assert profile["selected_month"] == "2026-09"
        assert profile["attendance"]["total_shifts"] == 2
        assert profile["attendance"]["present_count"] == 2
        assert profile["attendance"]["attendance_rate_pct"] == 100.0
        assert profile["attendance"]["total_hours_worked"] == 18.0
        assert profile["productivity"]["avg_ipp"] == 120.0
        assert profile["productivity"]["total_items_picked"] == 840
        assert len(profile["salaries"]) >= 1
        assert len(profile["ratings"]) >= 1

        # 6. Test API Router Endpoint
        api_res = client.get(f"/api/v1/zepto/employees/{emp_id}/profile-analytics?year_month=2026-09")
        assert api_res.status_code == 200
        data = api_res.json()
        assert data["success"] is True
        assert data["employee"]["name"] == emp_name
        assert data["attendance"]["attendance_rate_pct"] == 100.0
        assert data["productivity"]["avg_ipp"] == 120.0

        # 7. Test Hub UI Template Rendering
        hub_res = client.get("/zepto")
        assert hub_res.status_code == 200
        assert "staffEmployeeDrawer" in hub_res.text
        assert "staffEmployeeDrawerBackdrop" in hub_res.text
        assert "staffDrawerMonthSelect" in hub_res.text
        assert "staffDrawerAttRate" in hub_res.text
        assert "staffDrawerIPP" in hub_res.text
        assert "staffDrawerPunchTableBody" in hub_res.text
        assert "staffDrawerSalaryTableBody" in hub_res.text
    finally:
        zepto_db.delete_attendance_import(saved_batch["import_id"], settings=settings)
        zepto_db.delete_employee(emp_id, settings)


def test_zepto_hub_available_months_and_dashboard_analytics(client):
    settings = Settings()
    # 1. Overview returns available_months list
    overview = zepto_db.get_zepto_overview(settings)
    assert "available_months" in overview
    assert isinstance(overview["available_months"], list)

    # 2. Attendance summary returns available_months list and selected_month
    att_summary = zepto_db.get_attendance_summary(year_month=None, settings=settings)
    assert "available_months" in att_summary
    assert "selected_month" in att_summary
    assert att_summary["selected_month"] == "ALL"

    # 3. Operations Dashboard analytics endpoint
    res = client.get("/api/v1/zepto/operations/analytics?month=ALL")
    assert res.status_code == 200
    data = res.json()
    assert "available_months" in data
    assert "mom_trends" in data
    assert "dod_metrics" in data
    assert "summary_kpis" in data


def test_zepto_rerun_loss_audit_reconciliation(client):
    """Test rerun email body vs Excel attachment reconciliation endpoint and DB method."""
    settings = Settings()
    # 1. Test database method
    summary = zepto_db.rerun_loss_audit_reconciliation(month="ALL", store_name="ALL", settings=settings)
    assert isinstance(summary, dict)
    assert "total_records" in summary
    assert "records" in summary
    assert "category_breakdown" in summary
    assert "reconciliation" in summary
    assert "match_rate_pct" in summary["reconciliation"]

    # 2. Test POST API endpoint
    res = client.post("/api/v1/zepto/loss/reconciliation/rerun", json={"month": "ALL", "store_name": "ALL"})
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert "reconciliation" in data
    assert "message" in data






