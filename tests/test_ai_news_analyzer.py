"""Unit tests for OmniRouter AI News Analysis & Heuristic Fallback Engine."""

import json
import pytest
import sqlite3
from unittest.mock import MagicMock, patch

from earnings_engine.config import Settings
from earnings_engine.data.ai_news_analyzer import (
    analyze_news_catalyst_ai,
    build_news_analysis_prompt,
    get_omnirouter_endpoint,
    get_omnirouter_api_key,
    _heuristic_fallback_analysis,
)
from earnings_engine.data.news_pipeline import process_and_verify_news_items, save_verified_news_records
from earnings_engine.data.catalysts_news import _connect


def test_build_news_analysis_prompt():
    item = {
        "ticker": "TCS.NS",
        "stock_name": "Tata Consultancy Services Ltd",
        "title": "TCS wins $1.2B AI infrastructure modernization deal with UK bank",
        "summary": "Multi-year deal to transform core banking operations using GenAI",
        "signal_price": 4200.0,
        "current_price": 4280.0,
        "published_at": "2026-08-28 09:15:00",
        "verified_numbers": {"order_value_usd_m": 1200.0, "currency": "USD"},
    }
    prompt = build_news_analysis_prompt(item)
    assert "TCS.NS" in prompt
    assert "Tata Consultancy Services" in prompt
    assert "4200.00" in prompt
    assert "1200.0" in prompt


def test_omnirouter_config_resolution(monkeypatch):
    monkeypatch.setenv("OMNIROUTER_API_URL", "https://custom.omnirouter.internal/v1")
    monkeypatch.setenv("OMNIROUTER_API_KEY", "omni_test_key_123")

    assert get_omnirouter_endpoint() == "https://custom.omnirouter.internal/v1/chat/completions"
    assert get_omnirouter_api_key() == "omni_test_key_123"


def test_omnirouter_mock_response():
    mock_resp_payload = {
        "choices": [{
            "message": {
                "content": json.dumps({
                    "direction": "BULLISH",
                    "impact_score": 88,
                    "impact_level": "HIGH",
                    "expected_horizon": "📅 1-3 Days",
                    "volatility_est": "±3% to ±7%",
                    "trading_takeaway": "Large-scale cloud modernization deal guarantees multi-quarter revenue visibility.",
                    "target_price": 4450.0,
                    "stop_loss": 4120.0,
                    "confidence_pct": 90,
                    "key_catalyst_triggers": ["$1.2B revenue accretion", "Tier-1 banking client"],
                    "primary_risk": "Currency fluctuations",
                })
            }
        }]
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_resp_payload

    with patch("requests.post", return_value=mock_resp):
        item = {
            "ticker": "TCS.NS",
            "stock_name": "Tata Consultancy Services",
            "title": "TCS wins $1.2B deal",
            "signal_price": 4200.0,
        }
        res = analyze_news_catalyst_ai(item, preferred_model="deepseek/deepseek-r1")
        assert res["direction"] == "BULLISH"
        assert res["impact_score"] == 88
        assert res["target_price"] == 4450.0
        assert "omnirout" in res["ai_model"]


def test_heuristic_fallback_analysis():
    # Bullish order win
    item_bull = {
        "ticker": "LT.NS",
        "title": "Larsen & Toubro bags contract for Rs 4,500 crore high-speed rail project",
        "summary": "Major infrastructure project awarded by NHSRCL",
        "signal_price": 3600.0,
    }
    res_bull = _heuristic_fallback_analysis(item_bull)
    assert res_bull["direction"] == "BULLISH"
    assert res_bull["impact_score"] >= 70
    assert res_bull["target_price"] > 3600.0
    assert res_bull["stop_loss"] < 3600.0
    assert res_bull["confidence_pct"] >= 70

    # Bearish profit drop
    item_bear = {
        "ticker": "ABC.NS",
        "title": "Company Q1 net profit plunges 60% on raw material spike",
        "summary": "Operating margin compresses severely",
        "signal_price": 500.0,
    }
    res_bear = _heuristic_fallback_analysis(item_bear)
    assert res_bear["direction"] == "BEARISH"
    assert res_bear["target_price"] < 500.0
    assert res_bear["stop_loss"] > 500.0


def test_news_injection_stores_omnirouter_ai_analysis(tmp_path):
    settings = Settings()
    settings.data_dirs = {"prices": tmp_path / "prices", "earnings": tmp_path / "earnings"}
    settings.ensure_dirs()

    with _connect(settings) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS price_history (
                ticker TEXT NOT NULL,
                date TEXT NOT NULL,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume REAL,
                PRIMARY KEY (ticker, date)
            )
        """)
        conn.execute("INSERT OR REPLACE INTO price_history VALUES ('PERSISTENT.NS', '2026-08-27', 5640.0, 5679.5, 5597.0, 5654.0, 191424)")
        conn.execute("INSERT OR REPLACE INTO price_history VALUES ('PERSISTENT.NS', '2026-08-28', 5677.0, 5910.0, 5677.0, 5875.0, 957631)")
        conn.commit()

    raw_items = [{
        "ticker": "PERSISTENT.NS",
        "title": "Persistent Systems expands digital engineering pact with US healthcare giant - Moneycontrol",
        "summary": "Strategic multi-year cloud transformation partnership expansion",
        "published_at": "2026-08-28 02:00:00",
        "publisher": "Moneycontrol",
    }]

    verified = process_and_verify_news_items(raw_items, settings=settings)
    assert len(verified) == 1
    v = verified[0]

    # Verify AI analysis fields were populated
    assert v["ai_analysis"] is not None
    assert v["ai_takeaway"] is not None
    assert v["ai_direction"] in ("BULLISH", "BEARISH", "NEUTRAL")
    assert v["signal_price"] == 5654.0
    assert v["current_price"] == 5875.0
    assert v["price_change_pct"] == 3.91
    assert v["ai_target"] is not None
    assert v["ai_target"] > 5654.0

    # Save to SQLite and check schema columns
    save_cnt = save_verified_news_records(verified, settings=settings)
    assert save_cnt == 1

    with _connect(settings) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM news_catalysts WHERE ticker = 'PERSISTENT.NS'").fetchone()
        assert row is not None
        assert row["ai_analysis"] is not None
        assert row["ai_takeaway"] is not None
        assert row["ai_direction"] == "BULLISH"
        assert row["signal_price"] == 5654.0
        assert row["current_price"] == 5875.0
        assert row["price_change_pct"] == 3.91
