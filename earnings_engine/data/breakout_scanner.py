"""Breakout Radar — Tiered Async Pooling Scanner & Scoring Engine.

Architecture: Three-tier graduated pool system that avoids rescanning the
entire universe every cycle.  Stocks are promoted/demoted between tiers
based on their breakout conviction score, with higher-conviction candidates
receiving more frequent rescoring.

Tiers
-----
- **T0 (Cold)** — Full universe scan every ``COLD_INTERVAL_MIN`` (default 60 min).
  Discovers new candidates and feeds them into T1/T2.
- **T1 (Warm)** — Rescored every ``WARM_INTERVAL_MIN`` (default 15 min).
  Stocks with ``composite_score ≥ WARM_THRESHOLD`` (25).
- **T2 (Hot)** — Rescored every ``HOT_INTERVAL_MIN`` (default 5 min).
  Stocks within striking distance of breakout: ``composite_score ≥ HOT_THRESHOLD``
  (50), or ``pct_from_high ≥ -5%``, or ``volume_ratio ≥ 1.5×``.

Demotion requires **two consecutive** low scores to prevent flicker from
a single noisy bar.  Volume-spike fast-tracking immediately promotes any
stock with ``volume_ratio ≥ 1.5×`` into the Hot pool.

Score Components (0 – 100)
--------------------------
1. Resistance Proximity  (0-30 pts) — price within 0-5% below the 20D / 52W high
2. Volume Surge          (0-20 pts) — today's volume vs 20D average
3. Price Compression     (0-15 pts) — ATR(14)/price squeeze (low volatility = coiling)
4. Momentum              (0-15 pts) — 30D return > 0 and price > 20D SMA
5. Fundamental Bonus     (0-20 pts) — earnings quality score (q1/q2/q3 avg, normalised)

Minimum score to appear in API results: BREAKOUT_MIN_SCORE (default 35).
"""

from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from earnings_engine.config import Settings
from earnings_engine.logging_utils import get_logger

logger = get_logger("earnings_engine.data.breakout_scanner")

# ---------------------------------------------------------------------------
# Configuration (overridable via environment variables)
# ---------------------------------------------------------------------------
BREAKOUT_MIN_SCORE: int = int(os.environ.get("BREAKOUT_MIN_SCORE", "35"))
BREAKOUT_MAX_CANDIDATES: int = int(os.environ.get("BREAKOUT_MAX_CANDIDATES", "100"))

# Tier thresholds
HOT_THRESHOLD: int = int(os.environ.get("BREAKOUT_HOT_THRESHOLD", "50"))
WARM_THRESHOLD: int = int(os.environ.get("BREAKOUT_WARM_THRESHOLD", "25"))
HOT_DEMOTION_THRESHOLD: int = int(os.environ.get("BREAKOUT_HOT_DEMOTION", "25"))
WARM_DEMOTION_THRESHOLD: int = int(os.environ.get("BREAKOUT_WARM_DEMOTION", "15"))

# Scan intervals (minutes)
COLD_INTERVAL_MIN: int = int(os.environ.get("BREAKOUT_COLD_INTERVAL_MIN", "60"))
WARM_INTERVAL_MIN: int = int(os.environ.get("BREAKOUT_WARM_INTERVAL_MIN", "15"))
HOT_INTERVAL_MIN: int = int(os.environ.get("BREAKOUT_HOT_INTERVAL_MIN", "5"))

# Legacy compat alias
BREAKOUT_SCAN_INTERVAL_MIN: int = COLD_INTERVAL_MIN

# ---------------------------------------------------------------------------
# Tiered in-memory pool
# ---------------------------------------------------------------------------
_pool: dict[str, Any] = {
    "hot": {},               # ticker → {"result": dict, "consecutive_low": 0}
    "warm": {},              # ticker → {"result": dict, "consecutive_low": 0}
    "candidates": [],        # merged sorted list for API (score ≥ BREAKOUT_MIN_SCORE)
    "last_cold_scan_at": None,
    "last_warm_scan_at": None,
    "last_hot_scan_at": None,
    "last_scan_at": None,    # most recent of any tier (compat)
    "last_scan_duration_s": 0.0,
    "cold_tickers_scanned": 0,
    "hot_count": 0,
    "warm_count": 0,
    "status": "idle",        # "idle" | "running" | "done" | "error"
    "error": None,
}

# Legacy compat alias
_cache = _pool


def _rebuild_candidates() -> None:
    """Merge hot + warm pools into a deduplicated, sorted candidates list."""
    merged: dict[str, dict] = {}
    for ticker, entry in _pool["hot"].items():
        merged[ticker] = entry["result"]
    for ticker, entry in _pool["warm"].items():
        if ticker not in merged:
            merged[ticker] = entry["result"]

    candidates = [r for r in merged.values() if r.get("composite_score", 0) >= BREAKOUT_MIN_SCORE]
    candidates.sort(key=lambda x: x.get("composite_score", 0), reverse=True)
    _pool["candidates"] = candidates[:BREAKOUT_MAX_CANDIDATES]
    _pool["hot_count"] = len(_pool["hot"])
    _pool["warm_count"] = len(_pool["warm"])


def _should_be_hot(result: dict) -> bool:
    """Check if a scored result qualifies for the Hot pool."""
    if result.get("composite_score", 0) >= HOT_THRESHOLD:
        return True
    pct = result.get("pct_from_high")
    if pct is not None and pct >= -5:
        return True
    vol = result.get("volume_ratio")
    if vol is not None and vol >= 1.5:
        return True
    return False


def _promote(ticker: str, result: dict) -> None:
    """Place a ticker into the correct tier based on its score."""
    if _should_be_hot(result):
        _pool["hot"][ticker] = {"result": result, "consecutive_low": 0}
        _pool["warm"].pop(ticker, None)
    elif result.get("composite_score", 0) >= WARM_THRESHOLD:
        if ticker not in _pool["hot"]:
            _pool["warm"][ticker] = {"result": result, "consecutive_low": 0}
    # Below warm threshold: don't add to any pool


def _demote_hot(ticker: str) -> None:
    """Demote a Hot ticker: increment consecutive_low, remove after 2 strikes."""
    entry = _pool["hot"].get(ticker)
    if not entry:
        return
    entry["consecutive_low"] += 1
    if entry["consecutive_low"] >= 2:
        result = entry["result"]
        del _pool["hot"][ticker]
        # Maybe keep in warm if score still qualifies
        if result.get("composite_score", 0) >= WARM_THRESHOLD:
            _pool["warm"][ticker] = {"result": result, "consecutive_low": 0}
            logger.debug("[BREAKOUT] %s demoted Hot → Warm (score %.1f)", ticker, result.get("composite_score", 0))
        else:
            logger.debug("[BREAKOUT] %s demoted Hot → Cold (score %.1f)", ticker, result.get("composite_score", 0))


def _demote_warm(ticker: str) -> None:
    """Demote a Warm ticker: increment consecutive_low, remove after 2 strikes."""
    entry = _pool["warm"].get(ticker)
    if not entry:
        return
    entry["consecutive_low"] += 1
    if entry["consecutive_low"] >= 2:
        logger.debug("[BREAKOUT] %s demoted Warm → Cold (score %.1f)", ticker, entry["result"].get("composite_score", 0))
        del _pool["warm"][ticker]


# ---------------------------------------------------------------------------
# Public API (backward-compatible)
# ---------------------------------------------------------------------------

def get_cached_scan_results(
    universe: str | None = None,
    settings: Settings | None = None,
    asof_date: str | None = None,
) -> list[dict[str, Any]]:
    """Return breakout candidates, optionally filtered by universe and point-in-time as-of date."""
    settings = settings or Settings()
    if asof_date:
        return run_breakout_scan(settings, universe=universe, asof_date=asof_date)

    all_candidates = list(_pool["candidates"])
    if not universe or universe.lower() in ("all", "any", "global", "monitored"):
        return all_candidates

    # Filter candidates by the requested universe / watchlist
    try:
        from earnings_engine.data.universe import load_universe
        from earnings_engine.data.watchlists import get_watchlist

        u_clean = universe.lower().strip()
        uni_tickers: set[str] = set()
        if u_clean in ("nifty_50", "nifty50", "nifty_top_50", "nse_top", "in", "nse"):
            uni_tickers = set(load_universe("NSE_TOP", settings) or load_universe("NIFTY_50", settings) or [])
        elif u_clean == "nse_large_cap":
            uni_tickers = set(load_universe("NSE_LARGE_CAP", settings) or [])
        elif u_clean in ("us_top", "us"):
            uni_tickers = set(load_universe("US_TOP", settings) or [])
        else:
            # Check custom watchlist
            wl_tickers = get_watchlist(universe, settings)
            if wl_tickers:
                uni_tickers = set(wl_tickers)
            else:
                uni_tickers = set(load_universe(universe, settings) or [])

        if uni_tickers:
            uni_normalized = {t.upper() for t in uni_tickers}
            return [c for c in all_candidates if c.get("ticker", "").upper() in uni_normalized]
    except Exception as e:
        logger.debug("[BREAKOUT] Error filtering by universe %s: %s", universe, e)

    return all_candidates


def get_scan_status(universe: str | None = None) -> dict[str, Any]:
    """Return a lightweight status dict for the API."""
    return {
        "status": _pool["status"],
        "last_scan_at": _pool["last_scan_at"],
        "last_cold_scan_at": _pool["last_cold_scan_at"],
        "last_warm_scan_at": _pool["last_warm_scan_at"],
        "last_hot_scan_at": _pool["last_hot_scan_at"],
        "last_scan_duration_s": _pool["last_scan_duration_s"],
        "cold_tickers_scanned": _pool["cold_tickers_scanned"],
        "hot_count": _pool["hot_count"],
        "warm_count": _pool["warm_count"],
        "candidates_found": len(_pool["candidates"]),
        "universe": universe or "ALL",
        "min_score": BREAKOUT_MIN_SCORE,
        "scan_intervals": {
            "cold_min": COLD_INTERVAL_MIN,
            "warm_min": WARM_INTERVAL_MIN,
            "hot_min": HOT_INTERVAL_MIN,
        },
        "error": _pool["error"],
    }


# ---------------------------------------------------------------------------
# Scoring helpers (unchanged from original)
# ---------------------------------------------------------------------------

def _score_resistance_proximity(closes: pd.Series) -> tuple[float, float]:
    """Return (score 0-30, pct_from_high).

    Points awarded based on how close current price is to the recent high.
    Closer = higher score.  Being above high = breakout already = also high.
    """
    if len(closes) < 2:
        return 0.0, float("nan")
    current = float(closes.iloc[-1])
    window = min(len(closes), 252)   # up to 1 year
    high = float(closes.tail(window).max())
    if high <= 0:
        return 0.0, float("nan")
    pct_from_high = (current - high) / high * 100  # negative = below high
    # -5% to 0% → 20-30 pts.  0% to +3% (breakout) → 25-30 pts.  Below -5% → 0
    if pct_from_high >= 0:           # above or at high (breakout)
        score = 30.0
    elif pct_from_high >= -1:
        score = 28.0
    elif pct_from_high >= -2:
        score = 24.0
    elif pct_from_high >= -3:
        score = 20.0
    elif pct_from_high >= -5:
        score = 14.0
    elif pct_from_high >= -8:
        score = 7.0
    else:
        score = 0.0
    return score, pct_from_high


def _score_volume_surge(volumes: pd.Series) -> tuple[float, float]:
    """Return (score 0-20, vol_ratio).

    Vol today vs 20D avg.  Ratio ≥ 2× → full 20 pts.
    """
    if len(volumes) < 5:
        return 0.0, float("nan")
    avg_20 = float(volumes.tail(21).iloc[:-1].mean()) if len(volumes) >= 21 else float(volumes.mean())
    today = float(volumes.iloc[-1])
    if avg_20 <= 0:
        return 0.0, float("nan")
    ratio = today / avg_20
    if ratio >= 2.0:
        score = 20.0
    elif ratio >= 1.5:
        score = 15.0
    elif ratio >= 1.2:
        score = 8.0
    elif ratio >= 1.0:
        score = 3.0
    else:
        score = 0.0
    return score, round(ratio, 2)


def _score_price_compression(closes: pd.Series) -> tuple[float, float]:
    """Return (score 0-15, atr_pct).

    ATR(14) / price.  Low ratio = price coiling = potential energy.
    """
    if len(closes) < 15:
        return 0.0, float("nan")
    # Approximate ATR using rolling 14D true range on close-only data
    daily_range = closes.pct_change().abs()
    atr_pct = float(daily_range.tail(14).mean()) * 100   # as % of price
    if atr_pct <= 0:
        return 0.0, float("nan")
    if atr_pct < 0.5:
        score = 15.0
    elif atr_pct < 1.0:
        score = 12.0
    elif atr_pct < 1.5:
        score = 8.0
    elif atr_pct < 2.5:
        score = 4.0
    else:
        score = 0.0
    return score, round(atr_pct, 3)


def _score_momentum(closes: pd.Series) -> tuple[float, str]:
    """Return (score 0-15, signal).

    30D return > 0 AND price > 20D SMA → strong momentum.
    """
    if len(closes) < 20:
        return 0.0, "insufficient"
    current = float(closes.iloc[-1])
    sma_20 = float(closes.tail(20).mean())
    ret_30 = float((closes.iloc[-1] / closes.iloc[max(0, len(closes) - 31)]) - 1) * 100

    above_sma = current > sma_20
    positive_momentum = ret_30 > 0

    if above_sma and positive_momentum and ret_30 > 5:
        score, signal = 15.0, "Strong"
    elif above_sma and positive_momentum:
        score, signal = 10.0, "Moderate"
    elif above_sma or positive_momentum:
        score, signal = 5.0, "Weak"
    else:
        score, signal = 0.0, "None"
    return score, signal


def _score_fundamental(quality_scores: list[float | None]) -> tuple[float, float]:
    """Return (score 0-20, avg_quality).

    Takes a list of quality scores (each 1-9) from q1/q2/q3 earnings history.
    Normalised: avg=9 → 20 pts, avg=1 → 0 pts.
    """
    valid = [q for q in quality_scores if q is not None and not (isinstance(q, float) and np.isnan(q))]
    if not valid:
        return 0.0, float("nan")
    avg_q = float(np.mean(valid))
    score = round((avg_q - 1) / 8 * 20, 1)   # map [1,9] → [0,20]
    return max(0.0, min(20.0, score)), round(avg_q, 2)


# ---------------------------------------------------------------------------
# Per-ticker scorer
# ---------------------------------------------------------------------------

def score_breakout(
    ticker: str,
    prices_df: pd.DataFrame,
    quality_scores: list[float | None] | None = None,
    asof_date: str | None = None,
) -> dict[str, Any] | None:
    """Score a single ticker point-in-time, and compute realized breakout outcomes.

    ``prices_df`` must have at least a ``close`` column (and optionally ``high``, ``low``, ``volume``).
    """
    if prices_df is None or prices_df.empty:
        return None

    df = prices_df.copy()
    if not isinstance(df.index, pd.DatetimeIndex):
        try:
            df.index = pd.to_datetime(df.index)
        except Exception:
            pass

    df = df.sort_index()

    # Point-in-time slicing
    if asof_date:
        asof_clean = str(asof_date).strip()[:10]
        hist_df = df.loc[df.index <= asof_clean]
        future_df = df.loc[df.index > asof_clean]
    else:
        hist_df = df
        future_df = pd.DataFrame()

    if hist_df.empty:
        return None

    # Ensure numeric close series
    closes = pd.to_numeric(hist_df["close"], errors="coerce").dropna()
    if len(closes) < 10:
        return None

    signal_date = str(hist_df.index[-1])[:10]
    signal_price = float(closes.iloc[-1])

    # Volume (optional)
    if "volume" in hist_df.columns:
        volumes = pd.to_numeric(hist_df["volume"], errors="coerce").fillna(0)
        volumes = volumes.reindex(closes.index, fill_value=0)
    else:
        volumes = pd.Series(dtype=float)

    # --- Sub-scores ---
    res_score, pct_from_high = _score_resistance_proximity(closes)
    vol_score, vol_ratio = _score_volume_surge(volumes) if len(volumes) >= 5 else (0.0, float("nan"))
    comp_score, atr_pct = _score_price_compression(closes)
    mom_score, momentum_signal = _score_momentum(closes)
    fund_score, avg_quality = _score_fundamental(quality_scores or [])

    composite = round(res_score + vol_score + comp_score + mom_score + fund_score, 1)

    # Calculate Breakout Levels
    window = min(len(hist_df), 252)
    high_series = pd.to_numeric(hist_df["high"], errors="coerce") if "high" in hist_df.columns else pd.to_numeric(hist_df["close"], errors="coerce")
    resistance_high = float(high_series.tail(window).max())
    breakout_trigger = round(resistance_high, 2)

    atr_pct_val = atr_pct if (atr_pct is not None and not np.isnan(atr_pct)) else 2.0
    atr_val = signal_price * (atr_pct_val / 100.0)
    target_price = round(max(breakout_trigger * 1.08, breakout_trigger + 2.0 * atr_val), 2)
    stop_loss = round(min(signal_price * 0.95, signal_price - 1.5 * atr_val), 2)

    # Current / Latest Market Data
    all_closes = pd.to_numeric(df["close"], errors="coerce").dropna()
    current_price = float(all_closes.iloc[-1])
    current_date = str(df.index[-1])[:10]

    # Evaluate Outcome (Did Breakout Happen?)
    if not future_df.empty and signal_date != current_date:
        f_highs = pd.to_numeric(future_df["high"], errors="coerce") if "high" in future_df.columns else pd.to_numeric(future_df["close"], errors="coerce")
        f_lows = pd.to_numeric(future_df["low"], errors="coerce") if "low" in future_df.columns else pd.to_numeric(future_df["close"], errors="coerce")
        post_high = float(f_highs.max()) if not f_highs.empty else signal_price
        post_low = float(f_lows.min()) if not f_lows.empty else signal_price

        realized_return_pct = round(((current_price - signal_price) / signal_price) * 100, 2)
        max_gain_pct = round(((post_high - signal_price) / signal_price) * 100, 2)
        days_elapsed = len(future_df)

        if post_high >= target_price:
            breakout_happened = True
            outcome = "TARGET_HIT"
            outcome_label = f"Target Hit 🎯 (+{max_gain_pct}%)"
            outcome_badge = "emerald"
        elif post_high >= breakout_trigger:
            breakout_happened = True
            if current_price >= signal_price:
                outcome = "BREAKOUT_SUCCEEDED"
                outcome_label = f"Breakout Succeeded ✅ ({realized_return_pct:+0.1f}%)"
                outcome_badge = "emerald"
            else:
                outcome = "BREAKOUT_RETRACED"
                outcome_label = f"Breakout Retraced ⚠️ ({realized_return_pct:+0.1f}%)"
                outcome_badge = "amber"
        elif post_low <= stop_loss:
            breakout_happened = False
            outcome = "STOP_LOSS_HIT"
            outcome_label = f"Stop Loss Hit 🛑 ({realized_return_pct:+0.1f}%)"
            outcome_badge = "rose"
        else:
            breakout_happened = False
            outcome = "NO_BREAKOUT"
            outcome_label = f"Failed / In Range ❌ ({realized_return_pct:+0.1f}%)"
            outcome_badge = "slate"
    else:
        breakout_happened = None
        outcome = "PENDING"
        outcome_label = "Pending Breakout ⏳"
        outcome_badge = "blue"
        realized_return_pct = 0.0
        max_gain_pct = None
        days_elapsed = 0
        post_high = signal_price

    # Mathematical Calculation & Reasoning Notes
    res_note = (
        f"Price ₹{signal_price:,.2f} is {pct_from_high:+.1f}% from 52W/recent high of ₹{resistance_high:,.2f} (awarding {res_score:.1f}/30 pts for proximity)"
        if not (isinstance(pct_from_high, float) and np.isnan(pct_from_high)) else "Insufficient price range data."
    )
    vol_note = (
        f"Latest volume is {vol_ratio:.2f}× the 20-day baseline average (awarding {vol_score:.1f}/20 pts for institutional participation)"
        if not (isinstance(vol_ratio, float) and np.isnan(vol_ratio)) else "Volume in line with 20D average (0/20 pts)."
    )
    comp_note = (
        f"ATR(14) is {atr_pct:.2f}% of price, indicating {'tight energy coiling & volatility compression' if (atr_pct or 0) < 1.5 else 'moderate volatility'} (awarding {comp_score:.1f}/15 pts)"
        if not (isinstance(atr_pct, float) and np.isnan(atr_pct)) else "Normal price volatility."
    )
    mom_note = f"Momentum signal is '{momentum_signal}' based on 30D return & 20D SMA trend posture (awarding {mom_score:.1f}/15 pts)"
    fund_note = (
        f"Historical quarterly earnings quality averages {avg_quality:.1f}/9 (awarding {fund_score:.1f}/20 pts fundamental bonus)"
        if not (isinstance(avg_quality, float) and np.isnan(avg_quality)) else "No quarterly quality history (0/20 pts)."
    )

    # Setup Archetype
    if (pct_from_high is not None and pct_from_high >= -1.5) and (vol_ratio is not None and vol_ratio >= 1.5):
        archetype = "🔥 High-Volume 52W Breakout"
    elif comp_score >= 12 and res_score >= 20:
        archetype = "🗜️ Coiling Resistance Squeeze"
    elif vol_ratio is not None and vol_ratio >= 1.8:
        archetype = "📊 Institutional Accumulation Surge"
    elif mom_score >= 10:
        archetype = "🚀 Trend Continuation Breakout"
    else:
        archetype = "📈 Resistance Approach Coil"

    risk_reward_ratio = round((target_price - signal_price) / max(0.01, (signal_price - stop_loss)), 2)

    calculation_notes = {
        "setup_archetype": archetype,
        "risk_reward_ratio": risk_reward_ratio,
        "resistance_reasoning": res_note,
        "volume_reasoning": vol_note,
        "compression_reasoning": comp_note,
        "momentum_reasoning": mom_note,
        "fundamental_reasoning": fund_note,
        "formula_summary": f"Score {composite}/100 = Res({res_score:.0f}) + Vol({vol_score:.0f}) + Squeeze({comp_score:.0f}) + Mom({mom_score:.0f}) + Fund({fund_score:.0f})",
    }

    return {
        "ticker": ticker,
        "signal_date": signal_date,
        "signal_price": round(signal_price, 2),
        "predicted_value": round(signal_price, 2),
        "breakout_trigger": breakout_trigger,
        "target_price": target_price,
        "stop_loss": stop_loss,
        "risk_reward_ratio": risk_reward_ratio,
        "setup_archetype": archetype,
        "calculation_notes": calculation_notes,
        "current_price": round(current_price, 2),
        "current_date": current_date,
        "realized_return_pct": realized_return_pct,
        "max_gain_pct": max_gain_pct,
        "breakout_happened": breakout_happened,
        "outcome": outcome,
        "outcome_label": outcome_label,
        "outcome_badge": outcome_badge,
        "days_elapsed": days_elapsed,
        "composite_score": composite,
        "resistance_score": res_score,
        "volume_score": vol_score,
        "compression_score": comp_score,
        "momentum_score": mom_score,
        "fundamental_score": fund_score,
        "pct_from_high": round(pct_from_high, 2) if not (isinstance(pct_from_high, float) and np.isnan(pct_from_high)) else None,
        "volume_ratio": vol_ratio if not (isinstance(vol_ratio, float) and np.isnan(vol_ratio)) else None,
        "atr_pct": atr_pct if not (isinstance(atr_pct, float) and np.isnan(atr_pct)) else None,
        "momentum_signal": momentum_signal,
        "avg_quality_score": avg_quality if not (isinstance(avg_quality, float) and np.isnan(avg_quality)) else None,
        "data_points": len(closes),
        "scanned_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Local Ollama Multi-Model AI Reasoning Engine
# ---------------------------------------------------------------------------

_AI_REASONING_CACHE: dict[str, dict[str, Any]] = {}


def generate_breakout_ai_reasoning(
    ticker: str,
    model_name: str | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Generate multi-model AI reasoning for a breakout candidate using local Ollama models.

    Supports:
    - `llama3.2:3b` (Fast local consensus)
    - `deepseek-r1:8b` (Deep chain-of-thought institutional reasoning)
    - `qwen2.5-coder:latest` (Algorithmic technical validation)
    """
    sym = ticker.strip().upper()
    settings = settings or Settings()

    # Check in-memory cache
    cache_key = f"{sym}_{model_name or 'default'}"
    if cache_key in _AI_REASONING_CACHE:
        return _AI_REASONING_CACHE[cache_key]

    # Get scored candidate details
    from earnings_engine.data.prices import load_prices, load_price_metrics
    prices_df = load_prices(sym, settings)
    metrics = load_price_metrics(sym, settings) or {}
    company_name = metrics.get("company_name") or sym
    industry = metrics.get("industry") or metrics.get("sector") or "—"

    quality_scores = [
        float(metrics.get(k)) if metrics.get(k) is not None else None
        for k in ("q1_earnings_score", "q2_earnings_score", "q3_earnings_score")
    ]
    scored = score_breakout(sym, prices_df, quality_scores) or {}

    notes = scored.get("calculation_notes", {})
    target = scored.get("target_price", 0)
    stop = scored.get("stop_loss", 0)
    trigger = scored.get("breakout_trigger", 0)
    cur_p = scored.get("current_price", 0)
    score = scored.get("composite_score", 0)
    archetype = scored.get("setup_archetype", "Breakout Coil")

    # Construct quantitative prompt
    prompt = f"""You are an elite quantitative trading analyst specializing in breakout pattern recognition and price action momentum.
Evaluate the following breakout setup for {sym} ({company_name}) and provide an institutional opinion.

### Setup Metrics:
- Ticker: {sym} | Industry: {industry}
- Setup Archetype: {archetype}
- Composite Breakout Score: {score}/100
- Current Price: ₹{cur_p}
- Breakout Trigger (Resistance): ₹{trigger} ({scored.get('pct_from_high', 0):+.1f}% from high)
- Upside Target Price: ₹{target}
- Invalidation Stop Loss: ₹{stop}
- Risk/Reward Ratio: {scored.get('risk_reward_ratio', 2.0)} : 1
- Volume Surge: {scored.get('volume_ratio', 1.0)}x of 20D average
- Price Compression (ATR %): {scored.get('atr_pct', 2.0)}%
- Momentum Signal: {scored.get('momentum_signal', 'Moderate')}
- Earnings Quality (1-9): {scored.get('avg_quality_score', 'N/A')}

### Instructions:
1. Explain whether this breakout has genuine institutional volume accumulation or fakeout/exhaustion risk.
2. Outline key execution game plan (Entry confirmation, trailing stop, target scaling).
3. Output strict JSON adhering to this schema:
{{
  "verdict": "HIGH_CONVICTION_BREAKOUT",
  "confidence_pct": 82,
  "model_used": "{model_name or 'Ollama'}",
  "accumulation_analysis": "2-3 sentences evaluating the volume surge and price coiling.",
  "fakeout_risk_assessment": "Key vulnerability or fakeout warning signs to monitor.",
  "execution_plan": "Specific entry trigger, stop loss discipline, and target level.",
  "key_reasons": ["Reason 1", "Reason 2", "Reason 3"]
}}
"""

    model_to_use = model_name or os.getenv("OLLAMA_MODEL", "llama3.2:3b")
    ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434")

    output_dict: dict[str, Any] | None = None

    # 1. Try Local Ollama
    try:
        import urllib.request
        data_payload = json.dumps({
            "model": model_to_use,
            "prompt": prompt,
            "stream": False,
            "format": "json",
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{ollama_host}/api/generate",
            data=data_payload,
            headers={"Content-Type": "application/json"},
        )
        # Timeout: 45s for 8B deepseek, 15s for 3b
        timeout = 45 if "8b" in model_to_use.lower() or "deepseek" in model_to_use.lower() else 18
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw_res = json.loads(resp.read().decode("utf-8"))
            resp_text = raw_res.get("response", "")
            m = re.search(r"\{[\s\S]*\}", resp_text)
            if m:
                output_dict = json.loads(m.group(0))
                output_dict["source"] = f"Local Ollama ({model_to_use})"
    except Exception as e:
        logger.debug("[BREAKOUT-AI] Local Ollama call (%s) failed/timed out: %s", model_to_use, e)

    # 2. Rule-based Institutional Fallback if local model unavailable
    if not output_dict:
        vol_r = scored.get("volume_ratio") or 1.0
        pct_h = scored.get("pct_from_high") or -3.0
        is_high_conviction = score >= 60 and vol_r >= 1.3 and pct_h >= -3.0

        verdict = "HIGH_CONVICTION_BREAKOUT" if is_high_conviction else ("POTENTIAL_BREAKOUT_COIL" if score >= 40 else "WATCHLIST_SETUP")
        conf = min(92, max(60, int(score * 0.9 + (vol_r * 5))))

        output_dict = {
            "verdict": verdict,
            "confidence_pct": conf,
            "model_used": "Institutional Quantitative Rule Engine",
            "source": "Quantitative Synthesis",
            "accumulation_analysis": (
                f"{sym} displays {vol_r:.2f}× volume surge alongside an ATR compression of {scored.get('atr_pct', 1.5):.2f}%, "
                f"indicating tight price energy coiled directly under key resistance at ₹{trigger:,.2f}."
            ),
            "fakeout_risk_assessment": (
                f"Watch for rejection at ₹{trigger:,.2f} on declining volume. Stop loss is strictly placed at ₹{stop:,.2f} "
                f"to protect capital against false breakouts."
            ),
            "execution_plan": (
                f"Enter on confirmed hourly close above ₹{trigger:,.2f}. Scale out 50% at initial target ₹{target:,.2f}, "
                f"and trail remaining position using 20D SMA."
            ),
            "key_reasons": [
                notes.get("resistance_reasoning", f"Within {pct_h:+.1f}% of key resistance high"),
                notes.get("volume_reasoning", f"{vol_r:.2f}x volume surge confirming buyer interest"),
                notes.get("compression_reasoning", "ATR squeeze signaling high potential energy release"),
            ],
        }

    output_dict["ticker"] = sym
    output_dict["company_name"] = company_name
    output_dict["score"] = score
    output_dict["archetype"] = archetype
    output_dict["trigger"] = trigger
    output_dict["target"] = target
    output_dict["stop_loss"] = stop
    output_dict["risk_reward_ratio"] = scored.get("risk_reward_ratio", 2.0)
    output_dict["calculation_notes"] = notes
    output_dict["generated_at"] = datetime.now(timezone.utc).isoformat()

    _AI_REASONING_CACHE[cache_key] = output_dict
    return output_dict


# ---------------------------------------------------------------------------
# Internal: score a single ticker with DB lookups
# ---------------------------------------------------------------------------

def _score_single_ticker(ticker: str, settings: Settings, asof_date: str | None = None) -> dict[str, Any] | None:
    """Load prices, metrics, and score a single ticker. Returns result dict or None."""
    try:
        from earnings_engine.data.prices import load_prices, load_price_metrics

        prices_df = load_prices(ticker, settings)
        if prices_df is None or prices_df.empty:
            return None

        metrics = load_price_metrics(ticker, settings) or {}
        quality_scores: list[float | None] = []
        for key in ("q1_earnings_score", "q2_earnings_score", "q3_earnings_score"):
            v = metrics.get(key)
            if v is not None:
                try:
                    quality_scores.append(float(v))
                except (TypeError, ValueError):
                    quality_scores.append(None)
            else:
                quality_scores.append(None)

        result = score_breakout(ticker, prices_df, quality_scores, asof_date=asof_date)
        if result:
            result["company_name"] = metrics.get("company_name") or ticker
            result["market_cap_cr"] = metrics.get("market_cap_cr") or metrics.get("market_cap")
            result["industry"] = metrics.get("industry") or metrics.get("sector") or "—"
        return result
    except Exception as e:
        logger.debug("[BREAKOUT] Error scoring %s: %s", ticker, e)
    return None


# ---------------------------------------------------------------------------
# Tier-specific scan functions
# ---------------------------------------------------------------------------

def _resolve_universe_tickers(settings: Settings, universe: str | None = None) -> list[str]:
    """Resolve the full set of tickers to scan from universes, watchlists, and DB."""
    from earnings_engine.data.watchlists import all_watchlists, get_watchlist
    from earnings_engine.data.universe import load_universe
    from earnings_engine.data.prices import _connect

    tickers: set[str] = set()
    u_clean = universe.lower().strip() if universe else "all"

    if u_clean in ("nifty_50", "nifty50", "nifty_top_50", "nse_top"):
        uni = load_universe("NSE_TOP", settings) or load_universe("NIFTY_50", settings)
        if uni:
            tickers.update(uni)
    elif u_clean == "nse_large_cap":
        large_caps = load_universe("NSE_LARGE_CAP", settings)
        if large_caps:
            tickers.update(large_caps[:120])
    elif u_clean in ("us_top", "us"):
        us_uni = load_universe("US_TOP", settings)
        if us_uni:
            tickers.update(us_uni)
    elif u_clean != "all":
        wl_tickers = get_watchlist(universe, settings)
        if wl_tickers:
            tickers.update(wl_tickers)
        else:
            custom_uni = load_universe(universe, settings)
            if custom_uni:
                tickers.update(custom_uni)

    if not tickers:
        try:
            wls = all_watchlists(settings)
            for wl in wls:
                if isinstance(wl, dict):
                    tickers.update(wl.get("tickers", []))
                elif isinstance(wl, str):
                    wl_tickers = get_watchlist(wl, settings)
                    if wl_tickers:
                        tickers.update(wl_tickers)
        except Exception as e:
            logger.warning("[BREAKOUT] Could not load watchlists: %s", e)

        try:
            for u in ("NSE_TOP", "IN"):
                uni = load_universe(u, settings)
                if uni:
                    tickers.update(uni)
            large_caps = load_universe("NSE_LARGE_CAP", settings)
            if large_caps:
                tickers.update(large_caps[:100])
        except Exception as e:
            logger.debug("[BREAKOUT] Universe load fallback: %s", e)

        if len(tickers) < 50:
            try:
                with _connect(settings) as conn:
                    rows = conn.execute("SELECT DISTINCT ticker FROM price_history LIMIT 100").fetchall()
                    tickers.update([r[0] for r in rows if r[0]])
            except Exception:
                pass

    return sorted(tickers)


def run_cold_scan(settings: Settings, universe: str | None = None) -> None:
    """T0 Cold Scan: score the entire universe and populate warm/hot pools."""
    t0 = time.perf_counter()
    _pool["status"] = "running"
    _pool["error"] = None

    ticker_list = _resolve_universe_tickers(settings, universe)
    if not ticker_list:
        logger.info("[BREAKOUT-COLD] No tickers found to scan.")
        _pool["status"] = "done"
        _pool["cold_tickers_scanned"] = 0
        _pool["last_cold_scan_at"] = datetime.now(timezone.utc).isoformat()
        _pool["last_scan_at"] = _pool["last_cold_scan_at"]
        return

    from concurrent.futures import ThreadPoolExecutor

    def _score(ticker: str) -> tuple[str, dict | None]:
        result = _score_single_ticker(ticker, settings)
        return ticker, result

    with ThreadPoolExecutor(max_workers=8) as executor:
        scored = list(executor.map(_score, ticker_list))

    promoted_hot = 0
    promoted_warm = 0
    for ticker, result in scored:
        if result is None:
            continue
        _promote(ticker, result)
        if ticker in _pool["hot"]:
            promoted_hot += 1
        elif ticker in _pool["warm"]:
            promoted_warm += 1

    _rebuild_candidates()

    elapsed = round(time.perf_counter() - t0, 2)
    now_iso = datetime.now(timezone.utc).isoformat()
    _pool.update({
        "last_cold_scan_at": now_iso,
        "last_scan_at": now_iso,
        "last_scan_duration_s": elapsed,
        "cold_tickers_scanned": len(ticker_list),
        "status": "done",
        "error": None,
    })

    logger.info(
        "[BREAKOUT-COLD] Full scan: %d tickers → %d hot, %d warm, %d API candidates in %.1fs",
        len(ticker_list), len(_pool["hot"]), len(_pool["warm"]), len(_pool["candidates"]), elapsed,
    )


def run_warm_rescore(settings: Settings) -> None:
    """T1 Warm Rescore: rescore only warm-pool tickers."""
    warm_tickers = list(_pool["warm"].keys())
    if not warm_tickers:
        return

    t0 = time.perf_counter()

    from concurrent.futures import ThreadPoolExecutor

    def _score(ticker: str) -> tuple[str, dict | None]:
        return ticker, _score_single_ticker(ticker, settings)

    with ThreadPoolExecutor(max_workers=6) as executor:
        scored = list(executor.map(_score, warm_tickers))

    for ticker, result in scored:
        if result is None:
            _demote_warm(ticker)
            continue

        new_score = result.get("composite_score", 0)
        if _should_be_hot(result):
            # Promote to hot
            _pool["warm"].pop(ticker, None)
            _pool["hot"][ticker] = {"result": result, "consecutive_low": 0}
        elif new_score >= WARM_THRESHOLD:
            _pool["warm"][ticker] = {"result": result, "consecutive_low": 0}
        elif new_score < WARM_DEMOTION_THRESHOLD:
            _demote_warm(ticker)
        else:
            # Between demotion threshold and warm threshold: keep but update
            if ticker in _pool["warm"]:
                _pool["warm"][ticker]["result"] = result

    _rebuild_candidates()

    elapsed = round(time.perf_counter() - t0, 2)
    now_iso = datetime.now(timezone.utc).isoformat()
    _pool["last_warm_scan_at"] = now_iso
    _pool["last_scan_at"] = now_iso

    logger.info(
        "[BREAKOUT-WARM] Rescore: %d warm tickers in %.1fs (hot=%d, warm=%d)",
        len(warm_tickers), elapsed, len(_pool["hot"]), len(_pool["warm"]),
    )


def run_hot_rescore(settings: Settings) -> None:
    """T2 Hot Rescore: rescore only hot-pool tickers for maximum freshness."""
    hot_tickers = list(_pool["hot"].keys())
    if not hot_tickers:
        return

    t0 = time.perf_counter()

    from concurrent.futures import ThreadPoolExecutor

    def _score(ticker: str) -> tuple[str, dict | None]:
        return ticker, _score_single_ticker(ticker, settings)

    with ThreadPoolExecutor(max_workers=4) as executor:
        scored = list(executor.map(_score, hot_tickers))

    for ticker, result in scored:
        if result is None:
            _demote_hot(ticker)
            continue

        new_score = result.get("composite_score", 0)
        if _should_be_hot(result):
            _pool["hot"][ticker] = {"result": result, "consecutive_low": 0}
        elif new_score < HOT_DEMOTION_THRESHOLD:
            # Score dropped: track for two-strike demotion
            if ticker in _pool["hot"]:
                _pool["hot"][ticker]["result"] = result
                _demote_hot(ticker)
        else:
            # Between demotion threshold and hot threshold: keep but update
            if ticker in _pool["hot"]:
                _pool["hot"][ticker]["result"] = result
                _pool["hot"][ticker]["consecutive_low"] = 0

    _rebuild_candidates()

    elapsed = round(time.perf_counter() - t0, 2)
    now_iso = datetime.now(timezone.utc).isoformat()
    _pool["last_hot_scan_at"] = now_iso
    _pool["last_scan_at"] = now_iso

    logger.debug(
        "[BREAKOUT-HOT] Rescore: %d hot tickers in %.1fs",
        len(hot_tickers), elapsed,
    )


# ---------------------------------------------------------------------------
# Full universe scan (backward-compatible, used for asof_date point-in-time)
# ---------------------------------------------------------------------------

def run_breakout_scan(
    settings: Settings,
    universe: str | None = None,
    asof_date: str | None = None,
) -> list[dict[str, Any]]:
    """Scan available tickers and return candidates sorted by score DESC point-in-time.

    For live scans (no asof_date), this delegates to `run_cold_scan` which
    populates the tiered pool and returns the merged candidates.
    For historical asof_date scans, performs a standalone full-universe scan.
    """
    if asof_date is None:
        # Live scan: use the tiered pool system
        run_cold_scan(settings, universe=universe)
        return list(_pool["candidates"])

    # Historical point-in-time scan (standalone, doesn't touch the pool)
    from concurrent.futures import ThreadPoolExecutor

    ticker_list = _resolve_universe_tickers(settings, universe)
    if not ticker_list:
        return []

    t0 = time.perf_counter()

    def _score(ticker: str) -> dict | None:
        return _score_single_ticker(ticker, settings, asof_date=asof_date)

    with ThreadPoolExecutor(max_workers=8) as executor:
        scored = list(executor.map(_score, ticker_list))

    candidates = [c for c in scored if c is not None and c.get("composite_score", 0) >= BREAKOUT_MIN_SCORE]
    candidates.sort(key=lambda x: x["composite_score"], reverse=True)
    candidates = candidates[:BREAKOUT_MAX_CANDIDATES]

    elapsed = round(time.perf_counter() - t0, 2)
    logger.info(
        "[BREAKOUT] Historical scan (asof=%s): %d tickers, %d candidates in %.1fs",
        asof_date, len(ticker_list), len(candidates), elapsed,
    )
    return candidates


# ---------------------------------------------------------------------------
# Background asyncio loop — Tiered Scanner
# ---------------------------------------------------------------------------

async def tiered_scanner_loop(settings: Settings) -> None:
    """Asyncio task: orchestrates cold/warm/hot scans at independent intervals.

    Timeline (example with defaults):
    - t=0s:    Cold scan (bootstrap all pools)
    - t=5m:    Hot rescore
    - t=10m:   Hot rescore
    - t=15m:   Hot rescore + Warm rescore
    - t=20m:   Hot rescore
    - ...
    - t=60m:   Hot rescore + Cold scan (discover new candidates)
    """
    cold_interval_s = COLD_INTERVAL_MIN * 60
    warm_interval_s = WARM_INTERVAL_MIN * 60
    hot_interval_s = HOT_INTERVAL_MIN * 60

    logger.info(
        "[BREAKOUT] Tiered scanner started. Cold: %dm, Warm: %dm, Hot: %dm, Min score: %d",
        COLD_INTERVAL_MIN, WARM_INTERVAL_MIN, HOT_INTERVAL_MIN, BREAKOUT_MIN_SCORE,
    )

    loop = asyncio.get_event_loop()

    # Bootstrap: run initial cold scan immediately
    try:
        await loop.run_in_executor(None, run_cold_scan, settings, None)
        logger.info("[BREAKOUT] Bootstrap cold scan complete. Hot: %d, Warm: %d", len(_pool["hot"]), len(_pool["warm"]))
    except Exception as e:
        logger.error("[BREAKOUT] Bootstrap cold scan failed: %s", e)
        _pool["status"] = "error"
        _pool["error"] = str(e)

    # Track time since last scan of each tier
    last_cold = time.monotonic()
    last_warm = time.monotonic()
    last_hot = time.monotonic()

    while True:
        try:
            await asyncio.sleep(hot_interval_s)
        except asyncio.CancelledError:
            logger.info("[BREAKOUT] Tiered scanner cancelled during sleep.")
            break

        now = time.monotonic()

        try:
            # Check which tiers need rescoring (in priority order: cold > warm > hot)
            if now - last_cold >= cold_interval_s:
                await loop.run_in_executor(None, run_cold_scan, settings, None)
                last_cold = now
                last_warm = now  # cold scan effectively rescores everything
                last_hot = now

            elif now - last_warm >= warm_interval_s:
                await loop.run_in_executor(None, run_hot_rescore, settings)
                await loop.run_in_executor(None, run_warm_rescore, settings)
                last_warm = now
                last_hot = now

            else:
                # Just hot rescore
                await loop.run_in_executor(None, run_hot_rescore, settings)
                last_hot = now

        except asyncio.CancelledError:
            logger.info("[BREAKOUT] Tiered scanner cancelled.")
            break
        except Exception as e:
            logger.error("[BREAKOUT] Scan cycle error: %s", e)
            _pool["status"] = "error"
            _pool["error"] = str(e)


# ---------------------------------------------------------------------------
# On-Demand Single-Stock Evaluation & Ticker Search
# ---------------------------------------------------------------------------

def evaluate_stock_breakout(
    ticker: str,
    asof_date: str | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Evaluate a single stock on-demand for Breakout Radar setup conviction, key levels, and sub-score metrics."""
    settings = settings or Settings()
    raw = (ticker or "").strip().upper()
    if not raw:
        return {"success": False, "error": "Ticker symbol cannot be empty."}

    # Normalize ticker (append .NS for Indian equities if missing suffix)
    sym = raw
    if not (sym.endswith(".NS") or sym.endswith(".BO") or "." in sym):
        sym = f"{sym}.NS"

    from earnings_engine.data.prices import load_prices, load_price_metrics, fetch_prices
    from earnings_engine.data.universe import load_market_cap

    prices_df = load_prices(sym, settings)
    if prices_df is None or len(prices_df) < 15:
        # Try raw symbol or fetch/ingest
        prices_df = load_prices(raw, settings)
        if prices_df is None or len(prices_df) < 15:
            try:
                prices_df = fetch_prices(sym, settings, force=False)
            except Exception as e:
                logger.warning("[BREAKOUT-EVAL] Fallback fetch failed for %s: %s", sym, e)

    if prices_df is None or prices_df.empty or len(prices_df) < 10:
        return {
            "success": False,
            "error": f"Insufficient price history found for {sym}. Please ensure the symbol is valid and has trading history.",
            "ticker": sym,
        }

    metrics = load_price_metrics(sym, settings) or load_price_metrics(raw, settings) or {}
    company_name = metrics.get("company_name") or sym.replace(".NS", "")
    industry = metrics.get("industry") or metrics.get("sector") or "General Equities"

    quality_scores = [
        float(metrics.get(k)) if metrics.get(k) is not None else None
        for k in ("q1_earnings_score", "q2_earnings_score", "q3_earnings_score")
    ]

    scored = score_breakout(sym, prices_df, quality_scores, asof_date=asof_date)
    if not scored:
        return {
            "success": False,
            "error": f"Could not compute breakout metrics for {sym}.",
            "ticker": sym,
        }

    scored["company_name"] = company_name
    scored["industry"] = industry
    scored["success"] = True

    # Setup Conviction Tier
    comp_score = scored.get("composite_score", 0)
    if comp_score >= HOT_THRESHOLD:
        tier = "HOT"
        tier_label = "🔥 High Conviction Setup"
        tier_badge = "emerald"
    elif comp_score >= WARM_THRESHOLD:
        tier = "WARM"
        tier_label = "⚡ Coiling / Approaching Trigger"
        tier_badge = "amber"
    else:
        tier = "COLD"
        tier_label = "💤 Low Momentum / Dormant"
        tier_badge = "slate"

    scored["tier"] = tier
    scored["tier_label"] = tier_label
    scored["tier_badge"] = tier_badge

    return scored


def search_breakout_tickers(
    query: str,
    limit: int = 15,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """Fast auto-complete lookup for stocks across price cache and universe registry."""
    settings = settings or Settings()
    q = (query or "").strip().upper()
    if not q:
        return []

    from earnings_engine.data.db import get_db_connection
    results: list[dict[str, Any]] = []
    seen: set[str] = set()

    try:
        conn = get_db_connection(settings)
        # 1. Search in tickers table
        rows = conn.execute(
            """
            SELECT ticker, name, sector, industry
            FROM tickers
            WHERE ticker LIKE ? OR name LIKE ?
            ORDER BY CASE WHEN ticker LIKE ? THEN 1 WHEN ticker LIKE ? THEN 2 ELSE 3 END, ticker
            LIMIT ?
            """,
            (f"{q}%", f"%{q}%", f"{q}", f"{q}%", limit),
        ).fetchall()

        for r in rows:
            sym = r[0].upper()
            if sym not in seen:
                seen.add(sym)
                market = "NSE" if sym.endswith(".NS") else ("BSE" if sym.endswith(".BO") else "US")
                results.append({
                    "symbol": sym,
                    "name": r[1] or sym.replace(".NS", ""),
                    "market": market,
                    "sector": r[2] or "Equities",
                })
    except Exception as e:
        logger.debug("[BREAKOUT-SEARCH] Tickers table search error: %s", e)

    # 2. Fallback: Search distinct tickers in price_history or universes if needed
    if len(results) < limit:
        try:
            conn = get_db_connection(settings)
            more_rows = conn.execute(
                """
                SELECT DISTINCT ticker
                FROM price_history
                WHERE ticker LIKE ?
                LIMIT ?
                """,
                (f"%{q}%", limit - len(results)),
            ).fetchall()
            for r in more_rows:
                sym = r[0].upper()
                if sym not in seen:
                    seen.add(sym)
                    market = "NSE" if sym.endswith(".NS") else ("BSE" if sym.endswith(".BO") else "US")
                    results.append({
                        "symbol": sym,
                        "name": sym.replace(".NS", ""),
                        "market": market,
                        "sector": "Equities",
                    })
        except Exception as e:
            logger.debug("[BREAKOUT-SEARCH] Price history search error: %s", e)

    return results[:limit]


# ---------------------------------------------------------------------------
# Legacy compat alias
# ---------------------------------------------------------------------------
breakout_scanner_loop = tiered_scanner_loop

