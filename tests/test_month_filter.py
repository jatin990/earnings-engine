"""Tests for precalculated Month Filter, present-day delta fetch records, and Date->Cap->Industry hierarchy."""

import json
from unittest.mock import patch, MagicMock
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from earnings_engine.config import Settings
from earnings_engine.data.earnings import (
    _connect,
    get_fetch_record_status,
    sync_present_day_earnings_delta,
    get_cached_month_filter,
    set_cached_month_filter,
)
from earnings_engine.reports.render import build_upcoming_results_fragments
from earnings_engine.api.server import app


@pytest.fixture
def test_settings(tmp_path):
    p_dir = tmp_path / "prices"
    e_dir = tmp_path / "earnings"
    settings = Settings(data_dirs={"prices": p_dir, "earnings": e_dir})
    settings.ensure_dirs()
    return settings


def test_earnings_fetch_log_schema(test_settings):
    """Test SQLite tables earnings_fetch_log and earnings_month_cache are created properly."""
    with _connect(test_settings) as conn:
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        assert "earnings_fetch_log" in tables
        assert "earnings_month_cache" in tables


def test_sync_present_day_earnings_delta(test_settings):
    """Test present-day delta sync records fetch status."""
    with patch("earnings_engine.data.earnings.fetch_event_calendar", return_value=[
        {"symbol": "RELIANCE", "date": pd.Timestamp.today().strftime("%Y-%m-%d"), "purpose": "Financial Results"}
    ]):
        status = sync_present_day_earnings_delta(test_settings, force=True)
        assert status["synced_today"] is True
        assert status["status"] == "UP_TO_DATE"
        assert status["today"] == pd.Timestamp.today().strftime("%Y-%m-%d")

        rec = get_fetch_record_status(test_settings)
        assert rec["synced_today"] is True
        assert rec["status"] == "UP_TO_DATE"


def test_month_filter_cache_storage(test_settings):
    """Test storing and retrieving precalculated month filter payload."""
    payload = {
        "success": True,
        "months": [{"month_key": "2026-08", "month_label": "Aug 2026", "stocks_count": 5}],
        "total_stocks": 5,
    }
    set_cached_month_filter(test_settings, "test_key", payload)
    cached = get_cached_month_filter(test_settings, "test_key")
    assert cached is not None
    assert cached["success"] is True
    assert cached["total_stocks"] == 5


def test_hierarchy_date_cap_industry_fragments():
    """Test build_upcoming_results_fragments groups by Date -> Market Cap -> Industry."""
    df = pd.DataFrame([
        {
            "ticker": "RELIANCE.NS",
            "company_name": "Reliance Industries",
            "earnings_date": "2026-08-25",
            "source": "nse",
            "market_cap": 1500000000000.0,
            "industry": "Oil & Gas",
        },
        {
            "ticker": "TCS.NS",
            "company_name": "Tata Consultancy Services",
            "earnings_date": "2026-08-25",
            "source": "nse",
            "market_cap": 1200000000000.0,
            "industry": "IT Services",
        },
        {
            "ticker": "SMALLDEV.NS",
            "company_name": "Small Tech",
            "earnings_date": "2026-08-25",
            "source": "nse",
            "market_cap": 500000000.0,
            "industry": "IT Services",
        },
    ])

    fragments = build_upcoming_results_fragments(df, on_demand=True)
    assert fragments["total_stocks"] == 3
    assert len(fragments["day_sections_list"]) == 1

    section_html = fragments["day_sections_list"][0]
    assert "2026-08-25" in section_html
    assert "Large Cap" in section_html
    assert "Small Cap" in section_html
    assert "Industry: IT Services" in section_html


def test_month_filter_api_endpoint(test_settings):
    """Test /api/v1/dashboard/month-filter API endpoint."""
    client = TestClient(app)
    response = client.get("/api/v1/dashboard/month-filter?market=IN")
    assert response.status_code == 200
    data = response.json()
    assert "fetch_record" in data
    assert "day_sections_list" in data
