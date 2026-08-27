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
    CreateCardOtpRequest,
    CreateCardRequest,
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
async def get_card_otp_requests(session: dict = Depends(require_scope("can_view_cards"))):
    """Retrieve pending and historical OTP requests for friend card sharing."""
    role = session.get("role")
    scopes = session.get("scopes", [])
    is_owner = bool(role == "owner" or "admin" in scopes or "*" in scopes)
    user_id = session.get("sub")

    conn = get_db_connection(_settings)
    with conn:
        if is_owner:
            rows = conn.execute("""
                SELECT o.id, o.card_id, o.requested_by_user_id, o.requested_by_name, o.transaction_amount,
                       o.merchant_name, o.purpose, o.status, o.otp_code, o.requested_at, o.resolved_at,
                       c.card_name, c.last4
                FROM card_otp_requests o
                JOIN credit_cards c ON o.card_id = c.id
                ORDER BY o.requested_at DESC LIMIT 50
            """).fetchall()
        else:
            rows = conn.execute("""
                SELECT o.id, o.card_id, o.requested_by_user_id, o.requested_by_name, o.transaction_amount,
                       o.merchant_name, o.purpose, o.status, o.otp_code, o.requested_at, o.resolved_at,
                       c.card_name, c.last4
                FROM card_otp_requests o
                JOIN credit_cards c ON o.card_id = c.id
                WHERE o.requested_by_user_id = ?
                ORDER BY o.requested_at DESC LIMIT 20
            """, (user_id,)).fetchall()

    requests_list = [
        {
            "id": r[0],
            "card_id": r[1],
            "requested_by_user_id": r[2],
            "requested_by_name": r[3],
            "transaction_amount": float(r[4] or 0.0),
            "merchant_name": r[5],
            "purpose": r[6],
            "status": r[7],
            "otp_code": r[8] if is_owner or r[7] == "approved" else None,
            "requested_at": r[9],
            "resolved_at": r[10],
            "card_name": r[11],
            "last4": r[12],
        }
        for r in rows
    ]
    return {"success": True, "count": len(requests_list), "otp_requests": requests_list, "is_owner": is_owner}


@router.post("/api/v1/cards/otp-requests")
async def create_card_otp_request(
    req: CreateCardOtpRequest,
    session: dict = Depends(require_scope("can_view_cards")),
):
    """Submit a real-time OTP request to use a friend/family card for an online payment."""
    user_id = session.get("sub", "friend_usr")
    user_name = session.get("name", "Friend User")
    req_id = f"otp_{uuid.uuid4().hex[:8]}"
    now_str = datetime.now().isoformat(timespec="seconds")

    conn = get_db_connection(_settings)
    with conn:
        card = conn.execute("SELECT id, card_name FROM credit_cards WHERE id = ?", (req.card_id,)).fetchone()
        if not card:
            raise HTTPException(status_code=404, detail="Credit card not found.")

        conn.execute("""
            INSERT INTO card_otp_requests (
                id, card_id, requested_by_user_id, requested_by_name, transaction_amount,
                merchant_name, purpose, status, requested_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)
        """, (
            req_id, req.card_id, user_id, user_name, req.transaction_amount,
            req.merchant_name, req.purpose, now_str
        ))
        conn.commit()

    logger.info("[CARDS-API] New OTP request %s by %s for ₹%.2f on %s", req_id, user_name, req.transaction_amount, req.merchant_name)
    return {"success": True, "request_id": req_id, "message": "OTP request dispatched to vault owner."}


@router.post("/api/v1/cards/otp-requests/{request_id}/approve")
async def approve_card_otp_request(
    request_id: str,
    req: ResolveCardOtpRequest,
    session: dict = Depends(require_scope("can_view_cards")),
):
    """Approve card OTP request and dispatch OTP code (Owner only)."""
    role = session.get("role")
    scopes = session.get("scopes", [])
    if role != "owner" and "admin" not in scopes and "*" not in scopes:
        raise HTTPException(status_code=403, detail="Only the vault owner can approve OTP requests.")

    now_str = datetime.now().isoformat(timespec="seconds")
    conn = get_db_connection(_settings)
    with conn:
        conn.execute("""
            UPDATE card_otp_requests
            SET status = 'approved', otp_code = ?, resolved_at = ?
            WHERE id = ?
        """, (req.otp_code, now_str, request_id))
        conn.commit()

    logger.info("[CARDS-API] Approved OTP request %s with code %s", request_id, req.otp_code)
    return {"success": True, "request_id": request_id, "status": "approved"}


@router.post("/api/v1/cards/otp-requests/{request_id}/reject")
async def reject_card_otp_request(
    request_id: str,
    session: dict = Depends(require_scope("can_view_cards")),
):
    """Reject card OTP request (Owner only)."""
    role = session.get("role")
    scopes = session.get("scopes", [])
    if role != "owner" and "admin" not in scopes and "*" not in scopes:
        raise HTTPException(status_code=403, detail="Only the vault owner can reject OTP requests.")

    now_str = datetime.now().isoformat(timespec="seconds")
    conn = get_db_connection(_settings)
    with conn:
        conn.execute("""
            UPDATE card_otp_requests
            SET status = 'rejected', resolved_at = ?
            WHERE id = ?
        """, (now_str, request_id))
        conn.commit()

    logger.info("[CARDS-API] Rejected OTP request %s", request_id)
    return {"success": True, "request_id": request_id, "status": "rejected"}
