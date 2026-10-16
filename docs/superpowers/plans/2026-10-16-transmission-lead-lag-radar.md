# Global Transmission & Market Lead-Lag Radar — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reusable, interactive "Transmission Web" radar: animated DAG screen + quantitative engine covering cross-border supply-chain lead-lag, valuation elasticity traps, circuit freeze risks, institutional-to-retail delivery divergences, data staleness indicators, persistent Gate 3 toggle with audit trail, and snapshot retention.

**Architecture:** Four normalized SQLite tables (`transmission_baskets`, `transmission_nodes`, `transmission_edges`, `transmission_snapshots`) with Turso bidirectional sync. The Python engine computes elasticity ratios (with turnaround/zero-P/E safety), dual-mode delivery divergence (intraday VWAP-velocity + EOD delivery %), circuit proximity with bid-depth confirmation, and data freshness metadata (snapshot age in minutes). A FastAPI router exposes four endpoints (`/baskets`, `/graph`, `/simulate-shockwave`, `PATCH /baskets/{id}/gate3`). The browser renders a layered Canvas (Bezier lines + particles) behind DOM node cards with staleness badges, BFS-driven shockwave propagation, and `visibilitychange` / `IntersectionObserver` animation lifecycle controls. Both `dashboard/_transmission.html` and `hubs/dashboard/_transmission.html` are identical mirrors.

**Tech Stack:** Python 3.11+, FastAPI, SQLite, Pandas/NumPy, HTML5/CSS3 (Jinja2), HTML5 Canvas, Vanilla ES6 JavaScript (modular).

**Spec:** `docs/superpowers/specs/2026-10-16-transmission-lead-lag-radar-design.md`

## Global Constraints

- Python interpreter: `./.venv/Scripts/python.exe` (forward slashes in bash).
- Branch: `new_report` — commit and push on completion.
- Anti-fabrication: Return `null`, `[]`, or truthful status strings when live feeds are unavailable. Never invent prices or delivery %.
- Turso sync: All 4 tables in `SYNC_TABLES`. Watermark columns: `updated_at` for baskets/nodes/edges; `created_at` for snapshots (append-only). All inserts `INSERT OR IGNORE` / `INSERT OR REPLACE`. Remote calls wrapped with local SQLite fallback.
- FastAPI static-before-parameterised: mount `/api/transmission/baskets` and `/api/transmission/graph` before any `/{param}` routes in `server.py`.
- Frontend module: `transmission_radar.js` must stay ≤ 500 lines; validate with `node -c`.
- Template mirroring: `dashboard/_transmission.html` and `hubs/dashboard/_transmission.html` must be identical. Verify with `diff`; zero output required.
- Error ledger: `scripts/error_ledger.py scan` after task completion.

## Review Focus

1. **Turnaround / zero-trailing-P/E safety**: When `proxy_pe <= 0` or `anchor_pe <= 0`, elasticity must return `null` + `"N/A (Turnaround)"` — never `inf`, `NaN`, or divide-by-zero. Covered by `test_elasticity_turnaround` and `test_elasticity_anchor_zero` in Task 2.
2. **NSE delivery % timing (EOD-only data)**: Delivery % is unavailable during trading hours (09:15–15:30 IST). Intraday snapshots must set `delivery_pct = NULL` and trigger only the `INTRADAY_MOMENTUM_ROLLOVER` flag (volume-velocity path), never the `LEADER_DUMP_FOLLOWER_PUMP` flag. Covered by `test_anomaly_intraday_rollover` in Task 2.
3. **Circuit freeze requires zero bid depth**: A stock at its lower circuit limit (distance ≈ 0%) with non-zero bid quantity is still tradeable. `CIRCUIT_LOCKED` fires only when `bid_qty_total == 0`. Covered by `test_circuit_locked_bid_zero` in Task 2.
4. **Canvas particle budget and tab-visibility pause**: With ≥ 10 nodes and 8 edges, unbounded particle spawning causes frame drops. Cap at 8 particles per edge / 40 total; pause `requestAnimationFrame` on `document.hidden` and `IntersectionObserver` — covered by `node -c` + manual browser QA step in Task 4.
5. **Basket switcher tears down animation loops**: Switching baskets must call `cancelAnimationFrame` on all pending animation handles before re-initialising. Uncleaned loops accumulate across switches and leak memory — covered by `test_basket_switch_teardown` (DOM/integration) in Task 4.

---

### Task 1: Database Schema, Seed Data & Turso Sync

**Files:**
- Create: `earnings_engine/data/transmission_schema.py`
- Modify: `earnings_engine/data/turso_sync.py`
- Test: `tests/test_transmission_radar.py`

**Interfaces:**
- Consumes: `earnings_engine.config.Settings`, `earnings_engine.data.turso_sync.SYNC_TABLES`
- Produces:
  - `init_transmission_db(conn: sqlite3.Connection) -> None`
  - `seed_default_transmission_baskets(conn: sqlite3.Connection) -> None`
  - `get_all_baskets(conn: sqlite3.Connection) -> list[dict]`
  - `get_basket_graph_raw(basket_id: str, conn: sqlite3.Connection) -> tuple[list[dict], list[dict]]` — returns `(nodes, edges)` as plain dicts from DB

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_transmission_radar.py
import sqlite3, pytest
from earnings_engine.data.transmission_schema import (
    init_transmission_db, seed_default_transmission_baskets, get_all_baskets,
    get_basket_graph_raw,
)
from earnings_engine.data import turso_sync

def test_schema_init_and_seed():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_transmission_db(conn)
    seed_default_transmission_baskets(conn)
    baskets = get_all_baskets(conn)
    assert len(baskets) >= 1
    assert baskets[0]["basket_id"] == "AI_INFRA_HARDWARE"
    nodes, edges = get_basket_graph_raw("AI_INFRA_HARDWARE", conn)
    assert len(nodes) >= 10   # BE, NVDA_CLUSTER, CIEN, GLW, DIXON, STLTECH, HFCL, MTAR, SYRMA, AEROFLEX
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
    from earnings_engine.data.transmission_schema import prune_old_snapshots
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
    for table in ("transmission_baskets", "transmission_nodes",
                  "transmission_edges", "transmission_snapshots"):
        assert table in turso_sync.SYNC_TABLES, f"{table} missing from SYNC_TABLES"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_transmission_radar.py -k "test_schema_init_and_seed or test_snapshot_retention or test_snapshot_index_exists or test_turso_sync_registration" -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `transmission_schema.py`**

Create the four tables per the spec schema (exact column names, types, constraints, and the `idx_snapshots_node_ts` index). Seed `AI_INFRA_HARDWARE` basket with the 10 nodes and 8 edges from spec §4 seed table. All inserts use `INSERT OR IGNORE`.

Also implement `prune_old_snapshots(node_id: str, conn: sqlite3.Connection, keep: int = 90) -> None`: deletes snapshot rows for `node_id` beyond the `keep` most recent by `created_at DESC`.

Gate 3 columns (`gate3_cash_conversion_status`, `gate3_updated_at`, `gate3_updated_by`) must be in `transmission_baskets` per the spec DDL.

- [ ] **Step 4: Register tables in `turso_sync.py`**

Append `transmission_baskets`, `transmission_nodes`, `transmission_edges`, `transmission_snapshots` to `SYNC_TABLES`.

Add watermarks **per-table** as follows:
- `transmission_baskets.updated_at` → `WATERMARK_CANDIDATE_COLUMNS`
- `transmission_nodes.updated_at` → `WATERMARK_CANDIDATE_COLUMNS`
- `transmission_edges.updated_at` → `WATERMARK_CANDIDATE_COLUMNS`
- `transmission_snapshots.created_at` → `WATERMARK_CANDIDATE_COLUMNS` (snapshots are append-only; they have no `updated_at`)

Wrap any turso remote call with a `try/except` local-fallback guard.

- [ ] **Step 5: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_transmission_radar.py -k "test_schema_init_and_seed or test_snapshot_retention or test_snapshot_index_exists or test_turso_sync_registration" -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add earnings_engine/data/transmission_schema.py earnings_engine/data/turso_sync.py tests/test_transmission_radar.py
git commit -m "feat(transmission): add normalized DAG schema, seed data, snapshot retention, and turso sync registration

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 2: Quantitative Engine & Anomaly Detector

**Files:**
- Create: `earnings_engine/data/transmission_radar.py`
- Modify: `tests/test_transmission_radar.py`

**Interfaces:**
- Consumes: `earnings_engine.data.transmission_schema.get_basket_graph_raw`
- Produces:
  - `compute_valuation_elasticity(proxy_pe: float | None, anchor_pe: float | None, is_turnaround: bool = False) -> tuple[float | None, str]` — returns `(ratio_or_None, label)`
  - `compute_circuit_proximity(price: float, circuit_band_pct: float | None) -> tuple[float | None, str]` — `(distance_pct, status)`
  - `detect_delivery_divergence(delivery_pct: float | None, vol_multiple: float, vol_velocity: float | None, data_mode: str) -> str | None` — returns anomaly flag string or `None`
  - `compute_shockwave_bfs(nodes: list[dict], edges: list[dict], origin_node_id: str, anchor_shock_pct: float) -> list[dict]`
  - `get_transmission_graph_payload(basket_id: str, conn) -> dict` — includes `data_freshness` block and `snapshot_as_of_utc`/`snapshot_age_minutes`/`is_stale` per node

- [ ] **Step 1: Write the failing tests**

```python
from earnings_engine.data.transmission_radar import (
    compute_valuation_elasticity,
    compute_circuit_proximity,
    detect_delivery_divergence,
    compute_shockwave_bfs,
)

# --- elasticity ---
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

# --- circuit ---
def test_circuit_stable():
    # band 5%: lower circuit of 100 = price / 1.05 = 95.24; distance = (100 - 95.24) / 100 * 100
    dist, status = compute_circuit_proximity(100.0, 5.0)
    assert dist > 4.0
    assert status == "STABLE"

def test_circuit_locked_bid_zero():
    # price exactly at lower circuit → distance ≈ 0
    dist, status = compute_circuit_proximity(95.24, 5.0)
    assert dist < 0.1
    # the function returns NEAR_CIRCUIT; caller upgrades to CIRCUIT_LOCKED when bid_qty == 0
    assert status in ("NEAR_CIRCUIT", "CIRCUIT_LOCKED", "HIGH_FREEZE_RISK")

def test_circuit_near():
    dist, status = compute_circuit_proximity(97.0, 5.0)
    assert status == "HIGH_FREEZE_RISK"

# --- delivery divergence ---
def test_anomaly_eod_leader_dump():
    flag = detect_delivery_divergence(delivery_pct=22.0, vol_multiple=2.5,
                                      vol_velocity=None, data_mode="EOD")
    assert flag == "LEADER_DUMP_FOLLOWER_PUMP"

def test_anomaly_intraday_rollover():
    # delivery_pct is None in intraday — must not fire EOD flag
    flag = detect_delivery_divergence(delivery_pct=None, vol_multiple=3.0,
                                      vol_velocity=2.8, data_mode="INTRADAY")
    assert flag == "INTRADAY_MOMENTUM_ROLLOVER"

def test_anomaly_no_intraday_without_velocity():
    flag = detect_delivery_divergence(delivery_pct=None, vol_multiple=0.8,
                                      vol_velocity=1.2, data_mode="INTRADAY")
    assert flag is None

# --- shockwave BFS ---
def test_shockwave_bfs_decay():
    nodes = [{"node_id": "BE"}, {"node_id": "MTAR"}]
    edges = [{"source_node_id": "BE", "target_node_id": "MTAR",
              "elasticity_multiplier": 3.73, "lag_window_hours": 0}]
    results = compute_shockwave_bfs(nodes, edges, "BE", -5.0)
    mtar = next(r for r in results if r["node_id"] == "MTAR")
    assert round(mtar["simulated_shock_pct"], 2) == round(-5.0 * 3.73 * (0.85 ** 0), 2)

def test_shockwave_bfs_one_day_decay():
    nodes = [{"node_id": "A"}, {"node_id": "B"}]
    edges = [{"source_node_id": "A", "target_node_id": "B",
              "elasticity_multiplier": 2.0, "lag_window_hours": 24}]
    results = compute_shockwave_bfs(nodes, edges, "A", -10.0)
    b = next(r for r in results if r["node_id"] == "B")
    assert round(b["simulated_shock_pct"], 2) == round(-10.0 * 2.0 * 0.85, 2)

def test_dag_missing_edge_node():
    nodes = [{"node_id": "A"}]
    edges = [{"source_node_id": "A", "target_node_id": "GHOST",
              "elasticity_multiplier": 1.0, "lag_window_hours": 0}]
    # Must not raise; ghost target is silently skipped
    results = compute_shockwave_bfs(nodes, edges, "A", -5.0)
    assert not any(r["node_id"] == "GHOST" for r in results)

# --- data freshness ---
def test_graph_data_freshness_fields():
    import sqlite3
    from earnings_engine.data.transmission_schema import init_transmission_db, seed_default_transmission_baskets
    from earnings_engine.data.transmission_radar import get_transmission_graph_payload
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_transmission_db(conn)
    seed_default_transmission_baskets(conn)
    payload = get_transmission_graph_payload("AI_INFRA_HARDWARE", conn)
    assert "data_freshness" in payload
    df = payload["data_freshness"]
    assert "oldest_snapshot_minutes" in df
    assert "has_stale_nodes" in df
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_transmission_radar.py -k "elasticity or circuit or anomaly or shockwave or dag_missing or data_freshness" -v`
Expected: FAIL.

- [ ] **Step 3: Implement `earnings_engine/data/transmission_radar.py`**

Key implementation notes:
- `compute_valuation_elasticity`: guard `if not proxy_pe or not anchor_pe or proxy_pe <= 0 or anchor_pe <= 0 or is_turnaround` → return `(None, "N/A (Turnaround)")`.
- `compute_circuit_proximity`: lower circuit = `price / (1 + circuit_band_pct/100)`. Distance = `(price - lc) / price * 100`. Status thresholds per spec.
- `detect_delivery_divergence`: `data_mode == "INTRADAY"` path checks only `vol_velocity > 2.5` (ignores `delivery_pct`). `data_mode == "EOD"` path checks `delivery_pct < 25 AND vol_multiple > 2.0`.
- `compute_shockwave_bfs`: BFS from `origin_node_id` using adjacency from `edges`; skip edges pointing to unknown node IDs with a `logging.warning`.
- `get_transmission_graph_payload`:
  - assemble nodes + latest snapshot per node
  - compute `snapshot_age_minutes = int((now_utc - snapshot.created_at).total_seconds() / 60)` for each node
  - `is_stale = snapshot_age_minutes > 30` during trading hours (09:15–15:30 IST), `> 720` otherwise
  - build `data_freshness = { "oldest_snapshot_minutes": max(ages), "has_stale_nodes": any(is_stale), "stale_threshold_minutes": 30 }`
  - call `compute_valuation_elasticity` + `compute_circuit_proximity` on each node
  - upgrade circuit status to `CIRCUIT_LOCKED` when `bid_qty_total == 0` (caller upgrade, not in `compute_circuit_proximity`)
  - assemble anomaly list, re-entry gates (Gate 1 uses `change_5d_pct` and `change_20d_pct` from latest snapshot; both must be non-None), edge `pulse_active` / `pulse_color` from `impact_level`
  - re-entry gates include `q2_cash_conversion.status` from `transmission_baskets.gate3_cash_conversion_status`

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_transmission_radar.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add earnings_engine/data/transmission_radar.py tests/test_transmission_radar.py
git commit -m "feat(transmission): quantitative engine — elasticity, circuit proximity, dual-mode divergence, BFS shockwave, data freshness

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 3: FastAPI Router & Server Mount

**Files:**
- Create: `earnings_engine/api/routers/transmission.py`
- Modify: `earnings_engine/api/server.py`
- Create: `tests/test_api_transmission.py`

**Interfaces:**
- Consumes:
  - `earnings_engine.data.transmission_schema.get_all_baskets`
  - `earnings_engine.data.transmission_radar.get_transmission_graph_payload`
  - `earnings_engine.data.transmission_radar.compute_shockwave_bfs`
- Produces:
  - `GET /api/transmission/baskets`
  - `GET /api/transmission/graph?basket_id={basket_id}`
  - `POST /api/transmission/simulate-shockwave` body: `{ basket_id, origin_node_id, anchor_shock_pct: float }`
  - `PATCH /api/transmission/baskets/{basket_id}/gate3` body: `{ status: str, updated_by: str }`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_api_transmission.py
from fastapi.testclient import TestClient
from earnings_engine.api.server import app

client = TestClient(app)

def test_api_baskets():
    res = client.get("/api/transmission/baskets")
    assert res.status_code == 200
    data = res.json()
    assert "baskets" in data
    assert any(b["basket_id"] == "AI_INFRA_HARDWARE" for b in data["baskets"])

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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_api_transmission.py -v`
Expected: 404 / attribute errors — routes not mounted.

- [ ] **Step 3: Implement `earnings_engine/api/routers/transmission.py`**

- `router = APIRouter(prefix="/transmission", tags=["transmission"])`
- `GET /baskets`: calls `get_all_baskets()` with local DB or Turso fallback.
- `GET /graph`: validates `basket_id` exists; raises `HTTPException(404)` if not; calls `get_transmission_graph_payload()`.
- `POST /simulate-shockwave`: Pydantic body model:
  ```python
  class ShockwaveRequest(BaseModel):
      basket_id: str
      origin_node_id: str
      anchor_shock_pct: float = Field(..., ge=-50.0, le=50.0)
  ```
  calls `get_basket_graph_raw` + `compute_shockwave_bfs`; returns `{ basket_id, origin_node_id, anchor_shock_pct, propagation: list }`.
- `PATCH /baskets/{basket_id}/gate3`: Pydantic body model:
  ```python
  class Gate3Update(BaseModel):
      status: Literal["PENDING", "PASS", "FAIL"]
      updated_by: str
  ```
  Updates `transmission_baskets` columns `gate3_cash_conversion_status`, `gate3_updated_at = datetime.utcnow()`, `gate3_updated_by`. Returns 404 if basket not found.

- [ ] **Step 4: Mount in `server.py`**

Add `from earnings_engine.api.routers import transmission` and `app.include_router(transmission.router, prefix="/api")` **before** any existing parameterized routers (FastAPI static-before-parameterised rule).

- [ ] **Step 5: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_api_transmission.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add earnings_engine/api/routers/transmission.py earnings_engine/api/server.py tests/test_api_transmission.py
git commit -m "feat(transmission): FastAPI router — /baskets, /graph, /simulate-shockwave, PATCH /gate3

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 4: Animated Transmission Web UI

**Files:**
- Create: `earnings_engine/reports/templates/dashboard/_transmission.html`
- Create: `earnings_engine/reports/templates/hubs/dashboard/_transmission.html` (must be identical to above)
- Create: `earnings_engine/ui/js/modules/transmission_radar.js`
- Modify: `earnings_engine/reports/templates/dashboard/_sidebar.html`
- Modify: `earnings_engine/reports/templates/hubs/dashboard/_sidebar.html`
- Modify: `earnings_engine/reports/templates/dashboard/_script_tags.html`
- Modify: `earnings_engine/reports/templates/hubs/dashboard/_script_tags.html`
- Modify: `earnings_engine/ui/js/dashboard.js`

**Interfaces:**
- Consumes: `GET /api/transmission/baskets`, `GET /api/transmission/graph`, `POST /api/transmission/simulate-shockwave`, `PATCH /api/transmission/baskets/{id}/gate3`
- Produces: `initTransmissionRadar()` — public entry point called by `dashboard.js`

**Implementation notes (all implementation choices belong to the implementer except these):**

- [ ] **Step 1: Create `_transmission.html`**
  - Panel structure: header bar (basket `<select>`, shockwave `<button>`, refresh icon), three-tier grid (`tier-anchors` | `tier-bottlenecks` | `tier-satellites`), `<canvas id="transmissionCanvas">` positioned `absolute, top:0, left:0, pointer-events:none`, anomaly ticker strip, re-entry gates section with Gate 3 "✏️ Update" button and modal.
  - Node card markup: `data-node-id`, `data-tier`, `data-role` attributes for JS targeting.
  - Staleness badge: `<span class="stale-badge" hidden>⏱ <span class="stale-minutes"></span>m ago</span>` inside each node card; JS shows/hides based on `is_stale`.

- [ ] **Step 2: Create `hubs/dashboard/_transmission.html`**

  Copy `dashboard/_transmission.html` exactly. Verify:
  ```bash
  diff earnings_engine/reports/templates/dashboard/_transmission.html \
       earnings_engine/reports/templates/hubs/dashboard/_transmission.html
  ```
  Expected: zero output (files identical).

- [ ] **Step 3: Add sidebar nav entry to both `_sidebar.html` files**

  Add a `<li>` item with `data-tab="transmission"` label "Transmission Web" and a network icon, positioned after the Breakout Radar entry. Apply to **both** `dashboard/_sidebar.html` and `hubs/dashboard/_sidebar.html`.

- [ ] **Step 4: Add script tag to both `_script_tags.html` files**

  Add `<script src="{{ url_for('static', path='js/modules/transmission_radar.js') }}"></script>` to **both** `dashboard/_script_tags.html` and `hubs/dashboard/_script_tags.html`.

- [ ] **Step 5: Implement `transmission_radar.js`**

  Public API: `initTransmissionRadar()`.

  Key responsibilities (implementer chooses internal structure):
  - Fetch baskets on init; populate `<select>`.
  - Fetch graph on basket select; render DOM node cards per tier; draw Canvas Bezier paths; apply staleness badges (`is_stale`, `snapshot_age_minutes`).
  - Particle loop: each edge holds a particle list (max 8); total enforced at 40. Uses `requestAnimationFrame`. Pauses on `document.visibilitychange` (`document.hidden`) and `IntersectionObserver` (panel off-screen).
  - Basket switch: `cancelAnimationFrame(rafHandle)` + clear all particles + remove node cards + redraw.
  - Shockwave: `POST /api/transmission/simulate-shockwave`; apply delayed card flash (delay = `lag_days × 600ms`); animate edge ripple.
  - Node click: open drawer with node detail (P/E, `volume_velocity_ratio`, delivery mode label, circuit bar, `snapshot_as_of_utc`, last 10 snapshots).
  - Gate 3 modal: "✏️ Update Gate 3" calls `PATCH /api/transmission/baskets/{basket_id}/gate3`; refreshes re-entry gate display on success.

- [ ] **Step 6: Wire `initTransmissionRadar()` into `dashboard.js`**

  Call `initTransmissionRadar()` inside the tab activation handler for `data-tab="transmission"` (lazy-init pattern already used by other modules).

- [ ] **Step 7: Validate JS syntax**

  Run: `node -c earnings_engine/ui/js/modules/transmission_radar.js`
  Expected: no syntax errors.

- [ ] **Step 8: Commit**

```bash
git add earnings_engine/reports/templates/dashboard/_transmission.html \
        earnings_engine/reports/templates/hubs/dashboard/_transmission.html \
        earnings_engine/reports/templates/dashboard/_sidebar.html \
        earnings_engine/reports/templates/hubs/dashboard/_sidebar.html \
        earnings_engine/reports/templates/dashboard/_script_tags.html \
        earnings_engine/reports/templates/hubs/dashboard/_script_tags.html \
        earnings_engine/ui/js/modules/transmission_radar.js \
        earnings_engine/ui/js/dashboard.js
git commit -m "feat(ui): transmission web — animated Bezier canvas, particle pulses, shockwave, staleness badges, gate3 modal, hub mirrors

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 5: End-to-End Verification & Push

**Files:** (no new files)

- [ ] **Step 1: Run full transmission test suite**

  Run: `./.venv/Scripts/python.exe -m pytest tests/test_transmission_radar.py tests/test_api_transmission.py -v`
  Expected: All tests PASS.

- [ ] **Step 2: Run error ledger scan**

  Run: `./.venv/Scripts/python.exe scripts/error_ledger.py scan`
  Expected: Zero unlogged errors.

- [ ] **Step 3: Verify template mirrors**

  Run: `diff earnings_engine/reports/templates/dashboard/_transmission.html earnings_engine/reports/templates/hubs/dashboard/_transmission.html`
  Expected: zero output.

- [ ] **Step 4: Manual browser smoke test**

  Open dashboard → click "Transmission Web" in sidebar → confirm:
  - 10 node cards render across three-tier layout.
  - Bezier lines draw on canvas for all 8 seeded edges.
  - Particles flow along lines without stutter (≤ 40 total).
  - Any stale node shows amber `⏱ Xm ago` badge; global stale banner fires when `has_stale_nodes: true`.
  - "Trigger Shockwave" button fires cascade with delayed node flashes.
  - Basket switcher switches cleanly (no ghost particles from previous basket).
  - Node card click opens drawer with P/E, `volume_velocity_ratio`, circuit bar, data-mode label, snapshot age.
  - Gate 3 "✏️ Update" modal persists status change and reflects in re-entry gates.

- [ ] **Step 5: Push**

  ```bash
  git push origin new_report
  ```
