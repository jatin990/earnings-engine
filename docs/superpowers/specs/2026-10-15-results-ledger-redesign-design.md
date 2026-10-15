# Results Ledger Redesign — Design Spec

**Date:** 2026-10-15  
**Status:** Approved

---

## 1. Goal

Redesign the Results Ledger tab (Corporate Earnings Calendar) with a black-and-white glossy terminal aesthetic matching the Institutional Intelligence page. Delete the existing template and JavaScript; replace with a focused, modular implementation. Same + more data. Colours strictly ≤ 4.

---

## 2. Design Language — "Institutional Monochrome"

### 2.1 Palette (4 colours max)

| Token | Value | Role |
|---|---|---|
| **Ink** | `#000000` / `#09090b` | All surfaces, table backgrounds |
| **Pearl** | `#f8fafc` / `#94a3b8` | Primary text / secondary/meta text |
| **Emerald** | `#34d399` / `rgba(52,211,153,0.15)` | Beat, positive return, up signal |
| **Rose** | `#fb7185` / `rgba(251,113,133,0.15)` | Miss, negative return, down signal |

No blues, cyans, purples, or amber anywhere in the Results Ledger. Semantic green/red on delta cells only. All other UI chrome is pure monochrome.

### 2.2 Surface & Border System

- Base canvas: `#000000`
- Card/container: `#09090b` with `border: 1px solid rgba(255,255,255,0.08)`
- Table header row: `background: #000000; color: #94a3b8` (monochrome mono text)
- Table body rows: alternate `background: transparent` / `background: rgba(255,255,255,0.025)` — no explicit colour class
- Separator between day groups: `border-top: 1px solid rgba(255,255,255,0.06)` — not a big box
- Glossy inset highlight: `inset 0 1px 0 rgba(255,255,255,0.06)` on the outermost container only

### 2.3 Typography

- Labels/headers: `font-family: var(--font-heading)` (`Space Grotesk`)
- Mono data: `font-family: var(--font-mono)` (`JetBrains Mono`)
- Uppercase column labels: `letter-spacing: 0.06em; font-size: 0.66rem`

---

## 3. Layout Architecture

```
┌──────────────────────────────────────────────────────────────┐
│ SECTION HEADER (slim 1-line)                                 │
│  "Results Ledger" [badge: N results · M dates]   [controls] │
├──────────────────────────────────────────────────────────────┤
│ RANGE CONTROL STRIP (single row)                             │
│  Preset chips  │  Dual-thumb slider  │  Market▼  │  Actions  │
├───────────┬────────────────┬────────────────────────────────┤
│  Month    │  This Month    │  Next Month                     │
│  (past)   │  (current)     │  (upcoming)  — inline stat row  │
├──────────────────────────────────────────────────────────────┤
│ TOOLBAR (no background — just border-bottom)                 │
│  🔍 filter  │  Industries▼  │  Cap: All|Large|Small │ Dense  │
├──────────────────────────────────────────────────────────────┤
│ DATE CHIP RAIL (rendered after load)                         │
│  All · Oct 16 · Oct 17 · Oct 18 · …                         │
├──────────────────────────────────────────────────────────────┤
│ TABLE (full-width, flat, no nested cards)                    │
│  sticky thead: TICKER│DATE│PRICE/CAP│EPS EST│BEAT│SURPRISE% │
│               RETURNS│EDGE│SETUP│S/R RANGE│52W│REL VOL      │
│  day-group divider rows (date label, not a container)        │
│  stock rows (click → existing slide-over drawer)             │
└──────────────────────────────────────────────────────────────┘
```

No `<section class="card">` wrapping the whole table. The outermost container is a single thin-bordered shell. Day groups are **divider rows inside `<tbody>`**, not nested `<details>` or `<section>` elements.

---

## 4. Range Control — Dual-Thumb Slider

The range control replaces the `<select>` preset dropdown with:

1. **Preset chips** (horizontal pill row): `Upcoming 3D`, `Upcoming 7D`, `Recent ±`, `±1M`, `±2M`, `Custom` — clicking a chip sets both slider thumbs and the badge.
2. **Dual-thumb range slider**: two `<input type="range">` overlaid on a single track using the CSS stacking trick.
   - Left thumb → `pastDays` (0–180)
   - Right thumb → `aheadDays` (1–90)
   - Live badge below track: `Past 30D · Ahead 7D`
3. Custom drag disables all preset chips (shows `⚙ Custom` chip as active).
4. The hidden text inputs `resultsPastDays` / `resultsDays` are replaced by data attributes on the slider container so the existing `loadResultsReport()` API call shape is unchanged: `?days=<ahead>&past_days=<past>`.

---

## 5. Month Summary Strip (replaces 3 large coloured cards)

Three inline stat cells separated by hairline dividers inside one slim strip container:

```
│ LAST MONTH        │ THIS MONTH         │ NEXT MONTH         │
│ Oct 2026          │ Nov 2026           │ Dec 2026           │
│ 42  Reported      │ 18  Active Season  │ 31  Scheduled      │
│ [Past]            │ [Active] [Drill]   │ [Pipeline] [Drill] │
```

- No coloured top borders, no backdrop-filter blobs.
- Click on the entire cell filters the table to that month (same logic as `filterResultsByMonth()`).
- Drilldown button calls `openResultsMonthModal()` (existing, unchanged).
- When no data: show `—` in count, text dim.

---

## 6. Table Columns

### 6.1 Existing columns (kept)

| # | Column | Data source |
|---|---|---|
| 1 | Ticker + Company | `ticker`, `company_name` |
| 2 | Earnings Date | `earnings_date` + relative badge (Today / T+1 etc.) |
| 3 | Price / Market Cap | `current_price`, `market_cap` |
| 4 | EPS Estimates | `eps_estimates_html` (server-rendered) |
| 5 | Historical Beat | `past_results_html` (server-rendered beat-rate) |
| 6 | Returns (7D/30D/3D) | `returns_consolidated_html` |
| 7 | Technical Setup | `technical_setup_badge_html` |
| 8 | S/R Range Bar | `range_bar_html` |
| 9 | 52-Week | `pct_from_52w_high_low` |
| 10 | Rel Vol | `rel_vol_html` |

### 6.2 New columns (added)

| # | Column | Source | Notes |
|---|---|---|---|
| 11 | **Surprise %** | `eps_surprise_pct` from `result_row.html` template field `{eps_surprise_pct}` | Shown only when `> 0 days` from result (past events). Green if beat, rose if miss. Format: `+4.2%` / `-1.8%`. Blank for upcoming events. |
| 12 | **AI Edge** | `ai_edge_score` field | LightGBM calibrated probability (0–100). Rendered as a slim 2-digit score badge: `72` in emerald if ≥ 60, white if 40–59, rose if < 40. Blank if `None`. |

Both new fields must be passed through from the existing server-rendered `result_row.html` template — no new API endpoints required. The backend `reports/generator.py` already exposes extra fields; if `eps_surprise_pct` / `ai_edge_score` are not yet in the template context, the template should render `""` (empty string) and display nothing — **never fabricate values**. The backend work to populate these fields (if not already returned by the API) is OUT OF SCOPE for this plan; the JS and template are prepared to consume them when available.

---

## 7. Day-Group Structure in DOM

**Current:** Each day is a `<details class="day-section">` with a `<summary>` and a nested `<table>`.

**New:** Single `<table class="results-table">` for the entire view. Day groups are `<tr class="day-divider-row">` that span all columns:

```html
<tr class="day-divider-row" data-date="2026-10-16">
  <td colspan="12">
    <span class="day-label">Thu, Oct 16 — 3 results</span>
    <span class="day-relative">Today</span>
  </td>
</tr>
<tr class="results-row" data-ticker="TCS.NS" ...> … </tr>
```

This eliminates all the nested accordion `<details>` and the duplicate `<table>` per day, making filtering vastly simpler.

---

## 8. Filtering & State

All client-side filtering (text search, industry, cap, month, date chip, density) is applied by toggling `display: none` on `<tr>` elements via `resultsLedger.filterTable()` in the new module. No re-renders.

State held in the `ResultsLedger` module object (not on `app`):

```js
{
  daySectionsMeta: [],   // [{date, month_key, month_label, stocks_count, rowRange}]
  months: [],            // [{month_key, month_label, stocks_count, is_current, is_past}]
  activeMonth: 'ALL',
  selectedDates: new Set(),
  capFilter: 'all',      // 'all' | 'large' | 'small'
  densityMode: 'compact',// 'compact' | 'standard'
  industries: new Set(), // selected industries (empty = all)
  searchQuery: '',
  totalStocks: 0,
  activeWindowName: '',
}
```

---

## 9. New JS Module: `results_ledger.js`

Extracted from `dashboard.js`. Exports one object `ResultsLedger` with methods:

| Method | Description |
|---|---|
| `init(app)` | Store `app` ref, bind DOM events |
| `loadReport()` | Fetch `/api/v1/dashboard/results/report`, render |
| `renderTable(data)` | Build single flat `<table>` with divider rows |
| `renderMonthStrip()` | Populate 3-cell month summary |
| `renderDateChipRail()` | Build chip rail above table |
| `filterTable()` | Apply all active filters in one pass |
| `setMonth(key)` | Set active month, call `filterTable()` |
| `toggleDate(date, event)` | Toggle date chip, call `filterTable()` |
| `setCapFilter(tier)` | Set cap filter, call `filterTable()` |
| `setDensity(mode)` | Toggle compact/standard row classes |
| `syncCalendar(btn)` | POST sync-calendar |
| `recalcPrices(btn)` | POST recalculate-prices |
| `summarize()` | Fetch AI summary (existing alert-based UI) |
| `exportCsv()` | Export visible rows |
| `exportJson()` | Export visible rows as JSON |
| `getSliderValues()` | Return `{pastDays, aheadDays}` from dual-thumb slider |
| `setPreset(key)` | Map preset key → slider positions + active chip |

`dashboard.js` delegates all `results*` method calls to `window.resultsLedger` (a module singleton) after tab activation. All existing `app.*` method names on the `results` domain are shimmed: `app.loadResultsReport = () => resultsLedger.loadReport()` etc., so no template onclick attributes need changing beyond the new template.

---

## 10. Template Files

| File | Action |
|---|---|
| `earnings_engine/reports/templates/dashboard/_results.html` | Delete & rewrite |
| `earnings_engine/reports/templates/hubs/dashboard/_results.html` | Mirror (identical) |
| `earnings_engine/reports/templates/result_row.html` | Delete & rewrite (add `{eps_surprise_pct}` and `{ai_edge_score}` slots) |

The mirroring rule from `reports/CLAUDE.md` applies: both `dashboard/` and `hubs/dashboard/` files must be kept byte-identical.

---

## 11. CSS

No new CSS file. Styles for the redesign are scoped inline-on-element or use existing tokens from `variables.css`. The dual-thumb slider requires a small `<style>` block embedded in the template (≤ 30 lines) handling the overlapped thumb CSS that can't be done with existing utilities.

The only new CSS class names introduced:

| Class | Purpose |
|---|---|
| `.rl-month-strip` | The 3-cell stat strip container |
| `.rl-month-cell` | Individual month stat cell |
| `.rl-month-cell.active` | Highlighted cell when that month is filtered |
| `.rl-range-slider` | Dual-thumb slider wrapper |
| `.rl-preset-chip` | Preset pill button |
| `.rl-preset-chip.active` | Highlighted chip |
| `.rl-day-divider` | Day-group divider row in table |
| `.rl-toolbar` | Control strip below month summary |
| `.results-row` | Stock data row (existing name, kept) |
| `.rl-surprise-pos` | Emerald surprise badge |
| `.rl-surprise-neg` | Rose surprise badge |
| `.rl-edge-hi` | AI Edge ≥ 60 (emerald) |
| `.rl-edge-lo` | AI Edge < 40 (rose) |

---

## 12. Invariants

- **Anti-Fabrication**: `eps_surprise_pct` and `ai_edge_score` render as empty string / dash if `None` or absent. No synthetic values.
- **Timeframe labelling**: Every return column shows its window (`7D`, `30D`, `3D`). Every metric badge shows its basis.
- **On-demand AI**: AI summary only on explicit button click. No auto LLM on tab open.
- **Zero mock data**: `—` or empty state for all absent fields.
- **CLAUDE.md mirror rule**: Both template paths identical after every change.
- **Module line limit**: `results_ledger.js` ≤ 600 lines. `dashboard.js` must shrink by the extracted block.
