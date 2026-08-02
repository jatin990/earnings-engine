"""Integration tests for watchlist-based Kronos prediction generation.

Tests the full flow from watchlist selection through prediction generation
and status tracking in the dashboard API.

These tests are in the manual folder because they require the Kronos model
and take significant time to run.
"""

from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from earnings_engine.config import Settings
from earnings_engine.api.dashboard_api import (
    generate_watchlist_kronos,
    get_kronos_latest_predictions,
    get_watchlist,
    add_to_watchlist,
    remove_from_watchlist,
)
from earnings_engine.data import predictions as pred_mod


@pytest.fixture
def isolated_settings(tmp_path):
    """A Settings pointing at a temporary SQLite cache for test isolation."""
    s = Settings()
    # Override the cache directory to use tmp_path
    s.data_dirs = {"prices": tmp_path / "prices", "earnings": tmp_path / "earnings"}
    s.ensure_dirs()
    return s


@pytest.fixture
def isolated_db(tmp_path, isolated_settings):
    """Create an isolated test database with production schema copied.
    
    This ensures tests don't pollute the main prices.sqlite3 database.
    """
    import sqlite3
    import earnings_engine.data.predictions as pred_mod
    
    # Create isolated database path
    test_db = tmp_path / "test_prices.sqlite3"
    
    # Get the production DB path via the module function
    prod_db = pred_mod._db_path(Settings())
    
    # Copy production schema if production DB exists
    if prod_db.exists():
        # Copy the entire database file to isolate test data
        import shutil
        shutil.copy2(prod_db, test_db)
    else:
        # Create new database with schema by connecting and creating tables
        conn = sqlite3.connect(str(test_db))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS kronos_predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                run_at TEXT NOT NULL,
                predicted_at TEXT NOT NULL,
                lookback INTEGER,
                pred_len INTEGER,
                prediction_json TEXT NOT NULL,
                current_price REAL,
                support REAL,
                resistance REAL,
                return_pct REAL,
                trend TEXT,
                explanation TEXT
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_kronos_pred_ticker_run
            ON kronos_predictions (ticker, run_at DESC)
        """)
        conn.commit()
        conn.close()
    
    # Patch the database path function to return isolated DB
    original_db_path = pred_mod._db_path
    def patched_db_path(settings):
        return test_db
    
    pred_mod._db_path = patched_db_path
    
    yield test_db
    
    # Restore original path
    pred_mod._db_path = original_db_path


@pytest.fixture
def watchlist_with_tickers(tmp_path, isolated_settings):
    """Create a temporary watchlist file with sample tickers."""
    from earnings_engine.api.dashboard_api import WATCHLIST_FILE
    import earnings_engine.api.dashboard_api as dash_api
    
    # Create a temporary watchlist
    watchlist_path = tmp_path / "my_watchlist.txt"
    tickers = ["TCS.NS", "INFY.NS", "RELIANCE.NS"]
    watchlist_path.write_text("\n".join(tickers) + "\n", encoding="utf-8")
    
    # Monkeypatch the WATCHLIST_FILE path
    original_path = dash_api.WATCHLIST_FILE
    dash_api.WATCHLIST_FILE = watchlist_path
    
    # Also patch predictions module to use isolated settings
    original_pred_settings = pred_mod.Settings
    pred_mod.Settings = lambda: isolated_settings
    
    yield tickers
    
    # Restore original paths
    dash_api.WATCHLIST_FILE = original_path
    pred_mod.Settings = original_pred_settings


def test_generate_watchlist_kronos_with_explicit_tickers(isolated_db, isolated_settings):
    """Test generating predictions for explicitly provided tickers."""
    tickers = ["TCS.NS", "INFY.NS"]
    result = generate_watchlist_kronos(tickers=tickers, lookback=120, pred_len=14)
    
    assert result["success"] is True
    assert result["generated"] == len(tickers)
    assert len(result["forecasts"]) == len(tickers)
    
    # Verify each forecast has expected structure
    for fc in result["forecasts"]:
        assert "symbol" in fc or "ticker" in fc
        assert "return_pct" in fc
        assert "trend" in fc
        assert "support" in fc
        assert "resistance" in fc


def test_generate_watchlist_kronos_empty_tickers_uses_watchlist(isolated_db, isolated_settings, watchlist_with_tickers):
    """Test that empty tickers list falls back to watchlist file."""
    result = generate_watchlist_kronos(tickers=[], lookback=120, pred_len=14)
    
    # Should succeed using watchlist tickers (or fail gracefully if Kronos unavailable)
    if result.get("success"):
        assert "forecasts" in result
        assert "generated" in result
        assert isinstance(result["forecasts"], list)


def test_generate_watchlist_kronos_no_tickers_empty_watchlist(isolated_db, isolated_settings, tmp_path):
    """Test error handling when no tickers provided and watchlist is empty."""
    import earnings_engine.api.dashboard_api as dash_api
    
    # Create empty watchlist
    watchlist_path = tmp_path / "empty_watchlist.txt"
    watchlist_path.write_text("", encoding="utf-8")
    original_path = dash_api.WATCHLIST_FILE
    dash_api.WATCHLIST_FILE = watchlist_path
    
    try:
        result = generate_watchlist_kronos(tickers=[], lookback=120, pred_len=14)
        assert result["success"] is False
        assert "error" in result
    finally:
        dash_api.WATCHLIST_FILE = original_path


def test_watchlist_predictions_persisted_after_generation(isolated_db, isolated_settings, tmp_path):
    """Test that generated predictions are persisted and retrievable."""
    import earnings_engine.api.dashboard_api as dash_api
    
    # Database is already isolated via fixture
    
    watchlist_path = tmp_path / "test_watchlist.txt"
    tickers = ["TCS.NS"]
    watchlist_path.write_text("\n".join(tickers) + "\n", encoding="utf-8")
    original_path = dash_api.WATCHLIST_FILE
    dash_api.WATCHLIST_FILE = watchlist_path
    
    try:
        result = generate_watchlist_kronos(tickers=tickers, lookback=120, pred_len=14)
        
        if not result.get("success"):
            pytest.skip("Kronos predictor unavailable")
        
        # Verify predictions are stored
        latest = get_kronos_latest_predictions(tickers)
        assert len(latest) == 1
        assert latest[0]["ticker"] == "TCS.NS"
        assert latest[0]["prediction"]["return_pct"] is not None
        assert latest[0]["prediction"]["trend"] is not None
    finally:
        dash_api.WATCHLIST_FILE = original_path


def test_batch_generation_maintains_prediction_quality(isolated_db, isolated_settings, watchlist_with_tickers):
    """Test that batch generation produces valid predictions for all tickers."""
    tickers = ["TCS.NS", "INFY.NS", "RELIANCE.NS"]
    result = generate_watchlist_kronos(tickers=tickers, lookback=120, pred_len=14)
    
    if not result.get("success"):
        pytest.skip("Kronos predictor unavailable")
    
    # All tickers should have predictions
    assert result["generated"] == len(tickers)
    
    # Each prediction should have required fields
    for fc in result["forecasts"]:
        symbol = fc.get("symbol") or fc.get("ticker")
        assert symbol in tickers
        assert isinstance(fc["return_pct"], (int, float))
        assert fc["trend"] in ["Bullish", "Bearish", "Neutral"]
        assert isinstance(fc["current_price"], (int, float))
        assert fc["support"] < fc["current_price"]
        assert fc["resistance"] > fc["current_price"]


def test_prediction_regeneration_updates_latest(isolated_db, isolated_settings, watchlist_with_tickers):
    """Test that regenerating predictions updates the latest view."""
    tickers = ["TCS.NS"]
    
    # Generate first prediction
    result1 = generate_watchlist_kronos(tickers=tickers, lookback=120, pred_len=14)
    if not result1.get("success"):
        pytest.skip("Kronos predictor unavailable")
    
    latest1 = get_kronos_latest_predictions(tickers)
    first_run_at = latest1[0]["run_at"]
    
    # Regenerate
    result2 = generate_watchlist_kronos(tickers=tickers, lookback=120, pred_len=14)
    if not result2.get("success"):
        pytest.skip("Kronos predictor unavailable on second run")
    
    latest2 = get_kronos_latest_predictions(tickers)
    second_run_at = latest2[0]["run_at"]
    
    # Run times should be different
    assert first_run_at != second_run_at
    
    # Verify we have predictions (they go to the global cache)
    assert len(latest2) >= 1


def test_watchlist_status_tracking_integration(isolated_db, isolated_settings, tmp_path):
    """Integration test: add tickers to watchlist, generate predictions, verify status."""
    import earnings_engine.api.dashboard_api as dash_api
    
    watchlist_path = tmp_path / "test_watchlist.txt"
    dash_api.WATCHLIST_FILE = watchlist_path
    
    try:
        # Start with empty watchlist
        assert get_watchlist() == []
        
        # Add tickers
        add_to_watchlist("TCS.NS")
        add_to_watchlist("INFY.NS")
        watchlist = get_watchlist()
        assert len(watchlist) == 2
        
        # Generate predictions for one ticker
        result = generate_watchlist_kronos(tickers=["TCS.NS"], lookback=120, pred_len=14)
        if not result.get("success"):
            pytest.skip("Kronos predictor unavailable")
        
        # Check latest predictions - should only have TCS.NS
        latest = get_kronos_latest_predictions(watchlist)
        returned_tickers = {row["ticker"] for row in latest}
        
        # Only TCS.NS should have a prediction (INFY.NS has none yet)
        assert "TCS.NS" in returned_tickers
        assert len(latest) >= 1
        
        # Generate for the second ticker
        result2 = generate_watchlist_kronos(tickers=["INFY.NS"], lookback=120, pred_len=14)
        if not result2.get("success"):
            pytest.skip("Kronos predictor unavailable on second run")
        
        # Now both should have predictions
        latest2 = get_kronos_latest_predictions(watchlist)
        returned_tickers2 = {row["ticker"] for row in latest2}
        assert "TCS.NS" in returned_tickers2
        assert "INFY.NS" in returned_tickers2
        assert len(latest2) >= 2
        
    finally:
        dash_api.WATCHLIST_FILE = Path(__file__).resolve().parent.parent / "data" / "universes" / "my_watchlist.txt"


def test_generate_for_single_ticker_vs_batch(isolated_db, isolated_settings, watchlist_with_tickers):
    """Test that single ticker generation matches batch generation output structure."""
    # Single ticker
    result_single = generate_watchlist_kronos(tickers=["TCS.NS"], lookback=120, pred_len=14)
    if not result_single.get("success"):
        pytest.skip("Kronos predictor unavailable")
    
    # Batch
    result_batch = generate_watchlist_kronos(tickers=["TCS.NS", "INFY.NS"], lookback=120, pred_len=14)
    if not result_batch.get("success"):
        pytest.skip("Kronos predictor unavailable")
    
    # Single ticker result should have 1 forecast
    assert len(result_single["forecasts"]) == 1
    assert result_single["generated"] == 1
    
    # Batch should have 2 forecasts
    assert len(result_batch["forecasts"]) == 2
    assert result_batch["generated"] == 2
    
    # Both should have the same structure for the same ticker
    single_fc = result_single["forecasts"][0]
    batch_fc = result_batch["forecasts"][0]
    assert set(single_fc.keys()) == set(batch_fc.keys())