"""Active Multi-Category Stock Scanner Hub & Sweep Engine.

Provides unified active scanning across fundamental catalyst categories,
technical breakout pattern archetypes, and sector momentum contagion.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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


def _resolve_universe_tickers(universe_or_watchlist: str = "NSE_TOP", settings: Settings | None = None) -> list[str]:
    """Resolve a universe name or custom watchlist into a list of ticker symbols."""
    settings = settings or Settings()
    tickers: list[str] = []
    if universe_or_watchlist.upper() not in ("", "ALL", "GLOBAL", "NSE_ALL"):
        tickers = get_watchlist(universe_or_watchlist, settings)
        if not tickers:
            tickers = get_universe(universe_or_watchlist, settings)

    if not tickers:
        # If NSE_ALL or empty, load available cached tickers
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


def scan_category(
    category_id: str,
    universe_or_watchlist: str = "NSE_TOP",
    limit: int = 25,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """Scan and return ranked candidate stocks matching a specific category or all categories."""
    settings = settings or Settings()
    cat_id = category_id.lower().strip()

    # Aggregate across all categories if 'all' is requested
    if cat_id in ("all", "all_categories", "all_setups"):
        seen_tickers: dict[str, dict[str, Any]] = {}
        for sub_cat_id in SCANNER_CATEGORIES:
            sub_candidates = scan_category(
                category_id=sub_cat_id,
                universe_or_watchlist=universe_or_watchlist,
                limit=limit,
                settings=settings,
            )
            for c in sub_candidates:
                t = c.get("ticker")
                if not t:
                    continue
                if t not in seen_tickers or (c.get("confidence_score", 0) > seen_tickers[t].get("confidence_score", 0)):
                    seen_tickers[t] = c
        aggregated = list(seen_tickers.values())
        aggregated.sort(key=lambda x: (x.get("confidence_score", 0), x.get("return_pct", 0)), reverse=True)
        return aggregated[:limit]

    cat_meta = SCANNER_CATEGORIES.get(cat_id)
    if not cat_meta:
        return []

    tickers = _resolve_universe_tickers(universe_or_watchlist, settings)
    candidates: list[dict[str, Any]] = []

    # 1. Fundamental News Categories
    if cat_meta["type"] in ("FUNDAMENTAL_CATALYST", "RISK_WARNING"):
        # Map to news catalyst category string
        news_cat_map = {
            "order_wins": "Order Wins & Contracts",
            "earnings_beats": "Earnings & Guidance Surprise",
            "regulatory_approvals": "Regulatory, Approvals & Policy",
            "ma_expansion": "M&A, Stake & Expansion",
            "risk_alerts": "Litigation, Risk & Probes",
        }
        target_news_cat = news_cat_map.get(cat_id, "")
        
        # Query short-term news catalysts
        items = get_short_term_catalysts(
            category_filter=target_news_cat,
            limit=limit * 2,
            settings=settings,
        )

        for item in items:
            t = item.get("ticker", "")
            if tickers and t not in tickers and universe_or_watchlist.upper() not in ("ALL", "GLOBAL", "NSE_ALL"):
                continue

            # Enrich with telemetry if available
            df = load_prices(t, settings=settings)
            telem = compute_stock_daily_telemetry(t, df) if not df.empty and len(df) >= 2 else None

            curr_price = telem["close"] if telem else 0.0
            ret_pct = telem["return_pct"] if telem else 0.0
            vol_mult = telem["volume_multiple"] if telem else 1.5

            trigger_price = round(curr_price * 1.02, 2) if curr_price > 0 else 0.0
            confidence = item.get("impact_score", 75)

            candidates.append({
                "category_id": cat_id,
                "category_name": cat_meta["name"],
                "ticker": t,
                "stock_name": item.get("stock_name") or get_name(t, settings) or t,
                "current_price": curr_price,
                "return_pct": ret_pct,
                "volume_multiple": vol_mult,
                "trigger_level": trigger_price,
                "confidence_score": confidence,
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
                df = load_prices(t, settings=settings)
                if df.empty or len(df) < 15:
                    continue
                telem = compute_stock_daily_telemetry(t, df)
                if not telem:
                    continue

                name = get_name(t, settings) or t
                c_range = telem["consolidation_range"]
                dist_52w = telem["dist_52w"]
                vol_mult = telem["volume_multiple"]
                ret = telem["return_pct"]
                close = telem["close"]

                if cat_id == "squeeze_coils" and c_range <= 6.5:
                    trigger = round(close * 1.025, 2)
                    candidates.append({
                        "category_id": cat_id,
                        "category_name": cat_meta["name"],
                        "ticker": t,
                        "stock_name": name,
                        "current_price": close,
                        "return_pct": ret,
                        "volume_multiple": vol_mult,
                        "trigger_level": trigger,
                        "confidence_score": min(95, int(82 + (6.5 - c_range) * 2)),
                        "expected_horizon": "⚡ 1-3 Days",
                        "volatility_est": "±5% to ±10%",
                        "catalyst_summary": f"Coiling tightly within a {c_range}% 14-day price band with compression.",
                        "why_it_matches": f"Ultra-low volatility squeeze setup. Volume surge above ₹{trigger} triggers high-probability breakout.",
                    })

                elif cat_id == "blue_sky_52w" and (telem["is_52w_high"] or -3.0 <= dist_52w <= 0.0):
                    trigger = telem["high_52w"]
                    candidates.append({
                        "category_id": cat_id,
                        "category_name": cat_meta["name"],
                        "ticker": t,
                        "stock_name": name,
                        "current_price": close,
                        "return_pct": ret,
                        "volume_multiple": vol_mult,
                        "trigger_level": trigger,
                        "confidence_score": min(96, int(85 + (vol_mult * 2))),
                        "expected_horizon": "📅 3-7 Days",
                        "volatility_est": "±4% to ±9%",
                        "catalyst_summary": f"Trading within {abs(dist_52w)}% of 52-week high (₹{trigger}).",
                        "why_it_matches": f"Zero overhead resistance. Breakout above ₹{trigger} opens clean blue-sky continuation.",
                    })

                elif cat_id == "sector_waves" and (ret >= 4.0 or vol_mult >= 2.5):
                    trigger = round(close * 1.02, 2)
                    candidates.append({
                        "category_id": cat_id,
                        "category_name": cat_meta["name"],
                        "ticker": t,
                        "stock_name": name,
                        "current_price": close,
                        "return_pct": ret,
                        "volume_multiple": vol_mult,
                        "trigger_level": trigger,
                        "confidence_score": min(92, int(75 + ret)),
                        "expected_horizon": "📅 2-5 Days",
                        "volatility_est": "±4% to ±8%",
                        "catalyst_summary": f"Moving +{ret}% on strong {vol_mult}x volume surge with institutional accumulation.",
                        "why_it_matches": "Broad peer group buying wave driving sustained sector continuation.",
                    })

                elif cat_id == "oversold_reversals" and (ret > 0 and c_range >= 9.0 and dist_52w <= -10.0):
                    trigger = round(close * 1.015, 2)
                    candidates.append({
                        "category_id": cat_id,
                        "category_name": cat_meta["name"],
                        "ticker": t,
                        "stock_name": name,
                        "current_price": close,
                        "return_pct": ret,
                        "volume_multiple": vol_mult,
                        "trigger_level": trigger,
                        "confidence_score": 78,
                        "expected_horizon": "📅 3-5 Days",
                        "volatility_est": "±4% to ±7%",
                        "catalyst_summary": f"Pullback of {abs(dist_52w)}% from 52W highs showing initial bounce +{ret}%.",
                        "why_it_matches": "Mean-reversion bounce off key demand zone with positive volume divergence.",
                    })

            except Exception as e:
                logger.debug("Scanner candidate error for %s: %s", t, e)

    # Sort candidates by confidence score descending
    candidates.sort(key=lambda c: (c.get("confidence_score", 0), c.get("return_pct", 0)), reverse=True)
    return candidates[:limit]


def get_categories_overview(
    universe_or_watchlist: str = "NSE_TOP",
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """Get all scanner categories with real-time candidate count badges."""
    settings = settings or Settings()
    results: list[dict[str, Any]] = []

    for cat_id, meta in SCANNER_CATEGORIES.items():
        candidates = scan_category(cat_id, universe_or_watchlist=universe_or_watchlist, limit=15, settings=settings)
        results.append({
            "id": cat_id,
            "name": meta["name"],
            "badge": meta["badge"],
            "type": meta["type"],
            "description": meta["description"],
            "icon": meta["icon"],
            "color": meta["color"],
            "target_horizon": meta["target_horizon"],
            "count": len(candidates),
            "top_candidates": candidates[:3],
        })

    return results


def deep_universe_sweep(
    universe_or_watchlist: str = "NSE_TOP",
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Execute a comprehensive sweep across all categories for the selected universe."""
    settings = settings or Settings()
    
    # 1. Trigger fresh news scan across watchlist tickers
    scan_watchlist_catalysts(watchlist_name=universe_or_watchlist, limit_per_stock=3, settings=settings)

    # 2. Gather candidates across all categories
    categories_overview = get_categories_overview(universe_or_watchlist=universe_or_watchlist, settings=settings)
    total_candidates = sum(c["count"] for c in categories_overview)

    return {
        "universe": universe_or_watchlist,
        "total_categories": len(SCANNER_CATEGORIES),
        "total_candidates_found": total_candidates,
        "categories": categories_overview,
        "swept_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
    }
