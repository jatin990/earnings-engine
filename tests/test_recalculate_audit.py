"""Unit tests for ticker recalculation, change detection, and audit logging."""
import json
from unittest.mock import patch
import pandas as pd
import pytest
from starlette.testclient import TestClient

from earnings_engine.api.server import app
from earnings_engine.config import Settings
from earnings_engine.data import earnings as earnings_mod
from earnings_engine.data import prices as prices_mod
from earnings_engine.data.ticker_audit import get_audit_history, init_audit_db, record_audit_entry
from earnings_engine.api.recalculate_api import recalculate_ticker_metrics


@pytest.fixture
def temp_settings(tmp_path):
    s = Settings()
    s.data_dirs["prices"] = tmp_path
    s.data_dirs["earnings"] = tmp_path
    s.ensure_dirs()
    with earnings_mod._connect(s):
        pass
    with prices_mod._connect(s):
        pass
    init_audit_db(s)
    return s


def test_audit_log_crud(temp_settings):
    """Test recording and retrieving audit history records."""
    entry = record_audit_entry(
        ticker="TEST.NS",
        has_changes=True,
        changes_summary=["Price: ₹100.00 → ₹110.00", "Result Date: 2026-08-20 → 2026-08-25"],
        previous_values={"current_price": 100.0, "earnings_date": "2026-08-20"},
        updated_values={"current_price": 110.0, "earnings_date": "2026-08-25"},
        diff_data={"current_price": {"old": 100.0, "new": 110.0}},
        settings=temp_settings,
    )
    assert entry["id"] is not None
    assert entry["ticker"] == "TEST.NS"
    assert entry["has_changes"] is True

    # Retrieve history for specific ticker
    history = get_audit_history("TEST.NS", settings=temp_settings)
    assert len(history) >= 1
    assert history[0]["ticker"] == "TEST.NS"
    assert history[0]["has_changes"] is True
    assert "Price" in history[0]["changes_summary"]


def test_recalculate_ticker_metrics_flow(temp_settings):
    """Test recalculate_ticker_metrics with mock data providers."""
    mock_earnings = pd.DataFrame([
        {"earnings_date": "2026-08-28", "eps_estimate": 10.0, "eps_reported": 12.0, "surprise_pct": 20.0}
    ])
    mock_prices = pd.DataFrame([
        {"date": "2026-08-20", "open": 100.0, "high": 105.0, "low": 98.0, "close": 102.0, "volume": 1000},
        {"date": "2026-08-21", "open": 102.0, "high": 108.0, "low": 101.0, "close": 106.0, "volume": 1200},
    ])

    with patch("earnings_engine.api.recalculate_api.earnings_mod.fetch_earnings", return_value=mock_earnings), \
         patch("earnings_engine.api.recalculate_api.prices_mod.fetch_prices", return_value=mock_prices), \
         patch("earnings_engine.api.recalculate_api.enrich_upcoming_results", return_value=pd.DataFrame([{"ticker": "RECALC_TEST.NS", "current_price": 106.0, "earnings_date": "2026-08-28"}])):
        res = recalculate_ticker_metrics("RECALC_TEST.NS", settings=temp_settings)

    assert res["success"] is True
    assert res["ticker"] == "RECALC_TEST.NS"
    assert "refreshed_at" in res
    assert "audit_id" in res


def test_recalculate_api_endpoints():
    """Test POST /api/v1/ticker/recalculate and GET /api/v1/ticker/audit-log endpoints."""
    client = TestClient(app)

    # Missing ticker parameter should return 422 Unprocessable Entity
    bad_res = client.post("/api/v1/ticker/recalculate")
    assert bad_res.status_code == 422

    # Audit log endpoint should return a list
    audit_res = client.get("/api/v1/ticker/audit-log?limit=10")
    assert audit_res.status_code == 200
    assert isinstance(audit_res.json(), list)
