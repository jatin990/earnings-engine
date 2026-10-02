"""Authoritative Trading Calendar & Market Session Resolver for NSE Indian Equities."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Set

IST_OFFSET = timedelta(hours=5, minutes=30)
IST_TZ = timezone(IST_OFFSET)

# ---------------------------------------------------------------------------
# Official NSE Equity Market Holidays
# ---------------------------------------------------------------------------

NSE_HOLIDAYS_2024: Set[str] = {
    "2024-01-22",  # Special Holiday
    "2024-01-26",  # Republic Day
    "2024-03-08",  # Mahashivratri
    "2024-03-25",  # Holi
    "2024-04-11",  # Id-Ul-Fitr (Ramzan Id)
    "2024-04-17",  # Shri Ram Navami
    "2024-05-01",  # Maharashtra Day
    "2024-05-20",  # Parliamentary Elections
    "2024-06-17",  # Bakri Id
    "2024-07-17",  # Moharram
    "2024-08-15",  # Independence Day
    "2024-10-02",  # Mahatma Gandhi Jayanti
    "2024-11-01",  # Diwali Laxmi Pujan (Muhurat Trading only)
    "2024-11-15",  # Gurunanak Jayanti
    "2024-12-25",  # Christmas
}

NSE_HOLIDAYS_2025: Set[str] = {
    "2025-02-26",  # Mahashivratri
    "2025-03-14",  # Holi
    "2025-03-31",  # Id-Ul-Fitr
    "2025-04-10",  # Shri Mahavir Jayanti
    "2025-04-14",  # Dr. Baba Saheb Ambedkar Jayanti
    "2025-04-18",  # Good Friday
    "2025-05-01",  # Maharashtra Day
    "2025-08-15",  # Independence Day
    "2025-08-27",  # Ganesh Chaturthi
    "2025-10-02",  # Mahatma Gandhi Jayanti
    "2025-10-21",  # Diwali Laxmi Pujan
    "2025-10-22",  # Diwali Balipratipada
    "2025-11-05",  # Gurunanak Jayanti
    "2025-12-25",  # Christmas
}

NSE_HOLIDAYS_2026: Set[str] = {
    "2026-01-26",  # Republic Day
    "2026-03-03",  # Holi
    "2026-03-20",  # Id-Ul-Fitr
    "2026-04-03",  # Good Friday
    "2026-04-14",  # Dr. Baba Saheb Ambedkar Jayanti
    "2026-05-01",  # Maharashtra Day
    "2026-06-17",  # Bakri Id
    "2026-08-15",  # Independence Day
    "2026-09-02",  # Janmashtami
    "2026-10-02",  # Mahatma Gandhi Jayanti
    "2026-10-20",  # Dussehra
    "2026-11-09",  # Diwali Laxmi Pujan
    "2026-11-10",  # Diwali Balipratipada
    "2026-12-25",  # Christmas
}

ALL_NSE_HOLIDAYS: Set[str] = NSE_HOLIDAYS_2024 | NSE_HOLIDAYS_2025 | NSE_HOLIDAYS_2026


def is_market_holiday(d: date) -> bool:
    """Check if a date is a scheduled NSE equity market holiday."""
    return d.isoformat() in ALL_NSE_HOLIDAYS


def is_trading_day(d: date) -> bool:
    """Check if a date is an active NSE trading day (not weekend or scheduled holiday)."""
    if d.weekday() >= 5:  # Saturday (5) or Sunday (6)
        return False
    return not is_market_holiday(d)


def get_latest_completed_trading_day(ref_date: date | None = None) -> date:
    """Get the most recent completed NSE trading day prior to or on ref_date."""
    cur = ref_date or datetime.now(timezone.utc).date()
    while not is_trading_day(cur):
        cur -= timedelta(days=1)
    return cur


def is_indian_market_open(ts: float | None = None) -> bool:
    """Check if the Indian equity market is currently open for continuous trading (09:15 - 15:30 IST on a trading day)."""
    now_dt = datetime.fromtimestamp(ts, tz=timezone.utc) if ts else datetime.now(timezone.utc)
    ist_dt = now_dt.astimezone(IST_TZ)

    if not is_trading_day(ist_dt.date()):
        return False

    time_val = ist_dt.hour + ist_dt.minute / 60.0
    # Continuous market hours: 09:15 to 15:30 IST
    return 9.25 <= time_val < 15.5
