"""
tests/test_deals_service.py
Targeted tests for block deals retrieval, PIT compliance, and inflow window metrics.
"""
import sqlite3
import pytest
from earnings_engine.common.symbols import normalize_symbol
from earnings_engine.services.deals_service import (
    get_institutional_inflow_metrics,
    get_stock_block_deals,
)


@pytest.fixture
def mock_db(tmp_path):
    db_file = tmp_path / "test_engine.db"
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE bulk_block_deals (
            deal_date TEXT,
            symbol TEXT,
            client_name TEXT,
            buy_sell TEXT,
            quantity INTEGER,
            trade_price REAL,
            deal_type TEXT,
            exchange TEXT
        )
    """)
    deals = [
        ("2026-03-01", "RELIANCE", "SBI Mutual Fund", "BUY", 100000, 2500.0, "BLOCK", "NSE"),
        ("2026-03-10", "RELIANCE", "Vanguard Emerging", "B", 50000, 2550.0, "BULK", "NSE"),
        ("2026-03-15", "RELIANCE", "HDFC Life", "SELL", 40000, 2600.0, "BLOCK", "NSE"),
        ("2026-03-25", "RELIANCE", "BlackRock Fund", "BUY", 80000, 2620.0, "BLOCK", "NSE"),
        ("2026-03-10", "TCS", "Morgan Stanley", "BUY", 20000, 4000.0, "BLOCK", "NSE"),
    ]
    cursor.executemany(
        "INSERT INTO bulk_block_deals VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        deals,
    )
    conn.commit()
    conn.close()
    return str(db_file)


def test_symbol_normalization():
    assert normalize_symbol("RELIANCE.NS") == "RELIANCE"
    assert normalize_symbol("TCS-EQ") == "TCS"
    assert normalize_symbol("INFY.BO") == "INFY"
    assert normalize_symbol("  tatamotors  ") == "TATAMOTORS"


def test_deals_retrieval_and_pit_boundary(mock_db):
    deals = get_stock_block_deals(mock_db, "RELIANCE.NS", asof_date="2026-03-15")
    
    assert len(deals) == 3
    assert deals[0]["client_name"] == "HDFC Life"
    assert deals[0]["direction"] == "SELL"
    assert deals[0]["seller_name"] == "HDFC Life"
    assert deals[0]["buyer_name"] is None
    assert deals[0]["value_cr"] == round((40000 * 2600.0) / 1e7, 2)

    dates = [d["deal_date"] for d in deals]
    assert "2026-03-25" not in dates


def test_institutional_inflow_calculation(mock_db):
    inflow = get_institutional_inflow_metrics(
        mock_db,
        "RELIANCE",
        asof_date="2026-03-15",
        horizon_days=30,
    )

    assert inflow["horizon_days"] == 30
    assert inflow["total_deals"] == 3
    assert inflow["total_buy_cr"] == 37.75
    assert inflow["total_sell_cr"] == 10.4
    assert inflow["net_inflow_cr"] == 27.35
    assert inflow["sentiment"] == "ACCUMULATION"
