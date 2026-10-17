"""Comprehensive unit test suite for the Transmission Lead-Lag Radar.

Covers:
- Database schema initialization, table structures, and default seed data
- Snapshot retention pruning logic and index existence
- Turso cloud sync table registration
- Valuation elasticity calculations and edge cases (turnarounds, zero/negative P/E)
- Circuit proximity and status calculations
- Dual-mode delivery divergence (EOD delivery % vs Intraday volume velocity)
- Breadth-First Search (BFS) shockwave propagation with temporal exponential decay
- Graph payload construction with data freshness telemetry
"""

from __future__ import annotations

import sqlite3
import pytest

from earnings_engine.data import turso_sync
from earnings_engine.data.transmission_schema import (
    init_transmission_db,
    prune_old_snapshots,
    seed_default_transmission_baskets,
    get_all_baskets,
    get_basket_graph_raw,
)


# ============================================================================
# Task 1 Tests: Schema, Seed Data, Snapshot Retention & Turso Sync
# ============================================================================

def test_expanded_topology():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_transmission_db(conn)
    seed_default_transmission_baskets(conn)

    nodes, edges = get_basket_graph_raw("AI_INFRA_HARDWARE", conn)
    node_ids = {n["node_id"] for n in nodes}
    edge_ids = {e["edge_id"] for e in edges}

    # Verify all 18 nodes are present
    expected_new_nodes = {
        "VRT", "ETN", "GEV", "APARINDS.NS", "POWERINDIA.NS",
        "VOLTAMP.NS", "TARIL.NS", "SCHNEIDER.NS"
    }
    assert expected_new_nodes.issubset(node_ids), f"Missing nodes: {expected_new_nodes - node_ids}"
    assert len(nodes) == 18

    # Verify new key edges are present
    expected_new_edges = {
        "VRT_AEROFLEX", "ETN_POWERINDIA", "GEV_APARINDS",
        "ETN_SCHNEIDER", "POWERINDIA_VOLTAMP", "POWERINDIA_TARIL",
        "GEV_POWERINDIA", "NVDA_VRT", "BE_POWERINDIA"
    }
    assert expected_new_edges.issubset(edge_ids), f"Missing edges: {expected_new_edges - edge_ids}"
    assert len(edges) == 17


def test_schema_init_and_seed():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_transmission_db(conn)
    seed_default_transmission_baskets(conn)

    baskets = get_all_baskets(conn)
    assert len(baskets) >= 1
    assert baskets[0]["basket_id"] == "AI_INFRA_HARDWARE"
    assert baskets[0]["gate3_status"] == "PENDING"

    nodes, edges = get_basket_graph_raw("AI_INFRA_HARDWARE", conn)
    assert len(nodes) >= 10   # all spec nodes seeded
    assert len(edges) >= 8    # all spec edges seeded


def test_snapshot_retention():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_transmission_db(conn)
    seed_default_transmission_baskets(conn)

    # Insert 95 snapshots for a single node
    for i in range(95):
        conn.execute(
            "INSERT INTO transmission_snapshots (node_id, current_price, change_1d_pct) VALUES (?, ?, ?)",
            ("BE", 18.0 + i * 0.01, -0.1),
        )
    conn.commit()

    # Run the retention cleanup (pruning to 90 most recent)
    prune_old_snapshots("BE", conn, keep=90)
    count = conn.execute("SELECT COUNT(*) FROM transmission_snapshots WHERE node_id = 'BE'").fetchone()[0]
    assert count == 90


def test_snapshot_index_exists():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_transmission_db(conn)
    indexes = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")]
    assert "idx_snapshots_node_ts" in indexes


def test_turso_sync_registration():
    for table in (
        "transmission_baskets",
        "transmission_nodes",
        "transmission_edges",
        "transmission_snapshots",
    ):
        assert table in turso_sync.SYNC_TABLES, f"{table} missing from SYNC_TABLES"


# ============================================================================
# Task 2 Tests: Quantitative Engine & Anomaly Detector
# ============================================================================

from earnings_engine.data.transmission_radar import (
    compute_valuation_elasticity,
    compute_circuit_proximity,
    detect_delivery_divergence,
    compute_shockwave_bfs,
    get_transmission_graph_payload,
)


def test_elasticity_normal():
    ratio, label = compute_valuation_elasticity(168.0, 45.0)
    assert round(ratio, 2) == 3.73
    assert label == "EXTREME"


def test_elasticity_elevated():
    ratio, label = compute_valuation_elasticity(90.0, 45.0)
    assert round(ratio, 2) == 2.0
    assert label == "ELEVATED"


def test_elasticity_turnaround():
    ratio, label = compute_valuation_elasticity(-5.0, 45.0, is_turnaround=True)
    assert ratio is None
    assert label == "N/A (Turnaround)"


def test_elasticity_anchor_zero():
    ratio, label = compute_valuation_elasticity(168.0, 0.0)
    assert ratio is None
    assert "Turnaround" in label or "N/A" in label


def test_circuit_stable():
    # band 5%: lower circuit of 100 = 100 / 1.05 = 95.238; distance = (100 - 95.238) / 100 * 100 = 4.76%
    dist, status = compute_circuit_proximity(100.0, 5.0)
    assert dist > 4.0
    assert status == "STABLE"


def test_circuit_locked_bid_zero():
    # price exactly at lower circuit -> distance ~ 0
    dist, status = compute_circuit_proximity(95.24, 5.0)
    assert dist < 0.1
    assert status in ("NEAR_CIRCUIT", "CIRCUIT_LOCKED", "HIGH_FREEZE_RISK")


def test_circuit_near():
    dist, status = compute_circuit_proximity(97.0, 5.0)
    assert status == "HIGH_FREEZE_RISK"


def test_anomaly_eod_leader_dump():
    flag = detect_delivery_divergence(
        delivery_pct=22.0, vol_multiple=2.5, vol_velocity=None, data_mode="EOD"
    )
    assert flag == "LEADER_DUMP_FOLLOWER_PUMP"


def test_anomaly_intraday_rollover():
    # delivery_pct is None in intraday — must not fire EOD flag
    flag = detect_delivery_divergence(
        delivery_pct=None, vol_multiple=3.0, vol_velocity=2.8, data_mode="INTRADAY"
    )
    assert flag == "INTRADAY_MOMENTUM_ROLLOVER"


def test_anomaly_no_intraday_without_velocity():
    flag = detect_delivery_divergence(
        delivery_pct=None, vol_multiple=0.8, vol_velocity=1.2, data_mode="INTRADAY"
    )
    assert flag is None


def test_shockwave_bfs_decay():
    nodes = [{"node_id": "BE"}, {"node_id": "MTAR"}]
    edges = [{
        "source_node_id": "BE",
        "target_node_id": "MTAR",
        "elasticity_multiplier": 3.73,
        "lag_window_hours": 0,
    }]
    results = compute_shockwave_bfs(nodes, edges, "BE", -5.0)
    mtar = next(r for r in results if r["node_id"] == "MTAR")
    assert round(mtar["simulated_shock_pct"], 2) == round(-5.0 * 3.73 * (0.85 ** 0), 2)


def test_shockwave_bfs_one_day_decay():
    nodes = [{"node_id": "A"}, {"node_id": "B"}]
    edges = [{
        "source_node_id": "A",
        "target_node_id": "B",
        "elasticity_multiplier": 2.0,
        "lag_window_hours": 24,
    }]
    results = compute_shockwave_bfs(nodes, edges, "A", -10.0)
    b = next(r for r in results if r["node_id"] == "B")
    assert round(b["simulated_shock_pct"], 2) == round(-10.0 * 2.0 * 0.85, 2)


def test_dag_missing_edge_node():
    nodes = [{"node_id": "A"}]
    edges = [{
        "source_node_id": "A",
        "target_node_id": "GHOST",
        "elasticity_multiplier": 1.0,
        "lag_window_hours": 0,
    }]
    # Must not raise; ghost target is silently skipped
    results = compute_shockwave_bfs(nodes, edges, "A", -5.0)
    assert not any(r["node_id"] == "GHOST" for r in results)


def test_graph_data_freshness_fields():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_transmission_db(conn)
    seed_default_transmission_baskets(conn)

    payload = get_transmission_graph_payload("AI_INFRA_HARDWARE", conn)
    assert payload["status"] == "ok"
    assert "data_freshness" in payload
    df = payload["data_freshness"]
    assert "oldest_snapshot_minutes" in df
    assert "has_stale_nodes" in df
    assert len(payload["nodes"]) == 18
    assert len(payload["edges"]) == 17
    assert "reentry_gates" in payload

