# Implementation Plan: Institutional Results Breakout Radar Transformation

> **Subsystem**: Breakout Hub (`#breakout`) · Subtab: Results Radar (`breakoutResultsContainer`)  
> **Source of Truth**: `earnings_breakout_scanner.py`, `results_breakout.js`, `_breakout.html`  
> **Standards Compliance**: Zero Fabricated Data, Strict Point-in-Time (PIT), High-Resolution 2K Design System, Sumi QA Standards.

---

## 1. Problem Statement & Root Cause Diagnosis

The Results Breakout Radar scans recent (-3D default) and upcoming (+7D default) quarterly earnings releases for high-probability breakout patterns (Result-Day High Expansion, Post-Earnings Announcement Drift, Pre-Earnings Volatility Coil, Dip Absorption Recovery). 

While the backend engine (`earnings_breakout_scanner.py`) calculates rich quantitative metrics for 400+ stocks, **more than 80% of data points fail to render or display `NaN` / `—`** in the UI due to property key discrepancies between the Python dictionary and JavaScript consumer:

1. **`NaN` in Timing Badges & Headers**:
   - Backend returns `item.days_relative` (negative for past, positive for future).
   - Frontend accesses `item.days_since_result` (which evaluates to `undefined`).
   - `Math.abs(undefined)` produces `NaN`, resulting in `🟢 -NaND` or `Declared NaN Days Ago`.
2. **Blank Ticker Column**:
   - Frontend looks up `item.symbol`.
   - Backend only provides `item.ticker` (`TCS.NS`), leaving `item.symbol` undefined and the column cell blank.
3. **Empty Data Cells (`—`) in Table & Inspector**:
   - `item.trade_levels?.breakout_trigger` vs `item.breakout_trigger` (at root).
   - `item.trade_levels?.dist_to_trigger_pct` vs `item.pct_from_trigger` (at root).
   - `item.technicals?.volume_ratio_20d` vs `item.technicals.volume_ratio`.
   - `rs.reaction_day_ret_pct` vs `rs.reaction_day_return_pct`.
   - `rs.pre_close` vs `rs.pre_result_close`.
   - `tech.resistance_20d` vs `tech.high_20d`.
   - `tech.atr_14d` vs `tech.atr_val`.
   - `tl.suggested_entry` vs `tl.ideal_entry`.
   - `tl.target_1` / `tl.target_2` vs `tl.target_price`.
4. **All 5 Top KPI Cards Display `—`**:
   - Backend keys: `summary.declared_count`, `summary.upcoming_count`, `summary.breaking_out_count`, `total_candidates` (at root).
   - Frontend looks for: `summary.declared_results`, `summary.upcoming_results`, `summary.hot_setups`, `summary.total_candidates`, `summary.top_conviction_score`.
5. **Lack of Institutional Desk Features**:
   - No interactive column sorting (sorting by Score, Proximity to RDH, Volume Multiple, or Timing).
   - No quick-filter buttons for `Declared` vs `Upcoming` results.
   - Inspector lacks a visual breakout proximity gauge, Risk/Reward visualization, and position sizing calculation.
   - Template styles use hardcoded colors rather than design system tokens from `variables.css`.

---

## 2. Institutional Architecture & Target State

```
┌────────────────────────────────────────────────────────────────────────────────────────────────┐
│ TOP CONTROL TOOLBAR: Window Inputs (-3D/+7D), Presets, Timing Pills, Archetype, Min Score, Search │
├────────────────────────────────────────────────────────────────────────────────────────────────┤
│ KPI SUMMARY STRIP: Total Pool │ Declared Results │ Upcoming Results │ Breaking Out │ Top Score │
├────────────────────────────────────────────────────────┬───────────────────────────────────────┤
│ LEFT 50%: Interactive Sortable Results Table           │ RIGHT 50%: Sticky Anatomy Inspector   │
│ - Ticker Symbol & Company Subtitle                     │ - Stock Header + Conviction Score Ring│
│ - Timing Badge (🟢 -2D Declared / ⏳ +4D Upcoming)       │ - Visual Breakout Proximity Gauge     │
│ - Archetype Tag (RDH Expansion, PEAD Drift, etc.)      │ - Trade Execution Blueprint           │
│ - CMP & Breakout Trigger (RDH / 20D Resistance)        │   (Entry, SL, Target 1, Target 2, RRR)│
│ - Dist to Trigger % (color-coded proximity)            │ - Forensic Earnings Structure         │
│ - Volume Surge (e.g. 3.42x vs 20D avg)                 │   (RDH, RDL, Gap %, Reaction Return)  │
│ - Conviction Score Pill (0-100)                        │ - Catalyst, Surprise & Squeeze Telemetry│
│ - Fast Inspect Action Button                           │ - Action Hub: Open Terminal / Watchlist│
└────────────────────────────────────────────────────────┴───────────────────────────────────────┘
```

---

## 3. Detailed Step-by-Step Implementation Tasks

### Task 1: Backend Scanner Data Contract Enrichment (`earnings_breakout_scanner.py`)
- Populate `symbol` alongside `ticker` (e.g. `ticker.split('.')[0]`).
- Cast all NumPy floats (`np.float64`) to Python native `float` to eliminate JSON serialization quirks.
- Add dual-key aliases in candidate dictionary:
  - `days_since_result`: `days_rel`
  - `pct_from_trigger` and `dist_to_trigger_pct`
  - In `trade_levels`:
    - `breakout_trigger`: `breakout_trigger`
    - `dist_to_trigger_pct`: `pct_from_trigger`
    - `suggested_entry`: `ideal_entry`
    - `target_1`: `target_price` (+1.5 ATR)
    - `target_2`: round(ideal_entry + 3.0 * atr_val, 2)
  - In `technicals`:
    - `volume_ratio_20d`: `volume_ratio`
    - `resistance_20d`: `high_20d`
    - `atr_14d`: `atr_val`
    - `squeeze_on`: bool check (Bollinger Band bandwidth <= Keltner Channel bandwidth)
  - In `result_structure`:
    - `pre_close`: `pre_result_close`
    - `reaction_day_ret_pct`: `reaction_day_return_pct`
- Enrich `summary` dictionary with both naming conventions:
  - `total_candidates`: count
  - `declared_results`: `declared_count`
  - `upcoming_results`: `upcoming_count`
  - `hot_setups`: count of candidates with score >= 60
  - `breaking_out_count`: count of candidates where `current_price >= breakout_trigger`
  - `top_conviction_score`: highest score among candidates or `None`

### Task 2: Frontend View Controller Refactor (`results_breakout.js`)
- Standardize all number formatting with safe helpers (`_fmtPrice`, `_fmtPct`, `_fmtNum`, `_fmtRatio`) that gracefully handle `null`, `undefined`, and `NaN`.
- Implement robust property access with fallback chaining:
  - `const symbol = item.symbol || (item.ticker ? item.ticker.split('.')[0] : '—');`
  - `const days = item.days_since_result ?? item.days_relative ?? 0;`
  - `const trigger = item.breakout_trigger ?? item.trade_levels?.breakout_trigger;`
  - `const dist = item.pct_from_trigger ?? item.trade_levels?.dist_to_trigger_pct;`
  - `const volSurge = item.technicals?.volume_ratio ?? item.technicals?.volume_ratio_20d;`
- Add Client-Side Multi-Column Sorting:
  - State: `app._resultsSort = { field: 'score', asc: false };`
  - Sorting supported on: `ticker`, `timing`, `price`, `trigger`, `dist`, `volume`, `score`.
  - Column header click handler: `app.sortResultsRadar(field)`.
- Add Timing Quick-Filter:
  - Filter state: `app._resultsTimingFilter = 'ALL';` (`ALL`, `DECLARED`, `UPCOMING`).
  - Integrated into `app.filterResultsRadar()`.
- Upgrade Candidate Anatomy Inspector (Right Pane):
  - Company & Symbol Header with Sector badge and Timing Pill.
  - Interactive Breakout Gauge (displaying relative position between 20D Low, Current Price, Breakout Trigger, and Target).
  - High-density Trade Execution Blueprint:
    - Entry, Stop Loss, Target 1 (+1.5 ATR), Target 2 (+3.0 ATR).
    - Risk/Reward ratio badge (`1 : X.X`).
  - Earnings Reaction Anatomy:
    - Result-Day High (RDH), Result-Day Low (RDL), Pre-Result Close, Reaction Day Gap %, Reaction Day Return %.
  - Fundamental Catalyst & Technical Telemetry:
    - EPS Reported vs Estimate, Surprise %, 14D ATR, 20D Resistance, 52W High, Squeeze status.
  - Action buttons wired directly to `app.openStockDetail('NSE', ticker)` and `app.toggleWatchlist(ticker)`.

### Task 3: Mirrored Template Alignment (`_breakout.html`)
- Synchronize both templates:
  1. `earnings_engine/reports/templates/dashboard/_breakout.html`
  2. `earnings_engine/reports/templates/hubs/dashboard/_breakout.html`
- Update table headers with clickable sort controls and indicator spans.
- Add Timing Filter toggle pill group (`All`, `🟢 Declared (-D)`, `⏳ Upcoming (+D)`).
- Ensure CSS styling leverages design system tokens (`var(--bg-well)`, `var(--bg-surface)`, `var(--border-subtle)`, `var(--color-bullish)`, `var(--color-bearish)`).
- Add responsive media query for split-container to collapse cleanly on screens under 1100px.

### Task 4: Verification, Quality Assurance & Anti-Fabrication
- Validate Python backend returns 100% valid, real, non-fabricated data with zero NaNs or null crashes.
- Validate JavaScript syntax using `node -c earnings_engine/ui/js/modules/results_breakout.js`.
- Run pytest suite for breakout and scanner endpoints.
- Check template diff to verify exact mirroring between dashboard and hub templates.
- Update Memory documentation.

---

## 4. Verification Checklist
- [ ] No `NaN` appears anywhere in table or inspector (timing badges, percentages, price levels).
- [ ] Every cell in the 9-column table renders real data (Symbol, Timing, Archetype, CMP, Trigger, Dist, Vol Surge, Score, Action).
- [ ] All 5 top KPI summary cards display live counts.
- [ ] Clicking table headers sorts ascending/descending.
- [ ] Timing pills filter correctly between All, Declared, and Upcoming setups.
- [ ] Clicking any row loads the detailed setup anatomy in the right inspector.
- [ ] Action buttons ("Open Stock Terminal" and "Watch") work as expected.
- [ ] Zero mock/fabricated fallbacks.
- [ ] Both template files are byte-for-byte identical.
