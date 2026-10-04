"""Unit tests for Results Calendar sync and recalculate endpoints."""

from __future__ import annotations

from unittest.mock import patch, MagicMock
import pandas as pd
from fastapi.testclient import TestClient

from earnings_engine.api.server import app
from earnings_engine.api import dashboard_api


def test_sync_results_calendar_function():
    """Test sync_results_calendar dashboard API function."""
    with patch("earnings_engine.data.earnings.ingest_nse_result_calendar", return_value={"total": 25, "inserted": 5, "errors": 0}), \
         patch("earnings_engine.data.earnings.sync_present_day_earnings_delta", return_value={"events_count": 25, "inserted_count": 5}), \
         patch("earnings_engine.api.dashboard_api.clear_dashboard_caches") as mock_clear:
        res = dashboard_api.sync_results_calendar(days=30, market="ALL")
        assert res["success"] is True
        assert res["synced_count"] == 25
        assert res["inserted_count"] == 5
        mock_clear.assert_called_once()


def test_recalculate_results_prices_function():
    """Test recalculate_results_prices dashboard API function."""
    mock_df = pd.DataFrame([{"ticker": "INFY.NS", "earnings_date": "2026-10-15"}])
    with patch("earnings_engine.data.earnings.upcoming_earnings", return_value=mock_df), \
         patch("earnings_engine.data.prices.ingest_prices", return_value={"INFY.NS": 200}), \
         patch("earnings_engine.api.dashboard_api.clear_dashboard_caches") as mock_clear:
        res = dashboard_api.recalculate_results_prices(days=30, market="ALL")
        assert res["success"] is True
        assert res["recalculated_count"] == 1
        mock_clear.assert_called_once()


def test_results_sync_router_endpoints():
    """Test POST endpoints for sync-calendar and recalculate-prices."""
    client = TestClient(app)

    with patch("earnings_engine.api.dashboard_api.sync_results_calendar", return_value={"success": True, "synced_count": 10}):
        resp = client.post("/api/v1/dashboard/results/sync-calendar?market=NSE_ALL&days=45")
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        assert resp.json()["synced_count"] == 10

    with patch("earnings_engine.api.dashboard_api.recalculate_results_prices", return_value={"success": True, "recalculated_count": 8}):
        resp = client.post("/api/v1/dashboard/results/recalculate-prices?market=NSE_ALL&days=45")
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        assert resp.json()["recalculated_count"] == 8
