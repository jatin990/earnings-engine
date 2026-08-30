"""Structured Data Models for Earnings Engine.

Provides type-safe Pydantic models for AI extraction, news intelligence,
catalyst analysis, financial projections, and temporal originality assessments.
"""

from __future__ import annotations

import json
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field, field_validator


class SentimentPolarity(str, Enum):
    """Sentiment polarity associated with news content."""
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


class TemporalOriginality(str, Enum):
    """Assessment of the news article's temporal originality."""
    NEW_PUBLICATION = "NEW_PUBLICATION"
    BREAKING = "BREAKING"
    DEVELOPING = "DEVELOPING"
    REPUBLICATION = "REPUBLICATION"


class FinancialProjections(BaseModel):
    """Explicitly stated price targets or financial projections extracted from news."""
    target_price: float | None = Field(default=None, description="Explicitly mentioned analyst price target or technical model target price in INR")
    stop_loss: float | None = Field(default=None, description="Defensive invalidation price or stop loss in INR")
    order_value_cr: float | None = Field(default=None, description="Explicit order win / contract value in Crore (₹ Cr)")
    revenue_projection_cr: float | None = Field(default=None, description="Projected future annual or quarterly revenue run-rate in Crore (₹ Cr)")
    ebitda_margin_pct: float | None = Field(default=None, description="Projected EBITDA / operating margin percentage")
    growth_rate_pct: float | None = Field(default=None, description="Projected YoY or QoQ revenue / PAT growth rate percentage")
    raw_projections: list[str] = Field(default_factory=list, description="List of verbatim projection quotes or key quantitative estimates")

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> FinancialProjections:
        if not data:
            return cls()
        return cls(
            target_price=data.get("target_price"),
            stop_loss=data.get("stop_loss"),
            order_value_cr=data.get("order_value_cr"),
            revenue_projection_cr=data.get("revenue_projection_cr"),
            ebitda_margin_pct=data.get("ebitda_margin_pct"),
            growth_rate_pct=data.get("growth_rate_pct"),
            raw_projections=data.get("raw_projections") or [],
        )


class NewsExtractedData(BaseModel):
    """Structured information extracted by the AI news analysis agent upon ingestion."""
    ticker: str = Field(..., description="Primary financial instrument's ticker symbol (e.g. TCS.NS, RELIANCE.NS)")
    stock_name: str | None = Field(default=None, description="Official company name")
    target_price: float | None = Field(default=None, description="Extracted price target in INR")
    stop_loss: float | None = Field(default=None, description="Defensive technical stop loss in INR")
    financial_projections: FinancialProjections = Field(default_factory=FinancialProjections, description="Financial projections & order estimates")
    sentiment: SentimentPolarity = Field(default=SentimentPolarity.NEUTRAL, description="Sentiment polarity (BULLISH, BEARISH, NEUTRAL)")
    direction: str = Field(default="NEUTRAL", description="Market direction alias (BULLISH, BEARISH, NEUTRAL)")
    temporal_originality: TemporalOriginality = Field(
        default=TemporalOriginality.NEW_PUBLICATION,
        description="Assessment of whether it is a new publication or republication of older content",
    )
    is_republication: bool = Field(default=False, description="True if the content is a re-broadcast or aggregation of previously disclosed historical news")
    originality_rationale: str = Field(default="", description="Explanation of why this is evaluated as new vs republication")
    impact_score: int = Field(default=50, ge=1, le=100, description="Quantitative catalyst impact magnitude score (0-100)")
    impact_level: str = Field(default="MEDIUM", description="Categorical impact level (HIGH, MEDIUM, LOW)")
    expected_horizon: str = Field(default="📅 1-3 Days", description="Expected price impact timeframe")
    volatility_est: str = Field(default="±2% to ±5%", description="Estimated price volatility range")
    trading_takeaway: str = Field(default="", description="1-2 sentences institutional trade rationale")
    confidence_pct: int = Field(default=75, ge=0, le=100, description="Model confidence score percentage")
    key_catalyst_triggers: list[str] = Field(default_factory=list, description="Extracted key driver triggers")
    primary_risk: str = Field(default="", description="Primary risk to the thesis")
    ai_model: str = Field(default="omniroute/ai-news-agent", description="AI model or engine utilized")
    ai_analyzed_at: str = Field(default="", description="UTC timestamp of extraction")

    @field_validator("ticker", mode="before")
    @classmethod
    def clean_ticker(cls, v: Any) -> str:
        if not v:
            return "UNKNOWN"
        t = str(v).strip().upper()
        return t

    @field_validator("direction", mode="before")
    @classmethod
    def sync_direction(cls, v: Any, info: Any) -> str:
        if v:
            v_str = str(v).strip().upper()
            if v_str in ("BULLISH", "BEARISH", "NEUTRAL"):
                return v_str
        return "NEUTRAL"

    def to_db_dict(self) -> dict[str, Any]:
        """Convert extracted payload to dictionary format ready for db.py / sqlite persistence."""
        proj_dict = self.financial_projections.model_dump()
        return {
            "ticker": self.ticker,
            "sentiment": self.sentiment.value if isinstance(self.sentiment, SentimentPolarity) else str(self.sentiment),
            "direction": self.direction,
            "target_price": self.target_price,
            "stop_loss": self.stop_loss,
            "financial_projections": json.dumps(proj_dict),
            "temporal_originality": self.temporal_originality.value if isinstance(self.temporal_originality, TemporalOriginality) else str(self.temporal_originality),
            "is_republication": 1 if self.is_republication else 0,
            "originality_rationale": self.originality_rationale,
            "impact_score": self.impact_score,
            "impact_level": self.impact_level,
            "expected_horizon": self.expected_horizon,
            "volatility_est": self.volatility_est,
            "trading_takeaway": self.trading_takeaway,
            "confidence_pct": self.confidence_pct,
            "key_catalyst_triggers": json.dumps(self.key_catalyst_triggers),
            "primary_risk": self.primary_risk,
            "ai_model": self.ai_model,
            "ai_analyzed_at": self.ai_analyzed_at,
        }
