"""Unit and integration tests for Institutional & Smart Money Buyers Period Inspector."""

from __future__ import annotations

import os
from unittest.mock import patch
import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from earnings_engine.api.server import app
from earnings_engine.cli import cli, buyers_cmd, institutional_buyers_cmd
from earnings_engine.data.institutional_accumulation import (
    _normalize_query_dates,
    _resolve_ticker_symbol,
    get_stock_buyers_in_period,
)
from earnings_engine.data.db import get_db_connection


@pytest.fixture(autouse=True)
def test_env():
    """Ensure tests run with TESTING=true for bypassing auth middleware in test client."""
    old_val = os.environ.get("TESTING")
    os.environ["TESTING"] = "true"
    yield
    if old_val is None:
        os.environ.pop("TESTING", None)
    else:
        os.environ["TESTING"] = old_val


def test_normalize_query_dates_month_formats():
    """Test date parsing for natural month-year and month prefix strings."""
    # FEB 2026 as from_date (open-ended to present)
    start, end, q = _normalize_query_dates("FEB 2026")
    assert start == "2026-02-01"
    assert end is None

    # From FEB 2026 (open-ended to present)
    start_from, end_from, _ = _normalize_query_dates("from FEB 2026")
    assert start_from == "2026-02-01"
    assert end_from is None

    # YYYY-MM format as from_date and to_date
    start_m, end_m, _ = _normalize_query_dates(from_date="2026-03", to_date="2026-03")
    assert start_m == "2026-03-01"
    assert end_m == "2026-03-31"


def test_normalize_query_dates_fiscal_quarters():
    """Test Indian fiscal quarter parsing (FY ends in March)."""
    # Q4 FY26: Jan 1, 2026 - Mar 31, 2026
    s_q4, e_q4, q4_name = _normalize_query_dates(quarter="Q4 FY26")
    assert s_q4 == "2026-01-01"
    assert e_q4 == "2026-03-31"
    assert q4_name == "Q4 FY26"

    # Q1 FY27: Apr 1, 2026 - Jun 30, 2026
    s_q1, e_q1, q1_name = _normalize_query_dates(quarter="Q1 FY27")
    assert s_q1 == "2026-04-01"
    assert e_q1 == "2026-06-30"
    assert q1_name == "Q1 FY27"


def test_normalize_query_dates_relative_and_iso():
    """Test relative offset (e.g. 90d) and standard ISO date strings."""
    # 90d as from_date
    s_90, e_90, _ = _normalize_query_dates("90d")
    assert s_90 is not None
    assert e_90 is None

    # Explicit ISO dates
    s_iso, e_iso, _ = _normalize_query_dates(from_date="2026-02-01", to_date="2026-02-20")
    assert s_iso == "2026-02-01"
    assert e_iso == "2026-02-20"


def test_resolve_ticker_symbol():
    """Test resolving raw symbols, company names, and base tickers."""
    with get_db_connection() as conn:
        # Canonical symbol
        sym, name = _resolve_ticker_symbol("STLTECH.NS", conn)
        assert sym == "STLTECH.NS"

        # Base symbol without .NS
        sym2, _ = _resolve_ticker_symbol("STLTECH", conn)
        assert sym2 == "STLTECH.NS"

        # Company name lookup
        sym3, name3 = _resolve_ticker_symbol("STERLITE TECH", conn)
        assert sym3 == "STLTECH.NS"
        assert "STERLITE" in name3.upper()


def test_get_stock_buyers_in_period_real_query():
    """Test analytical period buyers query on STLTECH.NS from Feb 2026."""
    res = get_stock_buyers_in_period(
        ticker="STERLITE TECH",
        from_date="FEB 2026",
    )
    assert res["success"] is True
    assert res["ticker"] == "STLTECH.NS"
    assert "company_name" in res
    assert res["total_buyers_count"] > 0
    assert res["total_capital_deployed_cr"] > 0.0

    summary = res["summary"]
    assert "fii_capital_deployed_cr" in summary
    assert "dii_capital_deployed_cr" in summary
    assert "super_investor_capital_deployed_cr" in summary
    assert summary["filings_count"] >= 0
    assert summary["block_deals_count"] >= 0

    buyers = res["buyers"]
    assert len(buyers) == res["total_buyers_count"]
    first_buyer = buyers[0]
    assert "buyer_name" in first_buyer
    assert "entity_class" in first_buyer
    assert "action" in first_buyer
    assert "capital_deployed_cr" in first_buyer
    assert "source" in first_buyer


def test_get_stock_buyers_entity_filtering():
    """Test filtering institutional buyers by FII entity class."""
    res_fii = get_stock_buyers_in_period(
        ticker="STLTECH.NS",
        from_date="2026-02-01",
        entity_type="FII",
    )
    assert res_fii["success"] is True
    for b in res_fii["buyers"]:
        assert "Foreign" in b["entity_class"] or "FII" in b["entity_class"]


def test_get_stock_buyers_empty_state():
    """Test honest zero-state return when a non-existent ticker or future empty window is requested."""
    res = get_stock_buyers_in_period(
        ticker="STLTECH.NS",
        from_date="2035-01-01",
    )
    assert res["success"] is True
    assert res["total_buyers_count"] == 0
    assert res["total_capital_deployed_cr"] == 0.0
    assert res["buyers"] == []


def test_fastapi_buyers_endpoint():
    """Test FastAPI REST endpoint for stock institutional buyers."""
    client = TestClient(app)
    response = client.get("/api/v1/institutional/stock/STLTECH.NS/buyers?from_date=FEB%202026")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["ticker"] == "STLTECH.NS"
    assert "summary" in data
    assert "buyers" in data
    assert data["total_buyers_count"] > 0


def test_fastapi_buyers_alias_endpoint():
    """Test secondary alias route /api/v1/institutional/buyers/{ticker}."""
    client = TestClient(app)
    response = client.get("/api/v1/institutional/buyers/STLTECH.NS?quarter=Q4%20FY26")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["ticker"] == "STLTECH.NS"


def test_cli_buyers_command():
    """Test Click CLI command `earnings-engine buyers`."""
    runner = CliRunner()
    result = runner.invoke(buyers_cmd, ["STLTECH.NS", "--from", "FEB 2026"])
    assert result.exit_code == 0
    output = result.output
    assert "INSTITUTIONAL & SMART MONEY BUYERS" in output
    assert "STLTECH.NS" in output
    assert "Total Capital Deployed" in output
    assert "Investor / Fund Name" in output


def test_cli_buyers_alias_command():
    """Test Click CLI command alias `earnings-engine institutional-buyers`."""
    runner = CliRunner()
    result = runner.invoke(institutional_buyers_cmd, ["STERLITE TECH", "--from", "2026-02-01", "--entity", "FII"])
    assert result.exit_code == 0
    output = result.output
    assert "STLTECH.NS" in output
    assert "Foreign" in output or "FII" in output
