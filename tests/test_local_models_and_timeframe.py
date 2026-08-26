import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from earnings_engine.config import Settings
from earnings_engine.consensus.context_builder import build_context, context_to_prompt
from earnings_engine.consensus.model_runner import (
    _query_local_model,
    run_consensus_models,
    MODEL_DISPLAY_NAMES,
)
from earnings_engine.api.server import app

client = TestClient(app)


def test_context_builder_timeframe():
    """Verify that build_context and context_to_prompt correctly incorporate chosen timeframe."""
    ctx = build_context("TCS.NS", timeframe_days=30, fetch_live=False)
    assert ctx["timeframe_days"] == 30
    prompt = context_to_prompt(ctx)
    assert "**Prediction Timeframe:** 30 days" in prompt


def test_local_models_endpoint():
    """Verify GET /api/v1/consensus/local-models returns model list and host."""
    response = client.get("/api/v1/consensus/local-models")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "models" in data
    assert len(data["models"]) >= 1
    assert "host" in data


def test_local_model_query_mock():
    """Verify _query_local_model handles response and extracts structured prediction."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": '{"direction": "BULLISH", "confidence_pct": 85, "target_price": 4200.0, "support_level": 3900.0, "resistance_level": 4300.0, "stop_loss_price": 3850.0, "risk_reward_ratio": 2.8, "recommended_action": "STRONG BUY", "key_drivers": ["Volume Surge", "Channel Breakout"], "primary_risk": "Market Volatility"}'
                }
            }
        ],
        "usage": {"total_tokens": 120},
    }

    with patch("requests.post", return_value=mock_resp):
        res = _query_local_model("local/deepseek-r1:8b", "Test prompt", timeout=10)
        assert res["direction"] == "BULLISH"
        assert res["confidence_pct"] == 85
        assert res["target_price"] == 4200.0
        assert res["is_local"] is True
        assert res["model_name"] == "Local (deepseek-r1:8b)"


def test_local_model_offline_fallback():
    """Verify _query_local_model gracefully handles offline local host."""
    with patch("requests.post", side_effect=ConnectionError("Connection refused")):
        res = _query_local_model("local/deepseek-r1:8b", "Test prompt", timeout=2)
        assert res["is_local"] is True
        assert res["direction"] == "NEUTRAL"
        assert "unavailable" in res["error"].lower()
