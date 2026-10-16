# Results Breakout Radar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a dedicated Results Breakout Radar for stocks declaring earnings in a user-configurable window (default: -3 to +7 days) with result-specific technical levels, 4 setup archetypes, an API endpoint, and a 50-50 split-screen UI inside the Breakout Hub.

**Architecture:** A fast, on-demand quantitative scanning module queries `earnings_history` across SQLite pools to filter eligible tickers, batch-loads price candles, and calculates Result-Day High (RDH), Result-Day Low (RDL), pre-result close, gap %, reaction %, and volume surge. It classifies stocks into 4 setup archetypes (`RDH_EXPANSION`, `PEAD_MOMENTUM`, `PRE_EARNINGS_COIL`, `POST_RESULT_RECOVERY`) with composite scoring (0–100) and trade levels. Exposed via `GET /api/breakout/results-radar` and rendered in a dedicated subtab under Breakout Radar with steppers, presets, filters, and a sticky inspector drawer.

**Tech Stack:** Python 3.11+, FastAPI, SQLite, Pandas, NumPy, HTML5/CSS3 (Jinja2), Vanilla ES6 JavaScript (modular architecture).

**Spec:** `docs/superpowers/specs/2026-10-16-results-breakout-radar-design.md`

## Global Constraints

- Python interpreter: `./.venv/Scripts/python.exe` (forward slashes in bash).
- Branch: Work directly on `new_report`.
- Anti-fabrication: Zero mock or synthetic data. Return truthful empty state (`total_candidates: 0`, `items: []`) if no stocks declare earnings in the window.
- Template mirroring: `earnings_engine/reports/templates/dashboard/_breakout.html` and `earnings_engine/reports/templates/hubs/dashboard/_breakout.html` must remain synchronized and identical.
- Frontend modularity: Javascript modules must stay under 500 lines and pass syntax validation with `node -c`.
- Error ledger: Run `scripts/error_ledger.py scan` after changes to verify zero regressions.

## Review Focus

1. **Empty window results**: When no stocks declare earnings in the given window (e.g. over holiday/off-season periods), the API returns a structured empty payload (`total_candidates: 0`, `items: []`) and UI shows a clean empty state without crashing or throwing null reference errors.
2. **Missing or single-day price data**: When a freshly listed IPO or illiquid stock has fewer than 20 price bars, the scanner safely handles `None` values for 20D SMA / ATR / 52W high without division-by-zero or NaN in JSON responses.
3. **Boundary dates & post-market announcements**: For earnings announced today after 15:30 IST, ensure reaction calculations treat the next trading session as the reaction candle rather than corrupting pre-result close.
4. **Invalid range parameters**: If a user enters negative future days or `past_days > 30`, the API enforces validation constraints (`ge=0, le=30`) returning HTTP 422 instead of unbounded DB queries.
5. **Subtab state persistence & tab navigation**: Switching between `Active Setup Pool`, `Results Breakout`, and `Tracked Archive` updates browser hash/localStorage cleanly without DOM ID conflicts or memory leaks in interval timers.

---

### Task 1: Results Breakout Quantitative Scanner Engine

**Files:**
- Create: `earnings_engine/data/earnings_breakout_scanner.py`

**Interfaces:**
- Consumes:
  - `earnings_engine.config.Settings`
  - `earnings_engine.data.earnings._connect`
  - `earnings_engine.data.prices.load_prices_batch`
  - `earnings_engine.data.industry.get_industry_map`
  - `earnings_engine.data.universe.resolve_universe`
- Produces:
  - `get_results_breakout_candidates(settings: Settings | None, past_days: int = 3, future_days: int = 7, archetype: str = "ALL", min_score: int = 30, universe: str = "all", now: datetime | None = None) -> dict[str, Any]`

- [ ] **Step 1: Write `earnings_breakout_scanner.py` with date-window filtering, reference levels, and scoring**

```python
"""Quantitative scanner for earnings results breakout setups.

Evaluates stocks reporting results in a configurable window [-past_days, +future_days]
relative to today, computing Result-Day High (RDH), Result-Day Low (RDL), reaction %,
volume ratios, setup archetypes, and composite conviction scores.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any
import numpy as np
import pandas as pd

from earnings_engine.config import Settings
from earnings_engine.data import prices as prices_mod
from earnings_engine.data.earnings import _connect as _earnings_connect
from earnings_engine.data.industry import get_industry_map
from earnings_engine.data.universe import resolve_universe

VALID_ARCHETYPES = {
    "ALL",
    "RDH_EXPANSION",
    "PEAD_MOMENTUM",
    "PRE_EARNINGS_COIL",
    "POST_RESULT_RECOVERY",
}

ARCHETYPE_METADATA = {
    "RDH_EXPANSION": {
        "label": "RDH Expansion",
        "badge": "RDH Breakout",
        "desc": "Testing or breaking above the Result-Day High candle.",
    },
    "PEAD_MOMENTUM": {
        "label": "PEAD Drift",
        "badge": "PEAD Momentum",
        "desc": "Post-Earnings Announcement Drift continuation on above-average volume.",
    },
    "PRE_EARNINGS_COIL": {
        "label": "Pre-Earnings Coil",
        "badge": "Pre-Earnings Coil",
        "desc": "Consolidating within striking distance of resistance ahead of results.",
    },
    "POST_RESULT_RECOVERY": {
        "label": "Post-Result Recovery",
        "badge": "Dip Absorption",
        "desc": "Knee-jerk dip absorbed, reclaiming the pre-result pivot level.",
    },
}
```

Implement `_load_window_earnings(settings, start_date, end_date, tickers)`:
Query `earnings_history` joined with tickers for `earnings_date BETWEEN ? AND ?`.
Batch load prices via `prices_mod.load_prices_batch(unique_tickers, settings)`.
Calculate for each ticker:
- Pre-result close $P_{\text{pre}}$, Result Day High ($RDH$), Result Day Low ($RDL$).
- Gap %, Reaction Day Return %, Intraday Recovery %.
- 20D SMA, 20D Volume Avg, ATR(14), 20D High, 52W High.
- Archetype classification:
  - If `is_declared`:
    - If `current_price >= RDH * 0.98` and `volume_ratio >= 1.2` $\rightarrow$ `RDH_EXPANSION`.
    - If `reaction_day_return_pct > 2.5` or `surprise_pct > 0` and `current_price >= pre_result_close` $\rightarrow$ `PEAD_MOMENTUM`.
    - If `reaction_day_gap_pct < -2.0` and `current_price >= pre_result_close` $\rightarrow$ `POST_RESULT_RECOVERY`.
    - Else fallback to `RDH_EXPANSION` or `PEAD_MOMENTUM` based on reaction sign.
  - If `not is_declared`:
    - `PRE_EARNINGS_COIL`.
- Composite score (0 to 100) combining Resistance Proximity (30), Volume (25), Surprise/Quality (20), Volatility/Squeeze (15), Reaction Retention (10).
- Trade levels: Ideal Entry, Target Price (trigger + 2*ATR), Stop Loss (trigger - 1.5*ATR), R:R.

- [ ] **Step 2: Syntax & import check**
Run: `./.venv/Scripts/python.exe -c "import earnings_engine.data.earnings_breakout_scanner as ebs; print(ebs.VALID_ARCHETYPES)"`
Expected: Output prints set of valid archetypes without error.

---

### Task 2: Scanner Unit & Edge-Case Tests

**Files:**
- Create: `tests/test_earnings_breakout_scanner.py`

- [ ] **Step 1: Write comprehensive pytest suite covering:**
  1. `test_empty_window`: Empty DB returns `total_candidates == 0` and empty list.
  2. `test_declared_rdh_expansion`: Synthetic price series where current price breaches RDH with volume surge, confirming archetype `RDH_EXPANSION` and high composite score.
  3. `test_upcoming_pre_earnings_coil`: Future earnings date within 7 days, price coiling near 20D high, confirming archetype `PRE_EARNINGS_COIL`.
  4. `test_post_result_recovery`: Gap down -3% followed by recovery above pre-close, confirming `POST_RESULT_RECOVERY`.
  5. `test_pead_momentum`: Strong positive surprise with steady uptrend, confirming `PEAD_MOMENTUM`.
  6. `test_insufficient_bars_edge_case`: Stock with only 3 bars handles ATR/SMA gracefully without exception.

- [ ] **Step 2: Run pytest**
Run: `./.venv/Scripts/python.exe -m pytest tests/test_earnings_breakout_scanner.py -v`
Expected: All tests PASS.

- [ ] **Step 3: Commit**
```bash
git add earnings_engine/data/earnings_breakout_scanner.py tests/test_earnings_breakout_scanner.py
git commit -m "feat(breakout): add Results Breakout Radar quantitative scanner engine

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 3: FastAPI Router Endpoint

**Files:**
- Modify: `earnings_engine/api/routers/breakout.py`

**Interfaces:**
- Consumes:
  - `earnings_engine.data.earnings_breakout_scanner.get_results_breakout_candidates`
- Produces:
  - Endpoint `GET /api/breakout/results-radar`

- [ ] **Step 1: Add `/results-radar` route to `earnings_engine/api/routers/breakout.py`**
Define route before any parameterized routes:
```python
@router.get("/results-radar")
def get_results_breakout_radar(
    past_days: int = Query(3, ge=0, le=30, description="Past calendar days of declared results to scan"),
    future_days: int = Query(7, ge=0, le=30, description="Future calendar days of upcoming results to scan"),
    archetype: str = Query("ALL", description="Filter by archetype: ALL, RDH_EXPANSION, PEAD_MOMENTUM, PRE_EARNINGS_COIL, POST_RESULT_RECOVERY"),
    min_score: int = Query(30, ge=0, le=100, description="Minimum composite breakout score cutoff"),
    universe: str = Query("all", description="Universe filter (nse_large_cap, nse_mid_cap, nifty_50, all)"),
) -> dict[str, Any]:
    """Return dedicated results breakout radar setups for stocks reporting in [-past_days, +future_days]."""
    ...
```

- [ ] **Step 2: Verify router loads without error**
Run: `./.venv/Scripts/python.exe -c "from earnings_engine.api.routers.breakout import router; print([r.path for r in router.routes if 'results-radar' in r.path])"`
Expected: Output prints `['/results-radar']`.

---

### Task 4: API Endpoint Integration Tests

**Files:**
- Create: `tests/test_breakout_results_radar_api.py`

- [ ] **Step 1: Write integration tests using `starlette.testclient.TestClient`:**
  - Test valid request with default parameters: returns status 200, contains `status: "ok"`, `window`, `summary`, `items`.
  - Test custom `past_days=5&future_days=10&archetype=RDH_EXPANSION`.
  - Test bounds validation: `past_days=-1` and `future_days=45` return HTTP 422 Unprocessable Entity.

- [ ] **Step 2: Run pytest**
Run: `./.venv/Scripts/python.exe -m pytest tests/test_breakout_results_radar_api.py -v`
Expected: PASS.

- [ ] **Step 3: Commit**
```bash
git add earnings_engine/api/routers/breakout.py tests/test_breakout_results_radar_api.py
git commit -m "feat(api): expose /api/breakout/results-radar endpoint

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 5: Frontend Template Subtab Markup

**Files:**
- Modify: `earnings_engine/reports/templates/dashboard/_breakout.html`
- Modify: `earnings_engine/reports/templates/hubs/dashboard/_breakout.html` (must be identical)

- [ ] **Step 1: Add subtab navigation header button**
In the subtab switcher header in `_breakout.html`:
Add button `#btnBreakoutSubtabResults` labeled `📊 Results Radar` alongside Scanner, Backtest, and Tracked Archive.

- [ ] **Step 2: Add container `#breakoutResultsContainer` with 50-50 split screen**
- Control Toolbar:
  - Range Inputs: `Past Days: [-3]` and `Future Days: [+7]`.
  - Preset Chips: `[-3 to +7] (Default)`, `[-1 to +3] (Earnings Week)`, `[-7 to +7] (Bi-Weekly)`, `[0 to +10] (Upcoming)`, `[-10 to 0] (Declared PEAD)`.
  - Archetype filter select: `All Archetypes`, `RDH Expansion`, `PEAD Drift`, `Pre-Earnings Coil`, `Dip Recovery`.
  - Tier filter select: `All Tiers`, `Hot Only (≥60)`, `Warm Only (≥30)`.
  - Universe select.
  - Refresh button `⚡ Rescan Window`.
- Left Pane (`#resultsBreakoutTableContainer`): High-density data table.
  - Columns: Ticker, Status/Timing, Score/Tier, Archetype, Trigger & Dist %, Reaction %, Volume Ratio, Surprise %, Actions.
- Right Pane (`#resultsBreakoutInspectorContainer`): Sticky Result & Setup Anatomy card.
  - Header: Symbol, Name, Price, Trigger Distance, Target/Stop R:R.
  - Result Reaction Timeline Card: $P_{\text{pre}} \rightarrow \text{Gap} \rightarrow RDH/RDL \rightarrow \text{Current}$.
  - Setup Diagnosis & Rationale.
  - Fundamentals & Quality Snapshot.

- [ ] **Step 3: Mirror changes to `earnings_engine/reports/templates/hubs/dashboard/_breakout.html`**
Verify zero diff between the two files.

---

### Task 6: Frontend Results Breakout Module & Subtab Switcher

**Files:**
- Create: `earnings_engine/ui/js/modules/results_breakout.js`
- Modify: `earnings_engine/ui/js/modules/tracked_breakouts.js` (add `'results'` subtab handling)
- Modify: `earnings_engine/ui/js/dashboard.js` (add module to `'breakout'` load bundle)
- Modify: `earnings_engine/reports/templates/dashboard/_script_tags.html` and `hubs/dashboard/_script_tags.html`

- [ ] **Step 1: Write `results_breakout.js`**
- Manages state: `past_days`, `future_days`, `archetype`, `tier`, `universe`, `data`, `selected_ticker`.
- `loadResultsBreakout()`: Fetches `/api/breakout/results-radar`.
- `renderTable()`: Renders interactive rows with sorting, timing chips, archetype badges.
- `selectRow(ticker)`: Populates the inspector drawer with reaction timeline, levels, and rationale.
- `setPreset(past, future)`: Updates inputs and triggers fetch.
- `onArchetypeChange(val)`, `onTierChange(val)`.

- [ ] **Step 2: Update `tracked_breakouts.js`**
Update `switchBreakoutSubtab(subtab)` to handle `subtab === 'results'`:
- Shows `#breakoutResultsContainer`.
- Highlights `#btnBreakoutSubtabResults`.
- Updates context label to `📊 Results Breakout Radar`.
- Calls `window.resultsBreakout && window.resultsBreakout.init()`.

- [ ] **Step 3: Validate syntax of all modified/created JS files**
Run: `node -c earnings_engine/ui/js/modules/results_breakout.js`
Run: `node -c earnings_engine/ui/js/modules/tracked_breakouts.js`
Run: `node -c earnings_engine/ui/js/dashboard.js`
Expected: Zero syntax errors.

---

### Task 7: Full System Verification, Linting, & Commit

- [ ] **Step 1: Run complete test suite for breakout subsystem**
Run: `./.venv/Scripts/python.exe -m pytest tests/test_earnings_breakout_scanner.py tests/test_breakout_results_radar_api.py -v`
Expected: 100% PASS.

- [ ] **Step 2: Check error ledger and git diff**
Run: `./.venv/Scripts/python.exe scripts/error_ledger.py scan`
Run: `git status`
Expected: Zero open regressions in ledger, clean working tree ready for commit.

- [ ] **Step 3: Commit and push**
```bash
git add .
git commit -m "feat(breakout): implement Results Breakout Radar for -3 to +7 days window

Co-Authored-By: Claude Code <noreply@anthropic.com>"
git push origin new_report
```
