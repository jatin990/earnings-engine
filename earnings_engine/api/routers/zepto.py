"""Zepto Store Management Hub — FastAPI REST API Router.

Provides endpoints for Dark Store Employees, MoM Salary & Bonus Tracking,
Store Out-of-Pocket Expenses, Hiring Candidates Pipeline, and ₹75L 50-50 Partner Capital Ledger.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse

from earnings_engine.config import Settings
from earnings_engine.data import zepto_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Zepto Hub"])
_settings = Settings()


# ---------------------------------------------------------------------------
# UI Page Route
# ---------------------------------------------------------------------------

@router.get("/zepto", response_class=HTMLResponse, summary="Zepto Store Hub UI")
async def get_zepto_hub_ui() -> HTMLResponse:
    """Render the Zepto Store Management Hub UI."""
    from earnings_engine.api.dependencies import get_template_env

    try:
        env = get_template_env()
        template = env.get_template("hubs/zepto/index.html")
        html = template.render(
            title="Zepto Dark Store Hub — Nexus",
            active_tab="zepto",
        )
        return HTMLResponse(html)
    except Exception as exc:
        logger.error("[ZEPTO-UI] Render error: %s", exc, exc_info=True)
        return HTMLResponse(
            f"<html><body><h1>Zepto Hub render error</h1><p>{exc}</p></body></html>",
            status_code=500,
        )


# ---------------------------------------------------------------------------
# Overview & Store Analytics
# ---------------------------------------------------------------------------

@router.get("/api/v1/zepto/overview", summary="Store Overview & Analytics")
async def get_zepto_overview_endpoint() -> dict[str, Any]:
    """Return aggregated headcount, attrition, spend insights and 50-50 equity progress."""
    try:
        data = zepto_db.get_zepto_overview(_settings)
        return {"success": True, **data}
    except Exception as e:
        logger.error("[ZEPTO-API] Error computing overview: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/v1/zepto/staffing-targets", summary="Get Staffing Targets & Capacity")
@router.get("/api/v1/zepto/role-configs", summary="Get Role Configs & Base Pay")
async def get_staffing_targets_endpoint() -> dict[str, Any]:
    """Retrieve customizable target headcount and base pay per store role with live fulfillment capacity."""
    try:
        role_configs = zepto_db.get_role_configs(_settings)
        overview = zepto_db.get_zepto_overview(_settings)
        return {
            "success": True,
            "targets": {r: role_configs[r]["target_count"] for r in role_configs},
            "base_pays": {r: role_configs[r]["base_pay"] for r in role_configs},
            "role_configs": role_configs,
            "projected_payroll_target": overview["headcount"]["projected_payroll_target"],
            "capacity": overview["headcount"]["capacity"],
            "roles": overview["config"]["roles"],
        }
    except Exception as e:
        logger.error("[ZEPTO-API] Error fetching staffing targets: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/api/v1/zepto/staffing-targets", summary="Update Staffing Targets & Base Pay")
@router.post("/api/v1/zepto/staffing-targets", summary="Update Staffing Targets & Base Pay (POST)")
@router.put("/api/v1/zepto/role-configs", summary="Update Role Configs")
@router.post("/api/v1/zepto/role-configs", summary="Update Role Configs (POST)")
async def update_staffing_targets_endpoint(payload: dict[str, Any]) -> dict[str, Any]:
    """Update customizable target headcount and/or monthly base pay per store role."""
    try:
        # Check if structured role_configs/configs provided
        if "role_configs" in payload or "configs" in payload:
            configs = payload.get("role_configs", payload.get("configs", {}))
            updated_configs = zepto_db.update_role_configs(configs, _settings)
        else:
            raw_targets = payload.get("targets", {})
            raw_base_pays = payload.get("base_pays", payload.get("base_pay", {}))

            # Also allow flat key-value pairs if targets key omitted
            if not raw_targets and not raw_base_pays:
                raw_targets = payload

            targets = {k.upper(): int(v) for k, v in raw_targets.items() if isinstance(v, (int, str)) and str(v).isdigit()}
            base_pays = {k.upper(): float(v) for k, v in raw_base_pays.items() if isinstance(v, (int, float, str)) and str(v).replace(".", "", 1).isdigit()}

            zepto_db.update_staffing_targets(targets, base_pays=base_pays, settings=_settings)
            updated_configs = zepto_db.get_role_configs(_settings)

        overview = zepto_db.get_zepto_overview(_settings)
        return {
            "success": True,
            "targets": {r: updated_configs[r]["target_count"] for r in updated_configs},
            "base_pays": {r: updated_configs[r]["base_pay"] for r in updated_configs},
            "role_configs": updated_configs,
            "projected_payroll_target": overview["headcount"]["projected_payroll_target"],
            "capacity": overview["headcount"]["capacity"],
            "roles": overview["config"]["roles"],
        }
    except Exception as e:
        logger.error("[ZEPTO-API] Error updating staffing targets: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------------------------
# Employees & Salaries
# ---------------------------------------------------------------------------

@router.get("/api/v1/zepto/employees", summary="List Store Employees")
async def get_employees_endpoint(
    role: str | None = Query(None, description="Filter by role e.g. PICKER, SHIFT_INCHARGE"),
    status: str | None = Query(None, description="Filter by status: ACTIVE, RESIGNED, ON_PROBATION"),
    search: str | None = Query(None, description="Search employee name or phone"),
) -> dict[str, Any]:
    """Retrieve store employees with role, status and search filters."""
    try:
        employees = zepto_db.get_employees(role=role, status=status, search=search, settings=_settings)
        return {"success": True, "count": len(employees), "items": employees}
    except Exception as e:
        logger.error("[ZEPTO-API] Error listing employees: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/v1/zepto/employees", summary="Create Store Employee")
async def create_employee_endpoint(payload: dict[str, Any]) -> dict[str, Any]:
    """Add a new employee to the store roster."""
    try:
        emp = zepto_db.create_employee(payload, _settings)
        return {"success": True, "employee": emp}
    except Exception as e:
        logger.error("[ZEPTO-API] Error creating employee: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/api/v1/zepto/employees/{emp_id}", summary="Get Employee Details")
async def get_employee_endpoint(emp_id: str) -> dict[str, Any]:
    """Get single employee record by ID."""
    emp = zepto_db.get_employee_by_id(emp_id, _settings)
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    salaries = zepto_db.get_employee_salaries(emp_id, _settings)
    return {"success": True, "employee": emp, "salaries": salaries}


@router.put("/api/v1/zepto/employees/{emp_id}", summary="Update Employee")
async def update_employee_endpoint(emp_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Update employee details, performance ratings, or resignation info."""
    try:
        emp = zepto_db.update_employee(emp_id, payload, _settings)
        if not emp:
            raise HTTPException(status_code=404, detail="Employee not found")
        return {"success": True, "employee": emp}
    except Exception as e:
        logger.error("[ZEPTO-API] Error updating employee %s: %s", emp_id, e)
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/api/v1/zepto/employees/{emp_id}", summary="Delete Employee")
async def delete_employee_endpoint(emp_id: str) -> dict[str, Any]:
    """Remove employee from store database."""
    zepto_db.delete_employee(emp_id, _settings)
    return {"success": True, "deleted_id": emp_id}


@router.post("/api/v1/zepto/employees/{emp_id}/bonus", summary="Award Performance Bonus")
async def add_bonus_endpoint(emp_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Add a performance bonus to an employee."""
    bonus_amount = float(payload.get("amount") or payload.get("bonus_amount") or 0.0)
    notes = payload.get("notes")
    emp = zepto_db.add_employee_bonus(emp_id, bonus_amount, notes=notes, settings=_settings)
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    return {"success": True, "employee": emp}


@router.get("/api/v1/zepto/employees/{emp_id}/salaries", summary="Get MoM Salary History")
async def get_employee_salaries_endpoint(emp_id: str) -> dict[str, Any]:
    """Retrieve Month-on-Month salary history and ratings for an employee."""
    salaries = zepto_db.get_employee_salaries(emp_id, _settings)
    return {"success": True, "employee_id": emp_id, "salaries": salaries}


@router.post("/api/v1/zepto/employees/{emp_id}/salaries", summary="Record Monthly Salary Payout")
async def record_salary_endpoint(emp_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Record or update a monthly salary slip with performance rating for an employee."""
    try:
        sal = zepto_db.record_employee_salary(emp_id, payload, _settings)
        return {"success": True, "salary": sal}
    except Exception as e:
        logger.error("[ZEPTO-API] Error recording salary for %s: %s", emp_id, e)
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/api/v1/zepto/employees/{emp_id}/ratings", summary="Get Employee Monthly Ratings")
async def get_employee_ratings_endpoint(emp_id: str) -> dict[str, Any]:
    """Retrieve all monthly performance ratings for an employee."""
    ratings = zepto_db.get_employee_monthly_ratings(emp_id, _settings)
    return {"success": True, "employee_id": emp_id, "ratings": ratings}


@router.post("/api/v1/zepto/employees/{emp_id}/ratings", summary="Record Monthly Employee Rating")
async def record_employee_rating_endpoint(emp_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Record or update an employee's performance rating for a specific month."""
    year_month = payload.get("year_month")
    rating = payload.get("rating")
    if not year_month or rating is None:
        raise HTTPException(status_code=400, detail="year_month and rating are required")
    try:
        res = zepto_db.record_employee_monthly_rating(
            emp_id=emp_id,
            year_month=year_month,
            rating=float(rating),
            feedback=payload.get("feedback"),
            settings=_settings,
        )
        return {"success": True, "rating": res}
    except Exception as e:
        logger.error("[ZEPTO-API] Error recording monthly rating for %s: %s", emp_id, e)
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------------------------
# Store Expenses
# ---------------------------------------------------------------------------

@router.get("/api/v1/zepto/expenses", summary="List Store Expenses")
async def get_expenses_endpoint(
    category: str | None = Query(None, description="Filter by category e.g. TRAINING, UNIFORMS_GEAR"),
    incurred_by: str | None = Query(None, description="Filter by partner or cash"),
    reimbursement_status: str | None = Query(None, description="Filter by reimbursement status: PENDING, REIMBURSED, ALL"),
    search: str | None = Query(None, description="Search expense title"),
) -> dict[str, Any]:
    """Retrieve store expenses ledger with category, payer, and reimbursement filters."""
    try:
        expenses = zepto_db.get_expenses(
            category=category,
            incurred_by=incurred_by,
            reimbursement_status=reimbursement_status,
            search=search,
            settings=_settings,
        )
        total = sum(e.get("amount", 0.0) for e in expenses)
        reimbursed_total = sum(
            e.get("amount", 0.0)
            for e in expenses
            if (e.get("is_reimbursable", 1) == 1 and e.get("is_reimbursed") == 1) or e.get("incurred_by") == "STORE_CASH"
        )
        pending_total = sum(
            e.get("amount", 0.0)
            for e in expenses
            if e.get("is_reimbursable", 1) == 1 and e.get("is_reimbursed") == 0 and e.get("incurred_by") != "STORE_CASH"
        )
        non_reimbursable_total = sum(
            e.get("amount", 0.0)
            for e in expenses
            if e.get("is_reimbursable", 1) == 0 and e.get("incurred_by") != "STORE_CASH"
        )
        return {
            "success": True,
            "count": len(expenses),
            "total_amount": total,
            "reimbursed_total": reimbursed_total,
            "pending_total": pending_total,
            "non_reimbursable_total": non_reimbursable_total,
            "items": expenses,
        }
    except Exception as e:
        logger.error("[ZEPTO-API] Error listing expenses: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/v1/zepto/expenses", summary="Create Store Expense")
async def create_expense_endpoint(payload: dict[str, Any]) -> dict[str, Any]:
    """Record an out-of-pocket store expense."""
    try:
        exp = zepto_db.create_expense(payload, _settings)
        return {"success": True, "expense": exp}
    except Exception as e:
        logger.error("[ZEPTO-API] Error recording expense: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/api/v1/zepto/expenses/{exp_id}", summary="Update Store Expense")
async def update_expense_endpoint(exp_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Update an existing store expense record."""
    try:
        exp = zepto_db.update_expense(exp_id, payload, _settings)
        return {"success": True, "expense": exp}
    except Exception as e:
        logger.error("[ZEPTO-API] Error updating expense %s: %s", exp_id, e)
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/api/v1/zepto/expenses/{exp_id}/reimburse", summary="Toggle Reimbursement Status")
async def toggle_expense_reimburse_endpoint(exp_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Toggle or directly set the reimbursement status of an expense."""
    try:
        is_reimbursed = payload.get("is_reimbursed") if payload else None
        res = zepto_db.toggle_expense_reimbursement(exp_id, is_reimbursed, _settings)
        return {"success": True, "result": res}
    except Exception as e:
        logger.error("[ZEPTO-API] Error toggling reimbursement for expense %s: %s", exp_id, e)
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/api/v1/zepto/expenses/{exp_id}", summary="Delete Store Expense")
async def delete_expense_endpoint(exp_id: str) -> dict[str, Any]:
    """Delete a store expense record."""
    zepto_db.delete_expense(exp_id, _settings)
    return {"success": True, "deleted_id": exp_id}


# ---------------------------------------------------------------------------
# Candidates (Hiring Pipeline)
# ---------------------------------------------------------------------------

@router.get("/api/v1/zepto/candidates", summary="List Hiring Candidates")
async def get_candidates_endpoint(
    stage: str | None = Query(None, description="Filter by stage: APPLIED, INTERVIEWING, SHORTLISTED"),
    target_role: str | None = Query(None, description="Filter by target role"),
    search: str | None = Query(None, description="Search candidate name or phone"),
) -> dict[str, Any]:
    """Retrieve candidate pipeline."""
    try:
        candidates = zepto_db.get_candidates(stage=stage, target_role=target_role, search=search, settings=_settings)
        return {"success": True, "count": len(candidates), "items": candidates}
    except Exception as e:
        logger.error("[ZEPTO-API] Error listing candidates: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/v1/zepto/candidates", summary="Create Candidate")
async def create_candidate_endpoint(payload: dict[str, Any]) -> dict[str, Any]:
    """Add a new prospective candidate to pipeline."""
    try:
        cand = zepto_db.create_candidate(payload, _settings)
        return {"success": True, "candidate": cand}
    except Exception as e:
        logger.error("[ZEPTO-API] Error creating candidate: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/api/v1/zepto/candidates/{cand_id}", summary="Update Candidate")
async def update_candidate_endpoint(cand_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Update candidate pipeline stage or interview notes."""
    try:
        res = zepto_db.update_candidate(cand_id, payload, _settings)
        return {"success": True, "candidate": res}
    except Exception as e:
        logger.error("[ZEPTO-API] Error updating candidate %s: %s", cand_id, e)
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/api/v1/zepto/candidates/{cand_id}/convert", summary="Hire / Convert Candidate to Employee")
async def convert_candidate_endpoint(cand_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """One-click conversion of candidate into active store staff."""
    payload = payload or {}
    try:
        res = zepto_db.convert_candidate_to_employee(
            cand_id=cand_id,
            joining_date=payload.get("joining_date"),
            base_salary=float(payload["base_salary"]) if payload.get("base_salary") else None,
            settings=_settings,
        )
        return {"success": True, **res}
    except Exception as e:
        logger.error("[ZEPTO-API] Error converting candidate %s: %s", cand_id, e)
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/api/v1/zepto/candidates/{cand_id}", summary="Delete Candidate")
async def delete_candidate_endpoint(cand_id: str) -> dict[str, Any]:
    """Delete candidate from pipeline."""
    zepto_db.delete_candidate(cand_id, _settings)
    return {"success": True, "deleted_id": cand_id}


# ---------------------------------------------------------------------------
# Zepto Security Deposit & 50-50 Capital Contribution Ledger
# ---------------------------------------------------------------------------

@router.get("/api/v1/zepto/security", summary="Get Security Deposit & Tranches")
async def get_security_endpoint() -> dict[str, Any]:
    """Retrieve ₹75L security deposit progress and payment tranches."""
    try:
        overview = zepto_db.get_zepto_overview(_settings)
        tranches = zepto_db.get_security_tranches(_settings)
        return {
            "success": True,
            "summary": overview.get("security_capital", {}),
            "tranches": tranches,
        }
    except Exception as e:
        logger.error("[ZEPTO-API] Error getting security capital: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


def _verify_master_role(request: Request) -> None:
    """Enforce Master / Owner role permissions for Master Security Deposit mutations."""
    from earnings_engine.api.dependencies import _get_current_session
    session = _get_current_session(request)
    role = session.get("role")
    scopes = session.get("scopes", [])
    
    # If a session role is present, ensure it is master/owner/admin
    if role and role not in ("owner", "admin") and not ("*" in scopes or "admin" in scopes or "zepto_master" in scopes):
        raise HTTPException(
            status_code=403,
            detail="Forbidden: Only Master Portal Admins have permission to record, edit, or modify Master Security Deposit payment tranches.",
        )


@router.post("/api/v1/zepto/security", summary="Record Capital Tranche (Master Only)")
async def create_security_tranche_endpoint(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    """Record a capital payment tranche sent to Zepto (Master Admin Only)."""
    _verify_master_role(request)
    try:
        tranche = zepto_db.create_security_tranche(payload, _settings)
        return {"success": True, "tranche": tranche}
    except Exception as e:
        logger.error("[ZEPTO-API] Error recording capital tranche: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/api/v1/zepto/security/{tranche_id}", summary="Get Single Capital Tranche")
async def get_security_tranche_endpoint(tranche_id: str) -> dict[str, Any]:
    """Retrieve a single security capital tranche by ID."""
    tranche = zepto_db.get_security_tranche_by_id(tranche_id, _settings)
    if not tranche:
        raise HTTPException(status_code=404, detail=f"Security tranche {tranche_id} not found")
    return {"success": True, "tranche": tranche}


@router.put("/api/v1/zepto/security/{tranche_id}", summary="Update Capital Tranche (Master Only)")
async def update_security_tranche_endpoint(tranche_id: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    """Update details of a capital tranche and/or transfer slip (Master Admin Only)."""
    _verify_master_role(request)
    try:
        tranche = zepto_db.update_security_tranche(tranche_id, payload, _settings)
        return {"success": True, "tranche": tranche}
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        logger.error("[ZEPTO-API] Error updating capital tranche %s: %s", tranche_id, e)
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/api/v1/zepto/security/{tranche_id}/proof", summary="Update Transfer Slip Ad-Hoc (Master Only)")
async def patch_security_proof_endpoint(tranche_id: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    """Ad-hoc upload and update of transfer slip or UTR reference for a tranche (Master Admin Only)."""
    _verify_master_role(request)
    proof_url = payload.get("proof_doc_url")
    if not proof_url:
        raise HTTPException(status_code=400, detail="proof_doc_url is required")
    try:
        res = zepto_db.update_security_proof(
            tranche_id=tranche_id,
            proof_doc_url=proof_url,
            reference_utr=payload.get("reference_utr"),
            notes=payload.get("notes"),
            settings=_settings,
        )
        return {"success": True, "tranche": res}
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        logger.error("[ZEPTO-API] Error patching proof for tranche %s: %s", tranche_id, e)
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/api/v1/zepto/security/{tranche_id}", summary="Delete Capital Tranche (Master Only)")
async def delete_security_tranche_endpoint(tranche_id: str, request: Request) -> dict[str, Any]:
    """Delete a capital tranche record (Master Admin Only)."""
    _verify_master_role(request)
    zepto_db.delete_security_tranche(tranche_id, _settings)
    return {"success": True, "deleted_id": tranche_id}


# ---------------------------------------------------------------------------
# Document Storage & Uploads
# ---------------------------------------------------------------------------

@router.post("/api/v1/zepto/upload", summary="Upload Document")
async def upload_document_endpoint(file: UploadFile = File(...)) -> dict[str, Any]:
    """Upload a document (Aadhar, Resume, Receipt, Proof) and get access URL."""
    try:
        content = await file.read()
        res = zepto_db.save_uploaded_file(content, file.filename or "document.pdf")
        return {"success": True, **res}
    except Exception as e:
        logger.error("[ZEPTO-API] Error uploading file: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/api/v1/zepto/documents/{filename}", summary="Download / Preview Document")
async def get_document_endpoint(filename: str) -> FileResponse:
    """Download or preview an uploaded store document."""
    upload_dir = Path("data/zepto/uploads")
    file_path = upload_dir / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path, filename=filename)


# ---------------------------------------------------------------------------
# Store Income & Customizable Partner Profit Split
# ---------------------------------------------------------------------------

@router.get("/api/v1/zepto/income-sources", summary="Get Income Source Categories")
async def get_income_sources_endpoint() -> dict[str, Any]:
    """Retrieve metadata for store income sources."""
    return {"success": True, "sources": zepto_db.INCOME_SOURCE_METADATA}


@router.get("/api/v1/zepto/income-split-settings", summary="Get Partner Split Ratio Settings")
async def get_income_split_settings_endpoint() -> dict[str, Any]:
    """Retrieve configurable profit split percentage between partners."""
    settings = zepto_db.get_income_split_settings(_settings)
    return {"success": True, "settings": settings}


@router.post("/api/v1/zepto/income-split-settings", summary="Update Partner Split Ratio Settings (POST)")
@router.put("/api/v1/zepto/income-split-settings", summary="Update Partner Split Ratio Settings (PUT)")
async def update_income_split_settings_endpoint(payload: dict[str, Any]) -> dict[str, Any]:
    """Update customizable income split percentage between Jatin and Harshiv."""
    p1_pct = payload.get("partner_1_share_pct")
    p2_pct = payload.get("partner_2_share_pct")
    if p1_pct is None or p2_pct is None:
        raise HTTPException(status_code=400, detail="partner_1_share_pct and partner_2_share_pct are required")
    try:
        updated = zepto_db.update_income_split_settings(
            partner_1_pct=float(p1_pct),
            partner_2_pct=float(p2_pct),
            partner_1_name=payload.get("partner_1_name"),
            partner_2_name=payload.get("partner_2_name"),
            settings=_settings,
        )
        return {"success": True, "settings": updated}
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error("[ZEPTO-API] Error updating income split settings: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/api/v1/zepto/income", summary="List Store Income Records")
async def get_income_endpoint(
    year_month: str | None = Query(None, description="Filter by year-month e.g. 2026-08"),
    income_source: str | None = Query(None, description="Filter by source e.g. COMMISSION, GROWTH_INCENTIVE"),
    search: str | None = Query(None, description="Search title, UTR, or notes"),
) -> dict[str, Any]:
    """Retrieve store income records with live aggregate totals and partner share breakdowns."""
    try:
        items = zepto_db.get_store_income(
            year_month=year_month,
            income_source=income_source,
            search=search,
            settings=_settings,
        )
        overview = zepto_db.get_zepto_overview(_settings)
        split_settings = zepto_db.get_income_split_settings(_settings)

        total_gross = sum(i.get("gross_amount", 0.0) for i in items)
        total_deductions = sum(i.get("deductions", 0.0) for i in items)
        total_net = sum(i.get("net_amount", 0.0) for i in items)
        partner_1_total = sum(i.get("partner_1_share_amount", 0.0) for i in items)
        partner_2_total = sum(i.get("partner_2_share_amount", 0.0) for i in items)

        return {
            "success": True,
            "count": len(items),
            "total_gross": total_gross,
            "total_deductions": total_deductions,
            "total_net": total_net,
            "partner_1_total": partner_1_total,
            "partner_2_total": partner_2_total,
            "split_settings": split_settings,
            "overview_income": overview.get("income", {}),
            "items": items,
        }
    except Exception as e:
        logger.error("[ZEPTO-API] Error retrieving store income: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/v1/zepto/income/{income_id}", summary="Get Store Income by ID")
async def get_income_by_id_endpoint(income_id: str) -> dict[str, Any]:
    """Retrieve a single income record."""
    inc = zepto_db.get_store_income_by_id(income_id, _settings)
    if not inc:
        raise HTTPException(status_code=404, detail=f"Income record {income_id} not found")
    return {"success": True, "income": inc}


@router.post("/api/v1/zepto/income", summary="Record Store Income")
async def create_income_endpoint(payload: dict[str, Any]) -> dict[str, Any]:
    """Record a new store income payment with custom or default partner split percentage."""
    if not payload.get("title") or payload.get("gross_amount") is None:
        raise HTTPException(status_code=400, detail="title and gross_amount are required")
    try:
        inc = zepto_db.create_store_income(payload, _settings)
        return {"success": True, "income": inc}
    except Exception as e:
        logger.error("[ZEPTO-API] Error recording store income: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/api/v1/zepto/income/{income_id}", summary="Update Store Income")
async def update_income_endpoint(income_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Update a store income record and recalculate partner distributions."""
    try:
        inc = zepto_db.update_store_income(income_id, payload, _settings)
        return {"success": True, "income": inc}
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        logger.error("[ZEPTO-API] Error updating store income %s: %s", income_id, e)
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/api/v1/zepto/income/{income_id}", summary="Delete Store Income")
async def delete_income_endpoint(income_id: str) -> dict[str, Any]:
    """Delete a store income record."""
    zepto_db.delete_store_income(income_id, _settings)
    return {"success": True, "deleted_id": income_id}


# ---------------------------------------------------------------------------
# Gmail OAuth 2.0 Linking & Status Endpoints
# ---------------------------------------------------------------------------

@router.get("/api/v1/zepto/gmail/status", summary="Gmail Integration Status")
async def get_gmail_status_endpoint() -> dict[str, Any]:
    """Return whether Gmail OAuth credentials are configured and whether an account is currently linked."""
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    is_configured = bool(client_id and client_secret and len(client_id.strip()) > 5)

    auth = zepto_db.get_gmail_auth("primary", _settings)
    is_connected = bool(auth and auth.get("access_token"))

    return {
        "success": True,
        "configured": is_configured,
        "connected": is_connected,
        "email": auth.get("email") if auth else None,
        "token_expiry": auth.get("token_expiry") if auth else None,
        "updated_at": auth.get("updated_at") if auth else None,
        "scopes": auth.get("scopes") if auth else None,
    }


@router.get("/api/v1/zepto/gmail/auth-url", summary="Generate Google OAuth Authorization URL")
async def get_gmail_auth_url_endpoint(request: Request) -> dict[str, Any]:
    """Generate Google OAuth 2.0 authorization URL with anti-CSRF state token."""
    import secrets
    import urllib.parse

    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise HTTPException(
            status_code=400,
            detail="GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be configured in environment variables.",
        )

    # Determine redirect URI: env var or dynamically from request
    redirect_uri = os.getenv("GOOGLE_REDIRECT_URI")
    if not redirect_uri:
        base_url = str(request.base_url).rstrip("/")
        redirect_uri = f"{base_url}/api/v1/zepto/gmail/callback"

    state = secrets.token_urlsafe(24)
    scopes = [
        "https://www.googleapis.com/auth/gmail.readonly",
        "openid",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile",
    ]

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(scopes),
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }

    auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(params)}"
    return {
        "success": True,
        "auth_url": auth_url,
        "state": state,
        "redirect_uri": redirect_uri,
    }


@router.get("/api/v1/zepto/gmail/callback", summary="Google OAuth Callback Handler")
async def get_gmail_callback_endpoint(
    request: Request,
    code: str | None = Query(None),
    error: str | None = Query(None),
    state: str | None = Query(None),
) -> Any:
    """Exchange authorization code for Google tokens and store in SQLite."""
    from datetime import datetime, timedelta, timezone
    from fastapi.responses import RedirectResponse
    import httpx

    if error:
        logger.warning("[GMAIL-OAUTH] User denied or error received: %s", error)
        return RedirectResponse(url="/zepto#gmail?error=access_denied")

    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code parameter.")

    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise HTTPException(status_code=500, detail="Google client credentials not configured.")

    redirect_uri = os.getenv("GOOGLE_REDIRECT_URI")
    if not redirect_uri:
        base_url = str(request.base_url).rstrip("/")
        redirect_uri = f"{base_url}/api/v1/zepto/gmail/callback"

    token_url = "https://oauth2.googleapis.com/token"
    token_payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # 1. Exchange code for access & refresh tokens
            tok_resp = await client.post(token_url, data=token_payload)
            if tok_resp.status_code != 200:
                logger.error("[GMAIL-OAUTH] Token exchange failed: %s", tok_resp.text)
                return RedirectResponse(url="/zepto#gmail?error=token_exchange_failed")

            token_data = tok_resp.json()
            access_token = token_data.get("access_token")
            refresh_token = token_data.get("refresh_token")
            expires_in = token_data.get("expires_in", 3600)
            token_type = token_data.get("token_type", "Bearer")
            scope_granted = token_data.get("scope", "")

            # Calculate expiry
            expiry_dt = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
            expiry_iso = expiry_dt.isoformat()

            # 2. Fetch User Profile to get Gmail Address
            userinfo_url = "https://www.googleapis.com/oauth2/v2/userinfo"
            user_resp = await client.get(
                userinfo_url,
                headers={"Authorization": f"Bearer {access_token}"}
            )
            email = "unknown@gmail.com"
            if user_resp.status_code == 200:
                u_data = user_resp.json()
                email = u_data.get("email", email)

            # 3. Save into zepto_db
            zepto_db.save_gmail_auth(
                email=email,
                access_token=access_token,
                refresh_token=refresh_token,
                token_expiry=expiry_iso,
                scopes=scope_granted,
                token_type=token_type,
                auth_id="primary",
                settings=_settings,
            )
            logger.info("[GMAIL-OAUTH] Successfully linked Gmail account: %s", email)

        return RedirectResponse(url="/zepto#gmail?status=connected")
    except Exception as exc:
        logger.error("[GMAIL-OAUTH] Exception in oauth callback: %s", exc, exc_info=True)
        return RedirectResponse(url="/zepto#gmail?error=internal_error")


@router.post("/api/v1/zepto/gmail/disconnect", summary="Disconnect Linked Gmail Account")
async def disconnect_gmail_endpoint() -> dict[str, Any]:
    """Revoke Google OAuth token and clear credentials from local database."""
    import httpx

    auth = zepto_db.get_gmail_auth("primary", _settings)
    if auth and auth.get("access_token"):
        # Best-effort revocation with Google
        try:
            revoke_url = f"https://oauth2.googleapis.com/revoke?token={auth['access_token']}"
            with httpx.Client(timeout=5.0) as client:
                client.post(revoke_url)
        except Exception as e:
            logger.debug("[GMAIL-OAUTH] Revocation notice: %s", e)

    zepto_db.delete_gmail_auth("primary", _settings)
    logger.info("[GMAIL-OAUTH] Disconnected Gmail account")
    return {"success": True, "status": "success", "message": "Gmail account disconnected"}

