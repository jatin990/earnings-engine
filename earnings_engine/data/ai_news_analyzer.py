"""Free AI News & Catalyst Analysis Engine powered by diegosouzapw/OmniRoute.

Executes real-time quantitative and structural catalyst analysis using diegosouzapw/OmniRoute
(https://github.com/diegosouzapw/OmniRoute) - an open-source self-hosted multi-LLM proxy and gateway
(defaulting to http://localhost:20128/v1) with quota-aware routing across 350+ providers
and deterministic fallback when offline.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from earnings_engine.config import Settings
from earnings_engine.data.omniroute_client import (
    DEFAULT_OMNIROUTER_MODELS,
    OMNIROUTE_SYSTEM_PROMPT,
    OmniRouteClient,
)

logger = logging.getLogger("earnings_engine.data.ai_news_analyzer")

# Global client cache
_omniroute_client: OmniRouteClient | None = None


def get_omniroute_client(settings: Settings | None = None) -> OmniRouteClient:
    """Return shared OmniRouteClient instance."""
    global _omniroute_client
    if _omniroute_client is None:
        _omniroute_client = OmniRouteClient(settings=settings)
    return _omniroute_client


def get_omniroute_endpoint(settings: Settings | None = None) -> str:
    """Resolve the active OmniRoute chat completions URL from client."""
    client = OmniRouteClient(settings=settings)
    return client.get_completions_url()


def get_omniroute_api_key(settings: Settings | None = None) -> str:
    """Resolve OmniRoute API key from client."""
    client = OmniRouteClient(settings=settings)
    return client.get_api_key()


# Backwards-compatibility aliases
get_omnirouter_endpoint = get_omniroute_endpoint
get_omnirouter_api_key = get_omniroute_api_key


def build_news_analysis_prompt(item: dict[str, Any]) -> str:
    """Format structured context for the OmniRoute news analysis."""
    client = get_omniroute_client()
    return client.format_prompt(item)


def _heuristic_fallback_analysis(item: dict[str, Any]) -> dict[str, Any]:
    """Fast deterministic rule-based analysis used when offline or without API keys."""
    client = get_omniroute_client()
    return client.fallback_heuristic_analysis(item)


def analyze_news_catalyst_ai(
    item: dict[str, Any],
    settings: Settings | None = None,
    preferred_model: str | None = None,
    timeout: int = 15,
) -> dict[str, Any]:
    """Execute AI analysis of a news catalyst using diegosouzapw/OmniRoute with heuristic fallback."""
    client = get_omniroute_client(settings)
    return client.analyze_catalyst(item, preferred_model=preferred_model, timeout=timeout)


def extract_structured_news_data(
    item: dict[str, Any],
    settings: Settings | None = None,
    preferred_model: str | None = None,
    timeout: int = 15,
) -> Any:
    """Execute structured information extraction returning a type-safe NewsExtractedData model instance."""
    from earnings_engine.data.models import FinancialProjections, NewsExtractedData, SentimentPolarity, TemporalOriginality

    raw = analyze_news_catalyst_ai(item, settings=settings, preferred_model=preferred_model, timeout=timeout)
    proj_raw = raw.get("financial_projections") or {}
    if not isinstance(proj_raw, dict):
        proj_raw = {}

    financial_projections = FinancialProjections.from_dict(proj_raw)
    if raw.get("target_price") and not financial_projections.target_price:
        financial_projections.target_price = raw.get("target_price")
    if raw.get("stop_loss") and not financial_projections.stop_loss:
        financial_projections.stop_loss = raw.get("stop_loss")

    raw_sentiment = (raw.get("sentiment") or raw.get("direction") or "NEUTRAL").upper()
    try:
        sentiment = SentimentPolarity(raw_sentiment)
    except Exception:
        sentiment = SentimentPolarity.NEUTRAL

    raw_orig = (raw.get("temporal_originality") or "NEW_PUBLICATION").upper()
    try:
        temporal_orig = TemporalOriginality(raw_orig)
    except Exception:
        temporal_orig = TemporalOriginality.REPUBLICATION if raw.get("is_republication") else TemporalOriginality.NEW_PUBLICATION

    return NewsExtractedData(
        ticker=(raw.get("ticker") or item.get("ticker") or "UNKNOWN").strip().upper(),
        stock_name=item.get("stock_name"),
        target_price=raw.get("target_price"),
        stop_loss=raw.get("stop_loss"),
        financial_projections=financial_projections,
        sentiment=sentiment,
        direction=sentiment.value,
        temporal_originality=temporal_orig,
        is_republication=bool(raw.get("is_republication", temporal_orig == TemporalOriginality.REPUBLICATION)),
        originality_rationale=raw.get("originality_rationale", ""),
        impact_score=int(raw.get("impact_score", 50)),
        impact_level=raw.get("impact_level", "MEDIUM"),
        expected_horizon=raw.get("expected_horizon", "📅 1-3 Days"),
        volatility_est=raw.get("volatility_est", "±2% to ±5%"),
        trading_takeaway=raw.get("trading_takeaway", ""),
        confidence_pct=int(raw.get("confidence_pct", 75)),
        key_catalyst_triggers=raw.get("key_catalyst_triggers") or [],
        primary_risk=raw.get("primary_risk", ""),
        ai_model=raw.get("ai_model", "omniroute/ai-news-agent"),
        ai_analyzed_at=raw.get("ai_analyzed_at", ""),
    )
