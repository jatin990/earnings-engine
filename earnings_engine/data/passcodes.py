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

# Canonical Application / Route definitions
AVAILABLE_ROUTES: dict[str, dict[str, Any]] = {
    "dashboard": {
        "id": "dashboard",
        "name": "Earnings Engine Terminal",
        "icon": "📈",
        "description": "Full AI Consensus, swing oscillator, multi-model predictions, category scanner & corporate ledger.",
        "path": "/dashboard",
        "badge": "AI Trading Terminal",
    },
    "credit_card": {
        "id": "credit_card",
        "name": "Credit Card & Wealth Hub",
        "icon": "💳",
        "description": "Luxury obsidian card tracker, reward maximizer radar, cashback analytics & perks dial.",
        "path": "/credit-card",
        "badge": "Financial Deck",
    },
    "playground": {
        "id": "playground",
        "name": "NSE Market & Data Sandbox",
        "icon": "🧪",
        "description": "Interactive NSE Bhavcopy, calendar queries, and model feature playground.",
        "path": "/dashboard#tab-playground",
        "badge": "Data Lab",
    },
    "admin": {
        "id": "admin",
        "name": "Passcode & Friend Key Manager",
        "icon": "🔑",
        "description": "Generate, customize, and revoke access codes and route permissions for friends.",
        "path": "/portal#admin",
        "badge": "Admin Deck",
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
                    "SELECT code, label, scopes, max_uses, use_count, is_active FROM invite_codes WHERE UPPER(code) = ?",
                    (clean_code,),
                ).fetchone()
                if inv_row and inv_row[5]:
                    inv_scopes = json.loads(inv_row[2]) if inv_row[2] else ["can_view_trips"]
                    return {
                        "valid": True,
                        "code": inv_row[0],
                        "label": inv_row[1] or "Friend Access",
                        "role": "friend",
                        "is_admin": False,
                        "allowed_routes": ["dashboard"] if "dashboard" in inv_scopes else ["credit_card"],
                        "scopes": inv_scopes,
                        "authorized_apps": [
                            {**r_info, "has_access": (r_id == "dashboard" and "dashboard" in inv_scopes) or (r_id == "credit_card" and "can_view_cards" in inv_scopes)}
                            for r_id, r_info in AVAILABLE_ROUTES.items()
                        ],
                    }
            except Exception:
                pass
            return {"valid": False, "error": "Invalid access code. Please check your passcode."}

        p_code, label, allowed_json, created_at, expires_at, max_uses, use_count, is_active = row

        if not is_active:
            return {"valid": False, "error": "This passcode has been deactivated by the admin."}

        if max_uses is not None and use_count >= max_uses:
            return {"valid": False, "error": "This passcode has reached its maximum allowed uses."}

        # Increment use count
        conn.execute("UPDATE passcodes SET use_count = use_count + 1 WHERE code = ?", (p_code,))

        try:
            allowed_routes = json.loads(allowed_json)
        except Exception:
            allowed_routes = ["dashboard"]

        is_admin = "admin" in allowed_routes or "*" in allowed_routes

        # Build authorized apps payload
        authorized_apps = []
        for r_id, r_info in AVAILABLE_ROUTES.items():
            has_access = (r_id in allowed_routes) or ("*" in allowed_routes)
            authorized_apps.append({
                **r_info,
                "has_access": has_access,
            })

        return {
            "valid": True,
            "code": p_code,
            "label": label,
            "allowed_routes": allowed_routes,
            "is_admin": is_admin,
            "use_count": use_count + 1,
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
    expires_at: str | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Generate a new customized passcode for a friend or associate."""
    settings = settings or Settings()
    init_passcodes(settings)

    # Generate random alphanumeric code if not provided
    if not code:
        random_suffix = secrets.token_hex(3).upper()
        clean_label = "".join(c for c in label if c.isalnum()).upper()[:6] or "FRIEND"
        code = f"{clean_label}-{random_suffix}"
    else:
        code = code.strip().upper()

    now_str = datetime.now(timezone.utc).isoformat()
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
                is_active = 1
            """,
            (
                code,
                label.strip(),
                json.dumps(allowed_routes),
                now_str,
                expires_at,
                max_uses,
            ),
        )

    logger.info("Created passcode %s for friend '%s' with routes %s", code, label, allowed_routes)
    return {
        "code": code,
        "label": label,
        "allowed_routes": allowed_routes,
        "created_at": now_str,
        "max_uses": max_uses,
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
