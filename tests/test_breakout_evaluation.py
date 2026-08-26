"""Unit & Integration Tests for On-Demand Breakout Stock Evaluation & Autocomplete Search."""
import pytest
import pandas as pd
import numpy as np
from starlette.testclient import TestClient

from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection
from earnings_engine.data.breakout_scanner import (
    evaluate_stock_breakout,
    search_breakout_tickers,
    score_breakout,
)
from earnings_engine.api.server import app


@pytest.fixture
def sample_stock_db():
    settings = Settings()
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
