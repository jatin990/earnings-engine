"""Tests for Standardized Model Inputs, Factor Weight Matrix & Prompt Formatter."""
import pytest
from earnings_engine.consensus.standard_inputs import (
    STANDARDIZED_FACTORS_WEIGHT_MODEL,
    build_standardized_model_context,
    format_standardized_llm_prompt,
)
from earnings_engine.consensus.context_builder import build_context, context_to_prompt


def test_standardized_factor_weight_hierarchy():
    matrix = STANDARDIZED_FACTORS_WEIGHT_MODEL
    assert matrix["version"] == "2.0.0"
    assert matrix["total_weight"] == 100.0

    pillars = matrix["pillars"]
    assert len(pillars) == 6

    # Verify all 6 pillars exist
    pillar_keys = [
        "pillar_1_institutional_flows",
        "pillar_2_technical_momentum",
        "pillar_3_earnings_surprises",
        "pillar_4_corporate_catalysts",
        "pillar_5_market_sentiment",
        "pillar_6_valuation_fundamentals",
    ]
    for pk in pillar_keys:
        assert pk in pillars

    # Verify sum of pillar weights equals 100.0%
    pillar_weight_sum = sum(p["weight_pct"] for p in pillars.values())
    assert abs(pillar_weight_sum - 100.0) < 1e-5

    # Verify every sub-factor has relevance and scope of improvement defined
    for pk, p in pillars.items():
        sub_sum = sum(sf["weight_pct"] for sf in p["sub_factors"])
        assert abs(sub_sum - p["weight_pct"]) < 1e-5
        for sf in p["sub_factors"]:
            assert "relevance" in sf
            assert "relevance_explanation" in sf
            assert "scope_of_improvement" in sf


def test_build_standardized_model_context_structure():
    ctx = build_standardized_model_context("ALLCARGO.NS", timeframe_days=14, fetch_live=False)
    assert ctx["ticker"] == "ALLCARGO.NS"
    assert ctx["timeframe_days"] == 14
    assert "factor_model_version" in ctx

    # Check 6 canonical pillars present in context dictionary
    assert "institutional_flows" in ctx
    assert "technical_momentum" in ctx
    assert "earnings_track_record" in ctx
    assert "corporate_catalysts" in ctx
    assert "market_sentiment" in ctx
    assert "valuation_fundamentals" in ctx

    # Verify market sentiment data
    assert "vix_regime" in ctx["market_sentiment"]
    assert "benchmark_symbol" in ctx["market_sentiment"]

    # Verify institutional flows data for ALLCARGO
    assert ctx["institutional_flows"]["accumulation_score"] >= 0


def test_format_standardized_llm_prompt_structure():
    ctx = build_standardized_model_context("ALLCARGO.NS", timeframe_days=14, fetch_live=False)
    prompt = format_standardized_llm_prompt(ctx)

    assert "# Point-in-Time Quantitative Analysis Context: ALLCARGO.NS" in prompt
    assert "Quantitative Factor Weight Rubric (Total: 100%)" in prompt
    assert "Pillar 1: Institutional & Smart Money Flows (Weight: 22%)" in prompt
    assert "Pillar 2: Technical Momentum & Price Structure (Weight: 20%)" in prompt
    assert "Pillar 3: Earnings Surprises & Track Record (Weight: 18%)" in prompt
    assert "Pillar 4: Corporate Catalysts & News Sentiment (Weight: 16%)" in prompt
    assert "Pillar 5: Market Sentiment & Macro Regime (Weight: 14%)" in prompt
    assert "Pillar 6: Valuation Multiples & Financial Health (Weight: 10%)" in prompt


def test_context_builder_backward_compatibility():
    # Ensure build_context and context_to_prompt work transparently
    ctx = build_context("TCS.NS", timeframe_days=14, fetch_live=False)
    assert ctx["ticker"] == "TCS.NS"
    assert "price_action" in ctx
    assert "swing_channel" in ctx
    assert "earnings" in ctx
    assert "catalysts" in ctx
    assert "market_sentiment" in ctx

    prompt = context_to_prompt(ctx)
    assert "TCS.NS" in prompt
    assert "Factor Weight Rubric" in prompt
