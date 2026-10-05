"""Zepto Store Management Hub — FastAPI REST API Router.

Provides endpoints for Dark Store Employees, MoM Salary & Bonus Tracking,
Store Out-of-Pocket Expenses, Hiring Candidates Pipeline, and ₹75L 50-50 Partner Capital Ledger.
"""

from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import logging
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, File, Form, HTTPException, Query, Request, UploadFile
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
async def get_zepto_overview_endpoint(
    month: str | None = Query(None),
) -> dict[str, Any]:
    """Return aggregated headcount, attrition, spend insights and 50-50 equity progress."""
    try:
        data = zepto_db.get_zepto_overview(_settings)
        return {"success": True, **data}
    except Exception as e:
        logger.error("[ZEPTO-API] Error computing overview: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/v1/zepto/operations/analytics", summary="Get Master MoM and DoD Operational Dashboard")
async def get_zepto_dashboard_analytics_endpoint(
    month: str | None = Query(None, description="Month in YYYY-MM format, or 'ALL'"),
    store_name: str | None = Query(None, description="Filter by dark store name"),
) -> dict[str, Any]:
    """Retrieve cross-operational Month-on-Month and Day-on-Day matrix covering attendance, loss, orders, GMV, and IPP."""
    try:
        data = zepto_db.get_zepto_dashboard_analytics(
            month=month,
            store_name=store_name,
            settings=_settings,
        )
        return {"success": True, **data}
    except Exception as exc:
        logger.error("[ZEPTO-ANALYTICS] Error fetching operations analytics: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


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
    search: str | None = Query(None, description="Search employee name, phone, ID"),
    include_hidden: bool = Query(False, description="Whether to include soft-hidden employees"),
) -> dict[str, Any]:
    """Retrieve store employees with role, status and search filters."""
    try:
        employees = zepto_db.get_employees(role=role, status=status, search=search, include_hidden=include_hidden, settings=_settings)
        return {"success": True, "count": len(employees), "items": employees}
    except Exception as e:
        logger.error("[ZEPTO-API] Error listing employees: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/v1/zepto/employees/sync-roster", summary="Sync Real Roster from Attendance")
async def sync_roster_endpoint() -> dict[str, Any]:
    """Auto-populate / sync master employee roster from imported attendance Excel sheets."""
    try:
        res = zepto_db.sync_roster_from_attendance(_settings)
        return {"success": True, **res}
    except Exception as e:
        logger.error("[ZEPTO-API] Error syncing roster: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/v1/zepto/employees/purge-framed", summary="Purge Framed Starter Employees")
async def purge_framed_endpoint() -> dict[str, Any]:
    """Purge synthetic/framed sample employees (emp_01 to emp_06)."""
    try:
        res = zepto_db.purge_mock_framed_employees(_settings)
        return {"success": True, **res}
    except Exception as e:
        logger.error("[ZEPTO-API] Error purging framed employees: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/api/v1/zepto/employees/{emp_id}/visibility", summary="Toggle Employee Hidden Visibility")
async def toggle_employee_visibility_endpoint(emp_id: str, payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    """Hide or unhide an employee in UI tables and metrics."""
    try:
        is_hidden = payload.get("is_hidden")
        if is_hidden is not None:
            is_hidden = bool(is_hidden)
        emp = zepto_db.toggle_employee_visibility(emp_id, is_hidden=is_hidden, settings=_settings)
        if not emp:
            raise HTTPException(status_code=404, detail="Employee not found")
        return {"success": True, "employee": emp}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("[ZEPTO-API] Error updating employee visibility %s: %s", emp_id, e)
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/api/v1/zepto/employees", summary="Create Store Employee")
async def create_employee_endpoint(payload: dict[str, Any]) -> dict[str, Any]:
    """Add a new employee to the store roster."""
    try:
        emp = zepto_db.create_employee(payload, _settings)
        return {"success": True, "employee": emp}
    except Exception as e:
        logger.error("[ZEPTO-API] Error creating employee: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/api/v1/zepto/employees/{emp_id}/profile-analytics", summary="Get Full Employee Profile Analytics & Monthly Drawer Drilldown")
async def get_employee_profile_analytics_endpoint(
    emp_id: str,
    year_month: str | None = Query(None),
) -> dict[str, Any]:
    """Retrieve individual employee bio, month-wise attendance scorecard, punch timeline, IPP productivity, and MoM salary/rating history."""
    try:
        profile = zepto_db.get_employee_profile_analytics(emp_id, year_month=year_month, settings=_settings)
        if not profile:
            raise HTTPException(status_code=404, detail=f"Employee '{emp_id}' not found.")
        return {"success": True, **profile}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("[ZEPTO-EMPLOYEE] Error fetching profile analytics for %s: %s", emp_id, exc)
        raise HTTPException(status_code=500, detail=str(exc))


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
# Offer Letter Generation & Management
# ---------------------------------------------------------------------------

@router.get("/api/v1/zepto/offer-letters", summary="List Offer Letters")
async def get_offer_letters_endpoint(
    search: str | None = Query(None, description="Search candidate name, role, or doc ref")
) -> dict[str, Any]:
    """Retrieve saved offer letters."""
    try:
        letters = zepto_db.get_offer_letters(search=search, settings=_settings)
        return {"success": True, "count": len(letters), "items": letters}
    except Exception as e:
        logger.error("[ZEPTO-API] Error listing offer letters: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/v1/zepto/offer-letters", summary="Save Offer Letter")
async def save_offer_letter_endpoint(payload: dict[str, Any]) -> dict[str, Any]:
    """Create or update an offer letter record."""
    try:
        if not payload.get("candidate_name"):
            raise HTTPException(status_code=422, detail="Candidate name is required.")
        letter = zepto_db.save_offer_letter(payload, settings=_settings)
        return {"success": True, "letter": letter}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("[ZEPTO-API] Error saving offer letter: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/v1/zepto/offer-letters/{letter_id}", summary="Get Offer Letter Details")
async def get_offer_letter_endpoint(letter_id: str) -> dict[str, Any]:
    """Retrieve full details and snapshot of an offer letter."""
    letter = zepto_db.get_offer_letter(letter_id, settings=_settings)
    if not letter:
        raise HTTPException(status_code=404, detail=f"Offer letter {letter_id} not found.")
    return {"success": True, "letter": letter}


@router.delete("/api/v1/zepto/offer-letters/{letter_id}", summary="Delete Offer Letter")
async def delete_offer_letter_endpoint(letter_id: str) -> dict[str, Any]:
    """Delete an offer letter."""
    success = zepto_db.delete_offer_letter(letter_id, settings=_settings)
    if not success:
        raise HTTPException(status_code=404, detail=f"Offer letter {letter_id} not found.")
    return {"success": True, "deleted": True, "id": letter_id}


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
# Local Email Serving & Detail Endpoints (Zero-Latency / Offline)
# ---------------------------------------------------------------------------

@router.get("/api/v1/zepto/gmail/emails", summary="Get Persisted Emails from Local Database")
async def get_persisted_emails_endpoint(
    month: str | None = Query(None, description="Month in YYYY-MM format or 'ALL'"),
    category: str | None = Query(None, description="Filter by category (DQ_LOSS, SHRINKAGE, ATTENDANCE, etc.)"),
    store_name: str | None = Query(None, description="Store name filter"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    """
    Serve operational emails directly from the local SQLite database for zero-latency UI rendering,
    with filtering by month, operational category, and store.
    """
    try:
        clean_month = None
        if month and month.upper() not in ("ALL", ""):
            clean_month = month.strip()

        emails = zepto_db.get_saved_gmail_messages(
            month=clean_month,
            category=category,
            store_name=store_name,
            limit=limit,
            offset=offset,
            settings=_settings,
        )
        return {
            "success": True,
            "count": len(emails),
            "month": clean_month or "ALL",
            "category": category,
            "emails": emails,
            "source": "LOCAL_DATABASE",
        }
    except Exception as exc:
        logger.error("[ZEPTO-EMAILS] Error fetching local emails: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/api/v1/zepto/gmail/emails/{email_id}", summary="Get Single Persisted Email with Linked DB Records")
async def get_persisted_email_detail_endpoint(email_id: str) -> dict[str, Any]:
    """
    Retrieve full email details (subject, sender, body HTML/text, metadata)
    along with any linked records created from it in zepto_loss_records,
    zepto_store_metrics, or zepto_attendance_imports.
    """
    try:
        email_data = zepto_db.get_saved_gmail_message_by_id(email_id, settings=_settings)
        if not email_data:
            raise HTTPException(status_code=404, detail=f"Email '{email_id}' not found in local database")
        return {
            "success": True,
            "email": email_data,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("[ZEPTO-EMAILS] Error retrieving email %s: %s", email_id, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Gmail OAuth 2.0 Linking & Status Endpoints
# ---------------------------------------------------------------------------

def _safe_b64decode(data_str: str) -> bytes:
    """Decode URL-safe base64 string handling missing RFC 4648 padding."""
    if not data_str:
        return b""
    clean_str = data_str.strip()
    pad = len(clean_str) % 4
    if pad:
        clean_str += "=" * (4 - pad)
    return base64.urlsafe_b64decode(clean_str.encode("utf-8"))


def _classify_zepto_email(subject: str, sender: str, snippet: str = "") -> dict[str, Any]:
    """
    Categorize dark store operational email based on subject line and sender
    using deterministic regex pattern matching first, falling back to keywords.
    """
    from earnings_engine.data.zepto_parsers import match_zepto_subject_pattern
    return match_zepto_subject_pattern(subject=subject, sender=sender, snippet=snippet)


def _build_gmail_month_query(month: str | None) -> tuple[str, str]:
    """
    Given a month string (e.g. '2026-08' or 'ALL' or None),
    returns (clean_month_ym, gmail_q_str).
    Defaults to current month if None or empty.
    Uses targeted operational keywords to avoid fetching unrelated emails.
    """
    from earnings_engine.data.zepto_parsers import build_targeted_gmail_query
    return build_targeted_gmail_query(month)


@router.get("/api/v1/zepto/gmail/recent-emails", summary="Get Categorized Dark Store Emails by Month")
async def get_recent_emails_endpoint(
    month: str | None = Query(None, description="Month in YYYY-MM format, 'ALL', or defaults to current month"),
    refresh: bool = Query(True, description="Whether to query live Gmail API or load directly from database"),
) -> dict[str, Any]:
    """
    Fetch dark store emails from linked Gmail partitioned by month (fetching all messages for that month),
    categorize by operational topic, persist into SQLite database (zepto_gmail_messages), and return structured records.
    """
    import urllib.parse
    import httpx

    clean_month, gmail_q = _build_gmail_month_query(month)
    token = zepto_db.get_valid_gmail_token("primary", _settings)

    # Fallback to local DB if not connected or refresh is False
    if not token or not refresh:
        saved_emails = zepto_db.get_saved_gmail_messages(month=clean_month, settings=_settings)
        if not token and not saved_emails:
            raise HTTPException(
                status_code=400,
                detail="No active Gmail account connected. Please link Gmail in the #gmail tab.",
            )
        return {
            "success": True,
            "month": clean_month,
            "count": len(saved_emails),
            "emails": saved_emails,
            "source": "DATABASE",
        }

    headers = {"Authorization": f"Bearer {token}"}

    try:
        # Step 1: Identify what is already saved locally so we only fetch delta from Gmail
        existing_msg_ids = zepto_db.get_saved_gmail_message_ids(settings=_settings)

        async with httpx.AsyncClient(timeout=45.0) as client:
            all_msg_summaries = []
            page_token = None
            max_pages = 10  # Paginate to check all message IDs for the month (lightweight query)

            for _ in range(max_pages):
                list_url = "https://gmail.googleapis.com/gmail/v1/users/me/messages?maxResults=50"
                if gmail_q:
                    list_url += f"&q={urllib.parse.quote(gmail_q)}"
                if page_token:
                    list_url += f"&pageToken={page_token}"

                resp = await client.get(list_url, headers=headers)
                if resp.status_code != 200:
                    if all_msg_summaries:
                        break
                    raise HTTPException(status_code=502, detail=f"Gmail API error: {resp.text}")

                page_data = resp.json()
                msgs = page_data.get("messages", [])
                if not msgs:
                    break
                all_msg_summaries.extend(msgs)
                page_token = page_data.get("nextPageToken")
                if not page_token:
                    break

            # Step 2: Delta detection - only fetch full bodies for emails not already in local database
            delta_summaries = [m for m in all_msg_summaries if m.get("id") not in existing_msg_ids]
            logger.info(
                "[GMAIL-DELTA] Month=%s: %d total messages found on Gmail, %d new delta messages to download",
                clean_month,
                len(all_msg_summaries),
                len(delta_summaries),
            )

            new_emails = []

            for msg_summary in delta_summaries:
                msg_id = msg_summary["id"]
                msg_url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{msg_id}?format=full"
                m_resp = await client.get(msg_url, headers=headers)
                if m_resp.status_code != 200:
                    continue

                msg_data = m_resp.json()
                payload = msg_data.get("payload", {})
                headers_list = payload.get("headers", [])

                subject = ""
                sender = ""
                date_str = ""
                for h in headers_list:
                    h_name = h.get("name", "").lower()
                    if h_name == "subject":
                        subject = h.get("value", "")
                    elif h_name == "from":
                        sender = h.get("value", "")
                    elif h_name == "date":
                        date_str = h.get("value", "")

                snippet = msg_data.get("snippet", "")

                # Extract plain text & HTML bodies from MIME parts
                body_text = ""
                body_html = ""
                def extract_bodies(part_node):
                    nonlocal body_text, body_html
                    m_type = part_node.get("mimeType", "")
                    b_data = part_node.get("body", {}).get("data")
                    if b_data:
                        try:
                            decoded = _safe_b64decode(b_data).decode("utf-8", errors="replace")
                            if m_type == "text/plain" and not body_text:
                                body_text = decoded
                            elif m_type == "text/html" and not body_html:
                                body_html = decoded
                        except Exception:
                            pass
                    for sub in part_node.get("parts", []):
                        extract_bodies(sub)

                extract_bodies(payload)
                if not body_text and snippet:
                    body_text = snippet

                # Collect attachment filenames
                attachments = []
                def extract_attachments(part_node):
                    fname = part_node.get("filename")
                    if fname:
                        attachments.append({
                            "filename": fname,
                            "mime_type": part_node.get("mimeType", ""),
                            "size_bytes": part_node.get("body", {}).get("size", 0),
                        })
                    for sub in part_node.get("parts", []):
                        extract_attachments(sub)

                extract_attachments(payload)

                cat_info = _classify_zepto_email(subject, sender, snippet)
                from earnings_engine.data.zepto_parsers import extract_metrics_from_email_body, parse_zepto_manpower_utilization_html
                extracted_metrics = extract_metrics_from_email_body(f"{subject} {snippet} {body_text}")
                if cat_info["category"] == "MANPOWER_UTILIZATION" and body_html:
                    parsed_manpower = parse_zepto_manpower_utilization_html(body_html, subject=subject)
                    if parsed_manpower.get("metrics"):
                        extracted_metrics.update(parsed_manpower["metrics"])

                # Format ISO date
                iso_date = cat_info.get("record_date") or datetime.now().strftime("%Y-%m-%d")
                if not cat_info.get("record_date") and date_str:
                    try:
                        from email.utils import parsedate_to_datetime
                        dt = parsedate_to_datetime(date_str)
                        iso_date = dt.strftime("%Y-%m-%d")
                    except Exception:
                        pass

                month_ym = iso_date[:7]
                store_name = cat_info.get("store_name") or "JMU-Sainik Colony"

                new_emails.append({
                    "id": msg_id,
                    "thread_id": msg_data.get("threadId"),
                    "store_name": store_name,
                    "subject": subject or "(No Subject)",
                    "from": sender,
                    "date": date_str,
                    "iso_date": iso_date,
                    "month_ym": month_ym,
                    "snippet": snippet,
                    "body_text": body_text,
                    "body_html": body_html,
                    "category": cat_info["category"],
                    "category_label": cat_info["category_label"],
                    "badge_color": cat_info["badge_color"],
                    "icon": cat_info["icon"],
                    "extracted_metrics": extracted_metrics,
                    "attachments": attachments,
                    "has_attachments": len(attachments) > 0,
                    "internal_date": msg_data.get("internalDate"),
                })

            # Step 3: Save any net-new delta emails to SQLite DB
            if new_emails:
                zepto_db.save_gmail_messages(new_emails, settings=_settings)

            # Step 4: Return consolidated list from local database for instant zero-latency rendering
            all_month_emails = zepto_db.get_saved_gmail_messages(month=clean_month, settings=_settings)

            return {
                "success": True,
                "month": clean_month,
                "count": len(all_month_emails),
                "emails": all_month_emails,
                "delta_fetched": len(new_emails),
                "source": "DATABASE_WITH_DELTA_SYNC" if new_emails else "DATABASE_UP_TO_DATE",
            }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("[GMAIL-API] Error fetching emails: %s", exc, exc_info=True)
        # Attempt fallback to DB
        saved_emails = zepto_db.get_saved_gmail_messages(month=clean_month, settings=_settings)
        if saved_emails:
            return {
                "success": True,
                "month": clean_month,
                "count": len(saved_emails),
                "emails": saved_emails,
                "source": "DATABASE_FALLBACK",
            }
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/api/v1/zepto/data/purge", summary="Purge Historical Operational Data for Clean Re-ingestion")
async def purge_zepto_data_endpoint(
    store_name: str | None = Query(None, description="Store name, or defaults to all stores"),
    month: str | None = Query(None, description="Month YYYY-MM, or defaults to all months"),
    include_emails: bool = Query(False, description="Whether to also purge ingested raw Gmail messages"),
) -> dict[str, Any]:
    """Purge historical operational records to enable clean re-ingestion with latest multi-sheet parsers."""
    purged = zepto_db.purge_zepto_operational_data(
        store_name=store_name,
        month=month,
        include_emails=include_emails,
        settings=_settings,
    )
    return {
        "status": "success",
        "message": f"Successfully purged operational records for store={store_name or 'ALL'}, month={month or 'ALL'}",
        "purged_counts": purged,
    }


@router.post("/api/v1/zepto/gmail/ingest-all-emails", summary="Ingest All Operational Emails & Parse Metrics into Database")
async def ingest_all_emails_endpoint(
    month: str | None = Query(None, description="Month in YYYY-MM format, 'ALL', or defaults to current month"),
    force: bool = Query(False, description="Force re-processing of already saved emails and attachments"),
    purge_existing: bool = Query(False, description="Purge operational database tables prior to re-ingestion"),
) -> dict[str, Any]:
    """
    Ingest all operational emails from linked Gmail inbox for the specified month (or all):
    1. Optionally purges old operational data if purge_existing is True.
    2. Fetches all messages for the month across operational categories and saves them into zepto_gmail_messages.
    3. Downloads and parses attached spreadsheets (.xlsx) for Attendance, Store Metrics, Manpower, and DQ Loss.
    4. Extracts structured body metrics (GMV, Orders, AOV, SLA, IPP, Loss) and updates persistent tables.
    5. Returns updated category counters and ingested payload details.
    """
    import base64
    import urllib.parse
    import httpx
    from earnings_engine.data.zepto_attendance_parser import parse_zepto_attendance_excel
    from earnings_engine.data.zepto_parsers import (
        parse_zepto_store_metrics_excel,
        parse_zepto_loss_shrinkage_excel,
        extract_metrics_from_email_body,
    )

    token = zepto_db.get_valid_gmail_token("primary", _settings)
    if not token:
        raise HTTPException(
            status_code=400,
            detail="No active Gmail account connected. Please link Gmail in the #gmail tab.",
        )

    clean_month, gmail_q = _build_gmail_month_query(month)

    if purge_existing:
        zepto_db.purge_zepto_operational_data(
            month=clean_month if clean_month != "ALL" else None,
            include_emails=False,
            settings=_settings,
        )

    headers = {"Authorization": f"Bearer {token}"}
    ingested_counts = {
        "STORE_METRICS": 0,
        "ATTENDANCE": 0,
        "MANPOWER_UTILIZATION": 0,
        "DQ_LOSS": 0,
        "SHRINKAGE": 0,
        "MANPOWER_PLAN": 0,
        "OPERATIONAL": 0,
        "SECURITY_ALERT": 0,
    }

    processed_details = {
        "attendance_records": 0,
        "store_metrics_records": 0,
        "manpower_records": 0,
        "loss_records": 0,
        "emails_scanned": 0,
        "month": clean_month,
    }

    try:
        # Step 1: Detect existing IDs to only process net-new delta emails unless force=True
        existing_msg_ids = set() if force else zepto_db.get_saved_gmail_message_ids(settings=_settings)

        async with httpx.AsyncClient(timeout=60.0) as client:
            all_msg_summaries = []
            page_token = None
            max_pages = 10  # Fetch message ID index for the month

            for _ in range(max_pages):
                list_url = "https://gmail.googleapis.com/gmail/v1/users/me/messages?maxResults=50"
                if gmail_q:
                    list_url += f"&q={urllib.parse.quote(gmail_q)}"
                if page_token:
                    list_url += f"&pageToken={page_token}"

                resp = await client.get(list_url, headers=headers)
                if resp.status_code != 200:
                    if all_msg_summaries:
                        break
                    raise HTTPException(status_code=502, detail=f"Gmail API error: {resp.text}")

                page_data = resp.json()
                msgs = page_data.get("messages", [])
                if not msgs:
                    break
                all_msg_summaries.extend(msgs)
                page_token = page_data.get("nextPageToken")
                if not page_token:
                    break

            processed_details["emails_scanned"] = len(all_msg_summaries)
            delta_summaries = [m for m in all_msg_summaries if m.get("id") not in existing_msg_ids]
            logger.info(
                "[GMAIL-INGEST-DELTA] Month=%s: %d total messages on Gmail, %d to ingest (force=%s)",
                clean_month,
                len(all_msg_summaries),
                len(delta_summaries),
                force,
            )
            emails_to_save = []

            for msg_summary in delta_summaries:
                msg_id = msg_summary["id"]
                msg_url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{msg_id}?format=full"
                m_resp = await client.get(msg_url, headers=headers)
                if m_resp.status_code != 200:
                    continue

                msg_data = m_resp.json()
                payload = msg_data.get("payload", {})
                headers_list = payload.get("headers", [])

                subject = ""
                sender = ""
                date_str = ""
                for h in headers_list:
                    h_name = h.get("name", "").lower()
                    if h_name == "subject":
                        subject = h.get("value", "")
                    elif h_name == "from":
                        sender = h.get("value", "")
                    elif h_name == "date":
                        date_str = h.get("value", "")

                snippet = msg_data.get("snippet", "")

                # Extract plain text & HTML bodies from MIME parts
                body_text = ""
                body_html = ""
                def extract_bodies(part_node):
                    nonlocal body_text, body_html
                    m_type = part_node.get("mimeType", "")
                    b_data = part_node.get("body", {}).get("data")
                    if b_data:
                        try:
                            decoded = _safe_b64decode(b_data).decode("utf-8", errors="replace")
                            if m_type == "text/plain" and not body_text:
                                body_text = decoded
                            elif m_type == "text/html" and not body_html:
                                body_html = decoded
                        except Exception:
                            pass
                    for sub in part_node.get("parts", []):
                        extract_bodies(sub)

                extract_bodies(payload)
                if not body_text and snippet:
                    body_text = snippet

                cat_info = _classify_zepto_email(subject, sender, snippet)
                category = cat_info["category"]
                if category in ingested_counts:
                    ingested_counts[category] += 1
                else:
                    ingested_counts["OPERATIONAL"] += 1

                # Parse body text & HTML metrics
                from earnings_engine.data.zepto_parsers import extract_metrics_from_email_body, parse_zepto_manpower_utilization_html
                body_metrics = extract_metrics_from_email_body(f"{subject} {snippet} {body_text}")
                if category == "MANPOWER_UTILIZATION" and body_html:
                    parsed_manpower = parse_zepto_manpower_utilization_html(body_html, subject=subject)
                    if parsed_manpower.get("metrics"):
                        body_metrics.update(parsed_manpower["metrics"])

                # Format ISO date from subject regex or date header
                iso_date = cat_info.get("record_date") or datetime.now().strftime("%Y-%m-%d")
                if not cat_info.get("record_date") and date_str:
                    try:
                        from email.utils import parsedate_to_datetime
                        dt = parsedate_to_datetime(date_str)
                        iso_date = dt.strftime("%Y-%m-%d")
                    except Exception:
                        pass

                store_name = cat_info.get("store_name") or "JMU-Sainik Colony"
                email_parsed_status = "PENDING"
                email_parsed_count = 0

                # Inspect and download attachments (.xlsx)
                all_parts = []
                def collect_parts(p_list):
                    for p in p_list:
                        all_parts.append(p)
                        if "parts" in p:
                            collect_parts(p["parts"])
                collect_parts(payload.get("parts", []))

                # Collect attachment metadata for email object
                attachments = []
                for p in all_parts:
                    fname = p.get("filename")
                    if fname:
                        attachments.append({
                            "filename": fname,
                            "mime_type": p.get("mimeType", ""),
                            "size_bytes": p.get("body", {}).get("size", 0),
                        })

                has_loss_attachment = any(
                    p.get("filename", "").lower().endswith((".xlsx", ".xlsm")) and
                    ("loss" in p.get("filename", "").lower() or "shrinkage" in p.get("filename", "").lower())
                    for p in all_parts
                )

                # If email contains store metrics text numbers, persist them
                if category == "STORE_METRICS" and (body_metrics.get("sales_gmv") or body_metrics.get("order_count") or body_metrics.get("packer_ipp")):
                    zepto_db.save_store_metrics({
                        "store_name": store_name,
                        "metric_date": iso_date,
                        "sales_gmv": body_metrics.get("sales_gmv", 0.0),
                        "order_count": body_metrics.get("order_count", 0),
                        "aov": body_metrics.get("aov", 0.0),
                        "sla_adherence_pct": body_metrics.get("sla_adherence_pct", 100.0),
                        "packer_ipp": body_metrics.get("packer_ipp", 0.0),
                        "raw_source": "GMAIL_BODY",
                        "source_email_id": msg_id,
                    }, settings=_settings)
                    processed_details["store_metrics_records"] += 1
                    email_parsed_status = "PARSED"
                    email_parsed_count += 1

                # If email contains Manpower Utilization numbers, record in metrics and utilization
                if category == "MANPOWER_UTILIZATION" and (body_metrics.get("packer_d1_hc") or body_metrics.get("packer_ipp") or body_metrics.get("d1_ipp")):
                    packer_hc = float(body_metrics.get("packer_d1_hc") or body_metrics.get("packer_headcount") or 0.0)
                    packer_ipp = float(body_metrics.get("packer_ipp") or body_metrics.get("d1_ipp") or 0.0)
                    flex_deduction = float(body_metrics.get("total_flex_deduction_d1") or body_metrics.get("flex_deductions") or 0.0)
                    if packer_ipp > 0 or packer_hc > 0 or flex_deduction > 0:
                        zepto_db.save_store_metrics({
                            "store_name": store_name,
                            "metric_date": iso_date,
                            "packer_ipp": packer_ipp,
                            "raw_source": "GMAIL_MANPOWER_UTILIZATION",
                            "source_email_id": msg_id,
                        }, settings=_settings)
                        processed_details["store_metrics_records"] += 1
                        email_parsed_status = "PARSED"
                        email_parsed_count += 1

                # If email contains DQ loss / shrinkage text numbers, persist only if no Excel attachment exists (prevents double-counting)
                if category in ("DQ_LOSS", "SHRINKAGE") and body_metrics.get("loss_amount") and not has_loss_attachment:
                    zepto_db.save_loss_record({
                        "store_name": store_name,
                        "record_date": iso_date,
                        "loss_type": category,
                        "category": "EMAIL_INGESTED",
                        "amount": body_metrics.get("loss_amount", 0.0),
                        "sku_count": 1,
                        "notes": f"Ingested from email: {subject[:60]}",
                        "source_email_id": msg_id,
                    }, settings=_settings)
                    processed_details["loss_records"] += 1
                    email_parsed_status = "PARSED"
                    email_parsed_count += 1

                for part in all_parts:
                    fname = part.get("filename", "")
                    if fname.lower().endswith((".xlsx", ".xlsm")):
                        body = part.get("body", {})
                        att_id = body.get("attachmentId")
                        raw_data = body.get("data")

                        if att_id:
                            att_url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{msg_id}/attachments/{att_id}"
                            a_resp = await client.get(att_url, headers=headers)
                            if a_resp.status_code == 200:
                                raw_data = a_resp.json().get("data")

                        if raw_data:
                            file_bytes = _safe_b64decode(raw_data)

                            # Route attachment parser by category or filename
                            if "attendance" in fname.lower() or category == "ATTENDANCE":
                                try:
                                    parsed_att = parse_zepto_attendance_excel(file_bytes, file_name=fname)
                                    saved_att = zepto_db.save_attendance_batch(
                                        parsed_att,
                                        source="GMAIL",
                                        source_email_id=msg_id,
                                        settings=_settings,
                                    )
                                    att_recs = saved_att.get("imported_records", 0)
                                    processed_details["attendance_records"] += att_recs
                                    email_parsed_status = "PARSED"
                                    email_parsed_count += att_recs
                                except Exception as e:
                                    logger.warning("[GMAIL-INGEST] Error parsing attendance attachment %s: %s", fname, e)
                                    if email_parsed_status != "PARSED":
                                        email_parsed_status = "FAILED"

                            elif "metric" in fname.lower() or "manpower" in fname.lower() or "utilization" in fname.lower() or category in ("STORE_METRICS", "MANPOWER_UTILIZATION"):
                                try:
                                    parsed_met = parse_zepto_store_metrics_excel(file_bytes, file_name=fname)
                                    for r in parsed_met.get("records", []):
                                        r["source_email_id"] = msg_id
                                        zepto_db.save_store_metrics(r, settings=_settings)
                                        processed_details["store_metrics_records"] += 1
                                        email_parsed_count += 1

                                    # Persist granular worker records into zepto_manpower_utilization
                                    w_records = parsed_met.get("worker_records", [])
                                    if w_records:
                                        zepto_db.save_manpower_utilization_batch(w_records, settings=_settings)
                                        processed_details["manpower_records"] += len(w_records)
                                        email_parsed_count += len(w_records)

                                    email_parsed_status = "PARSED"
                                except Exception as e:
                                    logger.warning("[GMAIL-INGEST] Error parsing store metrics attachment %s: %s", fname, e)
                                    if email_parsed_status != "PARSED":
                                        email_parsed_status = "FAILED"

                            elif "loss" in fname.lower() or "shrinkage" in fname.lower() or category in ("DQ_LOSS", "SHRINKAGE"):
                                try:
                                    parsed_loss = parse_zepto_loss_shrinkage_excel(file_bytes, file_name=fname)
                                    for r in parsed_loss.get("records", []):
                                        r["source_email_id"] = msg_id
                                        zepto_db.save_loss_record(r, settings=_settings)
                                        processed_details["loss_records"] += 1
                                        email_parsed_count += 1
                                    email_parsed_status = "PARSED"
                                except Exception as e:
                                    logger.warning("[GMAIL-INGEST] Error parsing loss attachment %s: %s", fname, e)
                                    if email_parsed_status != "PARSED":
                                        email_parsed_status = "FAILED"

                emails_to_save.append({
                    "id": msg_id,
                    "thread_id": msg_data.get("threadId"),
                    "store_name": store_name,
                    "subject": subject or "(No Subject)",
                    "from": sender,
                    "date": date_str,
                    "iso_date": iso_date,
                    "month_ym": iso_date[:7],
                    "snippet": snippet,
                    "body_text": body_text,
                    "body_html": body_html,
                    "category": category,
                    "category_label": cat_info.get("category_label", "Operational Update"),
                    "badge_color": cat_info.get("badge_color", "slate"),
                    "icon": cat_info.get("icon", "📧"),
                    "extracted_metrics": body_metrics,
                    "attachments": attachments,
                    "has_attachments": len(attachments) > 0,
                    "parsed_status": email_parsed_status,
                    "parsed_records_count": email_parsed_count,
                    "internal_date": msg_data.get("internalDate"),
                })

            # Persist all ingested emails into zepto_gmail_messages
            if emails_to_save:
                zepto_db.save_gmail_messages(emails_to_save, settings=_settings)

            # Synchronize zepto_employees master roster from unique attendance records
            roster_res = zepto_db.sync_roster_from_attendance(settings=_settings)
            logger.info("[GMAIL-INGEST] Synced employee roster from attendance: %s", roster_res)

            return {
                "success": True,
                "status": "success",
                "message": f"Successfully ingested {processed_details['emails_scanned']} emails for {clean_month} and synchronized metrics to database.",
                "category_counts": ingested_counts,
                "processed_details": processed_details,
                "roster_sync": roster_res,
            }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("[GMAIL-INGEST] Error during bulk email ingestion: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Email ingestion failed: {str(exc)}")


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


# ---------------------------------------------------------------------------
# Attendance Reports & Analytics Endpoints
# ---------------------------------------------------------------------------

@router.post("/api/v1/zepto/attendance/upload", summary="Upload Attendance Report (.xlsx)")
async def upload_attendance_report_endpoint(
    file: UploadFile = File(...),
) -> dict[str, Any]:
    """Upload and parse an Excel attendance report file and persist to database."""
    from earnings_engine.data.zepto_attendance_parser import parse_zepto_attendance_excel

    if not file.filename.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=400, detail="Only Excel .xlsx files are supported.")

    try:
        content = await file.read()
        parsed = parse_zepto_attendance_excel(content, file_name=file.filename)
        saved = zepto_db.save_attendance_batch(parsed, source="UPLOAD", settings=_settings)

        return {
            "success": True,
            "status": "success",
            "import_id": saved["import_id"],
            "store_name": saved["store_name"],
            "total_records": saved["imported_records"],
            "total_employees": saved["total_employees"],
            "date_range": {
                "start": saved["start_date"],
                "end": saved["end_date"],
            },
            "summary": parsed.get("summary", {}),
        }
    except Exception as exc:
        logger.error("[ZEPTO-ATTENDANCE] Error parsing attendance file: %s", exc, exc_info=True)
        raise HTTPException(status_code=400, detail=f"Failed to parse attendance file: {str(exc)}")


@router.get("/api/v1/zepto/attendance/summary", summary="Get Attendance Summary Metrics & KPIs")
async def get_attendance_summary_endpoint(
    store_name: str | None = Query(None, description="Filter by store name"),
    start_date: str | None = Query(None, description="Start date YYYY-MM-DD"),
    end_date: str | None = Query(None, description="End date YYYY-MM-DD"),
    year_month: str | None = Query(None, description="Filter by year-month YYYY-MM"),
) -> dict[str, Any]:
    """Retrieve aggregated attendance rate, active headcount, role breakdown, and daily trends."""
    try:
        summary = zepto_db.get_attendance_summary(
            store_name=store_name,
            start_date=start_date,
            end_date=end_date,
            year_month=year_month,
            settings=_settings,
        )
        return {"success": True, **summary}
    except Exception as exc:
        logger.error("[ZEPTO-ATTENDANCE] Error calculating attendance summary: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/api/v1/zepto/attendance/records", summary="List Detailed Attendance Records")
async def get_attendance_records_endpoint(
    store_name: str | None = Query(None),
    employee_id: str | None = Query(None),
    designation: str | None = Query(None),
    status: str | None = Query(None),
    date: str | None = Query(None),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    year_month: str | None = Query(None, description="Filter by year-month YYYY-MM"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    """Query granular employee punch and attendance status records."""
    try:
        records = zepto_db.get_attendance_records(
            store_name=store_name,
            employee_id=employee_id,
            designation=designation,
            status=status,
            date=date,
            start_date=start_date,
            end_date=end_date,
            year_month=year_month,
            limit=limit,
            offset=offset,
            settings=_settings,
        )
        return {
            "success": True,
            "count": len(records),
            "records": records,
        }
    except Exception as exc:
        logger.error("[ZEPTO-ATTENDANCE] Error fetching attendance records: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/api/v1/zepto/attendance/imports", summary="List Attendance Imports History")
async def get_attendance_imports_endpoint(
    limit: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    """List historical attendance report uploads."""
    try:
        imports = zepto_db.get_attendance_imports(limit=limit, settings=_settings)
        return {"success": True, "count": len(imports), "imports": imports}
    except Exception as exc:
        logger.error("[ZEPTO-ATTENDANCE] Error fetching imports: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.delete("/api/v1/zepto/attendance/imports/{import_id}", summary="Delete Attendance Import")
async def delete_attendance_import_endpoint(import_id: str) -> dict[str, Any]:
    """Delete an attendance import batch and its records."""
    try:
        zepto_db.delete_attendance_import(import_id, settings=_settings)
        return {"success": True, "status": "success", "deleted_id": import_id}
    except Exception as exc:
        logger.error("[ZEPTO-ATTENDANCE] Error deleting import %s: %s", import_id, exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/api/v1/zepto/gmail/sync-attendance", summary="Auto-Sync Attendance Reports from Linked Gmail")
async def sync_attendance_from_gmail_endpoint() -> dict[str, Any]:
    """Search linked dark store Gmail inbox for attendance reports (.xlsx), download attachments, and parse into DB."""
    import base64
    import httpx
    from earnings_engine.data.zepto_attendance_parser import parse_zepto_attendance_excel

    token = zepto_db.get_valid_gmail_token("primary", _settings)
    if not token:
        raise HTTPException(
            status_code=400,
            detail="No active Gmail account connected or Google credentials missing. Please link Gmail in the #gmail tab.",
        )

    headers = {"Authorization": f"Bearer {token}"}
    processed_files = []
    total_imported_records = 0

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # 1. Search for messages with attendance excel attachments
            # Query: has:attachment filename:xlsx (attendance OR muster OR report)
            q = "has:attachment filename:xlsx attendance"
            list_url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages?q={q}&maxResults=10"
            resp = await client.get(list_url, headers=headers)
            if resp.status_code != 200:
                # Fallback to broader query if needed
                list_url = "https://gmail.googleapis.com/gmail/v1/users/me/messages?q=has:attachment filename:xlsx&maxResults=10"
                resp = await client.get(list_url, headers=headers)

            if resp.status_code != 200:
                raise HTTPException(status_code=502, detail=f"Gmail API error: {resp.text}")

            msg_list = resp.json().get("messages", [])
            if not msg_list:
                return {
                    "success": True,
                    "status": "no_new_reports",
                    "message": "No new attendance report emails found in Gmail matching 'attendance'.",
                    "processed_count": 0,
                    "records_imported": 0,
                }

            # 2. Inspect messages for XLSX attachments
            for msg_summary in msg_list[:5]:
                msg_id = msg_summary["id"]
                msg_url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{msg_id}"
                m_resp = await client.get(msg_url, headers=headers)
                if m_resp.status_code != 200:
                    continue

                msg_data = m_resp.json()
                payload = msg_data.get("payload", {})
                parts = payload.get("parts", [])

                # Collect all parts recursively
                all_parts = []
                def collect_parts(p_list):
                    for p in p_list:
                        all_parts.append(p)
                        if "parts" in p:
                            collect_parts(p["parts"])
                collect_parts(parts)

                for part in all_parts:
                    fname = part.get("filename", "")
                    if fname.lower().endswith(".xlsx"):
                        body = part.get("body", {})
                        att_id = body.get("attachmentId")
                        raw_data = body.get("data")

                        if att_id:
                            att_url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{msg_id}/attachments/{att_id}"
                            a_resp = await client.get(att_url, headers=headers)
                            if a_resp.status_code == 200:
                                raw_data = a_resp.json().get("data")

                        if raw_data:
                            # Decode base64url data safely with padding
                            file_bytes = _safe_b64decode(raw_data)
                            parsed = parse_zepto_attendance_excel(file_bytes, file_name=fname)
                            saved = zepto_db.save_attendance_batch(parsed, source="GMAIL", settings=_settings)

                            processed_files.append({
                                "file_name": fname,
                                "store_name": saved["store_name"],
                                "records": saved["imported_records"],
                                "date_range": f"{saved['start_date']} to {saved['end_date']}",
                            })
                            total_imported_records += saved["imported_records"]

        return {
            "success": True,
            "status": "success",
            "message": f"Successfully processed {len(processed_files)} attendance reports from Gmail.",
            "processed_count": len(processed_files),
            "records_imported": total_imported_records,
            "files": processed_files,
        }
    except Exception as exc:
        logger.error("[GMAIL-ATTENDANCE] Sync exception: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Gmail sync failed: {str(exc)}")


# ---------------------------------------------------------------------------
# Employee Drilldown, Store Metrics, Loss & Utilization Endpoints
# ---------------------------------------------------------------------------

@router.get("/api/v1/zepto/attendance/employee/{employee_id}", summary="Get Employee Attendance Detail & 30-Day Punch History")
async def get_employee_attendance_detail_endpoint(
    employee_id: str,
    month: str | None = Query(None),
) -> dict[str, Any]:
    """Retrieve individual employee profile, metrics, risk tier, and punch ledger for slide-out drawer."""
    try:
        detail = zepto_db.get_employee_attendance_detail(employee_id, month=month, settings=_settings)
        if not detail:
            raise HTTPException(status_code=404, detail=f"Employee '{employee_id}' not found.")
        return {"success": True, "detail": detail}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("[ZEPTO-ATTENDANCE] Error fetching employee detail %s: %s", employee_id, exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/api/v1/zepto/metrics/summary", summary="Get Daily Dark Store Scorecard Metrics")
async def get_store_metrics_summary_endpoint(
    store_name: str | None = Query(None),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    month: str | None = Query(None),
) -> dict[str, Any]:
    """Retrieve daily sales GMV, orders, AOV, IPP, and SLA adherence trends with month filtering."""
    try:
        summary = zepto_db.get_store_metrics_summary(
            store_name=store_name,
            start_date=start_date,
            end_date=end_date,
            month=month,
            settings=_settings,
        )
        return {"success": True, **summary}
    except Exception as exc:
        logger.error("[ZEPTO-METRICS] Error fetching store metrics summary: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/api/v1/zepto/metrics", summary="Save Dark Store Daily Metric Record")
async def create_store_metrics_endpoint(record: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Insert or update a store performance scorecard row."""
    try:
        saved = zepto_db.save_store_metrics(record, settings=_settings)
        return {"success": True, **saved}
    except Exception as exc:
        logger.error("[ZEPTO-METRICS] Error saving store metric: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/api/v1/zepto/loss/summary", summary="Get DQ Loss, Shrinkage & Waste Breakdown")
async def get_loss_summary_endpoint(
    month: str | None = Query(None),
    store_name: str | None = Query(None),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    loss_type: str | None = Query(None),
    category: str | None = Query(None),
) -> dict[str, Any]:
    """Retrieve aggregated quality loss, shrinkage, and damage categorization with email-vs-excel reconciliation."""
    try:
        summary = zepto_db.get_loss_summary(
            month=month,
            store_name=store_name,
            start_date=start_date,
            end_date=end_date,
            loss_type=loss_type,
            category=category,
            settings=_settings,
        )
        return {"success": True, **summary}
    except Exception as exc:
        logger.error("[ZEPTO-LOSS] Error fetching loss summary: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/api/v1/zepto/loss/records", summary="Get Stored Itemized Loss & Excel Records")
async def get_loss_records_endpoint(
    month: str | None = Query(None),
    store_name: str | None = Query(None),
    category: str | None = Query(None),
    loss_type: str | None = Query(None),
    date: str | None = Query(None),
    search: str | None = Query(None),
    limit: int = Query(500, ge=1, le=2000),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    """Retrieve paginated and searchable itemized stored Excel loss and defect records."""
    try:
        data = zepto_db.get_loss_records(
            month=month,
            store_name=store_name,
            category=category,
            loss_type=loss_type,
            date=date,
            search=search,
            limit=limit,
            offset=offset,
            settings=_settings,
        )
        return {"success": True, **data}
    except Exception as exc:
        logger.error("[ZEPTO-LOSS-RECORDS] Error fetching loss records: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/api/v1/zepto/loss", summary="Record Damage, DQ Loss or Shrinkage")
async def create_loss_record_endpoint(record: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Insert a new loss or shrinkage record."""
    try:
        saved = zepto_db.save_loss_record(record, settings=_settings)
        return {"success": True, **saved}
    except Exception as exc:
        logger.error("[ZEPTO-LOSS] Error saving loss record: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/api/v1/zepto/utilization/summary", summary="Get Manpower Utilization & IPP Summary")
async def get_manpower_utilization_summary_endpoint(
    store_name: str | None = Query(None),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    month: str | None = Query(None),
) -> dict[str, Any]:
    """Retrieve items picked, active picker hours, idle hours, and average IPP with month filtering."""
    try:
        summary = zepto_db.get_manpower_utilization_summary(
            store_name=store_name,
            start_date=start_date,
            end_date=end_date,
            month=month,
            settings=_settings,
        )
        return {"success": True, **summary}
    except Exception as exc:
        logger.error("[ZEPTO-UTILIZATION] Error fetching manpower utilization summary: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/api/v1/zepto/utilization", summary="Save Manpower Utilization Record")
async def create_manpower_utilization_endpoint(record: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Insert a new daily manpower utilization and picking productivity record."""
    try:
        saved = zepto_db.save_manpower_utilization(record, settings=_settings)
        return {"success": True, **saved}
    except Exception as exc:
        logger.error("[ZEPTO-UTILIZATION] Error saving manpower utilization record: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Store Metrics & DQ Loss Excel Upload Endpoints
# ---------------------------------------------------------------------------

@router.post("/api/v1/zepto/metrics/upload", summary="Upload Store Metrics Report (.xlsx)")
async def upload_store_metrics_excel_endpoint(file: UploadFile = File(...)) -> dict[str, Any]:
    """Upload and parse an Excel daily store metric report."""
    from earnings_engine.data.zepto_parsers import parse_zepto_store_metrics_excel

    if not file.filename.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=400, detail="Only Excel .xlsx files are supported.")

    try:
        content = await file.read()
        parsed = parse_zepto_store_metrics_excel(content, file_name=file.filename)
        saved_count = 0
        for rec in parsed.get("records", []):
            zepto_db.save_store_metrics(rec, settings=_settings)
            saved_count += 1

        return {
            "success": True,
            "status": "success",
            "store_name": parsed.get("store_name"),
            "total_records": parsed.get("total_records", 0),
            "saved_count": saved_count,
        }
    except Exception as exc:
        logger.error("[ZEPTO-METRICS] Error parsing store metrics file: %s", exc, exc_info=True)
        raise HTTPException(status_code=400, detail=f"Failed to parse store metrics: {str(exc)}")


@router.post("/api/v1/zepto/loss/upload", summary="Upload DQ Loss / Shrinkage Report (.xlsx)")
async def upload_loss_shrinkage_excel_endpoint(file: UploadFile = File(...)) -> dict[str, Any]:
    """Upload and parse an Excel DQ loss, defect, and shrinkage report."""
    from earnings_engine.data.zepto_parsers import parse_zepto_loss_shrinkage_excel

    if not file.filename.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=400, detail="Only Excel .xlsx files are supported.")

    try:
        content = await file.read()
        parsed = parse_zepto_loss_shrinkage_excel(content, file_name=file.filename)
        saved_count = 0
        for rec in parsed.get("records", []):
            zepto_db.save_loss_record(rec, settings=_settings)
            saved_count += 1

        return {
            "success": True,
            "status": "success",
            "store_name": parsed.get("store_name"),
            "total_records": parsed.get("total_records", 0),
            "saved_count": saved_count,
        }
    except Exception as exc:
        logger.error("[ZEPTO-LOSS] Error parsing loss file: %s", exc, exc_info=True)
        raise HTTPException(status_code=400, detail=f"Failed to parse loss report: {str(exc)}")




