"""Tests for Market Sentiment & Macro Volatility Regime Harvester."""
import pytest
from earnings_engine.features.market_sentiment import (
    get_volatility_regime,
    get_market_sentiment,
    VOLATILITY_REGIMES,
)


def test_volatility_regime_classification():
    # Low risk
    low = get_volatility_regime(11.5)
    assert low["regime_key"] == "LOW_RISK_BULLISH"
    assert low["stance"] == "BULLISH"

    # Normal
    norm = get_volatility_regime(15.2)
    assert norm["regime_key"] == "STABLE_NORMAL"
    assert norm["stance"] == "NEUTRAL_BULLISH"

    # Elevated
    elev = get_volatility_regime(19.8)
    assert elev["regime_key"] == "ELEVATED_CHOP"
    assert elev["stance"] == "CAUTIOUS"

    # Panic
    panic = get_volatility_regime(26.4)
    assert panic["regime_key"] == "HIGH_RISK_PANIC"
    assert panic["stance"] == "BEARISH_DEFENSIVE"

    # None / Missing
    none_case = get_volatility_regime(None)
    assert none_case["regime_key"] == "STABLE_NORMAL"


def test_get_market_sentiment_structure():
    # Indian stock (Nifty 50 + India VIX)
    sent_in = get_market_sentiment("TCS.NS", fetch_live=False)
    assert sent_in["region"] == "IN"
    assert sent_in["benchmark_symbol"] == "^NSEI"
    assert sent_in["benchmark_name"] == "Nifty 50"
    assert sent_in["vix_symbol"] == "^INDIAVIX"
    assert "vix_level" in sent_in
    assert "vix_regime" in sent_in
    assert "market_sentiment_score" in sent_in
    assert 0 <= sent_in["market_sentiment_score"] <= 100

    # US stock (S&P 500 + CBOE VIX)
    sent_us = get_market_sentiment("NVDA", fetch_live=False)
    assert sent_us["region"] == "US"
    assert sent_us["benchmark_symbol"] == "^GSPC"
    assert sent_us["benchmark_name"] == "S&P 500"
    assert sent_us["vix_symbol"] == "^VIX"
