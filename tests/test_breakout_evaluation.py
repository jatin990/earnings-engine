"""Unit & Integration Tests for On-Demand Breakout Stock Evaluation & Autocomplete Search."""
import pytest
import pandas as pd
import numpy as np
from starlette.testclient import TestClient

from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection
from earnings_engine.data.prices import clear_price_df_cache
from earnings_engine.data.breakout_scanner import (
    evaluate_stock_breakout,
    search_breakout_tickers,
    score_breakout,
)
from earnings_engine.api.server import app


@pytest.fixture
def sample_stock_db():
    settings = Settings()
    clear_price_df_cache()
    conn = get_db_connection(settings)

    # Insert sample price history for RELIANCE.NS (100 daily bars)
    dates = pd.date_range("2026-01-01", periods=100, freq="B").strftime("%Y-%m-%d")
    np.random.seed(42)
    prices = 2500.0 + np.cumsum(np.random.randn(100) * 15.0)
    # Ensure upward momentum near highs
    prices[-10:] = np.linspace(2600.0, 2750.0, 10)

    with conn:
        conn.execute("DELETE FROM price_history WHERE ticker = 'RELIANCE.NS'")
        conn.execute("DELETE FROM tickers WHERE ticker = 'RELIANCE.NS'")
        conn.execute("INSERT OR REPLACE INTO tickers (ticker, name, sector, industry) VALUES ('RELIANCE.NS', 'Reliance Industries Ltd', 'Energy', 'Oil & Gas Refining')")

        for d, p in zip(dates, prices):
            conn.execute(
                """
                INSERT OR REPLACE INTO price_history (ticker, date, open, high, low, close, volume)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                ("RELIANCE.NS", d, float(p - 5), float(p + 10), float(p - 8), float(p), 1500000),
            )
        conn.commit()

    yield settings


def test_search_breakout_tickers(sample_stock_db):
    settings = sample_stock_db
    matches = search_breakout_tickers("RELI", limit=10, settings=settings)
    assert len(matches) >= 1
    symbols = [m["symbol"] for m in matches]
    assert "RELIANCE.NS" in symbols
    rel = [m for m in matches if m["symbol"] == "RELIANCE.NS"][0]
    assert rel["market"] == "NSE"
    assert "Reliance" in rel["name"]


def test_evaluate_stock_breakout_calculation(sample_stock_db):
    settings = sample_stock_db
    res = evaluate_stock_breakout("RELIANCE.NS", settings=settings)

    assert res["success"] is True
    assert res["ticker"] == "RELIANCE.NS"
    assert res["composite_score"] >= 0
    assert "resistance_score" in res
    assert "volume_score" in res
    assert "compression_score" in res
    assert "momentum_score" in res
    assert "fundamental_score" in res
    assert res["breakout_trigger"] > 0
    assert res["target_price"] > res["breakout_trigger"]
    assert res["stop_loss"] < res["current_price"]
    assert res["tier"] in ("HOT", "WARM", "COLD")


def test_evaluate_stock_breakout_api_endpoint(sample_stock_db):
    client = TestClient(app)

    # 1. Test Autocomplete Search API
    s_res = client.get("/api/v1/breakout-radar/search?q=RELI")
    assert s_res.status_code == 200
    s_data = s_res.json()
    assert s_data["success"] is True
    assert any(m["symbol"] == "RELIANCE.NS" for m in s_data["matches"])

    # 2. Test On-Demand Evaluation API
    e_res = client.get("/api/v1/breakout-radar/evaluate/RELIANCE")
    assert e_res.status_code == 200
    e_data = e_res.json()
    assert e_data["success"] is True
    assert e_data["ticker"] == "RELIANCE.NS"
    assert e_data["breakout_trigger"] > 0
    assert e_data["target_price"] > 0


def test_reevaluate_preserves_original_signal_and_position(sample_stock_db):
    """Test that re-evaluating an existing stock NEVER overrides original signal_price/signal_date."""
    settings = sample_stock_db
    conn = get_db_connection(settings)

    # 1. Manually insert an initial detected position at 2500.0 on 2026-08-15
    with conn:
        conn.execute("DELETE FROM breakout_radar WHERE ticker = 'RELIANCE.NS'")
        conn.execute(
            """
            INSERT INTO breakout_radar (
                ticker, strategy, tier, company_name, composite_score,
                signal_date, signal_price, predicted_value, breakout_trigger, target_price,
                stop_loss, current_price, current_date, realized_return_pct, max_gain_pct,
                outcome, scanned_at, created_at, updated_at
            ) VALUES (
                'RELIANCE.NS', 'CLASSIC_TECHNICAL', 'HOT', 'Reliance Industries Ltd', 85.0,
                '2026-08-15', 2500.0, 2500.0, 2550.0, 2750.0,
                2400.0, 2500.0, '2026-08-15', 0.0, 0.0,
                'ACTIVE', '2026-08-15T10:00:00Z', '2026-08-15T10:00:00Z', '2026-08-15T10:00:00Z'
            )
            """
        )
        conn.commit()

    # 2. Call evaluate_stock_breakout (which runs against latest price history ~2750.0)
    reeval_res = evaluate_stock_breakout("RELIANCE.NS", strategy="CLASSIC_TECHNICAL", settings=settings)

    assert reeval_res["success"] is True
    # Anchor attributes MUST be preserved
    assert reeval_res["signal_date"] == "2026-08-15"
    assert reeval_res["signal_price"] == 2500.0
    assert reeval_res["breakout_trigger"] == 2550.0
    assert reeval_res["target_price"] == 2750.0
    assert reeval_res["stop_loss"] == 2400.0

    # Current market price and P&L MUST be updated relative to the original position (2500.0)
    assert reeval_res["current_price"] == 2750.0
    assert reeval_res["realized_return_pct"] == round(((2750.0 - 2500.0) / 2500.0) * 100, 2)  # +10.0%
    assert reeval_res["outcome"] == "TARGET_HIT"  # 2750 >= target 2750

    # 3. Verify in database that breakout_radar still preserves the original signal_price
    db_row = conn.execute("SELECT signal_date, signal_price, current_price, realized_return_pct, outcome FROM breakout_radar WHERE ticker = 'RELIANCE.NS'").fetchone()
    assert db_row is not None
    assert db_row[0] == "2026-08-15"
    assert db_row[1] == 2500.0
    assert db_row[2] == 2750.0
    assert db_row[3] == 10.0
    assert db_row[4] == "TARGET_HIT"

