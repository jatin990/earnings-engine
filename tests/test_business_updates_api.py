from fastapi.testclient import TestClient
from earnings_engine.api.server import app

client = TestClient(app)

def test_get_business_updates():
    resp = client.get("/api/v1/news/business-updates?days=30")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "updates" in data
    assert "stats" in data
    assert "count" in data

def test_get_business_update_schedules():
    resp = client.get("/api/v1/news/business-updates/schedules")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "schedules" in data
    assert len(data["schedules"]) > 0

def test_sync_business_update_schedules_post():
    resp = client.post("/api/v1/news/business-updates/sync-schedules", json={})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["synced_count"] > 0
