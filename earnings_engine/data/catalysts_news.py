"""Short-term Market Catalysts and High-Impact News Scanner.

Fetches real-time financial headlines and corporate announcements across
multiple feeds (Yahoo RSS, Google News RSS, yfinance, NSE announcements),
scores their short-term price urgency/magnitude, categorizes catalyst drivers,
and estimates price impact horizons (1-5 trading days).
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection, is_turso_enabled, _cache_path
from earnings_engine.data.news_sentiment import (
    POSITIVE_WORDS,
    NEGATIVE_WORDS,
    _clean_text,
    calculate_headline_sentiment,
)
from earnings_engine.data.names import get_name

logger = logging.getLogger(__name__)

# High-impact short-term catalyst keyword patterns and weights
CATALYST_RULES: dict[str, dict[str, Any]] = {
    "Order Wins & Contracts": {
        "keywords": [
            "order win", "bags order", "secures order", "awarded contract", "receives order",
            "major contract", "multi-year deal", "commercial deal", "strategic deal",
            "crore order", "million order", "billion contract", "pact with", "signs agreement",
            "wins bid", "lowest bidder", "l1 bidder", "defense order", "railway contract"
        ],
        "base_impact": 82,
        "default_direction": "BULLISH",
        "horizon": "⚡ 1-2 Days (Immediate)",
        "volatility_est": "±4% to ±9%",
    },
    "Earnings & Guidance Surprise": {
        "keywords": [
            "profit surges", "profit jumps", "revenue beats", "earnings beat", "net profit up",
            "guidance raised", "upward revision", "strong q1", "strong q2", "strong q3", "strong q4",
            "q1 net profit", "q2 net profit", "q3 net profit", "q4 net profit", "ebitda surges",
            "profit plunges", "net loss", "margin expands", "guidance slashed", "revenue misses"
        ],
        "base_impact": 88,
        "default_direction": "BULLISH",
        "horizon": "⚡ 1-2 Days (Immediate)",
        "volatility_est": "±5% to ±12%",
    },
    "Regulatory, Approvals & Policy": {
        "keywords": [
            "fda approval", "usfda nod", "regulatory nod", "clearance", "rbi approval",
            "sebi nod", "government approval", "patent granted", "licence granted", "pli scheme",
            "tariff hike", "duty cut", "import duty", "subsidies", "anti-dumping",
            "environmental clearance"
        ],
        "base_impact": 80,
        "default_direction": "BULLISH",
        "horizon": "📅 2-4 Days (Swing)",
        "volatility_est": "±3% to ±8%",
    },
    "M&A, Stake & Expansion": {
        "keywords": [
            "acquisition", "acquires stake", "buys stake", "stake sale", "merger", "joint venture",
            "capacity expansion", "new plant", "capex", "investment of", "open offer",
            "block deal", "bulk deal", "promoter buys", "insider buying", "fund raising", "qip"
        ],
        "base_impact": 78,
        "default_direction": "BULLISH",
        "horizon": "📅 3-5 Days (Swing Momentum)",
        "volatility_est": "±4% to ±10%",
    },
    "Analyst Ratings & Targets": {
        "keywords": [
            "upgrade", "upgrades", "raised target", "price target raised", "buy rating",
            "outperform", "overweight", "initiates coverage", "strong buy", "downgrade",
            "slashes target", "underperform"
        ],
        "base_impact": 65,
        "default_direction": "BULLISH",
        "horizon": "📅 1-3 Days (Short-term)",
        "volatility_est": "±2% to ±6%",
    },
    "Corporate Action & Dividends": {
        "keywords": [
            "bonus issue", "bonus shares", "stock split", "dividend declared", "special dividend",
            "interim dividend", "record date", "share buyback", "board meeting for dividend"
        ],
        "base_impact": 68,
        "default_direction": "BULLISH",
        "horizon": "📅 2-5 Days",
        "volatility_est": "±2% to ±6%",
    },
    "Litigation, Risk & Probes": {
        "keywords": [
            "sebi probe", "sebi notice", "probe", "initiates probe", "ed search", "it raid", "fraud", "scam", "auditor resigns",
            "default on debt", "insolvency", "nclt", "penalty imposed", "lawsuit filed", "inquiry",
            "court stays", "usfda warning letter", "import alert", "downgraded to junk", "rbi ban"
        ],
        "base_impact": 90,
        "default_direction": "BEARISH",
        "horizon": "⚡ 1-2 Days (Immediate Panic)",
        "volatility_est": "±5% to ±15%",
    },
}

# High urgency booster words
URGENCY_BOOSTERS = {
    "breaking": 8, "huge": 6, "record": 6, "massive": 7, "surges": 6, "plunges": 7,
    "soars": 6, "crashes": 8, "billion": 6, "crore": 5, "approved": 7, "warning": 7,
    "banned": 9, "exclusive": 5, "multibagger": 5, "all-time high": 6, "52-week high": 5
}


def _connect(settings: Settings) -> Any:
    settings.ensure_dirs()
    conn = get_db_connection(settings)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS news_catalysts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            stock_name TEXT,
            title TEXT NOT NULL,
            publisher TEXT,
            link TEXT,
            published_at TEXT NOT NULL,
            summary TEXT,
            impact_score INTEGER NOT NULL,
            impact_level TEXT NOT NULL,
            category TEXT NOT NULL,
            direction TEXT NOT NULL,
            expected_horizon TEXT NOT NULL,
            volatility_est TEXT NOT NULL,
            why_it_matters TEXT,
            source TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(ticker, title)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_news_catalysts_ticker_impact
        ON news_catalysts (ticker, impact_score DESC, published_at DESC)
        """
    )
    conn.commit()
    return conn


def score_catalyst_headline(title: str, summary: str = "") -> dict[str, Any]:
    """Score the short-term market impact of a financial news headline and summary."""
    full_text = (title + " " + summary).lower()

    best_category = "General Financial News"
    best_impact = 40
    direction = "NEUTRAL"
    horizon = "📅 1-3 Days"
    volatility_est = "±1% to ±4%"

    # Match catalyst rules
    for cat_name, rule in CATALYST_RULES.items():
        matches = [kw for kw in rule["keywords"] if kw in full_text]
        if matches:
            score = rule["base_impact"] + (len(matches) - 1) * 3
            if score > best_impact:
                best_impact = score
                best_category = cat_name
                horizon = rule["horizon"]
                volatility_est = rule["volatility_est"]
                direction = rule["default_direction"]

    # Sentiment adjustment
    sentiment_score, sentiment_label = calculate_headline_sentiment(title, summary)
    if best_category == "Litigation, Risk & Probes":
        direction = "BEARISH"
    elif sentiment_label == "Bearish" and ("profit" in full_text and ("plunge" in full_text or "drop" in full_text or "loss" in full_text)):
        direction = "BEARISH"
    elif sentiment_label == "Bearish":
        direction = "BEARISH"
    elif sentiment_label == "Bullish":
        direction = "BULLISH"

    # Urgency keyword boost
    for kw, boost in URGENCY_BOOSTERS.items():
        if kw in full_text:
            best_impact += boost

    # Clamp impact score
    impact_score = min(99, max(25, best_impact))

    if impact_score >= 75:
        impact_level = "HIGH"
    elif impact_score >= 50:
        impact_level = "MEDIUM"
    else:
        impact_level = "LOW"

    # Human-readable "Why this matters" rationale
    why_it_matters = _generate_why_it_matters(best_category, direction, horizon, volatility_est, title)

    return {
        "impact_score": impact_score,
        "impact_level": impact_level,
        "category": best_category,
        "direction": direction,
        "expected_horizon": horizon,
        "volatility_est": volatility_est,
        "why_it_matters": why_it_matters,
        "sentiment_score": sentiment_score,
        "sentiment_label": sentiment_label,
    }


def _generate_why_it_matters(category: str, direction: str, horizon: str, volatility: str, title: str) -> str:
    """Generate concise trading rationale for why the headline can drive short-term price."""
    if category == "Order Wins & Contracts":
        return f"Direct revenue accretive trigger. Order wins typically cause immediate re-rating and volume surge ({volatility}) over {horizon}."
    elif category == "Earnings & Guidance Surprise":
        dir_text = "bullish momentum gap-up" if direction == "BULLISH" else "downward margin compression"
        return f"Fundamental quarter surprise. Expect {dir_text} with heightened volume over {horizon}."
    elif category == "Regulatory, Approvals & Policy":
        return f"Regulatory catalyst clears commercial hurdles. Can trigger strong institutional sector accumulation over {horizon}."
    elif category == "M&A, Stake & Expansion":
        return f"Capacity/strategic expansion. Positive for medium-term EPS growth with expected {volatility} move."
    elif category == "Analyst Ratings & Targets":
        return f"Brokerage target upgrade/downgrade provides institutional price target anchors over {horizon}."
    elif category == "Litigation, Risk & Probes":
        return f"⚠️ High-risk overhang. Probes or penalties can cause swift sentiment breakdown ({volatility}) over {horizon}."
    elif category == "Corporate Action & Dividends":
        return f"Corporate reward action. Often supports price floor leading into the announced record date."
    return f"Market news headline creating short-term sentiment momentum ({volatility})."


def fetch_ticker_catalysts(
    ticker: str,
    limit: int = 8,
    force: bool = False,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """Fetch and score short-term news catalysts for a single ticker with fast TTL caching."""
    import pandas as pd
    from concurrent.futures import ThreadPoolExecutor, as_completed

    settings = settings or Settings()
    ticker = ticker.strip().upper()
    name = get_name(ticker, settings) or ticker

    # 1. Check local cache freshness (6 hours TTL)
    if not force:
        with _connect(settings) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT * FROM news_catalysts
                WHERE ticker = ?
                ORDER BY published_at DESC, impact_score DESC
                LIMIT ?
                """,
                (ticker, limit),
            ).fetchall()
            if rows:
                latest_created = rows[0]["created_at"]
                if latest_created:
                    try:
                        dt = pd.to_datetime(latest_created)
                        if dt.tzinfo is None:
                            dt = dt.tz_localize("UTC")
                        age_hours = (datetime.now(timezone.utc) - dt).total_seconds() / 3600.0
                        if age_hours < 6.0:
                            return [dict(r) for r in rows]
                    except Exception:
                        return [dict(r) for r in rows]
                else:
                    return [dict(r) for r in rows]

    # 2. Parallel fetch from RSS / yfinance sources
    from earnings_engine.data.news_sentiment import fetch_yahoo_rss_news, fetch_google_news_rss, fetch_yfinance_news

    market = "IN" if ticker.endswith(".NS") or ticker.endswith(".BO") else "US"
    raw_items: list[dict[str, Any]] = []

    def _get_yahoo():
        return fetch_yahoo_rss_news(ticker)

    def _get_yf():
        return fetch_yfinance_news(ticker)

    def _get_google():
        return fetch_google_news_rss(ticker, market=market)

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(_get_yahoo), executor.submit(_get_yf), executor.submit(_get_google)]
        for f in as_completed(futures, timeout=3.5):
            try:
                res = f.result()
                if res:
                    raw_items.extend(res)
            except Exception:
                pass

    articles: list[dict[str, Any]] = []
    seen_titles: set[str] = set()
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    from earnings_engine.data.news_sentiment import _parse_iso_pubdate

    with _connect(settings) as conn:
        for item in raw_items:
            title = _clean_text(item.get("title", ""))
            if not title or title.lower() in seen_titles:
                continue
            seen_titles.add(title.lower())

            summary = _clean_text(item.get("summary", ""))
            publisher = item.get("publisher", "Market News")
            link = item.get("link", "")
            raw_pub = item.get("published_at")
            pub_date = _parse_iso_pubdate(raw_pub)

            scored = score_catalyst_headline(title, summary)

            record = {
                "ticker": ticker,
                "stock_name": name,
                "title": title,
                "publisher": publisher,
                "link": link,
                "published_at": pub_date,
                "summary": summary,
                "impact_score": scored["impact_score"],
                "impact_level": scored["impact_level"],
                "category": scored["category"],
                "direction": scored["direction"],
                "expected_horizon": scored["expected_horizon"],
                "volatility_est": scored["volatility_est"],
                "why_it_matters": scored["why_it_matters"],
                "source": item.get("source", "rss"),
                "created_at": now_str,
            }
            articles.append(record)

            # Store in SQLite cache
            try:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO news_catalysts (
                        ticker, stock_name, title, publisher, link, published_at,
                        summary, impact_score, impact_level, category, direction,
                        expected_horizon, volatility_est, why_it_matters, source, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record["ticker"], record["stock_name"], record["title"],
                        record["publisher"], record["link"], record["published_at"],
                        record["summary"], record["impact_score"], record["impact_level"],
                        record["category"], record["direction"], record["expected_horizon"],
                        record["volatility_est"], record["why_it_matters"], record["source"],
                        record["created_at"]
                    )
                )
            except Exception as e:
                logger.debug("Failed saving catalyst record: %s", e)

        conn.commit()

    logger.debug("[CATALYSTS] Processed %d catalyst items for %s", len(articles), ticker)

    # Sort by newest published date descending, then impact score
    articles.sort(key=lambda a: (a.get("published_at", ""), a.get("impact_score", 0)), reverse=True)
    return articles[:limit]


def get_short_term_catalysts(
    watchlist_or_universe: str | None = None,
    impact_filter: str | None = None,
    category_filter: str | None = None,
    direction_filter: str | None = None,
    search_query: str | None = None,
    limit: int = 50,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """Query short-term impact catalysts from SQLite cache sorted chronologically (newest first)."""
    settings = settings or Settings()
    with _connect(settings) as conn:
        conn.row_factory = sqlite3.Row

        query = "SELECT * FROM news_catalysts WHERE 1=1"
        params: list[Any] = []

        # Filter by watchlist / universe if supplied
        if watchlist_or_universe and watchlist_or_universe.upper() not in ("", "ALL", "GLOBAL", "NSE_ALL"):
            from earnings_engine.data.watchlists import get_watchlist
            from earnings_engine.data.universe import get_universe

            tickers = get_watchlist(watchlist_or_universe, settings) or get_universe(watchlist_or_universe, settings)
            if tickers:
                placeholders = ",".join("?" for _ in tickers)
                query += f" AND ticker IN ({placeholders})"
                params.extend(tickers)

        if impact_filter and impact_filter.upper() != "ALL":
            if impact_filter.upper() == "HIGH":
                query += " AND impact_level = 'HIGH'"
            elif impact_filter.upper() == "MEDIUM+":
                query += " AND impact_level IN ('HIGH', 'MEDIUM')"

        if category_filter and category_filter.upper() != "ALL":
            query += " AND category = ?"
            params.append(category_filter)

        if direction_filter and direction_filter.upper() != "ALL":
            query += " AND direction = ?"
            params.append(direction_filter.upper())

        if search_query:
            sq = f"%{search_query.strip().lower()}%"
            query += " AND (LOWER(title) LIKE ? OR LOWER(summary) LIKE ? OR LOWER(ticker) LIKE ? OR LOWER(stock_name) LIKE ?)"
            params.extend([sq, sq, sq, sq])

        query += " ORDER BY published_at DESC, impact_score DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


def get_catalyst_summary_stats(settings: Settings | None = None) -> dict[str, Any]:
    """Return high-level summary counts for catalyst distribution."""
    settings = settings or Settings()
    with _connect(settings) as conn:
        total = conn.execute("SELECT COUNT(*) FROM news_catalysts").fetchone()[0]
        high = conn.execute("SELECT COUNT(*) FROM news_catalysts WHERE impact_level = 'HIGH'").fetchone()[0]
        bullish = conn.execute("SELECT COUNT(*) FROM news_catalysts WHERE direction = 'BULLISH'").fetchone()[0]
        bearish = conn.execute("SELECT COUNT(*) FROM news_catalysts WHERE direction = 'BEARISH'").fetchone()[0]

        top_cats = conn.execute(
            """
            SELECT category, COUNT(*) as c
            FROM news_catalysts
            GROUP BY category
            ORDER BY c DESC
            LIMIT 5
            """
        ).fetchall()

        return {
            "total_catalysts": total,
            "high_impact_count": high,
            "bullish_count": bullish,
            "bearish_count": bearish,
            "top_categories": [
                {"category": r[0], "count": r[1]} for r in top_cats
            ],
        }


def scan_watchlist_catalysts(
    watchlist_name: str | None = None,
    limit_per_stock: int = 3,
    force: bool = False,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Scan and fetch real-time catalysts for all stocks in a watchlist/universe concurrently."""
    import time
    from concurrent.futures import ThreadPoolExecutor, as_completed

    t0 = time.perf_counter()
    settings = settings or Settings()
    from earnings_engine.data.watchlists import get_watchlist
    from earnings_engine.data.universe import get_universe

    tickers: list[str] = []
    if watchlist_name and watchlist_name.upper() not in ("", "ALL", "GLOBAL"):
        tickers = get_watchlist(watchlist_name, settings)
        if not tickers:
            tickers = get_universe(watchlist_name, settings)
    
    if not tickers:
        tickers = ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS", "BHARTIARTL.NS", "SBIN.NS", "LT.NS", "PCJEWELLER.NS", "FORCEMOT.NS"]

    all_found = 0
    high_impact_found = 0

    def _worker(t: str):
        try:
            items = fetch_ticker_catalysts(t, limit=limit_per_stock, force=force, settings=settings)
            return len(items), sum(1 for i in items if i.get("impact_level") == "HIGH")
        except Exception as e:
            logger.debug("Catalyst scan error for %s: %s", t, e)
            return 0, 0

    with ThreadPoolExecutor(max_workers=16) as pool:
        future_map = {pool.submit(_worker, t): t for t in tickers}
        for fut in as_completed(future_map):
            cnt, hi_cnt = fut.result()
            all_found += cnt
            high_impact_found += hi_cnt

    elapsed = time.perf_counter() - t0
    logger.info("[CATALYSTS] Scanned %d tickers in %.2fs (found %d catalysts, %d high impact)", len(tickers), elapsed, all_found, high_impact_found)

    stats = get_catalyst_summary_stats(settings)
    return {
        "scanned_tickers": len(tickers),
        "catalysts_fetched": all_found,
        "high_impact_found": high_impact_found,
        "elapsed_seconds": round(elapsed, 2),
        "stats": stats,
    }
