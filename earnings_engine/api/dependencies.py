"""Shared dependencies, authentication resolvers, session guards, and Pydantic models for API routers."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import time
from typing import Any

from fastapi import Depends, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from jinja2 import Environment, FileSystemLoader
from pydantic import BaseModel, Field

from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection
from earnings_engine.logging_utils import get_logger

logger = get_logger("earnings_engine.api.dependencies")

# Global settings instance
_settings = Settings()

# Templates directory
_templates_dir = Path(__file__).resolve().parent.parent / "reports" / "templates"


def get_template_env() -> Environment:
    """Return configured Jinja2 template environment."""
    return Environment(
        loader=FileSystemLoader(str(_templates_dir)),
        autoescape=True,
        auto_reload=True,
        cache_size=0,
    )


# ---------------------------------------------------------------------------
# Common Pydantic Request & Response Models
# ---------------------------------------------------------------------------

class VerifyCodeRequest(BaseModel):
    code: str


class RequestOtpRequest(BaseModel):
    email: str


class VerifyOtpRequest(BaseModel):
    email: str
    otp: str


class CreateInviteRequest(BaseModel):
    label: str = "Friend Invite"
    scopes: list[str] = ["can_view_trips"]
    allowed_email: str | None = None
    max_uses: int = 5
    expires_in_days: int | None = 14
    expires_in_hours: int | None = None
    expires_at: str | None = None
    code: str | None = None


class CreateTripRequest(BaseModel):
    title: str
    destination: str
    start_date: str
    end_date: str | None = None
    status: str = "planning"
    notes: str | None = None
    cover_image: str = "japan"
    estimated_budget: float = 150000.0
    is_shared_with_friends: bool = True
    flight_details: str | None = None
    hotel_details: str | None = None
    packing_list: list[str] = []


class SuggestTripActivityRequest(BaseModel):
    suggested_by_name: str = "Friend"
    activity_title: str
    location: str | None = None
    approx_cost: float = 0.0
    category: str | None = "SIGHTSEEING"


class CreateTripGroupRequest(BaseModel):
    name: str
    description: str = ""
    color: str = "#0284c7"
    icon: str = "🌴"
    trip_ids: list[str] = []
    members: list[dict[str, Any]] = []


class UpdateTripGroupRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    color: str | None = None
    icon: str | None = None


class AddGroupMemberRequest(BaseModel):
    name: str
    email: str
    role: str = "member"
    custom_passcode: str | None = None
    send_email: bool = True


class AttachGroupTripsRequest(BaseModel):
    trip_ids: list[str]


class CreateCardRequest(BaseModel):
    card_name: str
    issuer: str
    network: str = "VISA"
    last4: str = "0000"
    card_holder: str = "Nexus Master"
    color_theme: str = "dark"
    credit_limit: float = 500000.0
    available_limit: float = 450000.0
    billing_cycle_day: int = 15
    annual_fee_status: str = "Lifetime Free"
    lounge_access_summary: str = "Unlimited Domestic & International Lounge Visits"
    category_perks: dict[str, Any] = {}
    is_shared_with_friends: bool = True


class CreateCardOtpRequest(BaseModel):
    card_id: str
    requested_by_name: str = "Friend"
    amount: float = 0.0
    merchant: str = ""
    purpose: str | None = "Online Travel Booking"
    urgency: str = "normal"
    transaction_amount: float | None = None
    merchant_name: str | None = None

    def model_post_init(self, __context: Any) -> None:
        if self.transaction_amount is not None and not self.amount:
            self.amount = self.transaction_amount
        if self.merchant_name and not self.merchant:
            self.merchant = self.merchant_name


class ApproveCardOtpRequest(BaseModel):
    otp_code: str | None = None
    duration_minutes: int = 5
    response_notes: str | None = None


class RejectCardOtpRequest(BaseModel):
    response_notes: str | None = None


class ResolveCardOtpRequest(BaseModel):
    otp_code: str | None = None
    status: str = "approved"
    response_notes: str | None = None


class CreateNetWorthSnapshotRequest(BaseModel):
    as_of_date: str
    total_net_worth_band: str
    allocation_pct: dict[str, float]
    yoy_growth_pct: float | None = None


class CalculateEpsRequest(BaseModel):
    earnings_date: str | None = None
    override_estimate: float | None = None
    override_reported: float | None = None


class ConsensusPredictRequest(BaseModel):
    ticker: str | None = None
    tickers: list[str] | None = None
    timeframe_days: int = 14
    event_date: str | None = None
    force: bool = False
    force_refresh: bool = False
    models: list[str] | None = None
    local_model_url: str | None = None
    omniroute_model: str | None = None
    custom_directives: str | None = None
    temperature: float = 0.3
    include_raw_trace: bool = True


class ConsensusSettleRequest(BaseModel):
    as_of_date: str | None = None


# ---------------------------------------------------------------------------
# Auth Resolution & RBAC Dependencies
# ---------------------------------------------------------------------------

def _resolve_session(request: Request) -> dict[str, Any] | None:
    """Resolve session from cookie, Bearer header, or query code parameter."""
    from earnings_engine.data.auth import verify_session_token
    from earnings_engine.data.passcodes import verify_passcode

    # 1. Cookie check
    cookie_token = request.cookies.get("nexus_session")
    if cookie_token:
        payload = verify_session_token(cookie_token)
        if payload:
            return payload

    # 2. Authorization Header check
    auth_header = request.headers.get("Authorization") or request.headers.get("authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
        payload = verify_session_token(token)
        if payload:
            return payload
        # Or raw passcode as bearer token
        res = verify_passcode(token, _settings)
        if res.get("valid"):
            is_owner = res.get("role") == "owner" or res.get("is_admin")
            return {
                "sub": res.get("user_id", "usr_bearer"),
                "role": res.get("role", "owner" if is_owner else "friend"),
                "email": res.get("email", "bearer@nexus.local"),
                "name": res.get("name", "Nexus User"),
                "scopes": res.get("scopes", ["*"] if is_owner else ["can_view_trips"]),
                "passcode": token,
            }

    # 3. Direct Passcode Header check (e.g. X-Passcode, X-Nexus-Passcode)
    passcode_hdr = (
        request.headers.get("X-Passcode")
        or request.headers.get("x-passcode")
        or request.headers.get("X-Nexus-Passcode")
        or request.headers.get("x-nexus-passcode")
        or request.headers.get("X-Nexus-Code")
        or request.headers.get("x-nexus-code")
    )
    if passcode_hdr:
        res = verify_passcode(passcode_hdr, _settings)
        if res.get("valid"):
            is_owner = res.get("role") == "owner" or res.get("is_admin")
            return {
                "sub": res.get("user_id", "usr_hdr"),
                "role": res.get("role", "owner" if is_owner else "friend"),
                "email": res.get("email", "owner@nexus.local" if is_owner else "friend@nexus.local"),
                "name": res.get("name", "Nexus Master" if is_owner else "Nexus User"),
                "scopes": res.get("scopes", ["*"] if is_owner else ["can_view_trips"]),
                "allowed_routes": res.get("allowed_routes", []),
                "passcode": passcode_hdr,
            }

    # 4. Query parameter passcode fallback (e.g. /trips?code=NEXUS-XXXXXX)
    code_param = request.query_params.get("code") or request.query_params.get("passcode")
    if code_param:
        res = verify_passcode(code_param, _settings)
        if res.get("valid"):
            is_owner = res.get("role") == "owner" or res.get("is_admin")
            return {
                "sub": res.get("user_id", "usr_param"),
                "role": res.get("role", "owner" if is_owner else "friend"),
                "email": res.get("email", "friend@nexus.local"),
                "name": res.get("name", "Nexus User"),
                "scopes": res.get("scopes", ["*"] if is_owner else ["can_view_trips"]),
                "allowed_routes": res.get("allowed_routes", []),
                "passcode": code_param,
            }

    return None


def _get_current_session(request: Request) -> dict[str, Any]:
    """Resolve active user session from request state or credentials."""
    session = getattr(request.state, "session", None)
    if not session:
        session = _resolve_session(request)
    return session or {"role": None, "scopes": []}


def require_scope(required_scope: str):
    """Dependency callable that enforces owner role or explicit friend scope."""
    async def dependency(request: Request):
        session = _get_current_session(request)
        role = session.get("role")
        scopes = session.get("scopes", [])

        if not role:
            raise HTTPException(
                status_code=401,
                detail="Authentication required. Please provide a valid session token.",
            )

        if role == "owner" or "admin" in scopes or "*" in scopes or required_scope in scopes:
            return session

        raise HTTPException(
            status_code=403,
            detail=f"Access forbidden: your invite does not include permission '{required_scope}'.",
        )
    return dependency


def _require_master_role(request: Request | None) -> None:
    """Defensive check to ensure request session has Master (Owner / Admin) role."""
    if not request:
        return
    session = getattr(request.state, "session", None)
    if not session:
        session = _resolve_session(request)
    if session:
        role = session.get("role", "friend")
        scopes = set(session.get("scopes", []) + session.get("allowed_routes", []))
        if role in ("owner", "master") or "admin" in scopes or "*" in scopes:
            return
    raise HTTPException(status_code=403, detail="Owner privileges required.")
