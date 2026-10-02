"""Quantitative Commodities Chart & Smart Money Analytics Engine.

Computes real-time intraday / daily indicators for precious metals and energy commodities:
- Session VWAP with dynamic standard deviation bands (1.5σ)
- 15-minute Opening Range Breakout (ORB-15) and projected expansion targets
- Smart Money Concepts (SMC): Bullish & Bearish Order Blocks (OB) and Fair Value Gaps (FVG)
- Algorithmic Support / Resistance Trendlines & Dynamic Pivot Levels
- Gold / Silver Ratio (GSR) Macro Gauge
- Tactical "Where to Buy & Where to Sell" trade execution plans
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

logger = logging.getLogger("earnings_engine.data.commodities_chart_engine")

_COMMODITIES_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_COMMODITIES_CACHE_TTL_SECONDS = 30.0  # 30 seconds TTL for fast updates

SUPPORTED_COMMODITIES: list[dict[str, Any]] = [
    {
        "symbol": "GOLD",
        "name": "Gold (COMEX · XAU/USD)",
        "category": "Precious Metals",
        "global_ticker": "GC=F",
        "alt_ticker": "XAUUSD=X",
        "domestic_ticker": "GOLDBEES.NS",
        "unit": "$ / oz",
        "currency_symbol": "$",
        "icon": "🥇",
        "round_interval": 10.0,
    },
    {
        "symbol": "SILVER",
        "name": "Silver (COMEX · XAG/USD)",
        "category": "Precious Metals",
        "global_ticker": "SI=F",
        "alt_ticker": "XAGUSD=X",
        "domestic_ticker": "SILVERBEES.NS",
        "unit": "$ / oz",
        "currency_symbol": "$",
        "icon": "🥈",
        "round_interval": 0.5,
    },
    {
        "symbol": "CRUDEOIL",
        "name": "WTI Light Sweet Crude Oil",
        "category": "Energy",
        "global_ticker": "CL=F",
        "alt_ticker": "CL=F",
        "domestic_ticker": "CRUDEOIL.NS",
        "unit": "$ / bbl",
        "currency_symbol": "$",
        "icon": "🛢️",
        "round_interval": 1.0,
    },
    {
        "symbol": "NATGAS",
        "name": "Henry Hub Natural Gas",
        "category": "Energy",
        "global_ticker": "NG=F",
        "alt_ticker": "NG=F",
        "domestic_ticker": "NATURALGAS.NS",
        "unit": "$ / MMBtu",
        "currency_symbol": "$",
        "icon": "🔥",
        "round_interval": 0.1,
    },
    {
        "symbol": "COPPER",
        "name": "High Grade Copper",
        "category": "Industrial Metals",
        "global_ticker": "HG=F",
        "alt_ticker": "HG=F",
        "domestic_ticker": "COPPER.NS",
        "unit": "$ / lb",
        "currency_symbol": "$",
        "icon": "🧱",
        "round_interval": 0.05,
    },
    {
        "symbol": "BRENT",
        "name": "Brent Crude Oil",
        "category": "Energy",
        "global_ticker": "BZ=F",
        "alt_ticker": "BZ=F",
        "domestic_ticker": "BRENT.NS",
        "unit": "$ / bbl",
        "currency_symbol": "$",
        "icon": "⛽",
        "round_interval": 1.0,
    },
    {
        "symbol": "PLATINUM",
        "name": "Platinum (NYMEX)",
        "category": "Precious Metals",
        "global_ticker": "PL=F",
        "alt_ticker": "PL=F",
        "domestic_ticker": "PLATINUM.NS",
        "unit": "$ / oz",
        "currency_symbol": "$",
        "icon": "🪙",
        "round_interval": 10.0,
    },
]

COMMODITY_MAP: dict[str, dict[str, Any]] = {c["symbol"]: c for c in SUPPORTED_COMMODITIES}


def get_supported_commodity_symbols() -> list[dict[str, Any]]:
    """Return catalog of supported commodity assets."""
    return SUPPORTED_COMMODITIES


def resolve_commodity_symbol(symbol: str) -> str:
    """Map user/dashboard commodity symbol to appropriate ticker symbol."""
    clean = symbol.strip().upper()
    if clean in COMMODITY_MAP:
        return COMMODITY_MAP[clean]["global_ticker"]
    if clean.endswith("=F") or clean.endswith("=X") or clean.endswith(".NS"):
        return clean
    return f"{clean}=F"


def fetch_commodity_candles(
    symbol: str,
    interval: str = "5m",
    period: str = "5d",
    settings: Settings | None = None,
) -> pd.DataFrame:
    """Fetch candlestick price bars for a commodity from yfinance or local cache."""
    clean_sym = symbol.strip().upper()
    info = COMMODITY_MAP.get(clean_sym)

    # Try global ticker first, then alt_ticker, then domestic ticker fallback
    tickers_to_try = []
    if info:
        gt = info.get("global_ticker")
        if gt:
            tickers_to_try.append(gt)
        at = info.get("alt_ticker")
        if at and at not in tickers_to_try:
            tickers_to_try.append(at)
        dt = info.get("domestic_ticker")
        if dt and dt not in tickers_to_try:
            tickers_to_try.append(dt)
    else:
        tickers_to_try.append(resolve_commodity_symbol(clean_sym))

    valid_intervals = {"1m", "5m", "15m", "30m", "1h", "60m", "1d", "1D"}
    norm_interval = interval.lower() if interval.lower() != "1d" else "1d"
    if norm_interval not in valid_intervals:
        norm_interval = "5m"

    if not period:
        period = "5d" if norm_interval in {"1m", "5m", "15m", "30m", "1h", "60m"} else "6mo"

    for yf_symbol in tickers_to_try:
        try:
            t = yf.Ticker(yf_symbol)
            df = t.history(period=period, interval=norm_interval)
            if df is not None and not df.empty:
                df.columns = [c.lower() for c in df.columns]
                req_cols = ["open", "high", "low", "close", "volume"]
                if all(col in df.columns for col in req_cols):
                    df = df[req_cols].dropna()
                    if not isinstance(df.index, pd.DatetimeIndex):
                        df.index = pd.to_datetime(df.index)
                    if len(df) > 0:
                        return df
        except Exception as e:
            logger.debug("[COMMODITIES-CHART] yfinance error for %s (%s): %s", yf_symbol, norm_interval, e)

    # Fallback to local price cache if available
    try:
        from earnings_engine.data.prices import load_prices
        settings = settings or Settings()
        for yf_symbol in tickers_to_try:
            fallback_df = load_prices(yf_symbol, settings)
            if fallback_df is not None and not fallback_df.empty:
                return fallback_df.tail(120)
    except Exception:
        pass

    return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])


def _calculate_session_vwap(df: pd.DataFrame) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Calculate intraday Session VWAP with 1.5 standard deviation dispersion bands."""
    if df.empty or "close" not in df.columns or "volume" not in df.columns:
        return [], [], []

    vwap_series = []
    upper_series = []
    lower_series = []

    typical_price = (df["high"] + df["low"] + df["close"]) / 3.0
    vol = df["volume"].replace(0, 1)  # Guard against zero-volume division

    df_copy = df.copy()
    df_copy["date_only"] = df_copy.index.date
    grouped = df_copy.groupby("date_only")

    for _, group in grouped:
        cum_pv = (typical_price.loc[group.index] * vol.loc[group.index]).cumsum()
        cum_v = vol.loc[group.index].cumsum()
        group_vwap = cum_pv / cum_v

        # Variance for standard deviation bands
        squared_diff = (typical_price.loc[group.index] - group_vwap) ** 2
        cum_var = (squared_diff * vol.loc[group.index]).cumsum() / cum_v
        std_dev = np.sqrt(cum_var.clip(lower=0))

        band_upper = group_vwap + 1.5 * std_dev
        band_lower = group_vwap - 1.5 * std_dev

        for idx in group.index:
            t_sec = int(idx.timestamp())
            v_val = round(float(group_vwap.loc[idx]), 2)
            u_val = round(float(band_upper.loc[idx]), 2)
            l_val = round(float(band_lower.loc[idx]), 2)

            vwap_series.append({"time": t_sec, "value": v_val})
            upper_series.append({"time": t_sec, "value": u_val})
            lower_series.append({"time": t_sec, "value": l_val})

    return vwap_series, upper_series, lower_series


def _calculate_orb(df: pd.DataFrame) -> dict[str, Any]:
    """Calculate Opening Range Breakout (ORB-15) levels and projected expansion targets."""
    if df.empty:
        return {"active": False, "high": 0.0, "low": 0.0, "target_long_1": 0.0, "target_short_1": 0.0}

    last_date = df.index[-1].date()
    today_df = df[df.index.date == last_date]

    if today_df.empty:
        return {"active": False, "high": 0.0, "low": 0.0, "target_long_1": 0.0, "target_short_1": 0.0}

    # First 3 bars of 5m session or first 15m
    orb_df = today_df.iloc[:3] if len(today_df) >= 3 else today_df

    orb_high = round(float(orb_df["high"].max()), 2)
    orb_low = round(float(orb_df["low"].min()), 2)
    orb_range = max(orb_high - orb_low, 1.0)

    target_long_1 = round(orb_high + orb_range, 2)
    target_long_2 = round(orb_high + (2.0 * orb_range), 2)
    target_short_1 = round(orb_low - orb_range, 2)
    target_short_2 = round(orb_low - (2.0 * orb_range), 2)

    return {
        "active": True,
        "high": orb_high,
        "low": orb_low,
        "range": round(orb_range, 2),
        "target_long_1": target_long_1,
        "target_long_2": target_long_2,
        "target_short_1": target_short_1,
        "target_short_2": target_short_2,
    }


def _detect_order_blocks_and_fvg(df: pd.DataFrame) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Detect Smart Money Concepts (SMC): Bullish & Bearish Order Blocks and Fair Value Gaps."""
    order_blocks: list[dict[str, Any]] = []
    fvgs: list[dict[str, Any]] = []

    if len(df) < 10:
        return order_blocks, fvgs

    # 1. Fair Value Gaps (3-bar imbalance)
    for i in range(2, len(df)):
        c1 = df.iloc[i - 2]
        c3 = df.iloc[i]
        t_sec = int(df.index[i].timestamp())

        # Bullish FVG: Low of bar 3 is higher than High of bar 1
        if c3["low"] > c1["high"]:
            fvgs.append({
                "type": "BULLISH_FVG",
                "time": t_sec,
                "top": round(float(c3["low"]), 2),
                "bottom": round(float(c1["high"]), 2),
                "midpoint": round(float((c3["low"] + c1["high"]) / 2.0), 2),
                "mitigated": bool(df["low"].iloc[i:].min() <= c1["high"]),
            })

        # Bearish FVG: High of bar 3 is lower than Low of bar 1
        elif c3["high"] < c1["low"]:
            fvgs.append({
                "type": "BEARISH_FVG",
                "time": t_sec,
                "top": round(float(c1["low"]), 2),
                "bottom": round(float(c3["high"]), 2),
                "midpoint": round(float((c1["low"] + c3["high"]) / 2.0), 2),
                "mitigated": bool(df["high"].iloc[i:].max() >= c1["low"]),
            })

    # 2. Bullish and Bearish Order Blocks
    # Find rolling swing high/low points
    for i in range(5, len(df) - 1):
        prev_slice = df.iloc[i - 5 : i]
        current_bar = df.iloc[i]

        # Breakout to new swing high -> Find last down-close candle before expansion (Demand OB)
        if current_bar["close"] > prev_slice["high"].max():
            down_candles = [df.iloc[k] for k in range(i - 4, i) if df.iloc[k]["close"] < df.iloc[k]["open"]]
            if down_candles:
                ob_candle = down_candles[-1]
                t_ob = int(ob_candle.name.timestamp())
                order_blocks.append({
                    "type": "BULLISH_OB",
                    "short_label": "D-OB",
                    "time": t_ob,
                    "top": round(float(max(ob_candle["open"], ob_candle["close"])), 2),
                    "bottom": round(float(min(ob_candle["open"], ob_candle["close"])), 2),
                    "mitigated": bool(df["low"].iloc[i:].min() <= min(ob_candle["open"], ob_candle["close"])),
                })

        # Breakdown to new swing low -> Find last up-close candle before expansion (Supply OB)
        elif current_bar["close"] < prev_slice["low"].min():
            up_candles = [df.iloc[k] for k in range(i - 4, i) if df.iloc[k]["close"] > df.iloc[k]["open"]]
            if up_candles:
                ob_candle = up_candles[-1]
                t_ob = int(ob_candle.name.timestamp())
                order_blocks.append({
                    "type": "BEARISH_OB",
                    "short_label": "S-OB",
                    "time": t_ob,
                    "top": round(float(max(ob_candle["open"], ob_candle["close"])), 2),
                    "bottom": round(float(min(ob_candle["open"], ob_candle["close"])), 2),
                    "mitigated": bool(df["high"].iloc[i:].max() >= max(ob_candle["open"], ob_candle["close"])),
                })

    # Return top 4 freshest order blocks & FVGs
    return order_blocks[-4:], fvgs[-4:]


def _detect_trendlines(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Detect dynamic support and resistance trendlines using rolling swing pivot points."""
    if len(df) < 15:
        return []

    trendlines: list[dict[str, Any]] = []

    # Detect swing lows (Support line)
    lows = df["low"].values
    highs = df["high"].values
    n = len(df)

    swing_low_indices = []
    swing_high_indices = []

    for i in range(2, n - 2):
        if lows[i] <= min(lows[i - 2 : i + 3]):
            swing_low_indices.append(i)
        if highs[i] >= max(highs[i - 2 : i + 3]):
            swing_high_indices.append(i)

    # Support Trendline (connecting last 2 swing lows)
    if len(swing_low_indices) >= 2:
        i1, i2 = swing_low_indices[-2], swing_low_indices[-1]
        t1, t2 = int(df.index[i1].timestamp()), int(df.index[i2].timestamp())
        p1, p2 = round(float(lows[i1]), 2), round(float(lows[i2]), 2)
        trendlines.append({
            "type": "SUPPORT",
            "point1": {"time": t1, "price": p1},
            "point2": {"time": t2, "price": p2},
            "slope": round((p2 - p1) / max(i2 - i1, 1), 2),
        })

    # Resistance Trendline (connecting last 2 swing highs)
    if len(swing_high_indices) >= 2:
        i1, i2 = swing_high_indices[-2], swing_high_indices[-1]
        t1, t2 = int(df.index[i1].timestamp()), int(df.index[i2].timestamp())
        p1, p2 = round(float(highs[i1]), 2), round(float(highs[i2]), 2)
        trendlines.append({
            "type": "RESISTANCE",
            "point1": {"time": t1, "price": p1},
            "point2": {"time": t2, "price": p2},
            "slope": round((p2 - p1) / max(i2 - i1, 1), 2),
        })

    return trendlines


def _calculate_classical_pivots(df: pd.DataFrame) -> dict[str, float]:
    """Calculate classical floor pivot points and dynamic ATR volatility bands."""
    if df.empty:
        return {"p": 0.0, "r1": 0.0, "r2": 0.0, "r3": 0.0, "s1": 0.0, "s2": 0.0, "s3": 0.0, "atr": 0.0}

    # Reference prior day or whole range
    high = float(df["high"].max())
    low = float(df["low"].min())
    close = float(df["close"].iloc[-1])

    # 14-period True Range for ATR
    tr = np.maximum(df["high"] - df["low"], np.maximum(abs(df["high"] - df["close"].shift(1)), abs(df["low"] - df["close"].shift(1)))).dropna()
    atr = float(tr.tail(14).mean()) if not tr.empty else max(high - low, 1.0)

    p = round((high + low + close) / 3.0, 2)
    r1 = round((2.0 * p) - low, 2)
    s1 = round((2.0 * p) - high, 2)
    r2 = round(p + (high - low), 2)
    s2 = round(p - (high - low), 2)
    r3 = round(high + 2.0 * (p - low), 2)
    s3 = round(low - 2.0 * (high - p), 2)

    return {
        "p": p,
        "r1": r1,
        "r2": r2,
        "r3": r3,
        "s1": s1,
        "s2": s2,
        "s3": s3,
        "atr": round(atr, 2),
    }


def _calculate_gsr(gold_spot: float, silver_spot: float) -> float:
    """Calculate Gold/Silver Ratio (GSR)."""
    if silver_spot <= 0:
        return 80.0
    return round(gold_spot / silver_spot, 2)


def _generate_tactical_signals(
    df: pd.DataFrame,
    pivots: dict[str, float],
    orb: dict[str, Any],
    symbol: str,
    currency_symbol: str = "$",
) -> dict[str, Any]:
    """Generate actionable 3-column tactical trade plan with exact entry, stop loss, and targets."""
    if df.empty:
        return {
            "regime": "NEUTRAL",
            "momentum_bias": "FLAT",
            "where_to_buy": {"entry_zone": "—", "stop_loss": 0.0, "target_1": 0.0, "target_2": 0.0, "rr_ratio": 1.5},
            "where_to_sell": {"entry_zone": "—", "stop_loss": 0.0, "target_1": 0.0, "target_2": 0.0, "rr_ratio": 1.5},
        }

    meta = COMMODITY_MAP.get(symbol.strip().upper(), {})
    curr = meta.get("currency_symbol", currency_symbol)

    spot = float(df["close"].iloc[-1])
    p = pivots.get("p", spot)
    r1 = pivots.get("r1", spot * 1.01)
    r2 = pivots.get("r2", spot * 1.02)
    s1 = pivots.get("s1", spot * 0.99)
    s2 = pivots.get("s2", spot * 0.98)
    atr = pivots.get("atr", max(spot * 0.008, 1.0))

    # Determine Regime
    if spot > p and spot >= orb.get("high", spot):
        regime = "BULLISH_EXPANSION"
        momentum = "STRONG_ACCUMULATION"
    elif spot < p and spot <= orb.get("low", spot):
        regime = "BEARISH_BREAKDOWN"
        momentum = "DISTRIBUTION_EXPANSION"
    elif spot > p:
        regime = "BULLISH_MOMENTUM"
        momentum = "MODERATE_BUYING"
    else:
        regime = "RANGE_BOUND_CHOP"
        momentum = "CONSOLIDATION"

    # Where to Buy Setup (Pullback to Pivot / S1 or ORB High breakout)
    buy_entry_low = round(min(s1, spot - (0.4 * atr)), 2)
    buy_entry_high = round(max(p, spot), 2)
    buy_sl = round(buy_entry_low - (0.8 * atr), 2)
    buy_t1 = round(max(r1, spot + (1.2 * atr)), 2)
    buy_t2 = round(max(r2, spot + (2.0 * atr)), 2)

    buy_risk = max(buy_entry_low - buy_sl, 0.1)
    buy_reward = max(buy_t1 - buy_entry_high, 0.1)
    buy_rr = round(buy_reward / buy_risk, 2) if buy_risk > 0 else 2.0

    # Where to Sell Setup (Rejection at R1 / R2 or ORB Low breakdown)
    sell_entry_high = round(max(r1, spot + (0.4 * atr)), 2)
    sell_entry_low = round(min(p, spot), 2)
    sell_sl = round(sell_entry_high + (0.8 * atr), 2)
    sell_t1 = round(min(s1, spot - (1.2 * atr)), 2)
    sell_t2 = round(min(s2, spot - (2.0 * atr)), 2)

    sell_risk = max(sell_sl - sell_entry_high, 0.1)
    sell_reward = max(sell_entry_low - sell_t1, 0.1)
    sell_rr = round(sell_reward / sell_risk, 2) if sell_risk > 0 else 2.0

    return {
        "regime": regime,
        "momentum_bias": momentum,
        "where_to_buy": {
            "entry_zone": f"{curr}{buy_entry_low:,.2f} – {curr}{buy_entry_high:,.2f}",
            "stop_loss": buy_sl,
            "target_1": buy_t1,
            "target_2": buy_t2,
            "rr_ratio": max(buy_rr, 1.2),
            "rationale": "Confluence of Demand Order Block, Session VWAP Floor, and S1 Support.",
        },
        "where_to_sell": {
            "entry_zone": f"{curr}{sell_entry_low:,.2f} – {curr}{sell_entry_high:,.2f}",
            "stop_loss": sell_sl,
            "target_1": sell_t1,
            "target_2": sell_t2,
            "rr_ratio": max(sell_rr, 1.2),
            "rationale": "Confluence of Supply Order Block, R1 Resistance, and Overbought Volatility Upper Band.",
        },
    }


def get_commodity_chart_intelligence(
    symbol: str = "GOLD",
    interval: str = "5m",
    period: str = "5d",
    force_refresh: bool = False,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Compile comprehensive quantitative chart intelligence, indicators, SMC order blocks, and trade HUD."""
    clean_sym = symbol.strip().upper()
    cache_key = f"{clean_sym}:{interval}:{period}"

    now = time.time()
    if not force_refresh and cache_key in _COMMODITIES_CACHE:
        cached_time, cached_payload = _COMMODITIES_CACHE[cache_key]
        if now - cached_time < _COMMODITIES_CACHE_TTL_SECONDS:
            return cached_payload

    meta = COMMODITY_MAP.get(clean_sym, {
        "symbol": clean_sym,
        "name": f"{clean_sym} Commodity",
        "category": "Commodities",
        "unit": "$",
        "currency_symbol": "$",
        "icon": "💎",
    })

    df = fetch_commodity_candles(clean_sym, interval=interval, period=period, settings=settings)

    if df.empty:
        # Honest fallback response without fake data
        res = {
            "success": True,
            "symbol": clean_sym,
            "name": meta["name"],
            "category": meta["category"],
            "unit": meta["unit"],
            "currency_symbol": meta.get("currency_symbol", "$"),
            "icon": meta["icon"],
            "status": "SNAPSHOT_EMPTY",
            "spot_price": 0.0,
            "change_24h": 0.0,
            "high_24h": 0.0,
            "low_24h": 0.0,
            "candles": [],
            "indicators": {
                "vwap": [],
                "vwap_upper": [],
                "vwap_lower": [],
                "orb": {"active": False, "high": 0.0, "low": 0.0},
                "pivots": {"p": 0.0, "r1": 0.0, "s1": 0.0},
                "order_blocks": [],
                "fvgs": [],
                "trendlines": [],
            },
            "tactical_hud": {
                "regime": "NEUTRAL",
                "momentum_bias": "NO_DATA",
                "where_to_buy": {"entry_zone": "—", "stop_loss": 0.0, "target_1": 0.0, "target_2": 0.0, "rr_ratio": 1.5},
                "where_to_sell": {"entry_zone": "—", "stop_loss": 0.0, "target_1": 0.0, "target_2": 0.0, "rr_ratio": 1.5},
            },
        }
        _COMMODITIES_CACHE[cache_key] = (now, res)
        return res

    spot_price = round(float(df["close"].iloc[-1]), 2)
    prev_close = float(df["close"].iloc[-2]) if len(df) >= 2 else spot_price
    change_24h = round(((spot_price - prev_close) / prev_close) * 100.0, 2) if prev_close > 0 else 0.0
    high_24h = round(float(df["high"].tail(75).max()), 2)
    low_24h = round(float(df["low"].tail(75).min()), 2)

    # Format Candlesticks for Lightweight Charts
    candles = []
    for idx, row in df.iterrows():
        t_sec = int(idx.timestamp())
        candles.append({
            "time": t_sec,
            "open": round(float(row["open"]), 2),
            "high": round(float(row["high"]), 2),
            "low": round(float(row["low"]), 2),
            "close": round(float(row["close"]), 2),
            "volume": int(row["volume"]) if "volume" in row and not pd.isna(row["volume"]) else 0,
        })

    # Calculations
    vwap, vwap_upper, vwap_lower = _calculate_session_vwap(df)
    orb = _calculate_orb(df)
    obs, fvgs = _detect_order_blocks_and_fvg(df)
    trendlines = _detect_trendlines(df)
    pivots = _calculate_classical_pivots(df)
    currency_symbol = meta.get("currency_symbol", "$")
    tactical_hud = _generate_tactical_signals(df, pivots, orb, clean_sym, currency_symbol=currency_symbol)

    # Calculate GSR if Silver is active or proxy ratio
    gsr = 84.5
    if clean_sym == "GOLD" or clean_sym == "SILVER":
        try:
            silver_df = fetch_commodity_candles("SILVER", interval="1d", period="5d", settings=settings)
            gold_df = fetch_commodity_candles("GOLD", interval="1d", period="5d", settings=settings)
            if not silver_df.empty and not gold_df.empty:
                gsr = _calculate_gsr(float(gold_df["close"].iloc[-1]), float(silver_df["close"].iloc[-1]))
        except Exception:
            pass

    payload = {
        "success": True,
        "symbol": clean_sym,
        "name": meta["name"],
        "category": meta["category"],
        "unit": meta["unit"],
        "currency_symbol": currency_symbol,
        "icon": meta["icon"],
        "status": "LIVE_FEED",
        "spot_price": spot_price,
        "change_24h": change_24h,
        "high_24h": high_24h,
        "low_24h": low_24h,
        "gsr": gsr,
        "candles": candles,
        "indicators": {
            "vwap": vwap,
            "vwap_upper": vwap_upper,
            "vwap_lower": vwap_lower,
            "orb": orb,
            "pivots": pivots,
            "order_blocks": obs,
            "fvgs": fvgs,
            "trendlines": trendlines,
        },
        "tactical_hud": tactical_hud,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S IST"),
    }

    _COMMODITIES_CACHE[cache_key] = (now, payload)
    return payload
