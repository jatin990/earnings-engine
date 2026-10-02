"""
FastAPI routes for the Unified High-Impact Reg 30 Disclosures Stream.
"""

from fastapi import APIRouter, Query, BackgroundTasks, HTTPException
from typing import Optional, List, Dict, Any

from earnings_engine.db.reg30_storage import fetch_reg30_stream, fetch_reg30_stats
from earnings_engine.scrapers.bse_reg30_scraper import process_and_ingest_bse_filings

router = APIRouter(prefix="/api/reg30", tags=["Reg 30 Stream"])


@router.get("/stream")
def get_reg30_stream(
    category: Optional[str] = Query(None, description="ORDER_WIN, AUDITOR_RESIGN, RATING_DOWNGRADE, CAPEX_COD, etc."),
    sentiment: Optional[str] = Query(None, description="BULLISH, BEARISH, NEUTRAL"),
    impact: Optional[str] = Query(None, description="CRITICAL, HIGH, MEDIUM"),
    symbol: Optional[str] = Query(None, description="Filter by ticker or company name"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> Dict[str, Any]:
    """
    Returns the real-time unified stream of high-impact Reg 30 disclosures.
    """
    disclosures = fetch_reg30_stream(
        category=category,
        sentiment=sentiment,
        impact_level=impact,
        symbol=symbol,
        limit=limit,
        offset=offset,
    )
    return {
        "status": "success",
        "count": len(disclosures),
        "limit": limit,
        "offset": offset,
        "disclosures": disclosures,
    }


@router.get("/stats")
def get_reg30_stats() -> Dict[str, Any]:
    """
    Returns aggregate metrics: breakdown by sentiment and high-impact category.
    """
    stats = fetch_reg30_stats()
    return {
        "status": "success",
        "data": stats,
    }


@router.post("/refresh")
def trigger_reg30_refresh(
    background_tasks: BackgroundTasks,
    pages: int = Query(3, ge=1, le=10, description="Number of BSE pages to scan"),
) -> Dict[str, Any]:
    """
    Triggers background ingestion worker to poll latest filings from BSE and classify them.
    """
    background_tasks.add_task(process_and_ingest_bse_filings, pages=pages)
    return {
        "status": "queued",
        "message": f"Scanning latest {pages} pages of BSE corporate announcements for high-impact Reg 30 filings in the background.",
    }
