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


def test_non_fno_symbol_with_allow_non_fno(monkeypatch):
    sample_df = _sample_intraday_df()
    monkeypatch.setattr(oce, "fetch_chart_candles", lambda *args, **kwargs: sample_df)
    res = oce.get_options_chart_intelligence(symbol="UNSUPPORTED_NON_FNO_EQUITY_XYZ", allow_non_fno=True)
    assert res["success"] is True
    assert res["status"] in ["LIVE", "EOD_SNAPSHOT"]
    assert len(res["candles"]) == len(sample_df)
    assert res["derivatives_levels"] == {}
    assert "vwap" in res["indicators"]
    assert "where_to_buy" in res["tactical_signals"]


def test_timeframe_periods_weekly_and_monthly(monkeypatch):
    """Verify that weekly ('1w') and monthly ('1mo') intervals map to 2y and 5y periods."""
    captured_calls = []

    def mock_fetch(symbol, interval="5m", period="5d", settings=None):
        captured_calls.append({"symbol": symbol, "interval": interval, "period": period})
        return _sample_intraday_df()

    monkeypatch.setattr(oce, "fetch_chart_candles", mock_fetch)

    # 1. Weekly interval test
    oce.get_options_chart_intelligence(symbol="NIFTY", interval="1w", force_refresh=True)
    assert captured_calls[-1]["interval"] == "1w"
    assert captured_calls[-1]["period"] == "2y"

    # 2. Monthly interval test
    oce.get_options_chart_intelligence(symbol="NIFTY", interval="1mo", force_refresh=True)
    assert captured_calls[-1]["interval"] == "1mo"
    assert captured_calls[-1]["period"] == "5y"


def test_decompose_order_flow_and_whales():
    """Verify intrabar order flow decomposition and institutional whale detection."""
    df = _sample_intraday_df()
    flow_candles, summary = oce._decompose_order_flow_and_whales(df)

    assert len(flow_candles) == len(df)
    assert "total_buyer_vol" in summary
    assert "total_seller_vol" in summary
    assert "net_delta" in summary
    assert "whale_count" in summary
    assert "whale_threshold" in summary
    assert summary["dominant_session_side"] in ["BUYERS", "SELLERS", "BALANCED"]

    for candle in flow_candles:
        assert "time" in candle
        assert "open" in candle
        assert "close" in candle
        assert "buyer_vol" in candle
        assert "seller_vol" in candle
        assert "net_delta" in candle
        assert "is_whale" in candle
        assert "whale_tier" in candle
        assert "whale_side" in candle
        assert candle["buyer_vol"] + candle["seller_vol"] == candle["volume"]
        assert candle["net_delta"] == candle["buyer_vol"] - candle["seller_vol"]
        assert "footprint_levels" in candle
        assert len(candle["footprint_levels"]) == 4

        for lvl in candle["footprint_levels"]:
            assert "price" in lvl
            assert "price_low" in lvl
            assert "price_high" in lvl
            assert "buyer_vol" in lvl
            assert "seller_vol" in lvl
            assert "delta" in lvl
            assert "imbalance" in lvl
            assert "is_active_zone" in lvl
            assert lvl["active_type"] in ["NONE", "BIG_BUYER", "BIG_SELLER", "ABSORPTION"]
            assert lvl["buyer_vol"] + lvl["seller_vol"] >= 0
            assert lvl["delta"] == lvl["buyer_vol"] - lvl["seller_vol"]


def test_index_volume_proxy_hydration_mapping():
    """Verify that Indian cash indices have proxy ETF mapping registered."""
    assert "^NSEI" in oce.INDEX_VOLUME_PROXY_MAP
    assert oce.INDEX_VOLUME_PROXY_MAP["^NSEI"] == "NIFTYBEES.NS"
    assert "^NSEBANK" in oce.INDEX_VOLUME_PROXY_MAP
    assert oce.INDEX_VOLUME_PROXY_MAP["^NSEBANK"] == "BANKBEES.NS"
    assert "^BSESN" in oce.INDEX_VOLUME_PROXY_MAP
    assert oce.INDEX_VOLUME_PROXY_MAP["^BSESN"] == "SENSEXBEES.NS"


def test_decompose_options_contracts_flow():
    """Verify options contracts flow decomposition and institutional strike detection."""
    sample_strikes = [
        {
            "strike": 24800.0,
            "ce_vol": 12000,
            "pe_vol": 85000,
            "ce_change_oi": -2000,
            "pe_change_oi": 45000,
            "ce_ltp": 250.0,
            "pe_ltp": 45.0,
        },
        {
            "strike": 25000.0,
            "ce_vol": 120000,
            "pe_vol": 25000,
            "ce_change_oi": 60000,
            "pe_change_oi": -5000,
            "ce_ltp": 120.0,
            "pe_ltp": 115.0,
        },
        {
            "strike": 25200.0,
            "ce_vol": 30000,
            "pe_vol": 8000,
            "ce_change_oi": 15000,
            "pe_change_oi": 1000,
            "ce_ltp": 35.0,
            "pe_ltp": 210.0,
        },
    ]

    flow = oce._decompose_options_contracts_flow(sample_strikes)
    summary = flow["summary"]
    whale_strikes = flow["whale_strikes"]

    # Verify aggregation
    assert summary["call_vol_total"] == 12000 + 120000 + 30000
    assert summary["put_vol_total"] == 85000 + 25000 + 8000
    assert summary["call_added_total"] == -2000 + 60000 + 15000
    assert summary["put_added_total"] == 45000 + -5000 + 1000
    assert summary["net_contract_flow"] == summary["put_added_total"] - summary["call_added_total"]

    # Verify whale strike detection
    assert len(whale_strikes) > 0
    # 25000 CE has 120000 vol & +60000 added contracts -> must be detected
    ce_whales = [w for w in whale_strikes if w["contract_name"] == "25000 CE"]
    assert len(ce_whales) == 1
    assert ce_whales[0]["volume"] == 120000
    assert ce_whales[0]["contracts_added"] == 60000
    assert ce_whales[0]["action"] == "CONTRACTS_ADDED"

    # 24800 PE has 85000 vol & +45000 added contracts -> must be detected
    pe_whales = [w for w in whale_strikes if w["contract_name"] == "24800 PE"]
    assert len(pe_whales) == 1
    assert pe_whales[0]["volume"] == 85000
    assert pe_whales[0]["contracts_added"] == 45000





