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
    """Test GET /api/v1/consensus/models returns the 4 Claude Code OmniRoute models with status 200."""
    res = client.get("/api/v1/consensus/models")
    assert res.status_code == 200
    data = res.json()
    assert "models" in data
    assert "count" in data
    assert data["count"] == 4
    assert len(data["models"]) == 4

    model_ids = [m["id"] for m in data["models"]]
    assert "claude only" in model_ids
    assert "antigravityonly" in model_ids
    assert "free only" in model_ids
    assert "auto/smart" in model_ids


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
    raw_markdown = f"Here is the quantitative deliberation:\n```json\n{json.dumps(mock_llm_json, indent=2)}\n```"

    mock_execution_result = {
        "status": "success",
        "raw_text": raw_markdown,
        "reasoning_text": "Examining 14-day swing support and RSI momentum levels...",
        "tokens_used": 642,
        "latency_ms": 1250.5,
        "model_used": "antigravityonly",
    }

    mock_prompts = (
        "You are an elite quantitative analyst...",
        "Analyze TCS.NS based on the provided technical and catalyst context...",
        {"ticker": "TCS.NS"},
    )

    with patch(
        "earnings_engine.consensus.context_builder.build_customized_prompt",
        return_value=mock_prompts,
    ) as mock_builder, patch(
        "earnings_engine.data.omniroute_client.execute_omniroute_analysis",
        return_value=mock_execution_result,
    ) as mock_runner:
        payload = {
            "ticker": "TCS.NS",
            "model": "antigravityonly",
            "timeframe_days": 14,
            "include_technicals": True,
            "include_news": True,
            "include_institutional": True,
            "custom_prompt": "Evaluate support breakdown risk",
            "temperature": 0.2,
        }
        res = client.post("/api/v1/consensus/analyze", json=payload)
        assert res.status_code == 200
        data = res.json()

        # Check top-level contract
        assert data["ticker"] == "TCS.NS"
        assert data["model"] == "antigravityonly"
        assert data["status"] == "success"
        assert data["error"] is None
        assert data["latency_ms"] == 1250.5
        assert data["tokens_used"] == 642
        assert data["raw_text"] == raw_markdown
        assert data["reasoning_text"] == "Examining 14-day swing support and RSI momentum levels..."
        assert "--- SYSTEM PROMPT ---" in data["prompt_sent"]
        assert "--- USER PROMPT ---" in data["prompt_sent"]

        # Check structured parsed JSON
        structured = data["structured"]
        assert structured["direction"] == "BULLISH"
        assert structured["conviction_score"] == 85
        assert structured["target_price"] == 2850.0
        assert structured["stop_loss"] == 2650.0
        assert structured["risk_reward_ratio"] == 2.5
        assert structured["catalyst_summary"] == "Order win catalysts and margin expansion"
        assert structured["key_risks"] == ["Crude price volatility", "Broad market correction"]

        mock_builder.assert_called_once_with(
            ticker="TCS.NS",
            timeframe_days=14,
            include_technicals=True,
            include_news=True,
            include_institutional=True,
            custom_directives="Evaluate support breakdown risk",
            settings=pytest.approx(mock_builder.call_args.kwargs["settings"]) if "settings" in mock_builder.call_args.kwargs else None,
        ) if "settings" in mock_builder.call_args.kwargs else mock_builder.assert_called_once()
        mock_runner.assert_called_once_with(
            model="antigravityonly",
            system_prompt="You are an elite quantitative analyst...",
            user_prompt="Analyze TCS.NS based on the provided technical and catalyst context...",
            temperature=0.2,
        )


def test_post_consensus_analyze_unparseable_json_fallback(client):
    """Test fallback when LLM emits unparseable non-JSON text."""
    non_json_text = "I recommend BUYING this equity immediately due to breakout potential."
    mock_execution_result = {
        "status": "success",
        "raw_text": non_json_text,
        "reasoning_text": "Thinking through options...",
        "tokens_used": 150,
        "latency_ms": 450.0,
        "model_used": "free only",
    }
    mock_prompts = ("Sys prompt", "User prompt", {})

    with patch(
        "earnings_engine.consensus.context_builder.build_customized_prompt",
        return_value=mock_prompts,
    ), patch(
        "earnings_engine.data.omniroute_client.execute_omniroute_analysis",
        return_value=mock_execution_result,
    ):
        payload = {
            "ticker": "INFY.NS",
            "model": "free only",
            "timeframe_days": 7,
            "include_technicals": True,
            "include_news": False,
            "include_institutional": False,
        }
        res = client.post("/api/v1/consensus/analyze", json=payload)
        assert res.status_code == 200
        data = res.json()

        assert data["ticker"] == "INFY.NS"
        assert data["model"] == "free only"
        assert data["status"] == "success"
        assert data["raw_text"] == non_json_text
        assert data["structured"]["direction"] == "UNKNOWN"
        assert data["structured"]["thesis"] == non_json_text


def test_post_consensus_analyze_gateway_error(client):
    """Test handling of gateway error status from execute_omniroute_analysis."""
    mock_execution_result = {
        "status": "error",
        "error": "OmniRoute HTTP 503: Service Unavailable",
        "raw_text": "",
        "reasoning_text": "",
        "tokens_used": 0,
        "latency_ms": 2100.0,
        "model_used": "antigravityonly",
    }
    mock_prompts = ("Sys prompt", "User prompt", {})

    with patch(
        "earnings_engine.consensus.context_builder.build_customized_prompt",
        return_value=mock_prompts,
    ), patch(
        "earnings_engine.data.omniroute_client.execute_omniroute_analysis",
        return_value=mock_execution_result,
    ):
        payload = {
            "ticker": "HDFCBANK.NS",
            "model": "antigravityonly",
        }
        res = client.post("/api/v1/consensus/analyze", json=payload)
        assert res.status_code == 200
        data = res.json()

        assert data["ticker"] == "HDFCBANK.NS"
        assert data["status"] == "error"
        assert "503" in data["error"]
        assert data["structured"]["direction"] == "UNKNOWN"
        assert data["structured"]["thesis"] == ""
