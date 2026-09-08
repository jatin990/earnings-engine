"""Authentication, Passcode Portal, OTP Verification, and Access Management Routes."""

from __future__ import annotations

import json
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse

from earnings_engine.api.dependencies import (
    _get_current_session,
    _resolve_session,
    _settings,
    get_template_env,
    require_scope,
    CreateInviteRequest,
    RequestOtpRequest,
    VerifyCodeRequest,
    VerifyOtpRequest,
)
from earnings_engine.data.db import get_db_connection
from earnings_engine.logging_utils import get_logger

logger = get_logger("earnings_engine.api.routers.auth")

router = APIRouter(tags=["Auth & Access Control"])


@router.get("/", tags=["UI"], response_class=HTMLResponse)
@router.get("/portal", tags=["UI"], response_class=HTMLResponse)
@router.get("/join", tags=["UI"], response_class=HTMLResponse)
@router.get("/api/index.py", tags=["UI"], response_class=HTMLResponse, include_in_schema=False)
@router.get("/api/index", tags=["UI"], response_class=HTMLResponse, include_in_schema=False)
@router.get("/api", tags=["UI"], response_class=HTMLResponse, include_in_schema=False)
async def serve_portal():
    """Serve the Nexus Passcode Portal, Join Onboarding & App Launcher."""
    try:
        env = get_template_env()
        template = env.get_template("hubs/portal/index.html")
        html = template.render()
        return HTMLResponse(html)
    except Exception as exc:
        return HTMLResponse(
            f"<html><body><h1>Portal render error</h1><p>{exc}</p></body></html>",
            status_code=500,
        )


@router.post("/api/v1/auth/verify-code")
async def verify_portal_code(req: VerifyCodeRequest, response: Response):
    """Verify input passcode and return authorized applications and permissions."""
    from earnings_engine.data.passcodes import verify_passcode
    from earnings_engine.data.auth import create_session_token
    result = verify_passcode(req.code, _settings)
    if not result.get("valid"):
        raise HTTPException(status_code=401, detail=result.get("error", "Invalid access passcode."))
    
    is_owner = result.get("role") == "owner" or result.get("is_admin")
    role = result.get("role") or ("owner" if is_owner else "friend")
    scopes = result.get("scopes") or (
        ["can_view_trips", "can_view_cards", "can_view_net_worth", "can_view_zepto", "zepto", "admin", "dashboard", "credit_card"]
        if is_owner else ["can_view_trips"]
    )
    email = result.get("email") or ("owner@nexus.local" if is_owner else "friend@nexus.local")
    name = result.get("name") or ("Nexus Master" if is_owner else "Friend")

    token = create_session_token(
        user_id=result.get("user_id", "usr_portal"),
        role=role,
        email=email,
        name=name,
        scopes=scopes,
        expires_in_days=30 if is_owner else 14,
    )

    response.set_cookie(
        key="nexus_session",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=30 * 86400 if is_owner else 14 * 86400,
        path="/",
    )

    resp_data = {
        **result,
        "valid": True,
        "code": req.code,
        "role": role,
        "is_owner": is_owner,
        "user_id": result.get("user_id"),
        "name": name,
        "email": email,
        "scopes": scopes,
        "authorized_apps": result.get("authorized_apps", []),
        "landing_url": result.get("landing_url", "/dashboard" if is_owner else "/trips"),
        "token": token,
        "session_token": token,
    }
    return resp_data


@router.post("/api/v1/auth/request-otp")
async def request_otp_endpoint(req: RequestOtpRequest):
    """Generate and dispatch 6-digit email OTP for vault login."""
    from earnings_engine.data.auth import generate_and_send_email_otp
    res = generate_and_send_email_otp(req.email.strip().lower(), settings=_settings)
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error", "Failed to generate OTP"))
    return res


@router.post("/api/v1/auth/verify-otp")
async def verify_otp_endpoint(req: VerifyOtpRequest, response: Response):
    """Verify 6-digit OTP and issue authenticated session token."""
    from earnings_engine.data.auth import verify_email_otp
    res = verify_email_otp(req.email.strip().lower(), req.otp.strip(), settings=_settings)
    if not res.get("success"):
        raise HTTPException(status_code=401, detail=res.get("error", "Invalid or expired OTP"))

    token = res.get("token")
    if token:
        response.set_cookie(
            key="nexus_session",
            value=token,
            httponly=True,
            samesite="lax",
            max_age=30 * 86400,
            path="/",
        )
    return res


@router.post("/api/v1/auth/owner-login")
async def owner_login_endpoint(req: dict, response: Response):
    """Master owner login with secret credentials."""
    secret = req.get("master_key") or req.get("passcode")
    from earnings_engine.data.passcodes import verify_passcode
    from earnings_engine.data.auth import create_session_token
    res = verify_passcode(secret, _settings)
    if not res.get("valid") or res.get("role") != "owner":
        raise HTTPException(status_code=401, detail="Invalid master credentials.")

    token = create_session_token(
        user_id="usr_owner_001",
        role="owner",
        email="owner@nexus.local",
        name="Master Admin",
        scopes=["*"],
        expires_in_days=30,
    )
    response.set_cookie(
        key="nexus_session",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=30 * 86400,
        path="/",
    )
    return {"success": True, "role": "owner", "token": token}


@router.get("/api/v1/auth/session")
@router.get("/api/v1/auth/me")
async def get_current_user_session(request: Request, code: str | None = Query(None)):
    """Retrieve active session metadata and authorized scopes."""
    session = _get_current_session(request)
    if not session and code:
        from earnings_engine.data.passcodes import verify_passcode
        res = verify_passcode(code, _settings)
        if res.get("valid"):
            session = {
                "sub": res.get("user_id", "usr_portal"),
                "role": res.get("role", "friend"),
                "email": res.get("email"),
                "name": res.get("name"),
                "scopes": res.get("scopes", []),
            }
    if not session or not session.get("role"):
        return {"authenticated": False, "role": "guest", "scopes": []}
    return {
        "authenticated": True,
        "user_id": session.get("sub"),
        "role": session.get("role"),
        "email": session.get("email"),
        "name": session.get("name"),
        "scopes": session.get("scopes", []),
        "is_owner": session.get("role") == "owner",
    }


@router.get("/api/v1/auth/codes")
async def list_passcodes_endpoint(request: Request):
    """List active system passcodes (Owner only)."""
    session = _get_current_session(request)
    if session.get("role") != "owner" and "admin" not in session.get("scopes", []):
        raise HTTPException(status_code=403, detail="Owner privileges required.")

    from earnings_engine.data.passcodes import list_passcodes
    codes = list_passcodes(settings=_settings)
    return {"codes": codes, "passcodes": codes}


@router.post("/api/v1/auth/codes")
async def create_passcode_endpoint(req: dict, request: Request):
    """Create a new custom access passcode (Owner only)."""
    session = _get_current_session(request)
    if session.get("role") != "owner" and "admin" not in session.get("scopes", []):
        raise HTTPException(status_code=403, detail="Owner privileges required.")

    from earnings_engine.data.passcodes import create_passcode
    created = create_passcode(
        code=req.get("code"),
        label=req.get("label", "Custom Code"),
        allowed_routes=req.get("allowed_routes", req.get("allowed_apps", ["dashboard"])),
        max_uses=int(req.get("max_uses", 10)),
        expires_in_days=float(req.get("expires_in_days", 30)),
        settings=_settings,
    )
    return {"success": True, **created}


@router.delete("/api/v1/auth/codes/{code}")
async def revoke_passcode_endpoint(code: str, request: Request):
    """Revoke an active passcode (Owner only)."""
    session = _get_current_session(request)
    if session.get("role") != "owner" and "admin" not in session.get("scopes", []):
        raise HTTPException(status_code=403, detail="Owner privileges required.")

    from earnings_engine.data.passcodes import delete_passcode
    deleted = delete_passcode(code, settings=_settings)
    return {"success": True, "message": f"Code {code} revoked.", "deleted": deleted}


@router.get("/api/v1/invites")
async def list_invites_endpoint(request: Request):
    """Owner-only list of all created invite codes."""
    session = _get_current_session(request)
    if session.get("role") != "owner" and "admin" not in session.get("scopes", []):
        raise HTTPException(status_code=403, detail="Owner privileges required.")

    conn = get_db_connection(_settings)
    with conn:
        rows = conn.execute("""
            SELECT code, label, allowed_email, scopes, max_uses, uses_count, expires_at, is_active, created_at
            FROM invite_codes ORDER BY created_at DESC
        """).fetchall()

    invites = []
    for r in rows:
        try:
            scopes = json.loads(r[3]) if r[3] else []
        except Exception:
            scopes = []
        invites.append({
            "code": r[0],
            "label": r[1],
            "allowed_email": r[2],
            "scopes": scopes,
            "max_uses": r[4],
            "uses_count": r[5],
            "expires_at": r[6],
            "is_active": bool(r[7]),
            "created_at": r[8],
        })
    return {"invites": invites}


@router.post("/api/v1/invites")
async def create_invite_endpoint(req: CreateInviteRequest, request: Request):
    """Create a new scoped invite code."""
    session = _get_current_session(request)
    if session.get("role") != "owner" and "admin" not in session.get("scopes", []):
        raise HTTPException(status_code=403, detail="Owner privileges required.")

    from earnings_engine.data.auth import create_scoped_invite
    created = create_scoped_invite(
        label=req.label,
        scopes=req.scopes,
        allowed_email=req.allowed_email,
        max_uses=req.max_uses,
        expires_in_days=req.expires_in_days,
        expires_in_hours=req.expires_in_hours,
        expires_at=req.expires_at,
        custom_code=req.code,
        created_by=session.get("sub", "usr_owner_001"),
        settings=_settings,
    )
    return created


@router.delete("/api/v1/invites/{code}")
async def delete_invite_endpoint(code: str, request: Request):
    """Owner-only deletion and revocation of scoped invite code."""
    session = _get_current_session(request)
    if session.get("role") != "owner" and "admin" not in session.get("scopes", []):
        raise HTTPException(status_code=403, detail="Owner privileges required.")

    from earnings_engine.data.auth import delete_scoped_invite
    success = delete_scoped_invite(code, settings=_settings)
    return {"success": success, "code": code}


@router.get("/api/v1/friends")
async def list_friends_endpoint(request: Request):
    """List friend users and their permissions (Owner only)."""
    session = _get_current_session(request)
    if session.get("role") != "owner" and "admin" not in session.get("scopes", []):
        raise HTTPException(status_code=403, detail="Owner privileges required.")

    from earnings_engine.data.auth import list_friends
    friends = list_friends(settings=_settings)
    return {"success": True, "friends": friends}


@router.delete("/api/v1/friends/{user_id}")
async def revoke_friend_endpoint(user_id: str, request: Request):
    """Owner-only revocation and deactivation of friend user."""
    session = _get_current_session(request)
    if session.get("role") != "owner" and "admin" not in session.get("scopes", []):
        raise HTTPException(status_code=403, detail="Owner privileges required.")

    from earnings_engine.data.auth import revoke_friend_access
    success = revoke_friend_access(user_id, settings=_settings)
    return {"success": success, "user_id": user_id}


@router.post("/api/v1/friends/{user_id}/access")
@router.patch("/api/v1/friends/{user_id}/access")
async def update_friend_access_endpoint(user_id: str, request: Request):
    """Owner-only update of friend scoped permissions."""
    session = _get_current_session(request)
    if session.get("role") != "owner" and "admin" not in session.get("scopes", []):
        raise HTTPException(status_code=403, detail="Owner privileges required.")

    body = await request.json()
    scopes_dict = body.get("scopes") or {}
    from earnings_engine.data.auth import update_friend_scopes
    success = update_friend_scopes(user_id, scopes_dict, settings=_settings)
    if not success:
        raise HTTPException(status_code=404, detail="Friend not found.")
    return {"success": True, "user_id": user_id, "updated_scopes": scopes_dict}

