"""Unit and integration tests for diegosouzapw/OmniRoute AI Gateway client adapter."""

import json
from unittest.mock import MagicMock, patch

import pytest
from starlette.testclient import TestClient

from earnings_engine.api.server import app
from earnings_engine.config import Settings
from earnings_engine.data.omniroute_client import (
    DEFAULT_OMNIROUTER_MODELS,
    OMNIROUTE_PROBE_PORTS,
    OmniRouteClient,
)


@pytest.fixture
def client():
    return TestClient(app)


def test_omniroute_client_init_and_defaults():
    """Verify OmniRoute client defaults to diegosouzapw/OmniRoute port 20128."""
    settings = Settings()
    omni = OmniRouteClient(settings=settings)
    base_url = omni.get_configured_base_url()
    assert "20128" in base_url
    assert base_url.endswith("/v1")


def test_omniroute_probe_health_online():
    """Verify probe_health detects online diegosouzapw/OmniRoute daemon."""
    omni = OmniRouteClient()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "object": "list",
        "data": [
            {"id": "deepseek/deepseek-r1", "object": "model"},
            {"id": "meta-llama/llama-3.3-70b-instruct", "object": "model"},
            {"id": "google/gemini-2.0-flash", "object": "model"},
        ],
    }

    with patch("requests.get", return_value=mock_resp):
        health = omni.probe_health(timeout=1.0)
        assert health["status"] == "online"
        assert health["models_count"] == 3
        assert "deepseek/deepseek-r1" in health["models"]
        assert health["is_self_hosted"] is True


def test_omniroute_probe_health_offline():
    """Verify probe_health reports offline status when daemon is not running."""
    omni = OmniRouteClient()
    with patch("requests.get", side_effect=Exception("Connection refused")), \
         patch.object(omni, "get_api_key", return_value=""):
        health = omni.probe_health(timeout=0.1)
        assert health["status"] == "offline"
        assert health["models_count"] == 0
        assert "not detected on" in health["message"]
        assert "20128" in health["message"]


def test_omniroute_format_prompt():
    """Verify prompt formatting includes ticker, headline, summary, and price delta."""
    omni = OmniRouteClient()
    item = {
        "ticker": "RELIANCE.NS",
        "stock_name": "Reliance Industries",
        "title": "Reliance bags ₹12,000 Cr Green Energy contract",
        "summary": "Large EPC contract awarded for solar modules.",
        "signal_price": 2800.0,
        "current_price": 2850.0,
        "verified_numbers": {"contract_val_cr": 12000, "units_gw": 5},
    }
    prompt = omni.format_prompt(item)
    assert "RELIANCE.NS" in prompt
    assert "Reliance Industries" in prompt
    assert "Green Energy contract" in prompt
    assert "Pre-News Reference Close (Signal Price): INR 2800.00" in prompt
    assert "Latest Market Price: INR 2850.00" in prompt
    assert "Price Delta Since Signal: +1.79%" in prompt
    assert "contract_val_cr: 12000" in prompt


def test_omniroute_analyze_catalyst_mock_completion():
    """Verify analyze_catalyst parses structured JSON and calculates target/stop levels."""
    omni = OmniRouteClient()
    item = {
        "ticker": "TCS.NS",
        "stock_name": "Tata Consultancy Services",
        "title": "TCS signs mega $1.5B deal with European bank",
        "summary": "Multi-year core banking transformation agreement.",
        "signal_price": 4000.0,
        "current_price": 4050.0,
    }

    mock_llm_payload = {
        "direction": "BULLISH",
        "impact_score": 88,
        "impact_level": "HIGH",
        "expected_horizon": "📅 1-3 Days",
        "volatility_est": "±3% to ±6%",
        "trading_takeaway": "Direct revenue accretive mega-deal provides strong near-term price momentum.",
        "target_price": 4200.0,
        "stop_loss": 3920.0,
        "confidence_pct": 90,
        "key_catalyst_triggers": ["Order Win", "Revenue Expansion"],
        "primary_risk": "Broad market tech pullback",
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": json.dumps(mock_llm_payload)}}],
        "usage": {"total_tokens": 420, "prompt_tokens": 280, "completion_tokens": 140},
    }

    with patch("requests.post", return_value=mock_resp), \
         patch.object(omni, "get_completions_url", return_value="http://localhost:20128/v1/chat/completions"):
        res = omni.analyze_catalyst(item, preferred_model="deepseek/deepseek-r1")
        assert res["direction"] == "BULLISH"
        assert res["impact_score"] == 88
        assert res["impact_level"] == "HIGH"
        assert res["target_price"] == 4200.0
        assert res["stop_loss"] == 3920.0
        assert res["tokens_used"] == 420
        assert "omniroute/" in res["ai_model"] and "deepseek" in res["ai_model"]
        assert res["gateway"] == "diegosouzapw/OmniRoute"


def test_omniroute_analyze_catalyst_fallback():
    """Verify fallback_heuristic_analysis generates valid quantitative setups when offline."""
    omni = OmniRouteClient()
    item = {
        "ticker": "INFY.NS",
        "stock_name": "Infosys",
        "title": "Infosys expands AI collaboration with enterprise cloud provider",
        "summary": "Strategic expansion to build generative AI solutions.",
        "signal_price": 1800.0,
        "current_price": 1800.0,
    }

    with patch.object(omni, "get_api_key", return_value=""):
        res = omni.analyze_catalyst(item)
        assert res["direction"] in ("BULLISH", "NEUTRAL", "BEARISH")
        assert res["impact_score"] >= 25
        assert res["target_price"] is not None
        assert res["stop_loss"] is not None
        assert "omniroute" in res["ai_model"]
        assert "diegosouzapw/OmniRoute" in res["gateway"]


def test_omniroute_api_status_endpoint(client):
    """Verify /api/v1/omniroute/status endpoint returns gateway details."""
    mock_health = {
        "status": "online",
        "endpoint": "http://localhost:20128/v1",
        "latency_ms": 1.2,
        "models_count": 5,
        "models": ["deepseek/deepseek-r1"],
        "is_self_hosted": True,
    }
    with patch.object(OmniRouteClient, "probe_health", return_value=mock_health):
        res = client.get("/api/v1/omniroute/status")
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["gateway"] == "diegosouzapw/OmniRoute"
        assert data["status"] == "online"


def test_omniroute_cascade_on_503_provider_failure():
    """Verify that when a model encounters a 503 All target providers failed error, it cascades to a high-availability model."""
    omni = OmniRouteClient()
    item = {
        "ticker": "RELIANCE.NS",
        "stock_name": "Reliance Industries",
        "title": "Reliance expanding refinery capacity",
        "summary": "Capacity addition planned over next 2 years.",
        "signal_price": 2900.0,
        "current_price": 2920.0,
    }

    fail_resp = MagicMock()
    fail_resp.status_code = 503
    fail_resp.text = '{"error": {"message": "All target providers failed."}}'

    success_payload = {
        "direction": "BULLISH",
        "impact_score": 80,
        "impact_level": "HIGH",
        "expected_horizon": "📅 1-3 Days",
        "volatility_est": "±2% to ±4%",
        "trading_takeaway": "Capex driven growth.",
        "target_price": 3100.0,
        "stop_loss": 2850.0,
        "confidence_pct": 85,
    }
    succ_resp = MagicMock()
    succ_resp.status_code = 200
    succ_resp.json.return_value = {
        "choices": [{"message": {"content": json.dumps(success_payload)}}],
        "usage": {"total_tokens": 300},
    }

    with patch("requests.post", side_effect=[fail_resp, succ_resp]), \
         patch.object(omni, "get_completions_url", return_value="http://localhost:20128/v1/chat/completions"), \
         patch.object(omni, "get_api_key", return_value="test_key"):
        res = omni.analyze_catalyst(item, preferred_model="deepseek/deepseek-r1")
        assert res["direction"] == "BULLISH"
        assert res["impact_score"] == 80
        assert res["target_price"] == 3100.0
        assert "openai/gpt-4o-mini" in res["ai_model"]

