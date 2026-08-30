"""Test suite for TauricResearch TradingAgents Multi-Agent framework."""

import pytest
from fastapi.testclient import TestClient

from earnings_engine.api.server import app
from earnings_engine.config import Settings
from earnings_engine.trading_agents.models import (
    FundamentalAnalystReport,
    TechnicalAnalystReport,
    SentimentAnalystReport,
    BullResearcherReport,
    BearResearcherReport,
    RiskManagerReport,
    TradingAgentsReport,
)
from earnings_engine.trading_agents.storage import (
    save_trading_agents_report,
    get_latest_trading_agents_report,
    get_all_trading_agents_reports,
)
from earnings_engine.trading_agents.workflow import run_trading_agents_workflow

client = TestClient(app)


def test_trading_agents_models_instantiation():
    """Verify all 7 agent models instantiate and serialize to dict cleanly."""
    fa = FundamentalAnalystReport(score=8.5, stance="BULLISH", eps_surprise_streak=4, pe_ratio=24.5)
    ta = TechnicalAnalystReport(score=8.0, stance="BULLISH", trend_posture="UPTREND", current_price=1000.0, support_level=960.0, resistance_level=1080.0)
    sa = SentimentAnalystReport(score=7.5, stance="BULLISH", institutional_verdict="Accumulation", funds_accumulating_count=3)
    bull = BullResearcherReport(conviction_pct=85, target_price=1100.0, target_gain_pct=10.0, core_thesis="Strong growth momentum")
    bear = BearResearcherReport(conviction_pct=25, downside_floor=950.0, downside_risk_pct=5.0, core_thesis="Overhead resistance risk")
    rm = RiskManagerReport(volatility_risk="LOW", stop_loss_price=950.0, max_downside_pct=5.0, risk_reward_ratio=2.0)

    report = TradingAgentsReport(
        ticker="TEST.NS",
        company_name="Test Corp",
        current_price=1000.0,
        action="STRONG_BUY",
        conviction_score=85,
        target_price=1100.0,
        target_return_pct=10.0,
        stop_loss_price=950.0,
        risk_reward_ratio=2.0,
        fundamental_analyst=fa,
        technical_analyst=ta,
        sentiment_analyst=sa,
        bull_researcher=bull,
        bear_researcher=bear,
        risk_manager=rm,
    )

    d = report.to_dict()
    assert d["ticker"] == "TEST.NS"
    assert d["action"] == "STRONG_BUY"
    assert d["conviction_score"] == 85
    assert d["target_price"] == 1100.0
    assert d["fundamental_analyst"]["score"] == 8.5
    assert d["technical_analyst"]["score"] == 8.0
    assert d["sentiment_analyst"]["score"] == 7.5
    assert d["risk_manager"]["risk_reward_ratio"] == 2.0


def test_trading_agents_storage_and_retrieval():
    """Test saving and retrieving TradingAgents reports from SQLite."""
    settings = Settings()

    report = TradingAgentsReport(
        ticker="TATAMOTORS.NS",
        company_name="Tata Motors Ltd",
        current_price=950.0,
        action="BUY",
        conviction_score=78,
        target_price=1050.0,
        target_return_pct=10.5,
        stop_loss_price=900.0,
        risk_reward_ratio=2.0,
        executive_summary="Solid turnaround fundamentals and breakout momentum.",
    )

    saved = save_trading_agents_report(report, settings=settings)
    assert saved is True

    fetched = get_latest_trading_agents_report("TATAMOTORS.NS", settings=settings)
    assert fetched is not None
    assert fetched["ticker"] == "TATAMOTORS.NS"
    assert fetched["action"] == "BUY"
    assert fetched["conviction_score"] == 78

    all_reports = get_all_trading_agents_reports(limit=10, settings=settings)
    assert len(all_reports) >= 1
    assert any(r["ticker"] == "TATAMOTORS.NS" for r in all_reports)


def test_trading_agents_workflow_execution():
    """Test running full 7-agent workflow on a ticker."""
    settings = Settings()
    report = run_trading_agents_workflow(ticker="INFY.NS", timeframe_days=14, settings=settings, persist=False)

    assert report.ticker == "INFY.NS"
    assert report.action in ("STRONG_BUY", "BUY", "HOLD", "SELL", "STRONG_SELL")
    assert 0 <= report.conviction_score <= 100
    assert report.fundamental_analyst.score >= 1.0
    assert report.technical_analyst.score >= 1.0
    assert report.sentiment_analyst.score >= 1.0
    assert report.bull_researcher.target_price > 0
    assert report.risk_manager.stop_loss_price > 0
    assert report.risk_reward_ratio >= 1.5


def test_trading_agents_api_endpoints():
    """Verify FastAPI routes for TradingAgents multi-agent framework."""
    # 1. Status metadata endpoint
    status_resp = client.get("/api/v1/trading-agents/status")
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data["success"] is True
    assert status_data["agents_count"] == 7
    assert len(status_data["agents"]) == 7

    # 2. Analyze endpoint
    analyze_resp = client.post(
        "/api/v1/trading-agents/analyze",
        json={"ticker": "TCS.NS", "timeframe_days": 14, "force_refresh": True},
    )
    assert analyze_resp.status_code == 200
    data = analyze_resp.json()
    assert data["success"] is True
    assert "report" in data
    assert data["report"]["ticker"] == "TCS.NS"
    assert "fundamental_analyst" in data["report"]
    assert "bull_researcher" in data["report"]
    assert "bear_researcher" in data["report"]
    assert "risk_manager" in data["report"]

    # 3. Report retrieval endpoint
    report_resp = client.get("/api/v1/trading-agents/report/TCS.NS")
    assert report_resp.status_code == 200
    rep_data = report_resp.json()
    assert rep_data["success"] is True
    assert rep_data["report"]["ticker"] == "TCS.NS"

    # 4. All reports list endpoint
    all_resp = client.get("/api/v1/trading-agents/all?limit=10")
    assert all_resp.status_code == 200
    all_data = all_resp.json()
    assert all_data["success"] is True
    assert "reports" in all_data
