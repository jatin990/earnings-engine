"""Breakout Radar — Tiered Async Pooling Scanner & Scoring Engine.

Architecture: Three-tier graduated pool system that avoids rescanning the
entire universe every cycle.  Stocks are promoted/demoted between tiers
based on their breakout conviction score, with higher-conviction candidates
receiving more frequent rescoring.

Tiers
-----
- **T0 (Cold)** — Full universe scan every ``COLD_INTERVAL_MIN`` (default 60 min).
  Discovers new candidates and feeds them into T1/T2.
- **T1 (Warm)** — Rescored every ``WARM_INTERVAL_MIN`` (default 15 min).
  Stocks with ``composite_score ≥ WARM_THRESHOLD`` (25).
- **T2 (Hot)** — Rescored every ``HOT_INTERVAL_MIN`` (default 5 min).
  Stocks within striking distance of breakout: ``composite_score ≥ HOT_THRESHOLD``
  (50), or ``pct_from_high ≥ -5%``, or ``volume_ratio ≥ 1.5×``.

Demotion requires **two consecutive** low scores to prevent flicker from
a single noisy bar.  Volume-spike fast-tracking immediately promotes any
stock with ``volume_ratio ≥ 1.5×`` into the Hot pool.

Score Components (0 – 100)
--------------------------
1. Resistance Proximity  (0-30 pts) — price within 0-5% below the 20D / 52W high
2. Volume Surge          (0-20 pts) — today's volume vs 20D average
3. Price Compression     (0-15 pts) — ATR(14)/price squeeze (low volatility = coiling)
4. Momentum              (0-15 pts) — 30D return > 0 and price > 20D SMA
5. Fundamental Bonus     (0-20 pts) — earnings quality score (q1/q2/q3 avg, normalised)

Minimum score to appear in API results: BREAKOUT_MIN_SCORE (default 35).
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection
from earnings_engine.logging_utils import get_logger

logger = get_logger("earnings_engine.data.breakout_scanner")

# ---------------------------------------------------------------------------
# Configuration (overridable via environment variables)
# ---------------------------------------------------------------------------
BREAKOUT_MIN_SCORE: int = int(os.environ.get("BREAKOUT_MIN_SCORE", "35"))
BREAKOUT_MAX_CANDIDATES: int = int(os.environ.get("BREAKOUT_MAX_CANDIDATES", "100"))

# Tier thresholds
HOT_THRESHOLD: int = int(os.environ.get("BREAKOUT_HOT_THRESHOLD", "50"))
WARM_THRESHOLD: int = int(os.environ.get("BREAKOUT_WARM_THRESHOLD", "25"))
HOT_DEMOTION_THRESHOLD: int = int(os.environ.get("BREAKOUT_HOT_DEMOTION", "25"))
WARM_DEMOTION_THRESHOLD: int = int(os.environ.get("BREAKOUT_WARM_DEMOTION", "15"))

# Scan intervals (minutes)
COLD_INTERVAL_MIN: int = int(os.environ.get("BREAKOUT_COLD_INTERVAL_MIN", "60"))
WARM_INTERVAL_MIN: int = int(os.environ.get("BREAKOUT_WARM_INTERVAL_MIN", "15"))
HOT_INTERVAL_MIN: int = int(os.environ.get("BREAKOUT_HOT_INTERVAL_MIN", "5"))

# Legacy compat alias
BREAKOUT_SCAN_INTERVAL_MIN: int = COLD_INTERVAL_MIN

# ---------------------------------------------------------------------------
# Tiered in-memory pool
# ---------------------------------------------------------------------------
_pool: dict[str, Any] = {
    "hot": {},               # ticker → {"result": dict, "consecutive_low": 0}
    "warm": {},              # ticker → {"result": dict, "consecutive_low": 0}
    "candidates": [],        # merged sorted list for API (score ≥ BREAKOUT_MIN_SCORE)
    "last_cold_scan_at": None,
    "last_warm_scan_at": None,
    "last_hot_scan_at": None,
    "last_scan_at": None,    # most recent of any tier (compat)
    "last_scan_duration_s": 0.0,
    "cold_tickers_scanned": 0,
    "hot_count": 0,
    "warm_count": 0,
    "status": "idle",        # "idle" | "running" | "done" | "error"
    "error": None,
}

# Legacy compat alias
_cache = _pool


def _rebuild_candidates() -> None:
    """Merge hot + warm pools into a deduplicated, sorted candidates list."""
    merged: dict[str, dict] = {}
    for ticker, entry in _pool["hot"].items():
        merged[ticker] = entry["result"]
    for ticker, entry in _pool["warm"].items():
        if ticker not in merged:
            merged[ticker] = entry["result"]

    candidates = [r for r in merged.values() if r.get("composite_score", 0) >= BREAKOUT_MIN_SCORE]
    candidates.sort(key=lambda x: x.get("composite_score", 0), reverse=True)
    _pool["candidates"] = candidates[:BREAKOUT_MAX_CANDIDATES]
    _pool["hot_count"] = len(_pool["hot"])
    _pool["warm_count"] = len(_pool["warm"])


def _init_breakout_db(conn: Any) -> None:
    """Ensure breakout_radar table and performance indices exist."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS breakout_radar (
            ticker TEXT PRIMARY KEY,
            tier TEXT NOT NULL DEFAULT 'WARM',
            company_name TEXT,
            industry TEXT,
            composite_score REAL DEFAULT 0,
            resistance_score REAL DEFAULT 0,
            volume_score REAL DEFAULT 0,
            compression_score REAL DEFAULT 0,
            momentum_score REAL DEFAULT 0,
            fundamental_score REAL DEFAULT 0,
            signal_date TEXT,
            signal_price REAL,
            predicted_value REAL,
            breakout_trigger REAL,
            target_price REAL,
            stop_loss REAL,
            risk_reward_ratio REAL,
            current_price REAL,
            current_date TEXT,
            realized_return_pct REAL,
            max_gain_pct REAL,
            breakout_happened INTEGER DEFAULT 0,
            outcome TEXT DEFAULT 'ACTIVE',
            outcome_label TEXT,
            outcome_badge TEXT,
            days_elapsed INTEGER DEFAULT 0,
            setup_archetype TEXT,
            volume_ratio REAL,
            atr_pct REAL,
            pct_from_high REAL,
            avg_quality_score REAL,
            scanned_at TEXT,
            data_json TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )
        """
    )
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_breakout_tier ON breakout_radar(tier)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_breakout_score ON breakout_radar(composite_score DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_breakout_scanned_at ON breakout_radar(scanned_at DESC)")
    except Exception:
        pass


def save_breakout_pool_to_db(settings: Settings | None = None) -> None:
    """Persist current in-memory Hot, Warm, and candidate breakout setups into SQLite & Turso."""
    settings = settings or Settings()
    try:
        conn = get_db_connection(settings)
        _init_breakout_db(conn)

        records: list[dict[str, Any]] = []
        seen: set[str] = set()

        # 1. Hot pool
        for sym, entry in _pool.get("hot", {}).items():
            r = entry.get("result", {})
            if r and sym not in seen:
                seen.add(sym)
                records.append({**r, "tier": "HOT"})

        # 2. Warm pool
        for sym, entry in _pool.get("warm", {}).items():
            r = entry.get("result", {})
            if r and sym not in seen:
                seen.add(sym)
                records.append({**r, "tier": "WARM"})

        # 3. Candidates
        for r in _pool.get("candidates", []):
            sym = r.get("ticker")
            if sym and sym not in seen:
                seen.add(sym)
                records.append({**r, "tier": r.get("tier", "WARM")})

        if not records:
            return

        now_iso = datetime.now(timezone.utc).isoformat()
        rows_to_insert = []
        for r in records:
            ticker = r.get("ticker")
            if not ticker:
                continue
            sig_date = str(r.get("signal_date") or r.get("asof_date") or now_iso[:10]).strip()
            rows_to_insert.append((
                ticker,
                r.get("tier", "WARM"),
                r.get("company_name") or ticker,
                r.get("industry") or "—",
                float(r.get("composite_score", 0) or 0),
                float(r.get("resistance_score", 0) or 0),
                float(r.get("volume_score", 0) or 0),
                float(r.get("compression_score", 0) or 0),
                float(r.get("momentum_score", 0) or 0),
                float(r.get("fundamental_score", 0) or 0),
                sig_date,
                float(r["signal_price"]) if r.get("signal_price") is not None else (float(r["predicted_value"]) if r.get("predicted_value") is not None else (float(r["current_price"]) if r.get("current_price") is not None else None)),
                float(r["predicted_value"]) if r.get("predicted_value") is not None else (float(r["signal_price"]) if r.get("signal_price") is not None else (float(r["current_price"]) if r.get("current_price") is not None else None)),
                float(r.get("breakout_trigger")) if r.get("breakout_trigger") is not None else None,
                float(r.get("target_price")) if r.get("target_price") is not None else None,
                float(r.get("stop_loss")) if r.get("stop_loss") is not None else None,
                float(r.get("risk_reward_ratio")) if r.get("risk_reward_ratio") is not None else 2.0,
                float(r.get("current_price")) if r.get("current_price") is not None else None,
                str(r.get("current_date") or ""),
                float(r.get("realized_return_pct")) if r.get("realized_return_pct") is not None else 0.0,
                float(r.get("max_gain_pct")) if r.get("max_gain_pct") is not None else 0.0,
                1 if r.get("breakout_happened") else 0,
                str(r.get("outcome") or "ACTIVE"),
                str(r.get("outcome_label") or ""),
                str(r.get("outcome_badge") or ""),
                int(r.get("days_elapsed", 0) or 0),
                str(r.get("setup_archetype") or "Breakout Setup"),
                float(r.get("volume_ratio")) if r.get("volume_ratio") is not None else None,
                float(r.get("atr_pct")) if r.get("atr_pct") is not None else None,
                float(r.get("pct_from_high")) if r.get("pct_from_high") is not None else None,
                float(r.get("avg_quality_score")) if r.get("avg_quality_score") is not None else None,
                str(r.get("scanned_at") or now_iso),
                json.dumps(r, default=str),
                now_iso,
            ))

        upsert_sql = """
        INSERT INTO breakout_radar (
            ticker, tier, company_name, industry, composite_score,
            resistance_score, volume_score, compression_score, momentum_score, fundamental_score,
            signal_date, signal_price, predicted_value, breakout_trigger, target_price,
            stop_loss, risk_reward_ratio, current_price, current_date, realized_return_pct,
            max_gain_pct, breakout_happened, outcome, outcome_label, outcome_badge,
            days_elapsed, setup_archetype, volume_ratio, atr_pct, pct_from_high,
            avg_quality_score, scanned_at, data_json, updated_at
        ) VALUES (
            ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?,
            ?, ?, ?, ?
        )
        ON CONFLICT(ticker) DO UPDATE SET
            tier = excluded.tier,
            company_name = excluded.company_name,
            industry = excluded.industry,
            composite_score = excluded.composite_score,
            resistance_score = excluded.resistance_score,
            volume_score = excluded.volume_score,
            compression_score = excluded.compression_score,
            momentum_score = excluded.momentum_score,
            fundamental_score = excluded.fundamental_score,
            signal_date = excluded.signal_date,
            signal_price = excluded.signal_price,
            predicted_value = excluded.predicted_value,
            breakout_trigger = excluded.breakout_trigger,
            target_price = excluded.target_price,
            stop_loss = excluded.stop_loss,
            risk_reward_ratio = excluded.risk_reward_ratio,
            current_price = excluded.current_price,
            current_date = excluded.current_date,
            realized_return_pct = excluded.realized_return_pct,
            max_gain_pct = excluded.max_gain_pct,
            breakout_happened = excluded.breakout_happened,
            outcome = excluded.outcome,
            outcome_label = excluded.outcome_label,
            outcome_badge = excluded.outcome_badge,
            days_elapsed = excluded.days_elapsed,
            setup_archetype = excluded.setup_archetype,
            volume_ratio = excluded.volume_ratio,
            atr_pct = excluded.atr_pct,
            pct_from_high = excluded.pct_from_high,
            avg_quality_score = excluded.avg_quality_score,
            scanned_at = excluded.scanned_at,
            data_json = excluded.data_json,
            updated_at = excluded.updated_at
        """

        if hasattr(conn, "executemany"):
            conn.executemany(upsert_sql, rows_to_insert)

        # 2. Also persist / upsert to permanent historical archive: breakout_tracked_signals
        upsert_tracked_sql = """
        INSERT INTO breakout_tracked_signals (
            ticker, tier, company_name, industry, composite_score,
            resistance_score, volume_score, compression_score, momentum_score, fundamental_score,
            signal_date, signal_price, predicted_value, breakout_trigger, target_price,
            stop_loss, risk_reward_ratio, current_price, current_date, realized_return_pct,
            max_gain_pct, breakout_happened, outcome, outcome_label, outcome_badge,
            days_elapsed, setup_archetype, volume_ratio, atr_pct, pct_from_high,
            avg_quality_score, scanned_at, data_json, created_at, updated_at
        ) VALUES (
            ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?
        )
        ON CONFLICT(ticker, signal_date) DO UPDATE SET
            tier = excluded.tier,
            company_name = excluded.company_name,
            industry = excluded.industry,
            composite_score = excluded.composite_score,
            resistance_score = excluded.resistance_score,
            volume_score = excluded.volume_score,
            compression_score = excluded.compression_score,
            momentum_score = excluded.momentum_score,
            fundamental_score = excluded.fundamental_score,
            signal_price = excluded.signal_price,
            predicted_value = excluded.predicted_value,
            breakout_trigger = excluded.breakout_trigger,
            target_price = excluded.target_price,
            stop_loss = excluded.stop_loss,
            risk_reward_ratio = excluded.risk_reward_ratio,
            current_price = excluded.current_price,
            current_date = excluded.current_date,
            realized_return_pct = excluded.realized_return_pct,
            max_gain_pct = excluded.max_gain_pct,
            breakout_happened = excluded.breakout_happened,
            outcome = excluded.outcome,
            outcome_label = excluded.outcome_label,
            outcome_badge = excluded.outcome_badge,
            days_elapsed = excluded.days_elapsed,
            setup_archetype = excluded.setup_archetype,
            volume_ratio = excluded.volume_ratio,
            atr_pct = excluded.atr_pct,
            pct_from_high = excluded.pct_from_high,
            avg_quality_score = excluded.avg_quality_score,
            scanned_at = excluded.scanned_at,
            data_json = excluded.data_json,
            updated_at = excluded.updated_at
        """
        rows_for_tracked = []
        for r_tuple in rows_to_insert:
            # Tuple: ticker, tier, company_name, ..., updated_at (34 items)
            # For tracked, we need created_at and updated_at (35 items)
            # signal_date is index 10; ensure non-empty
            t_list = list(r_tuple)
            if not t_list[10]:
                t_list[10] = t_list[31][:10] if t_list[31] else now_iso[:10]
            # Add created_at, updated_at
            rows_for_tracked.append(tuple(t_list + [now_iso]))

        if hasattr(conn, "executemany"):
            try:
                conn.executemany(upsert_tracked_sql, rows_for_tracked)
            except Exception as e_track:
                logger.debug("[BREAKOUT-DB] Tracked signals archive upsert notice: %s", e_track)

        if hasattr(conn, "commit"):
            conn.commit()

        logger.debug("[BREAKOUT-DB] Persisted %d candidates to breakout_radar and breakout_tracked_signals.", len(rows_to_insert))
    except Exception as e:
        logger.warning("[BREAKOUT-DB] Failed to persist breakout pool to DB: %s", e)


def load_breakout_pool_from_db(settings: Settings | None = None) -> bool:
    """Load persisted breakout pool and candidates from SQLite / Turso database into in-memory pool."""
    settings = settings or Settings()
    try:
        conn = get_db_connection(settings)
        _init_breakout_db(conn)

        cur = conn.execute("SELECT * FROM breakout_radar ORDER BY composite_score DESC")
        rows = cur.fetchall()
        if not rows:
            return False

        hot_count = 0
        warm_count = 0
        for row in rows:
            data = None
            tier = "WARM"
            ticker = ""

            if hasattr(row, "get"):
                ticker = row.get("ticker", "")
                tier = (row.get("tier") or "WARM").upper()
                raw_json = row.get("data_json")
                if raw_json:
                    try:
                        data = json.loads(raw_json)
                    except Exception:
                        pass
                if not data:
                    data = dict(row)
            elif isinstance(row, (tuple, list)) and len(row) > 0:
                ticker = str(row[0])
                tier = str(row[1]).upper()
                if len(row) >= 33 and row[32]:
                    try:
                        data = json.loads(row[32])
                    except Exception:
                        pass
                if not data:
                    data = {"ticker": ticker, "tier": tier}

            if not data or not ticker:
                continue

            data["tier"] = tier
            if tier == "HOT":
                _pool["hot"][ticker] = {"result": data, "consecutive_low": 0}
                hot_count += 1
            else:
                _pool["warm"][ticker] = {"result": data, "consecutive_low": 0}
                warm_count += 1

        _rebuild_candidates()
        _pool["status"] = "done"
        logger.info("[BREAKOUT-DB] Loaded %d hot and %d warm candidates from database.", hot_count, warm_count)
        return True
    except Exception as e:
        logger.warning("[BREAKOUT-DB] Failed to load breakout pool from DB: %s", e)
        return False


def _should_be_hot(result: dict) -> bool:
    """Check if a scored result qualifies for the Hot pool."""
    if result.get("composite_score", 0) >= HOT_THRESHOLD:
        return True
    pct = result.get("pct_from_high")
    if pct is not None and pct >= -5:
        return True
    vol = result.get("volume_ratio")
    if vol is not None and vol >= 1.5:
        return True
    return False


def record_breakout_transition(
    ticker: str,
    event_type: str,
    from_tier: str,
    to_tier: str,
    score_before: float | None = None,
    score_after: float | None = None,
    price: float | None = None,
    trigger_price: float | None = None,
    reason: str = "",
    catalyst_impact: str | None = None,
    company_name: str | None = None,
    settings: Settings | None = None,
) -> None:
    """Record an audit trail event explaining why a stock moved in, out, or between breakout tiers."""
    settings = settings or Settings()
    try:
        from earnings_engine.data.migrations import apply_migrations
        apply_migrations(settings)
        conn = get_db_connection(settings)
        now_iso = datetime.now(timezone.utc).isoformat()
        if not company_name:
            from earnings_engine.data.names import get_name
            company_name = get_name(ticker) or ticker.replace(".NS", "")

        conn.execute(
            """
            INSERT INTO breakout_audit_log (
                ticker, company_name, event_type, from_tier, to_tier,
                score_before, score_after, price, trigger_price,
                reason, catalyst_impact, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                now_iso,
            ),
        )
        if hasattr(conn, "commit"):
            conn.commit()
    except Exception as e:
        logger.debug("[BREAKOUT-AUDIT] Failed recording transition for %s: %s", ticker, e)


def get_breakout_audit_log(
    ticker: str | None = None,
    limit: int = 50,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """Query recent breakout movement audit log entries with formatted explanations."""
    settings = settings or Settings()
    logs: list[dict[str, Any]] = []
    try:
        from earnings_engine.data.migrations import apply_migrations
        apply_migrations(settings)
        conn = get_db_connection(settings)
        if ticker:
            sym = ticker.strip().upper()
            if not (sym.endswith(".NS") or sym.endswith(".BO") or "." in sym):
                sym = f"{sym}.NS"
            rows = conn.execute(
                """
                SELECT id, ticker, company_name, event_type, from_tier, to_tier,
                       score_before, score_after, price, trigger_price,
                       reason, catalyst_impact, created_at
                FROM breakout_audit_log
                WHERE ticker = ?
                ORDER BY id DESC LIMIT ?
                """,
                (sym, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, ticker, company_name, event_type, from_tier, to_tier,
                       score_before, score_after, price, trigger_price,
                       reason, catalyst_impact, created_at
                FROM breakout_audit_log
                ORDER BY id DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()

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
            })
    except Exception as e:
        logger.warning("[BREAKOUT-AUDIT] Failed querying audit log: %s", e)
    return logs


def get_tracked_breakouts(
    days: int | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    tier: str | None = None,
    outcome: str | None = None,
    sort_by: str = "signal_date",
    limit: int = 200,
    live: bool = False,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Query permanently tracked breakout signals from breakout_tracked_signals with filtering and summary metrics."""
    settings = settings or Settings()
    try:
        from earnings_engine.data.migrations import apply_migrations
        apply_migrations(settings)
        conn = get_db_connection(settings)

        query_clauses = ["1=1"]
        params: list[Any] = []

        # 1. Date Filtering
        preset_days_int = None
        if days is not None and str(days).strip().lower() not in ("all", "all_time", "none", "", "0"):
            try:
                preset_days_int = int(days)
            except (ValueError, TypeError):
                preset_days_int = None

        if start_date and end_date:
            query_clauses.append("signal_date BETWEEN ? AND ?")
            params.extend([start_date, end_date])
        elif start_date:
            query_clauses.append("signal_date >= ?")
            params.append(start_date)
        elif end_date:
            query_clauses.append("signal_date <= ?")
            params.append(end_date)
        elif preset_days_int is not None and preset_days_int > 0:
            query_clauses.append("signal_date >= DATE('now', ?)")
            params.append(f"-{preset_days_int} days")

        # 2. Tier Filtering
        if tier and tier.upper() not in ("ALL", ""):
            query_clauses.append("UPPER(tier) = ?")
            params.append(tier.upper())

        # 3. Outcome Filtering
        if outcome and outcome.upper() not in ("ALL", ""):
            out_up = outcome.upper()
            if out_up in ("STOP_HIT", "STOP_LOSS_HIT"):
                query_clauses.append("UPPER(outcome) IN ('STOP_HIT', 'STOP_LOSS_HIT')")
            elif out_up in ("SETUP_FAILED", "BREAKOUT_FAILED"):
                query_clauses.append("UPPER(outcome) IN ('SETUP_FAILED', 'BREAKOUT_FAILED')")
            elif out_up in ("TRIGGERED", "BREAKOUT_SUCCEEDED"):
                query_clauses.append("UPPER(outcome) IN ('TRIGGERED', 'BREAKOUT_SUCCEEDED')")
            elif out_up in ("ACTIVE", "COILING_IN_PROFIT", "COILING_IN_RANGE"):
                query_clauses.append("UPPER(outcome) IN ('ACTIVE', 'COILING_IN_PROFIT', 'COILING_IN_RANGE')")
            else:
                query_clauses.append("UPPER(outcome) = ?")
                params.append(out_up)

        where_clause = " AND ".join(query_clauses)

        # 4. Sorting
        order_by = "signal_date DESC, composite_score DESC"
        if sort_by == "return_pct":
            order_by = "realized_return_pct DESC"
        elif sort_by == "max_gain":
            order_by = "max_gain_pct DESC"
        elif sort_by in ("score", "composite_score"):
            order_by = "composite_score DESC"
        elif sort_by == "days_elapsed":
            order_by = "days_elapsed ASC"
        elif sort_by == "signal_date_asc":
            order_by = "signal_date ASC"

        sql = f"""
            SELECT id, ticker, company_name, industry, tier, signal_date,
                   signal_price, predicted_value, breakout_trigger, target_price, stop_loss,
                   risk_reward_ratio, composite_score, resistance_score, volume_score, compression_score,
                   momentum_score, fundamental_score, volume_ratio, atr_pct, pct_from_high,
                   setup_archetype, current_price, current_date, realized_return_pct, max_gain_pct,
                   breakout_happened, outcome, outcome_label, outcome_badge, days_elapsed,
                   scanned_at, data_json, created_at, updated_at
            FROM breakout_tracked_signals
            WHERE {where_clause}
            ORDER BY {order_by}
            LIMIT ?
        """
        params.append(limit)

        cur = conn.execute(sql, tuple(params))
        rows = cur.fetchall()

        items: list[dict[str, Any]] = []
        for r in rows:
            raw_json = r[32]
            parsed_data = {}
            if raw_json:
                try:
                    parsed_data = json.loads(raw_json)
                except Exception:
                    pass

            item = {
                "id": r[0],
                "ticker": r[1],
                "company_name": r[2] or r[1].replace(".NS", ""),
                "industry": r[3] or "—",
                "tier": r[4],
                "signal_date": r[5],
                "signal_price": r[6],
                "predicted_value": r[7],
                "breakout_trigger": r[8],
                "target_price": r[9],
                "stop_loss": r[10],
                "risk_reward_ratio": r[11] or 2.0,
                "composite_score": r[12],
                "resistance_score": r[13],
                "volume_score": r[14],
                "compression_score": r[15],
                "momentum_score": r[16],
                "fundamental_score": r[17],
                "volume_ratio": r[18],
                "atr_pct": r[19],
                "pct_from_high": r[20],
                "setup_archetype": r[21] or "Breakout Setup",
                "current_price": r[22] or r[6],
                "current_date": r[23] or r[5],
                "realized_return_pct": r[24] or 0.0,
                "max_gain_pct": r[25] or 0.0,
                "breakout_happened": bool(r[26]),
                "outcome": r[27] or "ACTIVE",
                "outcome_label": r[28] or "Active Setup",
                "outcome_badge": r[29] or "ACTIVE",
                "days_elapsed": r[30] or 0,
                "scanned_at": r[31],
                "created_at": r[33],
                "updated_at": r[34],
            }
            if parsed_data:
                for k, v in parsed_data.items():
                    if k not in item and v is not None:
                        item[k] = v
            items.append(item)

        # 5. Optional live update
        if live and items:
            from concurrent.futures import ThreadPoolExecutor
            from earnings_engine.data.prices import fetch_prices
            import pandas as pd

            def _refresh_item(item_d: dict[str, Any]) -> None:
                t = item_d.get("ticker")
                sig_p = item_d.get("signal_price")
                trig_p = item_d.get("breakout_trigger")
                target_p = item_d.get("target_price")
                stop_p = item_d.get("stop_loss")
                sig_date = item_d.get("signal_date")

                if not t:
                    return
                try:
                    df = fetch_prices(t, settings, force=True)
                    if not df.empty and "close" in df.columns:
                        closes = pd.to_numeric(df["close"], errors="coerce").dropna()
                        if not closes.empty:
                            cur_p = round(float(closes.iloc[-1]), 2)
                            item_d["current_price"] = cur_p
                            item_d["current_date"] = str(df.index[-1])[:10]

                            if sig_p and sig_p > 0:
                                ret_pct = round(((cur_p - sig_p) / sig_p) * 100, 2)
                                item_d["realized_return_pct"] = ret_pct

                            post_high = cur_p
                            post_low = cur_p
                            if sig_date and sig_date in df.index:
                                post_df = df.loc[df.index >= sig_date]
                                if not post_df.empty:
                                    if "high" in post_df.columns:
                                        highs = pd.to_numeric(post_df["high"], errors="coerce").dropna()
                                        if not highs.empty:
                                            post_high = float(highs.max())
                                            if sig_p and sig_p > 0:
                                                max_gain = round(((post_high - sig_p) / sig_p) * 100, 2)
                                                item_d["max_gain_pct"] = max_gain
                                    if "low" in post_df.columns:
                                        lows = pd.to_numeric(post_df["low"], errors="coerce").dropna()
                                        if not lows.empty:
                                            post_low = float(lows.min())
                                    item_d["days_elapsed"] = len(post_df)

                            breakout_triggered = bool(trig_p and (cur_p >= trig_p or post_high >= trig_p))

                            if target_p and (cur_p >= target_p or post_high >= target_p):
                                item_d["outcome"] = "TARGET_HIT"
                                item_d["outcome_label"] = "Target Hit 🎯"
                                item_d["outcome_badge"] = "TARGET_HIT"
                                item_d["breakout_happened"] = True
                            elif breakout_triggered:
                                if stop_p and (cur_p <= stop_p or post_low <= stop_p):
                                    item_d["outcome"] = "STOP_HIT"
                                    item_d["outcome_label"] = "Stop Hit 🛑"
                                    item_d["outcome_badge"] = "STOP_HIT"
                                    item_d["breakout_happened"] = False
                                elif cur_p >= sig_p:
                                    item_d["outcome"] = "TRIGGERED"
                                    item_d["outcome_label"] = "Breakout Fired 🚀"
                                    item_d["outcome_badge"] = "TRIGGERED"
                                    item_d["breakout_happened"] = True
                                else:
                                    item_d["outcome"] = "BREAKOUT_RETRACED"
                                    item_d["outcome_label"] = "Breakout Retraced ⚠️"
                                    item_d["outcome_badge"] = "BREAKOUT_RETRACED"
                                    item_d["breakout_happened"] = False
                            elif stop_p and (cur_p <= stop_p or post_low <= stop_p):
                                item_d["outcome"] = "SETUP_FAILED"
                                item_d["outcome_label"] = "Setup Failed ❌"
                                item_d["outcome_badge"] = "SETUP_FAILED"
                                item_d["breakout_happened"] = False
                            else:
                                item_d["outcome"] = "ACTIVE"
                                item_d["outcome_label"] = "Active Coiling"
                                item_d["outcome_badge"] = "ACTIVE"
                except Exception as ex:
                    logger.debug("Failed refreshing tracked breakout for %s: %s", t, ex)

            with ThreadPoolExecutor(max_workers=min(10, len(items))) as pool:
                list(pool.map(_refresh_item, items))

        # 6. Summary metrics calculation
        total_tracked = len(items)
        positive_count = sum(1 for it in items if (it.get("realized_return_pct") or 0) > 0 or it.get("outcome") in ("TARGET_HIT", "TRIGGERED"))
        win_rate_pct = round((positive_count / total_tracked) * 100, 1) if total_tracked > 0 else 0.0

        all_rets = [it.get("realized_return_pct") or 0.0 for it in items]
        avg_return_pct = round(sum(all_rets) / len(all_rets), 2) if all_rets else 0.0

        best_item = max(items, key=lambda x: x.get("realized_return_pct") or -999) if items else None
        max_return_pct = best_item.get("realized_return_pct", 0.0) if best_item else 0.0
        max_return_ticker = best_item.get("ticker", "—") if best_item else "—"

        target_hit_count = sum(1 for it in items if it.get("outcome") == "TARGET_HIT")
        triggered_count = sum(1 for it in items if it.get("outcome") in ("TRIGGERED", "BREAKOUT_SUCCEEDED"))
        stop_hit_count = sum(1 for it in items if it.get("outcome") in ("STOP_HIT", "STOP_LOSS_HIT"))
        setup_failed_count = sum(1 for it in items if it.get("outcome") in ("SETUP_FAILED", "BREAKOUT_FAILED"))
        active_count = sum(1 for it in items if it.get("outcome") in ("ACTIVE", "COILING_IN_PROFIT", "COILING_IN_RANGE"))

        return {
            "success": True,
            "total_count": total_tracked,
            "timeframe": {
                "preset_days": days,
                "start_date": start_date,
                "end_date": end_date,
                "as_of": datetime.now(timezone.utc).isoformat(),
            },
            "summary": {
                "total_tracked": total_tracked,
                "win_rate_pct": win_rate_pct,
                "avg_return_pct": avg_return_pct,
                "max_return_pct": max_return_pct,
                "max_return_ticker": max_return_ticker,
                "active_count": active_count,
                "triggered_count": triggered_count,
                "target_hit_count": target_hit_count,
                "stop_hit_count": stop_hit_count,
                "setup_failed_count": setup_failed_count,
            },
            "items": items,
        }
    except Exception as e:
        logger.exception("[BREAKOUT-TRACKED] Failed fetching tracked breakouts: %s", e)
        return {
            "success": False,
            "error": str(e),
            "total_count": 0,
            "summary": {},
            "items": [],
        }


def _promote(ticker: str, result: dict, settings: Settings | None = None) -> None:
    """Place a ticker into the correct tier based on its score and audit the transition."""
    settings = settings or Settings()
    new_score = result.get("composite_score", 0)
    cur_p = result.get("current_price") or result.get("signal_price")
    trig_p = result.get("breakout_trigger")
    vol_r = result.get("volume_ratio", 1.0)
    cat_headline = (result.get("catalyst_headlines") or [None])[0]

    if _should_be_hot(result):
        was_warm = ticker in _pool["warm"]
        was_hot = ticker in _pool["hot"]
        _pool["hot"][ticker] = {"result": result, "consecutive_low": 0}
        _pool["warm"].pop(ticker, None)

        if not was_hot:
            from_t = "WARM" if was_warm else "COLD"
            reason_str = f"Promoted to HOT: Score {new_score:.1f} (>= {HOT_THRESHOLD}) with volume ratio {vol_r:.2f}x approaching resistance/trigger ₹{trig_p}"
            if cat_headline:
                reason_str += f" + News: {cat_headline}"
            record_breakout_transition(
                ticker=ticker,
                event_type="PROMOTED_HOT",
                from_tier=from_t,
                to_tier="HOT",
                score_before=None,
                score_after=new_score,
                price=cur_p,
                trigger_price=trig_p,
                reason=reason_str,
                catalyst_impact=cat_headline,
                settings=settings,
            )

    elif new_score >= WARM_THRESHOLD:
        if ticker not in _pool["hot"]:
            was_warm = ticker in _pool["warm"]
            _pool["warm"][ticker] = {"result": result, "consecutive_low": 0}
            if not was_warm:
                reason_str = f"Added to WARM: Coiling compression setup with score {new_score:.1f} (>= {WARM_THRESHOLD})"
                record_breakout_transition(
                    ticker=ticker,
                    event_type="ADDED_WARM",
                    from_tier="COLD",
                    to_tier="WARM",
                    score_before=None,
                    score_after=new_score,
                    price=cur_p,
                    trigger_price=trig_p,
                    reason=reason_str,
                    catalyst_impact=cat_headline,
                    settings=settings,
                )


def _demote_hot(ticker: str, settings: Settings | None = None) -> None:
    """Demote a Hot ticker: increment consecutive_low, remove after 2 strikes with audit log."""
    settings = settings or Settings()
    entry = _pool["hot"].get(ticker)
    if not entry:
        return
    entry["consecutive_low"] += 1
    if entry["consecutive_low"] >= 2:
        result = entry["result"]
        score = result.get("composite_score", 0)
        cur_p = result.get("current_price") or result.get("signal_price")
        trig_p = result.get("breakout_trigger")
        del _pool["hot"][ticker]

        # Maybe keep in warm if score still qualifies
        if score >= WARM_THRESHOLD:
            _pool["warm"][ticker] = {"result": result, "consecutive_low": 0}
            record_breakout_transition(
                ticker=ticker,
                event_type="DEMOTED_WARM",
                from_tier="HOT",
                to_tier="WARM",
                score_before=score,
                score_after=score,
                price=cur_p,
                trigger_price=trig_p,
                reason=f"Demoted HOT ➔ WARM: Score dropped to {score:.1f} (< {HOT_DEMOTION_THRESHOLD}) for 2 consecutive scan cycles",
                settings=settings,
            )
            logger.debug("[BREAKOUT] %s demoted Hot → Warm (score %.1f)", ticker, score)
        else:
            record_breakout_transition(
                ticker=ticker,
                event_type="REMOVED_COLD",
                from_tier="HOT",
                to_tier="COLD",
                score_before=score,
                score_after=score,
                price=cur_p,
                trigger_price=trig_p,
                reason=f"Removed from Breakout Radar: Score fell to {score:.1f} below minimum setup criteria",
                settings=settings,
            )
            logger.debug("[BREAKOUT] %s demoted Hot → Cold (score %.1f)", ticker, score)


def _demote_warm(ticker: str, settings: Settings | None = None) -> None:
    """Demote a Warm ticker: increment consecutive_low, remove after 2 strikes with audit log."""
    settings = settings or Settings()
    entry = _pool["warm"].get(ticker)
    if not entry:
        return
    entry["consecutive_low"] += 1
    if entry["consecutive_low"] >= 2:
        result = entry["result"]
        score = result.get("composite_score", 0)
        cur_p = result.get("current_price") or result.get("signal_price")
        trig_p = result.get("breakout_trigger")
        record_breakout_transition(
            ticker=ticker,
            event_type="REMOVED_COLD",
            from_tier="WARM",
            to_tier="COLD",
            score_before=score,
            score_after=score,
            price=cur_p,
            trigger_price=trig_p,
            reason=f"Removed from Warm Pool: Score dropped to {score:.1f} (< {WARM_DEMOTION_THRESHOLD}) for 2 consecutive cycles",
            settings=settings,
        )
        logger.debug("[BREAKOUT] %s demoted Warm → Cold (score %.1f)", ticker, score)
        del _pool["warm"][ticker]


# ---------------------------------------------------------------------------
# Public API (backward-compatible)
# ---------------------------------------------------------------------------

def get_cached_scan_results(
    universe: str | None = None,
    settings: Settings | None = None,
    asof_date: str | None = None,
) -> list[dict[str, Any]]:
    """Return breakout candidates, optionally filtered by universe and point-in-time as-of date."""
    settings = settings or Settings()
    if asof_date:
        return run_breakout_scan(settings, universe=universe, asof_date=asof_date)

    if not _pool.get("candidates"):
        load_breakout_pool_from_db(settings)

    all_candidates = list(_pool["candidates"])
    if not universe or universe.lower() in ("all", "any", "global", "monitored"):
        return all_candidates

    # Filter candidates by the requested universe / watchlist
    try:
        from earnings_engine.data.universe import load_universe
        from earnings_engine.data.watchlists import get_watchlist

        u_clean = universe.lower().strip()
        uni_tickers: set[str] = set()
        if u_clean in ("nifty_50", "nifty50", "nifty_top_50", "nse_top", "in", "nse"):
            uni_tickers = set(load_universe("NSE_TOP", settings) or load_universe("NIFTY_50", settings) or [])
        elif u_clean == "nse_large_cap":
            uni_tickers = set(load_universe("NSE_LARGE_CAP", settings) or [])
        elif u_clean in ("us_top", "us"):
            uni_tickers = set(load_universe("US_TOP", settings) or [])
        else:
            # Check custom watchlist
            wl_tickers = get_watchlist(universe, settings)
            if wl_tickers:
                uni_tickers = set(wl_tickers)
            else:
                uni_tickers = set(load_universe(universe, settings) or [])

        if uni_tickers:
            uni_normalized = {t.upper() for t in uni_tickers}
            return [c for c in all_candidates if c.get("ticker", "").upper() in uni_normalized]
    except Exception as e:
        logger.debug("[BREAKOUT] Error filtering by universe %s: %s", universe, e)

    return all_candidates


def get_scan_status(universe: str | None = None) -> dict[str, Any]:
    """Return a lightweight status dict for the API."""
    return {
        "status": _pool["status"],
        "last_scan_at": _pool["last_scan_at"],
        "last_cold_scan_at": _pool["last_cold_scan_at"],
        "last_warm_scan_at": _pool["last_warm_scan_at"],
        "last_hot_scan_at": _pool["last_hot_scan_at"],
        "last_scan_duration_s": _pool["last_scan_duration_s"],
        "cold_tickers_scanned": _pool["cold_tickers_scanned"],
        "hot_count": _pool["hot_count"],
        "warm_count": _pool["warm_count"],
        "candidates_found": len(_pool["candidates"]),
        "universe": universe or "ALL",
        "min_score": BREAKOUT_MIN_SCORE,
        "scan_intervals": {
            "cold_min": COLD_INTERVAL_MIN,
            "warm_min": WARM_INTERVAL_MIN,
            "hot_min": HOT_INTERVAL_MIN,
        },
        "error": _pool["error"],
    }


# ---------------------------------------------------------------------------
# Scoring helpers (unchanged from original)
# ---------------------------------------------------------------------------

def _score_resistance_proximity(closes: pd.Series) -> tuple[float, float]:
    """Return (score 0-40, pct_from_high).

    Points awarded based on how close current price is to the recent high.
    Closer = higher score.  Being above high = breakout already = also high.
    """
    if len(closes) < 2:
        return 0.0, float("nan")
    current = float(closes.iloc[-1])
    window = min(len(closes), 252)   # up to 1 year
    high = float(closes.tail(window).max())
    if high <= 0:
        return 0.0, float("nan")
    pct_from_high = (current - high) / high * 100  # negative = below high
    if pct_from_high >= 0:           # above or at high (breakout)
        score = 40.0
    elif pct_from_high >= -1:
        score = 37.0
    elif pct_from_high >= -2:
        score = 32.0
    elif pct_from_high >= -3:
        score = 25.0
    elif pct_from_high >= -5:
        score = 15.0
    elif pct_from_high >= -8:
        score = 5.0
    else:
        score = 0.0
    return score, pct_from_high


def _score_volume_surge(volumes: pd.Series) -> tuple[float, float]:
    """Return (score 0-10, vol_ratio).

    Vol today vs 20D avg. Reward moderate accumulation, penalize extreme churn/exhaustion.
    """
    if len(volumes) < 5:
        return 0.0, float("nan")
    avg_20 = float(volumes.tail(21).iloc[:-1].mean()) if len(volumes) >= 21 else float(volumes.mean())
    today = float(volumes.iloc[-1])
    if avg_20 <= 0:
        return 0.0, float("nan")
    ratio = today / avg_20
    if 1.0 <= ratio < 1.5:
        score = 10.0
    elif 1.5 <= ratio < 2.0:
        score = 7.0
    elif ratio >= 2.0:
        score = 4.0
    else:
        score = 0.0
    return score, round(ratio, 2)


def _score_price_compression(closes: pd.Series) -> tuple[float, float]:
    """Return (score 0-10, atr_pct).

    ATR(14) / price.  Low ratio = price coiling = potential energy.
    """
    if len(closes) < 15:
        return 0.0, float("nan")
    # Approximate ATR using rolling 14D true range on close-only data
    daily_range = closes.pct_change().abs()
    atr_pct = float(daily_range.tail(14).mean()) * 100   # as % of price
    if atr_pct <= 0:
        return 0.0, float("nan")
    if atr_pct < 0.5:
        score = 10.0
    elif atr_pct < 1.0:
        score = 8.0
    elif atr_pct < 1.5:
        score = 5.0
    elif atr_pct < 2.5:
        score = 2.0
    else:
        score = 0.0
    return score, round(atr_pct, 3)


def _score_momentum(closes: pd.Series) -> tuple[float, str]:
    """Return (score 0-25, signal).

    30D return > 0 AND price > 20D SMA → strong momentum.
    """
    if len(closes) < 20:
        return 0.0, "insufficient"
    current = float(closes.iloc[-1])
    sma_20 = float(closes.tail(20).mean())
    ret_30 = float((closes.iloc[-1] / closes.iloc[max(0, len(closes) - 31)]) - 1) * 100

    above_sma = current > sma_20
    positive_momentum = ret_30 > 0

    if above_sma and positive_momentum and ret_30 > 5:
        score, signal = 25.0, "Strong"
    elif above_sma and positive_momentum:
        score, signal = 18.0, "Moderate"
    elif above_sma or positive_momentum:
        score, signal = 8.0, "Weak"
    else:
        score, signal = 0.0, "None"
    return score, signal


def _score_fundamental(quality_scores: list[float | None]) -> tuple[float, float]:
    """Return (score 0-15, avg_quality).

    Takes a list of quality scores (each 1-9) from q1/q2/q3 earnings history.
    Normalised: avg=9 → 15 pts, avg=1 → 0 pts.
    """
    valid = [q for q in quality_scores if q is not None and not (isinstance(q, float) and np.isnan(q))]
    if not valid:
        return 0.0, float("nan")
    avg_q = float(np.mean(valid))
    score = round((avg_q - 1) / 8 * 15, 1)   # map [1,9] → [0,15]
    return max(0.0, min(15.0, score)), round(avg_q, 2)


# ---------------------------------------------------------------------------
# Per-ticker scorer
# ---------------------------------------------------------------------------

def score_breakout(
    ticker: str,
    prices_df: pd.DataFrame,
    quality_scores: list[float | None] | None = None,
    asof_date: str | None = None,
) -> dict[str, Any] | None:
    """Score a single ticker point-in-time, and compute realized breakout outcomes.

    ``prices_df`` must have at least a ``close`` column (and optionally ``high``, ``low``, ``volume``).
    """
    if prices_df is None or prices_df.empty:
        return None

    df = prices_df.copy()
    if not isinstance(df.index, pd.DatetimeIndex):
        try:
            df.index = pd.to_datetime(df.index)
        except Exception:
            pass

    df = df.sort_index()

    # Point-in-time slicing
    if asof_date:
        asof_clean = str(asof_date).strip()[:10]
        hist_df = df.loc[df.index <= asof_clean]
        future_df = df.loc[df.index > asof_clean]
    else:
        hist_df = df
        future_df = pd.DataFrame()

    if hist_df.empty:
        return None

    # Ensure numeric close series
    closes = pd.to_numeric(hist_df["close"], errors="coerce").dropna()
    if len(closes) < 10:
        return None

    signal_date = str(hist_df.index[-1])[:10]
    signal_price = float(closes.iloc[-1])

    # Volume (optional)
    if "volume" in hist_df.columns:
        volumes = pd.to_numeric(hist_df["volume"], errors="coerce").fillna(0)
        volumes = volumes.reindex(closes.index, fill_value=0)
    else:
        volumes = pd.Series(dtype=float)

    # --- Sub-scores ---
    res_score, pct_from_high = _score_resistance_proximity(closes)
    vol_score, vol_ratio = _score_volume_surge(volumes) if len(volumes) >= 5 else (0.0, float("nan"))
    comp_score, atr_pct = _score_price_compression(closes)
    mom_score, momentum_signal = _score_momentum(closes)
    fund_score, avg_quality = _score_fundamental(quality_scores or [])

    composite = round(res_score + vol_score + comp_score + mom_score + fund_score, 1)

    # Calculate Breakout Levels
    window = min(len(hist_df), 252)
    high_series = pd.to_numeric(hist_df["high"], errors="coerce") if "high" in hist_df.columns else pd.to_numeric(hist_df["close"], errors="coerce")
    resistance_high = float(high_series.tail(window).max())
    breakout_trigger = round(resistance_high, 2)

    atr_pct_val = atr_pct if (atr_pct is not None and not np.isnan(atr_pct)) else 2.0
    atr_val = signal_price * (atr_pct_val / 100.0)
    target_price = round(max(breakout_trigger * 1.08, breakout_trigger + 2.0 * atr_val), 2)
    stop_loss = round(min(signal_price * 0.95, signal_price - 1.5 * atr_val), 2)

    # Current / Latest Market Data
    all_closes = pd.to_numeric(df["close"], errors="coerce").dropna()
    current_price = float(all_closes.iloc[-1])
    current_date = str(df.index[-1])[:10]

    # Evaluate Outcome (Did Breakout Happen?)
    if not future_df.empty and signal_date != current_date:
        f_highs = pd.to_numeric(future_df["high"], errors="coerce") if "high" in future_df.columns else pd.to_numeric(future_df["close"], errors="coerce")
        f_lows = pd.to_numeric(future_df["low"], errors="coerce") if "low" in future_df.columns else pd.to_numeric(future_df["close"], errors="coerce")
        post_high = float(f_highs.max()) if not f_highs.empty else signal_price
        post_low = float(f_lows.min()) if not f_lows.empty else signal_price

        realized_return_pct = round(((current_price - signal_price) / signal_price) * 100, 2)
        max_gain_pct = round(((post_high - signal_price) / signal_price) * 100, 2)
        days_elapsed = len(future_df)

        breakout_fired = bool(post_high >= breakout_trigger or current_price >= breakout_trigger)

        if post_high >= target_price:
            breakout_happened = True
            outcome = "TARGET_HIT"
            outcome_label = f"Target Hit 🎯 (+{max_gain_pct}%)"
            outcome_badge = "emerald"
        elif breakout_fired:
            # Setup triggered breakout above resistance level
            if post_low <= stop_loss or current_price <= stop_loss:
                breakout_happened = False
                outcome = "STOP_LOSS_HIT"
                outcome_label = f"Stop Hit 🛑 ({realized_return_pct:+0.1f}%)"
                outcome_badge = "rose"
            elif current_price >= signal_price:
                breakout_happened = True
                outcome = "BREAKOUT_SUCCEEDED"
                outcome_label = f"Breakout Succeeded ✅ ({realized_return_pct:+0.1f}%)"
                outcome_badge = "emerald"
            else:
                breakout_happened = False
                outcome = "BREAKOUT_RETRACED"
                outcome_label = f"Breakout Retraced ⚠️ ({realized_return_pct:+0.1f}%)"
                outcome_badge = "amber"
        elif post_low <= stop_loss or current_price <= stop_loss:
            # Setup NEVER crossed trigger level and dropped into stop loss
            breakout_happened = False
            outcome = "SETUP_FAILED"
            outcome_label = f"Setup Failed ❌ ({realized_return_pct:+0.1f}%)"
            outcome_badge = "rose"
        elif current_price >= signal_price:
            breakout_happened = False
            outcome = "COILING_IN_PROFIT"
            outcome_label = f"Coiling In Green 🟢 ({realized_return_pct:+0.1f}%)"
            outcome_badge = "emerald"
        else:
            breakout_happened = False
            outcome = "COILING_IN_RANGE"
            outcome_label = f"Coiling In Range 🗜️ ({realized_return_pct:+0.1f}%)"
            outcome_badge = "slate"
    else:
        breakout_fired = False
        breakout_happened = None
        outcome = "PENDING"
        outcome_label = "Pending Breakout ⏳"
        outcome_badge = "blue"
        realized_return_pct = 0.0
        max_gain_pct = None
        days_elapsed = 0
        post_high = signal_price

    # One-liner narrative explaining what happened post-signal
    if outcome == "TARGET_HIT":
        one_liner = f"🎯 Target Hit: Reached peak ₹{post_high:,.2f} (+{max_gain_pct}%) in {days_elapsed}d; crossed trigger ₹{breakout_trigger:,.2f} with strong follow-through."
    elif outcome == "BREAKOUT_SUCCEEDED":
        one_liner = f"🚀 Breakout Succeeded: Breached trigger ₹{breakout_trigger:,.2f}, hit peak ₹{post_high:,.2f} (+{max_gain_pct}%), currently holding gains at ₹{current_price:,.2f} ({realized_return_pct:+.1f}%)."
    elif outcome == "BREAKOUT_RETRACED":
        one_liner = f"⚠️ Breakout Retraced: Triggered breakout to peak ₹{post_high:,.2f} (+{max_gain_pct}%) but retraced to ₹{current_price:,.2f} ({realized_return_pct:+.1f}%) on profit taking."
    elif outcome == "STOP_LOSS_HIT":
        one_liner = f"🛑 Stop Hit: Breached trigger but slipped below SL ₹{stop_loss:,.2f} ({realized_return_pct:+.1f}%) after hitting peak ₹{post_high:,.2f}."
    elif outcome == "SETUP_FAILED":
        one_liner = f"❌ Setup Failed: Never crossed breakout trigger ₹{breakout_trigger:,.2f}; broke below SL ₹{stop_loss:,.2f} ({realized_return_pct:+.1f}%)."
    elif outcome == "COILING_IN_PROFIT":
        one_liner = f"🟢 Coiling Green: Trading above signal price at ₹{current_price:,.2f} ({realized_return_pct:+.1f}%), awaiting trigger breach at ₹{breakout_trigger:,.2f}."
    elif outcome == "COILING_IN_RANGE":
        one_liner = f"🗜️ Coiling In Range: Consolidating near ₹{current_price:,.2f} ({realized_return_pct:+.1f}%), holding above SL ₹{stop_loss:,.2f}."
    else:
        one_liner = f"⏳ Active Setup: Monitoring for resistance breach at ₹{breakout_trigger:,.2f} with SL at ₹{stop_loss:,.2f}."

    # Anti-Fakeout & Volume Confirmation Parameters
    vol_expansion_str = f"{vol_ratio:.1f}x Vol" if (vol_ratio is not None and not np.isnan(vol_ratio)) else "1.0x Vol"
    is_vol_confirmed = bool(vol_ratio is not None and vol_ratio >= 1.5)
    is_fakeout_risk = bool(vol_ratio is not None and vol_ratio < 1.3 and (breakout_fired or (pct_from_high is not None and pct_from_high >= -1.0)))

    if is_vol_confirmed and res_score >= 25:
        confirmation_badge = f"⭐ High-Conviction Vol ({vol_expansion_str})"
        confirmation_color = "#34d399"
    elif is_fakeout_risk:
        confirmation_badge = f"⚠️ Low Vol Warning ({vol_expansion_str})"
        confirmation_color = "#fbbf24"
    elif vol_ratio is not None and vol_ratio >= 1.2:
        confirmation_badge = f"🔊 {vol_expansion_str} Expansion"
        confirmation_color = "#38bdf8"
    else:
        confirmation_badge = f"📊 Normal Vol ({vol_expansion_str})"
        confirmation_color = "#94a3b8"

    # Mathematical Calculation & Reasoning Notes
    res_note = (
        f"Price ₹{signal_price:,.2f} is {pct_from_high:+.1f}% from 52W/recent high of ₹{resistance_high:,.2f} (awarding {res_score:.1f}/30 pts for proximity)"
        if not (isinstance(pct_from_high, float) and np.isnan(pct_from_high)) else "Insufficient price range data."
    )
    vol_note = (
        f"Latest volume is {vol_ratio:.2f}× the 20-day baseline average (awarding {vol_score:.1f}/20 pts for institutional participation)"
        if not (isinstance(vol_ratio, float) and np.isnan(vol_ratio)) else "Volume in line with 20D average (0/20 pts)."
    )
    comp_note = (
        f"ATR(14) is {atr_pct:.2f}% of price, indicating {'tight energy coiling & volatility compression' if (atr_pct or 0) < 1.5 else 'moderate volatility'} (awarding {comp_score:.1f}/15 pts)"
        if not (isinstance(atr_pct, float) and np.isnan(atr_pct)) else "Normal price volatility."
    )
    mom_note = f"Momentum signal is '{momentum_signal}' based on 30D return & 20D SMA trend posture (awarding {mom_score:.1f}/15 pts)"
    fund_note = (
        f"Historical quarterly earnings quality averages {avg_quality:.1f}/9 (awarding {fund_score:.1f}/20 pts fundamental bonus)"
        if not (isinstance(avg_quality, float) and np.isnan(avg_quality)) else "No quarterly quality history (0/20 pts)."
    )

    # Setup Archetype
    if (pct_from_high is not None and pct_from_high >= -1.5) and (vol_ratio is not None and vol_ratio >= 1.5):
        archetype = "🔥 High-Volume 52W Breakout"
    elif comp_score >= 12 and res_score >= 20:
        archetype = "🗜️ Coiling Resistance Squeeze"
    elif vol_ratio is not None and vol_ratio >= 1.8:
        archetype = "📊 Institutional Accumulation Surge"
    elif mom_score >= 10:
        archetype = "🚀 Trend Continuation Breakout"
    else:
        archetype = "📈 Resistance Approach Coil"

    risk_reward_ratio = round((target_price - signal_price) / max(0.01, (signal_price - stop_loss)), 2)

    calculation_notes = {
        "setup_archetype": archetype,
        "risk_reward_ratio": risk_reward_ratio,
        "resistance_reasoning": res_note,
        "volume_reasoning": vol_note,
        "compression_reasoning": comp_note,
        "momentum_reasoning": mom_note,
        "fundamental_reasoning": fund_note,
        "formula_summary": f"Score {composite}/100 = Res({res_score:.0f}) + Vol({vol_score:.0f}) + Squeeze({comp_score:.0f}) + Mom({mom_score:.0f}) + Fund({fund_score:.0f})",
    }

    # Institutional Accumulation & Flow
    inst_flow = {}
    try:
        from earnings_engine.data.institutional_accumulation import get_stock_institutional_activity
        act = get_stock_institutional_activity(ticker)
        if act:
            inst_flow = {
                "accumulation_score": act.get("accumulation_score"),
                "verdict": act.get("verdict"),
                "funds_in": act.get("funds_accumulating_count", 0),
                "funds_out": act.get("funds_selling_count", 0),
                "net_flow_cr": act.get("net_flow_cr", 0.0),
            }
    except Exception:
        pass

    return {
        "ticker": ticker,
        "signal_date": signal_date,
        "signal_price": round(signal_price, 2),
        "predicted_value": round(signal_price, 2),
        "breakout_trigger": breakout_trigger,
        "target_price": target_price,
        "stop_loss": stop_loss,
        "risk_reward_ratio": risk_reward_ratio,
        "setup_archetype": archetype,
        "calculation_notes": calculation_notes,
        "institutional_flow": inst_flow,
        "current_price": round(current_price, 2),
        "current_date": current_date,
        "post_high": round(post_high, 2) if post_high is not None else round(signal_price, 2),
        "peak_price": round(post_high, 2) if post_high is not None else round(signal_price, 2),
        "peak_gain_pct": max_gain_pct,
        "realized_return_pct": realized_return_pct,
        "max_gain_pct": max_gain_pct,
        "breakout_happened": breakout_happened,
        "breakout_fired": breakout_fired,
        "outcome": outcome,
        "outcome_label": outcome_label,
        "outcome_badge": outcome_badge,
        "explanation_one_liner": one_liner,
        "what_happened_summary": one_liner,
        "confirmation_badge": confirmation_badge,
        "confirmation_color": confirmation_color,
        "vol_expansion_str": vol_expansion_str,
        "is_fakeout_risk": is_fakeout_risk,
        "is_vol_confirmed": is_vol_confirmed,
        "days_elapsed": days_elapsed,
        "composite_score": composite,
        "resistance_score": res_score,
        "volume_score": vol_score,
        "compression_score": comp_score,
        "momentum_score": mom_score,
        "fundamental_score": fund_score,
        "pct_from_high": round(pct_from_high, 2) if not (isinstance(pct_from_high, float) and np.isnan(pct_from_high)) else None,
        "volume_ratio": vol_ratio if not (isinstance(vol_ratio, float) and np.isnan(vol_ratio)) else None,
        "atr_pct": atr_pct if not (isinstance(atr_pct, float) and np.isnan(atr_pct)) else None,
        "momentum_signal": momentum_signal,
        "avg_quality_score": avg_quality if not (isinstance(avg_quality, float) and np.isnan(avg_quality)) else None,
        "data_points": len(closes),
        "scanned_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Local Ollama Multi-Model AI Reasoning Engine
# ---------------------------------------------------------------------------

_AI_REASONING_CACHE: dict[str, dict[str, Any]] = {}


def generate_breakout_ai_reasoning(
    ticker: str,
    model_name: str | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Generate multi-model AI reasoning for a breakout candidate using local Ollama models.

    Supports:
    - `llama3.2:3b` (Fast local consensus)
    - `deepseek-r1:8b` (Deep chain-of-thought institutional reasoning)
    - `qwen2.5-coder:latest` (Algorithmic technical validation)
    """
    sym = ticker.strip().upper()
    settings = settings or Settings()

    # Check in-memory cache
    cache_key = f"{sym}_{model_name or 'default'}"
    if cache_key in _AI_REASONING_CACHE:
        return _AI_REASONING_CACHE[cache_key]

    # Get scored candidate details
    from earnings_engine.data.prices import load_prices, load_price_metrics
    prices_df = load_prices(sym, settings)
    metrics = load_price_metrics(sym, settings) or {}
    company_name = metrics.get("company_name") or sym
    industry = metrics.get("industry") or metrics.get("sector") or "—"

    quality_scores = [
        float(metrics.get(k)) if metrics.get(k) is not None else None
        for k in ("q1_earnings_score", "q2_earnings_score", "q3_earnings_score")
    ]
    scored = score_breakout(sym, prices_df, quality_scores) or {}

    notes = scored.get("calculation_notes", {})
    target = scored.get("target_price", 0)
    stop = scored.get("stop_loss", 0)
    trigger = scored.get("breakout_trigger", 0)
    cur_p = scored.get("current_price", 0)
    score = scored.get("composite_score", 0)
    archetype = scored.get("setup_archetype", "Breakout Coil")

    # Construct quantitative prompt
    prompt = f"""You are an elite quantitative trading analyst specializing in breakout pattern recognition and price action momentum.
Evaluate the following breakout setup for {sym} ({company_name}) and provide an institutional opinion.

### Setup Metrics:
- Ticker: {sym} | Industry: {industry}
- Setup Archetype: {archetype}
- Composite Breakout Score: {score}/100
- Current Price: ₹{cur_p}
- Breakout Trigger (Resistance): ₹{trigger} ({scored.get('pct_from_high', 0):+.1f}% from high)
- Upside Target Price: ₹{target}
- Invalidation Stop Loss: ₹{stop}
- Risk/Reward Ratio: {scored.get('risk_reward_ratio', 2.0)} : 1
- Volume Surge: {scored.get('volume_ratio', 1.0)}x of 20D average
- Price Compression (ATR %): {scored.get('atr_pct', 2.0)}%
- Momentum Signal: {scored.get('momentum_signal', 'Moderate')}
- Earnings Quality (1-9): {scored.get('avg_quality_score', 'N/A')}

### Instructions:
1. Explain whether this breakout has genuine institutional volume accumulation or fakeout/exhaustion risk.
2. Outline key execution game plan (Entry confirmation, trailing stop, target scaling).
3. Output strict JSON adhering to this schema:
{{
  "verdict": "HIGH_CONVICTION_BREAKOUT",
  "confidence_pct": 82,
  "model_used": "{model_name or 'Ollama'}",
  "accumulation_analysis": "2-3 sentences evaluating the volume surge and price coiling.",
  "fakeout_risk_assessment": "Key vulnerability or fakeout warning signs to monitor.",
  "execution_plan": "Specific entry trigger, stop loss discipline, and target level.",
  "key_reasons": ["Reason 1", "Reason 2", "Reason 3"]
}}
"""

    model_to_use = model_name or os.getenv("OLLAMA_MODEL", "llama3.2:3b")
    ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434")

    output_dict: dict[str, Any] | None = None

    # 1. Try Local Ollama
    try:
        import urllib.request
        data_payload = json.dumps({
            "model": model_to_use,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {
                "num_ctx": 4096,
                "temperature": 0.3,
            },
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{ollama_host}/api/generate",
            data=data_payload,
            headers={"Content-Type": "application/json"},
        )
        # Timeout: 45s for 8B deepseek, 15s for 3b
        timeout = 45 if "8b" in model_to_use.lower() or "deepseek" in model_to_use.lower() else 18
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw_res = json.loads(resp.read().decode("utf-8"))
            resp_text = raw_res.get("response", "")
            m = re.search(r"\{[\s\S]*\}", resp_text)
            if m:
                output_dict = json.loads(m.group(0))
                output_dict["source"] = f"Local Ollama ({model_to_use})"
    except Exception as e:
        logger.debug("[BREAKOUT-AI] Local Ollama call (%s) failed/timed out: %s", model_to_use, e)

    # 2. Rule-based Institutional Fallback if local model unavailable
    if not output_dict:
        vol_r = scored.get("volume_ratio") or 1.0
        pct_h = scored.get("pct_from_high") or -3.0
        is_high_conviction = score >= 60 and vol_r >= 1.3 and pct_h >= -3.0

        verdict = "HIGH_CONVICTION_BREAKOUT" if is_high_conviction else ("POTENTIAL_BREAKOUT_COIL" if score >= 40 else "WATCHLIST_SETUP")
        conf = min(92, max(60, int(score * 0.9 + (vol_r * 5))))

        output_dict = {
            "verdict": verdict,
            "confidence_pct": conf,
            "model_used": "Institutional Quantitative Rule Engine",
            "source": "Quantitative Synthesis",
            "accumulation_analysis": (
                f"{sym} displays {vol_r:.2f}× volume surge alongside an ATR compression of {scored.get('atr_pct', 1.5):.2f}%, "
                f"indicating tight price energy coiled directly under key resistance at ₹{trigger:,.2f}."
            ),
            "fakeout_risk_assessment": (
                f"Watch for rejection at ₹{trigger:,.2f} on declining volume. Stop loss is strictly placed at ₹{stop:,.2f} "
                f"to protect capital against false breakouts."
            ),
            "execution_plan": (
                f"Enter on confirmed hourly close above ₹{trigger:,.2f}. Scale out 50% at initial target ₹{target:,.2f}, "
                f"and trail remaining position using 20D SMA."
            ),
            "key_reasons": [
                notes.get("resistance_reasoning", f"Within {pct_h:+.1f}% of key resistance high"),
                notes.get("volume_reasoning", f"{vol_r:.2f}x volume surge confirming buyer interest"),
                notes.get("compression_reasoning", "ATR squeeze signaling high potential energy release"),
            ],
        }

    output_dict["ticker"] = sym
    output_dict["company_name"] = company_name
    output_dict["score"] = score
    output_dict["archetype"] = archetype
    output_dict["trigger"] = trigger
    output_dict["target"] = target
    output_dict["stop_loss"] = stop
    output_dict["risk_reward_ratio"] = scored.get("risk_reward_ratio", 2.0)
    output_dict["calculation_notes"] = notes
    output_dict["generated_at"] = datetime.now(timezone.utc).isoformat()

    _AI_REASONING_CACHE[cache_key] = output_dict
    return output_dict


# ---------------------------------------------------------------------------
# Internal: score a single ticker with DB lookups
# ---------------------------------------------------------------------------

def _score_single_ticker(
    ticker: str,
    settings: Settings,
    asof_date: str | None = None,
    use_live_quote: bool = False,
) -> dict[str, Any] | None:
    """Load prices, metrics, news catalysts, and score a single ticker. Returns result dict or None."""
    try:
        from earnings_engine.data.prices import load_prices, load_price_metrics, fetch_live_quote

        prices_df = load_prices(ticker, settings)
        if prices_df is None or prices_df.empty:
            return None

        # 1. Live Price integration for Hot stocks / on-demand re-eval
        if use_live_quote and not asof_date:
            try:
                live_q = fetch_live_quote(ticker, settings, sync_db=False)
                if live_q and live_q.get("current_price"):
                    live_price = float(live_q["current_price"])
                    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                    if not prices_df.empty:
                        last_idx_str = str(prices_df.index[-1])[:10]
                        if last_idx_str == today_str:
                            prices_df.loc[prices_df.index[-1], "close"] = live_price
                            if live_q.get("volume"):
                                prices_df.loc[prices_df.index[-1], "volume"] = float(live_q["volume"])
                        else:
                            new_row = pd.DataFrame(
                                {
                                    "open": [float(live_q.get("open") or live_price)],
                                    "high": [max(live_price, float(live_q.get("high") or live_price))],
                                    "low": [min(live_price, float(live_q.get("low") or live_price))],
                                    "close": [live_price],
                                    "volume": [float(live_q.get("volume") or 0)],
                                },
                                index=pd.to_datetime([today_str]),
                            )
                            prices_df = pd.concat([prices_df, new_row])
            except Exception as e:
                logger.debug("[BREAKOUT-LIVE] Live quote fetch skipped for %s: %s", ticker, e)

        metrics = load_price_metrics(ticker, settings) or {}
        quality_scores: list[float | None] = []
        for key in ("q1_earnings_score", "q2_earnings_score", "q3_earnings_score"):
            v = metrics.get(key)
            if v is not None:
                try:
                    quality_scores.append(float(v))
                except (TypeError, ValueError):
                    quality_scores.append(None)
            else:
                quality_scores.append(None)

        result = score_breakout(ticker, prices_df, quality_scores, asof_date=asof_date)
        if result:
            result["company_name"] = metrics.get("company_name") or ticker
            result["market_cap_cr"] = metrics.get("market_cap_cr") or metrics.get("market_cap")
            result["industry"] = metrics.get("industry") or metrics.get("sector") or "—"

            # 2. News Catalyst Integration from pooled news database
            if not asof_date:
                try:
                    from earnings_engine.data.catalysts_news import get_recent_catalysts
                    catalysts = get_recent_catalysts(ticker, limit=3, settings=settings)
                    if catalysts:
                        top_cat = catalysts[0]
                        direction = str(top_cat.get("direction") or "NEUTRAL").upper()
                        impact = float(top_cat.get("impact_score") or 50)
                        title = str(top_cat.get("title") or "")
                        result["latest_news"] = {
                            "title": title,
                            "direction": direction,
                            "impact_score": impact,
                            "impact_level": top_cat.get("impact_level", "MEDIUM"),
                            "published_at": top_cat.get("published_at"),
                            "category": top_cat.get("category", "General"),
                        }
                        # Apply catalyst modifier to composite score
                        news_bonus = 0.0
                        if direction == "BULLISH" and impact >= 60:
                            news_bonus = min(10.0, round((impact - 50) / 50 * 10, 1))
                        elif direction == "BEARISH" and impact >= 65:
                            news_bonus = -min(15.0, round((impact - 50) / 50 * 15, 1))

                        if news_bonus != 0.0:
                            result["news_bonus"] = news_bonus
                            result["composite_score"] = max(0.0, min(100.0, round(result["composite_score"] + news_bonus, 1)))
                            cat_tag = "🚀 Bullish" if news_bonus > 0 else "⚠️ Bearish"
                            result.setdefault("reasoning", []).append(
                                f"{cat_tag} News Catalyst ({impact:.0f}% impact, {news_bonus:+.1f} pts): {title[:75]}..."
                            )
                except Exception as e:
                    logger.debug("[BREAKOUT-NEWS] Catalyst integration error for %s: %s", ticker, e)

        return result
    except Exception as e:
        logger.debug("[BREAKOUT] Error scoring %s: %s", ticker, e)
    return None


# ---------------------------------------------------------------------------
# Tier-specific scan functions
# ---------------------------------------------------------------------------

def _resolve_universe_tickers(settings: Settings, universe: str | None = None) -> list[str]:
    """Resolve the full set of tickers to scan from universes, watchlists, and DB."""
    from earnings_engine.data.watchlists import all_watchlists, get_watchlist
    from earnings_engine.data.universe import load_universe
    from earnings_engine.data.prices import _connect

    tickers: set[str] = set()
    u_clean = universe.lower().strip() if universe else "all"

    if u_clean in ("nifty_50", "nifty50", "nifty_top_50", "nse_top"):
        uni = load_universe("NSE_TOP", settings) or load_universe("NIFTY_50", settings)
        if uni:
            tickers.update(uni)
    elif u_clean == "nse_large_cap":
        large_caps = load_universe("NSE_LARGE_CAP", settings)
        if large_caps:
            tickers.update(large_caps[:120])
    elif u_clean in ("us_top", "us"):
        us_uni = load_universe("US_TOP", settings)
        if us_uni:
            tickers.update(us_uni)
    elif u_clean != "all":
        wl_tickers = get_watchlist(universe, settings)
        if wl_tickers:
            tickers.update(wl_tickers)
        else:
            custom_uni = load_universe(universe, settings)
            if custom_uni:
                tickers.update(custom_uni)

    if not tickers:
        try:
            wls = all_watchlists(settings)
            for wl in wls:
                if isinstance(wl, dict):
                    tickers.update(wl.get("tickers", []))
                elif isinstance(wl, str):
                    wl_tickers = get_watchlist(wl, settings)
                    if wl_tickers:
                        tickers.update(wl_tickers)
        except Exception as e:
            logger.warning("[BREAKOUT] Could not load watchlists: %s", e)

        try:
            for u in ("NSE_TOP", "IN"):
                uni = load_universe(u, settings)
                if uni:
                    tickers.update(uni)
            large_caps = load_universe("NSE_LARGE_CAP", settings)
            if large_caps:
                tickers.update(large_caps[:100])
        except Exception as e:
            logger.debug("[BREAKOUT] Universe load fallback: %s", e)

        if len(tickers) < 50:
            try:
                with _connect(settings) as conn:
                    rows = conn.execute("SELECT DISTINCT ticker FROM price_history LIMIT 100").fetchall()
                    tickers.update([r[0] for r in rows if r[0]])
            except Exception:
                pass

    return sorted(tickers)


def run_cold_scan(settings: Settings, universe: str | None = None, min_score: float | None = None, **kwargs: Any) -> None:
    """T0 Cold Scan: score the entire universe and populate warm/hot pools."""
    t0 = time.perf_counter()
    _pool["status"] = "running"
    _pool["error"] = None

    from earnings_engine.data.automation_schedules import record_job_start, record_job_finish
    record_job_start("breakout_cold_scan", settings)

    ticker_list = _resolve_universe_tickers(settings, universe)
    if not ticker_list:
        logger.info("[BREAKOUT-COLD] No tickers found to scan.")
        _pool["status"] = "done"
        _pool["cold_tickers_scanned"] = 0
        _pool["last_cold_scan_at"] = datetime.now(timezone.utc).isoformat()
        _pool["last_scan_at"] = _pool["last_cold_scan_at"]
        record_job_finish("breakout_cold_scan", 0.0, "No tickers found to scan.", settings=settings)
        return

    from concurrent.futures import ThreadPoolExecutor

    def _score(ticker: str) -> tuple[str, dict | None]:
        result = _score_single_ticker(ticker, settings)
        return ticker, result

    with ThreadPoolExecutor(max_workers=8) as executor:
        scored = list(executor.map(_score, ticker_list))

    promoted_hot = 0
    promoted_warm = 0
    for ticker, result in scored:
        if result is None:
            continue
        _promote(ticker, result, settings=settings)
        if ticker in _pool["hot"]:
            promoted_hot += 1
        elif ticker in _pool["warm"]:
            promoted_warm += 1

    _rebuild_candidates()
    save_breakout_pool_to_db(settings)

    elapsed = round(time.perf_counter() - t0, 2)
    now_iso = datetime.now(timezone.utc).isoformat()
    _pool.update({
        "last_cold_scan_at": now_iso,
        "last_scan_at": now_iso,
        "last_scan_duration_s": elapsed,
        "cold_tickers_scanned": len(ticker_list),
        "status": "done",
        "error": None,
    })

    summary_msg = f"Full scan: {len(ticker_list)} tickers → {len(_pool['hot'])} hot, {len(_pool['warm'])} warm, {len(_pool['candidates'])} candidates"
    record_job_finish("breakout_cold_scan", elapsed, summary_msg, settings=settings)

    logger.info(
        "[BREAKOUT-COLD] %s in %.1fs",
        summary_msg, elapsed,
    )


def run_warm_rescore(settings: Settings) -> None:
    """T1 Warm Rescore: rescore only warm-pool tickers."""
    warm_tickers = list(_pool["warm"].keys())
    if not warm_tickers:
        return

    t0 = time.perf_counter()
    from earnings_engine.data.automation_schedules import record_job_start, record_job_finish
    record_job_start("breakout_warm_rescore", settings)

    from earnings_engine.data.prices import fetch_batch_live_quotes
    from concurrent.futures import ThreadPoolExecutor

    # 1. Batch fetch latest quotes in parallel for warm setups
    try:
        fetch_batch_live_quotes(warm_tickers, settings=settings, sync_db=True, max_workers=8)
    except Exception as e:
        logger.debug("[BREAKOUT-WARM] Batch live quote fetch warning: %s", e)

    # 2. Rescore warm tickers
    def _score(ticker: str) -> tuple[str, dict | None]:
        return ticker, _score_single_ticker(ticker, settings, use_live_quote=False)

    with ThreadPoolExecutor(max_workers=6) as executor:
        scored = list(executor.map(_score, warm_tickers))

    for ticker, result in scored:
        if result is None:
            _demote_warm(ticker, settings=settings)
            continue

        new_score = result.get("composite_score", 0)
        if _should_be_hot(result):
            # Promote to hot
            _pool["warm"].pop(ticker, None)
            _pool["hot"][ticker] = {"result": result, "consecutive_low": 0}
            cur_p = result.get("current_price") or result.get("signal_price")
            trig_p = result.get("breakout_trigger")
            record_breakout_transition(
                ticker=ticker,
                event_type="PROMOTED_HOT",
                from_tier="WARM",
                to_tier="HOT",
                score_before=None,
                score_after=new_score,
                price=cur_p,
                trigger_price=trig_p,
                reason=f"Warm setup upgraded to HOT: Score {new_score:.1f} crossed threshold",
                settings=settings,
            )
        elif new_score >= WARM_THRESHOLD:
            _pool["warm"][ticker] = {"result": result, "consecutive_low": 0}
        elif new_score < WARM_DEMOTION_THRESHOLD:
            _demote_warm(ticker, settings=settings)
        else:
            # Between demotion threshold and warm threshold: keep but update
            if ticker in _pool["warm"]:
                _pool["warm"][ticker]["result"] = result

    _rebuild_candidates()
    save_breakout_pool_to_db(settings)

    elapsed = round(time.perf_counter() - t0, 2)
    now_iso = datetime.now(timezone.utc).isoformat()
    _pool["last_warm_scan_at"] = now_iso
    _pool["last_scan_at"] = now_iso

    summary_msg = f"Rescored {len(warm_tickers)} warm tickers (hot={len(_pool['hot'])}, warm={len(_pool['warm'])})"
    record_job_finish("breakout_warm_rescore", elapsed, summary_msg, settings=settings)

    logger.info(
        "[BREAKOUT-WARM] %s in %.1fs",
        summary_msg, elapsed,
    )


def run_hot_rescore(settings: Settings) -> None:
    """T2 Hot Rescore: rescore only hot-pool tickers in parallel batches for maximum freshness."""
    hot_tickers = list(_pool["hot"].keys())
    if not hot_tickers:
        return

    t0 = time.perf_counter()
    from earnings_engine.data.automation_schedules import record_job_start, record_job_finish
    record_job_start("breakout_hot_rescore", settings)

    from earnings_engine.data.prices import fetch_batch_live_quotes
    from concurrent.futures import ThreadPoolExecutor

    # 1. Batch fetch latest live market quotes in parallel (single sub-second batch)
    try:
        fetch_batch_live_quotes(hot_tickers, settings=settings, sync_db=True, max_workers=8)
    except Exception as e:
        logger.debug("[BREAKOUT-HOT] Batch live quote fetch warning: %s", e)

    # 2. Rescore hot tickers with freshest prices
    def _score(ticker: str) -> tuple[str, dict | None]:
        return ticker, _score_single_ticker(ticker, settings, use_live_quote=False)

    with ThreadPoolExecutor(max_workers=6) as executor:
        scored = list(executor.map(_score, hot_tickers))

    for ticker, result in scored:
        if result is None:
            _demote_hot(ticker, settings=settings)
            continue

        new_score = result.get("composite_score", 0)
        if _should_be_hot(result):
            _pool["hot"][ticker] = {"result": result, "consecutive_low": 0}
        elif new_score < HOT_DEMOTION_THRESHOLD:
            # Score dropped: track for two-strike demotion
            if ticker in _pool["hot"]:
                _pool["hot"][ticker]["result"] = result
                _demote_hot(ticker, settings=settings)
        else:
            # Between demotion threshold and hot threshold: keep but update
            if ticker in _pool["hot"]:
                _pool["hot"][ticker]["result"] = result
                _pool["hot"][ticker]["consecutive_low"] = 0

    _rebuild_candidates()
    save_breakout_pool_to_db(settings)

    elapsed = round(time.perf_counter() - t0, 2)
    now_iso = datetime.now(timezone.utc).isoformat()
    _pool["last_hot_scan_at"] = now_iso
    _pool["last_scan_at"] = now_iso

    summary_msg = f"Rescored {len(hot_tickers)} hot tickers"
    record_job_finish("breakout_hot_rescore", elapsed, summary_msg, settings=settings)

    logger.debug(
        "[BREAKOUT-HOT] %s in %.1fs",
        summary_msg, elapsed,
    )


# ---------------------------------------------------------------------------
# Full universe scan (backward-compatible, used for asof_date point-in-time)
# ---------------------------------------------------------------------------

def run_breakout_scan(
    settings: Settings,
    universe: str | None = None,
    asof_date: str | None = None,
) -> list[dict[str, Any]]:
    """Scan available tickers and return candidates sorted by score DESC point-in-time.

    For live scans (no asof_date), this delegates to `run_cold_scan` which
    populates the tiered pool and returns the merged candidates.
    For historical asof_date scans, performs a standalone full-universe scan.
    """
    if asof_date is None:
        # Live scan: use the tiered pool system
        run_cold_scan(settings, universe=universe)
        return list(_pool["candidates"])

    # Historical point-in-time scan (standalone, doesn't touch the pool)
    from concurrent.futures import ThreadPoolExecutor

    ticker_list = _resolve_universe_tickers(settings, universe)
    if not ticker_list:
        return []

    t0 = time.perf_counter()

    def _score(ticker: str) -> dict | None:
        return _score_single_ticker(ticker, settings, asof_date=asof_date)

    with ThreadPoolExecutor(max_workers=8) as executor:
        scored = list(executor.map(_score, ticker_list))

    candidates = [c for c in scored if c is not None and c.get("composite_score", 0) >= BREAKOUT_MIN_SCORE]
    candidates.sort(key=lambda x: x["composite_score"], reverse=True)
    candidates = candidates[:BREAKOUT_MAX_CANDIDATES]

    elapsed = round(time.perf_counter() - t0, 2)
    logger.info(
        "[BREAKOUT] Historical scan (asof=%s): %d tickers, %d candidates in %.1fs",
        asof_date, len(ticker_list), len(candidates), elapsed,
    )
    return candidates


# ---------------------------------------------------------------------------
# Background asyncio loop — Tiered Scanner
# ---------------------------------------------------------------------------

async def tiered_scanner_loop(settings: Settings) -> None:
    """Asyncio task: orchestrates cold/warm/hot scans at independent intervals.

    Timeline (example with defaults):
    - t=0s:    Cold scan (bootstrap all pools)
    - t=5m:    Hot rescore
    - t=10m:   Hot rescore
    - t=15m:   Hot rescore + Warm rescore
    - t=20m:   Hot rescore
    - ...
    - t=60m:   Hot rescore + Cold scan (discover new candidates)
    """
    cold_interval_s = COLD_INTERVAL_MIN * 60
    warm_interval_s = WARM_INTERVAL_MIN * 60
    hot_interval_s = HOT_INTERVAL_MIN * 60

    logger.info(
        "[BREAKOUT] Tiered scanner started. Cold: %dm, Warm: %dm, Hot: %dm, Min score: %d",
        COLD_INTERVAL_MIN, WARM_INTERVAL_MIN, HOT_INTERVAL_MIN, BREAKOUT_MIN_SCORE,
    )

    loop = asyncio.get_event_loop()

    # Bootstrap: run initial cold scan immediately
    try:
        await loop.run_in_executor(None, run_cold_scan, settings, None)
        logger.info("[BREAKOUT] Bootstrap cold scan complete. Hot: %d, Warm: %d", len(_pool["hot"]), len(_pool["warm"]))
    except Exception as e:
        logger.error("[BREAKOUT] Bootstrap cold scan failed: %s", e)
        _pool["status"] = "error"
        _pool["error"] = str(e)

    # Track time since last scan of each tier
    last_cold = time.monotonic()
    last_warm = time.monotonic()
    last_hot = time.monotonic()

    while True:
        try:
            await asyncio.sleep(hot_interval_s)
        except asyncio.CancelledError:
            logger.info("[BREAKOUT] Tiered scanner cancelled during sleep.")
            break

        now = time.monotonic()

        try:
            # Check which tiers need rescoring (in priority order: cold > warm > hot)
            if now - last_cold >= cold_interval_s:
                await loop.run_in_executor(None, run_cold_scan, settings, None)
                last_cold = now
                last_warm = now  # cold scan effectively rescores everything
                last_hot = now

            elif now - last_warm >= warm_interval_s:
                await loop.run_in_executor(None, run_hot_rescore, settings)
                await loop.run_in_executor(None, run_warm_rescore, settings)
                last_warm = now
                last_hot = now

            else:
                # Just hot rescore
                await loop.run_in_executor(None, run_hot_rescore, settings)
                last_hot = now

        except asyncio.CancelledError:
            logger.info("[BREAKOUT] Tiered scanner cancelled.")
            break
        except Exception as e:
            logger.error("[BREAKOUT] Scan cycle error: %s", e)
            _pool["status"] = "error"
            _pool["error"] = str(e)


# ---------------------------------------------------------------------------
# On-Demand Single-Stock Evaluation & Ticker Search
# ---------------------------------------------------------------------------

def evaluate_stock_breakout(
    ticker: str,
    asof_date: str | None = None,
    force_tier: str | None = None,
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
    from earnings_engine.data.universe import load_market_cap

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

    scored = score_breakout(sym, prices_df, quality_scores, asof_date=asof_date)
    if not scored:
        return {
            "success": False,
            "error": f"Could not compute breakout metrics for {sym}.",
            "ticker": sym,
        }

    scored["company_name"] = company_name
    scored["industry"] = industry
    scored["success"] = True

    # Setup Conviction Tier
    comp_score = scored.get("composite_score", 0)
    if comp_score >= HOT_THRESHOLD:
        tier = "HOT"
        tier_label = "🔥 High Conviction Setup"
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

    # Update active scan pools with freshest calculation
    if force_tier and force_tier.lower() == "hot":
        _pool["hot"][sym] = {"result": scored, "consecutive_low": 0}
        _pool["warm"].pop(sym, None)
        _rebuild_candidates()
    elif force_tier and force_tier.lower() == "warm":
        _pool["warm"][sym] = {"result": scored, "consecutive_low": 0}
        _pool["hot"].pop(sym, None)
        _rebuild_candidates()
    elif sym in _pool["hot"]:
        _pool["hot"][sym]["result"] = scored
        _pool["hot"][sym]["consecutive_low"] = 0
        _rebuild_candidates()
    elif sym in _pool["warm"]:
        _pool["warm"][sym]["result"] = scored
        _pool["warm"][sym]["consecutive_low"] = 0
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
    elif target_tier == "warm":
        _pool["warm"][sym] = {"result": result, "consecutive_low": 0}
        _pool["hot"].pop(sym, None)
    elif target_tier == "cold":
        _pool["hot"].pop(sym, None)
        _pool["warm"].pop(sym, None)
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

    from earnings_engine.data.db import get_db_connection
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


def run_historical_backtest(
    settings: Settings,
    universe: str | None = None,
) -> dict[str, Any]:
    """Run an on-demand historical backtest sweep over the last 90, 75, 60, 45, and 30 days.

    Returns structured stats comparing old vs new outcomes, component effect sizes,
    and performance by score/volume threshold.
    """
    from datetime import datetime, timedelta, timezone
    from concurrent.futures import ThreadPoolExecutor

    t_start = time.perf_counter()
    ticker_list = _resolve_universe_tickers(settings, universe)
    if not ticker_list:
        return {"success": False, "error": "No tickers found in universe."}

    # Standard historical dates
    asof_dates = [
        (datetime.now(timezone.utc) - timedelta(days=d)).strftime("%Y-%m-%d")
        for d in [90, 75, 60, 45, 30]
    ]

    all_results = []

    def _evaluate_date_tickers(date_str: str) -> list[dict[str, Any]]:
        date_results = []
        for ticker in ticker_list:
            try:
                res = _score_single_ticker(ticker, settings, asof_date=date_str)
                if res and res.get("composite_score", 0) >= 25:
                    res["asof_date"] = date_str
                    date_results.append(res)
            except Exception:
                pass
        return date_results

    with ThreadPoolExecutor(max_workers=min(8, len(asof_dates))) as executor:
        batches = list(executor.map(_evaluate_date_tickers, asof_dates))

    for b in batches:
        all_results.extend(b)

    resolved = [r for r in all_results if r.get("breakout_happened") is not None]
    broke = [r for r in resolved if r.get("breakout_happened") is True]
    failed = [r for r in resolved if r.get("breakout_happened") is False]

    total = len(all_results)
    total_resolved = len(resolved)
    total_broke = len(broke)
    total_failed = len(failed)

    win_rate = round(total_broke / total_resolved * 100, 1) if total_resolved else 0.0

    returns = [float(r["realized_return_pct"]) for r in resolved if r.get("realized_return_pct") is not None]
    avg_return = round(float(np.mean(returns)), 2) if returns else 0.0

    broke_returns = [float(r["realized_return_pct"]) for r in broke if r.get("realized_return_pct") is not None]
    failed_returns = [float(r["realized_return_pct"]) for r in failed if r.get("realized_return_pct") is not None]

    avg_broke_return = round(float(np.mean(broke_returns)), 2) if broke_returns else 0.0
    avg_failed_return = round(float(np.mean(failed_returns)), 2) if failed_returns else 0.0

    outcomes_count = {
        "TARGET_HIT": len([r for r in resolved if r.get("outcome") == "TARGET_HIT"]),
        "BREAKOUT_SUCCEEDED": len([r for r in resolved if r.get("outcome") == "BREAKOUT_SUCCEEDED"]),
        "BREAKOUT_RETRACED": len([r for r in resolved if r.get("outcome") == "BREAKOUT_RETRACED"]),
        "STOP_LOSS_HIT": len([r for r in resolved if r.get("outcome") == "STOP_LOSS_HIT"]),
        "NO_BREAKOUT": len([r for r in resolved if r.get("outcome") == "NO_BREAKOUT"]),
    }

    effect_sizes = {}
    fields = [
        ("composite_score", "Composite Score"),
        ("resistance_score", "Resistance Proximity"),
        ("volume_score", "Volume Surge"),
        ("compression_score", "Price Compression"),
        ("momentum_score", "Momentum"),
        ("fundamental_score", "Fundamental Quality"),
        ("pct_from_high", "% from 52W High"),
        ("volume_ratio", "Volume Ratio"),
        ("atr_pct", "ATR %"),
    ]

    for col, label in fields:
        bv = [float(r[col]) for r in broke if r.get(col) is not None]
        fv = [float(r[col]) for r in failed if r.get(col) is not None]
        if bv and fv:
            mean_b = np.mean(bv)
            mean_f = np.mean(fv)
            delta = mean_b - mean_f
            pooled_std = np.std(bv + fv) or 1.0
            es = abs(delta) / pooled_std
            effect_sizes[col] = {
                "label": label,
                "mean_breakout": round(float(mean_b), 2),
                "mean_failed": round(float(mean_f), 2),
                "delta": round(float(delta), 2),
                "effect_size": round(float(es), 3),
                "direction": "HIGHER in breakouts ↑" if delta > 0 else "LOWER in breakouts ↓",
            }

    score_thresholds = {}
    for th in [35, 45, 50, 55, 60, 65, 70]:
        th_res = [r for r in resolved if r.get("composite_score", 0) >= th]
        th_broke = [r for r in th_res if r.get("breakout_happened") is True]
        score_thresholds[str(th)] = {
            "count": len(th_res),
            "broke_count": len(th_broke),
            "win_rate_pct": round(len(th_broke) / len(th_res) * 100, 1) if th_res else 0.0,
        }

    vol_thresholds = {}
    for vr in [1.0, 1.2, 1.5, 2.0]:
        vr_res = [r for r in resolved if (r.get("volume_ratio") or 0) >= vr]
        vr_broke = [r for r in vr_res if r.get("breakout_happened") is True]
        vol_thresholds[f"{vr}x"] = {
            "count": len(vr_res),
            "broke_count": len(vr_broke),
            "win_rate_pct": round(len(vr_broke) / len(vr_res) * 100, 1) if vr_res else 0.0,
        }

    duration = round(time.perf_counter() - t_start, 2)

    return {
        "success": True,
        "universe": universe or "ALL",
        "total_candidates": total,
        "total_evaluated": total_resolved,
        "success_count": total_broke,
        "failed_count": total_failed,
        "win_rate_pct": win_rate,
        "avg_return_pct": avg_return,
        "avg_broke_return_pct": avg_broke_return,
        "avg_failed_return_pct": avg_failed_return,
        "outcomes": outcomes_count,
        "effect_sizes": effect_sizes,
        "score_thresholds": score_thresholds,
        "volume_thresholds": vol_thresholds,
        "duration_s": duration,
        "run_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Legacy compat alias
# ---------------------------------------------------------------------------
breakout_scanner_loop = tiered_scanner_loop

