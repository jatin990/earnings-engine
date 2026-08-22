"""SQLite-backed persistence for the Kronos AI price-prediction audit trail.

Every Kronos forecast (one per ticker per run) is stored as an immutable audit
row in the shared ``prices.sqlite3`` database so that the dashboard can display
an "Audit" view of all historical predictions plus a "Latest" view (the most
recent prediction per ticker).

Design notes
------------
* Reuses the *same* SQLite database as prices / earnings (see ``_cache_path`` in
  ``prices.py``) so there is a single cache file under ``data/cache/prices/``.
* The full forecast dict is kept verbatim in ``prediction_json`` for faithful
  replay, while the most-queried scalars are duplicated into indexed columns.
* ``run_at`` is the wall-clock time the prediction *run* started (several
  tickers share one ``run_at``).  ``predicted_at`` is the price-date the
  forecast was based on (defaults to ``run_at``).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from earnings_engine.config import Settings
from earnings_engine.data.prices import _cache_path as _prices_cache_path
from earnings_engine.logging_utils import get_logger

logger = get_logger("earnings_engine.data.predictions")


def _db_path(settings: Settings) -> Path:
    """Use the same SQLite database as prices / earnings."""
    return _prices_cache_path(settings)


def _connect(settings: Settings) -> sqlite3.Connection:
    """Connect to the shared SQLite database, creating the table if missing."""
    settings.ensure_dirs()
    connection = sqlite3.connect(_db_path(settings))
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS kronos_predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            run_at TEXT NOT NULL,
            predicted_at TEXT NOT NULL,
            lookback INTEGER,
            pred_len INTEGER,
            prediction_json TEXT NOT NULL,
            current_price REAL,
            support REAL,
            resistance REAL,
            return_pct REAL,
            trend TEXT,
            explanation TEXT
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_kronos_pred_ticker_run
        ON kronos_predictions (ticker, run_at DESC)
        """
    )
    connection.commit()
    return connection


# Columns returned by the readers, in a stable order.  ``prediction_json`` is
# always expanded back into a dict on read.
_READ_COLUMNS = (
    "id",
    "ticker",
    "run_at",
    "predicted_at",
    "lookback",
    "pred_len",
    "prediction_json",
    "current_price",
    "support",
    "resistance",
    "return_pct",
    "trend",
    "explanation",
)


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    """Convert a SQLite row into a friendly dict (JSON blob expanded)."""
    result: dict[str, Any] = {}
    for col in _READ_COLUMNS:
        result[col] = row[col] if col != "prediction_json" else None
    result["prediction"] = json.loads(row["prediction_json"]) if row["prediction_json"] else {}
    return result


def store_prediction(
    ticker: str,
    settings: Settings,
    payload: dict[str, Any],
    run_at: str | None = None,
    predicted_at: str | None = None,
) -> int:
    """Store a single Kronos prediction result as an immutable audit row.

    Parameters
    ----------
    ticker:
        The stock ticker the prediction is for.
    settings:
        Runtime :class:`Settings` (controls the cache DB path).
    payload:
        The full forecast dict produced by ``predict_single_stock`` (e.g.
        ``symbol``, ``name``, ``current_price``, ``support``, ``resistance``,
        ``return_pct``, ``trend``, ``results_date``, ``explanation``).
    run_at:
        Optional ISO timestamp for this prediction *run*.  Defaults to now.
    predicted_at:
        Optional ISO timestamp of the price-date the forecast was based on.
        Defaults to ``run_at``.

    Returns
    -------
    int
        The inserted row id.
    """
    now = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    run_at = run_at or now
    predicted_at = predicted_at or run_at

    prediction_json = json.dumps(payload, sort_keys=True, default=str)

    with _connect(settings) as connection:
        cursor = connection.execute(
            """
            INSERT INTO kronos_predictions
                (ticker, run_at, predicted_at, lookback, pred_len,
                 prediction_json, current_price, support, resistance,
                 return_pct, trend, explanation)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ticker,
                run_at,
                predicted_at,
                int(payload.get("lookback", 0)) if payload.get("lookback") is not None else None,
                int(payload.get("pred_len", 0)) if payload.get("pred_len") is not None else None,
                prediction_json,
                payload.get("current_price"),
                payload.get("support"),
                payload.get("resistance"),
                payload.get("return_pct"),
                payload.get("trend"),
                payload.get("explanation"),
            ),
        )
        connection.commit()

    logger.info("stored kronos prediction ticker=%s run_at=%s rowid=%s", ticker, run_at, cursor.lastrowid)
    return cursor.lastrowid


def load_prediction_history(
    tickers: list[str] | None = None,
    limit: int | None = None,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """Return the full audit history of stored predictions.

    Parameters
    ----------
    tickers:
        If provided, restrict to these tickers.
    limit:
        If provided, cap the number of rows returned (most recent first).
    settings:
        Optional settings; defaults to a fresh :class:`Settings`.
    """
    if settings is None:
        settings = Settings()

    query_parts = ["SELECT * FROM kronos_predictions"]
    params: list[Any] = []
    if tickers:
        placeholders = ", ".join(["?"] * len(tickers))
        query_parts.append(f"WHERE ticker IN ({placeholders})")
        params.extend(tickers)
    query_parts.append("ORDER BY run_at DESC, id DESC")
    if limit is not None:
        query_parts.append(f"LIMIT {int(limit)}")
    query = " ".join(query_parts)

    with _connect(settings) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(query, params).fetchall()

    return [_row_to_dict(r) for r in rows]


def load_latest_predictions(
    tickers: list[str] | None = None,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """Return the most-recent prediction for each ticker.

    "Most recent" is defined by the greatest ``(run_at, id)`` — i.e. the latest
    prediction run that touched a given ticker.  Multiple runs on the same
    ticker are collapsed to one row here.
    """
    history = load_prediction_history(tickers=tickers, settings=settings)

    seen: dict[str, dict[str, Any]] = {}
    for row in history:  # already ordered by run_at DESC, id DESC
        ticker = row["ticker"]
        if ticker not in seen:
            seen[ticker] = row
    return list(seen.values())


def load_predictions_by_date(
    tickers: list[str],
    date_str: str,
    settings: Settings | None = None,
) -> dict[str, dict[str, Any]]:
    """Return the most-recent prediction per ticker whose run started on ``date_str``.

    ``date_str`` is a ``YYYY-MM-DD`` calendar day.  ``run_at`` is stored as
    ``YYYY-MM-DD HH:MM:SS``, so a row "belongs to" a day when its ``run_at``
    prefix matches.  This lets the standalone ``cache-predictions`` workflow
    skip re-running the Kronos model when today's predictions already exist in
    the audit trail.

    Returns a dict ``{ticker: audit_row}`` (one row per ticker, most recent
    first).  Tickers with no prediction on that day are simply absent.
    """
    if settings is None:
        settings = Settings()

    if not tickers:
        return {}

    placeholders = ", ".join(["?"] * len(tickers))
    query = (
        "SELECT * FROM kronos_predictions "
        f"WHERE ticker IN ({placeholders}) AND substr(run_at, 1, 10) = ? "
        "ORDER BY run_at DESC, id DESC"
    )
    params: list[Any] = [*tickers, date_str]

    with _connect(settings) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(query, params).fetchall()

    seen: dict[str, dict[str, Any]] = {}
    for row in rows:
        ticker = row["ticker"]
        if ticker not in seen:
            seen[ticker] = _row_to_dict(row)
    return seen


def delete_prediction(
    ticker: str,
    run_at: str,
    settings: Settings | None = None,
) -> bool:
    """Delete a specific prediction row identified by ticker + run_at.

    Parameters
    ----------
    ticker:
        The stock ticker.
    run_at:
        The ISO timestamp string for the prediction run.
    settings:
        Optional settings; defaults to a fresh :class:`Settings`.

    Returns
    -------
    bool
        True if a row was deleted, False if no matching row was found.
    """
    if settings is None:
        settings = Settings()

    with _connect(settings) as connection:
        cursor = connection.execute(
            """
            DELETE FROM kronos_predictions
            WHERE ticker = ? AND run_at = ?
            """,
            (ticker, run_at),
        )
        connection.commit()
        deleted = cursor.rowcount > 0

    if deleted:
        logger.info("deleted kronos prediction ticker=%s run_at=%s", ticker, run_at)
    else:
        logger.warning("no kronos prediction found to delete ticker=%s run_at=%s", ticker, run_at)
    return deleted


def evaluate_prediction_outcome(
    predicted_price: float | None,
    predicted_return_pct: float | None,
    predicted_trend: str | None,
    current_price: float | None,
) -> dict[str, Any]:
    """Evaluate whether a single Kronos forecast worked or failed.

    Rules:
    - If Bullish (or predicted return > 0): Worked if actual move > 0, Failed if actual move < 0.
    - If Bearish (or predicted return < 0): Worked if actual move < 0, Failed if actual move > 0.
    - If Neutral or delta is 0 / missing: Flat / Pending.
    """
    if predicted_price is None or current_price is None or predicted_price <= 0:
        return {
            "status": "PENDING",
            "is_correct": None,
            "actual_delta": None,
            "actual_delta_pct": None,
            "label": "⏳ Pending",
            "badge_class": "badge-neutral",
        }

    delta = current_price - predicted_price
    delta_pct = (delta / predicted_price) * 100.0

    trend = (predicted_trend or "").capitalize()
    ret_pct = predicted_return_pct if predicted_return_pct is not None else 0.0

    is_bullish = trend == "Bullish" or ret_pct > 0.3
    is_bearish = trend == "Bearish" or ret_pct < -0.3

    if abs(delta_pct) < 0.05:
        return {
            "status": "FLAT",
            "is_correct": None,
            "actual_delta": round(delta, 2),
            "actual_delta_pct": round(delta_pct, 2),
            "label": "⏳ Flat (0.0%)",
            "badge_class": "badge-neutral",
        }

    if is_bullish:
        if delta_pct > 0:
            return {
                "status": "WORKED",
                "is_correct": True,
                "actual_delta": round(delta, 2),
                "actual_delta_pct": round(delta_pct, 2),
                "label": f"✅ Worked (+{delta_pct:.1f}%)",
                "badge_class": "price-positive",
            }
        else:
            return {
                "status": "FAILED",
                "is_correct": False,
                "actual_delta": round(delta, 2),
                "actual_delta_pct": round(delta_pct, 2),
                "label": f"❌ Failed ({delta_pct:.1f}%)",
                "badge_class": "price-negative",
            }
    elif is_bearish:
        if delta_pct < 0:
            return {
                "status": "WORKED",
                "is_correct": True,
                "actual_delta": round(delta, 2),
                "actual_delta_pct": round(delta_pct, 2),
                "label": f"✅ Worked ({delta_pct:.1f}%)",
                "badge_class": "price-positive",
            }
        else:
            return {
                "status": "FAILED",
                "is_correct": False,
                "actual_delta": round(delta, 2),
                "actual_delta_pct": round(delta_pct, 2),
                "label": f"❌ Failed (+{delta_pct:.1f}%)",
                "badge_class": "price-negative",
            }

    return {
        "status": "NEUTRAL",
        "is_correct": None,
        "actual_delta": round(delta, 2),
        "actual_delta_pct": round(delta_pct, 2),
        "label": f"Neutral ({delta_pct:+.1f}%)",
        "badge_class": "badge-neutral",
    }


def benchmark_ohlcv_forecast(
    forecast_series: list[dict[str, Any]],
    actual_prices: pd.DataFrame | list[dict[str, Any]] | None = None,
    ticker: str | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Benchmark a forecasted 14-day OHLCV series against actual realized daily bars.

    Parameters
    ----------
    forecast_series:
        List of forecasted daily OHLCV dicts:
        ``[{"date": "2026-08-18", "open": 100, "high": 105, "low": 98, "close": 104, "volume": 50000}, ...]``
    actual_prices:
        DataFrame or list of actual historical daily OHLCV bars.
    ticker:
        Stock ticker symbol to load prices for if actual_prices is None.
    settings:
        Settings instance.

    Returns
    -------
    dict with daily bar comparisons and aggregate benchmark metrics (MAPE, Directional Hit Rate, Corridor Hit Rate).
    """
    if settings is None:
        settings = Settings()

    # Load actual prices if not provided
    act_df: pd.DataFrame | None = None
    if isinstance(actual_prices, pd.DataFrame):
        act_df = actual_prices
    elif ticker:
        try:
            from earnings_engine.data.prices import fetch_prices, load_prices
            act_df = load_prices(ticker, settings)
            # If forecast dates extend past cached prices and market dates have elapsed, fetch delta
            series_dates = [str(f.get("date") or "").split(" ")[0] for f in forecast_series if f.get("date")]
            if series_dates:
                min_series_date = min(series_dates)
                max_cached_date = str(act_df.index.max()).split(" ")[0] if act_df is not None and not act_df.empty else ""
                today_str = datetime.now().strftime("%Y-%m-%d")
                if max_cached_date < today_str and (not max_cached_date or max_cached_date <= min_series_date or max_cached_date < max(series_dates)):
                    act_df = fetch_prices(ticker, settings)
        except Exception:
            act_df = None

    actual_map: dict[str, dict[str, float]] = {}
    if act_df is not None and not act_df.empty:
        for idx, row in act_df.iterrows():
            d_str = str(idx).split(" ")[0] if not isinstance(idx, str) else idx.split(" ")[0]
            try:
                actual_map[d_str] = {
                    "open": float(row["open"]) if pd.notna(row.get("open")) else 0.0,
                    "high": float(row["high"]) if pd.notna(row.get("high")) else 0.0,
                    "low": float(row["low"]) if pd.notna(row.get("low")) else 0.0,
                    "close": float(row["close"]) if pd.notna(row.get("close")) else 0.0,
                    "volume": float(row["volume"]) if pd.notna(row.get("volume")) else 0.0,
                }
            except (ValueError, KeyError, TypeError):
                continue
    elif isinstance(actual_prices, list):
        for item in actual_prices:
            d_str = str(item.get("date") or "").split(" ")[0]
            if d_str:
                actual_map[d_str] = {
                    "open": float(item.get("open") or 0.0),
                    "high": float(item.get("high") or 0.0),
                    "low": float(item.get("low") or 0.0),
                    "close": float(item.get("close") or 0.0),
                    "volume": float(item.get("volume") or 0.0),
                }

    bars: list[dict[str, Any]] = []
    settled_errors: list[float] = []
    range_hits = 0
    dir_hits = 0
    settled_count = 0
    prev_pred_close: float | None = None
    prev_act_close: float | None = None

    for f_bar in forecast_series:
        d_str = str(f_bar.get("date") or "").split(" ")[0]
        pred_o = float(f_bar.get("open") or 0.0)
        pred_h = float(f_bar.get("high") or 0.0)
        pred_l = float(f_bar.get("low") or 0.0)
        pred_c = float(f_bar.get("close") or 0.0)
        pred_v = float(f_bar.get("volume") or 0.0)

        act = actual_map.get(d_str)
        if act and act["close"] > 0:
            settled_count += 1
            act_c = act["close"]
            act_h = act["high"]
            act_l = act["low"]
            act_o = act["open"]
            act_v = act["volume"]

            err_pct = round(abs(act_c - pred_c) / act_c * 100.0, 2)
            delta_pct = round((act_c - pred_c) / pred_c * 100.0, 2) if pred_c > 0 else 0.0
            settled_errors.append(err_pct)

            # In-corridor hit: actual close was bounded by forecasted [low, high]
            corridor_hit = bool(pred_l * 0.99 <= act_c <= pred_h * 1.01)
            if corridor_hit:
                range_hits += 1

            # Directional hit: daily candle moved in forecasted direction
            dir_hit = None
            if prev_pred_close is not None and prev_act_close is not None:
                pred_up = pred_c >= prev_pred_close
                act_up = act_c >= prev_act_close
                dir_hit = (pred_up == act_up)
                if dir_hit:
                    dir_hits += 1

            bars.append({
                "date": d_str,
                "pred_open": pred_o,
                "pred_high": pred_h,
                "pred_low": pred_l,
                "pred_close": pred_c,
                "pred_volume": pred_v,
                "actual_open": act_o,
                "actual_high": act_h,
                "actual_low": act_l,
                "actual_close": act_c,
                "actual_volume": act_v,
                "delta_pct": delta_pct,
                "error_pct": err_pct,
                "corridor_hit": corridor_hit,
                "dir_hit": dir_hit,
                "status": "SETTLED",
                "label": f"✅ {err_pct:.1f}% err" if err_pct <= 3.0 else f"⚠️ {err_pct:.1f}% err",
            })
            prev_pred_close = pred_c
            prev_act_close = act_c
        else:
            bars.append({
                "date": d_str,
                "pred_open": pred_o,
                "pred_high": pred_h,
                "pred_low": pred_l,
                "pred_close": pred_c,
                "pred_volume": pred_v,
                "actual_open": None,
                "actual_high": None,
                "actual_low": None,
                "actual_close": None,
                "actual_volume": None,
                "delta_pct": None,
                "error_pct": None,
                "corridor_hit": None,
                "dir_hit": None,
                "status": "UPCOMING",
                "label": "⏳ Upcoming",
            })
            prev_pred_close = pred_c

    mape = round(float(pd.Series(settled_errors).mean()), 2) if settled_errors else 0.0
    corridor_hit_pct = round((range_hits / settled_count * 100.0), 1) if settled_count > 0 else 0.0
    dir_count = max(1, settled_count - 1) if settled_count > 1 else settled_count
    dir_hit_pct = round((dir_hits / dir_count * 100.0), 1) if settled_count > 1 else (100.0 if dir_hits > 0 else 0.0)

    # Composite OHLCV accuracy score
    price_score = max(0.0, 100.0 - mape)
    overall_score = round((price_score * 0.4 + corridor_hit_pct * 0.3 + dir_hit_pct * 0.3), 1) if settled_count > 0 else 0.0

    return {
        "bars": bars,
        "summary": {
            "total_bars": len(forecast_series),
            "settled_bars": settled_count,
            "upcoming_bars": len(forecast_series) - settled_count,
            "mape_pct": mape,
            "corridor_hit_pct": corridor_hit_pct,
            "directional_accuracy_pct": dir_hit_pct,
            "overall_score_pct": overall_score,
            "is_evaluated": settled_count > 0,
        },
    }


def get_kronos_accuracy_summary(
    tickers: list[str] | None = None,
    live_prices: dict[str, float] | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Calculate overall and per-stock Kronos prediction accuracy across the audit trail.

    Parameters
    ----------
    tickers:
        Optional list of tickers to restrict the accuracy calculation.
    live_prices:
        Optional pre-fetched dict ``{ticker: current_price}``. If None, prices
        are loaded from the local price cache.
    settings:
        Settings instance.

    Returns
    -------
    dict with overall stats and per-stock accuracy breakdown.
    """
    if settings is None:
        settings = Settings()

    history = load_prediction_history(tickers=tickers, settings=settings)
    if not history:
        return {
            "overall": {
                "total_predictions": 0,
                "evaluated_predictions": 0,
                "correct_count": 0,
                "failed_count": 0,
                "accuracy_pct": 0.0,
                "win_rate_pct": 0.0,
            },
            "by_stock": [],
        }

    # Gather latest known prices if not provided
    prices_map: dict[str, float] = dict(live_prices or {})
    all_tickers = {r["ticker"] for r in history}
    for t in all_tickers:
        if t not in prices_map:
            try:
                from earnings_engine.data.prices import load_prices
                pdf = load_prices(t, settings)
                if not pdf.empty and "close" in pdf.columns:
                    closes = pd.to_numeric(pdf["close"], errors="coerce").dropna()
                    if not closes.empty:
                        prices_map[t] = float(closes.iloc[-1])
            except Exception:
                pass

    # Group predictions by ticker and timeframe/date session
    # (Runs on the same calendar date or within 12h at similar price belong to 1 forecast period)
    ticker_runs: dict[str, list[dict[str, Any]]] = {}
    for row in history:
        t = row["ticker"]
        if t not in ticker_runs:
            ticker_runs[t] = []
        ticker_runs[t].append(row)

    by_stock_data: dict[str, dict[str, Any]] = {}
    total_evaluated = 0
    total_correct = 0
    total_failed = 0
    total_sessions_count = 0

    for ticker, rows in ticker_runs.items():
        # Sort newest first
        sorted_rows = sorted(rows, key=lambda r: str(r.get("run_at") or ""), reverse=True)
        
        # Cluster into timeframe sessions
        sessions: list[dict[str, Any]] = []
        cur_session: dict[str, Any] | None = None

        for row in sorted_rows:
            run_at_str = str(row.get("run_at") or "")
            run_date = run_at_str.split(" ")[0] if " " in run_at_str else run_at_str[:10]
            pred = row.get("prediction") or {}
            pred_p = pred.get("current_price") or row.get("current_price") or 0.0

            if cur_session is None:
                cur_session = {
                    "date": run_date,
                    "representative": row,
                    "runs": [row],
                    "anchor_price": pred_p,
                }
            else:
                price_diff_pct = (abs(pred_p - cur_session["anchor_price"]) / cur_session["anchor_price"] * 100.0) if cur_session["anchor_price"] > 0 else 0.0
                if run_date == cur_session["date"] or price_diff_pct < 0.75:
                    cur_session["runs"].append(row)
                else:
                    sessions.append(cur_session)
                    cur_session = {
                        "date": run_date,
                        "representative": row,
                        "runs": [row],
                        "anchor_price": pred_p,
                    }
        if cur_session:
            sessions.append(cur_session)

        st = {
            "ticker": ticker,
            "total_predictions": len(rows),
            "total_sessions": len(sessions),
            "evaluated_count": 0,
            "correct_count": 0,
            "failed_count": 0,
            "pending_count": 0,
            "pred_returns": [],
            "actual_returns": [],
            "latest_run_at": sorted_rows[0].get("run_at") if sorted_rows else None,
            "latest_status": "PENDING",
        }

        for sess in sessions:
            rep = sess["representative"]
            pred = rep.get("prediction") or {}
            pred_p = pred.get("current_price") or rep.get("current_price")
            ret_p = pred.get("return_pct") if pred.get("return_pct") is not None else rep.get("return_pct")
            trend = pred.get("trend") or rep.get("trend")
            cur_p = prices_map.get(ticker)

            outcome = evaluate_prediction_outcome(pred_p, ret_p, trend, cur_p)
            rep["outcome"] = outcome
            total_sessions_count += 1

            if outcome["status"] == "WORKED":
                st["evaluated_count"] += 1
                st["correct_count"] += 1
                total_evaluated += 1
                total_correct += 1
            elif outcome["status"] == "FAILED":
                st["evaluated_count"] += 1
                st["failed_count"] += 1
                total_evaluated += 1
                total_failed += 1
            else:
                st["pending_count"] += 1

            if ret_p is not None:
                st["pred_returns"].append(float(ret_p))
            if outcome["actual_delta_pct"] is not None:
                st["actual_returns"].append(float(outcome["actual_delta_pct"]))

        if sessions:
            st["latest_status"] = sessions[0]["representative"].get("outcome", {}).get("status", "PENDING")

        by_stock_data[ticker] = st

    by_stock_list: list[dict[str, Any]] = []
    for ticker, d in by_stock_data.items():
        ev = d["evaluated_count"]
        acc = round((d["correct_count"] / ev * 100.0), 1) if ev > 0 else 0.0
        avg_pred = round(float(pd.Series(d["pred_returns"]).mean()), 2) if d["pred_returns"] else 0.0
        avg_act = round(float(pd.Series(d["actual_returns"]).mean()), 2) if d["actual_returns"] else 0.0

        by_stock_list.append({
            "ticker": ticker,
            "total_predictions": d["total_predictions"],
            "total_sessions": d["total_sessions"],
            "evaluated_count": ev,
            "correct_count": d["correct_count"],
            "failed_count": d["failed_count"],
            "pending_count": d["pending_count"],
            "accuracy_pct": acc,
            "avg_predicted_return": avg_pred,
            "avg_actual_return": avg_act,
            "latest_run_at": d["latest_run_at"],
            "latest_status": d["latest_status"],
        })

    # Sort stocks by evaluated_count DESC, then accuracy_pct DESC
    by_stock_list.sort(key=lambda x: (x["evaluated_count"] > 0, x["accuracy_pct"], x["total_predictions"]), reverse=True)

    overall_acc = round((total_correct / total_evaluated * 100.0), 1) if total_evaluated > 0 else 0.0

    return {
        "overall": {
            "total_predictions": len(history),
            "evaluated_predictions": total_evaluated,
            "correct_count": total_correct,
            "failed_count": total_failed,
            "accuracy_pct": overall_acc,
            "win_rate_pct": overall_acc,
            "stocks_tracked": len(by_stock_list),
        },
        "by_stock": by_stock_list,
    }

