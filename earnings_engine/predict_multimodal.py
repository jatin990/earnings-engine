"""Multi-Modal AI Stock Prediction and Synthesis Engine.

Combines real-time news headlines, world events, price action, volume dynamics,
and horizontal swing channel support/resistance into structured, actionable AI forecasts.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection, is_turso_enabled, _cache_path
from earnings_engine.data.news_sentiment import get_ticker_news_and_sentiment
from earnings_engine.data.prices import load_prices

logger = logging.getLogger(__name__)

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")


def _get_db_path(settings: Settings | None = None) -> Path:
    s = settings or Settings()
    return _cache_path(s)


def init_multimodal_db(settings: Settings | None = None) -> None:
    """Initialize the table for AI multi-modal predictions."""
    conn = get_db_connection(settings)
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ai_news_predictions (
                ticker TEXT NOT NULL,
                run_at TEXT NOT NULL,
                current_price REAL,
                ai_signal TEXT,
                sentiment_score REAL,
                confidence REAL,
                volume_status TEXT,
                volume_ratio REAL,
                catalysts TEXT,
                risk_factors TEXT,
                thesis TEXT,
                news_count INTEGER,
                payload TEXT,
                PRIMARY KEY (ticker, run_at)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ai_news_ticker ON ai_news_predictions (ticker)")
        conn.commit()


def store_ai_prediction(ticker: str, payload: dict[str, Any], settings: Settings | None = None) -> None:
    """Store an AI multi-modal forecast into SQLite."""
    init_multimodal_db(settings)
    db_path = _get_db_path(settings)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    ticker = ticker.strip().upper()

    catalysts_json = json.dumps(payload.get("catalysts", []))
    risks_json = json.dumps(payload.get("risk_factors", []))
    payload_json = json.dumps(payload)

    conn = get_db_connection(settings)
    with conn:
        conn.execute("""
            INSERT OR REPLACE INTO ai_news_predictions (
                ticker, run_at, current_price, ai_signal, sentiment_score,
                confidence, volume_status, volume_ratio, catalysts, risk_factors,
                thesis, news_count, payload
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            ticker,
            now,
            payload.get("current_price"),
            payload.get("ai_signal"),
            payload.get("sentiment_score"),
            payload.get("confidence"),
            payload.get("volume_status"),
            payload.get("volume_ratio"),
            catalysts_json,
            risks_json,
            payload.get("thesis"),
            payload.get("news_count", 0),
            payload_json,
        ))
        conn.commit()


def get_latest_ai_prediction(ticker: str, settings: Settings | None = None) -> dict[str, Any] | None:
    """Fetch the latest AI multi-modal forecast for a ticker from database."""
    init_multimodal_db(settings)
    ticker = ticker.strip().upper()

    conn = get_db_connection(settings)
    with conn:
        row = conn.execute("""
            SELECT payload, run_at FROM ai_news_predictions
            WHERE ticker = ? ORDER BY run_at DESC LIMIT 1
        """, (ticker,)).fetchone()

    if not row:
        return None

    try:
        data = json.loads(row[0])
        data["run_at"] = row[1]
        return data
    except Exception:
        return None


def get_latest_ai_predictions_all(settings: Settings | None = None) -> list[dict[str, Any]]:
    """Fetch the most recent AI multi-modal prediction for each ticker."""
    init_multimodal_db(settings)

    conn = get_db_connection(settings)
    with conn:
        rows = conn.execute("""
            SELECT a.payload, a.run_at FROM ai_news_predictions a
            INNER JOIN (
                SELECT ticker, MAX(run_at) as max_run FROM ai_news_predictions GROUP BY ticker
            ) b ON a.ticker = b.ticker AND a.run_at = b.max_run
            ORDER BY a.run_at DESC
        """).fetchall()

    results: list[dict[str, Any]] = []
    for r in rows:
        try:
            d = json.loads(r[0])
            d["run_at"] = r[1]
            results.append(d)
        except Exception:
            continue
    return results


def _compute_price_volume_features(ticker: str, settings: Settings | None = None) -> dict[str, Any]:
    """Compute price momentum, volatility, and volume accumulation metrics from prices.sqlite3."""
    prices_df = load_prices(ticker, settings=settings)
    if prices_df is None or prices_df.empty or len(prices_df) < 5:
        return {
            "current_price": None,
            "return_7d": 0.0,
            "return_30d": 0.0,
            "volatility_20d": 0.0,
            "volume_ratio": 1.0,
            "volume_status": "Average Flow",
        }

    prices_df = prices_df.sort_values("date").reset_index(drop=True)
    closes = prices_df["close"].dropna().values
    cur_price = float(closes[-1])

    # Returns
    ret_7d = float(((closes[-1] - closes[-6]) / closes[-6]) * 100) if len(closes) >= 6 and closes[-6] > 0 else 0.0
    ret_30d = float(((closes[-1] - closes[-21]) / closes[-21]) * 100) if len(closes) >= 21 and closes[-21] > 0 else 0.0

    # Volatility
    if len(closes) >= 20:
        pct_changes = pd.Series(closes[-20:]).pct_change().dropna()
        vol_20d = float(pct_changes.std() * np.sqrt(252) * 100) if not pct_changes.empty else 0.0
    else:
        vol_20d = 0.0

    # Volume accumulation ratio
    if "volume" in prices_df.columns:
        vols = prices_df["volume"].dropna().values
        if len(vols) >= 20:
            avg_vol_20d = float(np.mean(vols[-20:]))
            recent_vol = float(np.mean(vols[-3:])) if len(vols) >= 3 else float(vols[-1])
            vol_ratio = round(recent_vol / max(avg_vol_20d, 1.0), 2)
        else:
            vol_ratio = 1.0
    else:
        vol_ratio = 1.0

    if vol_ratio >= 1.4:
        volume_status = "High Accumulation"
    elif vol_ratio <= 0.65:
        volume_status = "Low Volume / Distribution"
    else:
        volume_status = "Average Flow"

    return {
        "current_price": round(cur_price, 2),
        "return_7d": round(ret_7d, 2),
        "return_30d": round(ret_30d, 2),
        "volatility_20d": round(vol_20d, 2),
        "volume_ratio": vol_ratio,
        "volume_status": volume_status,
    }


def _synthesize_with_ollama(
    ticker: str,
    news_data: dict[str, Any],
    pv_data: dict[str, Any],
    swing_support: float | None = None,
    swing_resistance: float | None = None,
) -> dict[str, Any] | None:
    """Use Ollama local LLM to synthesize news, world events, price action, and volume."""
    articles = news_data.get("articles", [])[:5]
    headlines_text = "\n".join([
        f"- [{a.get('published_at', '')}] {a.get('title', '')} ({a.get('publisher', '')}): {a.get('summary', '')}"
        for a in articles
    ]) or "No recent news headlines available."

    prompt = f"""You are a senior quantitative & equity research analyst. Analyze the following multi-modal market data for stock {ticker} and synthesize a prediction thesis.

MARKET METRICS:
- Current Price: ₹{pv_data.get('current_price', 'N/A')}
- Support (Buy Zone): ₹{swing_support or 'N/A'}
- Resistance (Sell Zone): ₹{swing_resistance or 'N/A'}
- 7-Day Return: {pv_data.get('return_7d', 0)}%
- 30-Day Return: {pv_data.get('return_30d', 0)}%
- 20-Day Annualized Volatility: {pv_data.get('volatility_20d', 0)}%
- Volume Accumulation Status: {pv_data.get('volume_status')} (Ratio: {pv_data.get('volume_ratio')}x of 20D SMA)

RECENT NEWS & WORLD EVENTS:
{headlines_text}

TASK:
Provide a JSON response with:
1. "ai_signal": One of ["Strong Bullish", "Bullish", "Neutral", "Bearish", "Strong Bearish"]
2. "sentiment_score": Float between -1.0 (extremely negative) to +1.0 (extremely positive)
3. "confidence": Float between 0.5 and 0.95
4. "catalysts": Array of 2-3 concise bullet points of positive market drivers/catalysts
5. "risk_factors": Array of 2-3 concise downside risks
6. "thesis": 2-3 sentences explaining the synthesis of news sentiment, price action near support/resistance, and volume.

OUTPUT STRICTLY IN VALID JSON FORMAT WITHOUT MARKDOWN TICKS:
"""
    try:
        url = f"{OLLAMA_HOST}/api/generate"
        payload = {
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.2, "top_p": 0.9},
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=12) as response:
            resp_data = json.loads(response.read().decode("utf-8"))
            response_text = resp_data.get("response", "").strip()

            # Parse JSON
            parsed = json.loads(response_text)
            if "ai_signal" in parsed and "thesis" in parsed:
                return parsed
    except Exception as e:
        logger.debug("Ollama synthesis call failed for %s: %s", ticker, e)

    return None


def _deterministic_synthesis(
    ticker: str,
    news_data: dict[str, Any],
    pv_data: dict[str, Any],
    swing_support: float | None = None,
    swing_resistance: float | None = None,
) -> dict[str, Any]:
    """Deterministic quantitative & qualitative multi-factor synthesis fallback."""
    news_score = news_data.get("sentiment_score", 0.0)
    ret_7d = pv_data.get("return_7d", 0.0)
    ret_30d = pv_data.get("return_30d", 0.0)
    vol_ratio = pv_data.get("volume_ratio", 1.0)
    cur_price = pv_data.get("current_price")

    # Multi-factor score composition:
    # 40% News sentiment, 30% Price Momentum, 20% Volume flow, 10% Channel position
    momentum_norm = max(-1.0, min(1.0, (ret_7d * 0.4 + ret_30d * 0.6) / 10.0))
    volume_norm = max(-1.0, min(1.0, (vol_ratio - 1.0) / 0.5))

    channel_norm = 0.0
    channel_desc = "in a neutral trading range"
    if cur_price and swing_support and swing_resistance and swing_resistance > swing_support:
        pos = (cur_price - swing_support) / (swing_resistance - swing_support)
        if pos <= 0.25:
            channel_norm = 0.8
            channel_desc = "testing strong horizontal support (buy zone)"
        elif pos >= 0.85:
            channel_norm = -0.6
            channel_desc = "near upper horizontal resistance (sell zone)"
        else:
            channel_norm = 0.0
            channel_desc = "in the middle of its horizontal trading channel"

    combined_score = round(
        0.40 * news_score + 0.30 * momentum_norm + 0.20 * volume_norm + 0.10 * channel_norm, 2
    )
    combined_score = max(-1.0, min(1.0, combined_score))

    if combined_score >= 0.45:
        ai_signal = "Strong Bullish"
    elif combined_score >= 0.15:
        ai_signal = "Bullish"
    elif combined_score <= -0.45:
        ai_signal = "Strong Bearish"
    elif combined_score <= -0.15:
        ai_signal = "Bearish"
    else:
        ai_signal = "Neutral"

    confidence = round(0.65 + min(0.25, abs(combined_score) * 0.25 + (0.05 if news_data.get("articles_count", 0) >= 3 else 0)), 2)

    # Catalysts
    catalysts: list[str] = []
    top_topics = news_data.get("top_topics", [])
    if top_topics:
        catalysts.append(f"Active event buzz in {', '.join(top_topics[:2])}")
    if vol_ratio >= 1.3:
        catalysts.append(f"Volume accumulation surge at {vol_ratio}x 20-day average")
    if channel_norm > 0:
        catalysts.append(f"Favorable risk/reward positioning at horizontal support level (₹{swing_support})")
    if ret_7d > 2.0:
        catalysts.append(f"Positive short-term price momentum (+{ret_7d}% 7D move)")
    if not catalysts:
        catalysts.append("Consolidation with steady market liquidity")

    # Risk Factors
    risk_factors: list[str] = []
    if channel_norm < 0:
        risk_factors.append(f"Overhead resistance friction near ₹{swing_resistance}")
    if ret_30d < -5.0:
        risk_factors.append(f"Negative 30-day trend momentum ({ret_30d}%)")
    if vol_ratio < 0.7:
        risk_factors.append("Below-average trading volume / institutional participation")
    if news_score < -0.15:
        risk_factors.append("Headline negative sentiment / macroeconomic headwinds")
    if not risk_factors:
        risk_factors.append("Broader market volatility and macro interest rate sensitivity")

    thesis = (
        f"{ticker} displays a {ai_signal.lower()} synthesis profile (score: {combined_score:+.2f}). "
        f"Price action is {channel_desc} with {pv_data.get('volume_status', 'average volume').lower()}. "
        f"News sentiment is currently {news_data.get('sentiment_label', 'neutral').lower()} based on {news_data.get('articles_count', 0)} recent articles."
    )

    return {
        "ai_signal": ai_signal,
        "sentiment_score": combined_score,
        "confidence": confidence,
        "catalysts": catalysts[:3],
        "risk_factors": risk_factors[:3],
        "thesis": thesis,
    }


def run_multimodal_prediction(
    ticker: str,
    swing_support: float | None = None,
    swing_resistance: float | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Run full multi-modal prediction pipeline for a single ticker."""
    ticker = ticker.strip().upper()
    if not ticker:
        return {"error": "Ticker is required"}

    # 1. Fetch News & Sentiment
    news_data = get_ticker_news_and_sentiment(ticker, limit=8, settings=settings)

    # 2. Compute Price Action & Volume Dynamics
    pv_data = _compute_price_volume_features(ticker, settings=settings)

    # 3. LLM / Quant Synthesis
    synthesis = _synthesize_with_ollama(
        ticker,
        news_data,
        pv_data,
        swing_support=swing_support,
        swing_resistance=swing_resistance,
    )
    if not synthesis:
        synthesis = _deterministic_synthesis(
            ticker,
            news_data,
            pv_data,
            swing_support=swing_support,
            swing_resistance=swing_resistance,
        )

    # 4. Construct complete response payload
    result: dict[str, Any] = {
        "ticker": ticker,
        "current_price": pv_data.get("current_price"),
        "ai_signal": synthesis.get("ai_signal", "Neutral"),
        "sentiment_score": synthesis.get("sentiment_score", 0.0),
        "confidence": synthesis.get("confidence", 0.70),
        "volume_status": pv_data.get("volume_status", "Average Flow"),
        "volume_ratio": pv_data.get("volume_ratio", 1.0),
        "return_7d": pv_data.get("return_7d", 0.0),
        "return_30d": pv_data.get("return_30d", 0.0),
        "volatility_20d": pv_data.get("volatility_20d", 0.0),
        "swing_support": swing_support,
        "swing_resistance": swing_resistance,
        "catalysts": synthesis.get("catalysts", []),
        "risk_factors": synthesis.get("risk_factors", []),
        "thesis": synthesis.get("thesis", ""),
        "news_count": news_data.get("articles_count", 0),
        "news_sentiment_label": news_data.get("sentiment_label", "Neutral"),
        "news_sentiment_score": news_data.get("sentiment_score", 0.0),
        "top_topics": news_data.get("top_topics", []),
        "articles": news_data.get("articles", []),
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
    }

    # 5. Persist to SQLite
    try:
        store_ai_prediction(ticker, result, settings=settings)
    except Exception as e:
        logger.warning("Failed to store AI forecast for %s: %s", ticker, e)

    return result
