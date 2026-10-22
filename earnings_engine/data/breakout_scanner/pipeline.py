"""Breakout Scanner Orchestration, Multi-Strategy Scans, Backtesting, and Search Pipeline."""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Any
import numpy as np
import pandas as pd

from earnings_engine.config import Settings
from earnings_engine.data.universe import is_fno_eligible
from earnings_engine.data.breakout_scanner.constants import (
    BREAKOUT_STRATEGIES,
    BREAKOUT_MIN_SCORE,
    BREAKOUT_MAX_CANDIDATES,
    HOT_THRESHOLD,
    WARM_THRESHOLD,
    HOT_DEMOTION_THRESHOLD,
    WARM_DEMOTION_THRESHOLD,
    COLD_INTERVAL_MIN,
    WARM_INTERVAL_MIN,
    HOT_INTERVAL_MIN,
)
from earnings_engine.data.breakout_scanner.state import (
    _pool,
    _pool_key,
    _rebuild_candidates,
)
from earnings_engine.data.breakout_scanner.scoring import (
    _should_be_hot,
    score_breakout,
)

def _score_single_ticker(*args: Any, **kwargs: Any) -> Any:
    """Dynamic dispatcher to support monkeypatching at package level."""
    import sys
    bs_mod = sys.modules.get("earnings_engine.data.breakout_scanner")
    if bs_mod:
        fn = getattr(bs_mod, "_score_single_ticker", None)
        if fn and fn is not _score_single_ticker:
            return fn(*args, **kwargs)
    from earnings_engine.data.breakout_scanner.scoring import _score_single_ticker as _real_score
    return _real_score(*args, **kwargs)


def _dispatch_score_single_ticker(*args: Any, **kwargs: Any) -> dict[str, Any] | None:
    """Dynamically route to _score_single_ticker or facade monkeypatch if set."""
    import sys
    mod = sys.modules.get("earnings_engine.data.breakout_scanner")
    fn = getattr(mod, "_score_single_ticker", None) if mod else None
    if not fn:
        fn = _score_single_ticker
    return fn(*args, **kwargs)
from earnings_engine.data.breakout_scanner.storage import (
    _init_breakout_db,
    save_breakout_pool_to_db,
    load_breakout_pool_from_db,
    record_breakout_transition,
    _promote,
    _demote_hot,
    _demote_warm,
    get_tracked_ticker_set,
)
from earnings_engine.data.breakout_scanner.backtest import run_historical_backtest
from earnings_engine.data.breakout_scanner.scheduler import (
    tiered_scanner_loop,
    breakout_scanner_loop,
)
from earnings_engine.data.breakout_scanner.evaluation import (
    evaluate_stock_breakout,
    set_ticker_tier,
    search_breakout_tickers,
)
from earnings_engine.data.db import get_db_connection

logger = logging.getLogger(__name__)

def get_cached_scan_results(
    universe: str | None = None,
    settings: Settings | None = None,
    asof_date: str | None = None,
    strategy: str = "CLASSIC_TECHNICAL",
    tier: str | None = "ALL",
) -> list[dict[str, Any]]:
    """Return breakout candidates, optionally filtered by universe, point-in-time as-of date, and strategy."""
    settings = settings or Settings()
    strategy_clean = (strategy or "CLASSIC_TECHNICAL").upper().strip()

    if not _pool.get("candidates"):
        load_breakout_pool_from_db(settings)

    if asof_date:
        candidates = run_breakout_scan(settings, universe=universe, asof_date=asof_date, strategy=strategy_clean)
    else:
        if strategy_clean in ("ALL", "*"):
            candidates = list(_pool.get("candidates", []))
            if not candidates:
                try:
                    conn = get_db_connection(settings)
                    cur = conn.execute(
                        "SELECT data_json, ticker, strategy, composite_score FROM breakout_radar ORDER BY composite_score DESC LIMIT ?",
                        (BREAKOUT_MAX_CANDIDATES,),
                    )
                    db_cands = []
                    for row in cur.fetchall():
                        if row[0]:
                            try:
                                d = json.loads(row[0])
                                if d and d.get("ticker"):
                                    if row[2]:
                                        d["strategy"] = str(row[2])
                                    db_cands.append(d)
                            except Exception:
                                pass
                    if db_cands:
                        candidates = db_cands
                except Exception as e:
                    logger.debug("[BREAKOUT] DB direct fallback notice for ALL: %s", e)
        else:
            strat_pool = _pool.get("strategy_pools", {}).get(strategy_clean)
            if strat_pool and strat_pool.get("candidates"):
                candidates = list(strat_pool["candidates"])
            else:
                candidates = [c for c in _pool.get("candidates", []) if (c.get("strategy") or "CLASSIC_TECHNICAL").upper() == strategy_clean]

            # Direct SQLite fallback if in-memory pool doesn't have this strategy yet
            if not candidates and strategy_clean not in ("ALL", "*"):
                try:
                    conn = get_db_connection(settings)
                    cur = conn.execute(
                        "SELECT data_json, ticker, composite_score FROM breakout_radar WHERE UPPER(strategy) = ? ORDER BY composite_score DESC LIMIT ?",
                        (strategy_clean, BREAKOUT_MAX_CANDIDATES),
                    )
                    db_cands = []
                    for row in cur.fetchall():
                        if row[0]:
                            try:
                                d = json.loads(row[0])
                                if d and d.get("ticker"):
                                    d["strategy"] = strategy_clean
                                    db_cands.append(d)
                            except Exception:
                                pass
                    if db_cands:
                        candidates = db_cands
                except Exception as e:
                    logger.debug("[BREAKOUT] DB direct fallback notice for %s: %s", strategy_clean, e)

            # If still empty and strategy is valid, compute dynamically on the fly
            if not candidates and strategy_clean in BREAKOUT_STRATEGIES:
                try:
                    candidates = run_breakout_scan(settings, universe=universe, strategy=strategy_clean)
                except Exception as e:
                    logger.debug("[BREAKOUT] Dynamic scan fallback notice for %s: %s", strategy_clean, e)

            if not candidates and strategy_clean == "CLASSIC_TECHNICAL":
                candidates = list(_pool.get("candidates", []))

    # Enrich candidates with real-tracked status badge
    tracked_set = get_tracked_ticker_set(settings)
    for c in candidates:
        t = str(c.get("ticker", "")).upper()
        is_tracked = bool(t in tracked_set or c.get("scanned_at") or c.get("id"))
        c["is_real_tracked"] = is_tracked
        c["tracked_badge"] = "🟢 Real Tracked" if is_tracked else "📊 Dynamic Scan"
        c["tracking_status"] = "REAL_TIME_TRACKED" if is_tracked else "DYNAMIC_SCAN"

    if tier and tier.upper() != "ALL":
        target_tier = tier.upper().strip()
        candidates = [c for c in candidates if (c.get("tier") or "HOT").upper() == target_tier]

    if not universe or universe.lower() in ("all", "any", "global", "monitored"):
        return candidates

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
            candidates = [c for c in candidates if c.get("ticker", "").upper() in uni_normalized]
    except Exception as e:
        logger.debug("[BREAKOUT] Error filtering by universe %s: %s", universe, e)

    return candidates


def get_scan_status(universe: str | None = None, settings: Settings | None = None) -> dict[str, Any]:
    """Return a lightweight status dict for the API, lazy-loading persisted counts if uninitialized."""
    settings = settings or Settings()
    if _pool.get("hot_count", 0) == 0 and _pool.get("warm_count", 0) == 0:
        try:
            load_breakout_pool_from_db(settings)
        except Exception:
            pass
        if _pool.get("hot_count", 0) == 0 and _pool.get("warm_count", 0) == 0:
            try:
                conn = get_db_connection(settings)
                cur = conn.execute("SELECT UPPER(tier), COUNT(*) FROM breakout_radar GROUP BY UPPER(tier)")
                for row in cur.fetchall():
                    t_tier = str(row[0] or "").upper()
                    t_cnt = int(row[1] or 0)
                    if t_tier == "HOT":
                        _pool["hot_count"] = max(_pool.get("hot_count", 0), t_cnt)
                    elif t_tier == "WARM":
                        _pool["warm_count"] = max(_pool.get("warm_count", 0), t_cnt)
            except Exception:
                pass

    if not _pool.get("cold_tickers_scanned"):
        try:
            conn = get_db_connection(settings)
            row = conn.execute("SELECT COUNT(DISTINCT ticker) FROM price_history").fetchone()
            if row and row[0]:
                _pool["cold_tickers_scanned"] = int(row[0])
        except Exception:
            pass

    return {
        "status": _pool.get("status", "idle"),
        "is_scanning": _pool.get("status") == "running",
        "last_scan_at": _pool.get("last_scan_at"),
        "last_cold_scan_at": _pool.get("last_cold_scan_at"),
        "last_warm_scan_at": _pool.get("last_warm_scan_at"),
        "last_hot_scan_at": _pool.get("last_hot_scan_at"),
        "last_scan_duration_s": _pool.get("last_scan_duration_s", 0.0),
        "cold_tickers_scanned": _pool.get("cold_tickers_scanned", 0),
        "hot_count": _pool.get("hot_count", 0),
        "warm_count": _pool.get("warm_count", 0),
        "candidates_found": len(_pool.get("candidates", [])),
        "universe": universe or "ALL",
        "min_score": BREAKOUT_MIN_SCORE,
        "scan_intervals": {
            "cold_min": COLD_INTERVAL_MIN,
            "warm_min": WARM_INTERVAL_MIN,
            "hot_min": HOT_INTERVAL_MIN,
        },
        "error": _pool.get("error"),
    }



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
                    rows = conn.execute("SELECT ticker FROM tickers WHERE ticker IS NOT NULL LIMIT 100").fetchall()
                    if not rows:
                        rows = conn.execute("SELECT DISTINCT ticker FROM price_history LIMIT 100").fetchall()
                    tickers.update([r[0] for r in rows if r[0]])
            except Exception:
                pass

    return sorted(tickers)


def run_multi_strategy_parallel_scan(
    settings: Settings | None = None,
    universe: str | None = None,
    min_score: float | None = 30.0,
    strategies: list[str] | None = None,
    tickers: list[str] | None = None,
    job_id: str = "breakout_all_strategies_parallel",
    max_workers_per_strat: int = 6,
    record_schedule_event: bool = True,
    **kwargs: Any,
) -> dict[str, Any]:
    """Execute all 5 (or selected) breakout strategies in parallel across the universe.

    Spawns concurrent worker threads for each strategy to scan the market universe
    simultaneously, discovers setups, updates cache/pools, persists to SQLite/Turso,
    and logs run metrics to automation_schedules.
    """
    settings = settings or Settings()
    t0 = time.perf_counter()
    _pool["status"] = "running"
    _pool["error"] = None

    if record_schedule_event:
        from earnings_engine.data.automation_schedules import record_job_start, record_job_finish
        record_job_start(job_id, settings)

    strategies_to_run = strategies or list(BREAKOUT_STRATEGIES.keys())
    ticker_list = tickers if (tickers is not None and len(tickers) > 0) else _resolve_universe_tickers(settings, universe)

    if not ticker_list:
        summary_msg = "No tickers found in universe to scan."
        if record_schedule_event:
            record_job_finish(job_id, 0.0, summary_msg, settings=settings)
        return {"success": False, "message": summary_msg, "strategies": {}, "total_candidates": 0}

    from concurrent.futures import ThreadPoolExecutor
    from earnings_engine.data.prices import load_prices_batch, load_price_metrics_batch
    from earnings_engine.data.catalysts_news import get_recent_catalysts_batch
    from earnings_engine.data.cross_strategy import compute_market_regime_multiplier

    # Bulk pre-load prices, metrics, catalysts, and macro conditions across all tickers
    prices_map = load_prices_batch(ticker_list, settings=settings)
    metrics_map = load_price_metrics_batch(ticker_list, settings=settings)
    catalysts_map = get_recent_catalysts_batch(ticker_list, limit_per_ticker=3, settings=settings)
    macro_info = None
    try:
        macro_info = compute_market_regime_multiplier(settings)
    except Exception as e:
        logger.debug("[BREAKOUT-MACRO] Macro precompute warning: %s", e)

    strategy_results: dict[str, Any] = {}

    def _scan_strategy(strat_id: str) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
        s_t0 = time.perf_counter()
        meta = BREAKOUT_STRATEGIES.get(strat_id, {})
        strat_candidates: list[dict[str, Any]] = []

        def _score_one(t: str) -> dict[str, Any] | None:
            return _dispatch_score_single_ticker(
                t,
                settings,
                strategy=strat_id,
                prices_df=prices_map.get(t),
                metrics=metrics_map.get(t),
                catalysts=catalysts_map.get(t),
                macro_info=macro_info,
            )

        strat_clean = strat_id.upper().strip()
        strat_tickers = [t for t in ticker_list if is_fno_eligible(t)] if strat_clean == "NSE_FO_CALL_WALL" else ticker_list

        with ThreadPoolExecutor(max_workers=max_workers_per_strat) as executor:
            scored_list = list(executor.map(_score_one, strat_tickers))

        for res in scored_list:
            if res and (res.get("composite_score") or 0) >= (min_score or 30.0):
                strat_candidates.append(res)

        s_elapsed = round(time.perf_counter() - s_t0, 2)
        top_ticker = None
        top_score = 0.0
        if strat_candidates:
            strat_candidates.sort(key=lambda x: x.get("composite_score", 0), reverse=True)
            top_ticker = strat_candidates[0].get("ticker")
            top_score = strat_candidates[0].get("composite_score", 0)

        stats = {
            "strategy_id": strat_id,
            "strategy_name": meta.get("name", strat_id),
            "candidates_found": len(strat_candidates),
            "top_candidate": top_ticker,
            "top_score": top_score,
            "elapsed_seconds": s_elapsed,
        }
        logger.info(
            "[BREAKOUT-STRAT] Strategy %s finished in %.2fs -> %d candidates found (top: %s @ %.1f)",
            meta.get("name", strat_id),
            s_elapsed,
            len(strat_candidates),
            top_ticker or "none",
            top_score,
        )
        return strat_id, strat_candidates, stats

    logger.info(
        "[BREAKOUT-PARALLEL] Initiating multi-strategy scan across %d tickers (%d strategies in parallel)...",
        len(ticker_list),
        len(strategies_to_run),
    )
    # Run all strategies in parallel
    with ThreadPoolExecutor(max_workers=len(strategies_to_run)) as strat_executor:
        parallel_outputs = list(strat_executor.map(_scan_strategy, strategies_to_run))

    total_candidates = 0
    for strat_id, strat_candidates, stats in parallel_outputs:
        strategy_results[strat_id] = stats
        total_candidates += len(strat_candidates)

        # Populate in-memory pool for candidates
        for res in strat_candidates:
            ticker = res.get("ticker")
            if ticker:
                _promote(ticker, res, settings=settings)

    _rebuild_candidates()
    save_breakout_pool_to_db(settings)

    # Batch-fetch and sync latest quotes for all discovered setups & hot stocks
    try:
        cand_tickers = list({res.get("ticker") for _, strat_cands, _ in parallel_outputs for res in strat_cands if res.get("ticker")})
        hot_tickers = list({k.split("::")[0] for k in _pool.get("hot", {}).keys() if k})
        all_sync_tickers = list(dict.fromkeys(hot_tickers + cand_tickers))[:80]
        if all_sync_tickers:
            from earnings_engine.data.prices import fetch_batch_live_quotes
            fetch_batch_live_quotes(all_sync_tickers, settings=settings, sync_db=True, max_workers=10)
    except Exception as sync_err:
        logger.debug("[BREAKOUT-PARALLEL] Auto-quote sync notice: %s", sync_err)

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

    strat_summary_items = [
        f"{BREAKOUT_STRATEGIES.get(s, {}).get('short_name', s)}: {strategy_results.get(s, {}).get('candidates_found', 0)}"
        for s in strategies_to_run
    ]
    summary_msg = f"Multi-Strategy Parallel Sweep ({len(strategies_to_run)} strats, {len(ticker_list)} tickers in {elapsed}s): {', '.join(strat_summary_items)} → {total_candidates} setups."

    if record_schedule_event:
        record_job_finish(job_id, elapsed, summary_msg, settings=settings)

    logger.info("[BREAKOUT-PARALLEL] %s", summary_msg)

    return {
        "success": True,
        "job_id": job_id,
        "universe": universe or "NSE_ALL",
        "tickers_scanned": len(ticker_list),
        "total_candidates": total_candidates,
        "elapsed_seconds": elapsed,
        "strategy_results": strategy_results,
        "summary": summary_msg,
    }


def run_cold_scan(
    settings: Settings,
    universe: str | None = None,
    min_score: float | None = None,
    strategy: str = "CLASSIC_TECHNICAL",
    **kwargs: Any,
) -> None:
    """T0 Cold Scan: score the entire universe for a single strategy or all strategies in parallel."""
    strat_clean = strategy.upper()
    if strat_clean in ("ALL", "MULTI_STRATEGY_PARALLEL", "PARALLEL"):
        run_multi_strategy_parallel_scan(
            settings=settings,
            universe=universe,
            min_score=min_score or 30.0,
            record_schedule_event=True,
            **kwargs,
        )
        return

    job_id_map = {
        "CLASSIC_TECHNICAL": "breakout_cold_scan",
        "NSE_DELIVERY_ABSORPTION": "breakout_delivery_absorption_scan",
        "NSE_FO_CALL_WALL": "breakout_fo_call_wall_scan",
        "VOLUME_PROFILE_VAH": "breakout_volume_profile_scan",
        "DONCHIAN_TTM_SQUEEZE": "breakout_donchian_squeeze_scan",
    }
    job_id = job_id_map.get(strat_clean, "breakout_cold_scan")

    t0 = time.perf_counter()
    _pool["status"] = "running"
    _pool["error"] = None

    from earnings_engine.data.automation_schedules import record_job_start, record_job_finish
    record_job_start(job_id, settings)

    ticker_list = _resolve_universe_tickers(settings, universe)
    if strat_clean == "NSE_FO_CALL_WALL":
        ticker_list = [t for t in ticker_list if is_fno_eligible(t)]
    if not ticker_list:
        logger.info("[BREAKOUT-COLD] No tickers found to scan for %s.", strat_clean)
        _pool["status"] = "done"
        _pool["cold_tickers_scanned"] = 0
        now_iso = datetime.now(timezone.utc).isoformat()
        _pool["last_cold_scan_at"] = now_iso
        _pool["last_scan_at"] = now_iso
        record_job_finish(job_id, 0.0, f"No tickers found to scan for {strat_clean}.", settings=settings)
        return

    from concurrent.futures import ThreadPoolExecutor
    from earnings_engine.logging_utils import BatchProgressLogger
    from earnings_engine.data.prices import fetch_batch_live_quotes, load_prices_batch, load_price_metrics_batch
    from earnings_engine.data.catalysts_news import get_recent_catalysts_batch
    from earnings_engine.data.cross_strategy import compute_market_regime_multiplier

    # Always refresh live quotes for the full universe first (batched), then bulk
    # pre-load prices, metrics, catalysts, and macro conditions across all tickers
    try:
        fetch_batch_live_quotes(ticker_list, settings=settings, sync_db=True, max_workers=8, force=True)
    except Exception as e:
        logger.debug("[BREAKOUT-COLD] Batch live quote fetch warning: %s", e)

    prices_map = load_prices_batch(ticker_list, settings=settings)
    metrics_map = load_price_metrics_batch(ticker_list, settings=settings)
    catalysts_map = get_recent_catalysts_batch(ticker_list, limit_per_ticker=3, settings=settings)
    macro_info = None
    try:
        macro_info = compute_market_regime_multiplier(settings)
    except Exception as e:
        logger.debug("[BREAKOUT-MACRO] Macro precompute warning: %s", e)

    progress = BatchProgressLogger(
        name=f"breakout_{strat_clean.lower()}",
        total=len(ticker_list),
        unit="tickers",
        milestones=[20, 40, 60, 80, 100],
    )

    def _score(ticker: str) -> tuple[str, dict | None]:
        result = _dispatch_score_single_ticker(
            ticker,
            settings,
            strategy=strat_clean,
            prices_df=prices_map.get(ticker),
            metrics=metrics_map.get(ticker),
            catalysts=catalysts_map.get(ticker),
            macro_info=macro_info,
        )
        return ticker, result

    scored = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        for item in executor.map(_score, ticker_list):
            scored.append(item)
            progress.update(1)
    progress.finish()

    promoted_hot = 0
    promoted_warm = 0
    cands_found = 0
    for ticker, result in scored:
        if result is None:
            continue
        if (result.get("composite_score") or 0) >= (min_score or 30.0):
            cands_found += 1
        _promote(ticker, result, settings=settings)
        if ticker in _pool["hot"]:
            promoted_hot += 1
        elif ticker in _pool["warm"]:
            promoted_warm += 1

    _rebuild_candidates()
    save_breakout_pool_to_db(settings)

    # Batch-fetch and sync latest quotes for all discovered setups & hot stocks
    try:
        disc_tickers = [t for t, r in scored if r is not None and (r.get("composite_score") or 0) >= (min_score or 30.0)]
        hot_tickers = list({k.split("::")[0] for k in _pool.get("hot", {}).keys() if k})
        all_sync_tickers = list(dict.fromkeys(hot_tickers + disc_tickers))[:60]
        if all_sync_tickers:
            from earnings_engine.data.prices import fetch_batch_live_quotes
            fetch_batch_live_quotes(all_sync_tickers, settings=settings, sync_db=True, max_workers=10)
    except Exception as sync_err:
        logger.debug("[BREAKOUT-COLD] Auto-quote sync notice: %s", sync_err)

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

    strat_name = BREAKOUT_STRATEGIES.get(strat_clean, {}).get("name", strat_clean)
    summary_msg = f"{strat_name} sweep: {len(ticker_list)} tickers → {len(_pool['hot'])} hot, {len(_pool['warm'])} warm, {cands_found} setups"
    record_job_finish(job_id, elapsed, summary_msg, settings=settings)

    logger.info("[BREAKOUT-COLD] %s in %.1fs", summary_msg, elapsed)


def run_warm_rescore(settings: Settings) -> None:
    """T1 Warm Rescore: rescore only warm-pool setups."""
    warm_keys = list(_pool["warm"].keys())
    if not warm_keys:
        return

    t0 = time.perf_counter()
    from earnings_engine.data.automation_schedules import record_job_start, record_job_finish
    record_job_start("breakout_warm_rescore", settings)

    from earnings_engine.data.prices import fetch_batch_live_quotes, load_prices_batch, load_price_metrics_batch
    from earnings_engine.data.catalysts_news import get_recent_catalysts_batch
    from earnings_engine.data.cross_strategy import compute_market_regime_multiplier
    from concurrent.futures import ThreadPoolExecutor

    # 1. Extract tickers for live quote batch fetch (always live — bypass TTL cache)
    tickers_to_fetch = list({k.split("::")[0] for k in warm_keys})
    try:
        fetch_batch_live_quotes(tickers_to_fetch, settings=settings, sync_db=True, max_workers=8, force=True)
    except Exception as e:
        logger.debug("[BREAKOUT-WARM] Batch live quote fetch warning: %s", e)

    prices_map = load_prices_batch(tickers_to_fetch, settings=settings)
    metrics_map = load_price_metrics_batch(tickers_to_fetch, settings=settings)
    catalysts_map = get_recent_catalysts_batch(tickers_to_fetch, limit_per_ticker=3, settings=settings)
    macro_info = None
    try:
        macro_info = compute_market_regime_multiplier(settings)
    except Exception as e:
        logger.debug("[BREAKOUT-WARM] Macro precompute warning: %s", e)

    # 2. Rescore warm tickers per strategy
    def _score(key: str) -> tuple[str, dict | None]:
        parts = key.split("::")
        ticker = parts[0]
        strat = parts[1] if len(parts) > 1 else "CLASSIC_TECHNICAL"
        return key, _dispatch_score_single_ticker(
            ticker,
            settings,
            strategy=strat,
            use_live_quote=False,
            prices_df=prices_map.get(ticker),
            metrics=metrics_map.get(ticker),
            catalysts=catalysts_map.get(ticker),
            macro_info=macro_info,
        )

    with ThreadPoolExecutor(max_workers=6) as executor:
        scored = list(executor.map(_score, warm_keys))

    for key, result in scored:
        if result is None:
            _demote_warm(key, settings=settings)
            continue

        parts = key.split("::")
        ticker = parts[0]
        strat = parts[1] if len(parts) > 1 else "CLASSIC_TECHNICAL"
        result["strategy"] = strat

        new_score = result.get("composite_score", 0)
        if _should_be_hot(result):
            _promote(ticker, result, settings=settings)
        elif new_score >= WARM_THRESHOLD:
            _pool["warm"][key] = {"result": result, "consecutive_low": 0}
        elif new_score < WARM_DEMOTION_THRESHOLD:
            _demote_warm(key, settings=settings)
        else:
            if key in _pool["warm"]:
                _pool["warm"][key]["result"] = result

    _rebuild_candidates()
    save_breakout_pool_to_db(settings)

    elapsed = round(time.perf_counter() - t0, 2)
    now_iso = datetime.now(timezone.utc).isoformat()
    _pool["last_warm_scan_at"] = now_iso
    _pool["last_scan_at"] = now_iso

    summary_msg = f"Rescored {len(warm_keys)} warm setups (hot={len(_pool['hot'])}, warm={len(_pool['warm'])})"
    record_job_finish("breakout_warm_rescore", elapsed, summary_msg, settings=settings)

    logger.info(
        "[BREAKOUT-WARM] %s in %.1fs",
        summary_msg, elapsed,
    )


def run_hot_rescore(settings: Settings) -> None:
    """T2 Hot Rescore: rescore only hot-pool setups in parallel batches for maximum freshness."""
    hot_keys = list(_pool["hot"].keys())
    if not hot_keys:
        return

    t0 = time.perf_counter()
    from earnings_engine.data.automation_schedules import record_job_start, record_job_finish
    record_job_start("breakout_hot_rescore", settings)

    from earnings_engine.data.prices import fetch_batch_live_quotes
    from concurrent.futures import ThreadPoolExecutor

    # 1. Batch fetch latest live market quotes in parallel (single sub-second batch)
    tickers_to_fetch = list({k.split("::")[0] for k in hot_keys})
    try:
        fetch_batch_live_quotes(tickers_to_fetch, settings=settings, sync_db=True, max_workers=8, force=True)
    except Exception as e:
        logger.debug("[BREAKOUT-HOT] Batch live quote fetch warning: %s", e)

    from earnings_engine.data.prices import load_prices_batch, load_price_metrics_batch
    from earnings_engine.data.catalysts_news import get_recent_catalysts_batch
    from earnings_engine.data.cross_strategy import compute_market_regime_multiplier

    prices_map = load_prices_batch(tickers_to_fetch, settings=settings)
    metrics_map = load_price_metrics_batch(tickers_to_fetch, settings=settings)
    catalysts_map = get_recent_catalysts_batch(tickers_to_fetch, limit_per_ticker=3, settings=settings)
    macro_info = None
    try:
        macro_info = compute_market_regime_multiplier(settings)
    except Exception as e:
        logger.debug("[BREAKOUT-HOT] Macro precompute warning: %s", e)

    # 2. Rescore hot tickers with freshest prices
    def _score(key: str) -> tuple[str, dict | None]:
        parts = key.split("::")
        ticker = parts[0]
        strat = parts[1] if len(parts) > 1 else "CLASSIC_TECHNICAL"
        return key, _dispatch_score_single_ticker(
            ticker,
            settings,
            strategy=strat,
            use_live_quote=False,
            prices_df=prices_map.get(ticker),
            metrics=metrics_map.get(ticker),
            catalysts=catalysts_map.get(ticker),
            macro_info=macro_info,
        )

    with ThreadPoolExecutor(max_workers=6) as executor:
        scored = list(executor.map(_score, hot_keys))

    for key, result in scored:
        if result is None:
            _demote_hot(key, settings=settings)
            continue

        parts = key.split("::")
        ticker = parts[0]
        strat = parts[1] if len(parts) > 1 else "CLASSIC_TECHNICAL"
        result["strategy"] = strat

        new_score = result.get("composite_score", 0)
        if _should_be_hot(result):
            _pool["hot"][key] = {"result": result, "consecutive_low": 0}
        else:
            if key in _pool["hot"]:
                _pool["hot"][key]["result"] = result
                _demote_hot(key, settings=settings)

    _rebuild_candidates()
    save_breakout_pool_to_db(settings)

    elapsed = round(time.perf_counter() - t0, 2)
    now_iso = datetime.now(timezone.utc).isoformat()
    _pool["last_hot_scan_at"] = now_iso
    _pool["last_scan_at"] = now_iso

    summary_msg = f"Rescored {len(hot_keys)} hot setups (hot={len(_pool['hot'])}, warm={len(_pool['warm'])})"
    record_job_finish("breakout_hot_rescore", elapsed, summary_msg, settings=settings)

    logger.debug(
        "[BREAKOUT-HOT] %s in %.1fs",
        summary_msg, elapsed,
    )


# ---------------------------------------------------------------------------
# Full universe scan (backward-compatible, used for asof_date point-in-time)
# ---------------------------------------------------------------------------

def run_breakout_scan(
    settings: Settings,
    universe: str | None = None,
    asof_date: str | None = None,
    strategy: str = "CLASSIC_TECHNICAL",
) -> list[dict[str, Any]]:
    """Scan available tickers and return candidates sorted by score DESC point-in-time using the specified strategy."""
    strategy_clean = (strategy or "CLASSIC_TECHNICAL").upper().strip()
    if strategy_clean not in BREAKOUT_STRATEGIES:
        strategy_clean = "CLASSIC_TECHNICAL"

    if asof_date is None and strategy_clean == "CLASSIC_TECHNICAL":
        # Live classic scan: use the tiered pool system
        run_cold_scan(settings, universe=universe)
        return list(_pool["candidates"])

    from concurrent.futures import ThreadPoolExecutor
    from earnings_engine.data.prices import load_prices_batch, load_price_metrics_batch
    from earnings_engine.data.catalysts_news import get_recent_catalysts_batch
    from earnings_engine.data.cross_strategy import compute_market_regime_multiplier

    ticker_list = _resolve_universe_tickers(settings, universe)
    if strategy_clean == "NSE_FO_CALL_WALL":
        ticker_list = [t for t in ticker_list if is_fno_eligible(t)]
    if not ticker_list:
        return []

    t0 = time.perf_counter()

    prices_map = load_prices_batch(ticker_list, settings=settings)
    metrics_map = load_price_metrics_batch(ticker_list, settings=settings)
    catalysts_map = get_recent_catalysts_batch(ticker_list, limit_per_ticker=3, settings=settings)
    macro_info = None
    try:
        macro_info = compute_market_regime_multiplier(settings)
    except Exception as e:
        logger.debug("[BREAKOUT-SCAN] Macro precompute warning: %s", e)

    def _score(ticker: str) -> dict | None:
        return _dispatch_score_single_ticker(
            ticker,
            settings,
            asof_date=asof_date,
            strategy=strategy_clean,
            prices_df=prices_map.get(ticker),
            metrics=metrics_map.get(ticker),
            catalysts=catalysts_map.get(ticker),
            macro_info=macro_info,
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        scored = list(executor.map(_score, ticker_list))

    candidates = [c for c in scored if c is not None and c.get("composite_score", 0) >= BREAKOUT_MIN_SCORE]
    candidates.sort(key=lambda x: x["composite_score"], reverse=True)
    candidates = candidates[:BREAKOUT_MAX_CANDIDATES]

    elapsed = round(time.perf_counter() - t0, 2)
    logger.info(
        "[BREAKOUT] Scan (strategy=%s, asof=%s): %d tickers, %d candidates in %.1fs",
        strategy_clean, asof_date or "LIVE", len(ticker_list), len(candidates), elapsed,
    )
    return candidates
