"""
earnings_engine/api/routers/deals.py
FastAPI router for block deals and institutional flow intelligence.
"""
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from earnings_engine.config import Settings
from earnings_engine.data.db import _cache_path
from earnings_engine.services.deals_service import (
    get_institutional_inflow_metrics,
    get_stock_block_deals,
)

router = APIRouter(prefix="/api/deals", tags=["Deals & Institutional Flows"])
_settings = Settings()


def _get_active_db_path() -> str:
    return str(_cache_path(_settings))


# 1. Static / Literal Route First
@router.get("/inflow/summary")
def get_inflow_summary(
    symbol: str = Query(..., description="Stock symbol, e.g., RELIANCE or RELIANCE.NS"),
    horizon_days: int = Query(30, description="Window horizon in days (e.g., 30, 90)"),
    asof_date: Optional[str] = Query(None, description="Point-in-time date boundary (YYYY-MM-DD)"),
):
    try:
        return get_institutional_inflow_metrics(
            db_path=_get_active_db_path(),
            symbol=symbol,
            asof_date=asof_date,
            horizon_days=horizon_days,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# 2. Parameterized Route
@router.get("/{symbol}")
def get_deals_by_symbol(
    symbol: str,
    asof_date: Optional[str] = Query(None, description="Point-in-time date boundary (YYYY-MM-DD)"),
    horizon_days: int = Query(30, description="Inflow calculation window in days"),
    limit: int = Query(50, le=200, description="Max number of deals to return"),
):
    try:
        deals = get_stock_block_deals(
            db_path=_get_active_db_path(),
            symbol=symbol,
            asof_date=asof_date,
            limit=limit,
        )
        inflow = get_institutional_inflow_metrics(
            db_path=_get_active_db_path(),
            symbol=symbol,
            asof_date=asof_date,
            horizon_days=horizon_days,
        )
        return {
            "symbol": symbol,
            "asof_date": asof_date,
            "inflow_metrics": inflow,
            "deals_count": len(deals),
            "deals": deals,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
