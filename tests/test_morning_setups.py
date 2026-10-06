"""
tests/test_morning_setups.py
Unit tests for Morning Setups: Block & Bulk Deals Intelligence and Upcoming Board Meetings Radar.
Asserts database persistence, catalyst impact tiering, query filtering, and API contracts.
"""
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection
from earnings_engine.data.migrations import apply_migrations
from earnings_engine.data.morning_setups import (
    classify_board_meeting_impact,
    clean_nse_deal_symbol,
    store_morning_block_deals,
    store_upcoming_board_meetings,
    get_morning_block_deals,
    get_morning_deals_summary,
    get_upcoming_board_meetings,
    get_board_meetings_summary,
    group_deals_by_symbol,
    enrich_tickers_with_technicals,
)
from earnings_engine.api.server import create_app


@pytest.fixture
def test_settings(tmp_path, monkeypatch):
    """Fixture providing isolated SQLite database settings."""
    monkeypatch.delenv("TURSO_DATABASE_URL", raising=False)
    monkeypatch.delenv("TURSO_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("EARNINGS_ENGINE_DB_PATH", raising=False)
    monkeypatch.setenv("EARNINGS_ENGINE_DB_NAME", f"test_{tmp_path.name}.sqlite3")
    settings = Settings()
    settings.data_dirs["prices"] = tmp_path
    settings.data_dirs["earnings"] = tmp_path
    settings.ensure_dirs()
    apply_migrations(settings, force=True)
    return settings


def test_classify_board_meeting_impact():
    """Verify keyword classification into HIGH, MEDIUM, and ROUTINE impact tiers."""
    # High impact
    assert classify_board_meeting_impact("Consider and approve Audited Financial Results") == "HIGH"
    assert classify_board_meeting_impact("Recommendation of Bonus Shares Issue") == "HIGH"
    assert classify_board_meeting_impact("Proposal for Stock Split / Sub-division of shares") == "HIGH"
    assert classify_board_meeting_impact("Proposal for Buyback of Equity Shares") == "HIGH"

    # Medium impact
    assert classify_board_meeting_impact("Consider Interim Dividend for FY26") == "MEDIUM"
    assert classify_board_meeting_impact("Fund raising via Rights Issue / QIP") == "MEDIUM"

    # Routine
    assert classify_board_meeting_impact("General corporate administration meeting") == "ROUTINE"
    assert classify_board_meeting_impact("") == "ROUTINE"


def test_clean_nse_deal_symbol():
    """Verify symbol cleaning and NSE ticker formatting."""
    assert clean_nse_deal_symbol("TRENT") == "TRENT.NS"
    assert clean_nse_deal_symbol("NYKAA.NS") == "NYKAA.NS"
    assert clean_nse_deal_symbol("  infy  ") == "INFY.NS"


def test_store_and_query_morning_deals(test_settings):
    """Test storage, deduplication, and multi-attribute querying of block and bulk deals."""
    deals = [
        {
            "deal_date": "2026-10-06",
            "ticker": "TRENT.NS",
            "client_name": "GOLDMAN SACHS INDIA FUND",
            "deal_type": "BLOCK",
            "transaction_type": "BUY",
            "quantity": 500000,
            "trade_price": 7500.0,
            "value_cr": 375.0,
        },
        {
            "deal_date": "2026-10-06",
            "ticker": "NYKAA.NS",
            "client_name": "FIDELITY INVESTMENTS",
            "deal_type": "BULK",
            "transaction_type": "SELL",
            "quantity": 1200000,
            "trade_price": 195.0,
            "value_cr": 23.4,
        },
        {
            "deal_date": "2026-10-05",
            "ticker": "INFY.NS",
            "client_name": "MORGAN STANLEY ASIA",
            "deal_type": "BLOCK",
            "transaction_type": "BUY",
            "quantity": 100000,
            "trade_price": 1850.0,
            "value_cr": 18.5,
        },
    ]

    inserted = store_morning_block_deals(test_settings, deals)
    assert inserted == 3

    # Duplicate insertion should be safely ignored (INSERT OR IGNORE)
    reinserted = store_morning_block_deals(test_settings, deals)
    assert reinserted == 0

    # Query with filters
    all_deals = get_morning_block_deals(test_settings)
    assert len(all_deals) == 3

    # Filter by ticker
    trent_deals = get_morning_block_deals(test_settings, ticker="TRENT")
    assert len(trent_deals) == 1
    assert trent_deals[0]["ticker"] == "TRENT.NS"
    assert trent_deals[0]["deal_type"] == "BLOCK"
    assert trent_deals[0]["transaction_type"] == "BUY"

    # Filter by transaction type
    sell_deals = get_morning_block_deals(test_settings, transaction_type="SELL")
    assert len(sell_deals) == 1
    assert sell_deals[0]["ticker"] == "NYKAA.NS"

    # Filter by min_value_cr
    mega_deals = get_morning_block_deals(test_settings, min_value_cr=50.0)
    assert len(mega_deals) == 1
    assert mega_deals[0]["ticker"] == "TRENT.NS"

    # Check deals summary
    summary = get_morning_deals_summary(test_settings)
    assert summary["total_deals"] == 3
    assert summary["block_deals_count"] == 2
    assert summary["bulk_deals_count"] == 1
    assert summary["gross_buy_cr"] == pytest.approx(393.5, 0.1)
    assert summary["gross_sell_cr"] == pytest.approx(23.4, 0.1)


def test_store_and_query_board_meetings(test_settings):
    """Test storage, deduplication, and catalyst impact querying of board meetings."""
    meetings = [
        {
            "ticker": "TRENT.NS",
            "company_name": "Trent Limited",
            "meeting_date": "2026-10-14",
            "purpose": "Financial Results for Q2 FY27 and Interim Dividend",
            "impact_tier": "HIGH",
        },
        {
            "ticker": "NYKAA.NS",
            "company_name": "FSN E-Commerce Ventures Limited",
            "meeting_date": "2026-10-20",
            "purpose": "Consider proposal for Bonus Issue of Shares",
            "impact_tier": "HIGH",
        },
        {
            "ticker": "TCS.NS",
            "company_name": "Tata Consultancy Services Limited",
            "meeting_date": "2026-10-08",
            "purpose": "Quarterly Financial Results",
            "impact_tier": "HIGH",
        },
        {
            "ticker": "RELIANCE.NS",
            "company_name": "Reliance Industries Limited",
            "meeting_date": "2026-11-05",
            "purpose": "Routine General Administration",
            "impact_tier": "ROUTINE",
        },
    ]

    inserted = store_upcoming_board_meetings(test_settings, meetings)
    assert inserted == 4

    # Query all meetings
    res = get_upcoming_board_meetings(test_settings)
    assert len(res) == 4

    # Query high impact meetings
    high_res = get_upcoming_board_meetings(test_settings, impact_tier="HIGH")
    assert len(high_res) == 3

    # Query specific ticker
    nykaa_res = get_upcoming_board_meetings(test_settings, ticker="NYKAA")
    assert len(nykaa_res) == 1
    assert nykaa_res[0]["company_name"] == "FSN E-Commerce Ventures Limited"

    # Query summary metrics
    summary = get_board_meetings_summary(test_settings)
    assert summary["total_upcoming"] == 4
    assert summary["high_impact_count"] == 3
    assert summary["routine_count"] == 1


def test_morning_setups_api_endpoints(test_settings):
    """Verify FastAPI REST API contracts for deals and board meetings."""
    with patch("earnings_engine.api.routers.morning_setups._settings", test_settings):
        app = create_app()
        client = TestClient(app)

        # Seed data
        store_morning_block_deals(test_settings, [
            {
                "deal_date": "2026-10-06",
                "ticker": "TRENT.NS",
                "client_name": "VANGUARD INTL",
                "deal_type": "BLOCK",
                "transaction_type": "BUY",
                "quantity": 300000,
                "trade_price": 7500.0,
                "value_cr": 225.0,
            }
        ])
        store_upcoming_board_meetings(test_settings, [
            {
                "ticker": "TRENT.NS",
                "company_name": "Trent Limited",
                "meeting_date": "2026-10-15",
                "purpose": "Financial Results",
                "impact_tier": "HIGH",
            }
        ])

        # Test Deals Summary endpoint (static route)
        resp = client.get("/api/v1/morning-setups/deals/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_deals"] == 1
        assert data["gross_buy_cr"] == 225.0

        # Test Deals List endpoint
        resp = client.get("/api/v1/morning-setups/deals?ticker=TRENT")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["count"] == 1
        assert data["deals"][0]["ticker"] == "TRENT.NS"

        # Test Board Meetings Summary endpoint (static route)
        resp = client.get("/api/v1/morning-setups/board-meetings/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_upcoming"] == 1
        assert data["high_impact_count"] == 1

        # Test Board Meetings List endpoint
        resp = client.get("/api/v1/morning-setups/board-meetings?impact_tier=HIGH")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["count"] == 1
        assert data["meetings"][0]["ticker"] == "TRENT.NS"


def test_group_deals_by_symbol():
    """Verify deal aggregation by symbol, VWAP, net flow, and print breakdown."""
    sample_deals = [
        {
            "deal_date": "2026-10-06",
            "ticker": "TRENT.NS",
            "security_name": "Trent Limited",
            "client_name": "FUND A",
            "deal_type": "BLOCK",
            "transaction_type": "BUY",
            "quantity": 1000,
            "trade_price": 5000.0,
            "value_cr": 0.5,
        },
        {
            "deal_date": "2026-10-06",
            "ticker": "TRENT.NS",
            "security_name": "Trent Limited",
            "client_name": "FUND B",
            "deal_type": "BULK",
            "transaction_type": "SELL",
            "quantity": 500,
            "trade_price": 5100.0,
            "value_cr": 0.255,
        },
        {
            "deal_date": "2026-10-06",
            "ticker": "INFY.NS",
            "security_name": "Infosys Limited",
            "client_name": "FUND C",
            "deal_type": "BLOCK",
            "transaction_type": "BUY",
            "quantity": 2000,
            "trade_price": 1800.0,
            "value_cr": 0.36,
        },
    ]

    grouped = group_deals_by_symbol(sample_deals)
    assert len(grouped) == 2

    trent = next(g for g in grouped if g["ticker"] == "TRENT.NS")
    assert trent["total_deals"] == 2
    assert trent["block_count"] == 1
    assert trent["bulk_count"] == 1
    assert trent["total_quantity"] == 1500
    assert trent["gross_buy_cr"] == 0.5
    assert trent["gross_sell_cr"] == 0.26
    assert trent["net_value_cr"] == 0.24
    assert trent["total_value_cr"] == 0.76
    # Total turnover = 1000 * 5000 + 500 * 5100 = 5,000,000 + 2,550,000 = 7,550,000. Total qty = 1500. VWAP = 7550000 / 1500 = 5033.33
    assert trent["vwap"] == pytest.approx(5033.33, 0.01)
    assert len(trent["prints"]) == 2

    infy = next(g for g in grouped if g["ticker"] == "INFY.NS")
    assert infy["total_deals"] == 1
    assert infy["vwap"] == 1800.0
    assert infy["net_value_cr"] == 0.36


def test_deals_api_with_group_by_symbol(test_settings):
    """Verify deals API returns grouped response when group_by_symbol=true."""
    with patch("earnings_engine.api.routers.morning_setups._settings", test_settings):
        app = create_app()
        client = TestClient(app)

        store_morning_block_deals(test_settings, [
            {
                "deal_date": "2026-10-06",
                "ticker": "TRENT.NS",
                "client_name": "BUYER 1",
                "deal_type": "BLOCK",
                "transaction_type": "BUY",
                "quantity": 2000,
                "trade_price": 7500.0,
                "value_cr": 1.5,
            },
            {
                "deal_date": "2026-10-06",
                "ticker": "TRENT.NS",
                "client_name": "SELLER 1",
                "deal_type": "BLOCK",
                "transaction_type": "SELL",
                "quantity": 1000,
                "trade_price": 7500.0,
                "value_cr": 0.75,
            },
        ])

        resp = client.get("/api/v1/morning-setups/deals?group_by_symbol=true")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["grouped"] is True
        assert data["count"] == 1
        assert data["deals"][0]["ticker"] == "TRENT.NS"
        assert data["deals"][0]["total_deals"] == 2
        assert data["deals"][0]["net_value_cr"] == 0.75
        assert "technicals" in data


def test_enrich_tickers_with_technicals():
    """Verify technical indicator computation (1D/7D/30D returns, 20/50 DMA) and anti-fabrication."""
    import pandas as pd
    import numpy as np

    # Generate 60 days of synthetic prices for testing
    closes = [100.0 + i * 2.0 for i in range(60)]
    df = pd.DataFrame({"close": closes}, index=pd.date_range("2026-08-01", periods=60, freq="D"))

    with patch("earnings_engine.data.morning_setups.load_prices_batch") as mock_load:
        mock_load.return_value = {"TRENT.NS": df, "MISSING.NS": pd.DataFrame()}

        tech = enrich_tickers_with_technicals(["TRENT.NS", "MISSING.NS"])

        assert "TRENT.NS" in tech
        trent_tech = tech["TRENT.NS"]
        assert trent_tech["latest_close"] == closes[-1]
        assert trent_tech["return_1d"] is not None
        assert trent_tech["return_7d"] is not None
        assert trent_tech["return_30d"] is not None
        assert trent_tech["dma_20"] is not None
        assert trent_tech["dma_50"] is not None
        assert trent_tech["price_vs_dma20_pct"] is not None
        assert trent_tech["price_vs_dma50_pct"] is not None

        # Anti-fabrication check: missing symbol must return None, not fake numbers
        assert "MISSING.NS" in tech
        missing_tech = tech["MISSING.NS"]
        assert missing_tech["latest_close"] is None
        assert missing_tech["return_1d"] is None
        assert missing_tech["return_7d"] is None
        assert missing_tech["return_30d"] is None
        assert missing_tech["dma_20"] is None
        assert missing_tech["dma_50"] is None


