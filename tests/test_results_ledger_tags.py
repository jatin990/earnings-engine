"""Tests for multi-dimensional institutional tags in Results Ledger."""

import pytest
from earnings_engine.reports.render import build_institutional_tags


def test_build_institutional_tags():
    sample_row = {
        "ticker": "INFY.NS",
        "pct_from_52w_high": -1.8,  # Within 2.5% of high -> Testing 52W High
        "pct_from_52w_low": 42.0,
        "rel_vol_5d_vs_63d": 2.4,   # Vol surge >= 2.0x
        "beat_rate_pct": 87.5,
        "total_historical_quarters": 8,
        "source": "nse",
        "news_items": [
            {
                "title": "Infosys inks $450M cloud deal",
                "category": "ORDER_WIN",
                "impact_level": "HIGH",
                "direction": "POSITIVE",
            }
        ],
        "is_breakout_active": True,
        "breakout_score": 78,
    }
    tags = build_institutional_tags(sample_row)
    tag_labels = [t["label"] for t in tags]

    assert any("Order Win" in l for l in tag_labels)
    assert any("52W High" in l for l in tag_labels)
    assert any("Vol Surge" in l for l in tag_labels)
    assert any("Breakout" in l or "Elite" in l for l in tag_labels)
    assert any("NSE" in l or "Exchange" in l for l in tag_labels)


def test_build_institutional_tags_unconfirmed_source():
    sample_row = {
        "ticker": "ESTIMATE.NS",
        "pct_from_52w_high": -30.0,
        "pct_from_52w_low": 2.0,   # Near 52W low
        "beat_rate_pct": 20.0,
        "total_historical_quarters": 6,
        "source": "yfinance",
    }
    tags = build_institutional_tags(sample_row)
    tag_labels = [t["label"] for t in tags]

    assert any("Unconfirmed" in l or "Projected" in l for l in tag_labels)
    assert any("52W Low" in l for l in tag_labels)
    assert any("Misser" in l or "Lagging" in l for l in tag_labels)
