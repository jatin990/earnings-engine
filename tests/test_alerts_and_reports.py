"""Unit tests for Custom Alert Rules and Research Report Exporter routers."""

import pytest
from fastapi.testclient import TestClient

from earnings_engine.api.server import app


@pytest.fixture
def client():
    return TestClient(app)


def test_alert_rules_crud_and_dispatch(client):
    # 1. Get rules (seeds default rules if empty)
    resp = client.get("/api/v1/alerts/rules")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "rules" in data
    assert len(data["rules"]) >= 1

    # 2. Create new rule
    new_rule = {
        "name": "Test Breakout Squeeze",
        "strategy": "MOMENTUM",
        "min_score": 82.5,
        "min_volume_surge": 2.5,
        "tier": "TIER_1",
        "target_universe": "NSE_TOP",
        "max_entry_delay_pct": 2.0,
        "actions_json": ["browser", "email"],
        "is_active": True,
    }
    resp = client.post("/api/v1/alerts/rules", json=new_rule)
    assert resp.status_code == 200
    created = resp.json()
    assert created["status"] == "ok"
    rule_id = created["id"]

    # 3. Update rule
    update_payload = {
        "name": "Test Breakout Squeeze Updated",
        "strategy": "MOMENTUM",
        "min_score": 85.0,
        "min_volume_surge": 3.0,
        "tier": "TIER_1",
        "target_universe": "NSE_TOP",
        "max_entry_delay_pct": 1.5,
        "actions_json": ["browser"],
        "is_active": False,
    }
    resp = client.put(f"/api/v1/alerts/rules/{rule_id}", json=update_payload)
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

    # 4. Test dispatch (browser channel)
    resp = client.post(
        "/api/v1/alerts/test-dispatch",
        json={
            "channel": "browser",
            "sample_ticker": "INFY.NS",
            "sample_strategy": "Momentum",
            "sample_score": 88.0,
            "sample_surge": 2.6,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["channel"] == "browser"

    # 5. Get logs
    resp = client.get("/api/v1/alerts/logs")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

    # 6. Delete rule
    resp = client.delete(f"/api/v1/alerts/rules/{rule_id}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_reports_export_endpoints(client):
    # 1. Radar CSV export
    resp = client.get("/api/v1/reports/export/radar?type=breakout&universe=NSE_TOP")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "attachment;" in resp.headers.get("content-disposition", "")

    # 2. Single-ticker research bundle JSON
    resp = client.get("/api/v1/reports/export/ticker/TCS.NS")
    assert resp.status_code == 200
    bundle = resp.json()
    assert bundle["ticker"] == "TCS.NS"
    assert "technical" in bundle
    assert "institutional" in bundle

    # 3. Printable HTML research memo
    resp = client.get("/api/v1/reports/export/print-pack/TCS.NS")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "NEXUS QUANTITATIVE TERMINAL" in resp.text


def test_webhook_ssrf_protection(client):
    """Verify that private, loopback, and cloud metadata webhook targets are rejected."""
    bad_urls = [
        "http://127.0.0.1:8000/internal",
        "http://localhost:5000/hook",
        "http://169.254.169.254/latest/meta-data",
        "http://10.0.0.1/admin",
        "http://192.168.1.1/router",
        "http://172.16.0.5/api",
        "ftp://example.com/hook",
        "file:///etc/passwd",
        "gopher://example.com",
    ]
    for url in bad_urls:
        resp = client.post(
            "/api/v1/alerts/test-dispatch",
            json={
                "channel": "webhook",
                "webhook_url": url,
                "sample_ticker": "TCS.NS",
            },
        )
        assert resp.status_code == 400, f"Expected 400 for unsafe URL: {url}"
        assert "Invalid webhook URL" in resp.json()["detail"]

