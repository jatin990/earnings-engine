"""Broadband Indian Financial News & Regulatory Disclosures Aggregator.

Fetches market-wide, non-ticker-specific corporate and financial news from:
1. MoneyControl RSS Feeds (Latest News, Market Reports, Results, Business)
2. Economic Times Markets RSS Feeds (Markets, Earnings, Corporate Trends)
3. LiveMint RSS Feeds (Markets, Companies)
4. NDTV Profit RSS Feed
5. Google News Market-Wide Feeds (Corporate Announcements, SEBI, Deals)
6. BSE Corporate Filings API (Authoritative Exchange Disclosures)
7. NSE Corporate Announcements API

Provides a high-throughput parallel aggregator (`fetch_all_broadband_news`) returning
normalized news event objects ready for multi-stock entity resolution, deduping, and AI triage.
"""

from __future__ import annotations

import email.utils
import html
import json
import logging
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from typing import Any

from earnings_engine.config import Settings

logger = logging.getLogger(__name__)

# Standard browser headers to avoid 403 blocks from financial portals
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/json,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
}

MONEYCONTROL_FEEDS = [
    ("https://www.moneycontrol.com/rss/latestnews.xml", "MoneyControl"),
    ("https://www.moneycontrol.com/rss/marketreports.xml", "MoneyControl Markets"),
    ("https://www.moneycontrol.com/rss/results.xml", "MoneyControl Results"),
    ("https://www.moneycontrol.com/rss/business.xml", "MoneyControl Business"),
]

ET_FEEDS = [
    ("https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms", "ET Markets"),
    ("https://economictimes.indiatimes.com/markets/stocks/earnings/rssfeeds/2146842.cms", "ET Earnings"),
    ("https://economictimes.indiatimes.com/news/company/corporate-trends/rssfeeds/2143429.cms", "ET Corporate"),
]

LIVEMINT_FEEDS = [
    ("https://www.livemint.com/rss/markets", "LiveMint Markets"),
    ("https://www.livemint.com/rss/companies", "LiveMint Companies"),
]

BUSINESS_STANDARD_FEEDS = [
    ("https://www.business-standard.com/rss/markets-106.rss", "Business Standard Markets"),
    ("https://www.business-standard.com/rss/companies-101.rss", "Business Standard Companies"),
]

HINDU_BUSINESSLINE_FEEDS = [
    ("https://www.thehindubusinessline.com/markets/feeder/default.rss", "Hindu BusinessLine Markets"),
    ("https://www.thehindubusinessline.com/companies/feeder/default.rss", "Hindu BusinessLine Companies"),
]

NDTV_FEEDS = [
    ("https://feeds.feedburner.com/ndtvprofit-latest", "NDTV Profit"),
]

GOOGLE_BROADBAND_QUERIES = [
    ("Indian stock market when:1d", "Google News Markets"),
    ("BSE NSE corporate announcements when:1d", "Google News Announcements"),
    ("order win acquisition merger dividend India stocks when:1d", "Google News Deals"),
]


def _clean_html_text(raw_html: str) -> str:
    """Remove HTML tags, decode entities, and normalize whitespace."""
    if not raw_html:
        return ""
    text = re.sub(r"<[^>]+>", " ", raw_html)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _parse_rss_date(pub_date_str: str | None) -> str:
    """Parse various RSS pubDate formats into ISO-8601 UTC string."""
    if not pub_date_str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    pub_date_str = pub_date_str.strip()
    try:
        # RFC 2822 format (e.g., 'Mon, 01 Sep 2026 08:30:00 +0530')
        parsed_tuple = email.utils.parsedate_tz(pub_date_str)
        if parsed_tuple:
            timestamp = email.utils.mktime_tz(parsed_tuple)
            dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        pass

    # Common ISO-like or custom formats
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S%z",
        "%d %b %Y %H:%M:%S",
        "%a, %d %b %Y %H:%M:%S %Z",
        "%a, %d %b %Y %H:%M:%S %z",
        "%Y/%m/%d %H:%M:%S",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(pub_date_str, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            continue

    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _find_child(node: ET.Element, tags: list[str]) -> ET.Element | None:
    """Find first matching child tag using explicit 'is not None' checks.

    In Python's xml.etree.ElementTree, `bool(element)` evaluates to False if the
    element has no sub-children (len(element) == 0), causing `a or b` chains to fail
    on leaf nodes like <title>Text</title>. Explicitly checking `child is not None`
    preserves leaf nodes correctly.
    """
    for tag in tags:
        child = node.find(tag)
        if child is not None:
            return child
    return None


def _fetch_rss_feed(url: str, publisher_name: str, timeout: float = 6.0) -> list[dict[str, Any]]:
    """Fetch and parse a generic RSS XML feed."""
    items: list[dict[str, Any]] = []
    req = urllib.request.Request(url, headers=DEFAULT_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            xml_data = resp.read()
        root = ET.fromstring(xml_data)

        # Handle RSS 2.0 or Atom
        channel = root.find("channel")
        item_nodes = channel.findall("item") if channel is not None else root.findall(".//item")
        if not item_nodes:
            item_nodes = root.findall(".//{http://www.w3.org/2005/Atom}entry")

        for node in item_nodes:
            title_node = _find_child(node, ["title", "{http://www.w3.org/2005/Atom}title"])
            title = _clean_html_text(title_node.text or "") if title_node is not None else ""
            if not title or len(title) < 8:
                continue

            link_node = _find_child(node, ["link", "{http://www.w3.org/2005/Atom}link"])
            link = ""
            if link_node is not None:
                link = link_node.attrib.get("href", "") or (link_node.text or "")

            desc_node = _find_child(
                node,
                [
                    "description",
                    "summary",
                    "{http://www.w3.org/2005/Atom}summary",
                    "{http://www.w3.org/2005/Atom}content",
                ],
            )
            summary = _clean_html_text(desc_node.text or "") if desc_node is not None else ""

            pub_node = _find_child(
                node,
                [
                    "pubDate",
                    "published",
                    "{http://www.w3.org/2005/Atom}published",
                    "{http://www.w3.org/2005/Atom}updated",
                ],
            )
            pub_date_str = pub_node.text if pub_node is not None else None
            pub_iso = _parse_rss_date(pub_date_str)

            items.append({
                "title": title,
                "summary": summary,
                "published_at": pub_iso,
                "publisher": publisher_name,
                "link": link,
                "source": "broadband_rss",
                "raw_event": {
                    "feed_url": url,
                    "raw_pubDate": pub_date_str,
                }
            })
    except Exception as e:
        logger.debug("[NEWS-SOURCES] Error fetching RSS feed %s (%s): %s", publisher_name, url, e)

    return items


def fetch_moneycontrol_rss(timeout: float = 6.0) -> list[dict[str, Any]]:
    """Fetch recent headlines across MoneyControl RSS feeds."""
    results: list[dict[str, Any]] = []
    for feed_url, pub_name in MONEYCONTROL_FEEDS:
        items = _fetch_rss_feed(feed_url, pub_name, timeout=timeout)
        results.extend(items)
    return results


def fetch_et_markets_rss(timeout: float = 6.0) -> list[dict[str, Any]]:
    """Fetch recent headlines across Economic Times Markets RSS feeds."""
    results: list[dict[str, Any]] = []
    for feed_url, pub_name in ET_FEEDS:
        items = _fetch_rss_feed(feed_url, pub_name, timeout=timeout)
        results.extend(items)
    return results


def fetch_livemint_rss(timeout: float = 6.0) -> list[dict[str, Any]]:
    """Fetch recent headlines across LiveMint RSS feeds."""
    results: list[dict[str, Any]] = []
    for feed_url, pub_name in LIVEMINT_FEEDS:
        items = _fetch_rss_feed(feed_url, pub_name, timeout=timeout)
        results.extend(items)
    return results


def fetch_business_standard_rss(timeout: float = 6.0) -> list[dict[str, Any]]:
    """Fetch recent headlines across Business Standard RSS feeds."""
    results: list[dict[str, Any]] = []
    for feed_url, pub_name in BUSINESS_STANDARD_FEEDS:
        items = _fetch_rss_feed(feed_url, pub_name, timeout=timeout)
        results.extend(items)
    return results


def fetch_hindu_businessline_rss(timeout: float = 6.0) -> list[dict[str, Any]]:
    """Fetch recent headlines across Hindu BusinessLine RSS feeds."""
    results: list[dict[str, Any]] = []
    for feed_url, pub_name in HINDU_BUSINESSLINE_FEEDS:
        items = _fetch_rss_feed(feed_url, pub_name, timeout=timeout)
        results.extend(items)
    return results


def fetch_ndtv_profit_rss(timeout: float = 6.0) -> list[dict[str, Any]]:
    """Fetch recent headlines across NDTV Profit RSS feeds."""
    results: list[dict[str, Any]] = []
    for feed_url, pub_name in NDTV_FEEDS:
        items = _fetch_rss_feed(feed_url, pub_name, timeout=timeout)
        results.extend(items)
    return results


def fetch_google_news_broadband(timeout: float = 6.0) -> list[dict[str, Any]]:
    """Fetch market-wide Google News RSS feeds for Indian equity catalysts."""
    results: list[dict[str, Any]] = []
    for q, pub_name in GOOGLE_BROADBAND_QUERIES:
        encoded_q = urllib.parse.quote(q)
        url = f"https://news.google.com/rss/search?q={encoded_q}&hl=en-IN&gl=IN&ceid=IN:en"
        items = _fetch_rss_feed(url, pub_name, timeout=timeout)
        for it in items:
            # Google news publisher extraction e.g. "Title - The Economic Times"
            t = it["title"]
            if " - " in t:
                parts = t.rsplit(" - ", 1)
                it["title"] = parts[0].strip()
                if len(parts) > 1 and parts[1].strip():
                    it["publisher"] = parts[1].strip()
        results.extend(items)
    return results


def fetch_bse_filings(lookback_days: int = 1, timeout: float = 6.0) -> list[dict[str, Any]]:
    """Fetch authoritative corporate filings from BSE India Announcements API."""
    items: list[dict[str, Any]] = []
    now = datetime.now()
    to_date = now.strftime("%Y%m%d")
    from_date = (now - timedelta(days=max(1, lookback_days))).strftime("%Y%m%d")
    
    url = f"https://api.bseindia.com/BseIndiaAPI/api/AnnGetData/w?strCat=-&strPrevDate={from_date}&strScrip=&strSearch=P&strToDate={to_date}&strType=C"
    req = urllib.request.Request(
        url,
        headers={
            **DEFAULT_HEADERS,
            "Origin": "https://www.bseindia.com",
            "Referer": "https://www.bseindia.com/corporates/ann.html",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw_text = resp.read().decode("utf-8", errors="ignore")
        data = json.loads(raw_text)
        if not isinstance(data, dict):
            return []
        ann_table = data.get("Table") or data.get("Table1") or []
        if isinstance(ann_table, list):
            for row in ann_table:
                # Expected BSE fields: SLONGNAME / SCRIP_CD, HEADLINE, MORE / NEWSSUB, DT_TM
                scrip = str(row.get("SCRIP_CD") or "").strip()
                company_name = str(row.get("SLONGNAME") or row.get("sLongName") or "").strip()
                headline = _clean_html_text(str(row.get("HEADLINE") or row.get("Headline") or ""))
                details = _clean_html_text(str(row.get("MORE") or row.get("NEWSSUB") or row.get("News_sub") or ""))
                dt_str = str(row.get("DT_TM") or row.get("DissemDT") or "").strip()

                if not headline and not details:
                    continue

                full_title = headline if headline else details
                if company_name and not full_title.lower().startswith(company_name.lower()):
                    full_title = f"{company_name}: {full_title}"

                pub_iso = _parse_rss_date(dt_str)

                items.append({
                    "title": full_title[:250],
                    "summary": details[:1000] if details != headline else "",
                    "published_at": pub_iso,
                    "publisher": "BSE Corporate Disclosures",
                    "link": f"https://www.bseindia.com/corporates/ann.html?scrip={scrip}",
                    "source": "bse_filings",
                    "raw_event": row,
                })
    except Exception as e:
        logger.debug("[NEWS-SOURCES] BSE filings API query failed: %s", e)

    return items


def fetch_nse_announcements(lookback_days: int = 1, timeout: float = 6.0) -> list[dict[str, Any]]:
    """Fetch authoritative corporate announcements from NSE India API."""
    items: list[dict[str, Any]] = []
    now = datetime.now()
    to_date = now.strftime("%d-%m-%Y")
    from_date = (now - timedelta(days=max(1, lookback_days))).strftime("%d-%m-%Y")

    url = f"https://www.nseindia.com/api/corporate-announcements?index=equities&from_date={from_date}&to_date={to_date}"
    req = urllib.request.Request(
        url,
        headers={
            **DEFAULT_HEADERS,
            "Origin": "https://www.nseindia.com",
            "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-announcements",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw_text = resp.read().decode("utf-8", errors="ignore")
        data = json.loads(raw_text)
        ann_rows = data if isinstance(data, list) else data.get("data", [])
        for row in ann_rows:
            symbol = str(row.get("symbol") or "").strip()
            company_name = str(row.get("companyName") or symbol).strip()
            subject = _clean_html_text(str(row.get("subject") or row.get("desc") or ""))
            details = _clean_html_text(str(row.get("attchmntText") or row.get("details") or ""))
            an_dt = str(row.get("an_dt") or row.get("date") or "").strip()

            if not subject:
                continue

            full_title = f"{symbol}: {subject}" if symbol else subject
            pub_iso = _parse_rss_date(an_dt)

            items.append({
                "title": full_title[:250],
                "summary": details[:1000] if details else subject,
                "published_at": pub_iso,
                "publisher": "NSE Corporate Disclosures",
                "link": f"https://www.nseindia.com/get-quotes/equity?symbol={symbol}" if symbol else "https://www.nseindia.com",
                "source": "nse_announcements",
                "raw_event": row,
            })
    except Exception as e:
        logger.debug("[NEWS-SOURCES] NSE announcements API query failed: %s", e)

    return items


def fetch_all_broadband_news(timeout: float = 7.0) -> list[dict[str, Any]]:
    """Execute parallel harvesting across all broadband financial news and filing feeds.

    Aggregates:
    - MoneyControl (Latest, Markets, Results, Business)
    - Economic Times (Markets, Earnings, Corporate)
    - LiveMint (Markets, Companies)
    - NDTV Profit
    - Google News (Broad Indian Market Queries)
    - BSE & NSE Official Corporate Announcements

    Returns a deduplicated list of standardized raw news event items.
    """
    fetchers = [
        ("MoneyControl", lambda: fetch_moneycontrol_rss(timeout=timeout)),
        ("EconomicTimes", lambda: fetch_et_markets_rss(timeout=timeout)),
        ("LiveMint", lambda: fetch_livemint_rss(timeout=timeout)),
        ("BusinessStandard", lambda: fetch_business_standard_rss(timeout=timeout)),
        ("HinduBusinessLine", lambda: fetch_hindu_businessline_rss(timeout=timeout)),
        ("NDTVProfit", lambda: fetch_ndtv_profit_rss(timeout=timeout)),
        ("GoogleNewsBroadband", lambda: fetch_google_news_broadband(timeout=timeout)),
        ("BSEFilings", lambda: fetch_bse_filings(lookback_days=1, timeout=timeout)),
        ("NSEAnnouncements", lambda: fetch_nse_announcements(lookback_days=1, timeout=timeout)),
    ]

    all_items: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=min(8, len(fetchers))) as pool:
        future_map = {pool.submit(fn): name for name, fn in fetchers}
        for fut in as_completed(future_map):
            name = future_map[fut]
            try:
                res = fut.result()
                if res:
                    logger.debug("[NEWS-SOURCES] %s fetched %d items", name, len(res))
                    all_items.extend(res)
            except Exception as e:
                logger.debug("[NEWS-SOURCES] %s execution failed: %s", name, e)

    # Basic in-memory deduplication by normalized headline string
    deduped: list[dict[str, Any]] = []
    seen_titles: set[str] = set()

    for it in all_items:
        t_clean = re.sub(r"[^a-z0-9]", "", it.get("title", "").lower())
        if not t_clean or len(t_clean) < 10:
            continue
        if t_clean in seen_titles:
            continue
        seen_titles.add(t_clean)
        deduped.append(it)

    logger.info("[NEWS-SOURCES] Harvested %d broadband news items (%d unique)", len(all_items), len(deduped))
    return deduped
