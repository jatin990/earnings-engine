"""Breakout Radar — Background Scanner & Scoring Engine.

Runs on a configurable interval while the server is live.  For each ticker
that has local cached prices it computes a 5-component **Breakout Score**
(0 – 100) and stores the sorted candidate list in an in-memory cache so the
``/api/v1/breakout-radar`` endpoint can respond instantly.

Score Components
----------------
1. Resistance Proximity  (0-30 pts) — price within 0-5% below the 20D / 52W high
2. Volume Surge          (0-20 pts) — today's volume vs 20D average
3. Price Compression     (0-15 pts) — ATR(14)/price squeeze (low volatility = coiling)
4. Momentum              (0-15 pts) — 30D return > 0 and price > 20D SMA
5. Fundamental Bonus     (0-20 pts) — earnings quality score (q1/q2/q3 avg, normalised)

Minimum score to appear in results: BREAKOUT_MIN_SCORE (default 35).
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
BREAKOUT_SCAN_INTERVAL_MIN: int = int(os.environ.get("BREAKOUT_SCAN_INTERVAL_MIN", "30"))
BREAKOUT_MIN_SCORE: int = int(os.environ.get("BREAKOUT_MIN_SCORE", "35"))
BREAKOUT_MAX_CANDIDATES: int = int(os.environ.get("BREAKOUT_MAX_CANDIDATES", "100"))

# ---------------------------------------------------------------------------
# In-memory cache
# ---------------------------------------------------------------------------
_cache: dict[str, Any] = {
    "candidates": [],          # list[dict] sorted by score DESC
    "last_scan_at": None,      # ISO8601 str
    "last_scan_duration_s": 0.0,
    "tickers_scanned": 0,
    "status": "idle",          # "idle" | "running" | "done" | "error"
    "error": None,
}


def get_cached_scan_results(
    universe: str | None = None,
    settings: Settings | None = None,
    asof_date: str | None = None,
) -> list[dict[str, Any]]:
    """Return breakout candidates, optionally filtered by universe and point-in-time as-of date."""
    settings = settings or Settings()
    if asof_date:
        return run_breakout_scan(settings, universe=universe, asof_date=asof_date)

    all_candidates = list(_cache["candidates"])
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
        "status": _cache["status"],
        "last_scan_at": _cache["last_scan_at"],
        "last_scan_duration_s": _cache["last_scan_duration_s"],
        "tickers_scanned": _cache["tickers_scanned"],
        "candidates_found": len(_cache["candidates"]),
        "universe": universe or _cache.get("last_universe", "ALL"),
        "min_score": BREAKOUT_MIN_SCORE,
        "scan_interval_min": BREAKOUT_SCAN_INTERVAL_MIN,
        "error": _cache["error"],
    }


# ---------------------------------------------------------------------------
# Scoring helpers
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

    return {
        "ticker": ticker,
        "signal_date": signal_date,
        "signal_price": round(signal_price, 2),
        "predicted_value": round(signal_price, 2),
        "breakout_trigger": breakout_trigger,
        "target_price": target_price,
        "stop_loss": stop_loss,
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
# Full universe scan
# ---------------------------------------------------------------------------

def run_breakout_scan(
    settings: Settings,
    universe: str | None = None,
    asof_date: str | None = None,
) -> list[dict[str, Any]]:
    """Scan available tickers and return candidates sorted by score DESC point-in-time."""
    from concurrent.futures import ThreadPoolExecutor
    from earnings_engine.data import prices as prices_mod
    from earnings_engine.data.watchlists import all_watchlists, get_watchlist
    from earnings_engine.data.universe import load_universe
    from earnings_engine.data.prices import load_prices, load_price_metrics, _connect

    is_live_scan = asof_date is None
    if is_live_scan:
        _cache["status"] = "running"
        _cache["error"] = None
    t0 = time.perf_counter()

    tickers: set[str] = set()
    u_clean = universe.lower().strip() if universe else "all"

    if u_clean in ("nifty_50", "nifty50", "nifty_top_50", "nse_top"):
        # Specifically scan NIFTY 50 benchmark constituents
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
        # Try custom watchlist first, then named universe
        wl_tickers = get_watchlist(universe, settings)
        if wl_tickers:
            tickers.update(wl_tickers)
        else:
            custom_uni = load_universe(universe, settings)
            if custom_uni:
                tickers.update(custom_uni)

    # If universe was "all" or nothing matched above, collect comprehensive universe
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

    if not tickers:
        logger.info("[BREAKOUT] No tickers found to scan.")
        if is_live_scan:
            _cache["status"] = "done"
            _cache["candidates"] = []
            _cache["tickers_scanned"] = 0
            _cache["last_scan_at"] = datetime.now(timezone.utc).isoformat()
            _cache["last_scan_duration_s"] = round(time.perf_counter() - t0, 2)
        return []

    ticker_list = sorted(tickers)

    def _score_single(ticker: str) -> dict[str, Any] | None:
        try:
            prices_df = load_prices(ticker, settings)
            if prices_df is None or prices_df.empty:
                return None

            # Load quality scores from stored metrics
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
            if result and result["composite_score"] >= BREAKOUT_MIN_SCORE:
                # Enrich with company name from metrics if available
                result["company_name"] = metrics.get("company_name") or ticker
                result["market_cap_cr"] = metrics.get("market_cap_cr") or metrics.get("market_cap")
                result["industry"] = metrics.get("industry") or metrics.get("sector") or "—"
                return result
        except Exception as e:
            logger.debug("[BREAKOUT] Error scoring %s: %s", ticker, e)
        return None

    # Run scoring concurrently using thread pool (I/O & DB queries)
    candidates: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        scored = list(executor.map(_score_single, ticker_list))
        candidates = [c for c in scored if c is not None]

    # Sort by composite score descending
    candidates.sort(key=lambda x: x["composite_score"], reverse=True)
    candidates = candidates[:BREAKOUT_MAX_CANDIDATES]

    elapsed = round(time.perf_counter() - t0, 2)
    if is_live_scan:
        _cache.update({
            "candidates": candidates,
            "last_scan_at": datetime.now(timezone.utc).isoformat(),
            "last_scan_duration_s": elapsed,
            "tickers_scanned": len(ticker_list),
            "last_universe": universe or "ALL",
            "status": "done",
            "error": None,
        })

    logger.info(
        "[BREAKOUT] Scan complete (asof=%s): %d tickers scanned, %d candidates in %.1fs",
        asof_date or "LIVE", len(ticker_list), len(candidates), elapsed,
    )
    return candidates


# ---------------------------------------------------------------------------
# Background asyncio loop (started from server lifespan)
# ---------------------------------------------------------------------------

async def breakout_scanner_loop(settings: Settings) -> None:
    """Asyncio task: runs run_breakout_scan() every BREAKOUT_SCAN_INTERVAL_MIN minutes."""
    interval_s = BREAKOUT_SCAN_INTERVAL_MIN * 60
    logger.info(
        "[BREAKOUT] Scanner started. Interval: %d min, min score: %d",
        BREAKOUT_SCAN_INTERVAL_MIN, BREAKOUT_MIN_SCORE,
    )
    while True:
        try:
            # Run blocking scan in a thread pool executor so we don't block the event loop
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, run_breakout_scan, settings)
        except asyncio.CancelledError:
            logger.info("[BREAKOUT] Scanner loop cancelled (server shutdown).")
            break
        except Exception as e:
            logger.error("[BREAKOUT] Scan error: %s", e)
            _cache["status"] = "error"
            _cache["error"] = str(e)

        try:
            await asyncio.sleep(interval_s)
        except asyncio.CancelledError:
            logger.info("[BREAKOUT] Scanner loop cancelled during sleep.")
            break
