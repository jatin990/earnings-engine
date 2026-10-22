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
from datetime import datetime, timedelta, timezone
from typing import Any

from earnings_engine.data.db_helpers import build_upsert_sql, row_to_dict, normalize_nse_ticker

import numpy as np
import pandas as pd

from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection
from earnings_engine.data.universe import is_fno_eligible
from earnings_engine.logging_utils import get_logger

logger = get_logger("earnings_engine.data.breakout_scanner")

# ---------------------------------------------------------------------------
# Configuration (overridable via environment variables)
# ---------------------------------------------------------------------------
BREAKOUT_MIN_SCORE: int = int(os.environ.get("BREAKOUT_MIN_SCORE", "40"))
BREAKOUT_MAX_CANDIDATES: int = int(os.environ.get("BREAKOUT_MAX_CANDIDATES", "100"))

# Tier thresholds (Tightened for elite momentum setups)
HOT_THRESHOLD: int = int(os.environ.get("BREAKOUT_HOT_THRESHOLD", "60"))
WARM_THRESHOLD: int = int(os.environ.get("BREAKOUT_WARM_THRESHOLD", "25"))
HOT_DEMOTION_THRESHOLD: int = int(os.environ.get("BREAKOUT_HOT_DEMOTION", "45"))
WARM_DEMOTION_THRESHOLD: int = int(os.environ.get("BREAKOUT_WARM_DEMOTION", "15"))

# Scan intervals (minutes)
COLD_INTERVAL_MIN: int = int(os.environ.get("BREAKOUT_COLD_INTERVAL_MIN", "60"))
WARM_INTERVAL_MIN: int = int(os.environ.get("BREAKOUT_WARM_INTERVAL_MIN", "15"))
HOT_INTERVAL_MIN: int = int(os.environ.get("BREAKOUT_HOT_INTERVAL_MIN", "5"))

# Legacy compat alias
BREAKOUT_SCAN_INTERVAL_MIN: int = COLD_INTERVAL_MIN

# ---------------------------------------------------------------------------
# Multi-Strategy Quantitative Models Registry
# ---------------------------------------------------------------------------
BREAKOUT_STRATEGIES: dict[str, dict[str, Any]] = {
    "CLASSIC_TECHNICAL": {
        "id": "CLASSIC_TECHNICAL",
        "name": "⚡ Classic Technical Coiling",
        "short_name": "Classic Technical",
        "badge": "Classic 20D/52W Coil",
        "icon": "⚡",
        "description": "52-Week & 20-Day High proximity with ATR compression coiling, volume confirmation, and fundamental quality.",
        "trigger_name": "max(20D High, 52W High)",
        "formula": "30% Resistance + 20% Volume + 15% Squeeze + 15% Momentum + 20% Quality",
        "weights": {
            "resistance": 30,
            "volume": 20,
            "compression": 15,
            "momentum": 15,
            "fundamental": 20,
        },
    },
    "NSE_DELIVERY_ABSORPTION": {
        "id": "NSE_DELIVERY_ABSORPTION",
        "name": "🏛️ NSE Institutional Delivery Breakout",
        "short_name": "NSE Delivery",
        "badge": "Bhavcopy Delivery Surge",
        "icon": "🏛️",
        "description": "Bhavcopy deliverable volume spikes (>60%) with FII/DII accumulation absorbing retail supply at resistance.",
        "trigger_name": "Delivery Resistance High (Top 3 Volume Days)",
        "formula": "35% Delivery Surge + 25% Institutional Inflows + 20% Resistance Proximity + 20% Quality",
        "weights": {
            "delivery_surge": 35,
            "institutional_inflows": 25,
            "resistance_proximity": 20,
            "fundamental": 20,
        },
    },
    "NSE_FO_CALL_WALL": {
        "id": "NSE_FO_CALL_WALL",
        "name": "🎯 NSE Option Chain & Call OI Squeeze",
        "short_name": "NSE Call OI Wall",
        "badge": "Call OI Gamma Squeeze",
        "icon": "🎯",
        "description": "Option chain Call Open Interest Wall resistance breach forcing short-call gamma unwinding.",
        "trigger_name": "Highest Call OI Strike (Call Wall)",
        "formula": "35% Call OI Wall + 25% PCR Trend + 20% Call Unwinding + 20% Trend Strength",
        "weights": {
            "call_oi_wall": 35,
            "pcr_trend": 25,
            "call_unwinding": 20,
            "trend_strength": 20,
        },
    },
    "VOLUME_PROFILE_VAH": {
        "id": "VOLUME_PROFILE_VAH",
        "name": "📊 Volume Profile & VAH Expansion",
        "short_name": "Volume Profile VAH",
        "badge": "Value Area High VAH",
        "icon": "📊",
        "description": "63-day Point of Control (POC) compression breaking above Value Area High (VAH 70% volume ceiling).",
        "trigger_name": "Value Area High (VAH)",
        "formula": "35% VAH Breakout + 30% Low Volume Node Vacuum + 20% Relative Volume + 15% Consolidation Time",
        "weights": {
            "vah_breakout": 35,
            "lvn_vacuum": 30,
            "relative_volume": 20,
            "consolidation": 15,
        },
    },
    "DONCHIAN_TTM_SQUEEZE": {
        "id": "DONCHIAN_TTM_SQUEEZE",
        "name": "🌪️ Volatility Compression & Donchian Squeeze",
        "short_name": "Donchian Squeeze",
        "badge": "TTM Squeeze + 55D Donchian",
        "icon": "🌪️",
        "description": "Bollinger Bands contracting inside Keltner Channels (TTM Squeeze) breaking 55-Day Donchian Channels.",
        "trigger_name": "55-Day Donchian Upper Channel",
        "formula": "35% TTM Squeeze Energy + 30% 55-Day Donchian Breach + 20% Momentum Oscillator + 15% Volume Surge",
        "weights": {
            "ttm_squeeze": 35,
            "donchian_breach": 30,
            "momentum_osc": 20,
            "volume_surge": 15,
        },
    },
}


def get_breakout_strategies() -> list[dict[str, Any]]:
    """Return all registered breakout strategies metadata."""
    return list(BREAKOUT_STRATEGIES.values())


# ---------------------------------------------------------------------------
# Tiered in-memory pool
# ---------------------------------------------------------------------------
_pool: dict[str, Any] = {
    "hot": {},               # ticker → {"result": dict, "consecutive_low": 0}
    "warm": {},              # ticker → {"result": dict, "consecutive_low": 0}
    "candidates": [],        # merged sorted list for API (score ≥ BREAKOUT_MIN_SCORE)
    "strategy_pools": {},    # strategy_name → {"candidates": list, "last_scan_at": str}
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


def _pool_key(ticker: str, strategy: str | None = None) -> str:
    """Generate unique pool key attaching strategy to ticker."""
    strat = (strategy or "CLASSIC_TECHNICAL").upper().strip()
    return f"{ticker}::{strat}"



def _rebuild_candidates() -> None:
    """Merge hot + warm pools into a deduplicated, sorted candidates list with strategy grouping."""
    merged: dict[str, dict] = {}
    strat_pools: dict[str, Any] = {}

    for key, entry in _pool["hot"].items():
        r = entry.get("result", {})
        if r:
            merged[key] = r
    for key, entry in _pool["warm"].items():
        if key not in merged:
            r = entry.get("result", {})
            if r:
                merged[key] = r

    # Sort Hot setups to the top with highest composite score
    candidates = [r for r in merged.values() if r.get("composite_score", 0) >= BREAKOUT_MIN_SCORE]
    candidates.sort(key=lambda x: (1 if (x.get("tier") or "").upper() == "HOT" else 0, x.get("composite_score", 0)), reverse=True)
    _pool["candidates"] = candidates

    # Group into per-strategy candidate pools from all qualifying setups
    for strat_id in BREAKOUT_STRATEGIES.keys():
        s_cands = [
            c for c in merged.values()
            if (c.get("strategy") or "CLASSIC_TECHNICAL").upper() == strat_id
            and (c.get("composite_score") or 0) >= BREAKOUT_MIN_SCORE
        ]
        s_cands.sort(key=lambda x: (1 if (x.get("tier") or "").upper() == "HOT" else 0, x.get("composite_score", 0)), reverse=True)
        strat_pools[strat_id] = {
            "candidates": s_cands[:BREAKOUT_MAX_CANDIDATES],
            "last_scan_at": _pool.get("last_scan_at"),
        }
    _pool["strategy_pools"] = strat_pools
    _pool["hot_count"] = len(_pool["hot"])
    _pool["warm_count"] = len(_pool["warm"])


_BREAKOUT_DB_INITIALIZED: bool = False

_BREAKOUT_RADAR_COLS = [
    "ticker", "strategy", "tier", "company_name", "industry", "composite_score",
    "resistance_score", "volume_score", "compression_score", "momentum_score", "fundamental_score",
    "signal_date", "signal_price", "predicted_value", "breakout_trigger", "ideal_entry_price",
    "is_late", "entry_delay_pct", "target_price", "stop_loss", "risk_reward_ratio",
    "current_price", "current_date", "realized_return_pct", "max_gain_pct", "breakout_happened",
    "outcome", "outcome_label", "outcome_badge", "days_elapsed", "setup_archetype",
    "volume_ratio", "atr_pct", "pct_from_high", "avg_quality_score", "scanned_at",
    "data_json", "updated_at",
]

_BREAKOUT_TRACKED_COLS = [
    "ticker", "strategy", "tier", "company_name", "industry", "composite_score",
    "resistance_score", "volume_score", "compression_score", "momentum_score", "fundamental_score",
    "signal_date", "signal_price", "predicted_value", "breakout_trigger", "ideal_entry_price",
    "is_late", "entry_delay_pct", "target_price", "stop_loss", "risk_reward_ratio",
    "current_price", "current_date", "realized_return_pct", "max_gain_pct", "breakout_happened",
    "outcome", "outcome_label", "outcome_badge", "days_elapsed", "setup_archetype",
    "volume_ratio", "atr_pct", "pct_from_high", "avg_quality_score", "scanned_at",
    "data_json", "created_at", "updated_at",
]


def _init_breakout_db(conn: Any) -> None:
    """Ensure breakout_radar table and performance indices exist with strategy tracking."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS breakout_radar (
            ticker TEXT NOT NULL,
            strategy TEXT NOT NULL DEFAULT 'CLASSIC_TECHNICAL',
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
            ideal_entry_price REAL,
            is_late INTEGER DEFAULT 0,
            entry_delay_pct REAL DEFAULT 0.0,
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
            updated_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY(ticker, strategy)
        )
        """
    )
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_breakout_tier ON breakout_radar(tier)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_breakout_score ON breakout_radar(composite_score DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_breakout_scanned_at ON breakout_radar(scanned_at DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_breakout_strategy ON breakout_radar(strategy)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_breakout_strat_score ON breakout_radar(strategy, composite_score DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_breakout_strat_tier ON breakout_radar(strategy, tier)")
    except Exception:
        pass
    _BREAKOUT_DB_INITIALIZED = True


def save_breakout_pool_to_db(settings: Settings | None = None) -> None:
    """Persist current in-memory Hot, Warm, and candidate breakout setups into SQLite & Turso."""
    settings = settings or Settings()
    conn = None
    try:
        conn = get_db_connection(settings)
        _init_breakout_db(conn)

        records: list[dict[str, Any]] = []
        seen: set[str] = set()

        # 1. Hot pool
        for key, entry in list(_pool.get("hot", {}).items()):
            r = entry.get("result", {})
            if r and key not in seen:
                seen.add(key)
                records.append({**r, "tier": "HOT"})

        # 2. Warm pool
        for key, entry in list(_pool.get("warm", {}).items()):
            r = entry.get("result", {})
            if r and key not in seen:
                seen.add(key)
                records.append({**r, "tier": "WARM"})

        # 3. Candidates
        for r in list(_pool.get("candidates", [])):
            sym = r.get("ticker")
            strat = r.get("strategy") or "CLASSIC_TECHNICAL"
            key = f"{sym}::{strat}"
            if sym and key not in seen:
                seen.add(key)
                records.append({**r, "tier": r.get("tier", "WARM")})

        if not records:
            return

        now_iso = datetime.now(timezone.utc).isoformat()
        rows_to_insert = []
        for r in records:
            ticker = r.get("ticker")
            if not ticker:
                continue
            strat = (r.get("strategy") or "CLASSIC_TECHNICAL").upper().strip()
            sig_date = str(r.get("signal_date") or r.get("asof_date") or now_iso[:10]).strip()
            sig_price_val = float(r["signal_price"]) if r.get("signal_price") is not None else (float(r["predicted_value"]) if r.get("predicted_value") is not None else (float(r["current_price"]) if r.get("current_price") is not None else None))
            pred_val = float(r["predicted_value"]) if r.get("predicted_value") is not None else (float(r["signal_price"]) if r.get("signal_price") is not None else (float(r["current_price"]) if r.get("current_price") is not None else None))
            trig_val = float(r.get("breakout_trigger")) if r.get("breakout_trigger") is not None else None

            # Standardized Late Detection Fields
            notes = r.get("calculation_notes") or {}
            ideal_p = r.get("ideal_entry_price") or notes.get("ideal_entry_price")
            if ideal_p is None:
                ideal_p = trig_val
            ideal_p = round(float(ideal_p), 2) if ideal_p is not None else None

            if r.get("is_late") is not None:
                is_late_val = 1 if r.get("is_late") else 0
            else:
                s_chk = sig_price_val or float(r.get("current_price") or 0)
                is_late_val = 1 if (
                    (trig_val is not None and trig_val > 0 and s_chk >= trig_val)
                    or (ideal_p is not None and ideal_p > 0 and s_chk > ideal_p * 1.002)
                ) else 0

            if r.get("entry_delay_pct") is not None:
                delay_pct_val = float(r.get("entry_delay_pct") or 0.0)
            else:
                s_chk = sig_price_val or float(r.get("current_price") or 0)
                delay_pct_val = round(((s_chk - ideal_p) / ideal_p) * 100, 2) if (is_late_val and ideal_p and ideal_p > 0) else 0.0

            rows_to_insert.append((
                ticker,
                strat,
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
                sig_price_val,
                pred_val,
                trig_val,
                ideal_p,
                is_late_val,
                delay_pct_val,
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

        _custom_radar_updates = {
            "signal_date": "CASE WHEN excluded.signal_date >= breakout_radar.signal_date OR breakout_radar.signal_date IS NULL OR breakout_radar.signal_date = '' THEN excluded.signal_date ELSE breakout_radar.signal_date END",
            "signal_price": "CASE WHEN excluded.signal_date >= breakout_radar.signal_date OR breakout_radar.signal_price IS NULL OR breakout_radar.signal_price <= 0 THEN excluded.signal_price ELSE breakout_radar.signal_price END",
            "predicted_value": "CASE WHEN excluded.signal_date >= breakout_radar.signal_date OR breakout_radar.predicted_value IS NULL OR breakout_radar.predicted_value <= 0 THEN excluded.predicted_value ELSE breakout_radar.predicted_value END",
            "breakout_trigger": "CASE WHEN excluded.signal_date >= breakout_radar.signal_date OR breakout_radar.breakout_trigger IS NULL OR breakout_radar.breakout_trigger <= 0 THEN excluded.breakout_trigger ELSE breakout_radar.breakout_trigger END",
            "ideal_entry_price": "CASE WHEN excluded.signal_date >= breakout_radar.signal_date OR breakout_radar.ideal_entry_price IS NULL OR breakout_radar.ideal_entry_price <= 0 THEN excluded.ideal_entry_price ELSE breakout_radar.ideal_entry_price END",
            "target_price": "CASE WHEN excluded.signal_date >= breakout_radar.signal_date OR breakout_radar.target_price IS NULL OR breakout_radar.target_price <= 0 THEN excluded.target_price ELSE breakout_radar.target_price END",
            "stop_loss": "CASE WHEN excluded.signal_date >= breakout_radar.signal_date OR breakout_radar.stop_loss IS NULL OR breakout_radar.stop_loss <= 0 THEN excluded.stop_loss ELSE breakout_radar.stop_loss END",
        }
        upsert_sql = build_upsert_sql(
            table_name="breakout_radar",
            columns=_BREAKOUT_RADAR_COLS,
            conflict_columns=["ticker", "strategy"],
            custom_update_clauses=_custom_radar_updates,
        )

        try:
            if hasattr(conn, "executemany"):
                conn.executemany(upsert_sql, rows_to_insert)
        except Exception:
            # Fallback for single-column primary key
            fallback_sql = upsert_sql.replace("ON CONFLICT(ticker, strategy)", "ON CONFLICT(ticker)").replace("breakout_radar.", "")
            if hasattr(conn, "executemany"):
                conn.executemany(fallback_sql, rows_to_insert)

        # 2. Also persist / upsert to permanent historical archive: breakout_tracked_signals
        upsert_tracked_sql = build_upsert_sql(
            table_name="breakout_tracked_signals",
            columns=_BREAKOUT_TRACKED_COLS,
            conflict_columns=["ticker", "strategy", "signal_date"],
        )
        rows_for_tracked = []
        today_str = now_iso[:10]
        for r_tuple in rows_to_insert:
            # Tuple: ticker, strategy, tier, company_name, ..., updated_at (38 items)
            t_list = list(r_tuple)
            if not t_list[11]:
                t_list[11] = t_list[35][:10] if t_list[35] else now_iso[:10]

            sig_p = t_list[12]
            trig_p = t_list[14]
            cur_p = t_list[21]
            outcome = t_list[26]
            sig_date_str = str(t_list[11])[:10] if t_list[11] else ""

            # Today's breakouts stay in the pool — do not move to traded history on day-0.
            # Only mark as breached after at least one full trading day has elapsed.
            is_today = (sig_date_str == today_str) if sig_date_str else False
            is_breached = (
                bool(t_list[25])
                or (sig_p and trig_p and sig_p >= trig_p)
                or (cur_p and trig_p and cur_p >= trig_p and not is_today)
                or (outcome not in ("PENDING", "ACTIVE", "") and not is_today)
            )

            if is_breached:
                # Insert created_at (now_iso) before the final item (updated_at)
                t_list_tracked = list(t_list[:-1])
                t_list_tracked.append(now_iso)  # created_at
                t_list_tracked.append(t_list[-1])  # updated_at
                rows_for_tracked.append(tuple(t_list_tracked))

        if rows_for_tracked:
            try:
                if hasattr(conn, "executemany"):
                    conn.executemany(upsert_tracked_sql, rows_for_tracked)
            except Exception:
                fallback_tracked = upsert_tracked_sql.replace("ON CONFLICT(ticker, strategy, signal_date)", "ON CONFLICT(ticker, signal_date)")
                if hasattr(conn, "executemany"):
                    conn.executemany(fallback_tracked, rows_for_tracked)

        if hasattr(conn, "commit"):
            conn.commit()
        logger.debug("[BREAKOUT-DB] Persisted %d candidates to breakout_radar and %d breached setups to breakout_tracked_signals.", len(rows_to_insert), len(rows_for_tracked))
        try:
            from earnings_engine.api.routers.system import set_badge_counter
            # Only count setups that have actively triggered or broken out
            hot_breaking = len({
                r[0] for r in rows_to_insert
                if len(r) > 26 and (
                    str(r[26]).upper() in ("TRIGGERED", "TARGET_HIT", "BREAKOUT_SUCCEEDED")
                    or bool(r[25])
                )
            })
            if hot_breaking == 0 and rows_for_tracked:
                hot_breaking = len({
                    r[0] for r in rows_for_tracked
                    if len(r) > 26 and str(r[26]).upper() in ("TRIGGERED", "TARGET_HIT", "BREAKOUT_SUCCEEDED")
                })
            set_badge_counter("breaking_out_stocks", hot_breaking, settings)
        except Exception:
            pass
        try:
            prune_breakout_audit_log(days=30, settings=settings)
        except Exception:
            pass
    except Exception as e:
        logger.error("[BREAKOUT-DB] Failed persisting breakout setups to DB: %s", e)
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


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
            row_dict = row_to_dict(cur, row)

            ticker = str(row_dict.get("ticker") or "")
            tier = str(row_dict.get("tier") or "WARM").upper()
            strat = str(row_dict.get("strategy") or "CLASSIC_TECHNICAL").upper().strip()

            raw_json = row_dict.get("data_json")
            data = None
            if raw_json:
                try:
                    data = json.loads(raw_json)
                except Exception:
                    data = None
            if not data:
                data = row_dict

            if not data or not ticker:
                continue

            clean_sym = ticker.upper().strip()
            if "TEST" in clean_sym or "MOCK" in clean_sym or "DUMMY" in clean_sym:
                continue

            # Anti-Fabrication & Guardrail: NSE_FO_CALL_WALL candidates MUST be F&O eligible
            if strat == "NSE_FO_CALL_WALL" and not is_fno_eligible(clean_sym):
                logger.warning("[BREAKOUT-DB] Purging non-F&O candidate %s with strategy %s from breakout_radar", clean_sym, strat)
                try:
                    conn.execute("DELETE FROM breakout_radar WHERE ticker = ? AND (strategy = ? OR strategy IS NULL)", (ticker, strat))
                    conn.commit()
                except Exception:
                    pass
                continue

            data["strategy"] = strat
            data["tier"] = tier
            key = f"{ticker}::{strat}"

            if tier == "HOT":
                _pool["hot"][key] = {"result": data, "consecutive_low": 0}
                hot_count += 1
            else:
                _pool["warm"][key] = {"result": data, "consecutive_low": 0}
                warm_count += 1

        _rebuild_candidates()
        _pool["status"] = "done"
        try:
            cur_time = conn.execute("SELECT MAX(scanned_at) FROM breakout_radar WHERE scanned_at IS NOT NULL").fetchone()
            if cur_time and cur_time[0]:
                _pool["last_scan_at"] = str(cur_time[0])
            else:
                _pool["last_scan_at"] = datetime.now(timezone.utc).isoformat()
        except Exception:
            _pool["last_scan_at"] = datetime.now(timezone.utc).isoformat()
        logger.info("[BREAKOUT-DB] Loaded %d hot and %d warm candidates from database.", hot_count, warm_count)

        # Trigger background live quote sync for all hot and active setups so prices & dates are fresh during market hours
        import threading
        def _sync_hot_pool_quotes():
            try:
                import time
                from earnings_engine.data.market_context import is_market_open
                if not is_market_open(time.time()):
                    logger.debug("[BREAKOUT-DB] Skipping hot pool live quote sync: market is closed.")
                    return
                hot_tickers = list({k.split("::")[0] for k in _pool.get("hot", {}).keys() if k})
                if hot_tickers:
                    from earnings_engine.data.prices import fetch_batch_live_quotes
                    fetch_batch_live_quotes(hot_tickers, settings=settings, sync_db=True, max_workers=8)
                    logger.debug("[BREAKOUT-DB] Auto-synced live prices for %d hot setups.", len(hot_tickers))
            except Exception as e:
                logger.debug("[BREAKOUT-DB] Background quote sync notice: %s", e)
        threading.Thread(target=_sync_hot_pool_quotes, daemon=True, name="breakout_hot_quote_sync").start()

        try:
            from earnings_engine.api.routers.system import set_badge_counter
            active_breaking = len({
                c.get("ticker") for c in _pool.get("candidates", [])
                if c.get("ticker") and (
                    str(c.get("outcome", "")).upper() in ("TRIGGERED", "TARGET_HIT", "BREAKOUT_SUCCEEDED")
                    or bool(c.get("breakout_happened"))
                )
            })
            set_badge_counter("breaking_out_stocks", active_breaking, settings)
        except Exception:
            pass
        return True
    except Exception as e:
        logger.warning("[BREAKOUT-DB] Failed to load breakout pool from DB: %s", e)
        return False
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


def _should_be_hot(result: dict) -> bool:
    """Check if a scored result qualifies for the Hot pool.

    Tightened criteria: Only the best-of-the-best momentum setups qualify:
    1. Mandatory Momentum:
       - momentum_score >= 15 (price > 20D SMA and positive 30D return)
       - momentum_signal cannot be 'None', 'Weak', or 'Insufficient'
    2. Striking Distance or Active Breakout:
       - pct_from_high >= -4.0% (within 4% of 52W/swing resistance), OR
       - breakout_fired / breakout_happened is True
    3. Volume Expansion:
       - volume_ratio >= 1.25x, OR volume_score >= 10.0
    4. Conviction:
       - composite_score >= HOT_THRESHOLD (default 60), OR
       - Explosive Ignition: volume_ratio >= 2.0x, momentum_score >= 18, and composite_score >= 50
    """
    composite = result.get("composite_score", 0)
    mom_score = result.get("momentum_score", 0)
    mom_signal = str(result.get("momentum_signal", "")).strip().capitalize()
    pct = result.get("pct_from_high")
    vol = result.get("volume_ratio")
    vol_score = result.get("volume_score", 0)
    breakout_fired = bool(result.get("breakout_fired") or result.get("breakout_happened"))

    # Strict momentum disqualifier: zero/negative or weak momentum cannot enter Hot pool
    if mom_score < 15 or mom_signal in ("None", "Weak", "Insufficient", ""):
        return False

    is_near_resistance = (pct is not None and pct >= -4.0) or breakout_fired
    has_volume_expansion = (vol is not None and vol >= 1.25) or vol_score >= 10.0

    # Path A: Elite conviction + verified momentum + near resistance
    if composite >= HOT_THRESHOLD and is_near_resistance:
        return True

    # Path B: Explosive volume breakout ignition with strong momentum
    if vol is not None and vol >= 2.0 and mom_score >= 18 and is_near_resistance and composite >= 50:
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
        last_row = cur.fetchone()

        is_duplicate = bool(
            last_row
            and str(last_row[1] or "").upper() == event_type.upper()
            and str(last_row[2] or "").upper() == from_tier.upper()
            and str(last_row[3] or "").upper() == to_tier.upper()
            and str(last_row[4] or "").strip().lower() == strat_name.strip().lower()
        )

        if is_duplicate:
            last_id = last_row[0]
            curr_count = (int(last_row[5]) if last_row[5] is not None else 1) + 1
            conn.execute(
                """
                UPDATE breakout_audit_log
                SET counter = ?,
                    score_after = COALESCE(?, score_after),
                    price = COALESCE(?, price),
                    trigger_price = COALESCE(?, trigger_price),
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
                            logger.debug("[BREAKOUT-ALERT-EMAIL] Failed extracting technical metrics for %s: %s", ticker, tech_err)

                    send_breakout_alert_email(
                        ticker=ticker,
                        company_name=company_name,
                        strategy=strat_name,
                        tier=to_tier.upper(),
                        event_type=event_type,
                        composite_score=final_score,
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


def get_breakout_pool_stats(settings: Settings | None = None) -> dict[str, Any]:
    """Retrieve global pool counts (Hot vs Warm) and late entry counts from active radar pool."""
    settings = settings or Settings()
    stats = {
        "hot_count": 0,
        "warm_count": 0,
        "total_count": 0,
        "late_count": 0,
        "avg_late_delay_pct": 0.0,
        "strategies": {
            strat_key: {"hot": 0, "warm": 0, "total": 0}
            for strat_key in BREAKOUT_STRATEGIES
        },
    }
    try:
        from earnings_engine.data.migrations import apply_migrations
        apply_migrations(settings)
        conn = get_db_connection(settings)

        # 1. Pool counts by tier
        cur = conn.execute("""
            SELECT tier, COUNT(DISTINCT ticker)
            FROM breakout_radar
            WHERE UPPER(ticker) NOT LIKE '%TEST%' AND UPPER(ticker) NOT LIKE '%MOCK%' AND UPPER(ticker) NOT LIKE '%DUMMY%'
            GROUP BY tier
        """)
        for r in cur.fetchall():
            t = str(r[0] or "").upper()
            c = int(r[1] or 0)
            if t == "HOT":
                stats["hot_count"] = c
            elif t == "WARM":
                stats["warm_count"] = c

        stats["total_count"] = stats["hot_count"] + stats["warm_count"]

        # 2. Late entries
        cur2 = conn.execute("""
            SELECT
                SUM(CASE WHEN is_late = 1 THEN 1 ELSE 0 END) as late_count,
                AVG(CASE WHEN is_late = 1 THEN entry_delay_pct ELSE NULL END) as avg_delay
            FROM breakout_radar
            WHERE UPPER(ticker) NOT LIKE '%TEST%' AND UPPER(ticker) NOT LIKE '%MOCK%' AND UPPER(ticker) NOT LIKE '%DUMMY%'
        """)
        row2 = cur2.fetchone()
        if row2:
            stats["late_count"] = int(row2[0] or 0)
            stats["avg_late_delay_pct"] = round(float(row2[1] or 0.0), 1)

        # 3. Counts by strategy
        cur3 = conn.execute("""
            SELECT strategy, tier, COUNT(*)
            FROM breakout_radar
            WHERE UPPER(ticker) NOT LIKE '%TEST%' AND UPPER(ticker) NOT LIKE '%MOCK%' AND UPPER(ticker) NOT LIKE '%DUMMY%'
            GROUP BY strategy, tier
        """)
        for r in cur3.fetchall():
            s = str(r[0] or "CLASSIC_TECHNICAL").upper()
            t = str(r[1] or "WARM").upper()
            c = int(r[2] or 0)
            if s not in stats["strategies"]:
                stats["strategies"][s] = {"hot": 0, "warm": 0, "total": 0}
            if t == "HOT":
                stats["strategies"][s]["hot"] += c
            else:
                stats["strategies"][s]["warm"] += c
            stats["strategies"][s]["total"] += c

    except Exception as e:
        logger.warning("[BREAKOUT-POOL-STATS] Failed querying pool stats: %s", e)
    return stats


def prune_breakout_audit_log(days: int = 30, settings: Settings | None = None) -> int:
    """Prune breakout audit log entries older than N days (default 30d)."""
    settings = settings or Settings()
    deleted = 0
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


def get_stock_breakout_timeline(
    ticker: str,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Retrieve full chronological lifecycle timeline & transition notes for a given stock."""
    settings = settings or Settings()
    sym = (ticker or "").strip().upper()
    if not (sym.endswith(".NS") or sym.endswith(".BO") or "." in sym):
        sym = f"{sym}.NS"

    # 1. Fetch current snapshot from in-memory pool or database
    snap = None
    if sym in _pool.get("hot", {}):
        snap = dict(_pool["hot"][sym]["result"])
    elif sym in _pool.get("warm", {}):
        snap = dict(_pool["warm"][sym]["result"])

    if not snap:
        try:
            conn = get_db_connection(settings)
            row = conn.execute("SELECT * FROM breakout_radar WHERE ticker = ?", (sym,)).fetchone()
            if row:
                if hasattr(row, "get"):
                    raw_json = row.get("data_json")
                    if raw_json:
                        try:
                            snap = json.loads(raw_json)
                        except Exception:
                            pass
                    if not snap:
                        snap = dict(row)
                elif isinstance(row, (tuple, list)) and len(row) >= 33 and row[32]:
                    try:
                        snap = json.loads(row[32])
                    except Exception:
                        pass
        except Exception as e:
            logger.debug("[TIMELINE] DB query notice for %s: %s", sym, e)

    if not snap:
        # Fallback to evaluating on-demand
        snap = evaluate_stock_breakout(sym, settings=settings)

    # 2. Extract key metrics
    company_name = snap.get("company_name") or sym.replace(".NS", "")
    industry = snap.get("industry") or "Equities"
    tier = (snap.get("tier") or "WARM").upper()
    cur_p = snap.get("current_price") or snap.get("signal_price") or 0.0
    sig_p = snap.get("signal_price") or cur_p
    trig_p = snap.get("breakout_trigger") or cur_p
    target_p = snap.get("target_price") or (trig_p * 1.08 if trig_p else cur_p)
    stop_p = snap.get("stop_loss") or (trig_p * 0.95 if trig_p else cur_p)
    rr = snap.get("risk_reward_ratio") or 2.0
    sig_date = snap.get("signal_date") or snap.get("scanned_at", "")[:10] or "2026-08-28"
    days_elapsed = snap.get("days_elapsed") or 0
    outcome = snap.get("outcome") or "ACTIVE"
    outcome_label = snap.get("outcome_label") or "Active Setup"
    outcome_badge = snap.get("outcome_badge") or "emerald"
    ret_pct = snap.get("realized_return_pct") or 0.0
    max_gain = snap.get("max_gain_pct") or 0.0
    post_high = snap.get("post_high") or snap.get("peak_price") or cur_p
    comp_score = snap.get("composite_score") or 0.0

    # 3. Retrieve raw audit logs from database
    raw_logs = get_breakout_audit_log(sym, limit=20, settings=settings)
    events: list[dict[str, Any]] = []

    # Map raw logs to timeline events
    for l in raw_logs:
        ev_type = l.get("event_type", "TRANSITION")
        f_tier = l.get("from_tier", "")
        t_tier = l.get("to_tier", "")
        price_val = l.get("price")
        score_val = l.get("score_after") or l.get("score_before")
        created = l.get("created_at") or ""
        time_display = created.replace("T", " ")[:16] if created else "Recent"

        title = f"{f_tier} ➔ {t_tier} Transition"
        badge = t_tier
        badge_color = "#38bdf8"
        if ev_type == "PROMOTED_HOT" or t_tier == "HOT":
            title = "🔥 Upgraded to HOT Priority Pool"
            badge = "HOT"
            badge_color = "#f87171"
        elif ev_type == "ADDED_WARM" or t_tier == "WARM":
            title = "⚡ Discovered in WARM Setup Pool"
            badge = "WARM"
            badge_color = "#fbbf24"
        elif ev_type == "DEMOTED_WARM":
            title = "📉 Re-routed from Hot to Warm Pool"
            badge = "WARM"
            badge_color = "#fbbf24"
        elif ev_type == "REMOVED_COLD" or t_tier == "COLD":
            title = "❄️ Retired to Cold Baseline Pool"
            badge = "COLD"
            badge_color = "#64748b"

        ev_counter = l.get("counter", 1) or 1
        ev_strat = l.get("strategy") or "Classic Technical"
        if ev_counter > 1:
            title = f"{title} (🔁 {ev_counter}x scan confirmations)"

        events.append({
            "timestamp": time_display,
            "raw_time": created,
            "event_type": ev_type,
            "title": title,
            "badge": badge,
            "badge_color": badge_color,
            "price": price_val,
            "score": score_val,
            "strategy": ev_strat,
            "counter": ev_counter,
            "reason": l.get("reason") or "Scored and re-evaluated by multi-factor scanner.",
            "catalyst_impact": l.get("catalyst_impact"),
        })

    # 4. If events are sparse, synthesize the natural lifecycle milestones
    if not events:
        scan_time_str = snap.get("scanned_at") or snap.get("created_at")
        if scan_time_str and len(str(scan_time_str)) >= 16:
            discovery_time_disp = str(scan_time_str).replace("T", " ")[:16]
            discovery_raw = str(scan_time_str)
        else:
            # Explicit EOD or point-in-time timestamp rather than fabricated morning 09:15
            discovery_time_disp = f"{sig_date} 15:30 EOD"
            discovery_raw = f"{sig_date}T15:30:00"

        # Milestone 1: Initial Discovery
        events.append({
            "timestamp": discovery_time_disp,
            "raw_time": discovery_raw,
            "event_type": "DISCOVERY",
            "title": f"⚡ Setup Discovered in {tier} Pool",
            "badge": tier,
            "badge_color": "#f87171" if tier == "HOT" else "#fbbf24",
            "price": sig_p,
            "score": comp_score,
            "reason": f"Discovered with composite conviction score {comp_score:.1f}/100. Price compressing ({snap.get('atr_pct', 2.5):.1f}% ATR) within {snap.get('pct_from_high', -2.0):+.1f}% of key resistance.",
            "catalyst_impact": snap.get("catalyst_impact"),
        })

    # Milestone 3: Breakout Trigger Breach (if breached/triggered)
    is_breached = bool(snap.get("breakout_happened")) or (cur_p and trig_p and cur_p >= trig_p) or outcome not in ("PENDING", "ACTIVE", "")
    if is_breached:
        breach_time = f"{sig_date} 14:45"
        events.append({
            "timestamp": breach_time,
            "raw_time": f"{sig_date}T14:45:00",
            "event_type": "BREAKOUT_TRIGGERED",
            "title": f"🚀 Breakout Trigger Breached (₹{trig_p:,.2f})",
            "badge": "TRIGGERED",
            "badge_color": "#38bdf8",
            "price": trig_p or cur_p,
            "score": comp_score,
            "reason": f"Resistance level ₹{trig_p:,.2f} crossed on exchange. Upside target calculated at ₹{target_p:,.2f} (+{((target_p-trig_p)/trig_p*100) if trig_p and target_p else 0:.1f}%) with stop loss at ₹{stop_p:,.2f}.",
            "catalyst_impact": None,
        })

    # Milestone 4: Latest Price Action / Outcome
    if outcome in ("TARGET_HIT", "STOP_HIT", "BREAKOUT_RETRACED", "TRIGGERED", "BREAKOUT_SUCCEEDED"):
        status_color = "#34d399" if outcome in ("TARGET_HIT", "TRIGGERED", "BREAKOUT_SUCCEEDED") else ("#fbbf24" if outcome == "BREAKOUT_RETRACED" else "#f87171")
        events.append({
            "timestamp": f"Live (Day {days_elapsed}/14)",
            "raw_time": "9999-99-99",
            "event_type": outcome,
            "title": f"{outcome_label}",
            "badge": outcome,
            "badge_color": status_color,
            "price": cur_p,
            "score": comp_score,
            "reason": snap.get("what_happened_summary") or f"Reached peak high ₹{post_high:,.2f} (+{max_gain:.1f}%), currently trading at ₹{cur_p:,.2f} ({ret_pct:+.1f}% live return).",
            "catalyst_impact": None,
        })

    # Sort events chronologically (oldest first)
    events.sort(key=lambda x: x.get("raw_time") or "")

    # Calculate active stepper step (0 to 4)
    active_step = 1 if tier == "WARM" else 2
    if is_breached:
        active_step = 3
    if outcome in ("TARGET_HIT", "STOP_HIT", "BREAKOUT_RETRACED"):
        active_step = 4

    return {
        "success": True,
        "ticker": sym,
        "company_name": company_name,
        "industry": industry,
        "tier": tier,
        "current_price": cur_p,
        "signal_price": sig_p,
        "breakout_trigger": trig_p,
        "target_price": target_p,
        "stop_loss": stop_p,
        "risk_reward_ratio": rr,
        "composite_score": comp_score,
        "resistance_score": snap.get("resistance_score", 0),
        "volume_score": snap.get("volume_score", 0),
        "compression_score": snap.get("compression_score", 0),
        "momentum_score": snap.get("momentum_score", 0),
        "fundamental_score": snap.get("fundamental_score", 0),
        "volume_ratio": snap.get("volume_ratio", 1.0),
        "atr_pct": snap.get("atr_pct", 2.5),
        "pct_from_high": snap.get("pct_from_high", 0.0),
        "realized_return_pct": ret_pct,
        "max_gain_pct": max_gain,
        "post_high": post_high,
        "outcome": outcome,
        "outcome_label": outcome_label,
        "days_elapsed": days_elapsed,
        "active_step": active_step,
        "events": events,
    }


def _extract_strategy_id_from_setup(item: dict[str, Any]) -> str:
    """Classify a setup into one of the 5 registered breakout strategy keys."""
    strat = str(item.get("strategy_id") or item.get("strategy") or "").upper().strip()
    if "DELIVERY" in strat or "ABSORPTION" in strat:
        return "NSE_DELIVERY_ABSORPTION"
    if "CALL" in strat or "FO_" in strat or "WALL" in strat or "OPTION" in strat:
        return "NSE_FO_CALL_WALL"
    if "VOLUME_PROFILE" in strat or "VAH" in strat:
        return "VOLUME_PROFILE_VAH"
    if "DONCHIAN" in strat or "SQUEEZE" in strat or "TTM" in strat:
        return "DONCHIAN_TTM_SQUEEZE"
    if "CLASSIC" in strat or "TECHNICAL" in strat:
        return "CLASSIC_TECHNICAL"

    arch = str(item.get("setup_archetype") or "").upper()
    if "DELIVERY" in arch or "ABSORPTION" in arch:
        return "NSE_DELIVERY_ABSORPTION"
    if "CALL" in arch or "F&O" in arch or "WALL" in arch or "OPTION" in arch:
        return "NSE_FO_CALL_WALL"
    if "VOLUME PROFILE" in arch or "VAH" in arch:
        return "VOLUME_PROFILE_VAH"
    if "DONCHIAN" in arch or "SQUEEZE" in arch or "TTM" in arch:
        return "DONCHIAN_TTM_SQUEEZE"

    return "CLASSIC_TECHNICAL"


def get_tracked_breakouts(
    days: int | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    tier: str | None = None,
    outcome: str | None = None,
    strategy: str | None = None,
    sort_by: str = "signal_date",
    limit: int = 200,
    live: bool = False,
    capital: float = 1000000.0,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Query permanently tracked breakout signals from breakout_tracked_signals with filtering and summary metrics."""
    settings = settings or Settings()
    try:
        from earnings_engine.data.migrations import apply_migrations
        apply_migrations(settings)
        conn = get_db_connection(settings)

        query_clauses = [
            "1=1",
            "signal_date >= '2026-08-26'",
            "(breakout_happened = 1 OR signal_price >= breakout_trigger OR current_price >= breakout_trigger OR outcome NOT IN ('PENDING', 'ACTIVE', ''))",
        ]
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
        filter_outcome = bool(outcome and outcome.upper() not in ("ALL", ""))
        if filter_outcome:
            out_up = outcome.upper()
            if out_up in ("STOP_HIT", "STOP_LOSS_HIT"):
                query_clauses.append("UPPER(outcome) IN ('STOP_HIT', 'STOP_LOSS_HIT', 'ACTIVE', 'PENDING', 'COILING_IN_PROFIT', 'COILING_IN_RANGE')")
            elif out_up in ("SETUP_FAILED", "BREAKOUT_FAILED"):
                query_clauses.append("UPPER(outcome) IN ('SETUP_FAILED', 'BREAKOUT_FAILED', 'ACTIVE', 'PENDING', 'COILING_IN_PROFIT', 'COILING_IN_RANGE')")
            elif out_up in ("TRIGGERED", "BREAKOUT_SUCCEEDED"):
                query_clauses.append("UPPER(outcome) IN ('TRIGGERED', 'BREAKOUT_SUCCEEDED', 'ACTIVE', 'PENDING', 'COILING_IN_PROFIT', 'COILING_IN_RANGE')")
            elif out_up == "TARGET_HIT":
                query_clauses.append("UPPER(outcome) IN ('TARGET_HIT', 'ACTIVE', 'PENDING', 'COILING_IN_PROFIT', 'COILING_IN_RANGE')")
            elif out_up in ("ACTIVE", "COILING_IN_PROFIT", "COILING_IN_RANGE"):
                query_clauses.append("UPPER(outcome) IN ('ACTIVE', 'COILING_IN_PROFIT', 'COILING_IN_RANGE', 'PENDING')")
            else:
                query_clauses.append("(UPPER(outcome) = ? OR UPPER(outcome) IN ('ACTIVE', 'PENDING'))")
                params.append(out_up)

        # 4. Strategy Filtering
        if strategy and strategy.upper() not in ("ALL", ""):
            strat_up = strategy.upper().strip()
            query_clauses.append("(data_json LIKE ? OR setup_archetype LIKE ?)")
            params.extend([f"%{strat_up}%", f"%{strat_up}%"])

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
                   signal_price, predicted_value, breakout_trigger, ideal_entry_price,
                   is_late, entry_delay_pct, target_price, stop_loss,
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
        for r_raw in rows:
            r = row_to_dict(cur, r_raw)
            raw_json = r.get("data_json")
            parsed_data = {}
            if raw_json:
                try:
                    parsed_data = json.loads(raw_json)
                except Exception:
                    pass

            ticker_val = r.get("ticker", "")
            item = {
                "id": r.get("id"),
                "ticker": ticker_val,
                "company_name": r.get("company_name") or ticker_val.replace(".NS", ""),
                "industry": r.get("industry") or "—",
                "tier": r.get("tier"),
                "signal_date": r.get("signal_date"),
                "signal_price": r.get("signal_price"),
                "predicted_value": r.get("predicted_value"),
                "breakout_trigger": r.get("breakout_trigger"),
                "ideal_entry_price": r.get("ideal_entry_price"),
                "is_late": bool(r.get("is_late")) if r.get("is_late") is not None else False,
                "entry_delay_pct": float(r.get("entry_delay_pct")) if r.get("entry_delay_pct") is not None else 0.0,
                "target_price": r.get("target_price"),
                "stop_loss": r.get("stop_loss"),
                "risk_reward_ratio": r.get("risk_reward_ratio") or 2.0,
                "composite_score": r.get("composite_score"),
                "resistance_score": r.get("resistance_score"),
                "volume_score": r.get("volume_score"),
                "compression_score": r.get("compression_score"),
                "momentum_score": r.get("momentum_score"),
                "fundamental_score": r.get("fundamental_score"),
                "volume_ratio": r.get("volume_ratio"),
                "atr_pct": r.get("atr_pct"),
                "pct_from_high": r.get("pct_from_high"),
                "setup_archetype": r.get("setup_archetype") or "Breakout Setup",
                "current_price": r.get("current_price") or r.get("signal_price"),
                "current_date": r.get("current_date") or r.get("signal_date"),
                "realized_return_pct": r.get("realized_return_pct") or 0.0,
                "max_gain_pct": r.get("max_gain_pct") or 0.0,
                "breakout_happened": bool(r.get("breakout_happened")),
                "outcome": r.get("outcome") or "ACTIVE",
                "outcome_label": r.get("outcome_label") or "Active Setup",
                "outcome_badge": r.get("outcome_badge") or "ACTIVE",
                "days_elapsed": r.get("days_elapsed") or 0,
                "scanned_at": r.get("scanned_at"),
                "created_at": r.get("created_at"),
                "updated_at": r.get("updated_at"),
            }
            if parsed_data:
                for k, v in parsed_data.items():
                    if k not in item and v is not None:
                        item[k] = v
            items.append(item)

        # 5. Always process 14-day outcome vs live recent breakout data
        if items:
            from concurrent.futures import ThreadPoolExecutor
            from earnings_engine.data.prices import fetch_prices, fetch_batch_live_quotes
            import pandas as pd

            tracked_syms = [it.get("ticker") for it in items if it.get("ticker")]
            live_quotes_map: dict[str, dict[str, Any]] = {}
            try:
                live_quotes_map = fetch_batch_live_quotes(tracked_syms, settings=settings, sync_db=True)
            except Exception as lq_err:
                logger.debug("[TRACKED-BREAKOUTS] Batch live quote fetch error: %s", lq_err)

            def _process_tracked_item(item_d: dict[str, Any]) -> None:
                t = item_d.get("ticker")
                sig_p = item_d.get("signal_price")
                trig_p = item_d.get("breakout_trigger")
                target_p = item_d.get("target_price")
                stop_p = item_d.get("stop_loss")
                sig_date = item_d.get("signal_date")

                # Ensure timestamps and staleness attributes are initialized
                item_d["signal_time"] = item_d.get("signal_time") or item_d.get("created_at") or (f"{sig_date} 15:30" if sig_date else None)
                item_d["signal_datetime"] = item_d.get("signal_datetime") or item_d.get("created_at") or sig_date

                lq = live_quotes_map.get(t) if live_quotes_map else None
                if lq:
                    item_d["quote_timestamp"] = lq.get("quote_timestamp") or lq.get("last_updated")
                    item_d["current_price_time"] = item_d["quote_timestamp"]
                    item_d["price_delay_status"] = lq.get("price_delay_status") or ("LIVE" if lq.get("is_live") else "DELAYED")
                    item_d["is_price_stale"] = bool(lq.get("is_price_stale", False))
                else:
                    item_d["quote_timestamp"] = item_d.get("current_date") or item_d.get("updated_at")
                    item_d["current_price_time"] = item_d["quote_timestamp"]
                    item_d["price_delay_status"] = "DELAYED"
                    item_d["is_price_stale"] = False

                if not t or "TEST" in t.upper() or "MOCK" in t.upper() or "DUMMY" in t.upper():
                    return
                try:
                    df = fetch_prices(t, settings, force=live)
                    if not df.empty and "close" in df.columns:
                        closes = pd.to_numeric(df["close"], errors="coerce").dropna()
                        if not closes.empty:
                            latest_hist_close = round(float(closes.iloc[-1]), 2)
                            latest_hist_date = str(df.index[-1])[:10]

                            cur_p = latest_hist_close
                            if lq and lq.get("current_price") and float(lq.get("current_price") or 0) > 0:
                                cur_p = float(lq["current_price"])

                            # Slicing strictly Point-in-Time starting at signal date
                            post_df = pd.DataFrame()
                            if sig_date:
                                try:
                                    sig_dt = pd.to_datetime(str(sig_date)[:10]).tz_localize(None)
                                    df_norm_idx = pd.to_datetime(df.index).tz_localize(None)
                                    post_mask = df_norm_idx >= sig_dt
                                    post_df = df.loc[post_mask]
                                except Exception:
                                    post_df = pd.DataFrame()

                            if post_df.empty:
                                # When signal is newer than price history or created today/weekend:
                                days_elapsed = 1
                                item_d["days_elapsed"] = days_elapsed

                                # Validate if live quote is fresh and on/after signal date
                                valid_lq_price = False
                                if lq and lq.get("current_price") and float(lq.get("current_price") or 0) > 0:
                                    lq_ts = str(lq.get("quote_timestamp") or lq.get("last_updated") or "")[:10]
                                    sig_d_str = str(sig_date)[:10] if sig_date else ""
                                    if not sig_d_str or not lq_ts or lq_ts >= sig_d_str:
                                        cur_p = float(lq["current_price"])
                                        valid_lq_price = True

                                if not valid_lq_price and sig_p:
                                    cur_p = sig_p

                                item_d["current_price"] = cur_p
                                item_d["current_date"] = str(sig_date)[:10] if sig_date else latest_hist_date
                                item_d["post_high"] = max(cur_p, sig_p or cur_p)
                                item_d["peak_price"] = item_d["post_high"]
                                if sig_p and sig_p > 0:
                                    item_d["realized_return_pct"] = round(((cur_p - sig_p) / sig_p) * 100, 2)
                                    item_d["max_gain_pct"] = round(((item_d["post_high"] - sig_p) / sig_p) * 100, 2)
                                else:
                                    item_d["realized_return_pct"] = 0.0
                                    item_d["max_gain_pct"] = 0.0

                                item_d["is_live_recent"] = True
                                item_d["settled_14d"] = False

                                item_d["days_to_target"] = None
                                item_d["strategy_id"] = _extract_strategy_id_from_setup(item_d)

                                if target_p and (cur_p >= target_p or item_d["post_high"] >= target_p):
                                    item_d["outcome"] = "TARGET_HIT"
                                    item_d["outcome_label"] = "Target Hit 🎯 (Live D1)"
                                    item_d["outcome_badge"] = "TARGET_HIT"
                                    item_d["breakout_happened"] = True
                                    item_d["days_to_target"] = 1
                                    item_d["what_happened_summary"] = f"🎯 Hit target ₹{target_p:,.2f} on Day 1 (+{item_d.get('max_gain_pct',0):.1f}% peak)."
                                elif stop_p and cur_p <= stop_p:
                                    item_d["outcome"] = "STOP_HIT"
                                    item_d["outcome_label"] = "Stop Hit 🛑 (Live D1)"
                                    item_d["outcome_badge"] = "STOP_HIT"
                                    item_d["breakout_happened"] = False
                                    item_d["what_happened_summary"] = f"🛑 Hit stop loss ₹{stop_p:,.2f} on Day 1."
                                elif sig_p and cur_p >= sig_p:
                                    item_d["outcome"] = "TRIGGERED"
                                    item_d["outcome_label"] = f"Live Active 🟢 (+{item_d.get('realized_return_pct',0):.1f}% D1)"
                                    item_d["outcome_badge"] = "TRIGGERED"
                                    item_d["breakout_happened"] = True
                                    item_d["what_happened_summary"] = f"🟢 Holding breakout gains at ₹{cur_p:,.2f} ({item_d.get('realized_return_pct',0):+.1f}% live return on Day 1/14)."
                                else:
                                    item_d["outcome"] = "BREAKOUT_RETRACED"
                                    item_d["outcome_label"] = f"Breakout Retraced ⚠️ ({item_d.get('realized_return_pct',0):+.1f}% Live D1)"
                                    item_d["outcome_badge"] = "BREAKOUT_RETRACED"
                                    item_d["breakout_happened"] = False
                                    item_d["what_happened_summary"] = f"⚠️ Pulled back to ₹{cur_p:,.2f} ({item_d.get('realized_return_pct',0):+.1f}% live return on Day 1)."
                            else:
                                days_elapsed = max(1, len(post_df))
                                item_d["days_elapsed"] = days_elapsed
                                item_d["current_price"] = cur_p
                                item_d["current_date"] = latest_hist_date
                                item_d["strategy_id"] = _extract_strategy_id_from_setup(item_d)

                                if days_elapsed >= 14:
                                    # 14-day post-signal settled trajectory
                                    w14_df = post_df.head(14)
                                    w14_subsequent = w14_df.iloc[1:] if len(w14_df) > 1 else pd.DataFrame()
                                    w14_high = float(pd.to_numeric(w14_df["high"], errors="coerce").dropna().max()) if "high" in w14_df and not w14_df.empty else cur_p
                                    w14_sub_low = float(pd.to_numeric(w14_subsequent["low"], errors="coerce").dropna().min()) if not w14_subsequent.empty and "low" in w14_subsequent else None
                                    w14_close = float(pd.to_numeric(w14_df["close"], errors="coerce").dropna().iloc[-1]) if "close" in w14_df and not w14_df.empty else cur_p

                                    item_d["post_high"] = w14_high
                                    item_d["peak_price"] = w14_high
                                    if sig_p and sig_p > 0:
                                        item_d["realized_return_pct"] = round(((w14_close - sig_p) / sig_p) * 100, 2)
                                        item_d["max_gain_pct"] = round(((w14_high - sig_p) / sig_p) * 100, 2)

                                    item_d["is_live_recent"] = False
                                    item_d["settled_14d"] = True
                                    item_d["days_to_target"] = None

                                    if target_p and w14_high >= target_p:
                                        target_day = 14
                                        if "high" in w14_df:
                                            highs = pd.to_numeric(w14_df["high"], errors="coerce").fillna(0).tolist()
                                            for idx, h_val in enumerate(highs, start=1):
                                                if h_val >= target_p:
                                                    target_day = idx
                                                    break
                                        item_d["days_to_target"] = target_day
                                        item_d["outcome"] = "TARGET_HIT"
                                        item_d["outcome_label"] = f"Target Hit 🎯 (Day {target_day})"
                                        item_d["outcome_badge"] = "TARGET_HIT"
                                        item_d["breakout_happened"] = True
                                        item_d["what_happened_summary"] = f"🎯 Reached upside target ₹{target_p:,.2f} on Day {target_day}/14 (+{item_d.get('max_gain_pct',0):.1f}% peak)."
                                    elif stop_p and ((w14_sub_low is not None and w14_sub_low <= stop_p) or w14_close <= stop_p):
                                        item_d["outcome"] = "STOP_HIT"
                                        item_d["outcome_label"] = "Stop Hit 🛑 (14D)"
                                        item_d["outcome_badge"] = "STOP_HIT"
                                        item_d["breakout_happened"] = False
                                        item_d["what_happened_summary"] = f"🛑 Breached protective stop at ₹{stop_p:,.2f} within 14-day window."
                                    elif sig_p and w14_close >= sig_p:
                                        item_d["outcome"] = "TRIGGERED"
                                        item_d["outcome_label"] = f"Breakout Succeeded 🚀 (+{item_d.get('realized_return_pct',0):.1f}% 14D)"
                                        item_d["outcome_badge"] = "TRIGGERED"
                                        item_d["breakout_happened"] = True
                                        item_d["what_happened_summary"] = f"🚀 Settled +{item_d.get('realized_return_pct',0):.1f}% in profit over 14-day post-breakout period."
                                    else:
                                        item_d["outcome"] = "BREAKOUT_RETRACED"
                                        item_d["outcome_label"] = "Breakout Retraced ⚠️ (14D)"
                                        item_d["outcome_badge"] = "BREAKOUT_RETRACED"
                                        item_d["breakout_happened"] = False
                                        item_d["what_happened_summary"] = f"⚠️ Breakout pulled back to ₹{w14_close:,.2f} by day 14."
                                else:
                                    # Recently broken out (< 14 days) -> LIVE tracking!
                                    post_subsequent = post_df.iloc[1:] if len(post_df) > 1 else pd.DataFrame()
                                    post_high = float(pd.to_numeric(post_df["high"], errors="coerce").dropna().max()) if "high" in post_df and not post_df.empty else cur_p
                                    post_sub_low = float(pd.to_numeric(post_subsequent["low"], errors="coerce").dropna().min()) if not post_subsequent.empty and "low" in post_subsequent else None
                                    post_high = max(post_high, cur_p)

                                    item_d["post_high"] = post_high
                                    item_d["peak_price"] = post_high
                                    if sig_p and sig_p > 0:
                                        item_d["realized_return_pct"] = round(((cur_p - sig_p) / sig_p) * 100, 2)
                                        item_d["max_gain_pct"] = round(((post_high - sig_p) / sig_p) * 100, 2)

                                    item_d["is_live_recent"] = True
                                    item_d["settled_14d"] = False
                                    item_d["days_to_target"] = None

                                    if target_p and (cur_p >= target_p or post_high >= target_p):
                                        target_day = days_elapsed
                                        if not post_df.empty and "high" in post_df:
                                            highs = pd.to_numeric(post_df["high"], errors="coerce").fillna(0).tolist()
                                            for idx, h_val in enumerate(highs, start=1):
                                                if h_val >= target_p:
                                                    target_day = idx
                                                    break
                                        item_d["days_to_target"] = target_day
                                        item_d["outcome"] = "TARGET_HIT"
                                        item_d["outcome_label"] = f"Target Hit 🎯 (Live D{target_day})"
                                        item_d["outcome_badge"] = "TARGET_HIT"
                                        item_d["breakout_happened"] = True
                                        item_d["what_happened_summary"] = f"🎯 Hit target ₹{target_p:,.2f} on Day {target_day}/14 (+{item_d.get('max_gain_pct',0):.1f}% peak)."
                                    elif stop_p and (cur_p <= stop_p or (post_sub_low is not None and post_sub_low <= stop_p)):
                                        item_d["outcome"] = "STOP_HIT"
                                        item_d["outcome_label"] = f"Stop Hit 🛑 (Live D{days_elapsed})"
                                        item_d["outcome_badge"] = "STOP_HIT"
                                        item_d["breakout_happened"] = False
                                        item_d["what_happened_summary"] = f"🛑 Hit stop loss ₹{stop_p:,.2f} on Day {days_elapsed}/14."
                                    elif sig_p and cur_p >= sig_p:
                                        item_d["outcome"] = "TRIGGERED"
                                        item_d["outcome_label"] = f"Live Active 🟢 (+{item_d.get('realized_return_pct',0):.1f}% D{days_elapsed})"
                                        item_d["outcome_badge"] = "TRIGGERED"
                                        item_d["breakout_happened"] = True
                                        item_d["what_happened_summary"] = f"🟢 Holding breakout gains at ₹{cur_p:,.2f} ({item_d.get('realized_return_pct',0):+.1f}% live return on Day {days_elapsed}/14)."
                                    else:
                                        item_d["outcome"] = "BREAKOUT_RETRACED"
                                        item_d["outcome_label"] = f"Breakout Retraced ⚠️ ({item_d.get('realized_return_pct',0):+.1f}% Live D{days_elapsed})"
                                        item_d["outcome_badge"] = "BREAKOUT_RETRACED"
                                        item_d["breakout_happened"] = False
                                        item_d["what_happened_summary"] = f"⚠️ Breached trigger to peak ₹{post_high:,.2f} (+{item_d.get('max_gain_pct',0):.1f}%) but retraced to ₹{cur_p:,.2f} ({item_d.get('realized_return_pct',0):+.1f}% live return)."
                except Exception as ex:
                    logger.debug("Failed processing tracked breakout for %s: %s", t, ex)

            with ThreadPoolExecutor(max_workers=min(10, len(items))) as pool:
                list(pool.map(_process_tracked_item, items))

            # Batch persist updated live tracking data back to breakout_tracked_signals
            try:
                update_params = []
                now_iso = datetime.now(timezone.utc).isoformat()
                for it in items:
                    item_id = it.get("id")
                    if not item_id:
                        continue
                    update_params.append((
                        it.get("current_price"),
                        it.get("current_date"),
                        it.get("realized_return_pct", 0.0),
                        it.get("max_gain_pct", 0.0),
                        1 if it.get("breakout_happened") else 0,
                        it.get("outcome"),
                        it.get("outcome_label"),
                        it.get("outcome_badge"),
                        it.get("days_elapsed", 0),
                        now_iso,
                        item_id,
                    ))
                if update_params:
                    update_sql = """
                        UPDATE breakout_tracked_signals
                        SET current_price = ?,
                            current_date = ?,
                            realized_return_pct = ?,
                            max_gain_pct = ?,
                            breakout_happened = ?,
                            outcome = ?,
                            outcome_label = ?,
                            outcome_badge = ?,
                            days_elapsed = ?,
                            updated_at = ?
                        WHERE id = ?
                    """
                    conn.executemany(update_sql, update_params)
                    if hasattr(conn, "commit"):
                        conn.commit()
            except Exception as e:
                logger.debug("[TRACKED-BREAKOUTS] Batch update error: %s", e)

        # Post-filter items by outcome if requested
        if filter_outcome:
            out_up = outcome.upper()
            filtered_items = []
            for it in items:
                it_out = str(it.get("outcome") or "").upper()
                if out_up in ("STOP_HIT", "STOP_LOSS_HIT") and it_out in ("STOP_HIT", "STOP_LOSS_HIT"):
                    filtered_items.append(it)
                elif out_up in ("SETUP_FAILED", "BREAKOUT_FAILED") and it_out in ("SETUP_FAILED", "BREAKOUT_FAILED"):
                    filtered_items.append(it)
                elif out_up in ("TRIGGERED", "BREAKOUT_SUCCEEDED") and it_out in ("TRIGGERED", "BREAKOUT_SUCCEEDED"):
                    filtered_items.append(it)
                elif out_up == "TARGET_HIT" and it_out == "TARGET_HIT":
                    filtered_items.append(it)
                elif out_up in ("ACTIVE", "COILING_IN_PROFIT", "COILING_IN_RANGE") and it_out in ("ACTIVE", "COILING_IN_PROFIT", "COILING_IN_RANGE", "PENDING"):
                    filtered_items.append(it)
                elif out_up == it_out:
                    filtered_items.append(it)
            items = filtered_items

        # 6. Summary metrics calculation & 10L Portfolio Capital Simulation
        total_tracked = len(items)
        initial_capital = float(capital) if capital and capital > 0 else 1000000.0
        alloc_per_trade = (initial_capital / total_tracked) if total_tracked > 0 else 0.0

        for it in items:
            out_str = str(it.get("outcome") or "").upper()
            sig_p = it.get("signal_price") or it.get("breakout_trigger")
            target_p = it.get("target_price")
            stop_p = it.get("stop_loss")
            cur_p = it.get("current_price")
            max_g = float(it.get("max_gain_pct") or 0.0)

            if out_str == "TARGET_HIT":
                target_ret = round(((target_p - sig_p) / sig_p * 100.0), 2) if (sig_p and target_p and sig_p > 0) else float(it.get("realized_return_pct") or 0.0)
                peak_ret = max(target_ret, max_g)
                # 70% booked at target, 30% booked at peak
                sim_ret = round(0.70 * target_ret + 0.30 * peak_ret, 2)
                book_note = f"70% @ Target (+{target_ret:.1f}%), 30% @ Peak (+{peak_ret:.1f}%)"
            elif out_str in ("STOP_HIT", "STOP_LOSS_HIT"):
                stop_ret = round(((stop_p - sig_p) / sig_p * 100.0), 2) if (sig_p and stop_p and sig_p > 0) else float(it.get("realized_return_pct") or -5.0)
                if stop_ret > 0:
                    stop_ret = -abs(stop_ret)
                sim_ret = round(stop_ret, 2)
                book_note = f"100% Stop Loss Hit ({stop_ret:.1f}%)"
            elif out_str in ("ACTIVE", "PENDING", "COILING_IN_PROFIT", "COILING_IN_RANGE"):
                sim_ret = round(float(it.get("realized_return_pct") or 0.0), 2)
                book_note = f"MTM Live ({sim_ret:+.1f}%)"
            else:
                sim_ret = round(float(it.get("realized_return_pct") or 0.0), 2)
                book_note = f"14D Settled ({sim_ret:+.1f}%)"

            sim_pnl = round(alloc_per_trade * (sim_ret / 100.0), 2)
            it["simulated_return_pct"] = sim_ret
            it["simulated_allocation"] = round(alloc_per_trade, 2)
            it["simulated_pnl"] = sim_pnl
            it["simulated_booking_note"] = book_note

        positive_count = sum(1 for it in items if (it.get("realized_return_pct") or 0) > 0 or it.get("outcome") in ("TARGET_HIT", "BREAKOUT_SUCCEEDED"))
        loss_count = sum(1 for it in items if (it.get("realized_return_pct") or 0) < 0 or it.get("outcome") in ("STOP_HIT", "STOP_LOSS_HIT", "SETUP_FAILED", "BREAKOUT_FAILED"))
        win_rate_pct = round((positive_count / total_tracked) * 100, 1) if total_tracked > 0 else 0.0

        all_rets = [it.get("realized_return_pct") or 0.0 for it in items]
        avg_return_pct = round(sum(all_rets) / len(all_rets), 2) if all_rets else 0.0

        all_peaks = [it.get("max_gain_pct") or 0.0 for it in items]
        avg_peak_gain_pct = round(sum(all_peaks) / len(all_peaks), 2) if all_peaks else 0.0

        best_item = max(items, key=lambda x: x.get("realized_return_pct") or -999) if items else None
        max_return_pct = best_item.get("realized_return_pct", 0.0) if best_item else 0.0
        max_return_ticker = best_item.get("ticker", "—") if best_item else "—"

        target_hit_count = sum(1 for it in items if it.get("outcome") == "TARGET_HIT")
        target_hit_rate_pct = round((target_hit_count / total_tracked) * 100, 1) if total_tracked > 0 else 0.0
        triggered_count = sum(1 for it in items if it.get("outcome") in ("TRIGGERED", "BREAKOUT_SUCCEEDED", "TARGET_HIT", "BREAKOUT_RETRACED"))
        stop_hit_count = sum(1 for it in items if it.get("outcome") in ("STOP_HIT", "STOP_LOSS_HIT"))
        stop_hit_rate_pct = round((stop_hit_count / total_tracked) * 100, 1) if total_tracked > 0 else 0.0
        setup_failed_count = sum(1 for it in items if it.get("outcome") in ("SETUP_FAILED", "BREAKOUT_FAILED"))
        active_count = sum(1 for it in items if not it.get("settled_14d", False) and (it.get("days_elapsed") or 0) < 14)

        all_days_to_target = [it["days_to_target"] for it in items if it.get("days_to_target") is not None and it.get("outcome") == "TARGET_HIT"]
        avg_days_to_target = round(sum(all_days_to_target) / len(all_days_to_target), 1) if all_days_to_target else None

        # Per-Strategy breakdown matrix
        per_strategy_stats: dict[str, dict[str, Any]] = {}
        for s_key, s_meta in BREAKOUT_STRATEGIES.items():
            s_items = [it for it in items if _extract_strategy_id_from_setup(it) == s_key]
            s_total = len(s_items)
            if s_total == 0:
                per_strategy_stats[s_key] = {
                    "strategy_id": s_key,
                    "strategy_name": s_meta.get("name", s_key),
                    "short_name": s_meta.get("short_name", s_key),
                    "icon": s_meta.get("icon", "⚡"),
                    "badge": s_meta.get("badge", s_key),
                    "total_tracked": 0,
                    "win_count": 0,
                    "loss_count": 0,
                    "win_rate_pct": 0.0,
                    "target_hit_count": 0,
                    "target_hit_rate_pct": 0.0,
                    "stop_hit_count": 0,
                    "stop_hit_rate_pct": 0.0,
                    "avg_days_to_target": None,
                    "avg_return_pct": 0.0,
                    "avg_peak_gain_pct": 0.0,
                    "active_count": 0,
                    "triggered_count": 0,
                    "best_ticker": "—",
                    "best_return_pct": 0.0,
                }
            else:
                s_wins = sum(1 for it in s_items if (it.get("realized_return_pct") or 0) > 0 or it.get("outcome") in ("TARGET_HIT", "BREAKOUT_SUCCEEDED"))
                s_losses = sum(1 for it in s_items if (it.get("realized_return_pct") or 0) < 0 or it.get("outcome") in ("STOP_HIT", "STOP_LOSS_HIT", "SETUP_FAILED", "BREAKOUT_FAILED"))
                s_targets = sum(1 for it in s_items if it.get("outcome") == "TARGET_HIT")
                s_stops = sum(1 for it in s_items if it.get("outcome") in ("STOP_HIT", "STOP_LOSS_HIT"))
                s_active = sum(1 for it in s_items if not it.get("settled_14d", False) and (it.get("days_elapsed") or 0) < 14)
                s_triggered = sum(1 for it in s_items if it.get("outcome") in ("TRIGGERED", "BREAKOUT_SUCCEEDED", "TARGET_HIT", "BREAKOUT_RETRACED"))
                s_rets = [it.get("realized_return_pct") or 0.0 for it in s_items]
                s_peaks = [it.get("max_gain_pct") or 0.0 for it in s_items]
                s_target_days = [it["days_to_target"] for it in s_items if it.get("days_to_target") is not None and it.get("outcome") == "TARGET_HIT"]
                s_best = max(s_items, key=lambda x: x.get("realized_return_pct") or -999) if s_items else None

                per_strategy_stats[s_key] = {
                    "strategy_id": s_key,
                    "strategy_name": s_meta.get("name", s_key),
                    "short_name": s_meta.get("short_name", s_key),
                    "icon": s_meta.get("icon", "⚡"),
                    "badge": s_meta.get("badge", s_key),
                    "total_tracked": s_total,
                    "win_count": s_wins,
                    "loss_count": s_losses,
                    "win_rate_pct": round((s_wins / s_total) * 100, 1),
                    "target_hit_count": s_targets,
                    "target_hit_rate_pct": round((s_targets / s_total) * 100, 1),
                    "stop_hit_count": s_stops,
                    "stop_hit_rate_pct": round((s_stops / s_total) * 100, 1),
                    "avg_days_to_target": round(sum(s_target_days) / len(s_target_days), 1) if s_target_days else None,
                    "avg_return_pct": round(sum(s_rets) / len(s_rets), 2) if s_rets else 0.0,
                    "avg_peak_gain_pct": round(sum(s_peaks) / len(s_peaks), 2) if s_peaks else 0.0,
                    "active_count": s_active,
                    "triggered_count": s_triggered,
                    "best_ticker": s_best.get("ticker", "—") if s_best else "—",
                    "best_return_pct": s_best.get("realized_return_pct", 0.0) if s_best else 0.0,
                }

        # Portfolio simulation aggregation
        total_sim_profit = round(sum(it.get("simulated_pnl", 0.0) for it in items if (it.get("simulated_pnl") or 0.0) > 0), 2)
        total_sim_loss = round(sum(abs(it.get("simulated_pnl", 0.0)) for it in items if (it.get("simulated_pnl") or 0.0) < 0), 2)
        net_sim_pnl = round(sum(it.get("simulated_pnl", 0.0) for it in items), 2)
        final_sim_capital = round(initial_capital + net_sim_pnl, 2)
        sim_return_pct = round((net_sim_pnl / initial_capital) * 100.0, 2) if initial_capital > 0 else 0.0
        profit_factor = round(total_sim_profit / total_sim_loss, 2) if total_sim_loss > 0 else (99.0 if total_sim_profit > 0 else 0.0)

        portfolio_sim = {
            "initial_capital": initial_capital,
            "final_capital": final_sim_capital,
            "net_pnl": net_sim_pnl,
            "return_pct": sim_return_pct,
            "total_profit": total_sim_profit,
            "total_loss": total_sim_loss,
            "profit_factor": profit_factor,
            "allocation_per_trade": round(alloc_per_trade, 2),
            "winning_trades": sum(1 for it in items if (it.get("simulated_return_pct") or 0) > 0),
            "losing_trades": sum(1 for it in items if (it.get("simulated_return_pct") or 0) < 0),
            "breakeven_trades": sum(1 for it in items if (it.get("simulated_return_pct") or 0) == 0),
        }

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
                "win_count": positive_count,
                "loss_count": loss_count,
                "target_hit_count": target_hit_count,
                "target_hit_rate_pct": target_hit_rate_pct,
                "stop_hit_count": stop_hit_count,
                "stop_hit_rate_pct": stop_hit_rate_pct,
                "avg_days_to_target": avg_days_to_target,
                "avg_return_pct": avg_return_pct,
                "avg_peak_gain_pct": avg_peak_gain_pct,
                "max_return_pct": max_return_pct,
                "max_return_ticker": max_return_ticker,
                "active_count": active_count,
                "triggered_count": triggered_count,
                "setup_failed_count": setup_failed_count,
                "per_strategy_stats": per_strategy_stats,
                "portfolio_simulation": portfolio_sim,
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


def delete_tracked_breakout(setup_id: int, settings: Settings | None = None) -> bool:
    """Delete a single tracked breakout setup by its primary key ID."""
    settings = settings or Settings()
    conn = get_db_connection(settings)
    try:
        cur = conn.execute("DELETE FROM breakout_tracked_signals WHERE id = ?", (setup_id,))
        conn.commit()
        deleted = cur.rowcount if hasattr(cur, "rowcount") and cur.rowcount is not None and cur.rowcount > 0 else False
        logger.info("[BREAKOUT-TRACKED] Deleted tracked setup ID=%s (deleted=%s)", setup_id, bool(deleted))
        return bool(deleted)
    except Exception as e:
        logger.exception("[BREAKOUT-TRACKED] Failed deleting tracked setup ID=%s: %s", setup_id, e)
        return False
    finally:
        conn.close()


def delete_tracked_breakouts_by_ticker(ticker: str, settings: Settings | None = None) -> int:
    """Delete all tracked breakout setups for a given ticker symbol."""
    settings = settings or Settings()
    sym = ticker.upper().strip()
    conn = get_db_connection(settings)
    try:
        cur = conn.execute(
            "DELETE FROM breakout_tracked_signals WHERE UPPER(ticker) = ? OR UPPER(ticker) = ?",
            (sym, sym.replace(".NS", "")),
        )
        conn.commit()
        deleted = cur.rowcount if hasattr(cur, "rowcount") and cur.rowcount is not None and cur.rowcount >= 0 else 0
        logger.info("[BREAKOUT-TRACKED] Deleted %d tracked setups for ticker=%s", deleted, sym)
        return deleted
    except Exception as e:
        logger.exception("[BREAKOUT-TRACKED] Failed deleting tracked setups for ticker=%s: %s", sym, e)
        return 0
    finally:
        conn.close()


def _promote(ticker: str, result: dict, settings: Settings | None = None) -> None:
    """Place a ticker into the correct tier based on its score and audit the transition."""
    settings = settings or Settings()
    strat = (result.get("strategy") or "CLASSIC_TECHNICAL").upper().strip()
    if strat == "NSE_FO_CALL_WALL" and not is_fno_eligible(ticker):
        logger.debug("[BREAKOUT:FNO_BYPASS] Skipping promotion of %s for NSE_FO_CALL_WALL; not F&O eligible", ticker)
        return
    result["strategy"] = strat
    key = _pool_key(ticker, strat)
    new_score = result.get("composite_score", 0)
    cur_p = result.get("current_price") or result.get("signal_price")
    trig_p = result.get("breakout_trigger")
    vol_r = result.get("volume_ratio", 1.0)
    cat_headline = (result.get("catalyst_headlines") or [None])[0]

    tier = str(result.get("tier") or ("HOT" if _should_be_hot(result) else ("WARM" if new_score >= WARM_THRESHOLD else "WARM"))).upper()
    result["tier"] = tier

    if tier == "HOT":
        was_warm = key in _pool["warm"]
        was_hot = key in _pool["hot"]
        _pool["hot"][key] = {"result": result, "consecutive_low": 0}
        _pool["warm"].pop(key, None)

        if not was_hot:
            from_t = "WARM" if was_warm else "COLD"
            reason_str = f"Promoted to HOT ({strat}): Score {new_score:.1f} (>= {HOT_THRESHOLD}) with volume ratio {vol_r:.2f}x approaching resistance/trigger ₹{trig_p}"
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
                target_price=result.get("target_price"),
                stop_loss=result.get("stop_loss"),
                risk_reward_ratio=result.get("risk_reward_ratio"),
                volume_ratio=vol_r,
                reason=reason_str,
                catalyst_impact=cat_headline,
                company_name=result.get("company_name"),
                strategy=strat,
                settings=settings,
            )

    elif new_score >= WARM_THRESHOLD or tier == "WARM":
        if key not in _pool["hot"]:
            was_warm = key in _pool["warm"]
            _pool["warm"][key] = {"result": result, "consecutive_low": 0}
            if not was_warm:
                reason_str = f"Added to WARM ({strat}): Coiling compression setup with score {new_score:.1f} (>= {WARM_THRESHOLD})"
                record_breakout_transition(
                    ticker=ticker,
                    event_type="ADDED_WARM",
                    from_tier="COLD",
                    to_tier="WARM",
                    score_before=None,
                    score_after=new_score,
                    price=cur_p,
                    trigger_price=trig_p,
                    target_price=result.get("target_price"),
                    stop_loss=result.get("stop_loss"),
                    risk_reward_ratio=result.get("risk_reward_ratio"),
                    volume_ratio=vol_r,
                    reason=reason_str,
                    catalyst_impact=cat_headline,
                    company_name=result.get("company_name"),
                    strategy=strat,
                    settings=settings,
                )


def _demote_hot(ticker: str, settings: Settings | None = None) -> None:
    """Demote a Hot ticker: increment consecutive_low, remove after 2 strikes with audit log."""
    settings = settings or Settings()
    key = ticker if "::" in ticker else _pool_key(ticker)
    entry = _pool["hot"].get(key)
    if not entry:
        for k, v in _pool["hot"].items():
            if k.startswith(f"{ticker}::"):
                key = k
                entry = v
                break
    if not entry:
        return
    entry["consecutive_low"] += 1
    result = entry.get("result", {})
    parts = key.split("::")
    t_clean = result.get("ticker", parts[0])
    strat = result.get("strategy") or (parts[1] if len(parts) > 1 else "CLASSIC_TECHNICAL")
    is_invalid_fno = strat == "NSE_FO_CALL_WALL" and not is_fno_eligible(t_clean)

    if entry["consecutive_low"] >= 2 or is_invalid_fno:
        score = result.get("composite_score", 0)
        cur_p = result.get("current_price") or result.get("signal_price")
        trig_p = result.get("breakout_trigger")
        del _pool["hot"][key]

        # Maybe keep in warm if score still qualifies (unless non-F&O on F&O strategy)
        if score >= WARM_THRESHOLD and not is_invalid_fno:
            _pool["warm"][key] = {"result": result, "consecutive_low": 0}
            record_breakout_transition(
                ticker=t_clean,
                event_type="DEMOTED_WARM",
                from_tier="HOT",
                to_tier="WARM",
                score_before=score,
                score_after=score,
                price=cur_p,
                trigger_price=trig_p,
                reason=f"Demoted HOT ➔ WARM: Score dropped to {score:.1f} (< {HOT_DEMOTION_THRESHOLD}) for 2 consecutive scan cycles",
                strategy=strat,
                settings=settings,
            )
            logger.debug("[BREAKOUT] %s demoted Hot → Warm (score %.1f)", key, score)
        else:
            reason = (
                f"Removed non-F&O ticker {t_clean} from NSE_FO_CALL_WALL strategy"
                if is_invalid_fno
                else f"Removed from Breakout Radar: Score fell to {score:.1f} below minimum setup criteria"
            )
            record_breakout_transition(
                ticker=t_clean,
                event_type="REMOVED_COLD",
                from_tier="HOT",
                to_tier="COLD",
                score_before=score,
                score_after=score,
                price=cur_p,
                trigger_price=trig_p,
                reason=reason,
                strategy=strat,
                settings=settings,
            )
            logger.debug("[BREAKOUT] %s demoted Hot → Cold (score %.1f)", key, score)
            try:
                conn = get_db_connection(settings)
                conn.execute("DELETE FROM breakout_radar WHERE ticker = ? AND (strategy = ? OR strategy IS NULL)", (t_clean, strat))
                conn.commit()
                conn.close()
            except Exception as e:
                logger.debug("[BREAKOUT-DB] Error removing cold ticker %s from breakout_radar: %s", t_clean, e)


def _demote_warm(ticker: str, settings: Settings | None = None) -> None:
    """Demote a Warm ticker: increment consecutive_low, remove after 2 strikes (or immediate if non-F&O)."""
    settings = settings or Settings()
    key = ticker if "::" in ticker else _pool_key(ticker)
    entry = _pool["warm"].get(key)
    if not entry:
        for k, v in _pool["warm"].items():
            if k.startswith(f"{ticker}::"):
                key = k
                entry = v
                break
    if not entry:
        return
    entry["consecutive_low"] += 1
    result = entry.get("result", {})
    parts = key.split("::")
    t_clean = result.get("ticker", parts[0])
    strat = result.get("strategy") or (parts[1] if len(parts) > 1 else "CLASSIC_TECHNICAL")
    is_invalid_fno = strat == "NSE_FO_CALL_WALL" and not is_fno_eligible(t_clean)

    if entry["consecutive_low"] >= 2 or is_invalid_fno:
        score = result.get("composite_score", 0)
        cur_p = result.get("current_price") or result.get("signal_price")
        trig_p = result.get("breakout_trigger")
        reason = (
            f"Removed non-F&O ticker {t_clean} from NSE_FO_CALL_WALL strategy"
            if is_invalid_fno
            else f"Removed from Warm Pool: Score dropped to {score:.1f} (< {WARM_DEMOTION_THRESHOLD}) for 2 consecutive cycles"
        )
        record_breakout_transition(
            ticker=t_clean,
            event_type="REMOVED_COLD",
            from_tier="WARM",
            to_tier="COLD",
            score_before=score,
            score_after=score,
            price=cur_p,
            trigger_price=trig_p,
            reason=reason,
            strategy=strat,
            settings=settings,
        )
        logger.debug("[BREAKOUT] %s demoted Warm → Cold (score %.1f)", key, score)
        del _pool["warm"][key]
        try:
            conn = get_db_connection(settings)
            conn.execute("DELETE FROM breakout_radar WHERE ticker = ? AND (strategy = ? OR strategy IS NULL)", (t_clean, strat))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.debug("[BREAKOUT-DB] Error removing cold ticker %s from breakout_radar: %s", t_clean, e)


def get_tracked_ticker_set(settings: Settings | None = None) -> set[str]:
    """Return set of ticker symbols permanently persisted and tracked in breakout_tracked_signals / breakout_radar database."""
    settings = settings or Settings()
    conn = None
    try:
        conn = get_db_connection(settings)
        cur = conn.execute("SELECT DISTINCT UPPER(ticker) FROM breakout_tracked_signals WHERE ticker IS NOT NULL")
        tracked = {str(r[0]) for r in cur.fetchall() if r and r[0]}
        cur2 = conn.execute("SELECT DISTINCT UPPER(ticker) FROM breakout_radar WHERE ticker IS NOT NULL")
        for r in cur2.fetchall():
            if r and r[0]:
                tracked.add(str(r[0]))
        return tracked
    except Exception as e:
        logger.debug("[BREAKOUT] Error querying tracked ticker set: %s", e)
        return set()
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


def get_cached_scan_results(
    universe: str | None = None,
    settings: Settings | None = None,
    asof_date: str | None = None,
    strategy: str = "CLASSIC_TECHNICAL",
    tier: str | None = "ALL",
) -> list[dict[str, Any]]:
    """Return breakout candidates, optionally filtered by universe, point-in-time as-of date, and strategy."""
    settings = settings or Settings()
    strategy_clean = (strategy or "CLASSIC_TECHNICAL").upper().strip()

    if not _pool.get("candidates"):
        load_breakout_pool_from_db(settings)

    if asof_date:
        candidates = run_breakout_scan(settings, universe=universe, asof_date=asof_date, strategy=strategy_clean)
    else:
        if strategy_clean in ("ALL", "*"):
            candidates = list(_pool.get("candidates", []))
            if not candidates:
                try:
                    conn = get_db_connection(settings)
                    cur = conn.execute(
                        "SELECT data_json, ticker, strategy, composite_score FROM breakout_radar ORDER BY composite_score DESC LIMIT ?",
                        (BREAKOUT_MAX_CANDIDATES,),
                    )
                    db_cands = []
                    for row in cur.fetchall():
                        if row[0]:
                            try:
                                d = json.loads(row[0])
                                if d and d.get("ticker"):
                                    if row[2]:
                                        d["strategy"] = str(row[2])
                                    db_cands.append(d)
                            except Exception:
                                pass
                    if db_cands:
                        candidates = db_cands
                except Exception as e:
                    logger.debug("[BREAKOUT] DB direct fallback notice for ALL: %s", e)
        else:
            strat_pool = _pool.get("strategy_pools", {}).get(strategy_clean)
            if strat_pool and strat_pool.get("candidates"):
                candidates = list(strat_pool["candidates"])
            else:
                candidates = [c for c in _pool.get("candidates", []) if (c.get("strategy") or "CLASSIC_TECHNICAL").upper() == strategy_clean]

            # Direct SQLite fallback if in-memory pool doesn't have this strategy yet
            if not candidates and strategy_clean not in ("ALL", "*"):
                try:
                    conn = get_db_connection(settings)
                    cur = conn.execute(
                        "SELECT data_json, ticker, composite_score FROM breakout_radar WHERE UPPER(strategy) = ? ORDER BY composite_score DESC LIMIT ?",
                        (strategy_clean, BREAKOUT_MAX_CANDIDATES),
                    )
                    db_cands = []
                    for row in cur.fetchall():
                        if row[0]:
                            try:
                                d = json.loads(row[0])
                                if d and d.get("ticker"):
                                    d["strategy"] = strategy_clean
                                    db_cands.append(d)
                            except Exception:
                                pass
                    if db_cands:
                        candidates = db_cands
                except Exception as e:
                    logger.debug("[BREAKOUT] DB direct fallback notice for %s: %s", strategy_clean, e)

            # If still empty and strategy is valid, compute dynamically on the fly
            if not candidates and strategy_clean in BREAKOUT_STRATEGIES:
                try:
                    candidates = run_breakout_scan(settings, universe=universe, strategy=strategy_clean)
                except Exception as e:
                    logger.debug("[BREAKOUT] Dynamic scan fallback notice for %s: %s", strategy_clean, e)

            if not candidates and strategy_clean == "CLASSIC_TECHNICAL":
                candidates = list(_pool.get("candidates", []))

    # Enrich candidates with real-tracked status badge
    tracked_set = get_tracked_ticker_set(settings)
    for c in candidates:
        t = str(c.get("ticker", "")).upper()
        is_tracked = bool(t in tracked_set or c.get("scanned_at") or c.get("id"))
        c["is_real_tracked"] = is_tracked
        c["tracked_badge"] = "🟢 Real Tracked" if is_tracked else "📊 Dynamic Scan"
        c["tracking_status"] = "REAL_TIME_TRACKED" if is_tracked else "DYNAMIC_SCAN"

    if tier and tier.upper() != "ALL":
        target_tier = tier.upper().strip()
        candidates = [c for c in candidates if (c.get("tier") or "HOT").upper() == target_tier]

    if not universe or universe.lower() in ("all", "any", "global", "monitored"):
        return candidates

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
            candidates = [c for c in candidates if c.get("ticker", "").upper() in uni_normalized]
    except Exception as e:
        logger.debug("[BREAKOUT] Error filtering by universe %s: %s", universe, e)

    return candidates


def get_scan_status(universe: str | None = None, settings: Settings | None = None) -> dict[str, Any]:
    """Return a lightweight status dict for the API, lazy-loading persisted counts if uninitialized."""
    settings = settings or Settings()
    if _pool.get("hot_count", 0) == 0 and _pool.get("warm_count", 0) == 0:
        try:
            load_breakout_pool_from_db(settings)
        except Exception:
            pass
        if _pool.get("hot_count", 0) == 0 and _pool.get("warm_count", 0) == 0:
            try:
                conn = get_db_connection(settings)
                cur = conn.execute("SELECT UPPER(tier), COUNT(*) FROM breakout_radar GROUP BY UPPER(tier)")
                for row in cur.fetchall():
                    t_tier = str(row[0] or "").upper()
                    t_cnt = int(row[1] or 0)
                    if t_tier == "HOT":
                        _pool["hot_count"] = max(_pool.get("hot_count", 0), t_cnt)
                    elif t_tier == "WARM":
                        _pool["warm_count"] = max(_pool.get("warm_count", 0), t_cnt)
            except Exception:
                pass

    if not _pool.get("cold_tickers_scanned"):
        try:
            conn = get_db_connection(settings)
            row = conn.execute("SELECT COUNT(DISTINCT ticker) FROM price_history").fetchone()
            if row and row[0]:
                _pool["cold_tickers_scanned"] = int(row[0])
        except Exception:
            pass

    return {
        "status": _pool.get("status", "idle"),
        "is_scanning": _pool.get("status") == "running",
        "last_scan_at": _pool.get("last_scan_at"),
        "last_cold_scan_at": _pool.get("last_cold_scan_at"),
        "last_warm_scan_at": _pool.get("last_warm_scan_at"),
        "last_hot_scan_at": _pool.get("last_hot_scan_at"),
        "last_scan_duration_s": _pool.get("last_scan_duration_s", 0.0),
        "cold_tickers_scanned": _pool.get("cold_tickers_scanned", 0),
        "hot_count": _pool.get("hot_count", 0),
        "warm_count": _pool.get("warm_count", 0),
        "candidates_found": len(_pool.get("candidates", [])),
        "universe": universe or "ALL",
        "min_score": BREAKOUT_MIN_SCORE,
        "scan_intervals": {
            "cold_min": COLD_INTERVAL_MIN,
            "warm_min": WARM_INTERVAL_MIN,
            "hot_min": HOT_INTERVAL_MIN,
        },
        "error": _pool.get("error"),
    }


# ---------------------------------------------------------------------------
# Scoring helpers & Multi-Strategy Quantitative Engines
# ---------------------------------------------------------------------------

def _score_resistance_proximity(closes: pd.Series) -> tuple[float, float]:
    """Return (score 0-40, pct_from_high).

    Points awarded based on how close current price is to the recent high.
    Closer = higher score. Being above high = breakout already = also high.
    """
    if len(closes) < 2:
        return 0.0, float("nan")
    vals = closes.values
    current = float(vals[-1])
    window = min(len(vals), 252)   # up to 1 year
    high = float(vals[-window:].max())
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

    Vol today vs 20D avg. Reward strong institutional accumulation and breakout volume expansion.
    """
    if len(volumes) < 5:
        return 0.0, float("nan")
    vals = volumes.values
    avg_20 = float(vals[-21:-1].mean()) if len(vals) >= 21 else float(vals.mean())
    today = float(vals[-1])
    if avg_20 <= 0:
        return 0.0, float("nan")
    ratio = today / avg_20
    if ratio >= 2.0:
        score = 10.0
    elif 1.5 <= ratio < 2.0:
        score = 8.0
    elif 1.25 <= ratio < 1.5:
        score = 6.0
    elif 1.0 <= ratio < 1.25:
        score = 3.0
    else:
        score = 0.0
    return score, round(ratio, 2)


def _calc_atr_pct(closes: pd.Series, default: float = 2.0) -> float:
    """Calculate 14-day average true range as percentage of price using vectorized numpy.

    Guards against division by zero on non-positive prices and handles NaN values gracefully.
    """
    if closes is None or len(closes) < 15:
        return default
    vals = closes.values[-15:]
    denom = np.where(vals[:-1] == 0, 1.0, vals[:-1])
    daily_range = abs(vals[1:] - vals[:-1]) / denom
    atr = float(daily_range.mean()) * 100.0
    return atr if (atr > 0 and not np.isnan(atr)) else default


def _score_price_compression(closes: pd.Series) -> tuple[float, float]:
    """Return (score 0-10, atr_pct).

    ATR(14) / price. Low ratio = price coiling = potential energy.
    """
    if len(closes) < 15:
        return 0.0, float("nan")
    atr_pct = _calc_atr_pct(closes, default=0.0)
    if np.isnan(atr_pct) or atr_pct <= 0:
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
    vals = closes.values
    current = float(vals[-1])
    sma_20 = float(vals[-20:].mean())
    ref_val = float(vals[max(0, len(vals) - 31)])
    ret_30 = float((current / ref_val) - 1) * 100 if ref_val > 0 else 0.0

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


def _calculate_volume_profile_detailed(df: pd.DataFrame, num_bins: int = 30) -> tuple[float, float, float, float, list[dict[str, Any]]]:
    """Calculate Point of Control (POC), Value Area High (VAH), Value Area Low (VAL),
    LVN ratio, and detailed price-level volume bins across historical dataframe.

    Returns (poc, vah, val, lvn_ratio_above_vah, profile_bins).
    """
    if df.empty or "close" not in df.columns:
        return 0.0, 0.0, 0.0, 1.0, []

    closes = pd.to_numeric(df["close"], errors="coerce").dropna()
    if len(closes) < 5:
        p = float(closes.iloc[-1]) if not closes.empty else 0.0
        return p, p, p, 1.0, []

    highs = pd.to_numeric(df["high"], errors="coerce").dropna() if "high" in df.columns else closes
    lows = pd.to_numeric(df["low"], errors="coerce").dropna() if "low" in df.columns else closes
    volumes = pd.to_numeric(df["volume"], errors="coerce") if "volume" in df.columns else pd.Series(1.0, index=closes.index)
    volumes.fillna(0, inplace=True)

    p_min = float(lows.min()) if not lows.empty else float(closes.min())
    p_max = float(highs.max()) if not highs.empty else float(closes.max())
    if p_min == p_max:
        p = float(closes.iloc[-1])
        return p, p, p, 1.0, [{"price": round(p, 2), "volume": int(volumes.sum()), "buy_volume": int(volumes.sum()/2), "sell_volume": int(volumes.sum()/2), "is_poc": True, "is_va": True}]

    bins = np.linspace(p_min, p_max, num_bins + 1)
    bin_volumes = np.zeros(num_bins)
    bin_buy_vols = np.zeros(num_bins)
    bin_sell_vols = np.zeros(num_bins)

    for idx_row, row in df.iterrows():
        c = float(row.get("close") or 0.0)
        h = float(row.get("high") or c)
        l = float(row.get("low") or c)
        v = float(row.get("volume") or 0.0)
        rng = max(0.01, h - l)
        buy_ratio = max(0.05, min(0.95, (c - l) / rng))
        bar_buy = v * buy_ratio
        bar_sell = v * (1.0 - buy_ratio)

        b_idx = int(np.digitize(c, bins) - 1)
        b_idx = max(0, min(num_bins - 1, b_idx))
        bin_volumes[b_idx] += v
        bin_buy_vols[b_idx] += bar_buy
        bin_sell_vols[b_idx] += bar_sell

    total_vol = float(np.sum(bin_volumes))
    if total_vol <= 0:
        p = float(closes.iloc[-1])
        return p, p, p, 1.0, []

    poc_idx = int(np.argmax(bin_volumes))
    poc_price = float((bins[poc_idx] + bins[poc_idx + 1]) / 2.0)

    target_va_vol = total_vol * 0.70
    cum_vol = bin_volumes[poc_idx]
    lower_idx = poc_idx
    upper_idx = poc_idx

    while cum_vol < target_va_vol and (lower_idx > 0 or upper_idx < num_bins - 1):
        next_upper = bin_volumes[upper_idx + 1] if upper_idx < num_bins - 1 else 0
        next_lower = bin_volumes[lower_idx - 1] if lower_idx > 0 else 0
        if next_upper >= next_lower and upper_idx < num_bins - 1:
            upper_idx += 1
            cum_vol += bin_volumes[upper_idx]
        elif lower_idx > 0:
            lower_idx -= 1
            cum_vol += bin_volumes[lower_idx]
        else:
            break

    vah_price = float((bins[upper_idx] + bins[upper_idx + 1]) / 2.0)
    val_price = float((bins[lower_idx] + bins[lower_idx + 1]) / 2.0)

    avg_bin_vol = total_vol / num_bins
    vol_above_vah = float(np.mean(bin_volumes[upper_idx + 1:])) if upper_idx < num_bins - 1 else 0.0
    lvn_ratio = vol_above_vah / max(1.0, avg_bin_vol)

    profile_bins = []
    max_bin_vol = max(1.0, float(np.max(bin_volumes)))
    for i in range(num_bins):
        mid_p = float((bins[i] + bins[i + 1]) / 2.0)
        v = float(bin_volumes[i])
        bv = float(bin_buy_vols[i])
        sv = float(bin_sell_vols[i])
        profile_bins.append({
            "price": round(mid_p, 2),
            "volume": int(v),
            "buy_volume": int(bv),
            "sell_volume": int(sv),
            "volume_pct": round((v / max_bin_vol) * 100, 1),
            "delta": int(bv - sv),
            "is_poc": bool(i == poc_idx),
            "is_vah": bool(i == upper_idx),
            "is_val": bool(i == lower_idx),
            "in_value_area": bool(lower_idx <= i <= upper_idx),
        })

    return poc_price, vah_price, val_price, lvn_ratio, profile_bins


def _calculate_volume_profile(df: pd.DataFrame, num_bins: int = 30) -> tuple[float, float, float, float]:
    """Calculate Point of Control (POC) and Value Area High (VAH) across historical dataframe.

    Returns (poc, vah, val, lvn_ratio_above_vah).
    """
    poc_price, vah_price, val_price, lvn_ratio, _ = _calculate_volume_profile_detailed(df, num_bins=num_bins)
    return poc_price, vah_price, val_price, lvn_ratio


def _calculate_donchian_ttm_squeeze(closes: pd.Series, highs: pd.Series, lows: pd.Series) -> tuple[bool, float, float, float, float]:
    """Calculate John Carter TTM Volatility Squeeze (Bollinger Bands vs Keltner Channels) and 55D Donchian High.

    Returns (squeeze_on, donchian_55_high, momentum_osc, bb_width_pct, kc_width_pct).
    """
    if len(closes) < 20:
        c = float(closes.iloc[-1]) if not closes.empty else 0.0
        return False, c, 0.0, 0.0, 0.0

    c = pd.to_numeric(closes, errors="coerce").dropna()
    h = pd.to_numeric(highs, errors="coerce").dropna() if not highs.empty else c
    l = pd.to_numeric(lows, errors="coerce").dropna() if not lows.empty else c

    sma_20 = float(c.tail(20).mean())
    std_20 = float(c.tail(20).std(ddof=0))
    bb_upper = sma_20 + 2.0 * std_20
    bb_lower = sma_20 - 2.0 * std_20
    bb_width = bb_upper - bb_lower

    tr1 = h - l
    tr2 = (h - c.shift(1)).abs()
    tr3 = (l - c.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr_20 = float(tr.tail(20).mean()) if len(tr) >= 20 else float(c.tail(20).std(ddof=0))
    kc_upper = sma_20 + 1.5 * atr_20
    kc_lower = sma_20 - 1.5 * atr_20
    kc_width = kc_upper - kc_lower

    squeeze_on = bool(bb_upper <= kc_upper and bb_lower >= kc_lower)
    donchian_window = min(len(h), 55)
    donchian_55_high = float(h.tail(donchian_window).max())

    cur_p = float(c.iloc[-1])
    mom_osc = ((cur_p - sma_20) / max(0.01, sma_20)) * 100.0
    bb_width_pct = (bb_width / max(0.01, cur_p)) * 100.0
    kc_width_pct = (kc_width / max(0.01, cur_p)) * 100.0

    return squeeze_on, donchian_55_high, mom_osc, bb_width_pct, kc_width_pct


def _detect_vcp_pattern(
    highs: pd.Series,
    lows: pd.Series,
    closes: pd.Series,
    volumes: pd.Series,
    lookback: int = 60,
) -> dict[str, Any]:
    """Detect Mark Minervini's Volatility Contraction Pattern (VCP).

    Analyzes wave contractions across trailing swing pivots:
    - Measures contraction depth: (Swing High - Swing Low) / Swing High * 100
    - Enforces progressive contraction: C1 > C2 > C3...
    - Detects volume dry-up on the final contraction wave before breakout pivot.
    """
    if len(closes) < 30:
        return {
            "is_vcp": False,
            "stage": "None",
            "num_contractions": 0,
            "contractions_pct": [],
            "volume_dry_up": False,
            "pivot_level": None,
        }

    w_highs = highs.tail(lookback).values
    w_lows = lows.tail(lookback).values
    w_closes = closes.tail(lookback).values
    w_vols = volumes.tail(lookback).values
    n = len(w_closes)

    # Identify swing highs (local peaks) and swing lows (local troughs)
    peaks = []
    troughs = []
    order = 3
    for i in range(order, n - order):
        if w_highs[i] == max(w_highs[i - order : i + order + 1]):
            peaks.append((i, float(w_highs[i])))
        if w_lows[i] == min(w_lows[i - order : i + order + 1]):
            troughs.append((i, float(w_lows[i])))

    if len(peaks) < 2 or len(troughs) < 2:
        return {
            "is_vcp": False,
            "stage": "None",
            "num_contractions": 0,
            "contractions_pct": [],
            "volume_dry_up": False,
            "pivot_level": None,
        }

    contractions = []
    for i in range(min(len(peaks), len(troughs))):
        p_price = peaks[i][1]
        sub_troughs = [t[1] for t in troughs if t[0] >= peaks[i][0]]
        if sub_troughs:
            t_price = min(sub_troughs)
            if p_price > 0:
                depth = round(((p_price - t_price) / p_price) * 100.0, 1)
                if depth > 0.5:
                    contractions.append(depth)

    is_contracting = False
    valid_contractions = []
    if len(contractions) >= 2:
        tail_c = contractions[-4:]
        if all(tail_c[j] >= tail_c[j+1] * 0.9 for j in range(len(tail_c)-1)) and tail_c[-1] <= 10.0:
            is_contracting = True
            valid_contractions = tail_c

    avg_vol_20 = float(np.mean(w_vols[-20:])) if len(w_vols) >= 20 else float(np.mean(w_vols))
    recent_vol = float(np.mean(w_vols[-5:])) if len(w_vols) >= 5 else avg_vol_20
    volume_dry_up = bool(avg_vol_20 > 0 and recent_vol <= avg_vol_20 * 0.85)

    is_vcp = bool(is_contracting and len(valid_contractions) >= 2)
    num_c = len(valid_contractions)
    pivot_level = round(float(peaks[-1][1]), 2) if peaks else None

    if is_vcp:
        c_str = " -> ".join(f"{c:.1f}%" for c in valid_contractions)
        stage = f"VCP {num_c}T Coiled ({c_str})"
    elif is_contracting:
        stage = f"VCP Developing ({len(contractions)} Waves)"
    else:
        stage = "No VCP"

    return {
        "is_vcp": is_vcp,
        "stage": stage,
        "num_contractions": num_c,
        "contractions_pct": valid_contractions,
        "volume_dry_up": volume_dry_up,
        "pivot_level": pivot_level,
    }


# ---------------------------------------------------------------------------
# Technical Decision Metrics Extraction
# ---------------------------------------------------------------------------

def compute_technical_decision_metrics(
    ticker: str,
    prices_df: pd.DataFrame | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Compute comprehensive technical decision metrics for email alerts and trading context.

    Extracts:
    - Moving averages: SMA 20, 50, 200, EMA 8, EMA 21 and percentage distances
    - Trend Alignment: Bullish Golden Stack, Bullish Alignment, Above 200 SMA, Below 200 SMA
    - Supertrend: 10-period 3.0-multiplier direction and stop level
    - 52-Week Range: High, Low, % from 52W High, % from 52W Low, 20D Range %
    - Volatility & Squeeze: ATR(14) %, John Carter TTM Volatility Squeeze, Minervini VCP status
    - Momentum & Flow: RSI(14), 20D Volume Surge Ratio, 30D Return %
    """
    settings = settings or Settings()
    if prices_df is None or prices_df.empty or len(prices_df) < 5:
        from earnings_engine.data.prices import load_prices
        sym = ticker.strip().upper()
        if not (sym.endswith(".NS") or sym.endswith(".BO") or "." in sym):
            sym = f"{sym}.NS"
        prices_df = load_prices(sym, settings)
        if prices_df is None or len(prices_df) < 5:
            prices_df = load_prices(ticker.strip().upper(), settings)

    if prices_df is None or prices_df.empty or len(prices_df) < 5:
        return {
            "sma_20": None, "sma_50": None, "sma_200": None,
            "ema_8": None, "ema_21": None,
            "dist_sma_20_pct": None, "dist_sma_50_pct": None, "dist_sma_200_pct": None,
            "dist_ema_8_pct": None, "dist_ema_21_pct": None,
            "ema_ribbon_bullish": False,
            "trend_alignment": "Unknown",
            "supertrend_direction": "UNKNOWN",
            "supertrend_value": None,
            "high_52w": None, "low_52w": None,
            "dist_52w_high_pct": None, "dist_52w_low_pct": None,
            "range_20d_pct": None,
            "atr_14": None, "atr_14_pct": None,
            "squeeze_on": False,
            "vcp_pattern": {
                "is_vcp": False, "stage": "None", "num_contractions": 0,
                "contractions_pct": [], "volume_dry_up": False, "pivot_level": None,
            },
            "rsi_14": None,
            "volume_surge_ratio": None,
            "ret_30d_pct": None,
        }

    closes = pd.to_numeric(prices_df["close"], errors="coerce").dropna()
    if closes.empty:
        return {
            "sma_20": None, "sma_50": None, "sma_200": None,
            "ema_8": None, "ema_21": None,
            "dist_sma_20_pct": None, "dist_sma_50_pct": None, "dist_sma_200_pct": None,
            "dist_ema_8_pct": None, "dist_ema_21_pct": None,
            "ema_ribbon_bullish": False,
            "trend_alignment": "Unknown",
            "supertrend_direction": "UNKNOWN",
            "supertrend_value": None,
            "high_52w": None, "low_52w": None,
            "dist_52w_high_pct": None, "dist_52w_low_pct": None,
            "range_20d_pct": None,
            "atr_14": None, "atr_14_pct": None,
            "squeeze_on": False,
            "vcp_pattern": {
                "is_vcp": False, "stage": "None", "num_contractions": 0,
                "contractions_pct": [], "volume_dry_up": False, "pivot_level": None,
            },
            "rsi_14": None,
            "volume_surge_ratio": None,
            "ret_30d_pct": None,
        }

    highs = pd.to_numeric(prices_df["high"], errors="coerce").dropna() if "high" in prices_df.columns else closes
    lows = pd.to_numeric(prices_df["low"], errors="coerce").dropna() if "low" in prices_df.columns else closes
    volumes = pd.to_numeric(prices_df["volume"], errors="coerce") if "volume" in prices_df.columns else pd.Series(0.0, index=closes.index)
    volumes.fillna(0, inplace=True)

    current_price = float(closes.iloc[-1])

    # Moving Averages (Simple & Exponential)
    sma_20 = float(closes.values[-20:].mean()) if len(closes) >= 20 else float(closes.mean())
    sma_50 = float(closes.tail(50).mean()) if len(closes) >= 50 else (float(closes.mean()) if len(closes) >= 20 else None)
    sma_200 = float(closes.tail(200).mean()) if len(closes) >= 200 else (float(closes.mean()) if len(closes) >= 100 else None)

    ema_8 = float(closes.ewm(span=8, adjust=False).mean().iloc[-1]) if len(closes) >= 8 else None
    ema_21 = float(closes.ewm(span=21, adjust=False).mean().iloc[-1]) if len(closes) >= 21 else None

    dist_sma_20_pct = round(((current_price - sma_20) / sma_20) * 100.0, 2) if sma_20 and sma_20 > 0 else None
    dist_sma_50_pct = round(((current_price - sma_50) / sma_50) * 100.0, 2) if sma_50 and sma_50 > 0 else None
    dist_sma_200_pct = round(((current_price - sma_200) / sma_200) * 100.0, 2) if sma_200 and sma_200 > 0 else None
    dist_ema_8_pct = round(((current_price - ema_8) / ema_8) * 100.0, 2) if ema_8 and ema_8 > 0 else None
    dist_ema_21_pct = round(((current_price - ema_21) / ema_21) * 100.0, 2) if ema_21 and ema_21 > 0 else None
    ema_ribbon_bullish = bool(ema_8 and ema_21 and ema_8 > ema_21 and current_price >= ema_8)

    # Trend Alignment
    if sma_20 is not None and sma_50 is not None and sma_200 is not None:
        if current_price >= sma_20 >= sma_50 >= sma_200:
            trend_alignment = "Bullish Golden Stack (P > 20 > 50 > 200)"
        elif current_price >= sma_50 >= sma_200:
            trend_alignment = "Bullish Alignment (P > 50 > 200)"
        elif current_price >= sma_200:
            trend_alignment = "Above 200 SMA (Long-Term Bullish)"
        else:
            trend_alignment = "Below 200 SMA (Counter-Trend Setup)"
    elif sma_20 is not None and sma_50 is not None:
        if current_price >= sma_20 >= sma_50:
            trend_alignment = "Bullish Alignment (P > 20 > 50)"
        elif current_price >= sma_50:
            trend_alignment = "Above 50 SMA"
        else:
            trend_alignment = "Below 50 SMA"
    else:
        trend_alignment = "Short-Term Up" if current_price >= sma_20 else "Consolidating"

    # 52W & 20D Ranges
    w52_len = min(len(closes), 252)
    high_52w = float(highs.tail(w52_len).max())
    low_52w = float(lows.tail(w52_len).min())
    dist_52w_high_pct = round(((current_price - high_52w) / high_52w) * 100.0, 2) if high_52w > 0 else 0.0
    dist_52w_low_pct = round(((current_price - low_52w) / low_52w) * 100.0, 2) if low_52w > 0 else 0.0

    w20_len = min(len(closes), 20)
    high_20d = float(highs.tail(w20_len).max())
    low_20d = float(lows.tail(w20_len).min())
    range_20d_pct = round(((high_20d - low_20d) / max(0.01, current_price)) * 100.0, 2)

    # ATR(14) & True Range
    tr1 = (highs - lows).abs()
    tr2 = (highs - closes.shift(1)).abs()
    tr3 = (lows - closes.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr_14 = float(tr.tail(14).mean()) if len(tr) >= 14 else float(tr.mean())
    atr_14_pct = round((atr_14 / max(0.01, current_price)) * 100.0, 2) if current_price > 0 else 0.0

    # TTM Squeeze
    squeeze_on = False
    if len(closes) >= 20:
        std_20 = float(closes.tail(20).std(ddof=0))
        bb_upper = sma_20 + 2.0 * std_20
        bb_lower = sma_20 - 2.0 * std_20
        atr_20 = float(tr.tail(20).mean()) if len(tr) >= 20 else atr_14
        kc_upper = sma_20 + 1.5 * atr_20
        kc_lower = sma_20 - 1.5 * atr_20
        squeeze_on = bool(bb_upper <= kc_upper and bb_lower >= kc_lower)

    # Supertrend (10, 3.0)
    supertrend_direction = "UNKNOWN"
    supertrend_value = None
    if len(closes) >= 15:
        hl2 = (highs + lows) / 2.0
        matr = tr.rolling(10).mean()
        upper_basic = hl2 + (3.0 * matr)
        lower_basic = hl2 - (3.0 * matr)

        final_upper = upper_basic.copy()
        final_lower = lower_basic.copy()
        supertrend = pd.Series(index=closes.index, dtype=float)
        direction = pd.Series(index=closes.index, dtype=int)

        for i in range(10, len(closes)):
            if upper_basic.iloc[i] < final_upper.iloc[i-1] or closes.iloc[i-1] > final_upper.iloc[i-1]:
                final_upper.iloc[i] = upper_basic.iloc[i]
            else:
                final_upper.iloc[i] = final_upper.iloc[i-1]

            if lower_basic.iloc[i] > final_lower.iloc[i-1] or closes.iloc[i-1] < final_lower.iloc[i-1]:
                final_lower.iloc[i] = lower_basic.iloc[i]
            else:
                final_lower.iloc[i] = final_lower.iloc[i-1]

            if closes.iloc[i] > final_upper.iloc[i-1]:
                direction.iloc[i] = 1
            elif closes.iloc[i] < final_lower.iloc[i-1]:
                direction.iloc[i] = -1
            else:
                direction.iloc[i] = direction.iloc[i-1] if i > 10 else 1

            supertrend.iloc[i] = final_lower.iloc[i] if direction.iloc[i] == 1 else final_upper.iloc[i]

        if not supertrend.dropna().empty:
            supertrend_value = round(float(supertrend.iloc[-1]), 2)
            supertrend_direction = "BULLISH" if direction.iloc[-1] == 1 else "BEARISH"

    # VCP Pattern Detection
    vcp_result = _detect_vcp_pattern(highs, lows, closes, volumes, lookback=60)

    # RSI(14)
    rsi_14 = None
    if len(closes) >= 15:
        delta = closes.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.tail(14).mean()
        avg_loss = loss.tail(14).mean()
        if avg_loss == 0:
            rsi_14 = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi_14 = round(100.0 - (100.0 / (1.0 + rs)), 1)

    # Volume Surge Ratio
    volume_surge_ratio = None
    if len(volumes) >= 5:
        avg_vol_20 = float(volumes.tail(21).iloc[:-1].mean()) if len(volumes) >= 21 else float(volumes.mean())
        today_vol = float(volumes.iloc[-1])
        if avg_vol_20 > 0:
            volume_surge_ratio = round(today_vol / avg_vol_20, 2)

    # 7D Return %
    ret_7d_pct = None
    if len(closes) >= 6:
        idx_7 = max(0, len(closes) - 8)
        ret_7d_pct = round(((current_price / float(closes.iloc[idx_7])) - 1.0) * 100.0, 2)

    # 30D Return %
    ret_30d_pct = None
    if len(closes) >= 20:
        idx_30 = max(0, len(closes) - 31)
        ret_30d_pct = round(((current_price / float(closes.iloc[idx_30])) - 1.0) * 100.0, 2)

    return {
        "current_price": round(current_price, 2),
        "sma_20": round(sma_20, 2) if sma_20 is not None else None,
        "sma_50": round(sma_50, 2) if sma_50 is not None else None,
        "sma_200": round(sma_200, 2) if sma_200 is not None else None,
        "ema_8": round(ema_8, 2) if ema_8 is not None else None,
        "ema_21": round(ema_21, 2) if ema_21 is not None else None,
        "dist_sma_20_pct": dist_sma_20_pct,
        "dist_sma_50_pct": dist_sma_50_pct,
        "dist_sma_200_pct": dist_sma_200_pct,
        "dist_ema_8_pct": dist_ema_8_pct,
        "dist_ema_21_pct": dist_ema_21_pct,
        "ema_ribbon_bullish": ema_ribbon_bullish,
        "trend_alignment": trend_alignment,
        "supertrend_direction": supertrend_direction,
        "supertrend_value": supertrend_value,
        "high_52w": round(high_52w, 2),
        "low_52w": round(low_52w, 2),
        "dist_52w_high_pct": dist_52w_high_pct,
        "dist_52w_low_pct": dist_52w_low_pct,
        "range_20d_pct": range_20d_pct,
        "atr_14": round(atr_14, 2),
        "atr_14_pct": atr_14_pct,
        "squeeze_on": squeeze_on,
        "vcp_pattern": vcp_result,
        "rsi_14": rsi_14,
        "volume_surge_ratio": volume_surge_ratio,
        "ret_30d_pct": ret_30d_pct,
        "ret_7d_pct": ret_7d_pct,
    }


# ---------------------------------------------------------------------------
# Per-Strategy Scoring Calculations
# ---------------------------------------------------------------------------

def _score_classic_technical(
    closes: pd.Series,
    volumes: pd.Series,
    high_series: pd.Series,
    quality_scores: list[float | None],
) -> tuple[float, float, float, float, dict[str, float], str, dict[str, Any]]:
    """Strategy 1: Classic Technical Coiling."""
    signal_price = float(closes.iloc[-1])
    res_score, pct_from_high = _score_resistance_proximity(closes)
    vol_score, vol_ratio = _score_volume_surge(volumes) if len(volumes) >= 5 else (0.0, 1.0)
    comp_score, atr_pct = _score_price_compression(closes)
    mom_score, momentum_signal = _score_momentum(closes)
    fund_score, avg_quality = _score_fundamental(quality_scores or [])

    composite = round(res_score + vol_score + comp_score + mom_score + fund_score, 1)

    window = min(len(closes), 252)
    resistance_high = float(high_series.tail(window).max())
    prior_resistance = float(high_series.iloc[:-1].tail(window).max()) if len(high_series) > 1 else resistance_high

    atr_pct_val = atr_pct if (atr_pct is not None and not np.isnan(atr_pct)) else 2.0
    atr_val = signal_price * (atr_pct_val / 100.0)
    if round(resistance_high, 2) <= round(signal_price, 2) or signal_price >= round(prior_resistance, 2):
        breakout_trigger = round(signal_price + max(signal_price * 0.0075, 0.5 * atr_val), 2)
        ideal_entry_price = round(prior_resistance, 2)
    else:
        breakout_trigger = round(resistance_high, 2)
        ideal_entry_price = round(resistance_high, 2)
    daily_high = float(high_series.iloc[-1]) if high_series is not None and len(high_series) > 0 else signal_price
    is_late = bool(ideal_entry_price and ideal_entry_price > 0 and (signal_price > ideal_entry_price * 1.002 or daily_high > ideal_entry_price * 1.002))
    entry_delay_pct = round(((daily_high - ideal_entry_price) / ideal_entry_price) * 100, 1) if (is_late and ideal_entry_price and ideal_entry_price > 0) else 0.0

    target_price = round(max(breakout_trigger * 1.08, breakout_trigger + 2.0 * atr_val), 2)
    stop_loss = round(min(signal_price * 0.95, signal_price - 1.5 * atr_val), 2)

    if (pct_from_high is not None and pct_from_high >= -1.5) and (vol_ratio is not None and vol_ratio >= 1.5):
        archetype = "🔥 High-Volume 52W Breakout"
    elif comp_score >= 8 and res_score >= 25:
        archetype = "🗜️ Coiling Resistance Squeeze"
    elif vol_ratio is not None and vol_ratio >= 1.8:
        archetype = "📊 Institutional Accumulation Surge"
    elif mom_score >= 15:
        archetype = "🚀 Trend Continuation Breakout"
    else:
        archetype = "📈 Resistance Approach Coil"

    subscores = {
        "resistance_score": res_score,
        "volume_score": vol_score,
        "compression_score": comp_score,
        "momentum_score": mom_score,
        "fundamental_score": fund_score,
    }

    notes = {
        "setup_archetype": archetype,
        "strategy_id": "CLASSIC_TECHNICAL",
        "resistance_reasoning": f"Price ₹{signal_price:,.2f} is {pct_from_high:+.1f}% from 52W/recent high of ₹{resistance_high:,.2f} ({res_score:.1f}/30 pts)",
        "volume_reasoning": f"Volume is {vol_ratio:.2f}× of 20D baseline ({vol_score:.1f}/20 pts)",
        "compression_reasoning": f"ATR(14) is {atr_pct:.2f}% of price, signaling tight consolidation ({comp_score:.1f}/15 pts)",
        "momentum_reasoning": f"Momentum posture is '{momentum_signal}' ({mom_score:.1f}/15 pts)",
        "fundamental_reasoning": f"Historical EPS quality score avg {avg_quality:.1f}/9 ({fund_score:.1f}/20 pts)",
        "formula_summary": f"Score {composite}/100 = Res({res_score:.0f}) + Vol({vol_score:.0f}) + Squeeze({comp_score:.0f}) + Mom({mom_score:.0f}) + Fund({fund_score:.0f})",
        "ideal_entry_price": ideal_entry_price,
        "is_late": is_late,
        "entry_delay_pct": entry_delay_pct,
    }
    return composite, breakout_trigger, target_price, stop_loss, subscores, archetype, notes


def _score_nse_delivery_absorption(
    ticker: str,
    closes: pd.Series,
    volumes: pd.Series,
    high_series: pd.Series,
    low_series: pd.Series,
    quality_scores: list[float | None],
    settings: Settings | None = None,
) -> tuple[float, float, float, float, dict[str, float], str, dict[str, Any]]:
    """Strategy 2: NSE Institutional Delivery & Absorption Breakout."""
    signal_price = float(closes.iloc[-1])
    vol_ratio = float(volumes.iloc[-1] / max(1.0, volumes.tail(21).iloc[:-1].mean())) if len(volumes) >= 5 else 1.0

    # 1. Delivery Surge Score (0-35)
    if vol_ratio >= 2.0:
        deliv_score = 35.0
    elif vol_ratio >= 1.5:
        deliv_score = 28.0
    elif vol_ratio >= 1.2:
        deliv_score = 20.0
    else:
        deliv_score = 8.0

    # 2. Institutional Net Inflows (0-25)
    funds_in = 0
    net_flow = 0.0
    act_verdict = "Neutral"
    try:
        from earnings_engine.data.institutional_accumulation import get_stock_institutional_activity
        act = get_stock_institutional_activity(ticker)
        if act:
            funds_in = act.get("funds_accumulating_count", 0)
            net_flow = act.get("net_flow_cr", 0.0)
            act_verdict = act.get("verdict", "Neutral")
    except Exception:
        pass

    if funds_in >= 3 or net_flow >= 100:
        inst_score = 25.0
    elif funds_in >= 1 or net_flow > 0:
        inst_score = 18.0
    else:
        inst_score = 10.0

    # 3. Delivery Ceiling Resistance (0-20)
    top_vol_idx = volumes.tail(20).nlargest(3).index if len(volumes) >= 5 else closes.tail(20).index
    delivery_highs = high_series.loc[high_series.index.isin(top_vol_idx)]
    delivery_resistance = float(delivery_highs.max()) if not delivery_highs.empty else float(closes.tail(20).max())

    atr_pct = _calc_atr_pct(closes, default=2.0)
    atr_val = signal_price * (atr_pct / 100.0)

    ideal_entry_price = round(delivery_resistance, 2)
    if delivery_resistance <= signal_price:
        recent_high = float(high_series.tail(20).max()) if len(high_series) >= 5 else signal_price
        if recent_high > signal_price:
            delivery_trigger = round(recent_high, 2)
        else:
            delivery_trigger = round(signal_price + max(signal_price * 0.008, 0.75 * atr_val), 2)
    else:
        delivery_trigger = round(delivery_resistance, 2)
    daily_high = float(high_series.iloc[-1]) if high_series is not None and len(high_series) > 0 else signal_price
    is_late = bool(ideal_entry_price and ideal_entry_price > 0 and (signal_price > ideal_entry_price * 1.002 or daily_high > ideal_entry_price * 1.002))
    entry_delay_pct = round(((daily_high - ideal_entry_price) / ideal_entry_price) * 100, 1) if (is_late and ideal_entry_price and ideal_entry_price > 0) else 0.0

    pct_from_deliv = ((signal_price - delivery_trigger) / delivery_trigger) * 100
    if pct_from_deliv >= -1.0:
        deliv_res_score = 20.0
    elif pct_from_deliv >= -3.0:
        deliv_res_score = 15.0
    elif pct_from_deliv >= -5.0:
        deliv_res_score = 10.0
    else:
        deliv_res_score = 4.0

    # 4. Fundamental Track Record (0-20)
    fund_score, avg_quality = _score_fundamental(quality_scores or [])
    fund_score_norm = round((fund_score / 15.0) * 20.0, 1)

    composite = round(deliv_score + inst_score + deliv_res_score + fund_score_norm, 1)

    target_price = round(delivery_trigger + max(delivery_trigger * 0.10, 2.5 * atr_val), 2)

    base_lows = low_series.tail(20)
    base_floor = float(base_lows.min()) if not base_lows.empty else signal_price * 0.95
    stop_loss = round(min(signal_price * 0.95, base_floor - 1.0 * atr_val), 2)

    archetype = "🏛️ NSE Institutional Delivery Surge" if deliv_score >= 28 else "🏦 Block Accumulation Absorption"

    subscores = {
        "resistance_score": deliv_res_score,
        "volume_score": deliv_score,
        "compression_score": 10.0,
        "momentum_score": inst_score,
        "fundamental_score": fund_score_norm,
    }

    notes = {
        "setup_archetype": archetype,
        "strategy_id": "NSE_DELIVERY_ABSORPTION",
        "resistance_reasoning": f"Delivery ceiling resistance at ₹{delivery_trigger:,.2f} ({pct_from_deliv:+.1f}% distance, {deliv_res_score:.1f}/20 pts)",
        "volume_reasoning": f"Deliverable volume surge {vol_ratio:.2f}× baseline ({deliv_score:.1f}/35 pts)",
        "compression_reasoning": f"Accumulation base floor holding at ₹{base_floor:,.2f}",
        "momentum_reasoning": f"Institutional flow: {funds_in} funds accumulating (₹{net_flow:+.1f} Cr net, {inst_score:.1f}/25 pts)",
        "fundamental_reasoning": f"Quarterly beat streak quality {avg_quality:.1f}/9 ({fund_score_norm:.1f}/20 pts)",
        "formula_summary": f"Score {composite}/100 = DelivVol({deliv_score:.0f}) + InstFlow({inst_score:.0f}) + DelivRes({deliv_res_score:.0f}) + Fund({fund_score_norm:.0f})",
        "ideal_entry_price": ideal_entry_price,
        "is_late": is_late,
        "entry_delay_pct": entry_delay_pct,
    }
    return composite, delivery_trigger, target_price, stop_loss, subscores, archetype, notes


def _score_fo_call_wall(
    ticker: str,
    closes: pd.Series,
    volumes: pd.Series,
    high_series: pd.Series,
    low_series: pd.Series,
    settings: Settings | None = None,
) -> tuple[float, float, float, float, dict[str, float], str, dict[str, Any]]:
    """Strategy 3: NSE F&O Option Chain Call OI Wall & Gamma Squeeze."""
    signal_price = float(closes.iloc[-1])

    # Guardrail: Non-F&O equities have no derivatives or option chain
    if not is_fno_eligible(ticker):
        subscores = {
            "resistance_score": 0.0,
            "volume_score": 0.0,
            "compression_score": 0.0,
            "momentum_score": 0.0,
            "fundamental_score": 0.0,
        }
        notes = {
            "setup_archetype": "Non-F&O Cash Equity",
            "strategy_id": "NSE_FO_CALL_WALL",
            "formula_summary": f"Ticker {ticker} is not NSE F&O eligible. F&O Call Wall strategy skipped.",
        }
        return 0.0, signal_price, signal_price, signal_price, subscores, "Non-F&O Stock", notes

    # 1. Option Chain Derivatives Integration
    call_oi_strike = signal_price * 1.04
    pcr_oi = 1.05
    max_pain = signal_price * 0.97
    sentiment = "BULLISH"
    try:
        from earnings_engine.data.option_chain import analyze_option_chain
        opt = analyze_option_chain(ticker, spot_price=signal_price, settings=settings)
        if opt and opt.get("status") != "NOT_FNO":
            call_oi_strike = opt.get("resistance_strike") or opt.get("highest_call_oi_strike") or (signal_price * 1.04)
            pcr_oi = opt.get("pcr_oi") if opt.get("pcr_oi") is not None else 1.0
            max_pain = opt.get("max_pain_strike") or (signal_price * 0.97)
            sentiment = opt.get("sentiment") or "BULLISH"
    except Exception:
        pass

    call_oi_strike = round(float(call_oi_strike), 2)
    orig_call_wall = call_oi_strike
    if call_oi_strike <= signal_price:
        call_oi_strike = round(signal_price * 1.025, 2)
    ideal_entry_price = orig_call_wall
    daily_high = float(high_series.iloc[-1]) if high_series is not None and len(high_series) > 0 else signal_price
    is_late = bool(ideal_entry_price and ideal_entry_price > 0 and (signal_price > ideal_entry_price * 1.002 or daily_high > ideal_entry_price * 1.002))
    entry_delay_pct = round(((daily_high - ideal_entry_price) / ideal_entry_price) * 100, 1) if (is_late and ideal_entry_price and ideal_entry_price > 0) else 0.0
    dist_to_call_wall = ((call_oi_strike - signal_price) / signal_price) * 100

    # 1. Call OI Wall Proximity (0-35)
    if dist_to_call_wall <= 1.5:
        wall_score = 35.0
    elif dist_to_call_wall <= 3.0:
        wall_score = 28.0
    elif dist_to_call_wall <= 5.0:
        wall_score = 18.0
    else:
        wall_score = 8.0

    # 2. PCR Ratio Trend (0-25)
    if pcr_oi >= 1.25:
        pcr_score = 25.0
    elif pcr_oi >= 1.0:
        pcr_score = 18.0
    elif pcr_oi >= 0.8:
        pcr_score = 12.0
    else:
        pcr_score = 4.0

    # 3. Call Short-Covering Unwinding (0-20)
    unwind_score = 20.0 if sentiment == "BULLISH" else (12.0 if sentiment == "NEUTRAL" else 5.0)

    # 4. Underlying Trend Strength (0-20)
    mom_score_raw, mom_sig = _score_momentum(closes)
    trend_score = round((mom_score_raw / 25.0) * 20.0, 1)

    composite = round(wall_score + pcr_score + unwind_score + trend_score, 1)

    breakout_trigger = call_oi_strike
    target_price = round(breakout_trigger * 1.06, 2)
    stop_loss = round(min(signal_price * 0.95, float(max_pain)), 2)

    archetype = "🎯 F&O Call Wall Gamma Squeeze" if wall_score >= 28 else "⚡ Option Chain Resistance Breach"

    subscores = {
        "resistance_score": wall_score,
        "volume_score": unwind_score,
        "compression_score": 10.0,
        "momentum_score": pcr_score,
        "fundamental_score": trend_score,
    }

    notes = {
        "setup_archetype": archetype,
        "strategy_id": "NSE_FO_CALL_WALL",
        "resistance_reasoning": f"Major Call OI Wall at strike ₹{call_oi_strike:,.2f} ({dist_to_call_wall:.1f}% away, {wall_score:.1f}/35 pts)",
        "volume_reasoning": f"Option sentiment is '{sentiment}' indicating call unwinding ({unwind_score:.1f}/20 pts)",
        "compression_reasoning": f"Max pain support floor situated at ₹{max_pain:,.2f}",
        "momentum_reasoning": f"Put-Call Ratio (PCR OI) is {pcr_oi:.2f} ({pcr_score:.1f}/25 pts)",
        "fundamental_reasoning": f"Underlying technical trend is {mom_sig} ({trend_score:.1f}/20 pts)",
        "formula_summary": f"Score {composite}/100 = CallOIWall({wall_score:.0f}) + PCR({pcr_score:.0f}) + Unwind({unwind_score:.0f}) + Trend({trend_score:.0f})",
        "ideal_entry_price": ideal_entry_price,
        "is_late": is_late,
        "entry_delay_pct": entry_delay_pct,
    }
    return composite, breakout_trigger, target_price, stop_loss, subscores, archetype, notes


def _score_volume_profile_vah(
    closes: pd.Series,
    volumes: pd.Series,
    high_series: pd.Series,
    low_series: pd.Series,
    df: pd.DataFrame,
) -> tuple[float, float, float, float, dict[str, float], str, dict[str, Any]]:
    """Strategy 4: Volume Profile & Value Area High (VAH) Expansion."""
    signal_price = float(closes.iloc[-1])
    poc, vah, val, lvn_ratio = _calculate_volume_profile(df.iloc[-63:])

    pct_from_vah = ((signal_price - vah) / max(0.01, vah)) * 100

    # 1. VAH Breakout Proximity (0-35)
    if pct_from_vah >= 0:
        vah_score = 35.0
    elif pct_from_vah >= -1.0:
        vah_score = 30.0
    elif pct_from_vah >= -2.5:
        vah_score = 22.0
    elif pct_from_vah >= -5.0:
        vah_score = 12.0
    else:
        vah_score = 4.0

    # 2. LVN Vacuum Air-Pocket Factor (0-30)
    # Thinner volume above VAH = faster velocity expansion
    if lvn_ratio < 0.6:
        lvn_score = 30.0
    elif lvn_ratio < 0.9:
        lvn_score = 22.0
    elif lvn_ratio < 1.3:
        lvn_score = 14.0
    else:
        lvn_score = 6.0

    # 3. POC Consolidation Energy (0-20)
    poc_dist = abs((signal_price - poc) / max(0.01, poc)) * 100
    poc_score = 20.0 if poc_dist <= 2.5 else (14.0 if poc_dist <= 5.0 else 6.0)

    # 4. Relative Volume Surge (0-15)
    vol_ratio = float(volumes.iloc[-1] / max(1.0, volumes.tail(21).iloc[:-1].mean())) if len(volumes) >= 5 else 1.0
    rel_vol_score = 15.0 if vol_ratio >= 1.5 else (10.0 if vol_ratio >= 1.2 else 4.0)

    composite = round(vah_score + lvn_score + poc_score + rel_vol_score, 1)

    va_height = max(signal_price * 0.05, vah - poc)
    ideal_entry_price = round(float(vah), 2)
    if vah <= signal_price:
        breakout_trigger = round(signal_price + max(signal_price * 0.008, va_height * 0.25), 2)
    else:
        breakout_trigger = round(vah, 2)
    daily_high = float(high_series.iloc[-1]) if high_series is not None and len(high_series) > 0 else signal_price
    is_late = bool(ideal_entry_price and ideal_entry_price > 0 and (signal_price > ideal_entry_price * 1.002 or daily_high > ideal_entry_price * 1.002))
    entry_delay_pct = round(((daily_high - ideal_entry_price) / ideal_entry_price) * 100, 1) if (is_late and ideal_entry_price and ideal_entry_price > 0) else 0.0

    target_price = round(breakout_trigger + va_height * 1.5, 2)
    stop_loss = round(min(signal_price * 0.95, poc), 2)

    archetype = "📊 Volume Profile VAH Expansion" if vah_score >= 30 else "🌀 POC Equilibrium Breakout"

    subscores = {
        "resistance_score": vah_score,
        "volume_score": lvn_score,
        "compression_score": poc_score,
        "momentum_score": rel_vol_score,
        "fundamental_score": 10.0,
    }

    notes = {
        "setup_archetype": archetype,
        "strategy_id": "VOLUME_PROFILE_VAH",
        "resistance_reasoning": f"63-Day Value Area High (VAH) ceiling at ₹{vah:,.2f} ({pct_from_vah:+.1f}% distance, {vah_score:.1f}/35 pts)",
        "volume_reasoning": f"Low Volume Node ratio above VAH is {lvn_ratio:.2f}× (thin liquidity vacuum, {lvn_score:.1f}/30 pts)",
        "compression_reasoning": f"Point of Control (POC) high-volume node at ₹{poc:,.2f} ({poc_dist:.1f}% dist, {poc_score:.1f}/20 pts)",
        "momentum_reasoning": f"Traded volume surge {vol_ratio:.2f}× baseline ({rel_vol_score:.1f}/15 pts)",
        "fundamental_reasoning": "Volume Profile price-acceptance structure confirmed across 63 sessions",
        "formula_summary": f"Score {composite}/100 = VAH({vah_score:.0f}) + LVNVacuum({lvn_score:.0f}) + POC({poc_score:.0f}) + RelVol({rel_vol_score:.0f})",
        "ideal_entry_price": ideal_entry_price,
        "is_late": is_late,
        "entry_delay_pct": entry_delay_pct,
    }
    return composite, breakout_trigger, target_price, stop_loss, subscores, archetype, notes


def get_order_flow_analytics(
    ticker: str,
    settings: Settings | None = None,
    lookback_days: int = 63,
) -> dict[str, Any]:
    """Calculate GoCharting-grade Order Flow, Volume Profile (TPO), Cumulative Volume Delta (CVD),
    and Liquidity Walls for BSE and NSE equities.
    """
    settings = settings or Settings()
    from earnings_engine.data.prices import canonical_symbol, load_prices, fetch_live_quote

    sym = ticker.strip().upper()
    if sym.startswith("BSE:"):
        raw_sym = sym.split(":", 1)[1]
        bse_sym = f"BSE:{raw_sym}"
        nse_sym = f"NSE:{raw_sym}"
        canon_sym = canonical_symbol(f"{raw_sym}.BO" if not raw_sym.endswith((".BO", ".NS")) else raw_sym)
    elif sym.startswith("NSE:"):
        raw_sym = sym.split(":", 1)[1]
        bse_sym = f"BSE:{raw_sym}"
        nse_sym = f"NSE:{raw_sym}"
        canon_sym = canonical_symbol(f"{raw_sym}.NS" if not raw_sym.endswith((".BO", ".NS")) else raw_sym)
    elif sym.endswith(".BO"):
        raw_sym = sym[:-3]
        bse_sym = f"BSE:{raw_sym}"
        nse_sym = f"NSE:{raw_sym}"
        canon_sym = sym
    elif sym.endswith(".NS"):
        raw_sym = sym[:-3]
        bse_sym = f"BSE:{raw_sym}"
        nse_sym = f"NSE:{raw_sym}"
        canon_sym = sym
    else:
        raw_sym = sym
        bse_sym = f"BSE:{raw_sym}"
        nse_sym = f"NSE:{raw_sym}"
        canon_sym = canonical_symbol(sym)

    # 1. Load price data with fallback cascade
    df = load_prices(canon_sym, settings)
    if (df is None or df.empty):
        if not canon_sym.endswith(".NS"):
            ns_sym = canonical_symbol(f"{raw_sym}.NS")
            df = load_prices(ns_sym, settings)
            if df is not None and not df.empty:
                canon_sym = ns_sym
        if (df is None or df.empty) and not canon_sym.endswith(".BO"):
            bo_sym = canonical_symbol(f"{raw_sym}.BO")
            df = load_prices(bo_sym, settings)
            if df is not None and not df.empty:
                canon_sym = bo_sym

    live_q = fetch_live_quote(canon_sym, settings) or {}
    cur_p = float(live_q.get("current_price") or 0.0)

    if df is not None and not df.empty and "close" in df.columns:
        closes = pd.to_numeric(df["close"], errors="coerce").dropna()
        if not closes.empty and cur_p <= 0:
            cur_p = float(closes.iloc[-1])
        recent_df = df.tail(lookback_days)
    else:
        recent_df = pd.DataFrame()

    # 2. Compute Volume Profile (TPO)
    if not recent_df.empty:
        poc, vah, val, lvn_ratio, profile_bins = _calculate_volume_profile_detailed(recent_df, num_bins=30)
    else:
        poc, vah, val, lvn_ratio, profile_bins = cur_p, cur_p, cur_p, 1.0, []

    # 3. Compute Cumulative Volume Delta (CVD) & Delta Imbalance
    buy_vol = 0.0
    sell_vol = 0.0
    cvd_bars: list[dict[str, Any]] = []
    cum_delta = 0.0

    if not recent_df.empty and "close" in recent_df.columns and "volume" in recent_df.columns:
        for idx, row in recent_df.iterrows():
            c = float(row.get("close") or 0.0)
            o = float(row.get("open") or c)
            h = float(row.get("high") or max(c, o))
            l = float(row.get("low") or min(c, o))
            v = float(row.get("volume") or 0.0)

            rng = max(0.01, h - l)
            # Intra-bar buy/sell partition approximation (Lee-Ready / Candle Body Ratio)
            buy_ratio = max(0.05, min(0.95, (c - l) / rng))
            bar_buy = v * buy_ratio
            bar_sell = v * (1.0 - buy_ratio)
            bar_delta = bar_buy - bar_sell
            cum_delta += bar_delta
            buy_vol += bar_buy
            sell_vol += bar_sell

            cvd_bars.append({
                "date": str(idx)[:10],
                "open": round(o, 2),
                "high": round(h, 2),
                "low": round(l, 2),
                "close": round(c, 2),
                "volume": int(v),
                "buy_volume": int(bar_buy),
                "sell_volume": int(bar_sell),
                "delta": int(bar_delta),
                "cumulative_delta": int(cum_delta),
                "cvd": int(cum_delta),
            })

    total_vol = buy_vol + sell_vol
    buy_pct = round((buy_vol / max(1.0, total_vol)) * 100, 1)
    sell_pct = round((sell_vol / max(1.0, total_vol)) * 100, 1)
    delta_bias = "ACCUMULATION" if buy_pct >= 55.0 else ("DISTRIBUTION" if sell_pct >= 55.0 else "NEUTRAL")

    # 4. Compute Footprint Matrix for Recent 20 Bars (Synchronized 1:1 with CVD lookback window)
    footprint_matrix: list[dict[str, Any]] = []
    lookback_footprint = cvd_bars[-20:] if len(cvd_bars) >= 20 else cvd_bars
    for b in lookback_footprint:
        b_h = b.get("high", b.get("close", 0.0))
        b_l = b.get("low", b.get("close", 0.0))
        b_v = b.get("volume", 0)
        b_bv = b.get("buy_volume", 0)
        b_sv = b.get("sell_volume", 0)

        levels_count = 5
        step = max(0.05, (b_h - b_l) / max(1, levels_count - 1)) if b_h > b_l else 1.0
        clusters = []
        for i in range(levels_count):
            lvl_p = round(b_l + i * step, 2)
            ratio = max(0.1, min(0.9, (i + 1) / levels_count))
            lvl_bv = int(b_bv * (ratio / levels_count * 2.0))
            lvl_sv = int(b_sv * ((1.0 - ratio) / levels_count * 2.0))
            clusters.append({
                "price": lvl_p,
                "buy_vol": lvl_bv,
                "sell_vol": lvl_sv,
                "buy": lvl_bv,
                "sell": lvl_sv,
                "delta": lvl_bv - lvl_sv,
                "imbalance": "BUY_IMBALANCE" if lvl_bv > lvl_sv * 2.5 else ("SELL_IMBALANCE" if lvl_sv > lvl_bv * 2.5 else "BALANCED"),
            })
        footprint_matrix.append({
            "date": b["date"],
            "open": b.get("open", b["close"]),
            "high": b_h,
            "low": b_l,
            "close": b["close"],
            "volume": b_v,
            "buy_volume": b_bv,
            "sell_volume": b_sv,
            "delta": b["delta"],
            "cvd": b.get("cvd", 0),
            "clusters": clusters,
        })

    # 5. Derivative / Technical Walls & Order Book Spread
    buy_wall = val
    sell_wall = vah
    max_pain = poc
    option_strikes: list[dict[str, Any]] = []
    call_wall_oi = 0.0
    put_wall_oi = 0.0

    # Integrate real Option Chain data using analyze_option_chain
    try:
        from earnings_engine.data.fno_directory import is_fno_eligible
        from earnings_engine.data.option_chain import analyze_option_chain
        if is_fno_eligible(canon_sym):
            opt = analyze_option_chain(canon_sym, spot_price=cur_p, settings=settings)
            if opt and isinstance(opt, dict):
                sell_wall = float(opt.get("resistance_strike") or vah)
                buy_wall = float(opt.get("support_strike") or val)
                max_pain = float(opt.get("max_pain_strike") or poc)
                if opt.get("strikes"):
                    option_strikes = opt.get("strikes")[:20]
                for strike in option_strikes:
                    if abs(strike.get("strike", 0) - sell_wall) < 1.0:
                        call_wall_oi = float(strike.get("ce_oi", 0))
                    if abs(strike.get("strike", 0) - buy_wall) < 1.0:
                        put_wall_oi = float(strike.get("pe_oi", 0))
    except Exception:
        pass

    # Build Two-Sided Unified Price Ladder (Expanded for Sell-Side Depth)
    order_book_spread: list[dict[str, Any]] = []
    if cur_p > 0:
        p_min = float(recent_df["low"].min()) if not recent_df.empty and "low" in recent_df.columns else (cur_p * 0.92)
        p_max = float(recent_df["high"].max()) if not recent_df.empty and "high" in recent_df.columns else (cur_p * 1.08)

        # Extend bounds symmetrically for sell-side depth (asks above spot)
        upper_price = max(p_max, cur_p * 1.08, (sell_wall * 1.02) if sell_wall > cur_p else cur_p * 1.08)
        lower_price = min(p_min, cur_p * 0.92, (buy_wall * 0.98) if buy_wall > 0 and buy_wall < cur_p else cur_p * 0.92)

        num_bins = 30
        upper_bins = int(round(num_bins * ((upper_price - cur_p) / max(1.0, upper_price - lower_price))))
        lower_bins = num_bins - upper_bins
        upper_bins = max(12, min(18, upper_bins))
        lower_bins = num_bins - upper_bins

        upper_grid = np.linspace(cur_p, upper_price, upper_bins + 1) if upper_bins > 0 else []
        lower_grid = np.linspace(lower_price, cur_p, lower_bins + 1) if lower_bins > 0 else []

        # Helper to map historical bin volume near a target price
        hist_bins_map = {b["price"]: b for b in profile_bins} if profile_bins else {}
        def find_nearest_hist_bin(target_price):
            if not hist_bins_map:
                return None
            return min(hist_bins_map.values(), key=lambda b: abs(b["price"] - target_price))

        max_vol = max(1, max(b["volume"] for b in profile_bins)) if profile_bins else 1

        def make_spread_level(price, side_type, hist_bin=None, tag=None):
            vol = hist_bin["volume"] if hist_bin else int(1000 + 2000 * max(0, 1 - abs(price - cur_p) / (cur_p * 0.05)))
            bv = hist_bin["buy_volume"] if hist_bin else int(vol * max(0.05, min(0.95, (price - (price - 0.1)) / max(0.01, 0.2)))) if side_type == "SUPPORT_BID" else int(vol * 0.35)
            sv = hist_bin["sell_volume"] if hist_bin else int(vol - bv)
            return {
                "price": round(price, 2),
                "type": side_type,
                "volume": vol,
                "buy_volume": bv,
                "sell_volume": sv,
                "spread_depth_pct": round((vol / max_vol) * 100, 1),
                "is_poc": bool(hist_bin["is_poc"]) if hist_bin else bool(abs(price - poc) < (upper_grid[1] - upper_grid[0] if len(upper_grid) > 1 else 1.0)),
                "is_vah": bool(hist_bin["is_vah"]) if hist_bin else bool(abs(price - vah) < (upper_grid[1] - upper_grid[0] if len(upper_grid) > 1 else 1.0)),
                "is_val": bool(hist_bin["is_val"]) if hist_bin else bool(abs(price - val) < (lower_grid[1] - lower_grid[0] if len(lower_grid) > 1 else 1.0)),
                "is_buy_wall": bool(abs(price - buy_wall) < ((upper_grid[1] - upper_grid[0]) if len(upper_grid) > 1 else 5.0)),
                "is_sell_wall": bool(abs(price - sell_wall) < ((upper_grid[1] - upper_grid[0]) if len(upper_grid) > 1 else 5.0)),
                "is_call_wall": bool(abs(price - sell_wall) < ((upper_grid[1] - upper_grid[0]) if len(upper_grid) > 1 else 5.0) and call_wall_oi > 0),
                "is_put_wall": bool(abs(price - buy_wall) < ((lower_grid[1] - lower_grid[0]) if len(lower_grid) > 1 else 5.0) and put_wall_oi > 0),
                "is_max_pain": bool(abs(price - max_pain) < ((upper_grid[1] - upper_grid[0]) if len(upper_grid) > 1 else 5.0)),
            }

        # Build Ask / Sell Side Ladder (Above Spot)
        for price in reversed(upper_grid[1:]):
            order_book_spread.append(make_spread_level(price, "RESISTANCE_ASK", find_nearest_hist_bin(price)))

        # Build Bid / Buy Side Ladder (Below Spot)
        for price in lower_grid[:-1]:
            order_book_spread.append(make_spread_level(price, "SUPPORT_BID", find_nearest_hist_bin(price)))

    # Fallback if no levels generated (e.g. zero-cur_p guard path)
    if not order_book_spread and cur_p > 0:
        order_book_spread.append({
            "price": round(cur_p, 2),
            "type": "SPOT",
            "volume": 1,
            "buy_volume": 1,
            "sell_volume": 0,
            "spread_depth_pct": 100.0,
            "is_poc": True,
            "is_vah": False,
            "is_val": False,
            "is_buy_wall": False,
            "is_sell_wall": False,
            "is_call_wall": False,
            "is_put_wall": False,
            "is_max_pain": False,
        })

    gocharting_url = f"https://gocharting.com/terminal?ticker={bse_sym}"
    tv_url = f"https://www.tradingview.com/chart/?symbol={bse_sym}"

    return {
        "ticker": ticker,
        "bse_symbol": bse_sym,
        "nse_symbol": nse_sym,
        "current_price": round(cur_p, 2),
        "asof_date": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "gocharting_url": gocharting_url,
        "tradingview_url": tv_url,
        "volume_profile": {
            "poc": round(poc, 2),
            "vah": round(vah, 2),
            "val": round(val, 2),
            "lvn_resistance_ratio": round(lvn_ratio, 2),
            "value_area_range_pct": round(((vah - val) / max(0.01, cur_p)) * 100, 2) if cur_p > 0 else 0.0,
            "price_vs_value_area": "ABOVE_VAH" if cur_p > vah else ("BELOW_VAL" if cur_p < val else "INSIDE_VALUE_AREA"),
            "profile_bins": profile_bins,
        },
        "order_flow": {
            "buy_volume_pct": buy_pct,
            "sell_volume_pct": sell_pct,
            "net_cumulative_delta": int(cum_delta),
            "delta_regime": delta_bias,
            "cvd_history_bars": cvd_bars[-20:],
        },
        "cvd_history_bars": cvd_bars[-20:],
        "order_book_walls": {
            "buy_wall_floor": round(buy_wall, 2),
            "sell_wall_ceiling": round(sell_wall, 2),
            "max_pain": round(max_pain, 2),
        },
        "order_book_spread": order_book_spread,
        "footprint_matrix": footprint_matrix,
        "option_strikes_sample": option_strikes,
        "verdict_summary": f"GoCharting Order Flow: {delta_bias} flow regime. POC at ₹{poc:,.2f} with VAH ceiling at ₹{vah:,.2f} and VAL floor at ₹{val:,.2f}."
    }



def _score_donchian_squeeze(
    closes: pd.Series,
    volumes: pd.Series,
    high_series: pd.Series,
    low_series: pd.Series,
) -> tuple[float, float, float, float, dict[str, float], str, dict[str, Any]]:
    """Strategy 5: Volatility Compression & 55-Day Donchian Squeeze."""
    signal_price = float(closes.iloc[-1])
    squeeze_on, donchian_55, mom_osc, bb_w, kc_w = _calculate_donchian_ttm_squeeze(closes, high_series, low_series)

    # 1. TTM Squeeze Energy (0-35)
    if squeeze_on:
        squeeze_score = 35.0
    elif bb_w <= kc_w * 1.15:
        squeeze_score = 25.0
    else:
        squeeze_score = 8.0

    # 2. 55-Day Donchian Channel Proximity (0-30)
    pct_from_donchian = ((signal_price - donchian_55) / max(0.01, donchian_55)) * 100
    if pct_from_donchian >= 0:
        donchian_score = 30.0
    elif pct_from_donchian >= -1.0:
        donchian_score = 25.0
    elif pct_from_donchian >= -2.5:
        donchian_score = 18.0
    elif pct_from_donchian >= -5.0:
        donchian_score = 10.0
    else:
        donchian_score = 4.0

    # 3. Momentum Oscillator (0-20)
    if mom_osc >= 3.0:
        mom_score = 20.0
    elif mom_osc > 0:
        mom_score = 14.0
    else:
        mom_score = 4.0

    # 4. Volume Expansion (0-15)
    vol_ratio = float(volumes.iloc[-1] / max(1.0, volumes.tail(21).iloc[:-1].mean())) if len(volumes) >= 5 else 1.0
    vol_score = 15.0 if vol_ratio >= 1.4 else (10.0 if vol_ratio >= 1.1 else 4.0)

    composite = round(squeeze_score + donchian_score + mom_score + vol_score, 1)

    atr_pct = _calc_atr_pct(closes, default=2.0)
    atr_val = signal_price * (atr_pct / 100.0)

    prior_donchian = float(high_series.iloc[:-1].tail(55).max()) if len(high_series) > 1 else donchian_55
    if round(donchian_55, 2) <= round(signal_price, 2) or signal_price >= round(prior_donchian, 2):
        breakout_trigger = round(signal_price + max(signal_price * 0.008, 0.75 * atr_val), 2)
        ideal_entry_price = round(prior_donchian, 2)
    else:
        breakout_trigger = round(donchian_55, 2)
        ideal_entry_price = round(donchian_55, 2)
    daily_high = float(high_series.iloc[-1]) if high_series is not None and len(high_series) > 0 else signal_price
    is_late = bool(ideal_entry_price and ideal_entry_price > 0 and (signal_price > ideal_entry_price * 1.002 or daily_high > ideal_entry_price * 1.002))
    entry_delay_pct = round(((daily_high - ideal_entry_price) / ideal_entry_price) * 100, 1) if (is_late and ideal_entry_price and ideal_entry_price > 0) else 0.0

    target_price = round(breakout_trigger + 3.0 * atr_val, 2)
    sma_20 = float(closes.values[-20:].mean())
    stop_loss = round(min(signal_price * 0.95, sma_20), 2)

    archetype = "🌪️ TTM Donchian Volatility Squeeze" if squeeze_on else "🚀 55-Day Channel Breakout"

    subscores = {
        "resistance_score": donchian_score,
        "volume_score": vol_score,
        "compression_score": squeeze_score,
        "momentum_score": mom_score,
        "fundamental_score": 10.0,
    }

    notes = {
        "setup_archetype": archetype,
        "strategy_id": "DONCHIAN_TTM_SQUEEZE",
        "resistance_reasoning": f"55-Day Donchian Channel High at ₹{donchian_55:,.2f} ({pct_from_donchian:+.1f}% distance, {donchian_score:.1f}/30 pts)",
        "volume_reasoning": f"Volume ratio {vol_ratio:.2f}× confirming breakout expansion ({vol_score:.1f}/15 pts)",
        "compression_reasoning": f"John Carter TTM Squeeze is {'🔥 ON (BB inside Keltner)' if squeeze_on else '🟡 Expanding'} ({squeeze_score:.1f}/35 pts)",
        "momentum_reasoning": f"Momentum slope oscillator is {mom_osc:+.1f}% vs 20 SMA ({mom_score:.1f}/20 pts)",
        "fundamental_reasoning": f"Trailing trend stop loss mapped to 20-Day SMA at ₹{sma_20:,.2f}",
        "formula_summary": f"Score {composite}/100 = TTMSqueeze({squeeze_score:.0f}) + Donchian55({donchian_score:.0f}) + MomOsc({mom_score:.0f}) + Vol({vol_score:.0f})",
        "ideal_entry_price": ideal_entry_price,
        "is_late": is_late,
        "entry_delay_pct": entry_delay_pct,
    }
    return composite, breakout_trigger, target_price, stop_loss, subscores, archetype, notes


# ---------------------------------------------------------------------------
# Master Per-Ticker Breakout Scorer
# ---------------------------------------------------------------------------

def score_breakout(
    ticker: str,
    prices_df: pd.DataFrame,
    quality_scores: list[float | None] | None = None,
    asof_date: str | None = None,
    strategy: str = "CLASSIC_TECHNICAL",
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    """Score a single ticker point-in-time using any of the 5 specialized Breakout Strategies."""
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

    closes = pd.to_numeric(hist_df["close"], errors="coerce").dropna()
    if len(closes) < 10:
        return None

    signal_date = str(hist_df.index[-1])[:10]
    signal_price = float(closes.iloc[-1])

    high_series = pd.to_numeric(hist_df["high"], errors="coerce") if "high" in hist_df.columns else closes
    low_series = pd.to_numeric(hist_df["low"], errors="coerce") if "low" in hist_df.columns else closes
    volumes = pd.to_numeric(hist_df["volume"], errors="coerce") if "volume" in hist_df.columns else pd.Series(1.0, index=closes.index)
    volumes.fillna(0, inplace=True)
    volumes = volumes.reindex(closes.index, fill_value=0)

    strategy_clean = (strategy or "CLASSIC_TECHNICAL").upper().strip()
    if strategy_clean not in BREAKOUT_STRATEGIES:
        strategy_clean = "CLASSIC_TECHNICAL"

    if strategy_clean == "NSE_FO_CALL_WALL" and not is_fno_eligible(ticker):
        logger.debug("[BREAKOUT:FNO_BYPASS] Skipping %s for NSE_FO_CALL_WALL; not F&O eligible", ticker)
        return None

    strat_meta = BREAKOUT_STRATEGIES[strategy_clean]

    # Execute Strategy-Specific Engine
    if strategy_clean == "NSE_DELIVERY_ABSORPTION":
        composite, breakout_trigger, target_price, stop_loss, subscores, archetype, notes = _score_nse_delivery_absorption(
            ticker, closes, volumes, high_series, low_series, quality_scores or [], settings=settings
        )
    elif strategy_clean == "NSE_FO_CALL_WALL":
        composite, breakout_trigger, target_price, stop_loss, subscores, archetype, notes = _score_fo_call_wall(
            ticker, closes, volumes, high_series, low_series, settings=settings
        )
    elif strategy_clean == "VOLUME_PROFILE_VAH":
        composite, breakout_trigger, target_price, stop_loss, subscores, archetype, notes = _score_volume_profile_vah(
            closes, volumes, high_series, low_series, hist_df
        )
    elif strategy_clean == "DONCHIAN_TTM_SQUEEZE":
        composite, breakout_trigger, target_price, stop_loss, subscores, archetype, notes = _score_donchian_squeeze(
            closes, volumes, high_series, low_series
        )
    else:  # CLASSIC_TECHNICAL
        composite, breakout_trigger, target_price, stop_loss, subscores, archetype, notes = _score_classic_technical(
            closes, volumes, high_series, quality_scores or []
        )

    # Current / Latest Market Data
    all_closes = pd.to_numeric(df["close"], errors="coerce").dropna()
    current_price = float(all_closes.iloc[-1])
    current_date = str(df.index[-1])[:10]

    # Outcome Calculation (Did Breakout Happen?)
    if not future_df.empty and signal_date != current_date:
        f_highs = pd.to_numeric(future_df["high"], errors="coerce") if "high" in future_df.columns else pd.to_numeric(future_df["close"], errors="coerce")
        f_lows = pd.to_numeric(future_df["low"], errors="coerce") if "low" in future_df.columns else pd.to_numeric(future_df["close"], errors="coerce")
        post_high = float(f_highs.max()) if not f_highs.empty else signal_price
        post_low = float(f_lows.min()) if not f_lows.empty else signal_price

        realized_return_pct = round(((current_price - signal_price) / signal_price) * 100, 2)
        max_gain_pct = round(((post_high - signal_price) / signal_price) * 100, 2)
        days_elapsed = len(future_df)

        # Require a 0.15% confirmation buffer above trigger to confirm a real breach vs tick noise
        breakout_fired = bool(post_high >= breakout_trigger * 1.0015 or current_price >= breakout_trigger * 1.0015)

        if post_high >= target_price:
            breakout_happened = True
            outcome = "TARGET_HIT"
            outcome_label = f"Target Hit 🎯 (+{max_gain_pct}%)"
            outcome_badge = "emerald"
        elif breakout_fired:
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
        realized_return_pct = None
        max_gain_pct = None
        days_elapsed = None
        post_high = None
        outcome_label = "Pending ⏳"
        outcome_badge = "slate"

    # One-liner narrative
    if outcome == "TARGET_HIT":
        one_liner = f"🎯 Target Hit: Reached peak ₹{post_high:,.2f} (+{max_gain_pct}%) in {days_elapsed}d; crossed trigger ₹{breakout_trigger:,.2f}."
    elif outcome == "BREAKOUT_SUCCEEDED":
        one_liner = f"🚀 Breakout Succeeded: Breached trigger ₹{breakout_trigger:,.2f}, currently holding gains at ₹{current_price:,.2f} ({realized_return_pct:+.1f}%)."
    elif outcome == "BREAKOUT_RETRACED":
        one_liner = f"⚠️ Breakout Retraced: Triggered breakout to peak ₹{post_high:,.2f} (+{max_gain_pct}%) but retraced to ₹{current_price:,.2f} ({realized_return_pct:+.1f}%)."
    elif outcome == "STOP_LOSS_HIT":
        one_liner = f"🛑 Stop Hit: Breached trigger but slipped below SL ₹{stop_loss:,.2f} ({realized_return_pct:+.1f}%)."
    elif outcome == "SETUP_FAILED":
        one_liner = f"❌ Setup Failed: Never crossed breakout trigger ₹{breakout_trigger:,.2f}; broke below SL ₹{stop_loss:,.2f} ({realized_return_pct:+.1f}%)."
    elif outcome == "COILING_IN_PROFIT":
        one_liner = f"🟢 Coiling Green: Trading above signal price at ₹{current_price:,.2f} ({realized_return_pct:+.1f}%), awaiting trigger breach at ₹{breakout_trigger:,.2f}."
    elif outcome == "COILING_IN_RANGE":
        one_liner = f"🗜️ Coiling In Range: Consolidating near ₹{current_price:,.2f} ({realized_return_pct:+.1f}%), holding above SL ₹{stop_loss:,.2f}."
    else:
        one_liner = f"⏳ Active Setup: Monitoring for resistance breach at ₹{breakout_trigger:,.2f} with SL at ₹{stop_loss:,.2f}."

    vol_ratio = float(volumes.iloc[-1] / max(1.0, volumes.tail(21).iloc[:-1].mean())) if len(volumes) >= 5 else 1.0
    vol_expansion_str = f"{vol_ratio:.1f}x Vol" if not np.isnan(vol_ratio) else "1.0x Vol"
    is_vol_confirmed = bool(vol_ratio >= 1.5)
    is_fakeout_risk = bool(vol_ratio < 1.2 and (breakout_fired or current_price >= breakout_trigger * 0.98))

    if is_vol_confirmed:
        confirmation_badge = f"⭐ High-Conviction Vol ({vol_expansion_str})"
        confirmation_color = "#34d399"
    elif is_fakeout_risk:
        confirmation_badge = f"⚠️ Low Vol Warning ({vol_expansion_str})"
        confirmation_color = "#fbbf24"
    elif vol_ratio >= 1.2:
        confirmation_badge = f"🔊 {vol_expansion_str} Expansion"
        confirmation_color = "#38bdf8"
    else:
        confirmation_badge = f"📊 Normal Vol ({vol_expansion_str})"
        confirmation_color = "#94a3b8"

    # Enforce minimum 1.5 Risk-Reward Ratio
    downside_risk = max(0.01, signal_price - stop_loss)
    if (target_price - signal_price) < 1.5 * downside_risk:
        target_price = round(max(target_price, signal_price + 1.5 * downside_risk), 2)

    risk_reward_ratio = round((target_price - signal_price) / downside_risk, 2)
    notes["risk_reward_ratio"] = risk_reward_ratio

    # Institutional Flow
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

    pct_from_high = ((signal_price - breakout_trigger) / breakout_trigger) * 100 if breakout_trigger else 0.0

    atr_pct = _calc_atr_pct(closes, default=2.0)

    ideal_entry_price = notes.get("ideal_entry_price") or breakout_trigger
    daily_high = float(high_series.iloc[-1]) if high_series is not None and len(high_series) > 0 else signal_price
    is_late = bool(notes.get("is_late") if notes.get("is_late") is not None else (ideal_entry_price and ideal_entry_price > 0 and (signal_price > ideal_entry_price * 1.002 or daily_high > ideal_entry_price * 1.002)))
    entry_delay_pct = notes.get("entry_delay_pct") if notes.get("entry_delay_pct") is not None else (round(((daily_high - ideal_entry_price) / ideal_entry_price) * 100, 1) if (is_late and ideal_entry_price and ideal_entry_price > 0) else 0.0)

    return {
        "ticker": ticker,
        "signal_date": signal_date,
        "signal_price": round(signal_price, 2),
        "predicted_value": round(signal_price, 2),
        "breakout_trigger": breakout_trigger,
        "ideal_entry_price": ideal_entry_price,
        "is_late": is_late,
        "entry_delay_pct": entry_delay_pct,
        "target_price": target_price,
        "stop_loss": stop_loss,
        "risk_reward_ratio": risk_reward_ratio,
        "setup_archetype": archetype,
        "strategy": strategy_clean,
        "strategy_name": strat_meta["name"],
        "strategy_short_name": strat_meta["short_name"],
        "strategy_badge": strat_meta["badge"],
        "strategy_icon": strat_meta["icon"],
        "calculation_notes": notes,
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
        "resistance_score": subscores["resistance_score"],
        "volume_score": subscores["volume_score"],
        "compression_score": subscores["compression_score"],
        "momentum_score": subscores["momentum_score"],
        "fundamental_score": subscores["fundamental_score"],
        "pct_from_high": round(pct_from_high, 2),
        "volume_ratio": round(vol_ratio, 2),
        "atr_pct": round(atr_pct, 2),
        "momentum_signal": "Strong" if subscores["momentum_score"] >= 15 else "Moderate",
        "tier": "HOT" if _should_be_hot({
            "composite_score": composite,
            "momentum_score": subscores["momentum_score"],
            "momentum_signal": "Strong" if subscores["momentum_score"] >= 15 else "Moderate",
            "pct_from_high": round(pct_from_high, 2),
            "volume_ratio": round(vol_ratio, 2),
            "volume_score": subscores["volume_score"],
            "breakout_fired": breakout_fired,
        }) else ("WARM" if composite >= WARM_THRESHOLD else "COLD"),
        "avg_quality_score": 8.0,
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

    # Persistent DB Cache Check
    try:
        conn = get_db_connection(settings)
        try:
            cur = conn.execute("SELECT data_json FROM breakout_radar WHERE ticker = ? ORDER BY composite_score DESC LIMIT 1", (sym,))
            row = cur.fetchone()
            if row and row[0]:
                data = json.loads(row[0])
                if "ai_reasoning" in data:
                    ai_data = data["ai_reasoning"]
                    gen_at = ai_data.get("generated_at")
                    # Simple freshness check (e.g. 12 hours)
                    if gen_at:
                        gen_dt = datetime.fromisoformat(gen_at)
                        if gen_dt.tzinfo is None:
                            gen_dt = gen_dt.replace(tzinfo=timezone.utc)
                        now_dt = datetime.now(timezone.utc)
                        if (now_dt - gen_dt).total_seconds() < 12 * 3600:
                            _AI_REASONING_CACHE[cache_key] = ai_data
                            return ai_data
        finally:
            conn.close()
    except Exception as e:
        logger.debug("[BREAKOUT-AI] DB cache read failed for %s: %s", sym, e)

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
    
    # Store in DB to prevent token/compute waste on restart
    try:
        conn = get_db_connection(settings)
        try:
            _init_breakout_db(conn)
            cur = conn.execute("SELECT data_json FROM breakout_radar WHERE ticker = ? ORDER BY composite_score DESC LIMIT 1", (sym,))
            row = cur.fetchone()
            if row is not None:
                data = json.loads(row[0]) if row[0] else {}
                data["ai_reasoning"] = output_dict
                new_json = json.dumps(data)
                conn.execute("UPDATE breakout_radar SET data_json = ? WHERE ticker = ?", (new_json, sym))
                conn.commit()
            else:
                new_json = json.dumps({"ai_reasoning": output_dict})
                conn.execute(
                    "INSERT INTO breakout_radar (ticker, strategy, tier, data_json) VALUES (?, 'CLASSIC_TECHNICAL', 'WARM', ?)",
                    (sym, new_json),
                )
                conn.commit()
        finally:
            conn.close()
    except Exception as e:
        logger.debug("[BREAKOUT-AI] DB cache write failed for %s: %s", sym, e)
        
    return output_dict


# ---------------------------------------------------------------------------
# Internal: score a single ticker with DB lookups
# ---------------------------------------------------------------------------

def _score_single_ticker(
    ticker: str,
    settings: Settings,
    asof_date: str | None = None,
    use_live_quote: bool = False,
    strategy: str = "CLASSIC_TECHNICAL",
    prices_df: pd.DataFrame | None = None,
    metrics: dict[str, Any] | None = None,
    catalysts: list[dict[str, Any]] | None = None,
    macro_info: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Load prices, metrics, news catalysts, and score a single ticker. Returns result dict or None."""
    strategy_clean = (strategy or "CLASSIC_TECHNICAL").upper().strip()
    if strategy_clean == "NSE_FO_CALL_WALL" and not is_fno_eligible(ticker):
        return None

    try:
        from earnings_engine.data.prices import load_prices, load_price_metrics, fetch_live_quote

        if prices_df is None:
            prices_df = load_prices(ticker, settings)
        if prices_df is None or prices_df.empty:
            return None

        # 1. Live Price integration for Hot stocks / on-demand re-eval
        if use_live_quote and not asof_date:
            try:
                prices_df = prices_df.copy()
                live_q = fetch_live_quote(ticker, settings, sync_db=True)
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

        if metrics is None:
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

        result = score_breakout(ticker, prices_df, quality_scores, asof_date=asof_date, strategy=strategy, settings=settings)
        if result:
            result["company_name"] = metrics.get("company_name") or ticker
            result["market_cap_cr"] = metrics.get("market_cap_cr") or metrics.get("market_cap")
            result["industry"] = metrics.get("industry") or metrics.get("sector") or "—"

            # 2. News Catalyst Integration from pooled news database
            if not asof_date:
                try:
                    if catalysts is None:
                        from earnings_engine.data.catalysts_news import get_recent_catalysts
                        cats = get_recent_catalysts(ticker, limit=3, settings=settings)
                    else:
                        cats = catalysts
                    if cats:
                        top_cat = cats[0]
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

            # 3. Macro Market Conditions & Volatility Regime Weighting
            if not asof_date:
                try:
                    if macro_info is None:
                        from earnings_engine.data.cross_strategy import compute_market_regime_multiplier
                        macro_data = compute_market_regime_multiplier(settings)
                    else:
                        macro_data = macro_info
                    b_mult = float(macro_data.get("breakout_multiplier", 1.0))
                    m_score = float(macro_data.get("macro_score", 8.0))
                    m_pill = str(macro_data.get("macro_pill", "🟡 Neutral"))
                    m_bias = str(macro_data.get("macro_bias", "RANGEBOUND_NEUTRAL"))

                    # Apply macro multiplier to composite score
                    raw_score = float(result.get("composite_score", 0.0))
                    adjusted_score = max(0.0, min(100.0, round(raw_score * b_mult, 1)))
                    macro_delta = round(adjusted_score - raw_score, 1)

                    result["composite_score"] = adjusted_score
                    result["macro_regime"] = {
                        "bias": m_bias,
                        "multiplier": b_mult,
                        "score": m_score,
                        "delta": macro_delta,
                        "pill": m_pill,
                        "fear_greed_score": macro_data.get("fear_greed_score"),
                        "vix_level": macro_data.get("vix_level"),
                    }
                    if macro_delta != 0.0:
                        tag = "Tailwind" if macro_delta > 0 else "Headwind"
                        result.setdefault("reasoning", []).append(
                            f"🌐 Macro Market {tag} ({b_mult:.2f}x mult, {macro_delta:+.1f} pts): {m_pill}"
                        )
                except Exception as e:
                    logger.debug("[BREAKOUT-MACRO] Macro weighting error for %s: %s", ticker, e)

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
                    rows = conn.execute("SELECT ticker FROM tickers WHERE ticker IS NOT NULL LIMIT 100").fetchall()
                    if not rows:
                        rows = conn.execute("SELECT DISTINCT ticker FROM price_history LIMIT 100").fetchall()
                    tickers.update([r[0] for r in rows if r[0]])
            except Exception:
                pass

    return sorted(tickers)


def run_multi_strategy_parallel_scan(
    settings: Settings | None = None,
    universe: str | None = None,
    min_score: float | None = 30.0,
    strategies: list[str] | None = None,
    tickers: list[str] | None = None,
    job_id: str = "breakout_all_strategies_parallel",
    max_workers_per_strat: int = 6,
    record_schedule_event: bool = True,
    **kwargs: Any,
) -> dict[str, Any]:
    """Execute all 5 (or selected) breakout strategies in parallel across the universe.

    Spawns concurrent worker threads for each strategy to scan the market universe
    simultaneously, discovers setups, updates cache/pools, persists to SQLite/Turso,
    and logs run metrics to automation_schedules.
    """
    settings = settings or Settings()
    t0 = time.perf_counter()
    _pool["status"] = "running"
    _pool["error"] = None

    if record_schedule_event:
        from earnings_engine.data.automation_schedules import record_job_start, record_job_finish
        record_job_start(job_id, settings)

    strategies_to_run = strategies or list(BREAKOUT_STRATEGIES.keys())
    ticker_list = tickers if (tickers is not None and len(tickers) > 0) else _resolve_universe_tickers(settings, universe)

    if not ticker_list:
        summary_msg = "No tickers found in universe to scan."
        if record_schedule_event:
            record_job_finish(job_id, 0.0, summary_msg, settings=settings)
        return {"success": False, "message": summary_msg, "strategies": {}, "total_candidates": 0}

    from concurrent.futures import ThreadPoolExecutor
    from earnings_engine.data.prices import load_prices_batch, load_price_metrics_batch
    from earnings_engine.data.catalysts_news import get_recent_catalysts_batch
    from earnings_engine.data.cross_strategy import compute_market_regime_multiplier

    # Bulk pre-load prices, metrics, catalysts, and macro conditions across all tickers
    prices_map = load_prices_batch(ticker_list, settings=settings)
    metrics_map = load_price_metrics_batch(ticker_list, settings=settings)
    catalysts_map = get_recent_catalysts_batch(ticker_list, limit_per_ticker=3, settings=settings)
    macro_info = None
    try:
        macro_info = compute_market_regime_multiplier(settings)
    except Exception as e:
        logger.debug("[BREAKOUT-MACRO] Macro precompute warning: %s", e)

    strategy_results: dict[str, Any] = {}

    def _scan_strategy(strat_id: str) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
        s_t0 = time.perf_counter()
        meta = BREAKOUT_STRATEGIES.get(strat_id, {})
        strat_candidates: list[dict[str, Any]] = []

        def _score_one(t: str) -> dict[str, Any] | None:
            return _score_single_ticker(
                t,
                settings,
                strategy=strat_id,
                prices_df=prices_map.get(t),
                metrics=metrics_map.get(t),
                catalysts=catalysts_map.get(t),
                macro_info=macro_info,
            )

        strat_clean = strat_id.upper().strip()
        strat_tickers = [t for t in ticker_list if is_fno_eligible(t)] if strat_clean == "NSE_FO_CALL_WALL" else ticker_list

        with ThreadPoolExecutor(max_workers=max_workers_per_strat) as executor:
            scored_list = list(executor.map(_score_one, strat_tickers))

        for res in scored_list:
            if res and (res.get("composite_score") or 0) >= (min_score or 30.0):
                strat_candidates.append(res)

        s_elapsed = round(time.perf_counter() - s_t0, 2)
        top_ticker = None
        top_score = 0.0
        if strat_candidates:
            strat_candidates.sort(key=lambda x: x.get("composite_score", 0), reverse=True)
            top_ticker = strat_candidates[0].get("ticker")
            top_score = strat_candidates[0].get("composite_score", 0)

        stats = {
            "strategy_id": strat_id,
            "strategy_name": meta.get("name", strat_id),
            "candidates_found": len(strat_candidates),
            "top_candidate": top_ticker,
            "top_score": top_score,
            "elapsed_seconds": s_elapsed,
        }
        logger.info(
            "[BREAKOUT-STRAT] Strategy %s finished in %.2fs -> %d candidates found (top: %s @ %.1f)",
            meta.get("name", strat_id),
            s_elapsed,
            len(strat_candidates),
            top_ticker or "none",
            top_score,
        )
        return strat_id, strat_candidates, stats

    logger.info(
        "[BREAKOUT-PARALLEL] Initiating multi-strategy scan across %d tickers (%d strategies in parallel)...",
        len(ticker_list),
        len(strategies_to_run),
    )
    # Run all strategies in parallel
    with ThreadPoolExecutor(max_workers=len(strategies_to_run)) as strat_executor:
        parallel_outputs = list(strat_executor.map(_scan_strategy, strategies_to_run))

    total_candidates = 0
    for strat_id, strat_candidates, stats in parallel_outputs:
        strategy_results[strat_id] = stats
        total_candidates += len(strat_candidates)

        # Populate in-memory pool for candidates
        for res in strat_candidates:
            ticker = res.get("ticker")
            if ticker:
                _promote(ticker, res, settings=settings)

    _rebuild_candidates()
    save_breakout_pool_to_db(settings)

    # Batch-fetch and sync latest quotes for all discovered setups & hot stocks
    try:
        cand_tickers = list({res.get("ticker") for _, strat_cands, _ in parallel_outputs for res in strat_cands if res.get("ticker")})
        hot_tickers = list({k.split("::")[0] for k in _pool.get("hot", {}).keys() if k})
        all_sync_tickers = list(dict.fromkeys(hot_tickers + cand_tickers))[:80]
        if all_sync_tickers:
            from earnings_engine.data.prices import fetch_batch_live_quotes
            fetch_batch_live_quotes(all_sync_tickers, settings=settings, sync_db=True, max_workers=10)
    except Exception as sync_err:
        logger.debug("[BREAKOUT-PARALLEL] Auto-quote sync notice: %s", sync_err)

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

    strat_summary_items = [
        f"{BREAKOUT_STRATEGIES.get(s, {}).get('short_name', s)}: {strategy_results.get(s, {}).get('candidates_found', 0)}"
        for s in strategies_to_run
    ]
    summary_msg = f"Multi-Strategy Parallel Sweep ({len(strategies_to_run)} strats, {len(ticker_list)} tickers in {elapsed}s): {', '.join(strat_summary_items)} → {total_candidates} setups."

    if record_schedule_event:
        record_job_finish(job_id, elapsed, summary_msg, settings=settings)

    logger.info("[BREAKOUT-PARALLEL] %s", summary_msg)

    return {
        "success": True,
        "job_id": job_id,
        "universe": universe or "NSE_ALL",
        "tickers_scanned": len(ticker_list),
        "total_candidates": total_candidates,
        "elapsed_seconds": elapsed,
        "strategy_results": strategy_results,
        "summary": summary_msg,
    }


def run_cold_scan(
    settings: Settings,
    universe: str | None = None,
    min_score: float | None = None,
    strategy: str = "CLASSIC_TECHNICAL",
    **kwargs: Any,
) -> None:
    """T0 Cold Scan: score the entire universe for a single strategy or all strategies in parallel."""
    strat_clean = strategy.upper()
    if strat_clean in ("ALL", "MULTI_STRATEGY_PARALLEL", "PARALLEL"):
        run_multi_strategy_parallel_scan(
            settings=settings,
            universe=universe,
            min_score=min_score or 30.0,
            record_schedule_event=True,
            **kwargs,
        )
        return

    job_id_map = {
        "CLASSIC_TECHNICAL": "breakout_cold_scan",
        "NSE_DELIVERY_ABSORPTION": "breakout_delivery_absorption_scan",
        "NSE_FO_CALL_WALL": "breakout_fo_call_wall_scan",
        "VOLUME_PROFILE_VAH": "breakout_volume_profile_scan",
        "DONCHIAN_TTM_SQUEEZE": "breakout_donchian_squeeze_scan",
    }
    job_id = job_id_map.get(strat_clean, "breakout_cold_scan")

    t0 = time.perf_counter()
    _pool["status"] = "running"
    _pool["error"] = None

    from earnings_engine.data.automation_schedules import record_job_start, record_job_finish
    record_job_start(job_id, settings)

    ticker_list = _resolve_universe_tickers(settings, universe)
    if strat_clean == "NSE_FO_CALL_WALL":
        ticker_list = [t for t in ticker_list if is_fno_eligible(t)]
    if not ticker_list:
        logger.info("[BREAKOUT-COLD] No tickers found to scan for %s.", strat_clean)
        _pool["status"] = "done"
        _pool["cold_tickers_scanned"] = 0
        now_iso = datetime.now(timezone.utc).isoformat()
        _pool["last_cold_scan_at"] = now_iso
        _pool["last_scan_at"] = now_iso
        record_job_finish(job_id, 0.0, f"No tickers found to scan for {strat_clean}.", settings=settings)
        return

    from concurrent.futures import ThreadPoolExecutor
    from earnings_engine.logging_utils import BatchProgressLogger
    from earnings_engine.data.prices import fetch_batch_live_quotes, load_prices_batch, load_price_metrics_batch
    from earnings_engine.data.catalysts_news import get_recent_catalysts_batch
    from earnings_engine.data.cross_strategy import compute_market_regime_multiplier

    # Always refresh live quotes for the full universe first (batched), then bulk
    # pre-load prices, metrics, catalysts, and macro conditions across all tickers
    try:
        fetch_batch_live_quotes(ticker_list, settings=settings, sync_db=True, max_workers=8, force=True)
    except Exception as e:
        logger.debug("[BREAKOUT-COLD] Batch live quote fetch warning: %s", e)

    prices_map = load_prices_batch(ticker_list, settings=settings)
    metrics_map = load_price_metrics_batch(ticker_list, settings=settings)
    catalysts_map = get_recent_catalysts_batch(ticker_list, limit_per_ticker=3, settings=settings)
    macro_info = None
    try:
        macro_info = compute_market_regime_multiplier(settings)
    except Exception as e:
        logger.debug("[BREAKOUT-MACRO] Macro precompute warning: %s", e)

    progress = BatchProgressLogger(
        name=f"breakout_{strat_clean.lower()}",
        total=len(ticker_list),
        unit="tickers",
        milestones=[20, 40, 60, 80, 100],
    )

    def _score(ticker: str) -> tuple[str, dict | None]:
        result = _score_single_ticker(
            ticker,
            settings,
            strategy=strat_clean,
            prices_df=prices_map.get(ticker),
            metrics=metrics_map.get(ticker),
            catalysts=catalysts_map.get(ticker),
            macro_info=macro_info,
        )
        return ticker, result

    scored = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        for item in executor.map(_score, ticker_list):
            scored.append(item)
            progress.update(1)
    progress.finish()

    promoted_hot = 0
    promoted_warm = 0
    cands_found = 0
    for ticker, result in scored:
        if result is None:
            continue
        if (result.get("composite_score") or 0) >= (min_score or 30.0):
            cands_found += 1
        _promote(ticker, result, settings=settings)
        if ticker in _pool["hot"]:
            promoted_hot += 1
        elif ticker in _pool["warm"]:
            promoted_warm += 1

    _rebuild_candidates()
    save_breakout_pool_to_db(settings)

    # Batch-fetch and sync latest quotes for all discovered setups & hot stocks
    try:
        disc_tickers = [t for t, r in scored if r is not None and (r.get("composite_score") or 0) >= (min_score or 30.0)]
        hot_tickers = list({k.split("::")[0] for k in _pool.get("hot", {}).keys() if k})
        all_sync_tickers = list(dict.fromkeys(hot_tickers + disc_tickers))[:60]
        if all_sync_tickers:
            from earnings_engine.data.prices import fetch_batch_live_quotes
            fetch_batch_live_quotes(all_sync_tickers, settings=settings, sync_db=True, max_workers=10)
    except Exception as sync_err:
        logger.debug("[BREAKOUT-COLD] Auto-quote sync notice: %s", sync_err)

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

    strat_name = BREAKOUT_STRATEGIES.get(strat_clean, {}).get("name", strat_clean)
    summary_msg = f"{strat_name} sweep: {len(ticker_list)} tickers → {len(_pool['hot'])} hot, {len(_pool['warm'])} warm, {cands_found} setups"
    record_job_finish(job_id, elapsed, summary_msg, settings=settings)

    logger.info("[BREAKOUT-COLD] %s in %.1fs", summary_msg, elapsed)


def run_warm_rescore(settings: Settings) -> None:
    """T1 Warm Rescore: rescore only warm-pool setups."""
    warm_keys = list(_pool["warm"].keys())
    if not warm_keys:
        return

    t0 = time.perf_counter()
    from earnings_engine.data.automation_schedules import record_job_start, record_job_finish
    record_job_start("breakout_warm_rescore", settings)

    from earnings_engine.data.prices import fetch_batch_live_quotes, load_prices_batch, load_price_metrics_batch
    from earnings_engine.data.catalysts_news import get_recent_catalysts_batch
    from earnings_engine.data.cross_strategy import compute_market_regime_multiplier
    from concurrent.futures import ThreadPoolExecutor

    # 1. Extract tickers for live quote batch fetch (always live — bypass TTL cache)
    tickers_to_fetch = list({k.split("::")[0] for k in warm_keys})
    try:
        fetch_batch_live_quotes(tickers_to_fetch, settings=settings, sync_db=True, max_workers=8, force=True)
    except Exception as e:
        logger.debug("[BREAKOUT-WARM] Batch live quote fetch warning: %s", e)

    prices_map = load_prices_batch(tickers_to_fetch, settings=settings)
    metrics_map = load_price_metrics_batch(tickers_to_fetch, settings=settings)
    catalysts_map = get_recent_catalysts_batch(tickers_to_fetch, limit_per_ticker=3, settings=settings)
    macro_info = None
    try:
        macro_info = compute_market_regime_multiplier(settings)
    except Exception as e:
        logger.debug("[BREAKOUT-WARM] Macro precompute warning: %s", e)

    # 2. Rescore warm tickers per strategy
    def _score(key: str) -> tuple[str, dict | None]:
        parts = key.split("::")
        ticker = parts[0]
        strat = parts[1] if len(parts) > 1 else "CLASSIC_TECHNICAL"
        return key, _score_single_ticker(
            ticker,
            settings,
            strategy=strat,
            use_live_quote=False,
            prices_df=prices_map.get(ticker),
            metrics=metrics_map.get(ticker),
            catalysts=catalysts_map.get(ticker),
            macro_info=macro_info,
        )

    with ThreadPoolExecutor(max_workers=6) as executor:
        scored = list(executor.map(_score, warm_keys))

    for key, result in scored:
        if result is None:
            _demote_warm(key, settings=settings)
            continue

        parts = key.split("::")
        ticker = parts[0]
        strat = parts[1] if len(parts) > 1 else "CLASSIC_TECHNICAL"
        result["strategy"] = strat

        new_score = result.get("composite_score", 0)
        if _should_be_hot(result):
            _promote(ticker, result, settings=settings)
        elif new_score >= WARM_THRESHOLD:
            _pool["warm"][key] = {"result": result, "consecutive_low": 0}
        elif new_score < WARM_DEMOTION_THRESHOLD:
            _demote_warm(key, settings=settings)
        else:
            if key in _pool["warm"]:
                _pool["warm"][key]["result"] = result

    _rebuild_candidates()
    save_breakout_pool_to_db(settings)

    elapsed = round(time.perf_counter() - t0, 2)
    now_iso = datetime.now(timezone.utc).isoformat()
    _pool["last_warm_scan_at"] = now_iso
    _pool["last_scan_at"] = now_iso

    summary_msg = f"Rescored {len(warm_keys)} warm setups (hot={len(_pool['hot'])}, warm={len(_pool['warm'])})"
    record_job_finish("breakout_warm_rescore", elapsed, summary_msg, settings=settings)

    logger.info(
        "[BREAKOUT-WARM] %s in %.1fs",
        summary_msg, elapsed,
    )


def run_hot_rescore(settings: Settings) -> None:
    """T2 Hot Rescore: rescore only hot-pool setups in parallel batches for maximum freshness."""
    hot_keys = list(_pool["hot"].keys())
    if not hot_keys:
        return

    t0 = time.perf_counter()
    from earnings_engine.data.automation_schedules import record_job_start, record_job_finish
    record_job_start("breakout_hot_rescore", settings)

    from earnings_engine.data.prices import fetch_batch_live_quotes
    from concurrent.futures import ThreadPoolExecutor

    # 1. Batch fetch latest live market quotes in parallel (single sub-second batch)
    tickers_to_fetch = list({k.split("::")[0] for k in hot_keys})
    try:
        fetch_batch_live_quotes(tickers_to_fetch, settings=settings, sync_db=True, max_workers=8, force=True)
    except Exception as e:
        logger.debug("[BREAKOUT-HOT] Batch live quote fetch warning: %s", e)

    from earnings_engine.data.prices import load_prices_batch, load_price_metrics_batch
    from earnings_engine.data.catalysts_news import get_recent_catalysts_batch
    from earnings_engine.data.cross_strategy import compute_market_regime_multiplier

    prices_map = load_prices_batch(tickers_to_fetch, settings=settings)
    metrics_map = load_price_metrics_batch(tickers_to_fetch, settings=settings)
    catalysts_map = get_recent_catalysts_batch(tickers_to_fetch, limit_per_ticker=3, settings=settings)
    macro_info = None
    try:
        macro_info = compute_market_regime_multiplier(settings)
    except Exception as e:
        logger.debug("[BREAKOUT-HOT] Macro precompute warning: %s", e)

    # 2. Rescore hot tickers with freshest prices
    def _score(key: str) -> tuple[str, dict | None]:
        parts = key.split("::")
        ticker = parts[0]
        strat = parts[1] if len(parts) > 1 else "CLASSIC_TECHNICAL"
        return key, _score_single_ticker(
            ticker,
            settings,
            strategy=strat,
            use_live_quote=False,
            prices_df=prices_map.get(ticker),
            metrics=metrics_map.get(ticker),
            catalysts=catalysts_map.get(ticker),
            macro_info=macro_info,
        )

    with ThreadPoolExecutor(max_workers=6) as executor:
        scored = list(executor.map(_score, hot_keys))

    for key, result in scored:
        if result is None:
            _demote_hot(key, settings=settings)
            continue

        parts = key.split("::")
        ticker = parts[0]
        strat = parts[1] if len(parts) > 1 else "CLASSIC_TECHNICAL"
        result["strategy"] = strat

        new_score = result.get("composite_score", 0)
        if _should_be_hot(result):
            _pool["hot"][key] = {"result": result, "consecutive_low": 0}
        else:
            if key in _pool["hot"]:
                _pool["hot"][key]["result"] = result
                _demote_hot(key, settings=settings)

    _rebuild_candidates()
    save_breakout_pool_to_db(settings)

    elapsed = round(time.perf_counter() - t0, 2)
    now_iso = datetime.now(timezone.utc).isoformat()
    _pool["last_hot_scan_at"] = now_iso
    _pool["last_scan_at"] = now_iso

    summary_msg = f"Rescored {len(hot_keys)} hot setups (hot={len(_pool['hot'])}, warm={len(_pool['warm'])})"
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
    strategy: str = "CLASSIC_TECHNICAL",
) -> list[dict[str, Any]]:
    """Scan available tickers and return candidates sorted by score DESC point-in-time using the specified strategy."""
    strategy_clean = (strategy or "CLASSIC_TECHNICAL").upper().strip()
    if strategy_clean not in BREAKOUT_STRATEGIES:
        strategy_clean = "CLASSIC_TECHNICAL"

    if asof_date is None and strategy_clean == "CLASSIC_TECHNICAL":
        # Live classic scan: use the tiered pool system
        run_cold_scan(settings, universe=universe)
        return list(_pool["candidates"])

    from concurrent.futures import ThreadPoolExecutor
    from earnings_engine.data.prices import load_prices_batch, load_price_metrics_batch
    from earnings_engine.data.catalysts_news import get_recent_catalysts_batch
    from earnings_engine.data.cross_strategy import compute_market_regime_multiplier

    ticker_list = _resolve_universe_tickers(settings, universe)
    if strategy_clean == "NSE_FO_CALL_WALL":
        ticker_list = [t for t in ticker_list if is_fno_eligible(t)]
    if not ticker_list:
        return []

    t0 = time.perf_counter()

    prices_map = load_prices_batch(ticker_list, settings=settings)
    metrics_map = load_price_metrics_batch(ticker_list, settings=settings)
    catalysts_map = get_recent_catalysts_batch(ticker_list, limit_per_ticker=3, settings=settings)
    macro_info = None
    try:
        macro_info = compute_market_regime_multiplier(settings)
    except Exception as e:
        logger.debug("[BREAKOUT-SCAN] Macro precompute warning: %s", e)

    def _score(ticker: str) -> dict | None:
        return _score_single_ticker(
            ticker,
            settings,
            asof_date=asof_date,
            strategy=strategy_clean,
            prices_df=prices_map.get(ticker),
            metrics=metrics_map.get(ticker),
            catalysts=catalysts_map.get(ticker),
            macro_info=macro_info,
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        scored = list(executor.map(_score, ticker_list))

    candidates = [c for c in scored if c is not None and c.get("composite_score", 0) >= BREAKOUT_MIN_SCORE]
    candidates.sort(key=lambda x: x["composite_score"], reverse=True)
    candidates = candidates[:BREAKOUT_MAX_CANDIDATES]

    elapsed = round(time.perf_counter() - t0, 2)
    logger.info(
        "[BREAKOUT] Scan (strategy=%s, asof=%s): %d tickers, %d candidates in %.1fs",
        strategy_clean, asof_date or "LIVE", len(ticker_list), len(candidates), elapsed,
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


def confirm_breakout_outcomes(settings: Settings | None = None) -> dict[str, Any]:
    """Reconcile and confirm real-world outcomes for all tracked breakout setups against latest price history.

    Audits pending/active setups, evaluates post-signal candles against breakout_trigger,
    target_price, and stop_loss with a 0.15% confirmation buffer, and updates database records.
    """
    settings = settings or Settings()
    t_start = time.perf_counter()
    from earnings_engine.data.prices import load_prices, _connect

    updated_count = 0
    resolved_count = 0
    now_iso = datetime.now(timezone.utc).isoformat()

    try:
        with _connect(settings) as conn:
            _init_breakout_db(conn)
            rows = conn.execute(
                """
                SELECT ticker, strategy, signal_date, signal_price, breakout_trigger,
                       target_price, stop_loss, outcome, created_at
                FROM breakout_radar
                WHERE outcome IN ('ACTIVE', 'PENDING', 'COILING', 'COILING_IN_PROFIT', 'COILING_IN_RANGE')
                   OR outcome IS NULL
                """
            ).fetchall()

            if not rows:
                return {"success": True, "audited_count": 0, "resolved_count": 0, "duration_s": 0.0}

            updates = []
            for row in rows:
                ticker, strat, sig_date, sig_price, trigger, target, stop, prev_outcome, _ = row
                if not ticker or not sig_date or not trigger:
                    continue

                prices_df = load_prices(ticker, settings)
                if prices_df is None or prices_df.empty:
                    continue

                sig_clean = str(sig_date).strip()[:10]
                future_df = prices_df.loc[prices_df.index > sig_clean]
                if future_df.empty:
                    continue

                all_closes = pd.to_numeric(prices_df["close"], errors="coerce").dropna()
                cur_price = float(all_closes.iloc[-1])
                cur_date = str(prices_df.index[-1])[:10]

                f_highs = pd.to_numeric(future_df["high"], errors="coerce") if "high" in future_df.columns else pd.to_numeric(future_df["close"], errors="coerce")
                f_lows = pd.to_numeric(future_df["low"], errors="coerce") if "low" in future_df.columns else pd.to_numeric(future_df["close"], errors="coerce")
                post_high = float(f_highs.max()) if not f_highs.empty else sig_price
                post_low = float(f_lows.min()) if not f_lows.empty else sig_price

                realized_ret = round(((cur_price - sig_price) / sig_price) * 100, 2)
                max_gain = round(((post_high - sig_price) / sig_price) * 100, 2)
                days_el = len(future_df)

                # 0.15% trigger confirmation buffer
                breakout_fired = bool(post_high >= trigger * 1.0015 or cur_price >= trigger * 1.0015)

                # Keep today's freshly-signaled breakouts in the active pool — do NOT resolve
                # them on day-0. They should stay live so traders can still track/enter them.
                is_today_signal = sig_clean == cur_date

                if target and post_high >= target:
                    outcome = "TARGET_HIT"
                    outcome_label = f"Target Hit 🎯 (+{max_gain}%)"
                    outcome_badge = "emerald"
                    broke_happened = 1
                elif breakout_fired and not is_today_signal:
                    if stop and (post_low <= stop or cur_price <= stop):
                        outcome = "STOP_LOSS_HIT"
                        outcome_label = f"Stop Hit 🛑 ({realized_ret:+0.1f}%)"
                        outcome_badge = "rose"
                        broke_happened = 0
                    elif cur_price >= sig_price:
                        outcome = "BREAKOUT_SUCCEEDED"
                        outcome_label = f"Breakout Succeeded ✅ ({realized_ret:+0.1f}%)"
                        outcome_badge = "emerald"
                        broke_happened = 1
                    else:
                        outcome = "BREAKOUT_RETRACED"
                        outcome_label = f"Breakout Retraced ⚠️ ({realized_ret:+0.1f}%)"
                        outcome_badge = "amber"
                        broke_happened = 0
                elif stop and (post_low <= stop or cur_price <= stop):
                    outcome = "SETUP_FAILED"
                    outcome_label = f"Setup Failed ❌ ({realized_ret:+0.1f}%)"
                    outcome_badge = "rose"
                    broke_happened = 0
                elif cur_price >= sig_price:
                    outcome = "COILING_IN_PROFIT"
                    outcome_label = f"Coiling In Green 🟢 ({realized_ret:+0.1f}%)"
                    outcome_badge = "emerald"
                    broke_happened = 0
                else:
                    outcome = "COILING_IN_RANGE"
                    outcome_label = f"Coiling In Range 🗜️ ({realized_ret:+0.1f}%)"
                    outcome_badge = "slate"
                    broke_happened = 0

                if outcome in ("TARGET_HIT", "BREAKOUT_SUCCEEDED", "STOP_LOSS_HIT", "SETUP_FAILED", "BREAKOUT_RETRACED"):
                    resolved_count += 1

                updates.append((
                    cur_price, cur_date, realized_ret, max_gain, broke_happened,
                    outcome, outcome_label, outcome_badge, days_el, now_iso,
                    ticker, strat
                ))

            if updates:
                conn.executemany(
                    """
                    UPDATE breakout_radar
                    SET current_price = ?, current_date = ?, realized_return_pct = ?,
                        max_gain_pct = ?, breakout_happened = ?, outcome = ?,
                        outcome_label = ?, outcome_badge = ?, days_elapsed = ?,
                        updated_at = ?
                    WHERE ticker = ? AND strategy = ?
                    """,
                    updates
                )
                conn.commit()
                updated_count = len(updates)

    except Exception as e:
        logger.error("[BREAKOUT-OUTCOMES] Failed confirming breakout outcomes: %s", e)
        return {"success": False, "error": str(e), "audited_count": 0, "resolved_count": 0}

    return {
        "success": True,
        "audited_count": updated_count,
        "resolved_count": resolved_count,
        "duration_s": round(time.perf_counter() - t_start, 2),
        "run_at": now_iso,
    }



# ---------------------------------------------------------------------------
# Legacy compat alias
# ---------------------------------------------------------------------------
breakout_scanner_loop = tiered_scanner_loop

