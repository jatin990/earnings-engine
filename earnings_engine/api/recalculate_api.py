"""On-demand ticker refresh, live metric recalculation, diff analysis, and audit trail."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import pandas as pd

from earnings_engine.config import Settings
from earnings_engine.data import earnings as earnings_mod
from earnings_engine.data import prices as prices_mod
from earnings_engine.data import swing_ranges as swing_ranges_mod
from earnings_engine.data.market_context import detect_swing_range, enrich_upcoming_results
from earnings_engine.data.ticker_audit import record_audit_entry
from earnings_engine.logging_utils import get_logger

logger = get_logger("earnings_engine.api.recalculate_api")


def _snapshot_ticker_state(ticker: str, settings: Settings) -> dict[str, Any]:
    """Capture current cached state for a ticker before re-fetching."""
    from earnings_engine.data.db import get_db_connection

    state: dict[str, Any] = {
        "ticker": ticker,
        "earnings_date": None,
        "current_price": None,
        "week_high": None,
        "week_low": None,
        "week_change": None,
        "pct_from_52w_high": None,
        "pct_from_52w_low": None,
        "thirty_day_return_pct": None,
        "seven_day_return_pct": None,
        "three_day_return_pct": None,
        "channel_position_pct": None,
        "earnings_week_move_pct": None,
        "current_support": None,
        "next_resistance": None,
        "q1_earnings_score": None,
        "q2_earnings_score": None,
        "q3_earnings_score": None,
        "prev_3q_earnings_score": None,
        "q1_ai_summary": None,
        "q2_ai_summary": None,
        "q3_ai_summary": None,
        "eps_estimate": None,
        "eps_reported": None,
        "surprise_pct": None,
    }

    try:
        conn = get_db_connection(settings)
        # 1. Upcoming earnings date
        today_str = pd.Timestamp.today().strftime("%Y-%m-%d")
        e_row = conn.execute(
            "SELECT earnings_date FROM earnings_history WHERE ticker = ? AND earnings_date >= ? ORDER BY earnings_date ASC LIMIT 1",
            (ticker, today_str),
        ).fetchone()
        if not e_row:
            # Fallback to latest past earnings date
            e_row = conn.execute(
                "SELECT earnings_date FROM earnings_history WHERE ticker = ? ORDER BY earnings_date DESC LIMIT 1",
                (ticker,),
            ).fetchone()
        if e_row:
            state["earnings_date"] = str(e_row[0])

        # 2. Metrics cache
        m_row = conn.execute("SELECT metrics FROM tickers WHERE ticker = ?", (ticker,)).fetchone()
        if m_row and m_row[0]:
            try:
                m_data = json.loads(m_row[0]) if isinstance(m_row[0], str) else m_row[0]
                for k in [
                    "current_price", "week_high", "week_low", "week_change",
                    "pct_from_52w_high", "pct_from_52w_low", "thirty_day_return_pct",
                    "seven_day_return_pct", "three_day_return_pct", "channel_position_pct",
                    "earnings_week_move_pct",
                    "current_support", "next_resistance", "q1_earnings_score",
                    "q2_earnings_score", "q3_earnings_score", "prev_3q_earnings_score",
                    "q1_ai_summary", "q2_ai_summary", "q3_ai_summary",
                    "eps_estimate", "eps_reported", "surprise_pct",
                ]:
                    if k in m_data:
                        state[k] = m_data[k]
            except Exception:
                pass

        # 3. Swing ranges
        sr_row = conn.execute("SELECT lower_bound, upper_bound FROM swing_ranges WHERE ticker = ?", (ticker,)).fetchone()
        if sr_row:
            if state["current_support"] is None and sr_row[0] is not None:
                state["current_support"] = float(sr_row[0])
            if state["next_resistance"] is None and sr_row[1] is not None:
                state["next_resistance"] = float(sr_row[1])

        # 4. Fallback latest price if missing in metrics
        if state["current_price"] is None:
            p_row = conn.execute("SELECT close FROM price_history WHERE ticker = ? ORDER BY date DESC LIMIT 1", (ticker,)).fetchone()
            if p_row and p_row[0] is not None:
                state["current_price"] = float(p_row[0])

    except Exception as e:
        logger.warning("Error creating snapshot for %s: %s", ticker, e)

    return state


def recalculate_ticker_metrics(ticker: str, settings: Settings | None = None) -> dict[str, Any]:
    """Force re-fetch earnings date, prices, recalculate metrics, and log audit trail."""
    settings = settings or Settings()
    ticker = ticker.strip().upper()
    if not ticker:
        return {"success": False, "error": "Ticker is required"}

    # 1. Take snapshot of existing values
    prev_state = _snapshot_ticker_state(ticker, settings)
    fresh_earnings_date = prev_state.get("earnings_date")

    # 2. Force fetch fresh earnings dates from external providers
    try:
        e_df = earnings_mod.fetch_earnings(ticker, settings, force=True)
        if e_df is not None and not e_df.empty and "earnings_date" in e_df.columns:
            today_ts = pd.Timestamp.now().normalize()
            # Look for next upcoming date
            future_events = e_df[pd.to_datetime(e_df["earnings_date"]) >= today_ts].sort_values("earnings_date")
            if not future_events.empty:
                fresh_earnings_date = pd.to_datetime(future_events.iloc[0]["earnings_date"]).strftime("%Y-%m-%d")
            else:
                # Or latest recorded date
                latest_events = e_df.sort_values("earnings_date", ascending=False)
                if not latest_events.empty:
                    fresh_earnings_date = pd.to_datetime(latest_events.iloc[0]["earnings_date"]).strftime("%Y-%m-%d")
    except Exception as e:
        logger.warning("Force fetch earnings for %s failed: %s", ticker, e)

    # 3. Force fetch latest daily prices
    try:
        prices_mod.fetch_prices(ticker, settings, force=True)
    except Exception as e:
        logger.warning("Force fetch prices for %s failed: %s", ticker, e)

    # 4. Re-calculate metrics with force=True
    try:
        input_data = {"ticker": ticker}
        if fresh_earnings_date:
            input_data["earnings_date"] = fresh_earnings_date
        input_df = pd.DataFrame([input_data])
        enriched_df = enrich_upcoming_results(input_df, settings, force=True)
        if enriched_df.empty:
            enriched_row: dict[str, Any] = {}
        else:
            enriched_row = enriched_df.iloc[0].to_dict()
    except Exception as e:
        logger.warning("Enrichment during recalculate for %s failed: %s", ticker, e)
        enriched_row = {}

    # Extract updated values
    updated_state: dict[str, Any] = {
        "ticker": ticker,
        "earnings_date": enriched_row.get("earnings_date") or fresh_earnings_date,
        "current_price": enriched_row.get("current_price"),
        "week_high": enriched_row.get("week_high"),
        "week_low": enriched_row.get("week_low"),
        "week_change": enriched_row.get("week_change"),
        "pct_from_52w_high": enriched_row.get("pct_from_52w_high"),
        "pct_from_52w_low": enriched_row.get("pct_from_52w_low"),
        "thirty_day_return_pct": enriched_row.get("thirty_day_return_pct"),
        "seven_day_return_pct": enriched_row.get("seven_day_return_pct"),
        "three_day_return_pct": enriched_row.get("three_day_return_pct"),
        "channel_position_pct": enriched_row.get("channel_position_pct"),
        "earnings_week_move_pct": enriched_row.get("earnings_week_move_pct"),
        "current_support": enriched_row.get("current_support"),
        "next_resistance": enriched_row.get("next_resistance"),
        "q1_earnings_score": enriched_row.get("q1_earnings_score"),
        "q2_earnings_score": enriched_row.get("q2_earnings_score"),
        "q3_earnings_score": enriched_row.get("q3_earnings_score"),
        "prev_3q_earnings_score": enriched_row.get("prev_3q_earnings_score"),
        "q1_ai_summary": enriched_row.get("q1_ai_summary"),
        "q2_ai_summary": enriched_row.get("q2_ai_summary"),
        "q3_ai_summary": enriched_row.get("q3_ai_summary"),
        "eps_estimate": enriched_row.get("eps_estimate"),
        "eps_reported": enriched_row.get("eps_reported"),
        "surprise_pct": enriched_row.get("surprise_pct"),
    }

    # Format timestamps
    for k, v in list(updated_state.items()):
        if isinstance(v, pd.Timestamp):
            updated_state[k] = v.strftime("%Y-%m-%d")
        elif pd.isna(v):
            updated_state[k] = None

    # 5. Compute diff
    diff_data: dict[str, dict[str, Any]] = {}
    changes_summary: list[str] = []

    def _val_differs(v1: Any, v2: Any, tol: float = 0.001) -> bool:
        if v1 is None and v2 is None:
            return False
        if v1 is None or v2 is None:
            return True
        if isinstance(v1, (int, float)) and isinstance(v2, (int, float)):
            return abs(float(v1) - float(v2)) > tol
        return str(v1).strip() != str(v2).strip()

    def _fmt_val(k: str, val: Any) -> str:
        if val is None or pd.isna(val):
            return "—"
        if isinstance(val, (int, float)):
            if "score" in k:
                return f"{int(val)}/9"
            if "pct" in k or "return" in k or "change" in k:
                sign = "+" if float(val) > 0 else ""
                return f"{sign}{float(val):.2f}%"
            if "price" in k or "high" in k or "low" in k or "support" in k or "resistance" in k:
                return f"₹{float(val):,.2f}"
            return f"{float(val):.2f}"
        return str(val)

    field_labels = {
        "earnings_date": "Result Date",
        "current_price": "Price",
        "week_high": "52W High",
        "week_low": "52W Low",
        "week_change": "1W Change",
        "pct_from_52w_high": "% from 52W High",
        "pct_from_52w_low": "% from 52W Low",
        "thirty_day_return_pct": "30D Return",
        "seven_day_return_pct": "7D Return",
        "three_day_return_pct": "3D Return",
        "channel_position_pct": "Channel Position %",
        "earnings_week_move_pct": "Result Week Move",
        "current_support": "Support Channel",
        "next_resistance": "Resistance Channel",
        "q1_earnings_score": "Q1 Quality Score",
        "q2_earnings_score": "Q2 Quality Score",
        "q3_earnings_score": "Q3 Quality Score",
        "prev_3q_earnings_score": "3Q Avg Quality",
        "eps_estimate": "EPS Estimate",
        "eps_reported": "EPS Reported",
        "surprise_pct": "Surprise %",
    }

    for key, label in field_labels.items():
        old_val = prev_state.get(key)
        new_val = updated_state.get(key)
        if _val_differs(old_val, new_val):
            diff_data[key] = {"old": old_val, "new": new_val}
            changes_summary.append(f"{label}: {_fmt_val(key, old_val)} → {_fmt_val(key, new_val)}")

    has_changes = len(changes_summary) > 0

    # 6. Record Audit Log
    audit_entry = record_audit_entry(
        ticker=ticker,
        has_changes=has_changes,
        changes_summary=changes_summary if has_changes else ["No metrics changed; live data already up to date."],
        previous_values=prev_state,
        updated_values=updated_state,
        diff_data=diff_data,
        settings=settings,
    )

    return {
        "success": True,
        "ticker": ticker,
        "has_changes": has_changes,
        "changes_count": len(changes_summary),
        "changes_summary": changes_summary if has_changes else ["No changes detected; all data up to date."],
        "diff_data": diff_data,
        "previous_metrics": prev_state,
        "updated_metrics": updated_state,
        "refreshed_at": audit_entry["refreshed_at"],
        "audit_id": audit_entry["id"],
    }


def recalculate_batch_metrics(
    tickers: list[str],
    settings: Settings | None = None,
    max_tickers: int = 50,
) -> dict[str, Any]:
    """Recalculate metrics for a batch of tickers sequentially and collect diffs."""
    settings = settings or Settings()
    clean_tickers = list(dict.fromkeys([t.strip().upper() for t in tickers if t and t.strip()]))[:max_tickers]
    if not clean_tickers:
        return {"success": False, "error": "No valid tickers provided"}

    results: list[dict[str, Any]] = []
    total_changed = 0

    for sym in clean_tickers:
        try:
            res = recalculate_ticker_metrics(sym, settings)
            if res.get("has_changes"):
                total_changed += 1
            results.append(res)
        except Exception as e:
            logger.warning("Batch recalculation error for %s: %s", sym, e)
            results.append({"success": False, "ticker": sym, "error": str(e)})

    return {
        "success": True,
        "total_requested": len(clean_tickers),
        "total_changed": total_changed,
        "results": results,
    }

