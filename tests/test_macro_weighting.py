"""Test suite for universal market conditions weighting across Breakout, Swing, and AI consensus."""

from unittest.mock import patch
import pytest
import pandas as pd
from earnings_engine.config import Settings
from earnings_engine.data.cross_strategy import compute_market_regime_multiplier
from earnings_engine.data.swing_scanner import evaluate_stock_swing


@pytest.fixture
def temp_settings(tmp_path):
    s = Settings()
    s.data_dirs["prices"] = tmp_path
    s.ensure_dirs()
    from earnings_engine.data.migrations import apply_migrations
    apply_migrations(s)
    return s


def test_market_regime_multiplier_bullish(temp_settings):
    with patch("earnings_engine.data.cross_strategy.get_market_macro_summary") as mock_macro:
        mock_macro.return_value = {
            "fear_greed_score": 72.0,
            "fear_greed_label": "Greed",
            "vix_level": 13.5,
            "macro_bias": "BULLISH_EXPANSION",
            "macro_badge": "🟢 Risk-On",
        }
        res = compute_market_regime_multiplier(temp_settings)
        assert res["breakout_multiplier"] == 1.15
        assert res["swing_multiplier"] == 1.10
        assert res["macro_score"] == 15.0
        assert "Tailwinds" in res["macro_pill"]


def test_market_regime_multiplier_bearish(temp_settings):
    with patch("earnings_engine.data.cross_strategy.get_market_macro_summary") as mock_macro:
        mock_macro.return_value = {
            "fear_greed_score": 28.0,
            "fear_greed_label": "Extreme Fear",
            "vix_level": 22.8,
            "macro_bias": "BEARISH_DEFENSIVE",
            "macro_badge": "🔴 Risk-Off",
        }
        res = compute_market_regime_multiplier(temp_settings)
        assert res["breakout_multiplier"] == 0.75
        assert res["swing_multiplier"] == 0.80
        assert res["macro_score"] == 0.0
        assert "Headwinds" in res["macro_pill"]


def test_swing_scanner_macro_weighting(temp_settings):
    ticker = "TESTSWING.NS"
    # Create sample prices DataFrame
    dates = pd.date_range(end="2026-08-28", periods=40)
    prices_df = pd.DataFrame(
        {
            "open": [100.0 + i * 0.1 for i in range(40)],
            "high": [102.0 + i * 0.1 for i in range(40)],
            "low": [99.0 + i * 0.1 for i in range(40)],
            "close": [101.0 for _ in range(40)],  # Close at support floor 100
            "volume": [1000000 for _ in range(40)],
        },
        index=dates,
    )

    # Mock bullish macro
    with patch("earnings_engine.data.cross_strategy.get_market_macro_summary") as mock_macro:
        mock_macro.return_value = {
            "fear_greed_score": 75.0,
            "fear_greed_label": "Extreme Greed",
            "vix_level": 13.0,
            "macro_bias": "BULLISH_EXPANSION",
            "macro_badge": "🟢 Risk-On",
        }
        res_bull = evaluate_stock_swing(
            ticker=ticker,
            settings=temp_settings,
            prices_df=prices_df,
            stored_range={"lower_bound": 100.0, "upper_bound": 125.0, "source": "user", "cycles": 3},
            earnings_score=7.0,
        )

        assert res_bull is not None
        assert "macro_regime" in res_bull
        assert res_bull["macro_regime"]["multiplier"] == 1.10
        score_bull = res_bull["composite_score"]

    # Mock bearish macro
    with patch("earnings_engine.data.cross_strategy.get_market_macro_summary") as mock_macro:
        mock_macro.return_value = {
            "fear_greed_score": 25.0,
            "fear_greed_label": "Fear",
            "vix_level": 23.0,
            "macro_bias": "BEARISH_DEFENSIVE",
            "macro_badge": "🔴 Risk-Off",
        }
        res_bear = evaluate_stock_swing(
            ticker=ticker,
            settings=temp_settings,
            prices_df=prices_df,
            stored_range={"lower_bound": 100.0, "upper_bound": 125.0, "source": "user", "cycles": 3},
            earnings_score=7.0,
        )

        assert res_bear is not None
        assert res_bear["macro_regime"]["multiplier"] == 0.80
        score_bear = res_bear["composite_score"]

    # Assert that bullish macro produces higher composite score than bearish macro
    assert score_bull > score_bear


def test_ai_consensus_macro_pillar_context(temp_settings):
    from earnings_engine.consensus.standard_inputs import build_standardized_model_context, format_standardized_llm_prompt

    with patch("earnings_engine.data.cross_strategy.get_market_macro_summary") as mock_macro:
        mock_macro.return_value = {
            "fear_greed_score": 68.5,
            "fear_greed_label": "Greed",
            "vix_level": 13.8,
            "macro_bias": "BULLISH_EXPANSION",
            "macro_badge": "🟢 Risk-On",
        }
        ctx = build_standardized_model_context("TCS.NS", settings=temp_settings, fetch_live=False)
        assert "market_sentiment" in ctx
        assert ctx["market_sentiment"].get("macro_bias") == "BULLISH_EXPANSION"
        assert ctx["market_sentiment"].get("fear_greed_score") == 68.5

        prompt = format_standardized_llm_prompt(ctx)
        assert "Pillar 5: Market Sentiment & Macro Regime" in prompt
        assert "Fear & Greed Index" in prompt
