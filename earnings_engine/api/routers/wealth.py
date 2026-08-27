"""Net Worth & Asset Allocation Hub Routes."""

from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from earnings_engine.api.dependencies import (
    _settings,
    get_template_env,
    require_scope,
    CreateNetWorthSnapshotRequest,
)
from earnings_engine.data.db import get_db_connection
from earnings_engine.logging_utils import get_logger

logger = get_logger("earnings_engine.api.routers.wealth")

router = APIRouter(tags=["Net Worth & Wealth Hub"])


@router.get("/net-worth", tags=["UI"], response_class=HTMLResponse)
async def serve_net_worth():
    """Serve the Net Worth & Asset Allocation Hub page."""
    try:
        env = get_template_env()
        template = env.get_template("net_worth.html")
        html = template.render()
        return HTMLResponse(html)
    except Exception as exc:
        return HTMLResponse(
            f"<html><body><h1>Net Worth Hub render error</h1><p>{exc}</p></body></html>",
            status_code=500,
        )


@router.get("/api/v1/net-worth")
async def get_net_worth_endpoint(session: dict = Depends(require_scope("can_view_net_worth"))):
    """Retrieve net worth asset allocation breakdown, liquid cash, equity, mutual funds, real estate."""
    role = session.get("role")
    scopes = session.get("scopes", [])
    is_owner = bool(role == "owner" or "admin" in scopes or "*" in scopes)

    conn = get_db_connection(_settings)
    with conn:
        row = conn.execute("""
            SELECT id, as_of_date, total_net_worth_band, allocation_pct, yoy_growth_pct, updated_at
            FROM net_worth_snapshots
            ORDER BY as_of_date DESC LIMIT 1
        """).fetchone()

    if not row:
        default_alloc = {
            "Indian Equities": 42.5,
            "US Equities": 14.0,
            "Mutual Funds & SGBs": 22.0,
            "Real Estate": 11.5,
            "Liquid Cash & Arbitrage": 10.0,
        }
        return {
            "success": True,
            "snapshot": None,
            "is_owner": is_owner,
        }

    try:
        alloc = json.loads(row[3]) if row[3] else {}
    except Exception:
        alloc = {}

    return {
        "success": True,
        "is_owner": is_owner,
        "snapshot": {
            "id": row[0],
            "as_of_date": row[1],
            "total_net_worth_band": row[2] if is_owner else "Confidential HNI Tier",
            "allocation_pct": alloc,
            "yoy_growth_pct": row[4],
            "updated_at": row[5],
        }
    }


@router.post("/api/v1/net-worth")
async def create_net_worth_snapshot(
    req: CreateNetWorthSnapshotRequest,
    session: dict = Depends(require_scope("can_view_net_worth")),
):
    """Record a new net worth snapshot and asset allocation (Owner only)."""
    role = session.get("role")
    scopes = session.get("scopes", [])
    if role != "owner" and "admin" not in scopes and "*" not in scopes:
        raise HTTPException(status_code=403, detail="Only the vault owner can update net worth snapshots.")

    import uuid
    snap_id = f"nw_{uuid.uuid4().hex[:8]}"
    now_str = datetime.now().isoformat(timespec="seconds")
    alloc_str = json.dumps(req.allocation_pct)

    conn = get_db_connection(_settings)
    with conn:
        conn.execute("""
            INSERT INTO net_worth_snapshots (id, as_of_date, total_net_worth_band, allocation_pct, yoy_growth_pct, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (snap_id, req.as_of_date, req.total_net_worth_band, alloc_str, req.yoy_growth_pct, now_str))
        conn.commit()

    logger.info("[NET-WORTH-API] Recorded new net worth snapshot %s (%s)", snap_id, req.total_net_worth_band)
    return {"success": True, "snapshot_id": snap_id, "message": "Net worth snapshot updated successfully."}


@router.get("/api/v1/net-worth/history")
async def get_net_worth_history(session: dict = Depends(require_scope("can_view_net_worth"))):
    """Retrieve historical net worth snapshots for trend tracking."""
    role = session.get("role")
    scopes = session.get("scopes", [])
    is_owner = bool(role == "owner" or "admin" in scopes or "*" in scopes)

    conn = get_db_connection(_settings)
    with conn:
        rows = conn.execute("""
            SELECT id, as_of_date, total_net_worth_band, allocation_pct, yoy_growth_pct, updated_at
            FROM net_worth_snapshots
            ORDER BY as_of_date ASC
        """).fetchall()

    history = []
    for r in rows:
        try:
            alloc = json.loads(r[3]) if r[3] else {}
        except Exception:
            alloc = {}
        history.append({
            "id": r[0],
            "as_of_date": r[1],
            "total_net_worth_band": r[2] if is_owner else "Protected Band",
            "allocation_pct": alloc,
            "yoy_growth_pct": r[4],
            "updated_at": r[5],
        })

    return {"success": True, "count": len(history), "history": history}
