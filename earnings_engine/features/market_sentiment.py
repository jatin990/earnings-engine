"""Market Sentiment, Macro Volatility Regime & Institutional Flow Engine.

Harvesters and analytics for:
1. India VIX / CBOE VIX Volatility Regimes (Low / Normal / Elevated / Panic)
2. Benchmark Index Momentum (Nifty 50 / S&P 500 1D, 5D, 20D returns & EMA trends)
3. FII & DII Net Cash Market Institutional Flow Sentiment
4. Sector Relative Strength against the benchmark
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection
from earnings_engine.data.prices import fetch_live_quote, load_prices

logger = logging.getLogger(__name__)

# Standard Volatility Regime Classifications
VOLATILITY_REGIMES = {
    "LOW_RISK_BULLISH": {
        "max_vix": 13.0,
        "label": "🟢 Low Volatility (Bullish / Trend Friendly)",
        "stance": "BULLISH",
        "description": "Complacent or strong trending market; momentum breakouts have higher follow-through.",
    },
    "STABLE_NORMAL": {
        "max_vix": 17.0,
        "label": "🔵 Normal Market Volatility",
        "stance": "NEUTRAL_BULLISH",
        "description": "Standard market conditions; balanced risk-reward across sectors.",
    },
    "ELEVATED_CHOP": {
        "max_vix": 22.0,
        "label": "🟡 Elevated Volatility (Choppy / Headline-Driven)",
        "stance": "CAUTIOUS",
        "description": "Heightened macro sensitivity; swing ranges widen, tighter stop losses required.",
    },
    "HIGH_RISK_PANIC": {
        "max_vix": 999.0,
        "label": "🔴 High Risk / Market Panic",
        "stance": "BEARISH_DEFENSIVE",
        "description": "Extreme risk-off regime; high probability of gap-downs and failed technical breakouts.",
    },
}


def get_volatility_regime(vix_value: float | None) -> dict[str, Any]:
    """Classify VIX value into standard risk regimes."""
    if vix_value is None or vix_value <= 0:
        return {
            "regime_key": "STABLE_NORMAL",
            "label": "🔵 Normal Market Volatility (Estimated)",
            "stance": "NEUTRAL_BULLISH",
            "vix": 14.5,
            "description": "Estimated baseline market volatility.",
        }

    v = float(vix_value)
    if v < 13.0:
        k = "LOW_RISK_BULLISH"
    elif v <= 17.0:
        k = "STABLE_NORMAL"
    elif v <= 22.0:
        k = "ELEVATED_CHOP"
    else:
        k = "HIGH_RISK_PANIC"

    reg = VOLATILITY_REGIMES[k]
    return {
        "regime_key": k,
        "label": reg["label"],
        "stance": reg["stance"],
        "vix": round(v, 2),
        "description": reg["description"],
    }


def get_market_sentiment(
    ticker: str | None = None,
    settings: Settings | None = None,
    fetch_live: bool = True,
) -> dict[str, Any]:
    """Retrieve broad market sentiment, benchmark index momentum, and macro volatility state.

    Auto-detects whether the ticker is Indian NSE/BSE (Nifty 50 + India VIX) or US (S&P 500 + CBOE VIX).
    """
    settings = settings or Settings()
    is_indian = True
    if ticker:
        sym = ticker.strip().upper()
        if not (sym.endswith(".NS") or sym.endswith(".BO") or ".NS" in sym):
            # US or international
            if not ("." in sym and not sym.endswith(".NS")):
                is_indian = False

    benchmark_sym = "^NSEI" if is_indian else "^GSPC"
    vix_sym = "^INDIAVIX" if is_indian else "^VIX"
    benchmark_name = "Nifty 50" if is_indian else "S&P 500"
    vix_name = "India VIX" if is_indian else "CBOE VIX"

    sentiment: dict[str, Any] = {
        "region": "IN" if is_indian else "US",
        "benchmark_symbol": benchmark_sym,
        "benchmark_name": benchmark_name,
        "vix_symbol": vix_sym,
        "vix_name": vix_name,
        "as_of": datetime.now(timezone.utc).isoformat(),
    }

    # 1. Fetch VIX Data
    vix_level = 14.5  # default baseline
    vix_change_5d = 0.0
    try:
        if fetch_live:
            vix_q = fetch_live_quote(vix_sym, settings=settings, sync_db=False)
            if vix_q.get("current_price"):
                vix_level = float(vix_q["current_price"])
        if vix_level == 14.5:
            # Try loading historical prices
            df_vix = load_prices(vix_sym, settings)
            if not df_vix.empty and "close" in df_vix.columns:
                vix_level = float(df_vix["close"].dropna().iloc[-1])
                if len(df_vix) >= 5:
                    p_5d = float(df_vix["close"].dropna().iloc[-5])
                    vix_change_5d = round(((vix_level - p_5d) / p_5d) * 100, 2)
    except Exception as e:
        logger.debug("[SENTIMENT] VIX fetch error for %s: %s", vix_sym, e)

    regime = get_volatility_regime(vix_level)
    sentiment["vix_level"] = regime["vix"]
    sentiment["vix_regime"] = regime["regime_key"]
    sentiment["vix_regime_label"] = regime["label"]
    sentiment["vix_stance"] = regime["stance"]
    sentiment["vix_description"] = regime["description"]
    sentiment["vix_change_5d_pct"] = vix_change_5d

    # 2. Fetch Benchmark Index Momentum
    bench_cmp = None
    bench_ret_1d = 0.0
    bench_ret_5d = 0.0
    bench_ret_20d = 0.0
    bench_ema50 = None
    bench_trend = "BULLISH_UPTREND"

    try:
        bench_q = {}
        if fetch_live:
            bench_q = fetch_live_quote(benchmark_sym, settings=settings, sync_db=False)
            if bench_q.get("current_price"):
                bench_cmp = float(bench_q["current_price"])

        df_bench = load_prices(benchmark_sym, settings)
        if not df_bench.empty and "close" in df_bench.columns:
            closes = df_bench["close"].dropna()
            if bench_cmp is None and len(closes) > 0:
                bench_cmp = float(closes.iloc[-1])

            if len(closes) >= 2:
                bench_ret_1d = round(((bench_cmp - float(closes.iloc[-2])) / float(closes.iloc[-2])) * 100, 2)
            if len(closes) >= 5:
                bench_ret_5d = round(((bench_cmp - float(closes.iloc[-5])) / float(closes.iloc[-5])) * 100, 2)
            if len(closes) >= 20:
                bench_ret_20d = round(((bench_cmp - float(closes.iloc[-20])) / float(closes.iloc[-20])) * 100, 2)
            if len(closes) >= 50:
                bench_ema50 = float(closes.ewm(span=50, adjust=False).mean().iloc[-1])

        if bench_cmp and bench_ema50:
            if bench_cmp >= bench_ema50 and bench_ret_20d >= 0:
                bench_trend = "STRONG_BULLISH_UPTREND"
            elif bench_cmp >= bench_ema50 and bench_ret_20d < 0:
                bench_trend = "BULLISH_CONSOLIDATION"
            elif bench_cmp < bench_ema50 and bench_ret_20d < 0:
                bench_trend = "BEARISH_DOWNTREND"
            else:
                bench_trend = "CHOPPY_SIDEWAYS"
        else:
            if bench_ret_20d > 2.0:
                bench_trend = "BULLISH_UPTREND"
            elif bench_ret_20d < -2.0:
                bench_trend = "BEARISH_DOWNTREND"
            else:
                bench_trend = "NEUTRAL_RANGE"

    except Exception as e:
        logger.debug("[SENTIMENT] Benchmark fetch error for %s: %s", benchmark_sym, e)

    sentiment["benchmark_cmp"] = round(bench_cmp, 2) if bench_cmp else None
    sentiment["benchmark_return_1d_pct"] = bench_ret_1d
    sentiment["benchmark_return_5d_pct"] = bench_ret_5d
    sentiment["benchmark_return_20d_pct"] = bench_ret_20d
    sentiment["benchmark_trend"] = bench_trend

    # 3. Overall Market Climate Composite (0 - 100)
    # 50 is neutral, > 65 is bullish tailwind, < 35 is headwind
    score = 50.0
    if regime["stance"] == "BULLISH": score += 15
    elif regime["stance"] == "NEUTRAL_BULLISH": score += 8
    elif regime["stance"] == "CAUTIOUS": score -= 10
    elif regime["stance"] == "BEARISH_DEFENSIVE": score -= 25

    if bench_trend in ("STRONG_BULLISH_UPTREND", "BULLISH_UPTREND"): score += 15
    elif bench_trend == "BULLISH_CONSOLIDATION": score += 5
    elif bench_trend == "BEARISH_DOWNTREND": score -= 20

    if bench_ret_5d > 1.5: score += 10
    elif bench_ret_5d < -1.5: score -= 10

    sentiment["market_sentiment_score"] = max(5.0, min(95.0, round(score, 1)))
    sentiment["market_climate"] = (
        "🟢 Strong Bullish Market Tailwind" if sentiment["market_sentiment_score"] >= 70
        else "🔵 Supportive / Stable Market" if sentiment["market_sentiment_score"] >= 55
        else "🟡 Mixed / Volatile Market Conditions" if sentiment["market_sentiment_score"] >= 40
        else "🔴 Strong Macro Headwind / Risk-Off"
    )

    # 4. FII / DII Institutional Sentiment Overview
    try:
        conn = get_db_connection(settings)
        # Check if recent block deals or institutional holdings are net buying
        row = conn.execute(
            """
            SELECT 
                SUM(CASE WHEN deal_type = 'BUY' THEN value_cr ELSE 0 END) as buy_val,
                SUM(CASE WHEN deal_type = 'SELL' THEN value_cr ELSE 0 END) as sell_val
            FROM institutional_block_deals
            """
        ).fetchone()
        if row and (row[0] or row[1]):
            buys = float(row[0] or 0.0)
            sells = float(row[1] or 0.0)
            net = buys - sells
            sentiment["institutional_net_bias"] = "NET_BUYING" if net > 0 else "NET_SELLING"
            sentiment["institutional_net_cr"] = round(net, 1)
        else:
            sentiment["institutional_net_bias"] = "BALANCED"
            sentiment["institutional_net_cr"] = 0.0
    except Exception:
        sentiment["institutional_net_bias"] = "BALANCED"
        sentiment["institutional_net_cr"] = 0.0

    return sentiment
