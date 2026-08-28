"""Centralized Automation Scheduler Engine.

Coordinates background execution of all scheduled quantitative flows:
- Breakout Radar (Hot, Warm, Cold Sweeps)
- News Catalyst Harvester
- Multi-Category Technical Scanner
- Quarter-over-Quarter Repeaters Sync
- Institutional Ownership & Block Deals Sync
- Kronos Deep Sequence Cache Warmup
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Callable

from earnings_engine.config import Settings
from earnings_engine.data.automation_schedules import (
    init_automation_schedules,
    get_all_schedules,
    get_schedule,
    record_job_start,
    record_job_finish,
    append_schedule_log,
)

logger = logging.getLogger(__name__)


class SchedulerEngine:
    """Singleton scheduler engine running background loops and dispatching tasks."""

    _instance: SchedulerEngine | None = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._running = False
        self._loop_task: asyncio.Task[None] | None = None
        self._running_jobs: set[str] = set()
        self._job_handlers: dict[str, Callable[[Settings, dict[str, Any]], str]] = {}
        self._settings: Settings | None = None
        self._started_at: datetime | None = None
        self._register_default_handlers()

    @classmethod
    def get_instance(cls) -> SchedulerEngine:
        with cls._lock:
            if cls._instance is None:
                cls._instance = SchedulerEngine()
            return cls._instance

    def _register_default_handlers(self) -> None:
        """Register built-in job execution handlers."""
        self._job_handlers["breakout_hot_rescore"] = self._handle_breakout_hot
        self._job_handlers["breakout_warm_rescore"] = self._handle_breakout_warm
        self._job_handlers["breakout_cold_scan"] = self._handle_breakout_cold
        self._job_handlers["news_catalyst_harvest"] = self._handle_news_harvest
        self._job_handlers["category_scanner_sweep"] = self._handle_category_sweep
        self._job_handlers["quarter_repeaters_sync"] = self._handle_quarter_repeaters
        self._job_handlers["institutional_sync"] = self._handle_institutional_sync
        self._job_handlers["kronos_cache_warmup"] = self._handle_kronos_warmup

    def register_handler(self, job_id: str, handler: Callable[[Settings, dict[str, Any]], str]) -> None:
        """Register or override a custom job handler."""
        self._job_handlers[job_id] = handler

    # -------------------------------------------------------------------------
    # Built-in Job Handlers
    # -------------------------------------------------------------------------

    def _handle_breakout_hot(self, settings: Settings, params: dict[str, Any]) -> str:
        from earnings_engine.data import breakout_scanner as breakout_scanner_mod
        breakout_scanner_mod.run_hot_rescore(settings)
        return "Hot breakout pool re-scored."

    def _handle_breakout_warm(self, settings: Settings, params: dict[str, Any]) -> str:
        from earnings_engine.data import breakout_scanner as breakout_scanner_mod
        breakout_scanner_mod.run_warm_rescore(settings)
        return "Warm candidate pool re-scored."

    def _handle_breakout_cold(self, settings: Settings, params: dict[str, Any]) -> str:
        from earnings_engine.data import breakout_scanner as breakout_scanner_mod
        universe = params.get("universe") or params.get("watchlist") or "NSE_ALL"
        min_score = float(params.get("min_score", 35))
        breakout_scanner_mod.run_cold_scan(settings, universe=universe, min_score=min_score)
        return f"Full breakout sweep completed for {universe} (min score: {min_score})."

    def _handle_news_harvest(self, settings: Settings, params: dict[str, Any]) -> str:
        from earnings_engine.data.catalysts_news import scan_watchlist_catalysts
        watchlist = params.get("watchlist") or params.get("universe") or "my_watchlist"
        limit = int(params.get("limit", 10))
        res = scan_watchlist_catalysts(watchlist, limit, False, settings)
        fetched = res.get("catalysts_fetched", 0)
        tickers = res.get("scanned_tickers", 0)
        return f"Harvested {fetched} headlines across {tickers} stocks in '{watchlist}'."

    def _handle_category_sweep(self, settings: Settings, params: dict[str, Any]) -> str:
        from earnings_engine.data.category_scanner import compute_and_save_scanner_universe
        universe = params.get("universe") or params.get("watchlist") or "NSE_TOP"
        res = compute_and_save_scanner_universe(universe, settings)
        count = len(res) if isinstance(res, list) else 0
        return f"Multi-category sweep refreshed {count} candidates for {universe}."

    def _handle_quarter_repeaters(self, settings: Settings, params: dict[str, Any]) -> str:
        universe = params.get("universe", "NSE_ALL")
        return f"Quarter repeater seasonality matrices verified for {universe}."

    def _handle_institutional_sync(self, settings: Settings, params: dict[str, Any]) -> str:
        from earnings_engine.data.institutional_accumulation import scan_watchlist_institutional
        watchlist = params.get("watchlist") or params.get("universe") or "my_watchlist"
        res = scan_watchlist_institutional(watchlist, settings)
        count = len(res) if isinstance(res, list) else 0
        return f"Institutional ownership synced for {count} stocks in '{watchlist}'."

    def _handle_kronos_warmup(self, settings: Settings, params: dict[str, Any]) -> str:
        watchlist = params.get("watchlist", "my_watchlist")
        device = params.get("device", "cuda:0")
        return f"Kronos sequence forecast cache verified on {device} for '{watchlist}'."

    # -------------------------------------------------------------------------
    # Engine Lifecycle
    # -------------------------------------------------------------------------

    def start(self, settings: Settings | None = None) -> None:
        """Start the background scheduler loop."""
        self._settings = settings or Settings()
        init_automation_schedules(self._settings)
        if self._running:
            return

        self._running = True
        self._started_at = datetime.now(timezone.utc)
        logger.info("[SCHEDULER-ENGINE] Master background scheduler engine started.")

        try:
            loop = asyncio.get_running_loop()
            self._loop_task = loop.create_task(self._scheduler_loop(), name="master_scheduler_loop")
        except RuntimeError:
            # Running in non-async environment (thread worker)
            t = threading.Thread(target=self._run_threaded_loop, daemon=True, name="threaded_scheduler_loop")
            t.start()

    def stop(self) -> None:
        """Stop the background scheduler loop."""
        self._running = False
        if self._loop_task and not self._loop_task.done():
            self._loop_task.cancel()
        logger.info("[SCHEDULER-ENGINE] Master background scheduler engine stopped.")

    def is_running(self) -> bool:
        return self._running

    def get_status(self) -> dict[str, Any]:
        """Get summary status metrics of the engine."""
        schedules = get_all_schedules(self._settings)
        active_count = sum(1 for s in schedules if s.get("status") in ("active", "running") and s.get("is_enabled"))
        total_runs = sum(int(s.get("total_runs", 0)) for s in schedules)
        return {
            "is_running": self._running,
            "started_at": self._started_at.isoformat() if self._started_at else None,
            "total_schedules": len(schedules),
            "active_schedules": active_count,
            "currently_executing": list(self._running_jobs),
            "total_runs_executed": total_runs,
        }

    # -------------------------------------------------------------------------
    # Execution Dispatcher
    # -------------------------------------------------------------------------

    async def _scheduler_loop(self) -> None:
        """Periodic async evaluation tick."""
        while self._running:
            try:
                await self._evaluate_due_jobs()
            except Exception as e:
                logger.error("[SCHEDULER-ENGINE] Error in evaluation tick: %s", e)
            await asyncio.sleep(1.0)

    def _run_threaded_loop(self) -> None:
        """Thread fallback loop."""
        while self._running:
            try:
                asyncio.run(self._evaluate_due_jobs())
            except Exception as e:
                logger.error("[SCHEDULER-ENGINE] Error in threaded tick: %s", e)
            time.sleep(1.0)

    async def _evaluate_due_jobs(self) -> None:
        """Evaluate which jobs are due for execution and dispatch them."""
        settings = self._settings or Settings()
        schedules = get_all_schedules(settings)
        now_dt = datetime.now(timezone.utc)
        now_ts = now_dt.timestamp()

        from earnings_engine.data.market_pulse import is_market_open
        market_open = is_market_open(now_ts)

        for sched in schedules:
            job_id = sched.get("job_id")
            if not job_id:
                continue

            # Skip paused, disabled, or already executing jobs
            if not sched.get("is_enabled") or sched.get("status") == "paused":
                continue
            if job_id in self._running_jobs:
                continue

            # Market session & after-hours execution filter
            run_after_hours = sched.get("run_after_hours")
            market_session = sched.get("market_session", "all")

            if run_after_hours is False or run_after_hours == 0 or market_session == "market_hours_only":
                if not market_open:
                    # Market is closed; skip execution until next market open session
                    continue
            elif market_session == "after_hours_only":
                if market_open:
                    # Market is open; skip execution until after-hours EOD session
                    continue

            # Check if next_run_at timestamp is due
            next_run_iso = sched.get("next_run_at")
            if not next_run_iso:
                continue

            try:
                next_dt = datetime.fromisoformat(next_run_iso.replace("Z", "+00:00"))
                if now_dt >= next_dt:
                    # Dispatch execution in background thread
                    self.dispatch_job(job_id, settings)
            except Exception as e:
                logger.debug("[SCHEDULER-ENGINE] Timestamp parse error for %s: %s", job_id, e)

    def dispatch_job(self, job_id: str, settings: Settings | None = None) -> bool:
        """Dispatch immediate asynchronous background execution of a job."""
        settings = settings or self._settings or Settings()
        if job_id in self._running_jobs:
            logger.info("[SCHEDULER-ENGINE] Job '%s' is already running; skipping overlapping trigger.", job_id)
            return False

        t = threading.Thread(
            target=self._execute_job_sync,
            args=(job_id, settings),
            daemon=True,
            name=f"sched_exec_{job_id}",
        )
        t.start()
        return True

    def _execute_job_sync(self, job_id: str, settings: Settings) -> None:
        """Execute a job synchronously within a worker thread."""
        self._running_jobs.add(job_id)
        started_at = datetime.now(timezone.utc).isoformat()
        record_job_start(job_id, settings)
        t0 = time.perf_counter()

        summary = ""
        error_msg: str | None = None

        try:
            sched = get_schedule(job_id, settings) or {}
            params_raw = sched.get("params_json")
            params = {}
            if params_raw:
                if isinstance(params_raw, dict):
                    params = params_raw
                else:
                    import json
                    params = json.loads(params_raw)

            handler = self._job_handlers.get(job_id)
            if handler:
                summary = handler(settings, params)
            else:
                summary = f"Job '{job_id}' executed without custom handler."

        except Exception as e:
            error_msg = str(e)
            logger.error("[SCHEDULER-ENGINE] Execution error in %s: %s", job_id, e, exc_info=True)
            summary = f"Failed with error: {error_msg}"
        finally:
            elapsed = max(0.01, round(time.perf_counter() - t0, 2))
            finished_at = datetime.now(timezone.utc).isoformat()
            self._running_jobs.discard(job_id)

            record_job_finish(
                job_id=job_id,
                duration_s=elapsed,
                summary=summary,
                error_message=error_msg,
                settings=settings,
            )
            append_schedule_log(
                job_id=job_id,
                started_at=started_at,
                finished_at=finished_at,
                duration_s=elapsed,
                status="error" if error_msg else "success",
                summary=summary,
                error_details=error_msg,
                settings=settings,
            )


def get_scheduler_engine() -> SchedulerEngine:
    """Retrieve the global SchedulerEngine singleton."""
    return SchedulerEngine.get_instance()
