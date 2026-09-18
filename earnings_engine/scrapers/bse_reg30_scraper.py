"""
BSE Corporate Announcements Scraper for SEBI Reg 30 Disclosures.
Polls BSE Corporate Announcements feed and filters for High-Impact Reg 30 catalysts.
"""

import hashlib
import logging
import requests
from datetime import datetime
from typing import List, Dict, Any, Optional

from earnings_engine.processing.reg30_classifier import classify_reg30_filing
from earnings_engine.db.reg30_storage import init_reg30_db, insert_reg30_disclosure

logger = logging.getLogger(__name__)

BSE_ANNOUNCEMENTS_API = "https://api.bseindia.com/BseIndiaAPI/api/AnnGetData/w"
BSE_ATTACHMENT_BASE = "https://www.bseindia.com/xml-data/corpfiling/AttachHis/"

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.bseindia.com/corporates/ann.html",
    "Origin": "https://www.bseindia.com",
}


def generate_disclosure_id(scrip_code: str, headline: str, timestamp_str: str) -> str:
    """Generates a deterministic unique hash ID for deduplication."""
    raw = f"{scrip_code}_{headline}_{timestamp_str}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:24]


def fetch_bse_announcements(
    category: str = "Company Update",
    page_no: int = 1,
    timeout: int = 15,
) -> List[Dict[str, Any]]:
    """
    Fetches corporate announcements from the official BSE endpoint.
    """
    params = {
        "strCat": category,
        "strPrevDate": "",
        "strScrip": "",
        "strSearch": "P",
        "strToDate": "",
        "strType": "C",
        "pageno": str(page_no),
    }

    try:
        resp = requests.get(
            BSE_ANNOUNCEMENTS_API,
            params=params,
            headers=DEFAULT_HEADERS,
            timeout=timeout,
        )
        if resp.status_code != 200:
            logger.warning(f"BSE API returned status {resp.status_code}")
            return []

        data = resp.json()
        table = data.get("Table", [])
        if not isinstance(table, list):
            return []
        return table
    except Exception as e:
        logger.error(f"Error fetching BSE announcements: {e}")
        return []


def process_and_ingest_bse_filings(
    pages: int = 3,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Pulls recent BSE announcements across pages, filters for high-impact Reg 30 events,
    and ingests them into the SQLite database.
    """
    init_reg30_db(db_path=db_path)

    total_scanned = 0
    high_impact_saved = 0
    items_captured: List[Dict[str, Any]] = []

    # Scan standard company updates and board meeting categories
    categories_to_scan = ["Company Update", "Result", "Corp Action"]

    for cat in categories_to_scan:
        for p in range(1, pages + 1):
            raw_items = fetch_bse_announcements(category=cat, page_no=p)
            if not raw_items:
                break

            for raw in raw_items:
                total_scanned += 1
                headline = (raw.get("HEADLINE") or raw.get("NEWSSUB") or "").strip()
                description = (raw.get("MORE") or "").strip()
                scrip_code = str(raw.get("SCRIP_CD") or "").strip()
                company_name = str(raw.get("SLONGNAME") or raw.get("SC_NAME") or "").strip()
                symbol = str(raw.get("SCRIP_CD") or "").strip()
                dt_tm = str(raw.get("NEWS_DT") or raw.get("DT_TM") or datetime.utcnow().isoformat())
                attachment = raw.get("ATTACHMENTNAME") or ""

                pdf_url = f"{BSE_ATTACHMENT_BASE}{attachment}" if attachment else "https://www.bseindia.com"

                # Classify
                classification = classify_reg30_filing(headline, description)
                if classification:
                    item_id = generate_disclosure_id(scrip_code, headline, dt_tm)
                    record = {
                        "id": item_id,
                        "symbol": symbol,
                        "bse_code": scrip_code,
                        "company_name": company_name,
                        "timestamp": dt_tm,
                        "category": classification["category"],
                        "category_name": classification["category_name"],
                        "sentiment": classification["sentiment"],
                        "impact_level": classification["impact_level"],
                        "headline": headline,
                        "description": description,
                        "order_value_cr": classification.get("order_value_cr"),
                        "pdf_url": pdf_url,
                        "source": "BSE",
                    }
                    inserted = insert_reg30_disclosure(record, db_path=db_path)
                    if inserted:
                        high_impact_saved += 1
                    items_captured.append(record)

    return {
        "total_scanned": total_scanned,
        "high_impact_captured": len(items_captured),
        "new_inserted": high_impact_saved,
    }
