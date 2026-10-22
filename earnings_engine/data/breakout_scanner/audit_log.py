"""Audit logging and transition history tracking for Breakout Radar."""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any

from earnings_engine.config import Settings
from earnings_engine.data.breakout_scanner.constants import (
    HOT_THRESHOLD,
    WARM_THRESHOLD,
)
from earnings_engine.data.breakout_scanner.state import (
    _pool,
    _pool_key,
)
from earnings_engine.data.db import get_db_connection
from earnings_engine.data.breakout_scanner.indicators import compute_technical_decision_metrics

logger = logging.getLogger(__name__)


def record_breakout_transition(
    ticker: str,
    event_type: str,
    from_tier: str,
    to_tier: str,
    score_before: float | None = None,
    score_after: float | None = None,
    price: float | None = None,
    trigger_price: float | None = None,
    target_price: float | None = None,
    stop_loss: float | None = None,
    risk_reward_ratio: float | None = None,
    volume_ratio: float | None = None,
    reason: str = "",
    catalyst_impact: str | None = None,
    company_name: str | None = None,
    strategy: str | None = "Classic Technical",
    technical_data: dict[str, Any] | None = None,
    settings: Settings | None = None,
    send_email: bool = True,
    sync_email: bool = False,
) -> None:
    """Record an audit trail event explaining why a stock moved in, out, or between breakout tiers.

    If the incoming event matches the immediately preceding transition for this ticker and strategy,
    it increments an occurrence counter instead of inserting redundant duplicate rows.
    When a new breakout transition into HOT or WARM is recorded, automatically dispatches an alert email
    to the configured notification recipients.
    """
    settings = settings or Settings()
    try:
        from earnings_engine.data.migrations import apply_migrations
        apply_migrations(settings)
        conn = get_db_connection(settings)
        now_iso = datetime.now(timezone.utc).isoformat()
        if not company_name:
            from earnings_engine.data.names import get_name
            company_name = get_name(ticker) or ticker.replace(".NS", "")

        strat_name = (strategy or "Classic Technical").strip()
        if strat_name.upper() in ("CLASSIC_TECHNICAL", "CLASSIC TECHNICAL"):
            strat_name = "Classic Technical"
        elif strat_name.upper() in ("NSE_DELIVERY_ABSORPTION", "NSE DELIVERY"):
            strat_name = "NSE Delivery"
        elif strat_name.upper() in ("NSE_FO_CALL_WALL", "NSE CALL OI WALL"):
            strat_name = "NSE Call OI Wall"
        elif strat_name.upper() in ("VOLUME_PROFILE_VAH", "VOLUME PROFILE VAH"):
            strat_name = "Volume Profile VAH"
        elif strat_name.upper() in ("DONCHIAN_TTM_SQUEEZE", "DONCHIAN SQUEEZE"):
            strat_name = "Donchian Squeeze"

        # Check last recorded transition for this ticker and strategy
        cur = conn.execute(
            """
            SELECT id, event_type, from_tier, to_tier, strategy, counter
            FROM breakout_audit_log
            WHERE ticker = ? AND strategy = ?
            ORDER BY id DESC LIMIT 1
            """,
            (ticker, strat_name),
        )
        row = cur.fetchone()

        # Deduplication condition
        if (
            row
            and row[1] == event_type
            and (row[2] or "").upper() == from_tier.upper()
            and (row[3] or "").upper() == to_tier.upper()
        ):
            last_id = row[0]
            conn.execute(
                """
                UPDATE breakout_audit_log
                SET counter = counter + 1,
                    score_after = COALESCE(?, score_after),
                    price = COALESCE(?, price),
                    trigger_price = COALESCE(?, trigger_price),
                    reason = COALESCE(?, reason),
                    catalyst_impact = COALESCE(?, catalyst_impact),
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    round(float(score_after), 1) if score_after is not None else None,
                    round(float(price), 2) if price is not None else None,
                    round(float(trigger_price), 2) if trigger_price is not None else None,
                    reason if reason else None,
                    catalyst_impact if catalyst_impact else None,
                    now_iso,
                    last_id,
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO breakout_audit_log (
                    ticker, company_name, event_type, from_tier, to_tier,
                    score_before, score_after, price, trigger_price,
                    reason, catalyst_impact, strategy, counter, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                """,
                (
                    ticker,
                    company_name,
                    event_type,
                    from_tier.upper(),
                    to_tier.upper(),
                    round(float(score_before), 1) if score_before is not None else None,
                    round(float(score_after), 1) if score_after is not None else None,
                    round(float(price), 2) if price is not None else None,
                    round(float(trigger_price), 2) if trigger_price is not None else None,
                    reason,
                    catalyst_impact,
                    strat_name,
                    now_iso,
                    now_iso,
                ),
            )

            # Dispatch breakout notification email for newly recorded breakout setups
            if send_email and (
                to_tier.upper() in ("HOT", "WARM")
                or event_type.upper() in ("PROMOTED_HOT", "ADDED_WARM", "BREAKOUT_TRIGGERED", "BREAKOUT_CONFIRMED")
            ):
                try:
                    p_key = _pool_key(ticker, strat_name)
                    pool_cand = (
                        _pool.get("hot", {}).get(p_key, {}).get("result")
                        or _pool.get("warm", {}).get(p_key, {}).get("result")
                        or _pool.get("hot", {}).get(ticker, {}).get("result")
                        or _pool.get("warm", {}).get(ticker, {}).get("result")
                    )

                    final_target = target_price or (pool_cand.get("target_price") if pool_cand else None)
                    final_stop = stop_loss or (pool_cand.get("stop_loss") if pool_cand else None)
                    final_rr = risk_reward_ratio or (pool_cand.get("risk_reward_ratio") if pool_cand else None)
                    final_vol = volume_ratio or (pool_cand.get("volume_ratio") if pool_cand else None)
                    final_price = price or (pool_cand.get("current_price") or pool_cand.get("signal_price") if pool_cand else None)
                    final_trigger = trigger_price or (pool_cand.get("breakout_trigger") if pool_cand else None)
                    final_score = score_after if score_after is not None else (pool_cand.get("composite_score") if pool_cand else None)

                    if final_price and final_price > 0:
                        if not final_target:
                            final_target = round(final_price * 1.08, 2)
                        if not final_stop:
                            final_stop = round(final_price * 0.96, 2)
                        if not final_rr and (final_price - final_stop) > 0:
                            final_rr = round((final_target - final_price) / (final_price - final_stop), 2)

                    from earnings_engine.emailing import send_breakout_alert_email
                    tech_metrics = technical_data
                    if tech_metrics is None:
                        try:
                            tech_metrics = compute_technical_decision_metrics(ticker, settings=settings)
                        except Exception as tech_err:
                            logger.debug("[BREAKOUT-ALERT-EMAIL] Failed enriching technical metrics for %s: %s", ticker, tech_err)
                            tech_metrics = None

                    send_breakout_alert_email(
                        ticker=ticker,
                        company_name=company_name,
                        tier=to_tier.upper(),
                        strategy=strat_name,
                        score=final_score or 0.0,
                        current_price=final_price,
                        trigger_price=final_trigger,
                        target_price=final_target,
                        stop_loss=final_stop,
                        risk_reward_ratio=final_rr,
                        volume_ratio=final_vol,
                        reason=reason,
                        catalyst_impact=catalyst_impact,
                        technical_data=tech_metrics,
                        sync=sync_email,
                    )
                except Exception as mail_err:
                    logger.debug("[BREAKOUT-ALERT-EMAIL] Failed dispatching breakout alert email for %s: %s", ticker, mail_err)

        if hasattr(conn, "commit"):
            conn.commit()
    except Exception as e:
        logger.debug("[BREAKOUT-AUDIT] Failed recording transition for %s: %s", ticker, e)


def get_breakout_audit_log(
    ticker: str | None = None,
    limit: int = 50,
    strategy: str | None = None,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """Query recent breakout movement audit log entries with formatted explanations."""
    settings = settings or Settings()
    logs: list[dict[str, Any]] = []
    try:
        from earnings_engine.data.migrations import apply_migrations
        apply_migrations(settings)
        conn = get_db_connection(settings)
        wheres: list[str] = []
        params: list[Any] = []
        if ticker:
            sym = ticker.strip().upper()
            if not (sym.endswith(".NS") or sym.endswith(".BO") or "." in sym):
                sym = f"{sym}.NS"
            wheres.append("ticker = ?")
            params.append(sym)
        else:
            wheres.append("UPPER(ticker) NOT LIKE '%TEST%' AND UPPER(ticker) NOT LIKE '%MOCK%' AND UPPER(ticker) NOT LIKE '%DUMMY%'")
        if strategy and strategy.upper() not in ("ALL", "*"):
            wheres.append("(UPPER(strategy) = ? OR UPPER(strategy) = ?)")
            params.extend([strategy.upper(), strategy.replace("_", " ").upper()])

        query = f"""
            SELECT id, ticker, company_name, event_type, from_tier, to_tier,
                   score_before, score_after, price, trigger_price,
                   reason, catalyst_impact, created_at, strategy, counter, updated_at
            FROM breakout_audit_log
            WHERE {' AND '.join(wheres)}
            ORDER BY id DESC LIMIT ?
        """
        params.append(limit)
        rows = conn.execute(query, params).fetchall()

        for r in rows:
            logs.append({
                "id": r[0],
                "ticker": r[1],
                "company_name": r[2] or r[1].replace(".NS", ""),
                "event_type": r[3],
                "from_tier": r[4],
                "to_tier": r[5],
                "score_before": r[6],
                "score_after": r[7],
                "price": r[8],
                "trigger_price": r[9],
                "reason": r[10] or "Automated multi-factor evaluation",
                "catalyst_impact": r[11],
                "created_at": r[12],
                "strategy": r[13] or "Classic Technical",
                "counter": r[14] or 1,
                "updated_at": r[15] or r[12],
            })
    except Exception as e:
        logger.warning("[BREAKOUT-AUDIT] Failed querying audit log: %s", e)
    return logs


def get_breakout_audit_log_count(
    ticker: str | None = None,
    strategy: str | None = None,
    settings: Settings | None = None,
) -> int:
    """Return total count of breakout movement audit log entries matching filters."""
    settings = settings or Settings()
    total = 0
    try:
        from earnings_engine.data.migrations import apply_migrations
        apply_migrations(settings)
        conn = get_db_connection(settings)
        wheres: list[str] = []
        params: list[Any] = []
        if ticker:
            sym = ticker.strip().upper()
            if not (sym.endswith(".NS") or sym.endswith(".BO") or "." in sym):
                sym = f"{sym}.NS"
            wheres.append("ticker = ?")
            params.append(sym)
        else:
            wheres.append("UPPER(ticker) NOT LIKE '%TEST%' AND UPPER(ticker) NOT LIKE '%MOCK%' AND UPPER(ticker) NOT LIKE '%DUMMY%'")
        if strategy and strategy.upper() not in ("ALL", "*"):
            wheres.append("(UPPER(strategy) = ? OR UPPER(strategy) = ?)")
            params.extend([strategy.upper(), strategy.replace("_", " ").upper()])

        where_clause = f"WHERE {' AND '.join(wheres)}" if wheres else ""
        row = conn.execute(f"SELECT COUNT(*) FROM breakout_audit_log {where_clause}", tuple(params)).fetchone()
        if row and row[0] is not None:
            total = int(row[0])
    except Exception as e:
        logger.warning("[BREAKOUT-AUDIT] Failed counting audit log: %s", e)
    return total


def get_breakout_audit_summary_stats(
    strategy: str | None = None,
    settings: Settings | None = None,
) -> dict[str, int]:
    """Return aggregated transition totals (Cold->Hot, Cold->Warm, Warm->Hot, Exits, Total)."""
    settings = settings or Settings()
    summary = {
        "total_events": 0,
        "cold_to_hot": 0,
        "cold_to_warm": 0,
        "warm_to_hot": 0,
        "hot_to_cold": 0,
        "warm_to_cold": 0,
        "exits": 0,
    }
    try:
        from earnings_engine.data.migrations import apply_migrations
        apply_migrations(settings)
        conn = get_db_connection(settings)
        wheres: list[str] = [
            "UPPER(ticker) NOT LIKE '%TEST%' AND UPPER(ticker) NOT LIKE '%MOCK%' AND UPPER(ticker) NOT LIKE '%DUMMY%'"
        ]
        params: list[Any] = []
        if strategy and strategy.upper() not in ("ALL", "*"):
            wheres.append("(UPPER(strategy) = ? OR UPPER(strategy) = ?)")
            params.extend([strategy.upper(), strategy.replace("_", " ").upper()])

        where_clause = f"WHERE {' AND '.join(wheres)}"
        sql = f"""
            SELECT
                COUNT(*) as total_events,
                SUM(CASE WHEN from_tier = 'COLD' AND to_tier = 'HOT' THEN 1 ELSE 0 END) as cold_to_hot,
                SUM(CASE WHEN from_tier = 'COLD' AND to_tier = 'WARM' THEN 1 ELSE 0 END) as cold_to_warm,
                SUM(CASE WHEN from_tier = 'WARM' AND to_tier = 'HOT' THEN 1 ELSE 0 END) as warm_to_hot,
                SUM(CASE WHEN from_tier = 'HOT' AND to_tier = 'COLD' THEN 1 ELSE 0 END) as hot_to_cold,
                SUM(CASE WHEN from_tier = 'WARM' AND to_tier = 'COLD' THEN 1 ELSE 0 END) as warm_to_cold,
                SUM(CASE WHEN to_tier = 'COLD' THEN 1 ELSE 0 END) as exits
            FROM breakout_audit_log
            {where_clause}
        """
        row = conn.execute(sql, tuple(params)).fetchone()
        if row:
            summary["total_events"] = int(row[0] or 0)
            summary["cold_to_hot"] = int(row[1] or 0)
            summary["cold_to_warm"] = int(row[2] or 0)
            summary["warm_to_hot"] = int(row[3] or 0)
            summary["hot_to_cold"] = int(row[4] or 0)
            summary["warm_to_cold"] = int(row[5] or 0)
            summary["exits"] = int(row[6] or 0)
    except Exception as e:
        logger.warning("[BREAKOUT-AUDIT] Failed querying audit summary stats: %s", e)
    return summary


def prune_breakout_audit_log(days: int = 30, settings: Settings | None = None) -> int:
    """Prune breakout audit log entries older than N days (default 30d)."""
    settings = settings or Settings()
    deleted = 0
    conn = None
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        cutoff_iso = cutoff.isoformat()
        conn = get_db_connection(settings)
        cur = conn.execute(
            """
            DELETE FROM breakout_audit_log
            WHERE replace(created_at, 'T', ' ') < replace(?, 'T', ' ')
            """,
            (cutoff_iso,),
        )
        deleted = cur.rowcount if cur and cur.rowcount is not None else 0
        if hasattr(conn, "commit"):
            conn.commit()
        if deleted > 0:
            logger.info("[BREAKOUT-AUDIT] Pruned %d records older than %d days (%s)", deleted, days, cutoff_iso[:10])
    except Exception as e:
        logger.warning("[BREAKOUT-AUDIT] Failed pruning audit log: %s", e)
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
    return deleted
