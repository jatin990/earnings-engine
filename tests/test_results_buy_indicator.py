"""Tests for the Results tab 4-pillar quantitative Buy Indicator scoring engine."""

import pandas as pd
import pytest

from earnings_engine.reports.render import compute_buy_indicator


def test_compute_buy_indicator_strong_buy():
    """Verify high-conviction bullish profile yields STRONG BUY signal."""
    row = {
        "channel_position_pct": 20.0,  # Near support (P1: 15)
        "technical_setup": {"label": "🚀 Momentum Breakout"},  # High reward setup (P1: 10)
        "pct_from_52w_high": -3.5,  # Within 10% of 52W high (P1: 5) -> P1 = 30
        "beat_rate_pct": 100.0,  # 4/4 beats (P2: 15)
        "total_historical_quarters": 4,
        "prev_3q_earnings_score": 8.0,  # High quality (P2: ~8.9) -> P2 = 23.9
        "seven_day_return_pct": 4.5,  # Strong momentum (P3: 7)
        "thirty_day_return_pct": 9.2,  # Strong momentum (P3: 8)
        "rel_vol_5d_vs_63d": 2.5,  # Volume surge (P3: 10) -> P3 = 25
    }
    consensus_pred = {
        "consensus_direction": "STRONG BULLISH",
        "consensus_return_pct": 5.2,
    }
    row["kronos_14d"] = {"trend": "Bullish", "return_pct": 4.0}
    row["gbm_prediction"] = {"direction": "UP", "confidence": 0.82}

    res = compute_buy_indicator(row, consensus_pred=consensus_pred)
    assert res["signal"] == "STRONG BUY"
    assert res["score"] >= 75
    assert "signal-strong-buy" in res["badge_class"]
    assert "STRONG BUY" in res["badge_html"]
    assert res["pillars"]["technical"] == 30.0
    assert res["pillars"]["momentum"] == 25.0
    assert not res["pillars"]["rescaled"]


def test_compute_buy_indicator_avoid():
    """Verify breakdown profile with heavy overhead resistance yields AVOID signal."""
    row = {
        "channel_position_pct": 92.0,  # Extreme resistance (P1: 0)
        "technical_setup": {"label": "⚠️ Support Breakdown"},  # Breakdown (P1: 1)
        "pct_from_52w_high": -38.0,  # Far below 52W high (P1: 1) -> P1 = 2
        "beat_rate_pct": 15.0,  # Poor track record (P2: 0)
        "total_historical_quarters": 4,
        "prev_3q_earnings_score": 2.0,  # Low quality (P2: ~2.2) -> P2 = 2.2
        "seven_day_return_pct": -6.2,  # Falling (P3: 0)
        "thirty_day_return_pct": -12.5,  # Falling (P3: 0)
        "rel_vol_5d_vs_63d": 0.4,  # Anemic vol (P3: 1) -> P3 = 1
    }
    consensus_pred = {
        "consensus_direction": "BEARISH",
        "consensus_return_pct": -4.0,
    }
    row["kronos_14d"] = {"trend": "Bearish", "return_pct": -5.0}
    row["gbm_prediction"] = {"direction": "DOWN", "confidence": 0.75}

    res = compute_buy_indicator(row, consensus_pred=consensus_pred)
    assert res["signal"] == "AVOID"
    assert res["score"] < 35
    assert "signal-avoid" in res["badge_class"]


def test_compute_buy_indicator_dynamic_rescaling_without_ai():
    """Verify zero-token on-demand fairness: when no AI models have run, score rescales to 100%."""
    # Good technicals and beat rate, but NO AI models run yet
    row = {
        "channel_position_pct": 25.0,  # 15
        "technical_setup": {"label": "🎯 S/R Bounce"},  # 10
        "pct_from_52w_high": -5.0,  # 5 -> P1 = 30
        "beat_rate_pct": 80.0,  # 15
        "total_historical_quarters": 4,
        "prev_3q_earnings_score": 7.0,  # (7/9)*10 = 7.78 -> P2 = 22.78
        "seven_day_return_pct": 2.0,  # 5
        "thirty_day_return_pct": 3.0,  # 5
        "rel_vol_5d_vs_63d": 1.4,  # 7 -> P3 = 17
        # Total pillars 1-3 = 30 + 22.78 + 17 = 69.78 out of 80
        # Rescaled: (69.78 / 80) * 100 = 87.2 -> STRONG BUY
    }

    res = compute_buy_indicator(row, consensus_pred=None)
    assert res["pillars"]["rescaled"] is True
    assert res["score"] >= 75
    assert res["signal"] == "STRONG BUY"
    assert "Dynamic Re-scale" in res["tooltip"]


def test_compute_buy_indicator_defaults_and_missing_data():
    """Verify handling of completely empty row does not crash and produces neutral score."""
    res = compute_buy_indicator({}, consensus_pred=None)
    assert isinstance(res["score"], int)
    assert 0 <= res["score"] <= 100
    assert res["signal"] in ("STRONG BUY", "BUY", "ACCUMULATE", "NEUTRAL", "AVOID")
    assert "data-buy-score" in res["badge_html"] or "signal-badge" in res["badge_html"]


def test_build_upcoming_results_fragments_includes_buy_indicator():
    """Verify that build_upcoming_results_fragments renders the buy indicator column and data attributes."""
    from earnings_engine.reports.render import build_upcoming_results_fragments

    df = pd.DataFrame([
        {
            "ticker": "INFY.NS",
            "company_name": "Infosys Ltd",
            "earnings_date": "2026-10-20",
            "source": "nse",
            "market_cap": 800000000000.0,
            "industry": "IT Services",
            "current_price": 1850.0,
            "channel_position_pct": 25.0,
            "beat_rate_pct": 100.0,
            "total_historical_quarters": 4,
            "seven_day_return_pct": 3.5,
            "thirty_day_return_pct": 6.2,
            "rel_vol_5d_vs_63d": 1.8,
        }
    ])

    fragments = build_upcoming_results_fragments(df, on_demand=True)
    assert fragments["total_stocks"] == 1
    sec = fragments["sections"][0]
    stock_entry = sec["stocks"][0]
    assert stock_entry["ticker"] == "INFY.NS"
    row_html = stock_entry["row_html"]

    # Verify column 3 cell is present with signal badge
    assert "cell-action-signal" in row_html
    assert "signal-badge" in row_html
    assert "data-buy-score=" in row_html
    assert "data-buy-signal=" in row_html

