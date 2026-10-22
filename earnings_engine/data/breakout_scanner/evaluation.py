"""On-demand single-stock evaluation, tier assignment, and ticker search for Breakout Radar."""

from __future__ import annotations

import logging
from typing import Any

from earnings_engine.config import Settings
from earnings_engine.data.breakout_scanner.constants import (
    HOT_THRESHOLD,
    WARM_THRESHOLD,
)
from earnings_engine.data.breakout_scanner.state import (
    _pool,
    _rebuild_candidates,
)
from earnings_engine.data.breakout_scanner.scoring import score_breakout, _should_be_hot
from earnings_engine.data.breakout_scanner.audit_log import record_breakout_transition
from earnings_engine.data.breakout_scanner.storage import save_breakout_pool_to_db
from earnings_engine.data.db import get_db_connection

logger = logging.getLogger(__name__)


def evaluate_stock_breakout(
    ticker: str,
    asof_date: str | None = None,
    force_tier: str | None = None,
    strategy: str = "CLASSIC_TECHNICAL",
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Evaluate a single stock on-demand for Breakout Radar setup conviction, key levels, and sub-score metrics."""
    settings = settings or Settings()
    raw = (ticker or "").strip().upper()
    if not raw:
        return {"success": False, "error": "Ticker symbol cannot be empty."}

    # Normalize ticker (append .NS for Indian equities if missing suffix)
    sym = raw
    if not (sym.endswith(".NS") or sym.endswith(".BO") or "." in sym):
        sym = f"{sym}.NS"

    from earnings_engine.data.prices import load_prices, load_price_metrics, fetch_prices

    prices_df = load_prices(sym, settings)
    if prices_df is None or len(prices_df) < 15:
        # Try raw symbol or fetch/ingest
        prices_df = load_prices(raw, settings)
        if prices_df is None or len(prices_df) < 15:
            try:
                prices_df = fetch_prices(sym, settings, force=False)
            except Exception as e:
                logger.warning("[BREAKOUT-EVAL] Fallback fetch failed for %s: %s", sym, e)

    if prices_df is None or prices_df.empty or len(prices_df) < 10:
        return {
            "success": False,
            "error": f"Insufficient price history found for {sym}. Please ensure the symbol is valid and has trading history.",
            "ticker": sym,
        }

    metrics = load_price_metrics(sym, settings) or load_price_metrics(raw, settings) or {}
    company_name = metrics.get("company_name") or sym.replace(".NS", "")
    industry = metrics.get("industry") or metrics.get("sector") or "General Equities"

    quality_scores = [
        float(metrics.get(k)) if metrics.get(k) is not None else None
        for k in ("q1_earnings_score", "q2_earnings_score", "q3_earnings_score")
    ]

    scored = score_breakout(sym, prices_df, quality_scores, asof_date=asof_date, strategy=strategy, settings=settings)
    if not scored:
        return {
            "success": False,
            "error": f"Could not compute breakout metrics for {sym}.",
            "ticker": sym,
        }

    scored["company_name"] = company_name
    scored["industry"] = industry
    scored["success"] = True

    # Check for existing position in database to guarantee signal_price & signal_date immutability
    strat_clean = (strategy or "CLASSIC_TECHNICAL").upper().strip()
    if strat_clean in ("ALL", "*"):
        strat_clean = "CLASSIC_TECHNICAL"

    scored["strategy"] = strat_clean
    current_price = scored.get("current_price") or scored.get("signal_price")
    current_date = scored.get("current_date") or scored.get("signal_date")

    existing_row = None
    try:
        conn = get_db_connection(settings)
        cur = conn.execute(
            "SELECT signal_date, signal_price, predicted_value, breakout_trigger, target_price, stop_loss, outcome, max_gain_pct, created_at FROM breakout_radar WHERE ticker = ? AND UPPER(strategy) = ?",
            (sym, strat_clean),
        )
        existing_row = cur.fetchone()
    except Exception as e:
        logger.debug("[BREAKOUT-EVAL] Existing position check error: %s", e)

    if existing_row:
        orig_sig_date = str(existing_row[0] or "")
        orig_sig_price = float(existing_row[1]) if existing_row[1] is not None else None
        orig_pred_val = float(existing_row[2]) if existing_row[2] is not None else None
        orig_trigger = float(existing_row[3]) if existing_row[3] is not None else None
        orig_target = float(existing_row[4]) if existing_row[4] is not None else None
        orig_stop = float(existing_row[5]) if existing_row[5] is not None else None
        prev_outcome = str(existing_row[6] or "ACTIVE").upper()
        prev_max_gain = float(existing_row[7] or 0.0)

        # Check if previous position reached terminal state (TARGET_HIT/STOP_HIT) AND current price has formed a new setup at distinct level (>= 5% diff)
        is_distinct_new_position = (
            prev_outcome in ("TARGET_HIT", "STOP_HIT")
            and orig_sig_price is not None
            and orig_sig_price > 0
            and current_price is not None
            and abs(current_price - orig_sig_price) / orig_sig_price >= 0.05
        )

        if not is_distinct_new_position and orig_sig_price is not None and orig_sig_price > 0:
            # PRESERVE ORIGINAL POSITION ANCHOR
            scored["signal_date"] = orig_sig_date
            scored["signal_price"] = orig_sig_price
            scored["predicted_value"] = orig_pred_val or orig_sig_price
            if orig_trigger:
                scored["breakout_trigger"] = orig_trigger
            if orig_target:
                scored["target_price"] = orig_target
            if orig_stop:
                scored["stop_loss"] = orig_stop

            # UPDATE LIVE POSITION METRICS RELATIVE TO ORIGINAL ANCHOR
            if current_price and orig_sig_price > 0:
                rel_ret = round(((current_price - orig_sig_price) / orig_sig_price) * 100, 2)
                scored["realized_return_pct"] = rel_ret
                scored["max_gain_pct"] = max(prev_max_gain, rel_ret)

                # Update trading days elapsed since original inception
                try:
                    import pandas as pd
                    d_cur = pd.to_datetime(current_date)
                    d_orig = pd.to_datetime(orig_sig_date)
                    scored["days_elapsed"] = max(0, int((d_cur - d_orig).days))
                except Exception:
                    scored["days_elapsed"] = 0

                # Recompute outcome against original triggers
                trig = scored.get("breakout_trigger")
                targ = scored.get("target_price")
                stop = scored.get("stop_loss")

                if targ and current_price >= targ:
                    scored["outcome"] = "TARGET_HIT"
                    scored["outcome_label"] = "🎯 Target Reached"
                    scored["outcome_badge"] = "emerald"
                    scored["breakout_happened"] = 1
                elif stop and current_price <= stop:
                    scored["outcome"] = "STOP_HIT"
                    scored["outcome_label"] = "🛑 Invalidation Triggered"
                    scored["outcome_badge"] = "rose"
                    scored["breakout_happened"] = 0
                elif trig and current_price >= trig * 1.0015:
                    scored["outcome"] = "TRIGGERED"
                    scored["outcome_label"] = "🚀 Breakout Active"
                    scored["outcome_badge"] = "blue"
                    scored["breakout_happened"] = 1
                else:
                    scored["outcome"] = "ACTIVE"
                    scored["outcome_label"] = "⏳ Approaching Trigger"
                    scored["outcome_badge"] = "amber"
                    scored["breakout_happened"] = 0

    # Setup Conviction Tier
    comp_score = scored.get("composite_score", 0)
    if _should_be_hot(scored):
        tier = "HOT"
        tier_label = "🔥 Hot Momentum Setup"
        tier_badge = "emerald"
    elif comp_score >= WARM_THRESHOLD:
        tier = "WARM"
        tier_label = "⚡ Coiling / Approaching Trigger"
        tier_badge = "amber"
    else:
        tier = "COLD"
        tier_label = "💤 Low Momentum / Dormant"
        tier_badge = "slate"

    scored["tier"] = tier
    scored["tier_label"] = tier_label
    scored["tier_badge"] = tier_badge

    # Update active scan pools with freshest calculation using multi-strategy key
    key = f"{sym}::{strat_clean}"
    if force_tier and force_tier.lower() == "hot":
        _pool["hot"][key] = {"result": scored, "consecutive_low": 0}
        _pool["warm"].pop(key, None)
    elif force_tier and force_tier.lower() == "warm":
        _pool["warm"][key] = {"result": scored, "consecutive_low": 0}
        _pool["hot"].pop(key, None)
    elif key in _pool["hot"]:
        _pool["hot"][key]["result"] = scored
        _pool["hot"][key]["consecutive_low"] = 0
    elif key in _pool["warm"]:
        _pool["warm"][key]["result"] = scored
        _pool["warm"][key]["consecutive_low"] = 0
    elif comp_score >= HOT_THRESHOLD:
        _pool["hot"][key] = {"result": scored, "consecutive_low": 0}
    else:
        _pool["warm"][key] = {"result": scored, "consecutive_low": 0}

    _rebuild_candidates()
    save_breakout_pool_to_db(settings)
    return scored


def set_ticker_tier(
    ticker: str,
    tier: str,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Manually assign or promote a ticker into Hot, Warm, or Cold pool."""
    settings = settings or Settings()
    sym = (ticker or "").strip().upper()
    if not (sym.endswith(".NS") or sym.endswith(".BO") or "." in sym):
        sym = f"{sym}.NS"
    target_tier = tier.strip().lower()

    entry = _pool["hot"].get(sym) or _pool["warm"].get(sym)
    if entry:
        result = entry["result"]
    else:
        eval_res = evaluate_stock_breakout(sym, settings=settings)
        if not eval_res.get("success"):
            return {"success": False, "error": eval_res.get("error", "Failed to evaluate ticker")}
        result = eval_res

    if target_tier == "hot":
        _pool["hot"][sym] = {"result": result, "consecutive_low": 0}
        _pool["warm"].pop(sym, None)
        record_breakout_transition(
            ticker=sym,
            event_type="PROMOTED_HOT",
            from_tier="MANUAL",
            to_tier="HOT",
            score_after=result.get("composite_score"),
            price=result.get("current_price") or result.get("signal_price"),
            trigger_price=result.get("breakout_trigger"),
            target_price=result.get("target_price"),
            stop_loss=result.get("stop_loss"),
            risk_reward_ratio=result.get("risk_reward_ratio"),
            volume_ratio=result.get("volume_ratio"),
            reason="Manually assigned to HOT tier",
            company_name=result.get("company_name"),
            strategy=result.get("strategy", "Classic Technical"),
            settings=settings,
        )
    elif target_tier == "warm":
        _pool["warm"][sym] = {"result": result, "consecutive_low": 0}
        _pool["hot"].pop(sym, None)
        record_breakout_transition(
            ticker=sym,
            event_type="ADDED_WARM",
            from_tier="MANUAL",
            to_tier="WARM",
            score_after=result.get("composite_score"),
            price=result.get("current_price") or result.get("signal_price"),
            trigger_price=result.get("breakout_trigger"),
            target_price=result.get("target_price"),
            stop_loss=result.get("stop_loss"),
            risk_reward_ratio=result.get("risk_reward_ratio"),
            volume_ratio=result.get("volume_ratio"),
            reason="Manually assigned to WARM tier",
            company_name=result.get("company_name"),
            strategy=result.get("strategy", "Classic Technical"),
            settings=settings,
        )
    elif target_tier == "cold":
        _pool["hot"].pop(sym, None)
        _pool["warm"].pop(sym, None)
        record_breakout_transition(
            ticker=sym,
            event_type="REMOVED_COLD",
            from_tier="MANUAL",
            to_tier="COLD",
            score_after=result.get("composite_score"),
            price=result.get("current_price") or result.get("signal_price"),
            trigger_price=result.get("breakout_trigger"),
            reason="Manually demoted to COLD tier",
            company_name=result.get("company_name"),
            strategy=result.get("strategy", "Classic Technical"),
            settings=settings,
            send_email=False,
        )
    else:
        return {"success": False, "error": f"Invalid tier '{tier}'. Must be 'hot', 'warm', or 'cold'."}

    _rebuild_candidates()
    save_breakout_pool_to_db(settings)
    return {
        "success": True,
        "ticker": sym,
        "tier": target_tier.upper(),
        "hot_count": len(_pool["hot"]),
        "warm_count": len(_pool["warm"]),
        "candidate": result,
    }


def search_breakout_tickers(
    query: str,
    limit: int = 15,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """Fast auto-complete lookup for stocks across price cache and universe registry."""
    settings = settings or Settings()
    q = (query or "").strip().upper()
    if not q:
        return []

    results: list[dict[str, Any]] = []
    seen: set[str] = set()

    try:
        conn = get_db_connection(settings)
        # 1. Search in tickers table
        rows = conn.execute(
            """
            SELECT ticker, name, sector, industry
            FROM tickers
            WHERE ticker LIKE ? OR name LIKE ?
            ORDER BY CASE WHEN ticker LIKE ? THEN 1 WHEN ticker LIKE ? THEN 2 ELSE 3 END, ticker
            LIMIT ?
            """,
            (f"{q}%", f"%{q}%", f"{q}", f"{q}%", limit),
        ).fetchall()

        for r in rows:
            sym = r[0].upper()
            if sym not in seen:
                seen.add(sym)
                market = "NSE" if sym.endswith(".NS") else ("BSE" if sym.endswith(".BO") else "US")
                results.append({
                    "symbol": sym,
                    "name": r[1] or sym.replace(".NS", ""),
                    "market": market,
                    "sector": r[2] or "Equities",
                })
    except Exception as e:
        logger.debug("[BREAKOUT-SEARCH] Tickers table search error: %s", e)

    # 2. Fallback: Search distinct tickers in price_history or universes if needed
    if len(results) < limit:
        try:
            conn = get_db_connection(settings)
            more_rows = conn.execute(
                """
                SELECT DISTINCT ticker
                FROM price_history
                WHERE ticker LIKE ?
                LIMIT ?
                """,
                (f"%{q}%", limit - len(results)),
            ).fetchall()
            for r in more_rows:
                sym = r[0].upper()
                if sym not in seen:
                    seen.add(sym)
                    market = "NSE" if sym.endswith(".NS") else ("BSE" if sym.endswith(".BO") else "US")
                    results.append({
                        "symbol": sym,
                        "name": sym.replace(".NS", ""),
                        "market": market,
                        "sector": "Equities",
                    })
        except Exception as e:
            logger.debug("[BREAKOUT-SEARCH] Price history search error: %s", e)

    return results[:limit]
