"""
Unit tests for Reg 30 High-Impact Stream Classifier, Storage, and Routing.
"""

import pytest
import sqlite3
from earnings_engine.processing.reg30_classifier import classify_reg30_filing, extract_order_value_cr
from earnings_engine.db.reg30_storage import (
    init_reg30_db,
    insert_reg30_disclosure,
    fetch_reg30_stream,
    fetch_reg30_stats,
)


def test_order_value_extraction():
    text1 = "Company has bagged a major order worth Rs. 145.50 Crore from PSU entity."
    assert extract_order_value_cr(text1) == 145.50

    text2 = "Received purchase order for INR 50 Cr."
    assert extract_order_value_cr(text2) == 50.0

    text3 = "General meeting intimation without financial number."
    assert extract_order_value_cr(text3) is None


def test_reg30_classification_order_win():
    headline = "Receipt of Letter of Award (LOA) for Turnkey Solar EPC Project"
    desc = "Awarded contract valued at Rs. 210 Cr."
    result = classify_reg30_filing(headline, desc)
    assert result is not None
    assert result["category"] == "ORDER_WIN"
    assert result["sentiment"] == "BULLISH"
    assert result["impact_level"] == "HIGH"
    assert result["order_value_cr"] == 210.0


def test_reg30_classification_auditor_resignation():
    headline = "Resignation of Statutory Auditor of the Company"
    desc = "Intimation under Reg 30 regarding resignation of M/s ABC & Co before term completion."
    result = classify_reg30_filing(headline, desc)
    assert result is not None
    assert result["category"] == "AUDITOR_RESIGN"
    assert result["sentiment"] == "BEARISH"
    assert result["impact_level"] == "CRITICAL"


def test_reg30_classification_downgrade():
    headline = "Credit Rating Downgrade by CRISIL Ratings"
    desc = "Long-term bank loan facilities revised downward from A to BBB- with negative outlook."
    result = classify_reg30_filing(headline, desc)
    assert result is not None
    assert result["category"] == "RATING_DOWNGRADE"
    assert result["sentiment"] == "BEARISH"
    assert result["impact_level"] == "HIGH"


def test_reg30_classification_noise_filter():
    headline = "Trading Window Closure for Q2 Results"
    desc = "Trading window shall remain closed from October 1 until 48 hours after declaration."
    result = classify_reg30_filing(headline, desc)
    assert result is None

    headline2 = "Loss of Share Certificate Intimation"
    result2 = classify_reg30_filing(headline2, "")
    assert result2 is None

    headline3 = "CRISIL Re-affirmation of Credit Rating"
    result3 = classify_reg30_filing(headline3, "")
    assert result3 is None


def test_reg30_storage_flow():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_reg30_db(conn=conn)

    item = {
        "id": "hash123",
        "symbol": "RATNAVEER",
        "bse_code": "543978",
        "company_name": "Ratnaveer Precision Engineering Ltd",
        "timestamp": "2026-09-18T10:30:00",
        "category": "ORDER_WIN",
        "category_name": "Order Win / Contract",
        "sentiment": "BULLISH",
        "impact_level": "HIGH",
        "headline": "Secured major export order worth Rs 120 Cr",
        "description": "Order to be executed in 6 months",
        "order_value_cr": 120.0,
        "pdf_url": "https://www.bseindia.com/test.pdf",
        "source": "BSE",
    }

    inserted = insert_reg30_disclosure(item, conn=conn)
    assert inserted is True

    # Deduplication test
    dup_inserted = insert_reg30_disclosure(item, conn=conn)
    assert dup_inserted is False

    # Stream fetching
    stream = fetch_reg30_stream(conn=conn)
    assert len(stream) == 1
    assert stream[0]["symbol"] == "RATNAVEER"
    assert stream[0]["sentiment"] == "BULLISH"

    # Stats fetching
    stats = fetch_reg30_stats(conn=conn)
    assert stats["total_disclosures"] == 1
    assert stats["by_sentiment"]["BULLISH"] == 1
    assert len(stats["by_category"]) == 1
    assert stats["by_category"][0]["category"] == "ORDER_WIN"
    conn.close()
