# Morning Deals Deduplication & Institutional Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate artifactual duplicate block/bulk deals, automatically pair bilateral buyer-seller cross trades, and upgrade Morning Setups with institutional-grade intelligence tags and quantitative clarity.

**Architecture:** 
1. Backend ingestion (`morning_setups.py`) sanitizes client strings and suppresses generic live-window placeholders (`NSE Block Window ...`) whenever settled EOD CSV counterparties exist.
2. A database cleanup pass purges legacy placeholder shadowing where real counterparties are already recorded.
3. An algorithmic trade-pairing engine identifies bilateral block crosses (`(deal_date, ticker, quantity, trade_price)` matching BUY and SELL legs) and exposes counterparty linkage.
4. An institutional badge system annotates deals with deal nature (`⚡ Matched Block Cross`, `🎯 Open Market Accumulation`, `🔻 Institutional Exit`), Breakout Radar synergy, and 52W high proximity.
5. Frontend UI (`_morning_setups.html` mirrored across both templates and `morning_setups.js`) renders linked counterparty chips and clear net-flow summaries.

**Tech Stack:** Python 3.12+, FastAPI, SQLite/Turso WAL, Jinja2, Vanilla ES6+ Modular JavaScript.

**Spec:** `docs/superpowers/specs/2026-10-20-morning-deals-upgrade-spec.md` (derived from market microstructure analysis).

## Global Constraints

- Never fabricate dummy or simulated counterparty names or prices; adhere strictly to anti-fabrication standards.
- Maintain template mirroring rule: `reports/templates/dashboard/_morning_setups.html` and `reports/templates/hubs/dashboard/_morning_setups.html` must remain bit-for-bit identical.
- Keep `SYNC_TABLES` and SQLite WAL compatibility intact.
- Follow static-route-first precedence in FastAPI routers.
- JavaScript modules must validate with `node -c`.

## Review Focus

1. Partial quantity fills or multiple sub-allocations on the same price must not be mistakenly collapsed or dropped.
2. Live API ingestion running before EOD CSV publication must still insert live provisional records without error.
3. Ingestion deduplication must be idempotent: running sync repeatedly must produce 0 duplicate records.
4. Bilateral trade pairing must strictly match `deal_date`, `ticker`, `trade_price`, and `quantity` with opposing sides (`BUY` vs `SELL`).
5. Grouped by symbol aggregation must maintain accurate Volume-Weighted Average Price (VWAP) and net flow calculations.

---

### Task 1: Ingestion Normalization & Placeholder De-Shadowing Engine

**Files:**
- Modify: `earnings_engine/data/morning_setups.py:545-710`
- Test: `tests/test_morning_deals_dedup.py`

**Interfaces:**
- Consumes: Raw CSV and JSON feeds from official NSE endpoints (`bulk.csv`, `block.csv`, `api/block-deal`).
- Produces: Sanitized, de-shadowed records in `morning_block_deals` without generic placeholder collisions.

- [ ] **Step 1: Write failing test for client normalization and placeholder de-shadowing**

```python
def test_placeholder_deshadowing_and_client_normalization():
    # Test that generic live placeholder "NSE Block Window (Window 1)" is superseded
    # when official counterparty records exist for the same deal.
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_morning_deals_dedup.py::test_placeholder_deshadowing_and_client_normalization -v`
Expected: FAIL

- [ ] **Step 3: Implement client normalization and placeholder de-shadowing in `morning_setups.py`**

- In `clean_client_name(name: str) -> str`: strip punctuation, excessive whitespace, and standard legal entity abbreviations for uniform hashing.
- In `sync_all_morning_deals(settings)`:
  - If official CSV block deals exist for `(deal_date, ticker, quantity, trade_price)`, skip or delete existing generic `"NSE Block Window ..."` records (`source='NSE_LIVE'`) for that tuple.
  - Implement a purge of legacy orphan placeholders in SQLite.

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_morning_deals_dedup.py::test_placeholder_deshadowing_and_client_normalization -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add earnings_engine/data/morning_setups.py tests/test_morning_deals_dedup.py
git commit -m "feat(morning-setups): add client normalization and placeholder de-shadowing"
```

---

### Task 2: Bilateral Trade Counterparty Pairing Engine

**Files:**
- Modify: `earnings_engine/data/morning_setups.py:950-1040`
- Modify: `earnings_engine/api/routers/morning_setups.py:65-115`
- Test: `tests/test_morning_deals_dedup.py`

**Interfaces:**
- Consumes: `morning_block_deals` rows.
- Produces: Enhanced deal records with `is_matched_cross: bool`, `counterparty_name: str | None`, and `deal_nature: str`.

- [ ] **Step 1: Write failing test for trade counterparty pairing**

```python
def test_bilateral_trade_pairing():
    # When buyer (Fund A) and seller (Fund B) execute identical qty & price on same date,
    # engine identifies matched cross and attaches counterparty_name.
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_morning_deals_dedup.py::test_bilateral_trade_pairing -v`
Expected: FAIL

- [ ] **Step 3: Implement bilateral pairing in `morning_setups.py`**

- In `pair_bilateral_deals(deals: list[dict[str, Any]]) -> list[dict[str, Any]]`:
  - Build lookup index on `(deal_date, ticker, quantity, round(trade_price, 2))`.
  - When matching opposing `BUY` and `SELL` legs exist:
    - Set `is_matched_cross = True`
    - Attach `counterparty_name` to each leg
    - Set `deal_nature = "MATCHED_CROSS"`
  - For unpaired deals, classify as `"OPEN_MARKET_ACCUMULATION"` (BUY) or `"INSTITUTIONAL_EXIT"` (SELL).

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_morning_deals_dedup.py::test_bilateral_trade_pairing -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add earnings_engine/data/morning_setups.py earnings_engine/api/routers/morning_setups.py tests/test_morning_deals_dedup.py
git commit -m "feat(morning-setups): implement bilateral trade pairing and cross-trade classification"
```

---

### Task 3: Multi-Dimensional Institutional Badging Engine

**Files:**
- Modify: `earnings_engine/data/morning_setups.py:176-370`
- Test: `tests/test_morning_deals_dedup.py`

**Interfaces:**
- Consumes: Ticker list, live market quotes, Breakout Radar DB, prices cache.
- Produces: Institutional tag metadata attached to each deal/grouped record.

- [ ] **Step 1: Write failing test for institutional tags generation**

```python
def test_morning_setups_institutional_tags():
    # Verify generation of badges:
    # - "Matched Block Cross"
    # - "Breakout Radar Active"
    # - "Testing 52W High"
    # - "Upcoming Results (N Days)"
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_morning_deals_dedup.py::test_morning_setups_institutional_tags -v`
Expected: FAIL

- [ ] **Step 3: Implement technical and catalyst enrichment in `morning_setups.py`**

- Cross-check `breakout_radar` for active candidate tier.
- Compute 52-week high drawdown with negative sign convention (`((price / high_52w) - 1.0) * 100.0`).
- Attach contextual tags array to each deal print.

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_morning_deals_dedup.py::test_morning_setups_institutional_tags -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add earnings_engine/data/morning_setups.py tests/test_morning_deals_dedup.py
git commit -m "feat(morning-setups): add multi-dimensional institutional tagging to morning deals"
```

---

### Task 4: UI & Template Upgrade with Linked Counterparty Chips

**Files:**
- Modify: `earnings_engine/ui/js/modules/morning_setups.js`
- Modify: `earnings_engine/reports/templates/dashboard/_morning_setups.html`
- Modify: `earnings_engine/reports/templates/hubs/dashboard/_morning_setups.html`

**Interfaces:**
- Consumes: Enriched deals payload from `/api/v1/morning-setups/deals`.
- Produces: Polished high-density terminal table with linked counterparty chips, explicit badges, and bit-for-bit mirrored HTML templates.

- [ ] **Step 1: Update `morning_setups.js` to render linked counterparty chips and institutional badges**

- In flat view: If `d.is_matched_cross`, render an interactive chip: `⇄ Matched with: <Counterparty Name>`, clarifying why both rows exist.
- In grouped view: Display `Cross-Trade Volume (₹0 Net Flow)` badge when gross buy == gross sell.
- Render institutional tag badges (`⚡ Block Cross`, `🔥 Breakout`, `🎯 Testing 52W High`).

- [ ] **Step 2: Update both Jinja2 templates (`dashboard` and `hubs/dashboard`) identically**

- Ensure sticky header z-indexes are coordinated (`thead th: z-index 25`).
- Ensure consistent design system tokens (`var(--bg-surface)`, `var(--text-primary)`, `var(--border-subtle)`).

- [ ] **Step 3: Validate JavaScript syntax**

Run: `node -c earnings_engine/ui/js/modules/morning_setups.js`
Expected: Clean exit (0 errors)

- [ ] **Step 4: Commit**

```bash
git add earnings_engine/ui/js/modules/morning_setups.js earnings_engine/reports/templates/dashboard/_morning_setups.html earnings_engine/reports/templates/hubs/dashboard/_morning_setups.html
git commit -m "feat(morning-setups): render linked counterparty chips and institutional tags in UI"
```

---

### Task 5: End-to-End Verification & Database Cleanup

**Files:**
- Modify: `tests/test_morning_setups.py`
- Test: Full morning setups test suite

- [ ] **Step 1: Run complete test suite for morning setups**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_morning_setups.py tests/test_morning_deals_dedup.py -v`
Expected: All tests PASS.

- [ ] **Step 2: Run error ledger scan**

Run: `./.venv/Scripts/python.exe scripts/error_ledger.py scan`
Expected: Clean.

- [ ] **Step 3: Execute DB cleanup on legacy duplicate placeholders**

Run cleanup script to purge orphan `NSE Block Window` records superseded by official CSV counterparties.

- [ ] **Step 4: Final commit and push**

```bash
git add -A
git commit -m "chore(morning-setups): verify morning deals deduplication and push updates"
git push origin new_report
```
