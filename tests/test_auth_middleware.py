"""Unit tests for the Nexus Authentication Middleware and protected route enforcement."""
from __future__ import annotations

import os
from starlette.testclient import TestClient

from earnings_engine.config import Settings
from earnings_engine.data.passcodes import init_passcodes
from earnings_engine.api.server import app


def test_unauthenticated_dashboard_redirect():
    # Explicitly clear testing bypass env var for this specific test
    client = TestClient(app, follow_redirects=False)
    
    # 1. Unauthenticated request to /dashboard redirects to /portal
    resp = client.get("/dashboard")
    assert resp.status_code == 302
    assert "/portal?redirect=/dashboard" in resp.headers["location"]

    # 2. Unauthenticated request to /credit-card redirects to /portal
    resp_cc = client.get("/credit-card")
    assert resp_cc.status_code == 302
    assert "/portal?redirect=/credit-card" in resp_cc.headers["location"]


def test_authenticated_dashboard_with_passcode_and_cookie():
    init_passcodes()
    client = TestClient(app, follow_redirects=False)

    # 1. Access with query parameter ?code=NEXUS-MASTER
    resp_query = client.get("/dashboard?code=NEXUS-MASTER")
    assert resp_query.status_code == 200
    assert "Quantum Trading Terminal" in resp_query.text
    assert client.cookies.get("nexus_session") is not None

    # 2. Subsequent access using the cookie
    resp_cookie = client.get("/dashboard")
    assert resp_cookie.status_code == 200
    assert "Quantum Trading Terminal" in resp_cookie.text

    # 3. Access using X-Passcode header
    client_no_cookie = TestClient(app, follow_redirects=False)
    resp_hdr = client_no_cookie.get("/dashboard", headers={"X-Passcode": "NEXUS-MASTER"})
    assert resp_hdr.status_code == 200


def test_public_routes_accessible_without_auth():
    client = TestClient(app, follow_redirects=False)

    # Portal page
    resp_portal = client.get("/portal")
    assert resp_portal.status_code == 200
    assert "NEXUS GATEWAY" in resp_portal.text

    # Join page
    resp_join = client.get("/join")
    assert resp_join.status_code == 200

    # Auth verify-code API
    resp_api = client.post("/api/v1/auth/verify-code", json={"code": "NEXUS-MASTER"})
    assert resp_api.status_code == 200
    assert resp_api.json()["valid"] is True


def test_invalid_passcode_rejected():
    client = TestClient(app, follow_redirects=False)

    # Invalid code in query param redirects to portal
    resp = client.get("/dashboard?code=WRONG-CODE-999")
    assert resp.status_code == 302
    assert "/portal?redirect=/dashboard" in resp.headers["location"]

    # Invalid code in header redirects to portal
    resp_hdr = client.get("/dashboard", headers={"X-Passcode": "WRONG-CODE-999"})
    assert resp_hdr.status_code == 302

