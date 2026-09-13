import pytest
from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection
from earnings_engine.data.migrations import apply_migrations
from earnings_engine.data.institutional_accumulation import (
    evaluate_and_track_strategy_signals,
    get_tracked_smart_money_signals,
)

@pytest.fixture
def test_env(tmp_path, monkeypatch):
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
        conn.execute("INSERT OR REPLACE INTO tickers (ticker, name, market_cap) VALUES ('WELCORP.NS', 'Welspun Corp Ltd', 20000.0)")
        conn.execute("INSERT OR REPLACE INTO price_history (ticker, date, open, high, low, close, volume) VALUES ('WELCORP.NS', '2026-08-01', 500.0, 520.0, 495.0, 500.0, 1000000)")
        conn.execute("INSERT OR REPLACE INTO price_history (ticker, date, open, high, low, close, volume) VALUES ('WELCORP.NS', '2026-08-30', 600.0, 610.0, 590.0, 600.0, 1500000)")
        conn.execute("""
            INSERT OR REPLACE INTO shareholding_patterns (ticker, quarter, promoter_pct, fii_pct, dii_mf_pct, public_retail_pct, other_pct, updated_at)
            VALUES ('WELCORP.NS', 'Q1 FY27', 48.0, 25.0, 15.0, 12.0, 0.0, '2026-08-05')
        """)
        conn.execute("""
            INSERT OR REPLACE INTO shareholding_patterns (ticker, quarter, promoter_pct, fii_pct, dii_mf_pct, public_retail_pct, other_pct, updated_at)
            VALUES ('WELCORP.NS', 'Q4 FY26', 48.0, 18.0, 14.0, 20.0, 0.0, '2026-05-05')
        """)
    return s

def test_evaluate_and_track_strategy_signals(test_env):
    s = test_env
    res = evaluate_and_track_strategy_signals(settings=s)
    assert res["total_signals"] >= 1

    signals_data = get_tracked_smart_money_signals(strategy="ALL_STRATEGIES", settings=s)
    signals = signals_data.get("signals", [])
    assert len(signals) >= 1
    sig = signals[0]
    assert sig["ticker"] == "WELCORP.NS"
    assert sig["signal_price"] > 0
    assert sig["current_price"] == 600.0
    assert sig["outcome_return_pct"] is not None
    assert sig["target_price"] > sig["signal_price"]
    assert sig["stop_loss"] < sig["signal_price"]
    assert sig["lifecycle_status"] in ("ACTIVE", "TARGET_HIT")


def test_strategy_filtering_and_lifecycle_transitions(tmp_path, monkeypatch):
    monkeypatch.delenv("TURSO_DATABASE_URL", raising=False)
    monkeypatch.delenv("TURSO_AUTH_TOKEN", raising=False)
    monkeypatch.setenv("EARNINGS_ENGINE_DB_NAME", f"test_strat_{tmp_path.name}.sqlite3")
    s = Settings()
    s.data_dirs["prices"] = tmp_path
    s.data_dirs["earnings"] = tmp_path
    s.ensure_dirs()
    apply_migrations(s)

    conn = get_db_connection(s)
    with conn:
        # Stock 1: Block Deal Momentum
        conn.execute("INSERT OR REPLACE INTO tickers (ticker, name, market_cap) VALUES ('BLOCKCO.NS', 'Block Deal Co', 50000.0)")
        conn.execute("INSERT OR REPLACE INTO price_history (ticker, date, open, high, low, close, volume) VALUES ('BLOCKCO.NS', '2026-08-01', 100.0, 105.0, 95.0, 100.0, 5000000)")
        conn.execute("INSERT OR REPLACE INTO price_history (ticker, date, open, high, low, close, volume) VALUES ('BLOCKCO.NS', '2026-08-20', 125.0, 130.0, 120.0, 125.0, 6000000)")
        conn.execute("""
            INSERT OR REPLACE INTO institutional_block_deals (deal_date, ticker, client_name, deal_type, quantity, price, value_cr, pct_equity, exchange, created_at)
            VALUES ('2026-08-05', 'BLOCKCO.NS', 'NIPPON INDIA MF', 'BUY', 500000, 100.0, 30.0, 1.5, 'NSE', '2026-08-05')
        """)

        # Stock 2: Domestic Absorption in Small Cap
        conn.execute("INSERT OR REPLACE INTO tickers (ticker, name, market_cap) VALUES ('SMALLDOM.NS', 'Smallcap Dom Co', 3000.0)")
        conn.execute("INSERT OR REPLACE INTO price_history (ticker, date, open, high, low, close, volume) VALUES ('SMALLDOM.NS', '2026-08-01', 200.0, 205.0, 195.0, 200.0, 1000000)")
        conn.execute("INSERT OR REPLACE INTO price_history (ticker, date, open, high, low, close, volume) VALUES ('SMALLDOM.NS', '2026-08-20', 180.0, 185.0, 175.0, 180.0, 1000000)")
        conn.execute("""
            INSERT OR REPLACE INTO institutional_holdings (ticker, fund_name, fund_type, action, quarter, holding_value_cr, stake_pct, change_pct, change_shares, recent_buy_price, reported_date, created_at)
            VALUES ('SMALLDOM.NS', 'HDFC Small Cap Fund', 'Domestic Mutual Fund (DII)', 'NEW BUY', 'Q1 FY27', 35.0, 1.2, 1.2, 1750000, 200.0, '2026-08-05', '2026-08-05')
        """)

    # Evaluate
    res = evaluate_and_track_strategy_signals(settings=s)
    assert res["total_signals"] >= 2

    # Query Block deal strategy
    block_res = get_tracked_smart_money_signals(strategy="BLOCK_DEAL_MOMENTUM", settings=s)
    block_tickers = [x["ticker"] for x in block_res.get("signals", [])]
    assert "BLOCKCO.NS" in block_tickers

    # Query Domestic absorption strategy
    dom_res = get_tracked_smart_money_signals(strategy="DOMESTIC_ABSORPTION", settings=s)
    dom_tickers = [x["ticker"] for x in dom_res.get("signals", [])]
    assert "SMALLDOM.NS" in dom_tickers

    # Check signal price immutability across subsequent evaluation
    sig_block = [x for x in block_res["signals"] if x["ticker"] == "BLOCKCO.NS"][0]
    initial_sig_price = sig_block["signal_price"]
    assert initial_sig_price == 100.0
    assert sig_block["outcome_return_pct"] == 25.0
    assert sig_block["lifecycle_status"] == "TARGET_HIT"  # 125 >= 120 (100 * 1.20)


def test_dual_acceleration_and_sorting(tmp_path, monkeypatch):
    monkeypatch.delenv("TURSO_DATABASE_URL", raising=False)
    monkeypatch.delenv("TURSO_AUTH_TOKEN", raising=False)
    monkeypatch.setenv("EARNINGS_ENGINE_DB_NAME", f"test_dual_{tmp_path.name}.sqlite3")
    s = Settings()
    s.data_dirs["prices"] = tmp_path
    s.data_dirs["earnings"] = tmp_path
    s.ensure_dirs()
    apply_migrations(s)

    conn = get_db_connection(s)
    with conn:
        conn.execute("INSERT OR REPLACE INTO tickers (ticker, name, market_cap) VALUES ('DUALACC.NS', 'Dual Acc Tech', 15000.0)")
        conn.execute("INSERT OR REPLACE INTO price_history (ticker, date, open, high, low, close, volume) VALUES ('DUALACC.NS', '2026-08-01', 300.0, 310.0, 290.0, 300.0, 2000000)")
        conn.execute("INSERT OR REPLACE INTO price_history (ticker, date, open, high, low, close, volume) VALUES ('DUALACC.NS', '2026-08-25', 330.0, 335.0, 320.0, 330.0, 2500000)")
        conn.execute("""
            INSERT OR REPLACE INTO shareholding_patterns (ticker, quarter, promoter_pct, fii_pct, dii_mf_pct, public_retail_pct, other_pct, updated_at)
            VALUES ('DUALACC.NS', 'Q1 FY27', 40.0, 22.0, 18.0, 20.0, 0.0, '2026-08-10')
        """)
        conn.execute("""
            INSERT OR REPLACE INTO shareholding_patterns (ticker, quarter, promoter_pct, fii_pct, dii_mf_pct, public_retail_pct, other_pct, updated_at)
            VALUES ('DUALACC.NS', 'Q4 FY26', 40.0, 19.0, 16.0, 25.0, 0.0, '2026-05-10')
        """)

    # Evaluate
    res = evaluate_and_track_strategy_signals(settings=s)
    assert res["total_signals"] >= 1

    signals_data = get_tracked_smart_money_signals(strategy="ALL_STRATEGIES", sort_by="return", settings=s)
    signals = signals_data.get("signals", [])
    assert len(signals) >= 1
    assert signals[0]["ticker"] == "DUALACC.NS"
    assert signals[0]["outcome_return_pct"] == 10.0
    assert signals[0]["lifecycle_status"] == "ACTIVE"

