from datetime import datetime, timezone
from unittest.mock import patch
from earnings_engine.data.prices import get_market_session, fetch_live_quote


def test_get_market_session_on_holiday():
    # 2026-10-02 11:00 IST (UTC 05:30) - Friday Gandhi Jayanti holiday
    dt_holiday = datetime(2026, 10, 2, 5, 30, tzinfo=timezone.utc)
    session = get_market_session("RELIANCE.NS", now_dt=dt_holiday)
    assert session["is_open"] is False
    assert session["is_holiday"] is True
    assert session["session"] == "closed"


def test_get_market_session_on_trading_day():
    # 2026-10-01 11:00 IST (UTC 05:30) - Thursday trading day in-hours
    dt_open = datetime(2026, 10, 1, 5, 30, tzinfo=timezone.utc)
    session = get_market_session("RELIANCE.NS", now_dt=dt_open)
    assert session["is_open"] is True
    assert session["is_holiday"] is False
    assert session["session"] == "regular"


def test_fetch_live_quote_on_holiday_no_network():
    dt_holiday = datetime(2026, 10, 2, 5, 30, tzinfo=timezone.utc)
    with patch("yfinance.Ticker") as mock_yf:
        # On holiday, fetch_live_quote should serve from SQLite without invoking yfinance
        quote = fetch_live_quote("RELIANCE.NS", now_dt=dt_holiday, sync_db=False)
        assert mock_yf.called is False
        assert "symbol" in quote
