"""Test suite for Kronos prediction audit merge tolerance (±0.5%)."""

import tempfile
import pytest
from earnings_engine.config import Settings
from earnings_engine.data.predictions import store_prediction, load_prediction_history


@pytest.fixture
def temp_settings(tmp_path):
    s = Settings()
    s.data_dirs["prices"] = tmp_path
    s.ensure_dirs()
    from earnings_engine.data.migrations import apply_migrations
    apply_migrations(s)
    return s


def test_kronos_prediction_insert_and_merge(temp_settings):
    ticker = "RELIANCE.NS"

    payload1 = {
        "symbol": ticker,
        "current_price": 3000.0,
        "support": 2950.0,
        "resistance": 3100.0,
        "return_pct": 3.2,
        "trend": "Bullish",
        "lookback": 120,
        "pred_len": 14,
        "explanation": "Initial forecast",
    }

    id1 = store_prediction(ticker, temp_settings, payload1, merge_tolerance_pct=0.5)
    assert id1 > 0

    hist1 = load_prediction_history(ticker, settings=temp_settings)
    assert len(hist1) == 1
    assert hist1[0]["return_pct"] == 3.2

    # Second prediction within ±0.5% (e.g. 3.4% vs 3.2% -> Δ = 0.2%)
    payload2 = {
        "symbol": ticker,
        "current_price": 3005.0,
        "support": 2955.0,
        "resistance": 3110.0,
        "return_pct": 3.4,
        "trend": "Bullish",
        "lookback": 120,
        "pred_len": 14,
        "explanation": "Refined forecast within 0.2%",
    }

    id2 = store_prediction(ticker, temp_settings, payload2, merge_tolerance_pct=0.5)
    # Should merge into the same row ID!
    assert id2 == id1

    hist2 = load_prediction_history(ticker, settings=temp_settings)
    assert len(hist2) == 1
    assert hist2[0]["return_pct"] == 3.4
    assert hist2[0]["explanation"] == "Refined forecast within 0.2%"

    # Third prediction with large shift (> 0.5% e.g. 5.1%)
    payload3 = {
        "symbol": ticker,
        "current_price": 3020.0,
        "support": 2960.0,
        "resistance": 3150.0,
        "return_pct": 5.1,
        "trend": "Bullish",
        "lookback": 120,
        "pred_len": 14,
        "explanation": "Breakout expansion forecast",
    }

    id3 = store_prediction(ticker, temp_settings, payload3, merge_tolerance_pct=0.5)
    # Should create a NEW row!
    assert id3 > id1

    hist3 = load_prediction_history(ticker, settings=temp_settings)
    assert len(hist3) == 2
