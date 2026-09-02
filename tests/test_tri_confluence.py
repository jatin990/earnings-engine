"""
Unit and integration tests for the Tri-Factor Alpha Synergy & Correlation engine.
Tests Pearson correlation math, quarterly alignment, synergy scoring, and FastAPI endpoints.
"""
from __future__ import annotations

import sqlite3
import pytest
from fastapi.testclient import TestClient

from earnings_engine.config import Settings
from earnings_engine.data.tri_confluence import (
    calculate_pearson_correlation,
    compute_ticker_tri_confluence,
    get_tri_confluence_scanner,
    get_tri_confluence_summary,
    clear_tri_confluence_cache,
)
from earnings_engine.api.server import app


# ---------------------------------------------------------------------------
# 1. Pearson Correlation Math & Edge Cases
# ---------------------------------------------------------------------------

def test_pearson_correlation_perfect_positive():
    x = [1.0, 2.0, 3.0, 4.0, 5.0]
    y = [2.0, 4.0, 6.0, 8.0, 10.0]
    r = calculate_pearson_correlation(x, y)
    assert r is not None
    assert pytest.approx(r, 0.01) == 1.0


def test_pearson_correlation_perfect_negative():
    x = [1.0, 2.0, 3.0, 4.0, 5.0]
    y = [10.0, 8.0, 6.0, 4.0, 2.0]
    r = calculate_pearson_correlation(x, y)
    assert r is not None
    assert pytest.approx(r, 0.01) == -1.0


def test_pearson_correlation_edge_cases():
    # Empty or single value
    assert calculate_pearson_correlation([], []) is None
    assert calculate_pearson_correlation([1.0], [2.0]) is None

    # Mismatched lengths
    assert calculate_pearson_correlation([1.0, 2.0], [1.0]) is None

    # Zero variance (flat series)
    assert calculate_pearson_correlation([2.0, 2.0, 2.0], [1.0, 2.0, 3.0]) == 0.0
    assert calculate_pearson_correlation([1.0, 2.0, 3.0], [5.0, 5.0, 5.0]) == 0.0


# ---------------------------------------------------------------------------
# 2. Database Quarterly Confluence Computation
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_db(tmp_path):
    """Create a temporary SQLite database with known quarterly data."""
    db_path = tmp_path / "test_prices.sqlite3"
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    # Create tables matching production migrations
    cur.execute("""
        CREATE TABLE tickers (
            ticker TEXT PRIMARY KEY,
            name TEXT,
            sector TEXT,
            industry TEXT,
            market_cap REAL,
            current_price REAL
        )
    """)

    cur.execute("""
        CREATE TABLE shareholding_patterns (
            ticker TEXT,
            quarter TEXT,
            promoter_pct REAL,
            fii_pct REAL,
            dii_mf_pct REAL,
            public_retail_pct REAL,
            other_pct REAL,
            updated_at TEXT,
            PRIMARY KEY (ticker, quarter)
        )
    """)

    cur.execute("""
        CREATE TABLE earnings_history (
            ticker TEXT,
            earnings_date TEXT,
            eps_estimate REAL,
            eps_reported REAL,
            surprise_pct REAL,
            source TEXT DEFAULT 'yfinance',
            PRIMARY KEY (ticker, earnings_date)
        )
    """)

    cur.execute("""
        CREATE TABLE price_history (
            ticker TEXT,
            date TEXT,
            close REAL,
            PRIMARY KEY (ticker, date)
        )
    """)

    cur.execute("""
        CREATE TABLE institutional_holdings (
            fund_name TEXT,
            fund_type TEXT,
            ticker TEXT,
            quarter TEXT,
            stake_pct REAL,
            holding_value_cr REAL,
            action TEXT,
            change_pct REAL
        )
    """)

    cur.execute(
        "INSERT INTO tickers VALUES (?, ?, ?, ?, ?, ?)",
        ("TEST1.NS", "Test Company Alpha", "Technology", "Software", 50000000000.0, 160.0)
    )

    # Populate TEST1.NS (Strong Triple Synergy: Inst UP, Beat UP, Return UP)
    # 4 distinct sequential quarters
    quarters_data = [
        ("2024-03-31", 15.0, 10.0, 8.0, 10.0, 25.0, 100.0),   # Inst: 25.0%
        ("2024-06-30", 16.5, 11.0, 10.0, 12.0, 20.0, 115.0),  # Inst: 27.5% (+2.5%), Beat +20%, Price +15%
        ("2024-09-30", 18.0, 12.0, 12.0, 15.0, 25.0, 135.0),  # Inst: 30.0% (+2.5%), Beat +25%, Price +17%
        ("2024-12-31", 20.0, 13.0, 14.0, 18.0, 28.5, 160.0),  # Inst: 33.0% (+3.0%), Beat +28.5%, Price +18%
    ]

    for q_date, fii, dii, est_eps, rep_eps, surp, px in quarters_data:
        cur.execute(
            "INSERT INTO shareholding_patterns VALUES (?, ?, 50.0, ?, ?, 20.0, 0.0, ?)",
            ("TEST1.NS", q_date, fii, dii, q_date)
        )
        cur.execute(
            "INSERT INTO earnings_history VALUES (?, ?, ?, ?, ?, 'test')",
            ("TEST1.NS", q_date, est_eps, rep_eps, surp)
        )
        cur.execute(
            "INSERT INTO price_history VALUES (?, ?, ?)",
            ("TEST1.NS", q_date, px)
        )

    # Insert top institutional holder for TEST1.NS
    cur.execute(
        "INSERT INTO institutional_holdings VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("SBI Bluechip Fund", "Mutual Fund", "TEST1.NS", "2024-12-31", 4.5, 320.0, "BUY", 12.5)
    )

    conn.commit()
    yield conn
    conn.close()


def test_compute_ticker_tri_confluence(mock_db):
    settings = Settings()
    res = compute_ticker_tri_confluence("TEST1.NS", settings=settings, conn=mock_db)

    assert res["ticker"] == "TEST1.NS"
    assert res["total_quarters"] == 4
    assert res["confluent_quarters"] >= 2
    assert res["hit_rate_pct"] >= 50.0
    assert res["corr_inst_return"] is not None
    assert res["corr_inst_return"] > 0.0
    assert res["corr_surprise_return"] is not None
    assert res["synergy_score"] >= 65.0
    assert res["grade"] in ["A+", "A"]
    assert len(res["quarters"]) == 4
    assert len(res["top_holders"]) == 1
    assert res["top_holders"][0]["fund_name"] == "SBI Bluechip Fund"
    assert len(res["insights"]) >= 2


def test_get_tri_confluence_scanner_and_summary(mock_db):
    settings = Settings()
    clear_tri_confluence_cache()

    scanner_results = get_tri_confluence_scanner(
        universe="ALL", min_score=0.0, sort_by="score", limit=10, settings=settings, conn=mock_db
    )
    assert len(scanner_results) >= 1
    assert scanner_results[0]["ticker"] == "TEST1.NS"
    assert scanner_results[0]["synergy_score"] >= 65.0

    summary = get_tri_confluence_summary(settings=settings, conn=mock_db)
    assert summary["total_screened"] >= 1
    assert summary["avg_inst_return_corr"] is not None


# ---------------------------------------------------------------------------
# 3. FastAPI Endpoint Integration Tests
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    return TestClient(app)


def test_api_tri_confluence_endpoints(client):
    # Summary endpoint
    res_summary = client.get("/api/v1/correlation/summary")
    assert res_summary.status_code == 200
    data_summary = res_summary.json()
    assert "total_screened" in data_summary
    assert "avg_inst_return_corr" in data_summary

    # Scanner endpoint
    res_scanner = client.get("/api/v1/correlation/tri-confluence?universe=ALL&limit=10")
    assert res_scanner.status_code == 200
    data_scanner = res_scanner.json()
    assert "items" in data_scanner
    assert "total" in data_scanner
    assert isinstance(data_scanner["items"], list)

    # Specific ticker endpoint
    res_ticker = client.get("/api/v1/correlation/ticker/ALLCARGO.NS")
    assert res_ticker.status_code == 200
    data_ticker = res_ticker.json()
    assert data_ticker["ticker"] == "ALLCARGO.NS"
    assert "synergy_score" in data_ticker
    assert "quarters" in data_ticker

    # Recalculate endpoint
    res_recalc = client.post("/api/v1/correlation/recalculate")
    assert res_recalc.status_code == 200
    data_recalc = res_recalc.json()
    assert data_recalc.get("status") == "recalculated"


# ---------------------------------------------------------------------------
# 4. SQLite Persistent Caching Tests
# ---------------------------------------------------------------------------

def test_tri_confluence_db_persistence_roundtrip(mock_db):
    from earnings_engine.data.tri_confluence import (
        store_tri_confluence_record,
        load_cached_ticker_tri_confluence,
        load_cached_tri_confluence_scanner,
        bulk_store_tri_confluence,
    )

    settings = Settings()

    record = {
        "ticker": "TEST2.NS",
        "clean_ticker": "TEST2",
        "company_name": "Test Company Beta",
        "sector": "Industrials",
        "industry": "Machinery",
        "market_cap": 25000000000.0,
        "market_cap_cr": 2500.0,
        "current_price": 450.0,
        "synergy_score": 88.5,
        "grade": "A+",
        "rating_label": "🔥 Triple Alpha Confluence",
        "rating_badge": "emerald",
        "status_desc": "High alignment across institutional accumulation and earnings outperformance.",
        "hit_rate_pct": 75.0,
        "confluent_quarters": 3,
        "total_quarters": 4,
        "corr_inst_return": 0.82,
        "corr_surprise_return": 0.74,
        "corr_inst_surprise": 0.65,
        "latest_quarter": "Q1 FY27",
        "latest_inst_pct": 32.5,
        "latest_inst_delta": 2.1,
        "latest_surprise_pct": 18.5,
        "latest_return_pct": 14.2,
        "latest_confluence_aligned": True,
        "quarters": [
            {"quarter": "Q4 FY26", "inst_pct": 30.4, "surprise_pct": 12.0, "quarter_return_pct": 8.5, "confluence_hit": True},
            {"quarter": "Q1 FY27", "inst_pct": 32.5, "surprise_pct": 18.5, "quarter_return_pct": 14.2, "confluence_hit": True}
        ],
        "top_holders": [
            {"fund_name": "HDFC Top 100", "fund_type": "Mutual Fund", "stake_pct": 3.8, "holding_value_cr": 95.0, "action": "BUY", "change_pct": 8.0}
        ],
        "insights": ["Institutional vs Price Correlation: r = +0.82"],
        "calculated_at": "2026-09-02T10:00:00",
        "updated_at": "2026-09-02T10:00:00"
    }

    # Test single store and load
    store_tri_confluence_record(record, conn=mock_db, settings=settings)
    loaded = load_cached_ticker_tri_confluence("TEST2.NS", settings=settings, conn=mock_db)

    assert loaded is not None
    assert loaded["ticker"] == "TEST2.NS"
    assert loaded["clean_ticker"] == "TEST2"
    assert loaded["synergy_score"] == 88.5
    assert loaded["grade"] == "A+"
    assert loaded["hit_rate_pct"] == 75.0
    assert len(loaded["quarters"]) == 2
    assert len(loaded["top_holders"]) == 1
    assert loaded["top_holders"][0]["fund_name"] == "HDFC Top 100"

    # Test scanner loading directly from SQLite
    scanner_results = load_cached_tri_confluence_scanner(
        universe="ALL", min_score=80.0, sort_by="score", limit=10, settings=settings, conn=mock_db
    )
    assert len(scanner_results) >= 1
    assert scanner_results[0]["ticker"] == "TEST2.NS"
    assert scanner_results[0]["rank"] == 1

