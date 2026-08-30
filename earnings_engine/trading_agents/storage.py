"""Database persistence and retrieval for TradingAgents reports.

Stores complete TradingAgents reports into SQLite and Turso with
composite indexing and fast JSON retrieval.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection
from earnings_engine.logging_utils import get_logger
from earnings_engine.trading_agents.models import (
    TradingAgentsReport,
    FundamentalAnalystReport,
    TechnicalAnalystReport,
    SentimentAnalystReport,
    BullResearcherReport,
    BearResearcherReport,
    RiskManagerReport,
)

logger = get_logger("earnings_engine.trading_agents.storage")


def init_trading_agents_db(conn: Any) -> None:
    """Ensure trading_agents_reports table and indices exist."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS trading_agents_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            company_name TEXT,
            industry TEXT,
            asof_date TEXT,
            timeframe_days INTEGER DEFAULT 14,
            current_price REAL,
            action TEXT DEFAULT 'HOLD',
            direction TEXT DEFAULT 'NEUTRAL',
            conviction_score INTEGER DEFAULT 50,
            target_price REAL,
            target_return_pct REAL,
            stop_loss_price REAL,
            risk_reward_ratio REAL,
            execution_timing TEXT,
            executive_summary TEXT,
            fundamental_score REAL,
            technical_score REAL,
            sentiment_score REAL,
            data_json TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )
        """
    )
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_trading_agents_ticker ON trading_agents_reports(ticker, created_at DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_trading_agents_action ON trading_agents_reports(action)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_trading_agents_score ON trading_agents_reports(conviction_score DESC)")
    except Exception:
        pass


def save_trading_agents_report(report: TradingAgentsReport, settings: Settings | None = None) -> bool:
    """Save a TradingAgentsReport into database."""
    settings = settings or Settings()
    try:
        conn = get_db_connection(settings)
        init_trading_agents_db(conn)

        rep_dict = report.to_dict()
        now_iso = datetime.now(timezone.utc).isoformat()

        conn.execute(
            """
            INSERT INTO trading_agents_reports (
                ticker, company_name, industry, asof_date, timeframe_days,
                current_price, action, direction, conviction_score,
                target_price, target_return_pct, stop_loss_price, risk_reward_ratio,
                execution_timing, executive_summary, fundamental_score, technical_score,
                sentiment_score, data_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report.ticker,
                report.company_name,
                report.industry,
                report.asof_date,
                report.timeframe_days,
                report.current_price,
                report.action,
                report.direction,
                report.conviction_score,
                report.target_price,
                report.target_return_pct,
                report.stop_loss_price,
                report.risk_reward_ratio,
                report.execution_timing,
                report.executive_summary,
                report.fundamental_analyst.score,
                report.technical_analyst.score,
                report.sentiment_analyst.score,
                json.dumps(rep_dict),
                now_iso,
                now_iso,
            ),
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error("[TRADING-AGENTS] Failed to save report for %s: %s", report.ticker, e)
        return False


def get_latest_trading_agents_report(ticker: str, settings: Settings | None = None) -> dict[str, Any] | None:
    """Retrieve the most recent TradingAgents report for a ticker."""
    settings = settings or Settings()
    sym = ticker.strip().upper()
    try:
        conn = get_db_connection(settings)
        init_trading_agents_db(conn)

        row = conn.execute(
            """
            SELECT data_json, created_at FROM trading_agents_reports
            WHERE ticker = ? ORDER BY id DESC LIMIT 1
            """,
            (sym,),
        ).fetchone()
        conn.close()

        if row and row[0]:
            data = json.loads(row[0])
            data["stored_at"] = row[1]
            return data
    except Exception as e:
        logger.debug("[TRADING-AGENTS] Error loading report for %s: %s", sym, e)
    return None


def get_all_trading_agents_reports(limit: int = 100, settings: Settings | None = None) -> list[dict[str, Any]]:
    """Retrieve the latest TradingAgents report across all distinct tickers."""
    settings = settings or Settings()
    reports: list[dict[str, Any]] = []
    try:
        conn = get_db_connection(settings)
        init_trading_agents_db(conn)

        rows = conn.execute(
            """
            SELECT data_json, created_at FROM trading_agents_reports
            WHERE id IN (
                SELECT MAX(id) FROM trading_agents_reports GROUP BY ticker
            )
            ORDER BY conviction_score DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
        conn.close()

        for r in rows:
            if r and r[0]:
                data = json.loads(r[0])
                data["stored_at"] = r[1]
                reports.append(data)
    except Exception as e:
        logger.debug("[TRADING-AGENTS] Error loading all reports: %s", e)
    return reports
