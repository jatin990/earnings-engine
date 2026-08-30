"""Short-term Market Catalysts and High-Impact News Scanner.

Fetches real-time financial headlines and corporate announcements across
multiple feeds (Yahoo RSS, Google News RSS, yfinance, NSE announcements),
scores their short-term price urgency/magnitude, categorizes catalyst drivers,
and estimates price impact horizons (1-5 trading days).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import sqlite3
import time
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
            "bags contract", "wins contract", "wins deal", "bags deal",
            "major contract", "multi-year deal", "commercial deal", "strategic deal",
            "crore order", "million order", "billion contract", "pact with", "signs agreement",
            "wins bid", "lowest bidder", "l1 bidder", "defense order", "railway contract",
            "letter of award", "letter of intent", "loi from", "purchase order", "turnkey project",
            "epc contract", "solar project order", "transmission order", "exports order",
            "repeat order", "bags mandate", "wins tender", "clinches order", "emerges l1",
            "secures mandate", "supply agreement", "signs mou", "offtake agreement",
            "long-term agreement", "commercial agreement", "supply contract", "order from", "bus order"
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
            "pat jumps", "pat surges", "pat up", "ebitda up", "operating profit rises",
            "margin expansion", "margin improves", "beats street", "beats estimates",
            "topline growth", "guidance upgrade", "fy guidance raised", "strong quarterly results",
            "profit plunges", "net loss", "margin contracts", "guidance slashed", "revenue misses",
            "profit declines", "pat falls", "loss widens", "misses estimates", "weak q1", "weak q2", "weak q3", "weak q4"
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
            "environmental clearance", "usfda approval", "anda approval", "tentative approval",
            "establishment inspection report", "eir with zero observations", "eir received",
            "nao classification", "vair classification", "dcfi clearance", "dgca approval",
            "cerc approval", "pci approval", "central bank nod", "cabinet nod", "defense clearance",
            "mining lease granted", "environmental approval", "pollution board clearance", "patent grant"
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
            "block deal", "bulk deal", "promoter buys", "insider buying", "fund raising", "qip",
            "acquires 100% stake", "acquires controlling stake", "signs definitive agreement",
            "share purchase agreement", "amalgamation", "demerger", "hiving off", "strategic partnership",
            "expansion plan", "brownfield expansion", "greenfield project", "commissioning of plant",
            "commercial operations commence", "preferential allotment", "rights issue",
            "warrant conversion", "institutional placement", "strategic investor"
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
            "slashes target", "underperform", "goldman sachs upgrades", "morgan stanley overweight",
            "jefferies maintains buy", "nomura initiates", "clsa upgrades", "macquarie buy",
            "kotak upgrades", "motilal oswal buy", "target price raised to", "raised price target",
            "bullish call", "initiates with buy", "maintains outperform", "downgrades to neutral",
            "downgraded to sell", "cuts price target", "target cut to"
        ],
        "base_impact": 65,
        "default_direction": "BULLISH",
        "horizon": "📅 1-3 Days (Short-term)",
        "volatility_est": "±2% to ±6%",
    },
    "Corporate Action & Dividends": {
        "keywords": [
            "bonus issue", "bonus shares", "stock split", "dividend declared", "special dividend",
            "interim dividend", "record date", "share buyback", "board meeting for dividend",
            "bonus share issue", "1:1 bonus", "1:2 bonus", "2:1 bonus", "sub-division of shares",
            "split from rs 10 to", "face value split", "final dividend of rs", "interim dividend of rs",
            "tender offer buyback", "open market buyback", "buyback price of rs", "capital reduction",
            "fix record date"
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
            "court stays", "usfda warning letter", "import alert", "downgraded to junk", "rbi ban", "tax demand", "gst notice", "it demand",
            "show cause notice", "enforcement directorate", "cbi probe", "forensic audit",
            "statutory auditor resigns", "adverse remarks", "whistleblower complaint",
            "form 483 with observations", "official action indicated", "oai classification",
            "import ban", "circuit limit revised down", "delisting notice", "income tax assessment",
            "nclt admits insolvency", "cirp initiated"
        ],
        "base_impact": 90,
        "default_direction": "BEARISH",
        "horizon": "⚡ 1-2 Days (Immediate Panic)",
        "volatility_est": "±5% to ±15%",
    },
    "Management, Governance & Ratings": {
        "keywords": [
            "rating upgraded", "rating upgrade", "crisil upgrade", "care upgrade", "icra upgrade",
            "appoints ceo", "appoints md", "new ceo", "promoter unpledge", "pledge released",
            "crisil upgrades rating to", "care upgrades outlook", "icra revises outlook to positive",
            "ind-ra upgrades", "rating assigned as aa+", "rating assigned as aaa",
            "appointed as managing director", "appointed as chief executive officer",
            "revocation of pledge", "release of pledged shares", "promoter increases stake",
            "open market purchase by promoter", "rating downgraded by care", "rating placed on watch negative",
            "invocation of pledged shares", "rating downgraded", "downgrade by crisil", "pledge invoked", "promoter pledge"
        ],
        "base_impact": 72,
        "default_direction": "BULLISH",
        "horizon": "📅 2-4 Days",
        "volatility_est": "±2% to ±6%",
    },
    "Miscellaneous Corporate Disclosures": {
        "keywords": [
            "intimation", "regulation 30", "lodr", "exchange disclosure", "commercial production",
            "operations resume", "plant shutdown", "business update", "clarification on", "investor presentation",
            "general update", "press release", "outcome of board meeting", "submission of disclosure",
            "newspaper publication", "schedule of analyst meet", "transcript of conference call",
            "audio recording of earnings call", "resumption of operations", "temporary disruption",
            "product launch", "new brand launch", "enters into agreement", "commercial launch"
        ],
        "base_impact": 55,
        "default_direction": "NEUTRAL",
        "horizon": "📅 1-2 Days",
        "volatility_est": "±1% to ±3%",
    },
}

# High urgency booster words
URGENCY_BOOSTERS = {
    "breaking": 8, "huge": 6, "record": 6, "massive": 7, "surges": 6, "plunges": 7,
    "soars": 6, "crashes": 8, "billion": 6, "crore": 5, "approved": 7, "warning": 7,
    "banned": 9, "exclusive": 5, "multibagger": 5, "all-time high": 6, "52-week high": 5,
    "mega": 7, "landslide": 6, "slashes": 6, "skyrockets": 7, "historic": 6, "cleared": 6
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
            verification_status TEXT DEFAULT 'VERIFIED',
            verification_flags TEXT DEFAULT '[]',
            verified_numbers TEXT DEFAULT '{}',
            entity_confidence REAL DEFAULT 0.85,
            canonical_hash TEXT,
            signal_price REAL,
            signal_date TEXT,
            current_price REAL,
            price_change_pct REAL,
            ai_analysis TEXT,
            ai_takeaway TEXT,
            ai_direction TEXT,
            ai_target REAL,
            ai_stop_loss REAL,
            ai_model TEXT,
            ai_analyzed_at TEXT,
            financial_projections TEXT DEFAULT '{}',
            sentiment TEXT DEFAULT 'NEUTRAL',
            temporal_originality TEXT DEFAULT 'NEW_PUBLICATION',
            is_republication INTEGER DEFAULT 0,
            originality_rationale TEXT DEFAULT '',
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
    try:
        existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(news_catalysts)").fetchall()}
        for col_name, col_type in [
            ("verification_status", "TEXT DEFAULT 'VERIFIED'"),
            ("verification_flags", "TEXT DEFAULT '[]'"),
            ("verified_numbers", "TEXT DEFAULT '{}'"),
            ("entity_confidence", "REAL DEFAULT 0.85"),
            ("canonical_hash", "TEXT"),
            ("signal_price", "REAL"),
            ("signal_date", "TEXT"),
            ("current_price", "REAL"),
            ("price_change_pct", "REAL"),
            ("ai_analysis", "TEXT"),
            ("ai_takeaway", "TEXT"),
            ("ai_direction", "TEXT"),
            ("ai_target", "REAL"),
            ("ai_stop_loss", "REAL"),
            ("ai_model", "TEXT"),
            ("ai_analyzed_at", "TEXT"),
            ("financial_projections", "TEXT DEFAULT '{}'"),
            ("sentiment", "TEXT DEFAULT 'NEUTRAL'"),
            ("temporal_originality", "TEXT DEFAULT 'NEW_PUBLICATION'"),
            ("is_republication", "INTEGER DEFAULT 0"),
            ("originality_rationale", "TEXT DEFAULT ''"),
        ]:
            if col_name not in existing_cols:
                conn.execute(f"ALTER TABLE news_catalysts ADD COLUMN {col_name} {col_type}")
    except Exception:
        pass
    # Self-healing: Ensure any raw RFC date strings with comma are converted to standard ISO YYYY-MM-DD HH:MM:SS
    try:
        raw_rows = conn.execute("SELECT id, published_at FROM news_catalysts WHERE published_at LIKE '%,%'").fetchall()
        if raw_rows:
            from earnings_engine.data.news_sentiment import _parse_iso_pubdate
            for r in raw_rows:
                iso_d = _parse_iso_pubdate(r[1])
                conn.execute("UPDATE news_catalysts SET published_at = ? WHERE id = ?", (iso_d, r[0]))
    except Exception:
        pass

    # Self-healing: Correct any misattributed Apollo Tyres headlines from APOLLO.NS to APOLLOTYRE.NS
    try:
        conn.execute(
            """
            DELETE FROM news_catalysts
            WHERE ticker = 'APOLLO.NS' AND (LOWER(title) LIKE '%apollo tyre%' OR LOWER(summary) LIKE '%apollo tyre%')
            AND title IN (SELECT title FROM news_catalysts WHERE ticker = 'APOLLOTYRE.NS')
            """
        )
        conn.execute(
            """
            UPDATE news_catalysts
            SET ticker = 'APOLLOTYRE.NS', stock_name = 'Apollo Tyres'
            WHERE ticker = 'APOLLO.NS' AND (LOWER(title) LIKE '%apollo tyre%' OR LOWER(summary) LIKE '%apollo tyre%')
            """
        )
        conn.execute(
            """
            DELETE FROM news_catalyst_outcomes
            WHERE ticker = 'APOLLO.NS' AND (LOWER(title) LIKE '%apollo tyre%' OR LOWER(summary) LIKE '%apollo tyre%')
            AND title IN (SELECT title FROM news_catalyst_outcomes WHERE ticker = 'APOLLOTYRE.NS')
            """
        )
        conn.execute(
            """
            UPDATE news_catalyst_outcomes
            SET ticker = 'APOLLOTYRE.NS', stock_name = 'Apollo Tyres'
            WHERE ticker = 'APOLLO.NS' AND (LOWER(title) LIKE '%apollo tyre%' OR LOWER(summary) LIKE '%apollo tyre%')
            """
        )
    except Exception:
        pass

    conn.commit()
    return conn


def disambiguate_ticker_for_headline(ticker: str, title: str, summary: str = "") -> str:
    """Disambiguate ticker when broad search keywords match separate corporate entities."""
    full_text = (title + " " + summary).lower()
    clean_sym = ticker.replace(".NS", "").replace(".BO", "").strip().upper()

    # 1. Apollo group disambiguation
    if clean_sym in ("APOLLO", "APOLLOTYRE", "APOLLOHOSP", "APOLLOPIPE"):
        if re.search(r"\b(apollo\s+tyres?|tyres?)\b", full_text):
            return "APOLLOTYRE.NS" if ticker.endswith(".NS") else ("APOLLOTYRE.BO" if ticker.endswith(".BO") else "APOLLOTYRE.NS")
        if re.search(r"\b(apollo\s+hospitals?|hospital|healthcare)\b", full_text):
            return "APOLLOHOSP.NS" if ticker.endswith(".NS") else ("APOLLOHOSP.BO" if ticker.endswith(".BO") else "APOLLOHOSP.NS")
        if re.search(r"\b(apollo\s+pipes?|pipes?)\b", full_text):
            return "APOLLOPIPE.NS" if ticker.endswith(".NS") else ("APOLLOPIPE.BO" if ticker.endswith(".BO") else "APOLLOPIPE.NS")
        if re.search(r"\b(apollo\s+micro|micro\s+systems?)\b", full_text):
            return "APOLLO.NS" if ticker.endswith(".NS") else ("APOLLO.BO" if ticker.endswith(".BO") else "APOLLO.NS")

    # 2. Tata group disambiguation
    if clean_sym in ("TATA", "TATAMOTORS", "TATASTEEL", "TATAPOWER", "TATACONSUM", "TATACOMM", "TATACHEM", "TATAELXSI"):
        if re.search(r"\b(tata\s+motors?|jlr|ev\s+curvv|harrier|safari)\b", full_text):
            return "TATAMOTORS.NS"
        if re.search(r"\b(tata\s+steel)\b", full_text):
            return "TATASTEEL.NS"
        if re.search(r"\b(tata\s+power|solar\s+roof)\b", full_text):
            return "TATAPOWER.NS"
        if re.search(r"\b(tata\s+consumer|tata\s+tea|sampann)\b", full_text):
            return "TATACONSUM.NS"
        if re.search(r"\b(tata\s+elxsi)\b", full_text):
            return "TATAELXSI.NS"
        if re.search(r"\b(tata\s+comm|tata\s+communications?)\b", full_text):
            return "TATACOMM.NS"
        if re.search(r"\b(tata\s+chem|tata\s+chemicals?)\b", full_text):
            return "TATACHEM.NS"

    # 3. Bajaj group disambiguation
    if clean_sym in ("BAJAJ", "BAJFINANCE", "BAJAJFINSV", "BAJAJ-AUTO", "BAJAJHLDNG"):
        if re.search(r"\b(bajaj\s+finance|bajfinance)\b", full_text):
            return "BAJFINANCE.NS"
        if re.search(r"\b(bajaj\s+finserv)\b", full_text):
            return "BAJAJFINSV.NS"
        if re.search(r"\b(bajaj\s+auto|pulsar|chetak)\b", full_text):
            return "BAJAJ-AUTO.NS"

    # 4. HDFC group disambiguation
    if clean_sym in ("HDFC", "HDFCBANK", "HDFCLIFE", "HDFCAMC"):
        if re.search(r"\b(hdfc\s+bank)\b", full_text):
            return "HDFCBANK.NS"
        if re.search(r"\b(hdfc\s+life|insurance)\b", full_text):
            return "HDFCLIFE.NS"
        if re.search(r"\b(hdfc\s+amc|mutual\s+fund)\b", full_text):
            return "HDFCAMC.NS"

    # 5. Adani group disambiguation
    if clean_sym in ("ADANI", "ADANIENT", "ADANIPORTS", "ADANIGREEN", "ADANIPOWER", "ADANIENSOL", "AWL"):
        if re.search(r"\b(adani\s+ports?|port)\b", full_text):
            return "ADANIPORTS.NS"
        if re.search(r"\b(adani\s+green|renewable)\b", full_text):
            return "ADANIGREEN.NS"
        if re.search(r"\b(adani\s+power)\b", full_text):
            return "ADANIPOWER.NS"
        if re.search(r"\b(adani\s+energy|transmission)\b", full_text):
            return "ADANIENSOL.NS"
        if re.search(r"\b(adani\s+wilmar|fortune)\b", full_text):
            return "AWL.NS"
        if re.search(r"\b(adani\s+enterprises?|flagship)\b", full_text):
            return "ADANIENT.NS"

    return ticker


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
    
    bearish_earnings_patterns = [
        "profit plunges", "net loss", "loss widens", "profit falls", "profit declines",
        "profit drops", "guidance slashed", "revenue misses", "misses estimates",
        "weak q1", "weak q2", "weak q3", "weak q4", "margin contracts", "plunges",
        "plunges 60%", "downgraded to sell", "cuts price target"
    ]
    if best_category == "Litigation, Risk & Probes":
        direction = "BEARISH"
    elif any(bp in full_text for bp in bearish_earnings_patterns):
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


def is_headline_current(title: str, summary: str = "", published_at: str = "") -> bool:
    """Validate that a news headline represents a live/upcoming catalyst rather than historical/stale event."""
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)

    # 1. Check published date recency (max 14 days old for short-term swing catalysts)
    if published_at:
        try:
            # Handle YYYY-MM-DD HH:MM:SS or ISO
            pub_dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
            if pub_dt.tzinfo is None:
                pub_dt = pub_dt.replace(tzinfo=timezone.utc)
            if (now - pub_dt).days > 14:
                return False
        except Exception:
            pass

    # 2. Check for explicit historical event dates in title/summary (e.g. "sets July 2 for merger" in August)
    full_text = (title + " " + summary).lower()
    month_map = {
        "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
        "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12
    }

    # Match patterns like "sets July 2", "on June 15", "held on May 10", "dated July 12"
    date_matches = re.findall(r"\b(sets|on|held|dated|meetings? on|for)\s+([a-z]+)\s+(\d{1,2})\b", full_text)
    for _, m_name, d_str in date_matches:
        m_num = month_map.get(m_name)
        if m_num:
            day = int(d_str)
            # If the month is strictly before the current month in the current year, it's historical
            if m_num < now.month or (m_num == now.month and day < (now.day - 7)):
                logger.debug("[CATALYSTS] Filtering historical event headline: %s (%s %d is past)", title, m_name, day)
                return False

    return True


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

    # 1. Check local cache freshness (6 hours TTL) and recency
    if not force:
        with _connect(settings) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT * FROM news_catalysts
                WHERE ticker = ? AND published_at >= datetime('now', '-14 days')
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
                            return [dict(r) for r in rows if is_headline_current(r["title"], r.get("summary", ""), r["published_at"])]
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
        return fetch_google_news_rss(ticker, market=market, company_name=name)

    executor = ThreadPoolExecutor(max_workers=3)
    try:
        futures = [executor.submit(_get_yahoo), executor.submit(_get_yf), executor.submit(_get_google)]
        try:
            for f in as_completed(futures, timeout=4.5):
                try:
                    res = f.result()
                    if res:
                        raw_items.extend(res)
                except Exception:
                    pass
        except BaseException:
            pass
    finally:
        try:
            executor.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass

    # 3. Route raw items through Institutional Multi-Section News Verification Pipeline
    from earnings_engine.data.news_pipeline import process_and_verify_news_items, save_verified_news_records

    # Inject target ticker into raw items if missing
    for it in raw_items:
        if "ticker" not in it:
            it["ticker"] = ticker

    articles = process_and_verify_news_items(raw_items, settings=settings, force_reanalyze=force)
    if articles:
        save_verified_news_records(articles, settings=settings)

    logger.debug("[CATALYSTS] Verified and saved %d catalyst items for %s", len(articles), ticker)

    # Sort by newest published date descending, then impact score
    articles.sort(key=lambda a: (a.get("published_at", ""), a.get("impact_score", 0)), reverse=True)
    return articles[:limit]


def get_short_term_catalysts(
    watchlist_or_universe: str | None = None,
    impact_filter: str | None = None,
    category_filter: str | None = None,
    direction_filter: str | None = None,
    search_query: str | None = None,
    days: int = 14,
    limit: int = 50,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """Query short-term impact catalysts from SQLite cache sorted chronologically (newest first)."""
    settings = settings or Settings()
    with _connect(settings) as conn:
        conn.row_factory = sqlite3.Row

        if days and days > 0:
            query = f"SELECT * FROM news_catalysts WHERE published_at >= datetime('now', '-{days} days') AND (verification_status IS NULL OR verification_status = 'VERIFIED')"
        else:
            query = "SELECT * FROM news_catalysts WHERE (verification_status IS NULL OR verification_status = 'VERIFIED')"
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
        valid = [dict(r) for r in rows if is_headline_current(r["title"], dict(r).get("summary") or "", r["published_at"])]

        # Fast price enrichment: compute signal_price and current_price for each catalyst item
        if valid:
            tickers = list({v["ticker"] for v in valid if v.get("ticker")})
            if tickers:
                placeholders = ",".join("?" for _ in tickers)
                try:
                    latest_rows = conn.execute(
                        f"""
                        SELECT ticker, close, date FROM price_history 
                        WHERE ticker IN ({placeholders}) 
                        AND date = (SELECT MAX(date) FROM price_history p2 WHERE p2.ticker = price_history.ticker)
                        """,
                        tickers,
                    ).fetchall()
                    latest_map = {r[0]: (float(r[1]), r[2]) for r in latest_rows if r[1] is not None}
                except Exception:
                    latest_map = {}

                for v in valid:
                    t = v.get("ticker")
                    pub_d = (v.get("published_at") or "")[:10]
                    cur_price, _ = latest_map.get(t, (None, None))
                    v["current_price"] = cur_price

                    # Look up signal price on or right before published_at date
                    if t and pub_d:
                        try:
                            sig_row = conn.execute(
                                "SELECT close, date FROM price_history WHERE ticker = ? AND date <= ? ORDER BY date DESC LIMIT 1",
                                (t, pub_d),
                            ).fetchone()
                            if sig_row and sig_row[0] is not None:
                                try:
                                    d_pub = datetime.strptime(pub_d[:10], "%Y-%m-%d").date()
                                    d_sig = datetime.strptime(str(sig_row[1])[:10], "%Y-%m-%d").date()
                                    if (d_pub - d_sig).days <= 7:
                                        v["signal_price"] = float(sig_row[0])
                                        v["signal_date"] = sig_row[1]
                                    else:
                                        v["signal_price"] = cur_price
                                        v["signal_date"] = pub_d
                                except Exception:
                                    v["signal_price"] = float(sig_row[0])
                                    v["signal_date"] = sig_row[1]
                            else:
                                v["signal_price"] = cur_price
                                v["signal_date"] = pub_d
                        except Exception:
                            v["signal_price"] = cur_price
                            v["signal_date"] = pub_d
                    else:
                        v["signal_price"] = cur_price
                        v["signal_date"] = pub_d

                    if v.get("signal_price") and v.get("current_price") and v["signal_price"] > 0:
                        v["price_change_pct"] = round(
                            ((v["current_price"] - v["signal_price"]) / v["signal_price"]) * 100.0, 2
                        )
                    else:
                        v["price_change_pct"] = 0.0

        return valid


def get_catalyst_summary_stats(
    watchlist_or_universe: str | None = None,
    days: int = 14,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Return high-level summary counts for catalyst distribution filtered by timeframe and universe."""
    if isinstance(watchlist_or_universe, Settings):
        settings = watchlist_or_universe
        watchlist_or_universe = None
    settings = settings or Settings()
    with _connect(settings) as conn:
        where_clauses: list[str] = []
        params: list[Any] = []

        if days and days > 0:
            where_clauses.append(f"published_at >= datetime('now', '-{days} days')")

        if watchlist_or_universe and isinstance(watchlist_or_universe, str) and watchlist_or_universe.upper() not in ("", "ALL", "GLOBAL", "NSE_ALL"):
            from earnings_engine.data.watchlists import get_watchlist
            from earnings_engine.data.universe import get_universe

            tickers = get_watchlist(watchlist_or_universe, settings) or get_universe(watchlist_or_universe, settings)
            if tickers:
                placeholders = ",".join("?" for _ in tickers)
                where_clauses.append(f"ticker IN ({placeholders})")
                params.extend(tickers)

        where_sql = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        total = conn.execute(f"SELECT COUNT(*) FROM news_catalysts {where_sql}", params).fetchone()[0]
        high_sql = (where_sql + " AND impact_level = 'HIGH'") if where_sql else " WHERE impact_level = 'HIGH'"
        high = conn.execute(f"SELECT COUNT(*) FROM news_catalysts {high_sql}", params).fetchone()[0]

        bull_sql = (where_sql + " AND direction = 'BULLISH'") if where_sql else " WHERE direction = 'BULLISH'"
        bullish = conn.execute(f"SELECT COUNT(*) FROM news_catalysts {bull_sql}", params).fetchone()[0]

        bear_sql = (where_sql + " AND direction = 'BEARISH'") if where_sql else " WHERE direction = 'BEARISH'"
        bearish = conn.execute(f"SELECT COUNT(*) FROM news_catalysts {bear_sql}", params).fetchone()[0]

        top_cats = conn.execute(
            f"""
            SELECT category, COUNT(*) as c
            FROM news_catalysts
            {where_sql}
            GROUP BY category
            ORDER BY c DESC
            LIMIT 5
            """,
            params,
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

    stats = get_catalyst_summary_stats(watchlist_or_universe=watchlist_name, settings=settings)
    return {
        "scanned_tickers": len(tickers),
        "catalysts_fetched": all_found,
        "high_impact_found": high_impact_found,
        "elapsed_seconds": round(elapsed, 2),
        "stats": stats,
    }


def get_recent_news_activity(
    limit: int = 50,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """Retrieve recently harvested news catalysts with impacted stock context and plain-English summary."""
    settings = settings or Settings()
    with _connect(settings) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT ticker, stock_name, title, publisher, link, published_at,
                   summary, impact_score, impact_level, category, direction,
                   expected_horizon, volatility_est, why_it_matters, created_at
            FROM news_catalysts
            ORDER BY published_at DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

        results = []
        for r in rows:
            d = dict(r)
            results.append(d)
        return results


async def news_catalyst_harvest_loop(settings: Settings | None = None) -> None:
    """Async background task: periodically harvests news across active stocks and updates schedules."""
    import asyncio
    settings = settings or Settings()
    interval_s = 600  # 10 minutes

    logger.info("[NEWS-HARVESTER] Started background news catalyst harvester loop (interval=%ds)", interval_s)
    loop = asyncio.get_event_loop()

    while True:
        try:
            from earnings_engine.data.automation_schedules import record_job_start, record_job_finish
            record_job_start("news_catalyst_harvest", settings)
            t0 = time.perf_counter()

            # Harvest for key watchlist and top breakout tickers
            res = await loop.run_in_executor(None, scan_watchlist_catalysts, "my_watchlist", 3, False, settings)
            elapsed = round(time.perf_counter() - t0, 2)
            summary_msg = f"Harvested {res.get('catalysts_fetched', 0)} headlines ({res.get('high_impact_found', 0)} high impact) across {res.get('scanned_tickers', 0)} stocks"
            record_job_finish("news_catalyst_harvest", elapsed, summary_msg, settings=settings)

        except asyncio.CancelledError:
            logger.info("[NEWS-HARVESTER] News catalyst harvester loop cancelled.")
            break
        except Exception as e:
            logger.error("[NEWS-HARVESTER] Harvest cycle error: %s", e)
            try:
                from earnings_engine.data.automation_schedules import record_job_finish
                record_job_finish("news_catalyst_harvest", 0.0, "", error_message=str(e), settings=settings)
            except Exception:
                pass

        try:
            await asyncio.sleep(interval_s)
        except asyncio.CancelledError:
            break

