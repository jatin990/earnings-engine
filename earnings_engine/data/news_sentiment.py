"""News and World Events Sentiment Analysis for financial tickers.

Fetches real-time financial headlines and world events using public zero-key
RSS streams and yfinance news feeds, parsing and scoring them with topic
categorization and sentiment polarity.
"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any
import urllib.request
import urllib.parse

from earnings_engine.config import Settings

logger = logging.getLogger(__name__)

# Key event classification dictionaries
EVENT_TOPIC_KEYWORDS: dict[str, list[str]] = {
    "Earnings & Guidance": [
        "earnings", "revenue", "profit", "quarter", "q1", "q2", "q3", "q4",
        "guidance", "eps", "ebitda", "net income", "topline", "bottomline",
        "results", "financial results"
    ],
    "Expansion & Deals": [
        "acquisition", "merger", "deal", "partnership", "invest", "expansion",
        "joint venture", "buyout", "contract", "order win", "agreement", "stake"
    ],
    "Regulatory & Macro": [
        "regulatory", "government", "policy", "tax", "central bank", "rbi", "fed",
        "inflation", "rate hike", "tariff", "compliance", "probe", "investigation", "sebi"
    ],
    "Product & Innovation": [
        "launch", "new product", "patent", "ai", "technology", "release", "innovation",
        "platform", "unveil", "clinical trial", "fda approval"
    ],
    "Analyst Ratings": [
        "upgrade", "downgrade", "target price", "buy rating", "outperform",
        "overweight", "underperform", "price target", "bull", "bear"
    ],
    "Litigation & Risk": [
        "lawsuit", "legal", "court", "fine", "penalty", "fraud", "scam", "dispute",
        "default", "debt", "downgraded"
    ],
}

# Positive and negative word dictionaries for fast, reliable lexicon sentiment
POSITIVE_WORDS = {
    "surge", "surges", "surged", "jump", "jumps", "jumped", "gain", "gains",
    "gained", "soar", "soars", "soared", "rally", "rallies", "rallied", "record",
    "high", "beat", "beats", "beating", "outperform", "outperformed", "strong",
    "bullish", "profit", "growth", "boost", "boosts", "boosted", "upgrade",
    "upgrades", "upgraded", "dividend", "acquisition", "win", "wins", "won",
    "expansion", "positive", "breakthrough", "success", "innovative", "rebound",
    "bags", "bagged", "order", "orders", "contract", "contracts", "secures", "secured",
    "deal", "deals", "approved", "approval", "approvals"
}

NEGATIVE_WORDS = {
    "plunge", "plunges", "plunged", "drop", "drops", "dropped", "fall", "falls",
    "fell", "tumble", "tumbles", "tumbled", "slump", "slumps", "slumped", "loss",
    "losses", "miss", "misses", "missed", "decline", "declines", "declined",
    "crash", "crashes", "crashed", "bearish", "weak", "warning", "probe",
    "investigation", "fine", "penalty", "lawsuit", "sued", "fraud", "default",
    "downgrade", "downgrades", "downgraded", "debt", "bankrupt", "crisis", "slashed"
}


def _clean_text(text: str) -> str:
    """Strip HTML tags and clean up whitespace."""
    if not text:
        return ""
    clean = re.sub(r"<[^>]+>", " ", text)
    clean = re.sub(r"&[a-z]+;", " ", clean)
    return " ".join(clean.split()).strip()


def calculate_headline_sentiment(title: str, summary: str = "") -> tuple[float, str]:
    """Calculate sentiment polarity score (-1.0 to +1.0) and label from headline/summary."""
    combined = (title + " " + summary).lower()
    words = re.findall(r"\b[a-z]{3,}\b", combined)
    if not words:
        return (0.0, "Neutral")

    pos_count = sum(1 for w in words if w in POSITIVE_WORDS)
    neg_count = sum(1 for w in words if w in NEGATIVE_WORDS)
    total = pos_count + neg_count

    if total == 0:
        return (0.0, "Neutral")

    score = (pos_count - neg_count) / max(total, 1)
    score = round(max(-1.0, min(1.0, score)), 2)

    if score >= 0.25:
        label = "Bullish"
    elif score <= -0.25:
        label = "Bearish"
    else:
        label = "Neutral"

    return (score, label)


def classify_topics(title: str, summary: str = "") -> list[str]:
    """Classify text into market event topics."""
    combined = (title + " " + summary).lower()
    matched_topics: list[str] = []

    for topic, keywords in EVENT_TOPIC_KEYWORDS.items():
        if any(kw in combined for kw in keywords):
            matched_topics.append(topic)

    return matched_topics or ["General Market News"]


import email.utils


def _parse_iso_pubdate(raw_date: Any) -> str:
    """Parse various date formats (RFC 2822 RSS pubDate, UNIX timestamp, ISO) into standard YYYY-MM-DD HH:MM:SS."""
    if not raw_date:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    if isinstance(raw_date, (int, float)):
        try:
            return datetime.fromtimestamp(raw_date, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    raw_str = str(raw_date).strip()

    # 1. Try RFC 2822 (standard for RSS feeds like 'Sat, 22 Aug 2026 09:30:00 GMT')
    try:
        dt = email.utils.parsedate_to_datetime(raw_str)
        if dt:
            return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        pass

    # 2. Try common formats
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%Y-%m-%dT%H:%M:%SZ",
        "%d-%m-%Y",
        "%d/%m/%Y",
    ):
        try:
            dt = datetime.strptime(raw_str[:19], fmt)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            pass

    return raw_str[:19]


def fetch_yfinance_news(ticker: str) -> list[dict[str, Any]]:
    """Fetch news from yfinance for a single ticker."""
    ticker = ticker.strip().upper()
    articles: list[dict[str, Any]] = []
    try:
        from earnings_engine.rate_limits import record_request
        try:
            record_request("yfinance")
        except Exception:
            pass
        import yfinance as yf
        t = yf.Ticker(ticker)
        raw_news = getattr(t, "news", []) or []
        for item in raw_news:
            if not isinstance(item, dict):
                continue
            title = item.get("title") or ""
            if not title:
                continue
            publisher = item.get("publisher") or "Yahoo Finance"
            link = item.get("link") or ""
            prov_time = item.get("providerPublishTime")
            pub_date = _parse_iso_pubdate(prov_time)
            summary = item.get("summary") or ""

            score, label = calculate_headline_sentiment(title, summary)
            topics = classify_topics(title, summary)

            articles.append({
                "title": _clean_text(title),
                "publisher": publisher,
                "link": link,
                "published_at": pub_date,
                "summary": _clean_text(summary),
                "sentiment_score": score,
                "sentiment_label": label,
                "topics": topics,
                "source": "yfinance",
            })
    except Exception as e:
        logger.debug("yfinance news fetch failed for %s: %s", ticker, e)

    return articles


def fetch_yahoo_rss_news(ticker: str) -> list[dict[str, Any]]:
    """Fetch real-time news headlines via Yahoo Finance RSS stream."""
    clean_sym = ticker.strip().upper()
    url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={urllib.parse.quote(clean_sym)}&region=US&lang=en-US"
    articles: list[dict[str, Any]] = []

    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            xml_data = response.read()

        root = ET.fromstring(xml_data)
        for item in root.findall("./channel/item"):
            title_el = item.find("title")
            link_el = item.find("link")
            desc_el = item.find("description")
            pub_el = item.find("pubDate")

            title = title_el.text if title_el is not None and title_el.text else ""
            if not title:
                continue

            summary = desc_el.text if desc_el is not None and desc_el.text else ""
            link = link_el.text if link_el is not None and link_el.text else ""
            pub_date = _parse_iso_pubdate(pub_el.text if pub_el is not None else None)

            score, label = calculate_headline_sentiment(title, summary)
            topics = classify_topics(title, summary)

            articles.append({
                "title": _clean_text(title),
                "publisher": "Yahoo Finance RSS",
                "link": link,
                "published_at": pub_date,
                "summary": _clean_text(summary),
                "sentiment_score": score,
                "sentiment_label": label,
                "topics": topics,
                "source": "yahoo_rss",
            })
    except Exception as e:
        logger.debug("Yahoo RSS fetch failed for %s: %s", ticker, e)

    return articles


def fetch_google_news_rss(ticker: str, market: str = "IN", company_name: str | None = None) -> list[dict[str, Any]]:
    """Fetch recent news headlines via Google News RSS search with strict recency filter."""
    base_sym = ticker.replace(".NS", "").replace(".BO", "").strip().upper()
    if company_name and len(company_name.strip()) > 2 and company_name.strip().upper() != base_sym:
        search_term = f'"{company_name.strip()}"'
    else:
        search_term = base_sym
    query = f"{search_term} stock news when:7d" if market == "IN" else f"{search_term} stock earnings when:7d"
    url = f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}&hl=en-IN&gl=IN&ceid=IN:en"
    articles: list[dict[str, Any]] = []

    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            xml_data = response.read()

        root = ET.fromstring(xml_data)
        for item in root.findall("./channel/item")[:8]:
            title_el = item.find("title")
            link_el = item.find("link")
            desc_el = item.find("description")
            pub_el = item.find("pubDate")
            source_el = item.find("source")

            title = title_el.text if title_el is not None and title_el.text else ""
            if not title:
                continue

            summary = desc_el.text if desc_el is not None and desc_el.text else ""
            link = link_el.text if link_el is not None and link_el.text else ""
            publisher = source_el.text if source_el is not None and source_el.text else "Google News"
            pub_date = _parse_iso_pubdate(pub_el.text if pub_el is not None else None)

            score, label = calculate_headline_sentiment(title, summary)
            topics = classify_topics(title, summary)

            articles.append({
                "title": _clean_text(title),
                "publisher": publisher,
                "link": link,
                "published_at": pub_date,
                "summary": _clean_text(summary),
                "sentiment_score": score,
                "sentiment_label": label,
                "topics": topics,
                "source": "google_rss",
            })
    except Exception as e:
        logger.debug("Google News RSS fetch failed for %s: %s", ticker, e)

    return articles


def get_ticker_news_and_sentiment(
    ticker: str,
    limit: int = 10,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Aggregate multi-source news articles for a ticker and compute aggregate sentiment metrics."""
    ticker = ticker.strip().upper()
    if not ticker:
        return {
            "ticker": ticker,
            "sentiment_score": 0.0,
            "sentiment_label": "Neutral",
            "bullish_count": 0,
            "bearish_count": 0,
            "neutral_count": 0,
            "articles_count": 0,
            "top_topics": [],
            "articles": [],
        }

    # Fetch from yfinance, Yahoo RSS, and Google News RSS
    all_articles: list[dict[str, Any]] = []
    seen_titles: set[str] = set()

    def _add_article(art: dict[str, Any]) -> None:
        title = art.get("title", "").strip().lower()
        if not title or title in seen_titles:
            return
        seen_titles.add(title)
        all_articles.append(art)

    # 1. yfinance
    for a in fetch_yfinance_news(ticker):
        _add_article(a)

    # 2. Yahoo RSS
    if len(all_articles) < limit:
        for a in fetch_yahoo_rss_news(ticker):
            _add_article(a)

    # 3. Google RSS
    if len(all_articles) < limit:
        market = "IN" if ticker.endswith(".NS") or ticker.endswith(".BO") else "US"
        for a in fetch_google_news_rss(ticker, market=market):
            _add_article(a)

    selected_articles = all_articles[:limit]
    if not selected_articles:
        return {
            "ticker": ticker,
            "sentiment_score": 0.0,
            "sentiment_label": "Neutral",
            "bullish_count": 0,
            "bearish_count": 0,
            "neutral_count": 0,
            "articles_count": 0,
            "top_topics": ["General Market News"],
            "articles": [],
        }

    # Calculate aggregate sentiment
    scores = [a["sentiment_score"] for a in selected_articles]
    avg_score = round(sum(scores) / max(len(scores), 1), 2)

    bullish_count = sum(1 for s in scores if s >= 0.25)
    bearish_count = sum(1 for s in scores if s <= -0.25)
    neutral_count = len(scores) - bullish_count - bearish_count

    if avg_score >= 0.20:
        agg_label = "Bullish"
    elif avg_score <= -0.20:
        agg_label = "Bearish"
    else:
        agg_label = "Neutral"

    # Aggregate topic counts
    topic_counts: dict[str, int] = {}
    for a in selected_articles:
        for top in a.get("topics", []):
            topic_counts[top] = topic_counts.get(top, 0) + 1

    top_topics = sorted(topic_counts.keys(), key=lambda t: topic_counts[t], reverse=True)[:4]

    return {
        "ticker": ticker,
        "sentiment_score": avg_score,
        "sentiment_label": agg_label,
        "bullish_count": bullish_count,
        "bearish_count": bearish_count,
        "neutral_count": neutral_count,
        "articles_count": len(selected_articles),
        "top_topics": top_topics,
        "articles": selected_articles,
    }
