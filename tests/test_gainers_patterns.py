"""Tests for Daily Top 10 Gainers, Driver Attribution & Pattern Discovery."""

from __future__ import annotations

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from earnings_engine.api.server import app
from earnings_engine.config import Settings
from earnings_engine.data.gainers_patterns import (
    compute_stock_daily_telemetry,
    attribute_surge_driver,
    get_daily_top_gainers,
    get_pattern_matrix_summary,
    scan_upcoming_breakout_setups,
)


def test_compute_stock_daily_telemetry():
    # Build sample OHLCV DataFrame
    dates = pd.date_range("2026-01-01", periods=30, freq="D")
    df = pd.DataFrame({
        "date": [d.strftime("%Y-%m-%d") for d in dates],
        "open": [100.0] * 29 + [102.0],
        "high": [105.0] * 29 + [114.0],
        "low": [98.0] * 29 + [101.5],
        "close": [100.0] * 29 + [112.5],
        "volume": [1_000_000] * 29 + [4_500_000],
    })

    telem = compute_stock_daily_telemetry("TEST.NS", df)
    assert telem is not None
    assert telem["return_pct"] == 12.5
    assert telem["volume_multiple"] == 4.5
    assert telem["is_52w_high"] == 1
    assert telem["consolidation_range"] <= 6.5


def test_attribute_surge_driver():
    telem = {
        "ticker": "TEST.NS",
        "return_pct": 14.2,
        "volume_multiple": 4.5,
        "is_52w_high": 1,
        "consolidation_range": 4.5,
        "candle_strength": 90.0,
    }
    driver, explanation, archetype = attribute_surge_driver(telem)
    assert driver in ("52W_HIGH_BREAKOUT", "VOLUME_SQUEEZE_EXPLOSION", "INSTITUTIONAL_ACCUMULATION")
    assert archetype in ("BLUE_SKY_52W_HIGH", "SQUEEZE_VOLUME_EXPLOSION")
    assert "Surged" in explanation or "Broke out" in explanation or "Exploded" in explanation


def test_get_pattern_matrix_summary():
    matrix = get_pattern_matrix_summary()
    assert isinstance(matrix, list)
    assert len(matrix) >= 5
    first = matrix[0]
    assert "name" in first
    assert "win_rate_3d" in first
    assert "avg_follow_through_pct" in first
    assert "technical_rules" in first


def test_get_daily_top_gainers_and_setups(tmp_path):
    settings = Settings(data_dirs={"prices": tmp_path, "earnings": tmp_path})
    settings.ensure_dirs()

    gainers = get_daily_top_gainers(universe_or_watchlist="NSE_ALL", top_n=5, settings=settings)
    assert isinstance(gainers, list)
    assert len(gainers) <= 5
    if gainers:
        assert "return_pct" in gainers[0]
        assert "driver_explanation" in gainers[0]
        assert "pattern_name" in gainers[0]

    setups = scan_upcoming_breakout_setups(universe_or_watchlist="NSE_TOP", settings=settings)
    assert isinstance(setups, list)


def test_gainers_api_endpoints():
    client = TestClient(app)

    # 1. Daily top gainers endpoint
    res = client.get("/api/v1/gainers/daily?top_n=5")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert "gainers" in data

    # 2. Pattern matrix endpoint
    res_pat = client.get("/api/v1/gainers/patterns")
    assert res_pat.status_code == 200
    pat_data = res_pat.json()
    assert pat_data["success"] is True
    assert "patterns" in pat_data

    # 3. Upcoming setups endpoint
    res_setups = client.get("/api/v1/gainers/upcoming-setups")
    assert res_setups.status_code == 200
    setup_data = res_setups.json()
    assert setup_data["success"] is True
    assert "setups" in setup_data
