import pytest
from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection
from earnings_engine.data.migrations import apply_migrations
from earnings_engine.data.institutional_accumulation import (
    get_stock_quarterly_financials,
    get_stock_forensic_dossier,
)

@pytest.fixture
def test_db(tmp_path, monkeypatch):
    monkeypatch.delenv("TURSO_DATABASE_URL", raising=False)
    monkeypatch.delenv("TURSO_AUTH_TOKEN", raising=False)
    monkeypatch.setenv("EARNINGS_ENGINE_DB_NAME", f"test_{tmp_path.name}.sqlite3")
    s = Settings()
    s.data_dirs["prices"] = tmp_path
    s.data_dirs["earnings"] = tmp_path
    s.ensure_dirs()
    apply_migrations(s)

    conn = get_db_connection(s)
    with conn:
        conn.execute("INSERT OR REPLACE INTO tickers (ticker, name, market_cap) VALUES ('RELIANCE.NS', 'Reliance Industries Ltd', 2000000.0)")
        conn.execute("INSERT OR REPLACE INTO price_history (ticker, date, open, high, low, close, volume) VALUES ('RELIANCE.NS', '2026-08-30', 2900.0, 2950.0, 2880.0, 2920.0, 5000000)")
        conn.execute("""
            INSERT OR REPLACE INTO quarterly_financials
            (ticker, quarter, period_end_date, revenue_cr, net_profit_cr, operating_profit_cr, operating_margin_pct, net_margin_pct, eps, yoy_revenue_growth_pct, yoy_pat_growth_pct)
            VALUES ('RELIANCE.NS', 'Q1 FY27', '2026-06-30', 235000.0, 19500.0, 38000.0, 16.2, 8.3, 28.8, 11.2, 14.5)
        """)
        conn.execute("""
            INSERT OR REPLACE INTO quarterly_financials
            (ticker, quarter, period_end_date, revenue_cr, net_profit_cr, operating_profit_cr, operating_margin_pct, net_margin_pct, eps, yoy_revenue_growth_pct, yoy_pat_growth_pct)
            VALUES ('RELIANCE.NS', 'Q4 FY26', '2026-03-31', 228000.0, 18900.0, 36500.0, 16.0, 8.3, 27.9, 9.8, 12.0)
        """)
        conn.execute("""
            INSERT OR REPLACE INTO institutional_holdings
            (ticker, fund_name, fund_type, holding_value_cr, stake_pct, change_pct, change_shares, quarter, reported_date)
            VALUES ('RELIANCE.NS', 'SBI Bluechip Fund', 'Mutual Fund (DII)', 1500.0, 1.25, 0.20, 1000000, 'Q1 FY27', '2026-08-01')
        """)
        conn.execute("""
            INSERT OR REPLACE INTO institutional_block_deals
            (ticker, deal_date, client_name, deal_type, quantity, price, value_cr, pct_equity, exchange)
            VALUES ('RELIANCE.NS', '2026-08-10', 'Vanguard Emerging Markets Fund', 'BUY', 500000, 2910.0, 145.5, 0.08, 'NSE')
        """)
        conn.execute("""
            INSERT OR REPLACE INTO institutional_radar_signals
            (ticker, strategy, signal_date, signal_price, current_price, target_price, stop_loss, outcome_return_pct, lifecycle_status, initial_score)
            VALUES ('RELIANCE.NS', 'WHALE_CONVICTION', '2026-08-05', 2850.0, 2920.0, 3420.0, 2622.0, 2.46, 'ACTIVE', 75.0)
        """)
    return s

def test_get_stock_quarterly_financials(test_db):
    s = test_db
    records = get_stock_quarterly_financials("RELIANCE.NS", settings=s)
    assert len(records) == 2
    assert records[0]["quarter"] == "Q1 FY27"
    assert records[0]["revenue_cr"] == 235000.0
    assert records[0]["net_profit_cr"] == 19500.0
    assert records[0]["operating_margin_pct"] == 16.2
    assert records[0]["yoy_pat_growth_pct"] == 14.5

def test_get_stock_forensic_dossier(test_db):
    s = test_db
    dossier = get_stock_forensic_dossier("RELIANCE.NS", settings=s)
    assert dossier is not None
    assert dossier["ticker"] == "RELIANCE.NS"
    assert "signal_timeline" in dossier
    assert len(dossier["signal_timeline"]) >= 1
    assert "buyers" in dossier
    assert len(dossier["buyers"]) >= 1
    assert "quarterly_income" in dossier
    assert len(dossier["quarterly_income"]) == 2
    assert "block_deals" in dossier
    assert len(dossier["block_deals"]) >= 1
