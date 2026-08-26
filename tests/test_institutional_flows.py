"""Tests for Institutional Accumulation, Mutual Fund Holdings, and Block Deals."""
import pytest
from fastapi.testclient import TestClient
from earnings_engine.api.server import app
from earnings_engine.data.institutional_accumulation import (
    get_stock_institutional_activity,
    get_top_accumulated_stocks,
    get_top_distributed_stocks,
    get_all_funds_activity,
    get_fund_portfolio_activity,
)


@pytest.fixture
def client():
    return TestClient(app)


def test_allcargo_institutional_breakdown():
    # Test ALLCARGO.NS specifically as requested
    activity = get_stock_institutional_activity("ALLCARGO.NS")
    assert activity is not None
    assert activity["ticker"] == "ALLCARGO.NS"
    assert activity["accumulation_score"] >= 70
    assert "Institutional Accumulation" in activity["verdict"]

    # Verify fund holdings present (Nippon India, Quant, HDFC, Ashish Kacholia, Vanguard)
    holdings = activity["holdings"]
    assert len(holdings) >= 4
    fund_names = [h["fund_name"] for h in holdings]
    assert any("Nippon" in fn for fn in fund_names)
    assert any("Quant" in fn for fn in fund_names)
    assert any("Ashish Kacholia" in fn for fn in fund_names)

    # Verify actions (e.g. Nippon India accumulated / new buy)
    actions = [h["action"] for h in holdings]
    assert "ACCUMULATED" in actions or "NEW BUY" in actions

    # Verify shareholding pattern trend
    patterns = activity["shareholding_patterns"]
    assert len(patterns) >= 2
    assert "fii_pct" in patterns[0]
    assert "dii_mf_pct" in patterns[0]

    # Verify block deals
    block_deals = activity["block_deals"]
    assert len(block_deals) >= 1
    assert block_deals[0]["deal_type"] in ["BUY", "SELL"]


def test_top_accumulated_and_distributed_stocks():
    acc = get_top_accumulated_stocks(limit=100)
    assert len(acc) >= 2
    tickers = [x["ticker"] for x in acc]
    assert "ALLCARGO.NS" in tickers
    assert "DIXON.NS" in tickers

    dist = get_top_distributed_stocks(limit=100)
    assert isinstance(dist, list)


def test_funds_directory_and_portfolio():
    funds = get_all_funds_activity(limit=20)
    assert len(funds) >= 4
    fund_names = [f["fund_name"] for f in funds]
    assert any("Nippon" in fn for fn in fund_names)

    # Test reverse fund portfolio lookup
    nippon_holdings = get_fund_portfolio_activity("Nippon India Small Cap Fund")
    assert nippon_holdings is not None
    assert len(nippon_holdings) >= 1
    assert any(h["ticker"] == "ALLCARGO.NS" for h in nippon_holdings)


def test_institutional_multi_quarter_and_dates():
    # Test DIXON.NS and unseeded ticker dynamic generation
    for ticker in ["DIXON.NS", "KAYNES.NS", "UNSEENTICKER.NS"]:
        activity = get_stock_institutional_activity(ticker)
        assert activity["success"] is True
        assert len(activity["holdings"]) >= 1
        assert len(activity["shareholding_patterns"]) >= 2
        
        # Verify reported_date is present and formatted
        for h in activity["holdings"]:
            assert h.get("reported_date") is not None
            assert len(h["reported_date"]) == 10  # YYYY-MM-DD
            
        # Verify shareholding patterns have quarter labels
        quarters = [p["quarter"] for p in activity["shareholding_patterns"]]
        assert any("FY27" in q or "FY26" in q for q in quarters)


def test_institutional_api_endpoints(client):
    # Summary
    res_sum = client.get("/api/v1/institutional/summary")
    assert res_sum.status_code == 200

    # Accumulating
    res_acc = client.get("/api/v1/institutional/accumulating")
    assert res_acc.status_code == 200
    assert len(res_acc.json()["items"]) >= 1

    # Single stock drilldown (ALLCARGO.NS)
    res_stock = client.get("/api/v1/institutional/stock/ALLCARGO.NS")
    assert res_stock.status_code == 200
    stock_data = res_stock.json()
    assert stock_data["ticker"] == "ALLCARGO.NS"
    assert len(stock_data["holdings"]) >= 1
    assert "reported_date" in stock_data["holdings"][0]

    # Funds list
    res_funds = client.get("/api/v1/institutional/funds")
    assert res_funds.status_code == 200
    assert len(res_funds.json()["funds"]) >= 1

    # Single fund drilldown
    res_fund = client.get("/api/v1/institutional/fund/Quant%20Small%20Cap%20Fund")
    assert res_fund.status_code == 200
    assert res_fund.json()["success"] is True
