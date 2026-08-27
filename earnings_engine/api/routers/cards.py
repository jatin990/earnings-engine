"""Credit Cards, Reward Perks, and OTP Verification Hub Routes."""

from __future__ import annotations

import json
from datetime import datetime
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from earnings_engine.api.dependencies import (
    _settings,
    get_template_env,
    require_scope,
    ApproveCardOtpRequest,
    CreateCardOtpRequest,
    CreateCardRequest,
    RejectCardOtpRequest,
    ResolveCardOtpRequest,
)
from earnings_engine.data.db import get_db_connection
from earnings_engine.logging_utils import get_logger

logger = get_logger("earnings_engine.api.routers.cards")

router = APIRouter(tags=["Credit Cards & Rewards Hub"])


@router.get("/credit-card", tags=["UI"], response_class=HTMLResponse)
@router.get("/credit-cards", tags=["UI"], response_class=HTMLResponse)
async def serve_credit_card():
    """Serve the Credit Card & Wealth Hub page."""
    try:
        env = get_template_env()
        template = env.get_template("credit_card.html")
        html = template.render()
        return HTMLResponse(html)
    except Exception as exc:
        return HTMLResponse(
            f"<html><body><h1>Credit Card Hub render error</h1><p>{exc}</p></body></html>",
            status_code=500,
        )


@router.get("/api/v1/cards")
async def get_cards_endpoint(session: dict = Depends(require_scope("can_view_cards"))):
    """Retrieve credit card benefits, reward rates, limits, and lounge access perks."""
    role = session.get("role")
    scopes = session.get("scopes", [])
    is_owner = bool(role == "owner" or "admin" in scopes or "*" in scopes)

    conn = get_db_connection(_settings)
    with conn:
        if is_owner:
            rows = conn.execute("""
                SELECT id, card_name, issuer, network, category_perks, lounge_access_summary,
                       annual_fee_status, display_order, last4, card_holder, color_theme,
                       credit_limit, available_limit, billing_cycle_day, is_shared_with_friends, created_at
                FROM credit_cards ORDER BY display_order ASC, created_at ASC
            """).fetchall()
        else:
            rows = conn.execute("""
                SELECT id, card_name, issuer, network, category_perks, lounge_access_summary,
                       annual_fee_status, display_order, last4, card_holder, color_theme,
                       credit_limit, available_limit, billing_cycle_day, is_shared_with_friends, created_at
                FROM credit_cards WHERE is_shared_with_friends = 1 ORDER BY display_order ASC, created_at ASC
            """).fetchall()

    cards = []
    for r in rows:
        try:
            perks = json.loads(r[4]) if r[4] else {}
        except Exception:
            perks = {}
        cards.append({
            "id": r[0],
            "card_name": r[1],
            "issuer": r[2],
            "network": r[3],
            "category_perks": perks,
            "lounge_access_summary": r[5],
            "annual_fee_status": r[6],
            "display_order": r[7],
            "last4": r[8],
            "card_holder": r[9],
            "color_theme": r[10] or "dark",
            "credit_limit": float(r[11] or 0.0),
            "available_limit": float(r[12] or 0.0),
            "billing_cycle_day": int(r[13] or 1),
            "is_shared_with_friends": bool(r[14]),
            "created_at": r[15],
        })
    return {"success": True, "count": len(cards), "cards": cards, "is_owner": is_owner}


@router.post("/api/v1/cards")
async def create_card_endpoint(req: CreateCardRequest, session: dict = Depends(require_scope("can_view_cards"))):
    """Add a new card to the credit card directory (Owner only)."""
    role = session.get("role")
    scopes = session.get("scopes", [])
    if role != "owner" and "admin" not in scopes and "*" not in scopes:
        raise HTTPException(status_code=403, detail="Only the vault owner can add credit cards.")

    card_id = f"card_{uuid.uuid4().hex[:8]}"
    now_str = datetime.now().isoformat(timespec="seconds")
    perks_str = json.dumps(req.category_perks)

    conn = get_db_connection(_settings)
    with conn:
        conn.execute("""
            INSERT INTO credit_cards (
                id, card_name, issuer, network, category_perks, lounge_access_summary,
                annual_fee_status, display_order, last4, card_holder, color_theme,
                credit_limit, available_limit, billing_cycle_day, is_shared_with_friends, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 10, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            card_id, req.card_name, req.issuer, req.network, perks_str, req.lounge_access_summary,
            req.annual_fee_status, req.last4, req.card_holder, req.color_theme,
            req.credit_limit, req.available_limit, req.billing_cycle_day,
            1 if req.is_shared_with_friends else 0, now_str
        ))
        conn.commit()

    logger.info("[CARDS-API] Created new card %s (%s - %s)", card_id, req.card_name, req.issuer)
    return {"success": True, "card_id": card_id, "message": "Card created successfully."}


@router.delete("/api/v1/cards/{card_id}")
async def delete_card_endpoint(card_id: str, session: dict = Depends(require_scope("can_view_cards"))):
    """Delete a credit card (Owner only)."""
    role = session.get("role")
    scopes = session.get("scopes", [])
    if role != "owner" and "admin" not in scopes and "*" not in scopes:
        raise HTTPException(status_code=403, detail="Only the vault owner can delete credit cards.")

    conn = get_db_connection(_settings)
    with conn:
        conn.execute("DELETE FROM credit_cards WHERE id = ?", (card_id,))
        conn.commit()

    logger.info("[CARDS-API] Deleted card %s", card_id)
    return {"success": True, "message": f"Card {card_id} deleted."}


@router.get("/api/v1/cards/otp-requests")
async def get_card_otp_requests_endpoint(
    card_id: str | None = None,
    status: str | None = None,
    session: dict = Depends(require_scope("can_view_cards")),
):
    """List OTP requests for credit cards with live status and expiration."""
    from datetime import timedelta
    role = session.get("role")
    scopes = session.get("scopes", [])
    is_owner = bool(role == "owner" or "admin" in scopes or "*" in scopes)

    conn = get_db_connection(_settings)
    with conn:
        query = """
            SELECT r.id, r.card_id, r.requested_by_name, r.requested_by_role, r.amount, r.merchant,
                   r.purpose, r.urgency, r.status, r.otp_code, r.otp_expires_at, r.response_notes,
                   r.created_at, r.updated_at, c.card_name, c.last4, c.color_theme, c.issuer
            FROM credit_card_otp_requests r
            LEFT JOIN credit_cards c ON r.card_id = c.id
            WHERE 1=1
        """
        params: list[Any] = []
        if card_id:
            query += " AND r.card_id = ?"
            params.append(card_id)
        if status:
            query += " AND r.status = ?"
            params.append(status)
        query += " ORDER BY r.created_at DESC LIMIT 50"

        rows = conn.execute(query, params).fetchall()

    requests_list: list[dict[str, Any]] = []
    now = datetime.now()
    for r in rows:
        req_status = r[8]
        otp_expires_at = r[10]
        remaining_seconds = 0
        if otp_expires_at:
            try:
                exp_dt = datetime.fromisoformat(otp_expires_at)
                diff = (exp_dt - now).total_seconds()
                if diff > 0:
                    remaining_seconds = int(diff)
                elif req_status == "approved":
                    req_status = "expired"
            except Exception:
                pass

        requests_list.append({
            "id": r[0],
            "card_id": r[1],
            "requested_by_name": r[2],
            "requested_by_role": r[3],
            "amount": float(r[4] or 0.0),
            "merchant": r[5],
            "purpose": r[6],
            "urgency": r[7],
            "status": req_status,
            "otp_code": r[9] if (req_status == "approved" or is_owner) else None,
            "otp_expires_at": otp_expires_at,
            "remaining_seconds": remaining_seconds,
            "response_notes": r[11],
            "created_at": r[12],
            "updated_at": r[13],
            "card_name": r[14] or "Shared Credit Card",
            "last4": r[15] or "8842",
            "color_theme": r[16] or "obsidian",
            "issuer": r[17] or "Bank",
        })

    return {
        "success": True,
        "count": len(requests_list),
        "requests": requests_list,
        "otp_requests": requests_list,
        "is_owner": is_owner,
    }


@router.post("/api/v1/cards/otp-requests")
async def create_card_otp_request_endpoint(
    req: CreateCardOtpRequest,
    session: dict = Depends(require_scope("can_view_cards")),
):
    """Submit a request for an OTP for a specific card and transaction amount."""
    role = session.get("role") or "friend"
    req_id = f"req_cc_{uuid.uuid4().hex[:8]}"
    now_str = datetime.now().isoformat(timespec="seconds")

    conn = get_db_connection(_settings)
    with conn:
        card = conn.execute("SELECT id, card_name FROM credit_cards WHERE id = ?", (req.card_id,)).fetchone()
        if not card:
            raise HTTPException(status_code=404, detail="Credit card not found.")

        conn.execute("""
            INSERT INTO credit_card_otp_requests (
                id, card_id, requested_by_name, requested_by_role, amount, merchant,
                purpose, urgency, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
        """, (
            req_id, req.card_id, req.requested_by_name, role, req.amount,
            req.merchant, req.purpose, req.urgency, now_str, now_str
        ))
        conn.commit()

    logger.info("[CARDS-OTP] New OTP request %s from %s for ₹%.2f on %s (%s)",
                req_id, req.requested_by_name, req.amount, card[1], req.merchant)
    return {
        "success": True,
        "request_id": req_id,
        "status": "pending",
        "message": f"OTP Request for ₹{req.amount:,.2f} at {req.merchant} submitted. Waiting for owner approval."
    }


@router.post("/api/v1/cards/otp-requests/{request_id}/approve")
async def approve_card_otp_request_endpoint(
    request_id: str,
    req: ApproveCardOtpRequest,
    session: dict = Depends(require_scope("can_view_cards")),
):
    """Approve a card OTP request and provide/generate the active OTP code (Owner only)."""
    from datetime import timedelta
    import random
    role = session.get("role")
    scopes = session.get("scopes", [])
    if role != "owner" and "admin" not in scopes and "*" not in scopes:
        raise HTTPException(status_code=403, detail="Only the vault owner can approve OTP requests.")

    otp_code = req.otp_code.strip() if req.otp_code else f"{random.randint(100000, 999999)}"
    duration = max(1, min(req.duration_minutes, 30))
    exp_dt = (datetime.now() + timedelta(minutes=duration)).isoformat(timespec="seconds")
    now_str = datetime.now().isoformat(timespec="seconds")

    conn = get_db_connection(_settings)
    with conn:
        row = conn.execute("SELECT id, requested_by_name, amount, merchant FROM credit_card_otp_requests WHERE id = ?", (request_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="OTP request not found.")

        conn.execute("""
            UPDATE credit_card_otp_requests
            SET status = 'approved', otp_code = ?, otp_expires_at = ?, response_notes = ?, updated_at = ?
            WHERE id = ?
        """, (otp_code, exp_dt, req.response_notes or "Approved by Owner", now_str, request_id))
        conn.commit()

    logger.info("[CARDS-OTP] Approved OTP request %s for %s (OTP: %s, expires: %s)", request_id, row[1], otp_code, exp_dt)
    return {
        "success": True,
        "request_id": request_id,
        "status": "approved",
        "otp_code": otp_code,
        "expires_at": exp_dt,
        "duration_minutes": duration,
        "message": f"OTP request approved. OTP code {otp_code} valid for {duration} minutes."
    }


@router.post("/api/v1/cards/otp-requests/{request_id}/reject")
async def reject_card_otp_request_endpoint(
    request_id: str,
    req: RejectCardOtpRequest,
    session: dict = Depends(require_scope("can_view_cards")),
):
    """Reject a card OTP request (Owner only)."""
    role = session.get("role")
    scopes = session.get("scopes", [])
    if role != "owner" and "admin" not in scopes and "*" not in scopes:
        raise HTTPException(status_code=403, detail="Only the vault owner can reject OTP requests.")

    now_str = datetime.now().isoformat(timespec="seconds")
    conn = get_db_connection(_settings)
    with conn:
        row = conn.execute("SELECT id, requested_by_name FROM credit_card_otp_requests WHERE id = ?", (request_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="OTP request not found.")

        conn.execute("""
            UPDATE credit_card_otp_requests
            SET status = 'rejected', response_notes = ?, updated_at = ?
            WHERE id = ?
        """, (req.response_notes or "Declined by Owner", now_str, request_id))
        conn.commit()

    logger.info("[CARDS-OTP] Rejected OTP request %s for %s", request_id, row[1])
    return {"success": True, "request_id": request_id, "status": "rejected", "message": "OTP request declined."}
