"""Breakout Radar Scanner, Setup Tracking, and AI Outcome Auditing Routes."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Query

from earnings_engine.api.dependencies import _settings
from earnings_engine.data import breakout_scanner as breakout_scanner_mod
from earnings_engine.logging_utils import get_logger

logger = get_logger("earnings_engine.api.routers.breakout")

router = APIRouter(tags=["Breakout Radar & Scanner"])


@router.get("/api/v1/breakout-radar")
async def get_breakout_radar_endpoint(
    universe: str | None = Query(None, description="Universe or watchlist to filter/scan (e.g. nifty_50, nse_top, nse_large_cap, us_top, all)"),
    min_score: float = Query(35.0, description="Minimum composite score to include"),
    limit: int = Query(50, ge=1, le=200, description="Max candidates to return"),
    sort_by: str = Query("composite_score", description="Sort field (composite_score, fundamental_score, resistance_score, volume_score, realized_return_pct)"),
    asof_date: str | None = Query(None, description="Point-in-time scan date in YYYY-MM-DD format"),
    live: bool = Query(False, description="Force live real-time price fetching for candidates"),
):
    """Return breakout candidates from the background scanner or point-in-time historical backtest."""
    import pandas as pd
    try:
        candidates = await asyncio.to_thread(
            breakout_scanner_mod.get_cached_scan_results,
            universe=universe,
            settings=_settings,
            asof_date=asof_date,
        )
        if candidates is None:
            candidates = []
        status = await asyncio.to_thread(breakout_scanner_mod.get_scan_status, universe=universe)

        # Apply min_score filter
        candidates = [c for c in candidates if (c.get("composite_score") or 0) >= min_score]

        # Live parallel price fetching if requested
        if live and candidates and not asof_date:
            from concurrent.futures import ThreadPoolExecutor
            from earnings_engine.data.prices import fetch_prices
            
            def _fetch_live(c: dict[str, Any]) -> None:
                t = c.get("ticker")
                if not t:
                    return
                try:
                    df = fetch_prices(t, _settings, force=True)
                    if not df.empty and "close" in df.columns:
                        closes = pd.to_numeric(df["close"], errors="coerce").dropna()
                        if not closes.empty:
                            cur_p = round(float(closes.iloc[-1]), 2)
                            c["current_price"] = cur_p
                            c["current_date"] = str(df.index[-1])[:10]
                            sig_p = c.get("predicted_value") or c.get("signal_price")
                            if sig_p and sig_p > 0:
                                c["realized_return_pct"] = round(((cur_p - sig_p) / sig_p) * 100, 2)
                            trig = c.get("breakout_trigger")
                            if trig:
                                c["breakout_happened"] = cur_p >= trig
                except Exception as e:
                    logger.debug("Failed live breakout refresh for %s: %s", t, e)

            with ThreadPoolExecutor(max_workers=min(10, len(candidates))) as pool:
                list(pool.map(_fetch_live, candidates))

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
            evaluated = [c for c in candidates if c.get("breakout_happened") is not None]
            if evaluated:
                successes = [c for c in evaluated if c.get("breakout_happened") is True]
                targets_hit = [c for c in evaluated if c.get("outcome") == "TARGET_HIT"]
                breakouts_succeeded = [c for c in evaluated if c.get("outcome") == "BREAKOUT_SUCCEEDED"]
                stop_losses_hit = [c for c in evaluated if c.get("outcome") == "STOP_LOSS_HIT"]
                no_breakouts = [c for c in evaluated if c.get("outcome") in ("NO_BREAKOUT", "FAILED")]
                win_rate = round(len(successes) / len(evaluated) * 100, 1)
                returns = [c.get("realized_return_pct", 0) for c in evaluated]
                avg_return = round(sum(returns) / len(returns), 2)
                max_gains = [c.get("max_gain_pct", 0) for c in evaluated if c.get("max_gain_pct") is not None]
                avg_peak_gain = round(sum(max_gains) / len(max_gains), 2) if max_gains else 0.0
                top_winner = max(evaluated, key=lambda x: x.get("realized_return_pct", -999))
                backtest_summary = {
                    "asof_date": asof_date,
                    "total_evaluated": len(evaluated),
                    "success_count": len(successes),
                    "targets_hit_count": len(targets_hit),
                    "breakouts_succeeded_count": len(breakouts_succeeded),
                    "stop_losses_hit_count": len(stop_losses_hit),
                    "no_breakout_count": len(no_breakouts),
                    "win_rate_pct": win_rate,
                    "avg_return_pct": avg_return,
                    "avg_peak_gain_pct": avg_peak_gain,
                    "top_winner_ticker": top_winner.get("ticker"),
                    "top_winner_gain_pct": top_winner.get("realized_return_pct"),
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
):
    """Trigger an immediate re-scan of tickers (runs in a background thread)."""
    import threading

    def _run():
        try:
            breakout_scanner_mod.run_breakout_scan(_settings, universe=universe)
        except Exception as e:
            logger.error("[BREAKOUT] Manual refresh error: %s", e)

    t = threading.Thread(target=_run, daemon=True, name="breakout_manual_refresh")
    t.start()
    return {"success": True, "message": f"Breakout scan triggered for {universe or 'all universes'} in background. Check /api/v1/breakout-radar shortly."}


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
    limit: int = Query(50, ge=1, le=200),
):
    """Retrieve historical audit logs of tracked breakout signals."""
    try:
        logs = await asyncio.to_thread(
            breakout_scanner_mod.get_breakout_audit_log,
            ticker=ticker,
            limit=limit,
            settings=_settings,
        )
        return {"success": True, "count": len(logs), "logs": logs}
    except Exception as e:
        logger.exception("Error in get_breakout_audit_log: %s", e)
        raise HTTPException(status_code=500, detail=f"Error fetching breakout audit log: {str(e)}")


@router.get("/api/v1/breakout-radar/evaluate/{ticker}")
async def evaluate_single_breakout(
    ticker: str,
    asof_date: str | None = Query(None, description="Point-in-time evaluation date in YYYY-MM-DD format"),
    force_tier: str | None = Query(None, description="Force promotion into 'hot' or 'warm' tier pool"),
):
    """Evaluate breakout potential for a single ticker."""
    sym = ticker.strip().upper()
    try:
        result = await asyncio.to_thread(
            breakout_scanner_mod.evaluate_stock_breakout,
            ticker=sym,
            asof_date=asof_date,
            force_tier=force_tier,
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
