"""Integration tests for Transmission Lead-Lag Radar API endpoints.

Validates:
- GET /api/transmission/baskets
- GET /api/transmission/graph?basket_id={basket_id}
- GET /api/transmission/graph data freshness telemetry
- GET /api/transmission/graph 404 on invalid basket
- POST /api/transmission/simulate-shockwave propagation
- POST /api/transmission/simulate-shockwave 422 out-of-range bounds
- PATCH /api/transmission/baskets/{basket_id}/gate3 status updates
- PATCH /api/transmission/baskets/{basket_id}/gate3 422 invalid status
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from earnings_engine.api.server import app

client = TestClient(app)


def test_api_baskets():
    res = client.get("/api/transmission/baskets")
    assert res.status_code == 200
    data = res.json()
    assert "baskets" in data
    basket_ids = {b["basket_id"] for b in data["baskets"]}
    assert "AI_INFRA_HARDWARE" in basket_ids
    assert "GLOBAL_CDMO_PEPTIDE_CASCADE" in basket_ids


def test_api_graph_cdmo_basket():
    res = client.get("/api/transmission/graph?basket_id=GLOBAL_CDMO_PEPTIDE_CASCADE")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert len(data["nodes"]) == 16
    assert len(data["edges"]) == 16
    assert "reentry_gates" in data
    assert "us_anchor_stabilization" in data["reentry_gates"]


def test_api_shockwave_cdmo():
    res = client.post("/api/transmission/simulate-shockwave", json={
        "basket_id": "GLOBAL_CDMO_PEPTIDE_CASCADE",
        "origin_node_id": "LLY",
        "anchor_shock_pct": 5.0,
    })
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data["propagation"], list)
    assert any(n["node_id"] == "DIVISLAB.NS" for n in data["propagation"])


def test_api_graph_shape():
    res = client.get("/api/transmission/graph?basket_id=AI_INFRA_HARDWARE")
    assert res.status_code == 200
    data = res.json()
    assert all(k in data for k in ("basket", "nodes", "edges", "anomalies", "reentry_gates", "data_freshness"))


def test_api_graph_node_freshness_fields():
    res = client.get("/api/transmission/graph?basket_id=AI_INFRA_HARDWARE")
    data = res.json()
    node = data["nodes"][0]
    assert "snapshot_as_of_utc" in node
    assert "snapshot_age_minutes" in node
    assert "is_stale" in node


def test_api_graph_invalid_basket():
    res = client.get("/api/transmission/graph?basket_id=DOES_NOT_EXIST")
    assert res.status_code == 404


def test_api_shockwave():
    res = client.post("/api/transmission/simulate-shockwave", json={
        "basket_id": "AI_INFRA_HARDWARE",
        "origin_node_id": "BE",
        "anchor_shock_pct": -5.0,
    })
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data["propagation"], list)
    assert all("simulated_shock_pct" in n for n in data["propagation"])


def test_api_shockwave_invalid_range():
    res = client.post("/api/transmission/simulate-shockwave", json={
        "basket_id": "AI_INFRA_HARDWARE",
        "origin_node_id": "BE",
        "anchor_shock_pct": -99.0,   # out of [-50, +50] bounds
    })
    assert res.status_code == 422


def test_api_gate3_update():
    res = client.patch("/api/transmission/baskets/AI_INFRA_HARDWARE/gate3",
                       json={"status": "PASS", "updated_by": "test_user"})
    assert res.status_code == 200
    # Confirm gate reflects update
    graph = client.get("/api/transmission/graph?basket_id=AI_INFRA_HARDWARE").json()
    assert graph["reentry_gates"]["q2_cash_conversion"]["status"] == "PASS"


def test_api_gate3_invalid_status():
    res = client.patch("/api/transmission/baskets/AI_INFRA_HARDWARE/gate3",
                       json={"status": "MAYBE", "updated_by": "test_user"})
    assert res.status_code == 422
