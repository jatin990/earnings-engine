"""Zepto Store Management Hub — Database Schema & Data Access Layer.

Handles persistence, aggregations, MoM salary tracking, attrition rates,
spend-per-person metrics, hiring pipeline conversions, and 50-50 partner equity ledger.
"""

from __future__ import annotations

import json
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

def _get_table_columns(conn: Any, table_name: str) -> set[str]:
    """Safely inspect existing column names for a table using PRAGMA table_info."""
    try:
        rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        cols = set()
        for r in rows:
            if hasattr(r, "get"):
                c = r.get("name")
            elif isinstance(r, (tuple, list)) and len(r) > 1:
                c = r[1]
            elif hasattr(r, "keys") and "name" in r.keys():
                c = r["name"]
            else:
                c = None
            if c:
                cols.add(c)
        return cols
    except Exception:
        return set()


# ===========================================================================
# Centralized Partners Configuration (Single Source of Truth)
# ===========================================================================
PARTNERS_CONFIG = {
    "partner_1": {
        "id": "partner_1",
        "name": "Jatin Abrol",
        "label": "Jatin Abrol",
        "role": "Partner",
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

# ---------------------------------------------------------------------------
# Store Roles & Staffing Thresholds
# ---------------------------------------------------------------------------

VALID_STAFF_ROLES = ["PICKER", "SHIFT_INCHARGE", "SECURITY_GUARD", "HOUSEKEEPING"]

DEFAULT_STAFFING_TARGETS = {
    "PICKER": 9,
    "SHIFT_INCHARGE": 3,
    "SECURITY_GUARD": 2,
    "HOUSEKEEPING": 1,
}

DEFAULT_ROLE_BASE_PAY = {
    "PICKER": 18000.0,
    "SHIFT_INCHARGE": 25000.0,
    "SECURITY_GUARD": 16000.0,
    "HOUSEKEEPING": 14000.0,
}

ROLE_METADATA = {
    "PICKER": {"label": "Picker", "icon": "🛒", "color": "purple", "desc": "Item picking, bin staging & UPT speed", "default_salary": 18000.0},
    "SHIFT_INCHARGE": {"label": "Shift Incharge", "icon": "⚡", "color": "indigo", "desc": "Shift management, inventory & dispatch audits", "default_salary": 25000.0},
    "SECURITY_GUARD": {"label": "Security Guard", "icon": "🛡️", "color": "blue", "desc": "Store entry, asset safety & night surveillance", "default_salary": 16000.0},
    "HOUSEKEEPING": {"label": "House Keeping", "icon": "🧹", "color": "emerald", "desc": "Warehouse cleaning, sanitation & spill management", "default_salary": 14000.0},
}

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
                is_hidden INTEGER DEFAULT 0,
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
                performance_rating REAL DEFAULT 5.0,
                payment_date TEXT,
                payment_status TEXT DEFAULT 'PAID',
                payment_mode TEXT DEFAULT 'BANK_TRANSFER',
                notes TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(employee_id) REFERENCES zepto_employees(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS zepto_monthly_ratings (
                id TEXT PRIMARY KEY,
                employee_id TEXT NOT NULL,
                year_month TEXT NOT NULL,
                rating REAL NOT NULL DEFAULT 5.0,
                feedback TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(employee_id, year_month),
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
                is_reimbursable INTEGER DEFAULT 1,
                is_reimbursed INTEGER DEFAULT 0,
                notes TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS zepto_store_income (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                income_source TEXT NOT NULL,
                gross_amount REAL NOT NULL,
                deductions REAL DEFAULT 0.0,
                net_amount REAL NOT NULL,
                income_date TEXT NOT NULL,
                year_month TEXT NOT NULL,
                partner_1_share_pct REAL NOT NULL DEFAULT 50.0,
                partner_2_share_pct REAL NOT NULL DEFAULT 50.0,
                partner_1_share_amount REAL NOT NULL,
                partner_2_share_amount REAL NOT NULL,
                proof_doc_url TEXT,
                payment_mode TEXT DEFAULT 'BANK_TRANSFER',
                reference_utr TEXT,
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS zepto_income_split_settings (
                id TEXT PRIMARY KEY,
                partner_1_name TEXT NOT NULL DEFAULT 'Jatin Abrol',
                partner_1_share_pct REAL NOT NULL DEFAULT 50.0,
                partner_2_name TEXT NOT NULL DEFAULT 'Harshiv Bargotra',
                partner_2_share_pct REAL NOT NULL DEFAULT 50.0,
                updated_at TEXT NOT NULL
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

            CREATE TABLE IF NOT EXISTS zepto_staffing_targets (
                role TEXT PRIMARY KEY,
                target_count INTEGER NOT NULL DEFAULT 0,
                default_base_salary REAL NOT NULL DEFAULT 15000.0,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS zepto_gmail_auth (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL,
                access_token TEXT NOT NULL,
                refresh_token TEXT,
                token_expiry TEXT,
                token_type TEXT DEFAULT 'Bearer',
                scopes TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'CONNECTED',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS zepto_attendance_imports (
                id TEXT PRIMARY KEY,
                file_name TEXT NOT NULL,
                store_name TEXT NOT NULL,
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                total_records INTEGER NOT NULL DEFAULT 0,
                total_employees INTEGER NOT NULL DEFAULT 0,
                source TEXT NOT NULL DEFAULT 'UPLOAD',
                imported_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS zepto_attendance_records (
                id TEXT PRIMARY KEY,
                import_id TEXT NOT NULL,
                store_name TEXT NOT NULL,
                employee_id TEXT NOT NULL,
                employee_name TEXT NOT NULL,
                designation TEXT NOT NULL,
                shift_date TEXT NOT NULL,
                shift_name TEXT,
                shift_time TEXT,
                punch_in TEXT,
                punch_out TEXT,
                work_duration_mins INTEGER DEFAULT 0,
                break_duration_mins INTEGER DEFAULT 0,
                raw_status TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(import_id) REFERENCES zepto_attendance_imports(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS zepto_store_metrics (
                id TEXT PRIMARY KEY,
                store_name TEXT NOT NULL,
                metric_date TEXT NOT NULL,
                sales_gmv REAL DEFAULT 0.0,
                order_count INTEGER DEFAULT 0,
                aov REAL DEFAULT 0.0,
                inbound_hours REAL DEFAULT 0.0,
                outbound_hours REAL DEFAULT 0.0,
                packer_ipp REAL DEFAULT 0.0,
                sla_adherence_pct REAL DEFAULT 100.0,
                raw_source TEXT DEFAULT 'MANUAL',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS zepto_loss_records (
                id TEXT PRIMARY KEY,
                store_name TEXT NOT NULL,
                record_date TEXT NOT NULL,
                loss_type TEXT NOT NULL,
                category TEXT NOT NULL,
                amount REAL DEFAULT 0.0,
                sku_count INTEGER DEFAULT 0,
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS zepto_manpower_utilization (
                id TEXT PRIMARY KEY,
                store_name TEXT NOT NULL,
                util_date TEXT NOT NULL,
                employee_id TEXT NOT NULL,
                employee_name TEXT NOT NULL,
                role TEXT,
                items_picked INTEGER DEFAULT 0,
                active_pick_hours REAL DEFAULT 0.0,
                idle_hours REAL DEFAULT 0.0,
                ipp REAL DEFAULT 0.0,
                flex_labor_cost REAL DEFAULT 0.0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS zepto_gmail_messages (
                id TEXT PRIMARY KEY,
                thread_id TEXT,
                subject TEXT,
                sender TEXT,
                date_str TEXT,
                iso_date TEXT,
                month_ym TEXT,
                snippet TEXT,
                category TEXT NOT NULL DEFAULT 'OPERATIONAL',
                category_label TEXT,
                badge_color TEXT,
                icon TEXT,
                extracted_metrics TEXT,
                attachments TEXT,
                has_attachments INTEGER DEFAULT 0,
                internal_date TEXT,
                synced_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_zepto_att_store_date ON zepto_attendance_records(store_name, shift_date);
            CREATE INDEX IF NOT EXISTS idx_zepto_att_emp ON zepto_attendance_records(employee_id, shift_date);
            CREATE INDEX IF NOT EXISTS idx_zepto_att_status ON zepto_attendance_records(status);

            CREATE INDEX IF NOT EXISTS idx_zepto_met_store_date ON zepto_store_metrics(store_name, metric_date);
            CREATE INDEX IF NOT EXISTS idx_zepto_loss_store_date ON zepto_loss_records(store_name, record_date);
            CREATE INDEX IF NOT EXISTS idx_zepto_util_store_date ON zepto_manpower_utilization(store_name, util_date);
            CREATE INDEX IF NOT EXISTS idx_zepto_gmail_msg_month ON zepto_gmail_messages(month_ym);
            CREATE INDEX IF NOT EXISTS idx_zepto_gmail_msg_date ON zepto_gmail_messages(iso_date);
            CREATE INDEX IF NOT EXISTS idx_zepto_gmail_msg_cat ON zepto_gmail_messages(category);

            CREATE INDEX IF NOT EXISTS idx_zepto_emp_status ON zepto_employees(status);
            CREATE INDEX IF NOT EXISTS idx_zepto_emp_role ON zepto_employees(role);
            CREATE INDEX IF NOT EXISTS idx_zepto_sal_emp ON zepto_salaries(employee_id, year_month);
            CREATE INDEX IF NOT EXISTS idx_zepto_rat_emp ON zepto_monthly_ratings(employee_id, year_month);
            CREATE INDEX IF NOT EXISTS idx_zepto_exp_date ON zepto_expenses(expense_date);
            CREATE INDEX IF NOT EXISTS idx_zepto_cand_stage ON zepto_candidates(stage);
            CREATE INDEX IF NOT EXISTS idx_zepto_inc_date ON zepto_store_income(income_date);
            CREATE INDEX IF NOT EXISTS idx_zepto_inc_month ON zepto_store_income(year_month);
        """)

        # Migration: Ensure is_hidden column exists on zepto_employees
        emp_cols = _get_table_columns(conn, "zepto_employees")
        if not emp_cols or "is_hidden" not in emp_cols:
            try:
                conn.execute("ALTER TABLE zepto_employees ADD COLUMN is_hidden INTEGER DEFAULT 0")
            except Exception:
                pass

        # Migration: Ensure performance_rating column exists on zepto_salaries
        sal_cols = _get_table_columns(conn, "zepto_salaries")
        if not sal_cols or "performance_rating" not in sal_cols:
            try:
                conn.execute("ALTER TABLE zepto_salaries ADD COLUMN performance_rating REAL DEFAULT 5.0")
            except Exception:
                pass

        # Migration: Ensure default_base_salary column exists on zepto_staffing_targets
        cols = _get_table_columns(conn, "zepto_staffing_targets")
        if not cols or "default_base_salary" not in cols:
            try:
                conn.execute("ALTER TABLE zepto_staffing_targets ADD COLUMN default_base_salary REAL DEFAULT 0.0")
            except Exception:
                pass

        # Migration: Ensure is_reimbursable column exists on zepto_expenses
        exp_cols = _get_table_columns(conn, "zepto_expenses")
        if not exp_cols or "is_reimbursable" not in exp_cols:
            try:
                conn.execute("ALTER TABLE zepto_expenses ADD COLUMN is_reimbursable INTEGER DEFAULT 1")
                conn.execute("UPDATE zepto_expenses SET is_reimbursable = 0, is_reimbursed = 1 WHERE incurred_by = 'STORE_CASH'")
            except Exception:
                pass

        # Migration: Ensure zepto_gmail_messages columns exist
        gmail_cols = _get_table_columns(conn, "zepto_gmail_messages")
        if gmail_cols:
            for col_name, col_type in [
                ("store_name", "TEXT DEFAULT ''"),
                ("body_text", "TEXT DEFAULT ''"),
                ("body_html", "TEXT DEFAULT ''"),
                ("parsed_status", "TEXT DEFAULT 'PENDING'"),
                ("parsed_records_count", "INTEGER DEFAULT 0"),
            ]:
                if col_name not in gmail_cols:
                    try:
                        conn.execute(f"ALTER TABLE zepto_gmail_messages ADD COLUMN {col_name} {col_type}")
                    except Exception:
                        pass

        # Migration: Ensure source_email_id exists on domain tables
        loss_cols = _get_table_columns(conn, "zepto_loss_records")
        if loss_cols and "source_email_id" not in loss_cols:
            try:
                conn.execute("ALTER TABLE zepto_loss_records ADD COLUMN source_email_id TEXT")
            except Exception:
                pass

        met_cols = _get_table_columns(conn, "zepto_store_metrics")
        if met_cols and "source_email_id" not in met_cols:
            try:
                conn.execute("ALTER TABLE zepto_store_metrics ADD COLUMN source_email_id TEXT")
            except Exception:
                pass

        att_imp_cols = _get_table_columns(conn, "zepto_attendance_imports")
        if att_imp_cols and "source_email_id" not in att_imp_cols:
            try:
                conn.execute("ALTER TABLE zepto_attendance_imports ADD COLUMN source_email_id TEXT")
            except Exception:
                pass

        # Ensure default income split settings exist
        now_iso = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """
            INSERT OR IGNORE INTO zepto_income_split_settings (
                id, partner_1_name, partner_1_share_pct, partner_2_name, partner_2_share_pct, updated_at
            ) VALUES ('default', ?, 50.0, ?, 50.0, ?)
            """,
            (PARTNER_1_NAME, PARTNER_2_NAME, now_iso)
        )

        # Seed default staffing targets and base pay if missing or zero
        for role, count in DEFAULT_STAFFING_TARGETS.items():
            default_pay = DEFAULT_ROLE_BASE_PAY.get(role, 15000.0)
            conn.execute(
                """
                INSERT INTO zepto_staffing_targets (role, target_count, default_base_salary, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(role) DO UPDATE SET
                    default_base_salary = CASE 
                        WHEN zepto_staffing_targets.default_base_salary IS NULL OR zepto_staffing_targets.default_base_salary <= 0 
                        THEN excluded.default_base_salary 
                        ELSE zepto_staffing_targets.default_base_salary 
                    END
                """,
                (role, count, default_pay, now_iso)
            )

        # Migrate existing Partner 1 / Partner 2 rows to centralized names
        conn.execute("UPDATE zepto_expenses SET incurred_by = ? WHERE incurred_by LIKE '%Partner 1%' OR incurred_by LIKE '%Jatin%'", (PARTNER_1_NAME,))
        conn.execute("UPDATE zepto_expenses SET incurred_by = ? WHERE incurred_by LIKE '%Partner 2%' OR incurred_by LIKE '%Harshiv%'", (PARTNER_2_NAME,))
        conn.execute("UPDATE zepto_security_capital SET partner_name = ? WHERE partner_name LIKE '%Partner 1%' OR partner_name LIKE '%Jatin%'", (PARTNER_1_NAME,))
        conn.execute("UPDATE zepto_security_capital SET partner_name = ? WHERE partner_name LIKE '%Partner 2%' OR partner_name LIKE '%Harshiv%'", (PARTNER_2_NAME,))

        # Normalize and migrate any legacy roles to the 4 strict roles
        conn.execute("UPDATE zepto_employees SET role = 'PICKER' WHERE role NOT IN ('PICKER', 'SHIFT_INCHARGE', 'SECURITY_GUARD', 'HOUSEKEEPING') AND (role LIKE '%PACK%' OR role LIKE '%RIDER%' OR role LIKE '%CASH%')")
        conn.execute("UPDATE zepto_employees SET role = 'SHIFT_INCHARGE' WHERE role NOT IN ('PICKER', 'SHIFT_INCHARGE', 'SECURITY_GUARD', 'HOUSEKEEPING') AND (role LIKE '%MANAGER%' OR role LIKE '%LEAD%')")
        conn.execute("UPDATE zepto_employees SET role = 'HOUSEKEEPING' WHERE role NOT IN ('PICKER', 'SHIFT_INCHARGE', 'SECURITY_GUARD', 'HOUSEKEEPING') AND role LIKE '%MAINT%'")
        conn.execute("UPDATE zepto_employees SET role = 'SECURITY_GUARD' WHERE role NOT IN ('PICKER', 'SHIFT_INCHARGE', 'SECURITY_GUARD', 'HOUSEKEEPING') AND role LIKE '%SEC%'")
        conn.execute("UPDATE zepto_employees SET role = 'PICKER' WHERE role NOT IN ('PICKER', 'SHIFT_INCHARGE', 'SECURITY_GUARD', 'HOUSEKEEPING')")

        conn.execute("UPDATE zepto_candidates SET target_role = 'PICKER' WHERE target_role NOT IN ('PICKER', 'SHIFT_INCHARGE', 'SECURITY_GUARD', 'HOUSEKEEPING') AND (target_role LIKE '%PACK%' OR target_role LIKE '%RIDER%' OR target_role LIKE '%CASH%')")
        conn.execute("UPDATE zepto_candidates SET target_role = 'SHIFT_INCHARGE' WHERE target_role NOT IN ('PICKER', 'SHIFT_INCHARGE', 'SECURITY_GUARD', 'HOUSEKEEPING') AND (target_role LIKE '%MANAGER%' OR target_role LIKE '%LEAD%')")
        conn.execute("UPDATE zepto_candidates SET target_role = 'HOUSEKEEPING' WHERE target_role NOT IN ('PICKER', 'SHIFT_INCHARGE', 'SECURITY_GUARD', 'HOUSEKEEPING') AND target_role LIKE '%MAINT%'")
        conn.execute("UPDATE zepto_candidates SET target_role = 'SECURITY_GUARD' WHERE target_role NOT IN ('PICKER', 'SHIFT_INCHARGE', 'SECURITY_GUARD', 'HOUSEKEEPING') AND target_role LIKE '%SEC%'")
        conn.execute("UPDATE zepto_candidates SET target_role = 'PICKER' WHERE target_role NOT IN ('PICKER', 'SHIFT_INCHARGE', 'SECURITY_GUARD', 'HOUSEKEEPING')")

        # Strict Anti-Fabrication: Do not automatically insert starter demo/mock records
        # Schema initialization leaves tables pristine and ready for authentic imports or user entry.


def _seed_sample_data(conn: sqlite3.Connection) -> None:
    """Insert initial starter seed records for store setup demonstration."""
    now_dt = datetime.now()
    now_iso = datetime.now(timezone.utc).isoformat()

    # Dynamic temporal anchors relative to current date
    cur_ym = now_dt.strftime("%Y-%m")
    m1_dt = (now_dt.replace(day=1) - timedelta(days=1))
    m1_ym = m1_dt.strftime("%Y-%m")
    m2_dt = (m1_dt.replace(day=1) - timedelta(days=1))
    m2_ym = m2_dt.strftime("%Y-%m")
    m3_dt = (m2_dt.replace(day=1) - timedelta(days=1))
    m3_ym = m3_dt.strftime("%Y-%m")

    # 1. Sample Staff (Only the 4 Store Roles)
    employees = [
        ("emp_01", "Rajesh Kumar", "SHIFT_INCHARGE", "+91 98765 43210", "rajesh.k@darkstore.in", f"{m3_ym}-01", None, None, "ACTIVE", 4.9, 32000.0, 3000.0, None, None, None, "Lead night shift incharge, high inventory accuracy", now_iso, now_iso),
        ("emp_02", "Amit Sharma", "PICKER", "+91 98123 45678", "amit.s@darkstore.in", f"{m3_ym}-15", None, None, "ACTIVE", 4.8, 18500.0, 1500.0, None, None, None, "Top picker: avg 48 items/hour", now_iso, now_iso),
        ("emp_03", "Vikas Verma", "PICKER", "+91 98234 56789", "vikas.v@darkstore.in", f"{m2_ym}-01", None, None, "ACTIVE", 4.5, 18000.0, 500.0, None, None, None, "Morning shift picker", now_iso, now_iso),
        ("emp_04", "Ramesh Chand", "SECURITY_GUARD", "+91 98345 67890", "ramesh.c@darkstore.in", f"{m3_ym}-10", None, None, "ACTIVE", 4.7, 16500.0, 1000.0, None, None, None, "Store entry and night gate security", now_iso, now_iso),
        ("emp_05", "Kavita Devi", "HOUSEKEEPING", "+91 98456 78901", "kavita.d@darkstore.in", f"{m3_ym}-20", None, None, "ACTIVE", 5.0, 14000.0, 1000.0, None, None, None, "Warehouse cleanliness & aisle maintenance", now_iso, now_iso),
        ("emp_06", "Deepak Patel", "PICKER", "+91 98567 89012", "deepak.p@darkstore.in", f"{m3_ym}-20", f"{m1_ym}-01", "Relocated to hometown", "RESIGNED", 3.8, 18000.0, 0.0, None, None, None, "Resigned due to personal relocation", now_iso, now_iso),
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

    # 2. Sample Salaries (with performance rating)
    salaries = [
        (str(uuid.uuid4()), "emp_01", m2_ym, 32000.0, 2500.0, 0.0, 34500.0, 4.9, f"{m1_ym}-02", "PAID", "BANK_TRANSFER", "Performance reward included", now_iso),
        (str(uuid.uuid4()), "emp_01", m1_ym, 32000.0, 3000.0, 0.0, 35000.0, 4.9, f"{m1_ym}-28", "PAID", "BANK_TRANSFER", "On-time shift incentive", now_iso),
        (str(uuid.uuid4()), "emp_02", m2_ym, 18500.0, 1200.0, 0.0, 19700.0, 4.7, f"{m1_ym}-02", "PAID", "BANK_TRANSFER", "Picker speed bonus", now_iso),
        (str(uuid.uuid4()), "emp_02", m1_ym, 18500.0, 1500.0, 0.0, 20000.0, 4.8, f"{m1_ym}-28", "PAID", "BANK_TRANSFER", "UPT bonus", now_iso),
        (str(uuid.uuid4()), "emp_04", m2_ym, 16500.0, 1000.0, 0.0, 17500.0, 4.7, f"{m1_ym}-02", "PAID", "BANK_TRANSFER", "Security attendance bonus", now_iso),
    ]
    conn.executemany(
        """
        INSERT INTO zepto_salaries (
            id, employee_id, year_month, base_amount, bonus_amount, deductions,
            net_paid, performance_rating, payment_date, payment_status, payment_mode, notes, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        salaries
    )

    # 3. Sample Monthly Ratings (MoM Performance History)
    monthly_ratings = [
        (str(uuid.uuid4()), "emp_01", m2_ym, 4.9, "Excellent night shift management and zero dispatch delays", now_iso, now_iso),
        (str(uuid.uuid4()), "emp_01", m1_ym, 4.9, "Maintained 99.8% inventory accuracy during peak surge", now_iso, now_iso),
        (str(uuid.uuid4()), "emp_02", m2_ym, 4.7, "Top picking speed: 46 items/hr", now_iso, now_iso),
        (str(uuid.uuid4()), "emp_02", m1_ym, 4.8, "Achieved store record 52 items/hr UPT speed", now_iso, now_iso),
        (str(uuid.uuid4()), "emp_03", m2_ym, 4.5, "Good picking consistency in morning shifts", now_iso, now_iso),
        (str(uuid.uuid4()), "emp_03", m1_ym, 4.5, "Reliable shift attendance", now_iso, now_iso),
        (str(uuid.uuid4()), "emp_04", m2_ym, 4.7, "Strict night surveillance and visitor logging", now_iso, now_iso),
        (str(uuid.uuid4()), "emp_04", m1_ym, 4.8, "Prevented inventory shrinkage during off-hours", now_iso, now_iso),
        (str(uuid.uuid4()), "emp_05", m2_ym, 5.0, "Flawless aisle hygiene and trash removal", now_iso, now_iso),
        (str(uuid.uuid4()), "emp_05", m1_ym, 5.0, "Zero pest inspection violations", now_iso, now_iso),
    ]
    conn.executemany(
        """
        INSERT INTO zepto_monthly_ratings (
            id, employee_id, year_month, rating, feedback, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        monthly_ratings
    )

    # 4. Sample Store Expenses
    expenses = [
        (str(uuid.uuid4()), "Initial Picker Onboarding & Zepto Training Batch", "TRAINING", 45000.0, f"{m3_ym}-05", PARTNER_1_NAME, None, "training_receipt.pdf", 1, "Offsite training & simulator software fee", now_iso),
        (str(uuid.uuid4()), "Staff Uniforms, Thermal Bags & Reflective Vests", "UNIFORMS_GEAR", 28500.0, f"{m3_ym}-12", PARTNER_2_NAME, None, "uniform_invoice.pdf", 0, "20 sets of customized shirts and thermal jackets (Pending Reimbursement)", now_iso),
        (str(uuid.uuid4()), "Heavy-Duty Warehouse Racks & Bins Installation", "EQUIPMENT", 125000.0, f"{m2_ym}-18", PARTNER_1_NAME, None, "racks_bill.pdf", 0, "Aisle A-D high density racking system (Pending Reimbursement)", now_iso),
        (str(uuid.uuid4()), "Staff Refreshment & Breakroom Tea/Snacks (Monthly)", "SNACKS_WELFARE", 8500.0, f"{m1_ym}-15", "STORE_CASH", None, None, 1, "Monthly pantry items & energy drinks", now_iso),
        (str(uuid.uuid4()), "Store Deep Cleaning & Pest Control Service", "STORE_MAINTENANCE", 12000.0, f"{m1_ym}-20", PARTNER_2_NAME, None, "pest_control_bill.pdf", 1, "Bi-weekly warehouse pest safety compliance", now_iso),
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

    # 5. Sample Store Income (50-50 Partner Split)
    store_income = [
        (str(uuid.uuid4()), f"Zepto Dark Store Monthly Order Commission ({m2_ym})", "COMMISSION", 420000.0, 4200.0, 415800.0, f"{m1_ym}-05", m2_ym, 50.0, 50.0, 207900.0, 207900.0, None, "BANK_TRANSFER", f"ZEPTO-COM-{m2_ym.replace('-', '')}-9821", "Base dark store order commission payout directly from Zepto Escrow", now_iso, now_iso),
        (str(uuid.uuid4()), "Zepto Peak Delivery & SLA Incentive Payout", "GROWTH_INCENTIVE", 180000.0, 1800.0, 178200.0, f"{m1_ym}-15", m1_ym, 50.0, 50.0, 89100.0, 89100.0, None, "BANK_TRANSFER", f"ZEPTO-INC-{m1_ym.replace('-', '')}-4412", "SLA < 10 mins dispatch reward", now_iso, now_iso),
        (str(uuid.uuid4()), "Brand Slotting & Warehouse End-Cap Promotion Fee", "ORDER_SLOTTING", 95000.0, 950.0, 94050.0, f"{m1_ym}-22", m1_ym, 50.0, 50.0, 47025.0, 47025.0, None, "BANK_TRANSFER", f"ZEPTO-SLOT-{m1_ym.replace('-', '')}-7711", "Beverage & FMCG priority shelf placement revenue", now_iso, now_iso),
    ]
    conn.executemany(
        """
        INSERT INTO zepto_store_income (
            id, title, income_source, gross_amount, deductions, net_amount,
            income_date, year_month, partner_1_share_pct, partner_2_share_pct,
            partner_1_share_amount, partner_2_share_amount, proof_doc_url,
            payment_mode, reference_utr, notes, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        store_income
    )

    # 6. Sample Hiring Candidates (4 Strict Roles)
    candidates = [
        (str(uuid.uuid4()), "Rohit Mehra", "+91 99001 12233", "rohit.m@gmail.com", "PICKER", 18500.0, 4.8, "INTERVIEWING", None, None, "1 yr experience at Blinkit dark store", (now_dt - timedelta(days=1)).strftime("%Y-%m-%d"), now_iso, now_iso),
        (str(uuid.uuid4()), "Manish Tiwari", "+91 99112 23344", "manish.t@gmail.com", "SHIFT_INCHARGE", 30000.0, 4.6, "SHORTLISTED", None, None, "Strong logistics background, clear communication", (now_dt - timedelta(days=2)).strftime("%Y-%m-%d"), now_iso, now_iso),
        (str(uuid.uuid4()), "Balwan Singh", "+91 99223 34455", "balwan.s@gmail.com", "SECURITY_GUARD", 16500.0, 4.5, "APPLIED", None, None, "Ex-serviceman with physical verification badge", None, now_iso, now_iso),
        (str(uuid.uuid4()), "Sunita Soni", "+91 99334 45566", "sunita.s@gmail.com", "HOUSEKEEPING", 14000.0, 4.4, "APPLIED", None, None, "Experienced dark store sanitization worker", None, now_iso, now_iso),
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

    # 7. Sample Security Capital Tranches (50-50 Partner Equity Split)
    capital_tranches = [
        (str(uuid.uuid4()), "Initial Franchise Security Tranche 1", 2000000.0, f"{m3_ym}-15", PARTNER_1_NAME, "NEFT_RTGS", f"HDFC{m3_ym.replace('-', '')}9812", None, "First deposit directly to Zepto Operations Escrow", now_iso),
        (str(uuid.uuid4()), "Initial Franchise Security Tranche 1 Match", 2000000.0, f"{m3_ym}-16", PARTNER_2_NAME, "NEFT_RTGS", f"ICIC{m3_ym.replace('-', '')}1142", None, "50% equity matching tranche", now_iso),
        (str(uuid.uuid4()), "Dark Store Capex & Inventory Deposit Tranche 2", 1000000.0, f"{m2_ym}-10", PARTNER_1_NAME, "NEFT_RTGS", f"HDFC{m2_ym.replace('-', '')}5521", None, "Second installment towards ₹75L commitment", now_iso),
        (str(uuid.uuid4()), "Dark Store Capex & Inventory Deposit Tranche 2 Match", 1000000.0, f"{m2_ym}-12", PARTNER_2_NAME, "NEFT_RTGS", f"ICIC{m2_ym.replace('-', '')}7891", None, "Matching second installment", now_iso),
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
# Staffing Thresholds & Role Base Pay Management
# ---------------------------------------------------------------------------

def get_role_configs(settings: Settings | None = None) -> dict[str, dict[str, Any]]:
    """Retrieve target staffing count and default monthly base pay per role."""
    settings = settings or Settings()
    ensure_zepto_schema(settings)
    with _connect(settings) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT role, target_count, default_base_salary, updated_at FROM zepto_staffing_targets").fetchall()
        configs = {}
        for r in rows:
            configs[r["role"]] = {
                "target_count": int(r["target_count"]),
                "base_pay": float(r["default_base_salary"] or DEFAULT_ROLE_BASE_PAY.get(r["role"], 15000.0)),
                "updated_at": r["updated_at"],
            }
        for role in VALID_STAFF_ROLES:
            if role not in configs:
                configs[role] = {
                    "target_count": DEFAULT_STAFFING_TARGETS.get(role, 0),
                    "base_pay": DEFAULT_ROLE_BASE_PAY.get(role, 15000.0),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
        return configs


def update_role_configs(configs: dict[str, dict[str, Any]], settings: Settings | None = None) -> dict[str, dict[str, Any]]:
    """Update target staffing count and/or default base pay per role."""
    settings = settings or Settings()
    ensure_zepto_schema(settings)
    now_iso = datetime.now(timezone.utc).isoformat()
    with _connect(settings) as conn:
        for role in VALID_STAFF_ROLES:
            if role in configs:
                cfg = configs[role]
                cnt = int(cfg.get("target_count", cfg.get("count", DEFAULT_STAFFING_TARGETS.get(role, 0))))
                pay = float(cfg.get("base_pay", cfg.get("salary", cfg.get("default_base_salary", DEFAULT_ROLE_BASE_PAY.get(role, 15000.0)))))
                conn.execute(
                    """
                    INSERT INTO zepto_staffing_targets (role, target_count, default_base_salary, updated_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(role) DO UPDATE SET 
                        target_count = excluded.target_count,
                        default_base_salary = excluded.default_base_salary,
                        updated_at = excluded.updated_at
                    """,
                    (role, max(0, cnt), max(0.0, pay), now_iso)
                )
    return get_role_configs(settings)


def get_staffing_targets(settings: Settings | None = None) -> dict[str, int]:
    """Retrieve target staffing thresholds per role."""
    configs = get_role_configs(settings)
    return {role: data["target_count"] for role, data in configs.items()}


def get_role_base_pays(settings: Settings | None = None) -> dict[str, float]:
    """Retrieve target monthly base pay per role."""
    configs = get_role_configs(settings)
    return {role: data["base_pay"] for role, data in configs.items()}


def update_staffing_targets(
    targets: dict[str, Any],
    base_pays: dict[str, Any] | None = None,
    settings: Settings | None = None
) -> dict[str, int]:
    """Update target staffing thresholds and optional role base pays."""
    settings = settings or Settings()
    ensure_zepto_schema(settings)
    now_iso = datetime.now(timezone.utc).isoformat()
    with _connect(settings) as conn:
        for role in VALID_STAFF_ROLES:
            cnt = None
            pay = None
            if role in targets:
                val = targets[role]
                if isinstance(val, dict):
                    cnt = int(val.get("target_count", val.get("count", 0)))
                    pay = float(val.get("base_pay", val.get("salary", DEFAULT_ROLE_BASE_PAY.get(role, 15000.0))))
                else:
                    cnt = max(0, int(val))
            if base_pays and role in base_pays:
                pay = max(0.0, float(base_pays[role]))

            if cnt is not None and pay is not None:
                conn.execute(
                    """
                    INSERT INTO zepto_staffing_targets (role, target_count, default_base_salary, updated_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(role) DO UPDATE SET 
                        target_count = excluded.target_count,
                        default_base_salary = excluded.default_base_salary,
                        updated_at = excluded.updated_at
                    """,
                    (role, cnt, pay, now_iso)
                )
            elif cnt is not None:
                conn.execute(
                    """
                    INSERT INTO zepto_staffing_targets (role, target_count, default_base_salary, updated_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(role) DO UPDATE SET 
                        target_count = excluded.target_count,
                        updated_at = excluded.updated_at
                    """,
                    (role, cnt, DEFAULT_ROLE_BASE_PAY.get(role, 15000.0), now_iso)
                )
            elif pay is not None:
                conn.execute(
                    """
                    INSERT INTO zepto_staffing_targets (role, target_count, default_base_salary, updated_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(role) DO UPDATE SET 
                        default_base_salary = excluded.default_base_salary,
                        updated_at = excluded.updated_at
                    """,
                    (role, DEFAULT_STAFFING_TARGETS.get(role, 0), pay, now_iso)
                )
    return get_staffing_targets(settings)


# ---------------------------------------------------------------------------
# Overview & Store Analytics
# ---------------------------------------------------------------------------

def get_zepto_overview(settings: Settings | None = None) -> dict[str, Any]:
    """Calculate aggregated store operational KPIs, partner equity, and payroll metrics."""
    settings = settings or Settings()
    ensure_zepto_schema(settings)

    with _connect(settings) as conn:
        conn.row_factory = sqlite3.Row

        # Employee Headcount
        emp_rows = conn.execute("SELECT role, status, COUNT(*) as cnt FROM zepto_employees WHERE (is_hidden = 0 OR is_hidden IS NULL) GROUP BY role, status").fetchall()
        active_count = 0
        resigned_count = 0
        probation_count = 0
        role_breakdown: dict[str, int] = {r: 0 for r in VALID_STAFF_ROLES}
        for r in emp_rows:
            st = r["status"]
            cnt = r["cnt"]
            role = r["role"]
            if st == "ACTIVE":
                active_count += cnt
                role_breakdown[role] = role_breakdown.get(role, 0) + cnt
            elif st == "RESIGNED":
                resigned_count += cnt
            elif st == "ON_PROBATION":
                probation_count += cnt
                active_count += cnt
                role_breakdown[role] = role_breakdown.get(role, 0) + cnt

        total_staff_ever = active_count + resigned_count
        attrition_rate = round((resigned_count / max(1, total_staff_ever)) * 100, 1)

        # Staffing Targets, Base Pay & Capacity Calculations
        role_configs = get_role_configs(settings)
        targets = {r: role_configs[r]["target_count"] for r in VALID_STAFF_ROLES}
        base_pays = {r: role_configs[r]["base_pay"] for r in VALID_STAFF_ROLES}
        total_target_headcount = sum(targets.values())

        staffing_capacity = {}
        projected_payroll_target = 0.0
        for role in VALID_STAFF_ROLES:
            t = targets.get(role, DEFAULT_STAFFING_TARGETS.get(role, 0))
            c = role_breakdown.get(role, 0)
            pay = base_pays.get(role, DEFAULT_ROLE_BASE_PAY.get(role, 15000.0))
            deficit = max(0, t - c)
            projected_role_pay = round(t * pay, 2)
            projected_payroll_target += projected_role_pay
            meta = ROLE_METADATA.get(role, {"label": role, "icon": "👤", "color": "slate", "desc": "", "default_salary": pay})

            staffing_capacity[role] = {
                "role": role,
                "label": meta["label"],
                "icon": meta["icon"],
                "color": meta["color"],
                "desc": meta["desc"],
                "current": c,
                "target": t,
                "base_pay": pay,
                "projected_role_payroll": projected_role_pay,
                "deficit": deficit,
                "fulfilled": c >= t,
                "pct": round((c / max(1, t)) * 100, 1),
            }

        overall_staffing_pct = round((active_count / max(1, total_target_headcount)) * 100, 1)
        projected_payroll_target = round(projected_payroll_target, 2)

        # Average Rating
        avg_rating_row = conn.execute("SELECT AVG(rating) as avg_r FROM zepto_employees WHERE status = 'ACTIVE' AND (is_hidden = 0 OR is_hidden IS NULL)").fetchone()
        avg_rating = round(float(avg_rating_row["avg_r"] or 5.0), 1)

        # Monthly Payroll
        payroll_row = conn.execute("SELECT SUM(base_salary_monthly + current_month_bonus) as total_pay FROM zepto_employees WHERE status = 'ACTIVE' AND (is_hidden = 0 OR is_hidden IS NULL)").fetchone()
        current_monthly_payroll = float(payroll_row["total_pay"] or 0.0)

        # Total Store Expenses & Reimbursements
        exp_row = conn.execute("SELECT SUM(amount) as total_exp FROM zepto_expenses").fetchone()
        total_expenses = float(exp_row["total_exp"] or 0.0)

        # Reimbursement calculations
        reimb_rows = conn.execute("""
            SELECT 
                incurred_by,
                is_reimbursable,
                is_reimbursed,
                SUM(amount) as total_amt,
                COUNT(*) as count
            FROM zepto_expenses
            GROUP BY incurred_by, is_reimbursable, is_reimbursed
        """).fetchall()

        total_reimbursed = 0.0
        total_pending_reimbursement = 0.0
        total_non_reimbursable = 0.0
        pending_by_partner: dict[str, float] = {}

        for r in reimb_rows:
            amt = float(r["total_amt"] or 0.0)
            incurred = (r["incurred_by"] or "").strip()
            is_claimable = int(r["is_reimbursable"] if r["is_reimbursable"] is not None else 1)
            is_r = int(r["is_reimbursed"] or 0)

            if is_claimable == 0 or incurred == "STORE_CASH":
                total_non_reimbursable += amt
                if incurred == "STORE_CASH" or is_r == 1:
                    total_reimbursed += amt
            elif is_r == 1:
                total_reimbursed += amt
            else:
                total_pending_reimbursement += amt
                pending_by_partner[incurred] = pending_by_partner.get(incurred, 0.0) + amt

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

        # Store Income & Customizable Partner Split Ratio
        split_row = conn.execute("SELECT partner_1_name, partner_1_share_pct, partner_2_name, partner_2_share_pct FROM zepto_income_split_settings WHERE id = 'default'").fetchone()
        if split_row:
            p1_split_pct = float(split_row["partner_1_share_pct"] or 50.0)
            p2_split_pct = float(split_row["partner_2_share_pct"] or 50.0)
        else:
            p1_split_pct = 50.0
            p2_split_pct = 50.0

        inc_summary_row = conn.execute("""
            SELECT 
                SUM(gross_amount) as total_gross,
                SUM(deductions) as total_deductions,
                SUM(net_amount) as total_net,
                SUM(partner_1_share_amount) as p1_total,
                SUM(partner_2_share_amount) as p2_total,
                COUNT(*) as inc_count
            FROM zepto_store_income
        """).fetchone()

        total_inc_gross = float(inc_summary_row["total_gross"] or 0.0)
        total_inc_deductions = float(inc_summary_row["total_deductions"] or 0.0)
        total_inc_net = float(inc_summary_row["total_net"] or 0.0)
        p1_inc_total = float(inc_summary_row["p1_total"] or 0.0)
        p2_inc_total = float(inc_summary_row["p2_total"] or 0.0)
        inc_count = int(inc_summary_row["inc_count"] or 0)

        # Income Source Breakdown
        inc_source_rows = conn.execute("SELECT income_source, SUM(net_amount) as net_src, COUNT(*) as cnt FROM zepto_store_income GROUP BY income_source").fetchall()
        inc_source_breakdown = {r["income_source"]: float(r["net_src"] or 0.0) for r in inc_source_rows}

        return {
            "config": {
                "partners": PARTNERS_CONFIG,
                "target_security_deposit": target_capital,
                "target_per_partner": target_per_partner,
                "roles": ROLE_METADATA,
            },
            "headcount": {
                "active": active_count,
                "target_total": total_target_headcount,
                "staffing_pct": overall_staffing_pct,
                "resigned": resigned_count,
                "probation": probation_count,
                "total_ever": total_staff_ever,
                "attrition_rate_pct": attrition_rate,
                "avg_rating": avg_rating,
                "role_breakdown": role_breakdown,
                "capacity": staffing_capacity,
                "targets": targets,
                "base_pays": base_pays,
                "role_configs": role_configs,
                "monthly_payroll": current_monthly_payroll,
                "projected_payroll_target": projected_payroll_target,
            },
            "expenses": {
                "total_expenses": total_expenses,
                "reimbursed_expenses": total_reimbursed,
                "pending_reimbursement": total_pending_reimbursement,
                "non_reimbursable_expenses": total_non_reimbursable,
                "pending_by_partner": pending_by_partner,
                "training_expenses": training_expenses,
                "spend_per_employee": spend_per_employee,
            },
            "income": {
                "total_gross": total_inc_gross,
                "total_deductions": total_inc_deductions,
                "total_net": total_inc_net,
                "income_count": inc_count,
                "partner_1": {
                    "id": "partner_1",
                    "name": PARTNERS_CONFIG["partner_1"]["name"],
                    "label": PARTNERS_CONFIG["partner_1"]["label"],
                    "initials": PARTNERS_CONFIG["partner_1"]["initials"],
                    "share_pct": p1_split_pct,
                    "total_amount": p1_inc_total,
                },
                "partner_2": {
                    "id": "partner_2",
                    "name": PARTNERS_CONFIG["partner_2"]["name"],
                    "label": PARTNERS_CONFIG["partner_2"]["label"],
                    "initials": PARTNERS_CONFIG["partner_2"]["initials"],
                    "share_pct": p2_split_pct,
                    "total_amount": p2_inc_total,
                },
                "split_settings": {
                    "partner_1_name": PARTNERS_CONFIG["partner_1"]["name"],
                    "partner_1_share_pct": p1_split_pct,
                    "partner_2_name": PARTNERS_CONFIG["partner_2"]["name"],
                    "partner_2_share_pct": p2_split_pct,
                },
                "source_breakdown": inc_source_breakdown,
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
    include_hidden: bool = False,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """Retrieve employees with optional role, status, and name/phone search, enriched with last present shift date."""
    settings = settings or Settings()
    ensure_zepto_schema(settings)
    with _connect(settings) as conn:
        conn.row_factory = sqlite3.Row
        query = """
            SELECT e.*, MAX(a.shift_date) as last_present_date
            FROM zepto_employees e
            LEFT JOIN zepto_attendance_records a
                ON (e.id = a.employee_id OR e.name = a.employee_name)
                AND a.status = 'PRESENT'
            WHERE 1=1
        """
        params: list[Any] = []

        if not include_hidden:
            query += " AND (e.is_hidden = 0 OR e.is_hidden IS NULL)"
        if role and role.upper() != "ALL":
            query += " AND e.role = ?"
            params.append(role.upper())
        if status and status.upper() != "ALL":
            query += " AND e.status = ?"
            params.append(status.upper())
        if search:
            query += " AND (e.name LIKE ? OR e.phone LIKE ? OR e.email LIKE ? OR e.id LIKE ?)"
            term = f"%{search.strip()}%"
            params.extend([term, term, term, term])

        query += " GROUP BY e.id ORDER BY e.is_hidden ASC, e.status ASC, e.role ASC, e.name ASC"
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
        "current_month_bonus", "is_hidden", "aadhar_doc_url", "resume_doc_url", "photo_url", "notes"
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
    """Retrieve Month-on-Month salary history for an employee including monthly ratings."""
    settings = settings or Settings()
    ensure_zepto_schema(settings)
    with _connect(settings) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT 
                s.*,
                COALESCE(r.rating, s.performance_rating, 5.0) AS performance_rating,
                r.feedback AS rating_feedback
            FROM zepto_salaries s
            LEFT JOIN zepto_monthly_ratings r 
                ON s.employee_id = r.employee_id AND s.year_month = r.year_month
            WHERE s.employee_id = ?
            ORDER BY s.year_month DESC
            """,
            (emp_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_employee_monthly_ratings(emp_id: str, settings: Settings | None = None) -> list[dict[str, Any]]:
    """Retrieve all recorded monthly performance ratings for an employee."""
    settings = settings or Settings()
    ensure_zepto_schema(settings)
    with _connect(settings) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM zepto_monthly_ratings WHERE employee_id = ? ORDER BY year_month DESC",
            (emp_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def record_employee_monthly_rating(
    emp_id: str,
    year_month: str,
    rating: float,
    feedback: str | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Record or update monthly performance rating for an employee and sync MoM records."""
    settings = settings or Settings()
    ensure_zepto_schema(settings)
    rating_id = str(uuid.uuid4())
    now_iso = datetime.now(timezone.utc).isoformat()
    r_val = max(1.0, min(5.0, round(float(rating), 2)))

    with _connect(settings) as conn:
        conn.execute(
            """
            INSERT INTO zepto_monthly_ratings (
                id, employee_id, year_month, rating, feedback, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(employee_id, year_month) DO UPDATE SET
                rating = excluded.rating,
                feedback = excluded.feedback,
                updated_at = excluded.updated_at
            """,
            (rating_id, emp_id, year_month, r_val, feedback or "", now_iso, now_iso)
        )
        # Sync with salary record if exists
        conn.execute(
            "UPDATE zepto_salaries SET performance_rating = ? WHERE employee_id = ? AND year_month = ?",
            (r_val, emp_id, year_month)
        )
        # Update latest rating on employee record
        conn.execute(
            "UPDATE zepto_employees SET rating = ?, updated_at = ? WHERE id = ?",
            (r_val, now_iso, emp_id)
        )

    return {
        "id": rating_id,
        "employee_id": emp_id,
        "year_month": year_month,
        "rating": r_val,
        "feedback": feedback or "",
        "updated_at": now_iso,
    }


def record_employee_salary(emp_id: str, salary_data: dict[str, Any], settings: Settings | None = None) -> dict[str, Any]:
    """Record monthly salary payout slip with MoM performance rating."""
    settings = settings or Settings()
    ensure_zepto_schema(settings)
    now_iso = datetime.now(timezone.utc).isoformat()

    ym = salary_data.get("year_month", datetime.now(timezone.utc).strftime("%Y-%m"))
    base = float(salary_data.get("base_amount", 0.0))
    bonus = float(salary_data.get("bonus_amount", 0.0))
    deductions = float(salary_data.get("deductions", 0.0))
    net = round(base + bonus - deductions, 2)
    p_rating = round(float(salary_data.get("performance_rating", 5.0)), 2)
    p_date = salary_data.get("payment_date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    p_status = salary_data.get("payment_status", "PAID")
    p_mode = salary_data.get("payment_mode", "BANK_TRANSFER")
    notes = salary_data.get("notes", "")

    with _connect(settings) as conn:
        existing = conn.execute(
            "SELECT id FROM zepto_salaries WHERE employee_id = ? AND year_month = ?",
            (emp_id, ym)
        ).fetchone()

        if existing:
            sal_id = existing[0]
            conn.execute(
                """
                UPDATE zepto_salaries SET
                    base_amount = ?, bonus_amount = ?, deductions = ?, net_paid = ?,
                    performance_rating = ?, payment_date = ?, payment_status = ?, payment_mode = ?, notes = ?
                WHERE id = ?
                """,
                (base, bonus, deductions, net, p_rating, p_date, p_status, p_mode, notes, sal_id)
            )
        else:
            sal_id = str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO zepto_salaries (
                    id, employee_id, year_month, base_amount, bonus_amount, deductions,
                    net_paid, performance_rating, payment_date, payment_status, payment_mode, notes, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (sal_id, emp_id, ym, base, bonus, deductions, net, p_rating, p_date, p_status, p_mode, notes, now_iso)
            )

        # Reset current_month_bonus on employee after recording salary slip
        conn.execute(
            "UPDATE zepto_employees SET current_month_bonus = 0.0, updated_at = ? WHERE id = ?",
            (now_iso, emp_id)
        )
        # Also ensure rating is recorded in zepto_monthly_ratings
        conn.execute(
            """
            INSERT INTO zepto_monthly_ratings (
                id, employee_id, year_month, rating, feedback, created_at, updated_at
            ) VALUES (?, ?, ?, ?, '', ?, ?)
            ON CONFLICT(employee_id, year_month) DO UPDATE SET
                rating = excluded.rating,
                updated_at = excluded.updated_at
            """,
            (str(uuid.uuid4()), emp_id, ym, p_rating, now_iso, now_iso)
        )

    return {
        "id": sal_id,
        "employee_id": emp_id,
        "year_month": ym,
        "base_amount": base,
        "bonus_amount": bonus,
        "deductions": deductions,
        "net_paid": net,
        "performance_rating": p_rating,
    }


def delete_employee(emp_id: str, settings: Settings | None = None) -> bool:
    """Delete an employee and their associated salary history, ratings, and utilization."""
    settings = settings or Settings()
    with _connect(settings) as conn:
        conn.execute("DELETE FROM zepto_salaries WHERE employee_id = ?", (emp_id,))
        conn.execute("DELETE FROM zepto_monthly_ratings WHERE employee_id = ?", (emp_id,))
        conn.execute("DELETE FROM zepto_manpower_utilization WHERE employee_id = ?", (emp_id,))
        conn.execute("DELETE FROM zepto_employees WHERE id = ?", (emp_id,))
    return True


def toggle_employee_visibility(emp_id: str, is_hidden: bool | None = None, settings: Settings | None = None) -> dict[str, Any] | None:
    """Toggle or set the hidden status of an employee. Hiding aligns status to RESIGNED, restoring resets to ACTIVE."""
    settings = settings or Settings()
    ensure_zepto_schema(settings)
    now_iso = datetime.now(timezone.utc).isoformat()
    with _connect(settings) as conn:
        conn.row_factory = sqlite3.Row
        emp = conn.execute("SELECT id, is_hidden, status FROM zepto_employees WHERE id = ?", (emp_id,)).fetchone()
        if not emp:
            return None
        current_hidden = bool(emp["is_hidden"]) if emp["is_hidden"] is not None else False
        new_hidden = int(is_hidden) if is_hidden is not None else int(not current_hidden)

        # When hidden (is_hidden = 1), automatically align status to RESIGNED
        # When unhidden/restored (is_hidden = 0), reset status back to ACTIVE if previously RESIGNED
        if new_hidden == 1:
            conn.execute(
                "UPDATE zepto_employees SET is_hidden = 1, status = 'RESIGNED', updated_at = ? WHERE id = ?",
                (now_iso, emp_id),
            )
        else:
            conn.execute(
                "UPDATE zepto_employees SET is_hidden = 0, status = 'ACTIVE', updated_at = ? WHERE id = ?",
                (now_iso, emp_id),
            )
    return get_employee_by_id(emp_id, settings)


def sync_roster_from_attendance(settings: Settings | None = None) -> dict[str, Any]:
    """Populate/sync zepto_employees master roster from unique attendance records."""
    settings = settings or Settings()
    ensure_zepto_schema(settings)
    now_iso = datetime.now(timezone.utc).isoformat()
    synced_count = 0

    with _connect(settings) as conn:
        conn.row_factory = sqlite3.Row
        # Find all distinct employees in attendance records
        att_emps = conn.execute(
            """
            SELECT employee_id, employee_name, designation, MIN(shift_date) as first_seen
            FROM zepto_attendance_records
            WHERE employee_id IS NOT NULL AND employee_id != ''
            GROUP BY employee_id
            """
        ).fetchall()

        for ae in att_emps:
            emp_id = ae["employee_id"]
            name = (ae["employee_name"] or emp_id).strip()
            desig = (ae["designation"] or "").strip()
            joining = ae["first_seen"] or datetime.now().strftime("%Y-%m-%d")

            # Map designation to standardized store role
            desig_lower = desig.lower()
            if "incharge" in desig_lower or "lead" in desig_lower or "shift" in desig_lower:
                role = "SHIFT_INCHARGE"
                base_sal = 25000.0
            elif "security" in desig_lower or "guard" in desig_lower:
                role = "SECURITY_GUARD"
                base_sal = 16000.0
            elif "housekeeping" in desig_lower or "clean" in desig_lower:
                role = "HOUSEKEEPING"
                base_sal = 14000.0
            else:
                role = "PICKER"
                base_sal = 18000.0

            # Insert or update
            existing = conn.execute("SELECT id FROM zepto_employees WHERE id = ?", (emp_id,)).fetchone()
            if not existing:
                conn.execute(
                    """
                    INSERT INTO zepto_employees (
                        id, name, role, phone, email, joining_date,
                        status, rating, base_salary_monthly, current_month_bonus,
                        is_hidden, notes, created_at, updated_at
                    ) VALUES (?, ?, ?, '', '', ?, 'ACTIVE', 5.0, ?, 0.0, 0, ?, ?, ?)
                    """,
                    (emp_id, name, role, joining, base_sal, f"Auto-synced from Dark Store Attendance ({desig})", now_iso, now_iso),
                )
                synced_count += 1
            else:
                # Keep active and update name/role if unconfigured
                conn.execute(
                    """
                    UPDATE zepto_employees SET
                        name = CASE WHEN name LIKE 'emp_%' OR name = '' THEN ? ELSE name END,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (name, now_iso, emp_id),
                )

    return {"status": "success", "synced_new_employees": synced_count, "total_attendance_staff": len(att_emps)}


def purge_mock_framed_employees(settings: Settings | None = None) -> dict[str, Any]:
    """Purge synthetic/mock starter employees (emp_01 to emp_06), demo candidates, mock expenses, sample income, and demo capital tranches."""
    settings = settings or Settings()
    ensure_zepto_schema(settings)
    purged_emp_count = 0
    purged_expenses_count = 0
    purged_candidates_count = 0
    purged_income_count = 0
    purged_capital_count = 0

    with _connect(settings) as conn:
        # 1. Purge framed starter employees
        mock_ids = ["emp_01", "emp_02", "emp_03", "emp_04", "emp_05", "emp_06"]
        placeholders = ",".join("?" for _ in mock_ids)
        res_emp = conn.execute(f"DELETE FROM zepto_employees WHERE id IN ({placeholders}) OR id LIKE 'emp_0%'", mock_ids)
        purged_emp_count = res_emp.rowcount
        conn.execute(f"DELETE FROM zepto_salaries WHERE employee_id IN ({placeholders}) OR employee_id LIKE 'emp_0%'", mock_ids)
        conn.execute(f"DELETE FROM zepto_monthly_ratings WHERE employee_id IN ({placeholders}) OR employee_id LIKE 'emp_0%'", mock_ids)

        # 2. Purge framed starter expenses
        mock_exp_titles = [
            "Initial Picker Onboarding & Zepto Training Batch",
            "Staff Uniforms, Thermal Bags & Reflective Vests",
            "Heavy-Duty Warehouse Racks & Bins Installation",
            "Staff Refreshment & Breakroom Tea/Snacks (Monthly)",
            "Store Deep Cleaning & Pest Control Service",
        ]
        res_exp = conn.execute(
            f"DELETE FROM zepto_expenses WHERE title IN ({','.join('?' for _ in mock_exp_titles)})",
            mock_exp_titles,
        )
        purged_expenses_count = res_exp.rowcount

        # 3. Purge framed demo candidates
        mock_cand_names = ["Rohit Mehra", "Manish Tiwari", "Balwan Singh", "Sunita Soni"]
        res_cand = conn.execute(
            f"DELETE FROM zepto_candidates WHERE name IN ({','.join('?' for _ in mock_cand_names)})",
            mock_cand_names,
        )
        purged_candidates_count = res_cand.rowcount

        # 4. Purge framed demo store income
        mock_income_titles = [
            "Zepto Dark Store Monthly Order Commission (July 2026)",
            "Zepto Peak Delivery & SLA Incentive Payout",
            "Brand Slotting & Warehouse End-Cap Promotion Fee",
        ]
        res_inc = conn.execute(
            f"DELETE FROM zepto_store_income WHERE title LIKE 'Zepto Dark Store Monthly Order Commission%' OR title IN ({','.join('?' for _ in mock_income_titles)})",
            mock_income_titles,
        )
        purged_income_count = res_inc.rowcount

        # 5. Purge framed demo capital tranches
        mock_cap_titles = [
            "Initial Franchise Security Tranche 1",
            "Initial Franchise Security Tranche 1 Match",
            "Dark Store Capex & Inventory Deposit Tranche 2",
            "Dark Store Capex & Inventory Deposit Tranche 2 Match",
        ]
        res_cap = conn.execute(
            f"DELETE FROM zepto_security_capital WHERE tranche_title IN ({','.join('?' for _ in mock_cap_titles)})",
            mock_cap_titles,
        )
        purged_capital_count = res_cap.rowcount

    return {
        "status": "success",
        "purged_count": purged_emp_count,
        "purged_employees": purged_emp_count,
        "purged_expenses": purged_expenses_count,
        "purged_candidates": purged_candidates_count,
        "purged_income": purged_income_count,
        "purged_capital": purged_capital_count,
    }


# ---------------------------------------------------------------------------
# Store Expenses Management
# ---------------------------------------------------------------------------

def get_expenses(
    category: str | None = None,
    incurred_by: str | None = None,
    reimbursement_status: str | None = None,
    search: str | None = None,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """Retrieve all store expenses with optional category, payer, and reimbursement status filters."""
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
        if reimbursement_status and reimbursement_status.upper() != "ALL":
            st = reimbursement_status.upper()
            if st == "PENDING":
                query += " AND is_reimbursable = 1 AND is_reimbursed = 0 AND incurred_by != 'STORE_CASH'"
            elif st == "REIMBURSED":
                query += " AND is_reimbursable = 1 AND is_reimbursed = 1"
            elif st in ("NOT_CLAIMABLE", "NONE", "DIRECT", "NON_REIMBURSABLE"):
                query += " AND (is_reimbursable = 0 OR incurred_by = 'STORE_CASH')"
        if search:
            query += " AND (title LIKE ? OR notes LIKE ?)"
            term = f"%{search.strip()}%"
            params.extend([term, term])

        query += " ORDER BY expense_date DESC, created_at DESC"
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


def create_expense(data: dict[str, Any], settings: Settings | None = None) -> dict[str, Any]:
    """Record a store expense with receipt document attachment and optional reimbursement flag."""
    settings = settings or Settings()
    ensure_zepto_schema(settings)
    exp_id = data.get("id") or str(uuid.uuid4())
    now_iso = datetime.now(timezone.utc).isoformat()

    incurred = data.get("incurred_by", "Jatin Abrol").strip()
    reimb_opt = data.get("reimbursement_option", data.get("reimbursement_status"))

    if reimb_opt:
        opt_upper = str(reimb_opt).upper()
        if opt_upper in ("NONE", "NO", "NOT_CLAIMABLE", "DIRECT", "0", "FALSE"):
            is_reimbursable = 0
            is_reimbursed = 0
        elif opt_upper in ("SETTLED", "REIMBURSED", "1", "TRUE"):
            is_reimbursable = 1
            is_reimbursed = 1
        else:  # PENDING / YES
            is_reimbursable = 1
            is_reimbursed = 0
    else:
        if incurred == "STORE_CASH":
            is_reimbursable = 0
            is_reimbursed = 1
        else:
            is_reimbursable = int(data.get("is_reimbursable", 1))
            is_reimbursed = int(data.get("is_reimbursed", 0))

    with _connect(settings) as conn:
        conn.execute(
            """
            INSERT INTO zepto_expenses (
                id, title, category, amount, expense_date, incurred_by,
                document_url, document_filename, is_reimbursable, is_reimbursed, notes, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                exp_id,
                data.get("title", "Store Expense").strip(),
                data.get("category", "OPERATIONAL").strip().upper(),
                float(data.get("amount", 0.0)),
                data.get("expense_date", datetime.now().strftime("%Y-%m-%d")),
                incurred,
                data.get("document_url"),
                data.get("document_filename"),
                is_reimbursable,
                is_reimbursed,
                data.get("notes", ""),
                now_iso,
            )
        )
    return {
        "id": exp_id,
        "title": data.get("title"),
        "amount": data.get("amount"),
        "is_reimbursable": is_reimbursable,
        "is_reimbursed": is_reimbursed
    }


def update_expense(exp_id: str, data: dict[str, Any], settings: Settings | None = None) -> dict[str, Any]:
    """Update an existing store expense record."""
    settings = settings or Settings()
    with _connect(settings) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute("SELECT * FROM zepto_expenses WHERE id = ?", (exp_id,)).fetchone()
        if not cur:
            raise ValueError(f"Expense {exp_id} not found")

        incurred = data.get("incurred_by", cur["incurred_by"]).strip()
        reimb_opt = data.get("reimbursement_option", data.get("reimbursement_status"))

        if reimb_opt:
            opt_upper = str(reimb_opt).upper()
            if opt_upper in ("NONE", "NO", "NOT_CLAIMABLE", "DIRECT", "0", "FALSE"):
                is_reimbursable = 0
                is_reimbursed = 0
            elif opt_upper in ("SETTLED", "REIMBURSED", "1", "TRUE"):
                is_reimbursable = 1
                is_reimbursed = 1
            else:
                is_reimbursable = 1
                is_reimbursed = 0
        else:
            is_reimbursable = int(data.get("is_reimbursable", cur["is_reimbursable"] if "is_reimbursable" in cur.keys() else 1))
            is_reimbursed = int(data.get("is_reimbursed", cur["is_reimbursed"]))

        conn.execute(
            """
            UPDATE zepto_expenses SET
                title = ?,
                category = ?,
                amount = ?,
                expense_date = ?,
                incurred_by = ?,
                document_url = COALESCE(?, document_url),
                document_filename = COALESCE(?, document_filename),
                is_reimbursable = ?,
                is_reimbursed = ?,
                notes = ?
            WHERE id = ?
            """,
            (
                data.get("title", cur["title"]).strip(),
                data.get("category", cur["category"]).strip().upper(),
                float(data.get("amount", cur["amount"])),
                data.get("expense_date", cur["expense_date"]),
                incurred,
                data.get("document_url"),
                data.get("document_filename"),
                is_reimbursable,
                is_reimbursed,
                data.get("notes", cur["notes"]),
                exp_id,
            )
        )
        return {
            "id": exp_id,
            "title": data.get("title", cur["title"]),
            "is_reimbursable": is_reimbursable,
            "is_reimbursed": is_reimbursed
        }


def toggle_expense_reimbursement(exp_id: str, is_reimbursed: int | None = None, settings: Settings | None = None) -> dict[str, Any]:
    """Toggle or directly set the reimbursement status of an out-of-pocket store expense."""
    settings = settings or Settings()
    with _connect(settings) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute("SELECT * FROM zepto_expenses WHERE id = ?", (exp_id,)).fetchone()
        if not cur:
            raise ValueError(f"Expense {exp_id} not found")

        if is_reimbursed is not None:
            new_val = 1 if int(is_reimbursed) == 1 else 0
            new_reimbursable = 1 if new_val == 1 or cur.get("is_reimbursable", 1) == 1 else 0
        else:
            new_val = 0 if cur["is_reimbursed"] == 1 else 1
            new_reimbursable = 1

        conn.execute(
            "UPDATE zepto_expenses SET is_reimbursed = ?, is_reimbursable = ? WHERE id = ?",
            (new_val, new_reimbursable, exp_id)
        )
        return {
            "id": exp_id,
            "title": cur["title"],
            "amount": cur["amount"],
            "incurred_by": cur["incurred_by"],
            "is_reimbursable": new_reimbursable,
            "is_reimbursed": new_val,
        }


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


def get_security_tranche_by_id(tranche_id: str, settings: Settings | None = None) -> dict[str, Any] | None:
    """Retrieve a single security capital payment tranche by ID."""
    settings = settings or Settings()
    ensure_zepto_schema(settings)
    with _connect(settings) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM zepto_security_capital WHERE id = ?", (tranche_id,)).fetchone()
        return dict(row) if row else None


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


def update_security_tranche(tranche_id: str, data: dict[str, Any], settings: Settings | None = None) -> dict[str, Any] | None:
    """Update an existing security deposit tranche and/or replace transfer proof slip ad-hoc."""
    settings = settings or Settings()
    ensure_zepto_schema(settings)
    with _connect(settings) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute("SELECT * FROM zepto_security_capital WHERE id = ?", (tranche_id,)).fetchone()
        if not cur:
            raise ValueError(f"Security tranche {tranche_id} not found")

        tranche_title = data.get("tranche_title", cur["tranche_title"]).strip()
        amount = float(data.get("amount", cur["amount"]))
        payment_date = data.get("payment_date", cur["payment_date"])
        partner_name = data.get("partner_name", cur["partner_name"]).strip()
        payment_mode = data.get("payment_mode", cur["payment_mode"]).strip()
        reference_utr = data.get("reference_utr", cur["reference_utr"]).strip()
        proof_doc_url = data.get("proof_doc_url") if "proof_doc_url" in data else cur["proof_doc_url"]
        notes = data.get("notes", cur["notes"])

        conn.execute(
            """
            UPDATE zepto_security_capital SET
                tranche_title = ?,
                amount = ?,
                payment_date = ?,
                partner_name = ?,
                payment_mode = ?,
                reference_utr = ?,
                proof_doc_url = ?,
                notes = ?
            WHERE id = ?
            """,
            (
                tranche_title, amount, payment_date, partner_name,
                payment_mode, reference_utr, proof_doc_url, notes, tranche_id
            )
        )
        return {
            "id": tranche_id,
            "tranche_title": tranche_title,
            "amount": amount,
            "payment_date": payment_date,
            "partner_name": partner_name,
            "payment_mode": payment_mode,
            "reference_utr": reference_utr,
            "proof_doc_url": proof_doc_url,
            "notes": notes,
        }


def update_security_proof(
    tranche_id: str,
    proof_doc_url: str,
    reference_utr: str | None = None,
    notes: str | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Ad-hoc update of transfer slip document and UTR reference for a capital tranche."""
    settings = settings or Settings()
    ensure_zepto_schema(settings)
    with _connect(settings) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute("SELECT * FROM zepto_security_capital WHERE id = ?", (tranche_id,)).fetchone()
        if not cur:
            raise ValueError(f"Security tranche {tranche_id} not found")

        utr = reference_utr if reference_utr is not None else cur["reference_utr"]
        n = notes if notes is not None else cur["notes"]

        conn.execute(
            "UPDATE zepto_security_capital SET proof_doc_url = ?, reference_utr = ?, notes = ? WHERE id = ?",
            (proof_doc_url, utr, n, tranche_id)
        )
        return {
            "id": tranche_id,
            "proof_doc_url": proof_doc_url,
            "reference_utr": utr,
            "notes": n,
        }


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


# ---------------------------------------------------------------------------
# Store Income & Customizable Partner Profit Split
# ---------------------------------------------------------------------------

VALID_INCOME_SOURCES = ["COMMISSION", "GROWTH_INCENTIVE", "ORDER_SLOTTING", "DELIVERY_SURCHARGE", "MISC"]

INCOME_SOURCE_METADATA = {
    "COMMISSION": {"label": "Order Commission", "icon": "🛍️", "color": "emerald", "desc": "Base dark store order commission payout"},
    "GROWTH_INCENTIVE": {"label": "SLA & Growth Incentive", "icon": "🚀", "color": "purple", "desc": "Sub-10m SLA speed & surge volume incentives"},
    "ORDER_SLOTTING": {"label": "Brand Slotting Fee", "icon": "🏷️", "color": "blue", "desc": "FMCG priority bin & category end-cap placement"},
    "DELIVERY_SURCHARGE": {"label": "Delivery Surcharge", "icon": "⚡", "color": "amber", "desc": "Rain & peak hour dispatch delivery margin"},
    "MISC": {"label": "Operational / Misc Income", "icon": "💵", "color": "pink", "desc": "Scrap sales, asset return or ancillary earnings"},
}


def get_income_split_settings(settings: Settings | None = None) -> dict[str, Any]:
    """Retrieve current profit/income distribution split ratio between partners."""
    settings = settings or Settings()
    ensure_zepto_schema(settings)
    with _connect(settings) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM zepto_income_split_settings WHERE id = 'default'").fetchone()
        if row:
            return {
                "partner_1_name": row["partner_1_name"] or PARTNER_1_NAME,
                "partner_1_share_pct": float(row["partner_1_share_pct"] or 50.0),
                "partner_2_name": row["partner_2_name"] or PARTNER_2_NAME,
                "partner_2_share_pct": float(row["partner_2_share_pct"] or 50.0),
                "updated_at": row["updated_at"],
            }
        return {
            "partner_1_name": PARTNER_1_NAME,
            "partner_1_share_pct": 50.0,
            "partner_2_name": PARTNER_2_NAME,
            "partner_2_share_pct": 50.0,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }


def update_income_split_settings(
    partner_1_pct: float,
    partner_2_pct: float,
    partner_1_name: str | None = None,
    partner_2_name: str | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Update customizable income split percentage between Jatin and Harshiv."""
    if isinstance(partner_1_name, Settings):
        settings = partner_1_name
        partner_1_name = None
    elif isinstance(partner_2_name, Settings):
        settings = partner_2_name
        partner_2_name = None

    settings = settings or Settings()
    ensure_zepto_schema(settings)
    p1 = round(float(partner_1_pct), 2)
    p2 = round(float(partner_2_pct), 2)
    if abs((p1 + p2) - 100.0) > 0.1:
        raise ValueError(f"Partner split percentages must total 100.0% (received {p1}% + {p2}% = {p1+p2}%)")

    name1 = partner_1_name or PARTNER_1_NAME
    name2 = partner_2_name or PARTNER_2_NAME
    now_iso = datetime.now(timezone.utc).isoformat()

    with _connect(settings) as conn:
        conn.execute(
            """
            INSERT INTO zepto_income_split_settings (
                id, partner_1_name, partner_1_share_pct, partner_2_name, partner_2_share_pct, updated_at
            ) VALUES ('default', ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                partner_1_name = excluded.partner_1_name,
                partner_1_share_pct = excluded.partner_1_share_pct,
                partner_2_name = excluded.partner_2_name,
                partner_2_share_pct = excluded.partner_2_share_pct,
                updated_at = excluded.updated_at
            """,
            (name1, p1, name2, p2, now_iso)
        )
    return get_income_split_settings(settings)


def get_store_income(
    year_month: str | None = None,
    income_source: str | None = None,
    search: str | None = None,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """Retrieve dark store income records with optional filtering."""
    settings = settings or Settings()
    ensure_zepto_schema(settings)
    with _connect(settings) as conn:
        conn.row_factory = sqlite3.Row
        query = "SELECT * FROM zepto_store_income WHERE 1=1"
        params: list[Any] = []

        if year_month and year_month.upper() != "ALL":
            query += " AND year_month = ?"
            params.append(year_month.strip())
        if income_source and income_source.upper() != "ALL":
            query += " AND income_source = ?"
            params.append(income_source.upper().strip())
        if search:
            query += " AND (title LIKE ? OR reference_utr LIKE ? OR notes LIKE ?)"
            term = f"%{search.strip()}%"
            params.extend([term, term, term])

        query += " ORDER BY income_date DESC, created_at DESC"
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


def get_store_income_by_id(income_id: str, settings: Settings | None = None) -> dict[str, Any] | None:
    """Retrieve single income record by ID."""
    settings = settings or Settings()
    ensure_zepto_schema(settings)
    with _connect(settings) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM zepto_store_income WHERE id = ?", (income_id,)).fetchone()
        return dict(row) if row else None


def create_store_income(data: dict[str, Any], settings: Settings | None = None) -> dict[str, Any]:
    """Record a new store income payment received with partner split distribution."""
    settings = settings or Settings()
    ensure_zepto_schema(settings)
    inc_id = data.get("id") or str(uuid.uuid4())
    now_iso = datetime.now(timezone.utc).isoformat()

    gross = float(data.get("gross_amount", 0.0))
    deductions = float(data.get("deductions", 0.0))
    net = round(gross - deductions, 2)

    # Get default split settings if not specified in data
    default_splits = get_income_split_settings(settings)
    p1_pct = float(data.get("partner_1_share_pct", default_splits["partner_1_share_pct"]))
    p2_pct = float(data.get("partner_2_share_pct", 100.0 - p1_pct))

    p1_amt = round(net * (p1_pct / 100.0), 2)
    p2_amt = round(net - p1_amt, 2)

    date_str = data.get("income_date", datetime.now().strftime("%Y-%m-%d"))
    ym = data.get("year_month") or date_str[:7]
    src = data.get("income_source", "COMMISSION").upper().strip()

    with _connect(settings) as conn:
        conn.execute(
            """
            INSERT INTO zepto_store_income (
                id, title, income_source, gross_amount, deductions, net_amount,
                income_date, year_month, partner_1_share_pct, partner_2_share_pct,
                partner_1_share_amount, partner_2_share_amount, proof_doc_url,
                payment_mode, reference_utr, notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                inc_id,
                data.get("title", "Zepto Store Income").strip(),
                src,
                gross,
                deductions,
                net,
                date_str,
                ym,
                p1_pct,
                p2_pct,
                p1_amt,
                p2_amt,
                data.get("proof_doc_url"),
                data.get("payment_mode", "BANK_TRANSFER").strip(),
                data.get("reference_utr", "").strip(),
                data.get("notes", ""),
                now_iso,
                now_iso,
            )
        )
    return get_store_income_by_id(inc_id, settings) or {"id": inc_id, "net_amount": net}


def update_store_income(income_id: str, data: dict[str, Any], settings: Settings | None = None) -> dict[str, Any] | None:
    """Update store income record and recalculate split."""
    settings = settings or Settings()
    ensure_zepto_schema(settings)
    with _connect(settings) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute("SELECT * FROM zepto_store_income WHERE id = ?", (income_id,)).fetchone()
        if not cur:
            raise ValueError(f"Income record {income_id} not found")

        title = data.get("title", cur["title"]).strip()
        src = data.get("income_source", cur["income_source"]).upper().strip()
        gross = float(data.get("gross_amount", cur["gross_amount"]))
        deductions = float(data.get("deductions", cur["deductions"]))
        net = round(gross - deductions, 2)
        date_str = data.get("income_date", cur["income_date"])
        ym = data.get("year_month", cur["year_month"])

        p1_pct = float(data.get("partner_1_share_pct", cur["partner_1_share_pct"]))
        p2_pct = float(data.get("partner_2_share_pct", 100.0 - p1_pct))
        p1_amt = round(net * (p1_pct / 100.0), 2)
        p2_amt = round(net - p1_amt, 2)

        proof = data.get("proof_doc_url") if "proof_doc_url" in data else cur["proof_doc_url"]
        mode = data.get("payment_mode", cur["payment_mode"]).strip()
        utr = data.get("reference_utr", cur["reference_utr"]).strip()
        notes = data.get("notes", cur["notes"])
        now_iso = datetime.now(timezone.utc).isoformat()

        conn.execute(
            """
            UPDATE zepto_store_income SET
                title = ?, income_source = ?, gross_amount = ?, deductions = ?, net_amount = ?,
                income_date = ?, year_month = ?, partner_1_share_pct = ?, partner_2_share_pct = ?,
                partner_1_share_amount = ?, partner_2_share_amount = ?, proof_doc_url = ?,
                payment_mode = ?, reference_utr = ?, notes = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                title, src, gross, deductions, net, date_str, ym,
                p1_pct, p2_pct, p1_amt, p2_amt, proof, mode, utr, notes, now_iso, income_id
            )
        )
    return get_store_income_by_id(income_id, settings)


def delete_store_income(income_id: str, settings: Settings | None = None) -> bool:
    """Delete a store income record."""
    settings = settings or Settings()
    with _connect(settings) as conn:
        conn.execute("DELETE FROM zepto_store_income WHERE id = ?", (income_id,))
    return True


# ---------------------------------------------------------------------------
# Gmail OAuth 2.0 Auth State & Token Management DAL
# ---------------------------------------------------------------------------

def save_gmail_auth(
    email: str,
    access_token: str,
    refresh_token: str | None = None,
    token_expiry: str | None = None,
    scopes: str = "https://www.googleapis.com/auth/gmail.readonly",
    token_type: str = "Bearer",
    auth_id: str = "primary",
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Persist or update Gmail OAuth credentials in SQLite."""
    settings = settings or Settings()
    ensure_zepto_schema(settings)
    now_iso = datetime.now(timezone.utc).isoformat()

    with _connect(settings) as conn:
        conn.row_factory = sqlite3.Row
        existing = conn.execute("SELECT * FROM zepto_gmail_auth WHERE id = ?", (auth_id,)).fetchone()

        # If no new refresh_token provided, preserve previous one
        final_refresh_token = refresh_token
        if not final_refresh_token and existing and existing["refresh_token"]:
            final_refresh_token = existing["refresh_token"]

        conn.execute(
            """
            INSERT INTO zepto_gmail_auth (
                id, email, access_token, refresh_token, token_expiry,
                token_type, scopes, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'CONNECTED', ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                email = excluded.email,
                access_token = excluded.access_token,
                refresh_token = COALESCE(excluded.refresh_token, zepto_gmail_auth.refresh_token),
                token_expiry = excluded.token_expiry,
                token_type = excluded.token_type,
                scopes = excluded.scopes,
                status = 'CONNECTED',
                updated_at = excluded.updated_at
            """,
            (
                auth_id, email.strip(), access_token.strip(), final_refresh_token,
                token_expiry, token_type, scopes, now_iso, now_iso
            )
        )
    return get_gmail_auth(auth_id, settings) or {
        "id": auth_id,
        "email": email,
        "access_token": access_token,
        "refresh_token": final_refresh_token,
        "token_expiry": token_expiry,
        "status": "CONNECTED",
    }


def get_gmail_auth(auth_id: str = "primary", settings: Settings | None = None) -> dict[str, Any] | None:
    """Retrieve current Gmail OAuth connection credentials."""
    settings = settings or Settings()
    ensure_zepto_schema(settings)
    with _connect(settings) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM zepto_gmail_auth WHERE id = ?", (auth_id,)).fetchone()
        if not row:
            return None
        return dict(row)


def delete_gmail_auth(auth_id: str = "primary", settings: Settings | None = None) -> bool:
    """Delete Gmail OAuth credentials upon user disconnect."""
    settings = settings or Settings()
    ensure_zepto_schema(settings)
    with _connect(settings) as conn:
        conn.execute("DELETE FROM zepto_gmail_auth WHERE id = ?", (auth_id,))
    return True


def get_valid_gmail_token(auth_id: str = "primary", settings: Settings | None = None) -> str | None:
    """Return a valid access token, auto-refreshing via refresh_token if expired or close to expiry."""
    import httpx

    auth_data = get_gmail_auth(auth_id, settings)
    if not auth_data or not auth_data.get("access_token"):
        return None

    # Check expiration
    token_expiry = auth_data.get("token_expiry")
    needs_refresh = False

    if token_expiry:
        try:
            exp_dt = datetime.fromisoformat(token_expiry.replace("Z", "+00:00"))
            # If token expires within next 300 seconds (5 min), refresh it
            now_utc = datetime.now(timezone.utc)
            if (exp_dt - now_utc).total_seconds() < 300:
                needs_refresh = True
        except Exception:
            needs_refresh = True

    if not needs_refresh:
        return str(auth_data["access_token"])

    # Attempt refresh
    refresh_token = auth_data.get("refresh_token")
    if not refresh_token:
        return str(auth_data["access_token"])

    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    if not client_id or not client_secret:
        return str(auth_data["access_token"])

    try:
        token_url = "https://oauth2.googleapis.com/token"
        payload = {
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(token_url, data=payload)
            if resp.status_code == 200:
                data = resp.json()
                new_access_token = data.get("access_token")
                expires_in = data.get("expires_in", 3600)
                from datetime import timedelta
                new_expiry = (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat()

                save_gmail_auth(
                    email=auth_data["email"],
                    access_token=new_access_token,
                    refresh_token=data.get("refresh_token") or refresh_token,
                    token_expiry=new_expiry,
                    scopes=auth_data.get("scopes", ""),
                    auth_id=auth_id,
                    settings=settings,
                )
                return str(new_access_token)
            else:
                logger.warning("[GMAIL-AUTH] Failed to refresh token: %s %s", resp.status_code, resp.text)
    except Exception as exc:
        logger.error("[GMAIL-AUTH] Exception while refreshing token: %s", exc)

    return str(auth_data["access_token"])


def save_gmail_messages(
    messages: list[dict[str, Any]],
    settings: Settings | None = None,
) -> int:
    """Save or update parsed Gmail message records in SQLite for persistent caching and queries."""
    if not messages:
        return 0
    settings = settings or Settings()
    ensure_zepto_schema(settings)
    now_iso = datetime.now(timezone.utc).isoformat()

    rows = []
    for msg in messages:
        msg_id = str(msg.get("id") or "").strip()
        if not msg_id:
            continue

        iso_date = msg.get("iso_date") or ""
        if not iso_date:
            date_str = msg.get("date") or msg.get("date_str") or ""
            if date_str:
                if len(date_str) >= 10 and date_str[4] == "-" and date_str[7] == "-":
                    iso_date = date_str[:10]
                else:
                    try:
                        from email.utils import parsedate_to_datetime
                        dt = parsedate_to_datetime(date_str)
                        iso_date = dt.strftime("%Y-%m-%d")
                    except Exception:
                        try:
                            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                            iso_date = dt.strftime("%Y-%m-%d")
                        except Exception:
                            iso_date = datetime.now().strftime("%Y-%m-%d")
            else:
                iso_date = datetime.now().strftime("%Y-%m-%d")

        month_ym = msg.get("month_ym") or iso_date[:7]

        extracted_metrics = msg.get("extracted_metrics")
        if isinstance(extracted_metrics, (dict, list)):
            extracted_metrics_json = json.dumps(extracted_metrics)
        else:
            extracted_metrics_json = str(extracted_metrics or "{}")

        attachments = msg.get("attachments")
        if isinstance(attachments, (dict, list)):
            attachments_json = json.dumps(attachments)
        else:
            attachments_json = str(attachments or "[]")

        has_attachments = 1 if (msg.get("has_attachments") or (isinstance(attachments, list) and len(attachments) > 0)) else 0
        store_name = str(msg.get("store_name") or "").strip()
        body_text = str(msg.get("body_text") or "").strip()
        body_html = str(msg.get("body_html") or "").strip()
        parsed_status = str(msg.get("parsed_status") or "PENDING").strip().upper()
        parsed_records_count = int(msg.get("parsed_records_count") or 0)

        rows.append((
            msg_id,
            msg.get("thread_id") or "",
            msg.get("subject") or "(No Subject)",
            msg.get("from") or msg.get("sender") or "",
            msg.get("date") or msg.get("date_str") or "",
            iso_date,
            month_ym,
            msg.get("snippet") or "",
            msg.get("category") or "OPERATIONAL",
            msg.get("category_label") or "",
            msg.get("badge_color") or "",
            msg.get("icon") or "",
            extracted_metrics_json,
            attachments_json,
            has_attachments,
            str(msg.get("internal_date") or ""),
            store_name,
            body_text,
            body_html,
            parsed_status,
            parsed_records_count,
            now_iso,
            now_iso,
            now_iso,
        ))

    if not rows:
        return 0

    with _connect(settings) as conn:
        conn.executemany(
            """
            INSERT INTO zepto_gmail_messages (
                id, thread_id, subject, sender, date_str,
                iso_date, month_ym, snippet, category, category_label,
                badge_color, icon, extracted_metrics, attachments,
                has_attachments, internal_date, store_name, body_text,
                body_html, parsed_status, parsed_records_count,
                synced_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                thread_id = excluded.thread_id,
                subject = excluded.subject,
                sender = excluded.sender,
                date_str = excluded.date_str,
                iso_date = excluded.iso_date,
                month_ym = excluded.month_ym,
                snippet = excluded.snippet,
                category = excluded.category,
                category_label = excluded.category_label,
                badge_color = excluded.badge_color,
                icon = excluded.icon,
                extracted_metrics = excluded.extracted_metrics,
                attachments = excluded.attachments,
                has_attachments = excluded.has_attachments,
                internal_date = excluded.internal_date,
                store_name = CASE WHEN excluded.store_name != '' THEN excluded.store_name ELSE zepto_gmail_messages.store_name END,
                body_text = CASE WHEN excluded.body_text != '' THEN excluded.body_text ELSE zepto_gmail_messages.body_text END,
                body_html = CASE WHEN excluded.body_html != '' THEN excluded.body_html ELSE zepto_gmail_messages.body_html END,
                parsed_status = CASE WHEN excluded.parsed_status != 'PENDING' THEN excluded.parsed_status ELSE zepto_gmail_messages.parsed_status END,
                parsed_records_count = CASE WHEN excluded.parsed_records_count > 0 THEN excluded.parsed_records_count ELSE zepto_gmail_messages.parsed_records_count END,
                synced_at = excluded.synced_at,
                updated_at = excluded.updated_at
            """,
            rows,
        )
    return len(rows)


def update_email_parsed_status(
    msg_id: str,
    parsed_status: str,
    parsed_records_count: int = 0,
    settings: Settings | None = None,
) -> bool:
    """Update email parsing status and translated records count."""
    settings = settings or Settings()
    ensure_zepto_schema(settings)
    now_iso = datetime.now(timezone.utc).isoformat()
    with _connect(settings) as conn:
        conn.execute(
            """
            UPDATE zepto_gmail_messages SET
                parsed_status = ?,
                parsed_records_count = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (parsed_status.upper(), parsed_records_count, now_iso, msg_id),
        )
    return True


def get_saved_gmail_message_by_id(
    msg_id: str,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    """Retrieve a single saved email by ID along with its translated linked records."""
    settings = settings or Settings()
    ensure_zepto_schema(settings)

    with _connect(settings) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM zepto_gmail_messages WHERE id = ?", (msg_id,)).fetchone()
        if not row:
            return None

        d = dict(row)
        d["from"] = d.get("sender", "")
        d["date"] = d.get("date_str", "")
        try:
            d["extracted_metrics"] = json.loads(d.get("extracted_metrics") or "{}")
        except Exception:
            d["extracted_metrics"] = {}
        try:
            d["attachments"] = json.loads(d.get("attachments") or "[]")
        except Exception:
            d["attachments"] = []

        # Find linked loss records
        loss_rows = conn.execute(
            "SELECT * FROM zepto_loss_records WHERE source_email_id = ? OR notes LIKE ? ORDER BY record_date DESC",
            (msg_id, f"%{msg_id}%"),
        ).fetchall()
        d["linked_loss_records"] = [dict(lr) for lr in loss_rows]

        # Find linked store metrics
        metric_rows = conn.execute(
            "SELECT * FROM zepto_store_metrics WHERE source_email_id = ? ORDER BY metric_date DESC",
            (msg_id,),
        ).fetchall()
        d["linked_store_metrics"] = [dict(mr) for mr in metric_rows]

        # Find linked attendance imports
        att_rows = conn.execute(
            "SELECT * FROM zepto_attendance_imports WHERE source_email_id = ? ORDER BY imported_at DESC",
            (msg_id,),
        ).fetchall()
        d["linked_attendance_imports"] = [dict(ar) for ar in att_rows]

        return d


def get_saved_gmail_messages(
    month: str | None = None,
    category: str | None = None,
    store_name: str | None = None,
    search: str | None = None,
    limit: int = 1000,
    offset: int = 0,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """Retrieve saved Gmail messages from SQLite database filtered by month, category, store, or search keyword."""
    settings = settings or Settings()
    ensure_zepto_schema(settings)

    query = "SELECT * FROM zepto_gmail_messages WHERE 1=1"
    params: list[Any] = []

    if month and month != "ALL":
        query += " AND month_ym = ?"
        params.append(month)

    if category and category != "ALL":
        query += " AND category = ?"
        params.append(category)

    if store_name and store_name != "ALL":
        query += " AND (store_name = ? OR store_name = '')"
        params.append(store_name)

    if search:
        s_pat = f"%{search.strip().lower()}%"
        query += " AND (LOWER(subject) LIKE ? OR LOWER(sender) LIKE ? OR LOWER(snippet) LIKE ? OR LOWER(store_name) LIKE ?)"
        params.extend([s_pat, s_pat, s_pat, s_pat])

    query += " ORDER BY CASE WHEN internal_date != '' THEN CAST(internal_date AS INTEGER) ELSE 0 END DESC, iso_date DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    with _connect(settings) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query, params).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["from"] = d.get("sender", "")
            d["date"] = d.get("date_str", "")
            try:
                d["extracted_metrics"] = json.loads(d.get("extracted_metrics") or "{}")
            except Exception:
                d["extracted_metrics"] = {}
            try:
                d["attachments"] = json.loads(d.get("attachments") or "[]")
            except Exception:
                d["attachments"] = []
            result.append(d)
        return result


# ---------------------------------------------------------------------------
# Attendance Reports & Muster Ingestion DAL
# ---------------------------------------------------------------------------

def save_attendance_batch(
    parsed_data: dict[str, Any],
    source: str = "UPLOAD",
    source_email_id: str | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """
    Persist parsed attendance records and metadata into SQLite cache.
    Uses MD5 composite ID for records to ensure idempotent upsert.
    """
    import hashlib

    settings = settings or Settings()
    ensure_zepto_schema(settings)
    now_iso = datetime.now(timezone.utc).isoformat()

    file_name = parsed_data.get("file_name") or "attendance_report.xlsx"
    store_name = parsed_data.get("store_name") or "Zepto Dark Store"
    start_date = parsed_data.get("start_date") or ""
    end_date = parsed_data.get("end_date") or ""
    records = parsed_data.get("records") or []
    total_records = len(records)
    total_employees = parsed_data.get("total_employees") or len({r.get("employee_id") for r in records if r.get("employee_id")})
    final_email_id = source_email_id or parsed_data.get("source_email_id")

    import_id = f"imp_{uuid.uuid4().hex[:8]}_{datetime.now().strftime('%Y%m%d%H%M%S')}"

    with _connect(settings) as conn:
        # 1. Insert Import Record
        conn.execute(
            """
            INSERT INTO zepto_attendance_imports (
                id, file_name, store_name, start_date, end_date,
                total_records, total_employees, source, source_email_id, imported_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                import_id,
                file_name,
                store_name,
                start_date,
                end_date,
                total_records,
                total_employees,
                source,
                final_email_id,
                now_iso,
                now_iso,
                now_iso,
            ),
        )

        # 2. Insert granular records
        insert_rows = []
        for r in records:
            emp_id = str(r.get("employee_id") or "").strip()
            shift_date = str(r.get("shift_date") or "").strip()
            # Deterministic composite key
            raw_key = f"{store_name}|{emp_id}|{shift_date}".encode("utf-8")
            rec_id = f"att_{hashlib.md5(raw_key).hexdigest()[:16]}"

            insert_rows.append((
                rec_id,
                import_id,
                store_name,
                emp_id,
                str(r.get("employee_name") or emp_id).strip(),
                str(r.get("designation") or "").strip(),
                shift_date,
                str(r.get("shift_name") or "").strip(),
                str(r.get("shift_time") or "").strip(),
                str(r.get("punch_in") or "").strip(),
                str(r.get("punch_out") or "").strip(),
                int(r.get("work_duration_mins") or 0),
                int(r.get("break_duration_mins") or 0),
                str(r.get("raw_status") or "P").strip(),
                str(r.get("status") or "PRESENT").strip(),
                now_iso,
                now_iso,
            ))

        if insert_rows:
            conn.executemany(
                """
                INSERT INTO zepto_attendance_records (
                    id, import_id, store_name, employee_id, employee_name, designation,
                    shift_date, shift_name, shift_time, punch_in, punch_out,
                    work_duration_mins, break_duration_mins, raw_status, status,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    import_id = excluded.import_id,
                    employee_name = excluded.employee_name,
                    designation = excluded.designation,
                    shift_name = excluded.shift_name,
                    shift_time = excluded.shift_time,
                    punch_in = excluded.punch_in,
                    punch_out = excluded.punch_out,
                    work_duration_mins = excluded.work_duration_mins,
                    break_duration_mins = excluded.break_duration_mins,
                    raw_status = excluded.raw_status,
                    status = excluded.status,
                    updated_at = excluded.updated_at
                """,
                insert_rows,
            )

    return {
        "status": "success",
        "import_id": import_id,
        "store_name": store_name,
        "imported_records": total_records,
        "total_employees": total_employees,
        "start_date": start_date,
        "end_date": end_date,
    }


def get_attendance_summary(
    store_name: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    year_month: str | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Calculate aggregated attendance KPIs, role distribution, status breakdown, and active staff monthly metrics."""
    settings = settings or Settings()
    ensure_zepto_schema(settings)

    where_clauses = ["1=1"]
    params: list[Any] = []

    if store_name:
        where_clauses.append("store_name = ?")
        params.append(store_name)
    if year_month and year_month.upper() != "ALL":
        where_clauses.append("shift_date LIKE ?")
        params.append(f"{year_month.strip()}%")
    else:
        if start_date:
            where_clauses.append("shift_date >= ?")
            params.append(start_date)
        if end_date:
            where_clauses.append("shift_date <= ?")
            params.append(end_date)

    where_sql = " AND ".join(where_clauses)

    with _connect(settings) as conn:
        conn.row_factory = sqlite3.Row

        # Overall counts & headcount
        stats_row = conn.execute(
            f"""
            SELECT
                COUNT(*) as total_shifts,
                COUNT(DISTINCT employee_id) as headcount,
                MIN(shift_date) as min_date,
                MAX(shift_date) as max_date,
                SUM(work_duration_mins) as total_work_mins,
                SUM(CASE WHEN status = 'PRESENT' THEN 1 ELSE 0 END) as present_count,
                SUM(CASE WHEN status = 'ABSENT' THEN 1 ELSE 0 END) as absent_count,
                SUM(CASE WHEN status = 'WEEK_OFF' THEN 1 ELSE 0 END) as week_off_count,
                SUM(CASE WHEN status = 'HALF_DAY' THEN 1 ELSE 0 END) as half_day_count,
                SUM(CASE WHEN status = 'HOLIDAY' THEN 1 ELSE 0 END) as holiday_count,
                SUM(CASE WHEN status = 'LEAVE' THEN 1 ELSE 0 END) as leave_count
            FROM zepto_attendance_records
            WHERE {where_sql}
            """,
            params,
        ).fetchone()

        total_shifts = stats_row["total_shifts"] if stats_row else 0
        headcount = stats_row["headcount"] if stats_row else 0
        present = stats_row["present_count"] or 0 if stats_row else 0
        absent = stats_row["absent_count"] or 0 if stats_row else 0
        week_off = stats_row["week_off_count"] or 0 if stats_row else 0
        half_day = stats_row["half_day_count"] or 0 if stats_row else 0
        holiday = stats_row["holiday_count"] or 0 if stats_row else 0
        leave = stats_row["leave_count"] or 0 if stats_row else 0
        total_work_mins = stats_row["total_work_mins"] or 0 if stats_row else 0

        denominator = present + absent + half_day
        attendance_rate = (
            round(((present + 0.5 * half_day) / denominator) * 100.0, 2)
            if denominator > 0
            else 0.0
        )

        # Role breakdown
        role_rows = conn.execute(
            f"""
            SELECT
                COALESCE(NULLIF(designation, ''), 'Unassigned') as role,
                COUNT(DISTINCT employee_id) as headcount,
                COUNT(*) as total_shifts,
                SUM(CASE WHEN status = 'PRESENT' THEN 1 ELSE 0 END) as present_count,
                SUM(CASE WHEN status = 'ABSENT' THEN 1 ELSE 0 END) as absent_count,
                SUM(work_duration_mins) as total_work_mins
            FROM zepto_attendance_records
            WHERE {where_sql}
            GROUP BY role
            ORDER BY total_shifts DESC
            """,
            params,
        ).fetchall()

        role_breakdown = []
        for r in role_rows:
            r_denom = (r["present_count"] or 0) + (r["absent_count"] or 0)
            r_rate = round(((r["present_count"] or 0) / r_denom) * 100.0, 1) if r_denom > 0 else 100.0
            role_breakdown.append({
                "role": r["role"],
                "headcount": r["headcount"],
                "total_shifts": r["total_shifts"],
                "present_count": r["present_count"] or 0,
                "absent_count": r["absent_count"] or 0,
                "attendance_rate_pct": r_rate,
                "total_hours_worked": round((r["total_work_mins"] or 0) / 60.0, 1),
            })

        # Daily trend
        daily_rows = conn.execute(
            f"""
            SELECT
                shift_date,
                COUNT(DISTINCT employee_id) as scheduled,
                SUM(CASE WHEN status = 'PRESENT' THEN 1 ELSE 0 END) as present,
                SUM(CASE WHEN status = 'ABSENT' THEN 1 ELSE 0 END) as absent,
                SUM(CASE WHEN status = 'WEEK_OFF' THEN 1 ELSE 0 END) as week_off,
                SUM(CASE WHEN status = 'HALF_DAY' THEN 1 ELSE 0 END) as half_day,
                SUM(CASE WHEN status = 'HOLIDAY' THEN 1 ELSE 0 END) as holiday
            FROM zepto_attendance_records
            WHERE {where_sql}
            GROUP BY shift_date
            ORDER BY shift_date ASC
            """,
            params,
        ).fetchall()

        daily_trend = [
            {
                "date": d["shift_date"],
                "scheduled": d["scheduled"],
                "present": d["present"],
                "absent": d["absent"],
                "week_off": d["week_off"],
                "half_day": d["half_day"],
                "holiday": d["holiday"],
            }
            for d in daily_rows
        ]

        # Absenteeism Watchlist (employees with absences >= 2 or high absence rate)
        emp_absent_rows = conn.execute(
            f"""
            SELECT
                employee_id,
                employee_name,
                COALESCE(NULLIF(designation, ''), 'Unassigned') as designation,
                COUNT(*) as total_shifts,
                SUM(CASE WHEN status = 'PRESENT' THEN 1 ELSE 0 END) as present_count,
                SUM(CASE WHEN status = 'ABSENT' THEN 1 ELSE 0 END) as absent_count,
                SUM(CASE WHEN status = 'HALF_DAY' THEN 1 ELSE 0 END) as half_day_count,
                SUM(CASE WHEN status = 'WEEK_OFF' THEN 1 ELSE 0 END) as week_off_count,
                SUM(work_duration_mins) as work_mins
            FROM zepto_attendance_records
            WHERE {where_sql}
            GROUP BY employee_id, employee_name, designation
            HAVING absent_count >= 1
            ORDER BY absent_count DESC, total_shifts DESC
            """,
            params,
        ).fetchall()

        absenteeism_watchlist = []
        for ea in emp_absent_rows:
            e_denom = (ea["present_count"] or 0) + (ea["absent_count"] or 0) + (ea["half_day_count"] or 0)
            e_rate = round((((ea["present_count"] or 0) + 0.5 * (ea["half_day_count"] or 0)) / e_denom) * 100.0, 1) if e_denom > 0 else 0.0
            abs_count = ea["absent_count"] or 0
            risk_tier = "CRITICAL" if abs_count >= 5 or e_rate < 50.0 else ("HIGH" if abs_count >= 3 else "MODERATE")
            absenteeism_watchlist.append({
                "employee_id": ea["employee_id"],
                "employee_name": ea["employee_name"],
                "designation": ea["designation"],
                "total_shifts": ea["total_shifts"],
                "present_count": ea["present_count"] or 0,
                "absent_count": abs_count,
                "half_day_count": ea["half_day_count"] or 0,
                "week_off_count": ea["week_off_count"] or 0,
                "attendance_rate_pct": e_rate,
                "risk_tier": risk_tier,
                "total_hours_worked": round((ea["work_mins"] or 0) / 60.0, 1),
            })

        # Operational Capacity Summary Buckets (Packers, Leadership, Inbound/Quality/NSO)
        capacity_summary = {
            "packers": {"scheduled": 0, "present": 0, "absent": 0, "rate": 0.0, "headcount": 0, "health": "HEALTHY"},
            "leadership": {"scheduled": 0, "present": 0, "absent": 0, "rate": 0.0, "headcount": 0, "health": "HEALTHY"},
            "inbound_quality_nso": {"scheduled": 0, "present": 0, "absent": 0, "rate": 0.0, "headcount": 0, "health": "HEALTHY"},
        }

        for r in role_breakdown:
            role_lower = r["role"].lower()
            if "packer" in role_lower or "picker" in role_lower:
                bucket = capacity_summary["packers"]
            elif "incharge" in role_lower or "lead" in role_lower or "technician" in role_lower:
                bucket = capacity_summary["leadership"]
            else:
                bucket = capacity_summary["inbound_quality_nso"]

            bucket["scheduled"] += r["total_shifts"]
            bucket["present"] += r["present_count"]
            bucket["absent"] += r["absent_count"]
            bucket["headcount"] += r["headcount"]

        for key, b in capacity_summary.items():
            denom = b["present"] + b["absent"]
            b["rate"] = round((b["present"] / denom) * 100.0, 1) if denom > 0 else 100.0
            if b["rate"] < 70.0:
                b["health"] = "ALERT"
            elif b["rate"] < 88.0:
                b["health"] = "WARNING"
            else:
                b["health"] = "OPTIMAL"

        # Active Staff Roster Summary for the Selected Period
        staff_summary_rows = conn.execute(
            f"""
            SELECT
                employee_id,
                employee_name,
                COALESCE(NULLIF(designation, ''), 'Unassigned') as designation,
                COUNT(*) as total_shifts,
                SUM(CASE WHEN status = 'PRESENT' THEN 1 ELSE 0 END) as present_count,
                SUM(CASE WHEN status = 'ABSENT' THEN 1 ELSE 0 END) as absent_count,
                SUM(CASE WHEN status = 'HALF_DAY' THEN 1 ELSE 0 END) as half_day_count,
                SUM(CASE WHEN status = 'WEEK_OFF' THEN 1 ELSE 0 END) as week_off_count,
                SUM(CASE WHEN status = 'HOLIDAY' THEN 1 ELSE 0 END) as holiday_count,
                SUM(work_duration_mins) as total_work_mins,
                SUM(break_duration_mins) as total_break_mins,
                MAX(shift_date) as last_shift_date
            FROM zepto_attendance_records
            WHERE {where_sql}
            GROUP BY employee_id, employee_name, designation
            ORDER BY present_count DESC, total_shifts DESC, employee_name ASC
            """,
            params,
        ).fetchall()

        staff_roster = []
        for s in staff_summary_rows:
            s_denom = (s["present_count"] or 0) + (s["absent_count"] or 0) + (s["half_day_count"] or 0)
            s_rate = round((((s["present_count"] or 0) + 0.5 * (s["half_day_count"] or 0)) / s_denom) * 100.0, 1) if s_denom > 0 else 0.0
            s_pres = s["present_count"] or 0
            s_abs = s["absent_count"] or 0
            s_mins = s["total_work_mins"] or 0
            avg_daily_hrs = round((s_mins / 60.0) / s_pres, 1) if s_pres > 0 else 0.0

            risk_tier = "LOW"
            if s_abs >= 4 or (s_denom >= 5 and s_rate < 70.0):
                risk_tier = "CRITICAL"
            elif s_abs >= 2 or (s_denom >= 5 and s_rate < 85.0):
                risk_tier = "HIGH"
            elif s_abs >= 1:
                risk_tier = "MODERATE"

            staff_roster.append({
                "employee_id": s["employee_id"],
                "employee_name": s["employee_name"],
                "designation": s["designation"],
                "total_shifts": s["total_shifts"],
                "present_count": s_pres,
                "absent_count": s_abs,
                "half_day_count": s["half_day_count"] or 0,
                "week_off_count": s["week_off_count"] or 0,
                "holiday_count": s["holiday_count"] or 0,
                "attendance_rate_pct": s_rate,
                "total_hours_worked": round(s_mins / 60.0, 1),
                "avg_daily_hours": avg_daily_hrs,
                "risk_tier": risk_tier,
                "last_shift_date": s["last_shift_date"],
            })

        return {
            "store_name": store_name or "All Stores",
            "period": {
                "start": stats_row["min_date"] or start_date or "",
                "end": stats_row["max_date"] or end_date or "",
            },
            "headcount": headcount,
            "total_shifts_scheduled": total_shifts,
            "attendance_rate_pct": attendance_rate,
            "total_hours_worked": round(total_work_mins / 60.0, 1),
            "status_distribution": {
                "PRESENT": present,
                "ABSENT": absent,
                "WEEK_OFF": week_off,
                "HALF_DAY": half_day,
                "HOLIDAY": holiday,
                "LEAVE": leave,
            },
            "role_breakdown": role_breakdown,
            "daily_trend": daily_trend,
            "absenteeism_watchlist": absenteeism_watchlist,
            "role_capacity_summary": capacity_summary,
            "staff_roster": staff_roster,
        }


def get_attendance_records(
    store_name: str | None = None,
    employee_id: str | None = None,
    designation: str | None = None,
    status: str | None = None,
    date: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    year_month: str | None = None,
    limit: int = 100,
    offset: int = 0,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """Retrieve detailed attendance punch records with filtering and pagination."""
    settings = settings or Settings()
    ensure_zepto_schema(settings)

    where_clauses = ["1=1"]
    params: list[Any] = []

    if store_name:
        where_clauses.append("store_name = ?")
        params.append(store_name)
    if employee_id:
        where_clauses.append("(employee_id = ? OR employee_name LIKE ?)")
        params.extend([employee_id, f"%{employee_id}%"])
    if designation:
        where_clauses.append("designation = ?")
        params.append(designation)
    if status:
        where_clauses.append("status = ?")
        params.append(status.upper())
    if date:
        where_clauses.append("shift_date = ?")
        params.append(date)
    if year_month and year_month.upper() != "ALL":
        where_clauses.append("shift_date LIKE ?")
        params.append(f"{year_month.strip()}%")
    else:
        if start_date:
            where_clauses.append("shift_date >= ?")
            params.append(start_date)
        if end_date:
            where_clauses.append("shift_date <= ?")
            params.append(end_date)

    where_sql = " AND ".join(where_clauses)
    params.extend([limit, offset])

    with _connect(settings) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"""
            SELECT * FROM zepto_attendance_records
            WHERE {where_sql}
            ORDER BY shift_date DESC, employee_name ASC
            LIMIT ? OFFSET ?
            """,
            params,
        ).fetchall()

        return [dict(r) for r in rows]


def get_attendance_imports(limit: int = 20, settings: Settings | None = None) -> list[dict[str, Any]]:
    """Fetch history of attendance report imports."""
    settings = settings or Settings()
    ensure_zepto_schema(settings)

    with _connect(settings) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT * FROM zepto_attendance_imports
            ORDER BY imported_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def delete_attendance_import(import_id: str, settings: Settings | None = None) -> bool:
    """Delete an attendance import batch and cascade delete its records."""
    settings = settings or Settings()
    with _connect(settings) as conn:
        conn.execute("DELETE FROM zepto_attendance_records WHERE import_id = ?", (import_id,))
        conn.execute("DELETE FROM zepto_attendance_imports WHERE id = ?", (import_id,))
    return True


# ---------------------------------------------------------------------------
# Employee Attendance Detail (Slide Drawer DAL)
# ---------------------------------------------------------------------------

def get_employee_attendance_detail(
    employee_id: str,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    """Retrieve 30-day comprehensive punch history, hours worked, and adherence scorecard for a single employee."""
    settings = settings or Settings()
    ensure_zepto_schema(settings)

    with _connect(settings) as conn:
        conn.row_factory = sqlite3.Row

        records = conn.execute(
            """
            SELECT * FROM zepto_attendance_records
            WHERE employee_id = ? OR employee_name = ?
            ORDER BY shift_date DESC
            """,
            (employee_id, employee_id),
        ).fetchall()

        if not records:
            return None

        records_list = [dict(r) for r in records]
        first = records_list[0]

        total_shifts = len(records_list)
        present = sum(1 for r in records_list if r["status"] == "PRESENT")
        absent = sum(1 for r in records_list if r["status"] == "ABSENT")
        week_off = sum(1 for r in records_list if r["status"] == "WEEK_OFF")
        half_day = sum(1 for r in records_list if r["status"] == "HALF_DAY")
        holiday = sum(1 for r in records_list if r["status"] == "HOLIDAY")
        total_work_mins = sum(r.get("work_duration_mins", 0) or 0 for r in records_list)
        total_break_mins = sum(r.get("break_duration_mins", 0) or 0 for r in records_list)

        denominator = present + absent + half_day
        att_rate = round(((present + 0.5 * half_day) / denominator) * 100.0, 1) if denominator > 0 else 0.0

        avg_shift_hours = round((total_work_mins / 60.0) / present, 1) if present > 0 else 0.0

        risk_tier = "LOW"
        if absent >= 4 or (denominator >= 5 and att_rate < 70.0):
            risk_tier = "CRITICAL"
        elif absent >= 2 or (denominator >= 5 and att_rate < 85.0):
            risk_tier = "HIGH"
        elif absent >= 1:
            risk_tier = "MODERATE"

        return {
            "employee_id": first["employee_id"],
            "employee_name": first["employee_name"],
            "designation": first["designation"] or "Unassigned",
            "store_name": first["store_name"],
            "total_shifts": total_shifts,
            "present_count": present,
            "absent_count": absent,
            "week_off_count": week_off,
            "half_day_count": half_day,
            "holiday_count": holiday,
            "attendance_rate_pct": att_rate,
            "total_hours_worked": round(total_work_mins / 60.0, 1),
            "avg_shift_hours": avg_shift_hours,
            "avg_break_mins": round(total_break_mins / present, 0) if present > 0 else 0,
            "risk_tier": risk_tier,
            "punch_history": records_list,
        }


def get_employee_profile_analytics(
    emp_id: str,
    year_month: str | None = None,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    """Retrieve comprehensive employee profile analytics for the Staff & Payroll side drawer:
    Employee bio, month-wise attendance scorecard, punch timeline, IPP productivity metrics,
    MoM performance ratings, and salary payouts.
    """
    settings = settings or Settings()
    ensure_zepto_schema(settings)

    with _connect(settings) as conn:
        conn.row_factory = sqlite3.Row

        emp_row = conn.execute(
            "SELECT * FROM zepto_employees WHERE id = ? OR name = ?",
            (emp_id, emp_id),
        ).fetchone()

        if not emp_row:
            first_att = conn.execute(
                "SELECT * FROM zepto_attendance_records WHERE employee_id = ? OR employee_name = ? LIMIT 1",
                (emp_id, emp_id),
            ).fetchone()
            if not first_att:
                return None
            employee = {
                "id": first_att["employee_id"],
                "name": first_att["employee_name"],
                "role": first_att["designation"] or "PICKER",
                "phone": "",
                "email": "",
                "joining_date": first_att["shift_date"],
                "resignation_date": None,
                "resignation_reason": None,
                "status": "ACTIVE",
                "rating": 5.0,
                "base_salary_monthly": 18000.0,
                "current_month_bonus": 0.0,
                "is_hidden": 0,
                "aadhar_doc_url": None,
                "resume_doc_url": None,
                "photo_url": None,
                "notes": "",
            }
        else:
            employee = dict(emp_row)

        emp_db_id = employee["id"]
        emp_name = employee["name"]

        # Available months from attendance records and salaries
        months_rows = conn.execute(
            """
            SELECT DISTINCT SUBSTR(shift_date, 1, 7) as ym
            FROM zepto_attendance_records
            WHERE employee_id = ? OR employee_name = ? OR employee_id = ? OR employee_name = ?
            UNION
            SELECT DISTINCT year_month as ym FROM zepto_salaries WHERE employee_id = ?
            UNION
            SELECT DISTINCT year_month as ym FROM zepto_monthly_ratings WHERE employee_id = ?
            ORDER BY ym DESC
            """,
            (emp_db_id, emp_name, emp_id, emp_id, emp_db_id, emp_db_id),
        ).fetchall()

        available_months = [r["ym"] for r in months_rows if r["ym"]]
        if not available_months:
            available_months = [datetime.now().strftime("%Y-%m")]

        selected_month = year_month if (year_month and year_month in available_months) else available_months[0]

        # Attendance punch history for selected month
        att_records = conn.execute(
            """
            SELECT * FROM zepto_attendance_records
            WHERE (employee_id = ? OR employee_name = ? OR employee_id = ? OR employee_name = ?)
              AND shift_date LIKE ?
            ORDER BY shift_date DESC
            """,
            (emp_db_id, emp_name, emp_id, emp_id, f"{selected_month}%"),
        ).fetchall()

        records_list = [dict(r) for r in att_records]
        total_shifts = len(records_list)
        present = sum(1 for r in records_list if r["status"] == "PRESENT")
        absent = sum(1 for r in records_list if r["status"] == "ABSENT")
        week_off = sum(1 for r in records_list if r["status"] == "WEEK_OFF")
        half_day = sum(1 for r in records_list if r["status"] == "HALF_DAY")
        holiday = sum(1 for r in records_list if r["status"] == "HOLIDAY")
        total_work_mins = sum(r.get("work_duration_mins", 0) or 0 for r in records_list)
        total_break_mins = sum(r.get("break_duration_mins", 0) or 0 for r in records_list)

        denominator = present + absent + half_day
        att_rate = round(((present + 0.5 * half_day) / denominator) * 100.0, 1) if denominator > 0 else 0.0
        avg_shift_hours = round((total_work_mins / 60.0) / present, 1) if present > 0 else 0.0
        avg_break_mins = round(total_break_mins / present, 0) if present > 0 else 0

        risk_tier = "LOW"
        if absent >= 4 or (denominator >= 5 and att_rate < 70.0):
            risk_tier = "CRITICAL"
        elif absent >= 2 or (denominator >= 5 and att_rate < 85.0):
            risk_tier = "HIGH"
        elif absent >= 1:
            risk_tier = "MODERATE"

        # Month-on-Month attendance trends (for sparkline / bar charts)
        mom_att_rows = conn.execute(
            """
            SELECT
                SUBSTR(shift_date, 1, 7) as ym,
                COUNT(*) as total_shifts,
                SUM(CASE WHEN status = 'PRESENT' THEN 1 ELSE 0 END) as present_count,
                SUM(CASE WHEN status = 'ABSENT' THEN 1 ELSE 0 END) as absent_count,
                SUM(CASE WHEN status = 'HALF_DAY' THEN 1 ELSE 0 END) as half_day_count,
                SUM(CASE WHEN status = 'WEEK_OFF' THEN 1 ELSE 0 END) as week_off_count,
                SUM(work_duration_mins) as work_mins
            FROM zepto_attendance_records
            WHERE (employee_id = ? OR employee_name = ? OR employee_id = ? OR employee_name = ?)
            GROUP BY ym
            ORDER BY ym ASC
            """,
            (emp_db_id, emp_name, emp_id, emp_id),
        ).fetchall()

        mom_attendance = []
        for ma in mom_att_rows:
            ma_pres = ma["present_count"] or 0
            ma_abs = ma["absent_count"] or 0
            ma_half = ma["half_day_count"] or 0
            ma_denom = ma_pres + ma_abs + ma_half
            ma_rate = round(((ma_pres + 0.5 * ma_half) / ma_denom) * 100.0, 1) if ma_denom > 0 else 0.0
            mom_attendance.append({
                "month": ma["ym"],
                "total_shifts": ma["total_shifts"],
                "present_count": ma_pres,
                "absent_count": ma_abs,
                "attendance_rate_pct": ma_rate,
                "hours_worked": round((ma["work_mins"] or 0) / 60.0, 1),
            })

        # IPP / Manpower Utilization metrics for selected month
        ipp_rows = conn.execute(
            """
            SELECT * FROM zepto_manpower_utilization
            WHERE (employee_id = ? OR employee_name = ? OR employee_id = ? OR employee_name = ?)
              AND util_date LIKE ?
            ORDER BY util_date DESC
            """,
            (emp_db_id, emp_name, emp_id, emp_id, f"{selected_month}%"),
        ).fetchall()

        ipp_list = [dict(r) for r in ipp_rows]
        total_items = sum(r.get("items_picked", 0) or 0 for r in ipp_list)
        total_active_hrs = sum(r.get("active_pick_hours", 0.0) or 0.0 for r in ipp_list)
        total_idle_hrs = sum(r.get("idle_hours", 0.0) or 0.0 for r in ipp_list)
        avg_ipp = round(total_items / total_active_hrs, 1) if total_active_hrs > 0 else 0.0

        # Latest physical presence across all shifts
        last_pres_row = conn.execute(
            """
            SELECT MAX(shift_date) as last_present_date
            FROM zepto_attendance_records
            WHERE (employee_id = ? OR employee_name = ? OR employee_id = ? OR employee_name = ?)
              AND status = 'PRESENT'
            """,
            (emp_db_id, emp_name, emp_id, emp_id),
        ).fetchone()
        employee["last_present_date"] = last_pres_row["last_present_date"] if last_pres_row else None

        # Salary history & ratings
        salaries = get_employee_salaries(emp_db_id, settings)
        ratings = get_employee_monthly_ratings(emp_db_id, settings)

        return {
            "employee": employee,
            "selected_month": selected_month,
            "available_months": available_months,
            "attendance": {
                "total_shifts": total_shifts,
                "present_count": present,
                "absent_count": absent,
                "half_day_count": half_day,
                "week_off_count": week_off,
                "holiday_count": holiday,
                "attendance_rate_pct": att_rate,
                "total_hours_worked": round(total_work_mins / 60.0, 1),
                "avg_shift_hours": avg_shift_hours,
                "avg_break_mins": avg_break_mins,
                "risk_tier": risk_tier,
                "punch_history": records_list,
                "mom_trend": mom_attendance,
            },
            "productivity": {
                "avg_ipp": avg_ipp,
                "total_items_picked": total_items,
                "total_active_hours": round(total_active_hrs, 1),
                "total_idle_hours": round(total_idle_hrs, 1),
                "daily_ipp_logs": ipp_list,
            },
            "salaries": salaries,
            "ratings": ratings,
        }


# ---------------------------------------------------------------------------
# Store Metrics Scorecard DAL
# ---------------------------------------------------------------------------

def save_store_metrics(data: dict[str, Any], settings: Settings | None = None) -> dict[str, Any]:
    """Persist or replace a daily store metric record."""
    settings = settings or Settings()
    ensure_zepto_schema(settings)
    store = data.get("store_name", "JMU-Sainik Colony").strip()
    date_str = data.get("metric_date", datetime.now().strftime("%Y-%m-%d")).strip()
    rec_id = data.get("id") or f"met_{store}_{date_str}"
    source_email_id = data.get("source_email_id")
    now_iso = datetime.now(timezone.utc).isoformat()

    with _connect(settings) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO zepto_store_metrics (
                id, store_name, metric_date, sales_gmv, order_count, aov,
                inbound_hours, outbound_hours, packer_ipp, sla_adherence_pct,
                raw_source, source_email_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                rec_id,
                store,
                date_str,
                float(data.get("sales_gmv", 0.0)),
                int(data.get("order_count", 0)),
                float(data.get("aov", 0.0)),
                float(data.get("inbound_hours", 0.0)),
                float(data.get("outbound_hours", 0.0)),
                float(data.get("packer_ipp", 0.0)),
                float(data.get("sla_adherence_pct", 100.0)),
                data.get("raw_source", "MANUAL"),
                source_email_id,
                now_iso,
                now_iso,
            ),
        )
    return {"id": rec_id, "store_name": store, "metric_date": date_str}


def get_store_metrics_summary(
    store_name: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Retrieve aggregated store metrics, daily trends, and SLA performance."""
    settings = settings or Settings()
    ensure_zepto_schema(settings)

    where = ["1=1"]
    params: list[Any] = []
    if store_name:
        where.append("store_name = ?")
        params.append(store_name)
    if start_date:
        where.append("metric_date >= ?")
        params.append(start_date)
    if end_date:
        where.append("metric_date <= ?")
        params.append(end_date)

    where_sql = " AND ".join(where)

    with _connect(settings) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"""
            SELECT * FROM zepto_store_metrics
            WHERE {where_sql}
            ORDER BY metric_date DESC
            """,
            params,
        ).fetchall()

        items = [dict(r) for r in rows]
        total_gmv = sum(i.get("sales_gmv", 0.0) for i in items)
        total_orders = sum(i.get("order_count", 0) for i in items)
        avg_aov = round(total_gmv / total_orders, 1) if total_orders > 0 else 0.0
        avg_sla = round(sum(i.get("sla_adherence_pct", 100.0) for i in items) / len(items), 1) if items else 100.0
        avg_ipp = round(sum(i.get("packer_ipp", 0.0) for i in items) / len(items), 1) if items else 0.0

        return {
            "total_gmv": round(total_gmv, 2),
            "total_orders": total_orders,
            "avg_aov": avg_aov,
            "avg_sla_adherence_pct": avg_sla,
            "avg_packer_ipp": avg_ipp,
            "daily_metrics": items,
        }


# ---------------------------------------------------------------------------
# Loss, Expiry & Shrinkage DAL
# ---------------------------------------------------------------------------

def save_loss_record(data: dict[str, Any], settings: Settings | None = None) -> dict[str, Any]:
    """Persist a dark store loss / shrinkage record."""
    settings = settings or Settings()
    ensure_zepto_schema(settings)
    rec_id = data.get("id") or f"loss_{uuid.uuid4().hex[:12]}"
    store = data.get("store_name", "JMU-Sainik Colony").strip()
    date_str = data.get("record_date", datetime.now().strftime("%Y-%m-%d")).strip()
    source_email_id = data.get("source_email_id")
    now_iso = datetime.now(timezone.utc).isoformat()

    with _connect(settings) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO zepto_loss_records (
                id, store_name, record_date, loss_type, category, amount,
                sku_count, notes, source_email_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                rec_id,
                store,
                date_str,
                data.get("loss_type", "DQ_LOSS").strip().upper(),
                data.get("category", "GENERAL").strip().upper(),
                float(data.get("amount", 0.0)),
                int(data.get("sku_count", 0)),
                data.get("notes", ""),
                source_email_id,
                now_iso,
                now_iso,
            ),
        )
    return {"id": rec_id, "amount": data.get("amount", 0.0)}


def get_loss_summary(
    month: str | None = None,
    store_name: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    loss_type: str | None = None,
    category: str | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Retrieve total store loss, category-wise DQ vs Shrinkage breakdown, email-vs-excel verification, and monthly index."""
    settings = settings or Settings()
    ensure_zepto_schema(settings)

    # 1. Discover distinct available months
    available_months: set[str] = set()
    with _connect(settings) as conn:
        conn.row_factory = sqlite3.Row
        m_rows = conn.execute(
            """
            SELECT DISTINCT substr(record_date, 1, 7) AS ym FROM zepto_loss_records WHERE record_date IS NOT NULL AND length(record_date) >= 7
            UNION
            SELECT DISTINCT month_ym AS ym FROM zepto_gmail_messages WHERE month_ym IS NOT NULL AND category IN ('DQ_LOSS', 'SHRINKAGE')
            """
        ).fetchall()
        for mr in m_rows:
            ym_val = str(mr["ym"] or "").strip()
            if ym_val and len(ym_val) == 7 and ym_val.count("-") == 1:
                available_months.add(ym_val)

    sorted_months = sorted(list(available_months), reverse=True)

    # 2. Build filter conditions for loss records
    where = ["1=1"]
    params: list[Any] = []

    if month and month != "ALL":
        where.append("substr(record_date, 1, 7) = ?")
        params.append(month)
    if store_name and store_name != "ALL":
        where.append("store_name = ?")
        params.append(store_name)
    if start_date:
        where.append("record_date >= ?")
        params.append(start_date)
    if end_date:
        where.append("record_date <= ?")
        params.append(end_date)
    if loss_type and loss_type != "ALL":
        where.append("loss_type = ?")
        params.append(loss_type)
    if category and category != "ALL":
        where.append("category = ?")
        params.append(category)

    where_sql = " AND ".join(where)

    with _connect(settings) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"""
            SELECT * FROM zepto_loss_records
            WHERE {where_sql}
            ORDER BY record_date DESC, created_at DESC
            """,
            params,
        ).fetchall()

        all_items = [dict(r) for r in rows]

        # Deduplication against generic EMAIL_INGESTED rollups when itemized Excel records exist for the same source_email_id
        email_ids_with_itemized = {
            it["source_email_id"] for it in all_items
            if it.get("source_email_id") and it.get("category") != "EMAIL_INGESTED"
        }

        active_items = []
        for it in all_items:
            # Skip email-ingested rollup row if granular Excel rows exist for this email
            if it.get("category") == "EMAIL_INGESTED" and it.get("source_email_id") in email_ids_with_itemized:
                continue
            active_items.append(it)

        # Core metric calculations
        total_loss = sum(float(i.get("amount") or 0.0) for i in active_items)
        dq_total = sum(float(i.get("amount") or 0.0) for i in active_items if i.get("loss_type") == "DQ_LOSS")
        shrinkage_total = sum(
            float(i.get("amount") or 0.0) for i in active_items
            if i.get("loss_type") in ("SHRINKAGE", "CYCLE_COUNT_VARIANCE", "SHORT_PICK")
        )
        spoilage_total = sum(
            float(i.get("amount") or 0.0) for i in active_items
            if i.get("loss_type") in ("SPOILAGE", "TRANSIT_DAMAGE", "EXPIRY")
        )
        total_skus = sum(int(i.get("sku_count") or 0) for i in active_items)

        # Category Matrix Breakdown (DQ vs Shrinkage vs Spoilage by Department)
        cat_map: dict[str, dict[str, Any]] = {}
        for it in active_items:
            cat = (it.get("category") or "GENERAL").strip().upper()
            l_type = (it.get("loss_type") or "DQ_LOSS").strip().upper()
            amt = float(it.get("amount") or 0.0)
            sku_cnt = int(it.get("sku_count") or 0)

            if cat not in cat_map:
                cat_map[cat] = {
                    "category": cat,
                    "total_amount": 0.0,
                    "dq_loss_amount": 0.0,
                    "shrinkage_amount": 0.0,
                    "spoilage_amount": 0.0,
                    "total_skus": 0,
                    "incident_count": 0,
                    "pct_of_total": 0.0,
                }

            cat_map[cat]["total_amount"] += amt
            cat_map[cat]["total_skus"] += sku_cnt
            cat_map[cat]["incident_count"] += 1

            if l_type == "DQ_LOSS":
                cat_map[cat]["dq_loss_amount"] += amt
            elif l_type in ("SHRINKAGE", "CYCLE_COUNT_VARIANCE", "SHORT_PICK"):
                cat_map[cat]["shrinkage_amount"] += amt
            else:
                cat_map[cat]["spoilage_amount"] += amt

        # Format and calculate percentage share
        cat_list = []
        for c_data in cat_map.values():
            c_data["total_amount"] = round(c_data["total_amount"], 2)
            c_data["dq_loss_amount"] = round(c_data["dq_loss_amount"], 2)
            c_data["shrinkage_amount"] = round(c_data["shrinkage_amount"], 2)
            c_data["spoilage_amount"] = round(c_data["spoilage_amount"], 2)
            c_data["pct_of_total"] = round((c_data["total_amount"] / total_loss * 100), 1) if total_loss > 0 else 0.0
            cat_list.append(c_data)

        cat_list.sort(key=lambda x: x["total_amount"], reverse=True)

        # 3. Email Body vs. Excel Verification / Reconciliation Ledger
        recon_where = ["category IN ('DQ_LOSS', 'SHRINKAGE')"]
        recon_params: list[Any] = []
        if month and month != "ALL":
            recon_where.append("month_ym = ?")
            recon_params.append(month)
        if store_name and store_name != "ALL":
            recon_where.append("(store_name = ? OR store_name = '')")
            recon_params.append(store_name)
        if start_date:
            recon_where.append("iso_date >= ?")
            recon_params.append(start_date)
        if end_date:
            recon_where.append("iso_date <= ?")
            recon_params.append(end_date)

        recon_where_sql = " AND ".join(recon_where)
        email_rows = conn.execute(
            f"""
            SELECT id, subject, sender, iso_date, month_ym, store_name, snippet, extracted_metrics, attachments, parsed_status, parsed_records_count
            FROM zepto_gmail_messages
            WHERE {recon_where_sql}
            ORDER BY iso_date DESC, id DESC
            """,
            recon_params,
        ).fetchall()

        recon_items = []
        matched_count = 0
        variance_count = 0

        for er in email_rows:
            e_dict = dict(er)
            try:
                metrics_obj = json.loads(e_dict.get("extracted_metrics") or "{}")
            except Exception:
                metrics_obj = {}
            try:
                attachments_list = json.loads(e_dict.get("attachments") or "[]")
            except Exception:
                attachments_list = []

            email_stated_amount = float(metrics_obj.get("loss_amount") or 0.0)
            msg_id = e_dict["id"]
            msg_date = e_dict["iso_date"]
            msg_store = e_dict["store_name"] or "JMU-Sainik Colony"

            # Query all linked Excel items for this message
            linked_excel_rows = conn.execute(
                """
                SELECT amount, sku_count, category, loss_type FROM zepto_loss_records
                WHERE (source_email_id = ? OR (record_date = ? AND store_name = ?))
                  AND category != 'EMAIL_INGESTED'
                """,
                (msg_id, msg_date, msg_store),
            ).fetchall()

            excel_sum = round(sum(float(lr["amount"] or 0.0) for lr in linked_excel_rows), 2)
            excel_sku_count = sum(int(lr["sku_count"] or 0) for lr in linked_excel_rows)
            excel_item_count = len(linked_excel_rows)

            variance = round(excel_sum - email_stated_amount, 2)
            status = "PENDING"

            if excel_sum > 0 and email_stated_amount > 0:
                if abs(variance) <= 1.0:
                    status = "MATCHED"
                    matched_count += 1
                else:
                    status = "VARIANCE"
                    variance_count += 1
            elif excel_sum > 0 and email_stated_amount == 0:
                status = "EXCEL_ONLY"
            elif excel_sum == 0 and email_stated_amount > 0:
                status = "EMAIL_ONLY"

            recon_items.append({
                "email_id": msg_id,
                "date": msg_date,
                "store_name": msg_store,
                "subject": e_dict["subject"],
                "sender": e_dict["sender"],
                "email_stated_amount": email_stated_amount,
                "excel_parsed_sum": excel_sum,
                "excel_item_count": excel_item_count,
                "excel_sku_count": excel_sku_count,
                "variance": variance,
                "status": status,
                "attachment_filename": attachments_list[0]["filename"] if attachments_list else None,
            })

        total_audits = len(recon_items)
        match_rate_pct = round((matched_count / (matched_count + variance_count) * 100), 1) if (matched_count + variance_count) > 0 else 100.0

        # 4. Monthly Trend aggregation
        month_trend_rows = conn.execute(
            """
            SELECT substr(record_date, 1, 7) AS ym,
                   SUM(amount) AS monthly_total,
                   SUM(CASE WHEN loss_type = 'DQ_LOSS' THEN amount ELSE 0 END) AS dq_total,
                   SUM(CASE WHEN loss_type IN ('SHRINKAGE', 'CYCLE_COUNT_VARIANCE', 'SHORT_PICK') THEN amount ELSE 0 END) AS shrink_total,
                   SUM(CASE WHEN loss_type IN ('SPOILAGE', 'TRANSIT_DAMAGE', 'EXPIRY') THEN amount ELSE 0 END) AS spoil_total,
                   COUNT(*) AS item_count,
                   SUM(sku_count) AS sku_count
            FROM zepto_loss_records
            WHERE category != 'EMAIL_INGESTED' AND record_date IS NOT NULL AND length(record_date) >= 7
            GROUP BY substr(record_date, 1, 7)
            ORDER BY ym DESC
            """
        ).fetchall()

        monthly_trends = [
            {
                "month_ym": mtr["ym"],
                "total_loss": round(float(mtr["monthly_total"] or 0.0), 2),
                "dq_loss": round(float(mtr["dq_total"] or 0.0), 2),
                "shrinkage": round(float(mtr["shrink_total"] or 0.0), 2),
                "spoilage": round(float(mtr["spoil_total"] or 0.0), 2),
                "item_count": int(mtr["item_count"] or 0),
                "sku_count": int(mtr["sku_count"] or 0),
            }
            for mtr in month_trend_rows
        ]

        return {
            "selected_month": month or "ALL",
            "available_months": sorted_months,
            "total_loss_amount": round(total_loss, 2),
            "dq_loss_total": round(dq_total, 2),
            "shrinkage_total": round(shrinkage_total, 2),
            "spoilage_total": round(spoilage_total, 2),
            "total_skus_affected": total_skus,
            "total_loss_records": len(active_items),
            "category_breakdown": cat_list,
            "reconciliation": {
                "items": recon_items,
                "total_audits": total_audits,
                "matched_count": matched_count,
                "variance_count": variance_count,
                "match_rate_pct": match_rate_pct,
            },
            "monthly_trends": monthly_trends,
            "records": active_items,
        }


def get_loss_records(
    month: str | None = None,
    store_name: str | None = None,
    category: str | None = None,
    loss_type: str | None = None,
    search: str | None = None,
    limit: int = 500,
    offset: int = 0,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Retrieve paginated and searchable itemized stored Excel entries."""
    settings = settings or Settings()
    ensure_zepto_schema(settings)

    where = ["1=1"]
    params: list[Any] = []

    if month and month != "ALL":
        where.append("substr(record_date, 1, 7) = ?")
        params.append(month)
    if store_name and store_name != "ALL":
        where.append("store_name = ?")
        params.append(store_name)
    if category and category != "ALL":
        where.append("category = ?")
        params.append(category)
    if loss_type and loss_type != "ALL":
        where.append("loss_type = ?")
        params.append(loss_type)
    if search:
        s_pat = f"%{search.strip().lower()}%"
        where.append("(LOWER(notes) LIKE ? OR LOWER(category) LIKE ? OR LOWER(loss_type) LIKE ? OR LOWER(store_name) LIKE ?)")
        params.extend([s_pat, s_pat, s_pat, s_pat])

    where_sql = " AND ".join(where)

    with _connect(settings) as conn:
        conn.row_factory = sqlite3.Row
        total_count = conn.execute(f"SELECT COUNT(*) AS cnt FROM zepto_loss_records WHERE {where_sql}", params).fetchone()["cnt"]

        query = f"""
            SELECT * FROM zepto_loss_records
            WHERE {where_sql}
            ORDER BY record_date DESC, created_at DESC
            LIMIT ? OFFSET ?
        """
        rows = conn.execute(query, params + [limit, offset]).fetchall()
        return {
            "total_count": total_count,
            "limit": limit,
            "offset": offset,
            "records": [dict(r) for r in rows],
        }


# ---------------------------------------------------------------------------
# Manpower Utilization & IPP DAL
# ---------------------------------------------------------------------------

def save_manpower_utilization(data: dict[str, Any], settings: Settings | None = None) -> dict[str, Any]:
    """Persist worker utilization and items-picked-per-hour metrics."""
    settings = settings or Settings()
    ensure_zepto_schema(settings)
    rec_id = data.get("id") or f"util_{uuid.uuid4().hex[:12]}"
    store = data.get("store_name", "JMU-Sainik Colony").strip()
    date_str = data.get("util_date", datetime.now().strftime("%Y-%m-%d")).strip()
    now_iso = datetime.now(timezone.utc).isoformat()

    items_picked = int(data.get("items_picked", 0))
    active_hours = float(data.get("active_pick_hours", 0.0))
    ipp = float(data.get("ipp", round(items_picked / active_hours, 1) if active_hours > 0 else 0.0))

    with _connect(settings) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO zepto_manpower_utilization (
                id, store_name, util_date, employee_id, employee_name, role,
                items_picked, active_pick_hours, idle_hours, ipp,
                flex_labor_cost, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                rec_id,
                store,
                date_str,
                data.get("employee_id", "").strip(),
                data.get("employee_name", "").strip(),
                data.get("role", "Picker").strip(),
                items_picked,
                active_hours,
                float(data.get("idle_hours", 0.0)),
                ipp,
                float(data.get("flex_labor_cost", 0.0)),
                now_iso,
                now_iso,
            ),
        )
    return {"id": rec_id, "ipp": ipp}


def get_manpower_utilization_summary(
    store_name: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Retrieve aggregated picker IPP, labor utilization, and efficiency metrics."""
    settings = settings or Settings()
    ensure_zepto_schema(settings)

    where = ["1=1"]
    params: list[Any] = []
    if store_name:
        where.append("store_name = ?")
        params.append(store_name)
    if start_date:
        where.append("util_date >= ?")
        params.append(start_date)
    if end_date:
        where.append("util_date <= ?")
        params.append(end_date)

    where_sql = " AND ".join(where)

    with _connect(settings) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"""
            SELECT * FROM zepto_manpower_utilization
            WHERE {where_sql}
            ORDER BY util_date DESC, ipp DESC
            """,
            params,
        ).fetchall()

        items = [dict(r) for r in rows]
        total_items = sum(i.get("items_picked", 0) for i in items)
        total_active_hours = sum(i.get("active_pick_hours", 0.0) for i in items)
        total_idle_hours = sum(i.get("idle_hours", 0.0) for i in items)
        total_flex_cost = sum(i.get("flex_labor_cost", 0.0) for i in items)
        avg_ipp = round(total_items / total_active_hours, 1) if total_active_hours > 0 else 0.0

        return {
            "total_items_picked": total_items,
            "total_active_hours": round(total_active_hours, 1),
            "total_idle_hours": round(total_idle_hours, 1),
            "avg_ipp": avg_ipp,
            "total_flex_cost": round(total_flex_cost, 2),
            "records": items,
        }


