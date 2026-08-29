"""Tests for Zepto Dark Store Management Hub."""

from __future__ import annotations

import io
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
    assert overview["headcount"]["active"] >= 1
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


def test_store_expenses_and_spend_per_employee():
    settings = Settings()
    exp_data = {
        "title": "Aisle B Barcode Scanners (x4)",
        "category": "EQUIPMENT",
        "amount": 22000.0,
        "incurred_by": "Jatin Abrol",
        "is_reimbursed": 0,
        "notes": "Handheld Zebra scanners (Pending Reimbursement)",
    }
    exp = zepto_db.create_expense(exp_data, settings)
    assert exp["id"] is not None
    assert exp["is_reimbursed"] == 0

    # Filter by category and reimbursement status
    pending_expenses = zepto_db.get_expenses(category="EQUIPMENT", reimbursement_status="PENDING", settings=settings)
    assert any(e["id"] == exp["id"] for e in pending_expenses)

    # Toggle reimbursement to settled
    toggled = zepto_db.toggle_expense_reimbursement(exp["id"], is_reimbursed=1, settings=settings)
    assert toggled["is_reimbursed"] == 1

    reimbursed_expenses = zepto_db.get_expenses(reimbursement_status="REIMBURSED", settings=settings)
    assert any(e["id"] == exp["id"] for e in reimbursed_expenses)

    overview = zepto_db.get_zepto_overview(settings)
    assert overview["expenses"]["spend_per_employee"] > 0
    assert "pending_reimbursement" in overview["expenses"]
    assert "reimbursed_expenses" in overview["expenses"]


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

    overview = zepto_db.get_zepto_overview(settings)
    sec = overview["security_capital"]
    assert sec["target_total"] == 7500000.0
    assert sec["target_per_partner"] == 3750000.0
    assert sec["partner_1"]["paid"] >= 500000.0
    assert "equalization" in sec


def test_zepto_api_endpoints(client):
    # 1. UI Page
    ui_resp = client.get("/zepto")
    assert ui_resp.status_code == 200
    assert "Zepto Dark Store Hub" in ui_resp.text

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

    # 6. Security API
    sec_resp = client.get("/api/v1/zepto/security")
    assert sec_resp.status_code == 200
    assert sec_resp.json()["success"] is True

    # 7. Staffing Targets API
    target_resp = client.get("/api/v1/zepto/staffing-targets")
    assert target_resp.status_code == 200
    target_json = target_resp.json()
    assert target_json["success"] is True
    assert "targets" in target_json
    assert "capacity" in target_json
    assert target_json["targets"]["PICKER"] >= 1

    # Update targets
    put_resp = client.put("/api/v1/zepto/staffing-targets", json={"targets": {"PICKER": 9, "SHIFT_INCHARGE": 3, "SECURITY_GUARD": 2, "HOUSEKEEPING": 1}})
    assert put_resp.status_code == 200
    assert put_resp.json()["targets"]["PICKER"] == 9


def test_customizable_staffing_targets():
    settings = Settings()
    # Check default thresholds
    targets = zepto_db.get_staffing_targets(settings)
    assert targets["PICKER"] == 9
    assert targets["SHIFT_INCHARGE"] == 3
    assert targets["SECURITY_GUARD"] == 2
    assert targets["HOUSEKEEPING"] == 1

    # Customize thresholds
    updated = zepto_db.update_staffing_targets(
        {"PICKER": 12, "SHIFT_INCHARGE": 4, "SECURITY_GUARD": 3, "HOUSEKEEPING": 2},
        settings
    )
    assert updated["PICKER"] == 12
    assert updated["SHIFT_INCHARGE"] == 4

    # Verify overview capacity calculation
    overview = zepto_db.get_zepto_overview(settings)
    cap = overview["headcount"]["capacity"]
    assert cap["PICKER"]["target"] == 12
    assert cap["SHIFT_INCHARGE"]["target"] == 4
    assert "deficit" in cap["PICKER"]
    assert "fulfilled" in cap["PICKER"]

    # Reset back to default
    zepto_db.update_staffing_targets(
        {"PICKER": 9, "SHIFT_INCHARGE": 3, "SECURITY_GUARD": 2, "HOUSEKEEPING": 1},
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
