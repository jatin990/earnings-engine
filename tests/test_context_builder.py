"""Tests for customizable context builder and directive injection."""
from __future__ import annotations

import pytest
from earnings_engine.consensus.context_builder import build_customized_prompt


def test_build_customized_prompt_all_toggles_enabled():
    """Verify prompt contains all sections and custom directives when toggles are True."""
    directives = "Focus strictly on debt reduction, margin trajectory, and resistance at 3000."
    sys_prompt, user_prompt, ctx = build_customized_prompt(
        ticker="RELIANCE.NS",
        timeframe_days=14,
        include_technicals=True,
        include_news=True,
        include_institutional=True,
        custom_directives=directives,
        fetch_live=False,
    )

    assert isinstance(sys_prompt, str) and len(sys_prompt) > 50
    assert isinstance(user_prompt, str) and len(user_prompt) > 100
    assert isinstance(ctx, dict)
    assert ctx["ticker"] == "RELIANCE.NS"

    # Header verification
    assert "RELIANCE.NS" in user_prompt
    assert "Timeframe" in user_prompt or "Trading Days" in user_prompt
    assert "Current Price" in user_prompt or "CMP" in user_prompt
    assert "Market Feed" in user_prompt or "Snapshot" in user_prompt or "Live" in user_prompt

    # Section verifications
    assert "Technical Momentum & Price Structure" in user_prompt
    assert "52W" in user_prompt or "52-Week" in user_prompt
    assert "EMA" in user_prompt
    assert "Volume" in user_prompt
    assert "ATR" in user_prompt

    assert "Institutional & Smart Money Flows" in user_prompt
    assert "Mutual Fund" in user_prompt or "DII" in user_prompt
    assert "FII" in user_prompt
    assert "Promoter" in user_prompt

    assert "Corporate Catalysts & Breaking News" in user_prompt

    # Custom directive section
    assert "🎯 Custom Focus & Analysis Directives" in user_prompt
    assert directives in user_prompt

    # Strict JSON output schema instructions verification
    assert "direction" in user_prompt
    assert "conviction_score" in user_prompt
    assert "target_price" in user_prompt
    assert "stop_loss" in user_prompt
    assert "risk_reward_ratio" in user_prompt
    assert "catalyst_summary" in user_prompt
    assert "thesis" in user_prompt
    assert "key_risks" in user_prompt


def test_build_customized_prompt_toggles_disabled():
    """Verify prompt excludes sections when toggles are False."""
    sys_prompt, user_prompt, ctx = build_customized_prompt(
        ticker="RELIANCE.NS",
        timeframe_days=14,
        include_technicals=False,
        include_news=False,
        include_institutional=False,
        custom_directives=None,
        fetch_live=False,
    )

    assert isinstance(sys_prompt, str)
    assert isinstance(user_prompt, str)
    assert isinstance(ctx, dict)

    # Header still present
    assert "RELIANCE.NS" in user_prompt

    # Excluded sections must not appear
    assert "Technical Momentum & Price Structure" not in user_prompt
    assert "Institutional & Smart Money Flows" not in user_prompt
    assert "Corporate Catalysts & Breaking News" not in user_prompt
    assert "🎯 Custom Focus & Analysis Directives" not in user_prompt

    # JSON schema must still be present for model output parsing
    assert "direction" in user_prompt
    assert "conviction_score" in user_prompt
    assert "target_price" in user_prompt
    assert "stop_loss" in user_prompt
    assert "risk_reward_ratio" in user_prompt
    assert "catalyst_summary" in user_prompt
    assert "thesis" in user_prompt
    assert "key_risks" in user_prompt


def test_build_customized_prompt_selective_toggles():
    """Verify selective toggle combinations work as expected."""
    # Only technicals
    _, prompt_tech_only, _ = build_customized_prompt(
        ticker="RELIANCE.NS",
        timeframe_days=7,
        include_technicals=True,
        include_news=False,
        include_institutional=False,
        custom_directives=None,
        fetch_live=False,
    )
    assert "Technical Momentum & Price Structure" in prompt_tech_only
    assert "Institutional & Smart Money Flows" not in prompt_tech_only
    assert "Corporate Catalysts & Breaking News" not in prompt_tech_only

    # Only news
    _, prompt_news_only, _ = build_customized_prompt(
        ticker="RELIANCE.NS",
        timeframe_days=7,
        include_technicals=False,
        include_news=True,
        include_institutional=False,
        custom_directives=None,
        fetch_live=False,
    )
    assert "Technical Momentum & Price Structure" not in prompt_news_only
    assert "Institutional & Smart Money Flows" not in prompt_news_only
    assert "Corporate Catalysts & Breaking News" in prompt_news_only
