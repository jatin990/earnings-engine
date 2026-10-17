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
        ("SUVENPHAR.NS", "GLOBAL_CDMO_PEPTIDE_CASCADE", "SUVENPHAR.NS", "Suven Pharma", "NSE", "PRIMARY_LEADER",
         "High-Margin Innovator Commercial CDMO & Global PE Platform", 20.0, None, None, None, 0, 2),
        ("LAURUSLABS.NS", "GLOBAL_CDMO_PEPTIDE_CASCADE", "LAURUSLABS.NS", "Laurus Labs", "NSE", "PRIMARY_LEADER",
         "Large-Scale Chemical CDMO & Precision Microbial Fermentation", None, None, None, None, 0, 2),
        ("PIRAMALPHI.NS", "GLOBAL_CDMO_PEPTIDE_CASCADE", "PIRAMALPHI.NS", "Piramal Pharma", "NSE", "PRIMARY_LEADER",
         "Sterile Injectables, ADCs & US/UK CDMO Facilities", None, None, None, None, 0, 2),

        # Tier 3: Specialized High-Beta Proxies & Pure-Plays (NSE)
        ("NEULANDLAB.NS", "GLOBAL_CDMO_PEPTIDE_CASCADE", "NEULANDLAB.NS", "Neuland Laboratories", "NSE", "HIGH_BETA_FOLLOWER",
         "Pure-Play Commercial Peptide Custom Manufacturing (CMS)", 5.0, None, None, None, 0, 3),
        ("CONCORDBIO.NS", "GLOBAL_CDMO_PEPTIDE_CASCADE", "CONCORDBIO.NS", "Concord Biotech", "NSE", "HIGH_BETA_FOLLOWER",
         "Precision Microbial Fermentation APIs & Immunosuppressants", 20.0, None, None, None, 0, 3),
        ("BLUEJET.NS", "GLOBAL_CDMO_PEPTIDE_CASCADE", "BLUEJET.NS", "Blue Jet Healthcare", "NSE", "HIGH_BETA_FOLLOWER",
         "Contrast Media Intermediates & High-Intensity Sweetener CDMO", 20.0, None, None, None, 0, 3),
        ("AMIORG.NS", "GLOBAL_CDMO_PEPTIDE_CASCADE", "AMIORG.NS", "Ami Organics", "NSE", "HIGH_BETA_FOLLOWER",
         "Advanced Regulatory Intermediates & Multi-Step Organic Synthesis", 10.0, None, None, None, 0, 3),
        ("JUBLPHARMA.NS", "GLOBAL_CDMO_PEPTIDE_CASCADE", "JUBLPHARMA.NS", "Jubilant Pharmova", "NSE", "HIGH_BETA_FOLLOWER",
         "Radiopharma, Sterile Injectables & Allergy Immunotherapy CDMO", 20.0, None, None, None, 0, 3),
        ("ANUPAM.NS", "GLOBAL_CDMO_PEPTIDE_CASCADE", "ANUPAM.NS", "Anupam Rasayan", "NSE", "HIGH_BETA_FOLLOWER",
         "Custom Chemical Synthesis & High-Barrier Fluorination Chemistries", 20.0, None, None, None, 0, 3),
    ]

    for n in cdmo_nodes:
        cur.execute("""
        INSERT OR IGNORE INTO transmission_nodes (
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
        ("TMO_SUVEN", "GLOBAL_CDMO_PEPTIDE_CASCADE", "TMO", "SUVENPHAR.NS",
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
        ("NVO_PIRAMAL", "GLOBAL_CDMO_PEPTIDE_CASCADE", "NVO", "PIRAMALPHI.NS",
         "Sterile Fill-Finish & Injectable Deficit", "Sterile Injectable Vials, Prefilled Syringes & ADC Manufacturing",
         "Novo Nordisk fill-finish supply crunch directs sterile injectable contracts to Piramal Pharma.",
         "CRITICAL", 0, 1.90),
        ("DIVIS_AMIORG", "GLOBAL_CDMO_PEPTIDE_CASCADE", "DIVISLAB.NS", "AMIORG.NS",
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
        ("LAURUS_ANUPAM", "GLOBAL_CDMO_PEPTIDE_CASCADE", "LAURUSLABS.NS", "ANUPAM.NS",
         "Complex Fluorination Reagent Demands", "High-Hazard Fluorination & Niche Agro/Pharma Synthesis",
         "Commercial chemical scaling requires specialized high-barrier fluorination chemistries from Anupam.",
         "MODERATE", 24, 1.40),
        ("SUVEN_AMIORG", "GLOBAL_CDMO_PEPTIDE_CASCADE", "SUVENPHAR.NS", "AMIORG.NS",
         "NCE Intermediate Outsourcing", "New Chemical Entity (NCE) Multi-Step Process Chemistry",
         "Suven innovator pipeline commercialization expands advanced intermediate procurement from Ami Organics.",
         "MODERATE", 24, 1.50),
        ("TMO_PIRAMAL", "GLOBAL_CDMO_PEPTIDE_CASCADE", "TMO", "PIRAMALPHI.NS",
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
        INSERT OR IGNORE INTO transmission_edges (
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
