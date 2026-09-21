"""Tests for institutional holdings pricing, baseline pre-IPO classification, and profit-taking accounting."""

from __future__ import annotations

import pytest
from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection
from earnings_engine.data.migrations import apply_migrations
from earnings_engine.data.institutional_accumulation import (
    get_stock_institutional_activity,
    get_top_stake_additions,
    recalculate_all_institutional_metrics,
)


@pytest.fixture
def test_settings(tmp_path, monkeypatch):
    monkeypatch.delenv("TURSO_DATABASE_URL", raising=False)
    monkeypatch.delenv("TURSO_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("EARNINGS_ENGINE_DB_PATH", raising=False)
    monkeypatch.setenv("EARNINGS_ENGINE_DB_NAME", f"test_inst_pt_{tmp_path.name}.sqlite3")
    s = Settings()
    s.data_dirs["prices"] = tmp_path
    s.data_dirs["earnings"] = tmp_path
    s.ensure_dirs()
    apply_migrations(s)
    return s


def test_baseline_pre_ipo_and_profit_taking_accounting(test_settings):
    """Verify that baseline holdings do not have fabricated prices, and PROFIT TAKING increments selling_count & outflow."""
    conn = get_db_connection(test_settings)
    with conn:
        conn.execute("INSERT OR REPLACE INTO tickers (ticker, name, market_cap) VALUES ('LENS.NS', 'Lenskart Solutions Ltd', 100000000000)")
        conn.execute("INSERT OR REPLACE INTO price_history (ticker, date, open, high, low, close, volume) VALUES ('LENS.NS', '2026-09-21', 680.0, 690.0, 675.0, 683.0, 500000)")
        conn.execute("INSERT OR REPLACE INTO price_history (ticker, date, open, high, low, close, volume) VALUES ('LENS.NS', '2026-06-15', 510.0, 520.0, 505.0, 510.0, 400000)")
        conn.execute("INSERT OR REPLACE INTO price_history (ticker, date, open, high, low, close, volume) VALUES ('LENS.NS', '2025-11-15', 400.0, 410.0, 395.0, 403.0, 300000)")

        # Shareholding patterns: Q1 FY27 vs Q4 FY26
        conn.execute("""
            INSERT OR REPLACE INTO shareholding_patterns
            (ticker, quarter, promoter_pct, fii_pct, dii_mf_pct, public_retail_pct, other_pct, updated_at)
            VALUES ('LENS.NS', 'Q1 FY27', 17.53, 12.76, 23.56, 45.73, 0.0, '2026-08-20')
        """)
        conn.execute("""
            INSERT OR REPLACE INTO shareholding_patterns
            (ticker, quarter, promoter_pct, fii_pct, dii_mf_pct, public_retail_pct, other_pct, updated_at)
            VALUES ('LENS.NS', 'Q4 FY26', 17.55, 4.26, 15.48, 62.30, 0.0, '2026-05-20')
        """)

        # Holdings in Q1 FY27:
        # 1. Pre-IPO fund trimming (PROFIT TAKING)
        conn.execute("""
            INSERT INTO institutional_holdings
            (ticker, fund_name, fund_type, quarter, shares_held, stake_pct, holding_value_cr, prev_stake_pct, action, change_pct, avg_price, recent_buy_price, recent_txn_price, recent_txn_date, recent_txn_type, reported_date)
            VALUES ('LENS.NS', 'SoftBank Vision Fund', 'Institutional Investor', 'Q1 FY27', 9860000, 9.86, 986.0, 13.13, 'PROFIT TAKING', -3.27, NULL, NULL, 510.0, '2026-04-01', 'SELL', '2026-06-30')
        """)
        # 2. Secondary market mutual fund (NEW BUY)
        conn.execute("""
            INSERT INTO institutional_holdings
            (ticker, fund_name, fund_type, quarter, shares_held, stake_pct, holding_value_cr, prev_stake_pct, action, change_pct, avg_price, recent_buy_price, recent_txn_price, recent_txn_date, recent_txn_type, reported_date)
            VALUES ('LENS.NS', 'Mirae Asset Large Cap', 'Mutual Fund (DII)', 'Q1 FY27', 1740000, 1.74, 174.0, 0.0, 'NEW BUY', 1.74, 510.0, 510.0, 510.0, '2026-04-01', 'BUY', '2026-06-30')
        """)
        # 3. Baseline holding from older quarter that dropped below 1% in Q1 FY27
        conn.execute("""
            INSERT INTO institutional_holdings
            (ticker, fund_name, fund_type, quarter, shares_held, stake_pct, holding_value_cr, prev_stake_pct, action, change_pct, avg_price, recent_buy_price, recent_txn_price, recent_txn_date, recent_txn_type, reported_date)
            VALUES ('LENS.NS', 'Old Fund From Q3', 'AIF', 'Q3 FY26', 1500000, 1.50, 150.0, 0.0, 'BASELINE', 1.50, NULL, NULL, 403.0, '2025-10-01', 'HOLD', '2025-12-31')
        """)
        conn.commit()

    rec_res = recalculate_all_institutional_metrics(settings=test_settings, force=True)
    assert rec_res["success"] is True

    # Check stock activity
    stock = get_stock_institutional_activity("LENS.NS", settings=test_settings, force_refresh=True)
    assert stock["funds_accumulating_count"] == 1  # Only Mirae Asset in Q1 FY27, not the old Q3 fund
    assert stock["funds_selling_count"] == 1       # SoftBank PROFIT TAKING recognized
    assert stock["gross_inflow_cr"] > 0
    assert stock["gross_outflow_cr"] > 0

    holdings = stock["holdings"]
    softbank = next(h for h in holdings if h["fund_name"] == "SoftBank Vision Fund")
    assert softbank["action"] == "PROFIT TAKING"
    assert softbank["avg_price"] is None  # Pre-IPO, unquoted cost basis
    assert softbank["recent_txn_price"] == 510.0
    assert softbank["recent_txn_type"] == "SELL"
    assert softbank["increase_amount_cr"] < 0  # Negative outflow amount

    mirae = next(h for h in holdings if h["fund_name"] == "Mirae Asset Large Cap")
    assert mirae["action"] == "NEW BUY"
    assert mirae["avg_price"] == 510.0
    assert mirae["recent_txn_type"] == "BUY"
    assert mirae["increase_amount_cr"] > 0