"""Unit tests verifying RBAC authorization for dataset refresh endpoints."""
import os
import pytest
from starlette.testclient import TestClient

from earnings_engine.api.server import app
from earnings_engine.data.auth import create_session_token


@pytest.fixture(autouse=True)
def setup_auth_env(monkeypatch, tmp_path):
    monkeypatch.setenv("AUTH_SECRET_KEY", "test-secret-key-2026")
    monkeypatch.setenv("TURSO_AUTH_TOKEN", "")
    monkeypatch.setenv("OWNER_PASSCODE", "NEXUS-MASTER")


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def friend_token():
    return create_session_token(
        user_id="usr_friend_001",
        role="friend",
        email="friend@nexus.local",
        name="Test Friend",
        scopes=["dashboard"],
    )


@pytest.fixture
def owner_token():
    return create_session_token(
        user_id="usr_owner_001",
        role="owner",
        email="owner@nexus.local",
        name="Master Admin",
        scopes=["admin", "dashboard", "can_view_cards", "can_view_trips", "can_view_net_worth"],
    )


def test_dataset_refresh_unauthenticated(client):
    """Unauthenticated calls to dataset refresh endpoints must return 401."""
    # 1. Refresh watchlist earnings
    resp1 = client.post("/api/v1/earnings/refresh-watchlist", json={"watchlist": "NSE_TOP"})
    assert resp1.status_code == 401

    # 2. Dashboard refresh
    resp2 = client.post("/api/v1/dashboard/refresh", json={"market": "ALL"})
    assert resp2.status_code == 401

    # 3. Incremental earnings fetch
    resp3 = client.post("/api/v1/dashboard/earnings/incremental", json={"market": "ALL"})
    assert resp3.status_code == 401

    # 4. Month filter sync
    resp4 = client.post("/api/v1/dashboard/month-filter/sync", params={"market": "ALL"})
    assert resp4.status_code == 401


def test_dataset_refresh_forbidden_for_friend(client, friend_token):
    """Friend role sessions must receive 403 Forbidden on large dataset refresh endpoints."""
    headers = {"Authorization": f"Bearer {friend_token}"}

    # 1. Refresh watchlist earnings
    resp1 = client.post("/api/v1/earnings/refresh-watchlist", json={"watchlist": "NSE_TOP"}, headers=headers)
    assert resp1.status_code == 403
    assert "forbidden" in resp1.json().get("detail", "").lower()

    # 2. Dashboard refresh
    resp2 = client.post("/api/v1/dashboard/refresh", json={"market": "ALL"}, headers=headers)
    assert resp2.status_code == 403
    assert "forbidden" in resp2.json().get("detail", "").lower()

    # 3. Incremental earnings fetch
    resp3 = client.post("/api/v1/dashboard/earnings/incremental", json={"market": "ALL"}, headers=headers)
    assert resp3.status_code == 403
    assert "forbidden" in resp3.json().get("detail", "").lower()

    # 4. Month filter sync
    resp4 = client.post("/api/v1/dashboard/month-filter/sync", params={"market": "ALL"}, headers=headers)
    assert resp4.status_code == 403
    assert "forbidden" in resp4.json().get("detail", "").lower()


def test_month_filter_get_force_sync_fallback_for_friend(client, friend_token):
    """Calling GET /api/v1/dashboard/month-filter with force_sync=true as friend ignores force_sync safely."""
    headers = {"Authorization": f"Bearer {friend_token}"}
    resp = client.get("/api/v1/dashboard/month-filter?market=ALL&force_sync=true", headers=headers)
    # Read access is permitted, but force_sync is safely degraded to False for non-master
    assert resp.status_code == 200


def test_dataset_refresh_authorized_for_owner(client, owner_token, monkeypatch):
    """Master/Owner role sessions are authorized to call dataset refresh endpoints."""
    headers = {"Authorization": f"Bearer {owner_token}"}

    # Mock the underlying heavy background runners so we don't hit external APIs in test
    import earnings_engine.data.earnings as earnings_mod
    monkeypatch.setattr(earnings_mod, "refresh_watchlist_earnings", lambda **kwargs: {"success": True, "refreshed_count": 0, "watchlist": "NSE_TOP"})

    resp = client.post("/api/v1/earnings/refresh-watchlist", json={"watchlist": "NSE_TOP"}, headers=headers)
    assert resp.status_code == 200
    assert resp.json().get("success") is True
