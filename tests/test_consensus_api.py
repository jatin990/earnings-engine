"""Unit and integration tests for OmniRoute direct analysis API endpoints."""

from __future__ import annotations

import json
from unittest.mock import patch
import pytest
from starlette.testclient import TestClient

from earnings_engine.api.server import app


@pytest.fixture
def client():
    return TestClient(app)


def test_get_consensus_models_catalog(client):
    """Test GET /api/v1/consensus/models returns the curated CCR / OmniRoute models with status 200."""
    res = client.get("/api/v1/consensus/models")
    assert res.status_code == 200
    data = res.json()
    assert "models" in data
    assert "count" in data
    assert data["count"] == 5
    assert len(data["models"]) == 5

    model_ids = [m["id"] for m in data["models"]]
    assert "antigravityonly" in model_ids
    assert "antigravity" in model_ids
    assert "Smart Coding" in model_ids
    assert "free only" in model_ids
    assert "auto/best-free" in model_ids


def test_post_consensus_analyze_success(client):
    """Test POST /api/v1/consensus/analyze with valid JSON output returns structured verdict and raw telemetry."""
    mock_llm_json = {
        "direction": "BULLISH",
        "conviction_score": 85,
        "target_price": 2850.0,
        "stop_loss": 2650.0,
        "risk_reward_ratio": 2.5,
        "catalyst_summary": "Order win catalysts and margin expansion",
        "thesis": "Consolidating near swing support floor with positive institutional accumulation.",
        "key_risks": ["Crude price volatility", "Broad market correction"],
    }
    raw_markdown = f"Here is the quantitative deliberation:\n`json\n{json.dumps(mock_llm_json, indent=2)}\n`"

    mock_execution_result = {
        "status": "success",
        "raw_text": raw_markdown,
        "reasoning_text": "Examining 14-day swing support and RSI momentum levels...",
        "tokens_used": 642,
        "latency_ms": 1150.4,
        "error": None,
    }

    with patch("earnings_engine.data.omniroute_client.execute_omniroute_analysis", return_value=mock_execution_result):
        payload = {
            "ticker": "RELIANCE.NS",
            "model": "antigravityonly",
            "timeframe_days": 14,
            "include_technicals": True,
            "include_news": True,
            "include_institutional": True,
            "custom_prompt": "Evaluate potential margin upside for next earnings.",
            "temperature": 0.2,
        }
        res = client.post("/api/v1/consensus/analyze", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["ticker"] == "RELIANCE.NS"
        assert data["model"] == "antigravityonly"
        assert data["structured"]["direction"] == "BULLISH"
        assert data["structured"]["conviction_score"] == 85
        assert data["structured"]["target_price"] == 2850.0
        assert data["latency_ms"] == 1150.4
        assert data["tokens_used"] == 642
        assert "reasoning_text" in data


def test_post_consensus_analyze_unparseable_json_fallback(client):
    """Test POST /api/v1/consensus/analyze handles unstructured narrative output gracefully."""
    raw_markdown = "The stock looks poised for an upside breakout above 2850 given current volume surge."
    mock_execution_result = {
        "status": "success",
        "raw_text": raw_markdown,
        "reasoning_text": "",
        "tokens_used": 210,
        "latency_ms": 980.0,
        "error": None,
    }

    with patch("earnings_engine.data.omniroute_client.execute_omniroute_analysis", return_value=mock_execution_result):
        payload = {
            "ticker": "TCS.NS",
            "model": "free only",
            "timeframe_days": 7,
        }
        res = client.post("/api/v1/consensus/analyze", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["ticker"] == "TCS.NS"
        assert data["structured"]["direction"] == "UNKNOWN"
        assert data["raw_text"] == raw_markdown


def test_post_consensus_analyze_gateway_error(client):
    """Test POST /api/v1/consensus/analyze reports downstream gateway failure cleanly."""
    mock_execution_result = {
        "status": "error",
        "raw_text": "",
        "reasoning_text": "",
        "tokens_used": 0,
        "latency_ms": 2500.0,
        "error": "OmniRoute daemon unreachable on port 20128.",
    }

    with patch("earnings_engine.data.omniroute_client.execute_omniroute_analysis", return_value=mock_execution_result):
        payload = {
            "ticker": "INFY.NS",
            "model": "Smart Coding",
            "timeframe_days": 14,
        }
        res = client.post("/api/v1/consensus/analyze", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "error"
        assert data["error"] == "OmniRoute daemon unreachable on port 20128."
