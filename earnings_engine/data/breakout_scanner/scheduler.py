"""Background asyncio scheduler loops for multi-tier Breakout Radar scanning."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from earnings_engine.config import Settings
from earnings_engine.data.breakout_scanner.constants import (
    COLD_INTERVAL_MIN,
    WARM_INTERVAL_MIN,
    HOT_INTERVAL_MIN,
    BREAKOUT_MIN_SCORE,
)
from earnings_engine.data.breakout_scanner.state import _pool

logger = logging.getLogger(__name__)


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
    from earnings_engine.data.breakout_scanner.pipeline import (
        run_cold_scan,
        run_warm_rescore,
        run_hot_rescore,
    )

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
# Legacy compat alias
# ---------------------------------------------------------------------------
breakout_scanner_loop = tiered_scanner_loop
