"""Unit tests for DB-first TTL caching and batch optimization of market quotes."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone, time as dt_time
from unittest.mock import MagicMock, patch
import pytest

from earnings_engine.config import Settings
from earnings_engine.data.prices import (
    _build_quote_from_cached_record,
    _get_market_session_status,
    _is_cached_quote_fresh,
    fetch_batch_live_quotes,
    fetch_live_quote,
)


def test_market_session_status_nse_and_us():
    """Verify market session status identifies NSE vs US trading hours correctly."""
    status_nse = _get_market_session_status("RELIANCE.NS")
    assert status_nse["open_time"] == dt_time(9, 15)
    assert status_nse["close_time"] == dt_time(15, 30)
    assert "is_open" in status_nse
    assert "is_weekend" in status_nse
    assert "market_date" in status_nse

    status_us = _get_market_session_status("AAPL")
    assert status_us["open_time"] == dt_time(9, 30)
    assert status_us["close_time"] == dt_time(16, 0)
    assert "is_open" in status_us
    assert "is_weekend" in status_us


def test_is_cached_quote_fresh_evaluations():
    """Verify freshness logic across market open, closed, post-market, pre-market, and weekend."""
    # 1. Invalid price
    assert not _is_cached_quote_fresh({"cur_close": None}, {"is_open": False})
    assert not _is_cached_quote_fresh({"cur_close": 0.0}, {"is_open": False})

    # 2. Weekend
    weekend_session = {"is_open": False, "is_weekend": True}
    assert _is_cached_quote_fresh({"cur_close": 150.0}, weekend_session)

    # 3. Post-market
    post_session = {
        "is_open": False,
        "is_weekend": False,
        "is_post_market": True,
        "market_date": "2026-09-11",
        "close_time": dt_time(15, 30),
    }
    # Today's close already in DB -> Fresh
    assert _is_cached_quote_fresh({"cur_close": 150.0, "cur_date": "2026-09-11"}, post_session)
    # Today's close not in DB -> Stale (needs to settle today's bar)
    assert not _is_cached_quote_fresh({"cur_close": 150.0, "cur_date": "2026-09-10"}, post_session)

    # 4. Pre-market
    pre_session = {
        "is_open": False,
        "is_weekend": False,
        "is_pre_market": True,
        "market_date": "2026-09-11",
    }
    # Recent close within 4 days -> Fresh
    assert _is_cached_quote_fresh({"cur_close": 150.0, "cur_date": "2026-09-10"}, pre_session)
    # Very old close (> 4 days) -> Stale
    assert not _is_cached_quote_fresh({"cur_close": 150.0, "cur_date": "2026-09-01"}, pre_session)

    # 5. Market Open (Live trading session)
    open_session = {
        "is_open": True,
        "is_weekend": False,
        "is_pre_market": False,
        "is_post_market": False,
        "market_date": "2026-09-11",
    }
    # Fresh within 5 minutes
    fresh_time = (datetime.now() - timedelta(minutes=2)).isoformat()
    assert _is_cached_quote_fresh(
        {"cur_close": 150.0, "prices_fetched_at": fresh_time},
        open_session,
        ttl_minutes=5,
    )
    # Stale after 5 minutes
    stale_time = (datetime.now() - timedelta(minutes=6)).isoformat()
    assert not _is_cached_quote_fresh(
        {"cur_close": 150.0, "prices_fetched_at": stale_time},
        open_session,
        ttl_minutes=5,
    )
    # Missing prices_fetched_at
    assert not _is_cached_quote_fresh(
        {"cur_close": 150.0, "prices_fetched_at": None},
        open_session,
        ttl_minutes=5,
    )


def test_build_quote_from_cached_record_structure_and_metrics():
    """Verify built quote dictionary adheres strictly to the 18-key contract."""
    record = {
        "ticker": "TEST.NS",
        "cur_close": 200.0,
        "prev_close": 190.0,
        "cur_open": 192.0,
        "cur_high": 205.0,
        "cur_low": 191.0,
        "w52_high": 250.0,
        "w52_low": 150.0,
        "cur_vol": 1000000,
        "avg_vol": 800000,
        "market_cap": 50000000000.0,
        "prices_fetched_at": "2026-09-11T10:00:00",
    }
    session = {"is_open": True}

    quote = _build_quote_from_cached_record("TEST.NS", record, session)

    expected_keys = {
        "ticker", "current_price", "previous_close", "day_change", "day_change_pct",
        "day_open", "day_high", "day_low", "week_52_high", "week_52_low",
        "volume", "avg_volume", "market_cap", "currency", "is_live",
        "last_updated", "pct_from_52w_high", "pct_from_52w_low",
    }
    assert set(quote.keys()) == expected_keys
    assert quote["ticker"] == "TEST.NS"
    assert quote["current_price"] == 200.0
    assert quote["previous_close"] == 190.0
    assert quote["day_change"] == 10.0
    assert quote["day_change_pct"] == round((200.0 / 190.0 - 1.0) * 100.0, 2)
    assert quote["pct_from_52w_high"] == round((200.0 / 250.0 - 1.0) * 100.0, 2)
    assert quote["pct_from_52w_low"] == round((200.0 / 150.0 - 1.0) * 100.0, 2)
    assert quote["currency"] == "INR"
    assert quote["is_live"] is True
    assert quote["volume"] == 1000000
    assert quote["avg_volume"] == 800000


def test_fetch_live_quote_cache_hit_bypasses_network():
    """Verify that when SQLite cache is fresh, fetch_live_quote does NOT invoke yfinance."""
    fresh_time = (datetime.now() - timedelta(minutes=1)).isoformat()
    mock_record = {
        "ticker": "CACHED.NS",
        "cur_close": 350.0,
        "prev_close": 340.0,
        "cur_open": 342.0,
        "cur_high": 355.0,
        "cur_low": 341.0,
        "w52_high": 400.0,
        "w52_low": 280.0,
        "cur_vol": 500000,
        "avg_vol": 450000,
        "market_cap": 100000000000.0,
        "cur_date": "2026-09-11",
        "prices_fetched_at": fresh_time,
    }

    with patch("earnings_engine.data.prices._get_cached_quotes_batch", return_value={"CACHED.NS": mock_record}), \
         patch("earnings_engine.data.prices.yf.Ticker") as mock_yf:

        quote = fetch_live_quote("CACHED.NS", force=False)

        assert mock_yf.call_count == 0
        assert quote["ticker"] == "CACHED.NS"
        assert quote["current_price"] == 350.0
        assert quote["previous_close"] == 340.0


def test_fetch_live_quote_force_bypasses_cache():
    """Verify that force=True calls network even if cache is fresh."""
    fresh_time = (datetime.now() - timedelta(minutes=1)).isoformat()
    mock_record = {
        "ticker": "FORCED.NS",
        "cur_close": 500.0,
        "prev_close": 490.0,
        "prices_fetched_at": fresh_time,
    }

    fast_info = MagicMock()
    fast_info.last_price = 505.0
    fast_info.previous_close = 490.0
    fast_info.open = 495.0
    fast_info.day_high = 510.0
    fast_info.day_low = 492.0
    fast_info.year_high = 550.0
    fast_info.year_low = 400.0
    fast_info.last_volume = 1200000
    fast_info.three_month_average_volume = 1000000
    fast_info.market_cap = 200000000000.0

    mock_ticker_inst = MagicMock()
    mock_ticker_inst.fast_info = fast_info

    with patch("earnings_engine.data.prices._get_cached_quotes_batch", return_value={"FORCED.NS": mock_record}), \
         patch("earnings_engine.data.prices.yf.Ticker", return_value=mock_ticker_inst) as mock_yf, \
         patch("earnings_engine.data.prices._connect") as mock_conn:

        quote = fetch_live_quote("FORCED.NS", force=True, sync_db=False)

        assert mock_yf.call_count == 1
        assert quote["current_price"] == 505.0


def test_fetch_batch_live_quotes_partitions_fresh_and_stale():
    """Verify fetch_batch_live_quotes only fetches stale tickers over network."""
    fresh_time = (datetime.now() - timedelta(minutes=1)).isoformat()
    mock_batch = {
        "FRESH.NS": {
            "ticker": "FRESH.NS",
            "cur_close": 100.0,
            "prev_close": 98.0,
            "cur_open": 99.0,
            "cur_high": 102.0,
            "cur_low": 98.0,
            "w52_high": 120.0,
            "w52_low": 80.0,
            "cur_vol": 100000,
            "avg_vol": 90000,
            "market_cap": 10000000000.0,
            "cur_date": "2026-09-11",
            "prices_fetched_at": fresh_time,
        }
        # STALE.NS is not in cache or stale
    }

    mock_stale_quote = {
        "ticker": "STALE.NS",
        "current_price": 250.0,
        "previous_close": 240.0,
        "day_change": 10.0,
        "day_change_pct": 4.17,
        "day_open": 242.0,
        "day_high": 255.0,
        "day_low": 241.0,
        "week_52_high": 300.0,
        "week_52_low": 180.0,
        "volume": 200000,
        "avg_volume": 180000,
        "market_cap": 50000000000.0,
        "currency": "INR",
        "is_live": True,
        "last_updated": datetime.now().isoformat(),
        "pct_from_52w_high": -16.67,
        "pct_from_52w_low": 38.89,
    }

    with patch("earnings_engine.data.prices._get_cached_quotes_batch", return_value=mock_batch), \
         patch("earnings_engine.data.prices.fetch_live_quote", return_value=mock_stale_quote) as mock_single:

        quotes = fetch_batch_live_quotes(["FRESH.NS", "STALE.NS"], force=False)

        # Only STALE.NS should have triggered fetch_live_quote
        assert mock_single.call_count == 1
        assert mock_single.call_args[0][0] == "STALE.NS"

        assert "FRESH.NS" in quotes
        assert "STALE.NS" in quotes
        assert quotes["FRESH.NS"]["current_price"] == 100.0
        assert quotes["STALE.NS"]["current_price"] == 250.0
