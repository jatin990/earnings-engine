"""Unit tests for the Multi-Model AI Consensus Engine."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
import pytest
from starlette.testclient import TestClient

from earnings_engine.config import Settings
from earnings_engine.consensus import aggregator, context_builder, failure_analyst, settlement, storage
from earnings_engine.api.server import app


@pytest.fixture
def mock_model_results():
    """Simulate 4 models responding to a stock context."""
    return [
        {
            "model_name": "DeepSeek-R1",
            "model_id": "deepseek/deepseek-r1",
            "direction": "BULLISH",
            "confidence_pct": 85,
            "target_return_pct": 6.5,
            "target_price": 2850.0,
            "support_level": 2650.0,
            "resistance_level": 2900.0,
            "key_drivers": ["Consolidating at swing support floor", "Positive order win catalysts"],
            "primary_risk": "Broad market weakness",
        },
        {
            "model_name": "Llama-3.3-70B",
            "model_id": "meta-llama/llama-3.3-70b-instruct",
            "direction": "BULLISH",
            "confidence_pct": 75,
            "target_return_pct": 4.5,
            "target_price": 2800.0,
            "support_level": 2680.0,
            "resistance_level": 2880.0,
            "key_drivers": ["Strong 20-day swing channel floor", "Expanding retail margins"],
            "primary_risk": "Crude oil volatility",
        },
        {
            "model_name": "Qwen-2.5-72B",
            "model_id": "qwen/qwen-2.5-72b-instruct",
            "direction": "BULLISH",
            "confidence_pct": 80,
            "target_return_pct": 5.0,
            "target_price": 2820.0,
            "support_level": 2660.0,
            "resistance_level": 2890.0,
            "key_drivers": ["Refining margin rebound", "Positive historical post-earnings bias"],
            "primary_risk": "High capex debt overhang",
        },
        {
            "model_name": "Mistral-Large",
            "model_id": "mistralai/mistral-large-2411",
            "direction": "BEARISH",
            "confidence_pct": 60,
            "target_return_pct": -2.5,
            "target_price": 2620.0,
            "support_level": 2580.0,
            "resistance_level": 2720.0,
            "key_drivers": ["High valuation multiple", "Tariff risk in exports"],
            "primary_risk": "Strong domestic demand offsets export weakness",
        },
    ]


def test_aggregator_consensus_math(mock_model_results):
    """Verify confidence-weighted direction, target prices, and agreement ratio."""
    as_of_price = 2700.0
    res = aggregator.aggregate_predictions(
        model_results=mock_model_results,
        ticker="RELIANCE.NS",
        as_of_price=as_of_price,
        timeframe_days=14,
    )

    assert res["ticker"] == "RELIANCE.NS"
    assert res["consensus_direction"] == "BULLISH"
    assert res["agreement_ratio"] == 0.75  # 3 of 4 models Bullish
    assert res["consensus_strength"] > 70.0
    assert res["consensus_target_price"] > as_of_price
    assert res["consensus_return_pct"] > 0
    assert "synthesized_thesis" in res
    assert "swing support" in res["synthesized_thesis"].lower() or "consensus" in res["synthesized_thesis"].lower()


def test_aggregator_all_error_fallback():
    """Verify graceful handling when all models return errors."""
    errored = [
        {"model_name": "DeepSeek-R1", "error": "HTTP 500"},
        {"model_name": "Llama-3.3-70B", "error": "Timeout"},
    ]
    res = aggregator.aggregate_predictions(
        model_results=errored,
        ticker="TCS.NS",
        as_of_price=3500.0,
    )
    assert res["consensus_direction"] == "NEUTRAL"
    assert res["valid_count"] == 0
    assert res["error_count"] == 2
    assert res["consensus_strength"] == 0.0


def test_context_builder_and_prompt():
    """Verify context assembly generates prompt markdown with key technical headers."""
    ctx = context_builder.build_context("RELIANCE.NS", timeframe_days=14, settings=Settings())
    assert ctx["ticker"] == "RELIANCE.NS"
    assert "price_action" in ctx
    assert "swing_channel" in ctx
    assert "earnings" in ctx
    assert "catalysts" in ctx

    prompt = context_builder.context_to_prompt(ctx)
    assert "Stock Analysis Context: RELIANCE.NS" in prompt
    assert "Price Action & Momentum" in prompt
    assert "Swing Channel & Structure" in prompt


def test_storage_crud_and_stats(mock_model_results):
    """Test saving a prediction, querying it, updating settlement, and reading stats."""
    settings = Settings()
    consensus = aggregator.aggregate_predictions(
        model_results=mock_model_results,
        ticker="TEST_TICKER.NS",
        as_of_price=1000.0,
        timeframe_days=14,
    )

    eval_date = (datetime.now() + timedelta(days=14)).strftime("%Y-%m-%d")
    pred_id = storage.save_prediction(consensus, evaluation_date=eval_date, settings=settings)
    assert pred_id > 0

    # Retrieve by ID
    pred = storage.get_prediction_by_id(pred_id, settings=settings)
    assert pred is not None
    assert pred["ticker"] == "TEST_TICKER.NS"
    assert pred["settlement_status"] == "PENDING"
    assert len(pred["models_breakdown"]) == 4

    # Update settlement
    storage.update_settlement(
        pred_id,
        {
            "settlement_status": "SUCCESS",
            "actual_exit_price": 1060.0,
            "actual_return_pct": 6.0,
            "is_direction_correct": 1,
        },
        settings=settings,
    )

    # Verify updated
    updated = storage.get_prediction_by_id(pred_id, settings=settings)
    assert updated["settlement_status"] == "SUCCESS"
    assert updated["actual_return_pct"] == 6.0

    # Stats
    stats = storage.get_accuracy_stats(settings=settings)
    assert stats["total_predictions"] >= 1
    assert stats["success_count"] >= 1


def test_settlement_evaluation_criteria():
    """Verify the settlement evaluation logic maps returns to correct outcome grades."""
    # Bullish target +5%, actual return +4% -> SUCCESS
    s1, c1 = settlement._evaluate_outcome("BULLISH", target_return_pct=5.0, actual_return_pct=4.0)
    assert s1 == "SUCCESS"
    assert c1 is True

    # Bullish target +5%, actual return +0.5% (under 50% target) -> PARTIAL
    s2, c2 = settlement._evaluate_outcome("BULLISH", target_return_pct=5.0, actual_return_pct=0.5)
    assert s2 == "PARTIAL"
    assert c2 is True

    # Bullish target +5%, actual return -2.5% -> FAILURE
    s3, c3 = settlement._evaluate_outcome("BULLISH", target_return_pct=5.0, actual_return_pct=-2.5)
    assert s3 == "FAILURE"
    assert c3 is False

    # Bearish target -5%, actual return -4.0% -> SUCCESS
    s4, c4 = settlement._evaluate_outcome("BEARISH", target_return_pct=-5.0, actual_return_pct=-4.0)
    assert s4 == "SUCCESS"
    assert c4 is True


def test_heuristic_failure_analysis():
    """Test rule-based fallback post-mortem when LLM key is absent."""
    pred = {
        "ticker": "FAIL_TEST.NS",
        "as_of_price": 500.0,
        "consensus_target_price": 550.0,
        "consensus_return_pct": 10.0,
        "consensus_direction": "BULLISH",
    }
    diag = failure_analyst._heuristic_failure_analysis(pred, actual_return_pct=-4.5)
    assert diag["failure_category"] == "FALSE_TECHNICAL_BREAKOUT"
    assert "summary" in diag
    assert "detailed_analysis" in diag
    assert "learning_lesson" in diag


def test_consensus_api_endpoints():
    """Test REST API endpoints via FastAPI TestClient."""
    client = TestClient(app)

    # 1. Latest predictions endpoint
    res = client.get("/api/v1/consensus/latest")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert "predictions" in data

    # 2. Accuracy stats endpoint
    res_stats = client.get("/api/v1/consensus/accuracy-stats")
    assert res_stats.status_code == 200
    stats = res_stats.json()
    assert stats["success"] is True
    assert "win_rate" in stats
    assert "model_stats" in stats

    # 3. Audit endpoint
    res_audit = client.get("/api/v1/consensus/audit")
    assert res_audit.status_code == 200
    assert res_audit.json()["success"] is True


def test_parse_model_json():
    """Test model json extraction across thinking tags, markdown, and raw strings."""
    from earnings_engine.consensus.model_runner import _parse_model_json

    assert _parse_model_json(None) is None
    assert _parse_model_json("") is None
    assert _parse_model_json("invalid json string") is None

    # DeepSeek-R1 thinking tag format
    r1_resp = "<think>Analyzing RELIANCE fundamentals... Target looks strong.</think>{\"direction\": \"BULLISH\", \"confidence_pct\": 85}"
    parsed = _parse_model_json(r1_resp)
    assert parsed is not None
    assert parsed["direction"] == "BULLISH"
    assert parsed["confidence_pct"] == 85

    # Markdown fence
    md_resp = "Here is the forecast:\n```json\n{\"direction\": \"BEARISH\", \"confidence_pct\": 60}\n```"
    parsed_md = _parse_model_json(md_resp)
    assert parsed_md is not None
    assert parsed_md["direction"] == "BEARISH"
