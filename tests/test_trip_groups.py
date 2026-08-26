"""Unit & Integration Tests for Trip Groups, Friend Passcodes, and Scoped Group Invites."""
import json
import pytest
from starlette.testclient import TestClient

from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection
from earnings_engine.data.passcodes import verify_passcode
from earnings_engine.data.auth import create_session_token
from earnings_engine.data.trips import (
    init_trips_db,
    create_trip_group,
    add_group_member,
    find_existing_friend_passcode,
    get_trip_groups,
    resolve_user_accessible_trips,
    attach_trips_to_group,
    detach_trip_from_group,
    remove_group_member,
)
from earnings_engine.api.server import app


@pytest.fixture
def clean_db():
    settings = Settings()
    init_trips_db(settings)
    conn = get_db_connection(settings)
    with conn:
        conn.execute("DELETE FROM trip_groups")
        conn.execute("DELETE FROM trip_group_members")
        conn.execute("DELETE FROM trip_group_trips")
        conn.execute("DELETE FROM trips")
        conn.execute("DELETE FROM passcodes WHERE code LIKE 'NEXUS-ALICE-%' OR code LIKE 'NEXUS-GRP-%' OR code LIKE 'NEXUS-CHARLIE-%' OR code LIKE 'NEXUS-DAVID-%' OR code LIKE 'NEXUS-BOB-%'")
        conn.commit()
    yield settings


def test_trip_group_creation_and_member_flow(clean_db):
    settings = clean_db

    # 1. Create a trip
    conn = get_db_connection(settings)
    with conn:
        conn.execute("""
            INSERT INTO trips (id, title, destination, start_date, end_date, status, created_at, is_shared_with_friends)
            VALUES ('trip_bali_01', 'Bali Villa & Scuba', 'Bali, Indonesia', '2026-10-01', '2026-10-10', 'confirmed', '2026-08-26', 0)
        """)
        conn.commit()

    # 2. Create a group
    grp = create_trip_group(
        name="Bali Expedition 2026",
        description="Scuba, surf, and villas in Uluwatu",
        icon="🌴",
        trip_ids=["trip_bali_01"],
        settings=settings,
    )
    assert grp["id"].startswith("grp_")
    assert grp["group_invite_code"].startswith("NEXUS-GRP-")

    # 3. Add a new friend (Alice)
    alice_res = add_group_member(
        group_id=grp["id"],
        name="Alice",
        email="alice@example.com",
        role="member",
        send_email=False,
        settings=settings,
    )
    assert alice_res["email"] == "alice@example.com"
    assert alice_res["passcode"].startswith("NEXUS-ALICE-")
    assert alice_res["is_existing_friend"] is False

    # 4. Lookup Alice's email -> Should find existing passcode
    existing_code, existing_name = find_existing_friend_passcode("alice@example.com", settings)
    assert existing_code == alice_res["passcode"]
    assert existing_name == "Alice"

    # 5. Add Alice to a second group -> Reuses same passcode!
    grp2 = create_trip_group(
        name="Goa Weekend",
        description="Quick beach trip",
        settings=settings,
    )
    alice_res2 = add_group_member(
        group_id=grp2["id"],
        name="Alice",
        email="alice@example.com",
        role="member",
        send_email=False,
        settings=settings,
    )
    assert alice_res2["passcode"] == alice_res["passcode"]
    assert alice_res2["is_existing_friend"] is True


def test_hierarchical_trip_access(clean_db):
    settings = clean_db
    conn = get_db_connection(settings)

    # Create 3 trips:
    # 1. Private Trip (Owner only)
    # 2. Group Trip (Bali Group only)
    # 3. Public Shared Trip (All friends)
    with conn:
        conn.execute("""
            INSERT INTO trips (id, title, destination, start_date, end_date, status, created_at, is_shared_with_friends)
            VALUES ('trip_pvt', 'Secret Solo Trip', 'Swiss Alps', '2026-11-01', '2026-11-05', 'confirmed', '2026-08-26', 0)
        """)
        conn.execute("""
            INSERT INTO trips (id, title, destination, start_date, end_date, status, created_at, is_shared_with_friends)
            VALUES ('trip_bali', 'Bali Villa & Scuba', 'Bali', '2026-10-01', '2026-10-10', 'confirmed', '2026-08-26', 0)
        """)
        conn.execute("""
            INSERT INTO trips (id, title, destination, start_date, end_date, status, created_at, is_shared_with_friends)
            VALUES ('trip_pub', 'Goa Reunion', 'Goa', '2026-12-20', '2026-12-25', 'confirmed', '2026-08-26', 1)
        """)
        conn.commit()

    # Create Bali Group and attach trip_bali
    grp = create_trip_group(name="Bali Pod", trip_ids=["trip_bali"], settings=settings)
    alice = add_group_member(group_id=grp["id"], name="Alice", email="alice@test.com", send_email=False, settings=settings)

    # 1. Test Owner Session -> Sees all 3 trips
    owner_session = {"role": "owner", "scopes": ["admin", "can_view_trips"]}
    owner_trips = resolve_user_accessible_trips(owner_session, settings)
    assert len(owner_trips) == 3

    # 2. Test Alice's Personal Passcode Session -> Sees trip_bali (group) + trip_pub (public), but NOT trip_pvt
    alice_session = {"role": "friend", "email": "alice@test.com", "passcode": alice["passcode"], "scopes": ["can_view_trips"]}
    alice_trips = resolve_user_accessible_trips(alice_session, settings)
    alice_trip_ids = [t["id"] for t in alice_trips]
    assert "trip_bali" in alice_trip_ids
    assert "trip_pub" in alice_trip_ids
    assert "trip_pvt" not in alice_trip_ids

    # 3. Test Group Invite Code Session -> Sees ONLY trip_bali
    group_invite_session = {"role": "group_guest", "group_id": grp["id"], "scopes": ["can_view_trips"]}
    grp_trips = resolve_user_accessible_trips(group_invite_session, settings)
    grp_trip_ids = [t["id"] for t in grp_trips]
    assert grp_trip_ids == ["trip_bali"]


def test_verify_passcode_resolution_with_groups(clean_db):
    settings = clean_db
    grp = create_trip_group(name="Tokyo 2026", settings=settings)
    bob = add_group_member(group_id=grp["id"], name="Bob", email="bob@test.com", send_email=False, settings=settings)

    # 1. Verify Bob's personal passcode
    res_bob = verify_passcode(bob["passcode"], settings)
    assert res_bob["valid"] is True
    assert res_bob["role"] == "friend"
    assert res_bob["email"] == "bob@test.com"
    assert res_bob["name"] == "Bob"
    assert "can_view_trips" in res_bob["scopes"]

    # 2. Verify Group Invite Code
    res_grp = verify_passcode(grp["group_invite_code"], settings)
    assert res_grp["valid"] is True
    assert res_grp["role"] == "group_guest"
    assert res_grp["is_group_invite"] is True
    assert res_grp["group_id"] == grp["id"]
    assert "can_view_trips" in res_grp["scopes"]


def test_api_endpoints_trip_groups(clean_db):
    settings = clean_db
    client = TestClient(app)

    # Auth headers with owner token
    owner_token = create_session_token(
        user_id="1",
        role="owner",
        email="owner@nexus.local",
        name="Owner",
        scopes=["admin", "can_view_trips"],
    )
    headers = {"Cookie": f"nexus_session={owner_token}"}

    # 1. Create a trip
    t_res = client.post(
        "/api/v1/trips",
        headers=headers,
        json={
            "title": "Ladakh Bike Ride",
            "destination": "Leh Ladakh",
            "start_date": "2026-09-01",
            "end_date": "2026-09-12",
            "status": "confirmed",
            "estimated_budget": 80000,
            "cover_image": "swiss",
            "is_shared_with_friends": True,
        }
    )
    assert t_res.status_code == 200
    trip_id = t_res.json()["trip_id"]

    # 2. Create a Group via API
    g_res = client.post(
        "/api/v1/trips/groups",
        headers=headers,
        json={
            "name": "Bikers Circle",
            "description": "High passes and camping",
            "icon": "⛰️",
            "trip_ids": [trip_id],
            "members": [
                {"name": "Charlie", "email": "charlie@test.com", "role": "member"}
            ]
        }
    )
    assert g_res.status_code == 200
    grp_data = g_res.json()["group"]
    group_id = grp_data["id"]
    assert grp_data["group_invite_code"].startswith("NEXUS-GRP-")
    assert len(grp_data["members"]) == 1
    charlie_code = grp_data["members"][0]["passcode"]

    # 3. Lookup Friend Endpoint
    lookup_res = client.get(f"/api/v1/trips/friends/lookup?email=charlie@test.com", headers=headers)
    assert lookup_res.status_code == 200
    assert lookup_res.json()["exists"] is True
    assert lookup_res.json()["passcode"] == charlie_code

    # 4. List Groups Endpoint
    list_res = client.get("/api/v1/trips/groups", headers=headers)
    assert list_res.status_code == 200
    groups = list_res.json()["groups"]
    assert len(groups) == 1
    assert groups[0]["name"] == "Bikers Circle"
    assert groups[0]["trip_count"] == 1
    assert groups[0]["member_count"] == 1

    # 5. Add Another Member via API
    m_res = client.post(
        f"/api/v1/trips/groups/{group_id}/members",
        headers=headers,
        json={
            "name": "David",
            "email": "david@test.com",
            "role": "organizer",
            "send_email": False
        }
    )
    assert m_res.status_code == 200
    assert m_res.json()["member"]["email"] == "david@test.com"
