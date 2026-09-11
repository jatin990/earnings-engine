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
    assert "Point-in-Time Quantitative Analysis Context: RELIANCE.NS" in prompt
    assert "Technical Momentum & Price Structure" in prompt
    assert "Quantitative Factor Weight Rubric" in prompt


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

    # 1. Latest predictions endpoint (including limit=500)
    res = client.get("/api/v1/consensus/latest?limit=500")
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

    # 3. Audit endpoint (including limit=500)
    res_audit = client.get("/api/v1/consensus/audit?limit=500")
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

    # Truncated response recovery (e.g. DeepSeek-R1 token limit cutoff)
    truncated_resp = "<think>Calculating risk reward...</think>{\n  \"direction\": \"NEUTRAL\",\n  \"confidence_pct\": 60,\n  \"target_return_pct\":"
    parsed_trunc = _parse_model_json(truncated_resp)
    assert parsed_trunc is not None
    assert parsed_trunc["direction"] == "NEUTRAL"
    assert parsed_trunc["confidence_pct"] == 60


def test_consensus_models_endpoint_and_rate_limits():
    """Test GET /api/v1/consensus/models returns available models and live rate limits."""
    from earnings_engine.rate_limits import get_models_rate_limits, record_request

    # Record some requests
    record_request("deepseek/deepseek-r1")
    record_request("meta-llama/llama-3.3-70b-instruct")

    models = get_models_rate_limits()
    assert len(models) >= 4
    model_ids = [m["id"] for m in models]
    assert "deepseek/deepseek-r1" in model_ids
    assert "meta-llama/llama-3.3-70b-instruct" in model_ids
    assert "qwen/qwen-2.5-72b-instruct" in model_ids
    assert "google/gemini-2.0-flash-001" in model_ids
    assert "google/gemma-4-31b-it:free" in model_ids

    client = TestClient(app)
    res = client.get("/api/v1/consensus/models")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert "models" in data
    assert "rate_limits" in data
    assert len(data["models"]) >= 4


def test_consensus_single_model_merges_breakdown(monkeypatch, mock_model_results):
    """Test that predicting with a single model merges with cached 4-model breakdown."""
    settings = Settings()
    # 1. Save an initial prediction with 4 models
    consensus_initial = aggregator.aggregate_predictions(
        model_results=mock_model_results,
        ticker="MERGE_TEST.NS",
        as_of_price=1000.0,
        timeframe_days=14,
    )
    storage.save_prediction(consensus_initial, evaluation_date="2026-09-01", settings=settings)

    # 2. Mock model runner to return only 1 model output
    from earnings_engine.consensus import model_runner
    single_model_output = [{
        "model_name": "DeepSeek-R1",
        "model_id": "deepseek/deepseek-r1",
        "direction": "BEARISH",
        "confidence_pct": 92,
        "target_return_pct": -4.0,
        "target_price": 960.0,
        "support_level": 940.0,
        "resistance_level": 1020.0,
        "key_drivers": ["Updated quarterly headwind"],
        "primary_risk": "Breakout above 1020",
    }]
    monkeypatch.setattr(model_runner, "run_consensus_models", lambda **kwargs: single_model_output)

    client = TestClient(app)
    res = client.post("/api/v1/consensus/predict", json={
        "ticker": "MERGE_TEST.NS",
        "force": True,
        "models": ["deepseek/deepseek-r1"]
    })
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    preds = data["predictions"]
    assert len(preds) == 1
    p = preds[0]
    # Check that breakdown contains merged models (4 total, with DeepSeek-R1 updated)
    breakdown = p["models_breakdown"]
    assert len(breakdown) == 4
    r1 = next(m for m in breakdown if m.get("model_name") == "DeepSeek-R1" or m.get("model_id") == "deepseek/deepseek-r1")
    assert r1["direction"] == "BEARISH"
    assert r1["confidence_pct"] == 92


def test_query_omniroute_model_cascades_on_503():
    """Verify _query_omniroute_model cascades to high-availability models on 503 error."""
    from unittest.mock import MagicMock, patch
    from earnings_engine.consensus.model_runner import _query_omniroute_model

    fail_resp = MagicMock()
    fail_resp.status_code = 503
    fail_resp.text = '{"error": "All target providers failed."}'

    succ_payload = {
        "direction": "BULLISH",
        "confidence_pct": 82,
        "target_return_pct": 5.0,
        "target_price": 1050.0,
        "support_level": 980.0,
        "resistance_level": 1080.0,
        "stop_loss_price": 960.0,
        "risk_reward_ratio": 2.5,
    }
    succ_resp = MagicMock()
    succ_resp.status_code = 200
    succ_resp.json.return_value = {
        "choices": [{"message": {"content": json.dumps(succ_payload)}}],
        "usage": {"total_tokens": 250},
    }

    with patch("requests.post", side_effect=[fail_resp, succ_resp]):
        res = _query_omniroute_model("omniroute/deepseek/deepseek-r1", "Test prompt", _ticker="TEST.NS")
        assert res["direction"] == "BULLISH"
        assert res["confidence_pct"] == 82
        assert res["target_price"] == 1050.0
        assert res["sub_model"] in ["openai/gpt-4o-mini", "meta-llama/llama-3.3-70b-instruct", "google/gemini-2.0-flash-001"]



