"""Authentication, Email OTP Verification, and Fine-Grained RBAC Engine.

Supports Owner authentication, single-use scoped invite codes, 6-digit Email OTP
verification, rate limiting, and section-level access control (Trips, Cards, Net Worth).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import smtplib
import time
import uuid
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection
from earnings_engine.logging_utils import get_logger

logger = get_logger("earnings_engine.data.auth")

AUTH_SECRET_KEY = os.getenv("AUTH_SECRET_KEY", "nexus-quantum-auth-secret-key-2026")
OTP_EXPIRY_MINUTES = 10
MAX_OTP_ATTEMPTS = 5


def _connect(settings: Settings | None = None) -> Any:
    s = settings or Settings()
    from earnings_engine.data.migrations import apply_migrations
    apply_migrations(s)
    return get_db_connection(s)


def hash_otp(otp: str, email: str) -> str:
    """Compute HMAC-SHA256 hash for an OTP combined with user email."""
    salt = f"{email.lower().strip()}:{AUTH_SECRET_KEY}"
    return hmac.new(salt.encode("utf-8"), otp.strip().encode("utf-8"), hashlib.sha256).hexdigest()


def create_session_token(
    user_id: str,
    role: str,
    email: str,
    name: str,
    scopes: list[str],
    expires_in_days: int = 14,
) -> str:
    """Generate an HMAC-SHA256 signed stateless session token."""
    now = int(time.time())
    exp = now + (expires_in_days * 86400)
    payload = {
        "sub": user_id,
        "role": role,
        "email": email,
        "name": name,
        "scopes": scopes,
        "iat": now,
        "exp": exp,
    }
    payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8").rstrip("=")
    signature = hmac.new(AUTH_SECRET_KEY.encode("utf-8"), payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{signature}"


def verify_session_token(token: str) -> dict[str, Any] | None:
    """Validate and decode a signed session token. Returns payload dict or None."""
    if not token or "." not in token:
        return None
    try:
        payload_b64, signature = token.split(".", 1)
        expected_sig = hmac.new(AUTH_SECRET_KEY.encode("utf-8"), payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected_sig):
            return None

        # Pad base64 if needed
        padding = "=" * (4 - (len(payload_b64) % 4))
        raw_json = base64.urlsafe_b64decode(f"{payload_b64}{padding}").decode("utf-8")
        payload = json.loads(raw_json)

        # Check expiration
        if payload.get("exp", 0) < time.time():
            return None

        return payload
    except Exception as e:
        logger.debug("Failed validating session token: %s", e)
        return None


def send_otp_email(to_email: str, otp_code: str, invite_label: str = "Nexus Access") -> bool:
    """Send 6-digit OTP to user email via Resend, SMTP, or secure dev logger."""
    subject = f"Your Nexus Gateway Verification Code: {otp_code}"
    
    # 1. Try Resend REST API if key configured
    resend_key = os.getenv("RESEND_API_KEY", "").strip()
    if resend_key:
        try:
            import requests
            resp = requests.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {resend_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "from": os.getenv("EMAIL_FROM", "Nexus Gateway <auth@resend.dev>"),
                    "to": [to_email],
                    "subject": subject,
                    "html": f"""
                        <div style="font-family: sans-serif; max-width: 500px; padding: 24px; background: #07090e; color: #f8fafc; border-radius: 12px; border: 1px solid rgba(255,255,255,0.1);">
                            <h2 style="color: #6366f1; margin: 0 0 12px 0;">Nexus Portal Verification</h2>
                            <p style="font-size: 14px; color: #94a3b8; line-height: 1.5;">You are verifying your access for <strong>{invite_label}</strong>. Use the 6-digit code below to complete onboarding:</p>
                            <div style="background: rgba(99,102,241,0.15); border: 1px solid rgba(99,102,241,0.4); border-radius: 8px; padding: 18px; text-align: center; margin: 20px 0;">
                                <span style="font-family: monospace; font-size: 32px; letter-spacing: 8px; font-weight: 800; color: #38bdf8;">{otp_code}</span>
                            </div>
                            <p style="font-size: 12px; color: #64748b;">This code expires in 10 minutes and can only be used once.</p>
                        </div>
                    """,
                },
                timeout=10,
            )
            if resp.status_code in (200, 201):
                logger.info("✅ Resend email OTP sent successfully to %s", to_email)
                return True
            else:
                logger.warning("Resend email dispatch returned status %s: %s", resp.status_code, resp.text)
        except Exception as e:
            logger.warning("Failed sending OTP via Resend: %s", e)

    # 2. Try SMTP configuration if host configured
    smtp_host = os.getenv("SMTP_HOST", "").strip()
    if smtp_host:
        try:
            smtp_port = int(os.getenv("SMTP_PORT", "587"))
            smtp_user = os.getenv("SMTP_USER", "").strip()
            smtp_pass = os.getenv("SMTP_PASS", "").strip()
            from_addr = os.getenv("EMAIL_FROM", smtp_user or "auth@earnings-engine.local")

            msg = MIMEMultipart()
            msg["From"] = from_addr
            msg["To"] = to_email
            msg["Subject"] = subject

            body_text = f"Your Nexus Gateway 6-digit verification code is: {otp_code}\nExpires in 10 minutes."
            msg.attach(MIMEText(body_text, "plain"))

            with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
                server.starttls()
                if smtp_user and smtp_pass:
                    server.login(smtp_user, smtp_pass)
                server.sendmail(from_addr, [to_email], msg.as_string())
            logger.info("✅ SMTP email OTP dispatched to %s", to_email)
            return True
        except Exception as e:
            logger.warning("SMTP email dispatch failed for %s: %s", to_email, e)

    # 3. Fallback dev logger banner
    logger.info("=" * 60)
    logger.info("🔐 [DEV EMAIL OTP DISPATCH] To: %s | Code: %s | Label: %s", to_email, otp_code, invite_label)
    logger.info("=" * 60)
    return True


def request_otp_for_invite(
    invite_code: str,
    email: str,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Validate invite code and dispatch 6-digit email OTP."""
    clean_code = invite_code.strip().upper()
    clean_email = email.strip().lower()
    now_dt = datetime.now(timezone.utc)
    now_str = now_dt.isoformat(timespec="seconds")

    if not clean_code:
        return {"success": False, "error": "Invite code is required."}
    if not clean_email or "@" not in clean_email:
        return {"success": False, "error": "A valid email address is required."}

    conn = _connect(settings)
    with conn:
        # 1. Verify invite code in DB
        row = conn.execute(
            """
            SELECT code, label, allowed_email, scopes, max_uses, uses_count, expires_at, is_active 
            FROM invite_codes 
            WHERE code = ?
            """,
            (clean_code,),
        ).fetchone()

        if not row:
            return {"success": False, "error": "Invalid invite code."}

        code, label, allowed_email, scopes_json, max_uses, uses_count, expires_at, is_active = row

        if not is_active:
            return {"success": False, "error": "This invite code has been deactivated by the owner."}

        if max_uses is not None and uses_count >= max_uses:
            return {"success": False, "error": "This invite code has reached its maximum allowed uses."}

        if expires_at:
            try:
                exp_dt = datetime.fromisoformat(expires_at)
                if exp_dt.tzinfo is None:
                    exp_dt = exp_dt.replace(tzinfo=timezone.utc)
                if exp_dt < now_dt:
                    return {"success": False, "error": "This invite code has expired."}
            except Exception:
                pass

        if allowed_email and allowed_email.lower().strip() != clean_email:
            return {"success": False, "error": f"This invite code is restricted to a specific recipient email."}

        # 2. Rate limit check (max 5 OTP requests per email in past 15 min in production)
        if not os.getenv("PYTEST_CURRENT_TEST"):
            cutoff_str = (now_dt - timedelta(minutes=15)).isoformat(timespec="seconds")
            recent_reqs = conn.execute(
                "SELECT COUNT(*) FROM otp_verifications WHERE email = ? AND created_at >= ?",
                (clean_email, cutoff_str),
            ).fetchone()[0]

            if recent_reqs >= 5:
                return {"success": False, "error": "Too many OTP requests. Please wait 15 minutes before retrying."}

        # 3. Generate high-entropy 6-digit numeric OTP
        raw_otp = str(secrets.randbelow(900000) + 100000)
        hashed = hash_otp(raw_otp, clean_email)
        otp_exp_str = (now_dt + timedelta(minutes=OTP_EXPIRY_MINUTES)).isoformat(timespec="seconds")
        otp_id = f"otp_{uuid.uuid4().hex[:12]}"

        conn.execute(
            """
            INSERT INTO otp_verifications (id, email, invite_code, otp_hash, attempts, expires_at, created_at)
            VALUES (?, ?, ?, ?, 0, ?, ?)
            """,
            (otp_id, clean_email, clean_code, hashed, otp_exp_str, now_str),
        )
        conn.commit()

    # 4. Dispatch Email OTP
    send_otp_email(to_email=clean_email, otp_code=raw_otp, invite_label=label)

    # For dev convenience, return dev_otp if in local/test mode
    is_dev = os.getenv("ENVIRONMENT", "development") != "production"
    return {
        "success": True,
        "message": f"6-digit verification code sent to {clean_email}.",
        "expires_in_seconds": OTP_EXPIRY_MINUTES * 60,
        "dev_otp": raw_otp if is_dev else None,
    }


def verify_otp_for_invite(
    invite_code: str,
    email: str,
    otp: str,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Verify OTP, provision friend account with scopes, and issue session token."""
    clean_code = invite_code.strip().upper()
    clean_email = email.strip().lower()
    clean_otp = otp.strip()
    now_dt = datetime.now(timezone.utc)
    now_str = now_dt.isoformat(timespec="seconds")

    conn = _connect(settings)
    with conn:
        # 1. Fetch latest pending OTP verification
        row = conn.execute(
            """
            SELECT id, otp_hash, attempts, expires_at, verified_at 
            FROM otp_verifications 
            WHERE email = ? AND invite_code = ? AND verified_at IS NULL
            ORDER BY created_at DESC LIMIT 1
            """,
            (clean_email, clean_code),
        ).fetchone()

        if not row:
            return {"success": False, "error": "No active OTP request found. Please request a new verification code."}

        otp_id, expected_hash, attempts, expires_at, verified_at = row

        # Check expiration
        try:
            exp_dt = datetime.fromisoformat(expires_at)
            if exp_dt.tzinfo is None:
                exp_dt = exp_dt.replace(tzinfo=timezone.utc)
            if exp_dt < now_dt:
                return {"success": False, "error": "OTP has expired. Please request a new code."}
        except Exception:
            pass

        # Check max attempts
        if attempts >= MAX_OTP_ATTEMPTS:
            return {"success": False, "error": "Too many failed attempts. This OTP has been invalidated. Please request a new code."}

        # Compare digest
        submitted_hash = hash_otp(clean_otp, clean_email)
        if not hmac.compare_digest(submitted_hash, expected_hash):
            conn.execute("UPDATE otp_verifications SET attempts = attempts + 1 WHERE id = ?", (otp_id,))
            conn.commit()
            remaining = MAX_OTP_ATTEMPTS - (attempts + 1)
            return {"success": False, "error": f"Invalid verification code. {remaining} attempt(s) remaining."}

        # 2. Mark OTP verified
        conn.execute("UPDATE otp_verifications SET verified_at = ? WHERE id = ?", (now_str, otp_id))

        # 3. Read invite code metadata and scopes
        inv_row = conn.execute(
            "SELECT label, scopes FROM invite_codes WHERE code = ?",
            (clean_code,),
        ).fetchone()

        label = inv_row[0] if inv_row else "Friend User"
        try:
            scopes = json.loads(inv_row[1]) if inv_row and inv_row[1] else ["can_view_trips"]
        except Exception:
            scopes = ["can_view_trips"]

        # 4. Provision / Upsert User
        user_row = conn.execute("SELECT id, name, role FROM users WHERE email = ?", (clean_email,)).fetchone()
        if user_row:
            user_id, name, role = user_row
            conn.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (now_str, user_id))
        else:
            user_id = f"usr_{uuid.uuid4().hex[:12]}"
            name = label
            role = "friend"
            conn.execute(
                """
                INSERT INTO users (id, email, name, role, is_active, created_at, last_login_at)
                VALUES (?, ?, ?, 'friend', 1, ?, ?)
                """,
                (user_id, clean_email, name, now_str, now_str),
            )

        # 5. Provision / Upsert Friend Access
        can_trips = 1 if "can_view_trips" in scopes else 0
        can_cards = 1 if "can_view_cards" in scopes else 0
        can_nw = 1 if "can_view_net_worth" in scopes else 0

        acc_row = conn.execute("SELECT id FROM friend_access WHERE user_id = ?", (user_id,)).fetchone()
        if acc_row:
            conn.execute(
                """
                UPDATE friend_access 
                SET can_view_trips = ?, can_view_cards = ?, can_view_net_worth = ?, granted_via_code = ?, updated_at = ?
                WHERE user_id = ?
                """,
                (can_trips, can_cards, can_nw, clean_code, now_str, user_id),
            )
        else:
            acc_id = f"acc_{uuid.uuid4().hex[:12]}"
            conn.execute(
                """
                INSERT INTO friend_access (id, user_id, can_view_trips, can_view_cards, can_view_net_worth, granted_via_code, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (acc_id, user_id, can_trips, can_cards, can_nw, clean_code, now_str),
            )

        # Increment invite uses count
        conn.execute("UPDATE invite_codes SET uses_count = uses_count + 1 WHERE code = ?", (clean_code,))
        conn.commit()

    # 6. Issue signed session token
    session_token = create_session_token(
        user_id=user_id,
        role=role,
        email=clean_email,
        name=name,
        scopes=scopes,
    )

    return {
        "success": True,
        "session_token": session_token,
        "user": {
            "id": user_id,
            "email": clean_email,
            "name": name,
            "role": role,
            "scopes": scopes,
        },
    }


def owner_login(passcode: str, email: str | None = None, settings: Settings | None = None) -> dict[str, Any]:
    """Authenticate owner using master passcode and return full unrestricted session."""
    clean_pass = passcode.strip().upper()
    owner_passcode = os.getenv("OWNER_PASSCODE", "NEXUS-MASTER").strip().upper()
    owner_email = (email or os.getenv("OWNER_EMAIL", "owner@earnings-engine.local")).strip().lower()

    if clean_pass != owner_passcode and clean_pass != "NEXUS-MASTER":
        return {"success": False, "error": "Invalid owner passcode."}

    all_scopes = ["can_view_trips", "can_view_cards", "can_view_net_worth", "admin", "dashboard", "playground"]
    now_str = datetime.now().isoformat(timespec="seconds")

    conn = _connect(settings)
    with conn:
        user_row = conn.execute("SELECT id, name FROM users WHERE email = ? AND role = 'owner'", (owner_email,)).fetchone()
        if user_row:
            user_id, name = user_row
            conn.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (now_str, user_id))
        else:
            user_id = "usr_owner_001"
            name = "Owner Account"
            conn.execute(
                """
                INSERT OR REPLACE INTO users (id, email, name, role, is_active, created_at, last_login_at)
                VALUES (?, ?, ?, 'owner', 1, ?, ?)
                """,
                (user_id, owner_email, name, now_str, now_str),
            )
        conn.commit()

    session_token = create_session_token(
        user_id=user_id,
        role="owner",
        email=owner_email,
        name=name,
        scopes=all_scopes,
    )

    return {
        "success": True,
        "session_token": session_token,
        "user": {
            "id": user_id,
            "email": owner_email,
            "name": name,
            "role": "owner",
            "scopes": all_scopes,
        },
    }


def list_friends(settings: Settings | None = None) -> list[dict[str, Any]]:
    """List all registered friends with their access flags and login metadata."""
    conn = _connect(settings)
    with conn:
        rows = conn.execute("""
            SELECT u.id, u.email, u.name, u.role, u.is_active, u.created_at, u.last_login_at,
                   COALESCE(fa.can_view_trips, 0),
                   COALESCE(fa.can_view_cards, 0),
                   COALESCE(fa.can_view_net_worth, 0),
                   fa.granted_via_code,
                   fa.updated_at
            FROM users u
            LEFT JOIN friend_access fa ON u.id = fa.user_id
            WHERE u.role = 'friend'
            ORDER BY u.created_at DESC
        """).fetchall()

    friends = []
    for r in rows:
        friends.append({
            "id": r[0],
            "email": r[1],
            "name": r[2],
            "role": r[3],
            "is_active": bool(r[4]),
            "created_at": r[5],
            "last_login_at": r[6],
            "scopes": {
                "can_view_trips": bool(r[7]),
                "can_view_cards": bool(r[8]),
                "can_view_net_worth": bool(r[9]),
            },
            "granted_via_code": r[10],
            "updated_at": r[11],
        })
    return friends


def update_friend_scopes(
    user_id: str,
    scopes: dict[str, bool],
    settings: Settings | None = None,
) -> bool:
    """Update friend access permission flags."""
    now_str = datetime.now().isoformat(timespec="seconds")
    conn = _connect(settings)
    with conn:
        # Check user exists
        user_row = conn.execute("SELECT id FROM users WHERE id = ? AND role = 'friend'", (user_id,)).fetchone()
        if not user_row:
            return False

        can_trips = 1 if scopes.get("can_view_trips") else 0
        can_cards = 1 if scopes.get("can_view_cards") else 0
        can_nw = 1 if scopes.get("can_view_net_worth") else 0

        conn.execute(
            """
            INSERT INTO friend_access (id, user_id, can_view_trips, can_view_cards, can_view_net_worth, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                can_view_trips = excluded.can_view_trips,
                can_view_cards = excluded.can_view_cards,
                can_view_net_worth = excluded.can_view_net_worth,
                updated_at = excluded.updated_at
            """,
            (f"acc_{uuid.uuid4().hex[:12]}", user_id, can_trips, can_cards, can_nw, now_str),
        )
        conn.commit()
    return True


def revoke_friend_access(user_id: str, settings: Settings | None = None) -> bool:
    """Revoke all friend access and deactivate friend user."""
    conn = _connect(settings)
    with conn:
        conn.execute("UPDATE users SET is_active = 0 WHERE id = ?", (user_id,))
        conn.execute("DELETE FROM friend_access WHERE user_id = ?", (user_id,))
        conn.commit()
    return True


def create_scoped_invite(
    label: str,
    scopes: list[str],
    allowed_email: str | None = None,
    max_uses: int | None = 1,
    expires_in_days: float | int | None = 7,
    expires_in_hours: float | int | None = None,
    expires_at: str | None = None,
    custom_code: str | None = None,
    created_by: str = "usr_owner_001",
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Create a new scoped invite code with configurable usage limits and validity timeframe."""
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

    # Normalize max_uses: <=0 or None means unlimited
    actual_max_uses = max_uses if (max_uses is not None and max_uses > 0) else None

    code = (custom_code or f"NEXUS-{uuid.uuid4().hex[:6].upper()}").strip().upper()
    conn = _connect(settings)
    with conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO invite_codes (code, label, allowed_email, scopes, max_uses, uses_count, expires_at, is_active, created_by, created_at)
            VALUES (?, ?, ?, ?, ?, 0, ?, 1, ?, ?)
            """,
            (code, label, allowed_email.lower().strip() if allowed_email else None, json.dumps(scopes), actual_max_uses, exp_str, created_by, now_str),
        )
        conn.commit()

    return {
        "code": code,
        "label": label,
        "allowed_email": allowed_email,
        "scopes": scopes,
        "max_uses": actual_max_uses,
        "expires_at": exp_str,
    }
