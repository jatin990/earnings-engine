import pytest
from earnings_engine.data.news_sources import (
    NSE_STATIC_RSS_FEEDS,
    _parse_rss_date,
    fetch_nse_static_rss_feeds,
)
from earnings_engine.data.catalysts_news import score_catalyst_headline
from earnings_engine.data.news_verifier import NewsVerifier


def test_nse_static_rss_feeds_configuration():
    """Verify that key NSE archive feeds are configured."""
    feed_names = [name for _, name, _ in NSE_STATIC_RSS_FEEDS]
    assert "NSE Announcements" in feed_names
    assert "NSE Corporate Actions" in feed_names
    assert "NSE Insider Trading" in feed_names
    assert "NSE Daily Buyback" in feed_names
    assert "NSE Board Meetings" in feed_names
    assert "NSE SAST Reg 29 (Substantial Acquisition)" in feed_names


def test_nse_date_parser_formats():
    """Verify custom NSE date timestamp parsing."""
    d1 = _parse_rss_date("12-Sep-2026 13:16:59")
    assert d1.startswith("2026-09-12")

    d2 = _parse_rss_date("2026-09-11 18:36:55")
    assert d2 == "2026-09-11 18:36:55"

    d3 = _parse_rss_date("08-Sep-2026 12:35")
    assert d3.startswith("2026-09-08")


def test_score_catalyst_headline_for_nse_disclosures():
    """Verify catalyst scoring rules on buyback, insider trading, and corporate actions."""
    # Corporate action
    res_ca = score_catalyst_headline(
        "VSTTILLERS: Corporate Action (Ex-Date: 16-Sep-2026)",
        "SERIES:EQ |PURPOSE:DIVIDEND - RS 25 PER SHARE |RECORD DATE:16-Sep-2026",
    )
    assert res_ca["category"] == "Corporate Action & Dividends"
    assert res_ca["impact_score"] >= 65

    # Buyback
    res_bb = score_catalyst_headline(
        "SIS: Daily Share Buy-Back Update",
        "SUBJECT : Daily Buy-Back of equity shares",
    )
    assert res_bb["category"] == "Corporate Action & Dividends"

    # Insider trading
    res_it = score_catalyst_headline(
        "QUESS: Insider Trading Disclosure (Reg 7(2))",
        "QUESS|Quess Corp Limited|Original|Regulation 7 (2)",
    )
    assert res_it["category"] == "Management, Governance & Ratings"


def test_news_verifier_handles_nse_rss_item():
    """Verify that NewsVerifier validates and resolves NSE static RSS events."""
    verifier = NewsVerifier()
    item = {
        "title": "SIS: Daily Share Buy-Back Update",
        "summary": "SUBJECT : Daily Buy-Back of equity shares",
        "published_at": "2026-09-11 18:36:55",
        "publisher": "NSE Daily Buyback",
        "link": "https://nsearchives.nseindia.com/corporate/SIS_11092026183556_Intimation.pdf",
        "ticker": "SIS.NS",
        "source": "nse_rss",
    }
    v_res = verifier.verify_news_item(item)
    assert v_res["verification_status"] == "VERIFIED"
    assert v_res["resolved_ticker"] == "SIS.NS"
