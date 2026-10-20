"""Unit tests for multi-source deduplication and semantic event clustering."""

from datetime import datetime, timezone
import pytest

from earnings_engine.data.catalysts_news import (
    compute_title_similarity,
    cluster_and_deduplicate_news_events,
)
from earnings_engine.data.news_sources import (
    TIER_1_OFFICIAL,
    TIER_2_MAJOR_FINANCIAL_PRESS,
    TIER_3_AGGREGATORS,
)


def test_compute_title_similarity():
    """Verify title similarity correctly scores paraphrased headlines."""
    title_a = "L&T secures mega order worth Rs 2,500 crore from ONGC"
    title_b = "Larsen and Toubro bags Rs 2,500 cr offshore contract from ONGC"
    title_c = "TCS signs $500M IT infrastructure deal with European insurer"

    sim_ab = compute_title_similarity(title_a, title_b)
    sim_ac = compute_title_similarity(title_a, title_c)

    assert sim_ab >= 0.40, f"Expected similarity >= 0.40, got {sim_ab}"
    assert sim_ac < 0.20, f"Expected unrelated titles < 0.20, got {sim_ac}"


def test_three_articles_same_order_collapse_into_one():
    """Verify that 3 articles for the same order win collapse into one parent event with multi-source attribution."""
    articles = [
        {
            "id": 101,
            "ticker": "LT.NS",
            "title": "LT: Outcome of Board Meeting - Secures ₹2,500 crore offshore EPC contract from ONGC",
            "publisher": "NSE Corporate Disclosures",
            "source": "nse_announcements",
            "source_tier": TIER_1_OFFICIAL,
            "category": "Order Wins & Contracts",
            "impact_score": 85,
            "impact_level": "HIGH",
            "direction": "BULLISH",
            "published_at": "2026-10-20 09:30:00",
            "url": "https://nsearchives.nseindia.com/corporate/LT_20102026.pdf",
        },
        {
            "id": 102,
            "ticker": "LT.NS",
            "title": "L&T wins Rs 2,500 crore order from ONGC for offshore project",
            "publisher": "Economic Times",
            "source": "media_et_markets",
            "source_tier": TIER_2_MAJOR_FINANCIAL_PRESS,
            "category": "Order Wins & Contracts",
            "impact_score": 80,
            "impact_level": "HIGH",
            "direction": "BULLISH",
            "published_at": "2026-10-20 10:15:00",
            "url": "https://economictimes.indiatimes.com/markets/stocks/news/lt-wins-order/123",
        },
        {
            "id": 103,
            "ticker": "LT.NS",
            "title": "L&T shares surge on Rs 2,500 cr ONGC contract win",
            "publisher": "LiveMint",
            "source": "media_livemint",
            "source_tier": TIER_2_MAJOR_FINANCIAL_PRESS,
            "category": "Order Wins & Contracts",
            "impact_score": 78,
            "impact_level": "HIGH",
            "direction": "BULLISH",
            "published_at": "2026-10-20 11:00:00",
            "url": "https://livemint.com/market/stock-market-news/lt-shares-surge/456",
        },
    ]

    clustered = cluster_and_deduplicate_news_events(articles, window_hours=48)

    assert len(clustered) == 1, f"Expected 1 collapsed event, got {len(clustered)}"
    parent = clustered[0]

    # Primary item should be Tier 1 NSE announcement
    assert parent["publisher"] == "NSE Corporate Disclosures"
    assert parent["source_tier"] == TIER_1_OFFICIAL
    assert parent["verification_status"] == "EXCHANGE_VERIFIED"
    assert parent["cluster_size"] == 3

    # Corroborating sources must capture all 3 publishers
    assert set(parent["corroborating_sources"]) == {
        "NSE Corporate Disclosures",
        "Economic Times",
        "LiveMint",
    }

    # Duplicates / sub-articles should contain the remaining 2 articles
    assert len(parent["duplicates"]) == 2
    duplicate_publishers = [d["publisher"] for d in parent["duplicates"]]
    assert "Economic Times" in duplicate_publishers
    assert "LiveMint" in duplicate_publishers
    assert parent.get("story_cluster_id") is not None


def test_articles_outside_48h_window_do_not_cluster():
    """Verify that articles covering similar events outside the 48h window do NOT collapse."""
    articles = [
        {
            "id": 201,
            "ticker": "LT.NS",
            "title": "L&T secures ₹2,500 crore offshore EPC contract from ONGC",
            "publisher": "NSE Corporate Disclosures",
            "source_tier": TIER_1_OFFICIAL,
            "published_at": "2026-10-10 09:30:00",
        },
        {
            "id": 202,
            "ticker": "LT.NS",
            "title": "L&T secures ₹2,500 crore offshore EPC contract from ONGC",
            "publisher": "Economic Times",
            "source_tier": TIER_2_MAJOR_FINANCIAL_PRESS,
            "published_at": "2026-10-15 09:30:00",  # 5 days later (> 48 hours)
        },
    ]

    clustered = cluster_and_deduplicate_news_events(articles, window_hours=48)
    assert len(clustered) == 2, "Events > 48h apart should not be collapsed into one"


def test_different_tickers_do_not_cluster():
    """Articles with identical headline patterns for different tickers must not cluster."""
    articles = [
        {
            "id": 301,
            "ticker": "LT.NS",
            "title": "Wins mega EPC order worth Rs 2500 crore",
            "publisher": "Economic Times",
            "published_at": "2026-10-20 10:00:00",
        },
        {
            "id": 302,
            "ticker": "BHEL.NS",
            "title": "Wins mega EPC order worth Rs 2500 crore",
            "publisher": "Business Standard",
            "published_at": "2026-10-20 10:30:00",
        },
    ]

    clustered = cluster_and_deduplicate_news_events(articles, window_hours=48)
    assert len(clustered) == 2, "Different tickers must not be clustered together"


def test_multi_source_corroboration_elevation_in_clustering():
    """Two Tier 2 press reports without exchange filing get elevated to CORROBORATED."""
    articles = [
        {
            "id": 401,
            "ticker": "TCS.NS",
            "title": "TCS signs $500M cloud migration partnership with Deutsche Bank",
            "publisher": "Economic Times",
            "source_tier": TIER_2_MAJOR_FINANCIAL_PRESS,
            "published_at": "2026-10-20 10:00:00",
        },
        {
            "id": 402,
            "ticker": "TCS.NS",
            "title": "Deutsche Bank awards $500M digital cloud contract to TCS",
            "publisher": "Reuters India",
            "source_tier": TIER_2_MAJOR_FINANCIAL_PRESS,
            "published_at": "2026-10-20 10:45:00",
        },
        {
            "id": 403,
            "ticker": "INFY.NS",
            "title": "Infosys wins local banking mandate in APAC region",
            "publisher": "Google News",
            "source_tier": TIER_3_AGGREGATORS,
            "published_at": "2026-10-20 11:00:00",
        },
    ]

    clustered = cluster_and_deduplicate_news_events(articles, window_hours=48)
    assert len(clustered) == 2  # 1 TCS cluster, 1 INFY cluster

    tcs_cluster = next(c for c in clustered if c["ticker"] == "TCS.NS")
    infy_cluster = next(c for c in clustered if c["ticker"] == "INFY.NS")

    assert tcs_cluster["cluster_size"] == 2
    assert tcs_cluster["verification_status"] == "CORROBORATED"
    assert "Economic Times" in tcs_cluster["corroborating_sources"]
    assert "Reuters India" in tcs_cluster["corroborating_sources"]

    assert infy_cluster["cluster_size"] == 1
    assert infy_cluster["verification_status"] == "UNVERIFIED_SINGLE_SOURCE"
