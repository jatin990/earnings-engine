"""Unit tests for Institutional Option Writing Velocity and Multi-Timeframe OI."""

import pytest
from earnings_engine.data.options_writing_velocity import (
    derive_multi_timeframe_oi,
    track_oi_snapshot,
    _classify_writing_sentiment,
    _fmt_indian_qty,
    _OI_SNAPSHOT_CACHE,
)


def test_fmt_indian_qty():
    assert _fmt_indian_qty(15000000) == "+1.50 Cr"
    assert _fmt_indian_qty(-250000) == "-2.50 L"
    assert _fmt_indian_qty(45000) == "+45.0 k"
    assert _fmt_indian_qty(500) == "+500"
    assert _fmt_indian_qty(0) == "0"


def test_classify_writing_sentiment():
    # Put Writing Dominance (Bullish)
    sent, badge, theme = _classify_writing_sentiment(call_delta=10000, put_delta=50000)
    assert sent == "PUT WRITING"
    assert "PUT WRITING" in badge
    assert theme == "emerald"

    # Call Writing Dominance (Bearish)
    sent, badge, theme = _classify_writing_sentiment(call_delta=50000, put_delta=10000)
    assert sent == "CALL WRITING"
    assert "CALL WRITING" in badge
    assert theme == "rose"

    # Both unwinding (Short covering)
    sent, badge, theme = _classify_writing_sentiment(call_delta=-50000, put_delta=-10000)
    assert sent == "SHORT COVERING"


def test_derive_multi_timeframe_oi_two_bars_and_15m():
    symbol = "TESTNIFTY"
    _OI_SNAPSHOT_CACHE.pop(symbol, None)

    strikes = [
        {"strike": 24000.0, "ce_oi": 100000, "pe_oi": 250000, "ce_change_oi": 5000, "pe_change_oi": 30000},
        {"strike": 24100.0, "ce_oi": 150000, "pe_oi": 120000, "ce_change_oi": 12000, "pe_change_oi": 8000},
    ]
    current_call_oi = 250000
    current_put_oi = 370000

    metrics = derive_multi_timeframe_oi(symbol, current_call_oi, current_put_oi, strikes)

    # 1. Total Positions (Two Bars)
    total_pos = metrics.get("total_positions", {})
    assert total_pos["call_oi"] == 250000
    assert total_pos["put_oi"] == 370000
    tot = 250000 + 370000
    assert total_pos["call_pct"] == round((250000 / tot) * 100, 1)
    assert total_pos["put_pct"] == round((370000 / tot) * 100, 1)
    assert "2.50 L" in total_pos["call_oi_formatted"]
    assert "3.70 L" in total_pos["put_oi_formatted"]

    # 2. Today full session metrics
    today = metrics.get("today", {})
    assert today["call_chg"] == 17000
    assert today["put_chg"] == 38000
    assert today["sentiment"] == "PUT WRITING"

    # 3. 15-Minute velocity metrics
    tf_15m = metrics.get("tf_15m", {})
    assert "call_chg" in tf_15m
    assert "put_chg" in tf_15m
    assert "call_pct_chg" in tf_15m
    assert "put_pct_chg" in tf_15m

    # 4. Strike-level 15m changes
    for s in strikes:
        assert "ce_change_15m" in s
        assert "pe_change_15m" in s

    # 5. Summary alert
    summary = metrics.get("summary_alert", {})
    assert "TESTNIFTY" in summary.get("text", "")
    assert summary.get("bias") in ("BULLISH", "BEARISH", "NEUTRAL")
    assert summary.get("pcr_oi") == round(370000 / 250000, 2)
