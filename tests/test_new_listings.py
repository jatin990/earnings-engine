"""Unit tests for Recent Market Additions, IPOs and Debut Earnings Sequence Tracking."""
import pytest
import pandas as pd
from datetime import datetime, timedelta

from earnings_engine.data.new_listings import (
    get_recent_nse_additions,
    compute_ticker_result_sequence,
    _EQUITY_LIST_CACHE,
)
from earnings_engine.api.stock_api import get_recent_market_additions, sync_recent_additions_to_watchlist
from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection


def test_compute_ticker_result_sequence_debut():
    settings = Settings()
    # Ticker with 0 past earnings in database -> 1st result (Debut)
    seq0 = compute_ticker_result_sequence("NEWIPO_STOCK.NS", settings=settings)
    assert seq0["result_sequence_number"] == 1
    assert seq0["is_debut"] is True
    assert "1st Result" in seq0["result_sequence_label"]
    assert seq0["result_sequence_badge"] == "amber"


def test_compute_ticker_result_sequence_history(monkeypatch, tmp_path):
    settings = Settings()
    conn = get_db_connection(settings)

    # Insert 1 mock past earnings date
    ticker_test = "TEST_IPO2.NS"
    conn.execute(
        "INSERT OR IGNORE INTO earnings_history (ticker, earnings_date, eps_reported, surprise_pct) VALUES (?, ?, ?, ?)",
        (ticker_test, "2026-05-15", 4.5, 12.0),
    )
    if hasattr(conn, "commit"):
        conn.commit()

    seq1 = compute_ticker_result_sequence(ticker_test, settings=settings)
    assert seq1["result_sequence_number"] == 2
    assert seq1["is_debut"] is False
    assert "2nd Public Result" in seq1["result_sequence_label"]
    assert seq1["result_sequence_badge"] == "emerald"

    # Clean up test row
    conn.execute("DELETE FROM earnings_history WHERE ticker = ?", (ticker_test,))
    if hasattr(conn, "commit"):
        conn.commit()


def test_get_recent_nse_additions_mock(monkeypatch):
    # Mock cached equity list dataframe with test listings
    now = datetime.now()
    mock_df = pd.DataFrame([
        {
            "SYMBOL": "TESTNEW1",
            "NAME OF COMPANY": "Test New Mainboard Ltd",
            "SERIES": "EQ",
            "DATE OF LISTING": (now - timedelta(days=5)).strftime("%d-%b-%Y"),
            "LISTING_DATE": now - timedelta(days=5),
            "FACE VALUE": 10,
        },
        {
            "SYMBOL": "TESTSME1",
            "NAME OF COMPANY": "Test SME Enterprise Ltd",
            "SERIES": "SM",
            "DATE OF LISTING": (now - timedelta(days=20)).strftime("%d-%b-%Y"),
            "LISTING_DATE": now - timedelta(days=20),
            "FACE VALUE": 10,
        },
        {
            "SYMBOL": "TESTOLD1",
            "NAME OF COMPANY": "Test Old Company Ltd",
            "SERIES": "EQ",
            "DATE OF LISTING": (now - timedelta(days=400)).strftime("%d-%b-%Y"),
            "LISTING_DATE": now - timedelta(days=400),
            "FACE VALUE": 1,
        }
    ])

    monkeypatch.setattr("earnings_engine.data.new_listings.fetch_all_nse_equities_cached", lambda: mock_df.copy())

    # Fetch 90 days
    additions = get_recent_nse_additions(days=90, limit=50, settings=Settings())
    assert len(additions) == 2
    
    t1 = additions[0]
    assert t1["ticker"] == "TESTNEW1.NS"
    assert t1["company_name"] == "Test New Mainboard Ltd"
    assert t1["is_sme"] is False
    assert t1["result_sequence_number"] == 1
    assert "1st Result" in t1["result_sequence_label"]

    t2 = additions[1]
    assert t2["ticker"] == "TESTSME1.NS"
    assert t2["is_sme"] is True


def test_api_recent_market_additions(monkeypatch):
    # Test API endpoint response structure
    res = get_recent_market_additions(days=180, limit=10, settings=Settings())
    assert res["success"] is True
    assert "items" in res
    assert res["lookback_days"] == 180
