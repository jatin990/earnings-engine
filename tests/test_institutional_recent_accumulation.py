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
        assert "Smart Money" in stl["badge"] or "FII" in stl["badge"]

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


def test_signal_tracking_ledger_persistence_and_returns():
    """Verify signal date, entry price, returns, and radar persistence."""
    import sqlite3
    from earnings_engine.data.institutional_accumulation import get_institutional_db_path

    res = get_stocks_under_institutional_accumulation(
        window="90d",
        entity_focus="smart_money",
        min_cr=1.0,
        limit=20,
    )
    assert res["success"] is True
    assert len(res["stocks"]) > 0

    for stock in res["stocks"]:
        assert "signal_date" in stock
        assert isinstance(stock["signal_date"], str)
        assert len(stock["signal_date"]) == 10  # YYYY-MM-DD
        assert "signal_price" in stock
        assert stock["signal_price"] is not None
        assert stock["signal_price"] > 0
        assert "return_since_signal_pct" in stock
        assert "days_on_radar" in stock
        assert stock["days_on_radar"] >= 0
        assert "is_new_entrant" in stock
        assert stock["is_new_entrant"] == (stock["days_on_radar"] <= 14)
        assert "peak_price" in stock
        assert "max_gain_pct" in stock

        # Verify mathematical return calculation: ((current_price - signal_price) / signal_price) * 100
        if stock.get("current_price") and stock.get("signal_price"):
            expected_ret = round(((stock["current_price"] - stock["signal_price"]) / stock["signal_price"]) * 100, 2)
            assert abs(stock["return_since_signal_pct"] - expected_ret) <= 0.05

    # Check persistence directly in sqlite table institutional_radar_signals
    db_path = get_institutional_db_path()
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM institutional_radar_signals")
    row_count = cur.fetchone()[0]
    assert row_count > 0, "institutional_radar_signals table should contain persisted radar records"

    first_ticker = res["stocks"][0]["ticker"]
    cur.execute(
        "SELECT signal_date, signal_price, current_price, current_return_pct FROM institutional_radar_signals WHERE ticker = ?",
        (first_ticker,),
    )
    sig_row = cur.fetchone()
    assert sig_row is not None
    assert sig_row[0] == res["stocks"][0]["signal_date"]
    assert abs(sig_row[1] - res["stocks"][0]["signal_price"]) < 0.01
    conn.close()


def test_emerging_stocks_and_eps_fundamentals():
    """Verify Small/Micro Cap emerging classification and EPS YoY fundamentals."""
    # Test emerging only filter
    res_emerging = get_stocks_under_institutional_accumulation(
        window="90d",
        entity_focus="all",
        min_cr=1.0,
        emerging_only=True,
        limit=20,
    )
    assert res_emerging["success"] is True
    for stock in res_emerging["stocks"]:
        assert stock["is_emerging"] is True
        assert stock["cap_category"] in ("Small Cap", "Micro Cap") or (stock["market_cap_cr"] or 0) < 15000

    # Test high EPS growth filter
    res_eps = get_stocks_under_institutional_accumulation(
        window="90d",
        entity_focus="all",
        min_cr=1.0,
        min_eps_growth=20.0,
        limit=20,
    )
    assert res_eps["success"] is True
    for stock in res_eps["stocks"]:
        assert stock["eps_growth_yoy"] is not None
        assert stock["eps_growth_yoy"] >= 20.0
        assert stock["has_good_eps"] is True

    # Test new entrants only filter
    res_new = get_stocks_under_institutional_accumulation(
        window="90d",
        entity_focus="all",
        min_cr=1.0,
        new_entrants_only=True,
        limit=20,
    )
    assert res_new["success"] is True
    for stock in res_new["stocks"]:
        assert stock["is_new_entrant"] is True
        assert stock["days_on_radar"] <= 14


def test_new_sorting_modes_extended():
    """Test extended sorting options: signal_date, return_since_signal, and eps_growth."""
    # Sort by signal_date (newest first)
    res_date = get_stocks_under_institutional_accumulation(
        window="90d",
        sort_by="signal_date",
        limit=20,
    )
    assert res_date["success"] is True
    dates = [s["signal_date"] for s in res_date["stocks"]]
    assert dates == sorted(dates, reverse=True)

    # Sort by return_since_signal (highest return first)
    res_ret = get_stocks_under_institutional_accumulation(
        window="90d",
        sort_by="return_since_signal",
        limit=20,
    )
    assert res_ret["success"] is True
    rets = [s["return_since_signal_pct"] for s in res_ret["stocks"]]
    assert rets == sorted(rets, reverse=True)

    # Sort by eps_growth (highest YoY growth first)
    res_eps = get_stocks_under_institutional_accumulation(
        window="90d",
        sort_by="eps_growth",
        limit=20,
    )
    assert res_eps["success"] is True
    eps_vals = [s["eps_growth_yoy"] if s["eps_growth_yoy"] is not None else -999999.0 for s in res_eps["stocks"]]
    assert eps_vals == sorted(eps_vals, reverse=True)


def test_fastapi_recent_accumulation_new_filters():
    """Test the FastAPI REST endpoint with emerging_only, min_eps_growth, new_entrants_only, and new sorts."""
    client = TestClient(app)

    # Emerging only
    r1 = client.get("/api/v1/institutional/recent-accumulation?window=90d&emerging_only=true&limit=10")
    assert r1.status_code == 200
    d1 = r1.json()
    assert d1["success"] is True
    for s in d1["stocks"]:
        assert s["is_emerging"] is True

    # Min EPS growth
    r2 = client.get("/api/v1/institutional/recent-accumulation?window=90d&min_eps_growth=20&limit=10")
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2["success"] is True
    for s in d2["stocks"]:
        assert s["eps_growth_yoy"] is not None
        assert s["eps_growth_yoy"] >= 20.0

    # New entrants only
    r3 = client.get("/api/v1/institutional/recent-accumulation?window=90d&new_entrants_only=true&limit=10")
    assert r3.status_code == 200
    d3 = r3.json()
    assert d3["success"] is True
    for s in d3["stocks"]:
        assert s["is_new_entrant"] is True

    # Sort by return since signal
    r4 = client.get("/api/v1/institutional/recent-accumulation?window=90d&sort_by=return_since_signal&limit=10")
    assert r4.status_code == 200
    d4 = r4.json()
    assert d4["success"] is True


def test_turso_sync_table_registration():
    """Verify institutional_radar_signals is strictly registered for Turso remote sync."""
    from earnings_engine.data.turso_sync import (
        SYNC_TABLES,
        WATERMARK_CANDIDATE_COLUMNS,
        DATE_ONLY_COLUMNS,
    )

    assert "institutional_radar_signals" in SYNC_TABLES
    assert "created_at" in WATERMARK_CANDIDATE_COLUMNS
    assert "updated_at" in WATERMARK_CANDIDATE_COLUMNS
    assert "last_seen_date" in WATERMARK_CANDIDATE_COLUMNS
    assert "signal_date" in DATE_ONLY_COLUMNS
    assert "last_seen_date" in DATE_ONLY_COLUMNS

