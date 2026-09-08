"""Settlement Worker & Outcome Evaluation Engine for AI Consensus Predictions.

Automatically grades pending predictions whose evaluation_date has arrived,
evaluates actual price returns against predicted targets, and triggers
the AI failure post-mortem diagnostic when a prediction fails.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from earnings_engine.config import Settings
from earnings_engine.consensus import failure_analyst, storage
from earnings_engine.data.db import get_db_connection

logger = logging.getLogger("earnings_engine.consensus.settlement")


def settle_pending_predictions(
    settings: Settings | None = None,
    as_of_date: str | None = None,
) -> dict[str, Any]:
    """Check and settle all mature consensus predictions.

    Args:
        settings: Optional Settings instance.
        as_of_date: ISO date string (YYYY-MM-DD) representing today. Defaults to current date.

    Returns:
        Summary dict containing settled counts, success count, failure count, etc.
    """
    settings = settings or Settings()
    today_str = as_of_date or datetime.now().strftime("%Y-%m-%d")

    pending_list = storage.get_pending_predictions(settings=settings, before_date=today_str)
    logger.info("[SETTLEMENT] Found %d pending consensus predictions due on or before %s", len(pending_list), today_str)

    settled_count = 0
    success_count = 0
    partial_count = 0
    failure_count = 0
    invalidated_count = 0
    settled_items: list[dict[str, Any]] = []

    for pred in pending_list:
        try:
            pred_id = pred["id"]
            ticker = pred["ticker"]
            as_of_price = float(pred["as_of_price"])
            eval_date = str(pred["evaluation_date"])[:10]
            consensus_dir = str(pred.get("consensus_direction", "NEUTRAL")).upper()
            target_return = float(pred.get("consensus_return_pct", 0.0))

            # Fetch the actual closing price on/near evaluation_date
            actual_price = _fetch_settlement_price(ticker, eval_date, settings)
            if actual_price is None or actual_price <= 0:
                logger.warning("[SETTLEMENT] Could not resolve exit price for %s on %s (pred_id=%d)", ticker, eval_date, pred_id)
                continue

            actual_return_pct = round(((actual_price / as_of_price) - 1.0) * 100.0, 2)

            # Evaluate outcome
            status, is_dir_correct = _evaluate_outcome(
                direction=consensus_dir,
                target_return_pct=target_return,
                actual_return_pct=actual_return_pct,
            )

            settlement_data: dict[str, Any] = {
                "settlement_status": status,
                "settled_at": datetime.now().isoformat(),
                "actual_exit_price": round(actual_price, 2),
                "actual_return_pct": actual_return_pct,
                "is_direction_correct": 1 if is_dir_correct else 0,
                "failure_category": None,
                "failure_reason_summary": None,
                "failure_post_mortem": None,
            }

            # If failed or partial, run AI post-mortem diagnostic
            if status in ("FAILURE", "PARTIAL"):
                try:
                    diag = failure_analyst.diagnose_failure(
                        prediction=pred,
                        actual_exit_price=actual_price,
                        actual_return_pct=actual_return_pct,
                        settings=settings,
                    )
                    settlement_data["failure_category"] = diag.get("failure_category")
                    settlement_data["failure_reason_summary"] = diag.get("summary")
                    settlement_data["failure_post_mortem"] = diag.get("detailed_analysis")
                except Exception as diag_err:
                    logger.error("[SETTLEMENT] Post-mortem diagnosis failed for pred_id=%d: %s", pred_id, diag_err)

            storage.update_settlement(pred_id, settlement_data, settings=settings)
            settled_count += 1

            if status == "SUCCESS":
                success_count += 1
            elif status == "PARTIAL":
                partial_count += 1
            elif status == "FAILURE":
                failure_count += 1
            else:
                invalidated_count += 1

            settled_items.append({
                "id": pred_id,
                "ticker": ticker,
                "status": status,
                "actual_return_pct": actual_return_pct,
                "predicted_return_pct": target_return,
            })

        except Exception as e:
            logger.error("[SETTLEMENT] Error settling prediction %s: %s", pred.get("id"), e)

    return {
        "as_of_date": today_str,
        "total_due": len(pending_list),
        "settled_count": settled_count,
        "success_count": success_count,
        "partial_count": partial_count,
        "failure_count": failure_count,
        "invalidated_count": invalidated_count,
        "settled_predictions": settled_items,
    }


def _evaluate_outcome(
    direction: str,
    target_return_pct: float,
    actual_return_pct: float,
) -> tuple[str, bool]:
    """Grade prediction outcome against actual returns.

    Criteria:
    - SUCCESS:
      - BULLISH and actual_return_pct > 0 and (actual_return_pct >= 0.5 * target_return_pct or target hit)
      - BEARISH and actual_return_pct < 0 and (actual_return_pct <= 0.5 * target_return_pct or target hit)
      - NEUTRAL and abs(actual_return_pct) <= 2.5%
    - PARTIAL:
      - Correct direction, but magnitude was under 50% of expected return.
    - FAILURE:
      - Wrong direction beyond threshold (e.g. Bullish predicted, but price dropped > -1.5%).
    """
    if direction == "BULLISH":
        if actual_return_pct >= 0.5 * max(target_return_pct, 1.0):
            return "SUCCESS", True
        elif actual_return_pct > 0:
            return "PARTIAL", True
        else:
            return "FAILURE", False

    elif direction == "BEARISH":
        if actual_return_pct <= 0.5 * min(target_return_pct, -1.0):
            return "SUCCESS", True
        elif actual_return_pct < 0:
            return "PARTIAL", True
        else:
            return "FAILURE", False

    else:  # NEUTRAL
        if abs(actual_return_pct) <= 2.5:
            return "SUCCESS", True
        elif abs(actual_return_pct) <= 5.0:
            return "PARTIAL", True
        else:
            return "FAILURE", False


def _fetch_settlement_price(ticker: str, eval_date: str, settings: Settings) -> float | None:
    """Fetch the latest available close price on or after evaluation date."""
    try:
        conn = get_db_connection(settings)
        # Check price_history on or after eval_date
        row = conn.execute(
            "SELECT close FROM price_history WHERE ticker = ? AND date >= ? ORDER BY date ASC LIMIT 1",
            (ticker, eval_date),
        ).fetchone()

        if not row:
            # If date hasn't been backfilled into history yet, check latest price
            row = conn.execute(
                "SELECT close FROM price_history WHERE ticker = ? ORDER BY date DESC LIMIT 1",
                (ticker,),
            ).fetchone()

        conn.close()
        if row and row[0] is not None:
            return float(row[0])

    except Exception as e:
        logger.debug("[SETTLEMENT] DB price lookup error for %s: %s", ticker, e)

    # Fallback to yfinance if not present in DB
    try:
        from earnings_engine.rate_limits import record_request
        try:
            record_request("yfinance")
        except Exception:
            pass
        import yfinance as yf
        t = yf.Ticker(ticker)
        hist = t.history(period="5d")
        if not hist.empty and "Close" in hist.columns:
            return float(hist["Close"].iloc[-1])
    except Exception as yf_err:
        logger.debug("[SETTLEMENT] yfinance fallback failed for %s: %s", ticker, yf_err)

    return None
