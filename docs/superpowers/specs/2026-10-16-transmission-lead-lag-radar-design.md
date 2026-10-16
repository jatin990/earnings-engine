# Design Specification: Global Transmission & Market Lead-Lag Radar

- **Date**: 2026-10-16
- **Status**: Approved for Planning & Architecture Review (v3 — Institutional Review Applied)
- **Target Subsystem**:
  - Database: `earnings_engine/data/db.py`, `earnings_engine/data/turso_sync.py` (SYNC_TABLES)
  - Core Engine: `earnings_engine/data/transmission_radar.py`
  - REST API: `earnings_engine/api/routers/transmission.py`, `earnings_engine/api/server.py`
  - Jinja2 Template: `earnings_engine/reports/templates/dashboard/_transmission.html`,
    `earnings_engine/reports/templates/hubs/dashboard/_transmission.html` (must be identical),
    `earnings_engine/reports/templates/dashboard/_sidebar.html`, `_script_tags.html`,
    `earnings_engine/reports/templates/hubs/dashboard/_sidebar.html`, `_script_tags.html`
  - Frontend UI: `earnings_engine/ui/js/modules/transmission_radar.js`
  - Tests: `tests/test_transmission_radar.py`, `tests/test_api_transmission.py`

---

## 1. Executive Summary & Problem Statement

In modern equity markets, price action in mid- and small-cap Indian stocks (e.g. STLTECH, HFCL, MTARTECH, SYRMA, Aeroflex) is rarely self-contained. These companies operate as derivative suppliers, contract manufacturers, and ancillary vendors whose valuation multiples and order-book expectations are tethered to global hyperscaler capex, US technology anchors, and domestic peer momentum.

Existing trading tools treat stocks in isolation. Traders miss critical cross-border transmission chain reactions and fall into three structural traps:

1. **The Valuation Elasticity Trap**: A 5% drop in a US anchor trading at 35x P/E triggers a 15–25% multiple compression in an Indian derivative trading at 100x–165x P/E because hyper-growth expectations are already priced in.
2. **The Circuit Freeze Trap**: While US anchors trade continuously, Indian mid-caps operate under strict 5% or 10% circuit limits. When global sentiment breaks overnight, pre-market sell orders overwhelm order books, locking investors in lower circuits with zero exit liquidity. A stock at its 5% Lower Circuit but with zero bid quantity is fully trapped — the circuit price alone is insufficient confirmation.
3. **Microstructure Lead-Lag & Distribution Divergence**: Institutional accumulation in narrative leaders (e.g., STLTECH) leads lower-priced retail momentum vehicles (e.g., HFCL) by 24–48 hours. When the leader's delivery % collapses while the follower's volume spikes 2x+, it signals a late-stage distribution climax. Delivery % data is only officially published by NSE **after market close** (~18:00 IST); therefore the anomaly flag cannot fire intraday from delivery % alone.

The **Global Transmission & Lead-Lag Radar** provides an interactive, animated "Transmission Web" visual connecting US Anchors → Physical Bottlenecks → Domestic Leaders → Satellite Proxies, combined with quantitative anomaly detection and a strategic re-entry gatekeeper.

---

## 2. Reusable Core Architecture: Normalized Factor Graph

Transmission is modeled as a normalized **Directed Acyclic Graph (DAG)** so any basket (AI Infra Hardware, OSAT / Semiconductors, Green Hydrogen, EV Subsystems, Defense) can be instantiated fully via seed data, with zero code changes.

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│                               THE TRANSMISSION WEB                                   │
├──────────────────────────┬──────────────────────────────┬────────────────────────────┤
│  TIER 1: US ANCHORS      │  TIER 2: DOMESTIC LEADERS    │  TIER 3: SATELLITE PROXIES │
│  (Hyperscalers/IP/OEM)   │  (Narrative & Direct Order)  │  (High-Beta / Sympathy)    │
├──────────────────────────┼──────────────────────────────┼────────────────────────────┤
│ Bloom Energy (BE)        │                              │ MTAR Technologies          │
│ P/E 45x                  │ ────────────────────────────►│ P/E 168x | 5% Band         │
│                          │                              │ Lag: T+0                   │
│ CoreWeave / NVDA / GLW   │ Sterlite Tech (STLTECH)      │ HFCL Ltd                   │
│ Optical Density 64x      │ P/E 112x  (Turnaround range) │ P/E 58x | 10% Band         │
│                          │ ────[1–2 Day Lag]───────────►│ Lag: T+1 to T+2            │
│ CIENA / Corning (GLW)    │ Syrma SGS                    │ Aeroflex Industries        │
│ Optical Comps / Fiber    │ P/E 88x | EMS Peer           │ SFN Liquid Cooling         │
│                          │ ────────────────────────────►│                            │
│ Dixon Technologies       │                              │                            │
│ (ORBIT_PEER trigger)     │ ────────────────────────────►│                            │
└──────────────────────────┴──────────────────────────────┴────────────────────────────┘
```

### 2.1 Static vs. Dynamic Factor Segregation

#### A. Static / Structural Factors (Configured per basket; reviewed quarterly or on earnings)

1. `basket_id`: Unique thematic basket identifier (e.g., `AI_INFRA_HARDWARE`).
2. `node_role`:
   - `GLOBAL_ANCHOR`: US mega-cap or hyperscaler holding primary IP/capex driver.
   - `PRIMARY_LEADER`: Domestic company with direct FII flow and export contracts.
   - `HIGH_BETA_FOLLOWER`: Lower nominal price, retail liquidity vehicle.
   - `ORBIT_PEER`: Moves with a distinct peer sub-group (e.g., Dixon/Kaynes for EMS).
   - `INDEPENDENT`: Grouped by basket narrative but driven by distinct physical contracts (e.g., MTAR on Bloom/ISRO).
3. `physical_bottleneck`: Explicit hardware lineage string (e.g., "Solid Oxide Fuel Cell Hot Boxes", "Intra-cluster Optical Ribbons 64x", "SFN Stainless Liquid Cooling Lines").
4. `circuit_band_pct`: NSE price band — `5.0`, `10.0`, `20.0`, or `NULL` for F&O instruments with no circuit.
5. `capital_structure_risk`: `LOW | MODERATE | HIGH` — rated from D/E ratio + fixed depreciation/finance obligations.
6. `anchor_pe_baseline`: Reference trailing P/E of the global anchor at basket creation time.
7. `is_turnaround`: Boolean — marks nodes whose trailing P/E is unreliable due to single-quarter profitability (e.g., STLTECH at 112x after a turnaround year). When `true`, valuation elasticity falls back to Price/Sales or Forward P/E (if seeded).

#### B. Dynamic / Real-Time Factors (Calculated on EOD sync + live price cache)

1. **`anchor_overnight_delta`**: 1-day, 5-day, and 20-day return % of the US anchor (e.g., BE, NVDA) — sourced from `prices.sqlite3` / live Yahoo Finance API. `change_20d_pct` stored in `transmission_snapshots` and used for Re-entry Gate 1 evaluation.

2. **`valuation_elasticity_ratio`**:
   $$\text{Elasticity Ratio} = \frac{\text{Proxy Trailing P/E}}{\text{Anchor Trailing P/E}}$$
   - Safe handling: If either P/E is `<= 0` or `NULL`, skip raw P/E ratio and annotate `is_turnaround: true`. Use Forward P/E or P/Sales if seeded; otherwise set `elasticity_ratio: null`, `elasticity_label: "N/A (Turnaround)"`.
   - Thresholds: `< 1.5×` → Normal; `1.5–2.5×` → Elevated; `> 2.5×` → **Extreme Vulnerability (Trap Triggered)**.

3. **`volume_delivery_divergence`** — dual-mode, reflecting NSE publication constraints:

   | Mode | Available | Trigger Condition | Flag |
   |------|-----------|-------------------|------|
   | **Intraday** | 09:15–15:30 IST | Leader volume velocity `>2.5×` 20D avg AND leader price slips below VWAP on declining tick volume | `INTRADAY_MOMENTUM_ROLLOVER` |
   | **EOD** (confirmed) | After 18:00 IST | Leader delivery % `< 25%` AND follower volume `> 2.0×` 20D avg | `LEADER_DUMP_FOLLOWER_PUMP` |

   Both flags are surfaced on the UI with distinct badge colours and the timestamp of the delivery data source. The actual `volume_velocity_ratio` (float) is stored alongside the binary flag to capture signal magnitude.

4. **`circuit_proximity`**:
   $$\text{Distance to LC} = \frac{\text{Current Price} - \text{Lower Circuit Limit}}{\text{Current Price}} \times 100\%$$
   - `CIRCUIT_LOCKED`: `distance <= 0.05%` **AND** `bid_qty_total == 0` (order-book depth confirms zero buyers).
   - `HIGH_FREEZE_RISK`: `distance < 2.0%` OR circuit hit once in the last 5 sessions.
   - `STABLE`: `distance > 5.0%` with balanced two-way order book.

5. **`shockwave_impact`** — computed on demand (not stored) when the user triggers a shockwave from any node:
   $$\text{Target Shock\%} = \text{Anchor Shock\%} \times \text{Edge.elasticity\_multiplier} \times \text{Decay}^{\lfloor \text{lag\_hours} / 24 \rfloor}$$
   - `Decay = 0.85` per day of lag. Propagated BFS across the DAG.
   - Input bounded: `anchor_shock_pct` must be in `[-50.0, +50.0]`; values outside this range return HTTP 422.

6. **`reentry_readiness_score`** (0–100%): Composite of three gates with equal weight (~33% each):
   - Gate 1: US anchor `change_5d_pct >= 0%` and `change_20d_pct >= -5%` (stabilizing bottom). Both sourced from `transmission_snapshots.change_5d_pct` and `transmission_snapshots.change_20d_pct`.
   - Gate 2: Satellite circuit status `== 'STABLE'` for ≥ 3 consecutive trading sessions.
   - Gate 3: Q2 billed cash conversion — persisted in `transmission_baskets.gate3_cash_conversion_status` (`PENDING | PASS | FAIL`). Updated via `PATCH /api/transmission/baskets/{basket_id}/gate3`. Defaults to `PENDING`.

7. **`data_freshness`**: Every `transmission_snapshots` row has a `created_at` timestamp. The API surfaces `snapshot_as_of_utc` and `snapshot_age_minutes` on every node in the graph response. A top-level `data_freshness` block reports `oldest_snapshot_minutes` and `has_stale_nodes` (stale = > 30 minutes during trading hours, > 12 hours overnight). The UI renders a staleness badge on any node exceeding the stale threshold.

---

## 3. Normalized Database Schema (SQLite + Turso Bidirectional Sync)

Four normalized tables registered in `SYNC_TABLES` in `earnings_engine/data/turso_sync.py`:

```sql
-- 1. Baskets
CREATE TABLE IF NOT EXISTS transmission_baskets (
    basket_id                      VARCHAR(50)  PRIMARY KEY,
    name                           VARCHAR(100) NOT NULL,
    description                    TEXT,
    macro_theme                    TEXT         NOT NULL,
    gate3_cash_conversion_status   VARCHAR(20)  DEFAULT 'PENDING', -- 'PENDING' | 'PASS' | 'FAIL'
    gate3_updated_at               TIMESTAMP,
    gate3_updated_by               VARCHAR(50),
    created_at                     TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    updated_at                     TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
);

-- 2. Nodes (one row per entity: US anchor, domestic leader, or satellite proxy)
CREATE TABLE IF NOT EXISTS transmission_nodes (
    node_id                    VARCHAR(50)  PRIMARY KEY,
    basket_id                  VARCHAR(50)  NOT NULL REFERENCES transmission_baskets(basket_id),
    symbol                     VARCHAR(30)  NOT NULL,
    name                       VARCHAR(100) NOT NULL,
    market                     VARCHAR(10)  NOT NULL, -- 'US' | 'NSE'
    role                       VARCHAR(30)  NOT NULL, -- 'GLOBAL_ANCHOR' | 'PRIMARY_LEADER' | 'HIGH_BETA_FOLLOWER' | 'ORBIT_PEER' | 'INDEPENDENT'
    product_lineage            TEXT         NOT NULL,
    circuit_band_pct           REAL,                  -- NULL for F&O; 5.0 / 10.0 / 20.0 for cash equities
    trailing_pe                REAL,
    forward_pe                 REAL,                  -- fallback for turnaround stocks
    price_to_sales             REAL,                  -- secondary fallback
    is_turnaround              INTEGER      NOT NULL DEFAULT 0, -- 1 = turnaround, use forward_pe / price_to_sales
    institutional_holding_pct  REAL,
    tier_column                INTEGER      NOT NULL DEFAULT 1, -- 1: Anchor | 2: Leader | 3: Satellite
    is_active                  INTEGER      DEFAULT 1,
    created_at                 TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    updated_at                 TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
);

-- 3. Directed Transmission Edges
CREATE TABLE IF NOT EXISTS transmission_edges (
    edge_id                VARCHAR(50)  PRIMARY KEY,
    basket_id              VARCHAR(50)  NOT NULL REFERENCES transmission_baskets(basket_id),
    source_node_id         VARCHAR(50)  NOT NULL REFERENCES transmission_nodes(node_id),
    target_node_id         VARCHAR(50)  NOT NULL REFERENCES transmission_nodes(node_id),
    catalyst_event         VARCHAR(100) NOT NULL,
    physical_bottleneck    TEXT         NOT NULL,
    transmission_mechanism TEXT         NOT NULL,
    impact_level           VARCHAR(20)  NOT NULL, -- 'CRITICAL' | 'HIGH' | 'MODERATE' | 'LOW'
    lag_window_hours       INTEGER      NOT NULL DEFAULT 0, -- 0 = same-session; 24 = next day; 48 = 2-day
    elasticity_multiplier  REAL         DEFAULT 1.0,
    divergence_trigger_rule TEXT,
    created_at             TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    updated_at             TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
);

-- 4. EOD Dynamic Telemetry & Anomaly Snapshots (append-only; last 90 sessions retained)
CREATE TABLE IF NOT EXISTS transmission_snapshots (
    snapshot_id                   INTEGER      PRIMARY KEY AUTOINCREMENT,
    node_id                       VARCHAR(50)  NOT NULL REFERENCES transmission_nodes(node_id),
    -- delivery_pct is NULL during intraday (NSE publishes only post-close ~18:00 IST)
    current_price                 REAL         NOT NULL,
    change_1d_pct                 REAL         NOT NULL,
    change_5d_pct                 REAL,
    change_20d_pct                REAL,          -- required for Re-entry Gate 1; computed from price bars if not in snapshot
    delivery_pct                  REAL,          -- NULL when snapshot is intraday
    bid_qty_total                 REAL,          -- top-5 bid depth sum; NULL if not available
    volume_multiple_20d           REAL,
    volume_velocity_ratio         REAL,          -- actual vol_velocity value that triggered/did-not-trigger flag; preserves magnitude
    intraday_volume_velocity_flag INTEGER      NOT NULL DEFAULT 0, -- 1 = INTRADAY_MOMENTUM_ROLLOVER fired
    distance_to_lower_circuit_pct REAL,
    circuit_status                VARCHAR(20)  DEFAULT 'NORMAL', -- 'NORMAL' | 'NEAR_CIRCUIT' | 'HIGH_FREEZE_RISK' | 'CIRCUIT_LOCKED'
    elasticity_ratio              REAL,          -- NULL if turnaround / zero P/E
    elasticity_label              VARCHAR(50),   -- 'NORMAL' | 'ELEVATED' | 'EXTREME' | 'N/A (Turnaround)'
    anomaly_flag                  VARCHAR(50),   -- 'NONE' | 'INTRADAY_MOMENTUM_ROLLOVER' | 'LEADER_DUMP_FOLLOWER_PUMP' | 'VALUATION_SQUEEZE' | 'CIRCUIT_FREEZE'
    data_mode                     VARCHAR(20)  DEFAULT 'EOD', -- 'INTRADAY' | 'EOD'
    created_at                    TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
);

-- Performance index for the node drawer's last-10-snapshots query and retention cleanup
CREATE INDEX IF NOT EXISTS idx_snapshots_node_ts
    ON transmission_snapshots(node_id, created_at DESC);
```

**Snapshot Retention Policy**: On each EOD sync, after inserting new snapshots, prune rows older than the 90 most recent per node:
```sql
DELETE FROM transmission_snapshots
WHERE snapshot_id NOT IN (
    SELECT snapshot_id FROM transmission_snapshots
    WHERE node_id = ?
    ORDER BY created_at DESC
    LIMIT 90
);
```
Run per-node in a loop inside `init_transmission_db` / the EOD sync routine.

**Turso Sync Conventions** (from `CLAUDE.md` & `turso_sync.py`):
- All four tables added to `SYNC_TABLES`.
- Watermark columns by table:
  - `transmission_baskets`: `updated_at` → `WATERMARK_CANDIDATE_COLUMNS`
  - `transmission_nodes`: `updated_at` → `WATERMARK_CANDIDATE_COLUMNS`
  - `transmission_edges`: `updated_at` → `WATERMARK_CANDIDATE_COLUMNS`
  - `transmission_snapshots`: `created_at` → `WATERMARK_CANDIDATE_COLUMNS` (append-only; no `updated_at`)
- All timestamps are full `TIMESTAMP` format (not `DATE_ONLY_COLUMNS`).
- All inserts use `INSERT OR IGNORE` / `INSERT OR REPLACE` to guarantee idempotency during bidirectional sync.
- All Turso remote calls wrapped with a local SQLite fallback.

---

## 4. Seed Data: `AI_INFRA_HARDWARE` Basket

The default basket seeds **10 nodes** and **8 edges** covering the full supply-chain topology from both source documents:

### Nodes (10)
| node_id | symbol | market | role | tier | is_turnaround | circuit_band_pct | Physical driver |
|---------|--------|--------|------|------|---------------|-----------------|-----------------|
| `BE` | BE | US | GLOBAL_ANCHOR | 1 | 0 | NULL | SOFC data-center power |
| `NVDA_CLUSTER` | NVDA | US | GLOBAL_ANCHOR | 1 | 0 | NULL | GPU compute / optical density |
| `CIEN` | CIEN | US | GLOBAL_ANCHOR | 1 | 0 | NULL | Optical transceiver comps |
| `GLW` | GLW | US | GLOBAL_ANCHOR | 1 | 0 | NULL | Fiber pricing / glass supply |
| `DIXON.NS` | DIXON.NS | NSE | ORBIT_PEER | 2 | 0 | NULL | EMS peer breakout signal |
| `STLTECH.NS` | STLTECH.NS | NSE | PRIMARY_LEADER | 2 | 1 | NULL | Ultra-density optical cables |
| `HFCL.NS` | HFCL.NS | NSE | HIGH_BETA_FOLLOWER | 3 | 0 | 10.0 | Hyperscaler cable exports |
| `MTARTECH.NS` | MTARTECH.NS | NSE | INDEPENDENT | 3 | 0 | 5.0 | SOFC hot boxes & manifolds |
| `SYRMA.NS` | SYRMA.NS | NSE | ORBIT_PEER | 3 | 0 | 10.0 | EMS box-builds & PCBA |
| `AEROFLEX.NS` | AEROFLEX.NS | NSE | HIGH_BETA_FOLLOWER | 3 | 0 | 10.0 | SFN liquid cooling hoses |

### Edges (8)
| edge_id | source → target | catalyst_event | impact_level | lag_hours |
|---------|-----------------|----------------|--------------|-----------|
| `BE_MTAR` | BE → MTARTECH.NS | Data Center Power Deficit | CRITICAL | 0 |
| `NVDA_STLTECH` | NVDA_CLUSTER → STLTECH.NS | Optical Density 64x Surge | CRITICAL | 0 |
| `NVDA_AEROFLEX` | NVDA_CLUSTER → AEROFLEX.NS | GPU Thermal Dissipation Demand | HIGH | 0 |
| `CIEN_STLTECH` | CIEN → STLTECH.NS | Optical Transceiver Earnings Beat | HIGH | 0 |
| `GLW_STLTECH` | GLW → STLTECH.NS | Fiber Pricing / Guide Raise | HIGH | 0 |
| `GLW_HFCL` | GLW → HFCL.NS | Fiber Pricing / Guide Raise | MODERATE | 24 |
| `STLTECH_HFCL` | STLTECH.NS → HFCL.NS | Optical Lead-Lag Pair | CRITICAL | 24–48 |
| `DIXON_SYRMA` | DIXON.NS → SYRMA.NS | EMS Peer Institutional Bid | HIGH | 0–4 |

---

## 5. REST API Contract

Mounted under `/api/transmission` **before** any parameterized routes in `earnings_engine/api/server.py` (per FastAPI static-before-parameterized rule):

### `GET /api/transmission/baskets`
Returns available transmission baskets with node/edge counts.

**Response shape:**
```json
{
  "baskets": [
    {
      "basket_id": "AI_INFRA_HARDWARE",
      "name": "Indian Hardware & AI Infrastructure Basket",
      "macro_theme": "Global Hyperscaler Capex → Optical Cables, SOFC Power & Thermal Hoses",
      "node_count": 10,
      "edge_count": 8,
      "gate3_status": "PENDING",
      "gate3_updated_at": null
    }
  ]
}
```

### `GET /api/transmission/graph?basket_id=AI_INFRA_HARDWARE`
Returns full DAG topology with real-time metrics, edge statuses, active anomaly list, re-entry gate statuses, and **data freshness metadata**.

**Response shape:**
```json
{
  "basket": { "basket_id": "AI_INFRA_HARDWARE", "name": "...", "status": "ACTIVE" },
  "data_freshness": {
    "oldest_snapshot_minutes": 43,
    "has_stale_nodes": true,
    "stale_threshold_minutes": 30
  },
  "nodes": [
    {
      "node_id": "BE",
      "symbol": "BE",
      "name": "Bloom Energy",
      "market": "US",
      "role": "GLOBAL_ANCHOR",
      "tier": 1,
      "price": 18.42,
      "change_1d_pct": -4.20,
      "change_5d_pct": -12.10,
      "change_20d_pct": -18.5,
      "trailing_pe": 45.0,
      "is_turnaround": false,
      "elasticity_ratio": null,
      "snapshot_as_of_utc": "2026-10-16T06:47:00Z",
      "snapshot_age_minutes": 43,
      "is_stale": true,
      "status": "BEARISH_PULLBACK"
    },
    {
      "node_id": "MTARTECH.NS",
      "symbol": "MTARTECH.NS",
      "name": "MTAR Technologies",
      "market": "NSE",
      "role": "INDEPENDENT",
      "tier": 3,
      "price": 1820.00,
      "change_1d_pct": -5.00,
      "trailing_pe": 168.0,
      "is_turnaround": false,
      "circuit_band_pct": 5.0,
      "bid_qty_total": 0,
      "distance_to_lower_circuit_pct": 0.0,
      "circuit_status": "CIRCUIT_LOCKED",
      "elasticity_ratio": 3.73,
      "elasticity_label": "EXTREME",
      "anomaly_flag": "CIRCUIT_FREEZE",
      "data_mode": "EOD",
      "snapshot_as_of_utc": "2026-10-16T12:31:00Z",
      "snapshot_age_minutes": 2,
      "is_stale": false
    }
  ],
  "edges": [
    {
      "edge_id": "BE_MTAR",
      "source": "BE",
      "target": "MTARTECH.NS",
      "catalyst": "Data Center Power Deficit",
      "physical_bottleneck": "SOFC Hot Boxes & Manifolds",
      "impact_level": "CRITICAL",
      "lag_hours": 0,
      "elasticity": 3.73,
      "pulse_active": true,
      "pulse_color": "#e53e3e",
      "pulse_direction": "source_to_target"
    }
  ],
  "anomalies": [
    {
      "type": "LEADER_DUMP_FOLLOWER_PUMP",
      "severity": "CRITICAL",
      "source": "STLTECH.NS",
      "target": "HFCL.NS",
      "data_mode": "EOD",
      "data_timestamp": "2026-10-16T18:14:00+05:30",
      "title": "EOD Delivery Divergence — STLTECH 22.1% vs HFCL 2.45× Volume",
      "description": "Institutional distribution pass-off confirmed by NSE EOD delivery data."
    },
    {
      "type": "VALUATION_ELASTICITY_TRAP",
      "severity": "SEVERE",
      "source": "BE",
      "target": "MTARTECH.NS",
      "title": "Extreme 3.73× Multiple Spread",
      "description": "Anchor BE at 45× P/E vs MTAR at 168× P/E. A 5% anchor move compresses MTAR ~18% under current multiple regime."
    }
  ],
  "reentry_gates": {
    "us_anchor_stabilization": { "status": "FAIL", "detail": "BE down -12.1% 5D; -18.5% 20D." },
    "circuit_liquidity_unlocked": { "status": "FAIL", "detail": "MTAR locked in 5% Lower Circuit, bid_qty=0." },
    "q2_cash_conversion": { "status": "PENDING", "detail": "Awaiting Q2 billed export cash flow prints.", "updated_at": null, "updated_by": null }
  }
}
```

### `POST /api/transmission/simulate-shockwave`
On-demand, stateless computation — does **not** write to DB.

**Request body:**
```json
{ "basket_id": "AI_INFRA_HARDWARE", "origin_node_id": "BE", "anchor_shock_pct": -5.0 }
```

**Validation:** `anchor_shock_pct` must be in `[-50.0, +50.0]`. Values outside this range return HTTP 422.

**Response shape:** list of `{ node_id, simulated_shock_pct, lag_days, propagation_order }` for every downstream node, computed via BFS with the decay formula:
$$\text{Target Shock\%} = \text{Anchor Shock\%} \times \text{Edge.elasticity\_multiplier} \times 0.85^{\lfloor \text{lag\_hours} / 24 \rfloor}$$

### `PATCH /api/transmission/baskets/{basket_id}/gate3`
Persist manual Gate 3 toggle. Body: `{ "status": "PASS" | "FAIL" | "PENDING", "updated_by": str }`. Updates `transmission_baskets.gate3_cash_conversion_status`, `gate3_updated_at`, `gate3_updated_by`. Returns 200 with updated basket row; 404 if basket not found; 422 if status value invalid.

---

## 6. UI Screen Architecture: "The Transmission Web"

```
┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│ NEXUS TRANSMISSION RADAR  |  Basket: [ AI Infra & Hardware ▼ ]    [⚡ Trigger Shockwave]  [⟳]  │
├─────────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                                 │
│  TIER 1: US ANCHORS          TIER 2: PHYSICAL / DOMESTIC           TIER 3: SATELLITE PROXIES   │
│                                                                                                 │
│  ┌────────────────────┐       ┌──────────────────────┐       ┌────────────────────────────┐    │
│  │  Bloom Energy (BE) │━━━━━━►│ Power Deficit: SOFC  │━━━━━━►│ MTARTECH  ₹1,820  -5% 🔴  │    │
│  │  $18.42  -4.2%  ▼  │─pulse─│ Hot Boxes & Manifold │─shock─│ 5% LC — bid_qty: 0 FROZEN  │    │
│  │  ⏱ 43 min ago  ⚠️  │       └──────────────────────┘       └────────────────────────────┘    │
│  └────────────────────┘                                                                         │
│            │                                                                                    │
│            ▼ (multi-link)                                                                       │
│  ┌────────────────────┐       ┌──────────────────────┐       ┌────────────────────────────┐    │
│  │ CoreWeave / NVDA   │━━━━━━►│ Optical 64× Density  │━━━━━━►│ STLTECH  ₹138  -1.8%       │    │
│  │ Hyperscaler Capex  │       │ Intra-cluster Fiber  │       │ Delivery: 22% ⚠️ DUMPING   │    │
│  └────────────────────┘       └──────────────────────┘       └──────────┬─────────────────┘    │
│                                                                 [1–2d Lag]                      │
│                                                                          ▼                      │
│  ┌────────────────────┐       ┌──────────────────────┐       ┌────────────────────────────┐    │
│  │ Dixon Technologies │━━━━━━►│ EMS / PCBA Assembly  │━━━━━━►│ HFCL  ₹96.20  +3.4%        │    │
│  │ ₹14,800  +4.2% ▲   │       │ Spillover Momentum   │       │ Vol: 2.45× avg  ⚠️ RETAIL  │    │
│  └────────────────────┘       └──────────────────────┘       └────────────────────────────┘    │
│                                                                                                 │
├─────────────────────────────────────────────────────────────────────────────────────────────────┤
│ ANOMALY TICKER  ⚠️ HFCL: Retail Momentum Trap (EOD Confirmed)  🛑 MTAR: Circuit Freeze          │
│                 📊 SYRMA: EMS Peer Spread Open  🟡 STLTECH: Distribution Rollover               │
├─────────────────────────────────────────────────────────────────────────────────────────────────┤
│ RE-ENTRY GATES  Gate 1: US Anchor Floor [❌ FAIL]  Gate 2: Circuit Unlock [❌ FAIL]             │
│                 Gate 3: Q2 Cash Conversion [⏳ PENDING]  [✏️ Update Gate 3]                      │
└─────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### Visual Engine Design Rules

1. **Layer Architecture (z-stacking)**:
   - **Layer 0 — Static HTML/DOM**: Node cards (ticker chip, price, change badge, anomaly icon, staleness badge). DOM elements give crisp text rendering, accessibility, and hover states at essentially zero GPU cost.
   - **Layer 1 — Canvas (positioned absolutely, pointer-events: none)**: Bezier transmission lines + particle pulses. Canvas sits behind DOM cards.

2. **Bezier Transmission Lines**: Cubic Bezier (`ctx.bezierCurveTo`) connecting the right edge of source node to the left edge of target node. Line stroke color encodes `impact_level`: `CRITICAL` = #e53e3e, `HIGH` = #ed8936, `MODERATE` = #ecc94b, `LOW` = #48bb78.

3. **Particle Flow Animation**:
   - Each active edge spawns particles that travel along the Bezier path at a speed inversely proportional to `lag_window_hours` (instant for 0h, slowest for 48h).
   - Particle count per edge capped at **8**; total canvas particle budget **≤ 40 across all edges**. Excess is silently skipped to maintain 60fps.
   - `requestAnimationFrame` loop paused via `document.addEventListener('visibilitychange')` when tab is hidden and via `IntersectionObserver` when the panel is scrolled off-screen.

4. **Shockwave Simulation**:
   - On button click, triggers a BFS traversal server-side (`POST /api/transmission/simulate-shockwave`) returning per-node shock %.
   - Visually: each node card flashes from its normal colour → red glow → settles at a darkened tint proportional to `simulated_shock_pct`. Flash fires with a delay equal to `lag_days × 600ms` to convey the sequential downstream cascade.
   - Bezier lines pulse with an expanding ripple animation during shockwave propagation.

5. **Staleness Badge**: Any node with `is_stale: true` shows a small amber `⏱ Xm ago` chip in the node card. The global `data_freshness.has_stale_nodes` flag shows a banner at the top of the panel.

6. **Interactive Node Drawer**: Clicking any node card opens a right-side drawer showing: P/E (trailing + forward where available), `is_turnaround` badge, `volume_velocity_ratio`, delivery % (with EOD-only caveat label), circuit proximity bar, `snapshot_as_of_utc` and age, historical anomaly log (last 10 snapshots from `idx_snapshots_node_ts`), and transmission edges in/out.

7. **Gate 3 Toggle**: A small "✏️ Update Gate 3" button in the re-entry gates section opens a modal to set status to `PASS / FAIL / PENDING` (calls `PATCH /api/transmission/baskets/{basket_id}/gate3`). Shows who last updated it and when.

8. **Basket Switcher**: Changing baskets calls `GET /api/transmission/baskets`, then `GET /api/transmission/graph?basket_id=...`. All running `requestAnimationFrame` loops and particle state are torn down (`cancelAnimationFrame`) before re-initialising for the new basket.

9. **Template Mirroring**: `earnings_engine/reports/templates/dashboard/_transmission.html` and `earnings_engine/reports/templates/hubs/dashboard/_transmission.html` must remain **identical**. Verify with `diff`; zero output required.

---

## 7. Testing Strategy

| Test | File | What it pins |
|------|------|-------------|
| `test_schema_init_and_seed` | `test_transmission_radar.py` | Tables created; default basket seeded with ≥10 nodes, ≥8 edges |
| `test_snapshot_retention` | `test_transmission_radar.py` | After inserting 95 snapshots for one node, only 90 remain |
| `test_snapshot_index_exists` | `test_transmission_radar.py` | `idx_snapshots_node_ts` present in sqlite_master |
| `test_elasticity_normal` | `test_transmission_radar.py` | 168 / 45 = 3.73×, label = EXTREME |
| `test_elasticity_elevated` | `test_transmission_radar.py` | 90 / 45 = 2.0×, label = ELEVATED |
| `test_elasticity_turnaround` | `test_transmission_radar.py` | When proxy P/E ≤ 0, returns `null` ratio + `"N/A (Turnaround)"` label |
| `test_elasticity_anchor_zero` | `test_transmission_radar.py` | When anchor P/E = 0, returns `null` ratio (no ZeroDivisionError) |
| `test_circuit_proximity_stable` | `test_transmission_radar.py` | Price 100, band 5% → LC = 95.24, distance = 4.76%, status = STABLE |
| `test_circuit_locked_bid_zero` | `test_transmission_radar.py` | distance ≈ 0 AND bid_qty = 0 → status = CIRCUIT_LOCKED |
| `test_circuit_near_no_bids` | `test_transmission_radar.py` | distance = 1.8% → status = HIGH_FREEZE_RISK even if bids present |
| `test_anomaly_eod_leader_dump` | `test_transmission_radar.py` | delivery=22%, vol_mult=2.5 → `LEADER_DUMP_FOLLOWER_PUMP` (EOD mode) |
| `test_anomaly_intraday_rollover` | `test_transmission_radar.py` | intraday snapshot, no delivery → `INTRADAY_MOMENTUM_ROLLOVER` when vol_velocity > 2.5× |
| `test_anomaly_no_intraday_without_velocity` | `test_transmission_radar.py` | vol_velocity = 1.2×, intraday → returns None |
| `test_shockwave_bfs_decay` | `test_transmission_radar.py` | -5% anchor, elasticity 3.73, lag 0d → -18.65% satellite |
| `test_shockwave_bfs_one_day_decay` | `test_transmission_radar.py` | -10% anchor, elasticity 2.0, lag 24h → −17.0% (× 0.85 decay) |
| `test_dag_missing_node_edge` | `test_transmission_radar.py` | Edge referencing non-existent node_id → logged, skipped, graph still renders |
| `test_turso_sync_registration` | `test_transmission_radar.py` | All 4 table names present in `SYNC_TABLES` list |
| `test_graph_data_freshness_fields` | `test_transmission_radar.py` | `get_transmission_graph_payload` returns `data_freshness` dict with `oldest_snapshot_minutes` |
| `test_gate3_persistence` | `test_transmission_radar.py` | PATCH gate3 to PASS persists; subsequent GET graph shows `q2_cash_conversion.status == "PASS"` |
| `test_api_baskets` | `test_api_transmission.py` | 200; `baskets[0].basket_id == "AI_INFRA_HARDWARE"` |
| `test_api_graph_shape` | `test_api_transmission.py` | 200; `nodes`, `edges`, `anomalies`, `reentry_gates`, `data_freshness` all present |
| `test_api_shockwave` | `test_api_transmission.py` | 200; downstream node has `simulated_shock_pct` matching decay formula |
| `test_api_shockwave_invalid_range` | `test_api_transmission.py` | `anchor_shock_pct: -99.0` → HTTP 422 |
| `test_api_invalid_basket` | `test_api_transmission.py` | Unknown basket_id → 404, no stack trace in body |
| `test_api_gate3_update` | `test_api_transmission.py` | PATCH gate3 → 200; GET graph confirms gate3 status updated |
| `test_api_gate3_invalid_status` | `test_api_transmission.py` | PATCH gate3 with `status: "MAYBE"` → 422 |
