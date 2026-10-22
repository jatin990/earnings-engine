"""In-memory caching utilities for Institutional Accumulation."""

from __future__ import annotations

import time
from typing import Any

# In-memory fast cache: {cache_key: (expiry_timestamp, payload)}
_INST_CACHE: dict[str, tuple[float, Any]] = {}


def _get_inst_cache(key: str) -> Any | None:
    now = time.time()
    if key in _INST_CACHE:
        exp, val = _INST_CACHE[key]
        if now < exp:
            return val
        del _INST_CACHE[key]
    return None


def _set_inst_cache(key: str, val: Any, ttl_seconds: float = 180.0) -> None:
    _INST_CACHE[key] = (time.time() + ttl_seconds, val)


def clear_institutional_cache() -> None:
    """Flush the institutional in-memory response cache."""
    _INST_CACHE.clear()
