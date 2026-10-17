# Global CDMO, Peptide & Biosecure Cascade Radar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the `GLOBAL_CDMO_PEPTIDE_CASCADE` basket in the Transmission Lead-Lag Radar, modeling the 16-node, 16-edge physical and regulatory transmission graph from US Innovators/Tools Titans to Indian Frontline CDMO Leaders and High-Beta Peptide/Fermentation Proxies, complete with live data hydration, corporate catalyst extraction, algorithmic trade actions, and an interactive UI basket switcher.

**Architecture:**
- **Normalized Data Layer (`transmission_schema.py`)**: Seed basket definition, 16 nodes across 3 tiers (US Anchors -> Indian Leaders -> Indian Satellites), and 16 directed bottleneck edges into SQLite.
- **Quantitative Telemetry & Re-Entry Gates (`transmission_radar.py`)**: Parameterize Re-entry Gate 1 to dynamically evaluate the designated lead anchor (`BE` for AI Infra, `LLY` for CDMO) and composite majority health rule ($\ge 3/5$ Tier-1 anchors stabilized), while preserving pairwise upstream elasticity and live corporate catalyst extraction.
- **Frontend Basket Switcher & Graph Layout (`transmission_radar.js` & templates)**: Implement responsive basket selector in mirrored Jinja2 templates and dynamic layout calculation supporting 16-node multi-tier graph rendering and trade matrix filtering.

**Tech Stack:** FastAPI, SQLite (WAL mode, Turso sync), yfinance, Vanilla JS (Canvas/SVG), Pytest.

**Spec:** `docs/superpowers/specs/2026-10-17-cdmo-transmission-radar-design.md`

## Global Constraints
- Absolute anti-fabrication: zero mock/dummy seeds; valuations, prices, volumes, and catalysts must originate from real market tables or live APIs.
- Indian equities require `.NS` suffix; US equities have no suffix.
- PRAGMA configuration: `journal_mode=WAL`, `busy_timeout=5000`.
- All newly added tables or columns must maintain backward compatibility and be registered in `SYNC_TABLES`.
- Template mirroring invariant: `reports/templates/dashboard/_transmission.html` and `reports/templates/hubs/dashboard/_transmission.html` must remain 100% identical.
- Zero inline scripts in Jinja2 templates; all JS syntax verified via `node -c`.
- Route declaration rule: declare static routes before parameterized routes.

## Review Focus
1. Backward compatibility: Ensure default basket calls without explicit `basket_id` parameter default seamlessly to `AI_INFRA_HARDWARE` and all 33 existing tests remain green.
2. US ticker resolution: Ensure US symbols (`LLY`, `NVO`, `TMO`, `DHR`, `CRL`) are fetched without `.NS` suffix while Indian tickers (`DIVISLAB.NS`, `NEULANDLAB.NS`, etc.) have `.NS`.
3. Gate 1 dynamic anchor selection: Prevent `KeyError` or `NoneType` attribute errors when evaluating Gate 1 on baskets with different anchor configurations.
4. Canvas node collision: Verify 16 nodes across 3 tiers render cleanly on both mobile and wide screens without overlapping text or nodes.
5. Catalyst lookback tolerance: Ensure nodes with no recent news or earnings reports return empty lists `[]` cleanly without breaking JSON serialization.

---

### Task 1: Seed Schema for `GLOBAL_CDMO_PEPTIDE_CASCADE` Basket, Nodes & Edges

**Files:**
- Modify: `earnings_engine/data/transmission_schema.py`
- Test: `tests/test_transmission_radar.py`

**Interfaces:**
- Consumes: `init_transmission_db`, `seed_default_transmission_baskets`, `get_basket_graph_raw`
- Produces: 16 nodes and 16 directed bottleneck edges in SQLite database for basket `GLOBAL_CDMO_PEPTIDE_CASCADE`.

- [ ] **Step 1: Write failing test in `tests/test_transmission_radar.py` checking for CDMO basket, 16 nodes, and 16 edges**

```python
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
        "DIVISLAB.NS", "SYNGENE.NS", "SUVENPHAR.NS", "LAURUSLABS.NS", "PIRAMALPHI.NS",
        "NEULANDLAB.NS", "CONCORDBIO.NS", "BLUEJET.NS", "AMIORG.NS", "JUBLPHARMA.NS", "ANUPAM.NS"
    }
    assert expected_nodes == node_ids
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_transmission_radar.py -k test_cdmo_topology`
Expected: FAIL with missing basket or nodes.

- [ ] **Step 3: Update `seed_default_transmission_baskets` in `earnings_engine/data/transmission_schema.py`**

Add `GLOBAL_CDMO_PEPTIDE_CASCADE` basket row, 16 node rows (Tier 1 US Anchors, Tier 2 Indian Leaders, Tier 3 Indian Proxies), and 16 directed edges as specified in the design doc.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_transmission_radar.py -k test_cdmo_topology`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add earnings_engine/data/transmission_schema.py tests/test_transmission_radar.py
git commit -m "feat(transmission): seed GLOBAL_CDMO_PEPTIDE_CASCADE basket, nodes, and directed edges"
```

---

### Task 2: Parameterize Gate 1 Re-Entry Logic & Dual-Level Anchor Evaluation

**Files:**
- Modify: `earnings_engine/data/transmission_radar.py`
- Test: `tests/test_transmission_radar.py`

**Interfaces:**
- Consumes: `get_transmission_graph_payload(basket_id: str, conn: sqlite3.Connection)`
- Produces: Dynamic Gate 1 evaluation based on primary anchor (`BE` for `AI_INFRA_HARDWARE`, `LLY` for `GLOBAL_CDMO_PEPTIDE_CASCADE`) and composite Tier-1 anchor health check ($\ge 3/5$ anchors with 20D return $\ge 0\%$).

- [ ] **Step 1: Write failing test for `GLOBAL_CDMO_PEPTIDE_CASCADE` Gate 1 re-entry logic in `tests/test_transmission_radar.py`**

```python
def test_cdmo_gate1_evaluation():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_transmission_db(conn)
    seed_default_transmission_baskets(conn)

    # Insert snapshots for LLY and Tier 1 anchors
    conn.execute("INSERT INTO transmission_snapshots (node_id, current_price, change_1d_pct, change_20d_pct) VALUES ('LLY', 900.0, 1.5, 4.2)")
    conn.execute("INSERT INTO transmission_snapshots (node_id, current_price, change_1d_pct, change_20d_pct) VALUES ('NVO', 120.0, 0.5, 2.1)")
    conn.execute("INSERT INTO transmission_snapshots (node_id, current_price, change_1d_pct, change_20d_pct) VALUES ('TMO', 550.0, -0.2, 1.0)")
    conn.commit()

    payload = get_transmission_graph_payload("GLOBAL_CDMO_PEPTIDE_CASCADE", conn)
    assert payload["status"] == "ok"
    gates = payload["reentry_gates"]
    assert gates["gate1_anchor_stabilization"]["status"] in ("PASSED", "WARNING")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_transmission_radar.py -k test_cdmo_gate1_evaluation`
Expected: FAIL due to hardcoded `BE` anchor reference.

- [ ] **Step 3: Implement parameterized Gate 1 evaluation in `earnings_engine/data/transmission_radar.py`**

Update Gate 1 logic in `get_transmission_graph_payload` to inspect the basket's primary anchor:
- For `AI_INFRA_HARDWARE`: `BE` (or fallback to primary anchor with tier_column=1)
- For `GLOBAL_CDMO_PEPTIDE_CASCADE`: `LLY`
- Include composite check counting Tier 1 anchors with `change_20d_pct >= 0.0`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_transmission_radar.py -k test_cdmo_gate1_evaluation`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add earnings_engine/data/transmission_radar.py tests/test_transmission_radar.py
git commit -m "feat(transmission): parameterize re-entry gate 1 for multi-basket anchor stabilization"
```

---

### Task 3: Hydrate Live Fundamentals & Quotes for CDMO Basket

**Files:**
- Modify: `earnings_engine/data/transmission_radar.py`
- Test: `tests/test_transmission_radar.py`

**Interfaces:**
- Consumes: `sync_transmission_fundamentals(basket_id: str, conn: sqlite3.Connection)`
- Produces: Live quotes, 1D/5D/20D changes, and P/E multiples updated for all 16 CDMO nodes without crashing or mocking.

- [ ] **Step 1: Write unit test in `tests/test_transmission_radar.py` verifying fundamental sync supports CDMO basket**

```python
def test_sync_transmission_fundamentals_cdmo():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_transmission_db(conn)
    seed_default_transmission_baskets(conn)

    # Call sync with offline mock or verify function handles all 16 symbols
    from earnings_engine.data.transmission_radar import sync_transmission_fundamentals
    res = sync_transmission_fundamentals("GLOBAL_CDMO_PEPTIDE_CASCADE", conn, fetch_live=False)
    assert res["basket_id"] == "GLOBAL_CDMO_PEPTIDE_CASCADE"
    assert res["nodes_synced"] == 16
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_transmission_radar.py -k test_sync_transmission_fundamentals_cdmo`
Expected: FAIL

- [ ] **Step 3: Update `sync_transmission_fundamentals` in `earnings_engine/data/transmission_radar.py`**

Ensure `sync_transmission_fundamentals` accepts `basket_id`, fetches nodes for that basket, and updates snapshots and node multiples cleanly.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_transmission_radar.py -k test_sync_transmission_fundamentals_cdmo`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add earnings_engine/data/transmission_radar.py tests/test_transmission_radar.py
git commit -m "feat(transmission): enable live fundamentals and snapshot hydration for CDMO basket"
```

---

### Task 4: Frontend UI Basket Switcher & Multi-Tier Graph Layout

**Files:**
- Modify:
  - `earnings_engine/reports/templates/dashboard/_transmission.html`
  - `earnings_engine/reports/templates/hubs/dashboard/_transmission.html`
  - `earnings_engine/ui/js/modules/transmission_radar.js`
- Test: `node -c earnings_engine/ui/js/modules/transmission_radar.js`

**Interfaces:**
- Consumes: User selection from basket dropdown `#transmissionBasketSelect`, fetches `/api/transmission/graph?basket_id={id}`
- Produces:
  1. Instant re-rendering of Canvas Web with 16-node 3-tier geometry.
  2. Updates Stats Ribbon, Gatekeeper Badges, Tactical Trade Action Matrix, and Shockwave Simulator.
  3. Strict template synchronization between dashboard and hubs partials.

- [ ] **Step 1: Add basket switcher `<select id="transmissionBasketSelect">` options to `_transmission.html`**

Update both `reports/templates/dashboard/_transmission.html` and `reports/templates/hubs/dashboard/_transmission.html` with:
- `<option value="AI_INFRA_HARDWARE">⚡ AI Infrastructure & Power Bottlenecks</option>`
- `<option value="GLOBAL_CDMO_PEPTIDE_CASCADE">🧬 Global CDMO, Peptide & Biosecure Cascade</option>`

- [ ] **Step 2: Update `transmission_radar.js` to handle basket switching and 16-node canvas positioning**

- Add change listener to `#transmissionBasketSelect` that triggers `fetchAndRenderGraph(selectedBasketId)`.
- Adjust column node spacing algorithms in `_computeNodePositions()` to distribute 5 Tier 1 anchors, 5 Tier 2 leaders, and 6 Tier 3 proxies evenly across vertical space without overlap.
- Wire URL hash or state persistence so reloading preserves the currently selected basket.

- [ ] **Step 3: Validate JavaScript syntax and template diff**

Run: `node -c earnings_engine/ui/js/modules/transmission_radar.js`
Expected: Clean pass with zero syntax errors.
Verify: `diff -u earnings_engine/reports/templates/dashboard/_transmission.html earnings_engine/reports/templates/hubs/dashboard/_transmission.html` produces 0 diffs.

- [ ] **Step 4: Commit**

```bash
git add earnings_engine/reports/templates/dashboard/_transmission.html earnings_engine/reports/templates/hubs/dashboard/_transmission.html earnings_engine/ui/js/modules/transmission_radar.js
git commit -m "feat(transmission-ui): add basket switcher and multi-tier layout for CDMO peptide cascade"
```

---

### Task 5: Full Integration Verification & End-to-End Testing

**Files:**
- Test: `tests/test_transmission_radar.py`, `tests/test_api_transmission.py`

- [ ] **Step 1: Run complete transmission test suite**

Run: `pytest tests/test_transmission_radar.py tests/test_api_transmission.py -v`
Expected: All tests pass (including all legacy tests and new CDMO tests).

- [ ] **Step 2: Pre-hydrate live market quotes for all 16 CDMO tickers**

Run Python snippet via CLI to verify live quote resolution for US tickers (`LLY`, `NVO`, `TMO`, `DHR`, `CRL`) and Indian tickers (`DIVISLAB.NS`, `NEULANDLAB.NS`, `CONCORDBIO.NS`, etc.).

- [ ] **Step 3: Run error ledger scan**

Run: `./.venv/Scripts/python.exe scripts/error_ledger.py scan`
Expected: 0 new errors.

- [ ] **Step 4: Push all commits directly to `origin/new_report`**

Run: `git push origin new_report`
Verify: Remote branch is up to date.
