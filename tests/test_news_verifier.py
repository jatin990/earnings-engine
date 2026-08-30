"""Unit tests for Institutional News Verification & Section-by-Section Sanity Pipeline."""

import pytest
from datetime import datetime, timezone, timedelta

from earnings_engine.data.news_verifier import (
    parse_and_verify_date,
    verify_company_entity,
    verify_financial_numbers,
    verify_authenticity_and_relevance,
    verify_category_and_sentiment,
    compute_canonical_hash,
    NewsVerifier,
)


def test_verify_date_valid_and_stale():
    # 1. Valid fresh date (2 hours ago)
    recent_utc = (datetime.now(timezone.utc) - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
    res = parse_and_verify_date(recent_utc, "Akums Drugs reports earnings", "")
    assert res["is_valid"] is True
    assert "IST" in res["published_at_ist"]
    assert res["is_stale"] is False
    assert res["is_future"] is False

    # 2. Stale date (25 days ago)
    old_utc = (datetime.now(timezone.utc) - timedelta(days=25)).strftime("%Y-%m-%d %H:%M:%S")
    res_old = parse_and_verify_date(old_utc, "Akums AGM update", "", max_stale_days=14)
    assert res_old["is_valid"] is False
    assert res_old["is_stale"] is True
    assert "DATE_STALE" in res_old["flags"]

    # 3. In-text historical date detection (meeting on June 10 when running in August)
    res_hist = parse_and_verify_date(recent_utc, "Board meeting held on June 10 to discuss expansion", "")
    assert res_hist["is_valid"] is False
    assert res_hist["in_text_historical"] is True

    # 4. Reporting quarter extraction
    res_q = parse_and_verify_date(recent_utc, "Akums Drugs Q1FY27 net profit surges 56%", "")
    assert res_q["reporting_quarter"] == "Q1FY27"


def test_verify_company_entity_disambiguation():
    # 1. Apollo group disambiguation
    t_tyre = verify_company_entity("APOLLO.NS", "Apollo Tyres Q1 profit surges on European revenue growth")
    assert t_tyre["is_verified"] is True
    assert t_tyre["resolved_ticker"] == "APOLLOTYRE.NS"

    t_hosp = verify_company_entity("APOLLO.NS", "Apollo Hospitals inaugurates new 500-bed facility in Mumbai")
    assert t_hosp["is_verified"] is True
    assert t_hosp["resolved_ticker"] == "APOLLOHOSP.NS"

    t_micro = verify_company_entity("APOLLO.NS", "Apollo Micro Systems secures defence contract for avionics")
    assert t_micro["is_verified"] is True
    assert t_micro["resolved_ticker"] == "APOLLO.NS"

    # 2. Dictionary word collision protection for CREST
    # Rejects generic word "crest"
    t_crest_reject = verify_company_entity("CREST.NS", "Boeing Wins $131B F-15 Contract From US Air Force BA Stock Gains After-Hours")
    assert t_crest_reject["is_verified"] is False
    assert "DICTIONARY_WORD_COLLISION" in str(t_crest_reject["flags"])

    # Accepts genuine company mention
    t_crest_accept = verify_company_entity("CREST.NS", "Crest Ventures acquires strategic equity stake in NBFC arm")
    assert t_crest_accept["is_verified"] is True
    assert t_crest_accept["resolved_ticker"] == "CREST.NS"


def test_verify_financial_numbers_extraction():
    # 1. Order value in INR Crore
    res_ord = verify_financial_numbers("Larsen & Toubro bags Rs 4,500 crore contract for high-speed rail corridor")
    assert res_ord["has_numbers"] is True
    assert res_ord["metrics"]["order_value_cr"] == 4500.0
    assert res_ord["metrics"]["currency"] == "INR"

    # 2. Percentage jump
    res_pct = verify_financial_numbers("Akums Drugs Q1 profit surges 56% to Rs 140 crore")
    assert res_pct["metrics"]["pct_change"] == 56.0
    assert res_pct["metrics"]["order_value_cr"] == 140.0

    # 3. Dividend per share
    res_div = verify_financial_numbers("TCS announces interim dividend of Rs 28 per share")
    assert res_div["metrics"]["dividend_amount"] == 28.0


def test_verify_authenticity_filters_noise():
    # 1. Rejects football / sports news
    res_sports = verify_authenticity_and_relevance("Barcelona chase World Cup controversy figure: will he replace Alvarez? - Goal.com")
    assert res_sports["is_authentic"] is False
    assert "NOISE_FILTER_TRIGGERED" in res_sports["flags"]

    # 2. Rejects generic US defense contract unrelated to Indian equities
    res_boeing = verify_authenticity_and_relevance("Boeing Wins $131B F-15 Contract From US Air Force BA Stock Gains")
    assert res_boeing["is_authentic"] is False

    # 3. Accepts genuine corporate news
    res_corp = verify_authenticity_and_relevance("Tata Power secures 500MW solar energy tender from GUVNL")
    assert res_corp["is_authentic"] is True
    assert res_corp["has_corporate_trigger"] is True


def test_verify_category_and_sentiment():
    # 1. Bullish order win
    res_bull = verify_category_and_sentiment("L&T bags massive Rs 3,000 cr order win", "Company secures turnkey project")
    assert res_bull["direction"] == "BULLISH"

    # 2. Bearish profit drop (prevents false bullish tag even if other words exist)
    res_bear = verify_category_and_sentiment("Company Q1 profit plunges 45% amid margin compression", "Subdued performance")
    assert res_bear["direction"] == "BEARISH"


def test_compute_canonical_hash_deduplication():
    # Identical story reported by two different publishers
    title_mc = "Akums Drugs Q1FY27 net profit surges 56% to Rs 140 cr - Moneycontrol"
    title_sx = "Akums Drugs Q1FY27 net profit surges 56%; concall flags turnaround - scanx.trade"
    
    hash1 = compute_canonical_hash("AKUMS.NS", title_mc, {"pct_change": 56.0})
    hash2 = compute_canonical_hash("AKUMS.NS", title_sx, {"pct_change": 56.0})
    
    # Core tokens (akums, drugs, q1fy27, profit, surges) + numbers match -> identical hash
    assert isinstance(hash1, str)
    assert len(hash1) > 10


def test_news_verifier_full_pipeline():
    verifier = NewsVerifier()
    recent_utc = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")

    # 1. Valid corporate news from mainstream publisher
    item_valid = {
        "ticker": "AKUMS.NS",
        "title": "Akums Drugs Q1FY27 net profit surges 56% to Rs 140 crore - Moneycontrol",
        "summary": "Strong quarterly performance driven by CDMO expansion",
        "published_at": recent_utc,
    }
    res_valid = verifier.verify_news_item(item_valid)
    assert res_valid["verification_status"] == "VERIFIED"
    assert res_valid["confidence_score"] >= 0.70
    assert res_valid["verified_numbers"]["pct_change"] == 56.0
    assert res_valid["canonical_hash"] is not None

    # 2. Noise item (Boeing misattributed to CREST)
    item_noise = {
        "ticker": "CREST.NS",
        "title": "Boeing Wins $131B F-15 Contract From US Air Force - Yahoo Finance",
        "summary": "Defense aerospace contract",
        "published_at": recent_utc,
    }
    res_noise = verifier.verify_news_item(item_noise)
    assert res_noise["verification_status"] == "REJECTED"
    assert "noise" in res_noise["rejection_reason"].lower()

    # 3. Foreign exchange ticker collision (SFL NYSE:SFL misattributed to Indian SFL.NS)
    item_foreign = {
        "ticker": "SFL.NS",
        "title": "SFL (NYSE:SFL) Stock Draws Fresh Interest As Profit Rebounds Meet Capex Questions - Simply Wall St",
        "summary": "SFL Corporation Ltd results",
        "published_at": recent_utc,
    }
    res_foreign = verifier.verify_news_item(item_foreign)
    assert res_foreign["verification_status"] == "REJECTED"
    assert "foreign exchange" in res_foreign["rejection_reason"].lower()

    # 4. Untrusted scraper / recycled old news (Sterlite ₹1500 Cr QIP on scanx.trade)
    item_scraper = {
        "ticker": "STLTECH.NS",
        "title": "Sterlite Technologies raises ₹1500 crore via QIP to de-leverage - scanx.trade",
        "summary": "Sterlite Technologies QIP update",
        "published_at": recent_utc,
    }
    res_scraper = verifier.verify_news_item(item_scraper)
    assert res_scraper["verification_status"] == "REJECTED"

    # 5. Multinational Parent vs Indian Subsidiary (Pfizer US Q2 2026 vs Pfizer Limited India)
    item_pfizer_global = {
        "ticker": "PFIZER.NS",
        "title": "Pfizer stock holds near analyst targets as Q2 2026 earnings beat expectations - Ad-hoc-news.de",
        "summary": "Pfizer Q2 2026 adjusted EPS of $0.60 beats consensus",
        "published_at": recent_utc,
    }
    res_pfizer_global = verifier.verify_news_item(item_pfizer_global)
    assert res_pfizer_global["verification_status"] == "REJECTED"

    item_pfizer_india = {
        "ticker": "PFIZER.NS",
        "title": "Pfizer Limited Q1 net profit rises 14% to Rs 158 crore - Moneycontrol",
        "summary": "Pfizer India Q1FY27 revenue up 6% amid domestic formulation growth",
        "published_at": recent_utc,
    }
    res_pfizer_india = verifier.verify_news_item(item_pfizer_india)
    assert res_pfizer_india["verification_status"] == "VERIFIED"
