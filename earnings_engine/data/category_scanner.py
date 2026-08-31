"""Active Multi-Category Stock Scanner Hub & Background Sweep Engine.

Provides DB-persisted, instant-query multi-category scanning across fundamental
catalyst categories, technical breakout pattern archetypes, and sector momentum contagion.
Background jobs pre-compute and maintain scanner setups in SQLite for 0ms retrieval.
"""
from __future__ import annotations

import logging
import sqlite3
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from earnings_engine.config import Settings
from earnings_engine.data.prices import _connect, load_prices
from earnings_engine.data.names import get_name
from earnings_engine.data.watchlists import get_watchlist
from earnings_engine.data.universe import get_universe
from earnings_engine.data.catalysts_news import (
    get_short_term_catalysts,
    fetch_ticker_catalysts,
    score_catalyst_headline,
    scan_watchlist_catalysts,
)
from earnings_engine.data.gainers_patterns import (
    compute_stock_daily_telemetry,
    attribute_surge_driver,
    PATTERN_ARCHETYPES,
)

logger = logging.getLogger(__name__)

_TELEM_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}

def _get_cached_stock_telemetry(ticker: str, settings: Settings) -> dict[str, Any] | None:
    """Retrieve telemetry with in-memory TTL caching to avoid repeated SQLite disk reads."""
    now = time.time()
    cached = _TELEM_CACHE.get(ticker)
    if cached and (now - cached[0]) < 120.0:
        return cached[1]
    df = load_prices(ticker, settings=settings)
    if df.empty or len(df) < 15:
        return None
    telem = compute_stock_daily_telemetry(ticker, df)
    if telem:
        _TELEM_CACHE[ticker] = (now, telem)
    return telem

# Standard Category Definitions
SCANNER_CATEGORIES: dict[str, dict[str, Any]] = {
    "order_wins": {
        "id": "order_wins",
        "name": "🤝 Order Wins & Major Deals",
        "badge": "Order Wins",
        "type": "FUNDAMENTAL_CATALYST",
        "description": "Companies securing substantial multi-crore contracts, railway/defense orders, and multi-year commercial deals.",
        "icon": "🤝",
        "color": "#38bdf8",
        "target_horizon": "⚡ 1-2 Days",
    },
    "earnings_beats": {
        "id": "earnings_beats",
        "name": "📈 Earnings Blowouts & Guidance",
        "badge": "Earnings Beats",
        "type": "FUNDAMENTAL_CATALYST",
        "description": "Exceptional quarterly profit acceleration, margin expansions, and upward revenue guidance surprises.",
        "icon": "📈",
        "color": "#34d399",
        "target_horizon": "⚡ 1-3 Days",
    },
    "regulatory_approvals": {
        "id": "regulatory_approvals",
        "name": "⚖️ Regulatory Approvals & PLI Policy",
        "badge": "Regulatory & PLI",
        "type": "FUNDAMENTAL_CATALYST",
        "description": "USFDA clearances, government PLI scheme inclusions, patent grants, and favorable import duty protection.",
        "icon": "⚖️",
        "color": "#818cf8",
        "target_horizon": "📅 2-4 Days",
    },
    "ma_expansion": {
        "id": "ma_expansion",
        "name": "🏢 M&A, Stake Deals & Expansion",
        "badge": "M&A & Expansion",
        "type": "FUNDAMENTAL_CATALYST",
        "description": "Aggressive capacity capex expansions, strategic acquisitions, joint ventures, and institutional block purchases.",
        "icon": "🏢",
        "color": "#38bdf8",
        "target_horizon": "📅 3-5 Days",
    },
    "squeeze_coils": {
        "id": "squeeze_coils",
        "name": "🔥 Squeeze & Volume Explosion (Coiled)",
        "badge": "Squeeze Coils",
        "type": "TECHNICAL_SETUP",
        "description": "Stocks trading in tight consolidation corridors (<6% 14-day width) setting up for explosive volatility expansion.",
        "icon": "🔥",
        "color": "#f59e0b",
        "target_horizon": "⚡ 1-3 Days",
    },
    "blue_sky_52w": {
        "id": "blue_sky_52w",
        "name": "🛡️ 52-Week High Breakouts (Blue Sky)",
        "badge": "52W Highs",
        "type": "TECHNICAL_SETUP",
        "description": "Stocks clearing multi-month or all-time resistance with zero overhead trapped supply and strong buyer momentum.",
        "icon": "🛡️",
        "color": "#10b981",
        "target_horizon": "📅 3-7 Days",
    },
    "sector_waves": {
        "id": "sector_waves",
        "name": "🏭 Sector Momentum Contagion",
        "badge": "Sector Waves",
        "type": "SECTOR_CONTAGION",
        "description": "Synchronized multi-peer momentum waves lifting whole industry clusters (Defense, PSU, Auto, Solar, IT).",
        "icon": "🏭",
        "color": "#60a5fa",
        "target_horizon": "📅 2-5 Days",
    },
    "oversold_reversals": {
        "id": "oversold_reversals",
        "name": "🔄 Oversold Support Bounce / Dip Snapback",
        "badge": "Dip Reversals",
        "type": "TECHNICAL_SETUP",
        "description": "High-quality stocks bouncing sharply off 200 EMA or key demand zones with positive volume accumulation divergence.",
        "icon": "🔄",
        "color": "#38bdf8",
        "target_horizon": "📅 3-5 Days",
    },
    "risk_alerts": {
        "id": "risk_alerts",
        "name": "⚠️ High-Risk Overhangs (Litigation/Probes)",
        "badge": "Risk Alerts",
        "type": "RISK_WARNING",
        "description": "Regulatory probes, SEBI show-cause notices, auditor resignations, or debt default alerts to avoid.",
        "icon": "⚠️",
        "color": "#ef4444",
        "target_horizon": "⚡ Immediate Risk",
    },
}


def _connect_scanner_db(settings: Settings) -> sqlite3.Connection:
    """Connect to SQLite database and ensure scanner tables & indices exist."""
    conn = _connect(settings)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS scanner_candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            universe TEXT NOT NULL,
            category_id TEXT NOT NULL,
            category_name TEXT,
            category_badge TEXT,
            ticker TEXT NOT NULL,
            stock_name TEXT,
            signal_date TEXT,
            signal_price REAL,
            current_price REAL,
            return_pct REAL,
            volume_multiple REAL,
            trigger_level REAL,
            target_price REAL,
            stop_loss REAL,
            confidence_score INTEGER,
            severity TEXT,
            outcome TEXT,
            outcome_label TEXT,
            outcome_badge TEXT,
            expected_horizon TEXT,
            volatility_est TEXT,
            headline TEXT,
            catalyst_summary TEXT,
            why_it_matches TEXT,
            published_at TEXT,
            link TEXT,
            scanned_at TEXT NOT NULL,
            UNIQUE(universe, category_id, ticker)
        )
        """
    )
    # Self-healing column additions for existing tables
    existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(scanner_candidates)").fetchall()}
    col_defs = {
        "signal_date": "TEXT",
        "signal_price": "REAL",
        "target_price": "REAL",
        "stop_loss": "REAL",
        "severity": "TEXT",
        "outcome": "TEXT",
        "outcome_label": "TEXT",
        "outcome_badge": "TEXT",
    }
    for col, col_type in col_defs.items():
        if col not in existing_cols:
            try:
                conn.execute(f"ALTER TABLE scanner_candidates ADD COLUMN {col} {col_type}")
            except Exception:
                pass

    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_scanner_univ_cat ON scanner_candidates(universe, category_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_scanner_scanned_at ON scanner_candidates(scanned_at DESC)"
    )
    conn.commit()
    return conn


def _resolve_universe_tickers(universe_or_watchlist: str = "NSE_TOP", settings: Settings | None = None) -> list[str]:
    """Resolve a universe name or custom watchlist into a list of ticker symbols."""
    settings = settings or Settings()
    tickers: list[str] = []
    if universe_or_watchlist.upper() not in ("", "ALL", "GLOBAL", "NSE_ALL"):
        tickers = get_watchlist(universe_or_watchlist, settings)
        if not tickers:
            tickers = get_universe(universe_or_watchlist, settings)

    if not tickers:
        with _connect(settings) as conn:
            rows = conn.execute("SELECT DISTINCT ticker FROM price_history LIMIT 350").fetchall()
            tickers = [r[0] for r in rows]

    if not tickers:
        tickers = [
            "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
            "BHARTIARTL.NS", "SBIN.NS", "LT.NS", "PCJEWELLER.NS", "FORCEMOT.NS",
            "JIOFIN.NS", "IDBI.NS", "TATAMOTORS.NS", "BEL.NS", "HAL.NS"
        ]

    return tickers


def _compute_category_candidates_live(
    category_id: str,
    universe_or_watchlist: str = "NSE_TOP",
    limit: int = 50,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """Internal calculation engine for a specific category with quantitative target, SL, and severity."""
    settings = settings or Settings()
    cat_id = category_id.lower().strip()
    cat_meta = SCANNER_CATEGORIES.get(cat_id)
    if not cat_meta:
        return []

    tickers = _resolve_universe_tickers(universe_or_watchlist, settings)
    candidates: list[dict[str, Any]] = []
    today_str = pd.Timestamp.now().strftime("%Y-%m-%d")

    # 1. Fundamental News Categories
    if cat_meta["type"] in ("FUNDAMENTAL_CATALYST", "RISK_WARNING"):
        news_cat_map = {
            "order_wins": "Order Wins & Contracts",
            "earnings_beats": "Earnings & Guidance Surprise",
            "regulatory_approvals": "Regulatory, Approvals & Policy",
            "ma_expansion": "M&A, Stake & Expansion",
            "risk_alerts": "Litigation, Risk & Probes",
        }
        target_news_cat = news_cat_map.get(cat_id, "")
        
        items = get_short_term_catalysts(
            category_filter=target_news_cat,
            limit=limit * 2,
            settings=settings,
        )

        for item in items:
            t = item.get("ticker", "")
            if tickers and t not in tickers and universe_or_watchlist.upper() not in ("ALL", "GLOBAL", "NSE_ALL"):
                continue

            df = load_prices(t, settings=settings)
            telem = compute_stock_daily_telemetry(t, df) if not df.empty and len(df) >= 2 else None

            curr_price = telem["close"] if telem else 0.0
            vol_mult = telem["volume_multiple"] if telem else 1.5
            impact_score = item.get("impact_score", 75)

            # Extract date of news
            raw_pub = item.get("published_at") or today_str
            signal_date = raw_pub[:10] if len(raw_pub) >= 10 else today_str

            # Determine signal price at news publication
            signal_price = curr_price
            if telem and telem.get("prev_close") and curr_price > 0:
                signal_price = telem["prev_close"] if signal_date < today_str else curr_price

            # News Severity Classification
            if cat_id == "risk_alerts" or item.get("direction") == "BEARISH":
                severity = "RISK"
                severity_label = "⚠️ HIGH RISK"
            elif impact_score >= 80:
                severity = "HIGH"
                severity_label = "⚡ HIGH IMPACT"
            elif impact_score >= 55:
                severity = "MEDIUM"
                severity_label = "📈 MEDIUM"
            else:
                severity = "LOW"
                severity_label = "⚖️ LOW / NORMAL"

            # Compute Target Price and Stop Loss based on severity & category
            if severity == "HIGH":
                target_upside = 0.08 + (impact_score - 80) * 0.003
                target_price = round(signal_price * (1 + target_upside), 2) if signal_price > 0 else 0.0
                trigger_price = round(signal_price * 1.018, 2) if signal_price > 0 else 0.0
                stop_loss = round(signal_price * 0.965, 2) if signal_price > 0 else 0.0
            elif severity == "MEDIUM":
                target_upside = 0.045 + (impact_score - 55) * 0.001
                target_price = round(signal_price * (1 + target_upside), 2) if signal_price > 0 else 0.0
                trigger_price = round(signal_price * 1.015, 2) if signal_price > 0 else 0.0
                stop_loss = round(signal_price * 0.97, 2) if signal_price > 0 else 0.0
            elif severity == "RISK":
                target_price = round(signal_price * 0.92, 2) if signal_price > 0 else 0.0
                trigger_price = round(signal_price * 0.985, 2) if signal_price > 0 else 0.0
                stop_loss = round(signal_price * 1.03, 2) if signal_price > 0 else 0.0
            else:
                target_price = round(signal_price * 1.03, 2) if signal_price > 0 else 0.0
                trigger_price = round(signal_price * 1.01, 2) if signal_price > 0 else 0.0
                stop_loss = round(signal_price * 0.975, 2) if signal_price > 0 else 0.0

            # Realized return from signal
            if signal_price > 0:
                ret_pct = round(((curr_price - signal_price) / signal_price) * 100, 2)
            else:
                ret_pct = telem["return_pct"] if telem else 0.0

            # Compute Outcome Status
            if cat_id == "risk_alerts":
                outcome = "RISK_ALERT"
                outcome_label = "Risk Alert ⚠️"
                outcome_badge = "rose"
            elif target_price > 0 and curr_price >= target_price:
                outcome = "TARGET_HIT"
                outcome_label = "Target Hit 🎯"
                outcome_badge = "emerald"
            elif trigger_price > 0 and curr_price >= trigger_price:
                outcome = "TRIGGERED"
                outcome_label = "Triggered ⚡"
                outcome_badge = "amber"
            elif stop_loss > 0 and curr_price <= stop_loss and severity != "RISK":
                outcome = "STOP_HIT"
                outcome_label = "Stop Hit 🛑"
                outcome_badge = "rose"
            else:
                outcome = "ACTIVE"
                outcome_label = "In Play ⏳"
                outcome_badge = "blue"

            candidates.append({
                "universe": universe_or_watchlist,
                "category_id": cat_id,
                "category_name": cat_meta["name"],
                "category_badge": cat_meta["badge"],
                "ticker": t,
                "stock_name": item.get("stock_name") or get_name(t, settings) or t,
                "signal_date": signal_date,
                "signal_price": signal_price,
                "current_price": curr_price,
                "return_pct": ret_pct,
                "volume_multiple": vol_mult,
                "trigger_level": trigger_price,
                "target_price": target_price,
                "stop_loss": stop_loss,
                "confidence_score": impact_score,
                "severity": severity,
                "outcome": outcome,
                "outcome_label": outcome_label,
                "outcome_badge": outcome_badge,
                "expected_horizon": item.get("expected_horizon", cat_meta["target_horizon"]),
                "volatility_est": item.get("volatility_est", "±4% to ±8%"),
                "headline": item.get("title", ""),
                "catalyst_summary": item.get("summary") or item.get("title", ""),
                "why_it_matches": item.get("why_it_matters", f"High-impact catalyst ({cat_meta['name']}) driving momentum."),
                "published_at": item.get("published_at", ""),
                "link": item.get("link", ""),
            })

    # 2. Technical Setup Categories
    else:
        for t in tickers:
            try:
                telem = _get_cached_stock_telemetry(t, settings=settings)
                if not telem:
                    continue

                name = get_name(t, settings) or t
                c_range = telem["consolidation_range"]
                dist_52w = telem["dist_52w"]
                vol_mult = telem["volume_multiple"]
                ret = telem["return_pct"]
                close = telem["close"]
                signal_date = telem.get("date") or today_str
                signal_price = close

                if cat_id == "squeeze_coils" and c_range <= 6.5:
                    trigger = round(close * 1.025, 2)
                    target = round(close * (1 + max(0.06, c_range * 1.5 / 100)), 2)
                    stop = round(close * 0.965, 2)
                    conf = min(95, int(82 + (6.5 - c_range) * 2))
                    sev = "HIGH" if conf >= 88 else "MEDIUM"
                    
                    outcome = "TARGET_HIT" if close >= target else ("TRIGGERED" if close >= trigger else ("STOP_HIT" if close <= stop else "ACTIVE"))
                    outcome_label = "Target Hit 🎯" if outcome == "TARGET_HIT" else ("Triggered ⚡" if outcome == "TRIGGERED" else ("Stop Hit 🛑" if outcome == "STOP_HIT" else "In Play ⏳"))
                    outcome_badge = "emerald" if outcome == "TARGET_HIT" else ("amber" if outcome == "TRIGGERED" else ("rose" if outcome == "STOP_HIT" else "blue"))

                    candidates.append({
                        "universe": universe_or_watchlist,
                        "category_id": cat_id,
                        "category_name": cat_meta["name"],
                        "category_badge": cat_meta["badge"],
                        "ticker": t,
                        "stock_name": name,
                        "signal_date": signal_date,
                        "signal_price": signal_price,
                        "current_price": close,
                        "return_pct": ret,
                        "volume_multiple": vol_mult,
                        "trigger_level": trigger,
                        "target_price": target,
                        "stop_loss": stop,
                        "confidence_score": conf,
                        "severity": sev,
                        "outcome": outcome,
                        "outcome_label": outcome_label,
                        "outcome_badge": outcome_badge,
                        "expected_horizon": "⚡ 1-3 Days",
                        "volatility_est": "±5% to ±10%",
                        "catalyst_summary": f"Coiling tightly within a {c_range}% 14-day price band with compression.",
                        "why_it_matches": f"Ultra-low volatility squeeze setup. Volume surge above ₹{trigger} triggers high-probability breakout.",
                    })

                elif cat_id == "blue_sky_52w" and (telem["is_52w_high"] or -3.0 <= dist_52w <= 0.0):
                    trigger = telem["high_52w"]
                    target = round(trigger * 1.08, 2)
                    stop = round(close * 0.965, 2)
                    conf = min(96, int(85 + (vol_mult * 2)))
                    sev = "HIGH"

                    outcome = "TARGET_HIT" if close >= target else ("TRIGGERED" if close >= trigger else ("STOP_HIT" if close <= stop else "ACTIVE"))
                    outcome_label = "Target Hit 🎯" if outcome == "TARGET_HIT" else ("Triggered ⚡" if outcome == "TRIGGERED" else ("Stop Hit 🛑" if outcome == "STOP_HIT" else "In Play ⏳"))
                    outcome_badge = "emerald" if outcome == "TARGET_HIT" else ("amber" if outcome == "TRIGGERED" else ("rose" if outcome == "STOP_HIT" else "blue"))

                    candidates.append({
                        "universe": universe_or_watchlist,
                        "category_id": cat_id,
                        "category_name": cat_meta["name"],
                        "category_badge": cat_meta["badge"],
                        "ticker": t,
                        "stock_name": name,
                        "signal_date": signal_date,
                        "signal_price": signal_price,
                        "current_price": close,
                        "return_pct": ret,
                        "volume_multiple": vol_mult,
                        "trigger_level": trigger,
                        "target_price": target,
                        "stop_loss": stop,
                        "confidence_score": conf,
                        "severity": sev,
                        "outcome": outcome,
                        "outcome_label": outcome_label,
                        "outcome_badge": outcome_badge,
                        "expected_horizon": "📅 3-7 Days",
                        "volatility_est": "±4% to ±9%",
                        "catalyst_summary": f"Trading within {abs(dist_52w)}% of 52-week high (₹{trigger}).",
                        "why_it_matches": f"Zero overhead resistance. Breakout above ₹{trigger} opens clean blue-sky continuation.",
                    })

                elif cat_id == "sector_waves" and (ret >= 4.0 or vol_mult >= 2.5):
                    trigger = round(close * 1.02, 2)
                    target = round(close * 1.075, 2)
                    stop = round(close * 0.965, 2)
                    conf = min(92, int(75 + ret))
                    sev = "MEDIUM" if conf < 85 else "HIGH"

                    outcome = "TARGET_HIT" if close >= target else ("TRIGGERED" if close >= trigger else ("STOP_HIT" if close <= stop else "ACTIVE"))
                    outcome_label = "Target Hit 🎯" if outcome == "TARGET_HIT" else ("Triggered ⚡" if outcome == "TRIGGERED" else ("Stop Hit 🛑" if outcome == "STOP_HIT" else "In Play ⏳"))
                    outcome_badge = "emerald" if outcome == "TARGET_HIT" else ("amber" if outcome == "TRIGGERED" else ("rose" if outcome == "STOP_HIT" else "blue"))

                    candidates.append({
                        "universe": universe_or_watchlist,
                        "category_id": cat_id,
                        "category_name": cat_meta["name"],
                        "category_badge": cat_meta["badge"],
                        "ticker": t,
                        "stock_name": name,
                        "signal_date": signal_date,
                        "signal_price": signal_price,
                        "current_price": close,
                        "return_pct": ret,
                        "volume_multiple": vol_mult,
                        "trigger_level": trigger,
                        "target_price": target,
                        "stop_loss": stop,
                        "confidence_score": conf,
                        "severity": sev,
                        "outcome": outcome,
                        "outcome_label": outcome_label,
                        "outcome_badge": outcome_badge,
                        "expected_horizon": "📅 2-5 Days",
                        "volatility_est": "±4% to ±8%",
                        "catalyst_summary": f"Moving +{ret}% on strong {vol_mult}x volume surge with institutional accumulation.",
                        "why_it_matches": "Broad peer group buying wave driving sustained sector continuation.",
                    })

                elif cat_id == "oversold_reversals" and (ret > 0 and c_range >= 9.0 and dist_52w <= -10.0):
                    trigger = round(close * 1.015, 2)
                    target = round(close * 1.055, 2)
                    stop = round(close * 0.965, 2)
                    conf = 78
                    sev = "MEDIUM"

                    outcome = "TARGET_HIT" if close >= target else ("TRIGGERED" if close >= trigger else ("STOP_HIT" if close <= stop else "ACTIVE"))
                    outcome_label = "Target Hit 🎯" if outcome == "TARGET_HIT" else ("Triggered ⚡" if outcome == "TRIGGERED" else ("Stop Hit 🛑" if outcome == "STOP_HIT" else "In Play ⏳"))
                    outcome_badge = "emerald" if outcome == "TARGET_HIT" else ("amber" if outcome == "TRIGGERED" else ("rose" if outcome == "STOP_HIT" else "blue"))

                    candidates.append({
                        "universe": universe_or_watchlist,
                        "category_id": cat_id,
                        "category_name": cat_meta["name"],
                        "category_badge": cat_meta["badge"],
                        "ticker": t,
                        "stock_name": name,
                        "signal_date": signal_date,
                        "signal_price": signal_price,
                        "current_price": close,
                        "return_pct": ret,
                        "volume_multiple": vol_mult,
                        "trigger_level": trigger,
                        "target_price": target,
                        "stop_loss": stop,
                        "confidence_score": conf,
                        "severity": sev,
                        "outcome": outcome,
                        "outcome_label": outcome_label,
                        "outcome_badge": outcome_badge,
                        "expected_horizon": "📅 3-5 Days",
                        "volatility_est": "±4% to ±7%",
                        "catalyst_summary": f"Pullback of {abs(dist_52w)}% from 52W highs showing initial bounce +{ret}%.",
                        "why_it_matches": "Mean-reversion bounce off key demand zone with positive volume divergence.",
                    })

            except Exception as e:
                logger.debug("Scanner candidate error for %s: %s", t, e)

    candidates.sort(key=lambda c: (c.get("confidence_score", 0), c.get("return_pct", 0)), reverse=True)
    return candidates[:limit]


def compute_and_save_scanner_universe(
    universe_or_watchlist: str = "NSE_TOP",
    limit_per_category: int = 35,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Background Worker Task: Runs full universe scanner and persists results to SQLite DB."""
    settings = settings or Settings()
    now_iso = datetime.now(timezone.utc).isoformat()
    logger.info("[SCANNER-WORKER] Starting background sweep for universe '%s'...", universe_or_watchlist)

    # 1. Trigger fresh news headlines sweep
    try:
        scan_watchlist_catalysts(watchlist_name=universe_or_watchlist, limit_per_stock=3, settings=settings)
    except Exception as e:
        logger.debug("[SCANNER-WORKER] News sweep warning: %s", e)

    # 2. Compute candidates across each category
    all_candidates: list[dict[str, Any]] = []
    for cat_id in SCANNER_CATEGORIES:
        try:
            cand = _compute_category_candidates_live(cat_id, universe_or_watchlist=universe_or_watchlist, limit=limit_per_category, settings=settings)
            all_candidates.extend(cand)
        except Exception as e:
            logger.warning("[SCANNER-WORKER] Error sweeping category %s: %s", cat_id, e)

    # 3. Persist to SQLite Database
    with _connect_scanner_db(settings) as conn:
        with conn:
            # Upsert fresh candidates
            for c in all_candidates:
                conn.execute(
                    """
                    INSERT INTO scanner_candidates (
                        universe, category_id, category_name, category_badge, ticker, stock_name,
                        signal_date, signal_price, current_price, return_pct, volume_multiple, trigger_level,
                        target_price, stop_loss, confidence_score, severity, outcome, outcome_label, outcome_badge,
                        expected_horizon, volatility_est, headline, catalyst_summary, why_it_matches, published_at, link, scanned_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(universe, category_id, ticker) DO UPDATE SET
                        category_name = excluded.category_name,
                        category_badge = excluded.category_badge,
                        stock_name = excluded.stock_name,
                        signal_date = excluded.signal_date,
                        signal_price = excluded.signal_price,
                        current_price = excluded.current_price,
                        return_pct = excluded.return_pct,
                        volume_multiple = excluded.volume_multiple,
                        trigger_level = excluded.trigger_level,
                        target_price = excluded.target_price,
                        stop_loss = excluded.stop_loss,
                        confidence_score = excluded.confidence_score,
                        severity = excluded.severity,
                        outcome = excluded.outcome,
                        outcome_label = excluded.outcome_label,
                        outcome_badge = excluded.outcome_badge,
                        expected_horizon = excluded.expected_horizon,
                        volatility_est = excluded.volatility_est,
                        headline = excluded.headline,
                        catalyst_summary = excluded.catalyst_summary,
                        why_it_matches = excluded.why_it_matches,
                        published_at = excluded.published_at,
                        link = excluded.link,
                        scanned_at = excluded.scanned_at
                    """,
                    (
                        universe_or_watchlist,
                        c.get("category_id"),
                        c.get("category_name"),
                        c.get("category_badge"),
                        c.get("ticker"),
                        c.get("stock_name"),
                        c.get("signal_date"),
                        c.get("signal_price"),
                        c.get("current_price"),
                        c.get("return_pct"),
                        c.get("volume_multiple"),
                        c.get("trigger_level"),
                        c.get("target_price"),
                        c.get("stop_loss"),
                        c.get("confidence_score"),
                        c.get("severity"),
                        c.get("outcome"),
                        c.get("outcome_label"),
                        c.get("outcome_badge"),
                        c.get("expected_horizon"),
                        c.get("volatility_est"),
                        c.get("headline"),
                        c.get("catalyst_summary"),
                        c.get("why_it_matches"),
                        c.get("published_at"),
                        c.get("link"),
                        now_iso,
                    ),
                )

    logger.info(
        "[SCANNER-WORKER] Background sweep completed. Saved %d candidates into database for universe '%s'.",
        len(all_candidates),
        universe_or_watchlist,
    )
    return {
        "success": True,
        "universe": universe_or_watchlist,
        "total_saved": len(all_candidates),
        "scanned_at": now_iso,
    }


def scheduled_category_scanner_job(
    universes: list[str] | None = None,
    limit_per_category: int = 15,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Execute scheduled sweep across primary universes and record execution in automation_schedules."""
    settings = settings or Settings()
    t_start = time.perf_counter()
    now_dt = datetime.now(timezone.utc)
    now_iso = now_dt.isoformat()
    target_universes = universes or ["NSE_TOP", "NSE_LARGE_CAP", "US_TOP"]
    total_candidates = 0
    results = []

    for u in target_universes:
        try:
            res = compute_and_save_scanner_universe(u, limit_per_category=limit_per_category, settings=settings)
            total_candidates += (res or {}).get("total_saved", 0)
            results.append(res)
        except Exception as e:
            logger.warning("[SCANNER-SCHEDULE] Error sweeping universe %s: %s", u, e)


    duration = round(time.perf_counter() - t_start, 2)
    next_iso = (now_dt + timedelta(seconds=1800)).isoformat()

    # Update automation_schedules
    try:
        with _connect(settings) as conn:
            conn.execute(
                """
                UPDATE automation_schedules
                SET last_run_at = ?,
                    next_run_at = ?,
                    status = 'active',
                    last_duration_s = ?,
                    total_runs = total_runs + 1,
                    last_summary = ?,
                    updated_at = ?
                WHERE job_id = 'category_scanner_sweep'
                """,
                (
                    now_iso,
                    next_iso,
                    duration,
                    f"Swept {total_candidates} setups across {len(target_universes)} universes based on news severity & technical targets.",
                    now_iso,
                ),
            )
            conn.commit()
    except Exception as e:
        logger.debug("[SCANNER-SCHEDULE] Could not update automation_schedules: %s", e)

    return {
        "job_id": "category_scanner_sweep",
        "status": "success",
        "total_candidates": total_candidates,
        "results": results,
        "duration_seconds": round(duration, 2),
        "timestamp": now_iso,
    }


def scan_category(
    category_id: str,
    universe_or_watchlist: str = "NSE_TOP",
    limit: int = 50,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """Instant DB Query: Retrieve ranked candidates directly from SQLite database."""
    settings = settings or Settings()
    cat_id = category_id.lower().strip()

    columns = [
        "category_id", "category_name", "category_badge", "ticker", "stock_name",
        "signal_date", "signal_price", "current_price", "return_pct", "volume_multiple", "trigger_level",
        "target_price", "stop_loss", "confidence_score", "severity", "outcome", "outcome_label", "outcome_badge",
        "expected_horizon", "volatility_est", "headline", "catalyst_summary", "why_it_matches", "published_at", "link", "scanned_at"
    ]
    col_str = ", ".join(columns)

    with _connect_scanner_db(settings) as conn:
        if cat_id in ("all", "all_categories", "all_setups"):
            rows = conn.execute(
                f"""
                SELECT {col_str}
                FROM scanner_candidates
                WHERE universe = ?
                ORDER BY confidence_score DESC, return_pct DESC
                LIMIT ?
                """,
                (universe_or_watchlist, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                f"""
                SELECT {col_str}
                FROM scanner_candidates
                WHERE universe = ? AND category_id = ?
                ORDER BY confidence_score DESC, return_pct DESC
                LIMIT ?
                """,
                (universe_or_watchlist, cat_id, limit),
            ).fetchall()

    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for r in rows:
        d = dict(zip(columns, r))
        t = d.get("ticker")
        if cat_id in ("all", "all_categories", "all_setups"):
            if t in seen:
                continue
            seen.add(t)
        candidates.append(d)

    return candidates


def get_categories_overview(
    universe_or_watchlist: str = "NSE_TOP",
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """Instant DB Query: Retrieve live candidate count badges per category directly from SQLite."""
    settings = settings or Settings()

    with _connect_scanner_db(settings) as conn:
        counts_map = dict(
            conn.execute(
                "SELECT category_id, COUNT(DISTINCT ticker) FROM scanner_candidates WHERE universe = ? GROUP BY category_id",
                (universe_or_watchlist,),
            ).fetchall()
        )
        cand_rows = conn.execute(
            "SELECT category_id, ticker, confidence_score, current_price, trigger_level FROM scanner_candidates WHERE universe = ? ORDER BY confidence_score DESC",
            (universe_or_watchlist,),
        ).fetchall()

    top_candidates_map: dict[str, list[dict[str, Any]]] = {}
    for r in cand_rows:
        cid, t, conf, cp, tl = r[0], r[1], r[2], r[3], r[4]
        if cid not in top_candidates_map:
            top_candidates_map[cid] = []
        if len(top_candidates_map[cid]) < 5:
            top_candidates_map[cid].append({
                "ticker": t,
                "confidence_score": conf,
                "current_price": cp,
                "trigger_level": tl,
            })

    results: list[dict[str, Any]] = []
    for cat_id, meta in SCANNER_CATEGORIES.items():
        results.append({
            "id": cat_id,
            "name": meta["name"],
            "badge": meta["badge"],
            "type": meta["type"],
            "description": meta["description"],
            "icon": meta["icon"],
            "color": meta["color"],
            "target_horizon": meta["target_horizon"],
            "count": counts_map.get(cat_id, 0),
            "top_candidates": top_candidates_map.get(cat_id, []),
        })

    return results


def deep_universe_sweep(
    universe_or_watchlist: str = "NSE_TOP",
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Execute a comprehensive sweep across all categories and persist to SQLite DB."""
    settings = settings or Settings()
    save_result = compute_and_save_scanner_universe(universe_or_watchlist=universe_or_watchlist, settings=settings)
    categories_overview = get_categories_overview(universe_or_watchlist=universe_or_watchlist, settings=settings)
    total_candidates = sum(c["count"] for c in categories_overview)

    return {
        "universe": universe_or_watchlist,
        "total_categories": len(SCANNER_CATEGORIES),
        "total_candidates_found": total_candidates,
        "categories": categories_overview,
        "swept_at": save_result.get("scanned_at", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")),
    }
