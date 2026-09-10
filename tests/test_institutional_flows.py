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

    # Verify shareholding pattern trend with quarterly start and live prices
    patterns = activity["shareholding_patterns"]
    assert len(patterns) >= 2
    assert "fii_pct" in patterns[0]
    assert "dii_mf_pct" in patterns[0]
    assert "quarter_start_date" in patterns[0]
    assert "is_current_quarter" in patterns[0]
    assert patterns[0]["is_current_quarter"] is True
    assert "stock_price" in patterns[0]
    assert patterns[0]["stock_price"] is not None
    assert patterns[0]["stock_price"] > 0

    # Verify block deals
    block_deals = activity["block_deals"]
    assert len(block_deals) >= 1
    assert block_deals[0]["deal_type"] in ["BUY", "SELL"]


def test_top_accumulated_and_distributed_stocks():
    acc = get_top_accumulated_stocks(limit=300)
    assert len(acc) >= 2
    tickers = [x["ticker"] for x in acc]
    assert "ALLCARGO.NS" in tickers
    assert "DIXON.NS" in tickers

    dist = get_top_distributed_stocks(limit=300)
    assert isinstance(dist, list)


def test_funds_directory_and_portfolio():
    funds = get_all_funds_activity(limit=20)
    assert len(funds) >= 4
    fund_names = [f["fund_name"] for f in funds]
    assert any("Nippon" in fn for fn in fund_names)
    assert "return_30d_pct" in funds[0]
    assert "return_1y_pct" in funds[0]

    # Test reverse fund portfolio lookup
    nippon_holdings = get_fund_portfolio_activity("Nippon India Small Cap Fund")
    assert nippon_holdings is not None
    assert len(nippon_holdings) >= 1
    assert any(h["ticker"] == "ALLCARGO.NS" for h in nippon_holdings)
    assert "return_30d_pct" in nippon_holdings[0]
    assert "return_1y_pct" in nippon_holdings[0]
    assert "company_name" in nippon_holdings[0]


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
    funds_data = res_funds.json()["funds"]
    assert len(funds_data) >= 1
    assert "return_30d_pct" in funds_data[0]
    assert "return_1y_pct" in funds_data[0]

    # Single fund drilldown
    top_fund_name = funds_data[0]["fund_name"]
    res_fund = client.get(f"/api/v1/institutional/fund/{top_fund_name}")
    assert res_fund.status_code == 200
    assert res_fund.json()["success"] is True
    assert len(res_fund.json()["holdings"]) >= 1
    assert "return_30d_pct" in res_fund.json()["holdings"][0]


def test_fii_interest_and_always_held_fallback():
    # 1. Constantly held stock (e.g. ALLCARGO.NS or TCS.NS)
    act_allcargo = get_stock_institutional_activity("ALLCARGO.NS")
    assert act_allcargo["fii_always_held"] is True
    assert "Had" in act_allcargo["fii_interest_summary"]
    assert "on Dec 2025" in act_allcargo["fii_interest_summary"]

    # 2. Stock with simulated FII interest start within 8M window (e.g. WIPRO.NS)
    act_wipro = get_stock_institutional_activity("WIPRO.NS")
    assert "fii_interest_summary" in act_wipro
    assert "is_new_fii_entry" in act_wipro
    assert "is_new_dii_entry" in act_wipro
    if not act_wipro["fii_always_held"]:
        assert act_wipro["fii_interest_quarter"] is not None
        assert act_wipro["fii_interest_date"] is not None
        assert "Interest:" in act_wipro["fii_interest_summary"]


def test_new_entry_badges_in_api(client):
    res_acc = client.get("/api/v1/institutional/accumulating")
    assert res_acc.status_code == 200
    items = res_acc.json()["items"]
    assert len(items) >= 1
    # Check that new entry fields are exposed in table API items
    assert "is_new_fii_entry" in items[0]
    assert "is_new_dii_entry" in items[0]
    assert "fii_interest_summary" in items[0]


def test_top_stake_additions_endpoint(client):
    res = client.get("/api/v1/institutional/top-additions?min_delta=3.0")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert "latest_additions" in data
    assert "historical_additions" in data
    assert len(data["latest_additions"]) >= 1
    top1 = data["latest_additions"][0]
    assert "inst_addition_pct" in top1
    assert "fii_delta_pct" in top1
    assert "dii_delta_pct" in top1
    assert "total_institutional_stake_pct" in top1
    assert top1["inst_addition_pct"] >= 3.0


def test_institutional_integrity_endpoints(client):
    """Verify integrity health summary, ticker provenance/audit, and verify-and-repair endpoints."""
    # 1. System-wide integrity health summary
    res1 = client.get("/api/v1/institutional/integrity")
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["success"] is True
    assert "health_score" in data1
    assert "status" in data1
    assert "cadences" in data1
    assert "recent_findings" in data1

    # 2. Stock-specific integrity provenance and audit trail
    res2 = client.get("/api/v1/institutional/integrity/TCS.NS")
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["success"] is True
    assert data2["ticker"] == "TCS.NS"
    assert "health_score" in data2
    assert "status" in data2
    assert "provenance_trail" in data2
    assert "mathematical_findings" in data2

    # 3. Trigger on-demand verify and repair
    res3 = client.post("/api/v1/institutional/verify-and-repair", json={"scope": "MATHEMATICAL", "auto_repair": False})
    assert res3.status_code == 200
    data3 = res3.json()
    assert data3["success"] is True
    assert "report" in data3
    assert "health_score" in data3["report"]


