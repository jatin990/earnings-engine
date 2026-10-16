"""Normalized SQLite schema, seed data, and retention logic for the Transmission Lead-Lag Radar.

Tables:
- transmission_baskets: Thematic baskets (e.g. AI_INFRA_HARDWARE) with Gate 3 persistent status
- transmission_nodes: Entities in the transmission chain (anchors, leaders, satellites)
- transmission_edges: Directed links between entities with catalyst, lag, and elasticity multiplier
- transmission_snapshots: Time-series / dynamic telemetry & anomaly snapshots with retention pruning
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Any

logger = logging.getLogger("earnings_engine.data.transmission_schema")


def init_transmission_db(conn: sqlite3.Connection) -> None:
    """Initialize the 4 normalized transmission tables and supporting indexes."""
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS transmission_baskets (
        basket_id                      VARCHAR(50)  PRIMARY KEY,
        name                           VARCHAR(100) NOT NULL,
        description                    TEXT,
        macro_theme                    TEXT         NOT NULL,
        gate3_cash_conversion_status   VARCHAR(20)  DEFAULT 'PENDING',
        gate3_updated_at               TIMESTAMP,
        gate3_updated_by               VARCHAR(50),
        created_at                     TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
        updated_at                     TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS transmission_nodes (
        node_id                    VARCHAR(50)  PRIMARY KEY,
        basket_id                  VARCHAR(50)  NOT NULL REFERENCES transmission_baskets(basket_id),
        symbol                     VARCHAR(30)  NOT NULL,
        name                       VARCHAR(100) NOT NULL,
        market                     VARCHAR(10)  NOT NULL,
        role                       VARCHAR(30)  NOT NULL,
        product_lineage            TEXT         NOT NULL,
        circuit_band_pct           REAL,
        trailing_pe                REAL,
        forward_pe                 REAL,
        price_to_sales             REAL,
        is_turnaround              INTEGER      NOT NULL DEFAULT 0,
        institutional_holding_pct  REAL,
        tier_column                INTEGER      NOT NULL DEFAULT 1,
        is_active                  INTEGER      DEFAULT 1,
        created_at                 TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
        updated_at                 TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS transmission_edges (
        edge_id                VARCHAR(50)  PRIMARY KEY,
        basket_id              VARCHAR(50)  NOT NULL REFERENCES transmission_baskets(basket_id),
        source_node_id         VARCHAR(50)  NOT NULL REFERENCES transmission_nodes(node_id),
        target_node_id         VARCHAR(50)  NOT NULL REFERENCES transmission_nodes(node_id),
        catalyst_event         VARCHAR(100) NOT NULL,
        physical_bottleneck    TEXT         NOT NULL,
        transmission_mechanism TEXT         NOT NULL,
        impact_level           VARCHAR(20)  NOT NULL,
        lag_window_hours       INTEGER      NOT NULL DEFAULT 0,
        elasticity_multiplier  REAL         DEFAULT 1.0,
        divergence_trigger_rule TEXT,
        created_at             TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
        updated_at             TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS transmission_snapshots (
        snapshot_id                   INTEGER      PRIMARY KEY AUTOINCREMENT,
        node_id                       VARCHAR(50)  NOT NULL REFERENCES transmission_nodes(node_id),
        current_price                 REAL         NOT NULL,
        change_1d_pct                 REAL         NOT NULL,
        change_5d_pct                 REAL,
        change_20d_pct                REAL,
        delivery_pct                  REAL,
        bid_qty_total                 REAL,
        volume_multiple_20d           REAL,
        volume_velocity_ratio         REAL,
        intraday_volume_velocity_flag INTEGER      NOT NULL DEFAULT 0,
        distance_to_lower_circuit_pct REAL,
        circuit_status                VARCHAR(20)  DEFAULT 'NORMAL',
        elasticity_ratio              REAL,
        elasticity_label              VARCHAR(50),
        anomaly_flag                  VARCHAR(50),
        data_mode                     VARCHAR(20)  DEFAULT 'EOD',
        created_at                    TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
    );
    """)

    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_snapshots_node_ts
        ON transmission_snapshots(node_id, created_at DESC);
    """)

    conn.commit()


def prune_old_snapshots(node_id: str, conn: sqlite3.Connection, keep: int = 90) -> None:
    """Delete snapshot rows for node_id older than the keep most recent."""
    cur = conn.cursor()
    cur.execute("""
    DELETE FROM transmission_snapshots
    WHERE node_id = ?
      AND snapshot_id NOT IN (
          SELECT snapshot_id FROM transmission_snapshots
          WHERE node_id = ?
          ORDER BY created_at DESC, snapshot_id DESC
          LIMIT ?
      );
    """, (node_id, node_id, keep))
    conn.commit()


def seed_default_transmission_baskets(conn: sqlite3.Connection) -> None:
    """Seed default AI_INFRA_HARDWARE basket, nodes, and directed edges."""
    cur = conn.cursor()

    # 1. Basket
    cur.execute("""
    INSERT OR IGNORE INTO transmission_baskets (
        basket_id, name, description, macro_theme
    ) VALUES (
        'AI_INFRA_HARDWARE',
        'Indian Hardware & AI Infrastructure Basket',
        'Cross-border transmission from global hyperscaler and AI capex anchors downstream into Indian physical bottleneck suppliers, leaders, and satellite proxies.',
        'Global Hyperscaler Capex -> Optical Cables, SOFC Power & Thermal Hoses'
    );
    """)

    # 2. Nodes (10 nodes per spec §4)
    nodes = [
        # (node_id, basket_id, symbol, name, market, role, product_lineage, circuit_band_pct, trailing_pe, forward_pe, price_to_sales, is_turnaround, tier_column)
        ("BE", "AI_INFRA_HARDWARE", "BE", "Bloom Energy", "US", "GLOBAL_ANCHOR", "Solid Oxide Fuel Cell Hot Boxes & Manifolds", None, 45.0, 32.0, 4.5, 0, 1),
        ("NVDA_CLUSTER", "AI_INFRA_HARDWARE", "NVDA", "Nvidia / CoreWeave Capex", "US", "GLOBAL_ANCHOR", "GPU Parallel Compute & Intra-cluster 64x Optical Density", None, 55.0, 35.0, 22.0, 0, 1),
        ("CIEN", "AI_INFRA_HARDWARE", "CIEN", "Ciena Corp", "US", "GLOBAL_ANCHOR", "Optical Transceiver & Data Center Interconnect Comps", None, 32.0, 24.0, 2.8, 0, 1),
        ("GLW", "AI_INFRA_HARDWARE", "GLW", "Corning Inc", "US", "GLOBAL_ANCHOR", "Global Optical Fiber Glass & Pricing Power", None, 28.0, 20.0, 2.4, 0, 1),
        ("DIXON.NS", "AI_INFRA_HARDWARE", "DIXON.NS", "Dixon Technologies", "NSE", "ORBIT_PEER", "Electronics Manufacturing Services (EMS) Sector Leader", None, 95.0, 65.0, 5.2, 0, 2),
        ("STLTECH.NS", "AI_INFRA_HARDWARE", "STLTECH.NS", "Sterlite Technologies", "NSE", "PRIMARY_LEADER", "Ultra-density Optical Ribbons & Hyperscaler Fiber Exports", None, 112.0, 28.0, 1.2, 1, 2),
        ("HFCL.NS", "AI_INFRA_HARDWARE", "HFCL.NS", "HFCL Ltd", "NSE", "HIGH_BETA_FOLLOWER", "Domestic Telecom Hardware, BharatNet & Optical Sympathy", 10.0, 58.0, 38.0, 2.1, 0, 3),
        ("MTARTECH.NS", "AI_INFRA_HARDWARE", "MTARTECH.NS", "MTAR Technologies", "NSE", "INDEPENDENT", "SOFC Power Hot Boxes, Hydrogen Manifolds & Aerospace Precision", 5.0, 168.0, 72.0, 9.8, 0, 3),
        ("SYRMA.NS", "AI_INFRA_HARDWARE", "SYRMA.NS", "Syrma SGS Technology", "NSE", "ORBIT_PEER", "EMS Box-builds, PCBA Assemblies & Industrial Electronics", 10.0, 88.0, 46.0, 4.2, 0, 3),
        ("AEROFLEX.NS", "AI_INFRA_HARDWARE", "AEROFLEX.NS", "Aeroflex Industries", "NSE", "HIGH_BETA_FOLLOWER", "Secondary Fluid Network (SFN) Stainless Liquid Cooling Hoses", 10.0, 62.0, 40.0, 7.5, 0, 3),
    ]

    for n in nodes:
        cur.execute("""
        INSERT OR IGNORE INTO transmission_nodes (
            node_id, basket_id, symbol, name, market, role, product_lineage,
            circuit_band_pct, trailing_pe, forward_pe, price_to_sales,
            is_turnaround, tier_column
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, n)

    # 3. Directed Edges (8 edges per spec §4)
    edges = [
        # (edge_id, basket_id, src, target, catalyst, bottleneck, mechanism, impact_level, lag_hours, elasticity)
        ("BE_MTAR", "AI_INFRA_HARDWARE", "BE", "MTARTECH.NS",
         "Data Center Power Deficit", "SOFC Hot Boxes & Manifolds",
         "Bloom SOFC export backlog drives direct precision component fabrication at MTAR.",
         "CRITICAL", 0, 3.73),
        ("NVDA_STLTECH", "AI_INFRA_HARDWARE", "NVDA_CLUSTER", "STLTECH.NS",
         "Optical Density 64x Surge", "Intra-cluster Optical Ribbons",
         "GPU cluster scale-out accelerates demand for high-fiber-count hyperscaler interconnects.",
         "CRITICAL", 0, 2.45),
        ("NVDA_AEROFLEX", "AI_INFRA_HARDWARE", "NVDA_CLUSTER", "AEROFLEX.NS",
         "GPU Thermal Dissipation Demand", "SFN Stainless Liquid Cooling Lines",
         "40kW-100kW+ rack liquid cooling shifts procurement toward specialized stainless hose assemblies.",
         "HIGH", 0, 1.80),
        ("CIEN_STLTECH", "AI_INFRA_HARDWARE", "CIEN", "STLTECH.NS",
         "Optical Transceiver Earnings Beat", "Data Center Optical Links",
         "Ciena hardware beats serve as direct leading demand confirmation for fiber suppliers.",
         "HIGH", 0, 1.50),
        ("GLW_STLTECH", "AI_INFRA_HARDWARE", "GLW", "STLTECH.NS",
         "Fiber Pricing / Guide Raise", "Glass Preform & Fiber Margins",
         "Corning fiber price increases expand EBITDA margin expectations for Sterlite Tech.",
         "HIGH", 0, 1.65),
        ("GLW_HFCL", "AI_INFRA_HARDWARE", "GLW", "HFCL.NS",
         "Fiber Pricing / Guide Raise", "Domestic Sympathy Cable Pricing",
         "Global optical benchmark strength spills over into retail optimism on HFCL.",
         "MODERATE", 24, 1.25),
        ("STLTECH_HFCL", "AI_INFRA_HARDWARE", "STLTECH.NS", "HFCL.NS",
         "Optical Lead-Lag Pair", "Domestic Retail Distribution Spillover",
         "Institutional accumulation in STLTECH rotates into high-beta retail participation in HFCL after 1-2 days.",
         "CRITICAL", 24, 1.40),
        ("DIXON_SYRMA", "AI_INFRA_HARDWARE", "DIXON.NS", "SYRMA.NS",
         "EMS Peer Institutional Bid", "EMS / PCBA Sector Multiple Spillover",
         "Institutional momentum in Dixon triggers afternoon sympathy bids in Syrma SGS.",
         "HIGH", 0, 1.20),
    ]

    for e in edges:
        cur.execute("""
        INSERT OR IGNORE INTO transmission_edges (
            edge_id, basket_id, source_node_id, target_node_id, catalyst_event,
            physical_bottleneck, transmission_mechanism, impact_level,
            lag_window_hours, elasticity_multiplier
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, e)

    # 4. Seed initial baseline snapshots so radar operates cleanly immediately
    initial_snapshots = [
        ("BE", 18.42, -4.20, -12.10, -18.5, None, None, 1.15, 1.15, 0, None, "NORMAL", None, "N/A (Anchor)", "NONE", "EOD"),
        ("NVDA_CLUSTER", 135.20, -1.80, -3.40, 4.20, None, None, 1.05, 1.05, 0, None, "NORMAL", None, "N/A (Anchor)", "NONE", "EOD"),
        ("CIEN", 64.50, 1.20, 2.50, 8.10, None, None, 0.95, 0.95, 0, None, "NORMAL", None, "N/A (Anchor)", "NONE", "EOD"),
        ("GLW", 46.20, -0.80, -1.50, 3.80, None, None, 0.90, 0.90, 0, None, "NORMAL", None, "N/A (Anchor)", "NONE", "EOD"),
        ("DIXON.NS", 14850.0, 4.20, 8.50, 14.20, 38.5, 25000, 1.85, 1.85, 0, 18.5, "NORMAL", 2.11, "ELEVATED", "NONE", "EOD"),
        ("STLTECH.NS", 138.20, -1.80, -5.20, -8.10, 22.1, 45000, 1.25, 1.25, 0, 12.4, "NORMAL", None, "N/A (Turnaround)", "NONE", "EOD"),
        ("HFCL.NS", 96.20, 3.40, 7.80, 11.50, 18.4, 65000, 2.45, 2.45, 0, 14.8, "NORMAL", 1.29, "NORMAL", "LEADER_DUMP_FOLLOWER_PUMP", "EOD"),
        ("MTARTECH.NS", 1820.0, -5.00, -14.20, -22.50, 45.2, 0, 0.85, 0.85, 0, 0.0, "CIRCUIT_LOCKED", 3.73, "EXTREME", "CIRCUIT_FREEZE", "EOD"),
        ("SYRMA.NS", 485.0, 1.50, 3.20, 5.40, 32.0, 38000, 1.35, 1.35, 0, 15.2, "NORMAL", 1.95, "ELEVATED", "NONE", "EOD"),
        ("AEROFLEX.NS", 175.50, -2.10, -4.50, 1.20, 26.5, 22000, 1.10, 1.10, 0, 12.0, "NORMAL", 1.38, "NORMAL", "NONE", "EOD"),
    ]

    for s in initial_snapshots:
        cur.execute("""
        INSERT INTO transmission_snapshots (
            node_id, current_price, change_1d_pct, change_5d_pct, change_20d_pct,
            delivery_pct, bid_qty_total, volume_multiple_20d, volume_velocity_ratio,
            intraday_volume_velocity_flag, distance_to_lower_circuit_pct,
            circuit_status, elasticity_ratio, elasticity_label, anomaly_flag, data_mode
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, s)

    conn.commit()


def get_all_baskets(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Return list of all configured transmission baskets with node/edge counts."""
    cur = conn.cursor()
    query = """
    SELECT
        b.basket_id,
        b.name,
        b.description,
        b.macro_theme,
        b.gate3_cash_conversion_status AS gate3_status,
        b.gate3_updated_at,
        b.gate3_updated_by,
        b.created_at,
        b.updated_at,
        (SELECT COUNT(*) FROM transmission_nodes n WHERE n.basket_id = b.basket_id) AS node_count,
        (SELECT COUNT(*) FROM transmission_edges e WHERE e.basket_id = b.basket_id) AS edge_count
    FROM transmission_baskets b
    ORDER BY b.basket_id ASC;
    """
    rows = cur.execute(query).fetchall()
    results = []
    for r in rows:
        if isinstance(r, sqlite3.Row):
            results.append(dict(r))
        else:
            cols = [col[0] for col in cur.description]
            results.append(dict(zip(cols, r)))
    return results


def get_basket_graph_raw(basket_id: str, conn: sqlite3.Connection) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return raw (nodes, edges) lists for a basket from the database."""
    cur = conn.cursor()

    cur.execute("""
    SELECT * FROM transmission_nodes
    WHERE basket_id = ? AND is_active = 1
    ORDER BY tier_column ASC, symbol ASC;
    """, (basket_id,))
    node_rows = cur.fetchall()
    nodes = []
    for r in node_rows:
        if isinstance(r, sqlite3.Row):
            nodes.append(dict(r))
        else:
            cols = [col[0] for col in cur.description]
            nodes.append(dict(zip(cols, r)))

    cur.execute("""
    SELECT * FROM transmission_edges
    WHERE basket_id = ?
    ORDER BY edge_id ASC;
    """, (basket_id,))
    edge_rows = cur.fetchall()
    edges = []
    for r in edge_rows:
        if isinstance(r, sqlite3.Row):
            edges.append(dict(r))
        else:
            cols = [col[0] for col in cur.description]
            edges.append(dict(zip(cols, r)))

    return nodes, edges
