"""Database storage layer for consensus predictions.

Manages the consensus_predictions table: creation, inserts, queries,
and settlement updates. Follows the same DB patterns as swing_ranges.py.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime
from typing import Any

from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection, is_turso_enabled

logger = logging.getLogger("earnings_engine.consensus.storage")

def _ensure_table(conn: Any) -> None:
    """Create the consensus_predictions table if it doesn't exist, and migrate columns."""

    conn.execute("""
        CREATE TABLE IF NOT EXISTS consensus_predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            created_at TEXT NOT NULL,
            evaluation_date TEXT NOT NULL,
            timeframe_days INTEGER DEFAULT 14,
            as_of_price REAL NOT NULL,
            consensus_direction TEXT NOT NULL,
            consensus_strength REAL NOT NULL,
            consensus_return_pct REAL NOT NULL,
            consensus_target_price REAL NOT NULL,
            consensus_support REAL,
            consensus_resistance REAL,
            model_count INTEGER NOT NULL,
            agreement_ratio REAL NOT NULL,
            models_breakdown_json TEXT NOT NULL,
            synthesized_thesis TEXT,
            system_prompt TEXT,
            raw_context_prompt TEXT,
            custom_directives TEXT,
            settlement_status TEXT DEFAULT 'PENDING',
            settled_at TEXT,
            actual_exit_price REAL,
            actual_return_pct REAL,
            is_direction_correct INTEGER,
            failure_category TEXT,
            failure_reason_summary TEXT,
            failure_post_mortem TEXT
        )
    """)
    # Migrations for existing database instances (idempotent pre-flight check)
    existing_cols = set()
    try:
        rows = conn.execute("PRAGMA table_info(consensus_predictions)").fetchall()
        for r in rows:
            if hasattr(r, "get"):
                c = r.get("name")
            elif isinstance(r, (tuple, list)) and len(r) > 1:
                c = r[1]
            elif hasattr(r, "keys") and "name" in r.keys():
                c = r["name"]
            else:
                c = None
            if c:
                existing_cols.add(c)
    except Exception:
        pass

    for col_name, col_def in (
        ("timeframe_days", "timeframe_days INTEGER DEFAULT 14"),
        ("system_prompt", "system_prompt TEXT"),
        ("raw_context_prompt", "raw_context_prompt TEXT"),
        ("custom_directives", "custom_directives TEXT"),
    ):
        if not existing_cols or col_name not in existing_cols:
            try:
                conn.execute(f"ALTER TABLE consensus_predictions ADD COLUMN {col_def}")
                conn.commit()
            except Exception:
                pass

    conn.execute("CREATE INDEX IF NOT EXISTS idx_consensus_ticker ON consensus_predictions(ticker)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_consensus_ticker_timeframe ON consensus_predictions(ticker, timeframe_days)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_consensus_status ON consensus_predictions(settlement_status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_consensus_eval_date ON consensus_predictions(evaluation_date)")
    conn.commit()


def _connect(settings: Settings) -> Any:
    """Get a DB connection and ensure the table exists."""
    conn = get_db_connection(settings)
    if not is_turso_enabled():
        try:
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA busy_timeout = 10000;")
        except Exception:
            pass
        if hasattr(conn, "row_factory"):
            conn.row_factory = sqlite3.Row
    _ensure_table(conn)
    return conn


def save_prediction(consensus: dict[str, Any], evaluation_date: str, settings: Settings | None = None) -> int:
    """Insert a consensus prediction into the database with full raw trace payload.

    Args:
        consensus: The consensus result dict from aggregator.aggregate_predictions().
        evaluation_date: ISO date string (YYYY-MM-DD) for when to evaluate.
        settings: Optional Settings instance.

    Returns:
        The inserted row ID.
    """
    settings = settings or Settings()
    conn = _connect(settings)

    models_json = json.dumps(consensus.get("models_breakdown", []), default=str)
    now = datetime.now().isoformat()
    timeframe_days = int(consensus.get("timeframe_days") or 14)

    cursor = conn.execute(
        """
        INSERT INTO consensus_predictions (
            ticker, created_at, evaluation_date, timeframe_days, as_of_price,
            consensus_direction, consensus_strength, consensus_return_pct,
            consensus_target_price, consensus_support, consensus_resistance,
            model_count, agreement_ratio, models_breakdown_json, synthesized_thesis,
            system_prompt, raw_context_prompt, custom_directives,
            settlement_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING')
        """,
        (
            consensus["ticker"],
            now,
            evaluation_date,
            timeframe_days,
            consensus["as_of_price"],
            consensus["consensus_direction"],
            consensus["consensus_strength"],
            consensus["consensus_return_pct"],
            consensus["consensus_target_price"],
            consensus.get("consensus_support"),
            consensus.get("consensus_resistance"),
            consensus["model_count"],
            consensus["agreement_ratio"],
            models_json,
            consensus.get("synthesized_thesis"),
            consensus.get("system_prompt"),
            consensus.get("raw_context_prompt"),
            consensus.get("custom_directives"),
        ),
    )
    conn.commit()

    # Retrieve the inserted ID
    row = conn.execute("SELECT last_insert_rowid()").fetchone()
    row_id = row[0] if row else 0
    conn.close()

    logger.info("[CONSENSUS-DB] Saved prediction for %s (id=%d, timeframe=%dd, direction=%s, strength=%.0f%%)",
                consensus["ticker"], row_id, timeframe_days, consensus["consensus_direction"], consensus["consensus_strength"])
    return row_id


def get_predictions(
    settings: Settings | None = None,
    ticker: str | None = None,
    timeframe_days: int | None = None,
    status: str | None = None,
    direction: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Query consensus predictions with optional filters."""
    settings = settings or Settings()
    conn = _connect(settings)

    query = "SELECT * FROM consensus_predictions WHERE 1=1"
    params: list[Any] = []

    if ticker:
        query += " AND ticker = ?"
        params.append(ticker)
    if timeframe_days is not None:
        query += " AND timeframe_days = ?"
        params.append(int(timeframe_days))
    if status:
        query += " AND settlement_status = ?"
        params.append(status.upper())
    if direction:
        query += " AND consensus_direction = ?"
        params.append(direction.upper())

    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(query, params).fetchall()
    conn.close()

    return [_row_to_dict(r) for r in rows]


def get_prediction_by_id(prediction_id: int, settings: Settings | None = None) -> dict[str, Any] | None:
    """Get a single prediction by ID."""
    settings = settings or Settings()
    conn = _connect(settings)

    row = conn.execute("SELECT * FROM consensus_predictions WHERE id = ?", (prediction_id,)).fetchone()
    conn.close()

    return _row_to_dict(row) if row else None


def get_pending_predictions(settings: Settings | None = None, before_date: str | None = None) -> list[dict[str, Any]]:
    """Get all PENDING predictions that are due for settlement."""
    settings = settings or Settings()
    conn = _connect(settings)

    if before_date:
        rows = conn.execute(
            "SELECT * FROM consensus_predictions WHERE settlement_status = 'PENDING' AND evaluation_date <= ? ORDER BY evaluation_date",
            (before_date,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM consensus_predictions WHERE settlement_status = 'PENDING' ORDER BY evaluation_date"
        ).fetchall()

    conn.close()
    return [_row_to_dict(r) for r in rows]


def update_settlement(
    prediction_id: int,
    settlement_data: dict[str, Any],
    settings: Settings | None = None,
) -> bool:
    """Update a prediction row with settlement results."""
    settings = settings or Settings()
    conn = _connect(settings)

    cursor = conn.execute(
        """
        UPDATE consensus_predictions
        SET settlement_status = ?,
            settled_at = ?,
            actual_exit_price = ?,
            actual_return_pct = ?,
            is_direction_correct = ?,
            failure_category = ?,
            failure_reason_summary = ?,
            failure_post_mortem = ?
        WHERE id = ?
        """,
        (
            settlement_data.get("settlement_status", "SUCCESS"),
            settlement_data.get("settled_at"),
            settlement_data.get("actual_exit_price"),
            settlement_data.get("actual_return_pct"),
            settlement_data.get("is_direction_correct"),
            settlement_data.get("failure_category"),
            settlement_data.get("failure_reason_summary"),
            settlement_data.get("failure_post_mortem"),
            prediction_id,
        ),
    )
    conn.commit()
    updated = cursor.rowcount > 0
    conn.close()

    logger.info("[CONSENSUS-DB] Updated settlement for prediction #%d (status=%s, correct=%s)",
                prediction_id, settlement_data.get("settlement_status"), settlement_data.get("is_direction_correct"))
    return updated


def get_accuracy_stats(settings: Settings | None = None) -> dict[str, Any]:
    """Calculate historical accuracy statistics from settled predictions."""
    settings = settings or Settings()
    conn = _connect(settings)

    total_settled = conn.execute(
        "SELECT COUNT(*) FROM consensus_predictions WHERE settlement_status != 'PENDING'"
    ).fetchone()[0]

    correct_count = conn.execute(
        "SELECT COUNT(*) FROM consensus_predictions WHERE is_direction_correct = 1"
    ).fetchone()[0]

    by_category_rows = conn.execute(
        """
        SELECT failure_category, COUNT(*) FROM consensus_predictions
        WHERE failure_category IS NOT NULL AND failure_category != ''
        GROUP BY failure_category ORDER BY COUNT(*) DESC
        """
    ).fetchall()

    conn.close()

    accuracy_pct = (correct_count / total_settled * 100) if total_settled > 0 else 0.0

    return {
        "total_settled": total_settled,
        "total_predictions": total_settled,
        "correct_predictions": correct_count,
        "success_count": correct_count,
        "overall_accuracy_pct": round(accuracy_pct, 1),
        "win_rate": round(accuracy_pct / 100.0, 3) if total_settled > 0 else 0.0,
        "failure_breakdown": {row[0]: row[1] for row in by_category_rows},
        "model_stats": get_model_leaderboard(settings),
    }


def get_model_leaderboard(settings: Settings | None = None) -> list[dict[str, Any]]:
    """Compute accuracy per individual model from models_breakdown_json of settled predictions."""
    settings = settings or Settings()
    conn = _connect(settings)

    rows = conn.execute(
        """
        SELECT models_breakdown_json, consensus_direction, is_direction_correct
        FROM consensus_predictions
        WHERE settlement_status != 'PENDING' AND is_direction_correct IS NOT NULL
        """
    ).fetchall()
    conn.close()

    model_total: dict[str, int] = {}
    model_correct: dict[str, int] = {}

    for r in rows:
        try:
            breakdown = json.loads(r[0]) if r[0] else []
            actual_correct = bool(r[2])

            for model_pred in breakdown:
                name = model_pred.get("model_name", "Unknown")
                if "error" in model_pred:
                    continue

                model_dir = model_pred.get("direction", "NEUTRAL").upper()
                model_total[name] = model_total.get(name, 0) + 1
                if actual_correct:
                    consensus_dir = r[1]
                    if model_dir == consensus_dir:
                        model_correct[name] = model_correct.get(name, 0) + 1
                else:
                    consensus_dir = r[1]
                    if model_dir != consensus_dir:
                        model_correct[name] = model_correct.get(name, 0) + 1
        except (json.JSONDecodeError, TypeError):
            continue

    stats = []
    for name in sorted(model_total.keys()):
        total = model_total[name]
        correct = model_correct.get(name, 0)
        stats.append({
            "model_name": name,
            "predictions": total,
            "correct": correct,
            "accuracy": round(correct / total * 100, 1) if total > 0 else 0.0,
        })

    return stats


def _row_to_dict(row: Any) -> dict[str, Any]:
    """Convert a database row to a dict."""
    if row is None:
        return {}

    # Check if row is already dict-like or sqlite3.Row with keys()
    if hasattr(row, "keys"):
        d = {k: row[k] for k in row.keys()}
    else:
        try:
            d = dict(row)
        except (TypeError, ValueError):
            columns = [
                "id", "ticker", "created_at", "evaluation_date", "timeframe_days", "as_of_price",
                "consensus_direction", "consensus_strength", "consensus_return_pct",
                "consensus_target_price", "consensus_support", "consensus_resistance",
                "model_count", "agreement_ratio", "models_breakdown_json", "synthesized_thesis",
                "settlement_status", "settled_at", "actual_exit_price", "actual_return_pct",
                "is_direction_correct", "failure_category", "failure_reason_summary", "failure_post_mortem",
                "system_prompt", "raw_context_prompt", "custom_directives",
            ]
            d = {}
            for i, col in enumerate(columns):
                try:
                    d[col] = row[i]
                except (IndexError, TypeError):
                    d[col] = None

    if d.get("timeframe_days") is None:
        d["timeframe_days"] = 14

    # Parse the JSON breakdown
    if "models_breakdown_json" in d and isinstance(d["models_breakdown_json"], str):
        try:
            d["models_breakdown"] = json.loads(d["models_breakdown_json"])
        except json.JSONDecodeError:
            d["models_breakdown"] = []

    return d


def get_prediction_trace(prediction_id: int, settings: Settings | None = None) -> dict[str, Any] | None:
    """Retrieve full inspection trace of a consensus prediction including all raw model inputs & outputs."""
    pred = get_prediction_by_id(prediction_id, settings=settings)
    if not pred:
        return None

    models = pred.get("models_breakdown", [])
    model_traces = []
    for m in models:
        model_traces.append({
            "model_name": m.get("model_name"),
            "model_id": m.get("model_id"),
            "sub_model": m.get("sub_model"),
            "direction": m.get("direction"),
            "confidence_pct": m.get("confidence_pct"),
            "target_price": m.get("target_price"),
            "target_return_pct": m.get("target_return_pct"),
            "support_level": m.get("support_level"),
            "resistance_level": m.get("resistance_level"),
            "stop_loss_price": m.get("stop_loss_price"),
            "risk_reward_ratio": m.get("risk_reward_ratio"),
            "recommended_action": m.get("recommended_action"),
            "chart_pattern": m.get("chart_pattern"),
            "volume_profile_insight": m.get("volume_profile_insight"),
            "key_drivers": m.get("key_drivers", []),
            "primary_risk": m.get("primary_risk"),
            "latency_ms": m.get("latency_ms"),
            "tokens_used": m.get("tokens_used"),
            "system_prompt": m.get("system_prompt") or pred.get("system_prompt"),
            "raw_prompt": m.get("raw_prompt") or pred.get("raw_context_prompt"),
            "raw_response": m.get("raw_response"),
            "reasoning_content": m.get("reasoning_content"),
            "parsed_json": m.get("parsed_json"),
            "telemetry": m.get("telemetry"),
            "error": m.get("error"),
            "is_local": m.get("is_local", False),
            "gateway": m.get("gateway"),
        })

    return {
        "id": pred["id"],
        "ticker": pred["ticker"],
        "created_at": pred["created_at"],
        "evaluation_date": pred["evaluation_date"],
        "timeframe_days": pred["timeframe_days"],
        "as_of_price": pred["as_of_price"],
        "consensus_direction": pred["consensus_direction"],
        "consensus_strength": pred["consensus_strength"],
        "consensus_return_pct": pred["consensus_return_pct"],
        "consensus_target_price": pred["consensus_target_price"],
        "consensus_support": pred.get("consensus_support"),
        "consensus_resistance": pred.get("consensus_resistance"),
        "agreement_ratio": pred["agreement_ratio"],
        "model_count": pred["model_count"],
        "synthesized_thesis": pred.get("synthesized_thesis"),
        "system_prompt": pred.get("system_prompt"),
        "raw_context_prompt": pred.get("raw_context_prompt"),
        "custom_directives": pred.get("custom_directives"),
        "settlement_status": pred.get("settlement_status"),
        "models": model_traces,
    }
