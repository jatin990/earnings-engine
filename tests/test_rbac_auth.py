"""Unit and integration tests for RBAC, Email OTP Onboarding, and Scoped Entity Endpoints."""
import pytest
from starlette.testclient import TestClient

from earnings_engine.api.server import app
from earnings_engine.data.auth import (
    create_scoped_invite,
    create_session_token,
    hash_otp,
    list_friends,
    owner_login,
    request_otp_for_invite,
    revoke_friend_access,
    update_friend_scopes,
    verify_otp_for_invite,
    verify_session_token,
)
from earnings_engine.data.migrations import apply_migrations


@pytest.fixture(autouse=True)
def ensure_db_migrated():
    apply_migrations()


def test_session_token_signing_and_verification():
    token = create_session_token(
        user_id="usr_test_123",
        role="friend",
        email="alex@test.com",
        name="Alex",
        scopes=["can_view_trips", "can_view_cards"],
    )
    assert token is not None
    assert "." in token

    payload = verify_session_token(token)
    assert payload is not None
    assert payload["sub"] == "usr_test_123"
    assert payload["role"] == "friend"
    assert payload["email"] == "alex@test.com"
    assert "can_view_trips" in payload["scopes"]
    assert "can_view_cards" in payload["scopes"]

    # Tampered token fails
    tampered = token[:-4] + "abcd"
    assert verify_session_token(tampered) is None


def test_request_and_verify_otp_flow():
    # 1. Create a scoped invite
    inv = create_scoped_invite(
        label="Sarah (Trips & Cards)",
        scopes=["can_view_trips", "can_view_cards"],
        max_uses=1,
        custom_code="TEST-SARAH-99",
    )
    assert inv["code"] == "TEST-SARAH-99"

    # 2. Request OTP for invite
    req_res = request_otp_for_invite(
        invite_code="TEST-SARAH-99",
        email="sarah@example.com",
    )
    assert req_res["success"] is True
    assert req_res["dev_otp"] is not None
    otp_code = req_res["dev_otp"]

    # 3. Verify OTP with incorrect code first
    fail_res = verify_otp_for_invite(
        invite_code="TEST-SARAH-99",
        email="sarah@example.com",
        otp="000000",
    )
    assert fail_res["success"] is False
    assert "Invalid verification code" in fail_res["error"]

    # 4. Verify OTP with correct code
    pass_res = verify_otp_for_invite(
        invite_code="TEST-SARAH-99",
        email="sarah@example.com",
        otp=otp_code,
    )
    assert pass_res["success"] is True
    assert pass_res["session_token"] is not None
    assert pass_res["user"]["email"] == "sarah@example.com"
    assert "can_view_trips" in pass_res["user"]["scopes"]
    assert "can_view_cards" in pass_res["user"]["scopes"]

    # 5. Single use invite code should now be exhausted
    second_req = request_otp_for_invite(
        invite_code="TEST-SARAH-99",
        email="sarah@example.com",
    )
    assert second_req["success"] is False
    assert "maximum allowed uses" in second_req["error"]


def test_invite_email_lock_enforcement():
    # Create invite locked to specific email
    inv = create_scoped_invite(
        label="Locked Invite",
        scopes=["can_view_trips"],
        allowed_email="only_me@test.com",
        custom_code="LOCKED-CODE-88",
    )
    assert inv["code"] == "LOCKED-CODE-88"

    # Request from different email rejected
    res_wrong = request_otp_for_invite(
        invite_code="LOCKED-CODE-88",
        email="imposter@test.com",
    )
    assert res_wrong["success"] is False
    assert "restricted to a specific recipient email" in res_wrong["error"]

    # Request from correct email accepted
    res_correct = request_otp_for_invite(
        invite_code="LOCKED-CODE-88",
        email="only_me@test.com",
    )
    assert res_correct["success"] is True


def test_owner_login_and_friend_management():
    # Owner login
    owner_res = owner_login(passcode="NEXUS-MASTER", email="owner@nexus.local")
    assert owner_res["success"] is True
    assert owner_res["user"]["role"] == "owner"
    assert "can_view_net_worth" in owner_res["user"]["scopes"]
    owner_token = owner_res["session_token"]

    client = TestClient(app)

    # 1. Owner can list friends
    resp_friends = client.get(
        "/api/v1/friends",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert resp_friends.status_code == 200
    friends_list = resp_friends.json()["friends"]
    assert isinstance(friends_list, list)

    # 2. Owner can generate new invite via API
    resp_inv = client.post(
        "/api/v1/invites",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "label": "API Generated Friend",
            "scopes": ["can_view_trips"],
            "max_uses": 2,
        },
    )
    assert resp_inv.status_code == 200
    created_code = resp_inv.json()["code"]
    assert created_code.startswith("NEXUS-")


def test_rbac_scope_guards_on_protected_endpoints():
    client = TestClient(app)

    # 1. Unauthenticated request to trips -> 401
    resp_unauth = client.get("/api/v1/trips")
    assert resp_unauth.status_code == 401

    # 2. Friend with only 'can_view_trips'
    trips_only_token = create_session_token(
        user_id="usr_trips_only",
        role="friend",
        email="traveler@test.com",
        name="Traveler",
        scopes=["can_view_trips"],
    )

    # Can access /trips -> 200
    resp_trips = client.get(
        "/api/v1/trips",
        headers={"Authorization": f"Bearer {trips_only_token}"},
    )
    assert resp_trips.status_code == 200
    assert "trips" in resp_trips.json()
    assert len(resp_trips.json()["trips"]) >= 1

    # Cannot access /net-worth -> 403 Forbidden
    resp_nw_forbidden = client.get(
        "/api/v1/net-worth",
        headers={"Authorization": f"Bearer {trips_only_token}"},
    )
    assert resp_nw_forbidden.status_code == 403
    assert "Access forbidden" in resp_nw_forbidden.json()["detail"]

    # 3. Friend with 'can_view_cards' and 'can_view_net_worth'
    wealth_token = create_session_token(
        user_id="usr_wealth_friend",
        role="friend",
        email="wealth@test.com",
        name="Wealth Friend",
        scopes=["can_view_cards", "can_view_net_worth"],
    )

    # Can access /cards -> 200
    resp_cards = client.get(
        "/api/v1/cards",
        headers={"Authorization": f"Bearer {wealth_token}"},
    )
    assert resp_cards.status_code == 200
    assert "cards" in resp_cards.json()

    # Can access /net-worth -> 200
    resp_nw = client.get(
        "/api/v1/net-worth",
        headers={"Authorization": f"Bearer {wealth_token}"},
    )
    assert resp_nw.status_code == 200
    assert "snapshot" in resp_nw.json()
    assert resp_nw.json()["snapshot"]["total_net_worth_band"] is not None

    # 4. Owner has unrestricted access to everything
    owner_token = create_session_token(
        user_id="usr_owner_001",
        role="owner",
        email="owner@test.com",
        name="Owner",
        scopes=[],
    )
    assert client.get("/api/v1/trips", headers={"Authorization": f"Bearer {owner_token}"}).status_code == 200
    assert client.get("/api/v1/cards", headers={"Authorization": f"Bearer {owner_token}"}).status_code == 200
    assert client.get("/api/v1/net-worth", headers={"Authorization": f"Bearer {owner_token}"}).status_code == 200
