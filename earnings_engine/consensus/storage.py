"""Database storage layer for consensus predictions.

Manages the consensus_predictions table: creation, inserts, queries,
and settlement updates. Follows the same DB patterns as swing_ranges.py.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection, is_turso_enabled

logger = logging.getLogger("earnings_engine.consensus.storage")

_TABLE_CREATED = False


def _ensure_table(conn: Any) -> None:
    """Create the consensus_predictions table if it doesn't exist."""
    global _TABLE_CREATED
    if _TABLE_CREATED:
        return

    conn.execute("""
        CREATE TABLE IF NOT EXISTS consensus_predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            created_at TEXT NOT NULL,
            evaluation_date TEXT NOT NULL,
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
    conn.execute("CREATE INDEX IF NOT EXISTS idx_consensus_ticker ON consensus_predictions(ticker)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_consensus_status ON consensus_predictions(settlement_status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_consensus_eval_date ON consensus_predictions(evaluation_date)")
    conn.commit()
    _TABLE_CREATED = True


def _connect(settings: Settings) -> Any:
    """Get a DB connection and ensure the table exists."""
    conn = get_db_connection(settings)
    if not is_turso_enabled():
        try:
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA busy_timeout = 10000;")
        except Exception:
            pass
    _ensure_table(conn)
    return conn


def save_prediction(consensus: dict[str, Any], evaluation_date: str, settings: Settings | None = None) -> int:
    """Insert a consensus prediction into the database.

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

    cursor = conn.execute(
        """
        INSERT INTO consensus_predictions (
            ticker, created_at, evaluation_date, as_of_price,
            consensus_direction, consensus_strength, consensus_return_pct,
            consensus_target_price, consensus_support, consensus_resistance,
            model_count, agreement_ratio, models_breakdown_json, synthesized_thesis,
            settlement_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING')
        """,
        (
            consensus["ticker"],
            now,
            evaluation_date,
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
        ),
    )
    conn.commit()

    # Retrieve the inserted ID
    row = conn.execute("SELECT last_insert_rowid()").fetchone()
    row_id = row[0] if row else 0
    conn.close()

    logger.info("[CONSENSUS-DB] Saved prediction for %s (id=%d, direction=%s, strength=%.0f%%)",
                consensus["ticker"], row_id, consensus["consensus_direction"], consensus["consensus_strength"])
    return row_id


def get_predictions(
    settings: Settings | None = None,
    ticker: str | None = None,
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
            "SELECT * FROM consensus_predictions WHERE settlement_status = 'PENDING' ORDER BY evaluation_date",
        ).fetchall()

    conn.close()
    return [_row_to_dict(r) for r in rows]


def update_settlement(
    prediction_id: int,
    settlement_data: dict[str, Any],
    settings: Settings | None = None,
) -> None:
    """Update a prediction with settlement outcome."""
    settings = settings or Settings()
    conn = _connect(settings)

    conn.execute(
        """
        UPDATE consensus_predictions SET
            settlement_status = ?,
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
            settlement_data["settlement_status"],
            settlement_data.get("settled_at", datetime.now().isoformat()),
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
    conn.close()

    logger.info("[CONSENSUS-DB] Updated settlement for id=%d -> %s", prediction_id, settlement_data["settlement_status"])


def get_accuracy_stats(settings: Settings | None = None) -> dict[str, Any]:
    """Compute aggregate accuracy statistics across all settled predictions."""
    settings = settings or Settings()
    conn = _connect(settings)

    total = conn.execute("SELECT COUNT(*) FROM consensus_predictions").fetchone()[0]
    pending = conn.execute("SELECT COUNT(*) FROM consensus_predictions WHERE settlement_status = 'PENDING'").fetchone()[0]
    settled = conn.execute("SELECT COUNT(*) FROM consensus_predictions WHERE settlement_status != 'PENDING'").fetchone()[0]
    success = conn.execute("SELECT COUNT(*) FROM consensus_predictions WHERE settlement_status = 'SUCCESS'").fetchone()[0]
    partial = conn.execute("SELECT COUNT(*) FROM consensus_predictions WHERE settlement_status = 'PARTIAL'").fetchone()[0]
    failure = conn.execute("SELECT COUNT(*) FROM consensus_predictions WHERE settlement_status = 'FAILURE'").fetchone()[0]

    # Win rate
    win_rate = (success / settled * 100) if settled > 0 else 0.0

    # Direction accuracy
    direction_correct = conn.execute(
        "SELECT COUNT(*) FROM consensus_predictions WHERE is_direction_correct = 1"
    ).fetchone()[0]
    direction_accuracy = (direction_correct / settled * 100) if settled > 0 else 0.0

    # Average consensus strength for wins vs losses
    avg_strength_win = conn.execute(
        "SELECT AVG(consensus_strength) FROM consensus_predictions WHERE settlement_status = 'SUCCESS'"
    ).fetchone()[0]
    avg_strength_loss = conn.execute(
        "SELECT AVG(consensus_strength) FROM consensus_predictions WHERE settlement_status = 'FAILURE'"
    ).fetchone()[0]

    # Top failure categories
    failure_cats = conn.execute(
        "SELECT failure_category, COUNT(*) as cnt FROM consensus_predictions "
        "WHERE failure_category IS NOT NULL GROUP BY failure_category ORDER BY cnt DESC LIMIT 5"
    ).fetchall()

    # Per-model accuracy (parse models_breakdown_json)
    # This is computed from settled predictions
    model_stats = _compute_model_stats(conn)

    conn.close()

    return {
        "total_predictions": total,
        "pending": pending,
        "settled": settled,
        "success_count": success,
        "partial_count": partial,
        "failure_count": failure,
        "win_rate": round(win_rate, 1),
        "direction_accuracy": round(direction_accuracy, 1),
        "avg_strength_wins": round(avg_strength_win, 1) if avg_strength_win else None,
        "avg_strength_losses": round(avg_strength_loss, 1) if avg_strength_loss else None,
        "top_failure_categories": [{"category": r[0], "count": r[1]} for r in failure_cats],
        "model_stats": model_stats,
    }


def _compute_model_stats(conn: Any) -> list[dict[str, Any]]:
    """Compute per-model directional accuracy from settled predictions."""
    rows = conn.execute(
        "SELECT models_breakdown_json, consensus_direction, is_direction_correct, settlement_status "
        "FROM consensus_predictions WHERE settlement_status IN ('SUCCESS', 'PARTIAL', 'FAILURE')"
    ).fetchall()

    model_correct: dict[str, int] = {}
    model_total: dict[str, int] = {}

    for r in rows:
        try:
            breakdown = json.loads(r[0])
            actual_correct = r[2]  # is_direction_correct for the overall consensus

            for model_pred in breakdown:
                name = model_pred.get("model_name", "Unknown")
                if "error" in model_pred:
                    continue

                model_dir = model_pred.get("direction", "NEUTRAL").upper()
                # A model is "correct" if its direction matched what actually happened
                # We use the consensus direction correctness as a proxy
                model_total[name] = model_total.get(name, 0) + 1
                if actual_correct:
                    # The consensus was correct — models aligned with consensus are correct
                    consensus_dir = r[1]
                    if model_dir == consensus_dir:
                        model_correct[name] = model_correct.get(name, 0) + 1
                else:
                    # Consensus was wrong — dissenters were correct
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

    # Column names for consensus_predictions table
    columns = [
        "id", "ticker", "created_at", "evaluation_date", "as_of_price",
        "consensus_direction", "consensus_strength", "consensus_return_pct",
        "consensus_target_price", "consensus_support", "consensus_resistance",
        "model_count", "agreement_ratio", "models_breakdown_json", "synthesized_thesis",
        "settlement_status", "settled_at", "actual_exit_price", "actual_return_pct",
        "is_direction_correct", "failure_category", "failure_reason_summary", "failure_post_mortem",
    ]

    # Support both dict-like rows (TursoRow) and tuple rows
    try:
        d = dict(row)
    except (TypeError, ValueError):
        d = {}
        for i, col in enumerate(columns):
            try:
                d[col] = row[i]
            except (IndexError, TypeError):
                d[col] = None

    # Parse the JSON breakdown
    if "models_breakdown_json" in d and isinstance(d["models_breakdown_json"], str):
        try:
            d["models_breakdown"] = json.loads(d["models_breakdown_json"])
        except json.JSONDecodeError:
            d["models_breakdown"] = []

    return d
