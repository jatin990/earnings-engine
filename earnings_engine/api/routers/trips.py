"""Trips & Travel Expeditions Hub Routes, Groups, Members, and Activity Management."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from earnings_engine.api.dependencies import (
    _settings,
    get_template_env,
    require_scope,
    AddGroupMemberRequest,
    AddPackingItemRequest,
    AttachGroupTripsRequest,
    CreateTripGroupRequest,
    CreateTripRequest,
    SuggestTripActivityRequest,
    UpdatePackingStatusRequest,
    UpdateTripGroupRequest,
)
from earnings_engine.data.db import get_db_connection
from earnings_engine.logging_utils import get_logger

logger = get_logger("earnings_engine.api.routers.trips")

router = APIRouter(tags=["Trips & Travel Hub"])


@router.get("/trips", tags=["UI"], response_class=HTMLResponse)
async def serve_trips():
    """Serve the Trips & Travel Hub page."""
    try:
        env = get_template_env()
        template = env.get_template("hubs/trips/index.html")
        html = template.render()
        return HTMLResponse(html)
    except Exception as exc:
        return HTMLResponse(
            f"<html><body><h1>Trips Hub render error</h1><p>{exc}</p></body></html>",
            status_code=500,
        )


@router.get("/api/v1/trips")
async def get_trips_endpoint(session: dict = Depends(require_scope("can_view_trips"))):
    """Retrieve travel plans and upcoming trip itineraries with hierarchical group access."""
    from earnings_engine.data.trips import resolve_user_accessible_trips
    role = session.get("role")
    scopes = session.get("scopes", [])
    is_owner = bool(role == "owner" or "admin" in scopes or "*" in scopes)

    trips = resolve_user_accessible_trips(session, _settings)
    return {"success": True, "count": len(trips), "trips": trips, "is_owner": is_owner}


@router.post("/api/v1/trips")
async def create_trip_endpoint(req: CreateTripRequest, session: dict = Depends(require_scope("can_view_trips"))):
    """Create a new trip itinerary (Owner only)."""
    role = session.get("role")
    scopes = session.get("scopes", [])
    if role != "owner" and "admin" not in scopes and "*" not in scopes:
        raise HTTPException(status_code=403, detail="Only the vault owner can add new trips.")

    trip_id = f"trip_{uuid.uuid4().hex[:8]}"
    now_str = datetime.now().isoformat(timespec="seconds")
    packing_str = json.dumps(req.packing_list) if req.packing_list else "[]"

    conn = get_db_connection(_settings)
    with conn:
        conn.execute("""
            INSERT INTO trips (
                id, title, destination, start_date, end_date, status, notes,
                cover_image, estimated_budget, is_shared_with_friends, flight_details,
                hotel_details, packing_list, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            trip_id, req.title, req.destination, req.start_date, req.end_date,
            req.status, req.notes, req.cover_image, req.estimated_budget,
            1 if req.is_shared_with_friends else 0, req.flight_details,
            req.hotel_details, packing_str, now_str
        ))
        conn.commit()

    logger.info("[TRIPS-API] Created new trip %s (%s - %s)", trip_id, req.title, req.destination)
    return {"success": True, "trip_id": trip_id, "message": "Trip itinerary created successfully."}


@router.delete("/api/v1/trips/{trip_id}")
async def delete_trip_endpoint(trip_id: str, session: dict = Depends(require_scope("can_view_trips"))):
    """Delete a trip from the vault (Owner only)."""
    role = session.get("role")
    scopes = session.get("scopes", [])
    if role != "owner" and "admin" not in scopes and "*" not in scopes:
        raise HTTPException(status_code=403, detail="Only the vault owner can delete trips.")

    conn = get_db_connection(_settings)
    with conn:
        conn.execute("DELETE FROM trips WHERE id = ?", (trip_id,))
        conn.execute("DELETE FROM trip_activities WHERE trip_id = ?", (trip_id,))
        conn.commit()

    logger.info("[TRIPS-API] Deleted trip %s", trip_id)
    return {"success": True, "message": f"Trip {trip_id} deleted."}


@router.get("/api/v1/trips/groups")
async def get_trip_groups_endpoint(session: dict = Depends(require_scope("can_view_trips"))):
    """Retrieve all trip groups, member rosters, and attached itineraries."""
    from earnings_engine.data.trips import get_trip_groups
    role = session.get("role")
    scopes = session.get("scopes", [])
    is_owner = bool(role == "owner" or "admin" in scopes or "*" in scopes)
    user_email = session.get("email")
    passcode = session.get("passcode")

    groups = get_trip_groups(
        settings=_settings,
        filter_user_email=user_email,
        filter_passcode=passcode,
        is_owner=is_owner,
    )
    return {"success": True, "count": len(groups), "groups": groups, "is_owner": is_owner}


@router.post("/api/v1/trips/groups")
async def create_trip_group_endpoint(
    req: CreateTripGroupRequest,
    request: Request,
    session: dict = Depends(require_scope("can_view_trips")),
):
    """Create a new trip group, auto-generate invite code, add members and attach trips."""
    from earnings_engine.data.trips import create_trip_group, add_group_member
    role = session.get("role")
    scopes = session.get("scopes", [])
    if role != "owner" and "admin" not in scopes and "*" not in scopes:
        raise HTTPException(status_code=403, detail="Only the vault owner can create new trip groups.")

    base_url = str(request.base_url).rstrip("/")
    grp = create_trip_group(
        name=req.name,
        description=req.description,
        color=req.color,
        icon=req.icon,
        trip_ids=req.trip_ids,
        settings=_settings,
    )

    added_members = []
    if req.members:
        for m in req.members:
            m_name = m.get("name", "")
            m_email = m.get("email", "")
            if m_email:
                try:
                    mem_res = add_group_member(
                        group_id=grp["id"],
                        name=m_name,
                        email=m_email,
                        role=m.get("role", "member"),
                        send_email=True,
                        base_url=base_url,
                        settings=_settings,
                    )
                    added_members.append(mem_res)
                except Exception as e:
                    logger.warning("[TRIPS-API] Failed adding member %s: %s", m_email, e)

    grp["members"] = added_members
    return {"success": True, "group": grp, "message": f"Group '{req.name}' created successfully."}


@router.put("/api/v1/trips/groups/{group_id}")
async def update_trip_group_endpoint(
    group_id: str,
    req: UpdateTripGroupRequest,
    session: dict = Depends(require_scope("can_view_trips")),
):
    """Update trip group details (Owner only)."""
    role = session.get("role")
    scopes = session.get("scopes", [])
    if role != "owner" and "admin" not in scopes and "*" not in scopes:
        raise HTTPException(status_code=403, detail="Only the vault owner can update trip groups.")

    conn = get_db_connection(_settings)
    with conn:
        grp = conn.execute("SELECT id FROM trip_groups WHERE id = ?", (group_id,)).fetchone()
        if not grp:
            raise HTTPException(status_code=404, detail="Trip group not found.")

        updates = []
        params = []
        if req.name is not None:
            updates.append("name = ?")
            params.append(req.name.strip())
        if req.description is not None:
            updates.append("description = ?")
            params.append(req.description.strip())
        if req.color is not None:
            updates.append("color = ?")
            params.append(req.color)
        if req.icon is not None:
            updates.append("icon = ?")
            params.append(req.icon)

        if updates:
            params.append(group_id)
            conn.execute(f"UPDATE trip_groups SET {', '.join(updates)} WHERE id = ?", params)
            conn.commit()

    return {"success": True, "message": "Group updated successfully."}


@router.delete("/api/v1/trips/groups/{group_id}")
async def delete_trip_group_endpoint(
    group_id: str,
    session: dict = Depends(require_scope("can_view_trips")),
):
    """Delete a trip group (Owner only)."""
    role = session.get("role")
    scopes = session.get("scopes", [])
    if role != "owner" and "admin" not in scopes and "*" not in scopes:
        raise HTTPException(status_code=403, detail="Only the vault owner can delete trip groups.")

    conn = get_db_connection(_settings)
    with conn:
        conn.execute("DELETE FROM trip_groups WHERE id = ?", (group_id,))
        conn.execute("DELETE FROM trip_group_members WHERE group_id = ?", (group_id,))
        conn.execute("DELETE FROM trip_group_trips WHERE group_id = ?", (group_id,))
        conn.commit()

    logger.info("[TRIPS-API] Deleted group %s", group_id)
    return {"success": True, "message": f"Group {group_id} deleted."}


@router.post("/api/v1/trips/groups/{group_id}/members")
async def add_group_member_endpoint(
    group_id: str,
    req: AddGroupMemberRequest,
    request: Request,
    session: dict = Depends(require_scope("can_view_trips")),
):
    """Add a friend to a trip group and send direct email invite."""
    from earnings_engine.data.trips import add_group_member
    role = session.get("role")
    scopes = session.get("scopes", [])
    if role != "owner" and "admin" not in scopes and "*" not in scopes:
        raise HTTPException(status_code=403, detail="Only the vault owner can add members to groups.")

    base_url = str(request.base_url).rstrip("/")
    res = add_group_member(
        group_id=group_id,
        name=req.name,
        email=req.email,
        role=req.role,
        custom_passcode=req.custom_passcode,
        send_email=req.send_email,
        base_url=base_url,
        settings=_settings,
    )
    return {"success": True, "member": res, "message": f"Added {req.name} to group."}


@router.delete("/api/v1/trips/groups/{group_id}/members/{member_id_or_email}")
async def remove_group_member_endpoint(
    group_id: str,
    member_id_or_email: str,
    session: dict = Depends(require_scope("can_view_trips")),
):
    """Remove a friend from a trip group."""
    from earnings_engine.data.trips import remove_group_member
    role = session.get("role")
    scopes = session.get("scopes", [])
    if role != "owner" and "admin" not in scopes and "*" not in scopes:
        raise HTTPException(status_code=403, detail="Only the vault owner can remove members.")

    success = remove_group_member(group_id=group_id, email_or_id=member_id_or_email, settings=_settings)
    return {"success": success, "message": "Member removed from group."}


@router.post("/api/v1/trips/groups/{group_id}/attach-trips")
async def attach_trips_endpoint(
    group_id: str,
    req: AttachGroupTripsRequest,
    session: dict = Depends(require_scope("can_view_trips")),
):
    """Attach trips to a group."""
    from earnings_engine.data.trips import attach_trips_to_group
    role = session.get("role")
    scopes = session.get("scopes", [])
    if role != "owner" and "admin" not in scopes and "*" not in scopes:
        raise HTTPException(status_code=403, detail="Only the vault owner can attach trips.")

    count = attach_trips_to_group(group_id=group_id, trip_ids=req.trip_ids, settings=_settings)
    return {"success": True, "attached_count": count, "message": f"Attached {count} trip(s) to group."}


@router.delete("/api/v1/trips/groups/{group_id}/trips/{trip_id}")
async def detach_trip_endpoint(
    group_id: str,
    trip_id: str,
    session: dict = Depends(require_scope("can_view_trips")),
):
    """Detach a trip from a group."""
    from earnings_engine.data.trips import detach_trip_from_group
    role = session.get("role")
    scopes = session.get("scopes", [])
    if role != "owner" and "admin" not in scopes and "*" not in scopes:
        raise HTTPException(status_code=403, detail="Only the vault owner can detach trips.")

    success = detach_trip_from_group(group_id=group_id, trip_id=trip_id, settings=_settings)
    return {"success": success, "message": "Trip detached from group."}


@router.get("/api/v1/trips/friends/lookup")
async def lookup_friend_endpoint(
    email: str = Query(..., description="Friend email to check"),
    session: dict = Depends(require_scope("can_view_trips")),
):
    """Lookup if a friend's email already has an existing name or passcode in the system."""
    from earnings_engine.data.trips import find_existing_friend_passcode
    passcode, name = find_existing_friend_passcode(email, _settings)
    return {
        "exists": bool(passcode is not None),
        "email": email,
        "name": name,
        "passcode": passcode,
    }


# ---------------------------------------------------------------------------
# Itinerary endpoints (must precede /{trip_id}/activities to avoid route conflict)
# ---------------------------------------------------------------------------


@router.get("/api/v1/trips/{trip_id}/itinerary")
async def get_trip_itinerary_endpoint(
    trip_id: str, session: dict = Depends(require_scope("can_view_trips"))
):
    """Retrieve the day-by-day itinerary for a trip, ordered by day number."""
    from earnings_engine.data.trips import get_trip_itinerary

    conn = get_db_connection(_settings)
    with conn:
        days = get_trip_itinerary(conn, trip_id)
    return {"success": True, "count": len(days), "itinerary": days}


# ---------------------------------------------------------------------------
# Packing list endpoints (must precede /{trip_id}/activities to avoid route conflict)
# ---------------------------------------------------------------------------


@router.get("/api/v1/trips/{trip_id}/packing")
async def get_trip_packing_endpoint(
    trip_id: str, session: dict = Depends(require_scope("can_view_trips"))
):
    """Retrieve all packing items for a trip with per-member status dictionaries."""
    from earnings_engine.data.trips import get_packing_items

    conn = get_db_connection(_settings)
    with conn:
        items = get_packing_items(conn, trip_id)
    return {"success": True, "count": len(items), "items": items}


@router.post("/api/v1/trips/{trip_id}/packing")
async def add_packing_item_endpoint(
    trip_id: str,
    req: AddPackingItemRequest,
    session: dict = Depends(require_scope("can_view_trips")),
):
    """Add a new packing item to a trip. Any authenticated member may add items."""
    from earnings_engine.data.trips import add_packing_item

    conn = get_db_connection(_settings)
    with conn:
        item = add_packing_item(conn, trip_id, req.name, req.category, req.added_by)
    return {"success": True, "item": item}


@router.delete("/api/v1/trips/{trip_id}/packing/{item_id}")
async def delete_packing_item_endpoint(
    trip_id: str,
    item_id: str,
    session: dict = Depends(require_scope("can_view_trips")),
):
    """Delete a packing item (owner only). Removes all associated status records."""
    role = session.get("role")
    scopes = session.get("scopes", [])
    if not (role == "owner" or "admin" in scopes or "*" in scopes):
        raise HTTPException(status_code=403, detail="Owner access required to delete packing items.")

    from earnings_engine.data.trips import delete_packing_item

    conn = get_db_connection(_settings)
    with conn:
        delete_packing_item(conn, item_id)
    return {"success": True, "deleted": item_id}


@router.patch("/api/v1/trips/{trip_id}/packing/{item_id}/status")
async def update_packing_status_endpoint(
    trip_id: str,
    item_id: str,
    req: UpdatePackingStatusRequest,
    session: dict = Depends(require_scope("can_view_trips")),
):
    """Update the packing status for a (item, member) pair. Valid values: pending | packed | confirmed."""
    valid_statuses = {"pending", "packed", "confirmed"}
    if req.status not in valid_statuses:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid status '{req.status}'. Must be one of: {sorted(valid_statuses)}",
        )

    from earnings_engine.data.trips import update_packing_status

    conn = get_db_connection(_settings)
    with conn:
        row = update_packing_status(conn, item_id, req.member_name, req.status)
    return {"success": True, "status": row}


@router.get("/api/v1/trips/{trip_id}/activities")
async def get_trip_activities_endpoint(trip_id: str, session: dict = Depends(require_scope("can_view_trips"))):
    """Retrieve suggested activities and votes for a trip."""
    conn = get_db_connection(_settings)
    with conn:
        rows = conn.execute("""
            SELECT id, trip_id, suggested_by_name, suggested_by_role, activity_title, location, approx_cost, votes_count, status, created_at
            FROM trip_activities WHERE trip_id = ? ORDER BY votes_count DESC, created_at ASC
        """, (trip_id,)).fetchall()
    activities = [
        {
            "id": r[0],
            "trip_id": r[1],
            "suggested_by_name": r[2],
            "suggested_by_role": r[3],
            "activity_title": r[4],
            "location": r[5],
            "approx_cost": float(r[6] or 0.0),
            "votes_count": int(r[7] or 1),
            "status": r[8],
            "created_at": r[9],
        }
        for r in rows
    ]
    return {"success": True, "count": len(activities), "activities": activities}


@router.post("/api/v1/trips/{trip_id}/activities")
async def suggest_trip_activity_endpoint(
    trip_id: str,
    req: SuggestTripActivityRequest,
    session: dict = Depends(require_scope("can_view_trips")),
):
    """Suggest an activity or excursion for a trip."""
    role = session.get("role") or "friend"
    act_id = f"act_{uuid.uuid4().hex[:8]}"
    now_str = datetime.now().isoformat(timespec="seconds")

    conn = get_db_connection(_settings)
    with conn:
        trip = conn.execute("SELECT id, title FROM trips WHERE id = ?", (trip_id,)).fetchone()
        if not trip:
            raise HTTPException(status_code=404, detail="Trip not found.")

        conn.execute("""
            INSERT INTO trip_activities (
                id, trip_id, suggested_by_name, suggested_by_role, activity_title, location, approx_cost, votes_count, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, 'suggested', ?)
        """, (act_id, trip_id, req.suggested_by_name, role, req.activity_title, req.location, req.approx_cost, now_str))
        conn.commit()

    logger.info("[TRIPS-API] New activity '%s' suggested by %s for %s", req.activity_title, req.suggested_by_name, trip[1])
    return {"success": True, "activity_id": act_id, "message": f"Activity '{req.activity_title}' suggested!"}


@router.post("/api/v1/trips/{trip_id}/activities/{activity_id}/vote")
async def vote_trip_activity_endpoint(
    trip_id: str,
    activity_id: str,
    session: dict = Depends(require_scope("can_view_trips")),
):
    """Upvote a suggested trip activity."""
    conn = get_db_connection(_settings)
    with conn:
        conn.execute("UPDATE trip_activities SET votes_count = votes_count + 1 WHERE id = ? AND trip_id = ?", (activity_id, trip_id))
        conn.commit()
        row = conn.execute("SELECT votes_count FROM trip_activities WHERE id = ?", (activity_id,)).fetchone()
        votes = row[0] if row else 1
    return {"success": True, "activity_id": activity_id, "votes_count": votes}


@router.delete("/api/v1/trips/{trip_id}/activities/{activity_id}")
async def delete_trip_activity_endpoint(
    trip_id: str,
    activity_id: str,
    session: dict = Depends(require_scope("can_view_trips")),
):
    """Delete a suggested trip activity."""
    conn = get_db_connection(_settings)
    with conn:
        conn.execute("DELETE FROM trip_activities WHERE id = ? AND trip_id = ?", (activity_id, trip_id))
        conn.commit()
    return {"success": True, "message": f"Activity {activity_id} removed."}

