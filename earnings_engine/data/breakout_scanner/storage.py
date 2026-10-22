"""Storage, persistence, and state management for Breakout Radar."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from earnings_engine.config import Settings
from earnings_engine.data.db_helpers import build_upsert_sql, row_to_dict
from earnings_engine.data.universe import is_fno_eligible
from earnings_engine.data.breakout_scanner.constants import (
    BREAKOUT_STRATEGIES,
    BREAKOUT_RADAR_COLS,
    BREAKOUT_TRACKED_COLS,
    _BREAKOUT_RADAR_COLS,
    _BREAKOUT_TRACKED_COLS,
    HOT_THRESHOLD,
    WARM_THRESHOLD,
    HOT_DEMOTION_THRESHOLD,
    WARM_DEMOTION_THRESHOLD,
)
from earnings_engine.data.breakout_scanner.state import (
    _pool,
    _pool_key,
    _rebuild_candidates,
)
from earnings_engine.data.db import get_db_connection
from earnings_engine.data.breakout_scanner.scoring import _should_be_hot
from earnings_engine.data.breakout_scanner.timeline import get_stock_breakout_timeline
from earnings_engine.data.breakout_scanner.transitions import (
    _promote,
    _demote_hot,
    _demote_warm,
)
from earnings_engine.data.breakout_scanner.audit_log import (
    record_breakout_transition,
    get_breakout_audit_log,
    get_breakout_audit_log_count,
    get_breakout_audit_summary_stats,
    prune_breakout_audit_log,
)
from earnings_engine.data.breakout_scanner.tracked import (
    _extract_strategy_id_from_setup,
    get_tracked_breakouts,
    delete_tracked_breakout,
    delete_tracked_breakouts_by_ticker,
    get_tracked_ticker_set,
    confirm_breakout_outcomes,
)

logger = logging.getLogger(__name__)

_BREAKOUT_DB_INITIALIZED: bool = False


def _init_breakout_db(conn: Any) -> None:
    """Ensure breakout_radar table and performance indices exist with strategy tracking."""
    global _BREAKOUT_DB_INITIALIZED
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
        for cand in list(_pool.get("candidates", [])):
            if not isinstance(cand, dict):
                continue
            t = cand.get("ticker")
            strat = cand.get("strategy") or "CLASSIC_TECHNICAL"
            key = f"{t}::{strat}"
            if t and key not in seen:
                seen.add(key)
                records.append(cand)

        if not records:
            logger.debug("[BREAKOUT-DB] No breakout records to persist.")
            return

        cols = [
            "ticker", "strategy", "tier", "company_name", "industry",
            "composite_score", "resistance_score", "volume_score",
            "compression_score", "momentum_score", "fundamental_score",
            "signal_date", "signal_price", "predicted_value", "breakout_trigger",
            "ideal_entry_price", "is_late", "entry_delay_pct", "target_price",
            "stop_loss", "risk_reward_ratio", "current_price", "current_date",
            "realized_return_pct", "max_gain_pct", "breakout_happened",
            "outcome", "outcome_label", "outcome_badge", "days_elapsed",
            "setup_archetype", "volume_ratio", "atr_pct", "pct_from_high",
            "avg_quality_score", "scanned_at", "data_json", "updated_at"
        ]
        sql = build_upsert_sql(
            "breakout_radar",
            columns=cols,
            conflict_columns=["ticker", "strategy"],
            update_columns=cols[2:],
        )

        now_iso = datetime.now(timezone.utc).isoformat()
        params_batch = []
        tracked_batch = []

        for rec in records:
            ticker = rec.get("ticker")
            if not ticker:
                continue

            strat = (rec.get("strategy") or "CLASSIC_TECHNICAL").upper().strip()
            if strat == "NSE_FO_CALL_WALL" and not is_fno_eligible(ticker):
                logger.debug("[BREAKOUT-DB] Filtered out non-F&O ticker %s for NSE_FO_CALL_WALL", ticker)
                continue

            tier = (rec.get("tier") or "WARM").upper()
            sig_date = rec.get("signal_date") or now_iso[:10]
            sig_price = rec.get("signal_price") or rec.get("current_price") or 0.0
            trigger = rec.get("breakout_trigger") or sig_price
            target = rec.get("target_price") or (trigger * 1.08 if trigger else sig_price)
            stop = rec.get("stop_loss") or (trigger * 0.95 if trigger else sig_price)
            rr = rec.get("risk_reward_ratio") or 2.0
            is_late_val = 1 if rec.get("is_late") else 0
            entry_delay = float(rec.get("entry_delay_pct") or 0.0)

            cur_price = rec.get("current_price") or sig_price
            cur_date = rec.get("current_date") or sig_date
            realized_ret = float(rec.get("realized_return_pct") or 0.0)
            max_gain = float(rec.get("max_gain_pct") or 0.0)
            breakout_happened_val = 1 if rec.get("breakout_happened") else 0
            outcome_val = rec.get("outcome") or "ACTIVE"
            outcome_label_val = rec.get("outcome_label") or "Active Setup"
            outcome_badge_val = rec.get("outcome_badge") or "ACTIVE"
            days_el = int(rec.get("days_elapsed") or 0)

            try:
                data_json_str = json.dumps(rec, default=str)
            except Exception:
                data_json_str = "{}"

            params_batch.append((
                ticker, strat, tier, rec.get("company_name"), rec.get("industry"),
                float(rec.get("composite_score") or 0),
                float(rec.get("resistance_score") or 0),
                float(rec.get("volume_score") or 0),
                float(rec.get("compression_score") or 0),
                float(rec.get("momentum_score") or 0),
                float(rec.get("fundamental_score") or 0),
                sig_date, float(sig_price),
                float(rec.get("predicted_value") or sig_price),
                float(trigger),
                float(rec.get("ideal_entry_price") or trigger),
                is_late_val, entry_delay, float(target), float(stop), float(rr),
                float(cur_price), cur_date, realized_ret, max_gain,
                breakout_happened_val, outcome_val, outcome_label_val, outcome_badge_val,
                days_el, rec.get("setup_archetype"),
                float(rec.get("volume_ratio") or 1.0),
                float(rec.get("atr_pct") or 0.0),
                float(rec.get("pct_from_high") or 0.0),
                float(rec.get("avg_quality_score") or 0.0),
                rec.get("scanned_at") or now_iso,
                data_json_str, now_iso
            ))

            tracked_batch.append((
                ticker, rec.get("company_name"), rec.get("industry"),
                tier, sig_date, float(sig_price),
                float(rec.get("predicted_value") or sig_price),
                float(trigger),
                float(rec.get("ideal_entry_price") or trigger),
                is_late_val, entry_delay, float(target), float(stop), float(rr),
                float(rec.get("composite_score") or 0),
                float(rec.get("resistance_score") or 0),
                float(rec.get("volume_score") or 0),
                float(rec.get("compression_score") or 0),
                float(rec.get("momentum_score") or 0),
                float(rec.get("fundamental_score") or 0),
                float(rec.get("volume_ratio") or 1.0),
                float(rec.get("atr_pct") or 0.0),
                float(rec.get("pct_from_high") or 0.0),
                rec.get("setup_archetype") or "Breakout Setup",
                float(cur_price), cur_date, realized_ret, max_gain,
                breakout_happened_val, outcome_val, outcome_label_val, outcome_badge_val,
                days_el, rec.get("scanned_at") or now_iso,
                data_json_str, now_iso, now_iso
            ))

        if params_batch:
            conn.executemany(sql, params_batch)
            logger.info("[BREAKOUT-DB] Persisted %d breakout records across strategies.", len(params_batch))

        if tracked_batch:
            try:
                from earnings_engine.data.migrations import apply_migrations
                apply_migrations(settings)
                tracked_sql = """
                    INSERT INTO breakout_tracked_signals (
                        ticker, company_name, industry, tier, signal_date, signal_price,
                        predicted_value, breakout_trigger, ideal_entry_price, is_late,
                        entry_delay_pct, target_price, stop_loss, risk_reward_ratio,
                        composite_score, resistance_score, volume_score, compression_score,
                        momentum_score, fundamental_score, volume_ratio, atr_pct, pct_from_high,
                        setup_archetype, current_price, current_date, realized_return_pct,
                        max_gain_pct, breakout_happened, outcome, outcome_label, outcome_badge,
                        days_elapsed, scanned_at, data_json, created_at, updated_at
                    ) VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                    )
                    ON CONFLICT(ticker, signal_date) DO UPDATE SET
                        current_price = excluded.current_price,
                        current_date = excluded.current_date,
                        realized_return_pct = excluded.realized_return_pct,
                        max_gain_pct = excluded.max_gain_pct,
                        breakout_happened = excluded.breakout_happened,
                        outcome = excluded.outcome,
                        outcome_label = excluded.outcome_label,
                        outcome_badge = excluded.outcome_badge,
                        days_elapsed = excluded.days_elapsed,
                        composite_score = excluded.composite_score,
                        breakout_trigger = excluded.breakout_trigger,
                        target_price = excluded.target_price,
                        stop_loss = excluded.stop_loss,
                        data_json = excluded.data_json,
                        updated_at = excluded.updated_at
                """
                conn.executemany(tracked_sql, tracked_batch)
                logger.info("[BREAKOUT-TRACKED] Synced %d signals into permanent audit ledger.", len(tracked_batch))
            except Exception as tr_err:
                logger.warning("[BREAKOUT-TRACKED] Failed inserting into tracked ledger: %s", tr_err)

        if hasattr(conn, "commit"):
            conn.commit()
    except Exception as e:
        logger.warning("[BREAKOUT-DB] Failed to save breakout pool: %s", e)
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


def load_breakout_pool_from_db(settings: Settings | None = None) -> bool:
    """Restore Hot and Warm pools into memory from the persistent SQLite database."""
    settings = settings or Settings()
    conn = None
    try:
        conn = get_db_connection(settings)
        _init_breakout_db(conn)

        cur = conn.execute(
            """
            SELECT * FROM breakout_radar
            ORDER BY composite_score DESC
            """
        )
        rows = cur.fetchall()
        if not rows:
            logger.info("[BREAKOUT-DB] No saved breakout setups found in DB.")
            return False

        _pool["hot"].clear()
        _pool["warm"].clear()

        hot_count = 0
        warm_count = 0

        for row in rows:
            row_dict = row_to_dict(cur, row)
            ticker = row_dict.get("ticker")
            tier = (row_dict.get("tier") or "WARM").upper()
            strat = (row_dict.get("strategy") or "CLASSIC_TECHNICAL").upper().strip()

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

