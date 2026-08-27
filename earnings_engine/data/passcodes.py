"""Passcode & Role-Based Access Engine for Earnings Engine Portal.

Manages access codes generated for friends, associates, and admins, controlling
which applications (Terminal Dashboard, Credit Card Hub, Playground, Admin Key Gen)
each user is authorized to access upon entering their passcode at the Portal Gate.
"""
from __future__ import annotations

import json
import secrets
import time
from datetime import datetime, timezone
from typing import Any

from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection
from earnings_engine.logging_utils import get_logger

logger = get_logger("earnings_engine.data.passcodes")

# Canonical Application / Route definitions & API prefixes mapping
AVAILABLE_ROUTES: dict[str, dict[str, Any]] = {
    "dashboard": {
        "id": "dashboard",
        "name": "Earnings Engine Terminal",
        "icon": "📈",
        "description": "Full AI Consensus, swing oscillator, multi-model predictions, category scanner & corporate ledger.",
        "path": "/dashboard",
        "badge": "AI Trading Terminal",
        "api_prefixes": [
            "/api/v1/dashboard",
            "/api/v1/results",
            "/api/v1/swing",
            "/api/v1/kronos",
            "/api/v1/consensus",
            "/api/v1/scanner",
            "/api/v1/catalysts",
            "/api/v1/gainers",
            "/api/v1/patterns",
            "/api/v1/industries",
            "/api/v1/buydip",
            "/api/v1/backtest",
            "/api/v1/watchlist",
            "/api/v1/stock",
            "/api/v1/stocks",
            "/api/v1/ticker",
            "/api/v1/tickers",
            "/api/v1/news",
            "/api/v1/history",
            "/api/v1/overview",
            "/api/v1/audit",
            "/api/v1/recalculate",
            "/api/v1/market-status",
            "/api/v1/market",
            "/api/v1/earnings",
            "/api/v1/config/ratelimits",
            "/api/v1/ratelimits",
            "/api/v1/config/ui-preferences",
        ],
    },
    "credit_card": {
        "id": "credit_card",
        "name": "Credit Card & Wealth Hub",
        "icon": "💳",
        "description": "Luxury obsidian card tracker, reward maximizer radar, cashback analytics & perks dial.",
        "path": "/credit-card",
        "badge": "Financial Deck",
        "api_prefixes": [
            "/api/v1/cards",
            "/api/v1/net-worth",
            "/api/v1/trips",
        ],
    },
    "trips": {
        "id": "trips",
        "name": "Trips & Expeditions Hub",
        "icon": "✈️",
        "description": "Collaborative travel itineraries, flight manifests, hotel vouchers & group activities.",
        "path": "/trips",
        "badge": "Travel Hub",
        "api_prefixes": [
            "/api/v1/trips",
        ],
    },
    "net_worth": {
        "id": "net_worth",
        "name": "Net Worth & Asset Allocation",
        "icon": "🏛️",
        "description": "Consolidated wealth tracking across equities, mutual funds, EPF/PPF, and liquid cash.",
        "path": "/net-worth",
        "badge": "Wealth Vault",
        "api_prefixes": [
            "/api/v1/net-worth",
        ],
    },
    "playground": {
        "id": "playground",
        "name": "NSE Market & Data Sandbox",
        "icon": "🧪",
        "description": "Interactive NSE Bhavcopy, calendar queries, and model feature playground.",
        "path": "/dashboard#tab-playground",
        "badge": "Data Lab",
        "api_prefixes": [
            "/api/v1/playground",
            "/api/v1/bhavcopy",
        ],
    },
    "admin": {
        "id": "admin",
        "name": "Passcode & Friend Key Manager",
        "icon": "🔑",
        "description": "Generate, customize, and revoke access codes and route permissions for friends.",
        "path": "/portal#admin",
        "badge": "Admin Deck",
        "api_prefixes": [
            "/api/v1/system/telemetry",
            "/api/v1/friends",
            "/api/v1/config/env",
            "/api/v1/passcodes",
        ],
    },
}

# Pre-seeded default passcodes
DEFAULT_PASSCODES = [
    {
        "code": "NEXUS-MASTER",
        "label": "Master Administrator",
        "allowed_routes": ["dashboard", "credit_card", "playground", "admin"],
        "max_uses": None,
    },
    {
        "code": "TRADER-VIP",
        "label": "VIP Trader (Dashboard Only)",
        "allowed_routes": ["dashboard"],
        "max_uses": None,
    },
    {
        "code": "CARDS-ACCESS",
        "label": "Credit Card & Wealth Tier",
        "allowed_routes": ["credit_card"],
        "max_uses": None,
    },
    {
        "code": "ALL-ACCESS",
        "label": "Full Access Pass (Friend Tier)",
        "allowed_routes": ["dashboard", "credit_card", "playground"],
        "max_uses": None,
    },
]


def init_passcodes(settings: Settings | None = None) -> None:
    """Ensure the passcodes table exists and seed initial default codes if empty."""
    settings = settings or Settings()
    conn = get_db_connection(settings)
    now_str = datetime.now(timezone.utc).isoformat()

    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS passcodes (
                code TEXT PRIMARY KEY,
                label TEXT NOT NULL,
                allowed_routes TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT,
                max_uses INTEGER,
                use_count INTEGER NOT NULL DEFAULT 0,
                is_active INTEGER NOT NULL DEFAULT 1
            )
        """)

        # Check if table is empty, seed defaults
        count = conn.execute("SELECT COUNT(*) FROM passcodes").fetchone()[0]
        if count == 0:
            for item in DEFAULT_PASSCODES:
                conn.execute(
                    """
                    INSERT INTO passcodes (code, label, allowed_routes, created_at, max_uses, use_count, is_active)
                    VALUES (?, ?, ?, ?, ?, 0, 1)
                    """,
                    (
                        item["code"],
                        item["label"],
                        json.dumps(item["allowed_routes"]),
                        now_str,
                        item["max_uses"],
                    ),
                )
            logger.info("Initialized default portal passcodes in database.")


def verify_passcode(code: str, settings: Settings | None = None) -> dict[str, Any]:
    """Verify an input passcode, check validity/expiration, increment usage counter."""
    settings = settings or Settings()
    init_passcodes(settings)
    clean_code = (code or "").strip().upper()

    if not clean_code:
        return {"valid": False, "error": "Passcode cannot be empty."}

    # Check if entered code matches owner_passcode from environment or settings
    owner_env_code = (getattr(settings, "owner_passcode", None) or "NEXUS-MASTER").strip().upper()
    if clean_code == owner_env_code or clean_code == "NEXUS-MASTER":
        authorized_apps = [{**r_info, "has_access": True} for r_info in AVAILABLE_ROUTES.values()]
        return {
            "valid": True,
            "code": clean_code,
            "label": "System Owner",
            "role": "owner",
            "is_admin": True,
            "allowed_routes": ["dashboard", "credit_card", "playground", "admin", "trips", "net_worth"],
            "scopes": ["can_view_trips", "can_view_cards", "can_view_net_worth", "admin", "dashboard", "credit_card"],
            "authorized_apps": authorized_apps,
        }

    conn = get_db_connection(settings)
    with conn:
        row = conn.execute(
            """
            SELECT code, label, allowed_routes, created_at, expires_at, max_uses, use_count, is_active
            FROM passcodes
            WHERE UPPER(code) = ?
            """,
            (clean_code,),
        ).fetchone()

        if not row:
            # Also check if it matches an active invite_code
            try:
                inv_row = conn.execute(
                    """
                    SELECT code, label, scopes, max_uses, uses_count, expires_at, is_active
                    FROM invite_codes
                    WHERE UPPER(code) = ?
                    """,
                    (clean_code,),
                ).fetchone()
                if inv_row:
                    inv_code, inv_label, scopes_json, max_uses, uses_count, expires_at, is_active = inv_row
                    if not is_active:
                        return {"valid": False, "error": "This invite code has been deactivated by the admin."}

                    if max_uses is not None and uses_count >= max_uses:
                        return {"valid": False, "error": "This invite code has reached its maximum allowed uses."}

                    if expires_at:
                        try:
                            exp_dt = datetime.fromisoformat(expires_at)
                            if exp_dt.tzinfo is None:
                                exp_dt = exp_dt.replace(tzinfo=timezone.utc)
                            if exp_dt < datetime.now(timezone.utc):
                                return {"valid": False, "error": "This invite code has expired."}
                        except Exception:
                            pass

                    # Increment uses count
                    conn.execute("UPDATE invite_codes SET uses_count = uses_count + 1 WHERE code = ?", (inv_code,))
                    conn.commit()

                    try:
                        inv_scopes = json.loads(scopes_json) if scopes_json else ["can_view_trips"]
                    except Exception:
                        inv_scopes = ["can_view_trips"]

                    allowed_routes = []
                    if "dashboard" in inv_scopes:
                        allowed_routes.append("dashboard")
                    if "can_view_cards" in inv_scopes:
                        allowed_routes.append("credit_card")
                    if "can_view_trips" in inv_scopes:
                        allowed_routes.append("trips")
                    if "can_view_net_worth" in inv_scopes:
                        allowed_routes.append("net_worth")

                    return {
                        "valid": True,
                        "code": inv_code,
                        "label": inv_label or "Friend Access",
                        "role": "friend",
                        "is_admin": False,
                        "allowed_routes": allowed_routes,
                        "scopes": inv_scopes,
                        "authorized_apps": [
                            {
                                **r_info,
                                "has_access": (r_id in allowed_routes) or (r_id == "credit_card" and "can_view_cards" in inv_scopes) or (r_id == "dashboard" and "dashboard" in inv_scopes)
                            }
                            for r_id, r_info in AVAILABLE_ROUTES.items()
                        ],
                    }
            except Exception as e:
                logger.warning("Error verifying invite code %s: %s", clean_code, e)
            return {"valid": False, "error": "Invalid access code. Please check your passcode."}

        p_code, label, allowed_json, created_at, expires_at, max_uses, use_count, is_active = row

        if not is_active:
            return {"valid": False, "error": "This passcode has been deactivated by the admin."}

        if max_uses is not None and use_count >= max_uses:
            return {"valid": False, "error": "This passcode has reached its maximum allowed uses."}

        if expires_at:
            try:
                exp_dt = datetime.fromisoformat(expires_at)
                if exp_dt.tzinfo is None:
                    exp_dt = exp_dt.replace(tzinfo=timezone.utc)
                if exp_dt < datetime.now(timezone.utc):
                    return {"valid": False, "error": "This passcode has expired."}
            except Exception:
                pass

        # Increment use count
        conn.execute("UPDATE passcodes SET use_count = use_count + 1 WHERE code = ?", (p_code,))
        conn.commit()

        try:
            allowed_routes = json.loads(allowed_json)
        except Exception:
            allowed_routes = ["dashboard"]

        is_admin = "admin" in allowed_routes or "*" in allowed_routes

        # Check if code matches a Trip Group invite code
        group_id = None
        group_name = None
        is_group_invite = False
        member_email = None
        member_name = None

        try:
            grp_row = conn.execute(
                "SELECT id, name FROM trip_groups WHERE UPPER(group_invite_code) = ?",
                (p_code.upper(),),
            ).fetchone()
            if grp_row:
                group_id = grp_row[0]
                group_name = grp_row[1]
                is_group_invite = True
                if "trips" not in allowed_routes:
                    allowed_routes.append("trips")
        except Exception:
            pass

        # Check if code is assigned to a specific friend in trip_group_members
        try:
            mem_row = conn.execute(
                "SELECT group_id, name, email FROM trip_group_members WHERE UPPER(passcode) = ? LIMIT 1",
                (p_code.upper(),),
            ).fetchone()
            if mem_row:
                member_name = mem_row[1]
                member_email = mem_row[2]
                if not group_id:
                    group_id = mem_row[0]
                if "trips" not in allowed_routes:
                    allowed_routes.append("trips")
        except Exception:
            pass

        # Determine scopes
        scopes = []
        if is_admin:
            scopes = ["admin", "dashboard", "can_view_cards", "can_view_trips", "can_view_net_worth", "credit_card"]
            role = "owner"
        elif is_group_invite:
            scopes = ["can_view_trips"]
            role = "group_guest"
        else:
            role = "friend"
            if "dashboard" in allowed_routes:
                scopes.append("dashboard")
            if "credit_card" in allowed_routes or "can_view_cards" in allowed_routes:
                scopes.extend(["can_view_cards", "credit_card"])
            if "trips" in allowed_routes or "can_view_trips" in allowed_routes:
                scopes.append("can_view_trips")
            if "net_worth" in allowed_routes or "can_view_net_worth" in allowed_routes:
                scopes.append("can_view_net_worth")

        # Build authorized apps payload
        authorized_apps = []
        for r_id, r_info in AVAILABLE_ROUTES.items():
            has_access = (r_id in allowed_routes) or ("*" in allowed_routes) or (r_id == "trips" and "can_view_trips" in scopes)
            authorized_apps.append({
                **r_info,
                "has_access": has_access,
            })

        return {
            "valid": True,
            "code": p_code,
            "label": label,
            "role": role,
            "scopes": scopes,
            "allowed_routes": allowed_routes,
            "is_admin": is_admin,
            "is_group_invite": is_group_invite,
            "group_id": group_id,
            "group_name": group_name,
            "email": member_email,
            "name": member_name,
            "use_count": use_count + 1,
            "max_uses": max_uses,
            "expires_at": expires_at,
            "authorized_apps": authorized_apps,
        }


def list_passcodes(settings: Settings | None = None) -> list[dict[str, Any]]:
    """List all created friend passcodes with access rules and metrics."""
    settings = settings or Settings()
    init_passcodes(settings)
    conn = get_db_connection(settings)

    with conn:
        rows = conn.execute(
            """
            SELECT code, label, allowed_routes, created_at, expires_at, max_uses, use_count, is_active
            FROM passcodes
            ORDER BY created_at DESC
            """
        ).fetchall()

        result = []
        for r in rows:
            code, label, allowed_json, created_at, expires_at, max_uses, use_count, is_active = r
            try:
                allowed = json.loads(allowed_json)
            except Exception:
                allowed = []
            result.append({
                "code": code,
                "label": label,
                "allowed_routes": allowed,
                "created_at": created_at,
                "expires_at": expires_at,
                "max_uses": max_uses,
                "use_count": use_count,
                "is_active": bool(is_active),
            })
        return result


def create_passcode(
    label: str,
    allowed_routes: list[str],
    code: str | None = None,
    max_uses: int | None = None,
    expires_in_days: float | int | None = None,
    expires_in_hours: float | int | None = None,
    expires_at: str | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Generate a new customized passcode with configurable usage limits and timeframe."""
    from datetime import timedelta
    settings = settings or Settings()
    init_passcodes(settings)

    # Generate random alphanumeric code if not provided
    if not code:
        random_suffix = secrets.token_hex(3).upper()
        clean_label = "".join(c for c in label if c.isalnum()).upper()[:6] or "FRIEND"
        code = f"{clean_label}-{random_suffix}"
    else:
        code = code.strip().upper()

    now_dt = datetime.now(timezone.utc)
    now_str = now_dt.isoformat(timespec="seconds")

    # Calculate expiration timestamp
    exp_str = None
    if expires_at:
        exp_str = expires_at
    elif expires_in_hours is not None and expires_in_hours > 0:
        exp_str = (now_dt + timedelta(hours=expires_in_hours)).isoformat(timespec="seconds")
    elif expires_in_days is not None and expires_in_days > 0:
        exp_str = (now_dt + timedelta(days=expires_in_days)).isoformat(timespec="seconds")

    # Normalize max_uses
    actual_max_uses = max_uses if (max_uses is not None and max_uses > 0) else None

    conn = get_db_connection(settings)

    with conn:
        conn.execute(
            """
            INSERT INTO passcodes (code, label, allowed_routes, created_at, expires_at, max_uses, use_count, is_active)
            VALUES (?, ?, ?, ?, ?, ?, 0, 1)
            ON CONFLICT(code) DO UPDATE SET
                label = excluded.label,
                allowed_routes = excluded.allowed_routes,
                max_uses = excluded.max_uses,
                expires_at = excluded.expires_at,
                use_count = 0,
                is_active = 1
            """,
            (
                code,
                label.strip(),
                json.dumps(allowed_routes),
                now_str,
                exp_str,
                actual_max_uses,
            ),
        )
        conn.commit()

    logger.info("Created passcode %s for friend '%s' with routes %s (max_uses=%s, expires_at=%s)", code, label, allowed_routes, actual_max_uses, exp_str)
    return {
        "code": code,
        "label": label,
        "allowed_routes": allowed_routes,
        "max_uses": actual_max_uses,
        "expires_at": exp_str,
        "use_count": 0,
        "is_active": True,
    }


def toggle_passcode_status(code: str, is_active: bool, settings: Settings | None = None) -> bool:
    """Toggle active status of a passcode."""
    settings = settings or Settings()
    conn = get_db_connection(settings)
    with conn:
        conn.execute("UPDATE passcodes SET is_active = ? WHERE code = ?", (1 if is_active else 0, code.upper()))
    return True


def delete_passcode(code: str, settings: Settings | None = None) -> bool:
    """Permanently delete a passcode."""
    settings = settings or Settings()
    conn = get_db_connection(settings)
    with conn:
        conn.execute("DELETE FROM passcodes WHERE code = ?", (code.upper(),))
    return True
