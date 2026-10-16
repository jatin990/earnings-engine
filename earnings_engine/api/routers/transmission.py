"""FastAPI router for Transmission Lead-Lag Radar.

Endpoints:
- GET  /api/transmission/baskets: List all configured thematic baskets
- GET  /api/transmission/graph: Full graph payload with nodes, edges, anomalies, gates, and freshness
- POST /api/transmission/simulate-shockwave: Real-time BFS shockwave impact simulation
- PATCH /api/transmission/baskets/{basket_id}/gate3: Update Gate 3 cash conversion audit status
"""

from __future__ import annotations

from datetime import datetime, timezone
import sqlite3
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection
from earnings_engine.data.transmission_schema import (
    init_transmission_db,
    seed_default_transmission_baskets,
    get_all_baskets,
    get_basket_graph_raw,
)
from earnings_engine.data.transmission_radar import (
    get_transmission_graph_payload,
    compute_shockwave_bfs,
)
from earnings_engine.logging_utils import get_logger

logger = get_logger("earnings_engine.api.routers.transmission")

router = APIRouter(prefix="/transmission", tags=["Transmission Lead-Lag Radar"])
_settings = Settings()


class ShockwaveRequest(BaseModel):
    basket_id: str
    origin_node_id: str
    anchor_shock_pct: float = Field(..., ge=-50.0, le=50.0)


class Gate3Update(BaseModel):
    status: Literal["PENDING", "PASS", "FAIL"]
    updated_by: str = Field(..., min_length=1)


def _ensure_transmission_seeded(conn: Any) -> None:
    """Ensure transmission tables and default basket exist."""
    try:
        init_transmission_db(conn)
        seed_default_transmission_baskets(conn)
    except Exception as e:
        logger.debug("[TRANSMISSION] Schema ensure note: %s", e)


# ============================================================================
# Static / Literal Endpoints First
# ============================================================================

@router.get("/baskets")
def list_baskets() -> dict[str, Any]:
    """Return list of all configured transmission baskets."""
    conn = get_db_connection(_settings)
    try:
        _ensure_transmission_seeded(conn)
        baskets = get_all_baskets(conn)
        return {"status": "ok", "baskets": baskets}
    finally:
        if hasattr(conn, "close"):
            conn.close()


@router.get("/graph")
def get_graph(basket_id: str = Query(..., description="ID of the basket, e.g. AI_INFRA_HARDWARE")) -> dict[str, Any]:
    """Return enriched graph payload including nodes, edges, telemetry, and reentry gates."""
    conn = get_db_connection(_settings)
    try:
        _ensure_transmission_seeded(conn)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM transmission_baskets WHERE basket_id = ?", (basket_id,))
        exists = cur.fetchone()[0]
        if not exists:
            raise HTTPException(status_code=404, detail=f"Basket '{basket_id}' not found.")

        payload = get_transmission_graph_payload(basket_id, conn)
        return payload
    finally:
        if hasattr(conn, "close"):
            conn.close()


@router.post("/simulate-shockwave")
def simulate_shockwave(req: ShockwaveRequest) -> dict[str, Any]:
    """Run on-demand BFS shockwave propagation across the DAG."""
    conn = get_db_connection(_settings)
    try:
        _ensure_transmission_seeded(conn)
        raw_nodes, raw_edges = get_basket_graph_raw(req.basket_id, conn)
        if not raw_nodes:
            raise HTTPException(status_code=404, detail=f"Basket '{req.basket_id}' has no nodes or does not exist.")

        # Check origin exists
        origin_exists = any(n["node_id"] == req.origin_node_id for n in raw_nodes)
        if not origin_exists:
            raise HTTPException(status_code=404, detail=f"Origin node '{req.origin_node_id}' not found in basket.")

        propagation = compute_shockwave_bfs(
            nodes=raw_nodes,
            edges=raw_edges,
            origin_node_id=req.origin_node_id,
            anchor_shock_pct=req.anchor_shock_pct,
        )

        return {
            "status": "ok",
            "basket_id": req.basket_id,
            "origin_node_id": req.origin_node_id,
            "anchor_shock_pct": req.anchor_shock_pct,
            "propagation": propagation,
        }
    finally:
        if hasattr(conn, "close"):
            conn.close()


# ============================================================================
# Parameterized Route
# ============================================================================

@router.patch("/baskets/{basket_id}/gate3")
def update_gate3_status(basket_id: str, body: Gate3Update) -> dict[str, Any]:
    """Update Gate 3 cash conversion audit status."""
    conn = get_db_connection(_settings)
    try:
        _ensure_transmission_seeded(conn)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM transmission_baskets WHERE basket_id = ?", (basket_id,))
        if not cur.fetchone()[0]:
            raise HTTPException(status_code=404, detail=f"Basket '{basket_id}' not found.")

        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("""
        UPDATE transmission_baskets
        SET gate3_cash_conversion_status = ?,
            gate3_updated_at = ?,
            gate3_updated_by = ?,
            updated_at = ?
        WHERE basket_id = ?;
        """, (body.status, now_str, body.updated_by, now_str, basket_id))
        conn.commit()

        return {
            "status": "ok",
            "basket_id": basket_id,
            "gate3_cash_conversion_status": body.status,
            "gate3_updated_at": now_str,
            "gate3_updated_by": body.updated_by,
        }
    finally:
        if hasattr(conn, "close"):
            conn.close()
