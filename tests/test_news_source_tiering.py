"""Unit tests for source tiering and exchange disclosure cross-referencing."""

from datetime import datetime, timezone
import pytest

from earnings_engine.data.news_sources import (
    get_source_tier,
    get_source_credibility_score,
    TIER_1_OFFICIAL,
    TIER_2_MAJOR_FINANCIAL_PRESS,
    TIER_3_AGGREGATORS,
)
from earnings_engine.data.catalysts_news import (
    cross_reference_exchange_disclosure,
    determine_catalyst_verification_status,
)


def test_source_tier_classification():
    """Verify that official exchange feeds are Tier 1, major press is Tier 2, and aggregators are Tier 3."""
    # Tier 1: Official / Primary
    assert get_source_tier(publisher="NSE Corporate Disclosures", source="nse_announcements") == TIER_1_OFFICIAL
    assert get_source_tier(publisher="BSE Corporate Filings", source="bse_announcements") == TIER_1_OFFICIAL
    assert get_source_tier(publisher="NSE Announcements", source="nse_rss") == TIER_1_OFFICIAL
    assert get_source_tier(publisher="RBI Press Releases", source="rbi_rss") == TIER_1_OFFICIAL
    assert get_source_tier(publisher="NEAPS Press Releases") == TIER_1_OFFICIAL
    assert get_source_credibility_score(publisher="NSE Announcements") == 1.0

    # Tier 2: Major Financial Press
    assert get_source_tier(publisher="Economic Times") == TIER_2_MAJOR_FINANCIAL_PRESS
    assert get_source_tier(publisher="ET Markets") == TIER_2_MAJOR_FINANCIAL_PRESS
    assert get_source_tier(publisher="Business Standard") == TIER_2_MAJOR_FINANCIAL_PRESS
    assert get_source_tier(publisher="LiveMint") == TIER_2_MAJOR_FINANCIAL_PRESS
    assert get_source_tier(publisher="Reuters India") == TIER_2_MAJOR_FINANCIAL_PRESS
    assert get_source_tier(publisher="Bloomberg") == TIER_2_MAJOR_FINANCIAL_PRESS
    assert get_source_tier(publisher="NDTV Profit") == TIER_2_MAJOR_FINANCIAL_PRESS
    assert get_source_tier(publisher="The Hindu BusinessLine") == TIER_2_MAJOR_FINANCIAL_PRESS
    assert get_source_credibility_score(publisher="Economic Times") >= 0.80

    # Tier 3: Aggregators / Syndication / Search
    assert get_source_tier(publisher="Google News Markets") == TIER_3_AGGREGATORS
    assert get_source_tier(publisher="MoneyControl") == TIER_3_AGGREGATORS
    assert get_source_tier(publisher="Yahoo Finance") == TIER_3_AGGREGATORS
    assert get_source_tier(publisher="Unknown Blog") == TIER_3_AGGREGATORS
    assert get_source_credibility_score(publisher="Google News") <= 0.60


def test_exchange_verified_directly_from_tier1():
    """News originating directly from Tier 1 (NSE/BSE) must be EXCHANGE_VERIFIED immediately."""
    item = {
        "ticker": "LT.NS",
        "title": "LT: Outcome of Board Meeting - Wins ₹2,500 crore offshore EPC contract",
        "publisher": "NSE Corporate Disclosures",
        "source": "nse_announcements",
        "category": "Order Wins & Contracts",
        "published_at": "2026-10-20 10:00:00",
    }
    status, flags = determine_catalyst_verification_status(item, matching_filings=[])
    assert status == "EXCHANGE_VERIFIED"
    assert "TIER_1_PRIMARY_DISCLOSURE" in flags


def test_exchange_cross_reference_matches_disclosure(tmp_path):
    """Tier 2 press article cross-referenced against an exchange disclosure gets EXCHANGE_VERIFIED."""
    from earnings_engine.config import Settings
    from earnings_engine.data.catalysts_news import _connect

    settings = Settings(data_dirs={"prices": tmp_path, "earnings": tmp_path})
    settings.ensure_dirs()

    # Seed an official exchange filing in SQLite
    with _connect(settings) as conn:
        conn.execute(
            """
            INSERT INTO news_catalysts (
                ticker, title, publisher, source, published_at,
                impact_score, impact_level, category, direction,
                expected_horizon, volatility_est, created_at, verification_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "LT.NS",
                "L&T: Intimation under Reg 30 - Secures Mega Order worth Rs 2500 Cr",
                "NSE Corporate Disclosures",
                "nse_announcements",
                "2026-10-20 09:30:00",
                85,
                "HIGH",
                "Order Wins & Contracts",
                "BULLISH",
                "1-2 Days",
                "±4% to ±9%",
                "2026-10-20 09:30:00",
                "EXCHANGE_VERIFIED",
            ),
        )
        conn.commit()

    press_article = {
        "ticker": "LT.NS",
        "title": "L&T shares rally after winning ₹2,500 crore mega order",
        "publisher": "Economic Times",
        "source": "media_et_markets",
        "category": "Order Wins & Contracts",
        "published_at": "2026-10-20 10:30:00",
    }

    matching_filings = cross_reference_exchange_disclosure(
        ticker="LT.NS",
        headline=press_article["title"],
        published_at="2026-10-20 10:30:00",
        settings=settings,
    )
    assert len(matching_filings) > 0

    status, flags = determine_catalyst_verification_status(
        press_article,
        matching_filings=matching_filings,
    )
    assert status == "EXCHANGE_VERIFIED"
    assert "EXCHANGE_DISCLOSURE_CORROBORATED" in flags


def test_multi_source_corroboration_without_filing():
    """Tier 2 articles corroborated by multiple independent Tier 2 sources become CORROBORATED."""
    press_article = {
        "ticker": "TCS.NS",
        "title": "TCS signs $500 million cloud transformation pact with European bank",
        "publisher": "Economic Times",
        "source": "media_et_markets",
        "category": "Order Wins & Contracts",
        "published_at": "2026-10-20 11:00:00",
    }
    independent_sources = ["Economic Times", "LiveMint", "Business Standard"]
    status, flags = determine_catalyst_verification_status(
        press_article,
        matching_filings=[],
        corroborating_sources=independent_sources,
    )
    assert status == "CORROBORATED"
    assert "MULTI_SOURCE_CORROBORATED" in flags


def test_single_unverified_source():
    """A single Tier 2 or Tier 3 article without exchange filing or corroboration is UNVERIFIED_SINGLE_SOURCE."""
    single_article = {
        "ticker": "INFY.NS",
        "title": "Infosys may win multi-million dollar defense contract says blog",
        "publisher": "Google News",
        "source": "google_rss",
        "category": "Order Wins & Contracts",
        "published_at": "2026-10-20 12:00:00",
    }
    status, flags = determine_catalyst_verification_status(
        single_article,
        matching_filings=[],
        corroborating_sources=["Google News"],
    )
    assert status == "UNVERIFIED_SINGLE_SOURCE"
    assert "SINGLE_SOURCE_UNCONFIRMED" in flags
