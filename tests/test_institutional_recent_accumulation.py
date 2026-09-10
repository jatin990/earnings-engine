"""Unit and integration tests for Quantitative Smart Money Accumulation Radar."""

from __future__ import annotations

import os
import pytest
from fastapi.testclient import TestClient

from earnings_engine.api.server import app
from earnings_engine.data.institutional_accumulation import (
    get_stocks_under_institutional_accumulation,
)


@pytest.fixture(autouse=True)
def test_env():
    """Ensure tests run with TESTING=true for bypassing auth middleware in test client."""
    old_val = os.environ.get("TESTING")
    os.environ["TESTING"] = "true"
    yield
    if old_val is None:
        os.environ.pop("TESTING", None)
    else:
        os.environ["TESTING"] = old_val


def test_get_stocks_under_institutional_accumulation_90d_structure():
    """Test 90D default lookback window returns structured accumulation metrics."""
    res = get_stocks_under_institutional_accumulation(
        window="90d",
        entity_focus="smart_money",
        min_cr=5.0,
        sort_by="score",
        limit=20,
    )
    assert res["success"] is True
    assert res["window"] == "90d"
    assert "Last 90 Days" in res["window_label"]
    assert "From " in res["period_description"]
    assert "macro_summary" in res
    assert "stocks" in res

    macro = res["macro_summary"]
    assert "total_stocks" in macro
    assert "total_smart_money_cr" in macro
    assert "total_domestic_absorption_cr" in macro
    assert "avg_dominance_pct" in macro
    assert macro["total_stocks"] >= len(res["stocks"])
    assert len(res["stocks"]) == 20
    assert res["count"] == 20
    assert res["total_screened"] == macro["total_stocks"]

    if res["stocks"]:
        stock = res["stocks"][0]
        # Core identification fields
        assert "ticker" in stock
        assert "company_name" in stock
        assert "sector" in stock
        assert "market_cap_cr" in stock
        assert "cap_category" in stock

        # Price and momentum context
        assert "current_price" in stock
        assert "change_pct" in stock
        assert "return_7d_pct" in stock
        assert "return_30d_pct" in stock

        # Quantitative flow breakdown
        assert "smart_money_inflow_cr" in stock
        assert "domestic_inflow_cr" in stock
        assert "total_inflow_cr" in stock
        assert "dominance_pct" in stock
        assert "conviction_score" in stock
        assert "classification" in stock
        assert "badge" in stock
        assert "whale_buyers" in stock
        assert "top_buyer_names" in stock
        assert "score_breakdown" in stock

        # Score breakdown checks
        sb = stock["score_breakdown"]
        assert "capital_score" in sb
        assert "dominance_score" in sb
        assert "whale_quality_score" in sb
        assert "momentum_score" in sb
        assert "final_score" in sb

        # Verification of mathematical relationship
        # Dominance = (smart_money / total_inflow) * 100
        total_calc = stock["smart_money_inflow_cr"] + stock["domestic_inflow_cr"]
        if total_calc > 0:
            expected_dom = round((stock["smart_money_inflow_cr"] / total_calc) * 100, 1)
            assert abs(stock["dominance_pct"] - expected_dom) <= 0.2


def test_smart_money_vs_domestic_absorption_differentiation():
    """Verify that smart money accumulation is cleanly distinguished from domestic absorption."""
    # Run with entity_focus="all" and low threshold to see both types
    res = get_stocks_under_institutional_accumulation(
        window="90d",
        entity_focus="all",
        min_cr=1.0,
        limit=50,
    )
    assert res["success"] is True
    stocks = res["stocks"]

    # Locate high conviction smart money leader (e.g. STLTECH.NS)
    stl_matches = [s for s in stocks if "STLTECH" in s["ticker"]]
    if stl_matches:
        stl = stl_matches[0]
        assert stl["smart_money_inflow_cr"] > 0
        assert stl["dominance_pct"] >= 60.0
        assert stl["conviction_score"] >= 60.0
        assert "High Smart Money" in stl["badge"] or "FII" in stl["badge"]

    # Check that any stock classified as domestic_absorption has the warning flag and capped score
    for s in stocks:
        if s["classification"] == "domestic_absorption":
            assert s["dominance_pct"] < 30.0
            assert "Domestic Absorption" in s["badge"]
            assert s["conviction_score"] <= 40.0


def test_rolling_windows():
    """Test 30D, 180D, and 365D rolling windows return valid results."""
    for win in ["30d", "180d", "365d"]:
        res = get_stocks_under_institutional_accumulation(window=win, min_cr=0.0, limit=10)
        assert res["success"] is True
        assert res["window"] == win
        assert isinstance(res["stocks"], list)


def test_entity_focus_filtering():
    """Test entity focus filters: smart_money, fii_only, super_investor, block_deals."""
    # FII only
    res_fii = get_stocks_under_institutional_accumulation(
        window="90d",
        entity_focus="fii_only",
        min_cr=1.0,
        limit=20,
    )
    assert res_fii["success"] is True
    for s in res_fii["stocks"]:
        assert s["breakdown"]["fii_cr"] > 0

    # Super Investor only
    res_super = get_stocks_under_institutional_accumulation(
        window="90d",
        entity_focus="super_investor",
        min_cr=1.0,
        limit=20,
    )
    assert res_super["success"] is True
    for s in res_super["stocks"]:
        assert s["breakdown"]["super_investor_cr"] > 0


def test_sorting_modes():
    """Test sorting by score, capital, dominance, and return_30d."""
    # Sort by score
    res_score = get_stocks_under_institutional_accumulation(window="90d", sort_by="score", limit=15)
    scores = [s["conviction_score"] for s in res_score["stocks"]]
    assert scores == sorted(scores, reverse=True)

    # Sort by capital
    res_cap = get_stocks_under_institutional_accumulation(window="90d", sort_by="capital", limit=15)
    caps = [s["smart_money_inflow_cr"] for s in res_cap["stocks"]]
    assert caps == sorted(caps, reverse=True)

    # Sort by dominance
    res_dom = get_stocks_under_institutional_accumulation(window="90d", sort_by="dominance", limit=15)
    doms = [s["dominance_pct"] for s in res_dom["stocks"]]
    assert doms == sorted(doms, reverse=True)


def test_fastapi_recent_accumulation_endpoint():
    """Test the FastAPI REST endpoint /api/v1/institutional/recent-accumulation."""
    client = TestClient(app)
    response = client.get("/api/v1/institutional/recent-accumulation?window=90d&entity_focus=smart_money&min_cr=5.0&limit=10")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["window"] == "90d"
    assert "macro_summary" in data
    assert "stocks" in data
    assert isinstance(data["stocks"], list)
    assert data["count"] == len(data["stocks"])
