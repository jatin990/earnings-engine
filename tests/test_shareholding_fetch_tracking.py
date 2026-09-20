"""Unit and integration tests for shareholding fetch tracking, error-stopping workflow, and UI endpoints."""

import os
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection
from earnings_engine.data.migrations import apply_migrations, reset_migration_cache
from earnings_engine.data.auth import create_session_token
from earnings_engine.data.nse_shareholding import (
    mark_shareholding_fetched,
    get_stock_fetch_status,
    ingest_stock_shareholding_pattern,
    ShareholdingIngestionError,
)
from earnings_engine.api.server import app


@pytest.fixture(autouse=True)
def test_env(temp_settings):
    """Ensure migrations are applied and TESTING=true for test client."""
    old_val = os.environ.get("TESTING")
    os.environ["TESTING"] = "true"
    reset_migration_cache()
    apply_migrations(temp_settings)
    yield
    if old_val is None:
        os.environ.pop("TESTING", None)
    else:
        os.environ["TESTING"] = old_val


@pytest.fixture
def auth_client():
    token = create_session_token(
        user_id="usr_admin",
        role="admin",
        email="admin@nexus.local",
        name="Admin",
        scopes=["admin", "read", "write"],
    )
    return TestClient(app, cookies={"nexus_session": token})


def test_mark_and_get_stock_fetch_status(temp_settings):
    """Verify mark_shareholding_fetched records success and failure diagnostics."""
    settings = temp_settings
    conn = get_db_connection(settings)

    # 1. Record a successful fetch
    mark_shareholding_fetched(
        "TEST_STOCK.NS",
        entities_count=12,
        source="EXCHANGE_REGULATORY_FILINGS",
        status="SUCCESS",
        error_message=None,
        response_code=200,
        duration_ms=450.5,
        settings=settings,
        conn=conn,
    )

    status = get_stock_fetch_status("TEST_STOCK.NS", settings=settings, conn=conn)
    assert status is not None
    assert status["ticker"] == "TEST_STOCK.NS"
    assert status["status"] == "SUCCESS"
    assert status["source"] == "EXCHANGE_REGULATORY_FILINGS"
    assert status["entities_count"] == 12
    assert status["response_code"] == 200
    assert status["duration_ms"] == 450.5
    assert status["error_message"] is None
    assert "ago" in status["time_ago"] or status["time_ago"] == "Recently"

    # 2. Record a failed fetch
    mark_shareholding_fetched(
        "TEST_STOCK.NS",
        entities_count=0,
        source="nse_api",
        status="FAILED",
        error_message="HTTP 403 Forbidden: Akamai bot-defense triggered",
        response_code=403,
        duration_ms=820.0,
        settings=settings,
        conn=conn,
    )

    status2 = get_stock_fetch_status("TEST_STOCK.NS", settings=settings, conn=conn)
    assert status2 is not None
    assert status2["status"] == "FAILED"
    assert status2["source"] == "nse_api"
    assert status2["response_code"] == 403
    assert "403 Forbidden" in status2["error_message"]
    assert status2["entities_count"] == 0


def test_ingest_stock_shareholding_fail_fast_stops_with_error(temp_settings):
    """Verify that failed ingestion never silently skips; it halts with ShareholdingIngestionError."""
    settings = temp_settings
    conn = get_db_connection(settings)

    # Mock both fetchers to fail
    with patch("earnings_engine.data.nse_shareholding.fetch_nse_shareholding", return_value=None), \
         patch("earnings_engine.data.nse_shareholding.fetch_regulatory_shareholding_filings", return_value={"success": False, "error": "HTTP 403 Forbidden"}):

        # fail_fast=True MUST stop with error
        with pytest.raises(ShareholdingIngestionError) as exc_info:
            ingest_stock_shareholding_pattern(
                ticker="FAIL_STOCK.NS",
                force=True,
                fail_fast=True,
                settings=settings,
            )

        assert "FAIL_STOCK.NS" in str(exc_info.value)
        assert exc_info.value.status_code == 502

        # Verify failure diagnostics persisted in DB
        status = get_stock_fetch_status("FAIL_STOCK.NS", settings=settings, conn=conn)
        assert status is not None
        assert status["status"] == "FAILED"
        assert "failed" in status["error_message"].lower()


def test_ingest_stock_shareholding_fail_fast_false_returns_diagnostic_dict(temp_settings):
    """Verify that fail_fast=False returns structured failure dictionary with diagnostics."""
    settings = temp_settings
    conn = get_db_connection(settings)

    with patch("earnings_engine.data.nse_shareholding.fetch_nse_shareholding", return_value=None), \
         patch("earnings_engine.data.nse_shareholding.fetch_regulatory_shareholding_filings", return_value={"success": False, "error": "Connection timeout"}):

        res = ingest_stock_shareholding_pattern(
            ticker="TIMEOUT_STOCK.NS",
            force=True,
            fail_fast=False,
            settings=settings,
        )

        assert res["success"] is False
        assert "TIMEOUT_STOCK.NS" in res["ticker"]
        assert "failed" in res["error"].lower()
        assert res["last_fetch"]["status"] == "FAILED"


def test_api_stock_fetch_status_and_trigger_endpoints(auth_client, temp_settings, monkeypatch):
    """Verify FastAPI endpoints for fetch-status and trigger fetch."""
    settings = temp_settings
    conn = get_db_connection(settings)

    # Point global _settings in router to temp_settings
    from earnings_engine.api import dependencies
    monkeypatch.setattr(dependencies, "_settings", temp_settings)
    from earnings_engine.api.routers import institutional
    monkeypatch.setattr(institutional, "_settings", temp_settings)

    # Seed fetch status for AQYLON.NS
    mark_shareholding_fetched(
        "AQYLON.NS",
        entities_count=20,
        source="EXCHANGE_REGULATORY_FILINGS",
        status="SUCCESS",
        error_message=None,
        response_code=200,
        duration_ms=320.0,
        settings=settings,
        conn=conn,
    )

    # 1. GET /fetch-status
    res = auth_client.get("/api/v1/institutional/stock/AQYLON.NS/fetch-status")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["status"] == "SUCCESS"
    assert data["entities_count"] == 20

    # 2. GET /stock/AQYLON.NS returns last_fetch
    res_stock = auth_client.get("/api/v1/institutional/stock/AQYLON.NS")
    assert res_stock.status_code == 200
    stock_data = res_stock.json()
    assert stock_data.get("last_fetch") is not None
    assert stock_data["last_fetch"]["status"] == "SUCCESS"

    # 3. POST /fetch with failing stock returns 422 with error detail
    with patch("earnings_engine.data.nse_shareholding.fetch_nse_shareholding", return_value=None), \
         patch("earnings_engine.data.nse_shareholding.fetch_regulatory_shareholding_filings", return_value={"success": False, "error": "No filings on record"}):

        res_fetch = auth_client.post("/api/v1/institutional/stock/BROKEN_CORP.NS/fetch")
        assert res_fetch.status_code == 422
        err_json = res_fetch.json()
        assert "failed" in err_json["detail"].lower() or "broken_corp" in err_json["detail"].lower()
