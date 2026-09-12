"""Unit tests for news feeds metadata and status endpoint."""

import pytest
from earnings_engine.data.news_sources import get_all_feed_metadata, NSE_STATIC_RSS_FEEDS


def test_get_all_feed_metadata_coverage():
    feeds = get_all_feed_metadata()
    assert len(feeds) >= 40

    # Ensure all NSE static RSS feeds are present
    nse_rss_feeds = [f for f in feeds if f.get("source_key") == "nse_rss"]
    assert len(nse_rss_feeds) == len(NSE_STATIC_RSS_FEEDS)
    assert any(f["name"] == "NSE Insider Trading" for f in nse_rss_feeds)
    assert any(f["name"] == "NSE Daily Buyback" for f in nse_rss_feeds)
    assert any(f["name"] == "NSE Corporate Actions" for f in nse_rss_feeds)

    # Ensure RBI and Media feeds are present
    assert any(f["name"] == "RBI Press Releases" for f in feeds)
    assert any("MoneyControl" in f["name"] for f in feeds)
    assert any("Business Today" in f["name"] for f in feeds)
    assert any("USFDA" in f["name"] for f in feeds)


@pytest.mark.anyio
async def test_get_news_feeds_status_endpoint():
    from earnings_engine.api.routers.news import get_news_feeds_status

    result = await get_news_feeds_status()
    assert result.get("success") is True
    assert result.get("total_feeds") >= 40
    assert "harvester_schedule" in result
    assert "feeds" in result

    feeds = result["feeds"]
    for f in feeds:
        assert "name" in f
        assert "url" in f
        assert "type" in f
        assert "group" in f
        assert "status" in f
