"""Short-term Market Catalysts and High-Impact News Scanner.

Fetches real-time financial headlines and corporate announcements across
multiple feeds (Yahoo RSS, Google News RSS, yfinance, NSE announcements),
scores their short-term price urgency/magnitude, categorizes catalyst drivers,
and estimates price impact horizons (1-5 trading days).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import sqlite3
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
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
        "horizon": "1-2 Days (Immediate)",
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
        "horizon": "1-2 Days (Immediate)",
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
        "horizon": "2-4 Days (Swing)",
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
        "horizon": "3-5 Days (Swing Momentum)",
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
    "Business Updates & Operational Disclosures": {
        "keywords": [
            "quarterly business update", "business update for q", "business update for the quarter",
            "business update", "key operational highlights", "operational performance update",
            "quarterly operating update", "q1 business update", "q2 business update",
            "q3 business update", "q4 business update", "monthly sales", "production and sales",
            "production and offtake", "monthly dispatch", "monthly dispatches", "vehicle sales",
            "jlr wholesales", "sales & dispatches", "sales and dispatches", "quarterly pre-sales",
            "quarterly bookings", "gross booking value", "collections update", "pre-sales & gross booking",
            "pre-sales", "gross advances and deposits", "advances and deposits", "casa ratio update",
            "quarterly loan growth", "disbursements update", "quarterly order inflow", "order book update",
            "standalone revenue & store count", "store count update", "operational highlights",
            "gross advances", "deposits update"
        ],
        "base_impact": 84,
        "default_direction": "BULLISH",
        "horizon": "📅 3-7 Days (Pre-Earnings Swing)",
        "volatility_est": "±4% to ±10%",
    },
    "Corporate Action & Dividends": {
        "keywords": [
            "bonus issue", "bonus shares", "stock split", "dividend declared", "special dividend",
            "interim dividend", "record date", "share buyback", "board meeting for dividend",
            "bonus share issue", "1:1 bonus", "1:2 bonus", "2:1 bonus", "sub-division of shares",
            "split from rs 10 to", "face value split", "final dividend of rs", "interim dividend of rs",
            "tender offer buyback", "open market buyback", "buyback price of rs", "capital reduction",
            "fix record date", "daily share buy-back", "daily buyback", "buy-back of equity shares",
            "corporate action", "ex-date:"
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
            "invocation of pledged shares", "rating downgraded", "downgrade by crisil", "pledge invoked", "promoter pledge",
            "insider trading", "insider trading disclosure", "regulation 7(2)", "regulation 7 (2)",
            "sast regulation 29", "sast reg 29", "sast regulation 31", "encumbrance of shares", "reason for encumbrance"
        ],
        "base_impact": 72,
        "default_direction": "BULLISH",
        "horizon": "📅 2-4 Days",
        "volatility_est": "±2% to ±6%",
    },
    "Miscellaneous Corporate Disclosures": {
        "keywords": [
            "intimation", "regulation 30", "lodr", "exchange disclosure", "commercial production",
            "operations resume", "plant shutdown", "clarification on", "investor presentation",
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


_INITIALIZED_DBS: set[str] = set()


def _connect(settings: Settings) -> Any:
    settings.ensure_dirs()
    conn = get_db_connection(settings)
    try:
        db_key = str(_cache_path(settings))
    except Exception:
        db_key = str(getattr(settings, "db_path", ""))
    if db_key not in _INITIALIZED_DBS:
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
                affected_tickers TEXT DEFAULT '[]',
                source_tier TEXT DEFAULT 'TIER_3',
                corroborating_sources TEXT DEFAULT '[]',
                story_cluster_id TEXT,
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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS news_catalysts_tickers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                catalyst_id INTEGER NOT NULL,
                ticker TEXT NOT NULL,
                impact_type TEXT DEFAULT 'PRIMARY',
                created_at TEXT,
                UNIQUE(catalyst_id, ticker)
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_nct_ticker ON news_catalysts_tickers (ticker)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_nct_catalyst_id ON news_catalysts_tickers (catalyst_id)")

        # News Feed Ingestion Audit & Telemetry Runs
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS news_feed_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                feed_id TEXT NOT NULL,
                feed_name TEXT,
                source_key TEXT,
                scanned_at TEXT NOT NULL,
                articles_fetched INTEGER DEFAULT 0,
                articles_added INTEGER DEFAULT 0,
                status TEXT DEFAULT 'SUCCESS',
                error_message TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_nfr_feed_id_scanned ON news_feed_runs (feed_id, scanned_at DESC)")

        # Corporate Business Update Schedules
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS business_update_schedules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                company_name TEXT,
                update_type TEXT NOT NULL,
                frequency TEXT NOT NULL,
                typical_days_after_period INTEGER DEFAULT 5,
                last_update_date TEXT,
                last_update_headline TEXT,
                last_update_reaction_1d REAL,
                last_update_reaction_3d REAL,
                next_expected_window_start TEXT,
                next_expected_window_end TEXT,
                confidence_score REAL DEFAULT 0.85,
                status TEXT DEFAULT 'ANTICIPATED',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(ticker, update_type)
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_bus_sched_ticker ON business_update_schedules (ticker)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_bus_sched_window ON business_update_schedules (next_expected_window_start, next_expected_window_end)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_bus_sched_status ON business_update_schedules (status)")

        try:
            existing_cols = set()
            for r in conn.execute("PRAGMA table_info(news_catalysts)").fetchall():
                if hasattr(r, "get"):
                    c = r.get("name")
                elif isinstance(r, (tuple, list)) and len(r) > 1:
                    c = r[1]
                elif hasattr(r, "keys") and "name" in r.keys():
                    c = r["name"]
                else:
                    c = None
                if c:
                    existing_cols.add(c)

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
                ("affected_tickers", "TEXT DEFAULT '[]'"),
                ("source_tier", "TEXT DEFAULT 'TIER_3'"),
                ("corroborating_sources", "TEXT DEFAULT '[]'"),
                ("story_cluster_id", "TEXT"),
            ]:
                if not existing_cols or col_name not in existing_cols:
                    try:
                        conn.execute(f"ALTER TABLE news_catalysts ADD COLUMN {col_name} {col_type}")
                    except Exception:
                        pass
            try:
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_news_catalysts_cluster
                    ON news_catalysts (story_cluster_id)
                    """
                )
            except Exception:
                pass
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
        _INITIALIZED_DBS.add(db_key)
    return conn


def cross_reference_exchange_disclosure(
    ticker: str,
    headline: str,
    published_at: str | None = None,
    settings: Settings | None = None,
    window_hours: int = 48,
) -> list[dict[str, Any]]:
    """Cross-reference a news headline against official exchange filings (NSE/BSE/Reg30).

    Searches for official disclosures for the same ticker within `window_hours` (default 48h)
    and verifies lexical/numeric overlap (e.g. order amount, project type, key tokens).
    Returns a list of matching official exchange disclosures.
    """
    settings = settings or Settings()
    ticker = ticker.strip().upper()
    matches: list[dict[str, Any]] = []

    # Clean headline tokens for comparison
    clean_headline = re.sub(r"[^\w\s]", " ", headline.lower())
    stop_words = {
        "shares", "share", "stock", "stocks", "rally", "rallies", "plunge", "plunges",
        "jumps", "jump", "today", "yesterday", "market", "markets", "after", "before",
        "ltd", "limited", "company", "says", "report", "reports", "quarter", "worth",
        "news", "corp", "india", "indian", "firm", "firms", "crore", "cr", "rs", "inr",
    }
    headline_tokens = {w for w in clean_headline.split() if len(w) >= 3 and w not in stop_words}
    headline_nums = set(re.findall(r"\b\d+(?:[\.,]\d+)?\b", clean_headline.replace(",", "")))

    try:
        with _connect(settings) as conn:
            conn.row_factory = sqlite3.Row

            tier1_sources = (
                "nse_announcements", "bse_announcements", "nse_rss", "rbi_rss",
                "exchange_filing", "exchange_filings", "corporate_disclosure"
            )
            placeholders = ",".join("?" for _ in tier1_sources)
            time_filter = ""
            params: list[Any] = [ticker]
            params.extend(tier1_sources)

            if published_at:
                try:
                    dt = datetime.fromisoformat(str(published_at)[:19].replace(" ", "T"))
                    dt_start = (dt - timedelta(hours=window_hours)).strftime("%Y-%m-%d %H:%M:%S")
                    dt_end = (dt + timedelta(hours=window_hours)).strftime("%Y-%m-%d %H:%M:%S")
                    time_filter = "AND published_at BETWEEN ? AND ?"
                    params.extend([dt_start, dt_end])
                except Exception:
                    pass

            query = f"""
                SELECT * FROM news_catalysts
                WHERE ticker = ?
                  AND (source_tier = 'TIER_1' OR source IN ({placeholders}) OR publisher LIKE '%NSE%' OR publisher LIKE '%BSE%')
                  {time_filter}
                ORDER BY published_at DESC
                LIMIT 50
            """
            rows = conn.execute(query, params).fetchall()
            for r in rows:
                filing_dict = dict(r)
                filing_title = (filing_dict.get("title") or "").lower()
                clean_f_title = re.sub(r"[^\w\s]", " ", filing_title)
                filing_tokens = {w for w in clean_f_title.split() if len(w) >= 3 and w not in stop_words}
                filing_nums = set(re.findall(r"\b\d+(?:[\.,]\d+)?\b", clean_f_title.replace(",", "")))

                common_nums = headline_nums.intersection(filing_nums)
                num_matched = bool(common_nums and any(float(n) > 1 for n in common_nums))

                overlap = headline_tokens.intersection(filing_tokens)
                jaccard = len(overlap) / max(1, len(headline_tokens.union(filing_tokens)))

                if (num_matched and len(overlap) >= 1) or len(overlap) >= 3 or jaccard >= 0.20:
                    filing_dict["match_rationale"] = f"Token overlap={len(overlap)}, num_matched={num_matched}"
                    matches.append(filing_dict)

            # Also check reg30_disclosures if table exists
            try:
                r30_check = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='reg30_disclosures'").fetchone()
                if r30_check:
                    clean_sym = ticker.replace(".NS", "").replace(".BO", "").strip().upper()
                    r30_rows = conn.execute(
                        "SELECT * FROM reg30_disclosures WHERE symbol = ? ORDER BY timestamp DESC LIMIT 30",
                        (clean_sym,),
                    ).fetchall()
                    for r in r30_rows:
                        rd = dict(r)
                        r_title = (rd.get("headline") or rd.get("description") or "").lower()
                        clean_r_title = re.sub(r"[^\w\s]", " ", r_title)
                        r_tokens = {w for w in clean_r_title.split() if len(w) >= 3 and w not in stop_words}
                        r_nums = set(re.findall(r"\b\d+(?:[\.,]\d+)?\b", clean_r_title.replace(",", "")))

                        common_nums = headline_nums.intersection(r_nums)
                        num_matched = bool(common_nums and any(float(n) > 1 for n in common_nums))
                        overlap = headline_tokens.intersection(r_tokens)
                        jaccard = len(overlap) / max(1, len(headline_tokens.union(r_tokens)))

                        if (num_matched and len(overlap) >= 1) or len(overlap) >= 3 or jaccard >= 0.20:
                            matches.append({
                                "ticker": ticker,
                                "title": rd.get("headline"),
                                "publisher": rd.get("source", "BSE"),
                                "source": "reg30_disclosures",
                                "published_at": rd.get("timestamp"),
                                "match_rationale": "Matched reg30_disclosures table",
                            })
            except Exception:
                pass

    except Exception as e:
        logger.debug("[CATALYSTS] cross_reference_exchange_disclosure error: %s", e)

    return matches


def determine_catalyst_verification_status(
    item: dict[str, Any],
    matching_filings: list[dict[str, Any]] | None = None,
    corroborating_sources: list[str] | None = None,
) -> tuple[str, list[str]]:
    """Assign deterministic verification status based on source tier, exchange filings, and multi-source corroboration.

    Returns:
        (status, flags) where status is one of:
        - 'EXCHANGE_VERIFIED': Originates directly from Tier 1 exchange feed or matched official exchange disclosure.
        - 'CORROBORATED': Multiple independent Tier 2 major press sources corroborate the story.
        - 'UNVERIFIED_SINGLE_SOURCE': Only a single source reports the catalyst without official exchange corroboration.
    """
    from earnings_engine.data.news_sources import (
        get_source_tier,
        TIER_1_OFFICIAL,
        TIER_2_MAJOR_FINANCIAL_PRESS,
        TIER_3_AGGREGATORS,
    )

    publisher = str(item.get("publisher") or "")
    source = str(item.get("source") or "")
    feed_id = str(item.get("feed_id") or "")
    flags: list[str] = []

    source_tier = get_source_tier(publisher, source, feed_id)

    # 1. Direct Tier 1 source
    if source_tier == TIER_1_OFFICIAL:
        flags.append("TIER_1_PRIMARY_DISCLOSURE")
        return "EXCHANGE_VERIFIED", flags

    # 2. Corroborated by official exchange disclosure
    if matching_filings and len(matching_filings) > 0:
        flags.append("EXCHANGE_DISCLOSURE_CORROBORATED")
        return "EXCHANGE_VERIFIED", flags

    # 3. Multi-source corroboration across independent press feeds
    unique_sources = set()
    if publisher:
        unique_sources.add(publisher.strip().lower())
    if corroborating_sources:
        for s in corroborating_sources:
            if s and s.strip():
                unique_sources.add(s.strip().lower())

    if len(unique_sources) >= 2:
        flags.append("MULTI_SOURCE_CORROBORATED")
        return "CORROBORATED", flags

    # 4. Single unconfirmed source
    flags.append("SINGLE_SOURCE_UNCONFIRMED")
    return "UNVERIFIED_SINGLE_SOURCE", flags


def _parse_catalyst_dt(pub: Any) -> datetime | None:
    """Parse catalyst timestamp string or datetime into UTC datetime."""
    if not pub:
        return None
    if isinstance(pub, datetime):
        return pub if pub.tzinfo else pub.replace(tzinfo=timezone.utc)
    s = str(pub).strip()
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d",
    ):
        try:
            dt = datetime.strptime(s[:19], fmt[: len(s[:19])])
            return dt.replace(tzinfo=timezone.utc)
        except Exception:
            pass
    try:
        from earnings_engine.data.news_sentiment import _parse_iso_pubdate
        iso = _parse_iso_pubdate(s)
        return datetime.strptime(iso, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except Exception:
        return None


def compute_title_similarity(title1: str, title2: str) -> float:
    """Compute normalized semantic token similarity between two headlines.

    Uses n-gram / token Jaccard similarity after removing noise words, publisher tags,
    ticker prefixes, and punctuation, with entity and numeric anchor matching.
    """
    if not title1 or not title2:
        return 0.0

    def _normalize_title_tokens(t: str) -> tuple[set[str], set[str]]:
        text = t.lower()
        # Remove publisher signature after hyphen or pipe (e.g. " - Economic Times", " | LiveMint")
        text = re.sub(r"[\-|–]\s*[a-z0-9\.\s]+$", "", text)
        # Normalize common financial abbreviations
        text = re.sub(r"₹", "rs ", text)
        text = re.sub(r"\bcrores?\b", "cr", text)
        text = re.sub(r"\bbillions?\b", "bn", text)
        text = re.sub(r"\bmillions?\b", "m", text)
        text = re.sub(r"[^\w\s]", " ", text)

        stop_words = {
            "the", "a", "an", "and", "or", "to", "of", "in", "for", "on", "with", "by", "from",
            "at", "as", "is", "be", "shares", "stock", "stocks", "says", "report", "reports",
            "outcome", "meeting", "board", "intimation", "reg", "regulation", "announcement",
            "ltd", "limited", "corp", "corporation", "company", "co", "its", "it", "after",
            "wins", "bag", "bags", "surges", "surge", "surged", "rally", "rallies", "gain", "gains",
        }
        words = text.split()
        tokens = {w for w in words if len(w) >= 2 and w not in stop_words}
        numbers = set(re.findall(r"\b\d+\b", text))
        return tokens, numbers

    tokens1, nums1 = _normalize_title_tokens(title1)
    tokens2, nums2 = _normalize_title_tokens(title2)

    if not tokens1 or not tokens2:
        return 0.0

    union_tokens = tokens1.union(tokens2)
    inter_tokens = tokens1.intersection(tokens2)
    jaccard = len(inter_tokens) / len(union_tokens)

    # Check shared significant numeric anchors (e.g., deal size '2500' or '500')
    shared_nums = {n for n in nums1.intersection(nums2) if int(n) > 1}
    if shared_nums:
        # If they share non-trivial numbers and have some word overlap, boost similarity
        if jaccard >= 0.20 or len(inter_tokens) >= 1:
            jaccard = min(1.0, jaccard + 0.30)

    return round(jaccard, 3)


def cluster_and_deduplicate_news_events(
    items: list[dict[str, Any]],
    window_hours: int = 48,
    similarity_threshold: float = 0.38,
) -> list[dict[str, Any]]:
    """Cluster news articles into deduplicated events with multi-source corroboration attribution.

    Groups articles by (ticker, temporal_window <= 48h, semantic_title_similarity >= threshold).
    Selects the highest-authority source as primary (Tier 1 > Tier 2 > Tier 3, then earliest pub),
    groups other reports under `duplicates`, aggregates `corroborating_sources`, and updates
    `verification_status` to EXCHANGE_VERIFIED or CORROBORATED based on corroboration depth.
    """
    if not items:
        return []

    from earnings_engine.data.news_sources import (
        get_source_tier,
        TIER_1_OFFICIAL,
        TIER_2_MAJOR_FINANCIAL_PRESS,
        TIER_3_AGGREGATORS,
    )

    # Group by normalized ticker
    by_ticker: dict[str, list[dict[str, Any]]] = {}
    for it in items:
        sym = str(it.get("ticker") or "").strip().upper()
        by_ticker.setdefault(sym, []).append(dict(it))

    clustered_results: list[dict[str, Any]] = []

    for ticker, ticker_items in by_ticker.items():
        # Parse and annotate timestamps
        annotated: list[tuple[datetime | None, dict[str, Any]]] = []
        for it in ticker_items:
            dt = _parse_catalyst_dt(it.get("published_at"))
            annotated.append((dt, it))

        # Clusters for this ticker: list of lists of items
        clusters: list[list[dict[str, Any]]] = []

        for dt, item in annotated:
            matched_cluster = None
            best_sim = -1.0

            title = item.get("title") or ""
            for cl in clusters:
                parent_dt = _parse_catalyst_dt(cl[0].get("published_at"))
                # Temporal gate
                if dt and parent_dt:
                    diff_hours = abs((dt - parent_dt).total_seconds()) / 3600.0
                    if diff_hours > window_hours:
                        continue

                sim = compute_title_similarity(title, cl[0].get("title") or "")
                if sim >= similarity_threshold and sim > best_sim:
                    best_sim = sim
                    matched_cluster = cl

            if matched_cluster is not None:
                matched_cluster.append(item)
            else:
                clusters.append([item])

        # Consolidate each cluster
        for cl in clusters:
            for it in cl:
                if not it.get("source_tier"):
                    it["source_tier"] = get_source_tier(it.get("publisher", ""), it.get("source", ""))

            def _rank_key(x: dict[str, Any]) -> tuple[int, int, str]:
                tier = x.get("source_tier")
                tier_score = 3 if tier == TIER_1_OFFICIAL else (2 if tier == TIER_2_MAJOR_FINANCIAL_PRESS else 1)
                impact = int(x.get("impact_score") or 0)
                pub = str(x.get("published_at") or "9999")
                return (-tier_score, -impact, pub)

            sorted_cl = sorted(cl, key=_rank_key)
            parent = dict(sorted_cl[0])
            duplicates = [dict(x) for x in sorted_cl[1:]]

            # Collect distinct corroborating sources
            all_publishers: list[str] = []
            for it in sorted_cl:
                pub = str(it.get("publisher") or "").strip()
                if pub and pub not in all_publishers:
                    all_publishers.append(pub)

            parent["duplicates"] = duplicates
            parent["cluster_size"] = len(sorted_cl)
            parent["corroborating_sources"] = all_publishers

            # Deterministic story_cluster_id
            cluster_seed = f"{ticker}:{parent.get('title', '')[:30]}:{len(sorted_cl)}"
            parent["story_cluster_id"] = f"cl_{hashlib.sha256(cluster_seed.encode('utf-8')).hexdigest()[:16]}"

            # Determine / elevate verification_status
            has_tier_1 = any(it.get("source_tier") == TIER_1_OFFICIAL for it in sorted_cl)
            tier_2_publishers = {
                it.get("publisher")
                for it in sorted_cl
                if it.get("source_tier") == TIER_2_MAJOR_FINANCIAL_PRESS
                and it.get("publisher")
            }

            if has_tier_1 or parent.get("verification_status") == "EXCHANGE_VERIFIED":
                parent["verification_status"] = "EXCHANGE_VERIFIED"
            elif len(tier_2_publishers) >= 2 or (len(all_publishers) >= 2 and any(it.get("source_tier") == TIER_2_MAJOR_FINANCIAL_PRESS for it in sorted_cl)):
                parent["verification_status"] = "CORROBORATED"
            elif parent.get("verification_status") not in ("EXCHANGE_VERIFIED", "CORROBORATED"):
                parent["verification_status"] = "UNVERIFIED_SINGLE_SOURCE"

            clustered_results.append(parent)

    clustered_results.sort(
        key=lambda x: (str(x.get("published_at") or ""), int(x.get("impact_score") or 0)),
        reverse=True,
    )
    return clustered_results


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

    # 6. Vodafone Idea disambiguation (prevent generic 'idea' word collision)
    if clean_sym in ("IDEA", "VODAFONEIDEA"):
        if re.search(r"\b(vodafone(?:\s+idea)?|vi\b|telecom|spectrum|agr\s+dues|arpu|subscribers?|dot\b|trai\b|5g\s+rollout|mobile\s+network)\b", full_text):
            return "IDEA.NS" if ticker.endswith(".NS") else ("IDEA.BO" if ticker.endswith(".BO") else "IDEA.NS")
        return None

    return ticker


ANALYST_SPECULATION_PATTERNS = [
    r"\b(?:analyst|brokerage|expert|nomura|jefferies|clsa|morgan stanley|goldman sachs|kotak|motilal|macquarie|investec|nirmal bang|geojit|sharekhan|icici direct)\s+(?:predicts?|sees?|expects?|views?|notes?|says?|estimates?)\b",
    r"\b(?:could|may|likely to|seen|expected to|poised to|predicted to|eyeing|eyes|in race for|in talks to|set to)\s+(?:win|bag|secure|sign|clinch|receive|order|contract|deal)\b",
    r"\b(?:potential|possible|probable|likely|eyeing|eyes|in race for|in talks for)\s+(?:order win|contract|deal|order|mandate|tender)\b",
    r"\b(?:here(?:'s|\s+is)\s+what\s+(?:brokerages?|analysts?)\s+say)\b",
    r"\b(?:brokerage\s+view|analyst\s+view|brokerage\s+take)\b",
]

ORDER_WIN_PATTERNS = [
    r"\b(?:wins?|bags?|secures?|awarded|receives?|clinches?)\b.*?\b(?:order|contract|deal|mandate|project|tender|licen[sc]e)\b",
    r"\b(?:order|contract|deal|project)\s+worth\s+(?:rs|inr|₹|\$)\b",
    r"\b(?:letter of award|loi\b|purchase order|epc contract|turnkey project|solar project)\b",
    r"\b(?:transmission orders?|exports? order|repeat order|secures? new)\b",
]

ADVERSE_REGULATORY_PATTERNS = [
    r"\b(?:form\s*483|warning\s+letter|import\s+alert|oai\s+classification|observations?|deficiency\s+letter)\b",
    r"\b(?:show[- ]cause\s+notice|penalty\s+of|imposes?\s+penalty|fine\s+of|penalised|penalized)\b",
    r"\b(?:closure\s+notice|raids?|searches?|probe|investigation|sebi\s+action|cbi|ed\s+raids?)\b",
    r"\b(?:ban\s+on|blacklists?|cancels?\s+licen[sc]e|suspends?\s+licen[sc]e)\b",
]


def score_catalyst_headline(title: str, summary: str = "") -> dict[str, Any]:
    """Score the short-term market impact of a financial news headline and summary."""
    full_text = (title + " " + summary).lower()

    best_category = "General Financial News"
    best_impact = 40
    direction = "NEUTRAL"
    horizon = "📅 1-3 Days"
    volatility_est = "±1% to ±4%"

    # 1. Speculative analyst commentary guard
    is_speculative_analyst_call = any(re.search(pat, full_text) for pat in ANALYST_SPECULATION_PATTERNS) or title.strip().endswith("?")

    # 2. Adverse regulatory action guard
    is_adverse_regulatory = any(re.search(pat, full_text) for pat in ADVERSE_REGULATORY_PATTERNS)

    # Match catalyst rules
    for cat_name, rule in CATALYST_RULES.items():
        # Negative guard: Disallow Order Wins if speculative analyst commentary
        if cat_name == "Order Wins & Contracts" and is_speculative_analyst_call:
            continue

        matches = [kw for kw in rule["keywords"] if kw in full_text]
        if matches:
            score = rule["base_impact"] + (len(matches) - 1) * 3
            if score > best_impact:
                best_impact = score
                best_category = cat_name
                horizon = rule["horizon"]
                volatility_est = rule["volatility_est"]
                direction = rule["default_direction"]

    # Match confirmed Order Wins regex patterns if not a speculative analyst call
    if not is_speculative_analyst_call:
        order_win_matched = any(re.search(pat, full_text) for pat in ORDER_WIN_PATTERNS)
        if order_win_matched and best_category in ("General Financial News", "Analyst Ratings & Targets"):
            rule = CATALYST_RULES["Order Wins & Contracts"]
            best_category = "Order Wins & Contracts"
            best_impact = max(best_impact, rule["base_impact"])
            horizon = rule["horizon"]
            volatility_est = rule["volatility_est"]
            direction = rule["default_direction"]

    # If it was a speculative analyst call, ensure it's categorized as Analyst Ratings & Targets
    if is_speculative_analyst_call and best_category in ("General Financial News", "Order Wins & Contracts"):
        rule = CATALYST_RULES["Analyst Ratings & Targets"]
        best_category = "Analyst Ratings & Targets"
        best_impact = max(best_impact, 65)
        horizon = rule["horizon"]
        volatility_est = rule["volatility_est"]
        direction = "BULLISH" if "buy" in full_text or "upgrade" in full_text or "positive" in full_text or "surge" in full_text else "NEUTRAL"

    # Sentiment adjustment
    sentiment_score, sentiment_label = calculate_headline_sentiment(title, summary)

    bearish_earnings_patterns = [
        "profit plunges", "net loss", "loss widens", "profit falls", "profit declines",
        "profit drops", "guidance slashed", "revenue misses", "misses estimates",
        "weak q1", "weak q2", "weak q3", "weak q4", "margin contracts", "plunges",
        "plunges 60%", "downgraded to sell", "cuts price target"
    ]
    if is_adverse_regulatory or best_category == "Litigation, Risk & Probes":
        direction = "BEARISH"
        if is_adverse_regulatory and best_category in ("General Financial News", "Regulatory, Approvals & Policy"):
            best_category = "Litigation, Risk & Probes" if ("probe" in full_text or "sebi" in full_text or "penalty" in full_text) else "Regulatory, Approvals & Policy"
            best_impact = max(best_impact, 80)
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


def is_business_update_headline(title: str, summary: str = "") -> bool:
    """Check if a headline/summary represents a corporate operational or business update disclosure."""
    text = (title + " " + (summary or "")).lower()

    # False positive exclusions: standard board meetings or declared financial results
    strong_exclusions = [
        "to consider financial results",
        "to consider unaudited",
        "to consider un-audited",
        "to consider audited",
        "un-audited financial results",
        "unaudited financial results",
        "audited financial results",
        "board meeting on",
        "notice of postal ballot",
        "loss of share certificate",
        "audio recording of earnings call",
        "transcript of conference call",
    ]
    if any(ex in text for ex in strong_exclusions):
        return False

    keywords = [
        "quarterly business update", "business update for q", "business update for the quarter",
        "business update", "key operational highlights", "operational performance update",
        "quarterly operating update", "q1 business update", "q2 business update",
        "q3 business update", "q4 business update", "monthly sales", "production and sales",
        "production and offtake", "monthly dispatch", "monthly dispatches", "vehicle sales",
        "jlr wholesales", "sales & dispatches", "sales and dispatches", "quarterly pre-sales",
        "quarterly bookings", "gross booking value", "collections update", "pre-sales & gross booking",
        "pre-sales", "gross advances and deposits", "advances and deposits", "casa ratio update",
        "quarterly loan growth", "disbursements update", "quarterly order inflow", "order book update",
        "standalone revenue & store count", "store count update", "operational highlights",
        "gross advances", "deposits update"
    ]
    return any(kw in text for kw in keywords)


def _generate_why_it_matters(category: str, direction: str, horizon: str, volatility: str, title: str) -> str:
    """Generate concise trading rationale for why the headline can drive short-term price."""
    if category == "Order Wins & Contracts":
        return f"Direct revenue accretive trigger. Order wins typically cause immediate re-rating and volume surge ({volatility}) over {horizon}."
    elif category == "Earnings & Guidance Surprise":
        dir_text = "bullish momentum gap-up" if direction == "BULLISH" else "downward margin compression"
        return f"Fundamental quarter surprise. Expect {dir_text} with heightened volume over {horizon}."
    elif category == "Business Updates & Operational Disclosures":
        return f"Key lead indicator ahead of official earnings. Operational disclosures provide immediate alpha ({volatility}) over {horizon}."
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


def get_recent_catalysts(
    ticker: str,
    limit: int = 3,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """Return recent cached catalysts for a ticker without triggering network requests."""
    settings = settings or Settings()
    ticker = ticker.strip().upper()
    try:
        with _connect(settings) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT * FROM news_catalysts
                WHERE ticker = ? AND published_at >= datetime('now', '-14 days')
                ORDER BY impact_score DESC, published_at DESC
                LIMIT ?
                """,
                (ticker, limit),
            ).fetchall()
            return [dict(r) for r in rows]
    except Exception as e:
        logger.debug("[CATALYSTS] Failed to retrieve recent catalysts for %s: %s", ticker, e)
        return []


def get_recent_catalysts_batch(
    tickers: list[str],
    limit_per_ticker: int = 3,
    settings: Settings | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Return recent cached catalysts for multiple tickers in batched queries."""
    if not tickers:
        return {}
    settings = settings or Settings()
    cleaned = [t.strip().upper() for t in tickers if t and t.strip()]
    unique_tickers = list(dict.fromkeys(cleaned))
    result: dict[str, list[dict[str, Any]]] = {t: [] for t in unique_tickers}

    CHUNK_SIZE = 200
    try:
        with _connect(settings) as conn:
            conn.row_factory = sqlite3.Row
            for i in range(0, len(unique_tickers), CHUNK_SIZE):
                chunk = unique_tickers[i : i + CHUNK_SIZE]
                placeholders = ",".join("?" for _ in chunk)
                query = f"""
                    SELECT * FROM news_catalysts
                    WHERE ticker IN ({placeholders}) AND published_at >= datetime('now', '-14 days')
                    ORDER BY impact_score DESC, published_at DESC
                """
                rows = conn.execute(query, chunk).fetchall()
                for r in rows:
                    row_dict = dict(r)
                    sym = row_dict.get("ticker")
                    if sym and sym in result:
                        if len(result[sym]) < limit_per_ticker:
                            result[sym].append(row_dict)
    except Exception as e:
        logger.debug("[CATALYSTS] Failed to retrieve batched recent catalysts: %s", e)
    return result


def fetch_ticker_catalysts(
    ticker: str,
    limit: int = 8,
    force: bool = False,
    run_ai: bool = False,
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

    articles = process_and_verify_news_items(raw_items, settings=settings, force_reanalyze=force, run_ai=run_ai)
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
    strict_verified_only: bool = False,
    deduplicate: bool = False,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """Query short-term impact catalysts from SQLite cache sorted chronologically (newest first)."""
    settings = settings or Settings()
    with _connect(settings) as conn:
        conn.row_factory = sqlite3.Row

        verification_filter = "(verification_status IS NULL OR verification_status != 'REJECTED')"
        if strict_verified_only:
            verification_filter = "verification_status IN ('EXCHANGE_VERIFIED', 'CORROBORATED')"

        if days and days > 0:
            query = f"SELECT * FROM news_catalysts WHERE published_at >= datetime('now', '-{days} days') AND {verification_filter}"
        else:
            query = f"SELECT * FROM news_catalysts WHERE {verification_filter}"
        params: list[Any] = []

        # Filter by watchlist / universe if supplied
        if watchlist_or_universe and watchlist_or_universe.upper() not in ("", "ALL", "GLOBAL", "NSE_ALL"):
            from earnings_engine.data.watchlists import get_watchlist
            from earnings_engine.data.universe import get_universe

            tickers = get_watchlist(watchlist_or_universe, settings) or get_universe(watchlist_or_universe, settings)
            if tickers:
                placeholders = ",".join("?" for _ in tickers)
                query += f" AND (ticker IN ({placeholders}) OR id IN (SELECT catalyst_id FROM news_catalysts_tickers WHERE ticker IN ({placeholders})))"
                params.extend(tickers)
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
                from earnings_engine.data.prices import fetch_batch_live_quotes, get_latest_cached_prices, load_prices_batch

                # Fetch real-time live quotes in parallel with graceful fallback
                live_quotes: dict[str, Any] = {}
                try:
                    live_quotes = fetch_batch_live_quotes(tickers, settings=settings, sync_db=True, max_workers=10)
                except Exception as e:
                    logger.debug("[CATALYSTS] fetch_batch_live_quotes failed: %s", e)

                latest_cached = get_latest_cached_prices(tickers, settings=settings)
                price_dfs = {}
                try:
                    price_dfs = load_prices_batch(tickers, settings=settings, days=max(days + 14, 30))
                except Exception as e:
                    logger.debug("[CATALYSTS] load_prices_batch failed: %s", e)
                today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

                for v in valid:
                    t = v.get("ticker")
                    pub_d = (v.get("published_at") or "")[:10]

                    # 1. Resolve current live market price
                    cur_price = None
                    if t and t in live_quotes and live_quotes[t]:
                        lq = live_quotes[t]
                        if isinstance(lq, dict):
                            cur_price = lq.get("price") or lq.get("close")
                        elif isinstance(lq, (int, float)):
                            cur_price = float(lq)

                    if (cur_price is None or cur_price <= 0) and t in latest_cached:
                        lc = latest_cached[t]
                        if isinstance(lc, dict) and lc.get("close") and float(lc["close"]) > 0:
                            cur_price = float(lc["close"])
                        elif isinstance(lc, (int, float)) and lc > 0:
                            cur_price = float(lc)

                    if (cur_price is None or cur_price <= 0) and v.get("current_price"):
                        cur_price = float(v["current_price"])

                    v["current_price"] = cur_price

                    # 2. Resolve pre-catalyst signal price (benchmark entry price)
                    existing_sig = v.get("signal_price")
                    sig_price = float(existing_sig) if existing_sig and float(existing_sig) > 0 else None
                    sig_date = v.get("signal_date")

                    if t and pub_d:
                        try:
                            # In-memory slice from batched prices if available
                            pdf = price_dfs.get(t) if price_dfs else None
                            sig_val = None
                            sig_dt_val = None
                            if pdf is not None and not pdf.empty:
                                pub_ts = pd.Timestamp(pub_d)
                                if pub_d >= today_str:
                                    sub_df = pdf.loc[pdf.index < pub_ts]
                                    if sub_df.empty or not (sub_df["close"] > 0).any():
                                        sub_df = pdf.loc[pdf.index <= pub_ts]
                                else:
                                    sub_df = pdf.loc[pdf.index <= pub_ts]
                                pos = sub_df[sub_df["close"] > 0]
                                if not pos.empty:
                                    sig_val = float(pos.iloc[-1]["close"])
                                    sig_dt_val = pos.index[-1].strftime("%Y-%m-%d")

                            if sig_val is not None:
                                try:
                                    d_pub = datetime.strptime(pub_d[:10], "%Y-%m-%d").date()
                                    d_sig = datetime.strptime(str(sig_dt_val)[:10], "%Y-%m-%d").date()
                                    if (d_pub - d_sig).days <= 14:
                                        if sig_price is None or (cur_price and abs(sig_price - cur_price) < 1e-4 and (d_pub - d_sig).days >= 0):
                                            sig_price = sig_val
                                            sig_date = sig_dt_val
                                except Exception:
                                    if sig_price is None:
                                        sig_price = sig_val
                                        sig_date = sig_dt_val
                            else:
                                # Fallback to single SQL lookup if not found in batch cache
                                if pub_d >= today_str:
                                    sig_row = conn.execute(
                                        "SELECT close, date FROM price_history WHERE ticker = ? AND date < ? AND close > 0 ORDER BY date DESC LIMIT 1",
                                        (t, pub_d),
                                    ).fetchone()
                                    if not sig_row:
                                        sig_row = conn.execute(
                                            "SELECT close, date FROM price_history WHERE ticker = ? AND date <= ? AND close > 0 ORDER BY date DESC LIMIT 1",
                                            (t, pub_d),
                                        ).fetchone()
                                else:
                                    sig_row = conn.execute(
                                        "SELECT close, date FROM price_history WHERE ticker = ? AND date <= ? AND close > 0 ORDER BY date DESC LIMIT 1",
                                        (t, pub_d),
                                    ).fetchone()

                                if sig_row and sig_row[0] is not None:
                                    try:
                                        d_pub = datetime.strptime(pub_d[:10], "%Y-%m-%d").date()
                                        d_sig = datetime.strptime(str(sig_row[1])[:10], "%Y-%m-%d").date()
                                        if (d_pub - d_sig).days <= 14:
                                            # Prefer the anchor query if missing or if existing was identical to current price
                                            if sig_price is None or (cur_price and abs(sig_price - cur_price) < 1e-4 and (d_pub - d_sig).days >= 0):
                                                sig_price = float(sig_row[0])
                                                sig_date = sig_row[1]
                                    except Exception:
                                        if sig_price is None:
                                            sig_price = float(sig_row[0])
                                            sig_date = sig_row[1]
                        except Exception as e:
                            logger.debug("[CATALYSTS] sig_price query error for %s: %s", t, e)

                    if sig_price is None or sig_price <= 0:
                        sig_price = cur_price
                        sig_date = pub_d

                    v["signal_price"] = sig_price
                    v["signal_date"] = sig_date

                    # 3. Calculate price change percentage
                    if sig_price and cur_price and sig_price > 0:
                        v["price_change_pct"] = round(
                            ((cur_price - sig_price) / sig_price) * 100.0, 2
                        )
                    else:
                        v["price_change_pct"] = 0.0

        if deduplicate and valid:
            valid = cluster_and_deduplicate_news_events(valid)

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
    days: int = 14,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """Retrieve recently harvested news catalysts with impacted stock context and plain-English summary.

    Applies the same recency contract as get_short_term_catalysts:
    - SQL date window (default 14 days)
    - is_headline_current() semantic staleness guard
    """
    settings = settings or Settings()
    with _connect(settings) as conn:
        conn.row_factory = sqlite3.Row
        if days and days > 0:
            rows = conn.execute(
                """
                SELECT ticker, stock_name, title, publisher, link, published_at,
                       summary, impact_score, impact_level, category, direction,
                       expected_horizon, volatility_est, why_it_matters, created_at
                FROM news_catalysts
                WHERE published_at >= datetime('now', '-' || ? || ' days')
                  AND (verification_status IS NULL OR verification_status = 'VERIFIED')
                ORDER BY published_at DESC, id DESC
                LIMIT ?
                """,
                (days, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT ticker, stock_name, title, publisher, link, published_at,
                       summary, impact_score, impact_level, category, direction,
                       expected_horizon, volatility_est, why_it_matters, created_at
                FROM news_catalysts
                WHERE (verification_status IS NULL OR verification_status = 'VERIFIED')
                ORDER BY published_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        results = []
        for r in rows:
            d = dict(r)
            # Secondary semantic staleness check — same guard as get_short_term_catalysts
            if not is_headline_current(d.get("title", ""), d.get("summary", ""), d.get("published_at", "")):
                continue
            results.append(d)
        return results


def record_feed_run(
    feed_id: str,
    feed_name: str,
    source_key: str,
    articles_fetched: int,
    articles_added: int,
    status: str = "SUCCESS",
    error_message: str | None = None,
    scanned_at: str | None = None,
    settings: Settings | None = None,
) -> None:
    """Record an ingestion execution run for a specific news / regulatory feed."""
    settings = settings or Settings()
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    scan_time = scanned_at or now_str
    with _connect(settings) as conn:
        conn.execute(
            """
            INSERT INTO news_feed_runs (
                feed_id, feed_name, source_key, scanned_at,
                articles_fetched, articles_added, status, error_message, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                feed_id, feed_name, source_key, scan_time,
                int(articles_fetched), int(articles_added), status,
                error_message, now_str
            )
        )
        conn.commit()


def record_feed_runs_batch(
    runs: list[dict[str, Any]],
    settings: Settings | None = None,
) -> None:
    """Batch-insert news feed ingestion execution logs."""
    if not runs:
        return
    settings = settings or Settings()
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    with _connect(settings) as conn:
        for r in runs:
            conn.execute(
                """
                INSERT INTO news_feed_runs (
                    feed_id, feed_name, source_key, scanned_at,
                    articles_fetched, articles_added, status, error_message, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    r.get("feed_id", "unknown"),
                    r.get("feed_name", ""),
                    r.get("source_key", "rss"),
                    r.get("scanned_at") or now_str,
                    int(r.get("articles_fetched", 0)),
                    int(r.get("articles_added", 0)),
                    r.get("status", "SUCCESS"),
                    r.get("error_message"),
                    now_str,
                )
            )
        conn.commit()


def get_latest_feed_runs(settings: Settings | None = None) -> dict[str, dict[str, Any]]:
    """Query the most recent ingestion run for every recorded feed in news_feed_runs."""
    settings = settings or Settings()
    latest: dict[str, dict[str, Any]] = {}
    with _connect(settings) as conn:
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """
                SELECT nfr.*
                FROM news_feed_runs nfr
                INNER JOIN (
                    SELECT feed_id, MAX(id) as max_id
                    FROM news_feed_runs
                    GROUP BY feed_id
                ) latest_sub ON nfr.id = latest_sub.max_id
                """
            ).fetchall()
            for r in rows:
                latest[r["feed_id"]] = dict(r)
        except Exception as e:
            logger.debug("[CATALYSTS] Failed querying latest feed runs: %s", e)
    return latest


def harvest_broadband_news(settings: Settings | None = None, run_ai: bool = True) -> dict[str, Any]:
    """Harvest market-wide broadband news feeds (MoneyControl, ET, Mint, NDTV, Google, BSE/NSE)."""
    settings = settings or Settings()
    t0 = time.perf_counter()
    from earnings_engine.data.news_sources import fetch_all_broadband_news_with_feed_telemetry
    from earnings_engine.data.news_pipeline import process_and_verify_news_items, save_verified_news_records_with_feed_breakdown

    raw_items, feed_telemetry = fetch_all_broadband_news_with_feed_telemetry(timeout=6.5)
    saved_cnt = 0
    feed_added_counts: dict[str, int] = {}
    if raw_items:
        articles = process_and_verify_news_items(raw_items, settings=settings, run_ai=run_ai)
        if articles:
            saved_cnt, feed_added_counts = save_verified_news_records_with_feed_breakdown(articles, settings=settings)

    # Attach added counts to each feed telemetry run and persist to news_feed_runs
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    runs_to_record: list[dict[str, Any]] = []
    for f in feed_telemetry:
        f_id = f.get("feed_id", "")
        f_fetched = f.get("articles_fetched", 0)
        f_added = feed_added_counts.get(f_id, 0)
        status = f.get("status", "SUCCESS")
        if status == "SUCCESS":
            if f_added > 0:
                status = "SUCCESS"
            elif f_fetched > 0:
                status = "NO_NEW_ARTICLES"
            else:
                status = "NO_NEW_ARTICLES"
        runs_to_record.append({
            "feed_id": f_id,
            "feed_name": f.get("feed_name", ""),
            "source_key": f.get("source_key", "rss"),
            "scanned_at": f.get("scanned_at") or now_str,
            "articles_fetched": f_fetched,
            "articles_added": f_added,
            "status": status,
            "error_message": f.get("error_message"),
        })

    if runs_to_record:
        record_feed_runs_batch(runs_to_record, settings=settings)

    elapsed = round(time.perf_counter() - t0, 2)
    logger.info("[NEWS-HARVESTER] Broadband harvest completed in %.2fs: %d raw fetched, %d verified & saved across %d feeds", elapsed, len(raw_items), saved_cnt, len(runs_to_record))
    return {
        "raw_fetched": len(raw_items),
        "saved_count": saved_cnt,
        "feeds_scanned": len(runs_to_record),
        "elapsed_seconds": elapsed,
    }


async def news_catalyst_harvest_loop(settings: Settings | None = None) -> None:
    """Async background task: periodically harvests broadband news and watchlist catalysts (interval=300s / 5 min)."""
    import asyncio
    settings = settings or Settings()
    interval_s = 300  # 5 minutes

    logger.info("[NEWS-HARVESTER] Started broadband news catalyst harvester loop (interval=%ds / 5m)", interval_s)
    loop = asyncio.get_event_loop()

    while True:
        try:
            from earnings_engine.data.automation_schedules import record_job_start, record_job_finish
            record_job_start("news_catalyst_harvest", settings)
            t0 = time.perf_counter()

            # 1. Harvest broadband market-wide feeds & exchange announcements (zero-token background execution)
            bb_res = await loop.run_in_executor(None, harvest_broadband_news, settings, False)

            # 2. Harvest for key watchlist tickers
            res = await loop.run_in_executor(None, scan_watchlist_catalysts, "my_watchlist", 3, False, settings)
            elapsed = round(time.perf_counter() - t0, 2)
            summary_msg = f"Harvested {bb_res.get('saved_count', 0)} broadband + {res.get('catalysts_fetched', 0)} watchlist headlines ({res.get('high_impact_found', 0)} high impact)"
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

