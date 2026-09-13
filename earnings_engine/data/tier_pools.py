"""Universal Tier & Pool Management Engine Plugin (Hot / Warm / Cold Bucketing).

Standardizes multi-speed graduated pool scanning, score-based conviction tiering,
2-strike hysteresis demotion, state transition auditing, and database persistence
across any market scanner (Breakout Radar, Swing Ranges, Tri-Confluence, etc.).
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection
from earnings_engine.logging_utils import get_logger

logger = get_logger("earnings_engine.data.tier_pools")


@dataclass(frozen=True)
class TierPoolConfig:
    """Configuration schema for a domain-specific Tier Pool Manager instance."""

    domain: str
    hot_threshold: float = 60.0
    warm_threshold: float = 25.0
    hot_demotion_threshold: float = 45.0
    warm_demotion_threshold: float = 15.0
    demotion_strikes: int = 2
    max_candidates: int = 100
    min_score: float = 20.0

    # DB Persistence
    table_name: str | None = None
    audit_table_name: str = "strategy_tier_audit_log"

    # Custom Qualifier & Guard Callables
    custom_hot_qualifier: Callable[[dict[str, Any]], bool] | None = None
    custom_warm_qualifier: Callable[[dict[str, Any]], bool] | None = None
    custom_hot_demotion_guard: Callable[[dict[str, Any]], bool] | None = None
    custom_warm_demotion_guard: Callable[[dict[str, Any]], bool] | None = None

    # Key & Event Hooks
    key_builder: Callable[[str, str | None], str] | None = None
    on_transition: Callable[[dict[str, Any]], None] | None = None


@dataclass
class PoolEntry:
    """Represents a single tracked ticker in an active pool tier."""

    result: dict[str, Any]
    consecutive_low: int = 0
    tier: str = "WARM"
    first_seen_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_scored_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def __setitem__(self, key: str, value: Any) -> None:
        setattr(self, key, value)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)


class TierPoolManager:
    """Universal state machine and lifecycle manager for Hot / Warm / Cold tier pools."""

    def __init__(self, config: TierPoolConfig):
        self.cfg = config
        self._pool: dict[str, Any] = {
            "hot": {},  # key -> PoolEntry
            "warm": {},  # key -> PoolEntry
            "candidates": [],
            "last_cold_scan_at": None,
            "last_warm_scan_at": None,
            "last_hot_scan_at": None,
            "last_scan_at": None,
            "last_scan_duration_s": 0.0,
            "cold_tickers_scanned": 0,
            "hot_count": 0,
            "warm_count": 0,
            "status": "idle",
            "error": None,
        }
        self._lock = asyncio.Lock()

    def get_pool_key(self, ticker: str, strategy: str | None = None) -> str:
        """Derive the unique pool key for a ticker/strategy tuple."""
        if self.cfg.key_builder:
            return self.cfg.key_builder(ticker, strategy)
        if strategy and strategy.upper() != "DEFAULT":
            return f"{ticker}::{strategy}"
        return ticker

    def evaluate_tier(self, candidate: dict[str, Any]) -> str:
        """Determine whether a candidate qualifies for HOT, WARM, or COLD."""
        score = float(candidate.get("composite_score", candidate.get("score", 0)) or 0)

        # 1. Custom Hot Qualifier hook or Hot score threshold
        if self.cfg.custom_hot_qualifier:
            if self.cfg.custom_hot_qualifier(candidate):
                return "HOT"
        elif score >= self.cfg.hot_threshold:
            return "HOT"

        # 2. Custom Warm Qualifier hook or Warm score threshold
        if self.cfg.custom_warm_qualifier:
            if self.cfg.custom_warm_qualifier(candidate):
                return "WARM"
        elif score >= self.cfg.warm_threshold:
            return "WARM"

        return "COLD"

    def record_transition(
        self,
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
        strategy: str | None = None,
        settings: Settings | None = None,
    ) -> None:
        """Persist a state transition event with deduplication counting and alert hooks."""
        settings = settings or Settings()
        now_iso = datetime.now(timezone.utc).isoformat()
        strat = strategy or "DEFAULT"

        try:
            conn = get_db_connection(settings)
            tbl = self.cfg.audit_table_name

            # Check for immediate previous duplicate transition to increment counter
            last_row = conn.execute(
                f"""
                SELECT id, from_tier, to_tier, score_after, event_type, counter
                FROM {tbl}
                WHERE domain = ? AND ticker = ? AND strategy = ?
                ORDER BY id DESC LIMIT 1
                """,
                (self.cfg.domain, ticker, strat),
            ).fetchone()

            is_duplicate = False
            if last_row:
                l_from = str(last_row[1] or "").upper()
                l_to = str(last_row[2] or "").upper()
                l_ev = str(last_row[4] or "").upper()
                if l_from == from_tier.upper() and l_to == to_tier.upper() and l_ev == event_type.upper():
                    is_duplicate = True

            if is_duplicate and last_row:
                last_id = last_row[0]
                curr_count = (int(last_row[5]) if last_row[5] is not None else 1) + 1
                conn.execute(
                    f"""
                    UPDATE {tbl}
                    SET counter = ?,
                        score_after = COALESCE(?, score_after),
                        price = COALESCE(?, price),
                        trigger_price = COALESCE(?, trigger_price),
                        target_price = COALESCE(?, target_price),
                        stop_loss = COALESCE(?, stop_loss),
                        risk_reward_ratio = COALESCE(?, risk_reward_ratio),
                        volume_ratio = COALESCE(?, volume_ratio),
                        reason = COALESCE(?, reason),
                        catalyst_impact = COALESCE(?, catalyst_impact),
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        curr_count,
                        round(float(score_after), 1) if score_after is not None else None,
                        round(float(price), 2) if price is not None else None,
                        round(float(trigger_price), 2) if trigger_price is not None else None,
                        round(float(target_price), 2) if target_price is not None else None,
                        round(float(stop_loss), 2) if stop_loss is not None else None,
                        round(float(risk_reward_ratio), 2) if risk_reward_ratio is not None else None,
                        round(float(volume_ratio), 2) if volume_ratio is not None else None,
                        reason if reason else None,
                        catalyst_impact if catalyst_impact else None,
                        now_iso,
                        last_id,
                    ),
                )
            else:
                conn.execute(
                    f"""
                    INSERT INTO {tbl} (
                        domain, ticker, company_name, strategy, event_type, from_tier, to_tier,
                        score_before, score_after, price, trigger_price, target_price, stop_loss,
                        risk_reward_ratio, volume_ratio, reason, catalyst_impact, counter, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                    """,
                    (
                        self.cfg.domain,
                        ticker,
                        company_name,
                        strat,
                        event_type,
                        from_tier.upper(),
                        to_tier.upper(),
                        round(float(score_before), 1) if score_before is not None else None,
                        round(float(score_after), 1) if score_after is not None else None,
                        round(float(price), 2) if price is not None else None,
                        round(float(trigger_price), 2) if trigger_price is not None else None,
                        round(float(target_price), 2) if target_price is not None else None,
                        round(float(stop_loss), 2) if stop_loss is not None else None,
                        round(float(risk_reward_ratio), 2) if risk_reward_ratio is not None else None,
                        round(float(volume_ratio), 2) if volume_ratio is not None else None,
                        reason,
                        catalyst_impact,
                        now_iso,
                        now_iso,
                    ),
                )

            if hasattr(conn, "commit"):
                conn.commit()

            # Execute optional transition hook (e.g. email or webhook dispatch)
            if self.cfg.on_transition:
                try:
                    payload = {
                        "domain": self.cfg.domain,
                        "ticker": ticker,
                        "event_type": event_type,
                        "from_tier": from_tier,
                        "to_tier": to_tier,
                        "score": score_after,
                        "price": price,
                        "reason": reason,
                        "strategy": strat,
                    }
                    self.cfg.on_transition(payload)
                except Exception as hook_err:
                    logger.warning("[%s-HOOK] Transition hook error: %s", self.cfg.domain.upper(), hook_err)

        except Exception as e:
            logger.warning("[%s-AUDIT] Failed recording transition for %s: %s", self.cfg.domain.upper(), ticker, e)

    def promote_or_update(
        self,
        candidate: dict[str, Any],
        settings: Settings | None = None,
        force_tier: str | None = None,
    ) -> str:
        """Promote, demote, or refresh a candidate inside the in-memory pool and log transitions."""
        ticker = str(candidate.get("ticker", "")).strip().upper()
        if not ticker:
            return "COLD"

        strat = candidate.get("strategy") or "DEFAULT"
        key = self.get_pool_key(ticker, strat)
        score = float(candidate.get("composite_score", candidate.get("score", 0)) or 0)
        target_tier = force_tier.upper() if force_tier else self.evaluate_tier(candidate)

        candidate["tier"] = target_tier
        was_hot = key in self._pool["hot"]
        was_warm = key in self._pool["warm"]
        prev_tier = "HOT" if was_hot else ("WARM" if was_warm else "COLD")

        now_iso = datetime.now(timezone.utc).isoformat()

        if target_tier == "HOT":
            self._pool["hot"][key] = PoolEntry(result=candidate, consecutive_low=0, tier="HOT", last_scored_at=now_iso)
            self._pool["warm"].pop(key, None)

            if prev_tier != "HOT":
                reason = f"Promoted to HOT ({strat}): Score {score:.1f} qualified for high conviction tier"
                self.record_transition(
                    ticker=ticker,
                    event_type="PROMOTED_HOT",
                    from_tier=prev_tier,
                    to_tier="HOT",
                    score_after=score,
                    price=candidate.get("current_price") or candidate.get("price"),
                    trigger_price=candidate.get("breakout_trigger") or candidate.get("trigger_price"),
                    target_price=candidate.get("target_price"),
                    stop_loss=candidate.get("stop_loss"),
                    risk_reward_ratio=candidate.get("risk_reward_ratio"),
                    volume_ratio=candidate.get("volume_ratio"),
                    reason=reason,
                    company_name=candidate.get("company_name"),
                    strategy=strat,
                    settings=settings,
                )

        elif target_tier == "WARM":
            if not was_hot or force_tier:
                self._pool["warm"][key] = PoolEntry(result=candidate, consecutive_low=0, tier="WARM", last_scored_at=now_iso)
                self._pool["hot"].pop(key, None)

                if prev_tier == "COLD":
                    reason = f"Added to WARM ({strat}): Compression setup with score {score:.1f}"
                    self.record_transition(
                        ticker=ticker,
                        event_type="ADDED_WARM",
                        from_tier="COLD",
                        to_tier="WARM",
                        score_after=score,
                        price=candidate.get("current_price") or candidate.get("price"),
                        trigger_price=candidate.get("breakout_trigger") or candidate.get("trigger_price"),
                        target_price=candidate.get("target_price"),
                        stop_loss=candidate.get("stop_loss"),
                        risk_reward_ratio=candidate.get("risk_reward_ratio"),
                        volume_ratio=candidate.get("volume_ratio"),
                        reason=reason,
                        company_name=candidate.get("company_name"),
                        strategy=strat,
                        settings=settings,
                    )
        else:
            # Demoted to COLD
            if was_hot or was_warm:
                self._pool["hot"].pop(key, None)
                self._pool["warm"].pop(key, None)
                self.record_transition(
                    ticker=ticker,
                    event_type="REMOVED_COLD",
                    from_tier=prev_tier,
                    to_tier="COLD",
                    score_after=score,
                    price=candidate.get("current_price") or candidate.get("price"),
                    reason=f"Removed to COLD ({strat}): Score {score:.1f} dropped below warm threshold",
                    company_name=candidate.get("company_name"),
                    strategy=strat,
                    settings=settings,
                )

        self._rebuild_candidates()
        return target_tier

    def check_hot_demotion(
        self,
        key: str,
        updated_result: dict[str, Any],
        settings: Settings | None = None,
    ) -> str:
        """Apply 2-strike hysteresis on Hot candidates before demoting."""
        entry: PoolEntry | None = self._pool["hot"].get(key)
        if not entry:
            return "COLD"

        score = float(updated_result.get("composite_score", updated_result.get("score", 0)) or 0)
        is_guarded = False
        if self.cfg.custom_hot_demotion_guard:
            is_guarded = self.cfg.custom_hot_demotion_guard(updated_result)

        if score >= self.cfg.hot_demotion_threshold or is_guarded:
            entry.consecutive_low = 0
            entry.result = updated_result
            return "HOT"

        entry.consecutive_low += 1
        if entry.consecutive_low >= self.cfg.demotion_strikes:
            del self._pool["hot"][key]
            ticker = str(updated_result.get("ticker", key.split("::")[0]))
            strat = updated_result.get("strategy") or (key.split("::")[1] if "::" in key else "DEFAULT")

            if score >= self.cfg.warm_threshold:
                self._pool["warm"][key] = PoolEntry(result=updated_result, consecutive_low=0, tier="WARM")
                self.record_transition(
                    ticker=ticker,
                    event_type="DEMOTED_WARM",
                    from_tier="HOT",
                    to_tier="WARM",
                    score_after=score,
                    price=updated_result.get("current_price") or updated_result.get("price"),
                    reason=f"Demoted HOT ➔ WARM: Score dropped to {score:.1f} for {self.cfg.demotion_strikes} consecutive cycles",
                    strategy=strat,
                    settings=settings,
                )
                self._rebuild_candidates()
                return "WARM"
            else:
                self.record_transition(
                    ticker=ticker,
                    event_type="REMOVED_COLD",
                    from_tier="HOT",
                    to_tier="COLD",
                    score_after=score,
                    price=updated_result.get("current_price") or updated_result.get("price"),
                    reason=f"Removed HOT ➔ COLD: Score dropped to {score:.1f} for {self.cfg.demotion_strikes} consecutive cycles",
                    strategy=strat,
                    settings=settings,
                )
                self._rebuild_candidates()
                return "COLD"

        return "HOT"

    def check_warm_demotion(
        self,
        key: str,
        updated_result: dict[str, Any],
        settings: Settings | None = None,
    ) -> str:
        """Apply 2-strike hysteresis on Warm candidates before removing to Cold."""
        entry: PoolEntry | None = self._pool["warm"].get(key)
        if not entry:
            return "COLD"

        score = float(updated_result.get("composite_score", updated_result.get("score", 0)) or 0)
        is_guarded = False
        if self.cfg.custom_warm_demotion_guard:
            is_guarded = self.cfg.custom_warm_demotion_guard(updated_result)

        if score >= self.cfg.warm_demotion_threshold or is_guarded:
            entry.consecutive_low = 0
            entry.result = updated_result
            return "WARM"

        entry.consecutive_low += 1
        if entry.consecutive_low >= self.cfg.demotion_strikes:
            del self._pool["warm"][key]
            ticker = str(updated_result.get("ticker", key.split("::")[0]))
            strat = updated_result.get("strategy") or (key.split("::")[1] if "::" in key else "DEFAULT")

            self.record_transition(
                ticker=ticker,
                event_type="REMOVED_COLD",
                from_tier="WARM",
                to_tier="COLD",
                score_after=score,
                price=updated_result.get("current_price") or updated_result.get("price"),
                reason=f"Removed WARM ➔ COLD: Score dropped to {score:.1f} for {self.cfg.demotion_strikes} consecutive cycles",
                strategy=strat,
                settings=settings,
            )
            self._rebuild_candidates()
            return "COLD"

        return "WARM"

    def _rebuild_candidates(self) -> list[dict[str, Any]]:
        """Combine Hot and Warm pools into a deduplicated, score-ranked candidate list."""
        seen: set[str] = set()
        cands: list[dict[str, Any]] = []

        # Sort Hot items first, then Warm items
        for entry in sorted(
            self._pool["hot"].values(),
            key=lambda e: float(e.result.get("composite_score", e.result.get("score", 0)) or 0),
            reverse=True,
        ):
            res = entry.result
            t = str(res.get("ticker", "")).upper()
            if t and t not in seen:
                seen.add(t)
                cands.append(res)

        for entry in sorted(
            self._pool["warm"].values(),
            key=lambda e: float(e.result.get("composite_score", e.result.get("score", 0)) or 0),
            reverse=True,
        ):
            res = entry.result
            t = str(res.get("ticker", "")).upper()
            if t and t not in seen:
                seen.add(t)
                cands.append(res)

        # Apply minimum score filter and max candidates cap
        filtered = [c for c in cands if float(c.get("composite_score", c.get("score", 0)) or 0) >= self.cfg.min_score]
        self._pool["candidates"] = filtered[: self.cfg.max_candidates]
        self._pool["hot_count"] = len(self._pool["hot"])
        self._pool["warm_count"] = len(self._pool["warm"])
        return self._pool["candidates"]

    def get_cached_results(self, tier: str | None = "ALL") -> list[dict[str, Any]]:
        """Return cached candidates filtered by tier (HOT, WARM, or ALL)."""
        target = (tier or "ALL").upper().strip()
        if target == "HOT":
            return [e.result for e in self._pool["hot"].values()]
        elif target == "WARM":
            return [e.result for e in self._pool["warm"].values()]
        return list(self._pool["candidates"])

    def get_pool_stats(self, settings: Settings | None = None) -> dict[str, Any]:
        """Query aggregate pool metrics from database or in-memory state."""
        settings = settings or Settings()
        stats = {
            "domain": self.cfg.domain,
            "hot_count": len(self._pool["hot"]),
            "warm_count": len(self._pool["warm"]),
            "total_count": len(self._pool["hot"]) + len(self._pool["warm"]),
            "last_scan_at": self._pool.get("last_scan_at"),
            "status": self._pool.get("status", "idle"),
            "strategies": {},
        }

        # If domain has dedicated DB table, fetch persistent distinct counts
        if self.cfg.table_name:
            try:
                conn = get_db_connection(settings)
                cur = conn.execute(
                    f"""
                    SELECT tier, COUNT(DISTINCT ticker)
                    FROM {self.cfg.table_name}
                    WHERE UPPER(ticker) NOT LIKE '%TEST%' AND UPPER(ticker) NOT LIKE '%MOCK%'
                    GROUP BY tier
                    """
                )
                db_hot = 0
                db_warm = 0
                for r in cur.fetchall():
                    t = str(r[0] or "").upper()
                    c = int(r[1] or 0)
                    if t == "HOT":
                        db_hot = c
                    elif t == "WARM":
                        db_warm = c
                if db_hot > 0 or db_warm > 0:
                    stats["hot_count"] = db_hot
                    stats["warm_count"] = db_warm
                    stats["total_count"] = db_hot + db_warm
            except Exception as e:
                logger.debug("[%s-STATS] DB pool count query error: %s", self.cfg.domain, e)

        return stats

    def get_audit_log(
        self,
        ticker: str | None = None,
        limit: int = 50,
        offset: int = 0,
        settings: Settings | None = None,
    ) -> dict[str, Any]:
        """Fetch historical transition event log with macro summary counts."""
        settings = settings or Settings()
        result: dict[str, Any] = {
            "domain": self.cfg.domain,
            "logs": [],
            "total_count": 0,
            "summary_stats": {
                "cold_to_hot": 0,
                "cold_to_warm": 0,
                "warm_to_hot": 0,
                "hot_to_cold": 0,
                "warm_to_cold": 0,
                "exits": 0,
            },
        }

        try:
            conn = get_db_connection(settings)
            tbl = self.cfg.audit_table_name

            params: list[Any] = [self.cfg.domain]
            where_sql = "WHERE domain = ?"
            if ticker:
                where_sql += " AND ticker = ?"
                params.append(ticker.upper())

            # 1. Total Count
            cur_count = conn.execute(f"SELECT COUNT(*) FROM {tbl} {where_sql}", params)
            result["total_count"] = cur_count.fetchone()[0] or 0

            # 2. Transition Summary
            cur_sum = conn.execute(
                f"""
                SELECT
                    SUM(CASE WHEN from_tier = 'COLD' AND to_tier = 'HOT' THEN 1 ELSE 0 END),
                    SUM(CASE WHEN from_tier = 'COLD' AND to_tier = 'WARM' THEN 1 ELSE 0 END),
                    SUM(CASE WHEN from_tier = 'WARM' AND to_tier = 'HOT' THEN 1 ELSE 0 END),
                    SUM(CASE WHEN from_tier = 'HOT' AND to_tier = 'COLD' THEN 1 ELSE 0 END),
                    SUM(CASE WHEN from_tier = 'WARM' AND to_tier = 'COLD' THEN 1 ELSE 0 END),
                    SUM(CASE WHEN to_tier = 'COLD' THEN 1 ELSE 0 END)
                FROM {tbl}
                WHERE domain = ?
                """,
                (self.cfg.domain,),
            )
            s_row = cur_sum.fetchone()
            if s_row:
                result["summary_stats"]["cold_to_hot"] = int(s_row[0] or 0)
                result["summary_stats"]["cold_to_warm"] = int(s_row[1] or 0)
                result["summary_stats"]["warm_to_hot"] = int(s_row[2] or 0)
                result["summary_stats"]["hot_to_cold"] = int(s_row[3] or 0)
                result["summary_stats"]["warm_to_cold"] = int(s_row[4] or 0)
                result["summary_stats"]["exits"] = int(s_row[5] or 0)

            # 3. Log Records
            query_params = list(params) + [limit, offset]
            cur_logs = conn.execute(
                f"""
                SELECT id, ticker, company_name, strategy, event_type, from_tier, to_tier,
                       score_before, score_after, price, trigger_price, target_price, stop_loss,
                       risk_reward_ratio, volume_ratio, reason, catalyst_impact, counter, created_at, updated_at
                FROM {tbl}
                {where_sql}
                ORDER BY id DESC
                LIMIT ? OFFSET ?
                """,
                query_params,
            )

            for r in cur_logs.fetchall():
                result["logs"].append({
                    "id": r[0],
                    "ticker": r[1],
                    "company_name": r[2],
                    "strategy": r[3],
                    "event_type": r[4],
                    "from_tier": r[5],
                    "to_tier": r[6],
                    "score_before": r[7],
                    "score_after": r[8],
                    "price": r[9],
                    "trigger_price": r[10],
                    "target_price": r[11],
                    "stop_loss": r[12],
                    "risk_reward_ratio": r[13],
                    "volume_ratio": r[14],
                    "reason": r[15],
                    "catalyst_impact": r[16],
                    "counter": r[17],
                    "created_at": r[18],
                    "updated_at": r[19],
                })

        except Exception as e:
            logger.warning("[%s-AUDIT-QUERY] Audit log fetch error: %s", self.cfg.domain, e)

        return result
