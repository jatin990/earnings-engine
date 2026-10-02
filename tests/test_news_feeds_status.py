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
        assert "id" in f
        assert "last_scanned_at" in f
        assert "last_articles_fetched" in f
        assert "last_articles_added" in f


def test_record_and_get_feed_runs(tmp_path):
    from earnings_engine.config import Settings
    from earnings_engine.data.catalysts_news import (
        record_feed_run,
        record_feed_runs_batch,
        get_latest_feed_runs,
    )

    settings = Settings(data_dirs={"prices": tmp_path, "earnings": tmp_path})
    settings.ensure_dirs()

    # Record single feed run
    record_feed_run(
        feed_id="nse_rss_insider",
        feed_name="NSE Insider Trading",
        source_key="nse_rss",
        articles_fetched=10,
        articles_added=3,
        status="ok",
        settings=settings,
    )

    # Record batch of feed runs
    batch = [
        {
            "feed_id": "rbi_press_releases",
            "feed_name": "RBI Press Releases",
            "source_key": "rbi_rss",
            "articles_fetched": 5,
            "articles_added": 0,
            "status": "ok",
        },
        {
            "feed_id": "bse_filings_api",
            "feed_name": "BSE Filings & Announcements API",
            "source_key": "bse_filings",
            "articles_fetched": 12,
            "articles_added": 4,
            "status": "ok",
        },
    ]
    record_feed_runs_batch(batch, settings=settings)

    latest = get_latest_feed_runs(settings=settings)
    assert "nse_rss_insider" in latest
    assert latest["nse_rss_insider"]["articles_fetched"] == 10
    assert latest["nse_rss_insider"]["articles_added"] == 3
    assert latest["nse_rss_insider"]["status"] == "ok"

    assert "rbi_press_releases" in latest
    assert latest["rbi_press_releases"]["articles_added"] == 0

    assert "bse_filings_api" in latest
    assert latest["bse_filings_api"]["articles_added"] == 4


def test_save_verified_news_records_with_feed_breakdown(tmp_path):
    from earnings_engine.config import Settings
    from earnings_engine.data.news_pipeline import save_verified_news_records_with_feed_breakdown

    settings = Settings(data_dirs={"prices": tmp_path, "earnings": tmp_path})
    settings.ensure_dirs()

    records = [
        {
            "ticker": "INFY.NS",
            "stock_name": "Infosys",
            "title": "Infosys signs $1B cloud deal with global enterprise",
            "summary": "Multi-year deal expands strategic partnership",
            "publisher": "Moneycontrol",
            "published_at": "2026-09-14 10:00:00",
            "feed_id": "media_moneycontrol",
            "feed_name": "MoneyControl Markets",
            "impact_score": 85,
            "impact_level": "HIGH",
            "category": "Order Wins & Contracts",
            "direction": "BULLISH",
        },
        {
            "ticker": "TCS.NS",
            "stock_name": "Tata Consultancy Services",
            "title": "TCS secures AI transformation contract",
            "summary": "Large scale deployment",
            "publisher": "NSE India",
            "published_at": "2026-09-14 10:30:00",
            "feed_id": "nse_rss_corporate_actions",
            "feed_name": "NSE Corporate Actions",
            "impact_score": 80,
            "impact_level": "HIGH",
            "category": "Order Wins & Contracts",
            "direction": "BULLISH",
        }
    ]

    # First insert: 2 new records
    added, breakdown = save_verified_news_records_with_feed_breakdown(records, settings=settings)
    assert added == 2
    assert breakdown.get("media_moneycontrol") == 1
    assert breakdown.get("nse_rss_corporate_actions") == 1

    # Second insert with same records: 0 new records (deduplicated by ticker+title)
    added_again, breakdown_again = save_verified_news_records_with_feed_breakdown(records, settings=settings)
    assert added_again == 0
    assert len(breakdown_again) == 0

