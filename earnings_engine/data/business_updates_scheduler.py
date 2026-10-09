"""Business Updates & Operational Disclosures Scheduler.

Calculates anticipated corporate operational disclosure windows based on
known reporting cadences, fiscal quarter ends, and historical disclosure behavior.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import date, datetime, timedelta
from typing import Any

from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection

logger = logging.getLogger(__name__)

# Known Indian tickers with recurring operational disclosures (quarterly business updates / monthly sales / banking advances)
KNOWN_UPDATE_CADENCES: list[dict[str, Any]] = [
    # Retail / Consumer Updates
    {
        "ticker": "PCJEWELLER.NS",
        "company_name": "PC Jeweller Ltd",
        "update_type": "QUARTERLY_BUSINESS_UPDATE",
        "frequency": "QUARTERLY",
        "typical_days_after_period": 3,
        "window_spread": 4, # window: day 2 to day 6 after quarter end
        "confidence_score": 0.90,
    },
    {
        "ticker": "TITAN.NS",
        "company_name": "Titan Company Ltd",
        "update_type": "QUARTERLY_BUSINESS_UPDATE",
        "frequency": "QUARTERLY",
        "typical_days_after_period": 6,
        "window_spread": 3,
        "confidence_score": 0.95,
    },
    {
        "ticker": "DMART.NS",
        "company_name": "Avenue Supermarts Ltd (DMart)",
        "update_type": "QUARTERLY_BUSINESS_UPDATE",
        "frequency": "QUARTERLY",
        "typical_days_after_period": 2,
        "window_spread": 2,
        "confidence_score": 0.95,
    },
    {
        "ticker": "KALYANKJIL.NS",
        "company_name": "Kalyan Jewellers India Ltd",
        "update_type": "QUARTERLY_BUSINESS_UPDATE",
        "frequency": "QUARTERLY",
        "typical_days_after_period": 5,
        "window_spread": 3,
        "confidence_score": 0.90,
    },
    {
        "ticker": "SENCO.NS",
        "company_name": "Senco Gold Ltd",
        "update_type": "QUARTERLY_BUSINESS_UPDATE",
        "frequency": "QUARTERLY",
        "typical_days_after_period": 6,
        "window_spread": 4,
        "confidence_score": 0.85,
    },
    {
        "ticker": "MARICO.NS",
        "company_name": "Marico Ltd",
        "update_type": "QUARTERLY_BUSINESS_UPDATE",
        "frequency": "QUARTERLY",
        "typical_days_after_period": 5,
        "window_spread": 3,
        "confidence_score": 0.90,
    },
    {
        "ticker": "DABUR.NS",
        "company_name": "Dabur India Ltd",
        "update_type": "QUARTERLY_BUSINESS_UPDATE",
        "frequency": "QUARTERLY",
        "typical_days_after_period": 6,
        "window_spread": 3,
        "confidence_score": 0.90,
    },
    {
        "ticker": "GODREJCP.NS",
        "company_name": "Godrej Consumer Products Ltd",
        "update_type": "QUARTERLY_BUSINESS_UPDATE",
        "frequency": "QUARTERLY",
        "typical_days_after_period": 7,
        "window_spread": 3,
        "confidence_score": 0.88,
    },
    # Real Estate Pre-Sales & Bookings
    {
        "ticker": "GODREJPROP.NS",
        "company_name": "Godrej Properties Ltd",
        "update_type": "REALTY_BOOKINGS",
        "frequency": "QUARTERLY",
        "typical_days_after_period": 5,
        "window_spread": 4,
        "confidence_score": 0.90,
    },
    {
        "ticker": "OBEROIRLTY.NS",
        "company_name": "Oberoi Realty Ltd",
        "update_type": "REALTY_BOOKINGS",
        "frequency": "QUARTERLY",
        "typical_days_after_period": 4,
        "window_spread": 3,
        "confidence_score": 0.90,
    },
    {
        "ticker": "LODHA.NS",
        "company_name": "Macrotech Developers Ltd (Lodha)",
        "update_type": "REALTY_BOOKINGS",
        "frequency": "QUARTERLY",
        "typical_days_after_period": 4,
        "window_spread": 3,
        "confidence_score": 0.90,
    },
    {
        "ticker": "PRESTIGE.NS",
        "company_name": "Prestige Estates Projects Ltd",
        "update_type": "REALTY_BOOKINGS",
        "frequency": "QUARTERLY",
        "typical_days_after_period": 7,
        "window_spread": 4,
        "confidence_score": 0.85,
    },
    {
        "ticker": "SOBHA.NS",
        "company_name": "Sobha Ltd",
        "update_type": "REALTY_BOOKINGS",
        "frequency": "QUARTERLY",
        "typical_days_after_period": 5,
        "window_spread": 3,
        "confidence_score": 0.90,
    },
    {
        "ticker": "BRIGADE.NS",
        "company_name": "Brigade Enterprises Ltd",
        "update_type": "REALTY_BOOKINGS",
        "frequency": "QUARTERLY",
        "typical_days_after_period": 8,
        "window_spread": 4,
        "confidence_score": 0.85,
    },
    {
        "ticker": "SIGNATURE.NS",
        "company_name": "Signatureglobal (India) Ltd",
        "update_type": "REALTY_BOOKINGS",
        "frequency": "QUARTERLY",
        "typical_days_after_period": 7,
        "window_spread": 4,
        "confidence_score": 0.85,
    },
    # Auto & Monthly Dispatches
    {
        "ticker": "BAJAJ-AUTO.NS",
        "company_name": "Bajaj Auto Ltd",
        "update_type": "MONTHLY_SALES",
        "frequency": "MONTHLY",
        "typical_days_after_period": 1,
        "window_spread": 2,
        "confidence_score": 0.98,
    },
    {
        "ticker": "MARUTI.NS",
        "company_name": "Maruti Suzuki India Ltd",
        "update_type": "MONTHLY_SALES",
        "frequency": "MONTHLY",
        "typical_days_after_period": 1,
        "window_spread": 2,
        "confidence_score": 0.98,
    },
    {
        "ticker": "TATAMOTORS.NS",
        "company_name": "Tata Motors Ltd",
        "update_type": "MONTHLY_SALES",
        "frequency": "MONTHLY",
        "typical_days_after_period": 1,
        "window_spread": 2,
        "confidence_score": 0.98,
    },
    {
        "ticker": "M&M.NS",
        "company_name": "Mahindra & Mahindra Ltd",
        "update_type": "MONTHLY_SALES",
        "frequency": "MONTHLY",
        "typical_days_after_period": 1,
        "window_spread": 2,
        "confidence_score": 0.98,
    },
    {
        "ticker": "HEROMOTOCO.NS",
        "company_name": "Hero MotoCorp Ltd",
        "update_type": "MONTHLY_SALES",
        "frequency": "MONTHLY",
        "typical_days_after_period": 2,
        "window_spread": 2,
        "confidence_score": 0.98,
    },
    {
        "ticker": "EICHERMOT.NS",
        "company_name": "Eicher Motors Ltd",
        "update_type": "MONTHLY_SALES",
        "frequency": "MONTHLY",
        "typical_days_after_period": 1,
        "window_spread": 2,
        "confidence_score": 0.98,
    },
    {
        "ticker": "TVSMOTOR.NS",
        "company_name": "TVS Motor Company Ltd",
        "update_type": "MONTHLY_SALES",
        "frequency": "MONTHLY",
        "typical_days_after_period": 1,
        "window_spread": 2,
        "confidence_score": 0.98,
    },
    {
        "ticker": "ASHOKLEY.NS",
        "company_name": "Ashok Leyland Ltd",
        "update_type": "MONTHLY_SALES",
        "frequency": "MONTHLY",
        "typical_days_after_period": 1,
        "window_spread": 2,
        "confidence_score": 0.98,
    },
    {
        "ticker": "ESCORTS.NS",
        "company_name": "Escorts Kubota Ltd",
        "update_type": "MONTHLY_SALES",
        "frequency": "MONTHLY",
        "typical_days_after_period": 1,
        "window_spread": 2,
        "confidence_score": 0.98,
    },
    # Banking & Financial Services Advances/Deposits
    {
        "ticker": "HDFCBANK.NS",
        "company_name": "HDFC Bank Ltd",
        "update_type": "BANKING_ADVANCES",
        "frequency": "QUARTERLY",
        "typical_days_after_period": 4,
        "window_spread": 3,
        "confidence_score": 0.95,
    },
    {
        "ticker": "BANDHANBNK.NS",
        "company_name": "Bandhan Bank Ltd",
        "update_type": "BANKING_ADVANCES",
        "frequency": "QUARTERLY",
        "typical_days_after_period": 5,
        "window_spread": 3,
        "confidence_score": 0.90,
    },
    {
        "ticker": "FEDERALBNK.NS",
        "company_name": "Federal Bank Ltd",
        "update_type": "BANKING_ADVANCES",
        "frequency": "QUARTERLY",
        "typical_days_after_period": 3,
        "window_spread": 2,
        "confidence_score": 0.92,
    },
    {
        "ticker": "IDFCFIRSTB.NS",
        "company_name": "IDFC First Bank Ltd",
        "update_type": "BANKING_ADVANCES",
        "frequency": "QUARTERLY",
        "typical_days_after_period": 5,
        "window_spread": 3,
        "confidence_score": 0.90,
    },
    {
        "ticker": "AUBANK.NS",
        "company_name": "AU Small Finance Bank Ltd",
        "update_type": "BANKING_ADVANCES",
        "frequency": "QUARTERLY",
        "typical_days_after_period": 4,
        "window_spread": 3,
        "confidence_score": 0.92,
    },
    {
        "ticker": "RBLBANK.NS",
        "company_name": "RBL Bank Ltd",
        "update_type": "BANKING_ADVANCES",
        "frequency": "QUARTERLY",
        "typical_days_after_period": 4,
        "window_spread": 3,
        "confidence_score": 0.90,
    },
    {
        "ticker": "EQUITASBNK.NS",
        "company_name": "Equitas Small Finance Bank Ltd",
        "update_type": "BANKING_ADVANCES",
        "frequency": "QUARTERLY",
        "typical_days_after_period": 5,
        "window_spread": 3,
        "confidence_score": 0.88,
    },
    {
        "ticker": "UJJIVANSFB.NS",
        "company_name": "Ujjivan Small Finance Bank Ltd",
        "update_type": "BANKING_ADVANCES",
        "frequency": "QUARTERLY",
        "typical_days_after_period": 5,
        "window_spread": 3,
        "confidence_score": 0.88,
    },
]


def _get_period_end_dates(as_of: date) -> tuple[date, date]:
    """Calculate the most recent and upcoming period end dates for Quarterly and Monthly cadences."""
    year = as_of.year
    month = as_of.month

    # Quarter end dates (Mar 31, Jun 30, Sep 30, Dec 31)
    q_ends = [
        date(year - 1, 12, 31),
        date(year, 3, 31),
        date(year, 6, 30),
        date(year, 9, 30),
        date(year, 12, 31),
        date(year + 1, 3, 31),
    ]

    # Find the nearest relevant quarter end (either just passed or upcoming)
    past_q_ends = [d for d in q_ends if d <= as_of]
    recent_q_end = past_q_ends[-1] if past_q_ends else date(year, 1, 1)

    future_q_ends = [d for d in q_ends if d > as_of]
    next_q_end = future_q_ends[0] if future_q_ends else date(year, 12, 31)

    # Monthly end dates
    # Last day of previous month
    first_of_this_month = date(year, month, 1)
    last_month_end = first_of_this_month - timedelta(days=1)

    # Last day of current month
    if month == 12:
        this_month_end = date(year, 12, 31)
    else:
        this_month_end = date(year, month + 1, 1) - timedelta(days=1)

    return recent_q_end, next_q_end, last_month_end, this_month_end


def compute_anticipated_business_update_schedules(
    settings: Settings | None = None,
    as_of_date: date | None = None,
) -> list[dict[str, Any]]:
    """Compute anticipated corporate operational update schedules based on calendar periodicity."""
    as_of = as_of_date or date.today()
    recent_q_end, next_q_end, last_month_end, this_month_end = _get_period_end_dates(as_of)

    schedules = []

    for item in KNOWN_UPDATE_CADENCES:
        freq = item["frequency"]
        typical_days = item["typical_days_after_period"]
        window_spread = item.get("window_spread", 3)

        if freq == "QUARTERLY":
            # Check if we are within 25 days after the recent quarter end
            days_since_q = (as_of - recent_q_end).days
            if 0 <= days_since_q <= 25:
                ref_period_end = recent_q_end
            else:
                ref_period_end = next_q_end
        else: # MONTHLY
            # Check if we are within 10 days after the last month end
            days_since_m = (as_of - last_month_end).days
            if 0 <= days_since_m <= 10:
                ref_period_end = last_month_end
            else:
                ref_period_end = this_month_end

        window_start = ref_period_end + timedelta(days=max(1, typical_days - 1))
        window_end = ref_period_end + timedelta(days=typical_days + window_spread)

        # Determine status
        if as_of > window_end:
            status = "OVERDUE"
        elif window_start <= as_of <= window_end:
            status = "DUE_NOW"
        else:
            status = "ANTICIPATED"

        now_str = datetime.now().isoformat()
        schedules.append({
            "ticker": item["ticker"],
            "company_name": item["company_name"],
            "update_type": item["update_type"],
            "frequency": item["frequency"],
            "typical_days_after_period": typical_days,
            "next_expected_window_start": window_start.strftime("%Y-%m-%d"),
            "next_expected_window_end": window_end.strftime("%Y-%m-%d"),
            "confidence_score": item["confidence_score"],
            "status": status,
            "created_at": now_str,
            "updated_at": now_str,
        })

    return schedules


def _ensure_schema(conn: Any) -> None:
    """Ensure business_update_schedules table and indexes exist."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS business_update_schedules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            company_name TEXT,
            update_type TEXT NOT NULL,
            frequency TEXT NOT NULL,
            typical_days_after_period INTEGER DEFAULT 5,
            last_update_date TEXT,
            last_update_headline TEXT,
            last_update_reaction_1d REAL,
            last_update_reaction_3d REAL,
            next_expected_window_start TEXT,
            next_expected_window_end TEXT,
            confidence_score REAL DEFAULT 0.85,
            status TEXT DEFAULT 'ANTICIPATED',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(ticker, update_type)
        )
        """
    )
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_bus_sched_ticker ON business_update_schedules (ticker)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_bus_sched_window ON business_update_schedules (next_expected_window_start, next_expected_window_end)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_bus_sched_status ON business_update_schedules (status)")
    except Exception:
        pass


def sync_business_update_schedules_db(
    settings: Settings | None = None,
    as_of_date: date | None = None,
) -> int:
    """Upsert calculated anticipated schedules into SQLite business_update_schedules table."""
    schedules = compute_anticipated_business_update_schedules(settings, as_of_date)
    if not schedules:
        return 0

    now_iso = datetime.now().isoformat()

    with get_db_connection(settings) as conn:
        _ensure_schema(conn)
        cursor = conn.cursor()
        for s in schedules:
            cursor.execute(
                """
                INSERT INTO business_update_schedules (
                    ticker, company_name, update_type, frequency,
                    typical_days_after_period, next_expected_window_start,
                    next_expected_window_end, confidence_score, status,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(ticker, update_type) DO UPDATE SET
                    company_name = excluded.company_name,
                    frequency = excluded.frequency,
                    typical_days_after_period = excluded.typical_days_after_period,
                    next_expected_window_start = excluded.next_expected_window_start,
                    next_expected_window_end = excluded.next_expected_window_end,
                    confidence_score = excluded.confidence_score,
                    status = excluded.status,
                    updated_at = excluded.updated_at
                """,
                (
                    s["ticker"],
                    s["company_name"],
                    s["update_type"],
                    s["frequency"],
                    s["typical_days_after_period"],
                    s["next_expected_window_start"],
                    s["next_expected_window_end"],
                    s["confidence_score"],
                    s["status"],
                    now_iso,
                    now_iso,
                )
            )
        conn.commit()

    logger.info("Synced %d business update schedules to database", len(schedules))
    return len(schedules)


def get_anticipated_schedules(
    settings: Settings | None = None,
    status: str | None = None,
    days_ahead: int = 14,
    as_of_date: date | None = None,
) -> list[dict[str, Any]]:
    """Retrieve anticipated business update schedules from database, syncing first if table is empty."""
    as_of = as_of_date or date.today()
    as_of_str = as_of.strftime("%Y-%m-%d")
    max_date_str = (as_of + timedelta(days=days_ahead)).strftime("%Y-%m-%d")

    with get_db_connection(settings) as conn:
        _ensure_schema(conn)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Check if table has rows; if not, sync first
        cursor.execute("SELECT COUNT(*) as cnt FROM business_update_schedules")
        row = cursor.fetchone()
        if not row or row["cnt"] == 0:
            sync_business_update_schedules_db(settings, as_of)

        query = """
            SELECT * FROM business_update_schedules
            WHERE 1=1
        """
        params: list[Any] = []

        if status:
            query += " AND status = ?"
            params.append(status.upper())
        else:
            # By default include DUE_NOW, ANTICIPATED within window
            query += " AND (status IN ('DUE_NOW', 'ANTICIPATED', 'OVERDUE'))"

        if days_ahead > 0:
            query += " AND next_expected_window_start <= ?"
            params.append(max_date_str)

        query += " ORDER BY next_expected_window_start ASC, ticker ASC"

        cursor.execute(query, params)
        rows = cursor.fetchall()
        return [dict(r) for r in rows]
