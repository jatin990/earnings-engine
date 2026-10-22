"""In-memory state and pool management for Breakout Radar."""

from __future__ import annotations

from typing import Any
from earnings_engine.data.breakout_scanner.constants import (
    BREAKOUT_MIN_SCORE,
    BREAKOUT_MAX_CANDIDATES,
    BREAKOUT_STRATEGIES,
)

# ---------------------------------------------------------------------------
# Tiered in-memory pool
# ---------------------------------------------------------------------------
_pool: dict[str, Any] = {
    "hot": {},               # ticker → {"result": dict, "consecutive_low": 0}
    "warm": {},              # ticker → {"result": dict, "consecutive_low": 0}
    "candidates": [],        # merged sorted list for API (score ≥ BREAKOUT_MIN_SCORE)
    "strategy_pools": {},    # strategy_name → {"candidates": list, "last_scan_at": str}
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

_BREAKOUT_DB_INITIALIZED: bool = False
_AI_REASONING_CACHE: dict[str, dict[str, Any]] = {}


def _pool_key(ticker: str, strategy: str | None = None) -> str:
    """Generate unique pool key attaching strategy to ticker."""
    strat = (strategy or "CLASSIC_TECHNICAL").upper().strip()
    return f"{ticker}::{strat}"


def _rebuild_candidates() -> None:
    """Merge hot + warm pools into a deduplicated, sorted candidates list with strategy grouping."""
    merged: dict[str, dict] = {}
    strat_pools: dict[str, Any] = {}

    for key, entry in _pool["hot"].items():
        r = entry.get("result", {})
        if r:
            merged[key] = r
    for key, entry in _pool["warm"].items():
        if key not in merged:
            r = entry.get("result", {})
            if r:
                merged[key] = r

    # Sort Hot setups to the top with highest composite score
    candidates = [r for r in merged.values() if r.get("composite_score", 0) >= BREAKOUT_MIN_SCORE]
    candidates.sort(
        key=lambda x: (
            1 if (x.get("tier") or "").upper() == "HOT" else 0,
            x.get("composite_score", 0),
        ),
        reverse=True,
    )
    _pool["candidates"] = candidates

    # Group into per-strategy candidate pools from all qualifying setups
    for strat_id in BREAKOUT_STRATEGIES.keys():
        s_cands = [
            c
            for c in merged.values()
            if (c.get("strategy") or "CLASSIC_TECHNICAL").upper() == strat_id
            and (c.get("composite_score") or 0) >= BREAKOUT_MIN_SCORE
        ]
        s_cands.sort(
            key=lambda x: (
                1 if (x.get("tier") or "").upper() == "HOT" else 0,
                x.get("composite_score", 0),
            ),
            reverse=True,
        )
        strat_pools[strat_id] = {
            "candidates": s_cands[:BREAKOUT_MAX_CANDIDATES],
            "last_scan_at": _pool.get("last_scan_at"),
        }
    _pool["strategy_pools"] = strat_pools
    _pool["hot_count"] = len(_pool["hot"])
    _pool["warm_count"] = len(_pool["warm"])
