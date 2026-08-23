"""Unit tests for the passcode authentication and route permission engine."""
import pytest
from starlette.testclient import TestClient

from earnings_engine.data.passcodes import (
    create_passcode,
    delete_passcode,
    init_passcodes,
    list_passcodes,
    verify_passcode,
)
from earnings_engine.api.server import app


def test_init_and_default_passcodes():
    init_passcodes()
    codes = list_passcodes()
    assert len(codes) >= 4

    master = next((c for c in codes if c["code"] == "NEXUS-MASTER"), None)
    assert master is not None
    assert "dashboard" in master["allowed_routes"]
    assert "credit_card" in master["allowed_routes"]
    assert "admin" in master["allowed_routes"]


def test_verify_passcode_permissions():
    init_passcodes()
    
    # Master code
    res_master = verify_passcode("NEXUS-MASTER")
    assert res_master["valid"] is True
    assert res_master["is_admin"] is True
    assert "dashboard" in res_master["allowed_routes"]
    assert "credit_card" in res_master["allowed_routes"]

    # Trader only code
    res_trader = verify_passcode("TRADER-VIP")
    assert res_trader["valid"] is True
    assert res_trader["is_admin"] is False
    assert "dashboard" in res_trader["allowed_routes"]
    assert "credit_card" not in res_trader["allowed_routes"]

    # Invalid code
    res_invalid = verify_passcode("INVALID-CODE-XYZ")
    assert res_invalid["valid"] is False


def test_create_and_delete_passcode():
    created = create_passcode(
        label="Test Friend",
        allowed_routes=["dashboard", "credit_card"],
        code="FRIEND-TEST-99",
    )
    assert created["code"] == "FRIEND-TEST-99"
    assert created["label"] == "Test Friend"

    verified = verify_passcode("FRIEND-TEST-99")
    assert verified["valid"] is True
    assert verified["label"] == "Test Friend"
    assert "credit_card" in verified["allowed_routes"]

    deleted = delete_passcode("FRIEND-TEST-99")
    assert deleted is True

    verified_after = verify_passcode("FRIEND-TEST-99")
    assert verified_after["valid"] is False


def test_passcode_api_endpoints():
    client = TestClient(app)

    # 1. Verify code endpoint
    resp = client.post("/api/v1/auth/verify-code", json={"code": "NEXUS-MASTER"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is True
    assert data["code"] == "NEXUS-MASTER"
    assert data["is_admin"] is True

    # 2. Invalid code endpoint
    resp_err = client.post("/api/v1/auth/verify-code", json={"code": "NON-EXISTENT"})
    assert resp_err.status_code == 401

    # 3. Create code endpoint
    resp_create = client.post("/api/v1/auth/codes", json={
        "label": "API Friend",
        "code": "API-FRIEND-01",
        "allowed_routes": ["dashboard"],
    })
    assert resp_create.status_code == 200
    created = resp_create.json()
    assert created["code"] == "API-FRIEND-01"

    # 4. List codes endpoint
    resp_list = client.get("/api/v1/auth/codes")
    assert resp_list.status_code == 200
    codes = resp_list.json()["passcodes"]
    assert any(c["code"] == "API-FRIEND-01" for c in codes)

    # 5. Delete code endpoint
    resp_del = client.delete("/api/v1/auth/codes/API-FRIEND-01")
    assert resp_del.status_code == 200

    # 6. Portal and Credit Card HTML routes
    portal_resp = client.get("/portal")
    assert portal_resp.status_code == 200
    assert "NEXUS GATEWAY" in portal_resp.text

    cards_resp = client.get("/credit-card")
    assert cards_resp.status_code == 200
    assert "OBSIDIAN INFINITE" in cards_resp.text
