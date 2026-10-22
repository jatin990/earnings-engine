"""Historical backtesting engine for Breakout Radar signals."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import numpy as np

from earnings_engine.config import Settings
from earnings_engine.data.breakout_scanner.scoring import _score_single_ticker

logger = logging.getLogger(__name__)


def run_historical_backtest(
    settings: Settings,
    universe: str | None = None,
) -> dict[str, Any]:
    """Run an on-demand historical backtest sweep over the last 90, 75, 60, 45, and 30 days.

    Returns structured stats comparing old vs new outcomes, component effect sizes,
    and performance by score/volume threshold.
    """
    from earnings_engine.data.breakout_scanner.pipeline import _resolve_universe_tickers

    t_start = time.perf_counter()
    ticker_list = _resolve_universe_tickers(settings, universe)
    if not ticker_list:
        return {"success": False, "error": "No tickers found in universe."}

    # Standard historical dates
    asof_dates = [
        (datetime.now(timezone.utc) - timedelta(days=d)).strftime("%Y-%m-%d")
        for d in [90, 75, 60, 45, 30]
    ]

    all_results = []

    def _evaluate_date_tickers(date_str: str) -> list[dict[str, Any]]:
        date_results = []
        for ticker in ticker_list:
            try:
                res = _score_single_ticker(ticker, settings, asof_date=date_str)
                if res and res.get("composite_score", 0) >= 25:
                    res["asof_date"] = date_str
                    date_results.append(res)
            except Exception:
                pass
        return date_results

    with ThreadPoolExecutor(max_workers=min(8, len(asof_dates))) as executor:
        batches = list(executor.map(_evaluate_date_tickers, asof_dates))

    for b in batches:
        all_results.extend(b)

    resolved = [r for r in all_results if r.get("breakout_happened") is not None]
    broke = [r for r in resolved if r.get("breakout_happened") is True]
    failed = [r for r in resolved if r.get("breakout_happened") is False]

    total = len(all_results)
    total_resolved = len(resolved)
    total_broke = len(broke)
    total_failed = len(failed)

    win_rate = round(total_broke / total_resolved * 100, 1) if total_resolved else 0.0

    returns = [float(r["realized_return_pct"]) for r in resolved if r.get("realized_return_pct") is not None]
    avg_return = round(float(np.mean(returns)), 2) if returns else 0.0

    broke_returns = [float(r["realized_return_pct"]) for r in broke if r.get("realized_return_pct") is not None]
    failed_returns = [float(r["realized_return_pct"]) for r in failed if r.get("realized_return_pct") is not None]

    avg_broke_return = round(float(np.mean(broke_returns)), 2) if broke_returns else 0.0
    avg_failed_return = round(float(np.mean(failed_returns)), 2) if failed_returns else 0.0

    outcomes_count = {
        "TARGET_HIT": len([r for r in resolved if r.get("outcome") == "TARGET_HIT"]),
        "BREAKOUT_SUCCEEDED": len([r for r in resolved if r.get("outcome") == "BREAKOUT_SUCCEEDED"]),
        "BREAKOUT_RETRACED": len([r for r in resolved if r.get("outcome") == "BREAKOUT_RETRACED"]),
        "STOP_LOSS_HIT": len([r for r in resolved if r.get("outcome") == "STOP_LOSS_HIT"]),
        "NO_BREAKOUT": len([r for r in resolved if r.get("outcome") == "NO_BREAKOUT"]),
    }

    effect_sizes = {}
    fields = [
        ("composite_score", "Composite Score"),
        ("resistance_score", "Resistance Proximity"),
        ("volume_score", "Volume Surge"),
        ("compression_score", "Price Compression"),
        ("momentum_score", "Momentum"),
        ("fundamental_score", "Fundamental Quality"),
        ("pct_from_high", "% from 52W High"),
        ("volume_ratio", "Volume Ratio"),
        ("atr_pct", "ATR %"),
    ]

    for col, label in fields:
        bv = [float(r[col]) for r in broke if r.get(col) is not None]
        fv = [float(r[col]) for r in failed if r.get(col) is not None]
        if bv and fv:
            mean_b = np.mean(bv)
            mean_f = np.mean(fv)
            delta = mean_b - mean_f
            pooled_std = np.std(bv + fv) or 1.0
            es = abs(delta) / pooled_std
            effect_sizes[col] = {
                "label": label,
                "mean_breakout": round(float(mean_b), 2),
                "mean_failed": round(float(mean_f), 2),
                "delta": round(float(delta), 2),
                "effect_size": round(float(es), 3),
                "direction": "HIGHER in breakouts ↑" if delta > 0 else "LOWER in breakouts ↓",
            }

    score_thresholds = {}
    for th in [35, 45, 50, 55, 60, 65, 70]:
        th_res = [r for r in resolved if r.get("composite_score", 0) >= th]
        th_broke = [r for r in th_res if r.get("breakout_happened") is True]
        score_thresholds[str(th)] = {
            "count": len(th_res),
            "broke_count": len(th_broke),
            "win_rate_pct": round(len(th_broke) / len(th_res) * 100, 1) if th_res else 0.0,
        }

    vol_thresholds = {}
    for vr in [1.0, 1.2, 1.5, 2.0]:
        vr_res = [r for r in resolved if (r.get("volume_ratio") or 0) >= vr]
        vr_broke = [r for r in vr_res if r.get("breakout_happened") is True]
        vol_thresholds[f"{vr}x"] = {
            "count": len(vr_res),
            "broke_count": len(vr_broke),
            "win_rate_pct": round(len(vr_broke) / len(vr_res) * 100, 1) if vr_res else 0.0,
        }

    duration = round(time.perf_counter() - t_start, 2)

    return {
        "success": True,
        "universe": universe or "ALL",
        "total_candidates": total,
        "total_evaluated": total_resolved,
        "success_count": total_broke,
        "failed_count": total_failed,
        "win_rate_pct": win_rate,
        "avg_return_pct": avg_return,
        "avg_broke_return_pct": avg_broke_return,
        "avg_failed_return_pct": avg_failed_return,
        "outcomes": outcomes_count,
        "effect_sizes": effect_sizes,
        "score_thresholds": score_thresholds,
        "volume_thresholds": vol_thresholds,
        "duration_s": duration,
        "run_at": datetime.now(timezone.utc).isoformat(),
    }
