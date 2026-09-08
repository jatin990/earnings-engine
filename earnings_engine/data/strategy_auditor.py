"""Strategy Auditor — SQLite-backed prediction tracking & performance metrics.

Records daily news-derived stock predictions (one row per ticker × strategy ×
date), automatically audits outcomes against actual price data once the target
evaluation window has passed, and computes per-strategy performance metrics
(Win Rate, Profit Factor, Sharpe Ratio, Brier Score, etc.).

Storage
-------
Two tables in the shared ``prices.sqlite3`` database:

* ``strategy_predictions`` — immutable log of every prediction.
* ``strategy_audit_logs``  — one audit outcome per prediction once evaluated.

Both tables are created lazily on first access via :func:`_connect`.
"""

from __future__ import annotations

import json
import math
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from earnings_engine.config import Settings, market_of
from earnings_engine.data.db import get_db_connection, is_turso_enabled, _cache_path as _prices_cache_path
from earnings_engine.logging_utils import get_logger

logger = get_logger("earnings_engine.data.strategy_auditor")

# ---------------------------------------------------------------------------
# Valid signal types and default holding horizons (calendar days).
# ---------------------------------------------------------------------------
VALID_SIGNALS = ("BULLISH", "BEARISH", "NEUTRAL")

DEFAULT_HOLDING_DAYS: dict[str, int] = {
    "1D": 1,
    "5D": 5,
    "POST_EARNINGS": 2,
    "14D": 14,
}

# ---------------------------------------------------------------------------
# SQLite helpers (mirrors predictions.py patterns).
# ---------------------------------------------------------------------------


def _db_path(settings: Settings) -> Path:
    """Use the same SQLite database as prices / earnings."""
    return _prices_cache_path(settings)


def _connect(settings: Settings) -> Any:
    """Connect & create audit tables if missing."""
    settings.ensure_dirs()
    conn = get_db_connection(settings)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS strategy_predictions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker          TEXT    NOT NULL,
            strategy_name   TEXT    NOT NULL,
            signal          TEXT    NOT NULL,
            confidence_pct  REAL,
            entry_price     REAL,
            expected_return_pct REAL,
            holding_horizon TEXT    NOT NULL DEFAULT '1D',
            target_date     TEXT,
            news_source     TEXT,
            news_headline   TEXT,
            notes           TEXT,
            market          TEXT,
            created_at      TEXT    NOT NULL
        )
    """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_strat_pred_ticker_strat
        ON strategy_predictions (ticker, strategy_name, created_at DESC)
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS strategy_audit_logs (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            prediction_id   INTEGER NOT NULL UNIQUE,
            actual_exit_price   REAL,
            actual_return_pct   REAL,
            outcome_status      TEXT NOT NULL,
            direction_correct   INTEGER,
            error_pct           REAL,
            audited_at          TEXT NOT NULL,
            FOREIGN KEY (prediction_id) REFERENCES strategy_predictions(id)
        )
    """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_strat_audit_pred
        ON strategy_audit_logs (prediction_id)
    """)

    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# Write helpers
# ---------------------------------------------------------------------------

def log_prediction(
    ticker: str,
    strategy_name: str,
    signal: str,
    settings: Settings | None = None,
    *,
    confidence_pct: float | None = None,
    entry_price: float | None = None,
    expected_return_pct: float | None = None,
    holding_horizon: str = "1D",
    target_date: str | None = None,
    news_source: str | None = None,
    news_headline: str | None = None,
    notes: str | None = None,
) -> int:
    """Persist a daily prediction for a ticker + strategy.

    Returns the inserted row id.
    """
    if settings is None:
        settings = Settings()

    signal_upper = signal.strip().upper()
    if signal_upper not in VALID_SIGNALS:
        raise ValueError(f"Invalid signal '{signal}'. Must be one of {VALID_SIGNALS}")

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    mkt = market_of(ticker)

    # Auto-resolve entry_price from cache if not provided
    if entry_price is None:
        try:
            from earnings_engine.data.prices import load_prices
            pdf = load_prices(ticker, settings)
            if not pdf.empty and "close" in pdf.columns:
                closes = pd.to_numeric(pdf["close"], errors="coerce").dropna()
                if not closes.empty:
                    entry_price = float(closes.iloc[-1])
        except Exception:
            pass

    # Auto-resolve target_date from holding_horizon
    if target_date is None and holding_horizon in DEFAULT_HOLDING_DAYS:
        target_date = (datetime.now() + timedelta(days=DEFAULT_HOLDING_DAYS[holding_horizon])).strftime("%Y-%m-%d")

    with _connect(settings) as conn:
        cursor = conn.execute(
            """
            INSERT INTO strategy_predictions
                (ticker, strategy_name, signal, confidence_pct, entry_price,
                 expected_return_pct, holding_horizon, target_date, news_source,
                 news_headline, notes, market, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ticker.upper(),
                strategy_name.strip(),
                signal_upper,
                confidence_pct,
                entry_price,
                expected_return_pct,
                holding_horizon,
                target_date,
                news_source,
                news_headline,
                notes,
                mkt,
                now_str,
            ),
        )
        conn.commit()

    row_id = cursor.lastrowid
    logger.info(
        "logged strategy prediction id=%s ticker=%s strategy=%s signal=%s",
        row_id, ticker, strategy_name, signal_upper,
    )
    return row_id


def log_predictions_bulk(
    predictions: list[dict[str, Any]],
    settings: Settings | None = None,
) -> list[int]:
    """Log multiple predictions at once. Each dict should contain at minimum
    ``ticker``, ``strategy_name``, and ``signal`` keys.

    Returns list of inserted row ids.
    """
    ids = []
    for pred in predictions:
        rid = log_prediction(
            ticker=pred["ticker"],
            strategy_name=pred["strategy_name"],
            signal=pred["signal"],
            settings=settings,
            confidence_pct=pred.get("confidence_pct"),
            entry_price=pred.get("entry_price"),
            expected_return_pct=pred.get("expected_return_pct"),
            holding_horizon=pred.get("holding_horizon", "1D"),
            target_date=pred.get("target_date"),
            news_source=pred.get("news_source"),
            news_headline=pred.get("news_headline"),
            notes=pred.get("notes"),
        )
        ids.append(rid)
    return ids


# ---------------------------------------------------------------------------
# Read helpers
# ---------------------------------------------------------------------------

def load_predictions(
    strategy_name: str | None = None,
    ticker: str | None = None,
    limit: int | None = None,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """Return predictions, optionally filtered by strategy and/or ticker."""
    if settings is None:
        settings = Settings()

    parts = ["SELECT * FROM strategy_predictions"]
    params: list[Any] = []
    wheres: list[str] = []
    if strategy_name:
        wheres.append("strategy_name = ?")
        params.append(strategy_name)
    if ticker:
        wheres.append("ticker = ?")
        params.append(ticker.upper())
    if wheres:
        parts.append("WHERE " + " AND ".join(wheres))
    parts.append("ORDER BY created_at DESC, id DESC")
    if limit:
        parts.append(f"LIMIT {int(limit)}")

    with _connect(settings) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(" ".join(parts), params).fetchall()

    return [dict(r) for r in rows]


def load_prediction_with_audit(
    prediction_id: int,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    """Load a single prediction with its audit log (if exists)."""
    if settings is None:
        settings = Settings()

    with _connect(settings) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT p.*, a.actual_exit_price, a.actual_return_pct,
                   a.outcome_status AS audit_status, a.direction_correct,
                   a.error_pct, a.audited_at
            FROM strategy_predictions p
            LEFT JOIN strategy_audit_logs a ON a.prediction_id = p.id
            WHERE p.id = ?
            """,
            (prediction_id,),
        ).fetchone()

    return dict(row) if row else None


def load_audit_history(
    strategy_name: str | None = None,
    ticker: str | None = None,
    status: str | None = None,
    limit: int = 200,
    offset: int = 0,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Return paginated prediction + audit history."""
    if settings is None:
        settings = Settings()

    parts = [
        """
        SELECT p.*, a.actual_exit_price, a.actual_return_pct,
               a.outcome_status AS audit_status, a.direction_correct,
               a.error_pct, a.audited_at
        FROM strategy_predictions p
        LEFT JOIN strategy_audit_logs a ON a.prediction_id = p.id
        """
    ]
    count_parts = ["SELECT COUNT(*) FROM strategy_predictions p LEFT JOIN strategy_audit_logs a ON a.prediction_id = p.id"]
    params: list[Any] = []
    wheres: list[str] = []

    if strategy_name:
        if "%" in strategy_name:
            wheres.append("p.strategy_name LIKE ?")
        else:
            wheres.append("p.strategy_name = ?")
        params.append(strategy_name)
    if ticker:
        wheres.append("p.ticker = ?")
        params.append(ticker.upper())
    if status:
        wheres.append("a.outcome_status = ?")
        params.append(status.upper())

    if wheres:
        where_clause = " WHERE " + " AND ".join(wheres)
        parts.append(where_clause)
        count_parts.append(where_clause)

    parts.append("ORDER BY p.created_at DESC, p.id DESC")
    parts.append(f"LIMIT {int(limit)} OFFSET {int(offset)}")

    with _connect(settings) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(" ".join(parts), params).fetchall()
        total = conn.execute(" ".join(count_parts), params).fetchone()[0]

    items = [dict(r) for r in rows]
    return {
        "items": items,
        "predictions": items,
        "total": total,
        "total_count": total,
        "limit": limit,
        "offset": offset,
    }


# ---------------------------------------------------------------------------
# Audit engine — evaluate past predictions against actual prices
# ---------------------------------------------------------------------------

def _evaluate_single(
    pred: dict[str, Any],
    actual_price: float | None,
) -> dict[str, Any]:
    """Evaluate a single prediction against the actual exit price.

    Returns audit log fields ready for INSERT.
    """
    entry_price = pred.get("entry_price")
    signal = (pred.get("signal") or "").upper()

    if entry_price is None or actual_price is None or entry_price <= 0:
        return {
            "outcome_status": "PENDING",
            "actual_exit_price": actual_price,
            "actual_return_pct": None,
            "direction_correct": None,
            "error_pct": None,
        }

    actual_return_pct = ((actual_price - entry_price) / entry_price) * 100.0
    expected_return = pred.get("expected_return_pct") or 0.0
    error_pct = abs(actual_return_pct - expected_return) if expected_return else abs(actual_return_pct)

    # Direction correctness
    if signal == "BULLISH":
        direction_correct = 1 if actual_return_pct > 0 else 0
    elif signal == "BEARISH":
        direction_correct = 1 if actual_return_pct < 0 else 0
    else:
        # NEUTRAL — correct if within ±1%
        direction_correct = 1 if abs(actual_return_pct) <= 1.0 else 0

    outcome = "WORKED" if direction_correct == 1 else "FAILED"

    return {
        "outcome_status": outcome,
        "actual_exit_price": round(actual_price, 2),
        "actual_return_pct": round(actual_return_pct, 2),
        "direction_correct": direction_correct,
        "error_pct": round(error_pct, 2),
    }


def audit_predictions(
    settings: Settings | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Evaluate all unaudited predictions whose target_date has passed.

    Parameters
    ----------
    force:
        If True, re-evaluate already-audited predictions too.

    Returns
    -------
    dict with counts: ``evaluated``, ``skipped``, ``pending``.
    """
    if settings is None:
        settings = Settings()

    today = datetime.now().strftime("%Y-%m-%d")

    with _connect(settings) as conn:
        conn.row_factory = sqlite3.Row

        if force:
            # Get all predictions with a target_date <= today
            rows = conn.execute(
                "SELECT * FROM strategy_predictions WHERE target_date IS NOT NULL AND target_date <= ?",
                (today,),
            ).fetchall()
        else:
            # Only unaudited predictions
            rows = conn.execute(
                """
                SELECT p.* FROM strategy_predictions p
                LEFT JOIN strategy_audit_logs a ON a.prediction_id = p.id
                WHERE a.id IS NULL
                  AND p.target_date IS NOT NULL
                  AND p.target_date <= ?
                """,
                (today,),
            ).fetchall()

    preds = [dict(r) for r in rows]
    evaluated = 0
    skipped = 0
    pending = 0

    # Ensure prices for all prediction tickers are fetched in batch
    pred_tickers = list({p["ticker"] for p in preds if p.get("ticker")})
    if pred_tickers:
        try:
            from earnings_engine.data.prices import ensure_prices_batch
            ensure_prices_batch(pred_tickers, settings)
        except Exception as e:
            logger.debug("[STRATEGY-AUDIT] Batch price fetch warning: %s", e)

    for pred in preds:
        ticker = pred["ticker"]
        target_date = pred["target_date"]

        # Fetch actual price on or near target_date
        actual_price = _get_price_on_date(ticker, target_date, settings, conn=conn)

        if actual_price is None:
            pending += 1
            continue

        result = _evaluate_single(pred, actual_price)
        if result["outcome_status"] == "PENDING":
            pending += 1
            continue

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if force:
            conn.execute("DELETE FROM strategy_audit_logs WHERE prediction_id = ?", (pred["id"],))
        conn.execute(
            """
            INSERT OR REPLACE INTO strategy_audit_logs
                (prediction_id, actual_exit_price, actual_return_pct,
                 outcome_status, direction_correct, error_pct, audited_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                pred["id"],
                result["actual_exit_price"],
                result["actual_return_pct"],
                result["outcome_status"],
                result["direction_correct"],
                result["error_pct"],
                now_str,
            ),
        )

        evaluated += 1
        if evaluated % 100 == 0:
            conn.commit()

        logger.debug(
            "audited prediction id=%s ticker=%s strategy=%s outcome=%s return=%.2f%%",
            pred["id"], ticker, pred["strategy_name"],
            result["outcome_status"], result["actual_return_pct"] or 0.0,
        )

    conn.commit()
    logger.info("audit complete: evaluated=%d skipped=%d pending=%d", evaluated, skipped, pending)
    return {"evaluated": evaluated, "skipped": skipped, "pending": pending}


def _get_price_on_date(
    ticker: str,
    date_str: str,
    settings: Settings,
    conn: sqlite3.Connection | None = None,
) -> float | None:
    """Get the closing price for a ticker on target_date, nearest window, or latest price."""
    target_dt = str(date_str)[:10]

    # Fast path: query price_history table directly via SQLite
    if conn is not None:
        try:
            max_dt = (pd.Timestamp(target_dt) + timedelta(days=7)).strftime("%Y-%m-%d")
            row = conn.execute(
                "SELECT close FROM price_history WHERE ticker = ? AND date >= ? AND date <= ? ORDER BY date ASC LIMIT 1",
                (ticker.upper(), target_dt, max_dt),
            ).fetchone()
            if row and row[0] is not None:
                return float(row[0])

            # If no price after target_dt, return the latest available price on record
            latest_row = conn.execute(
                "SELECT close FROM price_history WHERE ticker = ? AND close > 0 ORDER BY date DESC LIMIT 1",
                (ticker.upper(),),
            ).fetchone()
            if latest_row and latest_row[0] is not None:
                return float(latest_row[0])
        except Exception:
            pass

    try:
        from earnings_engine.data.prices import load_prices
        pdf = load_prices(ticker, settings)
        if pdf.empty or "close" not in pdf.columns:
            return None

        # Normalize index to date strings
        dates = pdf.index.astype(str).str[:10]
        pdf = pdf.copy()
        pdf["_date_str"] = dates.values

        # Exact match
        exact = pdf[pdf["_date_str"] == target_dt]
        if not exact.empty:
            val = pd.to_numeric(exact["close"], errors="coerce").dropna()
            if not val.empty:
                return float(val.iloc[-1])

        # Nearest match within 4 days after target_date
        target_ts = pd.Timestamp(target_dt)
        for offset in range(1, 5):
            check_date = (target_ts + timedelta(days=offset)).strftime("%Y-%m-%d")
            match = pdf[pdf["_date_str"] == check_date]
            if not match.empty:
                val = pd.to_numeric(match["close"], errors="coerce").dropna()
                if not val.empty:
                    return float(val.iloc[-1])

        # Fallback to latest available close price
        closes = pd.to_numeric(pdf["close"], errors="coerce").dropna()
        if not closes.empty:
            return float(closes.iloc[-1])

        return None
    except Exception:
        return None



# ---------------------------------------------------------------------------
# Metric calculations
# ---------------------------------------------------------------------------

def calculate_strategy_metrics(
    strategy_name: str | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Compute performance metrics for one or all strategies.

    Metrics per strategy:
    - Win Rate % (Direction Accuracy)
    - Profit Factor (sum of wins / abs sum of losses)
    - Average Return %
    - Cumulative Return %
    - Sharpe Ratio (annualized, assuming daily returns)
    - Sortino Ratio (downside deviation only)
    - Brier Score (calibration of confidence predictions)
    - Directional Precision & Recall (Bullish vs Bearish)
    - Breakdown by market
    """
    if settings is None:
        settings = Settings()

    query = """
        SELECT p.*, a.actual_exit_price, a.actual_return_pct,
               a.outcome_status AS audit_status, a.direction_correct,
               a.error_pct
        FROM strategy_predictions p
        INNER JOIN strategy_audit_logs a ON a.prediction_id = p.id
    """
    params: list[Any] = []
    if strategy_name:
        query += " WHERE p.strategy_name = ?"
        params.append(strategy_name)

    with _connect(settings) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query, params).fetchall()

    records = [dict(r) for r in rows]

    if not records:
        return {
            "overall": _empty_metrics(),
            "by_strategy": {},
            "by_market": {},
        }

    # Group by strategy
    by_strategy: dict[str, list[dict]] = {}
    for r in records:
        sn = r["strategy_name"]
        by_strategy.setdefault(sn, []).append(r)

    strategy_metrics = {}
    for sn, group in by_strategy.items():
        strategy_metrics[sn] = _compute_group_metrics(group)

    # Group by market
    by_market: dict[str, list[dict]] = {}
    for r in records:
        mkt = r.get("market") or market_of(r["ticker"])
        by_market.setdefault(mkt, []).append(r)

    market_metrics = {}
    for mkt, group in by_market.items():
        market_metrics[mkt] = _compute_group_metrics(group)

    # Overall
    overall = _compute_group_metrics(records)

    return {
        "overall": overall,
        "by_strategy": strategy_metrics,
        "by_market": market_metrics,
    }


def _empty_metrics() -> dict[str, Any]:
    return {
        "total_predictions": 0,
        "evaluated": 0,
        "wins": 0,
        "losses": 0,
        "win_rate_pct": 0.0,
        "profit_factor": 0.0,
        "avg_return_pct": 0.0,
        "cumulative_return_pct": 0.0,
        "sharpe_ratio": 0.0,
        "sortino_ratio": 0.0,
        "brier_score": None,
        "bullish_precision_pct": 0.0,
        "bearish_precision_pct": 0.0,
        "avg_error_pct": 0.0,
    }


def _compute_group_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute all performance metrics for a group of audited records."""
    if not records:
        return _empty_metrics()

    total = len(records)
    wins = sum(1 for r in records if r.get("audit_status") == "WORKED")
    losses = sum(1 for r in records if r.get("audit_status") == "FAILED")
    evaluated = wins + losses

    # Returns
    returns = [
        r["actual_return_pct"] for r in records
        if r.get("actual_return_pct") is not None
    ]
    win_returns = [ret for ret in returns if ret > 0]
    loss_returns = [ret for ret in returns if ret < 0]

    avg_return = float(pd.Series(returns).mean()) if returns else 0.0

    # Cumulative return (compounded)
    cum_return = 0.0
    if returns:
        product = 1.0
        for r in returns:
            product *= (1.0 + r / 100.0)
        cum_return = (product - 1.0) * 100.0

    # Win rate
    win_rate = (wins / evaluated * 100.0) if evaluated > 0 else 0.0

    # Profit factor
    sum_wins = sum(win_returns) if win_returns else 0.0
    sum_losses = abs(sum(loss_returns)) if loss_returns else 0.0
    profit_factor = (sum_wins / sum_losses) if sum_losses > 0 else (float("inf") if sum_wins > 0 else 0.0)

    # Sharpe ratio (annualized, assuming ~252 trading days)
    sharpe = 0.0
    if len(returns) >= 2:
        s = pd.Series(returns)
        mean_r = s.mean()
        std_r = s.std()
        if std_r > 0:
            sharpe = (mean_r / std_r) * math.sqrt(252)

    # Sortino ratio
    sortino = 0.0
    if len(returns) >= 2:
        s = pd.Series(returns)
        mean_r = s.mean()
        downside = s[s < 0]
        if not downside.empty:
            down_std = downside.std()
            if down_std > 0:
                sortino = (mean_r / down_std) * math.sqrt(252)

    # Brier score (for predictions with confidence_pct)
    brier = _compute_brier_score(records)

    # Directional precision
    bullish_preds = [r for r in records if (r.get("signal") or "").upper() == "BULLISH"]
    bearish_preds = [r for r in records if (r.get("signal") or "").upper() == "BEARISH"]
    bullish_correct = sum(1 for r in bullish_preds if r.get("audit_status") == "WORKED")
    bearish_correct = sum(1 for r in bearish_preds if r.get("audit_status") == "WORKED")
    bullish_precision = (bullish_correct / len(bullish_preds) * 100.0) if bullish_preds else 0.0
    bearish_precision = (bearish_correct / len(bearish_preds) * 100.0) if bearish_preds else 0.0

    # Average error
    errors = [r["error_pct"] for r in records if r.get("error_pct") is not None]
    avg_error = float(pd.Series(errors).mean()) if errors else 0.0

    return {
        "total_predictions": total,
        "evaluated": evaluated,
        "wins": wins,
        "losses": losses,
        "win_rate_pct": round(win_rate, 1),
        "profit_factor": round(profit_factor, 2) if profit_factor != float("inf") else "∞",
        "avg_return_pct": round(avg_return, 2),
        "cumulative_return_pct": round(cum_return, 2),
        "sharpe_ratio": round(sharpe, 2),
        "sortino_ratio": round(sortino, 2),
        "brier_score": brier,
        "bullish_precision_pct": round(bullish_precision, 1),
        "bearish_precision_pct": round(bearish_precision, 1),
        "avg_error_pct": round(avg_error, 2),
    }


def _compute_brier_score(records: list[dict[str, Any]]) -> float | None:
    """Brier Score for calibrated confidence predictions.

    Brier = (1/N) * Σ(forecast_probability - outcome)^2
    where forecast_probability = confidence_pct / 100 and outcome = 1 if correct else 0.

    Lower is better. A perfect predictor scores 0.0, random = 0.25.
    """
    scored = [
        r for r in records
        if r.get("confidence_pct") is not None and r.get("direction_correct") is not None
    ]
    if len(scored) < 3:
        return None

    total = 0.0
    for r in scored:
        prob = (r["confidence_pct"] or 50.0) / 100.0
        outcome = 1.0 if r["direction_correct"] == 1 else 0.0
        total += (prob - outcome) ** 2

    return round(total / len(scored), 4)


# ---------------------------------------------------------------------------
# Strategy listing
# ---------------------------------------------------------------------------

def list_strategies(settings: Settings | None = None) -> list[dict[str, Any]]:
    """Return a summary of all strategies that have predictions logged."""
    if settings is None:
        settings = Settings()

    with _connect(settings) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT strategy_name,
                   COUNT(*) AS total_predictions,
                   MIN(created_at) AS first_prediction,
                   MAX(created_at) AS last_prediction,
                   COUNT(DISTINCT ticker) AS unique_tickers
            FROM strategy_predictions
            GROUP BY strategy_name
            ORDER BY total_predictions DESC
        """).fetchall()

    return [dict(r) for r in rows]


def delete_prediction(
    prediction_id: int,
    settings: Settings | None = None,
) -> bool:
    """Delete a prediction and its audit log."""
    if settings is None:
        settings = Settings()

    with _connect(settings) as conn:
        conn.execute("DELETE FROM strategy_audit_logs WHERE prediction_id = ?", (prediction_id,))
        cursor = conn.execute("DELETE FROM strategy_predictions WHERE id = ?", (prediction_id,))
        conn.commit()
        return cursor.rowcount > 0


# ---------------------------------------------------------------------------
# Historical Ingestion & 1-Year Multi-Strategy Backtesting
# ---------------------------------------------------------------------------

def import_kronos_predictions(
    settings: Settings | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Import historical Kronos forecasts from `kronos_predictions` into
    `strategy_predictions` under strategy 'Kronos_AI', and audit outcomes.

    Parameters
    ----------
    force:
        If True, re-import and re-audit even if already present.

    Returns
    -------
    dict with counts: `imported`, `skipped`, `audited`, `win_rate_pct`.
    """
    if settings is None:
        settings = Settings()

    with _connect(settings) as conn:
        conn.row_factory = sqlite3.Row
        # Check if table exists
        has_kronos = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='kronos_predictions'"
        ).fetchone()

        if not has_kronos:
            logger.warning("kronos_predictions table does not exist in db")
            return {"imported": 0, "skipped": 0, "audited": 0, "message": "No kronos_predictions table found"}

        # Get existing imported (ticker, created_at) to avoid duplicates
        existing = set()
        if not force:
            rows_exist = conn.execute(
                "SELECT ticker, created_at FROM strategy_predictions WHERE strategy_name = 'Kronos_AI'"
            ).fetchall()
            existing = {(r["ticker"], r["created_at"]) for r in rows_exist}

        rows = conn.execute("SELECT * FROM kronos_predictions ORDER BY run_at ASC").fetchall()

    imported = 0
    skipped = 0

    to_insert = []
    for row_item in rows:
        r = dict(row_item)
        ticker = r["ticker"]
        run_at = r["run_at"]
        if (ticker, run_at) in existing:
            skipped += 1
            continue

        trend_str = (r.get("trend") or "Neutral").strip().capitalize()
        ret_pct = float(r["return_pct"]) if r.get("return_pct") is not None else 0.0

        if trend_str.upper() == "BULLISH" or ret_pct > 0.5:
            signal = "BULLISH"
        elif trend_str.upper() == "BEARISH" or ret_pct < -0.5:
            signal = "BEARISH"
        else:
            signal = "NEUTRAL"

        pred_len = int(r["pred_len"]) if r.get("pred_len") else 14
        pred_date = str(r.get("predicted_at") or run_at)[:10]

        try:
            target_date = (pd.Timestamp(pred_date) + timedelta(days=pred_len)).strftime("%Y-%m-%d")
        except Exception:
            target_date = (datetime.now() + timedelta(days=pred_len)).strftime("%Y-%m-%d")

        confidence = round(min(95.0, max(50.0, 55.0 + abs(ret_pct) * 2.5)), 1)
        entry_price = float(r["current_price"]) if r.get("current_price") is not None else None
        mkt = market_of(ticker)
        notes = f"Kronos AI Forecast: support={r.get('support')}, resistance={r.get('resistance')}"

        to_insert.append((
            ticker.upper(),
            "Kronos_AI",
            signal,
            confidence,
            entry_price,
            ret_pct,
            f"{pred_len}D",
            target_date,
            "Kronos_Deep_Predictor",
            f"Kronos AI Forecast: {trend_str} ({ret_pct:+.2f}%)",
            notes,
            mkt,
            run_at,
        ))

    if to_insert:
        with _connect(settings) as conn:
            conn.executemany(
                """
                INSERT INTO strategy_predictions
                    (ticker, strategy_name, signal, confidence_pct, entry_price,
                     expected_return_pct, holding_horizon, target_date, news_source,
                     news_headline, notes, market, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                to_insert,
            )
            conn.commit()
            imported = len(to_insert)

    # Run audit evaluation for all predictions whose target date has passed
    audit_res = audit_predictions(settings=settings, force=force)
    metrics = calculate_strategy_metrics(strategy_name="Kronos_AI", settings=settings)

    logger.info("imported %d Kronos predictions, %d skipped, %d audited", imported, skipped, audit_res["evaluated"])
    return {
        "imported": imported,
        "skipped": skipped,
        "audited": audit_res["evaluated"],
        "pending": audit_res["pending"],
        "metrics": metrics.get("by_strategy", {}).get("Kronos_AI", {}),
    }


def backtest_strategy_history(
    strategy_name: str = "ALL",
    days: int = 365,
    universe: str | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Execute a 1-year historical backtest across selected strategies,
    logging all historical prediction decisions and auditing them against
    actual price data.

    Supported strategies:
    - ``"Kronos_1Y_Backtest"`` / ``"Kronos_AI"``: 14-day multi-factor trend signals
    - ``"News_Momentum_Breakout"``: 5-day volume & 20-day high breakouts
    - ``"Earnings_Drift_GBM"``: Post-earnings announcement drift from event dataset
    - ``"Mean_Reversion_52W"``: 5-day mean reversion at 52-week extremes
    - ``"ALL"``: Runs all of the above

    Parameters
    ----------
    strategy_name:
        Name of the strategy to backtest or "ALL".
    days:
        Lookback window in days (default: 365 = 1 year).
    universe:
        Universe name (e.g. "NSE_TOP", "US_TOP", "IN", "US") or None for combined.
    settings:
        Configuration settings.

    Returns
    -------
    dict with generated counts and overall metrics.
    """
    if settings is None:
        settings = Settings()

    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    today_str = datetime.now().strftime("%Y-%m-%d")

    # Resolve universe tickers
    tickers: list[str] = []
    if universe:
        try:
            from earnings_engine.data.universe import load_universe
            tickers = load_universe(universe, settings)
        except Exception:
            pass

    if not tickers:
        try:
            with _connect(settings) as conn:
                db_tickers = [r[0] for r in conn.execute("SELECT ticker FROM tickers WHERE ticker IS NOT NULL").fetchall() if r[0]]
                if not db_tickers:
                    db_tickers = [r[0] for r in conn.execute("SELECT DISTINCT ticker FROM price_history").fetchall() if r[0]]
                if db_tickers:
                    tickers = db_tickers
        except Exception:
            try:
                with _connect(settings) as conn:
                    db_tickers = [r[0] for r in conn.execute("SELECT DISTINCT ticker FROM price_history").fetchall() if r[0]]
                    if db_tickers:
                        tickers = db_tickers
            except Exception:
                pass

    if not tickers:
        try:
            from earnings_engine.data.universe import _SEED_NSE_TOP, _SEED_US_TOP
            tickers = _SEED_NSE_TOP + _SEED_US_TOP
        except Exception:
            tickers = ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META"]

    strat_upper = strategy_name.strip().upper()
    run_all = strat_upper in ("ALL", "EVERYTHING", "*")

    generated_predictions = []

    # -----------------------------------------------------------------------
    # 1. Earnings_Drift_GBM — from event_dataset
    # -----------------------------------------------------------------------
    if run_all or "EARNINGS" in strat_upper:
        with _connect(settings) as conn:
            conn.row_factory = sqlite3.Row
            has_events = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='event_dataset'"
            ).fetchone()

            if has_events:
                rows = conn.execute(
                    """
                    SELECT * FROM event_dataset
                    WHERE earnings_date >= ? AND earnings_date <= ?
                    ORDER BY earnings_date ASC
                    """,
                    (start_date, today_str),
                ).fetchall()

                for row_item in rows:
                    r = dict(row_item)
                    t = r["ticker"]
                    edate = r["earnings_date"]
                    rdate = r["reaction_date"] or (pd.Timestamp(edate) + timedelta(days=2)).strftime("%Y-%m-%d")
                    past_up = float(r["past_up_rate"]) if r["past_up_rate"] is not None else 0.5
                    ret5 = float(r["ret_5d"]) if r["ret_5d"] is not None else 0.0
                    last_surp = float(r["last_surprise_pct"]) if r["last_surprise_pct"] is not None else 0.0

                    # GBM signal logic based on pre-event drift and surprise history
                    score = (past_up - 0.5) * 2.0 + (1.0 if ret5 > 0 else -1.0) * 0.5 + (1.0 if last_surp > 0 else -0.5) * 0.5
                    if score > 0.3:
                        sig = "BULLISH"
                        exp_ret = 3.5
                    elif score < -0.3:
                        sig = "BEARISH"
                        exp_ret = -3.5
                    else:
                        sig = "NEUTRAL"
                        exp_ret = 0.0

                    conf = round(min(90.0, max(55.0, 50.0 + abs(score) * 20.0)), 1)
                    eprice = _get_price_on_date(t, edate, settings, conn=conn)

                    generated_predictions.append((
                        t.upper(),
                        "Earnings_Drift_GBM",
                        sig,
                        conf,
                        eprice,
                        exp_ret,
                        "POST_EARNINGS",
                        rdate,
                        "Earnings_Event_Dataset",
                        f"Earnings Catalyst & Post-Earnings Drift (past_up={past_up:.1%})",
                        f"Pre-earnings momentum: ret_5d={ret5:.2f}%, last_surprise={last_surp:.1f}%",
                        r.get("market") or market_of(t),
                        f"{edate} 09:30:00",
                    ))

    # -----------------------------------------------------------------------
    # 2. Technical & Multi-Factor Strategies (Kronos, Breakout, Mean Reversion)
    # -----------------------------------------------------------------------
    if run_all or "KRONOS" in strat_upper or "BREAKOUT" in strat_upper or "REVERSION" in strat_upper or "MOMENTUM" in strat_upper:
        with _connect(settings) as conn:
            conn.row_factory = sqlite3.Row

            for ticker in tickers[:50]:  # Use top 50 tickers for robust backtest sample
                mkt = market_of(ticker)
                prows = conn.execute(
                    """
                    SELECT date, open, high, low, close, volume
                    FROM price_history
                    WHERE ticker = ? AND date >= ? AND date <= ?
                    ORDER BY date ASC
                    """,
                    (ticker.upper(), (pd.Timestamp(start_date) - timedelta(days=90)).strftime("%Y-%m-%d"), today_str),
                ).fetchall()

                if len(prows) < 30:
                    continue

                df = pd.DataFrame([dict(r) for r in prows])
                df["close"] = pd.to_numeric(df["close"], errors="coerce")
                df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0)
                df["sma20"] = df["close"].rolling(20).mean()
                df["sma50"] = df["close"].rolling(50).mean()
                df["roll_max20"] = df["close"].rolling(20).max()
                df["roll_min20"] = df["close"].rolling(20).min()
                df["roll_max252"] = df["close"].rolling(min(252, len(df))).max()
                df["roll_min252"] = df["close"].rolling(min(252, len(df))).min()
                df["vol_sma20"] = df["volume"].rolling(20).mean()

                # Sample every 5 trading days (weekly cadence)
                for idx in range(50, len(df), 5):
                    row = df.iloc[idx]
                    dt_str = str(row["date"])[:10]
                    if dt_str < start_date:
                        continue

                    close_p = float(row["close"])
                    sma20 = float(row["sma20"]) if pd.notnull(row["sma20"]) else close_p
                    sma50 = float(row["sma50"]) if pd.notnull(row["sma50"]) else sma20
                    vol = float(row["volume"])
                    vol_sma = float(row["vol_sma20"]) if pd.notnull(row["vol_sma20"]) else vol
                    max20 = float(row["roll_max20"]) if pd.notnull(row["roll_max20"]) else close_p
                    min20 = float(row["roll_min20"]) if pd.notnull(row["roll_min20"]) else close_p
                    max252 = float(row["roll_max252"]) if pd.notnull(row["roll_max252"]) else close_p
                    min252 = float(row["roll_min252"]) if pd.notnull(row["roll_min252"]) else close_p

                    # A. Kronos_1Y_Backtest (14-day horizon)
                    if run_all or "KRONOS" in strat_upper:
                        k_target = (pd.Timestamp(dt_str) + timedelta(days=14)).strftime("%Y-%m-%d")
                        chan_range = (max20 - min20) if max20 > min20 else 1.0
                        pos = (close_p - min20) / chan_range

                        if close_p > sma20 and sma20 > sma50:
                            k_sig = "BULLISH"
                            k_ret = round(3.5 + pos * 2.0, 2)
                        elif close_p < sma20 and sma20 < sma50:
                            k_sig = "BEARISH"
                            k_ret = round(-3.5 - (1.0 - pos) * 2.0, 2)
                        else:
                            k_sig = "NEUTRAL"
                            k_ret = 0.0

                        generated_predictions.append((
                            ticker.upper(),
                            "Kronos_1Y_Backtest",
                            k_sig,
                            round(60.0 + abs(k_ret) * 3.0, 1),
                            round(close_p, 2),
                            k_ret,
                            "14D",
                            k_target,
                            "Kronos_MultiFactor_Simulation",
                            f"Kronos 14D Trend Signal: {k_sig} ({k_ret:+.2f}%)",
                            f"SMA20={sma20:.2f}, SMA50={sma50:.2f}, Channel pos={pos:.2f}",
                            mkt,
                            f"{dt_str} 15:30:00",
                        ))

                    # B. News_Momentum_Breakout (5-day horizon)
                    if run_all or "BREAKOUT" in strat_upper or "MOMENTUM" in strat_upper:
                        if close_p >= max20 * 0.995 and vol >= vol_sma * 1.2:
                            b_target = (pd.Timestamp(dt_str) + timedelta(days=5)).strftime("%Y-%m-%d")
                            generated_predictions.append((
                                ticker.upper(),
                                "News_Momentum_Breakout",
                                "BULLISH",
                                78.0,
                                round(close_p, 2),
                                5.0,
                                "5D",
                                b_target,
                                "Catalyst_Volume_Radar",
                                "Volume Surge Breakout above 20-Day Resistance",
                                f"Volume {vol/vol_sma:.1f}x SMA20, Breakout price {close_p:.2f}",
                                mkt,
                                f"{dt_str} 15:30:00",
                            ))

                    # C. Mean_Reversion_52W (5-day horizon)
                    if run_all or "REVERSION" in strat_upper:
                        dist_low = (close_p - min252) / min252 if min252 > 0 else 1.0
                        dist_high = (max252 - close_p) / max252 if max252 > 0 else 1.0
                        r_target = (pd.Timestamp(dt_str) + timedelta(days=5)).strftime("%Y-%m-%d")

                        if dist_low < 0.04:  # within 4% of 52w low
                            generated_predictions.append((
                                ticker.upper(),
                                "Mean_Reversion_52W",
                                "BULLISH",
                                72.0,
                                round(close_p, 2),
                                4.0,
                                "5D",
                                r_target,
                                "52W_Extreme_Filter",
                                f"Oversold 52-Week Low Bounce Setup (+{dist_low:.1%} from 52w low)",
                                f"52w low={min252:.2f}, entry={close_p:.2f}",
                                mkt,
                                f"{dt_str} 15:30:00",
                            ))
                        elif dist_high < 0.02 and close_p < sma20:  # rejection at 52w high
                            generated_predictions.append((
                                ticker.upper(),
                                "Mean_Reversion_52W",
                                "BEARISH",
                                70.0,
                                round(close_p, 2),
                                -3.5,
                                "5D",
                                r_target,
                                "52W_Extreme_Filter",
                                f"Overbought 52-Week High Resistance Rejection (-{dist_high:.1%} from 52w high)",
                                f"52w high={max252:.2f}, entry={close_p:.2f}",
                                mkt,
                                f"{dt_str} 15:30:00",
                            ))

    # Bulk insert all generated backtest predictions
    inserted_count = 0
    if generated_predictions:
        with _connect(settings) as conn:
            # Avoid inserting duplicate (ticker, strategy_name, created_at)
            existing = set()
            rows_exist = conn.execute(
                "SELECT ticker, strategy_name, created_at FROM strategy_predictions"
            ).fetchall()
            existing = {(r[0], r[1], r[2]) for r in rows_exist}

            filtered = [p for p in generated_predictions if (p[0], p[1], p[12]) not in existing]

            if filtered:
                conn.executemany(
                    """
                    INSERT INTO strategy_predictions
                        (ticker, strategy_name, signal, confidence_pct, entry_price,
                         expected_return_pct, holding_horizon, target_date, news_source,
                         news_headline, notes, market, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    filtered,
                )
                conn.commit()
                inserted_count = len(filtered)

    # Automatically run audit against historical prices
    audit_res = audit_predictions(settings=settings, force=False)
    metrics = calculate_strategy_metrics(settings=settings)

    logger.info(
        "backtest complete: %d generated, %d inserted, %d audited",
        len(generated_predictions), inserted_count, audit_res["evaluated"],
    )

    return {
        "success": True,
        "strategy": strategy_name,
        "lookback_days": days,
        "predictions_generated": len(generated_predictions),
        "predictions_inserted": inserted_count,
        "audited_count": audit_res["evaluated"],
        "pending_count": audit_res["pending"],
        "overall_metrics": metrics.get("overall", {}),
        "by_strategy": metrics.get("by_strategy", {}),
    }

