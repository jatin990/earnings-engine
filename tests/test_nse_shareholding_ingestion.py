"""Tests for NSE Shareholding Pattern Ingestion & Institutional Entity Extractor."""
from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock, patch
import pytest

from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection
from earnings_engine.data.migrations import apply_migrations
from earnings_engine.data.nse_shareholding import (
    classify_institutional_entity,
    fetch_nse_shareholding,
    is_shareholding_fresh,
    mark_shareholding_fetched,
    parse_shareholding_response,
    extract_and_persist_stock_shareholding,
    ingest_universe_shareholding_patterns,
)
from earnings_engine.data.institutional_accumulation import (
    get_all_funds_activity,
    get_stock_institutional_activity,
)


@pytest.fixture(autouse=True)
def init_db(tmp_path, monkeypatch):
    """Ensure a clean temporary test database with all migrations applied."""
    monkeypatch.delenv("TURSO_DATABASE_URL", raising=False)
    monkeypatch.delenv("TURSO_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("EARNINGS_ENGINE_DB_PATH", raising=False)
    monkeypatch.setenv("EARNINGS_ENGINE_DB_NAME", f"test_{tmp_path.name}.sqlite3")
    s = Settings()
    s.data_dirs["prices"] = tmp_path
    s.data_dirs["earnings"] = tmp_path
    s.ensure_dirs()
    apply_migrations(s)

    conn = get_db_connection(s)
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO tickers (ticker, name, market_cap) VALUES ('RELIANCE.NS', 'Reliance Industries Ltd', 2000000.0)"
        )
        conn.execute(
            "INSERT OR REPLACE INTO tickers (ticker, name, market_cap) VALUES ('TCS.NS', 'Tata Consultancy Services', 1500000.0)"
        )
        conn.execute(
            "INSERT OR REPLACE INTO tickers (ticker, name, market_cap) VALUES ('INFY.NS', 'Infosys Limited', 700000.0)"
        )
        conn.execute(
            "INSERT OR REPLACE INTO price_history (ticker, date, open, high, low, close, volume) VALUES ('RELIANCE.NS', '2026-08-30', 2900.0, 2950.0, 2880.0, 2920.0, 5000000)"
        )
        conn.execute(
            "INSERT OR REPLACE INTO price_history (ticker, date, open, high, low, close, volume) VALUES ('TCS.NS', '2026-08-30', 4400.0, 4450.0, 4380.0, 4420.0, 2000000)"
        )
    return s


def test_classify_institutional_entity():
    """Verify institutional entity classifier accurately categorizes different market participants."""
    assert classify_institutional_entity("Ashish Kacholia") == "Super Investor"
    assert classify_institutional_entity("Mukul Agrawal") == "Super Investor"
    assert classify_institutional_entity("Vijay Kedia") == "Super Investor"
    assert classify_institutional_entity("Government Pension Fund Global") == "Foreign Sovereign / FII"
    assert classify_institutional_entity("Life Insurance Corporation of India") == "Insurance Company (DII)"
    assert classify_institutional_entity("SBI Bluechip Fund") == "Mutual Fund (DII)"
    assert classify_institutional_entity("Quant Active Fund") == "Mutual Fund (DII)"
    assert classify_institutional_entity("HDFC Mid-Cap Opportunities Fund") == "Mutual Fund (DII)"
    assert classify_institutional_entity("Nippon India Small Cap Fund") == "Mutual Fund (DII)"
    assert classify_institutional_entity("Vanguard Emerging Markets Stock Index Fund") == "Foreign Institutional (FII)"
    assert classify_institutional_entity("GQG Partners Emerging Markets Equity Fund") == "Foreign Institutional (FII)"
    assert classify_institutional_entity("BlackRock Global Funds") == "Foreign Institutional (FII)"


def test_parse_shareholding_response_nested(init_db):
    """Verify parsing nested NSE shareholding response extracting individual real entities."""
    settings = init_db
    conn = get_db_connection(settings)

    mock_nse_payload = {
        "data": [
            {
                "shareholderCategory": "Promoter & Promoter Group",
                "percentage": 50.31,
                "shareholders": [
                    {"name": "Mukesh D Ambani", "percentage": 2.50, "shares": 20000000},
                ],
            },
            {
                "shareholderCategory": "Mutual Funds",
                "percentage": 8.45,
                "shareholders": [
                    {"name": "SBI Bluechip Fund", "percentage": 1.25, "shares": 10000000},
                    {"name": "ICICI Prudential Value Discovery Fund", "percentage": 0.85, "shares": 6800000},
                    {"name": "Mirae Asset Large Cap Fund", "percentage": 0.75, "shares": 6000000},
                ],
            },
            {
                "shareholderCategory": "Foreign Portfolio Investors",
                "percentage": 22.10,
                "shareholders": [
                    {"name": "Vanguard Emerging Markets Fund", "percentage": 1.50, "shares": 12000000},
                    {"name": "GQG Partners Emerging Markets", "percentage": 1.10, "shares": 8800000},
                ],
            },
        ]
    }

    holdings, pattern = parse_shareholding_response(mock_nse_payload, "RELIANCE.NS", conn=conn)

    assert len(holdings) >= 5
    fund_names = [h["fund_name"] for h in holdings]
    assert "SBI Bluechip Fund" in fund_names
    assert "ICICI Prudential Value Discovery Fund" in fund_names
    assert "Mirae Asset Large Cap Fund" in fund_names
    assert "Vanguard Emerging Markets Fund" in fund_names
    assert "GQG Partners Emerging Markets" in fund_names

    # Check pattern summary
    assert pattern["promoter_pct"] == 50.31
    assert pattern["fii_pct"] == 22.10
    assert pattern["dii_mf_pct"] == 8.45


def test_is_shareholding_fresh_and_mark(init_db):
    """Verify freshness tracking avoids re-requesting fresh data."""
    settings = init_db
    conn = get_db_connection(settings)

    assert not is_shareholding_fresh("RELIANCE.NS", settings=settings, conn=conn)

    mark_shareholding_fetched("RELIANCE.NS", entities_count=5, source="nse_api", settings=settings, conn=conn)
    assert is_shareholding_fresh("RELIANCE.NS", max_age_days=1, settings=settings, conn=conn)



def test_ingest_universe_shareholding_patterns_mocked_nse(init_db):
    """Verify universe ingestion runs live NSE parse, persists real entities, and produces diverse funds."""
    settings = init_db
    conn = get_db_connection(settings)

    mock_reliance_payload = {
        "data": [
            {
                "shareholderCategory": "Mutual Funds",
                "percentage": 7.50,
                "shareholders": [
                    {"name": "SBI Bluechip Fund", "percentage": 1.40, "shares": 11000000},
                    {"name": "Kotak Flexicap Fund", "percentage": 0.95, "shares": 7500000},
                    {"name": "DSP Midcap Fund", "percentage": 0.65, "shares": 5200000},
                ],
            },
            {
                "shareholderCategory": "Super Investors",
                "percentage": 1.50,
                "shareholders": [
                    {"name": "Ashish Kacholia", "percentage": 0.50, "shares": 4000000},
                    {"name": "Radhakishan Damani", "percentage": 1.00, "shares": 8000000},
                ],
            },
        ]
    }

    mock_tcs_payload = {
        "data": [
            {
                "shareholderCategory": "Mutual Funds",
                "percentage": 9.20,
                "shareholders": [
                    {"name": "Axis Bluechip Fund", "percentage": 1.10, "shares": 4500000},
                    {"name": "UTI Flexi Cap Fund", "percentage": 0.80, "shares": 3200000},
                    {"name": "Tata Large & Mid Cap Fund", "percentage": 0.60, "shares": 2400000},
                ],
            },
            {
                "shareholderCategory": "Foreign Institutions",
                "percentage": 18.50,
                "shareholders": [
                    {"name": "BlackRock Emerging Markets Fund", "percentage": 1.30, "shares": 5200000},
                    {"name": "Capital Group Global Discovery", "percentage": 0.90, "shares": 3600000},
                ],
            },
        ]
    }

    def mock_fetch(sym, session=None, max_retries=3):
        if "RELIANCE" in sym:
            return mock_reliance_payload
        if "TCS" in sym:
            return mock_tcs_payload
        return None

    with patch("earnings_engine.data.nse_shareholding.fetch_nse_shareholding", side_effect=mock_fetch):
        res = ingest_universe_shareholding_patterns(
            tickers=["RELIANCE.NS", "TCS.NS"],
            rate_limit_delay=0.0,
            force=True,
            settings=settings,
        )

    assert res["success"] is True
    assert res["nse_fetched_count"] == 2
    assert res["total_entities_extracted"] >= 10

    # Query distinct fund names in database
    distinct_funds = conn.execute("SELECT DISTINCT fund_name FROM institutional_holdings").fetchall()
    fund_names = [r[0] for r in distinct_funds]

    assert len(fund_names) >= 10
    assert "Kotak Flexicap Fund" in fund_names
    assert "DSP Midcap Fund" in fund_names
    assert "Axis Bluechip Fund" in fund_names
    assert "UTI Flexi Cap Fund" in fund_names
    assert "Tata Large & Mid Cap Fund" in fund_names
    assert "BlackRock Emerging Markets Fund" in fund_names
    assert "Capital Group Global Discovery" in fund_names
    assert "Radhakishan Damani" in fund_names

    # Test get_all_funds_activity returns the real funds
    funds_activity = get_all_funds_activity(limit=50, settings=settings)
    assert len(funds_activity) >= 10
    activity_names = [f["fund_name"] for f in funds_activity]
    assert "Kotak Flexicap Fund" in activity_names
    assert "Axis Bluechip Fund" in activity_names


def test_ingest_universe_shareholding_patterns_fallback(init_db):
    """Verify graceful fallback when NSE endpoint is unreachable."""
    settings = init_db
    conn = get_db_connection(settings)

    with patch("earnings_engine.data.nse_shareholding.fetch_nse_shareholding", return_value=None):
        res = ingest_universe_shareholding_patterns(
            tickers=["INFY.NS"],
            rate_limit_delay=0.0,
            force=True,
            settings=settings,
        )

    assert res["success"] is True
    assert res["fallback_count"] == 1

    # Verify fallback generated institutional holdings for INFY.NS
    count = conn.execute("SELECT COUNT(*) FROM institutional_holdings WHERE ticker = 'INFY.NS'").fetchone()[0]
    assert count > 0

