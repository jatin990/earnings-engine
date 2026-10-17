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

    # 2. Nodes (18 nodes across AI Hardware, Power Deficit, Grid Electrification, & Liquid Cooling)
    # Valuations start NULL and are dynamically hydrated from live market fundamentals
    nodes = [
        # (node_id, basket_id, symbol, name, market, role, product_lineage, circuit_band_pct, trailing_pe, forward_pe, price_to_sales, is_turnaround, tier_column)
        ("BE", "AI_INFRA_HARDWARE", "BE", "Bloom Energy", "US", "GLOBAL_ANCHOR", "Solid Oxide Fuel Cell Hot Boxes & Manifolds", None, None, None, None, 0, 1),
        ("NVDA_CLUSTER", "AI_INFRA_HARDWARE", "NVDA", "Nvidia / CoreWeave Capex", "US", "GLOBAL_ANCHOR", "GPU Parallel Compute & Intra-cluster 64x Optical Density", None, None, None, None, 0, 1),
        ("CIEN", "AI_INFRA_HARDWARE", "CIEN", "Ciena Corp", "US", "GLOBAL_ANCHOR", "Optical Transceiver & Data Center Interconnect Comps", None, None, None, None, 0, 1),
        ("GLW", "AI_INFRA_HARDWARE", "GLW", "Corning Inc", "US", "GLOBAL_ANCHOR", "Global Optical Fiber Glass & Pricing Power", None, None, None, None, 0, 1),
        ("VRT", "AI_INFRA_HARDWARE", "VRT", "Vertiv Holdings", "US", "GLOBAL_ANCHOR", "Direct-to-Chip (D2C) Liquid Cooling & Thermal Management", None, None, None, None, 0, 1),
        ("ETN", "AI_INFRA_HARDWARE", "ETN", "Eaton Corp", "US", "GLOBAL_ANCHOR", "Intelligent Power Management & High Voltage Switchgear", None, None, None, None, 0, 1),
        ("GEV", "AI_INFRA_HARDWARE", "GEV", "GE Vernova", "US", "GLOBAL_ANCHOR", "Grid Electrification, Gas Turbines & Transformer Backbone", None, None, None, None, 0, 1),
        ("DIXON.NS", "AI_INFRA_HARDWARE", "DIXON.NS", "Dixon Technologies", "NSE", "ORBIT_PEER", "Electronics Manufacturing Services (EMS) Sector Leader", 20.0, None, None, None, 0, 2),
        ("STLTECH.NS", "AI_INFRA_HARDWARE", "STLTECH.NS", "Sterlite Technologies", "NSE", "PRIMARY_LEADER", "Ultra-density Optical Ribbons & Hyperscaler Fiber Exports", 20.0, None, None, None, 1, 2),
        ("APARINDS.NS", "AI_INFRA_HARDWARE", "APARINDS.NS", "Apar Industries", "NSE", "PRIMARY_LEADER", "World's Largest HTLS Conductor & Heavy Power Cable Exporter", 20.0, None, None, None, 0, 2),
        ("POWERINDIA.NS", "AI_INFRA_HARDWARE", "POWERINDIA.NS", "Hitachi Energy India", "NSE", "PRIMARY_LEADER", "Extra High Voltage (EHV) Transformers & GIS Substations", 20.0, None, None, None, 0, 2),
        ("HFCL.NS", "AI_INFRA_HARDWARE", "HFCL.NS", "HFCL Ltd", "NSE", "HIGH_BETA_FOLLOWER", "Domestic Telecom Hardware, BharatNet & Optical Sympathy", 10.0, None, None, None, 0, 3),
        ("MTARTECH.NS", "AI_INFRA_HARDWARE", "MTARTECH.NS", "MTAR Technologies", "NSE", "INDEPENDENT", "SOFC Power Hot Boxes, Hydrogen Manifolds & Aerospace Precision", 5.0, None, None, None, 0, 3),
        ("SYRMA.NS", "AI_INFRA_HARDWARE", "SYRMA.NS", "Syrma SGS Technology", "NSE", "ORBIT_PEER", "EMS Box-builds, PCBA Assemblies & Industrial Electronics", 10.0, None, None, None, 0, 3),
        ("AEROFLEX.NS", "AI_INFRA_HARDWARE", "AEROFLEX.NS", "Aeroflex Industries", "NSE", "HIGH_BETA_FOLLOWER", "Secondary Fluid Network (SFN) Stainless Liquid Cooling Hoses", 10.0, None, None, None, 0, 3),
        ("VOLTAMP.NS", "AI_INFRA_HARDWARE", "VOLTAMP.NS", "Voltamp Transformers", "NSE", "ORBIT_PEER", "Industrial & Data Center Substation Transformers", 5.0, None, None, None, 0, 3),
        ("TARIL.NS", "AI_INFRA_HARDWARE", "TARIL.NS", "Transformers and Rectifiers (India)", "NSE", "HIGH_BETA_FOLLOWER", "High-Capacity Power & Distribution Transformers", 5.0, None, None, None, 0, 3),
        ("SCHNEIDER.NS", "AI_INFRA_HARDWARE", "SCHNEIDER.NS", "Schneider Electric Infrastructure", "NSE", "HIGH_BETA_FOLLOWER", "Medium Voltage Data Center Distribution & Switchgear", 5.0, None, None, None, 0, 3),
    ]

    for n in nodes:
        cur.execute("""
        INSERT OR IGNORE INTO transmission_nodes (
            node_id, basket_id, symbol, name, market, role, product_lineage,
            circuit_band_pct, trailing_pe, forward_pe, price_to_sales,
            is_turnaround, tier_column
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, n)

    # 3. Directed Edges (17 edges mapping physical bottlenecks and transmission mechanisms)
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
        ("NVDA_VRT", "AI_INFRA_HARDWARE", "NVDA_CLUSTER", "VRT",
         "Rack Power Density >100kW", "Direct-to-Chip Thermal Management",
         "Next-gen Blackwell/Rubin GPU clusters require 100% liquid cooling, locking Vertiv into data center architectures.",
         "CRITICAL", 0, 2.20),
        ("VRT_AEROFLEX", "AI_INFRA_HARDWARE", "VRT", "AEROFLEX.NS",
         "Thermal Rack Liquid Cooling", "Secondary Fluid Lines",
         "40kW-100kW+ rack D2C cooling shifts procurement to specialized stainless hose assemblies.",
         "HIGH", 0, 2.10),
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
        ("ETN_POWERINDIA", "AI_INFRA_HARDWARE", "ETN", "POWERINDIA.NS",
         "High-Voltage Grid Architecture", "EHV Substations & Transformers",
         "Eaton power distribution orders reflect global substation capacity shortages, driving Hitachi Energy India backlog.",
         "CRITICAL", 0, 1.75),
        ("GEV_APARINDS", "AI_INFRA_HARDWARE", "GEV", "APARINDS.NS",
         "Grid Electrification Capex", "HTLS Heavy Transmission Conductors",
         "GE Vernova turbine and grid demand drives heavy export volumes for Apar HTLS reconductoring.",
         "HIGH", 0, 1.60),
        ("ETN_SCHNEIDER", "AI_INFRA_HARDWARE", "ETN", "SCHNEIDER.NS",
         "Switchgear & Substation Demand", "Domestic Switchgear Proxies",
         "Global switchgear backlogs lift domestic medium-voltage infrastructure valuation multiples.",
         "MODERATE", 24, 1.45),
        ("POWERINDIA_VOLTAMP", "AI_INFRA_HARDWARE", "POWERINDIA.NS", "VOLTAMP.NS",
         "Transformer Capacity Spillover", "Industrial Substation Transformers",
         "Lead-time elongation at Tier 1 transformer OEMs diverts industrial buyers to Voltamp.",
         "HIGH", 24, 1.35),
        ("POWERINDIA_TARIL", "AI_INFRA_HARDWARE", "POWERINDIA.NS", "TARIL.NS",
         "EHV Transformer Supply Deficit", "High-Beta Transformer Backlog",
         "Hitachi Energy order book expansion spills over into retail and institutional momentum for Transformers & Rectifiers.",
         "CRITICAL", 24, 1.85),
        ("GEV_POWERINDIA", "AI_INFRA_HARDWARE", "GEV", "POWERINDIA.NS",
         "Global Grid Electrification", "EHV Power Transmission Equipment",
         "Vernova electrification guide raises directly validate Hitachi Energy high-voltage equipment pipeline.",
         "HIGH", 0, 1.50),
        ("BE_POWERINDIA", "AI_INFRA_HARDWARE", "BE", "POWERINDIA.NS",
         "Behind-the-Meter Substation Interconnect", "Substation Interconnect Transformers",
         "Bloom fuel cell microgrids require dedicated step-up transformers and switchgear interconnects.",
         "HIGH", 24, 1.30),
    ]

    for e in edges:
        cur.execute("""
        INSERT OR IGNORE INTO transmission_edges (
            edge_id, basket_id, source_node_id, target_node_id, catalyst_event,
            physical_bottleneck, transmission_mechanism, impact_level,
            lag_window_hours, elasticity_multiplier
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, e)

    # 4. Basket 2: GLOBAL_CDMO_PEPTIDE_CASCADE
    cur.execute("""
    INSERT OR IGNORE INTO transmission_baskets (
        basket_id, name, description, macro_theme
    ) VALUES (
        'GLOBAL_CDMO_PEPTIDE_CASCADE',
        'Global CDMO, Peptide & Biosecure Cascade',
        'Cross-border transmission from US innovator and tools anchors downstream into Indian frontline CDMO leaders and high-beta peptide/fermentation proxies.',
        'GLP-1 Capacity Deficit & US BIOSECURE Act Decoupling'
    );
    """)

    # 5. Nodes for GLOBAL_CDMO_PEPTIDE_CASCADE (16 nodes)
    cdmo_nodes = [
        # Tier 1: Global Innovator Anchors & Tools Titans (US)
        ("LLY", "GLOBAL_CDMO_PEPTIDE_CASCADE", "LLY", "Eli Lilly", "US", "GLOBAL_ANCHOR",
         "Tirzepatide (Mounjaro/Zepbound) GLP-1/GIP Innovator Capex", None, None, None, None, 0, 1),
        ("NVO", "GLOBAL_CDMO_PEPTIDE_CASCADE", "NVO", "Novo Nordisk", "US", "GLOBAL_ANCHOR",
         "Semaglutide (Ozempic/Wegovy) GLP-1 Innovator & Fill-Finish Outsourcing", None, None, None, None, 0, 1),
        ("TMO", "GLOBAL_CDMO_PEPTIDE_CASCADE", "TMO", "Thermo Fisher Scientific", "US", "GLOBAL_ANCHOR",
         "Global Biopharma R&D Funding & Bioprocessing Services Bellwether", None, None, None, None, 0, 1),
        ("DHR", "GLOBAL_CDMO_PEPTIDE_CASCADE", "DHR", "Danaher Corp", "US", "GLOBAL_ANCHOR",
         "Upstream Bioprocess Filtration & Single-Use Chromatography Consumables", None, None, None, None, 0, 1),
        ("CRL", "GLOBAL_CDMO_PEPTIDE_CASCADE", "CRL", "Charles River Laboratories", "US", "GLOBAL_ANCHOR",
         "Early-Stage Drug Discovery & Pre-clinical CRO Pipeline Barometer", None, None, None, None, 0, 1),

        # Tier 2: Indian Frontline CDMO Leaders (NSE)
        ("DIVISLAB.NS", "GLOBAL_CDMO_PEPTIDE_CASCADE", "DIVISLAB.NS", "Divi's Laboratories", "NSE", "PRIMARY_LEADER",
         "Custom Synthesis Titan & Complex Peptide Building Blocks", None, None, None, None, 0, 2),
        ("SYNGENE.NS", "GLOBAL_CDMO_PEPTIDE_CASCADE", "SYNGENE.NS", "Syngene International", "NSE", "PRIMARY_LEADER",
         "Full-Lifecycle Biologics & Discovery CRDMO (WuXi Decoupling Target)", None, None, None, None, 0, 2),
        ("COHANCE.NS", "GLOBAL_CDMO_PEPTIDE_CASCADE", "COHANCE.NS", "Cohance Lifesciences", "NSE", "PRIMARY_LEADER",
         "High-Margin Innovator Commercial CDMO & Global PE Platform (Suven Pharma)", 20.0, None, None, None, 0, 2),
        ("LAURUSLABS.NS", "GLOBAL_CDMO_PEPTIDE_CASCADE", "LAURUSLABS.NS", "Laurus Labs", "NSE", "PRIMARY_LEADER",
         "Large-Scale Chemical CDMO & Precision Microbial Fermentation", None, None, None, None, 0, 2),
        ("PPLPHARMA.NS", "GLOBAL_CDMO_PEPTIDE_CASCADE", "PPLPHARMA.NS", "Piramal Pharma", "NSE", "PRIMARY_LEADER",
         "Sterile Injectables, ADCs & US/UK CDMO Facilities", None, None, None, None, 0, 2),

        # Tier 3: Specialized High-Beta Proxies & Pure-Plays (NSE)
        ("NEULANDLAB.NS", "GLOBAL_CDMO_PEPTIDE_CASCADE", "NEULANDLAB.NS", "Neuland Laboratories", "NSE", "HIGH_BETA_FOLLOWER",
         "Pure-Play Commercial Peptide Custom Manufacturing (CMS)", 5.0, None, None, None, 0, 3),
        ("CONCORDBIO.NS", "GLOBAL_CDMO_PEPTIDE_CASCADE", "CONCORDBIO.NS", "Concord Biotech", "NSE", "HIGH_BETA_FOLLOWER",
         "Precision Microbial Fermentation APIs & Immunosuppressants", 20.0, None, None, None, 0, 3),
        ("BLUEJET.NS", "GLOBAL_CDMO_PEPTIDE_CASCADE", "BLUEJET.NS", "Blue Jet Healthcare", "NSE", "HIGH_BETA_FOLLOWER",
         "Contrast Media Intermediates & High-Intensity Sweetener CDMO", 20.0, None, None, None, 0, 3),
        ("ACUTAAS.NS", "GLOBAL_CDMO_PEPTIDE_CASCADE", "ACUTAAS.NS", "Acutaas Chemicals (Ami)", "NSE", "HIGH_BETA_FOLLOWER",
         "Advanced Regulatory Intermediates & Multi-Step Organic Synthesis", 10.0, None, None, None, 0, 3),
        ("JUBLPHARMA.NS", "GLOBAL_CDMO_PEPTIDE_CASCADE", "JUBLPHARMA.NS", "Jubilant Pharmova", "NSE", "HIGH_BETA_FOLLOWER",
         "Radiopharma, Sterile Injectables & Allergy Immunotherapy CDMO", 20.0, None, None, None, 0, 3),
        ("ANURAS.NS", "GLOBAL_CDMO_PEPTIDE_CASCADE", "ANURAS.NS", "Anupam Rasayan", "NSE", "HIGH_BETA_FOLLOWER",
         "Custom Chemical Synthesis & High-Barrier Fluorination Chemistries", 20.0, None, None, None, 0, 3),
    ]

    # Purge old obsolete symbols from database if previously seeded
    cur.execute("""
    DELETE FROM transmission_nodes
    WHERE node_id IN ('SUVENPHAR.NS', 'PIRAMALPHI.NS', 'AMIORG.NS', 'ANUPAM.NS');
    """)
    cur.execute("""
    DELETE FROM transmission_edges
    WHERE source_node_id IN ('SUVENPHAR.NS', 'PIRAMALPHI.NS', 'AMIORG.NS', 'ANUPAM.NS')
       OR target_node_id IN ('SUVENPHAR.NS', 'PIRAMALPHI.NS', 'AMIORG.NS', 'ANUPAM.NS');
    """)

    for n in cdmo_nodes:
        cur.execute("""
        INSERT OR REPLACE INTO transmission_nodes (
            node_id, basket_id, symbol, name, market, role, product_lineage,
            circuit_band_pct, trailing_pe, forward_pe, price_to_sales,
            is_turnaround, tier_column
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, n)

    # 6. Directed Edges for GLOBAL_CDMO_PEPTIDE_CASCADE (16 edges)
    cdmo_edges = [
        ("LLY_DIVIS", "GLOBAL_CDMO_PEPTIDE_CASCADE", "LLY", "DIVISLAB.NS",
         "GLP-1 Commercial Ramp", "Peptide Building Blocks & Protected Amino Acids Supply",
         "Eli Lilly commercial ramp requires massive peptide building block synthesis and custom flow chemistry from Divi's.",
         "CRITICAL", 0, 1.85),
        ("NVO_NEULAND", "GLOBAL_CDMO_PEPTIDE_CASCADE", "NVO", "NEULANDLAB.NS",
         "Peptide Outsourcing Surge", "Commercial Peptide CMS Production Backlog",
         "Novo Nordisk API capacity deficits drive direct peptide CMS contract allocation to Neuland.",
         "CRITICAL", 0, 2.40),
        ("LLY_NEULAND", "GLOBAL_CDMO_PEPTIDE_CASCADE", "LLY", "NEULANDLAB.NS",
         "GLP-1 High-Beta Pass-Through", "Innovator Custom Manufacturing Spillovers",
         "Lilly demand surges create industry-wide peptide supply deficit, lifting Neuland CMS valuation.",
         "HIGH", 0, 2.10),
        ("TMO_SYNGENE", "GLOBAL_CDMO_PEPTIDE_CASCADE", "TMO", "SYNGENE.NS",
         "BIOSECURE Act WuXi Displacement", "Western Pharma RFP Rotation into Western-Compliant Discovery CRDMO",
         "Thermo Fisher biopharma backlog signals increased RFP rotation out of China into Syngene.",
         "CRITICAL", 24, 1.75),
        ("TMO_SUVEN", "GLOBAL_CDMO_PEPTIDE_CASCADE", "TMO", "COHANCE.NS",
         "Western Innovator Outsourcing", "Innovator Phase II/III Molecule Synthesis & Dedicated Blocks",
         "Global biopharma development funding recovery fuels Suven innovator CDMO commercial pipeline.",
         "HIGH", 24, 1.65),
        ("CRL_SYNGENE", "GLOBAL_CDMO_PEPTIDE_CASCADE", "CRL", "SYNGENE.NS",
         "Early-Stage Biotech R&D Rebound", "Pre-clinical Pipeline Expansion & Dedicated R&D Center Capex",
         "Charles River discovery recovery confirms inflection in early-stage biopharma research spend at Syngene.",
         "MODERATE", 24, 1.40),
        ("DHR_CONCORD", "GLOBAL_CDMO_PEPTIDE_CASCADE", "DHR", "CONCORDBIO.NS",
         "Bioprocess & Fermentation Deficit", "Large-Scale Microbial Fermentation & Downstream Purification",
         "Danaher bioprocess equipment demand reflects global fermentation capacity constraints benefiting Concord.",
         "HIGH", 24, 1.55),
        ("DHR_LAURUS", "GLOBAL_CDMO_PEPTIDE_CASCADE", "DHR", "LAURUSLABS.NS",
         "Fermentation Capacity Reservation", "Precision Microbial Fermentation Scale-up",
         "Bioprocess consumable demand expansion validates Laurus Bio precision fermentation commercialization.",
         "HIGH", 24, 1.60),
        ("NVO_PIRAMAL", "GLOBAL_CDMO_PEPTIDE_CASCADE", "NVO", "PPLPHARMA.NS",
         "Sterile Fill-Finish & Injectable Deficit", "Sterile Injectable Vials, Prefilled Syringes & ADC Manufacturing",
         "Novo Nordisk fill-finish supply crunch directs sterile injectable contracts to Piramal Pharma.",
         "CRITICAL", 0, 1.90),
        ("DIVIS_AMIORG", "GLOBAL_CDMO_PEPTIDE_CASCADE", "DIVISLAB.NS", "ACUTAAS.NS",
         "Commercial Block Intermediate Sourcing", "Advanced Regulatory Intermediates & Multi-Step Chemistry",
         "Divi's commercial block expansions cascade raw intermediate synthesis demand into Ami Organics.",
         "HIGH", 24, 1.45),
        ("DIVIS_BLUEJET", "GLOBAL_CDMO_PEPTIDE_CASCADE", "DIVISLAB.NS", "BLUEJET.NS",
         "Global Innovator Intermediates", "High-Purity Contrast Media Intermediates & Niche Chemical Blocks",
         "Custom synthesis capacity utilization at leaders directs niche intermediate contracts to Blue Jet.",
         "MODERATE", 24, 1.35),
        ("SYNGENE_JUBL", "GLOBAL_CDMO_PEPTIDE_CASCADE", "SYNGENE.NS", "JUBLPHARMA.NS",
         "Sterile Facility Spillover", "US/EU Injectable & Radiopharma Contract Manufacturing",
         "CRDMO capacity tightness across Indian leaders spills over into Jubilant sterile injectables.",
         "MODERATE", 24, 1.30),
        ("LAURUS_ANUPAM", "GLOBAL_CDMO_PEPTIDE_CASCADE", "LAURUSLABS.NS", "ANURAS.NS",
         "Complex Fluorination Reagent Demands", "High-Hazard Fluorination & Niche Agro/Pharma Synthesis",
         "Commercial chemical scaling requires specialized high-barrier fluorination chemistries from Anupam.",
         "MODERATE", 24, 1.40),
        ("SUVEN_AMIORG", "GLOBAL_CDMO_PEPTIDE_CASCADE", "COHANCE.NS", "ACUTAAS.NS",
         "NCE Intermediate Outsourcing", "New Chemical Entity (NCE) Multi-Step Process Chemistry",
         "Suven innovator pipeline commercialization expands advanced intermediate procurement from Ami Organics.",
         "MODERATE", 24, 1.50),
        ("TMO_PIRAMAL", "GLOBAL_CDMO_PEPTIDE_CASCADE", "TMO", "PPLPHARMA.NS",
         "Western Biopharma Services Recovery", "Sterile Fill-Finish & UK/US Clinical Trial Batch Logistics",
         "Thermo Fisher clinical services growth mirrors Piramal Pharma sterile injectables and ADC demand.",
         "HIGH", 24, 1.50),
        ("DIVIS_SYNGENE", "GLOBAL_CDMO_PEPTIDE_CASCADE", "DIVISLAB.NS", "SYNGENE.NS",
         "Indian CDMO Institutional Allocation", "FII/DII Peer Flow Rebalancing across Frontline Pharma Leaders",
         "Institutional inflows into Divi's trigger sympathy reallocation into Syngene discovery platform.",
         "MODERATE", 0, 1.20),
    ]

    for e in cdmo_edges:
        cur.execute("""
        INSERT OR REPLACE INTO transmission_edges (
            edge_id, basket_id, source_node_id, target_node_id, catalyst_event,
            physical_bottleneck, transmission_mechanism, impact_level,
            lag_window_hours, elasticity_multiplier
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, e)

    # ------------------------------------------------------------------------
    # 7. Basket 3: DEFENSE_AERO_SUPPLY_CHAIN
    # ------------------------------------------------------------------------
    cur.execute("""
    INSERT OR IGNORE INTO transmission_baskets (
        basket_id, name, description, macro_theme
    ) VALUES (
        'DEFENSE_AERO_SUPPLY_CHAIN',
        'Defense & Aerospace Electronics / Radar & Drones',
        'Cross-border lead-lag transmission from US defense primes (Lockheed, RTX, Kratos, L3Harris) into Indian defense electronics PSUs, airborne radar systems, and counter-drone specialists.',
        'Indigenization (IDDM), Electronic Warfare, Airborne Radars & Global Defense Replenishment'
    );
    """)

    defense_nodes = [
        # Tier 1: Global Defense Primes & Sensor Titans (US)
        ("LMT", "DEFENSE_AERO_SUPPLY_CHAIN", "LMT", "Lockheed Martin", "US", "GLOBAL_ANCHOR",
         "Fifth-Gen Fighters (F-35), Missile Defense Systems & Global Defense Procurement Bellwether", None, None, None, None, 0, 1),
        ("RTX", "DEFENSE_AERO_SUPPLY_CHAIN", "RTX", "RTX Corp (Raytheon)", "US", "GLOBAL_ANCHOR",
         "Radar Systems, Missile Guidance & Airborne Sensor Payloads", None, None, None, None, 0, 1),
        ("KTOS", "DEFENSE_AERO_SUPPLY_CHAIN", "KTOS", "Kratos Defense", "US", "GLOBAL_ANCHOR",
         "Jet Target Drones, Unmanned Aerial Systems & Counter-UAS Architecture", None, None, None, None, 0, 1),
        ("LHX", "DEFENSE_AERO_SUPPLY_CHAIN", "LHX", "L3Harris Technologies", "US", "GLOBAL_ANCHOR",
         "C4ISR Tactical Radios, Secure Comms & Electronic Warfare", None, None, None, None, 0, 1),

        # Tier 2: Indian Defense Frontline PSUs & System Integrators (NSE)
        ("BEL.NS", "DEFENSE_AERO_SUPPLY_CHAIN", "BEL.NS", "Bharat Electronics", "NSE", "PRIMARY_LEADER",
         "Defense Electronics, Naval Sonar, EW Systems & Akash Missile Radars", None, None, None, None, 0, 2),
        ("HAL.NS", "DEFENSE_AERO_SUPPLY_CHAIN", "HAL.NS", "Hindustan Aeronautics", "NSE", "PRIMARY_LEADER",
         "Tejas Fighter Jets, Light Combat Helicopters (LCH) & Aero Engines", None, None, None, None, 0, 2),
        ("BDL.NS", "DEFENSE_AERO_SUPPLY_CHAIN", "BDL.NS", "Bharat Dynamics", "NSE", "PRIMARY_LEADER",
         "Surface-to-Air / Anti-Tank Guided Missiles (Akash, Astra)", None, None, None, None, 0, 2),
        ("MAZDOCK.NS", "DEFENSE_AERO_SUPPLY_CHAIN", "MAZDOCK.NS", "Mazagon Dock Shipbuilders", "NSE", "PRIMARY_LEADER",
         "Submarines, Stealth Frigates & Heavy Naval Defense Platforms", None, None, None, None, 0, 2),

        # Tier 3: Specialized Indian Satellite Proxies & Drone Pure-Plays (NSE)
        ("DATAPATTNS.NS", "DEFENSE_AERO_SUPPLY_CHAIN", "DATAPATTNS.NS", "Data Patterns", "NSE", "HIGH_BETA_FOLLOWER",
         "Airborne Radars, Electronic Warfare Receivers & Satellite Payloads", 5.0, None, None, None, 0, 3),
        ("PARAS.NS", "DEFENSE_AERO_SUPPLY_CHAIN", "PARAS.NS", "Paras Defence", "NSE", "HIGH_BETA_FOLLOWER",
         "Optics & Optronics for Missiles/Tanks, EMP Racks & Drone Systems", 5.0, None, None, None, 0, 3),
        ("ASTRAMICRO.NS", "DEFENSE_AERO_SUPPLY_CHAIN", "ASTRAMICRO.NS", "Astra Microwave", "NSE", "HIGH_BETA_FOLLOWER",
         "Active Electronically Scanned Array (AESA) Radar Modules & Sub-systems", 5.0, None, None, None, 0, 3),
        ("ZENTEC.NS", "DEFENSE_AERO_SUPPLY_CHAIN", "ZENTEC.NS", "Zen Technologies", "NSE", "HIGH_BETA_FOLLOWER",
         "Combat Simulation Trainers & Anti-Drone / Counter-UAS Systems", 5.0, None, None, None, 0, 3),
        ("DCXINDIA.NS", "DEFENSE_AERO_SUPPLY_CHAIN", "DCXINDIA.NS", "DCX Systems", "NSE", "HIGH_BETA_FOLLOWER",
         "Electronic Sub-systems & Cable Harnesses for Defense Primes", 5.0, None, None, None, 0, 3),
        ("APOLLO.NS", "DEFENSE_AERO_SUPPLY_CHAIN", "APOLLO.NS", "Apollo Micro Systems", "NSE", "HIGH_BETA_FOLLOWER",
         "Ruggedized Weapon Control Systems, Torpedo Tracking & Missile Avionics", 5.0, None, None, None, 0, 3),
    ]

    for n in defense_nodes:
        cur.execute("""
        INSERT OR REPLACE INTO transmission_nodes (
            node_id, basket_id, symbol, name, market, role, product_lineage,
            circuit_band_pct, trailing_pe, forward_pe, price_to_sales,
            is_turnaround, tier_column
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, n)

    defense_edges = [
        ("LMT_BEL", "DEFENSE_AERO_SUPPLY_CHAIN", "LMT", "BEL.NS",
         "Global Defense Procurement", "Tactical Radars & Avionics Offsets",
         "US defense prime order books expand offset obligations to Bharat Electronics.",
         "CRITICAL", 0, 1.65),
        ("RTX_ASTRAMICRO", "DEFENSE_AERO_SUPPLY_CHAIN", "RTX", "ASTRAMICRO.NS",
         "AESA Radar Demand Surge", "Active Phased Array Modules",
         "Raytheon radar backlogs validate high-frequency microwave module volumes at Astra Microwave.",
         "HIGH", 0, 1.95),
        ("RTX_DATAPATTNS", "DEFENSE_AERO_SUPPLY_CHAIN", "RTX", "DATAPATTNS.NS",
         "Airborne EW Suite Demand", "Digital Receiver Units & Radar Processors",
         "Global airborne sensor replenishment drives high-beta multiple expansion in Data Patterns.",
         "CRITICAL", 0, 2.10),
        ("KTOS_ZENTEC", "DEFENSE_AERO_SUPPLY_CHAIN", "KTOS", "ZENTEC.NS",
         "Unmanned Warfare Inflection", "Anti-Drone & Counter-UAS Defense Surge",
         "Kratos unmanned combat momentum reflects drone defense imperative benefiting Zen Technologies.",
         "CRITICAL", 0, 2.25),
        ("LHX_BEL", "DEFENSE_AERO_SUPPLY_CHAIN", "LHX", "BEL.NS",
         "C4ISR Tactical Radios", "Software Defined Radios & Battle Grid",
         "L3Harris tactical radio backlogs spill over into Indian defense communication overhauls.",
         "HIGH", 24, 1.50),
        ("LMT_HAL", "DEFENSE_AERO_SUPPLY_CHAIN", "LMT", "HAL.NS",
         "Fighter Fleet Modernization", "Combat Aircraft Fabrication & Engine Overhaul",
         "Global combat jet procurement cycles re-rate HAL Tejas Mk1A delivery backlog.",
         "HIGH", 0, 1.55),
        ("HAL_DATAPATTNS", "DEFENSE_AERO_SUPPLY_CHAIN", "HAL.NS", "DATAPATTNS.NS",
         "Tejas Mk1A Avionics Integration", "Airborne Radar Processing Subsystems",
         "HAL aircraft execution cascades cockpit display and radar signal processing contracts to Data Patterns.",
         "CRITICAL", 24, 1.85),
        ("BEL_ASTRAMICRO", "DEFENSE_AERO_SUPPLY_CHAIN", "BEL.NS", "ASTRAMICRO.NS",
         "Missile Radar Module Sourcing", "Akash & QRSAM Phased Array Subsystems",
         "BEL order book expansion directly converts into sub-tier RF module orders for Astra Microwave.",
         "HIGH", 24, 1.50),
        ("BDL_APOLLO", "DEFENSE_AERO_SUPPLY_CHAIN", "BDL.NS", "APOLLO.NS",
         "Guided Weapon Control Systems", "Missile Avionics & Actuation Hardware",
         "Bharat Dynamics Akash/Astra missile ramp drives weapon control hardware orders to Apollo Micro.",
         "HIGH", 24, 1.60),
        ("BEL_PARAS", "DEFENSE_AERO_SUPPLY_CHAIN", "BEL.NS", "PARAS.NS",
         "Optronics Subcontracting", "Periscope Assemblies & Armored Vehicle Optronics",
         "BEL naval and land systems integration cascades periscope and optical component contracts to Paras.",
         "MODERATE", 24, 1.45),
        ("LMT_DCX", "DEFENSE_AERO_SUPPLY_CHAIN", "LMT", "DCXINDIA.NS",
         "Foreign Military Sales Offset", "Defense Cable Harness & System Integration",
         "Lockheed FMS export offset commitments generate dedicated sub-assembly awards for DCX.",
         "MODERATE", 24, 1.40),
        ("MAZDOCK_PARAS", "DEFENSE_AERO_SUPPLY_CHAIN", "MAZDOCK.NS", "PARAS.NS",
         "Naval Submarine Optronics", "Periscope Glass & Heavy Naval Optics",
         "Mazagon Dock submarine overhauls require specialized submarine periscope optics from Paras.",
         "MODERATE", 24, 1.35),
        ("BEL_DATAPATTNS", "DEFENSE_AERO_SUPPLY_CHAIN", "BEL.NS", "DATAPATTNS.NS",
         "Radar Collaboration Spillover", "Tactical Radar Signal Processing",
         "BEL radar prime contracts trigger sub-tier processing architecture integration at Data Patterns.",
         "HIGH", 24, 1.60),
    ]

    for e in defense_edges:
        cur.execute("""
        INSERT OR REPLACE INTO transmission_edges (
            edge_id, basket_id, source_node_id, target_node_id, catalyst_event,
            physical_bottleneck, transmission_mechanism, impact_level,
            lag_window_hours, elasticity_multiplier
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, e)

    # ------------------------------------------------------------------------
    # 8. Basket 4: SEMI_OSAT_ADVANCED_PACKAGING
    # ------------------------------------------------------------------------
    cur.execute("""
    INSERT OR IGNORE INTO transmission_baskets (
        basket_id, name, description, macro_theme
    ) VALUES (
        'SEMI_OSAT_ADVANCED_PACKAGING',
        'Semiconductor Packaging (OSAT) & Compound Silicon Carbide',
        'Cross-border lead-lag transmission from global semiconductor equipment and wafer titans (Applied Materials, ASML, Micron, KLA, ON Semi) into Indian OSAT assembly, testing, chip packaging, and compound SiC fabs.',
        'Semiconductor Mission (ISM), OSAT Assembly-Test Packaging & SiC/GaN Power Chips'
    );
    """)

    semi_nodes = [
        # Tier 1: Global Semiconductor Equipment & Memory Anchors (US/Europe)
        ("AMAT", "SEMI_OSAT_ADVANCED_PACKAGING", "AMAT", "Applied Materials", "US", "GLOBAL_ANCHOR",
         "Semiconductor Wafer Fab & Advanced Packaging Equipment Leader", None, None, None, None, 0, 1),
        ("ASML", "SEMI_OSAT_ADVANCED_PACKAGING", "ASML", "ASML Holding", "US", "GLOBAL_ANCHOR",
         "EUV/DUV Photolithography Monopoly & Silicon Expansion Barometer", None, None, None, None, 0, 1),
        ("MU", "SEMI_OSAT_ADVANCED_PACKAGING", "MU", "Micron Technology", "US", "GLOBAL_ANCHOR",
         "Memory Packaging Pioneer & Sanand OSAT Unit Anchor", None, None, None, None, 0, 1),
        ("KLAC", "SEMI_OSAT_ADVANCED_PACKAGING", "KLAC", "KLA Corp", "US", "GLOBAL_ANCHOR",
         "Process Control & Advanced Packaging Yield Inspection Systems", None, None, None, None, 0, 1),
        ("ON", "SEMI_OSAT_ADVANCED_PACKAGING", "ON", "ON Semiconductor", "US", "GLOBAL_ANCHOR",
         "Automotive Silicon Carbide (SiC) & GaN Power Modules", None, None, None, None, 0, 1),

        # Tier 2: Indian Frontline OSAT Titans & Chip Infrastructure (NSE)
        ("CGPOWER.NS", "SEMI_OSAT_ADVANCED_PACKAGING", "CGPOWER.NS", "CG Power", "NSE", "PRIMARY_LEADER",
         "Sanand OSAT Unit Joint Venture with Renesas Electronics & Stars Micro", None, None, None, None, 0, 2),
        ("KAYNES.NS", "SEMI_OSAT_ADVANCED_PACKAGING", "KAYNES.NS", "Kaynes Technology", "NSE", "PRIMARY_LEADER",
         "Sanand OSAT Facility (Kaynes Semicon) & High-Density Multi-Chip Modules", None, None, None, None, 0, 2),
        ("TATAELXSI.NS", "SEMI_OSAT_ADVANCED_PACKAGING", "TATAELXSI.NS", "Tata Elxsi", "NSE", "PRIMARY_LEADER",
         "Semiconductor Chip Design, Verification & Tata Electronics Fab Partner", None, None, None, None, 0, 2),
        ("NETWEB.NS", "SEMI_OSAT_ADVANCED_PACKAGING", "NETWEB.NS", "Netweb Technologies", "NSE", "PRIMARY_LEADER",
         "High-End Computing Solutions, Supercomputing & AI High-Density System Integration", None, None, None, None, 0, 2),

        # Tier 3: Specialized High-Beta Semi Design & Compound SiC Proxies (NSE)
        ("MOSCHIP.NS", "SEMI_OSAT_ADVANCED_PACKAGING", "MOSCHIP.NS", "MosChip Technologies", "NSE", "HIGH_BETA_FOLLOWER",
         "Turnkey ASIC Design, Embedded Systems & Silicon Verification", 5.0, None, None, None, 0, 3),
        ("RIR.NS", "SEMI_OSAT_ADVANCED_PACKAGING", "RIR.NS", "RIR Power Electronics", "NSE", "HIGH_BETA_FOLLOWER",
         "First Commercial Silicon Carbide (SiC) Power Semiconductor Fab in Odisha", 5.0, None, None, None, 0, 3),
        ("TATAINVEST.NS", "SEMI_OSAT_ADVANCED_PACKAGING", "TATAINVEST.NS", "Tata Investment", "NSE", "HIGH_BETA_FOLLOWER",
         "Strategic Holding Company with Direct Equity Exposure to Tata Electronics Fabs", 5.0, None, None, None, 0, 3),
    ]

    for n in semi_nodes:
        cur.execute("""
        INSERT OR REPLACE INTO transmission_nodes (
            node_id, basket_id, symbol, name, market, role, product_lineage,
            circuit_band_pct, trailing_pe, forward_pe, price_to_sales,
            is_turnaround, tier_column
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, n)

    semi_edges = [
        ("MU_KAYNES", "SEMI_OSAT_ADVANCED_PACKAGING", "MU", "KAYNES.NS",
         "Micron Sanand Spillover", "OSAT Multi-Chip Packaging Backlog",
         "Micron Sanand packaging expansion accelerates commercial traction for Kaynes Semicon OSAT unit.",
         "CRITICAL", 0, 2.15),
        ("AMAT_CGPOWER", "SEMI_OSAT_ADVANCED_PACKAGING", "AMAT", "CGPOWER.NS",
         "OSAT Packaging Tool Delivery", "Advanced Assembly & Test Tooling",
         "Applied Materials advanced packaging equipment delivery confirms progress on CG Power-Renesas OSAT.",
         "CRITICAL", 24, 1.85),
        ("ON_RIR", "SEMI_OSAT_ADVANCED_PACKAGING", "ON", "RIR.NS",
         "Automotive SiC Power Deficit", "Commercial Silicon Carbide Power Fab",
         "ON Semi SiC demand surges spill over into institutional re-rating for RIR Power Electronics SiC fab.",
         "CRITICAL", 0, 2.40),
        ("KLAC_MOSCHIP", "SEMI_OSAT_ADVANCED_PACKAGING", "KLAC", "MOSCHIP.NS",
         "Silicon Yield Verification", "Turnkey ASIC Layout & Test Services",
         "KLA process diagnostic momentum validates surging custom ASIC design and verification at MosChip.",
         "HIGH", 24, 1.70),
        ("ASML_TATAELXSI", "SEMI_OSAT_ADVANCED_PACKAGING", "ASML", "TATAELXSI.NS",
         "Global Fab Expansion Capex", "Chip Design & Physical Layout Services",
         "ASML lithography backlog expansion validates upstream engineering design pipelines at Tata Elxsi.",
         "HIGH", 24, 1.50),
        ("MU_CGPOWER", "SEMI_OSAT_ADVANCED_PACKAGING", "MU", "CGPOWER.NS",
         "Sanand Cluster Milestone", "Semiconductor Ecosystem Sentiment",
         "Micron operational milestones validate the Sanand semiconductor cluster, boosting CG Power.",
         "HIGH", 0, 1.75),
        ("KAYNES_MOSCHIP", "SEMI_OSAT_ADVANCED_PACKAGING", "KAYNES.NS", "MOSCHIP.NS",
         "Design-to-Packaging Synergy", "Turnkey Semiconductor Delivery",
         "Kaynes OSAT packaging orders cascade design verification and RTL-to-GDSII work to MosChip.",
         "HIGH", 24, 1.60),
        ("CGPOWER_KAYNES", "SEMI_OSAT_ADVANCED_PACKAGING", "CGPOWER.NS", "KAYNES.NS",
         "Domestic OSAT Multiple Expansion", "Packaging Capacity Scarcity Rebalancing",
         "Institutional momentum in CG Power OSAT re-rates Kaynes Semicon packaging valuation.",
         "HIGH", 0, 1.45),
        ("ASML_TATAINVEST", "SEMI_OSAT_ADVANCED_PACKAGING", "ASML", "TATAINVEST.NS",
         "Tata Dholera Fab Valuation", "Tata Electronics Direct Equity Spillover",
         "Global wafer fab re-rating directly lifts asset value of Tata Investment's equity portfolio.",
         "HIGH", 24, 1.55),
        ("AMAT_KAYNES", "SEMI_OSAT_ADVANCED_PACKAGING", "AMAT", "KAYNES.NS",
         "Substrate & Packaging Equipment", "OSAT Line Installation Capex",
         "Applied Materials tooling confirms Kaynes Semicon equipment delivery timeline.",
         "MODERATE", 24, 1.50),
        ("ON_CGPOWER", "SEMI_OSAT_ADVANCED_PACKAGING", "ON", "CGPOWER.NS",
         "Power Module Packaging", "Automotive Power Semiconductor Assembly",
         "Global automotive power semi demand directs multi-chip module packaging to CG Power Renesas JV.",
         "HIGH", 24, 1.50),
    ]

    for e in semi_edges:
        cur.execute("""
        INSERT OR REPLACE INTO transmission_edges (
            edge_id, basket_id, source_node_id, target_node_id, catalyst_event,
            physical_bottleneck, transmission_mechanism, impact_level,
            lag_window_hours, elasticity_multiplier
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, e)

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
