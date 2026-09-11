"""SQLite-backed daily cache for Kronos + GBM predictions.

Cached predictions are stored directly in the primary SQLite database (table `daily_prediction_cache`).
When the ``upcoming-results`` command or dashboard runs again on the same day, cached predictions
are reused instead of re-training the GBM model and re-running the Kronos model + Ollama calls.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection, is_turso_enabled, _cache_path
from earnings_engine.logging_utils import get_logger

logger = get_logger("earnings_engine.prediction_cache")


def _connect(settings: Settings | None = None) -> Any:
    s = settings or Settings()
    return get_db_connection(s)


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
    settings: Settings | None = None,
) -> dict[str, dict[str, dict[str, Any]]] | None:
    """Load today's cached predictions from SQLite.

    Returns {"kronos": {...}, "gbm": {...}} if the cache exists for today and
    covers ALL requested tickers; otherwise returns None so the caller
    recomputes and calls save_prediction_cache.
    """
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")

    norm_to_orig = {_normalize_ticker(t): t for t in tickers}
    requested_norm = set(norm_to_orig.keys())

    conn = _connect(settings)
    rows = conn.execute(
        "SELECT model_type, ticker, payload FROM daily_prediction_cache WHERE cache_date = ?",
        (date_str,),
    ).fetchall()
    conn.close()

    kronos_dict: dict[str, Any] = {}
    gbm_dict: dict[str, Any] = {}

    for model_type, ticker, payload_str in rows:
        norm_t = _normalize_ticker(ticker)
        if norm_t in requested_norm:
            try:
                val = json.loads(payload_str)
                if model_type == "kronos":
                    kronos_dict[norm_t] = val
                elif model_type == "gbm":
                    gbm_dict[norm_t] = val
            except Exception:
                pass

    if requested_norm - set(kronos_dict.keys()) or requested_norm - set(gbm_dict.keys()):
        logger.info(
            "[PRED-CACHE] Partial cache in SQLite for %s: missing %d/%d -> recomputing",
            date_str,
            len(requested_norm - set(kronos_dict.keys())),
            len(tickers),
        )
        return None

    result_kronos = {t: kronos_dict[_normalize_ticker(t)] for t in tickers}
    result_gbm = {t: gbm_dict[_normalize_ticker(t)] for t in tickers}
    logger.info("[PRED-CACHE] Cache hit in SQLite for %d tickers (%s)", len(tickers), date_str)
    return {"kronos": result_kronos, "gbm": result_gbm}


def load_prediction_cache_partial(
    tickers: list[str],
    date_str: str | None = None,
    settings: Settings | None = None,
) -> dict[str, dict[str, dict[str, Any]]]:
    """Load available per-ticker coverage from SQLite (not all-or-nothing)."""
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")

    norm_to_orig = {_normalize_ticker(t): t for t in tickers}
    requested_norm = set(norm_to_orig.keys())

    conn = _connect(settings)
    rows = conn.execute(
        "SELECT model_type, ticker, payload FROM daily_prediction_cache WHERE cache_date = ?",
        (date_str,),
    ).fetchall()
    conn.close()

    result_kronos: dict[str, Any] = {}
    result_gbm: dict[str, Any] = {}

    for model_type, ticker, payload_str in rows:
        norm_t = _normalize_ticker(ticker)
        if norm_t in requested_norm:
            orig_t = norm_to_orig[norm_t]
            try:
                val = json.loads(payload_str)
                if model_type == "kronos":
                    result_kronos[orig_t] = val
                elif model_type == "gbm":
                    result_gbm[orig_t] = val
            except Exception:
                pass

    logger.info(
        "[PRED-CACHE] Partial SQLite hit: kronos=%d/%d gbm=%d/%d tickers (%s)",
        len(result_kronos),
        len(tickers),
        len(result_gbm),
        len(tickers),
        date_str,
    )
    return {"kronos": result_kronos, "gbm": result_gbm}


def save_prediction_cache(
    kronos_map: dict[str, dict[str, Any]],
    gbm_map: dict[str, dict[str, Any]],
    date_str: str | None = None,
    settings: Settings | None = None,
) -> None:
    """Persist daily predictions cache directly into SQLite using batch execution."""
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    entries: list[tuple[str, str, str, str, str]] = []
    for ticker, payload in (kronos_map or {}).items():
        payload_json = json.dumps(payload, default=str)
        entries.append((date_str, "kronos", ticker, payload_json, now_str))

    for ticker, payload in (gbm_map or {}).items():
        payload_json = json.dumps(payload, default=str)
        entries.append((date_str, "gbm", ticker, payload_json, now_str))

    if entries:
        conn = _connect(settings)
        with conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO daily_prediction_cache
                (cache_date, model_type, ticker, payload, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                entries,
            )
        conn.close()

    logger.info(
        "[PRED-CACHE] Saved %d kronos + %d gbm predictions to SQLite (%s)",
        len(kronos_map or {}),
        len(gbm_map or {}),
        date_str,
    )