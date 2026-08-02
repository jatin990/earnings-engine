"""Tests for the Kronos prediction audit persistence layer."""

import json

import pandas as pd
import pytest

from earnings_engine.config import Settings
from earnings_engine.data import predictions as pred_mod


@pytest.fixture
def settings(tmp_path):
    """A Settings pointing at a temporary SQLite cache (no real data touched)."""
    s = Settings()
    s.data_dirs = {"prices": tmp_path / "prices", "earnings": tmp_path / "earnings"}
    s.ensure_dirs()
    return s


def _sample_payload(ticker_suffix: str = "NS"):
    """A realistic forecast dict as produced by predict_single_stock."""
    symbol = f"TCS.{ticker_suffix}"
    return {
        "symbol": symbol,
        "name": "TCS",
        "current_price": 4100.0,
        "support": 4050.0,
        "resistance": 4250.0,
        "return_pct": 3.50,
        "trend": "Bullish",
        "results_date": "04 Aug 2026",
        "last_week_change_pct": 1.2,
        "explanation": "TCS shows positive momentum.",
    }


def test_store_and_load_prediction_history_roundtrip(settings):
    """A stored prediction is retrievable with its full JSON payload expanded."""
    payload = _sample_payload()
    rowid = pred_mod.store_prediction("TCS.NS", settings, payload,
                                      run_at="2026-08-01 09:00:00",
                                      predicted_at="2026-08-01 09:00:00")
    assert rowid > 0

    history = pred_mod.load_prediction_history(settings=settings)
    assert len(history) == 1

    row = history[0]
    assert row["ticker"] == "TCS.NS"
    assert row["run_at"] == "2026-08-01 09:00:00"
    assert row["predicted_at"] == "2026-08-01 09:00:00"
    assert row["current_price"] == 4100.0
    assert row["support"] == 4050.0
    assert row["resistance"] == 4250.0
    assert row["return_pct"] == 3.50
    assert row["trend"] == "Bullish"
    # Full payload preserved verbatim.
    assert row["prediction"]["symbol"] == "TCS.NS"
    assert row["prediction"]["explanation"] == "TCS shows positive momentum."


def test_load_latest_predictions_collapses_to_one_per_ticker(settings):
    """Latest view returns only the most-recent run per ticker."""
    earlier = _sample_payload()
    later = _sample_payload()
    later["return_pct"] = 7.25
    later["trend"] = "Bullish"

    pred_mod.store_prediction("TCS.NS", settings, earlier, run_at="2026-08-01 09:00:00")
    pred_mod.store_prediction("TCS.NS", settings, later, run_at="2026-08-02 10:00:00")

    latest = pred_mod.load_latest_predictions(settings=settings)
    assert len(latest) == 1
    assert latest[0]["ticker"] == "TCS.NS"
    assert latest[0]["run_at"] == "2026-08-02 10:00:00"
    assert latest[0]["return_pct"] == 7.25


def test_load_latest_predictions_for_each_ticker(settings):
    """Latest view returns the newest prediction per ticker across tickers."""
    pred_mod.store_prediction("TCS.NS", settings, _sample_payload(), run_at="2026-08-01 09:00:00")
    pred_mod.store_prediction("INFY.NS", settings, _sample_payload(), run_at="2026-08-02 10:00:00")
    # An older second run for TCS should NOT win over the newer one.
    pred_mod.store_prediction("TCS.NS", settings, _sample_payload(), run_at="2026-08-03 11:00:00")

    latest = pred_mod.load_latest_predictions(settings=settings)
    assert {r["ticker"] for r in latest} == {"TCS.NS", "INFY.NS"}
    by_ticker = {r["ticker"]: r for r in latest}
    assert by_ticker["TCS.NS"]["run_at"] == "2026-08-03 11:00:00"


def test_load_history_filtered_by_ticker(settings):
    """Filtering by tickers restricts the audit to those symbols."""
    pred_mod.store_prediction("TCS.NS", settings, _sample_payload())
    pred_mod.store_prediction("INFY.NS", settings, _sample_payload())

    only_tcs = pred_mod.load_prediction_history(tickers=["TCS.NS"], settings=settings)
    assert len(only_tcs) == 1
    assert only_tcs[0]["ticker"] == "TCS.NS"


def test_load_history_limit_returns_most_recent(settings):
    """Limit caps the number of rows, most recent first."""
    for i, day in enumerate(["01", "02", "03", "04"]):
        p = _sample_payload()
        p["return_pct"] = float(i)
        pred_mod.store_prediction("TCS.NS", settings, p, run_at=f"2026-08-{day} 09:00:00")

    history = pred_mod.load_prediction_history(limit=2, settings=settings)
    assert len(history) == 2
    # Most recent first.
    assert history[0]["run_at"] == "2026-08-04 09:00:00"
    assert history[1]["run_at"] == "2026-08-03 09:00:00"


def test_store_prediction_persists_lookback_and_pred_len(settings):
    """lookback / pred_len carried in the payload are stored on their columns."""
    payload = _sample_payload()
    payload["lookback"] = 120
    payload["pred_len"] = 14

    pred_mod.store_prediction("TCS.NS", settings, payload, run_at="2026-08-01 09:00:00")

    row = pred_mod.load_prediction_history(settings=settings)[0]
    assert row["lookback"] == 120
    assert row["pred_len"] == 14


def test_empty_history_when_nothing_stored(settings):
    """No rows stored → both readers return an empty list."""
    assert pred_mod.load_prediction_history(settings=settings) == []
    assert pred_mod.load_latest_predictions(settings=settings) == []


def test_watchlist_predictions_status_tracking(settings):
    """Simulate watchlist prediction status: some tickers have predictions, some don't."""
    # Store predictions for TCS and INFY only
    pred_mod.store_prediction("TCS.NS", settings, _sample_payload(), run_at="2026-08-01 09:00:00")
    pred_mod.store_prediction("INFY.NS", settings, _sample_payload(), run_at="2026-08-02 10:00:00")
    
    # Get latest predictions for a watchlist of 4 tickers
    watchlist_tickers = ["TCS.NS", "INFY.NS", "RELIANCE.NS", "WIPRO.NS"]
    latest = pred_mod.load_latest_predictions(tickers=watchlist_tickers, settings=settings)
    
    # Only TCS and INFY should have predictions
    assert len(latest) == 2
    returned_tickers = {row["ticker"] for row in latest}
    assert returned_tickers == {"TCS.NS", "INFY.NS"}
    
    # Verify the ones without predictions are simply absent (not in the list)
    for row in latest:
        assert row["ticker"] in {"TCS.NS", "INFY.NS"}


def test_batch_watchlist_generation_readiness(settings):
    """Verify we can store multiple predictions in sequence (simulating batch generation)."""
    watchlist = ["TCS.NS", "INFY.NS", "RELIANCE.NS"]
    base_time = "2026-08-03 09:00:00"
    
    for i, ticker in enumerate(watchlist):
        payload = _sample_payload()
        payload["return_pct"] = float(i + 1)  # 1.0, 2.0, 3.0
        pred_mod.store_prediction(ticker, settings, payload, run_at=base_time)
    
    # All three should be retrievable
    latest = pred_mod.load_latest_predictions(tickers=watchlist, settings=settings)
    assert len(latest) == 3
    
    # Verify each ticker has the correct return_pct
    by_ticker = {row["ticker"]: row for row in latest}
    assert by_ticker["TCS.NS"]["return_pct"] == 1.0
    assert by_ticker["INFY.NS"]["return_pct"] == 2.0
    assert by_ticker["RELIANCE.NS"]["return_pct"] == 3.0
    
    # Verify run_at is the same for all (batch generated at same time)
    for row in latest:
        assert row["run_at"] == base_time


def test_watchlist_prediction_status_after_regeneration(settings):
    """After regenerating predictions, only the latest run should be returned."""
    # First run
    pred_mod.store_prediction("TCS.NS", settings, _sample_payload(), run_at="2026-08-01 09:00:00")
    first = pred_mod.load_latest_predictions(tickers=["TCS.NS"], settings=settings)[0]
    assert first["return_pct"] == 3.50
    assert first["run_at"] == "2026-08-01 09:00:00"
    
    # Second run (regenerated)
    updated_payload = _sample_payload()
    updated_payload["return_pct"] = 5.75
    pred_mod.store_prediction("TCS.NS", settings, updated_payload, run_at="2026-08-03 10:00:00")
    
    # Latest should reflect the new run
    latest = pred_mod.load_latest_predictions(tickers=["TCS.NS"], settings=settings)
    assert len(latest) == 1
    assert latest[0]["return_pct"] == 5.75
    assert latest[0]["run_at"] == "2026-08-03 10:00:00"
    
    # But history should have both
    history = pred_mod.load_prediction_history(tickers=["TCS.NS"], settings=settings)
    assert len(history) == 2
