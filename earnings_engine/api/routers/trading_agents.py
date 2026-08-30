"""FastAPI Router for TauricResearch TradingAgents Multi-Agent Workflow."""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException, Query

from earnings_engine.api.dependencies import _settings
from earnings_engine.logging_utils import get_logger
from earnings_engine.trading_agents.workflow import run_trading_agents_workflow
from earnings_engine.trading_agents.storage import (
    get_latest_trading_agents_report,
    get_all_trading_agents_reports,
)

logger = get_logger("earnings_engine.api.routers.trading_agents")

router = APIRouter(prefix="/api/v1/trading-agents", tags=["TradingAgents Multi-Agent Suite"])


class TradingAgentsAnalyzeRequest(BaseModel):
    """Request payload to trigger on-demand TradingAgents analysis."""
    ticker: str = Field(..., description="Stock ticker symbol (e.g., RELIANCE.NS, TCS.NS, NVDA)")
    timeframe_days: int = Field(14, description="Forecast & analysis trading horizon in days")
    force_refresh: bool = Field(False, description="Bypass cache and force full 7-agent re-run")


@router.post("/analyze")
def analyze_stock_with_trading_agents(
    req: TradingAgentsAnalyzeRequest,
) -> dict[str, Any]:
    """Execute the full 7-agent TradingAgents workflow for a single stock."""
    ticker = req.ticker.strip().upper()
    if not ticker:
        raise HTTPException(status_code=400, detail="Ticker symbol is required.")

    # Check cache unless force_refresh requested
    if not req.force_refresh:
        cached = get_latest_trading_agents_report(ticker, settings=_settings)
        if cached:
            return {"success": True, "cached": True, "report": cached}

    try:
        report = run_trading_agents_workflow(
            ticker=ticker,
            timeframe_days=req.timeframe_days,
            settings=_settings,
            persist=True,
        )
        return {"success": True, "cached": False, "report": report.to_dict()}
    except Exception as e:
        logger.error("[TRADING-AGENTS-API] Failed analyzing %s: %s", ticker, e)
        raise HTTPException(status_code=500, detail=f"TradingAgents execution failed: {e}")


@router.get("/report/{ticker}")
def get_stock_trading_agents_report(
    ticker: str,
) -> dict[str, Any]:
    """Retrieve the latest cached TradingAgents multi-agent report for a ticker."""
    sym = ticker.strip().upper()
    report = get_latest_trading_agents_report(sym, settings=_settings)
    if not report:
        # Generate on-demand if missing
        try:
            rep_obj = run_trading_agents_workflow(ticker=sym, settings=_settings, persist=True)
            report = rep_obj.to_dict()
        except Exception as e:
            logger.warning("[TRADING-AGENTS-API] On-demand fallback failed for %s: %s", sym, e)
            raise HTTPException(status_code=404, detail=f"No TradingAgents report found for {sym}")

    return {"success": True, "report": report}


@router.get("/all")
def get_all_reports(
    limit: int = Query(50, ge=1, le=500),
) -> dict[str, Any]:
    """Retrieve all latest TradingAgents reports across monitored universe."""
    reports = get_all_trading_agents_reports(limit=limit, settings=_settings)
    return {
        "success": True,
        "count": len(reports),
        "reports": reports,
    }


@router.get("/status")
def get_trading_agents_status() -> dict[str, Any]:
    """Return framework metadata, agents architecture, and capabilities."""
    return {
        "success": True,
        "framework": "TauricResearch/TradingAgents",
        "agents_count": 7,
        "agents": [
            {"id": "fundamental_analyst", "name": "Fundamental Analyst", "icon": "📊", "role": "Financial quality, valuation multiples & EPS surprises"},
            {"id": "technical_analyst", "name": "Technical Analyst", "icon": "📈", "role": "Trend, support/resistance, RSI, MACD & volume"},
            {"id": "sentiment_analyst", "name": "Sentiment & News Analyst", "icon": "📰", "role": "News catalysts, institutional flows & macro regime"},
            {"id": "bull_researcher", "name": "Bullish Researcher", "icon": "🐂", "role": "Upside thesis, growth drivers & target targets"},
            {"id": "bear_researcher", "name": "Bearish Researcher", "icon": "🐻", "role": "Downside risks, failure modes & breakdown levels"},
            {"id": "risk_manager", "name": "Risk & Portfolio Manager", "icon": "🛡️", "role": "Volatility risk, stop loss placement & position sizing"},
            {"id": "head_trader", "name": "Head Trader Execution", "icon": "🏛️", "role": "Executive trade synthesis, conviction & execution timing"},
        ],
    }
