"""Unit tests for Options Chart Intelligence Engine: VWAP, ORB, Order Blocks, FVGs, Trendlines & Tactical Signals."""

from __future__ import annotations

import pandas as pd
import pytest
from earnings_engine.data import options_chart_engine as oce


def _sample_intraday_df() -> pd.DataFrame:
    """Generate realistic 5-minute candle dataframe for testing."""
    timestamps = pd.date_range("2026-10-01 09:15", "2026-10-01 15:30", freq="5min")
    records = []
    base_price = 25000.0

    for i, ts in enumerate(timestamps):
        # Create an upward trend with an impulse move around bar 10 and pullback around bar 20
        drift = i * 4.0
        if 8 <= i <= 12:
            drift += 30.0  # Impulse bullish move
        elif 18 <= i <= 22:
            drift -= 15.0  # Pullback

        o = base_price + drift
        h = o + 15.0
        l = o - 10.0
        c = o + 5.0
        v = 50000 + (i * 1000)
        records.append({"timestamp": ts, "open": o, "high": h, "low": l, "close": c, "volume": v})

    df = pd.DataFrame(records)
    df.set_index("timestamp", inplace=True)
    return df


def test_calculate_session_vwap():
    df = _sample_intraday_df()
    vwap_data, upper_band, lower_band = oce._calculate_session_vwap(df)

    assert len(vwap_data) == len(df)
    assert len(upper_band) == len(df)
    assert len(lower_band) == len(df)

    # First candle typical price should equal first VWAP
    first_tp = (df.iloc[0]["high"] + df.iloc[0]["low"] + df.iloc[0]["close"]) / 3.0
    assert abs(vwap_data[0]["value"] - first_tp) < 1e-2

    # Upper band must be strictly greater than VWAP, lower band strictly less (when std > 0)
    assert upper_band[-1]["value"] >= vwap_data[-1]["value"]
    assert lower_band[-1]["value"] <= vwap_data[-1]["value"]


def test_calculate_orb():
    df = _sample_intraday_df()
    orb = oce._calculate_orb(df)

    assert orb["active"] is True
    assert orb["high"] > 0
    assert orb["low"] > 0
    assert orb["high"] >= orb["low"]
    assert orb["range"] == orb["high"] - orb["low"]
    assert orb["target_1"] > orb["high"]
    assert orb["target_2"] > orb["target_1"]


def test_detect_order_blocks_and_fvg():
    df = _sample_intraday_df()
    obs, fvgs = oce._detect_order_blocks_and_fvg(df)

    assert isinstance(obs, list)
    assert isinstance(fvgs, list)

    for ob in obs:
        assert ob["type"] in ["BULLISH_OB", "BEARISH_OB"]
        assert ob["top"] >= ob["bottom"]
        assert "start_time" in ob
        assert "mitigated" in ob

    for fvg in fvgs:
        assert fvg["type"] in ["BULLISH_FVG", "BEARISH_FVG"]
        assert fvg["top"] >= fvg["bottom"]


def test_detect_trendlines():
    df = _sample_intraday_df()
    trendlines = oce._detect_trendlines(df)

    assert isinstance(trendlines, list)
    for tl in trendlines:
        assert tl["type"] in ["SUPPORT", "RESISTANCE"]
        assert "p1" in tl and "p2" in tl
        assert "slope" in tl


def test_generate_tactical_signals():
    df = _sample_intraday_df()
    current_price = float(df["close"].iloc[-1])
    derivatives_levels = {
        "max_pain": 25050.0,
        "call_wall": 25200.0,
        "call_wall_oi": 12000000,
        "put_wall": 24900.0,
        "put_wall_oi": 14000000,
        "pcr_oi": 1.15,
        "sentiment": "BULLISH",
    }
    orb = oce._calculate_orb(df)
    obs, fvgs = oce._detect_order_blocks_and_fvg(df)

    signals = oce._generate_tactical_signals(
        df=df,
        current_price=current_price,
        derivatives_levels=derivatives_levels,
        orb=orb,
        order_blocks=obs,
        fvg_gaps=fvgs,
    )

    assert "primary_bias" in signals
    assert "regime" in signals
    assert "confidence_score" in signals
    assert "where_to_buy" in signals
    assert "where_to_sell" in signals

    buy_plan = signals["where_to_buy"]
    assert buy_plan["entry_low"] <= buy_plan["entry_high"]
    assert buy_plan["stop_loss"] < buy_plan["entry_low"]
    assert buy_plan["target_1"] > buy_plan["entry_high"]
    assert "risk_reward" in buy_plan

    sell_plan = signals["where_to_sell"]
    assert sell_plan["entry_low"] <= sell_plan["entry_high"]
    assert sell_plan["stop_loss"] > sell_plan["entry_high"]
    assert sell_plan["target_1"] < sell_plan["entry_low"]
    assert "risk_reward" in sell_plan


def test_non_fno_symbol_handling():
    res = oce.get_options_chart_intelligence(symbol="UNSUPPORTED_NON_FNO_EQUITY_ABC")
    assert res["status"] == "NOT_FNO"
    assert res["candles"] == []
