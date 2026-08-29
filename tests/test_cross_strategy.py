"""Test suite for cross-strategy confluence & news intelligence."""

import pytest
from earnings_engine.config import Settings
from earnings_engine.data.cross_strategy import (
    get_market_macro_summary,
    get_stock_news_sentiment,
    get_stock_confluence,
)
from earnings_engine.data.db import get_db_connection
from earnings_engine.consensus.storage import _ensure_table
from earnings_engine.data.catalysts_news import _connect as _ensure_catalysts_table


@pytest.fixture
def temp_settings(tmp_path):
    s = Settings()
    s.data_dirs["prices"] = tmp_path
    s.ensure_dirs()
    from earnings_engine.data.migrations import apply_migrations
    apply_migrations(s)
    return s


def test_market_macro_summary(temp_settings):
    macro = get_market_macro_summary(temp_settings)
    assert "fear_greed_score" in macro
    assert "vix_level" in macro
    assert "macro_badge" in macro


def test_stock_news_sentiment(temp_settings):
    ticker = "TCS.NS"
    _ensure_catalysts_table(temp_settings)
    conn = get_db_connection(temp_settings)
    conn.execute(
        """
        INSERT INTO news_catalysts (
            ticker, title, impact_score, category, direction, published_at,
            created_at, expected_horizon, volatility_est, impact_level
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ticker,
            "TCS wins $1.5B multi-year cloud transformation deal",
            85,
            "Order Win",
            "BULLISH",
            "2026-08-28 10:00:00",
            "2026-08-28 10:00:00",
            "📅 3-5 Days",
            "±2% to ±4%",
            "HIGH",
        ),
    )
    conn.commit()

    res = get_stock_news_sentiment(ticker, temp_settings)
    assert res["has_news"] is True
    assert res["sentiment_score"] == 0.85
    assert "Order Win" in res["badge_text"]


def test_stock_confluence_evaluation(temp_settings):
    ticker = "INFY.NS"
    conn = get_db_connection(temp_settings)
    _ensure_table(conn)

    # Insert AI Consensus prediction
    conn.execute(
        """
        INSERT INTO consensus_predictions (
            ticker, consensus_direction, consensus_strength, consensus_return_pct,
            consensus_target_price, created_at, evaluation_date, as_of_price,
            model_count, agreement_ratio, models_breakdown_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ticker,
            "STRONG BUY",
            88,
            4.5,
            1950.0,
            "2026-08-28 12:00:00",
            "2026-08-28",
            1860.0,
            4,
            1.0,
            "{}",
        ),
    )
    conn.commit()

    # Case 1: Dual Confluence (Swing Buy + Breakout)
    c_dual = get_stock_confluence(
        ticker,
        temp_settings,
        current_swing_item={"tier": "HOT", "swing_signal": "Buy Zone", "dist_to_support_pct": 1.2},
        current_breakout_item={"tier": "HOT", "breakout_score": 85},
    )
    assert c_dual["confluence_level"] == 3  # Triple because AI Consensus is also STRONG BUY!
    assert "TRIPLE" in c_dual["confluence_badge"]

    # Case 2: Swing Buy alone with AI
    c_ai_swing = get_stock_confluence(
        ticker,
        temp_settings,
        current_swing_item={"tier": "HOT", "swing_signal": "Buy Zone", "dist_to_support_pct": 1.5},
        current_breakout_item={"tier": "COLD"},
    )
    assert c_ai_swing["confluence_level"] == 2
    assert "AI SWING" in c_ai_swing["confluence_badge"]
