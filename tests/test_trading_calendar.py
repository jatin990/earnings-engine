from datetime import date, datetime, timezone
from earnings_engine.data.trading_calendar import (
    is_trading_day,
    is_market_holiday,
    get_latest_completed_trading_day,
    is_indian_market_open,
)


def test_trading_calendar_holidays_2026():
    # 2026-10-02 is Gandhi Jayanti (Friday holiday)
    gandhi_jayanti = date(2026, 10, 2)
    assert is_market_holiday(gandhi_jayanti) is True
    assert is_trading_day(gandhi_jayanti) is False

    # 2026-10-01 is Thursday (regular trading day)
    thursday = date(2026, 10, 1)
    assert is_market_holiday(thursday) is False
    assert is_trading_day(thursday) is True

    # 2026-10-03 is Saturday (weekend)
    saturday = date(2026, 10, 3)
    assert is_trading_day(saturday) is False
    assert is_market_holiday(saturday) is False


def test_get_latest_completed_trading_day():
    # On Gandhi Jayanti (2026-10-02), latest completed trading day is 2026-10-01
    latest = get_latest_completed_trading_day(date(2026, 10, 2))
    assert latest == date(2026, 10, 1)

    # On a Monday after weekend (e.g. 2026-10-05), prior completed trading day check
    latest_weekend = get_latest_completed_trading_day(date(2026, 10, 4))  # Sunday
    assert latest_weekend == date(2026, 10, 1)


def test_is_indian_market_open():
    # 2026-10-02 at 11:00 AM IST (holiday) -> False
    # 11:00 IST = 05:30 UTC
    dt_holiday = datetime(2026, 10, 2, 5, 30, tzinfo=timezone.utc)
    assert is_indian_market_open(dt_holiday.timestamp()) is False

    # 2026-10-01 at 11:00 AM IST (trading day in-hours) -> True
    dt_open = datetime(2026, 10, 1, 5, 30, tzinfo=timezone.utc)
    assert is_indian_market_open(dt_open.timestamp()) is True

    # 2026-10-01 at 18:00 IST (trading day post-market) -> False
    # 18:00 IST = 12:30 UTC
    dt_closed = datetime(2026, 10, 1, 12, 30, tzinfo=timezone.utc)
    assert is_indian_market_open(dt_closed.timestamp()) is False
