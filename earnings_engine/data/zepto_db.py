"""Zepto Store Management Hub — Database Schema & Data Access Layer.

Handles persistence, aggregations, MoM salary tracking, attrition rates,
spend-per-person metrics, hiring pipeline conversions, and 50-50 partner equity ledger.
"""

from __future__ import annotations

import logging
import math
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from earnings_engine.config import Settings
from earnings_engine.data.catalysts_news import _connect

logger = logging.getLogger(__name__)

ZEPTO_TOTAL_SECURITY_TARGET = 7500000.0  # ₹75 Lakhs total franchise deposit
PARTNER_EQUITY_SHARE = 0.50             # 50% equity share each (₹37.5L)

# ===========================================================================
# Centralized Partners Configuration (Single Source of Truth)
# ===========================================================================
PARTNERS_CONFIG = {
    "partner_1": {
        "id": "partner_1",
        "name": "Jatin Abrol",
        "label": "Jatin Abrol (Founder)",
        "role": "Founder",
        "initials": "JA",
        "share_pct": 50.0,
        "color": "purple",
    },
    "partner_2": {
        "id": "partner_2",
        "name": "Harshiv Bargotra",
        "label": "Harshiv Bargotra",
        "role": "Partner",
        "initials": "HB",
        "share_pct": 50.0,
        "color": "pink",
    },
}

PARTNER_1_NAME = PARTNERS_CONFIG["partner_1"]["name"]
PARTNER_2_NAME = PARTNERS_CONFIG["partner_2"]["name"]

UPLOAD_DIR = Path("data/zepto/uploads")


def _get_upload_dir() -> Path:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    return UPLOAD_DIR


def ensure_zepto_schema(settings: Settings | None = None) -> None:
    """Create Zepto Store tables and populate seed data if brand new."""
    settings = settings or Settings()
    with _connect(settings) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS zepto_employees (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                role TEXT NOT NULL,
                phone TEXT,
                email TEXT,
                joining_date TEXT NOT NULL,
                resignation_date TEXT,
                resignation_reason TEXT,
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                rating REAL DEFAULT 5.0,
                base_salary_monthly REAL NOT NULL DEFAULT 0.0,
                current_month_bonus REAL DEFAULT 0.0,
                aadhar_doc_url TEXT,
                resume_doc_url TEXT,
                photo_url TEXT,
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS zepto_salaries (
                id TEXT PRIMARY KEY,
                employee_id TEXT NOT NULL,
                year_month TEXT NOT NULL,
                base_amount REAL NOT NULL,
                bonus_amount REAL DEFAULT 0.0,
                deductions REAL DEFAULT 0.0,
                net_paid REAL NOT NULL,
                payment_date TEXT,
                payment_status TEXT DEFAULT 'PAID',
                payment_mode TEXT DEFAULT 'BANK_TRANSFER',
                notes TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(employee_id) REFERENCES zepto_employees(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS zepto_expenses (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                category TEXT NOT NULL,
                amount REAL NOT NULL,
                expense_date TEXT NOT NULL,
                incurred_by TEXT NOT NULL,
                document_url TEXT,
                document_filename TEXT,
                is_reimbursed INTEGER DEFAULT 0,
                notes TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS zepto_candidates (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                phone TEXT,
                email TEXT,
                target_role TEXT NOT NULL,
                expected_salary REAL,
                rating REAL DEFAULT 4.0,
                stage TEXT NOT NULL DEFAULT 'APPLIED',
                resume_doc_url TEXT,
                aadhar_doc_url TEXT,
                notes TEXT,
                interview_date TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS zepto_security_capital (
                id TEXT PRIMARY KEY,
                tranche_title TEXT NOT NULL,
                amount REAL NOT NULL,
                payment_date TEXT NOT NULL,
                partner_name TEXT NOT NULL,
                payment_mode TEXT DEFAULT 'NEFT_RTGS',
                reference_utr TEXT,
                proof_doc_url TEXT,
                notes TEXT,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_zepto_emp_status ON zepto_employees(status);
            CREATE INDEX IF NOT EXISTS idx_zepto_emp_role ON zepto_employees(role);
            CREATE INDEX IF NOT EXISTS idx_zepto_sal_emp ON zepto_salaries(employee_id, year_month);
            CREATE INDEX IF NOT EXISTS idx_zepto_exp_date ON zepto_expenses(expense_date);
            CREATE INDEX IF NOT EXISTS idx_zepto_cand_stage ON zepto_candidates(stage);
        """)

        # Migrate existing Partner 1 / Partner 2 rows to centralized names
        conn.execute("UPDATE zepto_expenses SET incurred_by = ? WHERE incurred_by LIKE '%Partner 1%' OR incurred_by LIKE '%Jatin%'", (PARTNER_1_NAME,))
        conn.execute("UPDATE zepto_expenses SET incurred_by = ? WHERE incurred_by LIKE '%Partner 2%' OR incurred_by LIKE '%Harshiv%'", (PARTNER_2_NAME,))
        conn.execute("UPDATE zepto_security_capital SET partner_name = ? WHERE partner_name LIKE '%Partner 1%' OR partner_name LIKE '%Jatin%'", (PARTNER_1_NAME,))
        conn.execute("UPDATE zepto_security_capital SET partner_name = ? WHERE partner_name LIKE '%Partner 2%' OR partner_name LIKE '%Harshiv%'", (PARTNER_2_NAME,))

        # Check if seed data needed
        row = conn.execute("SELECT COUNT(*) FROM zepto_employees").fetchone()
        if row and row[0] == 0:
            _seed_sample_data(conn)


def _seed_sample_data(conn: sqlite3.Connection) -> None:
    """Insert initial starter seed records for store setup demonstration."""
    now_iso = datetime.now(timezone.utc).isoformat()
    
    # 1. Sample Staff
    employees = [
        ("emp_01", "Rajesh Kumar", "SHIFT_INCHARGE", "+91 98765 43210", "rajesh.k@darkstore.in", "2026-06-01", None, None, "ACTIVE", 4.9, 32000.0, 3000.0, None, None, None, "Lead night shift incharge, high inventory accuracy", now_iso, now_iso),
        ("emp_02", "Amit Sharma", "PICKER", "+91 98123 45678", "amit.s@darkstore.in", "2026-06-15", None, None, "ACTIVE", 4.8, 18500.0, 1500.0, None, None, None, "Top picker: avg 48 items/hour", now_iso, now_iso),
        ("emp_03", "Vikas Verma", "PICKER", "+91 98234 56789", "vikas.v@darkstore.in", "2026-07-01", None, None, "ACTIVE", 4.5, 18000.0, 500.0, None, None, None, "Morning shift picker", now_iso, now_iso),
        ("emp_04", "Sunil Yadav", "PACKER", "+91 98345 67890", "sunil.y@darkstore.in", "2026-06-10", None, None, "ACTIVE", 4.7, 17500.0, 1000.0, None, None, None, "Bagging & cold-chain packing lead", now_iso, now_iso),
        ("emp_05", "Pooja Singh", "STORE_MANAGER", "+91 98456 78901", "pooja.s@darkstore.in", "2026-05-20", None, None, "ACTIVE", 5.0, 48000.0, 5000.0, None, None, None, "Overall store operations manager", now_iso, now_iso),
        ("emp_06", "Deepak Patel", "PICKER", "+91 98567 89012", "deepak.p@darkstore.in", "2026-06-20", "2026-08-01", "Relocated to hometown", "RESIGNED", 3.8, 18000.0, 0.0, None, None, None, "Resigned due to personal relocation", now_iso, now_iso),
    ]
    conn.executemany(
        """
        INSERT INTO zepto_employees (
            id, name, role, phone, email, joining_date, resignation_date, resignation_reason,
            status, rating, base_salary_monthly, current_month_bonus, aadhar_doc_url,
            resume_doc_url, photo_url, notes, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        employees
    )

    # 2. Sample Salaries
    salaries = [
        (str(uuid.uuid4()), "emp_01", "2026-07", 32000.0, 2500.0, 0.0, 34500.0, "2026-08-02", "PAID", "BANK_TRANSFER", "July performance reward included", now_iso),
        (str(uuid.uuid4()), "emp_01", "2026-08", 32000.0, 3000.0, 0.0, 35000.0, "2026-08-28", "PAID", "BANK_TRANSFER", "August on-time shift incentive", now_iso),
        (str(uuid.uuid4()), "emp_02", "2026-07", 18500.0, 1200.0, 0.0, 19700.0, "2026-08-02", "PAID", "BANK_TRANSFER", "July picker speed bonus", now_iso),
        (str(uuid.uuid4()), "emp_02", "2026-08", 18500.0, 1500.0, 0.0, 20000.0, "2026-08-28", "PAID", "BANK_TRANSFER", "August UPT bonus", now_iso),
        (str(uuid.uuid4()), "emp_05", "2026-07", 48000.0, 4000.0, 0.0, 52000.0, "2026-08-02", "PAID", "BANK_TRANSFER", "Monthly manager compensation", now_iso),
    ]
    conn.executemany(
        """
        INSERT INTO zepto_salaries (
            id, employee_id, year_month, base_amount, bonus_amount, deductions,
            net_paid, payment_date, payment_status, payment_mode, notes, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        salaries
    )

    # 3. Sample Store Expenses
    expenses = [
        (str(uuid.uuid4()), "Initial Picker Onboarding & Zepto Training Batch", "TRAINING", 45000.0, "2026-06-05", PARTNER_1_NAME, None, "training_receipt.pdf", 1, "Offsite training & simulator software fee", now_iso),
        (str(uuid.uuid4()), "Staff Uniforms, Thermal Bags & Reflective Vests", "UNIFORMS_GEAR", 28500.0, "2026-06-12", PARTNER_2_NAME, None, "uniform_invoice.pdf", 1, "20 sets of customized shirts and thermal jackets", now_iso),
        (str(uuid.uuid4()), "Heavy-Duty Warehouse Racks & Bins Installation", "EQUIPMENT", 125000.0, "2026-06-18", PARTNER_1_NAME, None, "racks_bill.pdf", 1, "Aisle A-D high density racking system", now_iso),
        (str(uuid.uuid4()), "Staff Refreshment & Breakroom Tea/Snacks (Monthly)", "SNACKS_WELFARE", 8500.0, "2026-08-15", "STORE_CASH", None, None, 1, "Monthly pantry items & energy drinks", now_iso),
        (str(uuid.uuid4()), "Store Deep Cleaning & Pest Control Service", "STORE_MAINTENANCE", 12000.0, "2026-08-20", PARTNER_2_NAME, None, "pest_control_bill.pdf", 1, "Bi-weekly warehouse pest safety compliance", now_iso),
    ]
    conn.executemany(
        """
        INSERT INTO zepto_expenses (
            id, title, category, amount, expense_date, incurred_by,
            document_url, document_filename, is_reimbursed, notes, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        expenses
    )

    # 4. Sample Hiring Candidates
    candidates = [
        (str(uuid.uuid4()), "Rohit Mehra", "+91 99001 12233", "rohit.m@gmail.com", "PICKER", 18500.0, 4.8, "INTERVIEWING", None, None, "1 yr experience at Blinkit dark store", "2026-08-30", now_iso, now_iso),
        (str(uuid.uuid4()), "Manish Tiwari", "+91 99112 23344", "manish.t@gmail.com", "SHIFT_INCHARGE", 30000.0, 4.6, "SHORTLISTED", None, None, "Strong logistics background, clear communication", "2026-08-29", now_iso, now_iso),
        (str(uuid.uuid4()), "Kavita Soni", "+91 99223 34455", "kavita.s@gmail.com", "PACKER", 17500.0, 4.2, "APPLIED", None, None, "Applied via referral, local resident", None, now_iso, now_iso),
    ]
    conn.executemany(
        """
        INSERT INTO zepto_candidates (
            id, name, phone, email, target_role, expected_salary, rating,
            stage, resume_doc_url, aadhar_doc_url, notes, interview_date, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        candidates
    )

    # 5. Sample Security Capital Tranches (50-50 Partner Equity Split)
    capital_tranches = [
        (str(uuid.uuid4()), "Initial Franchise Security Tranche 1", 2000000.0, "2026-05-15", PARTNER_1_NAME, "NEFT_RTGS", "HDFC202605159812", None, "First deposit directly to Zepto Operations Escrow", now_iso),
        (str(uuid.uuid4()), "Initial Franchise Security Tranche 1 Match", 2000000.0, "2026-05-16", PARTNER_2_NAME, "NEFT_RTGS", "ICIC202605161142", None, "50% equity matching tranche", now_iso),
        (str(uuid.uuid4()), "Dark Store Capex & Inventory Deposit Tranche 2", 1000000.0, "2026-06-10", PARTNER_1_NAME, "NEFT_RTGS", "HDFC202606105521", None, "Second installment towards ₹75L commitment", now_iso),
        (str(uuid.uuid4()), "Dark Store Capex & Inventory Deposit Tranche 2 Match", 1000000.0, "2026-06-12", PARTNER_2_NAME, "NEFT_RTGS", "ICIC202606127891", None, "Matching second installment", now_iso),
    ]
    conn.executemany(
        """
        INSERT INTO zepto_security_capital (
            id, tranche_title, amount, payment_date, partner_name,
            payment_mode, reference_utr, proof_doc_url, notes, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        capital_tranches
    )


# ---------------------------------------------------------------------------
# Overview & Store Analytics
# ---------------------------------------------------------------------------

def get_zepto_overview(settings: Settings | None = None) -> dict[str, Any]:
    """Calculate aggregated store intelligence, headcount, attrition, spend metrics & equity."""
    settings = settings or Settings()
    ensure_zepto_schema(settings)
    with _connect(settings) as conn:
        conn.row_factory = sqlite3.Row

        # Headcounts
        emp_rows = conn.execute("SELECT status, role, COUNT(*) as cnt FROM zepto_employees GROUP BY status, role").fetchall()
        active_count = 0
        resigned_count = 0
        probation_count = 0
        role_breakdown: dict[str, int] = {}
        for r in emp_rows:
            st = r["status"]
            cnt = r["cnt"]
            if st == "ACTIVE":
                active_count += cnt
                role_breakdown[r["role"]] = role_breakdown.get(r["role"], 0) + cnt
            elif st == "RESIGNED":
                resigned_count += cnt
            elif st == "ON_PROBATION":
                probation_count += cnt
                active_count += cnt

        total_staff_ever = active_count + resigned_count
        # Attrition / Iteration rate
        attrition_rate = round((resigned_count / max(1, total_staff_ever)) * 100, 1)

        # Average Rating
        avg_rating_row = conn.execute("SELECT AVG(rating) as avg_r FROM zepto_employees WHERE status = 'ACTIVE'").fetchone()
        avg_rating = round(float(avg_rating_row["avg_r"] or 5.0), 1)

        # Monthly Payroll
        payroll_row = conn.execute("SELECT SUM(base_salary_monthly + current_month_bonus) as total_pay FROM zepto_employees WHERE status = 'ACTIVE'").fetchone()
        current_monthly_payroll = float(payroll_row["total_pay"] or 0.0)

        # Total Store Expenses
        exp_row = conn.execute("SELECT SUM(amount) as total_exp FROM zepto_expenses").fetchone()
        total_expenses = float(exp_row["total_exp"] or 0.0)

        # Training Specific Expenses
        training_row = conn.execute("SELECT SUM(amount) as train_exp FROM zepto_expenses WHERE category = 'TRAINING'").fetchone()
        training_expenses = float(training_row["train_exp"] or 0.0)

        # Spend Per Active Employee Insight
        spend_per_employee = round(total_expenses / max(1, active_count), 2)

        # Candidate Pipeline Counts
        cand_rows = conn.execute("SELECT stage, COUNT(*) as cnt FROM zepto_candidates GROUP BY stage").fetchall()
        candidate_counts = {r["stage"]: r["cnt"] for r in cand_rows}
        active_candidates = sum(cnt for stage, cnt in candidate_counts.items() if stage not in ("REJECTED", "HIRED"))

        # Security Deposit & 50-50 Partner Equity
        sec_rows = conn.execute("SELECT partner_name, SUM(amount) as partner_total FROM zepto_security_capital GROUP BY partner_name").fetchall()
        partner_1_paid = 0.0
        partner_2_paid = 0.0
        for r in sec_rows:
            p_name = r["partner_name"].strip().lower()
            if "jatin" in p_name or "1" in p_name or "founder" in p_name:
                partner_1_paid += float(r["partner_total"] or 0.0)
            else:
                partner_2_paid += float(r["partner_total"] or 0.0)

        total_capital_deposited = partner_1_paid + partner_2_paid
        target_capital = ZEPTO_TOTAL_SECURITY_TARGET  # ₹75,00,000
        target_per_partner = target_capital * PARTNER_EQUITY_SHARE  # ₹37,50,000
        capital_progress_pct = round((total_capital_deposited / target_capital) * 100, 1)
        remaining_capital = max(0.0, target_capital - total_capital_deposited)

        partner_1_progress = round((partner_1_paid / target_per_partner) * 100, 1)
        partner_2_progress = round((partner_2_paid / target_per_partner) * 100, 1)
        equalization_diff = round(partner_1_paid - partner_2_paid, 2)

        return {
            "config": {
                "partners": PARTNERS_CONFIG,
                "target_security_deposit": target_capital,
                "target_per_partner": target_per_partner,
            },
            "headcount": {
                "active": active_count,
                "resigned": resigned_count,
                "probation": probation_count,
                "total_ever": total_staff_ever,
                "attrition_rate_pct": attrition_rate,
                "avg_rating": avg_rating,
                "role_breakdown": role_breakdown,
                "monthly_payroll": current_monthly_payroll,
            },
            "expenses": {
                "total_expenses": total_expenses,
                "training_expenses": training_expenses,
                "spend_per_employee": spend_per_employee,
            },
            "candidates": {
                "active_pipeline": active_candidates,
                "breakdown": candidate_counts,
            },
            "security_capital": {
                "target_total": target_capital,
                "target_per_partner": target_per_partner,
                "total_deposited": total_capital_deposited,
                "remaining_pending": remaining_capital,
                "progress_pct": capital_progress_pct,
                "partner_1": {
                    "id": "partner_1",
                    "name": PARTNERS_CONFIG["partner_1"]["name"],
                    "label": PARTNERS_CONFIG["partner_1"]["label"],
                    "initials": PARTNERS_CONFIG["partner_1"]["initials"],
                    "paid": partner_1_paid,
                    "target": target_per_partner,
                    "progress_pct": partner_1_progress,
                    "remaining": max(0.0, target_per_partner - partner_1_paid),
                },
                "partner_2": {
                    "id": "partner_2",
                    "name": PARTNERS_CONFIG["partner_2"]["name"],
                    "label": PARTNERS_CONFIG["partner_2"]["label"],
                    "initials": PARTNERS_CONFIG["partner_2"]["initials"],
                    "paid": partner_2_paid,
                    "target": target_per_partner,
                    "progress_pct": partner_2_progress,
                    "remaining": max(0.0, target_per_partner - partner_2_paid),
                },
                "equalization": {
                    "difference": equalization_diff,
                    "is_equal": abs(equalization_diff) < 1.0,
                    "status": "Balanced (50-50)" if abs(equalization_diff) < 1.0 else (
                        f"{PARTNERS_CONFIG['partner_1']['name']} is ahead by ₹{equalization_diff:,.0f}"
                        if equalization_diff > 0
                        else f"{PARTNERS_CONFIG['partner_2']['name']} is ahead by ₹{abs(equalization_diff):,.0f}"
                    ),
                }
            },
            "as_of": datetime.now(timezone.utc).isoformat(),
        }


# ---------------------------------------------------------------------------
# Employee Management & Salaries
# ---------------------------------------------------------------------------

def get_employees(
    role: str | None = None,
    status: str | None = None,
    search: str | None = None,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """Retrieve employees with optional role, status, and name/phone search."""
    settings = settings or Settings()
    ensure_zepto_schema(settings)
    with _connect(settings) as conn:
        conn.row_factory = sqlite3.Row
        query = "SELECT * FROM zepto_employees WHERE 1=1"
        params: list[Any] = []

        if role and role.upper() != "ALL":
            query += " AND role = ?"
            params.append(role.upper())
        if status and status.upper() != "ALL":
            query += " AND status = ?"
            params.append(status.upper())
        if search:
            query += " AND (name LIKE ? OR phone LIKE ? OR email LIKE ?)"
            term = f"%{search.strip()}%"
            params.extend([term, term, term])

        query += " ORDER BY status ASC, role ASC, name ASC"
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


def get_employee_by_id(emp_id: str, settings: Settings | None = None) -> dict[str, Any] | None:
    """Get single employee record by ID."""
    settings = settings or Settings()
    with _connect(settings) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM zepto_employees WHERE id = ?", (emp_id,)).fetchone()
        return dict(row) if row else None


def create_employee(data: dict[str, Any], settings: Settings | None = None) -> dict[str, Any]:
    """Create a new employee record."""
    settings = settings or Settings()
    ensure_zepto_schema(settings)
    emp_id = data.get("id") or f"emp_{uuid.uuid4().hex[:8]}"
    now_iso = datetime.now(timezone.utc).isoformat()

    with _connect(settings) as conn:
        conn.execute(
            """
            INSERT INTO zepto_employees (
                id, name, role, phone, email, joining_date, resignation_date,
                resignation_reason, status, rating, base_salary_monthly,
                current_month_bonus, aadhar_doc_url, resume_doc_url, photo_url,
                notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                emp_id,
                data.get("name", "New Employee").strip(),
                data.get("role", "PICKER").strip().upper(),
                data.get("phone", ""),
                data.get("email", ""),
                data.get("joining_date", datetime.now().strftime("%Y-%m-%d")),
                data.get("resignation_date"),
                data.get("resignation_reason"),
                data.get("status", "ACTIVE").upper(),
                float(data.get("rating", 5.0)),
                float(data.get("base_salary_monthly", 0.0)),
                float(data.get("current_month_bonus", 0.0)),
                data.get("aadhar_doc_url"),
                data.get("resume_doc_url"),
                data.get("photo_url"),
                data.get("notes", ""),
                now_iso,
                now_iso,
            )
        )
    return get_employee_by_id(emp_id, settings) or {"id": emp_id}


def update_employee(emp_id: str, data: dict[str, Any], settings: Settings | None = None) -> dict[str, Any] | None:
    """Update employee details, ratings, salary, or record resignation."""
    settings = settings or Settings()
    now_iso = datetime.now(timezone.utc).isoformat()
    fields = []
    params = []

    for key in (
        "name", "role", "phone", "email", "joining_date", "resignation_date",
        "resignation_reason", "status", "rating", "base_salary_monthly",
        "current_month_bonus", "aadhar_doc_url", "resume_doc_url", "photo_url", "notes"
    ):
        if key in data:
            fields.append(f"{key} = ?")
            params.append(data[key])

    if not fields:
        return get_employee_by_id(emp_id, settings)

    fields.append("updated_at = ?")
    params.append(now_iso)
    params.append(emp_id)

    with _connect(settings) as conn:
        conn.execute(f"UPDATE zepto_employees SET {', '.join(fields)} WHERE id = ?", params)

    return get_employee_by_id(emp_id, settings)


def add_employee_bonus(emp_id: str, bonus_amount: float, notes: str | None = None, settings: Settings | None = None) -> dict[str, Any] | None:
    """Award instant performance bonus to an employee."""
    settings = settings or Settings()
    with _connect(settings) as conn:
        conn.execute(
            "UPDATE zepto_employees SET current_month_bonus = current_month_bonus + ?, updated_at = ? WHERE id = ?",
            (float(bonus_amount), datetime.now(timezone.utc).isoformat(), emp_id)
        )
    return get_employee_by_id(emp_id, settings)


def get_employee_salaries(emp_id: str, settings: Settings | None = None) -> list[dict[str, Any]]:
    """Retrieve Month-on-Month salary history for an employee."""
    settings = settings or Settings()
    ensure_zepto_schema(settings)
    with _connect(settings) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM zepto_salaries WHERE employee_id = ? ORDER BY year_month DESC",
            (emp_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def record_employee_salary(emp_id: str, salary_data: dict[str, Any], settings: Settings | None = None) -> dict[str, Any]:
    """Record or update a monthly salary slip for an employee."""
    settings = settings or Settings()
    ensure_zepto_schema(settings)
    sal_id = salary_data.get("id") or str(uuid.uuid4())
    year_month = salary_data.get("year_month", datetime.now().strftime("%Y-%m"))
    base = float(salary_data.get("base_amount", 0.0))
    bonus = float(salary_data.get("bonus_amount", 0.0))
    deductions = float(salary_data.get("deductions", 0.0))
    net_paid = round(base + bonus - deductions, 2)
    now_iso = datetime.now(timezone.utc).isoformat()

    with _connect(settings) as conn:
        conn.execute(
            """
            INSERT INTO zepto_salaries (
                id, employee_id, year_month, base_amount, bonus_amount, deductions,
                net_paid, payment_date, payment_status, payment_mode, notes, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                base_amount = excluded.base_amount,
                bonus_amount = excluded.bonus_amount,
                deductions = excluded.deductions,
                net_paid = excluded.net_paid,
                payment_date = excluded.payment_date,
                payment_status = excluded.payment_status,
                notes = excluded.notes
            """,
            (
                sal_id, emp_id, year_month, base, bonus, deductions, net_paid,
                salary_data.get("payment_date", datetime.now().strftime("%Y-%m-%d")),
                salary_data.get("payment_status", "PAID"),
                salary_data.get("payment_mode", "BANK_TRANSFER"),
                salary_data.get("notes", ""),
                now_iso
            )
        )
    return {"id": sal_id, "employee_id": emp_id, "year_month": year_month, "net_paid": net_paid}


def delete_employee(emp_id: str, settings: Settings | None = None) -> bool:
    """Delete an employee and their associated salary history."""
    settings = settings or Settings()
    with _connect(settings) as conn:
        conn.execute("DELETE FROM zepto_salaries WHERE employee_id = ?", (emp_id,))
        conn.execute("DELETE FROM zepto_employees WHERE id = ?", (emp_id,))
    return True


# ---------------------------------------------------------------------------
# Store Expenses Management
# ---------------------------------------------------------------------------

def get_expenses(
    category: str | None = None,
    incurred_by: str | None = None,
    search: str | None = None,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """Retrieve all store expenses with optional filters."""
    settings = settings or Settings()
    ensure_zepto_schema(settings)
    with _connect(settings) as conn:
        conn.row_factory = sqlite3.Row
        query = "SELECT * FROM zepto_expenses WHERE 1=1"
        params: list[Any] = []

        if category and category.upper() != "ALL":
            query += " AND category = ?"
            params.append(category.upper())
        if incurred_by and incurred_by.upper() != "ALL":
            query += " AND incurred_by LIKE ?"
            params.append(f"%{incurred_by}%")
        if search:
            query += " AND (title LIKE ? OR notes LIKE ?)"
            term = f"%{search.strip()}%"
            params.extend([term, term])

        query += " ORDER BY expense_date DESC, created_at DESC"
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


def create_expense(data: dict[str, Any], settings: Settings | None = None) -> dict[str, Any]:
    """Record a store expense with receipt document attachment."""
    settings = settings or Settings()
    ensure_zepto_schema(settings)
    exp_id = data.get("id") or str(uuid.uuid4())
    now_iso = datetime.now(timezone.utc).isoformat()

    with _connect(settings) as conn:
        conn.execute(
            """
            INSERT INTO zepto_expenses (
                id, title, category, amount, expense_date, incurred_by,
                document_url, document_filename, is_reimbursed, notes, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                exp_id,
                data.get("title", "Store Expense").strip(),
                data.get("category", "OPERATIONAL").strip().upper(),
                float(data.get("amount", 0.0)),
                data.get("expense_date", datetime.now().strftime("%Y-%m-%d")),
                data.get("incurred_by", "Jatin Abrol").strip(),
                data.get("document_url"),
                data.get("document_filename"),
                int(data.get("is_reimbursed", 0)),
                data.get("notes", ""),
                now_iso,
            )
        )
    return {"id": exp_id, "title": data.get("title"), "amount": data.get("amount")}


def delete_expense(exp_id: str, settings: Settings | None = None) -> bool:
    """Delete a store expense record."""
    settings = settings or Settings()
    with _connect(settings) as conn:
        conn.execute("DELETE FROM zepto_expenses WHERE id = ?", (exp_id,))
    return True


# ---------------------------------------------------------------------------
# Candidates (Hiring Pipeline)
# ---------------------------------------------------------------------------

def get_candidates(
    stage: str | None = None,
    target_role: str | None = None,
    search: str | None = None,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """Retrieve prospective candidates in the hiring pipeline."""
    settings = settings or Settings()
    ensure_zepto_schema(settings)
    with _connect(settings) as conn:
        conn.row_factory = sqlite3.Row
        query = "SELECT * FROM zepto_candidates WHERE 1=1"
        params: list[Any] = []

        if stage and stage.upper() != "ALL":
            query += " AND stage = ?"
            params.append(stage.upper())
        if target_role and target_role.upper() != "ALL":
            query += " AND target_role = ?"
            params.append(target_role.upper())
        if search:
            query += " AND (name LIKE ? OR phone LIKE ? OR email LIKE ?)"
            term = f"%{search.strip()}%"
            params.extend([term, term, term])

        query += " ORDER BY created_at DESC"
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


def create_candidate(data: dict[str, Any], settings: Settings | None = None) -> dict[str, Any]:
    """Add a new candidate into the hiring pipeline."""
    settings = settings or Settings()
    ensure_zepto_schema(settings)
    cand_id = data.get("id") or str(uuid.uuid4())
    now_iso = datetime.now(timezone.utc).isoformat()

    with _connect(settings) as conn:
        conn.execute(
            """
            INSERT INTO zepto_candidates (
                id, name, phone, email, target_role, expected_salary, rating,
                stage, resume_doc_url, aadhar_doc_url, notes, interview_date, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cand_id,
                data.get("name", "New Candidate").strip(),
                data.get("phone", ""),
                data.get("email", ""),
                data.get("target_role", "PICKER").strip().upper(),
                float(data.get("expected_salary", 18000.0)) if data.get("expected_salary") else None,
                float(data.get("rating", 4.0)),
                data.get("stage", "APPLIED").strip().upper(),
                data.get("resume_doc_url"),
                data.get("aadhar_doc_url"),
                data.get("notes", ""),
                data.get("interview_date"),
                now_iso,
                now_iso,
            )
        )
    return {"id": cand_id, "name": data.get("name")}


def update_candidate(cand_id: str, data: dict[str, Any], settings: Settings | None = None) -> dict[str, Any] | None:
    """Update candidate pipeline stage, notes, or rating."""
    settings = settings or Settings()
    now_iso = datetime.now(timezone.utc).isoformat()
    fields = []
    params = []

    for key in ("name", "phone", "email", "target_role", "expected_salary", "rating", "stage", "resume_doc_url", "aadhar_doc_url", "notes", "interview_date"):
        if key in data:
            fields.append(f"{key} = ?")
            params.append(data[key])

    if not fields:
        return None

    fields.append("updated_at = ?")
    params.append(now_iso)
    params.append(cand_id)

    with _connect(settings) as conn:
        conn.execute(f"UPDATE zepto_candidates SET {', '.join(fields)} WHERE id = ?", params)
    return {"id": cand_id, "updated": True}


def convert_candidate_to_employee(
    cand_id: str,
    joining_date: str | None = None,
    base_salary: float | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """One-click conversion: promote a candidate into active employee roster."""
    settings = settings or Settings()
    ensure_zepto_schema(settings)
    with _connect(settings) as conn:
        conn.row_factory = sqlite3.Row
        cand = conn.execute("SELECT * FROM zepto_candidates WHERE id = ?", (cand_id,)).fetchone()
        if not cand:
            raise ValueError(f"Candidate {cand_id} not found.")

        cand_dict = dict(cand)
        emp_id = f"emp_{uuid.uuid4().hex[:8]}"
        joining = joining_date or datetime.now().strftime("%Y-%m-%d")
        salary = base_salary if base_salary is not None else (cand_dict.get("expected_salary") or 18000.0)

        # 1. Create employee
        emp_data = {
            "id": emp_id,
            "name": cand_dict["name"],
            "role": cand_dict["target_role"],
            "phone": cand_dict["phone"],
            "email": cand_dict["email"],
            "joining_date": joining,
            "status": "ACTIVE",
            "rating": cand_dict.get("rating", 4.5),
            "base_salary_monthly": salary,
            "resume_doc_url": cand_dict.get("resume_doc_url"),
            "aadhar_doc_url": cand_dict.get("aadhar_doc_url"),
            "notes": f"Converted from hiring pipeline candidate. {cand_dict.get('notes', '')}",
        }
        create_employee(emp_data, settings)

        # 2. Mark candidate stage as HIRED
        conn.execute("UPDATE zepto_candidates SET stage = 'HIRED', updated_at = ? WHERE id = ?", (datetime.now(timezone.utc).isoformat(), cand_id))

        return {"success": True, "employee_id": emp_id, "name": cand_dict["name"]}


def delete_candidate(cand_id: str, settings: Settings | None = None) -> bool:
    """Delete candidate from pipeline."""
    settings = settings or Settings()
    with _connect(settings) as conn:
        conn.execute("DELETE FROM zepto_candidates WHERE id = ?", (cand_id,))
    return True


# ---------------------------------------------------------------------------
# Zepto Security Deposit & 50-50 Partner Capital Ledger
# ---------------------------------------------------------------------------

def get_security_tranches(settings: Settings | None = None) -> list[dict[str, Any]]:
    """Retrieve all capital payment tranches sent to Zepto."""
    settings = settings or Settings()
    ensure_zepto_schema(settings)
    with _connect(settings) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM zepto_security_capital ORDER BY payment_date DESC, created_at DESC").fetchall()
        return [dict(r) for r in rows]


def create_security_tranche(data: dict[str, Any], settings: Settings | None = None) -> dict[str, Any]:
    """Record a new capital contribution tranche to Zepto."""
    settings = settings or Settings()
    ensure_zepto_schema(settings)
    tranche_id = data.get("id") or str(uuid.uuid4())
    now_iso = datetime.now(timezone.utc).isoformat()

    with _connect(settings) as conn:
        conn.execute(
            """
            INSERT INTO zepto_security_capital (
                id, tranche_title, amount, payment_date, partner_name,
                payment_mode, reference_utr, proof_doc_url, notes, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tranche_id,
                data.get("tranche_title", "Security Deposit Tranche").strip(),
                float(data.get("amount", 0.0)),
                data.get("payment_date", datetime.now().strftime("%Y-%m-%d")),
                data.get("partner_name", "Jatin Abrol").strip(),
                data.get("payment_mode", "NEFT_RTGS").strip(),
                data.get("reference_utr", "").strip(),
                data.get("proof_doc_url"),
                data.get("notes", ""),
                now_iso,
            )
        )
    return {"id": tranche_id, "amount": data.get("amount"), "partner_name": data.get("partner_name")}


def delete_security_tranche(tranche_id: str, settings: Settings | None = None) -> bool:
    """Delete a capital tranche record."""
    settings = settings or Settings()
    with _connect(settings) as conn:
        conn.execute("DELETE FROM zepto_security_capital WHERE id = ?", (tranche_id,))
    return True


# ---------------------------------------------------------------------------
# Document Storage Helper
# ---------------------------------------------------------------------------

def save_uploaded_file(file_bytes: bytes, filename: str) -> dict[str, str]:
    """Persist an uploaded document locally and return its relative URL."""
    upload_dir = _get_upload_dir()
    clean_name = os.path.basename(filename).replace(" ", "_")
    unique_prefix = uuid.uuid4().hex[:6]
    saved_filename = f"{unique_prefix}_{clean_name}"
    dest_path = upload_dir / saved_filename

    with open(dest_path, "wb") as f:
        f.write(file_bytes)

    doc_url = f"/api/v1/zepto/documents/{saved_filename}"
    return {
        "filename": clean_name,
        "saved_filename": saved_filename,
        "url": doc_url,
        "size_bytes": str(len(file_bytes)),
    }
