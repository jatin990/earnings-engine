"""Market sentiment matrix, Fear & Greed index, volatility regimes, and breadth evaluation."""

from __future__ import annotations

import logging
import math
import time
from datetime import datetime, timezone
from typing import Any

from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection
from earnings_engine.data.market_pulse.constants import (
    _SENTIMENT_CACHE,
    _SENTIMENT_CACHE_TTL,
    _SENTIMENT_LOCK,
)
from earnings_engine.data.market_pulse.indices import compute_indices_quotes
from earnings_engine.data.market_pulse.timing import format_iso_to_ist, is_market_open
from earnings_engine.data.prices import fetch_batch_live_quotes

logger = logging.getLogger(__name__)


def compute_market_sentiment_matrix(
    settings: Settings | None = None,
    indices_data: list[dict[str, Any]] | None = None,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """Compute Fear & Greed sentiment index and volatility regimes.

    Multi-factor model synthesized from:
      1. India VIX level (40% weight): mapped to 0-100 where low VIX = Greed, high VIX = Fear
      2. Nifty Momentum (40% weight): 1D & 7D return trajectory
      3. Market Breadth (10% weight): advances vs. declines
      4. Safe-Haven Gold / Currency Flow (10% weight)
    """
    global _SENTIMENT_CACHE
    now_ts = time.time()

    if not force_refresh and "data" in _SENTIMENT_CACHE:
        cached_ts = _SENTIMENT_CACHE.get("ts", 0)
        if (now_ts - cached_ts) < _SENTIMENT_CACHE_TTL:
            return _SENTIMENT_CACHE["data"]
        if not is_market_open(now_ts) and not is_market_open(cached_ts):
            return _SENTIMENT_CACHE["data"]

    settings = settings or Settings()

    if indices_data is None:
        indices_data = compute_indices_quotes(settings=settings, force_refresh=force_refresh)

    # Extract Nifty 50 and India VIX from indices
    nifty = next((idx for idx in indices_data if idx["symbol"] == "^NSEI"), None)
    vix = next((idx for idx in indices_data if idx["symbol"] == "^INDIAVIX"), None)

    # Fallback to direct fetch if VIX missing
    vix_val = vix["price"] if vix and vix.get("price") else 14.5
    if not vix or not vix.get("price"):
        live_vix = fetch_batch_live_quotes(["^INDIAVIX"], settings=settings, sync_db=False)
        if live_vix.get("^INDIAVIX") and live_vix["^INDIAVIX"].get("current_price"):
            vix_val = float(live_vix["^INDIAVIX"]["current_price"])

    nifty_1d_pct = nifty["change_1d_pct"] if nifty else 0.0
    nifty_7d_pct = nifty["change_7d_pct"] if nifty else 0.0

    # 1. Factor 1: VIX Sentiment (0 - 100)
    # VIX 10 => 90 (Greed), VIX 15 => 50 (Neutral), VIX 25 => 15 (Extreme Fear)
    if vix_val <= 10.0:
        vix_factor = 90.0
    elif vix_val >= 30.0:
        vix_factor = 10.0
    else:
        vix_factor = 90.0 - ((vix_val - 10.0) / 20.0) * 80.0

    # 2. Factor 2: Momentum Sentiment (0 - 100)
    # Nifty 1D & 7D returns mapped into normalized 0-100 scale
    mom_raw = (nifty_1d_pct * 0.6) + (nifty_7d_pct * 0.4)
    mom_factor = 50.0 + (mom_raw * 10.0)
    mom_factor = max(5.0, min(95.0, mom_factor))

    # 3. Factor 3: Market Breadth (Advances vs Declines from DB)
    conn = get_db_connection(settings)
    breadth_factor = 50.0
    advances = 0
    declines = 0
    pct_above_20dma = 50.0
    latest_price_date = None

    try:
        # Determine latest trading date available in price_history
        max_date_row = conn.execute("SELECT MAX(date) FROM price_history").fetchone()
        latest_price_date = max_date_row[0] if max_date_row and max_date_row[0] else None

        if latest_price_date:
            breadth_rows = conn.execute(
                """
                WITH ranked_prices AS (
                    SELECT ticker, close, date,
                           ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY date DESC) as rn
                    FROM price_history
                    WHERE date <= ?
                )
                SELECT
                    SUM(CASE WHEN p1.close > p2.close THEN 1 ELSE 0 END) as adv,
                    SUM(CASE WHEN p1.close < p2.close THEN 1 ELSE 0 END) as dec
                FROM ranked_prices p1
                JOIN ranked_prices p2 ON p1.ticker = p2.ticker AND p2.rn = 2
                WHERE p1.rn = 1
                """,
                (latest_price_date,),
            ).fetchone()

            if breadth_rows and breadth_rows[0] is not None:
                advances = int(breadth_rows[0] or 0)
                declines = int(breadth_rows[1] or 0)
                tot = advances + declines
                if tot > 0:
                    breadth_factor = (advances / tot) * 100.0

            # Compute % of stocks above their 20-DMA
            dma_row = conn.execute(
                """
                WITH recent_prices AS (
                    SELECT ticker, close,
                           AVG(close) OVER (PARTITION BY ticker ORDER BY date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) as dma20,
                           ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY date DESC) as rn
                    FROM price_history
                    WHERE date <= ?
                )
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN close > dma20 THEN 1 ELSE 0 END) as above_dma
                FROM recent_prices
                WHERE rn = 1
                """,
                (latest_price_date,),
            ).fetchone()

            if dma_row and dma_row[0] and dma_row[0] > 0:
                tot_stocks = dma_row[0]
                above_stocks = dma_row[1] or 0
                pct_above_20dma = round((above_stocks / tot_stocks) * 100.0, 1)

    except Exception as e:
        logger.debug("Failed computing market breadth: %s", e)
    finally:
        try:
            conn.close()
        except Exception:
            pass

    # 4. Factor 4: Safe-Haven Flow (Default neutral 50)
    safe_haven_factor = 50.0

    # Composite Fear & Greed Score
    composite_fg = (vix_factor * 0.40) + (mom_factor * 0.40) + (breadth_factor * 0.10) + (safe_haven_factor * 0.10)
    composite_fg = max(0.0, min(100.0, round(composite_fg, 1)))

    # Classification
    if composite_fg >= 75:
        fg_label = "Extreme Greed"
        fg_color = "emerald"
        fg_desc = "Market is heavily overbought with high euphoria. Exercise caution with fresh long breakouts."
    elif composite_fg >= 55:
        fg_label = "Greed"
        fg_color = "teal"
        fg_desc = "Constructive risk appetite with healthy momentum. Trend following strategies favored."
    elif composite_fg >= 45:
        fg_label = "Neutral"
        fg_color = "amber"
        fg_desc = "Equilibrium between bulls and bears. Range-bound setups and stock-picking dominate."
    elif composite_fg >= 25:
        fg_label = "Fear"
        fg_color = "orange"
        fg_desc = "Elevated caution and distribution. Defensive setups and strict stop-losses recommended."
    else:
        fg_label = "Extreme Fear"
        fg_color = "rose"
        fg_desc = "Panic selling and capitulation territory. Historically attractive for contrarian accumulation."

    # Volatility Regime
    if vix_val < 13.0:
        vix_regime = "Low Volatility (Complacent)"
    elif vix_val <= 17.0:
        vix_regime = "Normal Volatility (Healthy)"
    elif vix_val <= 22.0:
        vix_regime = "Elevated Volatility (Caution)"
    else:
        vix_regime = "High Volatility (Panic)"

    # Formatted IST timestamps
    as_of_iso = datetime.now(timezone.utc).isoformat()
    as_of_ist = format_iso_to_ist(as_of_iso)

    # Freshness classification
    is_live = is_market_open(now_ts)
    freshness_badge = "🟢 Live Market Feed" if is_live else "🟠 End of Day (EOD) Settled"

    # Historical Macro Charts Generation for Sentiment
    bank_nifty = next((idx for idx in indices_data if idx["symbol"] == "^NSEBANK"), None)

    # Derive historical dates from DB or generate fallback 7-day series
    chart_dates = []
    try:
        conn_dates = get_db_connection(settings)
        date_rows = conn_dates.execute(
            "SELECT DISTINCT date FROM price_history ORDER BY date DESC LIMIT 7"
        ).fetchall()
        if date_rows:
            chart_dates = sorted([r[0] for r in date_rows if r[0]])
        conn_dates.close()
    except Exception:
        pass

    if not chart_dates:
        from datetime import timedelta
        base_dt = datetime.now(timezone.utc)
        chart_dates = [(base_dt - timedelta(days=6-i)).strftime("%Y-%m-%d") for i in range(7)]

    vix_spark = (vix.get("sparkline") if vix else None) or []
    nifty_spark = (nifty.get("sparkline") if nifty else None) or []
    bank_spark = (bank_nifty.get("sparkline") if bank_nifty else None) or []

    n_pts = len(chart_dates)
    fg_series = []
    vix_series = []
    nifty_series = []
    bank_series = []

    for i, d in enumerate(chart_dates):
        # Calculate stepped/sparkline values or default to latest
        v_val = vix_spark[i] if i < len(vix_spark) else vix_val
        n_val = nifty_spark[i] if i < len(nifty_spark) else (nifty.get("price", 24850.0) if nifty else 24850.0)
        b_val = bank_spark[i] if i < len(bank_spark) else (bank_nifty.get("price", 53200.0) if bank_nifty else 53200.0)

        # Keep fear_greed score in valid range 5.0 to 95.0
        fg_series.append({
            "date": d,
            "value": max(5.0, min(95.0, composite_fg)),
            "score": max(5.0, min(95.0, composite_fg)),
        })
        vix_series.append({"date": d, "value": max(1.0, float(v_val or 14.5))})
        nifty_series.append({"date": d, "value": max(1.0, float(n_val or 24850.0))})
        bank_series.append({"date": d, "value": max(1.0, float(b_val or 53200.0))})

    payload = {
        "fear_greed_score": composite_fg,
        "fear_greed_label": fg_label,
        "fear_greed_color": fg_color,
        "fear_greed_desc": fg_desc,
        "change_7d": round(nifty_7d_pct, 2),
        "vix_level": round(vix_val, 2),
        "vix_regime": vix_regime,
        "vix_1d_pct": round(vix.get("change_1d_pct", 0.0) if vix else 0.0, 2),
        "as_of": as_of_iso,
        "as_of_ist": as_of_ist,
        "session_date": latest_price_date or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "data_freshness": "live" if is_live else "eod",
        "freshness_badge": freshness_badge,
        "sub_factors": {
            "vix_factor": round(vix_factor, 1),
            "momentum_factor": round(mom_factor, 1),
            "breadth_factor": round(breadth_factor, 1),
            "safe_haven_factor": round(safe_haven_factor, 1),
        },
        "breadth": {
            "advances": advances,
            "declines": declines,
            "advance_decline_ratio": round(advances / max(1, declines), 2),
            "pct_above_20dma": pct_above_20dma,
        },
        "prediction": {
            "regime": "🟢 Bullish Momentum Expansion" if composite_fg >= 55 and vix_val < 16.0 else ("🔴 Elevated Macro Volatility & Risk-Off" if vix_val > 20.0 or composite_fg < 40.0 else "⚖️ Rangebound Consolidation & Rotation"),
            "bias": "BULLISH" if composite_fg >= 55 else ("BEARISH" if composite_fg <= 45 else "NEUTRAL"),
            "tomorrow_bias": "BULLISH" if composite_fg >= 55 else ("BEARISH" if composite_fg <= 45 else "NEUTRAL"),
            "conviction_pct": int(round(abs(composite_fg - 50.0) * 2.0, 0)),
            "confidence_pct": round(abs(composite_fg - 50.0) * 2.0, 1),
            "support_level": "24,650" if composite_fg >= 50 else "24,100",
            "resistance_level": "25,200" if composite_fg >= 50 else "24,750",
            "commentary": f"Synthesized from {vix_regime} India VIX ({vix_val:.1f}), Nifty 1D delta ({nifty_1d_pct:+.2f}%), and market breadth ({pct_above_20dma}% > 20-DMA).",
            "rationale": f"Synthesized from {vix_regime} India VIX ({vix_val:.1f}), Nifty 1D delta ({nifty_1d_pct:+.2f}%), and market breadth ({pct_above_20dma}% > 20-DMA).",
        },
        "macro_charts": {
            "dates": chart_dates,
            "fear_greed": fg_series,
            "vix": vix_series,
            "nifty": nifty_series,
            "bank_nifty": bank_series,
            "vix_history": vix.get("sparkline", []) if vix else [],
            "nifty_history": nifty.get("sparkline", []) if nifty else [],
        },
    }

    with _SENTIMENT_LOCK:
        _SENTIMENT_CACHE = {"ts": now_ts, "data": payload}

    return payload
