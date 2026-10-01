import pytest
from earnings_engine.data.zepto_db import (
    ensure_zepto_schema,
    save_gmail_auth,
    get_gmail_auth,
    delete_gmail_auth,
)
from earnings_engine.data.turso_sync import SYNC_TABLES

def test_sync_tables_includes_zepto_gmail_auth():
    assert "zepto_gmail_auth" in SYNC_TABLES

def test_gmail_auth_crud_lifecycle():
    ensure_zepto_schema()
    # Save auth
    record = save_gmail_auth(
        email="darkstore@zepto.in",
        access_token="ya29.test_token",
        refresh_token="1//refresh_token",
        token_expiry="2026-12-31T23:59:59Z",
        scopes="https://www.googleapis.com/auth/gmail.readonly",
    )
    assert record["email"] == "darkstore@zepto.in"
    assert record["access_token"] == "ya29.test_token"

    # Get auth
    loaded = get_gmail_auth()
    assert loaded is not None
    assert loaded["email"] == "darkstore@zepto.in"
    assert loaded["refresh_token"] == "1//refresh_token"

    # Delete auth
    deleted = delete_gmail_auth()
    assert deleted is True
    assert get_gmail_auth() is None


@pytest.fixture
def auth_client():
    from fastapi.testclient import TestClient
    from earnings_engine.api.server import app
    from earnings_engine.data.auth import create_session_token

    c = TestClient(app)
    token = create_session_token(
        user_id="usr_owner",
        role="owner",
        email="owner@nexus.local",
        name="Nexus Owner",
        scopes=["*"],
    )
    c.cookies.set("nexus_session", token)
    return c


def test_gmail_status_unconfigured(monkeypatch, auth_client):
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)
    delete_gmail_auth()

    resp = auth_client.get("/api/v1/zepto/gmail/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["configured"] is False
    assert data["connected"] is False


def test_gmail_auth_url_generation(monkeypatch, auth_client):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "mock-client-id.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "mock-secret")

    resp = auth_client.get("/api/v1/zepto/gmail/auth-url")
    assert resp.status_code == 200
    data = resp.json()
    assert "auth_url" in data
    assert "mock-client-id" in data["auth_url"]
    assert "access_type=offline" in data["auth_url"]
    assert "state" in data


def test_gmail_disconnect_lifecycle(monkeypatch, auth_client):
    save_gmail_auth("test@gmail.com", "tok", "ref", "exp", "scope")
    resp = auth_client.post("/api/v1/zepto/gmail/disconnect")
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"
    assert get_gmail_auth() is None


def test_gmail_ingest_all_emails_endpoint_requires_auth(auth_client):
    # When no token connected
    resp = auth_client.post("/api/v1/zepto/gmail/ingest-all-emails")
    assert resp.status_code == 400
    assert "No active Gmail account" in resp.json()["detail"]


