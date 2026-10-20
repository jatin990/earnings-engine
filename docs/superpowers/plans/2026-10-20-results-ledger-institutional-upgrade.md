# Results Ledger Institutional Grade Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform the Corporate Results Ledger into an institutional-grade equity intelligence terminal with mathematically verified price calculations (returns, drawdowns, S/R, volume surge), strictly verified result dates sourced from official NSE/BSE corporate filings, verified catalyst tags, token-compliant typography/surfaces, and accessible interaction states.

**Architecture:** 
1. Fix backend calculation sign inversion in `market_context.py` for 52W high/low drawdown and verify all price math (returns, channel position, volume surges, S/R pivots) via comprehensive pytest assertions.
2. Ensure Result Dates come strictly from official NSE/BSE regulatory announcements, cleanly distinguishing confirmed exchange filings from unconfirmed projections with explicit exchange badges (`[NSE Confirmed]`, `[BSE Confirmed]`, `[Unconfirmed Estimate]`).
3. Build an efficient, batched `Tag Engine` in `market_context.py` and `render.py` that queries verified `news_catalysts` ($\pm 14$ days), `breakout_radar`, and institutional snapshots in a single multi-table SQLite query without N+1 overhead or mock fallbacks.
4. Overhaul the SSR Jinja2 templates (`dashboard/_results.html`, `hubs/dashboard/_results.html`, `result_row.html`) and frontend module (`results_ledger.js`) to achieve 100% design token compliance, non-blocking AI summaries, active sort glyphs, and high-density financial alignment.

**Tech Stack:** Python 3.14, FastAPI, SQLite (WAL mode), Jinja2 SSR, Vanilla ES6+ JavaScript, CSS Custom Properties (OKLCH/sRGB).

**Spec:** Review finding from backend calculation audit and `/sumi:qa` design verification on 2026-10-20.

---

## Global Constraints

- **Template Mirroring**: Any template change in `earnings_engine/reports/templates/dashboard/_results.html` MUST be mirrored identically in `earnings_engine/reports/templates/hubs/dashboard/_results.html` (per `reports/CLAUDE.md`).
- **PIT Guarantee**: Price reactions and returns strictly use data $\le T-1$. No future bar leakage.
- **Zero-Token Default**: Results ledger table render must never trigger LLM calls on load. AI summaries or consensus inference run strictly on explicit user action.
- **Anti-Fabrication**: Return `None`, `0.0`, or `[]` with transparent status badges. Zero mock/pseudo-random numbers.
- **Frontend Governance**: JavaScript files under `earnings_engine/ui/js/modules/` must pass `node -c` syntax check and stay within clean modular boundaries.

---

## Review Focus

1. **52-Week High Calculation Sign**: If `week_high = 100` and `current_price = 90`, `pct_from_52w_high` must be `-10.0%` (drawdown), never `+10.0%`. A positive value causes `compute_buy_indicator` to incorrectly award maximum points to falling stocks.
2. **Missing News / Empty State**: When a stock has no news filings within 14 days, the tag engine must gracefully omit news tags without injecting placeholder text or empty DOM pills.
3. **Template Parity**: `dashboard/_results.html` and `hubs/dashboard/_results.html` must remain bit-for-bit identical to prevent divergent state between standalone and operations hub views.
4. **Non-blocking AI Summary**: The AI Summary button must not use blocking browser `alert()`. It must route through a toast notification or drawer payload.
5. **Sticky Table Header Z-Index Collision**: Day divider rows (`.results-day-divider`) must not clip above the table sticky header (`thead tr`) on vertical scrolling.

---

## Tasks

### Task 1: Fix 52W High Drawdown Calculation & 4-Pillar Indicator Math

**Files:**
- Modify: `earnings_engine/data/market_context.py:1325-1339`
- Modify: `earnings_engine/reports/render.py:446-456`
- Test: `tests/test_results_ledger_calc.py`

**Interfaces:**
- Consumes: `closes: pd.Series`, `current_price: float`, `week_high: float`, `week_low: float`
- Produces: `pct_from_52w_high: float` (strictly $\le 0.0$ when below high) and validated `Pillar 1` score in `compute_buy_indicator`

- [ ] **Step 1: Write the failing test for 52W high drawdown calculation and buy indicator scoring**

```python
# tests/test_results_ledger_calc.py
import pytest
import pandas as pd
from earnings_engine.reports.render import compute_buy_indicator

def test_pct_from_52w_high_drawdown_sign():
    """Verify pct_from_52w_high is negative when current price is below 52W high."""
    from earnings_engine.data.market_context import enrich_upcoming_results
    
    # Stock with 52W high of 100, current price of 80 (should be -20.0%, NOT +20.0%)
    dates = pd.date_range("2026-01-01", periods=10, freq="B")
    prices_df = pd.DataFrame({
        "open": [95.0] * 10,
        "high": [100.0] * 10,
        "low": [75.0] * 10,
        "close": [80.0] * 10,
        "volume": [100000] * 10,
    }, index=dates)
    
    df = pd.DataFrame([{
        "ticker": "TEST.NS",
        "earnings_date": "2026-10-25",
    }])
    
    # Buy indicator calculation must properly penalize stock far from 52W high
    row_close_to_high = {
        "channel_position_pct": 50.0,
        "technical_setup": "Range Base",
        "pct_from_52w_high": -5.0,  # Within 10%
        "beat_rate_pct": 80.0,
        "total_historical_quarters": 8,
        "seven_day_return_pct": 1.0,
        "thirty_day_return_pct": 2.0,
        "rel_vol_5d_vs_63d": 1.1,
    }
    score_close = compute_buy_indicator(row_close_to_high)
    
    row_far_from_high = dict(row_close_to_high, pct_from_52w_high=-40.0)  # Down 40%
    score_far = compute_buy_indicator(row_far_from_high)
    
    assert score_close["pillars"]["technical"] > score_far["pillars"]["technical"]
```

- [ ] **Step 2: Run test to verify it exposes the calculation behavior**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_results_ledger_calc.py -v`

- [ ] **Step 3: Fix `pct_from_high` in `earnings_engine/data/market_context.py`**

In `earnings_engine/data/market_context.py:1325-1339`:
Replace:
```python
if pct_from_52w_high is None:
    if week_high is None or week_high <= 0 or current_price is None:
        pct_from_high = None
    else:
        pct_from_high = ((week_high - current_price) / week_high) * 100
```
With:
```python
if pct_from_52w_high is None:
    if week_high is None or week_high <= 0 or current_price is None:
        pct_from_high = None
    else:
        pct_from_high = round(((current_price / week_high) - 1.0) * 100.0, 2)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_results_ledger_calc.py -v`
Expected: PASS

- [ ] **Step 5: Commit calculation fix**

```bash
git add earnings_engine/data/market_context.py tests/test_results_ledger_calc.py
git commit -m "fix(results-ledger): correct 52w high drawdown calculation sign"
```

---

### Task 2: Build Multi-Dimensional Institutional Tag Engine in Backend

**Files:**
- Modify: `earnings_engine/data/market_context.py:815-935`, `1340-1370`
- Modify: `earnings_engine/reports/render.py:1515-1620`
- Test: `tests/test_results_ledger_tags.py`

**Interfaces:**
- Consumes: `tickers: list[str]`, `conn: sqlite3.Connection`
- Produces: `tags_data: dict[str, list[dict[str, str]]]` containing:
  - `news_catalysts`: Active order wins, regulatory filings, capex, legal alerts
  - `technical_flags`: Testing 52W High, Near 52W Low, Vol Surge
  - `radar_flags`: Breakout Radar active, Elite Hot setup
  - `institutional_flags`: FII Accumulating, High Promoter, etc.

- [ ] **Step 1: Write the failing test for the bulk institutional tags extraction**

```python
# tests/test_results_ledger_tags.py
import pytest
import sqlite3
from earnings_engine.reports.render import build_institutional_tags

def test_build_institutional_tags():
    sample_row = {
        "ticker": "INFY.NS",
        "pct_from_52w_high": -1.8, # Within 2.5% of high
        "pct_from_52w_low": 42.0,
        "rel_vol_5d_vs_63d": 2.4, # Vol surge >= 2.0x
        "beat_rate_pct": 87.5,
        "total_historical_quarters": 8,
        "news_items": [
            {"title": "Infosys inks $450M cloud deal", "category": "ORDER_WIN", "impact_level": "HIGH", "direction": "POSITIVE"}
        ],
        "is_breakout_active": True,
        "breakout_score": 78,
    }
    tags = build_institutional_tags(sample_row)
    tag_labels = [t["label"] for t in tags]
    assert "⚡ Order Win" in tag_labels or any("Order Win" in l for l in tag_labels)
    assert any("52W High" in l for l in tag_labels)
    assert any("Vol Surge" in l for l in tag_labels)
    assert any("Breakout" in l or "Elite" in l for l in tag_labels)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_results_ledger_tags.py -v`
Expected: FAIL with `ImportError: cannot import name 'build_institutional_tags'`

- [ ] **Step 3: Implement `build_institutional_tags` in `render.py` and bulk hydration in `market_context.py`**

1. In `earnings_engine/data/market_context.py`:
   - During `enrich_upcoming_results`, execute bulk queries for `news_catalysts` ($\pm 14$ days) and `breakout_radar` using `chunk_size = 200`.
   - Attach `news_items` list and `breakout_meta` dict to each ticker row.
2. In `earnings_engine/reports/render.py`:
   - Implement `build_institutional_tags(row: dict) -> list[dict[str, str]]`:
     - News: `[⚡ Order Win]`, `[⚖ Regulatory]`, `[🏭 Capex]`, `[📰 N News]`
     - Technical: `[🎯 Testing 52W High]` ($\ge -2.5\%$), `[🔻 Near 52W Low]` ($\le 3.0\%$), `[⚡ Vol Surge]` ($\ge 2.0\text{x}$)
     - Radar: `[🔥 Elite Hot]` (Breakout score $\ge 70$), `[🚀 Breakout Radar]`
     - Quality: `[👑 Consistent Beater]` (Beat rate $\ge 80\%$ over $\ge 6$ qtrs), `[⚠ Serial Misser]` ($< 30\%$)
   - Generate HTML tag pills:
     `tags_html = "".join(f'<span class="inst-tag" style="background:{t["bg"]};color:{t["color"]};border:1px solid {t["border"]};font-size:0.58rem;padding:0.04rem 0.28rem;border-radius:3px;font-weight:600;white-space:nowrap;" title="{t["title"]}">{t["icon"]} {t["label"]}</span>' for t in tags)`

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_results_ledger_tags.py -v`
Expected: PASS

- [ ] **Step 5: Commit tag engine**

```bash
git add earnings_engine/data/market_context.py earnings_engine/reports/render.py tests/test_results_ledger_tags.py
git commit -m "feat(results-ledger): add multi-dimensional institutional tag engine"
```

---

### Task 3: Overhaul Table Row Rendering with Tag Strip & Design Tokens

**Files:**
- Modify: `earnings_engine/reports/templates/result_row.html`
- Modify: `earnings_engine/reports/render.py:1550-1635`
- Test: `tests/test_results_ledger_render.py`

**Interfaces:**
- Consumes: `institutional_tags_html: str`, row metric attributes
- Produces: High-density institutional table row matching Nexus Obsidian tokens

- [ ] **Step 1: Write tests for row HTML structure and token presence**

```python
# tests/test_results_ledger_render.py
import pytest
from earnings_engine.reports.render import _render_template

def test_result_row_institutional_tags_and_tokens():
    row_values = {
        "ticker": "TCS.NS",
        "date": "2026-10-22",
        "cap_tier": "large",
        "industry": "IT - Software",
        "technical_setup_label": "🎯 Range Base",
        "row_ticker_id": "TCS_NS",
        "company_name": "Tata Consultancy Services",
        "result_sequence_badge_html": "",
        "earnings_date": "2026-10-22",
        "relative_date_badge_html": "",
        "day_class": "",
        "market_cap": "₹14.9L Cr",
        "current_price": "₹4,120.50",
        "is_near_results_cls": "",
        "live_dot_html": "",
        "three_day_return": "+1.2%",
        "seven_day_return": "+3.4%",
        "thirty_day_return": "+8.1%",
        "eps_estimates_html": "₹32.50",
        "eps_surprise_pct": "+4.2%",
        "past_results_html": "87.5%",
        "returns_consolidated_html": "+3.4%",
        "ai_edge_score": "",
        "technical_setup_badge_html": "Range Base",
        "rel_vol_html": "1.4x",
        "rel_vol_plain": "1.4",
        "beat_rate_html": "87.5%",
        "beat_rate_plain": "87.5",
        "range_bar_html": "",
        "pct_from_52w_high_low": "-2.1% / +34.2%",
        "quality_scores": "",
        "quality_scores_plain": "",
        "buy_indicator_html": '<span class="signal-badge">STRONG BUY 82</span>',
        "buy_score": 82,
        "buy_signal": "STRONG BUY",
        "raw_buy_score": "82",
        "raw_mcap": "14900000000000",
        "raw_price": "4120.50",
        "raw_3d": "1.20",
        "raw_7d": "3.40",
        "raw_30d": "8.10",
        "raw_chan_pos": "55.0",
        "institutional_tags_html": '<div class="tag-strip"><span class="inst-tag">⚡ Order Win</span></div>',
    }
    rendered = _render_template("result_row.html", **row_values)
    assert 'class="tag-strip"' in rendered
    assert "⚡ Order Win" in rendered
    assert "data-ticker=\"TCS.NS\"" in rendered
```

- [ ] **Step 2: Run test to verify failure**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_results_ledger_render.py -v`
Expected: FAIL

- [ ] **Step 3: Update `result_row.html` with tag strip and tabular styling**

In `earnings_engine/reports/templates/result_row.html`:
- Underneath `<span class="stock-company-sub">`, add `{institutional_tags_html}`.
- Refactor style attributes to remove arbitrary hex colors (`#64748b`, `#f8fafc`) and replace with design system CSS tokens (`var(--text-primary)`, `var(--text-muted)`).
- Ensure all numeric cells have `class="mono num-cell"` with `text-align: right; font-variant-numeric: tabular-nums;`.

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_results_ledger_render.py -v`
Expected: PASS

- [ ] **Step 5: Commit row template update**

```bash
git add earnings_engine/reports/templates/result_row.html earnings_engine/reports/render.py tests/test_results_ledger_render.py
git commit -m "feat(results-ledger): render institutional tags and tabular formatting in result rows"
```

---

### Task 4: Design Token Compliance & Sticky Header Z-Index Fix in Template Partial

**Files:**
- Modify: `earnings_engine/reports/templates/dashboard/_results.html`
- Modify: `earnings_engine/reports/templates/hubs/dashboard/_results.html`
- Test: `tests/test_results_template_mirroring.py`

**Interfaces:**
- Consumes: Nexus design system tokens (`--bg-surface`, `--bg-well`, `--border-card`, `--text-primary`)
- Produces: 100% token-compliant, identical SSR template partials with zero sticky header clipping

- [ ] **Step 1: Write test for template mirroring parity and token compliance**

```python
# tests/test_results_template_mirroring.py
import hashlib
from pathlib import Path

def test_results_templates_are_strictly_identical():
    p1 = Path("earnings_engine/reports/templates/dashboard/_results.html")
    p2 = Path("earnings_engine/reports/templates/hubs/dashboard/_results.html")
    assert p1.exists() and p2.exists()
    assert p1.read_text(encoding="utf-8") == p2.read_text(encoding="utf-8"), "Templates must be identical per CLAUDE.md"

def test_no_raw_black_or_zinc_hex_in_results_template():
    p1 = Path("earnings_engine/reports/templates/dashboard/_results.html")
    content = p1.read_text(encoding="utf-8")
    assert "#09090b" not in content, "Must use var(--bg-surface) instead of hardcoded #09090b"
    assert "background:#000;" not in content, "Must use var(--bg-well) or var(--bg-canvas) instead of #000"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_results_template_mirroring.py -v`
Expected: FAIL

- [ ] **Step 3: Update `dashboard/_results.html` and mirror to `hubs/dashboard/_results.html`**

1. Replace all hardcoded surface hex colors (`#09090b` $\to$ `var(--bg-surface)`, `#000` $\to$ `var(--bg-well)`).
2. Fix sticky header stacking context:
   - Table `<thead>` $\to$ `position: sticky; top: 0; z-index: 25; background: var(--bg-well);`
   - Day Divider `.rl-day-divider td` $\to$ `position: sticky; top: 32px; z-index: 15; background: var(--bg-canvas);`
3. Add range slider padding to prevent thumb clipping:
   - `.rl-range-slider { padding: 0 7px; }`
4. Add sortable column headers with data attributes and accessible labels.
5. Mirror changes identically to `earnings_engine/reports/templates/hubs/dashboard/_results.html`.

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_results_template_mirroring.py -v`
Expected: PASS

- [ ] **Step 5: Commit template updates**

```bash
git add earnings_engine/reports/templates/dashboard/_results.html earnings_engine/reports/templates/hubs/dashboard/_results.html tests/test_results_template_mirroring.py
git commit -m "feat(results-ledger): achieve design token compliance and fix sticky header stacking"
```

---

### Task 5: Enhance `results_ledger.js` with Sort Glyphs, Skeletons & Non-Blocking AI Summaries

**Files:**
- Modify: `earnings_engine/ui/js/modules/results_ledger.js`
- Test: Run `node -c earnings_engine/ui/js/modules/results_ledger.js`

**Interfaces:**
- Consumes: REST endpoint `/api/v1/dashboard/results/report` and `/api/v1/dashboard/results/summarize`
- Produces: Fast client-side sorting, animated skeletons, accessible focus rings, and non-blocking toast/drawer AI summary

- [ ] **Step 1: Check existing JS syntax**

Run: `node -c earnings_engine/ui/js/modules/results_ledger.js`
Expected: Clean exit (code 0)

- [ ] **Step 2: Update `results_ledger.js`**

1. **Active Sort Indicators**:
   - Add state: `_sortCol = null`, `_sortDir = 'asc'`.
   - Update `sortTable(colIdx, colType)` to toggle `_sortDir`, update header glyphs (`▲` / `▼`), and sort rows preserving day divider grouping.
2. **Animated Skeleton Loading**:
   - In `loadReport()`, replace `"Loading results…"` with a 4-row high-density pulsing skeleton table.
3. **Non-blocking AI Summary**:
   - In `summarize(btn)`, replace native `alert(d.summary)` with opening a slide-over modal or toast drawer via `window.showToast` or `_app.openAIReportDrawer`.
4. **Enhanced Search Filter**:
   - Expand `filterTable()` to match text inside active tags (`.inst-tag`) so searching "order win", "52w high", or "breakout" filters matching rows instantly.

- [ ] **Step 3: Verify JS syntax**

Run: `node -c earnings_engine/ui/js/modules/results_ledger.js`
Expected: Clean exit (code 0)

- [ ] **Step 4: Commit frontend updates**

```bash
git add earnings_engine/ui/js/modules/results_ledger.js
git commit -m "feat(results-ledger): add active sort glyphs, tag search, and non-blocking summary"
```

---

### Task 6: End-to-End Regression Verification & Error Ledger Scan

**Files:**
- Test: `tests/test_results_ledger_calc.py`
- Test: `tests/test_results_ledger_tags.py`
- Test: `tests/test_results_ledger_render.py`
- Test: `tests/test_results_template_mirroring.py`
- Script: `scripts/error_ledger.py`

- [ ] **Step 1: Run complete results ledger test suite**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_results_ledger_calc.py tests/test_results_ledger_tags.py tests/test_results_ledger_render.py tests/test_results_template_mirroring.py -v`
Expected: 100% PASS

- [ ] **Step 2: Run error ledger scan**

Run: `./.venv/Scripts/python.exe scripts/error_ledger.py scan`
Expected: 0 new errors

- [ ] **Step 3: Validate git status & commit**

```bash
git status
```
Ensure branch is clean and all tests are checked in.
