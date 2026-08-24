"""Unit tests for Credit Cards Hub and OTP Request/Approval APIs."""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from earnings_engine.api.server import app
from earnings_engine.data.auth import create_scoped_invite


@pytest.fixture
def owner_client():
    client = TestClient(app)
    # Login as owner using master passcode
    resp = client.post("/api/v1/auth/verify-code", json={"code": "NEXUS-MASTER"})
    assert resp.status_code == 200
    return client


@pytest.fixture
def friend_client():
    client = TestClient(app)
    # Create and login with a friend invite code having can_view_cards
    invite = create_scoped_invite(
        label="Amit Friend",
        scopes=["can_view_cards", "credit_card"],
        max_uses=5,
    )
    resp = client.post("/api/v1/auth/verify-code", json={"code": invite["code"]})
    assert resp.status_code == 200
    return client


def test_get_cards_and_roles(owner_client, friend_client):
    """Test retrieving cards for owner vs friend."""
    # Owner gets all cards
    res_owner = owner_client.get("/api/v1/cards")
    assert res_owner.status_code == 200
    data_owner = res_owner.json()
    assert data_owner["success"] is True
    assert data_owner["is_owner"] is True
    assert len(data_owner["cards"]) >= 1

    # Friend gets shared cards
    res_friend = friend_client.get("/api/v1/cards")
    assert res_friend.status_code == 200
    data_friend = res_friend.json()
    assert data_friend["success"] is True
    assert data_friend["is_owner"] is False
    for card in data_friend["cards"]:
        assert card["is_shared_with_friends"] is True


def test_create_and_delete_card(owner_client, friend_client):
    """Test adding a card by owner and access denial for friends."""
    payload = {
        "card_name": "Axis Atlas Travel Card",
        "issuer": "Axis Bank",
        "network": "Visa Signature",
        "last4": "5521",
        "card_holder": "Jatin",
        "color_theme": "sapphire-indigo",
        "credit_limit": 400000.0,
        "available_limit": 380000.0,
        "billing_cycle_day": 20,
        "category_perks": {"travel": "5 Edge Miles per ₹100", "tier": "Gold Tier Unlocked"},
        "lounge_access_summary": "12 Domestic & 4 International Visits",
        "annual_fee_status": "Paid (5000 Edge Miles Awarded)",
        "is_shared_with_friends": True,
        "display_order": 5,
    }

    # Friend cannot add a card
    res_forbidden = friend_client.post("/api/v1/cards", json=payload)
    assert res_forbidden.status_code == 403

    # Owner can add a card
    res_create = owner_client.post("/api/v1/cards", json=payload)
    assert res_create.status_code == 200
    card_id = res_create.json()["card_id"]
    assert card_id.startswith("card_")

    # Verify card exists
    res_list = owner_client.get("/api/v1/cards")
    cards = res_list.json()["cards"]
    assert any(c["id"] == card_id for c in cards)

    # Owner deletes the card
    res_delete = owner_client.delete(f"/api/v1/cards/{card_id}")
    assert res_delete.status_code == 200
    assert res_delete.json()["success"] is True


def test_otp_request_approval_workflow(owner_client, friend_client):
    """Test complete friend OTP request -> owner approval -> friend reveals OTP flow."""
    # 1. Get an existing card
    cards = friend_client.get("/api/v1/cards").json()["cards"]
    assert len(cards) > 0
    test_card_id = cards[0]["id"]

    # 2. Friend submits OTP request
    req_payload = {
        "card_id": test_card_id,
        "requested_by_name": "Rohan Friend",
        "amount": 3500.0,
        "merchant": "BookMyShow",
        "purpose": "Concert tickets for team",
        "urgency": "immediate",
    }
    res_req = friend_client.post("/api/v1/cards/otp-requests", json=req_payload)
    assert res_req.status_code == 200
    req_data = res_req.json()
    assert req_data["success"] is True
    req_id = req_data["request_id"]
    assert req_data["status"] == "pending"

    # 3. Check OTP requests list
    res_list = owner_client.get("/api/v1/cards/otp-requests")
    assert res_list.status_code == 200
    requests = res_list.json()["requests"]
    matched = [r for r in requests if r["id"] == req_id]
    assert len(matched) == 1
    assert matched[0]["status"] == "pending"
    assert matched[0]["amount"] == 3500.0

    # 4. Owner approves the request with an OTP
    res_approve = owner_client.post(
        f"/api/v1/cards/otp-requests/{req_id}/approve",
        json={"otp_code": "729401", "duration_minutes": 10, "response_notes": "Approved for concert"},
    )
    assert res_approve.status_code == 200
    app_data = res_approve.json()
    assert app_data["status"] == "approved"
    assert app_data["otp_code"] == "729401"

    # 5. Friend sees the approved request and revealed OTP
    res_friend_view = friend_client.get("/api/v1/cards/otp-requests")
    matched_friend = [r for r in res_friend_view.json()["requests"] if r["id"] == req_id]
    assert len(matched_friend) == 1
    assert matched_friend[0]["status"] == "approved"
    assert matched_friend[0]["otp_code"] == "729401"
    assert matched_friend[0]["remaining_seconds"] > 0
