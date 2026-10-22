"""Market timing, schedule calculations, and trading calendar logic."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

from earnings_engine.data.trading_calendar import (
    is_market_holiday,
    is_trading_day,
    get_latest_completed_trading_day,
    is_indian_market_open,
)
from earnings_engine.data.market_pulse.constants import IST_OFFSET, IST_TZ

logger = logging.getLogger(__name__)


def is_market_open(ts: float | None = None) -> bool:
    """Check if Indian market (NSE/BSE) is currently open at the given UTC timestamp."""
    if ts is None:
        ts = datetime.now(timezone.utc).timestamp()
    return is_indian_market_open(ts)


def format_iso_to_ist(iso_str: str | None, include_seconds: bool = False) -> str:
    """Format an ISO timestamp to human-readable IST string (e.g. '26 Sep 2026, 18:42 IST')."""
    if not iso_str:
        return "—"
    try:
        clean_str = str(iso_str).replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        ist_dt = dt.astimezone(IST_TZ)
        if include_seconds:
            return ist_dt.strftime("%d %b %Y, %H:%M:%S IST")
        return ist_dt.strftime("%d %b %Y, %H:%M IST")
    except Exception:
        return str(iso_str)


def compute_fii_dii_release_schedule(
    latest_date_in_db: str | None = None,
    now_dt: datetime | None = None,
) -> dict[str, Any]:
    """Calculate the expected next NSE FII/DII cash market settlement release time and countdown.

    NSE publishes daily cash market FII & DII provisional settlement figures on trading days
    (Monday - Friday) around 17:30 - 19:30 IST, with standard benchmark release target ~18:30 IST.
    """
    if now_dt is None:
        now_dt = datetime.now(timezone.utc)

    # Convert UTC to IST (+5:30)
    ist_dt = now_dt.astimezone(IST_TZ) if now_dt.tzinfo else (now_dt + IST_OFFSET)
    time_val = ist_dt.hour + ist_dt.minute / 60.0 + ist_dt.second / 3600.0

    today_date = ist_dt.date()
    today_str = today_date.strftime("%Y-%m-%d")
    is_today_settled = (latest_date_in_db == today_str)
    is_today_holiday = is_market_holiday(today_date)
    is_today_trading = is_trading_day(today_date)

    if not is_today_trading:
        # Weekend or Market Holiday -> Next active trading day
        next_day = today_date + timedelta(days=1)
        while not is_trading_day(next_day):
            next_day += timedelta(days=1)
        target_date = next_day
        status = "holiday_pause" if is_today_holiday else "weekend_pause"
        label = f"{target_date.strftime('%A')} ~18:30 IST"
    else:
        # Active trading day
        if time_val < 18.5:
            target_date = today_date
            status = "pending_today"
            label = "Today ~18:30 IST"
        else:
            if is_today_settled:
                next_day = today_date + timedelta(days=1)
                while not is_trading_day(next_day):
                    next_day += timedelta(days=1)
                target_date = next_day
                status = "settled"
                label = f"{target_date.strftime('%A')} ~18:30 IST"
            else:
                target_date = today_date
                status = "awaiting_settlement"
                label = "Today (Awaiting NSE Release)"

    target_dt_ist = datetime.combine(target_date, datetime.min.time()).replace(hour=18, minute=30, second=0)
    target_dt_utc = (target_dt_ist - IST_OFFSET).replace(tzinfo=timezone.utc)

    eta_seconds = max(0, int((target_dt_utc - now_dt).total_seconds()))
    hours = eta_seconds // 3600
    minutes = (eta_seconds % 3600) // 60

    if status == "awaiting_settlement":
        countdown_text = "Awaiting Release (Due ~18:30 IST)"
    elif eta_seconds == 0:
        countdown_text = "Release Expected Now"
    elif hours >= 24:
        days = hours // 24
        rem_hours = hours % 24
        countdown_text = f"in {days}d {rem_hours}h"
    elif hours > 0:
        countdown_text = f"in {hours}h {minutes}m"
    else:
        countdown_text = f"in {minutes}m"

    return {
        "expected_release_utc": target_dt_utc.isoformat(),
        "expected_release_ist": target_dt_ist.strftime("%d %b %Y, 18:30 IST"),
        "release_label": label,
        "label": label,
        "countdown_text": countdown_text,
        "countdown": countdown_text,
        "eta_seconds": eta_seconds,
        "status": status,
        "is_today_settled": is_today_settled,
        "latest_settled_date": latest_date_in_db or "",
    }


def get_expected_latest_trading_date(now_dt: datetime | None = None) -> str:
    """Calculate the expected latest trading day (ISO format YYYY-MM-DD) for which
    FII/DII cash market settlement figures should be published.

    NSE publishes cash market FII/DII settlements around 17:30 - 18:30 IST (12:00 - 13:00 UTC).
    Cutoff used: 18:00 IST (12:30 UTC).
    """
    if now_dt is None:
        now_dt = datetime.now(timezone.utc)

    # Convert UTC to IST (+5:30)
    ist_dt = now_dt.astimezone(IST_TZ) if now_dt.tzinfo else (now_dt + IST_OFFSET)
    target_date = ist_dt.date()

    if not is_trading_day(target_date):
        # Weekend or Holiday -> latest completed trading day
        target = get_latest_completed_trading_day(target_date)
    else:
        time_val = ist_dt.hour + ist_dt.minute / 60.0
        # If before 18:00 IST (18.0), today's settlement is not released yet; expect previous trading day
        if time_val < 18.0:
            target = get_latest_completed_trading_day(target_date - timedelta(days=1))
        else:
            target = target_date

    return target.strftime("%Y-%m-%d")
