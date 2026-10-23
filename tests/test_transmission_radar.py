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
    get_node_recent_catalysts,
    compute_node_trade_recommendation,
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

    payload = get_transmission_graph_payload("AI_INFRA_HARDWARE", conn, auto_sync=False)
    assert payload["status"] == "ok"
    assert "data_freshness" in payload
    df = payload["data_freshness"]
    assert "oldest_snapshot_minutes" in df
    assert "has_stale_nodes" in df
    assert len(payload["nodes"]) == 18
    assert len(payload["edges"]) == 17
    assert "reentry_gates" in payload
    # Check that nodes now have catalysts and trade_action fields
    for node in payload["nodes"]:
        assert "catalysts" in node
        assert isinstance(node["catalysts"], list)
        assert "trade_action" in node
        assert "action" in node["trade_action"]


def test_get_node_recent_catalysts_empty():
    conn = sqlite3.connect(":memory:")
    catalysts = get_node_recent_catalysts("NONEXISTENT", conn)
    assert catalysts == []


def test_get_node_recent_catalysts_with_data():
    conn = sqlite3.connect(":memory:")
    conn.execute("""
    CREATE TABLE news_catalysts (
        id INTEGER PRIMARY KEY,
        ticker TEXT,
        title TEXT,
        category TEXT,
        impact_score INTEGER,
        published_at TEXT,
        summary TEXT
    )
    """)
    conn.execute("""
    CREATE TABLE earnings_history (
        ticker TEXT,
        earnings_date TEXT,
        eps_estimate REAL,
        eps_reported REAL,
        surprise_pct REAL,
        source TEXT,
        PRIMARY KEY (ticker, earnings_date, source)
    )
    """)
    conn.execute("""
    INSERT INTO news_catalysts (ticker, title, category, impact_score, published_at, summary)
    VALUES ('POWERINDIA.NS', 'Hitachi Energy bags ₹1,200 Cr substation order', 'Order Wins & Contracts', 85, '2026-10-15', 'Mega order from PGCIL')
    """)
    conn.execute("""
    INSERT INTO earnings_history (ticker, earnings_date, eps_estimate, eps_reported, surprise_pct, source)
    VALUES ('POWERINDIA.NS', '2026-08-07', 45.0, 58.5, 30.0, 'nse')
    """)
    conn.commit()

    catalysts = get_node_recent_catalysts("POWERINDIA.NS", conn, limit=3)
    assert len(catalysts) == 2
    # Verify order win details
    order_cat = next(c for c in catalysts if c["category"] == "ORDER_WIN")
    assert "₹1,200 Cr" in order_cat["title"]
    assert order_cat["impact_score"] == 85
    assert order_cat["order_value_cr"] == 1200.0

    # Verify earnings surprise details
    earn_cat = next(c for c in catalysts if c["category"] == "EARNINGS_BEAT")
    assert earn_cat["impact_score"] >= 80
    assert "30.0%" in earn_cat["title"]


def test_trade_recommendation_trim_circuit_risk():
    node = {
        "node_id": "TARIL.NS",
        "symbol": "TARIL.NS",
        "circuit_status": "HIGH_FREEZE_RISK",
        "distance_to_lower_circuit_pct": 1.2,
        "elasticity_label": "NORMAL",
        "elasticity_ratio": 1.2,
        "institutional_holding_pct": 6.6,
        "change_1d_pct": -4.0,
        "role": "HIGH_BETA_FOLLOWER",
        "anomaly_flag": "NONE",
        "catalysts": [],
    }
    rec = compute_node_trade_recommendation(node)
    assert rec["action"] == "TRIM_CIRCUIT_RISK"
    assert rec["action_color"] == "#ef4444"
    assert "circuit" in rec["rationale"].lower()


def test_trade_recommendation_fade_valuation_trap():
    node = {
        "node_id": "AEROFLEX.NS",
        "symbol": "AEROFLEX.NS",
        "circuit_status": "STABLE",
        "distance_to_lower_circuit_pct": 8.5,
        "elasticity_label": "EXTREME",
        "elasticity_ratio": 3.76,
        "institutional_holding_pct": 1.35,
        "change_1d_pct": 2.0,
        "role": "HIGH_BETA_FOLLOWER",
        "anomaly_flag": "VALUATION_ELASTICITY_TRAP",
        "catalysts": [],
    }
    rec = compute_node_trade_recommendation(node)
    assert rec["action"] == "FADE_VALUATION_TRAP"
    assert rec["action_color"] == "#f59e0b"
    assert "float trap" in rec["key_risk"].lower() or "valuation" in rec["rationale"].lower()


def test_trade_recommendation_strong_buy_dip():
    node = {
        "node_id": "MTARTECH.NS",
        "symbol": "MTARTECH.NS",
        "circuit_status": "STABLE",
        "distance_to_lower_circuit_pct": 4.8,
        "elasticity_label": "DISCOUNTED",
        "elasticity_ratio": 0.56,
        "institutional_holding_pct": 33.7,
        "change_1d_pct": -3.1,
        "role": "INDEPENDENT",
        "anomaly_flag": "NONE",
        "catalysts": [{"category": "ORDER_WIN", "title": "Bags ₹250 Cr SOFC Manifold Order"}],
    }
    rec = compute_node_trade_recommendation(node)
    assert rec["action"] == "STRONG_BUY_DIP"
    assert rec["action_color"] == "#10b981"


def test_trade_recommendation_accumulate_breakout():
    node = {
        "node_id": "POWERINDIA.NS",
        "symbol": "POWERINDIA.NS",
        "circuit_status": "STABLE",
        "distance_to_lower_circuit_pct": 15.0,
        "elasticity_label": "NORMAL",
        "elasticity_ratio": 1.5,
        "institutional_holding_pct": 38.0,
        "change_1d_pct": 4.5,
        "volume_multiple_20d": 2.8,
        "role": "PRIMARY_LEADER",
        "anomaly_flag": "NONE",
        "catalysts": [{"category": "ORDER_WIN", "title": "Mega ₹1,200 Cr Order"}],
    }
    rec = compute_node_trade_recommendation(node)
    assert rec["action"] == "ACCUMULATE_BREAKOUT"
    assert rec["action_color"] == "#059669"


# ============================================================================
# CDMO Basket Tests: GLOBAL_CDMO_PEPTIDE_CASCADE
# ============================================================================

def test_cdmo_topology():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_transmission_db(conn)
    seed_default_transmission_baskets(conn)

    nodes, edges = get_basket_graph_raw("GLOBAL_CDMO_PEPTIDE_CASCADE", conn)
    assert len(nodes) == 16
    assert len(edges) == 16

    node_ids = {n["node_id"] for n in nodes}
    expected_nodes = {
        "LLY", "NVO", "TMO", "DHR", "CRL",
        "DIVISLAB.NS", "SYNGENE.NS", "COHANCE.NS", "LAURUSLABS.NS", "PPLPHARMA.NS",
        "NEULANDLAB.NS", "CONCORDBIO.NS", "BLUEJET.NS", "ACUTAAS.NS", "JUBLPHARMA.NS", "ANURAS.NS"
    }
    assert expected_nodes == node_ids


def test_defense_topology():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_transmission_db(conn)
    seed_default_transmission_baskets(conn)

    nodes, edges = get_basket_graph_raw("DEFENSE_AERO_SUPPLY_CHAIN", conn)
    assert len(nodes) == 14
    assert len(edges) == 13

    node_ids = {n["node_id"] for n in nodes}
    assert "LMT" in node_ids
    assert "BEL.NS" in node_ids
    assert "HAL.NS" in node_ids
    assert "ZENTEC.NS" in node_ids
    assert "DATAPATTNS.NS" in node_ids


def test_semi_topology():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_transmission_db(conn)
    seed_default_transmission_baskets(conn)

    nodes, edges = get_basket_graph_raw("SEMI_OSAT_ADVANCED_PACKAGING", conn)
    assert len(nodes) == 12
    assert len(edges) == 11

    node_ids = {n["node_id"] for n in nodes}
    assert "AMAT" in node_ids
    assert "CGPOWER.NS" in node_ids
    assert "KAYNES.NS" in node_ids
    assert "NETWEB.NS" in node_ids
    assert "RIR.NS" in node_ids


def test_cdmo_gate1_evaluation():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_transmission_db(conn)
    seed_default_transmission_baskets(conn)

    # Insert snapshots for LLY and Tier 1 anchors
    conn.execute(
        "INSERT INTO transmission_snapshots (node_id, current_price, change_1d_pct, change_5d_pct, change_20d_pct) "
        "VALUES ('LLY', 900.0, 1.5, 2.0, 4.2)"
    )
    conn.execute(
        "INSERT INTO transmission_snapshots (node_id, current_price, change_1d_pct, change_5d_pct, change_20d_pct) "
        "VALUES ('NVO', 120.0, 0.5, 1.0, 2.1)"
    )
    conn.execute(
        "INSERT INTO transmission_snapshots (node_id, current_price, change_1d_pct, change_5d_pct, change_20d_pct) "
        "VALUES ('TMO', 550.0, -0.2, 0.5, 1.0)"
    )
    conn.commit()

    payload = get_transmission_graph_payload("GLOBAL_CDMO_PEPTIDE_CASCADE", conn, auto_sync=False)
    assert payload["status"] == "ok"
    gates = payload["reentry_gates"]
    gate1 = gates["us_anchor_stabilization"]
    assert gate1["status"] == "PASS"
    assert "LLY" in gate1["detail"]


def test_sync_transmission_fundamentals_cdmo(monkeypatch):
    from unittest.mock import MagicMock
    import yfinance as yf
    from earnings_engine.data.transmission_radar import sync_transmission_fundamentals

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_transmission_db(conn)
    seed_default_transmission_baskets(conn)

    mock_ticker = MagicMock()
    mock_ticker.info = {
        "trailingPE": 45.2,
        "forwardPE": 38.0,
        "priceToSalesTrailing12Months": 12.5,
        "heldPercentInstitutions": 0.42,
    }
    monkeypatch.setattr(yf, "Ticker", lambda sym: mock_ticker)

    count = sync_transmission_fundamentals(conn, basket_id="GLOBAL_CDMO_PEPTIDE_CASCADE", force=True)
    assert count == 16

    cur = conn.cursor()
    cur.execute("SELECT trailing_pe, forward_pe, institutional_holding_pct FROM transmission_nodes WHERE node_id = 'LLY'")
    row = cur.fetchone()
    assert row[0] == 45.2
    assert row[1] == 38.0
    assert row[2] == 42.0


def test_trade_recommendation_upstream_shock_contagion():
    # Downstream Indian follower with strong pullback but upstream US anchor down -5.0%
    node = {
        "node_id": "MTARTECH.NS",
        "symbol": "MTARTECH.NS",
        "circuit_status": "STABLE",
        "distance_to_lower_circuit_pct": 5.0,
        "elasticity_label": "DISCOUNTED",
        "elasticity_ratio": 0.56,
        "institutional_holding_pct": 33.7,
        "change_1d_pct": -3.1,
        "role": "INDEPENDENT",
        "anomaly_flag": "NONE",
        "catalysts": [],
    }
    # When upstream shock is severe (-5.0%), tactical buy must be overridden to warning
    rec = compute_node_trade_recommendation(node, upstream_shock_pct=-5.0, gate1_status="FAIL")
    assert rec["action"] == "EXPECT_TRANSMISSION_DIP"
    assert rec["action_color"] == "#f97316"
    assert rec["execution_bias"] == "STAND_ASIDE"
    assert "transmission lead-lag window" in rec["rationale"].lower() or "upstream" in rec["rationale"].lower()


def test_graph_payload_upstream_shock_propagation():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_transmission_db(conn)
    seed_default_transmission_baskets(conn)

    # Insert snapshot where anchor BE is down -5.0%
    conn.execute(
        "INSERT INTO transmission_snapshots (node_id, current_price, change_1d_pct, change_5d_pct, change_20d_pct) "
        "VALUES ('BE', 18.0, -5.2, -6.0, -8.0)"
    )
    # Insert snapshot for downstream proxy MTARTECH.NS
    conn.execute(
        "INSERT INTO transmission_snapshots (node_id, current_price, change_1d_pct) "
        "VALUES ('MTARTECH.NS', 1800.0, -2.5)"
    )
    conn.commit()

    payload = get_transmission_graph_payload("AI_INFRA_HARDWARE", conn, auto_sync=False)
    assert payload["status"] == "ok"
    assert payload["reentry_gates"]["us_anchor_stabilization"]["status"] == "FAIL"

    # Verify downstream follower gets EXPECT_TRANSMISSION_DIP instead of naive buy
    mtar_node = next(n for n in payload["nodes"] if n["node_id"] == "MTARTECH.NS")
    assert mtar_node["trade_action"]["action"] == "EXPECT_TRANSMISSION_DIP"
    assert mtar_node["trade_action"]["execution_bias"] == "STAND_ASIDE"






