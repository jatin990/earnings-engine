"""Tests for Institutional Smart Money Signals and Forensic Dossier REST Endpoints."""

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
def setup_test_data(tmp_path, monkeypatch):
    monkeypatch.setenv("TESTING", "true")
    monkeypatch.delenv("TURSO_DATABASE_URL", raising=False)
    monkeypatch.delenv("TURSO_AUTH_TOKEN", raising=False)
    monkeypatch.setenv("EARNINGS_ENGINE_DB_NAME", f"test_api_signals_{tmp_path.name}.sqlite3")

    old_prices = _settings.data_dirs.get("prices")
    old_earnings = _settings.data_dirs.get("earnings")

    _settings.data_dirs["prices"] = tmp_path
    _settings.data_dirs["earnings"] = tmp_path
    _settings.ensure_dirs()
    apply_migrations(_settings)

    conn = get_db_connection(_settings)
    with conn:
        conn.execute("INSERT OR REPLACE INTO tickers (ticker, name, market_cap) VALUES ('RELIANCE.NS', 'Reliance Industries Ltd', 2000000.0)")
        conn.execute("INSERT OR REPLACE INTO price_history (ticker, date, open, high, low, close, volume) VALUES ('RELIANCE.NS', '2026-08-30', 2900.0, 2950.0, 2880.0, 2920.0, 5000000)")
        conn.execute("""
            INSERT OR REPLACE INTO quarterly_financials
            (ticker, quarter, period_end_date, revenue_cr, net_profit_cr, operating_profit_cr, operating_margin_pct, net_margin_pct, eps, yoy_revenue_growth_pct, yoy_pat_growth_pct)
            VALUES ('RELIANCE.NS', 'Q1 FY27', '2026-06-30', 235000.0, 19500.0, 38000.0, 16.2, 8.3, 28.8, 11.2, 14.5)
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
    try:
        yield _settings
    finally:
        if old_prices is not None:
            _settings.data_dirs["prices"] = old_prices
        if old_earnings is not None:
            _settings.data_dirs["earnings"] = old_earnings


def test_api_institutional_signals_and_forensics():
    client = TestClient(app)

    # 1. Signals endpoint
    resp = client.get("/api/v1/institutional/signals?strategy=ALL_STRATEGIES&limit=20")
    assert resp.status_code == 200
    data = resp.json()
    assert "signals" in data
    assert "macro_summary" in data
    assert len(data["signals"]) >= 1

    # 2. Stock forensics endpoint
    resp_f = client.get("/api/v1/institutional/stock/RELIANCE.NS/forensics")
    assert resp_f.status_code == 200
    fdata = resp_f.json()
    assert fdata["ticker"] == "RELIANCE.NS"
    assert "signal_timeline" in fdata
    assert len(fdata["signal_timeline"]) >= 1
    assert "buyers" in fdata
    assert len(fdata["buyers"]) >= 1
    assert "quarterly_income" in fdata
    assert len(fdata["quarterly_income"]) >= 1
    assert "block_deals" in fdata
    assert len(fdata["block_deals"]) >= 1


def test_api_institutional_signals_filters_and_sorting():
    client = TestClient(app)

    # Filter by strategy
    resp_whale = client.get("/api/v1/institutional/signals?strategy=WHALE_CONVICTION&status=all&sort_by=score")
    assert resp_whale.status_code == 200
    wdata = resp_whale.json()
    assert wdata["strategy"] == "WHALE_CONVICTION"

    # Filter by non-existent strategy should return empty list
    resp_empty = client.get("/api/v1/institutional/signals?strategy=NON_EXISTENT")
    assert resp_empty.status_code == 200
    edata = resp_empty.json()
    assert edata["signals"] == []


def test_api_institutional_stock_forensics_not_found():
    client = TestClient(app)
    resp = client.get("/api/v1/institutional/stock/UNKNOWN_NONEXISTENT_XYZ.NS/forensics")
    # Dossier synthesizes fallback with ticker, or 404
    assert resp.status_code in (200, 404)
