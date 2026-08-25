"""Tests for Multi-Factor Fundamental & Institutional Intelligence Pipeline."""

from __future__ import annotations

import pytest
from earnings_engine.config import Settings
from earnings_engine.features.fundamental_pipeline import (
    build_multi_factor_pipeline,
    format_pipeline_for_llm_prompt,
    SECTOR_BENCHMARKS,
)


def test_sector_benchmarks_presence():
    assert "IT" in SECTOR_BENCHMARKS
    assert "AUTO" in SECTOR_BENCHMARKS
    assert "FINANCIAL" in SECTOR_BENCHMARKS
    assert SECTOR_BENCHMARKS["IT"]["pe"] > 0
    assert SECTOR_BENCHMARKS["AUTO"]["buzz"] != ""


def test_build_multi_factor_pipeline_structure():
    settings = Settings()
    # Test with standard ticker
    res = build_multi_factor_pipeline("BAJAJ-AUTO.NS", settings=settings)
    assert res["success"] is True
    assert res["ticker"] == "BAJAJ-AUTO.NS"

    # Check 6 Pillars presence
    assert "fundamentals" in res
    assert "industry_dynamics" in res
    assert "institutional_flows" in res
    assert "volume_surge" in res
    assert "price_action" in res
    assert "news_catalysts" in res

    # Pillar 1: Fundamentals
    fund = res["fundamentals"]
    assert "pe_ratio" in fund
    assert "return_on_equity_pct" in fund
    assert "debt_to_equity" in fund

    # Pillar 2: Industry Dynamics
    ind = res["industry_dynamics"]
    assert "sector_benchmark_pe" in ind
    assert "industry_buzz_tag" in ind
    assert "relative_pe_discount_pct" in ind

    # Pillar 3: Institutional Flows (FII & MF/DII)
    inst = res["institutional_flows"]
    assert "fii_holding_pct" in inst
    assert "dii_mf_holding_pct" in inst
    assert "institutional_appetite" in inst

    # Pillar 4: Volume Surge
    vol = res["volume_surge"]
    assert "volume_5d_63d_ratio" in vol
    assert "volume_surge_score" in vol

    # Pillar 5: Price Action
    pa = res["price_action"]
    assert "swing_structure" in pa


def test_format_pipeline_for_llm_prompt():
    settings = Settings()
    res = build_multi_factor_pipeline("TCS.NS", settings=settings)
    prompt_txt = format_pipeline_for_llm_prompt(res)

    assert "Institutional & Multi-Factor Intelligence Briefing" in prompt_txt
    assert "Valuation & Trading Fundamentals" in prompt_txt
    assert "Industry Dynamics & Sector Momentum" in prompt_txt
    assert "Institutional Flows & Smart Money" in prompt_txt
    assert "Volume & Deliverable Accumulation" in prompt_txt
    assert "Price Action & Swing Channels" in prompt_txt
    assert "Corporate Filings & News Sentiment" in prompt_txt
