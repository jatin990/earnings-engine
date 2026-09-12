"""Unit tests for Recent Market Additions, IPOs and Debut Earnings Sequence Tracking."""
import pytest
import pandas as pd
from datetime import datetime, timedelta

from earnings_engine.data.new_listings import (
    get_recent_nse_additions,
    get_ipo_stock_detail,
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


def test_get_recent_nse_additions_enriched_fields(monkeypatch):
    settings = Settings()
    conn = get_db_connection(settings)

    ticker = "TEST_ENRICHED.NS"
    now = datetime.now()

    # Insert 10 days of prices into price_history
    # Listing day close: 100.0, Day 9 close: 150.0, ATH: 160.0, ATL: 95.0
    for i in range(10):
        d_str = (now - timedelta(days=10 - i)).strftime("%Y-%m-%d")
        close_p = 100.0 + (i * 5.0)  # 100 to 145
        if i == 9:
            close_p = 150.0
        high_p = 160.0 if i == 5 else close_p + 5.0
        low_p = 95.0 if i == 0 else close_p - 5.0
        conn.execute(
            "INSERT OR REPLACE INTO price_history (ticker, date, open, high, low, close, volume) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (ticker, d_str, close_p - 1.0, high_p, low_p, close_p, 1000 + i * 100),
        )
    if hasattr(conn, "commit"):
        conn.commit()

    mock_df = pd.DataFrame([
        {
            "SYMBOL": "TEST_ENRICHED",
            "NAME OF COMPANY": "Test Enriched Company Ltd",
            "SERIES": "EQ",
            "DATE OF LISTING": (now - timedelta(days=10)).strftime("%d-%b-%Y"),
            "LISTING_DATE": now - timedelta(days=10),
            "FACE VALUE": 10,
        }
    ])
    monkeypatch.setattr("earnings_engine.data.new_listings.fetch_all_nse_equities_cached", lambda: mock_df.copy())

    try:
        additions = get_recent_nse_additions(days=30, limit=10, settings=settings)
        assert len(additions) == 1
        item = additions[0]
        assert item["ticker"] == ticker
        assert item["listing_price"] == 100.0
        assert item["cmp"] == 150.0
        assert item["return_since_listing_pct"] == 50.0
        assert item["ath_price"] == 160.0
        # ath_distance_pct = ((150 - 160) / 160) * 100 = -6.25%
        assert item["ath_distance_pct"] == -6.25
        assert item["atl_price"] == 95.0
        assert item["return_7d_pct"] is not None
        assert item["volume_ratio_5_20"] is not None
    finally:
        conn.execute("DELETE FROM price_history WHERE ticker = ?", (ticker,))
        if hasattr(conn, "commit"):
            conn.commit()


def test_get_ipo_stock_detail(monkeypatch):
    settings = Settings()
    from earnings_engine.data.migrations import apply_migrations
    apply_migrations(settings)
    conn = get_db_connection(settings)

    ticker = "TEST_IPO_DETAIL.NS"
    now = datetime.now()

    # 1. Insert 25 days of price history
    for i in range(25):
        d_str = (now - timedelta(days=30 - i)).strftime("%Y-%m-%d")
        close_p = 200.0 + (i * 2.0)  # 200 to 248
        high_p = close_p + 4.0
        low_p = close_p - 4.0
        conn.execute(
            "INSERT OR REPLACE INTO price_history (ticker, date, open, high, low, close, volume) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (ticker, d_str, close_p, high_p, low_p, close_p, 5000 + i * 200),
        )

    # 2. Insert earnings_history (1 past event)
    conn.execute(
        "INSERT OR REPLACE INTO earnings_history (ticker, earnings_date, eps_reported, eps_estimate, surprise_pct, source) VALUES (?, ?, ?, ?, ?, ?)",
        (ticker, "2026-06-15", 4.8, 4.5, 6.67, "yfinance"),
    )

    # 3. Insert earnings_calendar (1 upcoming board meeting)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS earnings_calendar (
            ticker TEXT,
            earnings_date TEXT,
            eps_estimate REAL,
            eps_reported REAL,
            surprise_pct REAL,
            source TEXT
        )
    """)
    conn.execute(
        "INSERT OR REPLACE INTO earnings_calendar (ticker, earnings_date, eps_estimate, eps_reported, surprise_pct, source) VALUES (?, ?, ?, ?, ?, ?)",
        (ticker, "2026-09-25", 5.2, None, None, "nse"),
    )

    # 4. Insert institutional_holdings (Mutual Fund)
    conn.execute(
        """
        INSERT OR REPLACE INTO institutional_holdings
        (id, ticker, fund_name, fund_type, quarter, shares_held, stake_pct, holding_value_cr, action, reported_date, created_at)
        VALUES (999901, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (ticker, "Nippon India Small Cap Fund", "Mutual Fund (DII)", "Q1 FY27", 350000, 1.75, 18.5, "BUY", "2026-08-31", now.isoformat()),
    )

    # 5. Insert shareholding_patterns
    conn.execute(
        """
        INSERT OR REPLACE INTO shareholding_patterns
        (ticker, quarter, promoter_pct, fii_pct, dii_mf_pct, public_retail_pct, other_pct, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (ticker, "Q1 FY27", 62.5, 10.2, 12.8, 14.5, 0.0, now.isoformat()),
    )

    # 6. Insert institutional_block_deals
    conn.execute(
        """
        INSERT OR REPLACE INTO institutional_block_deals
        (id, deal_date, ticker, client_name, deal_type, quantity, price, value_cr, pct_equity, exchange, created_at)
        VALUES (999901, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("2026-08-15", ticker, "GOLDMAN SACHS INDIA", "BUY", 120000, 215.0, 2.58, 0.6, "NSE", now.isoformat()),
    )

    if hasattr(conn, "commit"):
        conn.commit()

    mock_df = pd.DataFrame([
        {
            "SYMBOL": "TEST_IPO_DETAIL",
            "NAME OF COMPANY": "Test IPO Detail Technologies Ltd",
            "SERIES": "EQ",
            "DATE OF LISTING": (now - timedelta(days=35)).strftime("%d-%b-%Y"),
            "LISTING_DATE": now - timedelta(days=35),
            "FACE VALUE": 10,
        }
    ])
    monkeypatch.setattr("earnings_engine.data.new_listings.fetch_all_nse_equities_cached", lambda: mock_df.copy())

    try:
        detail = get_ipo_stock_detail(ticker, settings=settings)
        assert detail["success"] is True
        assert detail["ticker"] == ticker
        assert detail["company_name"] == "Test IPO Detail Technologies Ltd"
        assert detail["series"] == "EQ"
        assert detail["is_sme"] is False
        assert detail["days_on_market"] >= 35

        # Technical checks
        tech = detail["technical"]
        assert tech["listing_day"] is not None
        assert tech["listing_price"] == 200.0
        assert tech["cmp"] == 248.0
        assert tech["return_since_listing_pct"] == 24.0
        assert tech["sma_20"] is not None and tech["sma_20"] > 0
        assert "stage" in tech
        assert "stage_badge" in tech
        assert tech["return_7d_pct"] is not None
        assert tech["return_30d_pct"] is not None

        # Earnings lifecycle checks
        el = detail["earnings_lifecycle"]
        assert el["past_earnings_count"] == 1
        assert el["result_sequence"]["result_sequence_number"] == 2
        assert "2nd Public Result" in el["result_sequence"]["result_sequence_label"]
        assert el["last_reported"] is not None
        assert el["last_reported"]["earnings_date"] == "2026-06-15"
        assert el["last_reported"]["eps_reported"] == 4.8
        assert el["upcoming_result"] is not None
        assert el["upcoming_result"]["earnings_date"] == "2026-09-25"
        assert "SEBI" in el["guidance_note"]

        # Institutional checks
        inst = detail["institutional"]
        assert inst["mutual_funds_count"] == 1
        mf = inst["mutual_funds"][0]
        assert mf["fund_name"] == "Nippon India Small Cap Fund"
        assert mf["shares_held"] == 350000
        assert mf["market_value_cr"] == 18.5
        assert mf["holding_pct"] == 1.75

        shp = inst["shareholding_pattern"]
        assert shp is not None
        assert shp["promoter_pct"] == 62.5
        assert shp["fii_pct"] == 10.2
        assert shp["dii_pct"] == 12.8

        bds = inst["block_deals"]
        assert len(bds) == 1
        assert bds[0]["client_name"] == "GOLDMAN SACHS INDIA"
        assert bds[0]["deal_type"] == "BUY"
    finally:
        conn.execute("DELETE FROM price_history WHERE ticker = ?", (ticker,))
        conn.execute("DELETE FROM earnings_history WHERE ticker = ?", (ticker,))
        conn.execute("DELETE FROM earnings_calendar WHERE ticker = ?", (ticker,))
        conn.execute("DELETE FROM institutional_holdings WHERE id = 999901")
        conn.execute("DELETE FROM shareholding_patterns WHERE ticker = ?", (ticker,))
        conn.execute("DELETE FROM institutional_block_deals WHERE id = 999901")
        if hasattr(conn, "commit"):
            conn.commit()


def test_get_ipo_stock_detail_empty_state():
    settings = Settings()
    detail = get_ipo_stock_detail("NONEXISTENT_IPO.NS", settings=settings)
    assert detail["success"] is True
    assert detail["ticker"] == "NONEXISTENT_IPO.NS"
    assert detail["technical"]["cmp"] is None
    assert detail["technical"]["stage"] == "New Debut (Awaiting Market History)"
    assert detail["earnings_lifecycle"]["past_earnings_count"] == 0
    assert detail["earnings_lifecycle"]["result_sequence"]["result_sequence_number"] == 1
    assert detail["institutional"]["mutual_funds"] == []
    assert detail["institutional"]["mutual_funds_count"] == 0


def test_get_ipo_stock_detail_stages(monkeypatch):
    settings = Settings()
    conn = get_db_connection(settings)
    ticker = "TEST_STAGE_BREAKOUT.NS"
    now = datetime.now()

    # Create ATH breakout scenario: CMP is at ATH
    for i in range(5):
        d_str = (now - timedelta(days=5 - i)).strftime("%Y-%m-%d")
        conn.execute(
            "INSERT OR REPLACE INTO price_history (ticker, date, open, high, low, close, volume) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (ticker, d_str, 100.0 + i, 105.0 + i, 98.0 + i, 105.0 + i, 2000),
        )
    if hasattr(conn, "commit"):
        conn.commit()

    try:
        detail = get_ipo_stock_detail(ticker, settings=settings)
        assert detail["success"] is True
        assert detail["technical"]["stage"] == "🔥 IPO Base Breakout (At ATH)"
        assert detail["technical"]["stage_badge"] == "emerald"
    finally:
        conn.execute("DELETE FROM price_history WHERE ticker = ?", (ticker,))
        if hasattr(conn, "commit"):
            conn.commit()


