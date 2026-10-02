"""Unit tests for Quantitative Commodities Chart & Smart Money Analytics Engine."""

from __future__ import annotations

import pandas as pd
import numpy as np
import pytest
from datetime import datetime, timedelta

from earnings_engine.data.commodities_chart_engine import (
    get_supported_commodity_symbols,
    resolve_commodity_symbol,
    get_commodity_chart_intelligence,
    _calculate_session_vwap,
    _calculate_orb,
    _detect_order_blocks_and_fvg,
    _detect_trendlines,
    _calculate_classical_pivots,
    _generate_tactical_signals,
    _calculate_gsr,
)


def _make_dummy_intraday_df(rows: int = 75, base_price: float = 78000.0) -> pd.DataFrame:
    """Generate mock 5m candlestick data for testing calculations."""
    times = [datetime(2026, 10, 1, 9, 15) + timedelta(minutes=5 * i) for i in range(rows)]
    np.random.seed(42)
    closes = [base_price]
    for _ in range(rows - 1):
        delta = np.random.normal(0, 15)
        closes.append(closes[-1] + delta)

    df = pd.DataFrame({
        "open": [c - np.random.uniform(0, 10) for c in closes],
        "high": [c + np.random.uniform(5, 20) for c in closes],
        "low": [c - np.random.uniform(5, 20) for c in closes],
        "close": closes,
        "volume": [int(v) for v in np.random.uniform(100, 1000, rows)],
    }, index=pd.DatetimeIndex(times))
    return df


def test_supported_commodities_list():
    syms = get_supported_commodity_symbols()
    assert len(syms) >= 5
    ids = [s["symbol"] for s in syms]
    assert "GOLD" in ids
    assert "SILVER" in ids
    assert "CRUDEOIL" in ids
    assert "NATGAS" in ids
    assert "COPPER" in ids


def test_resolve_commodity_symbol():
    assert resolve_commodity_symbol("GOLD") == "GOLDBEES.NS"
    assert resolve_commodity_symbol("SILVER") == "SILVERBEES.NS"
    assert resolve_commodity_symbol("GC=F") == "GC=F"
    assert resolve_commodity_symbol("GOLDBEES.NS") == "GOLDBEES.NS"


def test_calculate_session_vwap():
    df = _make_dummy_intraday_df(50, 78000.0)
    vwap, upper, lower = _calculate_session_vwap(df)
    assert len(vwap) == len(df)
    assert len(upper) == len(df)
    assert len(lower) == len(df)
    assert vwap[-1]["value"] > 0
    assert upper[-1]["value"] >= vwap[-1]["value"]
    assert lower[-1]["value"] <= vwap[-1]["value"]


def test_calculate_orb():
    df = _make_dummy_intraday_df(50, 78000.0)
    orb = _calculate_orb(df)
    assert "active" in orb
    assert orb["high"] > 0
    assert orb["low"] > 0
    assert orb["high"] >= orb["low"]
    assert orb["target_long_1"] > orb["high"]
    assert orb["target_short_1"] < orb["low"]


def test_detect_order_blocks_and_fvg():
    df = _make_dummy_intraday_df(60, 78000.0)
    obs, fvgs = _detect_order_blocks_and_fvg(df)
    assert isinstance(obs, list)
    assert isinstance(fvgs, list)
    if obs:
        ob = obs[0]
        assert "type" in ob
        assert "top" in ob
        assert "bottom" in ob
        assert ob["short_label"] in ("D-OB", "S-OB")


def test_detect_trendlines():
    df = _make_dummy_intraday_df(60, 78000.0)
    tls = _detect_trendlines(df)
    assert isinstance(tls, list)


def test_calculate_classical_pivots():
    df = _make_dummy_intraday_df(50, 78000.0)
    pivots = _calculate_classical_pivots(df)
    assert pivots["p"] > 0
    assert pivots["r1"] >= pivots["p"]
    assert pivots["s1"] <= pivots["p"]


def test_generate_tactical_signals():
    df = _make_dummy_intraday_df(50, 78000.0)
    pivots = _calculate_classical_pivots(df)
    orb = _calculate_orb(df)
    signals = _generate_tactical_signals(df, pivots, orb, "GOLD")

    assert "regime" in signals
    assert "where_to_buy" in signals
    assert "where_to_sell" in signals
    buy = signals["where_to_buy"]
    sell = signals["where_to_sell"]
    assert buy["entry_zone"] != ""
    assert buy["stop_loss"] > 0
    assert buy["target_1"] > buy["stop_loss"]
    assert sell["entry_zone"] != ""
    assert sell["stop_loss"] > 0


def test_calculate_gsr():
    gsr = _calculate_gsr(78000.0, 920.0)
    assert gsr > 0
    assert round(gsr, 1) == round(78000.0 / 920.0, 1)


def test_get_commodity_chart_intelligence_structure():
    data = get_commodity_chart_intelligence("GOLD", interval="5m", period="5d")
    assert data["success"] is True
    assert data["symbol"] == "GOLD"
    assert "candles" in data
    assert "indicators" in data
    assert "tactical_hud" in data
