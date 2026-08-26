"""Unit tests for Standardized 6-Pillar Model Inputs, Factor Evaluation, and Market Sentiment Integration."""
import pytest
from datetime import datetime

from earnings_engine.config import Settings
from earnings_engine.consensus.standard_inputs import (
    STANDARDIZED_FACTORS_WEIGHT_MODEL,
    build_standardized_stock_context,
    format_standardized_llm_prompt,
    evaluate_stock_standard_pillars,
)
from earnings_engine.api.stock_api import get_stock_overview, get_stock_factor_evaluation
from earnings_engine.api.dashboard_api import get_watchlist_quotes_api


def test_standardized_factor_weights_sum_to_100():
    pillars = STANDARDIZED_FACTORS_WEIGHT_MODEL["pillars"]
    total_wgt = sum(p["weight_pct"] for p in pillars.values())
    assert abs(total_wgt - 100.0) < 1e-5


def test_evaluate_stock_standard_pillars_synthesis():
    settings = Settings()
    eval_res = evaluate_stock_standard_pillars("TCS.NS", settings=settings)
    assert eval_res["ticker"] == "TCS.NS"
    assert "composite_score" in eval_res
    assert 0.0 <= eval_res["composite_score"] <= 100.0
    assert "verdict" in eval_res
    assert "verdict_badge" in eval_res
    assert "pillars" in eval_res
    
    pillars = eval_res["pillars"]
    assert "institutional_flows" in pillars
    assert "technical_momentum" in pillars
    assert "earnings_track_record" in pillars
    assert "corporate_catalysts" in pillars
    assert "market_sentiment" in pillars
    assert "valuation_fundamentals" in pillars

    # Ensure each pillar score is bounded
    for p_key, p_val in pillars.items():
        assert 0.0 <= p_val["score"] <= 100.0
        assert p_val["weight_pct"] > 0
        assert "badge" in p_val
        assert "detail" in p_val


def test_stock_overview_includes_factor_evaluation():
    settings = Settings()
    overview = get_stock_overview("INFY.NS", settings=settings)
    assert overview["success"] is True
    assert "factor_evaluation" in overview
    fe = overview["factor_evaluation"]
    assert fe.get("composite_score") is not None
    assert fe.get("verdict") is not None


def test_stock_factor_evaluation_endpoint_api():
    settings = Settings()
    res = get_stock_factor_evaluation("RELIANCE.NS", settings=settings)
    assert res["success"] is True
    assert "data" in res
    assert res["data"]["ticker"] == "RELIANCE.NS"


def test_watchlist_quotes_includes_institutional_and_sentiment():
    settings = Settings()
    res = get_watchlist_quotes_api(watchlist="DEFAULT", tickers=["TCS.NS", "INFY.NS"], live=False, settings=settings)
    assert res["success"] is True
    assert "market_sentiment" in res
    assert "items" in res
    assert len(res["items"]) >= 1
    item = res["items"][0]
    assert "funds_buying" in item
    assert "institutional_score" in item
