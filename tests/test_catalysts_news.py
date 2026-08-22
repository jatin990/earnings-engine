"""Tests for Short-Term Impact News & Catalyst Scanner."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from earnings_engine.api.server import app
from earnings_engine.config import Settings
from earnings_engine.data.catalysts_news import (
    score_catalyst_headline,
    fetch_ticker_catalysts,
    get_short_term_catalysts,
    get_catalyst_summary_stats,
    scan_watchlist_catalysts,
)


def test_score_catalyst_headline_order_win():
    headline = "L&T bags massive Rs 4,500 crore international railway contract"
    res = score_catalyst_headline(headline, "Multi-year deal secures strong revenue visibility")
    assert res["impact_score"] >= 75
    assert res["impact_level"] == "HIGH"
    assert res["category"] == "Order Wins & Contracts"
    assert res["direction"] == "BULLISH"
    assert "1-2 Days" in res["expected_horizon"]
    assert "Why this matters" in res["why_it_matters"] or len(res["why_it_matters"]) > 10


def test_score_catalyst_headline_earnings_surprise():
    headline = "Tata Motors Q3 net profit surges 137% on record JLR margins"
    res = score_catalyst_headline(headline, "Revenue beats street expectations with strong EBITDA expansion")
    assert res["impact_score"] >= 75
    assert res["category"] == "Earnings & Guidance Surprise"
    assert res["direction"] == "BULLISH"


def test_score_catalyst_headline_litigation_risk():
    headline = "SEBI issues show-cause notice and initiates probe against promoter group"
    res = score_catalyst_headline(headline, "Allegations of fund diversion under preliminary inquiry")
    assert res["impact_score"] >= 75
    assert res["category"] == "Litigation, Risk & Probes"
    assert res["direction"] == "BEARISH"


def test_fetch_and_cache_catalysts(tmp_path):
    settings = Settings(data_dirs={"prices": tmp_path, "earnings": tmp_path})
    settings.ensure_dirs()

    # Score and store test items
    items = fetch_ticker_catalysts("RELIANCE.NS", limit=4, settings=settings)
    assert isinstance(items, list)

    stats = get_catalyst_summary_stats(settings)
    assert "total_catalysts" in stats
    assert "high_impact_count" in stats

    filtered = get_short_term_catalysts(limit=10, settings=settings)
    assert isinstance(filtered, list)


def test_catalyst_api_endpoints():
    client = TestClient(app)

    # 1. Catalyst feed endpoint
    res = client.get("/api/v1/news/catalysts?limit=5")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert "catalysts" in data

    # 2. Catalyst stats endpoint
    res_stats = client.get("/api/v1/news/catalyst-stats")
    assert res_stats.status_code == 200
    stats_data = res_stats.json()
    assert stats_data["success"] is True
    assert "stats" in stats_data

    # 3. Catalyst scan endpoint
    res_scan = client.post("/api/v1/news/scan", json={"watchlist": "NSE_TOP"})
    assert res_scan.status_code == 200
    scan_data = res_scan.json()
    assert scan_data["success"] is True
