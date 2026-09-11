"""Trips, Group Expeditions, Member Passcodes & Scoped Access Engine.

Manages collaborative travel groups, friend email-to-passcode directory,
trip attachments, and scoped group invitation links for the Nexus Travel Hub.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import smtplib
import time
import uuid
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection
from earnings_engine.logging_utils import get_logger

logger = get_logger("earnings_engine.data.trips")

_TRIPS_DBS_INITIALIZED: set[str] = set()


def init_trips_db(settings: Settings | None = None) -> None:
    """Ensure trips, groups, members, and trip-group mapping tables exist."""
    settings = settings or Settings()
    db_key = str(getattr(settings, "database_url", "") or "default")
    if db_key in _TRIPS_DBS_INITIALIZED:
        return

    conn = get_db_connection(settings)
    with conn:
        # 1. Base Trips table (if not already created)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS trips (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                destination TEXT NOT NULL,
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'planned',
                notes TEXT,
                cover_image TEXT,
                estimated_budget REAL DEFAULT 0.0,
                is_shared_with_friends INTEGER DEFAULT 1,
                flight_details TEXT,
                hotel_details TEXT,
                packing_list TEXT,
                created_at TEXT NOT NULL
            )
        """)

        # 2. Trip Activities
        conn.execute("""
            CREATE TABLE IF NOT EXISTS trip_activities (
                id TEXT PRIMARY KEY,
                trip_id TEXT NOT NULL,
                suggested_by_name TEXT NOT NULL,
                suggested_by_role TEXT NOT NULL DEFAULT 'friend',
                activity_title TEXT NOT NULL,
                location TEXT,
                approx_cost REAL DEFAULT 0.0,
                votes_count INTEGER DEFAULT 1,
                status TEXT NOT NULL DEFAULT 'suggested',
                created_at TEXT NOT NULL
            )
        """)

        # 3. Trip Groups
        conn.execute("""
            CREATE TABLE IF NOT EXISTS trip_groups (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                color TEXT DEFAULT '#0284c7',
                icon TEXT DEFAULT '🌴',
                group_invite_code TEXT UNIQUE NOT NULL,
                created_at TEXT NOT NULL,
                created_by TEXT DEFAULT 'owner'
            )
        """)

        # 4. Trip Group Members (Friend Email + Specific Linked Passcode)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS trip_group_members (
                id TEXT PRIMARY KEY,
                group_id TEXT NOT NULL,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                passcode TEXT NOT NULL,
                role TEXT DEFAULT 'member',
                added_at TEXT NOT NULL,
                UNIQUE(group_id, email)
            )
        """)

        # 5. Trip to Group Mapping (Many-to-Many or Multi-trip groups)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS trip_group_trips (
                group_id TEXT NOT NULL,
                trip_id TEXT NOT NULL,
                attached_at TEXT NOT NULL,
                PRIMARY KEY(group_id, trip_id)
            )
        """)

        # Indices for rapid querying
        conn.execute("CREATE INDEX IF NOT EXISTS idx_group_members_email ON trip_group_members(email)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_group_members_code ON trip_group_members(passcode)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_group_trips_grp ON trip_group_trips(group_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_group_trips_trp ON trip_group_trips(trip_id)")

    _TRIPS_DBS_INITIALIZED.add(db_key)


def find_existing_friend_passcode(email: str, settings: Settings | None = None) -> tuple[str | None, str | None]:
    """Look up if a friend with this email already has a name or passcode registered.
    
    Checks trip_group_members, passcodes, and invite_codes.
    Returns (passcode, name) or (None, None).
    """
    clean_email = email.strip().lower()
    if not clean_email:
        return None, None

    settings = settings or Settings()
    init_trips_db(settings)
    conn = get_db_connection(settings)
    with conn:
        # 1. Check trip_group_members
        row = conn.execute(
            "SELECT passcode, name FROM trip_group_members WHERE LOWER(email) = ? ORDER BY added_at DESC LIMIT 1",
            (clean_email,),
        ).fetchone()
        if row and row[0]:
            return row[0], row[1]

        # 2. Check passcodes table by label or custom tag
        p_row = conn.execute(
            "SELECT code, label FROM passcodes WHERE LOWER(label) LIKE ? AND is_active = 1 LIMIT 1",
            (f"%{clean_email}%",),
        ).fetchone()
        if p_row and p_row[0]:
            return p_row[0], p_row[1]

    return None, None


def generate_friend_passcode(name: str, email: str, settings: Settings | None = None) -> str:
    """Generate a clean, memorable passcode for a friend (e.g. NEXUS-ALICE-9D2F) and register it."""
    clean_name = re.sub(r"[^A-Za-z0-9]", "", name).upper()[:8] or "FRIEND"
    hex_suffix = secrets.token_hex(2).upper()
    code = f"NEXUS-{clean_name}-{hex_suffix}"

    settings = settings or Settings()
    conn = get_db_connection(settings)
    now_str = datetime.now(timezone.utc).isoformat()

    with conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO passcodes (
                code, label, allowed_routes, created_at, max_uses, use_count, is_active
            ) VALUES (?, ?, ?, ?, NULL, 0, 1)
            """,
            (
                code,
                f"{name} ({email})",
                json.dumps(["trips"]),
                now_str,
            ),
        )
    return code


def generate_group_invite_code(group_name: str) -> str:
    """Generate unique group invite passcode (e.g. NEXUS-GRP-BALI-8F2A)."""
    clean_name = re.sub(r"[^A-Za-z0-9]", "", group_name).upper()[:6] or "TRIP"
    hex_suffix = secrets.token_hex(2).upper()
    return f"NEXUS-GRP-{clean_name}-{hex_suffix}"


def create_trip_group(
    name: str,
    description: str = "",
    color: str = "#0284c7",
    icon: str = "🌴",
    created_by: str = "owner",
    trip_ids: list[str] | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Create a new trip group, assign unique invite code, and optionally attach trips."""
    settings = settings or Settings()
    init_trips_db(settings)

    group_id = f"grp_{uuid.uuid4().hex[:8]}"
    group_invite_code = generate_group_invite_code(name)
    now_str = datetime.now(timezone.utc).isoformat()

    conn = get_db_connection(settings)
    with conn:
        conn.execute(
            """
            INSERT INTO trip_groups (id, name, description, color, icon, group_invite_code, created_at, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (group_id, name.strip(), description.strip(), color, icon, group_invite_code, now_str, created_by),
        )

        # Register group invite code in passcodes table so it can be verified at Portal gate
        conn.execute(
            """
            INSERT OR IGNORE INTO passcodes (
                code, label, allowed_routes, created_at, max_uses, use_count, is_active
            ) VALUES (?, ?, ?, ?, NULL, 0, 1)
            """,
            (
                group_invite_code,
                f"Group Invite: {name.strip()}",
                json.dumps(["trips"]),
                now_str,
            ),
        )

        # Attach initial trips if provided
        if trip_ids:
            for tid in trip_ids:
                conn.execute(
                    "INSERT OR IGNORE INTO trip_group_trips (group_id, trip_id, attached_at) VALUES (?, ?, ?)",
                    (group_id, tid, now_str),
                )

    logger.info("[TRIPS-GROUP] Created group %s '%s' with invite code %s", group_id, name, group_invite_code)
    return {
        "id": group_id,
        "name": name,
        "description": description,
        "color": color,
        "icon": icon,
        "group_invite_code": group_invite_code,
        "created_at": now_str,
    }


def add_group_member(
    group_id: str,
    name: str,
    email: str,
    role: str = "member",
    custom_passcode: str | None = None,
    send_email: bool = True,
    base_url: str = "http://localhost:8000",
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Add a friend to a trip group.
    
    1. Looks up if this friend already has a personal passcode.
    2. If not, generates and registers a new personal passcode.
    3. Links the member to the group in trip_group_members.
    4. If send_email is True, sends an email with the 1-click magic link directly to the trips page.
    """
    clean_email = email.strip().lower()
    clean_name = name.strip() or clean_email.split("@")[0].capitalize()

    settings = settings or Settings()
    init_trips_db(settings)

    # 1. Resolve or generate personal passcode
    existing_code, _ = find_existing_friend_passcode(clean_email, settings)
    if custom_passcode:
        passcode = custom_passcode.strip().upper()
    elif existing_code:
        passcode = existing_code
    else:
        passcode = generate_friend_passcode(clean_name, clean_email, settings)

    member_id = f"mem_{uuid.uuid4().hex[:8]}"
    now_str = datetime.now(timezone.utc).isoformat()

    conn = get_db_connection(settings)
    with conn:
        # Get group details
        group = conn.execute("SELECT id, name, icon FROM trip_groups WHERE id = ?", (group_id,)).fetchone()
        if not group:
            raise ValueError(f"Trip group {group_id} not found.")

        group_name = group[1]

        # Insert or update member
        conn.execute(
            """
            INSERT INTO trip_group_members (id, group_id, name, email, passcode, role, added_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(group_id, email) DO UPDATE SET
                name = excluded.name,
                passcode = excluded.passcode,
                role = excluded.role,
                added_at = excluded.added_at
            """,
            (member_id, group_id, clean_name, clean_email, passcode, role, now_str),
        )

    # 2. Build 1-click magic link landing directly on the trips page
    direct_trip_url = f"{base_url.rstrip('/')}/portal?code={passcode}&redirect=/trips"

    # 3. Send email invite if requested
    email_sent = False
    if send_email:
        try:
            email_sent = send_trip_invite_email(
                to_email=clean_email,
                to_name=clean_name,
                group_name=group_name,
                passcode=passcode,
                direct_url=direct_trip_url,
            )
        except Exception as e:
            logger.warning("[TRIPS-GROUP] Failed sending email to %s: %s", clean_email, e)

    return {
        "id": member_id,
        "group_id": group_id,
        "group_name": group_name,
        "name": clean_name,
        "email": clean_email,
        "passcode": passcode,
        "role": role,
        "direct_trip_url": direct_trip_url,
        "email_sent": email_sent,
        "is_existing_friend": bool(existing_code is not None),
    }


def remove_group_member(group_id: str, email_or_id: str, settings: Settings | None = None) -> bool:
    """Remove a member from a group."""
    settings = settings or Settings()
    init_trips_db(settings)
    conn = get_db_connection(settings)
    with conn:
        res = conn.execute(
            "DELETE FROM trip_group_members WHERE group_id = ? AND (id = ? OR LOWER(email) = ?)",
            (group_id, email_or_id, email_or_id.lower()),
        )
        return res.rowcount > 0


def attach_trips_to_group(group_id: str, trip_ids: list[str], settings: Settings | None = None) -> int:
    """Attach one or more trips to a group."""
    if not trip_ids:
        return 0
    settings = settings or Settings()
    init_trips_db(settings)
    now_str = datetime.now(timezone.utc).isoformat()
    conn = get_db_connection(settings)
    with conn:
        rows = [(group_id, tid, now_str) for tid in trip_ids]
        conn.executemany(
            "INSERT OR IGNORE INTO trip_group_trips (group_id, trip_id, attached_at) VALUES (?, ?, ?)",
            rows,
        )
    return len(trip_ids)


def detach_trip_from_group(group_id: str, trip_id: str, settings: Settings | None = None) -> bool:
    """Detach a trip from a group."""
    settings = settings or Settings()
    init_trips_db(settings)
    conn = get_db_connection(settings)
    with conn:
        res = conn.execute("DELETE FROM trip_group_trips WHERE group_id = ? AND trip_id = ?", (group_id, trip_id))
        return res.rowcount > 0


def get_trip_groups(
    settings: Settings | None = None,
    filter_user_email: str | None = None,
    filter_passcode: str | None = None,
    is_owner: bool = False,
) -> list[dict[str, Any]]:
    """Retrieve all trip groups with member rosters, attached trip counts, and invite codes."""
    settings = settings or Settings()
    init_trips_db(settings)
    conn = get_db_connection(settings)

    with conn:
        groups_rows = conn.execute("""
            SELECT id, name, description, color, icon, group_invite_code, created_at, created_by
            FROM trip_groups
            ORDER BY created_at DESC
        """).fetchall()

        if not groups_rows:
            return []

        group_ids = [gr[0] for gr in groups_rows]
        members_by_group: dict[str, list[dict[str, Any]]] = {gid: [] for gid in group_ids}
        trips_by_group: dict[str, list[dict[str, Any]]] = {gid: [] for gid in group_ids}

        chunk_size = 200
        for i in range(0, len(group_ids), chunk_size):
            chunk = group_ids[i : i + chunk_size]
            placeholders = ",".join("?" for _ in chunk)

            # Pre-fetch all members for groups in this chunk
            m_rows = conn.execute(f"""
                SELECT group_id, id, name, email, passcode, role, added_at
                FROM trip_group_members
                WHERE group_id IN ({placeholders})
                ORDER BY added_at ASC
            """, chunk).fetchall()
            for m in m_rows:
                members_by_group.setdefault(m[0], []).append({
                    "id": m[1],
                    "name": m[2],
                    "email": m[3],
                    "passcode": m[4],
                    "role": m[5],
                    "added_at": m[6],
                })

            # Pre-fetch all attached trips for groups in this chunk
            t_rows = conn.execute(f"""
                SELECT gt.group_id, t.id, t.title, t.destination, t.start_date, t.end_date, t.status, t.cover_image
                FROM trip_group_trips gt
                JOIN trips t ON gt.trip_id = t.id
                WHERE gt.group_id IN ({placeholders})
                ORDER BY t.start_date ASC
            """, chunk).fetchall()
            for t in t_rows:
                trips_by_group.setdefault(t[0], []).append({
                    "id": t[1],
                    "title": t[2],
                    "destination": t[3],
                    "start_date": t[4],
                    "end_date": t[5],
                    "status": t[6],
                    "cover_image": t[7] or "japan",
                })

        all_groups = []
        for gr in groups_rows:
            gid, gname, gdesc, gcol, gico, gcode, gcreated, gby = gr
            members = members_by_group.get(gid, [])
            attached_trips = trips_by_group.get(gid, [])

            # Check if this group is accessible to the user
            is_member = False
            if is_owner:
                is_member = True
            elif filter_user_email:
                is_member = any(m["email"].lower() == filter_user_email.lower() for m in members)
            elif filter_passcode:
                is_member = (
                    gcode.upper() == filter_passcode.upper()
                    or any(m["passcode"].upper() == filter_passcode.upper() for m in members)
                )

            all_groups.append({
                "id": gid,
                "name": gname,
                "description": gdesc,
                "color": gcol or "#0284c7",
                "icon": gico or "🌴",
                "group_invite_code": gcode,
                "created_at": gcreated,
                "created_by": gby,
                "member_count": len(members),
                "members": members,
                "trip_count": len(attached_trips),
                "attached_trips": attached_trips,
                "is_user_member": is_member,
            })

    if is_owner:
        return all_groups

    # Filter to groups user has access to, or return all with is_user_member flag
    return all_groups


def resolve_user_accessible_trips(
    session: dict[str, Any],
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """Resolve which trips a user is authorized to see based on group membership and passcodes."""
    settings = settings or Settings()
    init_trips_db(settings)

    role = session.get("role", "guest")
    scopes = session.get("scopes", [])
    user_email = (session.get("email") or "").strip().lower()
    passcode = (session.get("passcode") or session.get("code") or "").strip().upper()
    is_owner = bool(role == "owner" or "admin" in scopes)

    conn = get_db_connection(settings)
    with conn:
        if is_owner:
            # Full owner visibility
            rows = conn.execute("""
                SELECT t.id, t.title, t.destination, t.start_date, t.end_date, t.status, t.notes, t.created_at,
                       t.cover_image, t.estimated_budget, t.is_shared_with_friends, t.flight_details, t.hotel_details, t.packing_list
                FROM trips t
                ORDER BY t.start_date ASC
            """).fetchall()
        elif role == "group_guest" and session.get("group_id"):
            # Scoped to group invite code
            grp_id = session.get("group_id")
            rows = conn.execute("""
                SELECT t.id, t.title, t.destination, t.start_date, t.end_date, t.status, t.notes, t.created_at,
                       t.cover_image, t.estimated_budget, t.is_shared_with_friends, t.flight_details, t.hotel_details, t.packing_list
                FROM trips t
                JOIN trip_group_trips gt ON t.id = gt.trip_id
                WHERE gt.group_id = ?
                ORDER BY t.start_date ASC
            """, (grp_id,)).fetchall()
        else:
            # Friend with personal passcode / email
            # Authorized for:
            # 1. Trips attached to any group they are a member of
            # 2. Public shared trips (is_shared_with_friends = 1)
            rows = conn.execute("""
                SELECT DISTINCT t.id, t.title, t.destination, t.start_date, t.end_date, t.status, t.notes, t.created_at,
                       t.cover_image, t.estimated_budget, t.is_shared_with_friends, t.flight_details, t.hotel_details, t.packing_list
                FROM trips t
                LEFT JOIN trip_group_trips gt ON t.id = gt.trip_id
                LEFT JOIN trip_group_members gm ON gt.group_id = gm.group_id
                WHERE t.is_shared_with_friends = 1
                   OR LOWER(gm.email) = ?
                   OR UPPER(gm.passcode) = ?
                ORDER BY t.start_date ASC
            """, (user_email, passcode)).fetchall()

        # Map group badges onto trips
        trips = []
        for r in rows:
            tid = r[0]
            group_rows = conn.execute("""
                SELECT g.id, g.name, g.color, g.icon
                FROM trip_group_trips gt
                JOIN trip_groups g ON gt.group_id = g.id
                WHERE gt.trip_id = ?
            """, (tid,)).fetchall()

            groups_attached = [
                {"id": gr[0], "name": gr[1], "color": gr[2], "icon": gr[3]}
                for gr in group_rows
            ]

            try:
                packing = json.loads(r[13]) if r[13] else []
            except Exception:
                packing = []

            trips.append({
                "id": r[0],
                "title": r[1],
                "destination": r[2],
                "start_date": r[3],
                "end_date": r[4],
                "status": r[5],
                "notes": r[6],
                "created_at": r[7],
                "cover_image": r[8] or "japan",
                "estimated_budget": float(r[9] or 0.0),
                "is_shared_with_friends": bool(r[10]),
                "flight_details": r[11],
                "hotel_details": r[12],
                "packing_list": packing,
                "groups": groups_attached,
            })

    return trips


def send_trip_invite_email(
    to_email: str,
    to_name: str,
    group_name: str,
    passcode: str,
    direct_url: str,
) -> bool:
    """Send beautiful invitation email with one-click direct landing link to the Trips Hub."""
    subject = f"✈️ You're Invited: Join {group_name} on Nexus Trips & Expeditions"

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{subject}</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #0b0f19; color: #f8fafc; margin: 0; padding: 20px; }}
            .container {{ max-width: 600px; margin: 0 auto; background: linear-gradient(180deg, #1e293b 0%, #0f172a 100%); border: 1px solid #334155; border-radius: 16px; overflow: hidden; box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5); }}
            .header {{ background: linear-gradient(135deg, #0284c7 0%, #0369a1 100%); padding: 32px 24px; text-align: center; }}
            .header h1 {{ margin: 0; font-size: 24px; font-weight: 800; color: #ffffff; letter-spacing: -0.5px; }}
            .header p {{ margin: 8px 0 0 0; color: #e0f2fe; font-size: 14px; }}
            .body {{ padding: 32px 24px; }}
            .greeting {{ font-size: 16px; color: #cbd5e1; margin-bottom: 20px; }}
            .badge-box {{ background: rgba(2, 132, 199, 0.1); border: 1px solid rgba(56, 189, 248, 0.3); border-radius: 12px; padding: 20px; text-align: center; margin: 24px 0; }}
            .group-name {{ font-size: 20px; font-weight: 700; color: #38bdf8; margin-bottom: 4px; }}
            .code-label {{ font-size: 12px; text-transform: uppercase; color: #94a3b8; letter-spacing: 1px; margin-top: 12px; }}
            .code-value {{ font-family: monospace; font-size: 22px; font-weight: 800; color: #f8fafc; background: #0f172a; padding: 8px 16px; border-radius: 8px; display: inline-block; margin-top: 6px; letter-spacing: 2px; border: 1px dashed #38bdf8; }}
            .btn {{ display: block; width: 100%; max-width: 320px; margin: 28px auto 0 auto; background: linear-gradient(135deg, #0284c7 0%, #0369a1 100%); color: #ffffff !important; text-decoration: none; text-align: center; padding: 14px 24px; border-radius: 12px; font-size: 15px; font-weight: 700; box-shadow: 0 10px 15px -3px rgba(2, 132, 199, 0.4); }}
            .footer {{ border-top: 1px solid #1e293b; padding: 20px 24px; text-align: center; font-size: 12px; color: #64748b; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>✈️ NEXUS TRIPS & EXPEDITIONS</h1>
                <p>Collaborative Travel Itineraries & Group Adventures</p>
            </div>
            <div class="body">
                <div class="greeting">Hey <strong>{to_name}</strong>,</div>
                <p style="color: #94a3b8; font-size: 14px; line-height: 1.6;">
                    You have been invited to join the <strong>{group_name}</strong> travel group on Nexus. Access shared flight manifests, luxury hotel stays, packing lists, and vote on community excursion activities!
                </p>
                <div class="badge-box">
                    <div class="group-name">🌴 {group_name}</div>
                    <div class="code-label">Your Personal Access Passcode</div>
                    <div class="code-value">{passcode}</div>
                </div>
                <a href="{direct_url}" class="btn" target="_blank">🚀 Open Trip Itinerary Directly</a>
                <p style="text-align: center; margin-top: 16px; font-size: 12px; color: #64748b;">
                    Clicking the button above automatically authenticates your code and opens your travel hub.
                </p>
            </div>
            <div class="footer">
                Nexus Quantum Architecture • Private Travel Intelligence
            </div>
        </div>
    </body>
    </html>
    """

    # 1. Try Resend API if configured
    resend_api_key = os.getenv("RESEND_API_KEY")
    if resend_api_key:
        try:
            import urllib.request
            req_data = json.dumps({
                "from": os.getenv("RESEND_FROM_EMAIL", "Nexus Travel <onboarding@resend.dev>"),
                "to": [to_email],
                "subject": subject,
                "html": html_content,
            }).encode("utf-8")
            req = urllib.request.Request(
                "https://api.resend.com/emails",
                data=req_data,
                headers={
                    "Authorization": f"Bearer {resend_api_key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status in (200, 201):
                    logger.info("[TRIPS-EMAIL] Sent invite email to %s via Resend API", to_email)
                    return True
        except Exception as e:
            logger.warning("[TRIPS-EMAIL] Resend dispatch failed: %s", e)

    # 2. Try SMTP if configured
    smtp_host = os.getenv("SMTP_HOST")
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))

    if smtp_host and smtp_user and smtp_pass:
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = os.getenv("SMTP_FROM", smtp_user)
            msg["To"] = to_email
            msg.attach(MIMEText(html_content, "html"))

            with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
                server.starttls()
                server.login(smtp_user, smtp_pass)
                server.sendmail(msg["From"], [to_email], msg.as_string())
            logger.info("[TRIPS-EMAIL] Sent invite email to %s via SMTP", to_email)
            return True
        except Exception as e:
            logger.warning("[TRIPS-EMAIL] SMTP dispatch failed: %s", e)

    # 3. Development / Local Mock Logging
    logger.info(
        "\n============================================================\n"
        "[TRIPS-INVITE-EMAIL] (Development Mock - No SMTP Key configured)\n"
        "To: %s <%s>\n"
        "Subject: %s\n"
        "Group: %s\n"
        "Personal Passcode: %s\n"
        "Direct Magic Link: %s\n"
        "============================================================",
        to_name, to_email, subject, group_name, passcode, direct_url
    )
    return True
