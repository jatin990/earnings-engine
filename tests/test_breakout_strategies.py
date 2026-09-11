"""Unit and integration tests for Multi-Strategy Breakout Radar models.

Tests all 5 strategy scoring engines:
- CLASSIC_TECHNICAL
- NSE_DELIVERY_ABSORPTION
- NSE_FO_CALL_WALL
- VOLUME_PROFILE_VAH
- DONCHIAN_TTM_SQUEEZE
"""

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from earnings_engine.api.server import app
from earnings_engine.config import Settings
from earnings_engine.data.breakout_scanner import (
    BREAKOUT_STRATEGIES,
    get_breakout_strategies,
    score_breakout,
    _calculate_volume_profile,
    _calculate_donchian_ttm_squeeze,
)


@pytest.fixture
def sample_prices_df():
    """Create 90 days of synthetic OHLCV bars for testing."""
    dates = pd.date_range(end="2026-08-28", periods=90, freq="B")
    base_price = 1000.0
    
    # Uptrending price action with compression near the high
    prices = [base_price * (1 + 0.002 * i + 0.005 * np.sin(i / 5)) for i in range(90)]
    
    df = pd.DataFrame(
        {
            "open": [p * 0.995 for p in prices],
            "high": [p * 1.015 for p in prices],
            "low": [p * 0.985 for p in prices],
            "close": prices,
            "volume": [1_000_000 + 50_000 * (i % 10) for i in range(90)],
        },
        index=dates,
    )
    return df


def test_strategy_registry():
    """Verify strategy registry exposes all 5 required strategies with complete metadata."""
    strategies = get_breakout_strategies()
    assert len(strategies) == 5
    
    strat_ids = [s["id"] for s in strategies]
    assert "CLASSIC_TECHNICAL" in strat_ids
    assert "NSE_DELIVERY_ABSORPTION" in strat_ids
    assert "NSE_FO_CALL_WALL" in strat_ids
    assert "VOLUME_PROFILE_VAH" in strat_ids
    assert "DONCHIAN_TTM_SQUEEZE" in strat_ids
    
    for s in strategies:
        assert "name" in s
        assert "icon" in s
        assert "description" in s
        assert "formula" in s
        assert "weights" in s
        assert "trigger_name" in s


def test_calculate_volume_profile(sample_prices_df):
    """Test 63-day Point of Control (POC) and Value Area High (VAH) computation."""
    poc_price, vah_price, val_price, vah_vol_ratio = _calculate_volume_profile(sample_prices_df, num_bins=20)
    assert poc_price > 0
    assert vah_price > 0
    assert val_price > 0
    assert vah_price >= val_price
    assert vah_vol_ratio >= 0


def test_calculate_donchian_ttm_squeeze(sample_prices_df):
    """Test Bollinger inside Keltner Channels squeeze detection and 55D Donchian high."""
    closes = sample_prices_df["close"]
    highs = sample_prices_df["high"]
    lows = sample_prices_df["low"]
    
    is_ttm_squeeze, donchian_high_55, bb_width_pct, kc_width_pct, momentum_slope = _calculate_donchian_ttm_squeeze(closes, highs, lows)
    assert isinstance(is_ttm_squeeze, (bool, np.bool_))
    assert donchian_high_55 >= float(closes.iloc[-1])
    assert bb_width_pct >= 0
    assert kc_width_pct >= 0


def test_score_classic_technical(sample_prices_df):
    """Test Classic Technical Coiling scoring algorithm via score_breakout."""
    res = score_breakout("RELIANCE.NS", sample_prices_df, quality_scores=[7.0, 8.0, 7.5], strategy="CLASSIC_TECHNICAL")
    assert res is not None
    assert res["strategy"] == "CLASSIC_TECHNICAL"
    assert 0 <= res["composite_score"] <= 100
    assert res["breakout_trigger"] > 0
    assert res["target_price"] > res["breakout_trigger"]
    assert res["stop_loss"] < res["signal_price"]
    assert "resistance_score" in res
    assert "volume_score" in res


def test_score_nse_delivery_absorption(sample_prices_df):
    """Test NSE Institutional Delivery Absorption scoring algorithm via score_breakout."""
    settings = Settings()
    res = score_breakout("TCS.NS", sample_prices_df, strategy="NSE_DELIVERY_ABSORPTION", settings=settings)
    assert res is not None
    assert res["strategy"] == "NSE_DELIVERY_ABSORPTION"
    assert 0 <= res["composite_score"] <= 100
    assert res["breakout_trigger"] > 0
    assert "institutional_flow" in res
    assert "calculation_notes" in res
    assert res["calculation_notes"]["strategy_id"] == "NSE_DELIVERY_ABSORPTION"


def test_score_fo_call_wall(sample_prices_df):
    """Test NSE F&O Call Open Interest Wall breakout scoring algorithm via score_breakout."""
    settings = Settings()
    res = score_breakout("INFY.NS", sample_prices_df, strategy="NSE_FO_CALL_WALL", settings=settings)
    assert res is not None
    assert res["strategy"] == "NSE_FO_CALL_WALL"
    assert 0 <= res["composite_score"] <= 100
    assert res["breakout_trigger"] > 0
    assert "calculation_notes" in res
    assert res["calculation_notes"]["strategy_id"] == "NSE_FO_CALL_WALL"

    # Non-F&O cash equity must be immediately rejected with None / cold
    res_non_fno = score_breakout("SOUTHWEST.NS", sample_prices_df, strategy="NSE_FO_CALL_WALL", settings=settings)
    assert res_non_fno is None


def test_score_volume_profile_vah(sample_prices_df):
    """Test Volume Profile VAH & POC compression scoring algorithm via score_breakout."""
    res = score_breakout("TATAMOTORS.NS", sample_prices_df, strategy="VOLUME_PROFILE_VAH")
    assert res is not None
    assert res["strategy"] == "VOLUME_PROFILE_VAH"
    assert 0 <= res["composite_score"] <= 100
    assert res["breakout_trigger"] > 0
    assert "calculation_notes" in res
    assert res["calculation_notes"]["strategy_id"] == "VOLUME_PROFILE_VAH"


def test_score_donchian_squeeze(sample_prices_df):
    """Test Donchian 55D + TTM Squeeze scoring algorithm via score_breakout."""
    res = score_breakout("HDFCBANK.NS", sample_prices_df, strategy="DONCHIAN_TTM_SQUEEZE")
    assert res is not None
    assert res["strategy"] == "DONCHIAN_TTM_SQUEEZE"
    assert 0 <= res["composite_score"] <= 100
    assert res["breakout_trigger"] > 0
    assert "calculation_notes" in res
    assert res["calculation_notes"]["strategy_id"] == "DONCHIAN_TTM_SQUEEZE"


def test_score_breakout_dynamic_routing(sample_prices_df):
    """Test score_breakout function routes across all 5 strategies correctly."""
    for strat in (
        "CLASSIC_TECHNICAL",
        "NSE_DELIVERY_ABSORPTION",
        "NSE_FO_CALL_WALL",
        "VOLUME_PROFILE_VAH",
        "DONCHIAN_TTM_SQUEEZE",
    ):
        res = score_breakout("SBIN.NS", sample_prices_df, strategy=strat)
        assert res is not None
        assert res["strategy"] == strat
        assert res["strategy_name"] == BREAKOUT_STRATEGIES[strat]["name"]
        assert 0 <= res["composite_score"] <= 100
        assert res["breakout_trigger"] > 0


def test_api_strategies_endpoint():
    """Test GET /api/v1/breakout-radar/strategies API endpoint."""
    client = TestClient(app)
    
    resp = client.get("/api/v1/breakout-radar/strategies")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["count"] == 5
    assert len(data["strategies"]) == 5
    
    ids = [s["id"] for s in data["strategies"]]
    assert "CLASSIC_TECHNICAL" in ids
    assert "NSE_DELIVERY_ABSORPTION" in ids
    assert "NSE_FO_CALL_WALL" in ids
    assert "VOLUME_PROFILE_VAH" in ids
    assert "DONCHIAN_TTM_SQUEEZE" in ids


def test_api_breakout_radar_strategy_param():
    """Test GET /api/v1/breakout-radar with strategy query parameter."""
    client = TestClient(app)
    
    resp = client.get("/api/v1/breakout-radar?strategy=VOLUME_PROFILE_VAH&limit=5")
    assert resp.status_code == 200
    data = resp.json()
    assert "candidates" in data


def test_trigger_price_is_strictly_above_signal_price(sample_prices_df):
    """Verify that all 5 breakout strategies establish an overhead breakout_trigger above signal_price."""
    for strat in (
        "CLASSIC_TECHNICAL",
        "NSE_DELIVERY_ABSORPTION",
        "NSE_FO_CALL_WALL",
        "VOLUME_PROFILE_VAH",
        "DONCHIAN_TTM_SQUEEZE",
    ):
        res = score_breakout("INFY.NS", sample_prices_df, strategy=strat)
        assert res is not None
        assert res["breakout_trigger"] > res["signal_price"], (
            f"Strategy {strat} produced trigger {res['breakout_trigger']} <= signal_price {res['signal_price']}"
        )
        assert res["target_price"] > res["breakout_trigger"], (
            f"Strategy {strat} produced target {res['target_price']} <= trigger {res['breakout_trigger']}"
        )
        assert res["stop_loss"] < res["signal_price"], (
            f"Strategy {strat} produced SL {res['stop_loss']} >= signal_price {res['signal_price']}"
        )
        # Ensure minimum 1.5 Risk-Reward Ratio
        assert res["risk_reward_ratio"] >= 1.5


def test_confirm_breakout_outcomes():
    """Test confirm_breakout_outcomes execution."""
    from earnings_engine.data.breakout_scanner import confirm_breakout_outcomes
    settings = Settings()
    res = confirm_breakout_outcomes(settings=settings)
    assert res is not None
    assert res["success"] is True
    assert "audited_count" in res
    assert "resolved_count" in res


def test_breakout_backtest_engine(sample_prices_df, monkeypatch):
    """Test walk-forward breakout backtesting engine."""
    from earnings_engine.backtest.breakout_backtest import (
        BreakoutBacktestConfig,
        run_breakout_backtest,
    )
    import earnings_engine.backtest.breakout_backtest as bb_mod

    # Patch load_prices to return sample dataframe
    monkeypatch.setattr(bb_mod, "load_prices", lambda sym, s: sample_prices_df)

    cfg = BreakoutBacktestConfig(
        strategy="CLASSIC_TECHNICAL",
        universe="nifty_50",
        min_score=30.0,
        lookback_days=60,
    )
    result = run_breakout_backtest(config=cfg, tickers=["INFY.NS", "TCS.NS"])
    assert result is not None
    assert result.strategy == "CLASSIC_TECHNICAL"
    assert "total_return_pct" in result.to_dict()
    assert isinstance(result.trades, list)

