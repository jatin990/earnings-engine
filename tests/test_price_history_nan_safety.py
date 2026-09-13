"""Unit tests for price history NaN/Null safety and strict JSON serialization."""

import asyncio
import json
import math
import numpy as np
import pandas as pd
import pytest

from earnings_engine.config import Settings
from earnings_engine.data import prices as prices_mod
from earnings_engine.api.routers.dashboard import get_price_history


@pytest.fixture
def temp_settings(tmp_path):
    """Provide isolated Settings pointing to a temporary SQLite database."""
    s = Settings()
    s.data_dirs = {"prices": tmp_path / "prices", "earnings": tmp_path / "earnings"}
    s.ensure_dirs()
    with prices_mod._connect(s) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS price_history (
                ticker TEXT NOT NULL,
                date TEXT NOT NULL,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume REAL,
                PRIMARY KEY (ticker, date)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tickers (
                ticker TEXT PRIMARY KEY,
                prices_fetched_at TEXT,
                last_updated TEXT
            )
        """)
    return s


def test_write_prices_nan_filtering(temp_settings):
    """Ensure _write_prices discards rows with NaN, None, or non-positive close values."""
    ticker = "TEST_NAN.NS"
    dates = pd.date_range("2026-09-01", periods=6, freq="B")
    df = pd.DataFrame(
        {
            "open": [100.0, 101.0, np.nan, 103.0, 104.0, 105.0],
            "high": [105.0, np.nan, 102.0, 106.0, 107.0, 108.0],
            "low": [95.0, 96.0, 97.0, np.nan, 99.0, 100.0],
            "close": [102.0, np.nan, None, -5.0, 0.0, 106.0],  # Only index 0 and 5 are valid
            "volume": [1000, 2000, 3000, 4000, np.nan, 6000],
        },
        index=dates,
    )

    prices_mod._write_prices(ticker, temp_settings, df)

    with prices_mod._connect(temp_settings) as conn:
        rows = conn.execute("SELECT date, open, high, low, close, volume FROM price_history WHERE ticker = ? ORDER BY date", (ticker,)).fetchall()

    assert len(rows) == 2
    assert rows[0][0] == "2026-09-01"
    assert rows[0][4] == 102.0
    assert rows[1][0] == "2026-09-08"
    assert rows[1][4] == 106.0


def test_merge_prices_nan_filtering(temp_settings):
    """Ensure _merge_prices upserts only valid rows and rejects NaN/negative close values."""
    ticker = "TEST_MERGE.NS"
    dates = pd.date_range("2026-09-01", periods=4, freq="B")
    df = pd.DataFrame(
        {
            "open": [100.0, 101.0, float("nan"), 103.0],
            "high": [105.0, 106.0, 107.0, 108.0],
            "low": [95.0, 96.0, 97.0, 98.0],
            "close": [102.0, float("nan"), float("inf"), 104.0],
            "volume": [1000, 2000, 3000, 4000],
        },
        index=dates,
    )

    prices_mod._merge_prices(ticker, temp_settings, df)

    with prices_mod._connect(temp_settings) as conn:
        rows = conn.execute("SELECT date, close FROM price_history WHERE ticker = ? ORDER BY date", (ticker,)).fetchall()

    assert len(rows) == 2
    assert rows[0][1] == 102.0
    assert rows[1][1] == 104.0


def test_load_prices_batch_nan_safety(temp_settings):
    """Ensure load_prices_batch never returns NaN close values even if dirty rows existed."""
    ticker = "TEST_BATCH.NS"
    with prices_mod._connect(temp_settings) as conn:
        conn.execute(
            "INSERT INTO price_history (ticker, date, open, high, low, close, volume) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (ticker, "2026-09-01", 100.0, 105.0, 95.0, 102.0, 1000),
        )
        conn.execute(
            "INSERT INTO price_history (ticker, date, open, high, low, close, volume) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (ticker, "2026-09-02", 101.0, 106.0, 96.0, None, 2000),
        )
        conn.execute(
            "INSERT INTO price_history (ticker, date, open, high, low, close, volume) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (ticker, "2026-09-03", 102.0, 107.0, 97.0, 0.0, 3000),
        )
        conn.execute(
            "INSERT INTO price_history (ticker, date, open, high, low, close, volume) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (ticker, "2026-09-04", 103.0, 108.0, 98.0, 105.0, 4000),
        )

    res = prices_mod.load_prices_batch([ticker], temp_settings)
    df = res.get(ticker)
    assert df is not None
    assert len(df) == 2
    assert list(df["close"].values) == [102.0, 105.0]


def test_get_price_history_strict_json_compliance(monkeypatch, temp_settings):
    """Ensure get_price_history returns records that serialize cleanly with allow_nan=False."""
    ticker = "TEST_API_NAN.NS"
    dates = pd.date_range("2026-09-01", periods=5, freq="B")
    df = pd.DataFrame(
        {
            "open": [100.0, np.nan, 102.0, 103.0, 104.0],
            "high": [105.0, 106.0, np.nan, 108.0, 109.0],
            "low": [95.0, 96.0, 97.0, np.nan, 99.0],
            "close": [102.0, 103.0, 104.0, 105.0, 106.0],
            "volume": [1000, np.nan, 3000, 4000, 5000],
        },
        index=dates,
    )

    # Monkeypatch fetch_prices to return our test DataFrame
    monkeypatch.setattr(prices_mod, "fetch_prices", lambda sym, settings, force=False: df)

    records = asyncio.run(get_price_history(ticker))
    assert len(records) == 5

    # Strict JSON compliance test (FastAPI / Starlette standard)
    serialized = json.dumps(records, allow_nan=False)
    assert isinstance(serialized, str)
    assert len(serialized) > 0

    parsed = json.loads(serialized)
    for rec in parsed:
        assert isinstance(rec["open"], (int, float)) and not math.isnan(rec["open"])
        assert isinstance(rec["high"], (int, float)) and not math.isnan(rec["high"])
        assert isinstance(rec["low"], (int, float)) and not math.isnan(rec["low"])
        assert isinstance(rec["close"], (int, float)) and not math.isnan(rec["close"])
        assert isinstance(rec["volume"], int)
