"""Tests for Institutional Accumulation, Mutual Fund Holdings, and Block Deals."""
import pytest
from fastapi.testclient import TestClient
from earnings_engine.api.server import app
from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection
from earnings_engine.data.institutional_accumulation import (
    get_stock_institutional_activity,
    get_top_accumulated_stocks,
    get_top_distributed_stocks,
    get_all_funds_activity,
    get_fund_portfolio_activity,
    init_institutional_db,
)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def setup_test_institutional_data():
    """Seed isolated, authentic-format test fixtures into DB for institutional tests."""
    settings = Settings()
    init_institutional_db(settings)
    conn = get_db_connection(settings)

    # Insert test shareholding pattern for ALLCARGO.NS and DIXON.NS
    conn.execute(
        """
        INSERT OR REPLACE INTO shareholding_patterns (
            ticker, quarter, promoter_pct, fii_pct, dii_mf_pct, public_retail_pct, other_pct, updated_at
        ) VALUES
        ('ALLCARGO.NS', 'Q1 FY27', 45.45, 2.46, 3.01, 49.08, 0.0, '2026-08-27T07:10:20Z'),
        ('ALLCARGO.NS', 'Q4 FY26', 45.45, 2.40, 2.90, 49.25, 0.0, '2026-05-15T07:10:20Z'),
        ('DIXON.NS', 'Q1 FY27', 33.50, 18.20, 24.10, 24.20, 0.0, '2026-08-27T07:10:20Z')
        """
    )

    # Insert sample authentic test holdings for Nippon India Small Cap Fund
    conn.execute(
        """
        INSERT OR REPLACE INTO institutional_holdings (
            id, ticker, fund_name, fund_type, quarter, shares_held, stake_pct, holding_value_cr,
            prev_stake_pct, action, change_shares, change_pct, reported_date, created_at,
            avg_price, recent_buy_price, recent_txn_price, recent_txn_date, recent_txn_type,
            increase_amount_cr, total_amount_cr
        ) VALUES
        (99901, 'ALLCARGO.NS', 'Nippon India Small Cap Fund', 'Mutual Fund (DII)', 'Q1 FY27', 10484533, 0.70, 12.81, 0.55, 'ACCUMULATED', 2246685, 0.15, '2026-07-18', '2026-07-18T00:00:00Z', 11.24, 11.98, 11.98, '2026-07-15', 'BUY', 2.75, 12.81),
        (99902, 'ALLCARGO.NS', 'Quant Active Fund', 'Mutual Fund (DII)', 'Q1 FY27', 7488952, 0.50, 9.15, 0.0, 'NEW BUY', 7488952, 0.50, '2026-07-18', '2026-07-18T00:00:00Z', 11.24, 11.98, 11.98, '2026-07-16', 'BUY', 9.15, 9.15),
        (99903, 'ALLCARGO.NS', 'Ashish Kacholia', 'Super Investor', 'Q1 FY27', 4493371, 0.30, 5.49, 0.20, 'ACCUMULATED', 1497790, 0.10, '2026-07-18', '2026-07-18T00:00:00Z', 11.24, 11.98, 11.98, '2026-07-12', 'BUY', 1.83, 5.49),
        (99904, 'ALLCARGO.NS', 'Vanguard Emerging Markets Fund', 'Foreign Institutional (FII)', 'Q1 FY27', 13180556, 0.88, 16.11, 0.88, 'HOLD', 0, 0.0, '2026-07-18', '2026-07-18T00:00:00Z', 11.24, 11.98, 11.98, '2026-07-10', 'HOLD', 0.0, 16.11)
        """
    )

    # Insert sample authentic test block deal
    conn.execute(
        """
        INSERT OR REPLACE INTO institutional_block_deals (
            ticker, deal_date, client_name, deal_type, quantity, price, value_cr, created_at
        ) VALUES
        ('ALLCARGO.NS', '2026-07-15', 'Nippon India Small Cap Fund', 'BUY', 2246685, 11.98, 2.69, '2026-07-15T15:30:00Z')
        """
    )
    if hasattr(conn, "commit"):
        conn.commit()

    yield

    # Clean up test rows
    conn.execute("DELETE FROM institutional_holdings WHERE id IN (99901, 99902, 99903, 99904)")
    conn.execute("DELETE FROM institutional_block_deals WHERE deal_date = '2026-07-15' AND ticker = 'ALLCARGO.NS'")
    if hasattr(conn, "commit"):
        conn.commit()


def test_allcargo_institutional_breakdown():
    # Test ALLCARGO.NS activity structure and metrics
    activity = get_stock_institutional_activity("ALLCARGO.NS")
    assert activity is not None
    assert activity["ticker"] == "ALLCARGO.NS"
    assert "verdict" in activity

    # Verify fund holdings present from test fixtures
    holdings = activity["holdings"]
    assert len(holdings) >= 4
    fund_names = [h["fund_name"] for h in holdings]
    assert any("Nippon" in fn for fn in fund_names)
    assert any("Quant" in fn for fn in fund_names)
    assert any("Ashish Kacholia" in fn for fn in fund_names)

    # Verify actions
    actions = [h["action"] for h in holdings]
    assert "ACCUMULATED" in actions or "NEW BUY" in actions

    # Verify shareholding pattern trend
    patterns = activity["shareholding_patterns"]
    assert len(patterns) >= 2
    assert "fii_pct" in patterns[0]
    assert "dii_mf_pct" in patterns[0]
    assert "quarter_start_date" in patterns[0]
    assert "is_current_quarter" in patterns[0]
    assert patterns[0]["is_current_quarter"] is True

    # Verify block deals
    block_deals = activity["block_deals"]
    assert len(block_deals) >= 1
    assert block_deals[0]["deal_type"] in ["BUY", "SELL"]


def test_top_accumulated_and_distributed_stocks():
    acc = get_top_accumulated_stocks(limit=300)
    assert isinstance(acc, list)

    dist = get_top_distributed_stocks(limit=300)
    assert isinstance(dist, list)


def test_funds_directory_and_portfolio():
    funds = get_all_funds_activity(limit=20)
    assert len(funds) >= 1
    fund_names = [f["fund_name"] for f in funds]
    assert any("Nippon" in fn for fn in fund_names)

    # Test reverse fund portfolio lookup
    nippon_holdings = get_fund_portfolio_activity("Nippon India Small Cap Fund")
    assert nippon_holdings is not None
    assert len(nippon_holdings) >= 1
    assert any(h["ticker"] == "ALLCARGO.NS" for h in nippon_holdings)
    assert "company_name" in nippon_holdings[0]


def test_institutional_api_endpoints(client):
    # Summary
    res_sum = client.get("/api/v1/institutional/summary")
    assert res_sum.status_code == 200

    # Accumulating
    res_acc = client.get("/api/v1/institutional/accumulating")
    assert res_acc.status_code == 200

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

    # Single fund drilldown
    top_fund_name = funds_data[0]["fund_name"]
    res_fund = client.get(f"/api/v1/institutional/fund/{top_fund_name}")
    assert res_fund.status_code == 200
    assert res_fund.json()["success"] is True
    assert len(res_fund.json()["holdings"]) >= 1


def test_fii_interest_and_always_held_fallback():
    # 1. Constantly held stock (e.g. ALLCARGO.NS)
    act_allcargo = get_stock_institutional_activity("ALLCARGO.NS")
    assert "fii_interest_summary" in act_allcargo
    assert "is_new_fii_entry" in act_allcargo
