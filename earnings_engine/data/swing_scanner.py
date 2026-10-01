"""Swing Trading & Cycle Oscillators — Tiered Async Pooling Scanner & Scoring Engine.

Architecture: Three-tier graduated pool system mirroring Breakout Radar.
Avoids rescanning the entire universe on every cycle. Stocks are promoted
and demoted between tiers based on horizontal support channel proximity,
quality grade, and volume accumulation rhythm.

Tiers
-----
- **T0 (Cold)** — Full universe scan every ``SWING_COLD_INTERVAL_MIN`` (default 60 min).
  Computes ATR horizontal channels, multi-cycle support floors, and initial swing scores.
- **T1 (Warm)** — Rescored every ``SWING_WARM_INTERVAL_MIN`` (default 15 min).
  Stocks with ``composite_score ≥ SWING_WARM_THRESHOLD`` (25) or within 3%–10% of support.
- **T2 (Hot)** — Rescored every ``SWING_HOT_INTERVAL_MIN`` (default 5 min).
  Stocks in Active Buy Zone: ``0% ≤ dist_to_support ≤ 3%``, Strong Buy (Grade A + Buy Zone),
  support bounces, or breakdowns.

Demotion requires **two consecutive** out-of-band cycles to prevent flicker.
Fast-tracking immediately promotes any stock bouncing off support with volume surge.

Score Components (0 – 100)
--------------------------
1. Support Proximity      (0-35 pts) — closeness to support channel floor (0-3% = max)
2. Channel Quality/Cycles (0-20 pts) — multi-cycle rhythm & horizontal band stability
3. Volume Accumulation    (0-15 pts) — accumulation volume at support floor
4. Momentum & Compression (0-15 pts) — 30D trend and ATR channel squeeze
5. Fundamental Bonus      (0-15 pts) — quarterly earnings quality track record
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
from earnings_engine.data import swing_ranges as swing_ranges_mod
from earnings_engine.data.tier_pools import (
    TierPoolConfig,
    TierPoolManager,
    PoolEntry,
)
from earnings_engine.logging_utils import get_logger

logger = get_logger("earnings_engine.data.swing_scanner")

# ---------------------------------------------------------------------------
# Configuration (overridable via environment variables)
# ---------------------------------------------------------------------------
SWING_MIN_SCORE: int = int(os.environ.get("SWING_MIN_SCORE", "20"))
SWING_MAX_CANDIDATES: int = int(os.environ.get("SWING_MAX_CANDIDATES", "100"))

# Tier thresholds
SWING_HOT_THRESHOLD: int = int(os.environ.get("SWING_HOT_THRESHOLD", "50"))
SWING_WARM_THRESHOLD: int = int(os.environ.get("SWING_WARM_THRESHOLD", "25"))
SWING_HOT_DEMOTION_THRESHOLD: int = int(os.environ.get("SWING_HOT_DEMOTION", "25"))
SWING_WARM_DEMOTION_THRESHOLD: int = int(os.environ.get("SWING_WARM_DEMOTION", "15"))

# Scan intervals (minutes)
SWING_COLD_INTERVAL_MIN: int = int(os.environ.get("SWING_COLD_INTERVAL_MIN", "60"))
SWING_WARM_INTERVAL_MIN: int = int(os.environ.get("SWING_WARM_INTERVAL_MIN", "15"))
SWING_HOT_INTERVAL_MIN: int = int(os.environ.get("SWING_HOT_INTERVAL_MIN", "5"))


def _custom_swing_hot_qualifier(candidate: dict[str, Any]) -> bool:
    """Fast-track into HOT tier if in Strong Buy or immediate Support Zone (0-3% distance with volume)."""
    sig = candidate.get("swing_signal") or candidate.get("signal") or ""
    dist_pct = float(candidate.get("dist_to_support_pct", 99.0) or 99.0)
    vol_score = float(candidate.get("volume_score", 0.0) or 0.0)
    return (
        sig in ("Strong Buy", "Buy Zone")
        or (0.0 <= dist_pct <= 3.0 and vol_score >= 10.0)
    )


def _custom_swing_hot_demotion_guard(candidate: dict[str, Any]) -> bool:
    """Guard against HOT demotion if price is currently hovering tightly on support (dist <= 2.5%)."""
    dist_pct = float(candidate.get("dist_to_support_pct", 99.0) or 99.0)
    return 0.0 <= dist_pct <= 2.5


swing_tier_config = TierPoolConfig(
    domain="swing",
    hot_threshold=float(SWING_HOT_THRESHOLD),
    warm_threshold=float(SWING_WARM_THRESHOLD),
    hot_demotion_threshold=float(SWING_HOT_DEMOTION_THRESHOLD),
    warm_demotion_threshold=float(SWING_WARM_DEMOTION_THRESHOLD),
    demotion_strikes=2,
    max_candidates=SWING_MAX_CANDIDATES,
    min_score=float(SWING_MIN_SCORE),
    table_name="swing_radar",
    audit_table_name="strategy_tier_audit_log",
    custom_hot_qualifier=_custom_swing_hot_qualifier,
    custom_hot_demotion_guard=_custom_swing_hot_demotion_guard,
    key_builder=lambda ticker, strat: ticker.upper(),
)

swing_tier_manager = TierPoolManager(swing_tier_config)

# Share in-memory pool state directly with TierPoolManager
_pool: dict[str, Any] = swing_tier_manager._pool


def _rebuild_candidates() -> None:
    """Merge hot + warm pools into a deduplicated, sorted candidates list."""
    swing_tier_manager._rebuild_candidates()


def _init_swing_radar_db(conn: Any) -> None:
    """Ensure swing_radar table and indices exist."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS swing_radar (
            ticker TEXT PRIMARY KEY,
            tier TEXT NOT NULL DEFAULT 'WARM',
            company_name TEXT,
            industry TEXT,
            composite_score REAL DEFAULT 0,
            proximity_score REAL DEFAULT 0,
            channel_score REAL DEFAULT 0,
            volume_score REAL DEFAULT 0,
            momentum_score REAL DEFAULT 0,
            fundamental_score REAL DEFAULT 0,
            current_price REAL,
            support_level REAL,
            resistance_level REAL,
            spread_pct REAL,
            dist_to_support_pct REAL,
            channel_position_pct REAL,
            signal TEXT DEFAULT 'Neutral',
            source TEXT DEFAULT 'auto',
            cycles INTEGER DEFAULT 0,
            avg_cycle_days REAL DEFAULT 0,
            thirty_day_return_pct REAL,
            earnings_date TEXT,
            earnings_score REAL,
            kronos_json TEXT,
            ai_synthesis_json TEXT,
            consensus_json TEXT,
            scanned_at TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )
        """
    )
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_swing_radar_tier ON swing_radar(tier)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_swing_radar_score ON swing_radar(composite_score DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_swing_radar_signal ON swing_radar(signal)")
    except Exception:
        pass


def save_swing_pool_to_db(settings: Settings | None = None) -> None:
    """Persist current in-memory Hot, Warm, and candidate swing setups into SQLite & Turso."""
    settings = settings or Settings()
    try:
        conn = get_db_connection(settings)
        _init_swing_radar_db(conn)

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

            rows_to_insert.append((
                ticker,
                r.get("tier", "WARM"),
                r.get("company_name"),
                r.get("industry"),
                float(r.get("composite_score", 0)),
                float(r.get("proximity_score", 0)),
                float(r.get("channel_score", 0)),
                float(r.get("volume_score", 0)),
                float(r.get("momentum_score", 0)),
                float(r.get("fundamental_score", 0)),
                float(r["current_price"]) if r.get("current_price") is not None else None,
                float(r["current_support"]) if r.get("current_support") is not None else None,
                float(r["next_resistance"]) if r.get("next_resistance") is not None else None,
                float(r["spread_pct"]) if r.get("spread_pct") is not None else None,
                float(r["dist_to_support_pct"]) if r.get("dist_to_support_pct") is not None else None,
                float(r["channel_position_pct"]) if r.get("channel_position_pct") is not None else None,
                r.get("swing_signal", "Neutral"),
                r.get("source", "auto"),
                int(r.get("cycles") or 0),
                float(r.get("avg_cycle_days") or 0),
                float(r["thirty_day_return_pct"]) if r.get("thirty_day_return_pct") is not None else None,
                r.get("earnings_date"),
                float(r["prev_quarter_earnings_score"]) if r.get("prev_quarter_earnings_score") is not None else None,
                json.dumps(r.get("kronos_prediction") or {}),
                json.dumps(r.get("ai_synthesis") or {}),
                json.dumps(r.get("consensus") or {}),
                r.get("scanned_at") or now_iso,
                now_iso,
            ))

        conn.executemany(
            """
            INSERT INTO swing_radar (
                ticker, tier, company_name, industry, composite_score,
                proximity_score, channel_score, volume_score, momentum_score,
                fundamental_score, current_price, support_level, resistance_level,
                spread_pct, dist_to_support_pct, channel_position_pct, signal,
                source, cycles, avg_cycle_days, thirty_day_return_pct,
                earnings_date, earnings_score, kronos_json, ai_synthesis_json,
                consensus_json, scanned_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticker) DO UPDATE SET
                tier = excluded.tier,
                composite_score = excluded.composite_score,
                proximity_score = excluded.proximity_score,
                channel_score = excluded.channel_score,
                volume_score = excluded.volume_score,
                momentum_score = excluded.momentum_score,
                fundamental_score = excluded.fundamental_score,
                current_price = excluded.current_price,
                support_level = excluded.support_level,
                resistance_level = excluded.resistance_level,
                spread_pct = excluded.spread_pct,
                dist_to_support_pct = excluded.dist_to_support_pct,
                channel_position_pct = excluded.channel_position_pct,
                signal = excluded.signal,
                source = excluded.source,
                cycles = excluded.cycles,
                avg_cycle_days = excluded.avg_cycle_days,
                thirty_day_return_pct = excluded.thirty_day_return_pct,
                earnings_date = excluded.earnings_date,
                earnings_score = excluded.earnings_score,
                kronos_json = excluded.kronos_json,
                ai_synthesis_json = excluded.ai_synthesis_json,
                consensus_json = excluded.consensus_json,
                scanned_at = excluded.scanned_at,
                updated_at = excluded.updated_at
            """,
            rows_to_insert,
        )
        conn.commit()
        logger.info("[SWING-DB] Saved %d swing setups to SQLite/Turso", len(rows_to_insert))
    except Exception as e:
        logger.warning("[SWING-DB] Failed to save swing setups to database: %s", e)


def load_swing_pool_from_db(settings: Settings | None = None) -> None:
    """Hydrate in-memory pool from DB on startup so the UI is immediately populated."""
    settings = settings or Settings()
    try:
        conn = get_db_connection(settings)
        _init_swing_radar_db(conn)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM swing_radar ORDER BY composite_score DESC")
        rows = cursor.fetchall()
        if not rows:
            return

        cols = [c[0] for c in cursor.description]
        hot: dict[str, dict] = {}
        warm: dict[str, dict] = {}

        for row in rows:
            d = dict(zip(cols, row))
            sym = d.get("ticker")
            if not sym:
                continue

            item = {
                "ticker": sym,
                "tier": d.get("tier", "WARM"),
                "company_name": d.get("company_name"),
                "industry": d.get("industry"),
                "composite_score": d.get("composite_score", 0),
                "proximity_score": d.get("proximity_score", 0),
                "channel_score": d.get("channel_score", 0),
                "volume_score": d.get("volume_score", 0),
                "momentum_score": d.get("momentum_score", 0),
                "fundamental_score": d.get("fundamental_score", 0),
                "current_price": d.get("current_price"),
                "current_support": d.get("support_level"),
                "next_resistance": d.get("resistance_level"),
                "spread_pct": d.get("spread_pct"),
                "dist_to_support_pct": d.get("dist_to_support_pct"),
                "channel_position_pct": d.get("channel_position_pct"),
                "swing_signal": d.get("signal", "Neutral"),
                "source": d.get("source", "auto"),
                "cycles": d.get("cycles", 0),
                "avg_cycle_days": d.get("avg_cycle_days", 0),
                "thirty_day_return_pct": d.get("thirty_day_return_pct"),
                "earnings_date": d.get("earnings_date"),
                "prev_quarter_earnings_score": d.get("earnings_score"),
                "kronos_prediction": json.loads(d.get("kronos_json") or "{}"),
                "ai_synthesis": json.loads(d.get("ai_synthesis_json") or "{}"),
                "consensus": json.loads(d.get("consensus_json") or "{}"),
                "scanned_at": d.get("scanned_at"),
                "swing_range": {
                    "lower_bound": d.get("support_level"),
                    "upper_bound": d.get("resistance_level"),
                    "source": d.get("source", "auto"),
                    "cycles": d.get("cycles", 0),
                    "avg_cycle_days": d.get("avg_cycle_days", 0),
                }
            }

            entry = PoolEntry(
                result=item,
                consecutive_low=0,
                tier=str(d.get("tier", "WARM")).upper(),
                last_scored_at=d.get("scanned_at") or datetime.now(timezone.utc).isoformat(),
            )
            if d.get("tier") == "HOT":
                hot[sym] = entry
            else:
                warm[sym] = entry

        _pool["hot"] = hot
        _pool["warm"] = warm
        _rebuild_candidates()
        logger.info("[SWING-DB] Hydrated %d hot + %d warm candidates from DB", len(hot), len(warm))
    except Exception as e:
        logger.warning("[SWING-DB] Failed to hydrate swing pool: %s", e)


# ---------------------------------------------------------------------------
# Scoring Helpers
# ---------------------------------------------------------------------------

def _score_support_proximity(current_price: float, support: float, resistance: float) -> tuple[float, float, float, str]:
    """Score proximity to support floor (0-35 pts).

    Returns (score, dist_to_support_pct, channel_position_pct, signal)
    """
    if current_price <= 0 or support <= 0 or resistance <= support:
        return 0.0, 0.0, 0.0, "Neutral"

    dist_pct = ((current_price - support) / support) * 100
    spread = resistance - support
    pos_pct = max(0.0, min(100.0, ((current_price - support) / spread) * 100))

    if dist_pct < -3.0:
        # Below support floor (Breakdown)
        score = 0.0
        signal = "Breakdown"
    elif dist_pct <= 0.0:
        # At immediate support boundary (-3% to 0%)
        score = 30.0
        signal = "Buy Zone"
    elif dist_pct <= 1.5:
        # Sweet spot: right on top of support
        score = 35.0
        signal = "Buy Zone"
    elif dist_pct <= 3.5:
        # Near support
        score = 28.0
        signal = "Buy Zone"
    elif dist_pct <= 6.0:
        score = 18.0
        signal = "Buy"
    elif dist_pct <= 10.0:
        score = 10.0
        signal = "Neutral"
    elif pos_pct >= 95.0:
        score = 0.0
        signal = "Overbought"
    elif pos_pct >= 85.0:
        score = 2.0
        signal = "Sell Zone"
    else:
        score = 5.0
        signal = "Neutral"

    return score, round(dist_pct, 2), round(pos_pct, 1), signal


def _score_channel_quality(cycles: int, spread_pct: float, source: str) -> float:
    """Score channel quality and reliability (0-20 pts)."""
    score = 0.0
    if source == "user":
        score += 8.0  # User verified channel
    else:
        score += 4.0

    if cycles >= 4:
        score += 12.0
    elif cycles >= 2:
        score += 8.0
    elif cycles == 1:
        score += 4.0
    else:
        score += 2.0

    # Reward decent spread (10% - 40%), penalize razor thin (<5%) or wild (>60%)
    if 10.0 <= spread_pct <= 40.0:
        score = min(20.0, score + 2.0)

    return min(20.0, score)


def _score_volume_bounce(volumes: pd.Series) -> float:
    """Score volume accumulation at support (0-15 pts)."""
    if len(volumes) < 5:
        return 5.0
    avg_20 = float(volumes.tail(21).iloc[:-1].mean()) if len(volumes) >= 21 else float(volumes.mean())
    today = float(volumes.iloc[-1])
    if avg_20 <= 0:
        return 5.0
    ratio = today / avg_20
    if 1.2 <= ratio < 2.5:
        return 15.0
    elif 1.0 <= ratio < 1.2:
        return 10.0
    elif ratio >= 2.5:
        return 8.0  # Possible climax / high volatility
    else:
        return 5.0


def _score_momentum_compression(closes: pd.Series, mom_30d: float | None) -> float:
    """Score momentum and volatility compression (0-15 pts)."""
    score = 5.0
    if mom_30d is not None:
        if -5.0 <= mom_30d <= 15.0:
            score += 5.0  # Controlled base
        elif mom_30d > 15.0:
            score += 2.0  # Extended
        elif mom_30d < -15.0:
            score -= 2.0  # Sharp falling knife

    if len(closes) >= 14:
        # Check ATR/Price compression
        std_14 = float(closes.tail(14).std())
        mean_14 = float(closes.tail(14).mean())
        if mean_14 > 0:
            cv = (std_14 / mean_14) * 100
            if cv < 3.0:
                score += 5.0
            elif cv < 6.0:
                score += 3.0

    return max(0.0, min(15.0, score))


def _score_fundamental_bonus(earnings_score: float | None) -> float:
    """Score historical earnings quality (0-15 pts)."""
    if earnings_score is None:
        return 6.0
    # earnings_score is out of 9
    pct = max(0.0, min(9.0, float(earnings_score))) / 9.0
    return round(pct * 15.0, 1)


# ---------------------------------------------------------------------------
# Single Ticker Evaluator
# ---------------------------------------------------------------------------

def evaluate_stock_swing(
    ticker: str,
    settings: Settings,
    prices_df: pd.DataFrame | None = None,
    stored_range: dict[str, Any] | None = None,
    earnings_date: str | None = None,
    earnings_score: float | None = None,
) -> dict[str, Any] | None:
    """Compute full swing metrics and composite score for one ticker."""
    try:
        if prices_df is None or prices_df.empty:
            from earnings_engine.data.prices import load_prices
            prices_df = load_prices(ticker, settings)
        if prices_df.empty or len(prices_df) < 20:
            return None

        closes = prices_df["close"].dropna()
        volumes = prices_df["volume"].dropna()
        if len(closes) < 20:
            return None

        cur_price = float(closes.iloc[-1])
        if cur_price <= 0:
            return None

        # Load or derive support / resistance range
        from earnings_engine.data import swing_ranges as swing_ranges_mod
        sr = stored_range or swing_ranges_mod.get_swing_range("ALL", ticker, settings)

        if sr and sr.get("lower_bound") and sr.get("upper_bound"):
            support = float(sr["lower_bound"])
            resistance = float(sr["upper_bound"])
            source = sr.get("source", "auto")
            cycles = int(sr.get("cycles") or 0)
            avg_cycle_days = float(sr.get("avg_cycle_days") or 0)
        else:
            # Auto-derive from 60D channel extremes
            window_60 = min(len(closes), 63)
            recent_closes = closes.tail(window_60)
            support = float(recent_closes.min())
            resistance = float(recent_closes.max())
            source = "auto"
            cycles = 1
            avg_cycle_days = 45.0

        if resistance <= support:
            resistance = support * 1.15

        spread_pct = round(((resistance - support) / support) * 100, 1)

        # 30D Return
        mom_30d = None
        if len(closes) >= 22:
            prev_price = float(closes.iloc[-22])
            if prev_price > 0:
                mom_30d = round(((cur_price - prev_price) / prev_price) * 100, 2)

        # Scoring
        prox_score, dist_pct, pos_pct, signal = _score_support_proximity(cur_price, support, resistance)
        chan_score = _score_channel_quality(cycles, spread_pct, source)
        vol_score = _score_volume_bounce(volumes)
        mom_score = _score_momentum_compression(closes, mom_30d)
        fund_score = _score_fundamental_bonus(earnings_score)

        # Macro Market Conditions & Volatility Regime Weighting
        macro_mult = 1.0
        macro_info: dict[str, Any] = {}
        try:
            from earnings_engine.data.cross_strategy import compute_market_regime_multiplier
            macro_info = compute_market_regime_multiplier(settings)
            macro_mult = float(macro_info.get("swing_multiplier", 1.0))
        except Exception:
            pass

        comp_score = round((prox_score + chan_score + vol_score + mom_score + fund_score) * macro_mult, 1)
        comp_score = max(0.0, min(100.0, comp_score))

        # Upgrade signal if high quality in buy zone
        if signal == "Buy Zone" and earnings_score is not None and earnings_score >= 6.0:
            signal = "Strong Buy"

        # In risk-off defensive regime, tighten floor criteria to avoid catching falling knives
        if macro_info.get("macro_bias") == "BEARISH_DEFENSIVE" and dist_pct > 2.5 and signal == "Strong Buy":
            signal = "Buy Zone"

        # Determine Tier
        is_hot = (
            comp_score >= SWING_HOT_THRESHOLD or
            signal in ("Strong Buy", "Buy Zone") or
            (0.0 <= dist_pct <= 3.0 and vol_score >= 10.0)
        )
        tier = "HOT" if is_hot else ("WARM" if comp_score >= SWING_WARM_THRESHOLD else "COLD")

        return {
            "ticker": ticker,
            "tier": tier,
            "composite_score": comp_score,
            "proximity_score": prox_score,
            "channel_score": chan_score,
            "volume_score": vol_score,
            "momentum_score": mom_score,
            "fundamental_score": fund_score,
            "macro_regime": {
                "bias": macro_info.get("macro_bias", "RANGEBOUND_NEUTRAL"),
                "multiplier": macro_mult,
                "pill": macro_info.get("macro_pill", "🟡 Neutral"),
                "pill_color": macro_info.get("pill_color", "#fbbf24"),
                "fear_greed_score": macro_info.get("fear_greed_score"),
                "vix_level": macro_info.get("vix_level"),
            },
            "current_price": round(cur_price, 2),
            "current_support": round(support, 2),
            "next_resistance": round(resistance, 2),
            "spread_pct": spread_pct,
            "dist_to_support_pct": dist_pct,
            "channel_position_pct": pos_pct,
            "swing_signal": signal,
            "source": source,
            "cycles": cycles,
            "avg_cycle_days": avg_cycle_days,
            "thirty_day_return_pct": mom_30d,
            "earnings_date": earnings_date,
            "prev_quarter_earnings_score": earnings_score,
            "scanned_at": datetime.now(timezone.utc).isoformat(),
            "swing_range": {
                "lower_bound": round(support, 2),
                "upper_bound": round(resistance, 2),
                "source": source,
                "cycles": cycles,
                "avg_cycle_days": avg_cycle_days,
            }
        }
    except Exception as e:
        logger.debug("[SWING] Error evaluating %s: %s", ticker, e)
        return None


# ---------------------------------------------------------------------------
# Tiered Rescore Workflows
# ---------------------------------------------------------------------------

def run_hot_rescore(settings: Settings) -> None:
    """Rescore T2 (Hot) candidates every SWING_HOT_INTERVAL_MIN (3-5 min)."""
    if not _pool["hot"]:
        return
    logger.info("[SWING-HOT] Rescoring %d Hot candidates", len(_pool["hot"]))
    t0 = time.time()

    hot_symbols = list(_pool["hot"].keys())
    from earnings_engine.data.prices import load_prices_batch
    prices_map = load_prices_batch(hot_symbols, settings, days=120)
    ranges_map = swing_ranges_mod.get_swing_ranges_batch("ALL", hot_symbols, settings)

    for sym in hot_symbols:
        res = evaluate_stock_swing(
            sym,
            settings,
            prices_df=prices_map.get(sym),
            stored_range=ranges_map.get(sym),
        )
        if res is None:
            continue

        swing_tier_manager.check_hot_demotion(sym, res, settings=settings)

    swing_tier_manager._rebuild_candidates()
    _pool["last_hot_scan_at"] = datetime.now(timezone.utc).isoformat()
    _pool["last_scan_at"] = _pool["last_hot_scan_at"]
    _pool["last_scan_duration_s"] = round(time.time() - t0, 2)
    save_swing_pool_to_db(settings)


def run_warm_rescore(settings: Settings) -> None:
    """Rescore T1 (Warm) candidates every SWING_WARM_INTERVAL_MIN (15 min)."""
    if not _pool["warm"]:
        return
    logger.info("[SWING-WARM] Rescoring %d Warm candidates", len(_pool["warm"]))
    t0 = time.time()

    warm_symbols = list(_pool["warm"].keys())
    from earnings_engine.data.prices import load_prices_batch
    prices_map = load_prices_batch(warm_symbols, settings, days=120)
    ranges_map = swing_ranges_mod.get_swing_ranges_batch("ALL", warm_symbols, settings)

    for sym in warm_symbols:
        res = evaluate_stock_swing(
            sym,
            settings,
            prices_df=prices_map.get(sym),
            stored_range=ranges_map.get(sym),
        )
        if res is None:
            continue

        tier = swing_tier_manager.evaluate_tier(res)
        if tier == "HOT":
            swing_tier_manager.promote_or_update(res, settings=settings, force_tier="HOT")
        else:
            swing_tier_manager.check_warm_demotion(sym, res, settings=settings)

    swing_tier_manager._rebuild_candidates()
    _pool["last_warm_scan_at"] = datetime.now(timezone.utc).isoformat()
    _pool["last_scan_at"] = _pool["last_warm_scan_at"]
    _pool["last_scan_duration_s"] = round(time.time() - t0, 2)
    save_swing_pool_to_db(settings)


def run_cold_scan(
    settings: Settings,
    universe: str | None = None,
    min_score: int = SWING_MIN_SCORE,
) -> list[dict[str, Any]]:
    """Full universe discovery scan every SWING_COLD_INTERVAL_MIN (60 min)."""
    t0 = time.time()
    _pool["status"] = "running"
    _pool["error"] = None

    try:
        from earnings_engine.data.universe import load_universe, load_all
        from earnings_engine.data.earnings import upcoming_earnings
        from earnings_engine.data import swing_ranges as swing_ranges_mod

        if universe and universe.lower() not in ("all", "global", "monitored"):
            tickers = load_universe(universe.upper(), settings) or load_all(settings)
        else:
            tickers = load_all(settings)

        if not tickers:
            tickers = load_universe("NSE_TOP", settings) or []

        # Pre-fetch earnings calendar
        upcoming_map: dict[str, str] = {}
        try:
            up_df = upcoming_earnings(tickers, settings, days=90)
            if not up_df.empty:
                for _, ev in up_df.iterrows():
                    sym = str(ev["ticker"])
                    if sym not in upcoming_map:
                        upcoming_map[sym] = (
                            ev["earnings_date"].strftime("%Y-%m-%d")
                            if isinstance(ev["earnings_date"], pd.Timestamp)
                            else str(ev["earnings_date"])
                        )
        except Exception:
            pass

        # Batch load stored swing ranges
        try:
            stored_ranges = {r["ticker"]: r for r in swing_ranges_mod.list_ranges("ALL", settings)}
        except Exception:
            stored_ranges = {}

        # Batch load prices
        try:
            from earnings_engine.data.prices import load_prices_batch
            prices_map = load_prices_batch(tickers, settings, days=120)
        except Exception as e:
            logger.warning("[SWING-SCANNER] Failed batch loading prices: %s", e)
            prices_map = {}

        scanned_count = 0

        for ticker in tickers:
            scanned_count += 1
            res = evaluate_stock_swing(
                ticker=ticker,
                settings=settings,
                prices_df=prices_map.get(ticker),
                stored_range=stored_ranges.get(ticker),
                earnings_date=upcoming_map.get(ticker),
            )
            if res is None:
                continue

            swing_tier_manager.promote_or_update(res, settings=settings)

        _pool["cold_tickers_scanned"] = scanned_count
        swing_tier_manager._rebuild_candidates()

        now_iso = datetime.now(timezone.utc).isoformat()
        _pool["last_cold_scan_at"] = now_iso
        _pool["last_scan_at"] = now_iso
        _pool["last_scan_duration_s"] = round(time.time() - t0, 2)
        _pool["status"] = "done"

        save_swing_pool_to_db(settings)
        logger.info("[SWING-COLD] Full scan complete: %d tickers scanned -> %d HOT, %d WARM in %.2fs",
                    scanned_count, len(_pool["hot"]), len(_pool["warm"]), _pool["last_scan_duration_s"])
        return list(_pool["candidates"])
    except Exception as e:
        logger.exception("[SWING-COLD] Scan failed: %s", e)
        _pool["status"] = "error"
        _pool["error"] = str(e)
        return list(_pool["candidates"])


# ---------------------------------------------------------------------------
# Public APIs & Async Background Loop
# ---------------------------------------------------------------------------

def get_swing_pool_stats(settings: Settings | None = None) -> dict[str, Any]:
    """Return aggregate pool metrics from database or in-memory state."""
    return swing_tier_manager.get_pool_stats(settings=settings)


def get_swing_audit_log(
    ticker: str | None = None,
    limit: int = 50,
    offset: int = 0,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Fetch historical transition event log for swing trading setups."""
    return swing_tier_manager.get_audit_log(ticker=ticker, limit=limit, offset=offset, settings=settings)


def set_swing_manual_tier(
    ticker: str,
    tier: str,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Manually assign or override the tier of a stock in the swing radar."""
    t = swing_tier_manager.set_manual_tier(ticker, tier, settings=settings)
    save_swing_pool_to_db(settings)
    return {"success": True, "ticker": ticker, "tier": t}


def get_cached_swing_results(
    universe: str | None = None,
    tier: str | None = "ALL",
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """Return cached swing setups, optionally filtered by tier and universe / watchlist."""
    settings = settings or Settings()
    if not _pool.get("candidates") and not _pool.get("hot") and not _pool.get("warm"):
        load_swing_pool_from_db(settings)

    tier_filter = (tier or "ALL").upper().strip()
    if tier_filter == "HOT":
        candidates = [e.result for e in _pool["hot"].values()]
    elif tier_filter == "WARM":
        candidates = [e.result for e in _pool["warm"].values()]
    elif tier_filter == "COLD":
        candidates = [c for c in _pool.get("candidates", []) if (c.get("tier") or "").upper() == "COLD"]
        if not candidates:
            # Fallback to DB query for cold candidates if in-memory pool filtered them
            try:
                conn = get_db_connection(settings)
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM swing_radar WHERE tier = 'COLD' ORDER BY composite_score DESC LIMIT 100")
                rows = cursor.fetchall()
                cols = [col[0] for col in cursor.description]
                for r in rows:
                    d = dict(zip(cols, r))
                    candidates.append({
                        "ticker": d.get("ticker"),
                        "tier": "COLD",
                        "company_name": d.get("company_name"),
                        "industry": d.get("industry"),
                        "composite_score": d.get("composite_score", 0),
                        "current_price": d.get("current_price"),
                        "current_support": d.get("support_level"),
                        "next_resistance": d.get("resistance_level"),
                        "spread_pct": d.get("spread_pct"),
                        "dist_to_support_pct": d.get("dist_to_support_pct"),
                        "channel_position_pct": d.get("channel_position_pct"),
                        "swing_signal": d.get("signal", "Neutral"),
                        "source": d.get("source", "auto"),
                        "cycles": d.get("cycles", 0),
                        "avg_cycle_days": d.get("avg_cycle_days", 0),
                        "thirty_day_return_pct": d.get("thirty_day_return_pct"),
                    })
            except Exception:
                pass
    else:
        candidates = list(_pool["candidates"])

    if not universe or universe.lower() in ("all", "any", "global", "monitored"):
        return candidates

    try:
        from earnings_engine.data.universe import load_universe
        from earnings_engine.data.watchlists import get_watchlist

        u_clean = universe.lower().strip()
        uni_tickers: set[str] = set()
        if u_clean in ("nifty_50", "nifty50", "nse_top", "in", "nse"):
            uni_tickers = set(load_universe("NSE_TOP", settings) or load_universe("NIFTY_50", settings) or [])
        elif u_clean == "nse_large_cap":
            uni_tickers = set(load_universe("NSE_LARGE_CAP", settings) or [])
        elif u_clean in ("us_top", "us"):
            uni_tickers = set(load_universe("US_TOP", settings) or [])
        else:
            wl = get_watchlist(universe, settings)
            if wl:
                uni_tickers = set(wl)
            else:
                uni_tickers = set(load_universe(universe, settings) or [])

        if uni_tickers:
            uni_norm = {t.upper() for t in uni_tickers}
            return [c for c in candidates if c.get("ticker", "").upper() in uni_norm]
    except Exception as e:
        logger.debug("[SWING] Error filtering by universe %s: %s", universe, e)

    return candidates


def get_top_swingers(
    universe: str | None = None,
    min_cycles: int = 1,
    limit: int = 50,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """Return top-ranked swing setups in the market sorted by cycle regularity and profit potential.

    Scoring formula prioritizes:
    - Cycle Count (proven oscillation rhythm)
    - Cycle Velocity & Duration (healthy 10-45 day swing sweet spot)
    - Channel Spread (10-40% harmonic channel width)
    - Support Floor Proximity (closeness to 0-3% active buy zone)
    - Composite Score & Fundamental Quality
    """
    settings = settings or Settings()
    all_setups = get_cached_swing_results(universe=universe, tier="ALL", settings=settings)
    if not all_setups:
        load_swing_pool_from_db(settings)
        all_setups = get_cached_swing_results(universe=universe, tier="ALL", settings=settings)

    ranked: list[dict[str, Any]] = []

    for item in all_setups:
        ticker = item.get("ticker")
        if not ticker:
            continue

        cycles = int(item.get("cycles") or 0)
        avg_days = float(item.get("avg_cycle_days") or 0.0)
        spread_pct = float(item.get("spread_pct") or 0.0)
        dist_pct = float(item.get("dist_to_support_pct", 99.0) if item.get("dist_to_support_pct") is not None else 99.0)
        comp_score = float(item.get("composite_score") or 0.0)

        # Strict filter by minimum completed cycles
        if cycles < min_cycles:
            continue

        # Cycle Quality Points (0-40)
        cycle_pts = 0.0
        if cycles >= 4:
            cycle_pts += 25.0
        elif cycles >= 3:
            cycle_pts += 20.0
        elif cycles >= 2:
            cycle_pts += 15.0
        elif cycles == 1:
            cycle_pts += 8.0

        # Cycle Velocity Score (10-45 days is peak swing rhythm)
        if 10.0 <= avg_days <= 30.0:
            cycle_pts += 15.0
        elif 5.0 <= avg_days <= 60.0:
            cycle_pts += 10.0
        elif avg_days > 0:
            cycle_pts += 5.0

        # Spread Score (0-25)
        spread_pts = 0.0
        if 12.0 <= spread_pct <= 35.0:
            spread_pts = 25.0
        elif 8.0 <= spread_pct <= 50.0:
            spread_pts = 18.0
        elif spread_pct > 0:
            spread_pts = 10.0

        # Buy Zone Proximity Score (0-20)
        prox_pts = 0.0
        if 0.0 <= dist_pct <= 3.0:
            prox_pts = 20.0  # Immediate buy zone floor
        elif 3.0 < dist_pct <= 7.0:
            prox_pts = 14.0
        elif dist_pct <= 12.0:
            prox_pts = 8.0

        # Composite / Quality contribution (0-15)
        comp_pts = (comp_score / 100.0) * 15.0

        total_rank_score = round(cycle_pts + spread_pts + prox_pts + comp_pts, 1)

        # Build clean cycle health and timeframe metadata
        cycle_health = "High Frequency" if cycles >= 4 else ("Established" if cycles >= 2 else "Emerging")
        cycle_time_display = f"~{avg_days:.1f}d / cycle" if avg_days > 0 else "—"
        cycle_count_display = f"{cycles} Cycle{'s' if cycles != 1 else ''}"

        ranked.append({
            **item,
            "swing_rank_score": total_rank_score,
            "cycles": cycles,
            "avg_cycle_days": avg_days,
            "cycle_time_display": cycle_time_display,
            "cycle_count_display": cycle_count_display,
            "cycle_health": cycle_health,
            "timeframe_baseline": "90D Channel Rhythm",
        })

    # Sort descending by swing_rank_score, then composite_score, then cycles
    ranked.sort(
        key=lambda x: (
            x.get("swing_rank_score", 0),
            x.get("composite_score", 0),
            x.get("cycles", 0),
        ),
        reverse=True,
    )

    return ranked[:limit]


def get_scan_status(universe: str | None = None) -> dict[str, Any]:
    """Return status summary of the swing scanner."""
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
        "min_score": SWING_MIN_SCORE,
        "scan_intervals": {
            "cold_min": SWING_COLD_INTERVAL_MIN,
            "warm_min": SWING_WARM_INTERVAL_MIN,
            "hot_min": SWING_HOT_INTERVAL_MIN,
        },
        "error": _pool["error"],
    }


async def swing_scanner_loop(settings: Settings) -> None:
    """Non-blocking background loop orchestrating Cold, Warm, and Hot swing scans."""
    logger.info("[SWING-LOOP] Starting background swing scanner task")
    # Initial startup hydration / cold scan
    load_swing_pool_from_db(settings)
    if not _pool["candidates"]:
        await asyncio.to_thread(run_cold_scan, settings)

    last_cold = time.time()
    last_warm = time.time()
    last_hot = time.time()

    while True:
        try:
            await asyncio.sleep(60)  # Check interval every minute
            now = time.time()

            # 1. Hot rescore
            if (now - last_hot) >= (SWING_HOT_INTERVAL_MIN * 60):
                await asyncio.to_thread(run_hot_rescore, settings)
                last_hot = time.time()

            # 2. Warm rescore
            if (now - last_warm) >= (SWING_WARM_INTERVAL_MIN * 60):
                await asyncio.to_thread(run_warm_rescore, settings)
                last_warm = time.time()

            # 3. Cold scan
            if (now - last_cold) >= (SWING_COLD_INTERVAL_MIN * 60):
                await asyncio.to_thread(run_cold_scan, settings)
                last_cold = time.time()
        except asyncio.CancelledError:
            logger.info("[SWING-LOOP] Background swing scanner task cancelled")
            break
        except Exception as e:
            logger.warning("[SWING-LOOP] Error in swing scanner cycle: %s", e)
            await asyncio.sleep(10)
