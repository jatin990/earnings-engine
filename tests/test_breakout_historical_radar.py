"""Unit tests for Breakout Radar historical date picker and outcome engine."""
import pandas as pd
import numpy as np
import pytest
from starlette.testclient import TestClient

from earnings_engine.api.server import app
from earnings_engine.data.breakout_scanner import (
    score_breakout,
    _score_resistance_proximity,
    _score_volume_surge,
    _score_price_compression,
    _score_momentum,
    _score_fundamental,
)


@pytest.fixture
def client():
    return TestClient(app)


def test_breakout_subscores():
    """Verify sub-score formulas and boundaries."""
    # 1. Resistance proximity
    closes = pd.Series([100.0, 102.0, 105.0, 104.5, 105.0])
    res_score, pct_high = _score_resistance_proximity(closes)
    assert res_score >= 28.0
    assert pct_high >= -1.0

    # 2. Volume surge
    volumes = pd.Series([1000] * 20 + [2500])
    vol_score, vol_ratio = _score_volume_surge(volumes)
    assert vol_score == 20.0
    assert vol_ratio >= 2.0

    # 3. Compression
    comp_closes = pd.Series([100.0 + i * 0.05 for i in range(20)])
    comp_score, atr_pct = _score_price_compression(comp_closes)
    assert comp_score >= 12.0
    assert atr_pct < 1.0

    # 4. Momentum
    mom_closes = pd.Series([90.0 + i * 0.5 for i in range(35)])
    mom_score, mom_signal = _score_momentum(mom_closes)
    assert mom_score == 15.0
    assert mom_signal == "Strong"

    # 5. Fundamental
    fund_score, avg_q = _score_fundamental([8.0, 9.0, 8.5])
    assert fund_score >= 18.0
    assert avg_q >= 8.0


def test_score_breakout_live_vs_historical():
    """Verify point-in-time scoring and realized outcome evaluation."""
    dates = pd.date_range("2026-01-01", periods=60, freq="B")
    
    # Create price series where stock coils around 100 up to day 30, then breaks out to 115
    prices = [100.0 + np.sin(i / 3) * 2 for i in range(30)] + [102.0 + i * 0.5 for i in range(30)]
    df = pd.DataFrame({
        "open": prices,
        "high": [p + 1.0 for p in prices],
        "low": [p - 1.0 for p in prices],
        "close": prices,
        "volume": [10000] * 60,
    }, index=dates)

    # 1. Live scan (no asof_date)
    res_live = score_breakout("TEST.NS", df, quality_scores=[8.0, 8.0, 8.0])
    assert res_live is not None
    assert res_live["breakout_happened"] is None
    assert res_live["outcome"] == "PENDING"
    assert res_live["current_price"] == round(prices[-1], 2)

    # 2. Historical scan as-of day 30
    asof_date = dates[29].strftime("%Y-%m-%d")
    res_hist = score_breakout("TEST.NS", df, quality_scores=[8.0, 8.0, 8.0], asof_date=asof_date)
    assert res_hist is not None
    assert res_hist["signal_date"] == asof_date
    assert res_hist["signal_price"] == round(prices[29], 2)
    assert res_hist["current_price"] == round(prices[-1], 2)
    assert res_hist["breakout_happened"] is True
    assert res_hist["outcome"] in ("TARGET_HIT", "BREAKOUT_SUCCEEDED")
    assert res_hist["realized_return_pct"] > 0


def test_api_breakout_radar_with_asof_date(client, monkeypatch):
    """Verify /api/v1/breakout-radar endpoint handles asof_date and returns backtest summary."""
    import earnings_engine.data.breakout_scanner as bs_mod

    # Mock return data
    mock_candidate = {
        "ticker": "RELIANCE.NS",
        "company_name": "Reliance Industries",
        "industry": "Oil & Gas",
        "signal_date": "2026-01-15",
        "signal_price": 2400.0,
        "predicted_value": 2400.0,
        "breakout_trigger": 2450.0,
        "target_price": 2646.0,
        "stop_loss": 2280.0,
        "current_price": 2750.0,
        "realized_return_pct": 14.58,
        "max_gain_pct": 16.2,
        "breakout_happened": True,
        "outcome": "TARGET_HIT",
        "outcome_label": "Target Hit 🎯 (+16.2%)",
        "outcome_badge": "emerald",
        "composite_score": 88.5,
        "resistance_score": 28.0,
        "volume_score": 20.0,
        "compression_score": 12.0,
        "momentum_score": 15.0,
        "fundamental_score": 13.5,
    }

    monkeypatch.setattr(bs_mod, "get_cached_scan_results", lambda **kwargs: [mock_candidate])

    resp = client.get("/api/v1/breakout-radar?universe=nifty_50&asof_date=2026-01-15")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["asof_date"] == "2026-01-15"
    assert len(data["candidates"]) == 1
    assert data["candidates"][0]["predicted_value"] == 2400.0
    assert data["candidates"][0]["current_price"] == 2750.0
    assert data["candidates"][0]["breakout_happened"] is True
    assert data["backtest_summary"]["win_rate_pct"] == 100.0
