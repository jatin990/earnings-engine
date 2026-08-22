"""Daily JSON cache for Kronos + GBM predictions.

Cached predictions are keyed by the calendar date on which they were generated.
When the ``upcoming-results`` command runs again on the same day, the cached
predictions are reused instead of re-training the GBM model and re-running the
Kronos model + Ollama calls.

Cache layout: data/cache/predictions/predictions-YYYY-MM-DD.json
{
  "generated_date": "2026-08-04",
  "kronos": {"TICKER.NS": {full kronos dict}, ...},
  "gbm": {"TICKER.NS": {p_up, direction, confidence, earnings_date,
                         train_events, model}, ...}
}
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from earnings_engine.config import CACHE_DIR
from earnings_engine.logging_utils import get_logger

logger = get_logger("earnings_engine.prediction_cache")

PREDICTIONS_DIR = CACHE_DIR / "predictions"


def cache_path(date_str: str | None = None) -> Path:
    """Path to the daily predictions cache file."""
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")
    return PREDICTIONS_DIR / f"predictions-{date_str}.json"


def _normalize_ticker(ticker: str) -> str:
    """Uppercase + strip .NS/.BO suffix for cache-key comparison."""
    base = ticker.strip().upper()
    for suffix in (".NS", ".BO"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
            break
    return base


def load_prediction_cache(
    tickers: list[str],
    date_str: str | None = None,
) -> dict[str, dict[str, dict[str, Any]]] | None:
    """Load today's cached predictions, keyed by the caller's ticker strings.

    Returns {"kronos": {...}, "gbm": {...}} if the cache exists for today and
    covers ALL requested tickers; otherwise returns None so the caller
    recomputes and calls save_prediction_cache.
    """
    path = cache_path(date_str)
    if not path.exists():
        logger.info("[PRED-CACHE] No cache at %s", path)
        return None

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("[PRED-CACHE] Corrupt cache %s: %s", path, exc)
        return None

    expected_date = path.stem.replace("predictions-", "")
    if data.get("generated_date") != expected_date:
        logger.info("[PRED-CACHE] Cache is from a previous day: %s (expected %s)",
                    data.get("generated_date"), expected_date)
        return None

    def _norm(cache_map: dict) -> dict[str, dict[str, Any]]:
        return {_normalize_ticker(k): v for k, v in (cache_map or {}).items()}

    norm_kronos = _norm(data.get("kronos") or {})
    norm_gbm = _norm(data.get("gbm") or {})

    requested = {_normalize_ticker(t) for t in tickers}
    missing_kronos = requested - set(norm_kronos.keys())
    missing_gbm = requested - set(norm_gbm.keys())
    if missing_kronos or missing_gbm:
        logger.info("[PRED-CACHE] Partial cache: missing kronos=%s gbm=%s -> recomputing",
                    sorted(missing_kronos), sorted(missing_gbm))
        return None

    result_kronos: dict[str, dict[str, Any]] = {}
    result_gbm: dict[str, dict[str, Any]] = {}
    for t in tickers:
        base = _normalize_ticker(t)
        result_kronos[t] = norm_kronos[base]
        result_gbm[t] = norm_gbm[base]

    logger.info("[PRED-CACHE] Cache hit for %d tickers (%s)", len(tickers), path)
    return {"kronos": result_kronos, "gbm": result_gbm}


def load_prediction_cache_partial(
    tickers: list[str],
    date_str: str | None = None,
) -> dict[str, dict[str, dict[str, Any]]]:
    """Load available per-ticker coverage from today's cache (not all-or-nothing).

    Unlike :func:`load_prediction_cache` (which returns ``None`` unless EVERY
    requested ticker is covered), this returns whatever per-ticker entries exist
    for today so callers can reuse partial coverage and compute only the gaps.

    Returns ``{"kronos": {...}, "gbm": {...}}`` keyed by the caller's ticker
    strings (only the entries that are present).  Empty dicts if no cache.
    """
    path = cache_path(date_str)
    if not path.exists():
        return {"kronos": {}, "gbm": {}}

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("[PRED-CACHE] Corrupt cache %s: %s", path, exc)
        return {"kronos": {}, "gbm": {}}

    expected_date = path.stem.replace("predictions-", "")
    if data.get("generated_date") != expected_date:
        logger.info("[PRED-CACHE] Cache is from a previous day: %s (expected %s)",
                    data.get("generated_date"), expected_date)
        return {"kronos": {}, "gbm": {}}

    def _norm(cache_map: dict) -> dict[str, dict[str, Any]]:
        return {_normalize_ticker(k): v for k, v in (cache_map or {}).items()}

    norm_kronos = _norm(data.get("kronos") or {})
    norm_gbm = _norm(data.get("gbm") or {})

    result_kronos: dict[str, dict[str, Any]] = {}
    result_gbm: dict[str, dict[str, Any]] = {}
    for t in tickers:
        base = _normalize_ticker(t)
        if base in norm_kronos:
            result_kronos[t] = norm_kronos[base]
        if base in norm_gbm:
            result_gbm[t] = norm_gbm[base]

    logger.info("[PRED-CACHE] Partial cache hit: kronos=%d/%d gbm=%d/%d tickers (%s)",
                len(result_kronos), len(tickers), len(result_gbm), len(tickers), path)
    return {"kronos": result_kronos, "gbm": result_gbm}


def save_prediction_cache(
    kronos_map: dict[str, dict[str, Any]],
    gbm_map: dict[str, dict[str, Any]],
    date_str: str | None = None,
) -> Path:
    """Persist a daily predictions cache file, merging with any existing one."""
    PREDICTIONS_DIR.mkdir(parents=True, exist_ok=True)
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")
    path = cache_path(date_str)

    existing: dict[str, Any] = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            existing = {}

    existing.setdefault("kronos", {}).update(kronos_map or {})
    existing.setdefault("gbm", {}).update(gbm_map or {})
    existing["generated_date"] = date_str

    path.write_text(
        json.dumps(existing, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    logger.info("[PRED-CACHE] Saved %d kronos + %d gbm predictions to %s",
                len(existing.get("kronos", {})), len(existing.get("gbm", {})), path)
    return path