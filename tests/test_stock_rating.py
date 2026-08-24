"""Unit tests for Industry-Benchmarked Fundamental & Technical Stock Rating Engine."""

import pytest
from starlette.testclient import TestClient

from earnings_engine.config import Settings
from earnings_engine.data.stock_rating import (
    INDUSTRY_BENCHMARKS,
    match_industry_benchmark,
    evaluate_fundamental_rating,
    evaluate_technical_rating,
    generate_stock_ai_note,
    recalculate_stock_rating,
    get_stock_rating,
)


def test_match_industry_benchmark():
    sector, bm = match_industry_benchmark("Information Technology Services")
    assert sector == "IT Services & Tech"
    assert bm["pe"] == 26.5

    sector, bm = match_industry_benchmark("Private Commercial Bank")
    assert sector == "Banking & Financial Services"
    assert bm["pb"] == 2.2

    sector, bm = match_industry_benchmark("Automobile Manufacturer")
    assert sector == "Automotive & Ancillaries"

    sector, bm = match_industry_benchmark(None)
    assert sector == "General / Multi-Sector"


def test_evaluate_fundamental_rating_good_stock():
    financials = {
        "pe": 16.5,                # Low P/E vs 26.5 benchmark
        "roe": 28.0,               # High ROE vs 22.0 benchmark
        "debt_to_equity": 0.05,    # Debt free
        "operating_margin": 24.0,  # High margin
        "surprise_pct": 8.5,       # Positive beat
    }
    res = evaluate_fundamental_rating("TEST.NS", financials, "Software Infrastructure")
    assert res["grade"] == "GOOD"
    assert res["score"] >= 68.0
    assert res["sector"] == "IT Services & Tech"
    assert "pe_discount_pct" in res["metrics"]


def test_evaluate_fundamental_rating_poor_stock():
    financials = {
        "pe": 95.0,                # Extremely expensive
        "roe": 4.0,                # Weak ROE
        "debt_to_equity": 2.8,     # Heavy debt
        "operating_margin": 3.0,   # Low margin
        "surprise_pct": -12.0,     # Big miss
    }
    res = evaluate_fundamental_rating("WEAK.NS", financials, "Auto Parts")
    assert res["grade"] == "POOR"
    assert res["score"] < 45.0


def test_evaluate_technical_rating():
    # Bullish scenario
    res = evaluate_technical_rating(
        ticker="BULL.NS",
        price=1050.0,
        vwap=1025.0,
        volume_surge=2.4,
        support=1000.0,
        resistance=1200.0,
        news_sentiment="BULLISH",
    )
    assert res["grade"] in ("STRONG BUY", "BUY")
    assert res["score"] >= 58.0


def test_generate_stock_ai_note():
    fund_res = {
        "score": 78.0,
        "grade": "GOOD",
        "sector": "IT Services & Tech",
        "metrics": {
            "pe": 18.2,
            "benchmark_pe": 26.5,
            "pe_discount_pct": 31.3,
            "roe": 24.5,
            "debt_to_equity": 0.05,
        },
    }
    tech_res = {
        "score": 75.0,
        "grade": "BUY",
        "metrics": {
            "vwap_diff_pct": 2.4,
            "volume_surge": 1.8,
        },
    }
    note = generate_stock_ai_note("TCS.NS", fund_res, tech_res)
    assert "IT Services & Tech" in note
    assert "18.2x P/E" in note
    assert "VWAP" in note


def test_recalculate_stock_rating_flow(tmp_path):
    settings = Settings()
    settings.data_dirs["prices"] = tmp_path
    settings.data_dirs["earnings"] = tmp_path
    settings.ensure_dirs()
    res1 = recalculate_stock_rating("TCS.NS", settings, source="test_init")
    assert "fundamental" in res1
    assert "technical" in res1
    assert "diff" in res1
    assert res1["ticker"] == "TCS.NS"

    # Cached retrieval
    cached = get_stock_rating("TCS.NS", settings)
    assert cached is not None
    assert cached["ticker"] == "TCS.NS"


def test_api_stock_rating_endpoints():
    from earnings_engine.api.server import app
    client = TestClient(app)

    # 1. Recalculate
    resp = client.post("/api/v1/stock/INFY.NS/recalculate", json={"source": "pytest_test"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["ticker"] == "INFY.NS"
    assert "fundamental" in data

    # 2. Get rating
    resp = client.get("/api/v1/stock/INFY.NS/rating")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["ticker"] == "INFY.NS"
