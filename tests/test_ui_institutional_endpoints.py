"""UI Integration and REST Endpoint Tests for Smart Money Strategy Radar & 4-Tab Forensics."""

from __future__ import annotations

import os
import pytest
from fastapi.testclient import TestClient

from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection
from earnings_engine.data.migrations import apply_migrations
from earnings_engine.api.dependencies import _settings
from earnings_engine.api.server import app


@pytest.fixture(autouse=True)
def setup_ui_test_data(tmp_path, monkeypatch):
    monkeypatch.setenv("TESTING", "true")
    monkeypatch.delenv("TURSO_DATABASE_URL", raising=False)
    monkeypatch.delenv("TURSO_AUTH_TOKEN", raising=False)
    monkeypatch.setenv("EARNINGS_ENGINE_DB_NAME", f"test_ui_inst_{tmp_path.name}.sqlite3")

    old_prices = _settings.data_dirs.get("prices")
    old_earnings = _settings.data_dirs.get("earnings")

    _settings.data_dirs["prices"] = tmp_path
    _settings.data_dirs["earnings"] = tmp_path
    _settings.ensure_dirs()
    apply_migrations(_settings)

    conn = get_db_connection(_settings)
    with conn:
        conn.execute("INSERT OR REPLACE INTO tickers (ticker, name, market_cap, sector, industry) VALUES ('KAYNES.NS', 'Kaynes Technology India Ltd', 2500000.0, 'Industrials', 'Electronics')")
        conn.execute("INSERT OR REPLACE INTO price_history (ticker, date, open, high, low, close, volume) VALUES ('KAYNES.NS', '2026-09-12', 4800.0, 4890.0, 4780.0, 4850.0, 350000)")
        conn.execute("""
            INSERT OR REPLACE INTO quarterly_financials
            (ticker, quarter, period_end_date, revenue_cr, net_profit_cr, operating_profit_cr, operating_margin_pct, net_margin_pct, eps, yoy_revenue_growth_pct, yoy_pat_growth_pct)
            VALUES ('KAYNES.NS', 'Q1 FY27', '2026-06-30', 650.0, 82.5, 110.0, 16.9, 12.7, 14.2, 34.2, 42.1)
        """)
        conn.execute("""
            INSERT OR REPLACE INTO institutional_holdings
            (ticker, fund_name, fund_type, holding_value_cr, stake_pct, change_pct, change_shares, quarter, reported_date, avg_price, recent_buy_price)
            VALUES ('KAYNES.NS', 'GQG Partners Emerging Markets Fund', 'FII / Foreign Portfolio Investor', 450.0, 2.45, 0.85, 250000, 'Q1 FY27', '2026-06-30', 4120.0, 4120.0)
        """)
        conn.execute("""
            INSERT OR REPLACE INTO institutional_block_deals
            (ticker, deal_date, client_name, deal_type, quantity, price, value_cr, pct_equity, exchange)
            VALUES ('KAYNES.NS', '2026-08-20', 'Morgan Stanley Asia Singapore Pte', 'BUY', 150000, 4650.0, 69.75, 0.35, 'NSE')
        """)
        conn.execute("""
            INSERT OR REPLACE INTO institutional_radar_signals
            (ticker, strategy, signal_date, signal_price, current_price, target_price, stop_loss, outcome_return_pct, lifecycle_status, initial_score, initial_smart_money_cr, whale_count)
            VALUES ('KAYNES.NS', 'WHALE_CONVICTION', '2026-06-15', 4250.0, 4850.0, 5300.0, 3800.0, 14.12, 'ACTIVE', 88.5, 142.5, 4)
        """)
    try:
        yield _settings
    finally:
        if old_prices is not None:
            _settings.data_dirs["prices"] = old_prices
        if old_earnings is not None:
            _settings.data_dirs["earnings"] = old_earnings


def test_ui_institutional_endpoints():
    client = TestClient(app)

    # 1. Dashboard loads with Institutional / Smart Money templates
    resp = client.get("/dashboard")
    assert resp.status_code == 200
    assert "Smart Money" in resp.text or "Institutional" in resp.text

    # 2. Signals endpoint integration with strategy filters
    resp_sig = client.get("/api/v1/institutional/signals?strategy=ALL_STRATEGIES&limit=10")
    assert resp_sig.status_code == 200
    data = resp_sig.json()
    assert "signals" in data
    assert "macro_summary" in data
    assert len(data["signals"]) >= 1

    # 3. Strategy specific filter
    resp_whale = client.get("/api/v1/institutional/signals?strategy=WHALE_CONVICTION&status=active&limit=10")
    assert resp_whale.status_code == 200
    whale_data = resp_whale.json()
    assert len(whale_data["signals"]) >= 1
    assert whale_data["signals"][0]["strategy"] == "WHALE_CONVICTION"

    # 4. Stock Forensics 4-Tab Payload integration
    resp_f = client.get("/api/v1/institutional/stock/KAYNES.NS/forensics")
    assert resp_f.status_code == 200
    fdata = resp_f.json()
    assert fdata["ticker"] == "KAYNES.NS"
    # Tab 1: Buyers
    assert "buyers" in fdata
    assert len(fdata["buyers"]) >= 1
    # Tab 2: Quarterly Income / Financials
    assert "quarterly_income" in fdata or "quarterly_financials" in fdata
    # Tab 3: Block Deals
    assert "block_deals" in fdata
    assert len(fdata["block_deals"]) >= 1
    # Tab 4: Signal Lifecycle Timeline
    assert "signal_timeline" in fdata
    assert len(fdata["signal_timeline"]) >= 1
