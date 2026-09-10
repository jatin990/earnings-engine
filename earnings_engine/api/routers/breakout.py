"""Breakout Radar Scanner, Setup Tracking, and AI Outcome Auditing Routes."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query

from earnings_engine.api.dependencies import _settings
from earnings_engine.data import breakout_scanner as breakout_scanner_mod
from earnings_engine.logging_utils import get_logger

logger = get_logger("earnings_engine.api.routers.breakout")

router = APIRouter(tags=["Breakout Radar & Scanner"])


@router.get("/api/v1/breakout-radar/strategies")
async def get_breakout_strategies_endpoint():
    """Retrieve all available multi-strategy breakout models with descriptions and mathematical formulas."""
    strategies = breakout_scanner_mod.get_breakout_strategies()
    return {"success": True, "count": len(strategies), "strategies": strategies}


@router.get("/api/v1/breakout-radar")
async def get_breakout_radar_endpoint(
    universe: str | None = Query(None, description="Universe or watchlist to filter/scan (e.g. nifty_50, nse_top, nse_large_cap, us_top, all)"),
    strategy: str = Query("CLASSIC_TECHNICAL", description="Breakout strategy model (CLASSIC_TECHNICAL, NSE_DELIVERY_ABSORPTION, NSE_FO_CALL_WALL, VOLUME_PROFILE_VAH, DONCHIAN_TTM_SQUEEZE)"),
    min_score: float = Query(35.0, description="Minimum composite score to include"),
    limit: int = Query(50, ge=1, le=200, description="Max candidates to return"),
    sort_by: str = Query("composite_score", description="Sort field (composite_score, fundamental_score, resistance_score, volume_score, realized_return_pct)"),
    asof_date: str | None = Query(None, description="Point-in-time scan date in YYYY-MM-DD format"),
    live: bool = Query(False, description="Force live real-time price fetching for candidates"),
    real_tracked_only: bool = Query(False, description="Filter to show ONLY real-time tracked entries persisted in database archive"),
):
    """Return breakout candidates from the background scanner or point-in-time historical backtest."""
    import pandas as pd
    try:
        candidates = await asyncio.to_thread(
            breakout_scanner_mod.get_cached_scan_results,
            universe=universe,
            settings=_settings,
            asof_date=asof_date,
            strategy=strategy,
        )
        if candidates is None:
            candidates = []
        status = await asyncio.to_thread(breakout_scanner_mod.get_scan_status, universe=universe)

        # Reject any test or dummy tickers
        candidates = [c for c in candidates if not any(x in str(c.get("ticker", "")).upper() for x in ("TEST", "MOCK", "DUMMY"))]

        # Apply min_score filter
        candidates = [c for c in candidates if (c.get("composite_score") or 0) >= min_score]

        # Apply real_tracked_only filter if requested
        if real_tracked_only:
            candidates = [c for c in candidates if bool(c.get("is_real_tracked"))]

        # Synchronize candidate prices: auto-fetch live quotes for hot pool & candidate setups
        if candidates and not asof_date:
            candidate_tickers = [
                c.get("ticker")
                for c in candidates
                if c.get("ticker") and not any(x in str(c.get("ticker", "")).upper() for x in ("TEST", "MOCK", "DUMMY"))
            ]
            if candidate_tickers:
                import os
                from earnings_engine.data.prices import fetch_batch_live_quotes, get_latest_cached_prices
                from earnings_engine.data.db import is_server_environment

                is_serverless = is_server_environment() or os.environ.get("VERCEL") == "1" or os.environ.get("SERVERLESS") == "1"

                # Auto-sync top hot/active setups in parallel with sync_db=True (in serverless, only if live=True or dev)
                if live or not is_serverless:
                    try:
                        sync_tickers = candidate_tickers[:50]
                        live_quotes = fetch_batch_live_quotes(sync_tickers, settings=_settings, sync_db=True, max_workers=10)
                        for c in candidates:
                            t = c.get("ticker")
                            lq = live_quotes.get(t) if live_quotes else None
                            if lq and lq.get("current_price"):
                                cur_p = float(lq["current_price"])
                                c["current_price"] = cur_p
                                c["is_live"] = lq.get("is_live", True)
                                if lq.get("day_change_pct") is not None:
                                    c["day_change_pct"] = lq["day_change_pct"]
                                if lq.get("day_change") is not None:
                                    c["day_change"] = lq["day_change"]
                                if lq.get("day_high") is not None:
                                    c["day_high"] = lq["day_high"]
                                if lq.get("day_low") is not None:
                                    c["day_low"] = lq["day_low"]
                                if lq.get("volume") is not None:
                                    c["volume"] = lq["volume"]
                                c["current_date"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                                sig_p = c.get("predicted_value") or c.get("signal_price")
                                if sig_p and sig_p > 0:
                                    c["realized_return_pct"] = round(((cur_p - sig_p) / sig_p) * 100, 2)
                                trig = c.get("breakout_trigger")
                                if trig:
                                    c["breakout_happened"] = cur_p >= trig
                    except Exception as e:
                        logger.debug("Failed auto-sync live breakout batch refresh: %s", e)

                # Fallback to latest cached prices for any unsynced candidates
                try:
                    unsynced = [t for t in candidate_tickers if not any(c.get("ticker") == t and c.get("current_date") == datetime.now(timezone.utc).strftime("%Y-%m-%d") for c in candidates)]
                    if unsynced:
                        latest_prices = get_latest_cached_prices(unsynced, settings=_settings)
                        for c in candidates:
                            t = c.get("ticker")
                            if t in unsynced:
                                lp = latest_prices.get(t)
                                if lp and lp.get("close"):
                                    cur_p = float(lp["close"])
                                    c["current_price"] = cur_p
                                    c["current_date"] = lp.get("date") or c.get("current_date")
                                    sig_p = c.get("predicted_value") or c.get("signal_price")
                                    if sig_p and sig_p > 0:
                                        c["realized_return_pct"] = round(((cur_p - sig_p) / sig_p) * 100, 2)
                                    trig = c.get("breakout_trigger")
                                    if trig:
                                        c["breakout_happened"] = cur_p >= trig
                except Exception as e:
                    logger.debug("Failed syncing latest cached prices for remaining candidates: %s", e)

        # Compute prediction signals & color-coding for all candidates
        for c in candidates:
            cur_p = c.get("current_price")
            trig_p = c.get("breakout_trigger")
            target_p = c.get("target_price")
            stop_p = c.get("stop_loss")

            # Flag active breakout
            is_breaking = False
            if cur_p is not None and trig_p is not None and cur_p >= trig_p:
                is_breaking = True
            elif c.get("post_high") is not None and trig_p is not None and c.get("post_high") >= trig_p:
                is_breaking = True
            elif c.get("outcome") in ("TARGET_HIT", "BREAKOUT_SUCCEEDED"):
                is_breaking = True
            c["is_breaking_out"] = is_breaking

            if cur_p is not None:
                if target_p is not None and cur_p >= target_p:
                    c["prediction_signal"] = "TARGET_HIT"
                    c["prediction_color"] = "green"
                    c["prediction_label"] = "Target Hit 🎯"
                elif trig_p is not None and cur_p >= trig_p:
                    c["prediction_signal"] = "TRIGGERED"
                    c["prediction_color"] = "green"
                    c["prediction_label"] = "Breakout Fired 🚀"
                elif stop_p is not None and cur_p <= stop_p:
                    c["prediction_signal"] = "STOP_HIT"
                    c["prediction_color"] = "red"
                    c["prediction_label"] = "Stop Hit 🛑"
                elif trig_p is not None and stop_p is not None:
                    c["prediction_signal"] = "COILING"
                    c["prediction_color"] = "brown"
                    c["prediction_label"] = "Coiling 🗜️"
                else:
                    c["prediction_signal"] = "WATCH"
                    c["prediction_color"] = "blue"
                    c["prediction_label"] = "Watchlist ⏳"
            else:
                c["prediction_signal"] = "PENDING"
                c["prediction_color"] = "blue"
                c["prediction_label"] = "Pending ⏳"

        # Sort
        valid_sort = {
            "composite_score", "fundamental_score", "resistance_score", "volume_score",
            "compression_score", "momentum_score", "realized_return_pct", "predicted_value",
        }
        if sort_by not in valid_sort:
            sort_by = "composite_score"
        candidates.sort(key=lambda x: x.get(sort_by) or 0, reverse=True)

        # Compute historical outcome metrics if evaluating an older asof_date
        backtest_summary = {}
        if asof_date and candidates:
            evaluated = [c for c in candidates if c.get("outcome") is not None and c.get("outcome") != "PENDING"]
            if evaluated:
                # 1. Breakouts that actually fired (crossed / touched resistance trigger)
                fired_candidates = [
                    c for c in evaluated
                    if c.get("breakout_fired") is True
                    or (c.get("post_high") is not None and c.get("breakout_trigger") is not None and c.get("post_high") >= c.get("breakout_trigger"))
                    or (c.get("current_price") is not None and c.get("breakout_trigger") is not None and c.get("current_price") >= c.get("breakout_trigger"))
                    or c.get("outcome") in ("TARGET_HIT", "BREAKOUT_SUCCEEDED", "BREAKOUT_RETRACED")
                ]

                # Fired breakouts that succeeded / remain in profit (>= signal price or target)
                fired_successes = [
                    c for c in fired_candidates
                    if c.get("outcome") in ("TARGET_HIT", "BREAKOUT_SUCCEEDED")
                    or (c.get("current_price") is not None and c.get("signal_price") is not None and c.get("current_price") >= c.get("signal_price"))
                    or (c.get("realized_return_pct") or 0) >= 0
                ]
                fired_failures = [c for c in fired_candidates if c not in fired_successes]

                # Fired Win Rate % (strictly for setups that broke out)
                fired_win_rate = round(len(fired_successes) / len(fired_candidates) * 100, 1) if fired_candidates else 0.0

                # 2. Coiling setups (never reached trigger price)
                coiling_candidates = [c for c in evaluated if c not in fired_candidates]
                coiling_in_profit = [
                    c for c in coiling_candidates
                    if (c.get("realized_return_pct") or 0) >= 0 or c.get("outcome") == "COILING_IN_PROFIT"
                ]

                # Sub-category counts
                targets_hit = [c for c in evaluated if c.get("outcome") == "TARGET_HIT"]
                breakouts_succeeded = [c for c in evaluated if c.get("outcome") == "BREAKOUT_SUCCEEDED"]
                breakouts_retraced = [c for c in evaluated if c.get("outcome") == "BREAKOUT_RETRACED"]
                stop_losses_hit = [c for c in evaluated if c.get("outcome") in ("STOP_LOSS_HIT", "STOP_HIT")]
                setups_failed = [c for c in evaluated if c.get("outcome") in ("SETUP_FAILED", "BREAKOUT_FAILED")]

                returns = [c.get("realized_return_pct", 0) for c in evaluated if c.get("realized_return_pct") is not None]
                avg_return = round(sum(returns) / len(returns), 2) if returns else 0.0

                fired_returns = [c.get("realized_return_pct", 0) for c in fired_candidates if c.get("realized_return_pct") is not None]
                avg_fired_return = round(sum(fired_returns) / len(fired_returns), 2) if fired_returns else 0.0

                max_gains = [c.get("max_gain_pct", 0) for c in evaluated if c.get("max_gain_pct") is not None]
                avg_peak_gain = round(sum(max_gains) / len(max_gains), 2) if max_gains else 0.0
                top_winner = max(evaluated, key=lambda x: x.get("realized_return_pct", -999))

                backtest_summary = {
                    "asof_date": asof_date,
                    "total_evaluated": len(evaluated),
                    "breakout_fired_count": len(fired_candidates),
                    "breakout_fired_success_count": len(fired_successes),
                    "breakout_fired_failure_count": len(fired_failures),
                    "breakout_fired_win_rate_pct": fired_win_rate,
                    "win_rate_pct": fired_win_rate,
                    "success_count": len(fired_successes),
                    "coiling_count": len(coiling_candidates),
                    "coiling_in_profit_count": len(coiling_in_profit),
                    "targets_hit_count": len(targets_hit),
                    "breakouts_succeeded_count": len(breakouts_succeeded),
                    "breakouts_retraced_count": len(breakouts_retraced),
                    "stop_losses_hit_count": len(stop_losses_hit),
                    "setups_failed_count": len(setups_failed),
                    "avg_return_pct": avg_return,
                    "avg_fired_return_pct": avg_fired_return,
                    "avg_peak_gain_pct": avg_peak_gain,
                    "top_winner_ticker": top_winner.get("ticker"),
                    "top_winner_gain_pct": top_winner.get("realized_return_pct"),
                    "top_winner_price": top_winner.get("current_price"),
                }

        # Limit
        candidates = candidates[:limit]

        return {
            "success": True,
            "count": len(candidates),
            "asof_date": asof_date,
            "is_live": bool(live),
            "candidates": candidates,
            "setups": candidates,
            "universe": universe or "ALL",
            "scan_status": status,
            "backtest_summary": backtest_summary,
        }
    except Exception as e:
        logger.exception("Error in get_breakout_radar: %s", e)
        raise HTTPException(status_code=500, detail=f"Error fetching breakout radar: {str(e)}")


@router.post("/api/v1/breakout-radar/evaluate")
async def evaluate_breakout_candidates_endpoint(request: dict | None = None):
    """Trigger background scanning sweep of high-conviction breakout setups."""
    universe = (request or {}).get("universe") or (request or {}).get("market")
    try:
        results = await asyncio.to_thread(
            breakout_scanner_mod.run_breakout_scan,
            settings=_settings,
            universe=universe,
        )
        count = len(results) if results else 0
        return {"success": True, "detected_count": count, "message": f"Breakout scan complete. Found {count} setups."}
    except Exception as e:
        logger.exception("Error in evaluate_breakout_candidates: %s", e)
        raise HTTPException(status_code=500, detail=f"Breakout evaluation failed: {str(e)}")


@router.post("/api/v1/breakout-radar/refresh")
async def refresh_breakout_radar(
    universe: str | None = Query(None, description="Universe or watchlist to refresh scan for"),
    strategy: str = Query("ALL", description="Breakout strategy model (ALL, CLASSIC_TECHNICAL, NSE_DELIVERY_ABSORPTION, NSE_FO_CALL_WALL, VOLUME_PROFILE_VAH, DONCHIAN_TTM_SQUEEZE)"),
):
    """Trigger an immediate re-scan of tickers (runs in a background thread)."""
    import threading

    def _run():
        try:
            strat_clean = (strategy or "ALL").upper().strip()
            if strat_clean in ("ALL", "*"):
                for s_key in breakout_scanner_mod.BREAKOUT_STRATEGIES.keys():
                    try:
                        breakout_scanner_mod.run_breakout_scan(_settings, universe=universe, strategy=s_key)
                    except Exception as s_err:
                        logger.debug("[BREAKOUT] Multi-strategy refresh error for %s: %s", s_key, s_err)
            else:
                breakout_scanner_mod.run_breakout_scan(_settings, universe=universe, strategy=strat_clean)
        except Exception as e:
            logger.error("[BREAKOUT] Manual refresh error: %s", e)

    t = threading.Thread(target=_run, daemon=True, name="breakout_manual_refresh")
    t.start()
    return {"success": True, "message": f"Breakout scan ({strategy}) triggered for {universe or 'all universes'} in background. Check /api/v1/breakout-radar shortly."}


@router.get("/api/v1/breakout-radar/search")
async def search_breakout_stocks(
    q: str = Query(..., min_length=1, description="Ticker or company name search query"),
    limit: int = Query(15, ge=1, le=50, description="Max autocomplete matches"),
):
    """Fast auto-complete search for stocks across price cache and universe registry."""
    matches = await asyncio.to_thread(
        breakout_scanner_mod.search_breakout_tickers,
        query=q,
        limit=limit,
        settings=_settings,
    )
    return {"success": True, "query": q, "matches": matches}


@router.get("/api/v1/breakout-radar/status")
async def get_breakout_scan_status(
    universe: str | None = Query(None, description="Universe filter"),
):
    """Retrieve current breakout scanner status and metadata."""
    try:
        status = await asyncio.to_thread(breakout_scanner_mod.get_scan_status, universe=universe)
        return {"success": True, **status}
    except Exception as e:
        logger.exception("Error in get_breakout_scan_status: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/v1/breakout-radar/audit-log")
async def get_breakout_audit_log_endpoint(
    ticker: str | None = Query(None, description="Filter by ticker"),
    strategy: str | None = Query(None, description="Filter by strategy (e.g. CLASSIC_TECHNICAL, NSE_DELIVERY_ABSORPTION, etc.)"),
    limit: int = Query(50, ge=1, le=200),
):
    """Retrieve historical audit logs of tracked breakout signals."""
    try:
        logs = await asyncio.to_thread(
            breakout_scanner_mod.get_breakout_audit_log,
            ticker=ticker,
            limit=limit,
            strategy=strategy,
            settings=_settings,
        )
        total_count = await asyncio.to_thread(
            breakout_scanner_mod.get_breakout_audit_log_count,
            ticker=ticker,
            strategy=strategy,
            settings=_settings,
        )
        return {"success": True, "count": len(logs), "total_count": total_count, "logs": logs}
    except Exception as e:
        logger.exception("Error in get_breakout_audit_log: %s", e)
        raise HTTPException(status_code=500, detail=f"Error fetching breakout audit log: {str(e)}")


@router.get("/api/v1/breakout-radar/history/{ticker}")
async def get_breakout_stock_history_endpoint(
    ticker: str,
):
    """Retrieve full chronological lifecycle timeline & transition notes for a single stock."""
    try:
        data = await asyncio.to_thread(
            breakout_scanner_mod.get_stock_breakout_timeline,
            ticker=ticker,
            settings=_settings,
        )
        return data
    except Exception as e:
        logger.exception("Error in get_breakout_stock_history: %s", e)
        raise HTTPException(status_code=500, detail=f"Error fetching stock breakout history: {str(e)}")


@router.get("/api/v1/breakout/tracked")
@router.get("/api/v1/breakout-radar/tracked")
async def get_tracked_breakouts_endpoint(
    days: int | None = Query(None, description="Preset window in days (e.g. 1, 3, 7, 14, 30)"),
    start_date: str | None = Query(None, description="Start date filter in YYYY-MM-DD format"),
    end_date: str | None = Query(None, description="End date filter in YYYY-MM-DD format"),
    tier: str | None = Query(None, description="Filter by tier: ALL, HOT, WARM"),
    outcome: str | None = Query(None, description="Filter by outcome: ALL, TRIGGERED, TARGET_HIT, ACTIVE, STOP_HIT"),
    strategy: str | None = Query(None, description="Filter by breakout strategy model"),
    sort_by: str = Query("signal_date", description="Sort field (signal_date, return_pct, max_gain, score, days_elapsed)"),
    limit: int = Query(200, ge=1, le=500, description="Max records to return"),
    live: bool = Query(False, description="Optionally refresh current prices and realized returns"),
):
    """Retrieve permanently tracked breakout setups over customizable timeframes and date ranges."""
    try:
        data = await asyncio.to_thread(
            breakout_scanner_mod.get_tracked_breakouts,
            days=days,
            start_date=start_date,
            end_date=end_date,
            tier=tier,
            outcome=outcome,
            strategy=strategy,
            sort_by=sort_by,
            limit=limit,
            live=live,
            settings=_settings,
        )
        return data
    except Exception as e:
        logger.exception("Error in get_tracked_breakouts_endpoint: %s", e)
        raise HTTPException(status_code=500, detail=f"Error fetching tracked breakouts: {str(e)}")


@router.delete("/api/v1/breakout/tracked/{id}")
@router.delete("/api/v1/breakout-radar/tracked/{id}")
async def delete_tracked_breakout_endpoint(id: int):
    """Untrack / delete a single breakout setup by its unique record ID."""
    try:
        success = await asyncio.to_thread(
            breakout_scanner_mod.delete_tracked_breakout,
            setup_id=id,
            settings=_settings,
        )
        if not success:
            raise HTTPException(status_code=404, detail=f"Tracked breakout setup #{id} not found")
        return {
            "success": True,
            "id": id,
            "message": f"Successfully untracked breakout setup #{id}",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error in delete_tracked_breakout_endpoint: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to untrack setup: {str(e)}")


@router.delete("/api/v1/breakout/tracked/ticker/{ticker}")
@router.delete("/api/v1/breakout-radar/tracked/ticker/{ticker}")
async def delete_tracked_breakouts_by_ticker_endpoint(ticker: str):
    """Untrack / delete all breakout setups for a given ticker."""
    try:
        sym = ticker.strip()
        deleted_count = await asyncio.to_thread(
            breakout_scanner_mod.delete_tracked_breakouts_by_ticker,
            ticker=sym,
            settings=_settings,
        )
        return {
            "success": True,
            "ticker": sym,
            "deleted_count": deleted_count,
            "message": f"Successfully untracked {deleted_count} setups for {sym}",
        }
    except Exception as e:
        logger.exception("Error in delete_tracked_breakouts_by_ticker_endpoint: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to untrack setups for ticker: {str(e)}")


@router.get("/api/v1/breakout-radar/backtest")
async def run_breakout_historical_backtest(
    universe: str | None = Query(None, description="Universe or watchlist to run backtest on"),
):
    """Run an on-demand historical backtest sweep over 30/45/60/75/90 day periods."""
    try:
        stats = await asyncio.to_thread(
            breakout_scanner_mod.run_historical_backtest,
            settings=_settings,
            universe=universe,
        )
        return stats
    except Exception as e:
        logger.exception("Error in run_breakout_historical_backtest: %s", e)
        raise HTTPException(status_code=500, detail=f"Backtest run failed: {str(e)}")


@router.get("/api/v1/breakout-radar/evaluate/{ticker}")
async def evaluate_single_breakout(
    ticker: str,
    asof_date: str | None = Query(None, description="Point-in-time evaluation date in YYYY-MM-DD format"),
    force_tier: str | None = Query(None, description="Force promotion into 'hot' or 'warm' tier pool"),
    strategy: str = Query("CLASSIC_TECHNICAL", description="Breakout strategy model"),
):
    """Evaluate breakout potential for a single ticker."""
    sym = ticker.strip().upper()
    try:
        result = await asyncio.to_thread(
            breakout_scanner_mod.evaluate_stock_breakout,
            ticker=sym,
            asof_date=asof_date,
            force_tier=force_tier,
            strategy=strategy,
            settings=_settings,
        )
        return result
    except Exception as e:
        logger.exception("Error evaluating breakout for %s: %s", sym, e)
        raise HTTPException(status_code=500, detail=f"Error evaluating breakout: {str(e)}")


@router.post("/api/v1/breakout-radar/set-tier/{ticker}")
async def set_breakout_tier(
    ticker: str,
    tier: str = Query(..., description="Target tier: 'hot', 'warm', or 'cold'"),
):
    """Manually assign or promote a stock into Hot, Warm, or Cold breakout tier."""
    sym = ticker.strip().upper()
    try:
        result = await asyncio.to_thread(
            breakout_scanner_mod.set_ticker_tier,
            ticker=sym,
            tier=tier,
            settings=_settings,
        )
        return result
    except Exception as e:
        logger.exception("Error setting breakout tier for %s: %s", sym, e)
        raise HTTPException(status_code=500, detail=f"Failed to set breakout tier: {str(e)}")


@router.get("/api/v1/breakout-radar/ai-reasoning/{ticker}")
@router.post("/api/v1/breakout-radar/ai-reasoning/{ticker}")
async def get_breakout_ai_reasoning_endpoint(
    ticker: str,
    model_name: str | None = Query(None, description="Local Ollama model name"),
):
    """Return structured AI reasoning breakdown for a detected breakout setup."""
    sym = ticker.strip().upper()
    try:
        reasoning = await asyncio.to_thread(
            breakout_scanner_mod.generate_breakout_ai_reasoning,
            ticker=sym,
            model_name=model_name,
            settings=_settings,
        )
        res = {"success": True, "ticker": sym}
        if isinstance(reasoning, dict):
            res.update(reasoning)
            if "reasoning" not in res:
                res["reasoning"] = reasoning.get("thesis") or reasoning.get("summary") or str(reasoning)
        else:
            res["reasoning"] = str(reasoning) if reasoning else "Technical consolidation setup."
        return res
    except Exception as e:
        logger.exception("Error fetching breakout AI reasoning for %s: %s", sym, e)
        raise HTTPException(status_code=500, detail=f"Error fetching AI reasoning: {str(e)}")


# ---------------------------------------------------------------------------
# Multi-Strategy Parallel Scheduling & Automation Integration
# ---------------------------------------------------------------------------

@router.get("/api/v1/breakout-radar/schedules")
async def get_breakout_schedules_endpoint():
    """Retrieve all active and registered breakout scanning schedules and cadence states."""
    from earnings_engine.data.automation_schedules import get_all_schedules
    all_s = await asyncio.to_thread(get_all_schedules, _settings)
    breakout_schedules = [s for s in all_s if s.get("category") == "Breakout Radar" or str(s.get("job_id", "")).startswith("breakout")]
    return {"success": True, "count": len(breakout_schedules), "schedules": breakout_schedules}


@router.get("/api/v1/breakout-radar/status")
async def get_breakout_status_endpoint(universe: str | None = Query(None)):
    """Check current background scan execution status and pool metrics."""
    status = await asyncio.to_thread(breakout_scanner_mod.get_scan_status, universe=universe)
    return {
        "success": True,
        "status": status.get("status", "idle"),
        "is_scanning": status.get("status") == "running",
        "last_scan_at": status.get("last_scan_at"),
        "last_scan_duration_s": status.get("last_scan_duration_s", 0.0),
        "hot_count": status.get("hot_count", 0),
        "warm_count": status.get("warm_count", 0),
        "candidates_count": status.get("candidates_count", 0),
        "error": status.get("error"),
    }


@router.post("/api/v1/breakout-radar/refresh")
async def refresh_breakout_radar_endpoint(
    universe: str | None = Query(None),
    strategy: str = Query("CLASSIC_TECHNICAL"),
):
    """Schedule breakout scan in background."""
    from earnings_engine.data.scheduler_engine import get_scheduler_engine
    engine = get_scheduler_engine()
    job_id = "breakout_all_strategies_parallel" if strategy.upper() in ("ALL", "*") else f"breakout_{strategy.lower()}_scan"
    if job_id not in engine.handlers:
        job_id = "breakout_all_strategies_parallel"
    dispatched = engine.dispatch_job(job_id, _settings)
    return {
        "success": True,
        "status": "scheduled",
        "job_id": job_id,
        "dispatched": dispatched,
        "message": "Breakout scan is scheduled in the background. Please check back in a few moments as data is populated.",
    }


@router.post("/api/v1/breakout-radar/schedules/parallel-scan")
async def trigger_breakout_parallel_scan_endpoint(
    universe: str | None = Query(None, description="Universe to scan in parallel (e.g. NSE_ALL)"),
    min_score: float = Query(30.0, description="Minimum composite score threshold"),
    background: bool = Query(True, description="Run in background thread without waiting"),
):
    """Trigger parallel multi-strategy breakout scan across all 5 quantitative models asynchronously."""
    from earnings_engine.data.scheduler_engine import get_scheduler_engine
    engine = get_scheduler_engine()
    job_id = "breakout_all_strategies_parallel"
    dispatched = engine.dispatch_job(job_id, _settings)
    return {
        "success": True,
        "status": "scheduled",
        "job_id": job_id,
        "dispatched": dispatched,
        "message": "Parallel 5-strategy breakout scan is scheduled in the background. Please check back in a few moments as data is populated.",
    }


@router.post("/api/v1/breakout-radar/schedules/configure")
async def configure_breakout_schedule_endpoint(
    job_id: str = Query(..., description="Job ID (e.g. breakout_all_strategies_parallel, breakout_delivery_absorption_scan)"),
    interval_seconds: int | None = Query(None, ge=30, le=86400, description="Scan interval in seconds"),
    is_enabled: bool | None = Query(None, description="Enable or disable schedule"),
    status: str | None = Query(None, description="Status: 'active' or 'paused'"),
):
    """Update cadence interval or enabled state for any breakout strategy schedule."""
    from earnings_engine.data.automation_schedules import update_schedule
    updates = {}
    if interval_seconds is not None:
        updates["interval_seconds"] = interval_seconds
    if is_enabled is not None:
        updates["is_enabled"] = is_enabled
    if status is not None:
        updates["status"] = status

    try:
        updated = await asyncio.to_thread(update_schedule, job_id, updates, _settings)
        return {"success": True, "message": f"Updated schedule '{job_id}'", "schedule": updated}
    except Exception as e:
        logger.exception("Error configuring breakout schedule %s: %s", job_id, e)
        raise HTTPException(status_code=500, detail=f"Failed to configure schedule: {str(e)}")


@router.post("/api/v1/breakout-radar/schedules/{job_id}/trigger")
async def trigger_breakout_single_schedule_endpoint(job_id: str):
    """Trigger immediate execution of a specific breakout strategy schedule asynchronously in the background."""
    from earnings_engine.data.scheduler_engine import get_scheduler_engine
    engine = get_scheduler_engine()
    dispatched = engine.dispatch_job(job_id, _settings)
    return {
        "success": True,
        "status": "scheduled",
        "job_id": job_id,
        "dispatched": dispatched,
        "message": f"Breakout scan for '{job_id}' is scheduled in the background. Please check back in a few moments as data is populated." if dispatched else f"Job '{job_id}' is already running.",
    }

