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

BUSINESS_TODAY_FEEDS = [
    ("https://www.businesstoday.in/rss/stocks", "Business Today Stocks"),
    ("https://www.businesstoday.in/rss/markets", "Business Today Markets"),
    ("https://www.businesstoday.in/rss/industry", "Business Today Corporate"),
]

RBI_FEEDS = [
    ("https://www.rbi.org.in/pressreleases_rss.xml", "RBI Press Releases"),
]

# Official NSE Static Archive RSS Feeds (https://www.nseindia.com/static/rss-feed)
NSE_STATIC_RSS_FEEDS = [
    ("https://nsearchives.nseindia.com/content/RSS/Online_announcements.xml", "NSE Announcements", "corporate_disclosure"),
    ("https://nsearchives.nseindia.com/content/RSS/Corporate_action.xml", "NSE Corporate Actions", "corporate_action"),
    ("https://nsearchives.nseindia.com/content/RSS/InsiderTrading.xml", "NSE Insider Trading", "insider_trading"),
    ("https://nsearchives.nseindia.com/content/RSS/Daily_Buyback.xml", "NSE Daily Buyback", "buyback"),
    ("https://nsearchives.nseindia.com/content/RSS/Financial_Results.xml", "NSE Financial Results", "financial_results"),
    ("https://nsearchives.nseindia.com/content/RSS/Integrated_Filing_Financials.xml", "NSE Integrated Financials", "financial_results"),
    ("https://nsearchives.nseindia.com/content/RSS/Board_Meetings.xml", "NSE Board Meetings", "board_meeting"),
    ("https://nsearchives.nseindia.com/content/RSS/Sast_Regulation29.xml", "NSE SAST Reg 29 (Substantial Acquisition)", "takeover_sast"),
    ("https://nsearchives.nseindia.com/content/RSS/Sast_Regulation31.xml", "NSE SAST Reg 31 (Encumbrance/Pledge)", "promoter_pledge"),
    ("https://nsearchives.nseindia.com/content/RSS/Sast_ReasonForEncumbrance.xml", "NSE SAST Reason For Encumbrance", "promoter_pledge"),
    ("https://nsearchives.nseindia.com/content/RSS/Offer_Documents.xml", "NSE Offer Documents", "capital_raising"),
    ("https://nsearchives.nseindia.com/content/RSS/Related_Party_Trans.xml", "NSE Related Party Transactions", "governance"),
    ("https://nsearchives.nseindia.com/content/RSS/Secretarial_Compliance.xml", "NSE Secretarial Compliance", "governance"),
    ("https://nsearchives.nseindia.com/content/RSS/Statement_Of_Deviation.xml", "NSE Statement Of Deviation", "governance"),
    ("https://nsearchives.nseindia.com/content/RSS/Voting_Results.xml", "NSE Voting Results", "governance"),
    ("https://nsearchives.nseindia.com/content/RSS/Annual_Reports.xml", "NSE Annual Reports", "annual_report"),
    ("https://nsearchives.nseindia.com/content/RSS/brsr.xml", "NSE BRSR Reports", "sustainability"),
    ("https://nsearchives.nseindia.com/content/RSS/Investor_Complaints.xml", "NSE Investor Complaints", "governance"),
    ("https://nsearchives.nseindia.com/content/RSS/Circulars.xml", "NSE Circulars", "exchange_circular"),
]

GOOGLE_BROADBAND_QUERIES = [
    ("Indian stock market when:1d", "Google News Markets"),
    ("BSE NSE corporate announcements when:1d", "Google News Announcements"),
    ("order win acquisition merger dividend India stocks when:1d", "Google News Deals"),
    ("USFDA pharma inspection EIR 483 India when:1d", "Google News USFDA Pharma"),
    ("SEBI order OR penalty OR investigation when:1d", "Google News SEBI Enforcement"),
    ("NCLT insolvency admitted OR IBC India stocks when:1d", "Google News NCLT Insolvency"),
    ("FII DII buying selling stock market when:1d", "Google News Institutional Flows"),
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
        "%d-%b-%Y %H:%M:%S",
        "%d-%b-%Y %H:%M",
        "%d-%m-%Y %H:%M:%S",
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


def fetch_business_today_rss(timeout: float = 6.0) -> list[dict[str, Any]]:
    """Fetch recent market, corporate, and stock headlines from Business Today RSS feeds."""
    results: list[dict[str, Any]] = []
    for feed_url, pub_name in BUSINESS_TODAY_FEEDS:
        items = _fetch_rss_feed(feed_url, pub_name, timeout=timeout)
        results.extend(items)
    return results


def fetch_rbi_press_releases_rss(timeout: float = 6.0) -> list[dict[str, Any]]:
    """Fetch authoritative central bank press releases and policy circulars from RBI RSS."""
    results: list[dict[str, Any]] = []
    for feed_url, pub_name in RBI_FEEDS:
        items = _fetch_rss_feed(feed_url, pub_name, timeout=timeout)
        for it in items:
            it["category"] = "banking_regulatory"
            it["source"] = "rbi_rss"
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


def fetch_nse_static_rss_feeds(
    selected_feeds: list[tuple[str, str, str]] | None = None,
    timeout: float = 6.0,
) -> list[dict[str, Any]]:
    """Fetch official structured regulatory and corporate disclosures from NSE static RSS feeds.

    Harvests feeds hosted at https://nsearchives.nseindia.com/content/RSS/*.xml covering:
    - Announcements, Board Meetings, Corporate Actions (Dividends/Splits)
    - Insider Trading (Reg 7-2), Daily Share Buybacks, SAST Reg 29/31 & Encumbrances
    - Financial Results, Annual Reports, and Exchange Circulars.
    """
    feeds = selected_feeds or NSE_STATIC_RSS_FEEDS
    headers = {
        **DEFAULT_HEADERS,
        "Referer": "https://www.nseindia.com/static/rss-feed",
    }

    # Lazy-load company name and symbol caches for entity resolution
    clean_name_map: dict[str, str] = {}
    known_symbols: dict[str, str] = {}
    try:
        from earnings_engine.data.names import _connect
        conn = _connect(Settings())
        for t, n in conn.execute("SELECT ticker, name FROM tickers WHERE name IS NOT NULL").fetchall():
            norm = re.sub(r"[^a-z0-9]", "", str(n).lower().replace("limited", "").replace("ltd", ""))
            clean_name_map[norm] = t
        for r in conn.execute("SELECT ticker FROM tickers").fetchall():
            sym = r[0].replace(".NS", "").replace(".BO", "").upper()
            known_symbols[sym] = r[0]
    except Exception as e:
        logger.debug("[NEWS-SOURCES] NSE RSS symbol cache initialization notice: %s", e)

    def _resolve_symbol(title_str: str, desc_str: str, link_str: str) -> str | None:
        """Extract or resolve ticker symbol from NSE RSS metadata."""
        # 1. Pipe-delimited prefix e.g. "QUESS|Quess Corp Limited|..."
        pipe_m = re.match(r"^([A-Z0-9_\-]+)\|", desc_str)
        if pipe_m:
            c = pipe_m.group(1).upper()
            if c in known_symbols:
                return known_symbols[c]
            return f"{c}.NS"

        # 2. PDF filename prefix e.g. "/corporate/HUBTOWN_12092026..." or "/corporate/SIS_..."
        link_m = re.search(r"/corporate/([A-Za-z0-9]+)_", link_str)
        if link_m:
            cand = link_m.group(1).upper()
            if cand in known_symbols:
                return known_symbols[cand]
            if len(cand) >= 2 and not cand.startswith("XBRL") and not cand.startswith("INDAS"):
                return f"{cand}.NS"

        # 3. Clean company name from title e.g. "V.S.T Tillers Tractors Limited - Ex-Date: 16-Sep-2026"
        comp_candidate = title_str.split(" - ")[0].split(" : ")[0].strip()
        norm_name = re.sub(r"[^a-z0-9]", "", comp_candidate.lower().replace("limited", "").replace("ltd", ""))
        if norm_name in clean_name_map:
            return clean_name_map[norm_name]

        # 4. Full title match against clean company names
        norm_full = re.sub(r"[^a-z0-9]", "", title_str.lower().replace("limited", "").replace("ltd", ""))
        if norm_full in clean_name_map:
            return clean_name_map[norm_full]

        return None

    def _fetch_single_nse_feed(feed_url: str, pub_name: str, feed_category: str) -> list[dict[str, Any]]:
        feed_items: list[dict[str, Any]] = []
        req = urllib.request.Request(feed_url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                xml_data = resp.read()
            root = ET.fromstring(xml_data)
            channel = root.find("channel")
            raw_nodes = channel.findall("item") if channel is not None else root.findall(".//item")

            for node in raw_nodes:
                title_node = _find_child(node, ["title"])
                desc_node = _find_child(node, ["description"])
                link_node = _find_child(node, ["link"])
                date_node = _find_child(node, ["pubDate"])

                raw_title = _clean_html_text(title_node.text or "") if title_node is not None else ""
                raw_desc = _clean_html_text(desc_node.text or "") if desc_node is not None else ""
                link = (link_node.text or "").strip() if link_node is not None else ""
                raw_date = (date_node.text or "").strip() if date_node is not None else ""

                if not raw_title and not raw_desc:
                    continue

                pub_iso = _parse_rss_date(raw_date)
                sym = _resolve_symbol(raw_title, raw_desc, link)

                # Format human-friendly actionable headline
                if sym:
                    clean_sym = sym.replace(".NS", "")
                    if feed_category == "corporate_action" and "Ex-Date" in raw_title:
                        purpose_m = re.search(r"PURPOSE:([^\|]+)", raw_desc)
                        purpose = purpose_m.group(1).strip() if purpose_m else ""
                        headline = f"{clean_sym}: {purpose}" if purpose else f"{clean_sym}: Corporate Action"
                        if "Ex-Date" in raw_title:
                            ex_part = raw_title.split(" - ")[-1].strip()
                            headline += f" ({ex_part})"
                    elif feed_category == "insider_trading":
                        headline = f"{clean_sym}: Insider Trading Disclosure (Reg 7(2))"
                    elif feed_category == "buyback":
                        headline = f"{clean_sym}: Daily Share Buy-Back Update"
                    elif feed_category == "board_meeting":
                        meeting_m = re.search(r"Meeting Date:\s*([^\|]+)", raw_desc)
                        m_date = meeting_m.group(1).strip() if meeting_m else ""
                        headline = f"{clean_sym}: Board Meeting Scheduled {m_date}".strip()
                    elif raw_title and not raw_title.startswith(clean_sym):
                        # If description has specific subject
                        subj_m = re.search(r"SUBJECT:\s*([^\|]+)", raw_desc)
                        if subj_m:
                            headline = f"{clean_sym}: {subj_m.group(1).strip()}"
                        else:
                            headline = f"{clean_sym}: {raw_title}"
                    else:
                        headline = raw_title
                else:
                    headline = raw_title or raw_desc

                summary_text = raw_desc if raw_desc else raw_title
                feed_items.append({
                    "title": headline[:250],
                    "summary": summary_text[:1000],
                    "published_at": pub_iso,
                    "publisher": pub_name,
                    "link": link if link else "https://www.nseindia.com",
                    "source": "nse_rss",
                    "category": feed_category,
                    "ticker": sym,
                    "raw_event": {
                        "feed_url": feed_url,
                        "raw_title": raw_title,
                        "raw_desc": raw_desc,
                        "raw_date": raw_date,
                    },
                })
        except Exception as e:
            logger.debug("[NEWS-SOURCES] NSE RSS fetch failed for %s: %s", feed_url, e)

        return feed_items

    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=min(10, len(feeds))) as pool:
        future_map = {
            pool.submit(_fetch_single_nse_feed, u, pub, cat): pub
            for u, pub, cat in feeds
        }
        for fut in as_completed(future_map):
            try:
                res = fut.result()
                if res:
                    results.extend(res)
            except Exception as e:
                logger.debug("[NEWS-SOURCES] NSE RSS thread failed: %s", e)

    return results


def fetch_all_broadband_news(timeout: float = 7.0) -> list[dict[str, Any]]:
    """Execute parallel harvesting across all broadband financial news and filing feeds.

    Aggregates:
    - MoneyControl (Latest, Markets, Results, Business)
    - Economic Times (Markets, Earnings, Corporate)
    - LiveMint (Markets, Companies)
    - Business Standard (Markets, Companies)
    - Hindu BusinessLine (Markets, Companies)
    - NDTV Profit
    - Business Today (Stocks, Markets, Corporate)
    - RBI Official Press Releases & Circulars
    - Google News Targeted Catalyst Feeds (USFDA Pharma, SEBI Orders, NCLT, FII/DII)
    - BSE & NSE Official Corporate Announcements REST API
    - NSE Static Archive RSS Feeds (Announcements, Actions, Insider Trading, Buybacks, Meetings)

    Returns a deduplicated list of standardized raw news event items.
    """
    fetchers = [
        ("MoneyControl", lambda: fetch_moneycontrol_rss(timeout=timeout)),
        ("EconomicTimes", lambda: fetch_et_markets_rss(timeout=timeout)),
        ("LiveMint", lambda: fetch_livemint_rss(timeout=timeout)),
        ("BusinessStandard", lambda: fetch_business_standard_rss(timeout=timeout)),
        ("HinduBusinessLine", lambda: fetch_hindu_businessline_rss(timeout=timeout)),
        ("NDTVProfit", lambda: fetch_ndtv_profit_rss(timeout=timeout)),
        ("BusinessToday", lambda: fetch_business_today_rss(timeout=timeout)),
        ("RBIPressReleases", lambda: fetch_rbi_press_releases_rss(timeout=timeout)),
        ("GoogleNewsBroadband", lambda: fetch_google_news_broadband(timeout=timeout)),
        ("BSEFilings", lambda: fetch_bse_filings(lookback_days=1, timeout=timeout)),
        ("NSEAnnouncements", lambda: fetch_nse_announcements(lookback_days=1, timeout=timeout)),
        ("NSEStaticRSS", lambda: fetch_nse_static_rss_feeds(timeout=timeout)),
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


def get_all_feed_metadata() -> list[dict[str, Any]]:
    """Return structured metadata for all registered news, filing, and regulatory feeds.

    Covers:
    - 19 Official NSE Static RSS Feeds (Announcements, Corporate Actions, Insider Trading, etc.)
    - Financial Media RSS Feeds (MoneyControl, ET, Mint, Business Standard, Business Today, etc.)
    - Official Regulatory Feeds (RBI Press Releases, BSE/NSE APIs)
    - Targeted Topic Streams (USFDA, SEBI, NCLT, FII/DII)
    """
    feeds: list[dict[str, Any]] = []

    # 1. NSE Static Archive Feeds (Official Exchange XML)
    for url, name, cat in NSE_STATIC_RSS_FEEDS:
        slug = url.split("/")[-1].replace(".xml", "").lower()
        feeds.append({
            "id": f"nse_rss_{slug}",
            "name": name,
            "group": "NSE Exchange Disclosures",
            "category": cat.replace("_", " ").title(),
            "type": "Exchange XML",
            "url": url,
            "source_key": "nse_rss",
            "status": "Active",
            "description": f"Official NSE exchange XML feed for {name}",
        })

    # 2. Financial Portals & Media Feeds
    portal_groups = [
        ("MoneyControl", MONEYCONTROL_FEEDS, "Financial Portal"),
        ("Economic Times", ET_FEEDS, "Financial Newspaper"),
        ("LiveMint", LIVEMINT_FEEDS, "Financial Daily"),
        ("Business Standard", BUSINESS_STANDARD_FEEDS, "Financial Daily"),
        ("Hindu BusinessLine", HINDU_BUSINESSLINE_FEEDS, "Financial Daily"),
        ("NDTV Profit", NDTV_FEEDS, "Financial News Broadcast"),
        ("Business Today", BUSINESS_TODAY_FEEDS, "Business Magazine & Portal"),
    ]
    for publisher, feed_list, ftype in portal_groups:
        for url, name in feed_list:
            slug = re.sub(r"[^a-z0-9]", "_", name.lower())
            feeds.append({
                "id": f"media_{slug}",
                "name": name,
                "group": "Financial Media & Portals",
                "category": "Corporate & Market News",
                "type": "Portal RSS",
                "url": url,
                "source_key": "rss",
                "status": "Active",
                "description": f"{publisher} live RSS stream: {name}",
            })

    # 3. Regulatory & Official Institutional Feeds
    for url, name in RBI_FEEDS:
        feeds.append({
            "id": "rbi_press_releases",
            "name": name,
            "group": "Official Regulatory & Exchange",
            "category": "Monetary Policy & Circulars",
            "type": "Central Bank RSS",
            "url": url,
            "source_key": "rbi_rss",
            "status": "Active",
            "description": "Reserve Bank of India official press releases, notifications, and policy directives",
        })

    feeds.append({
        "id": "bse_announcements_api",
        "name": "BSE Corporate Announcements API",
        "group": "Official Regulatory & Exchange",
        "category": "Corporate Filings",
        "type": "Exchange REST API",
        "url": "https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w",
        "source_key": "bse_filings",
        "status": "Active",
        "description": "Bombay Stock Exchange real-time corporate filing stream",
    })

    feeds.append({
        "id": "nse_announcements_api",
        "name": "NSE Corporate Announcements API",
        "group": "Official Regulatory & Exchange",
        "category": "Corporate Filings",
        "type": "Exchange REST API",
        "url": "https://www.nseindia.com/api/corporate-announcements",
        "source_key": "nse_announcements",
        "status": "Active",
        "description": "National Stock Exchange real-time corporate announcements API",
    })

    # 4. Targeted Catalyst & Event Topic Streams
    for query, name in GOOGLE_BROADBAND_QUERIES:
        slug = re.sub(r"[^a-z0-9]", "_", name.lower())
        encoded_q = urllib.parse.quote(query)
        feed_url = f"https://news.google.com/rss/search?q={encoded_q}&hl=en-IN&gl=IN&ceid=IN:en"
        feeds.append({
            "id": f"topic_{slug}",
            "name": name,
            "group": "Targeted Regulatory Monitors",
            "category": "Regulatory & Market Flows",
            "type": "Topic RSS Stream",
            "url": feed_url,
            "source_key": "google_rss",
            "status": "Active",
            "description": f"Real-time event monitor for: '{query}'",
        })

    return feeds
