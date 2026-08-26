"""Tests for Breakout Movement & Tier Transition Audit Logging."""
import pytest
from fastapi.testclient import TestClient
from earnings_engine.api.server import app
from earnings_engine.data.breakout_scanner import (
    record_breakout_transition,
    get_breakout_audit_log,
)


@pytest.fixture
def client():
    return TestClient(app)


def test_breakout_audit_log_crud():
    record_breakout_transition(
        ticker="TESTSTOCK.NS",
        company_name="Test Stock Limited",
        from_tier="WARM",
        to_tier="HOT",
        event_type="PROMOTED_HOT",
        reason="Compression 88.5, volume surge 3.4x, price within 0.8% of 52W resistance",
        price=450.25,
        score_before=62.0,
        score_after=88.5,
        catalyst_impact="Heavy Q3 revenue beat and institutional buying",
    )

    logs = get_breakout_audit_log(ticker="TESTSTOCK.NS")
    assert len(logs) >= 1
    latest = logs[0]
    assert latest["ticker"] == "TESTSTOCK.NS"
    assert latest["from_tier"] == "WARM"
    assert latest["to_tier"] == "HOT"
    assert latest["event_type"] == "PROMOTED_HOT"
    assert latest["score_after"] == 88.5
    assert "Compression 88.5" in latest["reason"]


def test_breakout_audit_api_endpoint(client):
    res = client.get("/api/v1/breakout-radar/audit-log?limit=10")
    assert res.status_code == 200
    data = res.json()
    assert "logs" in data
    assert isinstance(data["logs"], list)
