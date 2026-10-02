"""Unit tests for Institutional Screen 3 Distinct Financial Metrics:
1. Increase by Percentage (%)
2. Increase by Amount in Crore (₹ Cr)
3. Total Amount in Crore (₹ Cr)
"""
import pytest
from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection
from earnings_engine.data.migrations import apply_migrations
from earnings_engine.data.institutional_accumulation import (
    get_stock_institutional_activity,
    get_top_stake_additions,
    get_fund_portfolio_activity,
)


@pytest.fixture
def test_settings(tmp_path, monkeypatch):
    monkeypatch.delenv("TURSO_DATABASE_URL", raising=False)
    monkeypatch.delenv("TURSO_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("EARNINGS_ENGINE_DB_PATH", raising=False)
    monkeypatch.setenv("EARNINGS_ENGINE_DB_NAME", f"test_{tmp_path.name}.sqlite3")
    s = Settings()
    s.data_dirs["prices"] = tmp_path
    s.data_dirs["earnings"] = tmp_path
    s.ensure_dirs()
    apply_migrations(s)
    return s


def test_stock_and_holdings_three_metrics(test_settings):
    """Verify that stock and fund-level holdings calculate and expose the 3 distinct financial metrics."""
    conn = get_db_connection(test_settings)
    with conn:
        # Seed ticker with market cap of ₹10,000 Cr (1e11)
        conn.execute(
            "INSERT OR REPLACE INTO tickers (ticker, name, market_cap) VALUES ('TESTCO.NS', 'Test Company Ltd', 100000000000)"
        )
        # Seed price history for price returns
        conn.execute("""
            INSERT OR REPLACE INTO price_history (ticker, date, open, high, low, close, volume)
            VALUES ('TESTCO.NS', '2026-08-28', 100.0, 105.0, 98.0, 102.0, 100000)
        """)
        # Seed shareholding patterns for QoQ comparison
        conn.execute("""
            INSERT OR REPLACE INTO shareholding_patterns 
            (ticker, quarter, promoter_pct, fii_pct, dii_mf_pct, public_retail_pct, other_pct, updated_at)
            VALUES ('TESTCO.NS', 'Q1 FY27', 50.0, 20.0, 15.0, 15.0, 0.0, '2026-08-20')
        """)
        conn.execute("""
            INSERT OR REPLACE INTO shareholding_patterns 
            (ticker, quarter, promoter_pct, fii_pct, dii_mf_pct, public_retail_pct, other_pct, updated_at)
            VALUES ('TESTCO.NS', 'Q4 FY26', 50.0, 18.0, 14.0, 18.0, 0.0, '2026-05-20')
        """)
        # Seed fund holdings
        conn.execute("""
            INSERT OR REPLACE INTO institutional_holdings 
            (fund_name, fund_type, ticker, quarter, action, stake_pct, prev_stake_pct, change_pct, holding_value_cr, avg_price, recent_buy_price, recent_txn_price, recent_txn_date, recent_txn_type, reported_date, created_at, increase_amount_cr, total_amount_cr)
            VALUES ('Alpha Growth Fund', 'Mutual Fund', 'TESTCO.NS', 'Q1 FY27', 'ACCUMULATED', 2.5, 2.0, 0.5, 250.0, 1000.0, 1050.0, 1050.0, '2026-08-20', 'BUY', '2026-08-20', '2026-08-20', 50.0, 250.0)
        """)
        conn.commit()

    res = get_stock_institutional_activity("TESTCO.NS", settings=test_settings)
    assert res is not None
    assert res["ticker"] == "TESTCO.NS"
    # Stock level metrics
    # Latest total inst = 20 + 15 = 35%; Previous = 18 + 14 = 32%; Delta = +3.0%
    assert res["increase_pct"] == 3.0
    # Increase amount = 3% of ₹10,000 Cr = ₹300.0 Cr
    assert res["increase_amount_cr"] == 300.0
    # Total amount = 35% of ₹10,000 Cr = ₹3500.0 Cr
    assert res["total_amount_cr"] == 3500.0

    # Fund level metrics in holdings table
    assert len(res["holdings"]) == 1
    h = res["holdings"][0]
    assert h["fund_name"] == "Alpha Growth Fund"
    assert h["change_pct"] == 0.5
    assert h["increase_amount_cr"] == 50.0
    assert h["total_amount_cr"] == 250.0


def test_top_stake_additions_three_metrics(test_settings):
    """Verify get_top_stake_additions returns the 3 distinct financial metrics."""
    conn = get_db_connection(test_settings)
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO tickers (ticker, name, market_cap) VALUES ('SURGE.NS', 'Surge Tech Ltd', 50000000000)"
        )
        conn.execute("""
            INSERT OR REPLACE INTO shareholding_patterns 
            (ticker, quarter, promoter_pct, fii_pct, dii_mf_pct, public_retail_pct, other_pct, updated_at)
            VALUES ('SURGE.NS', 'Q1 FY27', 40.0, 30.0, 15.0, 15.0, 0.0, '2026-08-20')
        """)
        conn.execute("""
            INSERT OR REPLACE INTO shareholding_patterns 
            (ticker, quarter, promoter_pct, fii_pct, dii_mf_pct, public_retail_pct, other_pct, updated_at)
            VALUES ('SURGE.NS', 'Q4 FY26', 40.0, 26.0, 15.0, 19.0, 0.0, '2026-05-20')
        """)
        conn.commit()

    res = get_top_stake_additions(min_delta=1.0, settings=test_settings)
    assert res["latest_count"] >= 1
    item = next(it for it in res["latest_additions"] if it["ticker"] == "SURGE.NS")
    # Increase % = 45% - 41% = 4.0%
    assert item["increase_pct"] == 4.0
    assert item["inst_addition_pct"] == 4.0
    # Market cap = ₹5,000 Cr; 4% = ₹200.0 Cr
    assert item["increase_amount_cr"] == 200.0
    # Total institutional stake = 45%; 45% of ₹5,000 Cr = ₹2,250.0 Cr
    assert item["total_amount_cr"] == 2250.0
    assert item["total_institutional_amount_cr"] == 2250.0


def test_fund_portfolio_activity_three_metrics(test_settings):
    """Verify get_fund_portfolio_activity returns the 3 distinct financial metrics for fund portfolios."""
    conn = get_db_connection(test_settings)
    with conn:
        conn.execute("""
            INSERT OR REPLACE INTO institutional_holdings 
            (fund_name, fund_type, ticker, quarter, action, stake_pct, change_pct, holding_value_cr, avg_price, recent_buy_price, recent_txn_price, recent_txn_date, recent_txn_type, reported_date, created_at, increase_amount_cr, total_amount_cr)
            VALUES ('Whale Capital', 'Super Investor', 'TITAN.NS', 'Q1 FY27', 'ACCUMULATED', 5.2, 0.8, 1250.0, 3200.0, 3350.0, 3350.0, '2026-08-25', 'BUY', '2026-08-25', '2026-08-25', 192.3, 1250.0)
        """)
        conn.commit()

    holdings = get_fund_portfolio_activity("Whale Capital", settings=test_settings)
    assert len(holdings) == 1
    h = holdings[0]
    assert h["ticker"] == "TITAN.NS"
    assert h["change_pct"] == 0.8
    assert h["increase_amount_cr"] == 192.31 or round(h["increase_amount_cr"], 1) == 192.3
    assert h["total_amount_cr"] == 1250.0


def test_top_stake_additions_deduplication_and_quarter_order(test_settings):
    """Verify historical surges deduplicate per ticker and sort multi-year quarters chronologically."""
    conn = get_db_connection(test_settings)
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO tickers (ticker, name, market_cap) VALUES ('DEDUP.NS', 'Dedup Tech Ltd', 10000000000)"
        )
        # Multiple quarters across FY25 and FY26
        conn.execute("""
            INSERT OR REPLACE INTO shareholding_patterns 
            (ticker, quarter, promoter_pct, fii_pct, dii_mf_pct, public_retail_pct, other_pct, updated_at)
            VALUES 
            ('DEDUP.NS', 'Q2 FY27', 40.0, 10.0, 10.0, 40.0, 0.0, '2026-08-20'),
            ('DEDUP.NS', 'Q1 FY27', 40.0, 8.0, 8.0, 44.0, 0.0, '2026-05-20'),
            ('DEDUP.NS', 'Q4 FY26', 40.0, 20.0, 15.0, 25.0, 0.0, '2026-02-20'),
            ('DEDUP.NS', 'Q3 FY26', 40.0, 5.0, 5.0, 50.0, 0.0, '2025-11-20'),
            ('DEDUP.NS', 'Q2 FY26', 40.0, 15.0, 15.0, 30.0, 0.0, '2025-08-20'),
            ('DEDUP.NS', 'Q1 FY26', 40.0, 2.0, 2.0, 56.0, 0.0, '2025-05-20')
        """)
        conn.commit()

    res = get_top_stake_additions(min_delta=3.0, settings=test_settings)
    # Ticker DEDUP.NS should appear at most once in historical surges with its highest surge
    dedup_hist = [x for x in res.get("historical_additions", []) if x["ticker"] == "DEDUP.NS"]
    assert len(dedup_hist) == 1
    # Q1 FY27 (16%) vs Q4 FY26 (35%) is -19% (unwind)
    # Q4 FY26 (35%) vs Q3 FY26 (10%) is +25%
    # Q3 FY26 (10%) vs Q2 FY26 (30%) is -20%
    # Q2 FY26 (30%) vs Q1 FY26 (4%) is +26%
    # Peak surge is Q2 FY26 vs Q1 FY26 (+26.0%)
    assert dedup_hist[0]["quarter_comparison"] == "Q2 FY26 vs Q1 FY26"
    assert dedup_hist[0]["inst_addition_pct"] == 26.0
