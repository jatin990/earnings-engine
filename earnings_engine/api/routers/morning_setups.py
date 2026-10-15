"""
earnings_engine/api/routers/morning_setups.py
FastAPI router for Morning Setups: Block & Bulk Deals Intelligence and Upcoming Board Meetings Radar.
Follows static-route-first precedence, zero-token default, and real data integrity.
"""
from typing import Any, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from earnings_engine.config import Settings
from earnings_engine.data.morning_setups import (
    clean_nse_deal_symbol,
    enrich_grouped_deals_with_live_quotes,
    enrich_tickers_with_technicals,
    get_board_meetings_summary,
    get_morning_block_deals,
    get_morning_deals_summary,
    get_upcoming_board_meetings,
    group_deals_by_symbol,
    sync_all_morning_deals,
    sync_upcoming_board_meetings,
)
from earnings_engine.data.prices import fetch_batch_live_quotes
from earnings_engine.logging_utils import get_logger

logger = get_logger("earnings_engine.api.routers.morning_setups")
router = APIRouter(prefix="/api/v1/morning-setups", tags=["Morning Setups & Catalysts"])
_settings = Settings()


class SyncResponse(BaseModel):
    status: str
    message: str
    details: dict[str, Any] = {}


# ============================================================================
# 1. Block & Bulk Deals Intelligence Endpoints (Static Routes First)
# ============================================================================

@router.get("/deals/summary")
def get_deals_summary_endpoint():
    """Return high-level summary metrics for block and bulk deals."""
    try:
        return get_morning_deals_summary(_settings)
    except Exception as e:
        logger.error("Failed to fetch morning deals summary: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/deals/sync", response_model=SyncResponse)
def trigger_deals_sync_endpoint():
    """Trigger manual on-demand synchronization of block and bulk deals from NSE."""
    try:
        res = sync_all_morning_deals(_settings)
        return SyncResponse(
            status="success",
            message=f"Synced deals successfully: {res.get('total_inserted', 0)} new deals inserted.",
            details=res,
        )
    except Exception as e:
        logger.error("Failed to sync morning deals: %s", e)
        raise HTTPException(status_code=500, detail=f"Sync failed: {e}")


@router.get("/deals")
def list_morning_deals_endpoint(
    deal_date: Optional[str] = Query(None, description="Exact date YYYY-MM-DD"),
    start_date: Optional[str] = Query(None, description="Start date YYYY-MM-DD for date range"),
    end_date: Optional[str] = Query(None, description="End date YYYY-MM-DD for date range"),
    deal_type: Optional[str] = Query(None, description="Filter: 'BLOCK' or 'BULK'"),
    transaction_type: Optional[str] = Query(None, description="Filter: 'BUY' or 'SELL'"),
    ticker: Optional[str] = Query(None, description="Ticker symbol filter, e.g., TRENT"),
    client_name: Optional[str] = Query(None, description="Client or fund name substring"),
    min_value_cr: Optional[float] = Query(None, ge=0.0, description="Minimum deal value in ₹ Crores (e.g., 5.0, 10.0, 50.0)"),
    group_by_symbol: bool = Query(False, description="Group and aggregate deals by symbol"),
    include_technicals: bool = Query(True, description="Enrich with 1D/7D/30D returns and 20/50 DMA"),
    include_live_quotes: bool = Query(True, description="When grouping, merge current/live market prices and vs-VWAP positioning"),
    upcoming_results_only: bool = Query(False, description="Filter deals strictly to tickers with financial results scheduled in next 10 days"),
    limit: int = Query(200, ge=1, le=1000, description="Max records to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
):
    """Query executed block and bulk deals with multi-attribute filtering."""
    try:
        deals = get_morning_block_deals(
            settings=_settings,
            deal_date=deal_date,
            start_date=start_date,
            end_date=end_date,
            deal_type=deal_type,
            transaction_type=transaction_type,
            ticker=ticker,
            client_name=client_name,
            min_value_cr=min_value_cr,
            limit=limit,
            offset=offset,
        )

        # Live quotes and technical indicators enrichment
        technicals: dict[str, Any] = {}
        quotes: dict[str, dict[str, Any]] = {}

        if deals and (include_technicals or (group_by_symbol and include_live_quotes) or upcoming_results_only):
            all_tickers = list(dict.fromkeys([clean_nse_deal_symbol(d.get("ticker")) for d in deals if d.get("ticker")]))
            try:
                quotes = fetch_batch_live_quotes(all_tickers, settings=_settings)
            except Exception as e:
                logger.error("[MORNING-SETUPS] Batch quote fetch failed: %s", e)
                quotes = {}

        if (include_technicals or upcoming_results_only) and deals:
            tickers = [d.get("ticker") for d in deals if d.get("ticker")]
            technicals = enrich_tickers_with_technicals(tickers, settings=_settings, live_quotes=quotes)

        # Filter to upcoming results if requested
        if upcoming_results_only:
            def _has_upcoming(t_sym: str) -> bool:
                c_sym = clean_nse_deal_symbol(t_sym)
                info = technicals.get(c_sym) or technicals.get(t_sym) or {}
                return bool(info.get("upcoming_result", {}).get("has_upcoming_result"))

            deals = [d for d in deals if _has_upcoming(d.get("ticker", ""))]

        if group_by_symbol:
            grouped = group_deals_by_symbol(deals)
            if include_live_quotes:
                grouped = enrich_grouped_deals_with_live_quotes(grouped, settings=_settings, quotes=quotes)
            return {
                "status": "success",
                "count": len(grouped),
                "deals": grouped,
                "grouped": True,
                "technicals": technicals,
                "live_quotes": include_live_quotes,
            }

        return {
            "status": "success",
            "count": len(deals),
            "deals": deals,
            "grouped": False,
            "technicals": technicals,
        }
    except Exception as e:
        logger.error("Failed to query morning deals: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# 2. Upcoming Board Meetings Radar Endpoints (Static Routes First)
# ============================================================================

@router.get("/board-meetings/summary")
def get_board_meetings_summary_endpoint():
    """Return high-level summary metrics and impact tier distribution for board meetings."""
    try:
        return get_board_meetings_summary(_settings)
    except Exception as e:
        logger.error("Failed to fetch board meetings summary: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/board-meetings/sync", response_model=SyncResponse)
def trigger_board_meetings_sync_endpoint(
    days_forward: int = Query(45, ge=7, le=90, description="Days forward to scrape from NSE calendar"),
):
    """Trigger manual on-demand synchronization of upcoming corporate board meetings."""
    try:
        res = sync_upcoming_board_meetings(_settings, days_forward=days_forward)
        return SyncResponse(
            status="success",
            message=f"Synced board meetings successfully: {res.get('inserted_or_updated', 0)} meetings recorded.",
            details=res,
        )
    except Exception as e:
        logger.error("Failed to sync board meetings: %s", e)
        raise HTTPException(status_code=500, detail=f"Sync failed: {e}")


@router.get("/board-meetings")
def list_board_meetings_endpoint(
    ticker: Optional[str] = Query(None, description="Ticker symbol filter, e.g., NYKAA, TRENT"),
    impact_tier: Optional[str] = Query(None, description="Impact tier filter: 'HIGH', 'MEDIUM', 'ROUTINE'"),
    days_ahead: Optional[int] = Query(None, ge=1, le=180, description="Meetings within the next N days"),
    from_date: Optional[str] = Query(None, description="Start date YYYY-MM-DD"),
    to_date: Optional[str] = Query(None, description="End date YYYY-MM-DD"),
    purpose_contains: Optional[str] = Query(None, description="Substring search on purpose (e.g., 'Dividend', 'Results')"),
    include_technicals: bool = Query(True, description="Enrich with 1D/7D/30D returns and 20/50 DMA"),
    limit: int = Query(200, ge=1, le=1000, description="Max records to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
):
    """Query upcoming corporate board meetings with catalyst tiering and horizon filters."""
    try:
        meetings = get_upcoming_board_meetings(
            settings=_settings,
            ticker=ticker,
            impact_tier=impact_tier,
            days_ahead=days_ahead,
            from_date=from_date,
            to_date=to_date,
            purpose_contains=purpose_contains,
            limit=limit,
            offset=offset,
        )

        technicals: dict[str, Any] = {}
        if include_technicals and meetings:
            tickers = [m.get("ticker") for m in meetings if m.get("ticker")]
            technicals = enrich_tickers_with_technicals(tickers, settings=_settings)

        return {
            "status": "success",
            "count": len(meetings),
            "meetings": meetings,
            "technicals": technicals,
        }
    except Exception as e:
        logger.error("Failed to query board meetings: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
