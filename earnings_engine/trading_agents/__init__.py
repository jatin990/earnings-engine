"""TauricResearch TradingAgents Multi-Agent Financial Trading Suite.

Simulates a collaborative 7-agent trading firm with specialized roles:
- Fundamental Analyst
- Technical Analyst
- Sentiment & News Analyst
- Bullish Researcher
- Bearish Researcher
- Risk & Portfolio Manager
- Head Trader Execution Engine
"""

from __future__ import annotations

from earnings_engine.trading_agents.models import (
    FundamentalAnalystReport,
    TechnicalAnalystReport,
    SentimentAnalystReport,
    BullResearcherReport,
    BearResearcherReport,
    RiskManagerReport,
    TradingAgentsReport,
)
from earnings_engine.trading_agents.workflow import run_trading_agents_workflow
from earnings_engine.trading_agents.storage import (
    save_trading_agents_report,
    get_latest_trading_agents_report,
    get_all_trading_agents_reports,
)

__all__ = [
    "FundamentalAnalystReport",
    "TechnicalAnalystReport",
    "SentimentAnalystReport",
    "BullResearcherReport",
    "BearResearcherReport",
    "RiskManagerReport",
    "TradingAgentsReport",
    "run_trading_agents_workflow",
    "save_trading_agents_report",
    "get_latest_trading_agents_report",
    "get_all_trading_agents_reports",
]
