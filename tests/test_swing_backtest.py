"""Unit tests for the swing-channel backtesting engine."""

import numpy as np
import pandas as pd
import pytest

from earnings_engine.backtest.swing_backtest import (
    SwingBacktestConfig,
    SwingTrade,
    compute_channel,
    run_swing_backtest,
)


def test_compute_channel_basic():
    """Verify rolling channel calculations and lack of lookahead bias (1-bar shift)."""
    dates = pd.date_range("2026-01-01", periods=30, freq="D")
    # Monotonically increasing close prices
    closes = np.linspace(100, 130, 30)
    df = pd.DataFrame({"close": closes, "high": closes + 1, "low": closes - 1}, index=dates)

    ch_df = compute_channel(df, lookback=20)
    assert "ch_support" in ch_df.columns
    assert "ch_resistance" in ch_df.columns
    assert "ch_position" in ch_df.columns

    # First 20 bars should be NaN due to 20 lookback + 1 bar shift
    assert pd.isna(ch_df["ch_resistance"].iloc[19])
    assert not pd.isna(ch_df["ch_resistance"].iloc[20])

    # Resistance at index 20 should be max of highs from index 0..19
    expected_res = df["high"].iloc[0:20].max()
    assert ch_df["ch_resistance"].iloc[20] == expected_res


def test_swing_trade_to_dict():
    """Test SwingTrade dictionary serialization."""
    trade = SwingTrade(
        ticker="TATAMOTORS.NS",
        entry_date="2026-01-15",
        entry_price=900.0,
        size=10,
        stop_loss=880.0,
        take_profit=950.0,
        exit_date="2026-01-20",
        exit_price=945.0,
        pnl=450.0,
        pnl_pct=5.0,
        exit_reason="Take Profit",
        hold_days=5,
    )
    d = trade.to_dict()
    assert d["ticker"] == "TATAMOTORS.NS"
    assert d["pnl"] == 450.0
    assert d["exit_reason"] == "Take Profit"


def test_run_swing_backtest_with_mock(monkeypatch):
    """Test full backtest cycle with simulated oscillating stock data."""
    dates = pd.date_range("2026-01-01", periods=60, freq="D")
    
    # 20 bars flat around 100, then dip to 91 (buy zone), then rally to 110 (take profit)
    prices = np.array([100.0] * 20 + [91.0, 92.0, 95.0, 105.0, 112.0] + [100.0] * 35)
    highs = prices + 2.0
    lows = prices - 2.0
    volumes = [10000] * 60
    volumes[20] = 25000  # volume spike on the dip bar

    mock_df = pd.DataFrame(
        {
            "open": prices,
            "high": highs,
            "low": lows,
            "close": prices,
            "volume": volumes,
        },
        index=dates,
    )
    mock_df.index.name = "date"

    def mock_load_prices(ticker, settings):
        return mock_df

    monkeypatch.setattr("earnings_engine.backtest.swing_backtest.load_prices", mock_load_prices)

    cfg = SwingBacktestConfig(
        initial_capital=100000.0,
        risk_per_trade_pct=0.02,
        channel_lookback=20,
        buy_zone_threshold=0.30,
        volume_surge_mult=1.2,
        lookback_months=6,
    )

    result = run_swing_backtest(["MOCK.NS"], cfg=cfg)

    assert result.total_trades >= 1
    assert result.initial_capital == 100000.0
    assert len(result.equity_curve) > 0
    assert isinstance(result.trades, list)
    first_trade = result.trades[0]
    assert first_trade.ticker == "MOCK.NS"
    assert first_trade.pnl != 0.0
