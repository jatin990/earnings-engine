import os
import json
import pytest
from starlette.testclient import TestClient
from earnings_engine.api.server import app
from earnings_engine.data.auth import create_session_token
from earnings_engine.data.migrations import apply_migrations


@pytest.fixture(autouse=True)
def setup_db(monkeypatch):
    monkeypatch.setenv("TURSO_DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("TURSO_AUTH_TOKEN", "")
    apply_migrations()


def test_trips_workflow_and_rbac():
    client = TestClient(app)

    owner_token = create_session_token(
        user_id="usr_owner",
        role="owner",
        email="owner@nexus.local",
        name="Nexus Owner",
        scopes=["admin", "dashboard", "can_view_trips", "can_view_cards", "can_view_net_worth"],
    )

    friend_token = create_session_token(
        user_id="usr_friend_trips",
        role="friend",
        email="friend@nexus.local",
        name="Friend User",
        scopes=["can_view_trips"],
    )

    unauth_token = create_session_token(
        user_id="usr_no_trips",
        role="friend",
        email="noaccess@nexus.local",
        name="No Access User",
        scopes=["dashboard"],
    )

    # 1. Unauthenticated request -> 401
    resp_unauth = client.get("/api/v1/trips")
    assert resp_unauth.status_code == 401

    # 2. Friend without trips scope -> 403
    resp_forbidden = client.get("/api/v1/trips", headers={"Authorization": f"Bearer {unauth_token}"})
    assert resp_forbidden.status_code == 403

    # 3. Friend with trips scope -> 200 (gets shared trips)
    resp_friend = client.get("/api/v1/trips", headers={"Authorization": f"Bearer {friend_token}"})
    assert resp_friend.status_code == 200
    data_friend = resp_friend.json()
    assert data_friend["success"] is True
    assert data_friend["is_owner"] is False
    assert len(data_friend["trips"]) >= 1
    trip_id = data_friend["trips"][0]["id"]

    # 4. Friend suggests an activity -> 200
    act_resp = client.post(
        f"/api/v1/trips/{trip_id}/activities",
        headers={"Authorization": f"Bearer {friend_token}"},
        json={
            "suggested_by_name": "Rohan Test",
            "activity_title": "Mount Fuji Viewpoint Sunrise",
            "location": "Hakone, Japan",
            "approx_cost": 3500.0,
        },
    )
    assert act_resp.status_code == 200
    assert act_resp.json()["success"] is True

    # 5. Retrieve activities for trip
    get_acts_resp = client.get(
        f"/api/v1/trips/{trip_id}/activities",
        headers={"Authorization": f"Bearer {friend_token}"},
    )
    assert get_acts_resp.status_code == 200
    assert get_acts_resp.json()["count"] >= 1

    # 6. Friend cannot create trip (Owner only) -> 403
    create_fail = client.post(
        "/api/v1/trips",
        headers={"Authorization": f"Bearer {friend_token}"},
        json={
            "title": "Unauthorized Trip",
            "destination": "Nowhere",
            "start_date": "2027-01-01",
        },
    )
    assert create_fail.status_code == 403

    # 7. Owner creates new trip -> 200
    create_ok = client.post(
        "/api/v1/trips",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "title": "Iceland Arctic Expedition",
            "destination": "Reykjavik, Iceland",
            "start_date": "2027-02-10",
            "end_date": "2027-02-20",
            "status": "confirmed",
            "estimated_budget": 350000.0,
            "cover_image": "aurora",
            "flight_details": "Qatar Airways QR-556",
            "hotel_details": "The Reykjavik EDITION",
            "notes": "Aurora hunting and ice caves",
            "is_shared_with_friends": True,
            "packing_list": ["Thermal layers", "Tripod"],
        },
    )
    assert create_ok.status_code == 200
    new_trip_id = create_ok.json()["trip_id"]

    # 8. Owner deletes trip -> 200
    del_ok = client.delete(
        f"/api/v1/trips/{new_trip_id}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert del_ok.status_code == 200


def test_net_worth_workflow_and_rbac():
    client = TestClient(app)

    owner_token = create_session_token(
        user_id="usr_owner",
        role="owner",
        email="owner@nexus.local",
        name="Nexus Owner",
        scopes=["admin", "dashboard", "can_view_net_worth"],
    )

    friend_token = create_session_token(
        user_id="usr_friend_nw",
        role="friend",
        email="friend@nexus.local",
        name="Friend User",
        scopes=["can_view_net_worth"],
    )

    unauth_token = create_session_token(
        user_id="usr_no_nw",
        role="friend",
        email="noaccess@nexus.local",
        name="No Access User",
        scopes=["dashboard"],
    )

    # 1. Unauthenticated request -> 401
    assert client.get("/api/v1/net-worth").status_code == 401

    # 2. Friend without scope -> 403
    assert client.get("/api/v1/net-worth", headers={"Authorization": f"Bearer {unauth_token}"}).status_code == 403

    # 3. Friend with net worth scope -> 200 (Safe band view)
    resp_nw = client.get("/api/v1/net-worth", headers={"Authorization": f"Bearer {friend_token}"})
    assert resp_nw.status_code == 200
    data_nw = resp_nw.json()
    assert data_nw["success"] is True
    assert data_nw["snapshot"]["total_net_worth_band"] is not None
    assert data_nw["is_owner"] is False

    # 4. Net worth history -> 200
    resp_hist = client.get("/api/v1/net-worth/history", headers={"Authorization": f"Bearer {friend_token}"})
    assert resp_hist.status_code == 200
    assert len(resp_hist.json()["history"]) >= 1

    # 5. Friend cannot update net worth -> 403
    upd_fail = client.post(
        "/api/v1/net-worth",
        headers={"Authorization": f"Bearer {friend_token}"},
        json={
            "as_of_date": "2026-09-01",
            "total_net_worth_band": "₹3.0Cr - ₹4.0Cr Band",
            "allocation_pct": {"Indian Equities": 60, "Debt & Liquid Funds": 40},
            "yoy_growth_pct": 30.0,
        },
    )
    assert upd_fail.status_code == 403

    # 6. Owner updates net worth snapshot -> 200
    upd_ok = client.post(
        "/api/v1/net-worth",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "as_of_date": "2026-09-01",
            "total_net_worth_band": "₹3.0Cr - ₹4.0Cr Band",
            "allocation_pct": {"Indian Equities": 60, "Debt & Liquid Funds": 40},
            "yoy_growth_pct": 30.0,
        },
    )
    assert upd_ok.status_code == 200
    assert upd_ok.json()["success"] is True


def test_html_views_serve_trips_and_net_worth():
    client = TestClient(app)

    owner_token = create_session_token(
        user_id="usr_owner",
        role="owner",
        email="owner@nexus.local",
        name="Nexus Owner",
        scopes=["admin", "dashboard", "can_view_trips", "can_view_net_worth"],
    )

    resp_trips = client.get("/trips", headers={"Authorization": f"Bearer {owner_token}"})
    assert resp_trips.status_code == 200
    assert "TRIPS & EXPEDITIONS" in resp_trips.text

    resp_nw = client.get("/net-worth", headers={"Authorization": f"Bearer {owner_token}"})
    assert resp_nw.status_code == 200
    assert "NET WORTH & WEALTH ALLOCATION" in resp_nw.text
