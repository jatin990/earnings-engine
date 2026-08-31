"""Unit tests for ticker string sanitization and ampersand decoding."""

import os
os.environ["TESTING"] = "true"

from fastapi.testclient import TestClient
from earnings_engine.api.routers.stocks import clean_ticker_param
from earnings_engine.api.server import app

client = TestClient(app)


def test_clean_ticker_param_ampersand():
    assert clean_ticker_param("M&M.NS") == "M&M.NS"
    assert clean_ticker_param("M&amp;M.NS") == "M&M.NS"
    assert clean_ticker_param("M%26M.NS") == "M&M.NS"
    assert clean_ticker_param("m&m.ns") == "M&M.NS"
    assert clean_ticker_param("  m&amp;m.ns  ") == "M&M.NS"
    assert clean_ticker_param("BAJAJ-AUTO.NS") == "BAJAJ-AUTO.NS"
    assert clean_ticker_param(None) == ""


def test_stock_detail_html_route_with_ampersand():
    # Test accessing with standard urlencoded ampersand
    res = client.get("/stock/M%26M.NS")
    assert res.status_code == 200
    # Jinja's tojson securely formats ampersand as \u0026, which evaluates to "M&M.NS" in JS
    assert 'const ACTIVE_SYM = "M\\u0026M.NS";' in res.text or 'const ACTIVE_SYM = "M&M.NS";' in res.text

    # Test accessing with raw/escaped ampersand
    res_escaped = client.get("/stock/M&amp;M.NS")
    assert res_escaped.status_code == 200
    assert 'const ACTIVE_SYM = "M\\u0026M.NS";' in res_escaped.text or 'const ACTIVE_SYM = "M&M.NS";' in res_escaped.text
