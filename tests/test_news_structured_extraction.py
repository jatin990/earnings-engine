"""Unit tests for Structured Information Extraction in AI News Ingestion Pipeline.

Tests verification of:
1. Primary financial instrument's ticker symbol
2. Explicitly stated price targets or financial projections
3. Sentiment polarity (BULLISH, BEARISH, NEUTRAL)
4. Assessment of temporal originality (NEW_PUBLICATION vs REPUBLICATION)
5. Integration with data models (models.py) and persistence layer (db.py)
"""

import json
import pytest
from earnings_engine.config import Settings
from earnings_engine.data.models import (
    FinancialProjections,
    NewsExtractedData,
    SentimentPolarity,
    TemporalOriginality,
)
from earnings_engine.data.omniroute_client import OmniRouteClient
from earnings_engine.data.ai_news_analyzer import (
    analyze_news_catalyst_ai,
    extract_structured_news_data,
    build_news_analysis_prompt,
)
from earnings_engine.data.db import get_db_connection
from earnings_engine.data.migrations import apply_migrations
from earnings_engine.data.news_pipeline import (
    ensure_news_verification_schema,
    process_and_verify_news_items,
    save_verified_news_records,
)
from earnings_engine.data.catalysts_news import get_short_term_catalysts


@pytest.fixture
def test_settings(tmp_path, monkeypatch):
    monkeypatch.delenv("TURSO_DATABASE_URL", raising=False)
    monkeypatch.delenv("TURSO_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("EARNINGS_ENGINE_DB_PATH", raising=False)
    monkeypatch.setenv("EARNINGS_ENGINE_DB_NAME", f"test_{tmp_path.name}.sqlite3")
    s = Settings()
    s.data_dirs["prices"] = tmp_path
    s.data_dirs["earnings"] = tmp_path
    s.ensure_dirs()
    apply_migrations(s)
    return s


def test_models_schema_and_serialization():
    """Verify NewsExtractedData and FinancialProjections Pydantic validation & DB dict formatting."""
    projections = FinancialProjections(
        target_price=2450.0,
        stop_loss=2180.0,
        order_value_cr=1250.0,
        revenue_projection_cr=4500.0,
        ebitda_margin_pct=24.5,
        growth_rate_pct=18.0,
        raw_projections=["Order Win: ₹1,250 Cr", "Margin: 24.5%"],
    )

    data = NewsExtractedData(
        ticker="LT.NS",
        stock_name="Larsen & Toubro",
        target_price=2450.0,
        stop_loss=2180.0,
        financial_projections=projections,
        sentiment=SentimentPolarity.BULLISH,
        direction="BULLISH",
        temporal_originality=TemporalOriginality.NEW_PUBLICATION,
        is_republication=False,
        originality_rationale="Fresh primary disclosure of mega infrastructure order win.",
        impact_score=88,
        impact_level="HIGH",
        expected_horizon="📅 1-3 Days",
        volatility_est="±4% to ±8%",
        trading_takeaway="Significant order accretion expands FY27 revenue visibility.",
        confidence_pct=92,
        key_catalyst_triggers=["Mega Infrastructure Order Win"],
        primary_risk="Execution delays in raw material procurement.",
    )

    assert data.ticker == "LT.NS"
    assert data.sentiment == SentimentPolarity.BULLISH
    assert data.temporal_originality == TemporalOriginality.NEW_PUBLICATION
    assert not data.is_republication
    assert data.financial_projections.order_value_cr == 1250.0

    db_dict = data.to_db_dict()
    assert db_dict["ticker"] == "LT.NS"
    assert db_dict["sentiment"] == "BULLISH"
    assert db_dict["temporal_originality"] == "NEW_PUBLICATION"
    assert db_dict["is_republication"] == 0
    assert "order_value_cr" in db_dict["financial_projections"]


def test_heuristic_extraction_fresh_breaking_news(test_settings):
    """Verify deterministic extraction of price targets, order projections, sentiment, and fresh originality."""
    client = OmniRouteClient(settings=test_settings)
    raw_item = {
        "ticker": "BHEL.NS",
        "stock_name": "Bharat Heavy Electricals Ltd",
        "title": "BHEL bags massive ₹4,200 Cr thermal power EPC order, EBITDA margin expected at 18%",
        "summary": "State-run BHEL has won a ₹4,200 crore contract for setting up a supercritical power plant. Revenue to surge by 22%.",
        "signal_price": 280.0,
        "current_price": 285.0,
        "published_at": "2026-08-30 10:00:00",
    }

    extracted = client.fallback_heuristic_analysis(raw_item)
    assert extracted["ticker"] == "BHEL.NS"
    assert extracted["sentiment"] == "BULLISH"
    assert extracted["direction"] == "BULLISH"
    assert extracted["target_price"] is not None and extracted["target_price"] > 280.0
    assert extracted["stop_loss"] is not None and extracted["stop_loss"] < 280.0
    
    # Financial projections verification
    proj = extracted["financial_projections"]
    assert proj["order_value_cr"] == 4200.0
    assert proj["ebitda_margin_pct"] == 18.0
    assert proj["growth_rate_pct"] == 22.0

    # Temporal originality verification (Breaking / New)
    assert extracted["temporal_originality"] in ("BREAKING", "NEW_PUBLICATION")
    assert not extracted["is_republication"]
    assert "primary" in extracted["originality_rationale"].lower() or "fresh" in extracted["originality_rationale"].lower() or "urgency" in extracted["originality_rationale"].lower()


def test_heuristic_extraction_republication_detection(test_settings):
    """Verify detection of republication when news references older historical events."""
    client = OmniRouteClient(settings=test_settings)
    raw_item = {
        "ticker": "TCS.NS",
        "stock_name": "Tata Consultancy Services",
        "title": "TCS reiterates Q1 deal win from earlier reported US client in 2024",
        "summary": "IT major TCS repeats its previous commentary on the legacy contract as reported earlier months ago.",
        "signal_price": 4200.0,
        "current_price": 4200.0,
        "published_at": "2026-08-30 11:30:00",
    }

    extracted = client.fallback_heuristic_analysis(raw_item)
    assert extracted["ticker"] == "TCS.NS"
    assert extracted["temporal_originality"] == "REPUBLICATION"
    assert extracted["is_republication"] is True
    assert "historical" in extracted["originality_rationale"].lower() or "previously" in extracted["originality_rationale"].lower() or "recap" in extracted["originality_rationale"].lower()


def test_extract_structured_news_data_model_wrapper(test_settings):
    """Verify extract_structured_news_data returns a valid NewsExtractedData Pydantic instance."""
    raw_item = {
        "ticker": "RELIANCE.NS",
        "stock_name": "Reliance Industries",
        "title": "Reliance bags major ₹8,500 Cr green energy contract with margin up by 15%",
        "summary": "Jio green energy division secures ₹8,500 crore solar project.",
        "signal_price": 2950.0,
        "current_price": 2980.0,
    }

    data: NewsExtractedData = extract_structured_news_data(raw_item, settings=test_settings)
    assert isinstance(data, NewsExtractedData)
    assert data.ticker == "RELIANCE.NS"
    assert data.sentiment == SentimentPolarity.BULLISH
    assert data.financial_projections.order_value_cr == 8500.0
    assert data.target_price is not None and data.target_price > 2950.0
    assert not data.is_republication


def test_pipeline_ingestion_and_sqlite_persistence(test_settings):
    """Verify end-to-end news ingestion, structured verification, and database storage in SQLite."""
    raw_items = [
        {
            "ticker": "TATAMOTORS.NS",
            "stock_name": "Tata Motors Ltd",
            "title": "Tata Motors bags ₹3,600 Cr electric bus order from state transport",
            "summary": "Tata Motors secures supply contract of ₹3,600 Cr for 2,500 EV buses. Margin projected at 12%.",
            "link": "https://example.com/news/tatamotors-ev-order",
            "publisher": "AutoNews",
            "published_at": "2026-08-30 08:30:00",
            "source": "test_rss",
        }
    ]

    # Process and verify
    verified = process_and_verify_news_items(raw_items, settings=test_settings)
    assert len(verified) == 1
    rec = verified[0]
    assert rec["ticker"] == "TATAMOTORS.NS"
    assert rec["sentiment"] == "BULLISH"
    assert rec["temporal_originality"] in ("BREAKING", "NEW_PUBLICATION")
    assert rec["is_republication"] == 0
    
    # Check financial projections field
    proj = json.loads(rec["financial_projections"])
    assert proj["order_value_cr"] == 3600.0

    # Persist to database
    saved_count = save_verified_news_records(verified, settings=test_settings)
    assert saved_count == 1

    # Query back using get_short_term_catalysts
    catalysts = get_short_term_catalysts(watchlist_or_universe="ALL", days=14, settings=test_settings)
    assert len(catalysts) >= 1
    saved = next(c for c in catalysts if c["ticker"] == "TATAMOTORS.NS")
    assert saved["sentiment"] == "BULLISH"
    assert saved["temporal_originality"] in ("BREAKING", "NEW_PUBLICATION")
    assert saved["is_republication"] == 0
    assert "order_value_cr" in saved["financial_projections"]


def test_news_ai_deduplication_and_db_caching(test_settings, monkeypatch):
    """Verify that news items already analyzed and present in the DB are NOT re-queried via AI."""
    import earnings_engine.data.ai_news_analyzer as analyzer_mod

    call_count = 0
    orig_analyze = analyzer_mod.analyze_news_catalyst_ai

    def mock_analyze(ctx, settings=None):
        nonlocal call_count
        call_count += 1
        return orig_analyze(ctx, settings=settings)

    monkeypatch.setattr(analyzer_mod, "analyze_news_catalyst_ai", mock_analyze)

    item = {
        "ticker": "TATAMOTORS.NS",
        "stock_name": "Tata Motors Ltd",
        "title": "Tata Motors wins ₹5,000 Cr commercial vehicle fleet order with 16% margin",
        "summary": "Tata Motors bags landmark order from state logistics corporation.",
        "link": "https://example.com/tatamotors-fleet",
        "publisher": "AutoNews",
        "published_at": "2026-08-30 11:00:00",
        "source": "rss_feed",
    }

    # 1. First run: should call analyze_news_catalyst_ai once
    v1 = process_and_verify_news_items([item], settings=test_settings)
    assert len(v1) == 1
    assert call_count == 1
    save_verified_news_records(v1, settings=test_settings)

    # 2. Duplicate in subsequent fetch/harvest run: should NOT call analyze_news_catalyst_ai again
    v2 = process_and_verify_news_items([item, item], settings=test_settings)
    assert len(v2) == 1
    assert call_count == 1  # Still 1! Reused from DB / in-memory cache

    # 3. Explicit force_reanalyze: should call AI again
    v3 = process_and_verify_news_items([item], settings=test_settings, force_reanalyze=True)
    assert len(v3) == 1
    assert call_count == 2  # Re-executed because force_reanalyze=True

