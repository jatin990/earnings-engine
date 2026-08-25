"""Unit and integration tests for Quarter Repeaters & AI Forward Earnings Radar."""

import pytest
from starlette.testclient import TestClient

from earnings_engine.api.server import app
from earnings_engine.config import Settings
from earnings_engine.data.quarter_repeaters import (
    classify_industry_buzz,
    compute_beat_streak,
    generate_ai_repeater_forecast,
    get_cached_repeater_prediction,
    scan_quarter_repeaters,
    store_repeater_prediction,
)


def test_classify_industry_buzz():
    """Test classification of stocks into thematic buzz categories."""
    assert "EMS & High-Tech Electronics" in classify_industry_buzz("Dixon Technologies", "Consumer Electronics", "Technology", "DIXON.NS")
    assert "Defense & Aerospace" in classify_industry_buzz("Hindustan Aeronautics", "Aerospace & Defense", "Industrials", "HAL.NS")
    assert "Power & Renewable" in classify_industry_buzz("Tata Power", "Electric Utilities", "Utilities", "TATAPOWER.NS")
    assert "Auto & EV" in classify_industry_buzz("Tata Motors", "Auto Manufacturers", "Consumer Cyclical", "TATAMOTORS.NS")


def test_compute_beat_streak():
    """Test calculation of multi-quarter consecutive earnings beat streaks."""
    metrics_3q_beat = {
        "q1_earnings_score": 8,
        "q1_surprise_pct": 12.5,
        "q1_week_high_pct": 6.8,
        "q2_earnings_score": 7,
        "q2_surprise_pct": 4.2,
        "q2_week_high_pct": 3.5,
        "q3_earnings_score": 8,
        "q3_surprise_pct": 15.0,
        "q3_week_high_pct": 9.2,
    }
    streak, history = compute_beat_streak(metrics_3q_beat)
    assert streak == 3
    assert len(history) == 3

    metrics_broken_streak = {
        "q1_earnings_score": 8,
        "q1_surprise_pct": 8.0,
        "q2_earnings_score": 3,
        "q2_surprise_pct": -6.5,
        "q3_earnings_score": 8,
        "q3_surprise_pct": 10.0,
    }
    streak2, _ = compute_beat_streak(metrics_broken_streak)
    assert streak2 == 1


def test_ai_repeater_forecast_generation_and_storage(tmp_path):
    """Test on-demand AI repeater forecasting and database caching."""
    settings = Settings()
    forecast = generate_ai_repeater_forecast("TCS.NS", settings=settings)

    assert forecast["ticker"] == "TCS.NS"
    assert "ai_repeat_verdict" in forecast
    assert forecast["repeat_probability_pct"] >= 0
    assert len(forecast["primary_growth_drivers"]) > 0
    assert len(forecast["thesis"]) > 10

    cached = get_cached_repeater_prediction("TCS.NS", settings=settings)
    assert cached is not None
    assert cached["ticker"] == "TCS.NS"
    assert cached["ai_repeat_verdict"] == forecast["ai_repeat_verdict"]


def test_api_quarter_repeaters_endpoints():
    """Test GET /api/v1/earnings-radar/repeaters endpoint."""
    client = TestClient(app)

    res = client.get("/api/v1/earnings-radar/repeaters?universe=all&limit=10")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert "candidates" in data
    assert "summary" in data
    assert "dominant_industry_buzz" in data["summary"]


def test_api_single_repeater_forecast_endpoint():
    """Test POST /api/v1/earnings-radar/repeaters/forecast/{ticker} endpoint."""
    client = TestClient(app)

    res = client.post("/api/v1/earnings-radar/repeaters/forecast/INFY.NS")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["ticker"] == "INFY.NS"
    assert "forecast" in data
    assert data["forecast"]["ai_repeat_verdict"] in (
        "STRONG_REPEAT_BEAT",
        "MODERATE_BEAT",
        "IN_LINE",
        "RISK_OF_MISS",
    )
