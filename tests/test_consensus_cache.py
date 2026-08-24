"""Unit tests for AI Consensus caching and UI response structure."""

from unittest.mock import patch
import pytest
from starlette.testclient import TestClient

from earnings_engine.api.server import app
from earnings_engine.config import Settings
from earnings_engine.consensus import storage


@pytest.fixture
def test_client():
    return TestClient(app)


def test_consensus_predict_caching_and_response_structure(test_client):
    """Test that POST /api/v1/consensus/predict caches predictions and honors force=False."""
    mock_consensus_result = {
        "ticker": "RELIANCE.NS",
        "as_of_price": 2950.0,
        "timeframe_days": 14,
        "consensus_direction": "BULLISH",
        "consensus_strength": 88.0,
        "consensus_return_pct": 5.4,
        "consensus_target_price": 3109.0,
        "consensus_support": 2900.0,
        "consensus_resistance": 3150.0,
        "consensus_stop_loss": 2880.0,
        "model_count": 4,
        "agreement_ratio": 1.0,
        "models_breakdown": [
            {"model_name": "DeepSeek-R1", "direction": "BULLISH", "confidence_pct": 90, "target_price": 3110.0},
            {"model_name": "Llama-3.3-70B", "direction": "BULLISH", "confidence_pct": 85, "target_price": 3100.0},
        ],
        "synthesized_thesis": "Strong technical base breakout above resistance.",
    }

    # Step 1: Initial call runs models
    with patch("earnings_engine.consensus.model_runner.run_consensus_models") as mock_runner:
        mock_runner.return_value = [
            {"model_name": "DeepSeek-R1", "direction": "BULLISH", "confidence": 90, "target_price": 3110.0},
            {"model_name": "Llama-3.3-70B", "direction": "BULLISH", "confidence": 85, "target_price": 3100.0},
        ]

        res = test_client.post(
            "/api/v1/consensus/predict",
            json={"ticker": "RELIANCE.NS", "timeframe_days": 14, "force": True},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert "predictions" in data
        assert "results" in data
        assert len(data["predictions"]) == 1
        assert data["predictions"][0]["ticker"] == "RELIANCE.NS"
        assert mock_runner.call_count == 1

    # Step 2: Second call with force=False should use CACHE and NOT call model_runner
    with patch("earnings_engine.consensus.model_runner.run_consensus_models") as mock_runner_second:
        res2 = test_client.post(
            "/api/v1/consensus/predict",
            json={"ticker": "RELIANCE.NS", "timeframe_days": 14, "force": False},
        )
        assert res2.status_code == 200
        data2 = res2.json()
        assert data2["success"] is True
        assert len(data2["predictions"]) == 1
        assert data2["predictions"][0]["consensus_direction"] == "BULLISH"
        # Verify model_runner was NOT called because cached result was returned
        assert mock_runner_second.call_count == 0

    # Step 3: Stock overview returns cached consensus
    res_stock = test_client.get("/api/v1/stock/RELIANCE.NS/overview")
    assert res_stock.status_code == 200
    stock_data = res_stock.json()
    assert stock_data["success"] is True
    assert stock_data["consensus"] is not None
    assert stock_data["consensus"]["consensus_direction"] == "BULLISH"
