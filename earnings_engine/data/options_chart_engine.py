"""Quantitative Options & Chart Intelligence Engine.

Computes real-time intraday / swing indicators for F&O equities & indices:
- Session VWAP with dynamic standard deviation bands
- 15-minute Opening Range Breakout (ORB-15) and projected targets
- Smart Money Concepts (SMC): Bullish & Bearish Order Blocks (OB) and Fair Value Gaps (FVG)
- Algorithmic Support / Resistance Trendlines
- Tactical "Where to Buy & Where to Sell" trade confluence plans
"""

from __future__ import annotations

import logging
import math
import time
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf

from earnings_engine.config import Settings
from earnings_engine.data import option_chain as oc_mod
from earnings_engine.data.universe import is_fno_eligible

logger = logging.getLogger("earnings_engine.data.options_chart_engine")

_CHART_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_CHART_CACHE_TTL_SECONDS = 30.0  # 30 seconds cache for rapid polling

INDEX_MAP = {
    "NIFTY": "^NSEI",
    "NIFTY50": "^NSEI",
    "NIFTY 50": "^NSEI",
    "NIFTY_50": "^NSEI",
    "BANKNIFTY": "^NSEBANK",
    "NIFTYBANK": "^NSEBANK",
    "NIFTY BANK": "^NSEBANK",
    "NIFTY_BANK": "^NSEBANK",
    "FINNIFTY": "NIFTY_FIN_SERVICE.NS",
    "NIFTY FINANCIAL SERVICES": "NIFTY_FIN_SERVICE.NS",
    "NIFTY_FIN_SERVICE": "NIFTY_FIN_SERVICE.NS",
    "MIDCPNIFTY": "NIFTY_MID_SELECT.NS",
    "NIFTY MIDCAP SELECT": "NIFTY_MID_SELECT.NS",
    "NIFTY_MID_SELECT": "NIFTY_MID_SELECT.NS",
    "NIFTYNXT50": "^NSEMDCP50",
    "NIFTY NEXT 50": "^NSEMDCP50",
    "NIFTYIT": "^CNXIT",
    "NIFTY IT": "^CNXIT",
    "SENSEX": "^BSESN",
    "BSESENSEX": "^BSESN",
    "BSE:SENSEX": "^BSESN",
    "SENSEX.BO": "^BSESN",
    "BSE SENSEX": "^BSESN",
    "BSE_SENSEX": "^BSESN",
}


def resolve_chart_symbol(symbol: str) -> str:
    """Map user/dashboard symbol to appropriate yfinance ticker."""
    clean = symbol.strip().upper().replace(".NS", "")
    if clean in INDEX_MAP:
        return INDEX_MAP[clean]
    if clean.startswith("^"):
        return clean
    return f"{clean}.NS"


def fetch_chart_candles(
    symbol: str,
    interval: str = "5m",
    period: str = "5d",
    settings: Settings | None = None,
) -> pd.DataFrame:
    """Fetch candlestick price history for chart rendering and quant analytics."""
    clean_sym = symbol.strip().upper().replace(".NS", "")
    yf_symbol = resolve_chart_symbol(clean_sym)

    valid_intervals = {"1m", "3m", "5m", "15m", "30m", "1h", "60m", "4h", "1d", "1D", "1w", "1W"}
    norm_interval = interval.lower() if interval.lower() not in {"1d", "1w"} else interval.lower()
    if norm_interval not in valid_intervals:
        norm_interval = "5m"

    # Default periods based on interval: auto-expand daily/weekly to 6mo/1y
    if norm_interval in {"1d", "d"} and period in {None, "", "5d"}:
        period = "6mo"
    elif norm_interval in {"1w", "w"} and period in {None, "", "5d"}:
        period = "1y"
    elif not period:
        period = "5d"

    try:
        t = yf.Ticker(yf_symbol)
        df = t.history(period=period, interval=norm_interval)
        if df is not None and not df.empty:
            df.columns = [c.lower() for c in df.columns]
            # Normalize column names
            req_cols = ["open", "high", "low", "close", "volume"]
            if all(col in df.columns for col in req_cols):
                df = df[req_cols].dropna()
                # Ensure index is localized datetime
                if not isinstance(df.index, pd.DatetimeIndex):
                    df.index = pd.to_datetime(df.index)
                return df
    except Exception as e:
        logger.debug("[OPTIONS-CHART] yfinance history error for %s (%s): %s", yf_symbol, norm_interval, e)

    # Fallback to local price cache if daily interval requested
    try:
        from earnings_engine.data.prices import load_prices
        settings = settings or Settings()
        fallback_df = load_prices(yf_symbol, settings)
        if fallback_df is not None and not fallback_df.empty:
            return fallback_df.tail(120)
    except Exception:
        pass

    return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])


def _calculate_session_vwap(df: pd.DataFrame) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Compute session-anchored VWAP and ±1.5σ volatility bands."""
    if df.empty:
        return [], [], []

    vwap_res = []
    upper_res = []
    lower_res = []

    # Group by date for intraday session reset
    dates = df.index.normalize()
    unique_dates = dates.unique()

    for d in unique_dates:
        mask = (dates == d)
        session_df = df.loc[mask]
        if session_df.empty:
            continue

        cum_pv = 0.0
        cum_vol = 0.0
        cum_sq_diff = 0.0

        for stamp, row in session_df.iterrows():
            unix_ts = int(stamp.timestamp())
            h, l, c = float(row["high"]), float(row["low"]), float(row["close"])
            v = max(float(row.get("volume", 0)), 1.0)
            tp = (h + l + c) / 3.0

            cum_pv += tp * v
            cum_vol += v
            vwap = cum_pv / cum_vol

            # Approximate variance
            cum_sq_diff += v * ((tp - vwap) ** 2)
            variance = cum_sq_diff / cum_vol
            std_dev = math.sqrt(max(variance, 0.0))

            up_band = vwap + (1.5 * std_dev)
            lo_band = vwap - (1.5 * std_dev)

            vwap_res.append({"time": unix_ts, "value": round(vwap, 2)})
            upper_res.append({"time": unix_ts, "value": round(up_band, 2)})
            lower_res.append({"time": unix_ts, "value": round(lo_band, 2)})

    return vwap_res, upper_res, lower_res


def _calculate_orb(df: pd.DataFrame) -> dict[str, Any]:
    """Calculate 15-minute Opening Range Breakout (ORB) and projected price targets."""
    default_orb = {
        "active": False,
        "time_range": "09:15 - 09:30 IST",
        "high": 0.0,
        "low": 0.0,
        "range": 0.0,
        "status": "INSIDE_RANGE",
        "target_1": 0.0,
        "target_2": 0.0,
        "downside_target_1": 0.0,
        "downside_target_2": 0.0,
    }

    if df.empty or len(df) < 3:
        return default_orb

    # Take today's or the last available day's bars
    last_date = df.index.normalize()[-1]
    today_bars = df.loc[df.index.normalize() == last_date]

    if today_bars.empty:
        return default_orb

    # The opening range is typically the first 3 5m bars (or first 15m)
    orb_window = today_bars.iloc[:3]
    orb_high = float(orb_window["high"].max())
    orb_low = float(orb_window["low"].min())
    orb_range = round(orb_high - orb_low, 2)

    current_close = float(today_bars["close"].iloc[-1])

    if current_close > orb_high:
        status = "BREAKOUT_BULLISH"
    elif current_close < orb_low:
        status = "BREAKDOWN_BEARISH"
    else:
        status = "INSIDE_RANGE"

    return {
        "active": True,
        "time_range": "09:15 - 09:30 IST",
        "high": round(orb_high, 2),
        "low": round(orb_low, 2),
        "range": orb_range,
        "status": status,
        "target_1": round(orb_high + (1.0 * orb_range), 2),
        "target_2": round(orb_high + (2.0 * orb_range), 2),
        "downside_target_1": round(orb_low - (1.0 * orb_range), 2),
        "downside_target_2": round(orb_low - (2.0 * orb_range), 2),
    }


def _detect_order_blocks_and_fvg(df: pd.DataFrame) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Detect Smart Money Order Blocks (OB) and Fair Value Gaps (FVG) with mitigation status."""
    if len(df) < 5:
        return [], []

    order_blocks = []
    fvgs = []

    # 1. Fair Value Gaps (FVG) - 3-candle imbalance pattern
    for i in range(2, len(df)):
        c0 = df.iloc[i - 2]  # Candle 1
        c1 = df.iloc[i - 1]  # Middle impulsive candle
        c2 = df.iloc[i]      # Candle 3
        ts = int(df.index[i].timestamp())

        # Bullish FVG: Low of candle 3 is higher than High of candle 1
        if float(c2["low"]) > float(c0["high"]) and float(c1["close"]) > float(c1["open"]):
            fvg_top = float(c2["low"])
            fvg_bottom = float(c0["high"])
            # Check if mitigated subsequently
            subsequent_lows = df.iloc[i + 1:]["low"]
            filled = bool((subsequent_lows <= fvg_bottom).any()) if not subsequent_lows.empty else False

            fvgs.append({
                "type": "BULLISH_FVG",
                "top": round(fvg_top, 2),
                "bottom": round(fvg_bottom, 2),
                "time": ts,
                "filled": filled,
                "label": "Demand Imbalance (FVG)",
            })

        # Bearish FVG: High of candle 3 is lower than Low of candle 1
        elif float(c2["high"]) < float(c0["low"]) and float(c1["close"]) < float(c1["open"]):
            fvg_top = float(c0["low"])
            fvg_bottom = float(c2["high"])
            subsequent_highs = df.iloc[i + 1:]["high"]
            filled = bool((subsequent_highs >= fvg_top).any()) if not subsequent_highs.empty else False

            fvgs.append({
                "type": "BEARISH_FVG",
                "top": round(fvg_top, 2),
                "bottom": round(fvg_bottom, 2),
                "time": ts,
                "filled": filled,
                "label": "Supply Imbalance (FVG)",
            })

    # 2. Smart Money Order Blocks (OB)
    for i in range(3, len(df) - 1):
        prev_candle = df.iloc[i]
        next_candles = df.iloc[i + 1: min(i + 4, len(df))]
        ts = int(df.index[i].timestamp())

        # Bullish OB: Bearish candle followed by strong upward impulse breaking recent high
        if float(prev_candle["close"]) < float(prev_candle["open"]):
            impulse_high = float(next_candles["high"].max())
            prior_swing_high = float(df.iloc[max(0, i - 5):i]["high"].max())

            if impulse_high > prior_swing_high:
                ob_top = float(prev_candle["high"])
                ob_bottom = float(prev_candle["low"])
                # Check mitigation
                after_candles = df.iloc[i + 4:]["low"] if len(df) > i + 4 else pd.Series([], dtype=float)
                mitigated = bool((after_candles <= ob_top).any()) if not after_candles.empty else False

                order_blocks.append({
                    "id": f"ob-bull-{ts}",
                    "type": "BULLISH_OB",
                    "top": round(ob_top, 2),
                    "bottom": round(ob_bottom, 2),
                    "start_time": ts,
                    "mitigated": mitigated,
                    "strength": "HIGH" if not mitigated else "TESTED",
                    "label": "Demand OB",
                    "short_label": "D-OB",
                })

        # Bearish OB: Bullish candle followed by strong downward impulse breaking recent low
        elif float(prev_candle["close"]) > float(prev_candle["open"]):
            impulse_low = float(next_candles["low"].min())
            prior_swing_low = float(df.iloc[max(0, i - 5):i]["low"].min())

            if impulse_low < prior_swing_low:
                ob_top = float(prev_candle["high"])
                ob_bottom = float(prev_candle["low"])
                after_candles = df.iloc[i + 4:]["high"] if len(df) > i + 4 else pd.Series([], dtype=float)
                mitigated = bool((after_candles >= ob_bottom).any()) if not after_candles.empty else False

                order_blocks.append({
                    "id": f"ob-bear-{ts}",
                    "type": "BEARISH_OB",
                    "top": round(ob_top, 2),
                    "bottom": round(ob_bottom, 2),
                    "start_time": ts,
                    "mitigated": mitigated,
                    "strength": "HIGH" if not mitigated else "TESTED",
                    "label": "Supply OB",
                    "short_label": "S-OB",
                })

    return order_blocks[-6:], fvgs[-6:]


def _detect_trendlines(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Compute rolling support and resistance trendlines across fractal swing pivots."""
    if len(df) < 10:
        return []

    trendlines = []
    highs = df["high"].values
    lows = df["low"].values
    times = [int(t.timestamp()) for t in df.index]

    swing_high_indices = []
    swing_low_indices = []

    # 5-bar fractal pivot detection
    for i in range(2, len(df) - 2):
        if highs[i] > highs[i - 1] and highs[i] > highs[i - 2] and highs[i] > highs[i + 1] and highs[i] > highs[i + 2]:
            swing_high_indices.append(i)
        if lows[i] < lows[i - 1] and lows[i] < lows[i - 2] and lows[i] < lows[i + 1] and lows[i] < lows[i + 2]:
            swing_low_indices.append(i)

    # Resistance Trendline from last 2 swing highs
    if len(swing_high_indices) >= 2:
        idx1, idx2 = swing_high_indices[-2], swing_high_indices[-1]
        p1_price, p2_price = float(highs[idx1]), float(highs[idx2])
        p1_time, p2_time = times[idx1], times[idx2]
        time_delta = max(p2_time - p1_time, 1)
        slope = (p2_price - p1_price) / time_delta

        trendlines.append({
            "type": "RESISTANCE",
            "p1": {"time": p1_time, "price": round(p1_price, 2)},
            "p2": {"time": p2_time, "price": round(p2_price, 2)},
            "slope": round(slope, 6),
            "broken": float(df["close"].iloc[-1]) > p2_price,
            "label": "Dynamic Resistance Line",
        })

    # Support Trendline from last 2 swing lows
    if len(swing_low_indices) >= 2:
        idx1, idx2 = swing_low_indices[-2], swing_low_indices[-1]
        p1_price, p2_price = float(lows[idx1]), float(lows[idx2])
        p1_time, p2_time = times[idx1], times[idx2]
        time_delta = max(p2_time - p1_time, 1)
        slope = (p2_price - p1_price) / time_delta

        trendlines.append({
            "type": "SUPPORT",
            "p1": {"time": p1_time, "price": round(p1_price, 2)},
            "p2": {"time": p2_time, "price": round(p2_price, 2)},
            "slope": round(slope, 6),
            "broken": float(df["close"].iloc[-1]) < p2_price,
            "label": "Dynamic Support Line",
        })

    return trendlines


def _generate_tactical_signals(
    df: pd.DataFrame,
    current_price: float,
    derivatives_levels: dict[str, Any],
    orb: dict[str, Any],
    order_blocks: list[dict[str, Any]],
    fvg_gaps: list[dict[str, Any]],
) -> dict[str, Any]:
    """Generate structured Where to Buy (Long) and Where to Sell (Short) setups with risk-reward ratios."""
    max_pain = float(derivatives_levels.get("max_pain") or current_price)
    call_wall = float(derivatives_levels.get("call_wall") or (current_price * 1.015))
    put_wall = float(derivatives_levels.get("put_wall") or (current_price * 0.985))
    pcr_oi = float(derivatives_levels.get("pcr_oi") or 1.0)
    sentiment = str(derivatives_levels.get("sentiment") or "NEUTRAL").upper()

    # Determine Bullish Demand Zone
    unmitigated_bull_obs = [ob for ob in order_blocks if ob.get("type") == "BULLISH_OB" and not ob.get("mitigated")]
    if unmitigated_bull_obs:
        best_bull_ob = unmitigated_bull_obs[-1]
        long_entry_low = float(best_bull_ob["bottom"])
        long_entry_high = float(best_bull_ob["top"])
        long_trigger = "Retest of Bullish Demand Order Block"
    elif put_wall and put_wall < current_price:
        long_entry_low = round(put_wall * 0.999, 2)
        long_entry_high = round(put_wall * 1.002, 2)
        long_trigger = f"Support at Put Wall (₹{int(put_wall):,}) with Bullish Reversal"
    else:
        long_entry_low = round(current_price * 0.995, 2)
        long_entry_high = round(current_price * 0.998, 2)
        long_trigger = "Dip to Intraday VWAP Lower Support Band"

    long_sl = round(long_entry_low * 0.997, 2)
    long_t1 = round(max(max_pain, current_price * 1.006), 2)
    long_t2 = round(max(call_wall, current_price * 1.015), 2)

    risk_long = max(long_entry_high - long_sl, 1.0)
    reward_long = max(long_t1 - long_entry_high, 1.0)
    rr_long_ratio = round(reward_long / risk_long, 1)

    # Determine Bearish Supply Zone
    unmitigated_bear_obs = [ob for ob in order_blocks if ob.get("type") == "BEARISH_OB" and not ob.get("mitigated")]
    if unmitigated_bear_obs:
        best_bear_ob = unmitigated_bear_obs[-1]
        short_entry_low = float(best_bear_ob["bottom"])
        short_entry_high = float(best_bear_ob["top"])
        short_trigger = "Rejection at Bearish Supply Order Block"
    elif call_wall and call_wall > current_price:
        short_entry_low = round(call_wall * 0.998, 2)
        short_entry_high = round(call_wall * 1.001, 2)
        short_trigger = f"Resistance at Call Wall (₹{int(call_wall):,}) with Rejection Wick"
    else:
        short_entry_low = round(current_price * 1.002, 2)
        short_entry_high = round(current_price * 1.005, 2)
        short_trigger = "Exhaustion at VWAP +1.5σ Upper Volatility Band"

    short_sl = round(short_entry_high * 1.003, 2)
    short_t1 = round(min(max_pain, current_price * 0.994), 2)
    short_t2 = round(min(put_wall, current_price * 0.985), 2)

    risk_short = max(short_sl - short_entry_low, 1.0)
    reward_short = max(short_entry_low - short_t1, 1.0)
    rr_short_ratio = round(reward_short / risk_short, 1)

    # Classify overall regime
    orb_status = orb.get("status", "INSIDE_RANGE")
    if orb_status == "BREAKOUT_BULLISH" and pcr_oi >= 1.0:
        regime = "⚡ Bullish Trend Day (ORB Breakout + Put Writing)"
        bias = "BULLISH_MOMENTUM"
        confidence = 88
    elif orb_status == "BREAKDOWN_BEARISH" and pcr_oi <= 0.9:
        regime = "🩸 Bearish Breakdown (ORB Breakdown + Call Writing)"
        bias = "BEARISH_MOMENTUM"
        confidence = 86
    elif sentiment == "BULLISH":
        regime = "📈 Buying on Dips (Bullish Structure above Support)"
        bias = "BULLISH_ACCUMULATION"
        confidence = 80
    elif sentiment == "BEARISH":
        regime = "📉 Selling on Rallies (Bearish Structure below Resistance)"
        bias = "BEARISH_DISTRIBUTION"
        confidence = 78
    else:
        regime = "🌪️ Rangebound Max Pain Pin (Mean Reversion Mode)"
        bias = "RANGEBOUND_NEUTRAL"
        confidence = 75

    return {
        "primary_bias": bias,
        "regime": regime,
        "confidence_score": confidence,
        "where_to_buy": {
            "label": "Bullish Confluence Long Setup",
            "entry_low": long_entry_low,
            "entry_high": long_entry_high,
            "trigger": long_trigger,
            "stop_loss": long_sl,
            "target_1": long_t1,
            "target_2": long_t2,
            "risk_reward": f"1 : {rr_long_ratio}",
        },
        "where_to_sell": {
            "label": "Bearish Confluence Short Setup",
            "entry_low": short_entry_low,
            "entry_high": short_entry_high,
            "trigger": short_trigger,
            "stop_loss": short_sl,
            "target_1": short_t1,
            "target_2": short_t2,
            "risk_reward": f"1 : {rr_short_ratio}",
        },
    }


def get_options_chart_intelligence(
    symbol: str = "NIFTY",
    interval: str = "5m",
    period: str = "5d",
    force_refresh: bool = False,
    allow_non_fno: bool = False,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Retrieve full candlestick history, quantitative indicators, SMC levels, and tactical trade plans."""
    clean_sym = symbol.strip().upper().replace(".NS", "")
    norm_interval = interval.lower() if interval.lower() not in {"1d", "1w"} else interval.lower()
    if norm_interval in {"1d", "d"} and period in {None, "", "5d"}:
        period = "6mo"
    elif norm_interval in {"1w", "w"} and period in {None, "", "5d"}:
        period = "1y"
    cache_key = f"{clean_sym}:{norm_interval}:{period}:{allow_non_fno}"

    now = time.monotonic()
    if not force_refresh and cache_key in _CHART_CACHE:
        cached_time, cached_res = _CHART_CACHE[cache_key]
        if (now - cached_time) < _CHART_CACHE_TTL_SECONDS:
            return cached_res

    # Anti-fabrication check for F&O eligibility
    is_fno = is_fno_eligible(clean_sym)
    if not is_fno and not allow_non_fno:
        res = {
            "success": True,
            "status": "NOT_FNO",
            "symbol": clean_sym,
            "message": f"{clean_sym} is not eligible for NSE/BSE Equity Derivatives (F&O).",
            "candles": [],
            "indicators": {},
            "smart_money": {},
            "derivatives_levels": {},
            "tactical_signals": {},
        }
        _CHART_CACHE[cache_key] = (now, res)
        return res

    settings = settings or Settings()

    # 1. Fetch Option Chain intelligence (Max Pain, Walls, PCR) if F&O eligible
    opt_analysis = {}
    if is_fno:
        try:
            opt_analysis = oc_mod.analyze_option_chain(clean_sym, force_refresh=force_refresh, settings=settings)
        except Exception as e:
            logger.debug("[OPTIONS-CHART] Option chain analysis fallback for %s: %s", clean_sym, e)
            opt_analysis = {}

    spot_price = float(opt_analysis.get("spot_price") or 0.0)

    # 2. Fetch Candlestick History
    df = fetch_chart_candles(clean_sym, interval=interval, period=period, settings=settings)

    if df.empty:
        # Graceful empty response with metadata
        res = {
            "success": True,
            "status": "NO_CANDLE_DATA",
            "symbol": clean_sym,
            "interval": interval,
            "current_price": spot_price,
            "candles": [],
            "indicators": {},
            "smart_money": {},
            "derivatives_levels": {
                "max_pain": opt_analysis.get("max_pain_strike"),
                "call_wall": opt_analysis.get("resistance_strike"),
                "put_wall": opt_analysis.get("support_strike"),
                "pcr_oi": opt_analysis.get("pcr_oi"),
                "sentiment": opt_analysis.get("sentiment") or "NEUTRAL",
            } if is_fno else {},
            "tactical_signals": {},
        }
        _CHART_CACHE[cache_key] = (now, res)
        return res

    # Format candles for Lightweight Charts
    candles = []
    for stamp, row in df.iterrows():
        unix_ts = int(stamp.timestamp())
        candles.append({
            "time": unix_ts,
            "open": round(float(row["open"]), 2),
            "high": round(float(row["high"]), 2),
            "low": round(float(row["low"]), 2),
            "close": round(float(row["close"]), 2),
            "volume": int(row.get("volume", 0)),
        })

    last_close = float(df["close"].iloc[-1])
    first_close = float(df["open"].iloc[0])
    price_change = round(last_close - first_close, 2)
    price_change_pct = round((price_change / first_close) * 100.0, 2) if first_close > 0 else 0.0

    if spot_price <= 0:
        spot_price = last_close

    # 3. Calculate Quant Indicators
    vwap_data, vwap_upper, vwap_lower = _calculate_session_vwap(df)
    orb_data = _calculate_orb(df)

    # 4. Smart Money Concepts (Order Blocks & Fair Value Gaps)
    order_blocks, fvgs = _detect_order_blocks_and_fvg(df)
    trendlines = _detect_trendlines(df)

    # 5. Derivatives Structural Levels
    if is_fno:
        derivatives_levels = {
            "max_pain": opt_analysis.get("max_pain_strike") or round(spot_price, 2),
            "call_wall": opt_analysis.get("resistance_strike") or round(spot_price * 1.02, 2),
            "call_wall_oi": opt_analysis.get("call_oi_total") or 0,
            "put_wall": opt_analysis.get("support_strike") or round(spot_price * 0.98, 2),
            "put_wall_oi": opt_analysis.get("put_oi_total") or 0,
            "pcr_oi": opt_analysis.get("pcr_oi") or 1.0,
            "sentiment": opt_analysis.get("sentiment") or "NEUTRAL",
            "straddle_expected_high": round(spot_price * 1.015, 2),
            "straddle_expected_low": round(spot_price * 0.985, 2),
        }
    else:
        derivatives_levels = {}

    # 6. Tactical Confluence Signals
    tactical_signals = _generate_tactical_signals(
        df=df,
        current_price=last_close,
        derivatives_levels=derivatives_levels,
        orb=orb_data,
        order_blocks=order_blocks,
        fvg_gaps=fvgs,
    )

    res = {
        "success": True,
        "status": "LIVE" if opt_analysis.get("status") == "LIVE" else "EOD_SNAPSHOT",
        "symbol": clean_sym,
        "underlying_name": opt_analysis.get("symbol") or clean_sym,
        "interval": interval,
        "current_price": round(last_close, 2),
        "price_change": price_change,
        "price_change_pct": price_change_pct,
        "as_of": datetime.now().strftime("%Y-%m-%d %H:%M:%S IST"),
        "candles": candles,
        "indicators": {
            "vwap": vwap_data,
            "vwap_upper_1": vwap_upper,
            "vwap_lower_1": vwap_lower,
            "orb": orb_data,
        },
        "smart_money": {
            "order_blocks": order_blocks,
            "fvg_gaps": fvgs,
            "trendlines": trendlines,
        },
        "derivatives_levels": derivatives_levels,
        "tactical_signals": tactical_signals,
    }

    _CHART_CACHE[cache_key] = (now, res)
    return res


def get_intraday_structure_summary(
    symbol: str = "NIFTY",
    interval: str = "5m",
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Provide lightweight intraday SMC and VWAP technical structure summary for Market Compass."""
    clean_sym = symbol.strip().upper().replace(".NS", "")
    try:
        data = get_options_chart_intelligence(
            symbol=clean_sym,
            interval=interval,
            period="5d",
            force_refresh=False,
            allow_non_fno=True,
            settings=settings,
        )
        if not data or not data.get("candles"):
            return {}

        current_price = float(data.get("current_price") or 0.0)
        indicators = data.get("indicators") or {}
        smart_money = data.get("smart_money") or {}
        orb = indicators.get("orb") or {}

        # 1. VWAP distance
        vwap_arr = indicators.get("vwap") or []
        latest_vwap = float(vwap_arr[-1]["value"]) if vwap_arr and "value" in vwap_arr[-1] else 0.0
        vwap_dist_pct = round(((current_price - latest_vwap) / latest_vwap) * 100.0, 2) if latest_vwap > 0 else 0.0

        # 2. SMC Order Block alignment
        order_blocks = smart_money.get("order_blocks") or []
        unmitigated_bullish = [ob for ob in order_blocks if ob.get("type") == "BULLISH_OB" and not ob.get("mitigated")]
        unmitigated_bearish = [ob for ob in order_blocks if ob.get("type") == "BEARISH_OB" and not ob.get("mitigated")]

        # 3. ORB status
        orb_status = orb.get("status", "INSIDE_RANGE")

        return {
            "current_price": current_price,
            "vwap": latest_vwap,
            "vwap_dist_pct": vwap_dist_pct,
            "orb_status": orb_status,
            "bullish_obs_count": len(unmitigated_bullish),
            "bearish_obs_count": len(unmitigated_bearish),
            "smc_bias": "BULLISH" if len(unmitigated_bullish) > len(unmitigated_bearish) else ("BEARISH" if len(unmitigated_bearish) > len(unmitigated_bullish) else "NEUTRAL"),
            "tactical_regime": (data.get("tactical_signals") or {}).get("primary_bias", "NEUTRAL"),
        }
    except Exception as e:
        logger.debug("[get_intraday_structure_summary] Error evaluating %s: %s", clean_sym, e)
        return {}


# Export alias
fetch_options_chart_intelligence = get_options_chart_intelligence
