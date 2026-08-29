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
    """Retrieve Month-on-Month salary history for an employee."""
    salaries = zepto_db.get_employee_salaries(emp_id, _settings)
    return {"success": True, "employee_id": emp_id, "salaries": salaries}


@router.post("/api/v1/zepto/employees/{emp_id}/salaries", summary="Record Monthly Salary Payout")
async def record_salary_endpoint(emp_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Record or update a monthly salary slip for an employee."""
    try:
        sal = zepto_db.record_employee_salary(emp_id, payload, _settings)
        return {"success": True, "salary": sal}
    except Exception as e:
        logger.error("[ZEPTO-API] Error recording salary for %s: %s", emp_id, e)
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
        reimbursed_total = sum(e.get("amount", 0.0) for e in expenses if e.get("is_reimbursed") == 1 or e.get("incurred_by") == "STORE_CASH")
        pending_total = sum(e.get("amount", 0.0) for e in expenses if e.get("is_reimbursed") == 0 and e.get("incurred_by") != "STORE_CASH")
        return {
            "success": True,
            "count": len(expenses),
            "total_amount": total,
            "reimbursed_total": reimbursed_total,
            "pending_total": pending_total,
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


@router.post("/api/v1/zepto/security", summary="Record Capital Tranche")
async def create_security_tranche_endpoint(payload: dict[str, Any]) -> dict[str, Any]:
    """Record a capital payment tranche sent to Zepto."""
    try:
        tranche = zepto_db.create_security_tranche(payload, _settings)
        return {"success": True, "tranche": tranche}
    except Exception as e:
        logger.error("[ZEPTO-API] Error recording capital tranche: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/api/v1/zepto/security/{tranche_id}", summary="Delete Capital Tranche")
async def delete_security_tranche_endpoint(tranche_id: str) -> dict[str, Any]:
    """Delete a capital tranche record."""
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
