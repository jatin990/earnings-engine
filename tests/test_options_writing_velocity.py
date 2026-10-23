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

    # 6. Expanded Multi-Timeframe Table (6 Core + 3 Extended Macro)
    tf_table = metrics.get("timeframes_table", [])
    assert len(tf_table) == 9
    timeframe_keys = [row["key"] for row in tf_table]
    assert timeframe_keys == ["5m", "15m", "30m", "1h", "4h", "today", "1w", "1mo", "3mo"]

    # Verify is_extended flags
    for row in tf_table:
        if row["key"] in ("1w", "1mo", "3mo"):
            assert row["is_extended"] is True
        else:
            assert row["is_extended"] is False

    for row in tf_table:
        assert "timeframe" in row
        assert "call_chg" in row
        assert "put_chg" in row
        assert "net_delta" in row
        assert "call_chg_fmt" in row
        assert "put_chg_fmt" in row
        assert "net_delta_fmt" in row
        assert row["bias"] in ("BULLISH", "BEARISH", "NEUTRAL")
        assert len(row["what_is_happening"]) > 10
        assert len(row["what_to_do"]) > 10

    # 7. Confluence Summary
    confluence = metrics.get("confluence_summary", {})
    assert "overall_bias" in confluence
    assert "headline" in confluence
    assert "master_directive" in confluence
    assert confluence["bullish_count"] + confluence["bearish_count"] + confluence["neutral_count"] == 6


def test_derive_timeframe_guidance_diagnostics():
    from earnings_engine.data.options_writing_velocity import _derive_timeframe_guidance

    # 1. 5m Bullish Put Writing
    bias, happening, todo = _derive_timeframe_guidance("5m", "PUT WRITING", 1000, 10000)
    assert bias == "BULLISH"
    assert "Microstructure Put Writing" in happening
    assert "BUY DIPS" in todo

    # 2. 15m Bearish Call Writing
    bias, happening, todo = _derive_timeframe_guidance("15m", "CALL WRITING", 25000, 2000)
    assert bias == "BEARISH"
    assert "Intraday Ceiling Build" in happening
    assert "SHORT BIAS" in todo

    # 3. 1h Short Covering
    bias, happening, todo = _derive_timeframe_guidance("1h", "SHORT COVERING", -30000, -5000)
    assert bias == "BULLISH"
    assert "Short Unwinding" in happening
    assert "SWING LONG" in todo

    # 4. 4h Neutral
    bias, happening, todo = _derive_timeframe_guidance("4h", "BALANCED", 5000, 5200)
    assert bias == "NEUTRAL"
    assert "Macro Indecision" in happening
    assert "HARVEST THETA" in todo

    # 5. 1w Macro Put Writing
    bias, happening, todo = _derive_timeframe_guidance("1w", "PUT WRITING", 10000, 45000)
    assert bias == "BULLISH"
    assert "Structural Weekly Put Writing" in happening
    assert "BUY WEEKLY DIP BASES" in todo

    # 6. 1mo Macro Call Writing
    bias, happening, todo = _derive_timeframe_guidance("1mo", "CALL WRITING", 90000, 20000)
    assert bias == "BEARISH"
    assert "Macro Monthly Supply Overhang" in happening
    assert "DEFENSIVE CYCLE PLAY" in todo

    # 7. 3mo Strategic Squeeze
    bias, happening, todo = _derive_timeframe_guidance("3mo", "SHORT COVERING", -60000, -10000)
    assert bias == "BULLISH"
    assert "Quarterly Capitulation Squeeze" in happening
    assert "LONG-TERM BULLISH TREND" in todo

