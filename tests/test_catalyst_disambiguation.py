"""Unit tests for analyst commentary vs real corporate action catalyst disambiguation."""

import pytest

from earnings_engine.data.catalysts_news import (
    score_catalyst_headline,
    disambiguate_ticker_for_headline,
)


def test_analyst_predicts_order_win_not_classified_as_order_win():
    """Analyst speculation / prediction must NOT be classified as an actual corporate Order Win."""
    headline = "Analyst predicts order win for L&T in upcoming quarter"
    summary = "Brokerage sees strong pipeline and expects company to bag large defense deals."

    res = score_catalyst_headline(headline, summary)

    assert res["category"] != "Order Wins & Contracts", (
        f"Analyst prediction should not be classified as Order Wins & Contracts, got {res['category']}"
    )
    assert res["category"] == "Analyst Ratings & Targets"


def test_brokerage_speculation_modals_not_classified_as_order_win():
    """Headlines with speculative modals ('could win', 'may win', 'likely to bag', 'eyes order') are not corporate order wins."""
    speculative_cases = [
        ("Jefferies sees L&T winning mega railway contract", "Analyst Ratings & Targets"),
        ("Could BHEL win Rs 5,000 crore thermal power tender? Brokerage view", "Analyst Ratings & Targets"),
        ("Tata Power likely to bag major solar project: Report", "Analyst Ratings & Targets"),
        ("Stock XYZ may win defense deal says Nomura", "Analyst Ratings & Targets"),
        ("L&T eyeing order worth Rs 3,000 cr in Middle East: Sources", "Analyst Ratings & Targets"),
    ]

    for title, expected_category in speculative_cases:
        res = score_catalyst_headline(title)
        assert res["category"] != "Order Wins & Contracts", (
            f"Speculative headline '{title}' was erroneously classified as Order Wins & Contracts"
        )
        assert res["category"] in ("Analyst Ratings & Targets", "General Financial News")


def test_actual_corporate_order_wins_preserved():
    """Legitimate confirmed corporate order wins must continue to be classified as Order Wins & Contracts."""
    confirmed_cases = [
        "L&T wins Rs 2,500 crore offshore contract from ONGC",
        "BHEL bags Rs 4,000 crore thermal power plant order from NTPC",
        "KEC International secures new transmission orders worth Rs 1,142 crore",
        "Tata Power receives letter of award for 200MW solar project",
    ]

    for title in confirmed_cases:
        res = score_catalyst_headline(title)
        assert res["category"] == "Order Wins & Contracts", (
            f"Confirmed order win '{title}' failed to classify as Order Wins & Contracts"
        )
        assert res["direction"] == "BULLISH"
        assert res["impact_score"] >= 75


def test_downward_regulatory_action_strictly_bearish():
    """USFDA Form 483 / Warning letters / regulatory penalties must strictly be BEARISH, never BULLISH."""
    adverse_cases = [
        "USFDA issues Form 483 with 10 observations for Dr Reddy's Srikakulam plant",
        "USFDA issues warning letter to Sun Pharma Dadra facility",
        "SEBI imposes penalty of Rs 25 lakh on company and promoters",
        "Pollution Control Board issues closure notice for manufacturing unit",
    ]

    for title in adverse_cases:
        res = score_catalyst_headline(title)
        assert res["direction"] == "BEARISH", (
            f"Adverse regulatory headline '{title}' should be BEARISH, got {res['direction']}"
        )
        assert res["category"] in ("Litigation, Risk & Probes", "Regulatory, Approvals & Policy")


def test_generic_idea_disambiguation():
    """Generic usage of word 'idea' should not match IDEA.NS (Vodafone Idea)."""
    generic_text = "RBI governor shares idea for central bank digital currency expansion"
    result_ticker = disambiguate_ticker_for_headline("IDEA.NS", generic_text, "")
    assert result_ticker is None, f"Generic word 'idea' should not match IDEA.NS, got {result_ticker}"

    telecom_text = "Vodafone Idea completes 5G spectrum rollout in 17 circles"
    result_telecom = disambiguate_ticker_for_headline("IDEA.NS", telecom_text, "")
    assert result_telecom == "IDEA.NS"
