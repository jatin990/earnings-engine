"""Tests for Kronos prediction outcome evaluation and accuracy aggregation."""

import pytest
from earnings_engine.data.predictions import evaluate_prediction_outcome, get_kronos_accuracy_summary


def test_evaluate_prediction_outcome_bullish_worked():
    """Bullish forecast where price rose should be evaluated as WORKED."""
    res = evaluate_prediction_outcome(
        predicted_price=100.0,
        predicted_return_pct=5.0,
        predicted_trend="Bullish",
        current_price=106.0,
    )
    assert res["status"] == "WORKED"
    assert res["is_correct"] is True
    assert "Worked" in res["label"]
    assert res["actual_delta"] == 6.0
    assert res["actual_delta_pct"] == 6.0


def test_evaluate_prediction_outcome_bullish_failed():
    """Bullish forecast where price dropped should be evaluated as FAILED."""
    res = evaluate_prediction_outcome(
        predicted_price=100.0,
        predicted_return_pct=5.0,
        predicted_trend="Bullish",
        current_price=95.0,
    )
    assert res["status"] == "FAILED"
    assert res["is_correct"] is False
    assert "Failed" in res["label"]
    assert res["actual_delta"] == -5.0


def test_evaluate_prediction_outcome_bearish_worked():
    """Bearish forecast where price dropped should be evaluated as WORKED."""
    res = evaluate_prediction_outcome(
        predicted_price=100.0,
        predicted_return_pct=-8.0,
        predicted_trend="Bearish",
        current_price=92.0,
    )
    assert res["status"] == "WORKED"
    assert res["is_correct"] is True
    assert "Worked" in res["label"]


def test_evaluate_prediction_outcome_bearish_failed():
    """Bearish forecast where price rose should be evaluated as FAILED."""
    res = evaluate_prediction_outcome(
        predicted_price=100.0,
        predicted_return_pct=-8.0,
        predicted_trend="Bearish",
        current_price=105.0,
    )
    assert res["status"] == "FAILED"
    assert res["is_correct"] is False
    assert "Failed" in res["label"]


def test_evaluate_prediction_outcome_pending():
    """Missing or invalid price should return PENDING."""
    res = evaluate_prediction_outcome(
        predicted_price=None,
        predicted_return_pct=5.0,
        predicted_trend="Bullish",
        current_price=100.0,
    )
    assert res["status"] == "PENDING"
    assert res["is_correct"] is None


def test_benchmark_ohlcv_forecast():
    """Verify daily bar comparison and metric calculations against realized prices."""
    from earnings_engine.data.predictions import benchmark_ohlcv_forecast

    forecast_series = [
        {"date": "2026-08-18", "open": 100.0, "high": 105.0, "low": 98.0, "close": 104.0, "volume": 10000},
        {"date": "2026-08-19", "open": 104.0, "high": 108.0, "low": 102.0, "close": 107.0, "volume": 12000},
        {"date": "2026-08-20", "open": 107.0, "high": 110.0, "low": 105.0, "close": 109.0, "volume": 15000},
    ]

    actual_prices = [
        {"date": "2026-08-18", "open": 100.5, "high": 104.5, "low": 99.0, "close": 103.5, "volume": 11000},
        {"date": "2026-08-19", "open": 103.8, "high": 107.5, "low": 103.0, "close": 106.8, "volume": 13000},
        # 2026-08-20 is not yet settled
    ]

    res = benchmark_ohlcv_forecast(forecast_series, actual_prices=actual_prices)
    summary = res["summary"]
    bars = res["bars"]

    assert summary["total_bars"] == 3
    assert summary["settled_bars"] == 2
    assert summary["upcoming_bars"] == 1
    assert summary["corridor_hit_pct"] == 100.0  # Both days settled inside predicted [L, H] range
    assert summary["mape_pct"] < 1.0  # Very small % error
    assert summary["is_evaluated"] is True

    assert bars[0]["status"] == "SETTLED"
    assert bars[0]["actual_close"] == 103.5
    assert bars[0]["corridor_hit"] is True

    assert bars[2]["status"] == "UPCOMING"
    assert bars[2]["actual_close"] is None

