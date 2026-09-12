import pytest
from earnings_engine.data.institutional_accumulation import (
    calculate_institutional_score,
    get_stock_buyers_in_period,
)
from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection


def test_calculate_institutional_score_backward_compatibility():
    """Verify that calling calculate_institutional_score with 9 positional arguments works identically and returns a valid 3-tuple."""
    score, verdict, verdict_badge = calculate_institutional_score(
        4, 1, 2, 45.5, 60.0, 14.5, 1.25, 80.0, 650.0
    )
    assert isinstance(score, float)
    assert 5.0 <= score <= 98.0
    assert isinstance(verdict, str)
    assert verdict_badge in ("emerald", "green", "amber", "rose")


def test_calculate_institutional_score_tier1_macro_flow():
    """Verify that Tier 1 aggregate macro flow (% stake addition & Rupee flow) directionally shifts conviction."""
    # Strong positive macro flow (+3.5% stake addition, ₹500 Cr flow)
    high_score, high_verdict, high_badge = calculate_institutional_score(
        accumulating_count=2,
        selling_count=2,
        new_buys_count=0,
        net_flow_cr=500.0,
        gross_inflow_cr=500.0,
        gross_outflow_cr=0.0,
        inst_addition_pct=3.5,
        increase_amount_cr=500.0,
        total_inst_amount_cr=1200.0,
    )

    # Strong negative distribution (-3.5% stake dump, -₹500 Cr outflow)
    low_score, low_verdict, low_badge = calculate_institutional_score(
        accumulating_count=2,
        selling_count=2,
        new_buys_count=0,
        net_flow_cr=-500.0,
        gross_inflow_cr=0.0,
        gross_outflow_cr=500.0,
        inst_addition_pct=-3.5,
        increase_amount_cr=-500.0,
        total_inst_amount_cr=1200.0,
    )

    assert high_score > 70.0
    assert low_score < 40.0
    assert high_badge in ("emerald", "green")
    assert low_badge == "rose"


def test_calculate_institutional_score_tier2_breadth_and_block_deals():
    """Verify that Tier 2 fund breadth and net block deals lift score."""
    # Baseline neutral score
    base_score, _, _ = calculate_institutional_score(
        accumulating_count=2,
        selling_count=2,
        new_buys_count=0,
        net_flow_cr=0.0,
        gross_inflow_cr=10.0,
        gross_outflow_cr=10.0,
        inst_addition_pct=0.0,
        increase_amount_cr=0.0,
        total_inst_amount_cr=300.0,
    )

    # With high breadth (+8 accumulating, +3 new buys) and +₹150 Cr net block deals
    boosted_score, _, _ = calculate_institutional_score(
        accumulating_count=10,
        selling_count=2,
        new_buys_count=3,
        net_flow_cr=0.0,
        gross_inflow_cr=10.0,
        gross_outflow_cr=10.0,
        inst_addition_pct=0.0,
        increase_amount_cr=0.0,
        total_inst_amount_cr=300.0,
        block_deals_net_cr=150.0,
        block_deals_count=4,
    )

    assert boosted_score > base_score + 15.0


def test_calculate_institutional_score_tier3_whale_conviction():
    """Verify that Tier 3 Super Investors and Marquee AMCs act as conviction booster."""
    score_no_whales, _, _ = calculate_institutional_score(
        accumulating_count=3,
        selling_count=1,
        new_buys_count=1,
        net_flow_cr=30.0,
        gross_inflow_cr=40.0,
        gross_outflow_cr=10.0,
        inst_addition_pct=0.5,
        increase_amount_cr=30.0,
        total_inst_amount_cr=400.0,
    )

    score_with_whales, _, _ = calculate_institutional_score(
        accumulating_count=3,
        selling_count=1,
        new_buys_count=1,
        net_flow_cr=30.0,
        gross_inflow_cr=40.0,
        gross_outflow_cr=10.0,
        inst_addition_pct=0.5,
        increase_amount_cr=30.0,
        total_inst_amount_cr=400.0,
        super_investor_count=2,
        super_investor_cr=50.0,
        marquee_amc_count=2,
        marquee_amc_cr=120.0,
        whale_capital_cr=170.0,
    )

    assert score_with_whales > score_no_whales + 10.0


def test_implied_filing_price_and_unrealized_pnl(monkeypatch):
    """Verify that implied filing price and unrealized P&L are computed accurately."""
    settings = Settings()
    conn = get_db_connection(settings)

    test_ticker = "TEST_STOCK.NS"
    try:
        conn.execute("DELETE FROM institutional_holdings WHERE ticker = ?", (test_ticker,))
        conn.execute("DELETE FROM price_history WHERE ticker = ?", (test_ticker,))

        # Seed price history with latest price of 1200.0
        conn.execute(
            "INSERT INTO price_history (ticker, date, open, high, low, close, volume) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (test_ticker, "2026-09-10", 1180.0, 1220.0, 1175.0, 1200.0, 500000),
        )

        # Seed holding with holding_value_cr=200.0 Cr, shares_held=2,000,000, but no explicit price (avg_price=0, buy_price=0)
        # Implied price should be (200.0 * 1e7) / 2_000_000 = 1000.0
        # Unrealized P&L against LTP (1200.0) should be ((1200 - 1000) / 1000) * 100 = +20.0%
        conn.execute(
            """
            INSERT INTO institutional_holdings (
                ticker, fund_name, fund_type, quarter, shares_held, stake_pct,
                holding_value_cr, prev_stake_pct, action, change_shares, change_pct,
                avg_price, recent_buy_price, recent_txn_date, reported_date, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                test_ticker, "Marquee Growth Fund", "Mutual Fund", "Q1 FY27", 2000000, 2.5,
                200.0, 1.5, "ACCUMULATED", 800000, 1.0,
                0.0, 0.0, "2026-06-15", "2026-06-30", "2026-09-12T00:00:00"
            ),
        )
        conn.commit()

        res = get_stock_buyers_in_period(test_ticker, from_date="ALL", settings=settings)
        assert res["success"] is True
        assert res["latest_market_price"] == 1200.0
        assert res["latest_price_date"] == "2026-09-10"

        buyers = res["buyers"]
        assert len(buyers) >= 1
        b = buyers[0]
        assert b["price"] == 1000.0
        assert b["avg_price"] == 1000.0
        assert b["latest_market_price"] == 1200.0
        assert b["unrealized_gain_pct"] == 20.0

        summary = res["summary"]
        assert summary["latest_market_price"] == 1200.0
        assert summary["avg_unrealized_gain_pct"] == 20.0
        assert summary["profitable_buyers_count"] == 1
        assert summary["unprofitable_buyers_count"] == 0

    finally:
        conn.execute("DELETE FROM institutional_holdings WHERE ticker = ?", (test_ticker,))
        conn.execute("DELETE FROM price_history WHERE ticker = ?", (test_ticker,))
        conn.commit()
        conn.close()
