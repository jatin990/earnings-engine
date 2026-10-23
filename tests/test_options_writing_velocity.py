"""Unit tests for Institutional Option Writing Velocity and Multi-Timeframe OI."""

import pytest
from earnings_engine.data.options_writing_velocity import (
    derive_multi_timeframe_oi,
    track_oi_snapshot,
    classify_strike_activity,
    derive_4category_flow,
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
    current_call_vol = 1200000
    current_put_vol = 1800000

    metrics = derive_multi_timeframe_oi(
        symbol,
        current_call_oi,
        current_put_oi,
        strikes,
        current_call_vol=current_call_vol,
        current_put_vol=current_put_vol,
    )

    # 1. Total Positions (Two Bars + Traded/Added Metrics)
    total_pos = metrics.get("total_positions", {})
    assert total_pos["call_oi"] == 250000
    assert total_pos["put_oi"] == 370000
    tot = 250000 + 370000
    assert total_pos["call_pct"] == round((250000 / tot) * 100, 1)
    assert total_pos["put_pct"] == round((370000 / tot) * 100, 1)
    assert "2.50 L" in total_pos["call_oi_formatted"]
    assert "3.70 L" in total_pos["put_oi_formatted"]
    assert total_pos["total_traded"] == 3000000
    assert total_pos["total_added"] == (17000 + 38000)
    assert "30.00 L" in total_pos["total_traded_fmt"]
    assert "55.0 k" in total_pos["total_added_fmt"]

    # 2. Today full session metrics
    today = metrics.get("today", {})
    assert today["call_chg"] == 17000
    assert today["put_chg"] == 38000
    assert today["sentiment"] == "PUT WRITING"
    assert today["total_traded"] == 3000000
    assert today["total_added"] == 55000
    assert "30.00 L" in today["total_traded_fmt"]
    assert "55.0 k" in today["total_added_fmt"]

    # 3. 15-Minute velocity metrics
    tf_15m = metrics.get("tf_15m", {})
    assert "call_chg" in tf_15m
    assert "put_chg" in tf_15m
    assert "call_pct_chg" in tf_15m
    assert "put_pct_chg" in tf_15m
    assert "total_traded" in tf_15m
    assert "total_added" in tf_15m
    assert "total_traded_fmt" in tf_15m
    assert "total_added_fmt" in tf_15m

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
        assert "total_traded" in row
        assert "total_added" in row
        assert "total_traded_fmt" in row
        assert "total_added_fmt" in row
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


def test_distinct_deltas_and_no_15m_30m_duplication():
    """Verify that 15m and 30m timeframes never collapse to identical duplicate deltas."""
    symbol = "NODUPNIFTY"
    _OI_SNAPSHOT_CACHE.pop(symbol, None)

    strikes = [
        {"strike": 24000.0, "ce_oi": 100000, "pe_oi": 200000, "ce_change_oi": 15000, "pe_change_oi": 45000},
        {"strike": 24100.0, "ce_oi": 150000, "pe_oi": 150000, "ce_change_oi": 20000, "pe_change_oi": 35000},
    ]
    current_call_oi = 250000
    current_put_oi = 350000

    metrics = derive_multi_timeframe_oi(
        symbol=symbol,
        current_call_oi=current_call_oi,
        current_put_oi=current_put_oi,
        strikes=strikes,
        spot_price=24050.0,
    )

    tf_table = {row["key"]: row for row in metrics["timeframes_table"]}

    # Verify 5m, 15m, 30m, 1h, 4h, today deltas exist
    assert "5m" in tf_table
    assert "15m" in tf_table
    assert "30m" in tf_table
    assert "1h" in tf_table
    assert "4h" in tf_table
    assert "today" in tf_table

    # CRITICAL INVARIANT: 15m and 30m must NOT have identical deltas (eradicating the +58k / +58k bug)
    call_15m = tf_table["15m"]["call_chg"]
    call_30m = tf_table["30m"]["call_chg"]
    put_15m = tf_table["15m"]["put_chg"]
    put_30m = tf_table["30m"]["put_chg"]

    assert call_15m != call_30m, f"Call delta duplicated across 15m and 30m: {call_15m}"
    assert put_15m != put_30m, f"Put delta duplicated across 15m and 30m: {put_15m}"
    assert abs(call_30m) > abs(call_15m), f"30m call delta ({call_30m}) should be larger horizon than 15m ({call_15m})"
    assert abs(put_30m) > abs(put_15m), f"30m put delta ({put_30m}) should be larger horizon than 15m ({put_15m})"


def test_classify_strike_activity_4categories():
    """Verify 4-quadrant classification of additions vs unwinding."""
    # 1. CE: Price Up, OI Up -> Call Buy (Long Buildup)
    res = classify_strike_activity(price_change=12.5, oi_change=5000, option_type="CE")
    assert res["category"] == "CALL_BUY"
    assert res["flow_type"] == "Long Buildup"
    assert res["is_addition"] is True
    assert res["is_unwinding"] is False
    assert res["contracts"] == 5000

    # 2. CE: Price Down, OI Down -> Call Buy (Long Liquidation / Unwinding)
    res = classify_strike_activity(price_change=-8.0, oi_change=-3000, option_type="CE")
    assert res["category"] == "CALL_BUY"
    assert res["flow_type"] == "Long Liquidation"
    assert res["is_addition"] is False
    assert res["is_unwinding"] is True
    assert res["contracts"] == 3000

    # 3. CE: Price Down, OI Up -> Call Sell (Short Buildup / Writing)
    res = classify_strike_activity(price_change=-15.0, oi_change=8000, option_type="CE")
    assert res["category"] == "CALL_SELL"
    assert res["flow_type"] == "Short Buildup (Writing)"
    assert res["is_addition"] is True
    assert res["is_unwinding"] is False
    assert res["contracts"] == 8000

    # 4. CE: Price Up, OI Down -> Call Sell (Short Covering / Unwinding)
    res = classify_strike_activity(price_change=20.0, oi_change=-4000, option_type="CE")
    assert res["category"] == "CALL_SELL"
    assert res["flow_type"] == "Short Covering"
    assert res["is_addition"] is False
    assert res["is_unwinding"] is True
    assert res["contracts"] == 4000

    # 5. PE: Price Up, OI Up -> Put Buy (Long Buildup)
    res = classify_strike_activity(price_change=10.0, oi_change=6000, option_type="PE")
    assert res["category"] == "PUT_BUY"
    assert res["flow_type"] == "Long Buildup"
    assert res["is_addition"] is True
    assert res["is_unwinding"] is False
    assert res["contracts"] == 6000

    # 6. PE: Price Down, OI Down -> Put Buy (Long Liquidation / Unwinding)
    res = classify_strike_activity(price_change=-5.0, oi_change=-2500, option_type="PE")
    assert res["category"] == "PUT_BUY"
    assert res["flow_type"] == "Long Liquidation"
    assert res["is_addition"] is False
    assert res["is_unwinding"] is True
    assert res["contracts"] == 2500

    # 7. PE: Price Down, OI Up -> Put Sell (Short Buildup / Writing)
    res = classify_strike_activity(price_change=-12.0, oi_change=10000, option_type="PE")
    assert res["category"] == "PUT_SELL"
    assert res["flow_type"] == "Short Buildup (Writing)"
    assert res["is_addition"] is True
    assert res["is_unwinding"] is False
    assert res["contracts"] == 10000

    # 8. PE: Price Up, OI Down -> Put Sell (Short Covering / Unwinding)
    res = classify_strike_activity(price_change=18.0, oi_change=-3500, option_type="PE")
    assert res["category"] == "PUT_SELL"
    assert res["flow_type"] == "Short Covering"
    assert res["is_addition"] is False
    assert res["is_unwinding"] is True
    assert res["contracts"] == 3500


def test_derive_4category_flow_aggregation():
    """Verify aggregated 4-category flow breakdown with additions and liquidations."""
    strikes = [
        # Call Buy (Long Buildup: Price +10, OI +10000)
        {"strike": 24000.0, "ce_pchange_oi": 10.0, "ce_change_oi": 10000, "pe_pchange_oi": -5.0, "pe_change_oi": 20000},
        # Call Sell (Short Buildup: Price -8, OI +15000), Put Buy (Long Buildup: Price +12, OI +8000)
        {"strike": 24100.0, "ce_pchange_oi": -8.0, "ce_change_oi": 15000, "pe_pchange_oi": 12.0, "pe_change_oi": 8000},
        # Call Buy Unwinding (Price -5, OI -4000), Put Sell Unwinding (Price +15, OI -6000)
        {"strike": 24200.0, "ce_pchange_oi": -5.0, "ce_change_oi": -4000, "pe_pchange_oi": 15.0, "pe_change_oi": -6000},
    ]

    flow = derive_4category_flow(strikes)
    assert "call_buy" in flow
    assert "call_sell" in flow
    assert "put_buy" in flow
    assert "put_sell" in flow

    cb = flow["call_buy"]
    assert cb["added"] == 10000
    assert cb["unwound"] == 4000
    assert cb["total"] == 14000
    assert "14.0 k" in cb["total_fmt"]

    cs = flow["call_sell"]
    assert cs["added"] == 15000
    assert cs["unwound"] == 0
    assert cs["total"] == 15000

    pb = flow["put_buy"]
    assert pb["added"] == 8000
    assert pb["unwound"] == 0
    assert pb["total"] == 8000

    ps = flow["put_sell"]
    assert ps["added"] == 20000
    assert ps["unwound"] == 6000
    assert ps["total"] == 26000

    tot = 14000 + 15000 + 8000 + 26000
    assert flow["total_contracts"] == tot
    assert cb["pct"] == round((14000 / tot) * 100, 1)



