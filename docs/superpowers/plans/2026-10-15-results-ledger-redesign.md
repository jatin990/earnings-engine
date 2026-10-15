# Results Ledger Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the Results Ledger tab as a black-and-white glossy terminal with a dual-thumb range slider, flat single-table DOM, and a standalone JS module extracted from dashboard.js.

**Architecture:** Delete the existing `_results.html` (both mirror paths) and `result_row.html`; rewrite them in an institutional monochrome style. Extract all results-related JavaScript from `dashboard.js` into a new `ui/js/modules/results_ledger.js` module with a clean `ResultsLedger` singleton. The API contract (`/api/v1/dashboard/results/report`) is unchanged; only the frontend changes.

**Tech Stack:** Jinja2 HTML templates, Vanilla JS (ES2020 module pattern), existing CSS tokens in `variables.css`, no new Python backend work required.

**Spec:** `docs/superpowers/specs/2026-10-15-results-ledger-redesign-design.md`

---

## Global Constraints

- Palette: exactly 4 colours — Ink (`#000000`/`#09090b`), Pearl (`#f8fafc`/`#94a3b8`), Emerald (`#34d399`/`rgba(52,211,153,0.15)`), Rose (`#fb7185`/`rgba(251,113,133,0.15)`). No blues, cyans, purples, or amber in Results Ledger UI.
- Anti-Fabrication: `eps_surprise_pct` and `ai_edge_score` render as `""` or `—` if `None`/absent. Never fabricate.
- CLAUDE.md mirror rule: `dashboard/_results.html` and `hubs/dashboard/_results.html` must be byte-identical after every edit.
- Module line limit: `results_ledger.js` ≤ 600 lines; `dashboard.js` must shrink by the extracted block.
- On-demand AI: AI summary fires only on explicit button click, never on tab open.
- Timeframe labelling: every return column label includes its window (`7D:`, `30D:`, `3D:`).
- `node -c earnings_engine/ui/js/modules/results_ledger.js` must exit 0 before every commit.
- Branch: `new_report`. Commit with `Co-Authored-By: Claude Code <noreply@anthropic.com>`.
- Working Python binary: `./.venv/Scripts/python.exe`.
- Error ledger: run `scripts/error_ledger.py scan` after Task 5 before final commit.

---

## Review Focus

1. **Dual-thumb slider with `pastDays=0`** — preset "Upcoming 3D" sets left thumb to 0; `?past_days=0` must reach the API correctly and the slider badge must read `Past 0D · Ahead 3D` (not blank or NaN).
2. **Month filter + date chip filter combined** — selecting "This Month" then clicking a date chip that belongs to Next Month should show an empty state, not silently show wrong rows.
3. **`eps_surprise_pct` absent in API response** — when the field is missing from the server template context, the cell must render a `—` dash, not `undefined`, `null`, or an empty `<td>` that breaks column alignment.
4. **Industry filter with "Select All" after "Clear All"** — clearing then re-selecting all must restore exactly the same visible rows as the unfiltered state; no rows should be permanently hidden.
5. **Density toggle during active filter** — switching compact ↔ standard after a text search filter is active must preserve row visibility and not reset the filter state.

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| **Delete & rewrite** | `earnings_engine/reports/templates/dashboard/_results.html` | Main results tab template |
| **Delete & rewrite** | `earnings_engine/reports/templates/hubs/dashboard/_results.html` | Mirror (identical) |
| **Delete & rewrite** | `earnings_engine/reports/templates/result_row.html` | Single `<tr>` row template |
| **Create** | `earnings_engine/ui/js/modules/results_ledger.js` | `ResultsLedger` singleton module |
| **Modify** | `earnings_engine/ui/js/dashboard.js` | Remove extracted results fns; add shims; load module |
| **Modify** | `earnings_engine/reports/templates/hubs/dashboard/_script_tags.html` | Add `<script src=".../results_ledger.js">` tag |
| **Modify** | `earnings_engine/reports/templates/dashboard/_script_tags.html` | Mirror: same script tag |

---

## Task 1: Delete old files and scaffold result_row.html

**Files:**
- Delete: `earnings_engine/reports/templates/dashboard/_results.html`
- Delete: `earnings_engine/reports/templates/hubs/dashboard/_results.html`
- Delete: `earnings_engine/reports/templates/result_row.html`
- Create: `earnings_engine/reports/templates/result_row.html`

**Interfaces:**
- Produces: `result_row.html` template — a single `<tr class="results-row">` with 12 `<td>` cells consumed by the server-side generator (`earnings_engine/reports/generator.py`). Field slots: `{ticker}`, `{row_ticker_id}`, `{cap_tier}`, `{industry}`, `{raw_price}`, `{raw_mcap}`, `{raw_3d}`, `{raw_7d}`, `{raw_30d}`, `{rel_vol_plain}`, `{beat_rate_plain}`, `{quality_scores_plain}`, `{earnings_date}`, `{relative_date_badge_html}`, `{live_dot_html}`, `{current_price}`, `{market_cap}`, `{eps_estimates_html}`, `{past_results_html}`, `{returns_consolidated_html}`, `{technical_setup_badge_html}`, `{range_bar_html}`, `{pct_from_52w_high_low}`, `{rel_vol_html}`, `{result_sequence_badge_html}`, `{company_name}`, `{day_class}`, `{is_near_results_cls}`, `{eps_surprise_pct}` (new, optional), `{ai_edge_score}` (new, optional).

- [ ] **Step 1: Verify field list in generator**

  ```bash
  grep -n "eps_surprise_pct\|ai_edge_score\|result_row" \
    earnings_engine/reports/generator.py | head -30
  ```
  
  Read what template context keys are passed. Note the exact variable names — they must match slots in the new `result_row.html`. If `eps_surprise_pct` and `ai_edge_score` are absent, that is expected; the new template will render `—` by default.

- [ ] **Step 2: Delete old files**

  ```bash
  rm earnings_engine/reports/templates/dashboard/_results.html
  rm earnings_engine/reports/templates/hubs/dashboard/_results.html
  rm earnings_engine/reports/templates/result_row.html
  ```

- [ ] **Step 3: Write new result_row.html**

  Create `earnings_engine/reports/templates/result_row.html` with the following content. Note: 12 `<td>` cells to match the new 12-column table header in Task 2.

  ```html
  <tr class="results-row {day_class} {is_near_results_cls}"
      id="row_{row_ticker_id}"
      data-ticker="{ticker}"
      data-cap="{cap_tier}"
      data-industry="{industry}"
      data-price="{raw_price}"
      data-mcap="{raw_mcap}"
      data-3d-ret="{raw_3d}"
      data-7d-ret="{raw_7d}"
      data-30d-ret="{raw_30d}"
      data-rel-vol="{rel_vol_plain}"
      data-beat-rate="{beat_rate_plain}"
      data-quality="{quality_scores_plain}"
      onclick="window.resultsLedger && window.resultsLedger.openDrawer('{ticker}')"
      style="cursor:pointer;"
      title="Click to open {ticker} inspector">

    <!-- 1: Ticker + Company -->
    <td class="stock-cell" style="padding:0.4rem 0.6rem;white-space:nowrap;">
      <div style="display:flex;flex-direction:column;gap:0.08rem;">
        <div style="display:flex;align-items:center;gap:0.3rem;">
          <span style="font-weight:700;color:#f8fafc;font-size:0.82rem;font-family:var(--font-mono);">{ticker}</span>
          <button type="button"
            onclick="event.stopPropagation(); window.resultsLedger && window.resultsLedger.refreshSinglePrice('{ticker}', this);"
            style="background:transparent;border:none;color:#525a6b;cursor:pointer;font-size:0.72rem;padding:0 0.1rem;line-height:1;transition:color 0.12s;"
            onmouseenter="this.style.color='#34d399';" onmouseleave="this.style.color='#525a6b';"
            title="Refresh live price">↻</button>
          <a href="/stock/{ticker}" target="_blank"
            onclick="event.stopPropagation();"
            style="color:#525a6b;text-decoration:none;font-size:0.68rem;transition:color 0.12s;"
            onmouseenter="this.style.color='#f8fafc';" onmouseleave="this.style.color='#525a6b';"
            title="Open full profile">↗</a>
          {result_sequence_badge_html}
        </div>
        <span style="color:#6b7485;font-size:0.68rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:160px;"
          title="{company_name} · {industry}">{company_name}</span>
      </div>
    </td>

    <!-- 2: Earnings Date -->
    <td class="cell-earnings-date" style="padding:0.4rem 0.5rem;white-space:nowrap;font-family:var(--font-mono);font-size:0.73rem;color:#c5cbd6;">
      <div style="display:flex;flex-direction:column;gap:0.08rem;">
        <span>{earnings_date}</span>
        {relative_date_badge_html}
      </div>
    </td>

    <!-- 3: Price / Market Cap -->
    <td class="cell-current-price" style="padding:0.4rem 0.5rem;white-space:nowrap;font-family:var(--font-mono);">
      <div style="display:flex;flex-direction:column;gap:0.08rem;">
        <div style="display:flex;align-items:center;gap:0.2rem;font-weight:700;font-size:0.8rem;color:#f8fafc;">
          {live_dot_html}<span>{current_price}</span>
        </div>
        <span style="font-size:0.65rem;color:#6b7485;">{market_cap}</span>
      </div>
    </td>

    <!-- 4: EPS Estimates -->
    <td class="cell-eps-estimates" style="padding:0.4rem 0.5rem;white-space:nowrap;font-family:var(--font-mono);font-size:0.73rem;">
      {eps_estimates_html}
    </td>

    <!-- 5: Historical Beat Rate -->
    <td class="cell-past-results" style="padding:0.4rem 0.5rem;white-space:nowrap;font-family:var(--font-mono);font-size:0.73rem;">
      {past_results_html}
    </td>

    <!-- 6: Surprise % (new — post-result events only, blank for upcoming) -->
    <td class="cell-surprise" style="padding:0.4rem 0.5rem;white-space:nowrap;font-family:var(--font-mono);font-size:0.73rem;text-align:right;">
      {eps_surprise_pct}
    </td>

    <!-- 7: Returns 3D/7D/30D -->
    <td class="cell-returns-consolidated" style="padding:0.4rem 0.5rem;white-space:nowrap;font-family:var(--font-mono);font-size:0.73rem;">
      {returns_consolidated_html}
    </td>

    <!-- 8: AI Edge Score (new) -->
    <td class="cell-ai-edge" style="padding:0.4rem 0.5rem;white-space:nowrap;text-align:center;font-family:var(--font-mono);font-size:0.73rem;">
      {ai_edge_score}
    </td>

    <!-- 9: Technical Setup -->
    <td class="cell-technical-setup" style="padding:0.4rem 0.5rem;white-space:nowrap;font-size:0.7rem;">
      {technical_setup_badge_html}
    </td>

    <!-- 10: S/R Range Bar -->
    <td class="cell-sr-structure" style="padding:0.4rem 0.5rem;font-size:0.7rem;line-height:1.2;">
      {range_bar_html}
    </td>

    <!-- 11: 52-Week -->
    <td class="cell-52w-range" style="padding:0.4rem 0.5rem;white-space:nowrap;font-family:var(--font-mono);font-size:0.7rem;">
      {pct_from_52w_high_low}
    </td>

    <!-- 12: Relative Volume -->
    <td class="cell-rel-vol" style="padding:0.4rem 0.5rem;white-space:nowrap;font-family:var(--font-mono);font-size:0.73rem;text-align:center;">
      {rel_vol_html}
    </td>
  </tr>
  ```

- [ ] **Step 4: Verify template renders (syntax check)**

  ```bash
  ./.venv/Scripts/python.exe -c "
  from jinja2 import Environment, FileSystemLoader
  env = Environment(loader=FileSystemLoader('earnings_engine/reports/templates'))
  t = env.get_template('result_row.html')
  print('OK:', t.filename)
  "
  ```
  
  Expected: `OK: ...result_row.html`

- [ ] **Step 5: Commit scaffold**

  ```bash
  git add earnings_engine/reports/templates/result_row.html
  git commit -m "feat(results-ledger): rewrite result_row.html with 12-col layout and new field slots

  - Adds eps_surprise_pct and ai_edge_score column slots
  - Delegates row click to window.resultsLedger.openDrawer()
  - Delegates price refresh to window.resultsLedger.refreshSinglePrice()
  
  Co-Authored-By: Claude Code <noreply@anthropic.com>"
  ```

---

## Task 2: Write new _results.html template (both mirror paths)

**Files:**
- Create: `earnings_engine/reports/templates/dashboard/_results.html`
- Create: `earnings_engine/reports/templates/hubs/dashboard/_results.html`

**Interfaces:**
- Consumes: Jinja2 macro `comps.market_dropdown(id, default, onchange)` from `dashboard/_components.html` (already imported in current template via `{% import 'dashboard/_components.html' as comps %}`).
- Produces: DOM structure consumed by `ResultsLedger.init()` in Task 3. Element IDs listed below must exist and be stable.

Required element IDs (Task 3 reads these):

| ID | Purpose |
|---|---|
| `tab-results` | Tab container |
| `rl-slider-past` | Left thumb input[type=range] |
| `rl-slider-ahead` | Right thumb input[type=range] |
| `rl-slider-badge` | Live "Past Nd · Ahead Md" text |
| `rl-preset-chips` | Container of preset chip buttons |
| `resultsMarket` | Market dropdown |
| `resultsLoadBtn` | Primary load button |
| `resultsCancelBtn` | Cancel button |
| `resultsSyncBtn` | Sync calendar button |
| `resultsRecalcAllBtn` | Recalc prices button |
| `resultsSummarizeBtn` | AI Summary button |
| `rl-month-strip` | 3-cell month stat strip |
| `rl-month-last` | Last month cell |
| `rl-month-this` | This month cell |
| `rl-month-next` | Next month cell |
| `resultsLiveSearch` | Text filter input |
| `resultsIndustryDropdownWrapper` | Industry filter wrapper |
| `resultsIndustryDropdownBtn` | Industry dropdown button |
| `resultsIndustryDropdownPanel` | Industry panel |
| `resultsIndustryBtnLabel` | Industry button label |
| `resultsIndustrySearchInput` | Industry search input |
| `resultsIndustrySelectedCount` | Industry count label |
| `resultsIndustryCheckboxList` | Industry checkbox list |
| `resultsFilterMatchCount` | "N matches" label |
| `rl-cap-all`, `rl-cap-large`, `rl-cap-small` | Cap filter buttons |
| `rl-density-compact`, `rl-density-standard` | Density toggle buttons |
| `resultsCount` | Result count badge in header |
| `rl-date-chip-rail` | Date chip rail |
| `resultsReportSections` | Table container div |
| `resultsReportStatus` | Status/timestamp bar |

- [ ] **Step 1: Write _results.html**

  Create `earnings_engine/reports/templates/dashboard/_results.html`:

  ```html
  {% import 'dashboard/_components.html' as comps %}
  <div id="tab-results" class="tab-content" style="width:100%;max-width:100%;padding-top:0.25rem;">

    <!-- === INLINE STYLES FOR DUAL-THUMB SLIDER & MODULE CSS CLASSES === -->
    <style>
      .rl-preset-chip { background:#09090b; border:1px solid rgba(255,255,255,0.12); color:#94a3b8; font-size:0.68rem; font-weight:600; padding:0.22rem 0.55rem; border-radius:4px; cursor:pointer; font-family:var(--font-mono); transition:all 0.12s; }
      .rl-preset-chip.active, .rl-preset-chip:hover { background:#1a1a1a; border-color:rgba(255,255,255,0.35); color:#f8fafc; }
      .rl-range-slider { position:relative; height:20px; display:flex; align-items:center; }
      .rl-range-slider input[type=range] { position:absolute; width:100%; height:4px; appearance:none; -webkit-appearance:none; background:transparent; pointer-events:none; }
      .rl-range-slider input[type=range]::-webkit-slider-thumb { appearance:none; -webkit-appearance:none; width:14px; height:14px; border-radius:50%; background:#f8fafc; border:2px solid #000; pointer-events:all; cursor:pointer; }
      .rl-range-slider input[type=range]::-moz-range-thumb { width:14px; height:14px; border-radius:50%; background:#f8fafc; border:2px solid #000; pointer-events:all; cursor:pointer; }
      .rl-range-track { position:absolute; width:100%; height:4px; background:rgba(255,255,255,0.12); border-radius:2px; }
      .rl-month-strip { display:grid; grid-template-columns:1fr 1fr 1fr; gap:0; border:1px solid rgba(255,255,255,0.08); border-radius:6px; overflow:hidden; margin-bottom:0.5rem; background:#09090b; }
      .rl-month-cell { padding:0.55rem 0.75rem; cursor:pointer; transition:background 0.12s; border-right:1px solid rgba(255,255,255,0.07); }
      .rl-month-cell:last-child { border-right:none; }
      .rl-month-cell:hover, .rl-month-cell.active { background:rgba(255,255,255,0.04); }
      .rl-day-divider td { background:#000; padding:0.3rem 0.6rem; border-top:1px solid rgba(255,255,255,0.07); }
      .results-row:hover td { background:rgba(255,255,255,0.03); }
      .results-row:nth-child(even) td { background:rgba(255,255,255,0.018); }
      .rl-surprise-pos { color:#34d399; }
      .rl-surprise-neg { color:#fb7185; }
      .rl-edge-hi { color:#34d399; font-weight:700; }
      .rl-edge-mid { color:#94a3b8; }
      .rl-edge-lo { color:#fb7185; }
      .rl-toolbar { display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:0.35rem; padding:0.35rem 0; border-bottom:1px solid rgba(255,255,255,0.07); margin-bottom:0.4rem; }
      .results-row.density-standard td { padding-top:0.55rem; padding-bottom:0.55rem; }
    </style>

    <!-- === SECTION HEADER === -->
    <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:0.5rem;border-bottom:1px solid rgba(255,255,255,0.07);padding-bottom:0.5rem;margin-bottom:0.65rem;">
      <div style="display:flex;align-items:center;gap:0.5rem;">
        <span style="font-size:1.05rem;font-weight:800;color:#f8fafc;font-family:var(--font-heading);letter-spacing:-0.02em;">Results Ledger</span>
        <span id="resultsCount" style="display:none;background:#09090b;color:#94a3b8;border:1px solid rgba(255,255,255,0.12);font-size:0.62rem;font-family:var(--font-mono);padding:0.1rem 0.45rem;border-radius:4px;font-weight:600;"></span>
      </div>
      <div style="display:flex;gap:0.3rem;align-items:center;flex-wrap:wrap;">
        <button type="button" id="resultsSyncBtn" onclick="window.resultsLedger && window.resultsLedger.syncCalendar(this)"
          style="height:26px;padding:0 0.55rem;background:#09090b;color:#94a3b8;border:1px solid rgba(255,255,255,0.12);font-size:0.68rem;font-weight:600;border-radius:4px;cursor:pointer;font-family:var(--font-mono);"
          title="Sync results calendar from NSE &amp; data feeds">📅 Sync</button>
        <button type="button" id="resultsRecalcAllBtn" onclick="window.resultsLedger && window.resultsLedger.recalcPrices(this)"
          style="height:26px;padding:0 0.55rem;background:#09090b;color:#94a3b8;border:1px solid rgba(255,255,255,0.12);font-size:0.68rem;font-weight:600;border-radius:4px;cursor:pointer;font-family:var(--font-mono);"
          title="Recalculate live prices &amp; S/R for all window stocks">⚡ Recalc</button>
        <button type="button" id="resultsSummarizeBtn" onclick="window.resultsLedger && window.resultsLedger.summarize(this)"
          style="height:26px;padding:0 0.55rem;background:#09090b;color:#94a3b8;border:1px solid rgba(255,255,255,0.12);font-size:0.68rem;font-weight:600;border-radius:4px;cursor:pointer;font-family:var(--font-mono);"
          title="AI summary of visible results">✦ AI Summary</button>
      </div>
    </div>

    <!-- === RANGE CONTROL STRIP === -->
    <div style="background:#09090b;border:1px solid rgba(255,255,255,0.08);border-radius:6px;padding:0.5rem 0.75rem;margin-bottom:0.5rem;box-shadow:inset 0 1px 0 rgba(255,255,255,0.06);">
      <!-- Preset chips row -->
      <div id="rl-preset-chips" style="display:flex;gap:0.3rem;flex-wrap:wrap;margin-bottom:0.45rem;">
        <button type="button" class="rl-preset-chip active" data-preset="next3" onclick="window.resultsLedger && window.resultsLedger.setPreset('next3')">Upcoming 3D</button>
        <button type="button" class="rl-preset-chip" data-preset="next7" onclick="window.resultsLedger && window.resultsLedger.setPreset('next7')">Upcoming 7D</button>
        <button type="button" class="rl-preset-chip" data-preset="recent" onclick="window.resultsLedger && window.resultsLedger.setPreset('recent')">Recent ±4/7D</button>
        <button type="button" class="rl-preset-chip" data-preset="pm30" onclick="window.resultsLedger && window.resultsLedger.setPreset('pm30')">±1 Month</button>
        <button type="button" class="rl-preset-chip" data-preset="pm60" onclick="window.resultsLedger && window.resultsLedger.setPreset('pm60')">±2 Months</button>
        <button type="button" class="rl-preset-chip" data-preset="next14" onclick="window.resultsLedger && window.resultsLedger.setPreset('next14')">14D Ahead</button>
        <button type="button" class="rl-preset-chip" data-preset="next30" onclick="window.resultsLedger && window.resultsLedger.setPreset('next30')">30D Ahead</button>
        <button type="button" class="rl-preset-chip" data-preset="past60" onclick="window.resultsLedger && window.resultsLedger.setPreset('past60')">Past 60D</button>
        <button type="button" class="rl-preset-chip" data-preset="custom" onclick="">⚙ Custom</button>
      </div>
      <!-- Dual-thumb slider + action row -->
      <div style="display:flex;align-items:center;gap:0.75rem;flex-wrap:wrap;">
        <div style="display:flex;flex-direction:column;gap:0.15rem;flex:1;min-width:180px;max-width:320px;">
          <div class="rl-range-slider">
            <div class="rl-range-track"></div>
            <input type="range" id="rl-slider-past" min="0" max="180" value="0"
              oninput="window.resultsLedger && window.resultsLedger.onSliderInput()">
            <input type="range" id="rl-slider-ahead" min="1" max="90" value="3"
              oninput="window.resultsLedger && window.resultsLedger.onSliderInput()">
          </div>
          <span id="rl-slider-badge" style="font-size:0.62rem;color:#6b7485;font-family:var(--font-mono);text-align:center;">Past 0D · Ahead 3D</span>
        </div>
        <div style="display:flex;gap:0.3rem;align-items:center;">
          {{ comps.market_dropdown('resultsMarket', 'ALL', "window.resultsLedger && window.resultsLedger.onMarketChange(this.value)") }}
          <button type="button" id="resultsLoadBtn" onclick="window.resultsLedger && window.resultsLedger.loadReport()"
            style="height:28px;padding:0 0.7rem;background:#f8fafc;color:#000;font-size:0.75rem;font-weight:700;border:none;border-radius:4px;cursor:pointer;font-family:var(--font-heading);">▶ Load</button>
          <button type="button" id="resultsCancelBtn" onclick="window.resultsLedger && window.resultsLedger.cancel()"
            style="display:none;height:28px;padding:0 0.6rem;background:#09090b;color:#fb7185;border:1px solid rgba(251,113,133,0.3);font-size:0.72rem;border-radius:4px;cursor:pointer;">⏹ Cancel</button>
        </div>
      </div>
    </div>

    <!-- === MONTH SUMMARY STRIP === -->
    <div id="rl-month-strip" class="rl-month-strip">
      <div id="rl-month-last" class="rl-month-cell" onclick="window.resultsLedger && window.resultsLedger.setMonth('last')">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.15rem;">
          <span id="rl-month-last-label" style="font-size:0.62rem;color:#6b7485;text-transform:uppercase;font-weight:700;letter-spacing:0.05em;">Last Month</span>
          <span style="font-size:0.58rem;color:#525a6b;background:rgba(255,255,255,0.05);padding:0.04rem 0.28rem;border-radius:3px;">Past</span>
        </div>
        <div id="rl-month-last-count" style="font-size:1.2rem;font-weight:800;color:#f8fafc;font-family:var(--font-mono);line-height:1.2;">—</div>
        <div id="rl-month-last-sub" style="font-size:0.62rem;color:#525a6b;margin-top:0.1rem;">Reported Results</div>
      </div>
      <div id="rl-month-this" class="rl-month-cell" onclick="window.resultsLedger && window.resultsLedger.setMonth('this')">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.15rem;">
          <span id="rl-month-this-label" style="font-size:0.62rem;color:#94a3b8;text-transform:uppercase;font-weight:700;letter-spacing:0.05em;">This Month</span>
          <div style="display:flex;gap:0.2rem;align-items:center;">
            <span style="font-size:0.58rem;color:#f8fafc;background:rgba(255,255,255,0.1);padding:0.04rem 0.28rem;border-radius:3px;font-weight:600;">Active</span>
            <button type="button" onclick="event.stopPropagation(); window.resultsLedger && window.resultsLedger.openMonthModal('this');"
              style="background:rgba(255,255,255,0.06);color:#94a3b8;border:none;padding:0.04rem 0.28rem;font-size:0.58rem;border-radius:3px;cursor:pointer;">🔍</button>
          </div>
        </div>
        <div id="rl-month-this-count" style="font-size:1.2rem;font-weight:800;color:#f8fafc;font-family:var(--font-mono);line-height:1.2;">—</div>
        <div id="rl-month-this-sub" style="font-size:0.62rem;color:#6b7485;margin-top:0.1rem;">Active Season</div>
      </div>
      <div id="rl-month-next" class="rl-month-cell" onclick="window.resultsLedger && window.resultsLedger.setMonth('next')">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.15rem;">
          <span id="rl-month-next-label" style="font-size:0.62rem;color:#6b7485;text-transform:uppercase;font-weight:700;letter-spacing:0.05em;">Next Month</span>
          <div style="display:flex;gap:0.2rem;align-items:center;">
            <span style="font-size:0.58rem;color:#6b7485;background:rgba(255,255,255,0.05);padding:0.04rem 0.28rem;border-radius:3px;">Pipeline</span>
            <button type="button" onclick="event.stopPropagation(); window.resultsLedger && window.resultsLedger.openMonthModal('next');"
              style="background:rgba(255,255,255,0.06);color:#6b7485;border:none;padding:0.04rem 0.28rem;font-size:0.58rem;border-radius:3px;cursor:pointer;">🔍</button>
          </div>
        </div>
        <div id="rl-month-next-count" style="font-size:1.2rem;font-weight:800;color:#f8fafc;font-family:var(--font-mono);line-height:1.2;">—</div>
        <div id="rl-month-next-sub" style="font-size:0.62rem;color:#525a6b;margin-top:0.1rem;">Scheduled</div>
      </div>
    </div>

    <!-- === MAIN TABLE CONTAINER === -->
    <div style="border:1px solid rgba(255,255,255,0.08);border-radius:6px;overflow:hidden;background:#000;box-shadow:inset 0 1px 0 rgba(255,255,255,0.04);">

      <!-- TOOLBAR (inside container, flush) -->
      <div class="rl-toolbar" style="padding:0.35rem 0.6rem;border-bottom:1px solid rgba(255,255,255,0.06);">
        <!-- Search -->
        <div style="display:flex;align-items:center;gap:0.3rem;flex:1;min-width:180px;max-width:360px;">
          <span style="font-size:0.68rem;color:#525a6b;">⌕</span>
          <input type="text" id="resultsLiveSearch"
            oninput="window.resultsLedger && window.resultsLedger.onSearchInput(this.value)"
            placeholder="Filter by ticker, company, industry, setup…"
            style="width:100%;height:24px;padding:0 0.4rem;background:#000;border:1px solid rgba(255,255,255,0.1);border-radius:3px;color:#f8fafc;font-size:0.7rem;font-family:var(--font-mono);outline:none;">
        </div>
        <!-- Right controls -->
        <div style="display:flex;align-items:center;gap:0.3rem;flex-wrap:wrap;font-size:0.68rem;">
          <!-- Industry dropdown -->
          <div id="resultsIndustryDropdownWrapper" style="position:relative;display:inline-block;">
            <button type="button" id="resultsIndustryDropdownBtn"
              onclick="window.resultsLedger && window.resultsLedger.toggleIndustryDropdown(event)"
              style="height:24px;padding:0 0.4rem;background:#000;border:1px solid rgba(255,255,255,0.12);border-radius:3px;color:#94a3b8;font-size:0.66rem;font-weight:600;cursor:pointer;display:flex;align-items:center;gap:0.25rem;font-family:var(--font-mono);"
              title="Filter by industry">
              <span id="resultsIndustryBtnLabel">Industries (All)</span>
              <span style="font-size:0.5rem;color:#525a6b;">▼</span>
            </button>
            <div id="resultsIndustryDropdownPanel" onclick="event.stopPropagation()"
              style="display:none;position:absolute;top:calc(100% + 3px);right:0;min-width:260px;max-width:320px;background:#09090b;border:1px solid rgba(255,255,255,0.15);border-radius:5px;box-shadow:0 12px 28px rgba(0,0,0,0.9);z-index:120;padding:0.4rem;">
              <div style="margin-bottom:0.3rem;display:flex;flex-direction:column;gap:0.25rem;">
                <input type="text" id="resultsIndustrySearchInput"
                  oninput="window.resultsLedger && window.resultsLedger.filterIndustryList(this.value)"
                  placeholder="Search industries…"
                  style="width:100%;height:22px;padding:0 0.35rem;background:#000;border:1px solid rgba(255,255,255,0.1);border-radius:3px;color:#f8fafc;font-size:0.66rem;font-family:var(--font-mono);outline:none;">
                <div style="display:flex;justify-content:space-between;align-items:center;font-size:0.6rem;padding:0 0.1rem;">
                  <div style="display:flex;gap:0.3rem;">
                    <button type="button" onclick="window.resultsLedger && window.resultsLedger.selectAllIndustries()"
                      style="background:transparent;border:none;color:#f8fafc;cursor:pointer;padding:0;font-size:0.6rem;font-weight:600;">Select All</button>
                    <span style="color:#525a6b;">|</span>
                    <button type="button" onclick="window.resultsLedger && window.resultsLedger.clearAllIndustries()"
                      style="background:transparent;border:none;color:#fb7185;cursor:pointer;padding:0;font-size:0.6rem;font-weight:600;">Clear All</button>
                  </div>
                  <span id="resultsIndustrySelectedCount" style="color:#6b7485;font-variant-numeric:tabular-nums;">All selected</span>
                </div>
              </div>
              <div id="resultsIndustryCheckboxList"
                style="max-height:210px;overflow-y:auto;display:flex;flex-direction:column;gap:0.18rem;padding-right:0.15rem;">
              </div>
            </div>
          </div>

          <span id="resultsFilterMatchCount" style="color:#f8fafc;font-family:var(--font-mono);font-weight:700;min-width:32px;"></span>

          <!-- Cap filter -->
          <div style="display:flex;align-items:center;background:#000;border:1px solid rgba(255,255,255,0.1);border-radius:3px;padding:1px;">
            <button type="button" id="rl-cap-all" onclick="window.resultsLedger && window.resultsLedger.setCapFilter('all')"
              style="background:rgba(255,255,255,0.12);color:#f8fafc;font-size:0.6rem;padding:0.08rem 0.3rem;border:none;border-radius:2px;cursor:pointer;font-weight:700;">All</button>
            <button type="button" id="rl-cap-large" onclick="window.resultsLedger && window.resultsLedger.setCapFilter('large')"
              style="background:transparent;color:#6b7485;font-size:0.6rem;padding:0.08rem 0.3rem;border:none;cursor:pointer;">Large</button>
            <button type="button" id="rl-cap-small" onclick="window.resultsLedger && window.resultsLedger.setCapFilter('small')"
              style="background:transparent;color:#6b7485;font-size:0.6rem;padding:0.08rem 0.3rem;border:none;cursor:pointer;">Small</button>
          </div>

          <!-- Density toggle -->
          <div style="display:flex;align-items:center;background:#000;border:1px solid rgba(255,255,255,0.1);border-radius:3px;padding:1px;">
            <button type="button" id="rl-density-compact" onclick="window.resultsLedger && window.resultsLedger.setDensity('compact')"
              style="background:rgba(255,255,255,0.12);color:#f8fafc;font-size:0.6rem;padding:0.08rem 0.3rem;border:none;border-radius:2px;cursor:pointer;font-weight:700;">Dense</button>
            <button type="button" id="rl-density-standard" onclick="window.resultsLedger && window.resultsLedger.setDensity('standard')"
              style="background:transparent;color:#6b7485;font-size:0.6rem;padding:0.08rem 0.3rem;border:none;cursor:pointer;">Comfort</button>
          </div>

          <!-- Export -->
          <button type="button" onclick="window.resultsLedger && window.resultsLedger.exportCsv()"
            style="height:22px;padding:0 0.35rem;background:#000;color:#6b7485;border:1px solid rgba(255,255,255,0.1);border-radius:3px;font-size:0.6rem;cursor:pointer;font-family:var(--font-mono);">⤓ CSV</button>
          <button type="button" onclick="window.resultsLedger && window.resultsLedger.exportJson()"
            style="height:22px;padding:0 0.35rem;background:#000;color:#6b7485;border:1px solid rgba(255,255,255,0.1);border-radius:3px;font-size:0.6rem;cursor:pointer;font-family:var(--font-mono);">⤓ JSON</button>
        </div>
      </div>

      <!-- DATE CHIP RAIL -->
      <div id="rl-date-chip-rail"
        style="display:none;padding:0.3rem 0.6rem;border-bottom:1px solid rgba(255,255,255,0.05);overflow-x:auto;white-space:nowrap;gap:0.25rem;">
      </div>

      <!-- TABLE AREA -->
      <div id="resultsReportSections" style="overflow-x:auto;">
        <!-- Empty state (replaced on load) -->
        <div style="text-align:center;padding:2.5rem 1rem;color:#525a6b;">
          <div style="font-size:1.5rem;margin-bottom:0.4rem;">📅</div>
          <h4 style="margin:0 0 0.3rem;color:#94a3b8;font-size:0.92rem;font-family:var(--font-heading);">Corporate Earnings Ready to Load</h4>
          <p style="max-width:400px;margin:0 auto 0.75rem;font-size:0.72rem;line-height:1.5;color:#525a6b;">
            Results are served from local cache. Click <strong style="color:#94a3b8;">Load</strong> to view upcoming earnings catalysts, technical setups, and S/R structures.
          </p>
          <button type="button" onclick="window.resultsLedger && window.resultsLedger.loadReport()"
            style="height:30px;padding:0 1rem;background:#f8fafc;color:#000;font-size:0.75rem;font-weight:700;border:none;border-radius:4px;cursor:pointer;font-family:var(--font-heading);">▶ Load Results Report</button>
        </div>
      </div>

      <!-- STATUS BAR -->
      <div id="resultsReportStatus"
        style="padding:0.25rem 0.6rem;font-size:0.64rem;color:#525a6b;font-family:var(--font-mono);border-top:1px solid rgba(255,255,255,0.05);">
      </div>
    </div>

  </div>
  ```

- [ ] **Step 2: Mirror to hubs path**

  ```bash
  cp earnings_engine/reports/templates/dashboard/_results.html \
     earnings_engine/reports/templates/hubs/dashboard/_results.html
  ```

- [ ] **Step 3: Verify Jinja2 parses both files**

  ```bash
  ./.venv/Scripts/python.exe -c "
  from jinja2 import Environment, FileSystemLoader
  for path in ['earnings_engine/reports/templates', 'earnings_engine/reports/templates/hubs']:
      env = Environment(loader=FileSystemLoader(path))
      t = env.get_template('dashboard/_results.html')
      print('OK:', path)
  "
  ```
  
  Expected: two `OK:` lines, no errors.

- [ ] **Step 4: Commit**

  ```bash
  git add earnings_engine/reports/templates/dashboard/_results.html \
          earnings_engine/reports/templates/hubs/dashboard/_results.html
  git commit -m "feat(results-ledger): rewrite _results.html — monochrome glossy terminal redesign

  - 4-colour palette: Ink/Pearl/Emerald/Rose only
  - Dual-thumb range slider replaces <select> preset
  - Preset chip row (Upcoming 3D/7D, ±1M, ±2M, Past 60D, Custom)
  - Month summary strip: 3 inline stat cells (no coloured cards)
  - Flat table container: no nested card boxes
  - Delegates all events to window.resultsLedger module
  - Mirrors to hubs/dashboard/_results.html (byte-identical)
  
  Co-Authored-By: Claude Code <noreply@anthropic.com>"
  ```

---

## Task 3: Create results_ledger.js module — core structure and load

**Files:**
- Create: `earnings_engine/ui/js/modules/results_ledger.js`

**Interfaces:**
- Consumes: `window.API_BASE` (set by dashboard), `window.app.fetchWithAbort(key, url)`, `window.app.openStockDrawer(ticker)`, `window.app.openResultsMonthModal(which)`, `window.app.resetTaskLoadingUI('results')`.
- Produces: `window.resultsLedger` singleton with methods `init(app)`, `loadReport()`, `cancel()`, `onSliderInput()`, `setPreset(key)`, `onMarketChange(val)`, `openDrawer(ticker)`, `refreshSinglePrice(ticker, btn)`, `openMonthModal(which)`.

The PRESET_MAP defines the canonical mapping preset key → `{pastDays, aheadDays, label}`:

```js
const PRESET_MAP = {
  next3:  { pastDays: 0,  aheadDays: 3,  label: 'Upcoming 3D' },
  next7:  { pastDays: 0,  aheadDays: 7,  label: 'Upcoming 7D' },
  recent: { pastDays: 4,  aheadDays: 7,  label: 'Recent ±4/7D' },
  pm30:   { pastDays: 30, aheadDays: 30, label: '±1 Month' },
  pm60:   { pastDays: 60, aheadDays: 60, label: '±2 Months' },
  next14: { pastDays: 0,  aheadDays: 14, label: '14D Ahead' },
  next30: { pastDays: 0,  aheadDays: 30, label: '30D Ahead' },
  next60: { pastDays: 0,  aheadDays: 60, label: '60D Ahead' },
  past60: { pastDays: 60, aheadDays: 0,  label: 'Past 60D' },
};
```

- [ ] **Step 1: Write the module skeleton**

  Create `earnings_engine/ui/js/modules/results_ledger.js`:

  ```js
  /**
   * results_ledger.js — Results Ledger module for Nexus Intelligence Platform
   *
   * Handles all Results Ledger tab logic: range control, fetch, table render,
   * filtering, month strip, date chips, export. Exposes window.resultsLedger.
   *
   * Palette: Ink (#000/#09090b) · Pearl (#f8fafc/#94a3b8) ·
   *          Emerald (#34d399) · Rose (#fb7185)
   */

  'use strict';

  const PRESET_MAP = {
    next3:  { pastDays: 0,  aheadDays: 3,  label: 'Upcoming 3D' },
    next7:  { pastDays: 0,  aheadDays: 7,  label: 'Upcoming 7D' },
    recent: { pastDays: 4,  aheadDays: 7,  label: 'Recent ±4/7D' },
    pm30:   { pastDays: 30, aheadDays: 30, label: '±1 Month' },
    pm60:   { pastDays: 60, aheadDays: 60, label: '±2 Months' },
    next14: { pastDays: 0,  aheadDays: 14, label: '14D Ahead' },
    next30: { pastDays: 0,  aheadDays: 30, label: '30D Ahead' },
    next60: { pastDays: 0,  aheadDays: 60, label: '60D Ahead' },
    past60: { pastDays: 60, aheadDays: 0,  label: 'Past 60D' },
    custom: { pastDays: null, aheadDays: null, label: '⚙ Custom' },
  };

  const ResultsLedger = {
    _app: null,

    // --- State ---
    daySectionsMeta: [],   // [{date, month_key, month_label, stocks_count, html}]
    months: [],            // [{month_key, month_label, stocks_count, is_current, is_past}]
    activeMonth: 'ALL',
    selectedDates: new Set(),
    capFilter: 'all',
    densityMode: 'compact',
    industries: new Set(),  // empty = all selected
    allIndustries: [],      // full list populated on load
    searchQuery: '',
    totalStocks: 0,
    activeWindowName: '',
    _abortCtrl: null,

    // --- Init ---

    init(app) {
      this._app = app;
      this.setPreset('next3');
      // Close industry dropdown on outside click
      document.addEventListener('click', (e) => {
        const panel = document.getElementById('resultsIndustryDropdownPanel');
        const btn = document.getElementById('resultsIndustryDropdownBtn');
        if (panel && !panel.contains(e.target) && e.target !== btn) {
          panel.style.display = 'none';
        }
      });
    },

    // --- Slider & Preset ---

    getSliderValues() {
      const past = parseInt(document.getElementById('rl-slider-past')?.value ?? 0, 10);
      const ahead = parseInt(document.getElementById('rl-slider-ahead')?.value ?? 3, 10);
      return { pastDays: past, aheadDays: Math.max(1, ahead) };
    },

    onSliderInput() {
      const { pastDays, aheadDays } = this.getSliderValues();
      const badge = document.getElementById('rl-slider-badge');
      if (badge) badge.textContent = `Past ${pastDays}D · Ahead ${aheadDays}D`;
      // Mark as custom — deactivate all preset chips
      document.querySelectorAll('#rl-preset-chips .rl-preset-chip').forEach(c => {
        c.classList.toggle('active', c.dataset.preset === 'custom');
      });
    },

    setPreset(key) {
      const p = PRESET_MAP[key];
      if (!p || key === 'custom') {
        return; // custom chip is a no-op; sliders already set
      }
      const pastEl = document.getElementById('rl-slider-past');
      const aheadEl = document.getElementById('rl-slider-ahead');
      if (pastEl) pastEl.value = p.pastDays;
      if (aheadEl) aheadEl.value = Math.max(1, p.aheadDays);
      const badge = document.getElementById('rl-slider-badge');
      if (badge) badge.textContent = `Past ${p.pastDays}D · Ahead ${p.aheadDays}D`;
      document.querySelectorAll('#rl-preset-chips .rl-preset-chip').forEach(c => {
        c.classList.toggle('active', c.dataset.preset === key);
      });
      this.activeWindowName = p.label;
    },

    onMarketChange() {
      // No auto-reload; user clicks Load
    },

    // --- Load ---

    async loadReport() {
      const { pastDays, aheadDays } = this.getSliderValues();
      const market = document.getElementById('resultsMarket')?.value || '';
      const query = `?days=${aheadDays}&past_days=${pastDays}` +
        (market ? `&market=${encodeURIComponent(market)}` : '');

      const loadBtn = document.getElementById('resultsLoadBtn');
      const cancelBtn = document.getElementById('resultsCancelBtn');
      const statusEl = document.getElementById('resultsReportStatus');
      const countBadge = document.getElementById('resultsCount');

      if (loadBtn) { loadBtn.disabled = true; loadBtn.textContent = 'Loading…'; }
      if (cancelBtn) cancelBtn.style.display = 'inline-block';
      if (statusEl) statusEl.textContent = `Fetching results — ${this.activeWindowName || 'custom window'}…`;

      // Abort any inflight request
      if (this._abortCtrl) this._abortCtrl.abort();
      this._abortCtrl = new AbortController();

      try {
        const res = await fetch(
          (window.API_BASE || '') + '/api/v1/dashboard/results/report' + query,
          { signal: this._abortCtrl.signal }
        );
        const data = await res.json();

        if (!data.success) {
          this._renderError(data.error || 'No results data found.');
          if (statusEl) statusEl.textContent = data.error || 'No results data.';
          return;
        }

        this._processApiResponse(data);
        this.renderTable();
        this.renderMonthStrip();
        this.renderDateChipRail();
        this.filterTable(); // Apply any pre-existing filters

        const totalDates = this.daySectionsMeta.length;
        if (countBadge) {
          countBadge.style.display = 'inline-block';
          countBadge.textContent = `${this.totalStocks} results · ${totalDates} dates`;
        }
        if (statusEl) {
          statusEl.textContent =
            `Loaded ${this.totalStocks} results across ${totalDates} dates` +
            ` — ${this.activeWindowName || 'custom'} window · ${new Date().toLocaleTimeString()}`;
        }

        // Attach popup elements if server sent them
        if (data.popups) {
          const existing = document.getElementById('resultsReportPopups');
          if (existing) existing.remove();
          const wrap = document.createElement('div');
          wrap.id = 'resultsReportPopups';
          wrap.innerHTML = data.popups;
          document.body.appendChild(wrap);
        }
      } catch (e) {
        if (e.name === 'AbortError') {
          if (statusEl) statusEl.textContent = 'Request cancelled.';
          return;
        }
        console.error('[ResultsLedger] loadReport error:', e);
        this._renderError('Network error: ' + (e.message || e));
        if (statusEl) statusEl.textContent = 'Error: ' + (e.message || e);
      } finally {
        if (loadBtn) { loadBtn.disabled = false; loadBtn.textContent = '▶ Load'; }
        if (cancelBtn) cancelBtn.style.display = 'none';
        this._abortCtrl = null;
      }
    },

    cancel() {
      if (this._abortCtrl) {
        this._abortCtrl.abort('user-cancelled');
      }
    },

    _processApiResponse(data) {
      // Reset state
      this.activeMonth = 'ALL';
      this.selectedDates.clear();

      const rawSections = (data.day_sections_list && data.day_sections_list.length)
        ? data.day_sections_list
        : (data.day_sections ? [data.day_sections] : []);

      const providedMeta = (data.day_sections_meta && data.day_sections_meta.length)
        ? data.day_sections_meta
        : null;

      this.months = (data.months && data.months.length) ? data.months : [];
      this.totalStocks = data.total_stocks || 0;

      if (providedMeta) {
        this.daySectionsMeta = providedMeta;
      } else {
        // Derive meta from HTML sections (fallback)
        this.daySectionsMeta = this._deriveMetaFromSections(rawSections);
        this.months = this._deriveMonthsFromMeta(this.daySectionsMeta);
        this.totalStocks = this.daySectionsMeta.reduce((a, m) => a + (m.stocks_count || 1), 0);
      }
    },

    _deriveMetaFromSections(sections) {
      const MONTH_NAMES = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
      const curMonthKey = new Date().toISOString().slice(0, 7);
      return sections.map(html => {
        const dateMatch = html.match(/(\\d{4}-\\d{2}-\\d{2})/);
        const dateStr = dateMatch ? dateMatch[1] : '';
        let monthKey = 'other';
        let monthLabel = 'Other';
        if (dateStr) {
          monthKey = dateStr.slice(0, 7);
          const parts = dateStr.split('-');
          monthLabel = (MONTH_NAMES[parseInt(parts[1], 10) - 1] || parts[1]) + ' ' + parts[0];
        }
        const countMatch = html.match(/class=[\"']day-count[\"']>\\s*(\\d+)/i);
        const stocksCount = countMatch ? parseInt(countMatch[1], 10) : ((html.match(/<tr/g) || []).length || 1);
        return { date: dateStr, month_key: monthKey, month_label: monthLabel, stocks_count: stocksCount, html };
      });
    },

    _deriveMonthsFromMeta(meta) {
      const curKey = new Date().toISOString().slice(0, 7);
      const map = {};
      meta.forEach(m => {
        if (!map[m.month_key]) {
          map[m.month_key] = {
            month_key: m.month_key, month_label: m.month_label,
            stocks_count: 0, dates_count: 0,
            is_current: m.month_key === curKey,
            is_past: m.month_key < curKey,
          };
        }
        map[m.month_key].stocks_count += m.stocks_count;
        map[m.month_key].dates_count += 1;
      });
      return Object.keys(map).sort().map(k => map[k]);
    },

    // --- Drawer ---
    openDrawer(ticker) {
      if (this._app && typeof this._app.openStockDrawer === 'function') {
        this._app.openStockDrawer(ticker);
      }
    },

    openMonthModal(which) {
      if (this._app && typeof this._app.openResultsMonthModal === 'function') {
        this._app.openResultsMonthModal(which);
      }
    },

    // --- Render helpers ---
    _renderError(msg) {
      const el = document.getElementById('resultsReportSections');
      if (!el) return;
      el.innerHTML = `
        <div style="text-align:center;padding:2rem 1rem;color:#6b7485;">
          <div style="margin-bottom:0.5rem;font-size:0.9rem;color:#fb7185;">⚠ ${msg}</div>
          <button type="button" onclick="window.resultsLedger && window.resultsLedger.loadReport()"
            style="height:28px;padding:0 0.8rem;background:#f8fafc;color:#000;font-size:0.72rem;font-weight:700;border:none;border-radius:4px;cursor:pointer;">↻ Retry</button>
        </div>`;
    },
  };

  window.resultsLedger = ResultsLedger;
  ```

- [ ] **Step 2: Syntax check**

  ```bash
  node -c earnings_engine/ui/js/modules/results_ledger.js
  ```
  
  Expected: `earnings_engine/ui/js/modules/results_ledger.js` syntax OK

- [ ] **Step 3: Commit module skeleton**

  ```bash
  git add earnings_engine/ui/js/modules/results_ledger.js
  git commit -m "feat(results-ledger): scaffold ResultsLedger module with load, preset, slider

  - PRESET_MAP canonical mapping (next3/7/recent/pm30/pm60 etc.)
  - loadReport() fetches /api/v1/dashboard/results/report with abort support
  - setPreset() drives dual-thumb slider and badge
  - onSliderInput() marks custom and updates badge
  - _processApiResponse() normalises day_sections_meta fallback
  - window.resultsLedger singleton
  
  Co-Authored-By: Claude Code <noreply@anthropic.com>"
  ```

---

## Task 4: Add table render, month strip render, date chip rail, and filtering

**Files:**
- Modify: `earnings_engine/ui/js/modules/results_ledger.js` (add methods after the skeleton)

**Interfaces:**
- Produces: `renderTable()`, `renderMonthStrip()`, `renderDateChipRail()`, `filterTable()`, `setMonth(key)`, `toggleDate(date, event)`, `setCapFilter(tier)`, `setDensity(mode)`, `onSearchInput(query)`, `toggleIndustryDropdown(event)`, `filterIndustryList(query)`, `selectAllIndustries()`, `clearAllIndustries()`.

- [ ] **Step 1: Add renderTable()**

  Add these methods inside `ResultsLedger = { … }` above `window.resultsLedger = ResultsLedger;`:

  ```js
    renderTable() {
      const container = document.getElementById('resultsReportSections');
      if (!container) return;

      if (!this.daySectionsMeta.length) {
        this._renderError('No results found in this window.');
        return;
      }

      // Build single flat table — day-divider rows + stock rows from server HTML
      // The server ships day sections as raw HTML blocks containing <tr> rows.
      // We extract them and inject into one consolidated <table>.
      const thead = `
        <thead>
          <tr style="background:#000;color:#94a3b8;font-family:var(--font-mono);font-size:0.64rem;text-transform:uppercase;letter-spacing:0.06em;position:sticky;top:0;z-index:2;">
            <th style="padding:0.38rem 0.6rem;text-align:left;border-bottom:1px solid rgba(255,255,255,0.1);white-space:nowrap;cursor:pointer;" onclick="window.resultsLedger && window.resultsLedger.sortBy('ticker')">Ticker ↕</th>
            <th style="padding:0.38rem 0.5rem;border-bottom:1px solid rgba(255,255,255,0.1);white-space:nowrap;cursor:pointer;" onclick="window.resultsLedger && window.resultsLedger.sortBy('date')">Date ↕</th>
            <th style="padding:0.38rem 0.5rem;border-bottom:1px solid rgba(255,255,255,0.1);white-space:nowrap;">Price / Cap</th>
            <th style="padding:0.38rem 0.5rem;border-bottom:1px solid rgba(255,255,255,0.1);white-space:nowrap;" title="EPS Estimates (Consensus)">EPS Est</th>
            <th style="padding:0.38rem 0.5rem;border-bottom:1px solid rgba(255,255,255,0.1);white-space:nowrap;cursor:pointer;" onclick="window.resultsLedger && window.resultsLedger.sortBy('beat_rate')" title="Historical Beat Rate">Beat% ↕</th>
            <th style="padding:0.38rem 0.5rem;border-bottom:1px solid rgba(255,255,255,0.1);white-space:nowrap;cursor:pointer;" onclick="window.resultsLedger && window.resultsLedger.sortBy('surprise')" title="EPS Surprise % (post-result)">Surprise ↕</th>
            <th style="padding:0.38rem 0.5rem;border-bottom:1px solid rgba(255,255,255,0.1);white-space:nowrap;" title="3D / 7D: · 30D: Returns">Returns</th>
            <th style="padding:0.38rem 0.5rem;border-bottom:1px solid rgba(255,255,255,0.1);text-align:center;cursor:pointer;" onclick="window.resultsLedger && window.resultsLedger.sortBy('edge')" title="AI Edge Score (LightGBM calibrated probability 0-100)">Edge ↕</th>
            <th style="padding:0.38rem 0.5rem;border-bottom:1px solid rgba(255,255,255,0.1);white-space:nowrap;">Setup</th>
            <th style="padding:0.38rem 0.5rem;border-bottom:1px solid rgba(255,255,255,0.1);">S/R Range</th>
            <th style="padding:0.38rem 0.5rem;border-bottom:1px solid rgba(255,255,255,0.1);white-space:nowrap;" title="% from 52-Week High / Low">52W</th>
            <th style="padding:0.38rem 0.5rem;border-bottom:1px solid rgba(255,255,255,0.1);text-align:center;white-space:nowrap;cursor:pointer;" onclick="window.resultsLedger && window.resultsLedger.sortBy('rel_vol')" title="Relative Volume (5D vs 63D avg)">RelVol ↕</th>
          </tr>
        </thead>`;

      // Build tbody: inject day-divider rows + extract <tr> rows from each section HTML
      let tbodyRows = '';
      this.daySectionsMeta.forEach(meta => {
        const relLabel = this._relativeDateLabel(meta.date);
        tbodyRows += `
          <tr class="rl-day-divider results-day-divider" data-date="${meta.date}" data-month="${meta.month_key}">
            <td colspan="12" style="background:#000;padding:0.3rem 0.6rem;border-top:1px solid rgba(255,255,255,0.07);">
              <span style="font-size:0.72rem;font-weight:700;color:#f8fafc;font-family:var(--font-heading);">${this._formatDate(meta.date)}</span>
              ${relLabel ? `<span style="margin-left:0.4rem;font-size:0.6rem;color:#525a6b;font-family:var(--font-mono);">${relLabel}</span>` : ''}
              <span style="margin-left:0.5rem;font-size:0.6rem;color:#6b7485;font-family:var(--font-mono);">${meta.stocks_count} result${meta.stocks_count !== 1 ? 's' : ''}</span>
            </td>
          </tr>`;
        // Extract stock rows from the pre-rendered server HTML blob
        tbodyRows += this._extractTrRows(meta.html);
      });

      container.innerHTML = `
        <table class="results-table" style="width:100%;border-collapse:collapse;table-layout:auto;">
          ${thead}
          <tbody>${tbodyRows}</tbody>
        </table>`;

      // Build industry list from actual row data
      this._buildIndustryList();
    },

    _extractTrRows(html) {
      // Server section HTML contains the <tr> rows; extract by matching <tr ...>...</tr>
      // Use a DOM parser to be safe
      const parser = new DOMParser();
      const doc = parser.parseFromString(`<table><tbody>${html}</tbody></table>`, 'text/html');
      const rows = doc.querySelectorAll('tbody tr');
      let out = '';
      rows.forEach(tr => { out += tr.outerHTML; });
      return out || html; // fallback: inject raw if parsing fails
    },

    _formatDate(dateStr) {
      if (!dateStr) return '—';
      try {
        const d = new Date(dateStr + 'T00:00:00');
        return d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
      } catch { return dateStr; }
    },

    _relativeDateLabel(dateStr) {
      if (!dateStr) return '';
      const today = new Date(); today.setHours(0,0,0,0);
      const d = new Date(dateStr + 'T00:00:00');
      const diff = Math.round((d - today) / 86400000);
      if (diff === 0) return 'Today';
      if (diff === 1) return 'Tomorrow';
      if (diff === -1) return 'Yesterday';
      if (diff > 0) return `T+${diff}`;
      return `T${diff}`;
    },
  ```

- [ ] **Step 2: Add renderMonthStrip()**

  ```js
    renderMonthStrip() {
      const MONTH_NAMES = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
      const now = new Date();
      const curKey = now.toISOString().slice(0, 7);
      const lastKey = new Date(now.getFullYear(), now.getMonth() - 1).toISOString().slice(0, 7);
      const nextKey = new Date(now.getFullYear(), now.getMonth() + 1).toISOString().slice(0, 7);

      const find = (key) => this.months.find(m => m.month_key === key) || null;
      const last = find(lastKey);
      const curr = find(curKey);
      const nxt  = find(nextKey);

      const setCell = (id, labelId, countId, subId, mo, fallbackLabel) => {
        const cell = document.getElementById(id);
        const label = document.getElementById(labelId);
        const count = document.getElementById(countId);
        const sub   = document.getElementById(subId);
        if (!cell) return;
        const m = mo;
        if (label) {
          label.textContent = m
            ? (MONTH_NAMES[parseInt(m.month_key.split('-')[1], 10) - 1] + ' ' + m.month_key.split('-')[0])
            : fallbackLabel;
        }
        if (count) count.textContent = m ? String(m.stocks_count) : '—';
        if (sub && m) sub.textContent = m.is_past ? 'Reported Results' : (m.is_current ? 'Active Season' : 'Scheduled');
        cell.classList.toggle('active',
          this.activeMonth !== 'ALL' && m && this.activeMonth === m.month_key);
      };

      setCell('rl-month-last','rl-month-last-label','rl-month-last-count','rl-month-last-sub', last, 'Last Month');
      setCell('rl-month-this','rl-month-this-label','rl-month-this-count','rl-month-this-sub', curr, 'This Month');
      setCell('rl-month-next','rl-month-next-label','rl-month-next-count','rl-month-next-sub', nxt,  'Next Month');
    },
  ```

- [ ] **Step 3: Add renderDateChipRail()**

  ```js
    renderDateChipRail() {
      const rail = document.getElementById('rl-date-chip-rail');
      if (!rail) return;
      if (!this.daySectionsMeta.length) { rail.style.display = 'none'; return; }

      const allActive = this.selectedDates.size === 0;
      let html = `<button type="button" class="day-chip day-chip-all${allActive ? ' active' : ''}"
        onclick="window.resultsLedger && window.resultsLedger.toggleDate('ALL', event)"
        data-date="ALL"
        style="display:inline-block;margin-right:0.2rem;padding:0.12rem 0.45rem;border-radius:9999px;font-size:0.62rem;font-family:var(--font-mono);cursor:pointer;font-weight:600;border:1px solid;${allActive ? 'background:#f8fafc;color:#000;border-color:#f8fafc;' : 'background:transparent;color:#94a3b8;border-color:rgba(255,255,255,0.15);'}">All</button>`;

      this.daySectionsMeta.forEach(m => {
        const isActive = !allActive && this.selectedDates.has(m.date);
        const rel = this._relativeDateLabel(m.date);
        const label = this._formatDate(m.date) + (rel ? ` · ${rel}` : '');
        html += `<button type="button" class="day-chip${isActive ? ' active' : ''}"
          data-date="${m.date}"
          onclick="window.resultsLedger && window.resultsLedger.toggleDate('${m.date}', event)"
          style="display:inline-block;margin-right:0.2rem;padding:0.12rem 0.45rem;border-radius:9999px;font-size:0.62rem;font-family:var(--font-mono);cursor:pointer;white-space:nowrap;border:1px solid;${isActive ? 'background:#f8fafc;color:#000;border-color:#f8fafc;' : 'background:transparent;color:#6b7485;border-color:rgba(255,255,255,0.1);'}">
          ${label} <span style="font-size:0.56rem;opacity:0.7;">${m.stocks_count}</span>
        </button>`;
      });

      rail.innerHTML = html;
      rail.style.display = 'flex';
      rail.style.flexWrap = 'wrap';
      rail.style.gap = '0.2rem';
    },
  ```

- [ ] **Step 4: Add filterTable() and month/date/cap/density/search/industry controls**

  ```js
    filterTable() {
      const tableRows = document.querySelectorAll(
        '#resultsReportSections table.results-table tbody tr'
      );
      const search = this.searchQuery.toLowerCase();
      const hasDates = this.selectedDates.size > 0;
      const hasIndustries = this.industries.size > 0;

      let visibleCount = 0;
      let currentDividerDate = null;
      let currentDividerMonth = null;

      tableRows.forEach(tr => {
        if (tr.classList.contains('results-day-divider')) {
          currentDividerDate = tr.dataset.date || null;
          currentDividerMonth = tr.dataset.month || null;
          // Divider visibility determined after scanning its rows
          return;
        }

        if (tr.classList.contains('results-row')) {
          // Month filter
          const monthOk = this.activeMonth === 'ALL' || currentDividerMonth === this.activeMonth;
          // Date chip filter
          const dateOk = !hasDates || (currentDividerDate && this.selectedDates.has(currentDividerDate));
          // Cap filter
          const cap = tr.dataset.cap || '';
          const capOk = this.capFilter === 'all' ||
            (this.capFilter === 'large' && cap === 'large') ||
            (this.capFilter === 'small' && cap !== 'large');
          // Industry filter
          const industry = (tr.dataset.industry || '').toLowerCase();
          const indOk = !hasIndustries ||
            [...this.industries].some(i => industry.includes(i.toLowerCase()));
          // Text search
          const searchOk = !search || (
            (tr.dataset.ticker || '').toLowerCase().includes(search) ||
            tr.textContent.toLowerCase().includes(search)
          );

          const visible = monthOk && dateOk && capOk && indOk && searchOk;
          tr.style.display = visible ? '' : 'none';
          if (visible) {
            visibleCount++;
            // Apply density
            tr.classList.toggle('density-standard', this.densityMode === 'standard');
          }
        }
      });

      // Show/hide day-divider rows based on whether they have any visible stock rows
      let divider = null;
      tableRows.forEach(tr => {
        if (tr.classList.contains('results-day-divider')) {
          divider = tr;
          return;
        }
        if (tr.classList.contains('results-row') && divider) {
          if (tr.style.display !== 'none') {
            divider.style.display = '';
          }
        }
      });
      // Second pass: hide dividers with no visible siblings
      let dividerEl = null;
      let dividerHasVisible = false;
      tableRows.forEach((tr, i) => {
        if (tr.classList.contains('results-day-divider')) {
          if (dividerEl && !dividerHasVisible) dividerEl.style.display = 'none';
          dividerEl = tr;
          dividerHasVisible = false;
        } else if (tr.classList.contains('results-row')) {
          if (tr.style.display !== 'none') dividerHasVisible = true;
        }
        if (i === tableRows.length - 1 && dividerEl && !dividerHasVisible) {
          dividerEl.style.display = 'none';
        }
      });

      const matchEl = document.getElementById('resultsFilterMatchCount');
      if (matchEl) matchEl.textContent = visibleCount ? `${visibleCount}` : '';
    },

    setMonth(key) {
      // Called from month strip cells; key is month_key string or 'last'/'this'/'next' alias
      const now = new Date();
      const aliases = {
        last: new Date(now.getFullYear(), now.getMonth() - 1).toISOString().slice(0, 7),
        this: new Date(now.getFullYear(), now.getMonth()).toISOString().slice(0, 7),
        next: new Date(now.getFullYear(), now.getMonth() + 1).toISOString().slice(0, 7),
      };
      const resolvedKey = aliases[key] || key;
      this.activeMonth = (this.activeMonth === resolvedKey) ? 'ALL' : resolvedKey;
      this.selectedDates.clear();

      // Update month cell active states
      ['rl-month-last','rl-month-this','rl-month-next'].forEach((id, idx) => {
        const aliasKey = ['last','this','next'][idx];
        const mk = aliases[aliasKey];
        const cell = document.getElementById(id);
        if (cell) cell.classList.toggle('active', this.activeMonth !== 'ALL' && mk === this.activeMonth);
      });

      this.renderDateChipRail(); // Reset chip states
      this.filterTable();
    },

    toggleDate(dateStr, event) {
      const isMulti = event && (event.ctrlKey || event.metaKey || event.shiftKey);
      if (dateStr === 'ALL') {
        this.selectedDates.clear();
      } else if (isMulti) {
        if (this.selectedDates.has(dateStr)) this.selectedDates.delete(dateStr);
        else this.selectedDates.add(dateStr);
      } else {
        if (this.selectedDates.size === 1 && this.selectedDates.has(dateStr)) {
          this.selectedDates.clear();
        } else {
          this.selectedDates.clear();
          this.selectedDates.add(dateStr);
        }
      }
      this.renderDateChipRail();
      this.filterTable();
    },

    setCapFilter(tier) {
      this.capFilter = tier;
      ['all','large','small'].forEach(t => {
        const btn = document.getElementById(`rl-cap-${t}`);
        if (!btn) return;
        btn.style.background = t === tier ? 'rgba(255,255,255,0.12)' : 'transparent';
        btn.style.color = t === tier ? '#f8fafc' : '#6b7485';
        btn.style.fontWeight = t === tier ? '700' : 'normal';
      });
      this.filterTable();
    },

    setDensity(mode) {
      this.densityMode = mode;
      ['compact','standard'].forEach(m => {
        const btn = document.getElementById(`rl-density-${m}`);
        if (!btn) return;
        btn.style.background = m === mode ? 'rgba(255,255,255,0.12)' : 'transparent';
        btn.style.color = m === mode ? '#f8fafc' : '#6b7485';
        btn.style.fontWeight = m === mode ? '700' : 'normal';
      });
      this.filterTable();
    },

    onSearchInput(query) {
      this.searchQuery = query;
      this.filterTable();
    },

    // --- Industry dropdown ---
    _buildIndustryList() {
      const rows = document.querySelectorAll(
        '#resultsReportSections table.results-table tbody tr.results-row'
      );
      const seen = new Set();
      rows.forEach(tr => {
        const ind = (tr.dataset.industry || '').trim();
        if (ind) seen.add(ind);
      });
      this.allIndustries = [...seen].sort();
      this.industries.clear(); // reset to "all selected"
      this._renderIndustryCheckboxes(this.allIndustries);
    },

    _renderIndustryCheckboxes(list) {
      const container = document.getElementById('resultsIndustryCheckboxList');
      if (!container) return;
      container.innerHTML = list.map(ind => {
        const checked = this.industries.size === 0 || this.industries.has(ind);
        return `<label style="display:flex;align-items:center;gap:0.35rem;font-size:0.66rem;color:#94a3b8;cursor:pointer;padding:0.08rem 0.1rem;">
          <input type="checkbox" value="${this._esc(ind)}" ${checked ? 'checked' : ''}
            onchange="window.resultsLedger && window.resultsLedger.onIndustryCheck(this)"
            style="accent-color:#f8fafc;width:11px;height:11px;">
          <span>${this._esc(ind)}</span>
        </label>`;
      }).join('');
      const selectedCount = document.getElementById('resultsIndustrySelectedCount');
      if (selectedCount) {
        selectedCount.textContent = this.industries.size === 0
          ? 'All selected'
          : `${list.length - this.industries.size} / ${list.length}`;
      }
    },

    onIndustryCheck(checkbox) {
      const val = checkbox.value;
      if (checkbox.checked) {
        this.industries.delete(val);
      } else {
        // When a box is unchecked, we track what's EXCLUDED
        // industries Set = set of excluded industries
        this.industries.add(val);
      }
      this.filterTable();
    },

    selectAllIndustries() {
      this.industries.clear();
      this._renderIndustryCheckboxes(this.allIndustries);
      this.filterTable();
    },

    clearAllIndustries() {
      this.allIndustries.forEach(i => this.industries.add(i));
      this._renderIndustryCheckboxes(this.allIndustries);
      this.filterTable();
    },

    filterIndustryList(query) {
      const q = query.toLowerCase();
      const filtered = this.allIndustries.filter(i => i.toLowerCase().includes(q));
      this._renderIndustryCheckboxes(filtered);
    },

    toggleIndustryDropdown(event) {
      event.stopPropagation();
      const panel = document.getElementById('resultsIndustryDropdownPanel');
      if (!panel) return;
      panel.style.display = panel.style.display === 'none' || !panel.style.display ? 'block' : 'none';
    },

    // --- Sorting ---
    sortBy(field) {
      const tbody = document.querySelector(
        '#resultsReportSections table.results-table tbody'
      );
      if (!tbody) return;
      // Group rows by divider
      const groups = [];
      let currentGroup = null;
      [...tbody.children].forEach(tr => {
        if (tr.classList.contains('results-day-divider')) {
          if (currentGroup) groups.push(currentGroup);
          currentGroup = { divider: tr, rows: [] };
        } else if (tr.classList.contains('results-row') && currentGroup) {
          currentGroup.rows.push(tr);
        }
      });
      if (currentGroup) groups.push(currentGroup);

      const getVal = (tr) => {
        switch (field) {
          case 'ticker': return (tr.dataset.ticker || '').toLowerCase();
          case 'date': return tr.dataset.date || '';
          case 'beat_rate': return parseFloat(tr.dataset.beatRate || '0');
          case 'surprise': return parseFloat(tr.dataset.surprise || '0');
          case 'edge': return parseFloat(tr.dataset.edge || '0');
          case 'rel_vol': return parseFloat(tr.dataset.relVol || '0');
          default: return '';
        }
      };
      const isNumeric = ['beat_rate','surprise','edge','rel_vol'].includes(field);
      const desc = isNumeric; // numeric sorts high-first by default

      groups.forEach(g => {
        g.rows.sort((a, b) => {
          const av = getVal(a), bv = getVal(b);
          if (isNumeric) return desc ? (bv - av) : (av - bv);
          return av < bv ? -1 : av > bv ? 1 : 0;
        });
        tbody.appendChild(g.divider);
        g.rows.forEach(r => tbody.appendChild(r));
      });
    },

    _esc(str) {
      return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
    },
  ```

- [ ] **Step 5: Syntax check**

  ```bash
  node -c earnings_engine/ui/js/modules/results_ledger.js
  ```
  
  Expected: syntax OK

- [ ] **Step 6: Commit**

  ```bash
  git add earnings_engine/ui/js/modules/results_ledger.js
  git commit -m "feat(results-ledger): add renderTable, renderMonthStrip, renderDateChipRail, filterTable

  - Single flat <table> with day-divider rows (no nested <details> accordion)
  - Month strip renders from live API data keyed by current calendar month
  - Date chip rail (monochrome pearl/ink pills, no colour)
  - filterTable() single-pass: month + date + cap + industry + text search
  - sortBy() per-day-group stable sort for ticker/date/beat/surprise/edge/relVol
  - Industry filter tracks excluded set; selectAll/clearAll
  
  Co-Authored-By: Claude Code <noreply@anthropic.com>"
  ```

---

## Task 5: Add secondary module methods — sync, recalc, summarize, export, refreshSinglePrice

**Files:**
- Modify: `earnings_engine/ui/js/modules/results_ledger.js` (add remaining methods)

**Interfaces:**
- Produces: `syncCalendar(btn)`, `recalcPrices(btn)`, `summarize(btn)`, `exportCsv()`, `exportJson()`, `refreshSinglePrice(ticker, btn)`, `updateDomRowWithMetrics(ticker, metrics)`.

- [ ] **Step 1: Add the methods**

  ```js
    // --- Sync Calendar ---
    async syncCalendar(btn) {
      const origHtml = btn ? btn.innerHTML : '📅 Sync';
      if (btn) { btn.disabled = true; btn.textContent = 'Syncing…'; }
      const statusEl = document.getElementById('resultsReportStatus');
      if (statusEl) statusEl.textContent = 'Syncing results calendar from NSE & data feeds…';

      const { aheadDays } = this.getSliderValues();
      const market = document.getElementById('resultsMarket')?.value || 'ALL';

      try {
        const res = await fetch(
          `${window.API_BASE || ''}/api/v1/dashboard/results/sync-calendar?days=${Math.max(aheadDays, 30)}&market=${encodeURIComponent(market)}`,
          { method: 'POST' }
        );
        const data = await res.json();
        if (data.success) {
          if (statusEl) statusEl.textContent = `✓ Synced (${data.synced_count || 0} verified, ${data.inserted_count || 0} new). Reloading…`;
          await this.loadReport();
        } else {
          if (statusEl) statusEl.textContent = `⚠ Sync failed: ${data.detail || data.error || 'Unknown'}`;
        }
      } catch (e) {
        console.error('[ResultsLedger] syncCalendar error:', e);
        if (statusEl) statusEl.textContent = `⚠ Network error: ${e.message || e}`;
      } finally {
        if (btn) { btn.disabled = false; btn.innerHTML = origHtml; }
      }
    },

    // --- Recalc Prices ---
    async recalcPrices(btn) {
      const origHtml = btn ? btn.innerHTML : '⚡ Recalc';
      if (btn) { btn.disabled = true; btn.textContent = 'Recalculating…'; }
      const statusEl = document.getElementById('resultsReportStatus');
      if (statusEl) statusEl.textContent = 'Recalculating live prices, technical setups, S/R metrics…';

      const { pastDays, aheadDays } = this.getSliderValues();
      const market = document.getElementById('resultsMarket')?.value || 'ALL';

      try {
        const res = await fetch(
          `${window.API_BASE || ''}/api/v1/dashboard/results/recalculate-prices?days=${aheadDays}&past_days=${pastDays}&market=${encodeURIComponent(market)}`,
          { method: 'POST' }
        );
        const data = await res.json();
        if (data.success) {
          if (statusEl) statusEl.textContent = `✓ Recalculated ${data.recalculated_count || 0} stocks. Reloading…`;
          await this.loadReport();
        } else {
          if (statusEl) statusEl.textContent = `⚠ Recalc failed: ${data.detail || data.error || 'Unknown'}`;
        }
      } catch (e) {
        console.error('[ResultsLedger] recalcPrices error:', e);
        if (statusEl) statusEl.textContent = `⚠ Network error: ${e.message || e}`;
      } finally {
        if (btn) { btn.disabled = false; btn.innerHTML = origHtml; }
      }
    },

    // --- AI Summarize ---
    async summarize(btn) {
      const origHtml = btn ? btn.innerHTML : '✦ AI Summary';
      if (btn) { btn.disabled = true; btn.textContent = 'Summarizing…'; }
      const { aheadDays } = this.getSliderValues();
      const market = document.getElementById('resultsMarket')?.value || 'ALL';
      try {
        const res = await fetch(
          `${window.API_BASE || ''}/api/v1/dashboard/results/summarize?days=${aheadDays}&market=${encodeURIComponent(market)}`
        );
        const data = await res.json();
        if (data && (data.summary || data.text)) {
          alert('✦ Corporate Results AI Synthesis:\n\n' + (data.summary || data.text));
        } else if (data && data.total_events !== undefined) {
          alert(
            `📊 Results Dataset Summary (${market})\n` +
            `• Total Events: ${data.total_events || 0}\n` +
            `• Beat Rate: ${data.overall_beat_rate ? (data.overall_beat_rate * 100).toFixed(1) + '%' : '—'}\n` +
            `• Up Reactions: ${data.overall_up_rate ? (data.overall_up_rate * 100).toFixed(1) + '%' : '—'}`
          );
        } else {
          alert('Failed to generate summary: ' + (data.error || 'Unknown error'));
        }
      } catch (e) {
        console.error('[ResultsLedger] summarize error:', e);
        alert('Error generating summary: ' + (e.message || e));
      } finally {
        if (btn) { btn.disabled = false; btn.innerHTML = origHtml; }
      }
    },

    // --- Single Price Refresh ---
    async refreshSinglePrice(ticker, btn) {
      if (!ticker) return;
      const origHtml = btn ? btn.innerHTML : '↻';
      if (btn) { btn.disabled = true; btn.textContent = '⏳'; btn.style.opacity = '0.6'; }
      try {
        const res = await fetch(
          `${window.API_BASE || ''}/api/v1/ticker/recalculate?ticker=${encodeURIComponent(ticker)}`,
          { method: 'POST' }
        );
        const data = await res.json();
        if (data.success && data.updated_metrics) {
          this.updateDomRowWithMetrics(ticker, data.updated_metrics);
          if (btn) { btn.textContent = '✓'; btn.style.color = '#34d399'; }
        } else {
          if (btn) { btn.textContent = '✗'; btn.style.color = '#fb7185'; }
        }
        if (btn) {
          setTimeout(() => {
            btn.innerHTML = origHtml; btn.style.color = ''; btn.style.opacity = '1'; btn.disabled = false;
          }, 1500);
        }
      } catch (e) {
        console.error('[ResultsLedger] refreshSinglePrice error:', ticker, e);
        if (btn) { btn.disabled = false; btn.innerHTML = origHtml; btn.style.opacity = '1'; }
      }
    },

    updateDomRowWithMetrics(ticker, metrics) {
      const row = document.querySelector(`#resultsReportSections tr[data-ticker="${CSS.escape(ticker)}"]`);
      if (!row || !metrics) return;
      // Update price cell text if new price provided
      if (metrics.current_price !== undefined) {
        const priceCell = row.querySelector('.cell-current-price');
        if (priceCell) {
          const span = priceCell.querySelector('span');
          if (span) span.textContent = metrics.current_price;
        }
      }
      // Additional metric DOM updates can be wired here as the API expands
    },

    // --- Export ---
    exportCsv() {
      const rows = document.querySelectorAll(
        '#resultsReportSections table.results-table tbody tr.results-row:not([style*="display: none"])'
      );
      if (!rows.length) return;
      const cols = ['Ticker','Date','Cap','Industry','Price','MCap','3D','7D','30D','RelVol','BeatRate'];
      const lines = [cols.join(',')];
      rows.forEach(tr => {
        lines.push([
          tr.dataset.ticker || '',
          tr.querySelector('.cell-earnings-date')?.textContent?.trim().split('\n')[0] || '',
          tr.dataset.cap || '',
          tr.dataset.industry || '',
          tr.dataset.price || '',
          tr.dataset.mcap || '',
          tr.dataset['3dRet'] || '',
          tr.dataset['7dRet'] || '',
          tr.dataset['30dRet'] || '',
          tr.dataset.relVol || '',
          tr.dataset.beatRate || '',
        ].map(v => `"${String(v).replace(/"/g,'""')}"`).join(','));
      });
      const blob = new Blob([lines.join('\n')], { type: 'text/csv' });
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = `results_ledger_${new Date().toISOString().slice(0,10)}.csv`;
      a.click();
    },

    exportJson() {
      const rows = document.querySelectorAll(
        '#resultsReportSections table.results-table tbody tr.results-row:not([style*="display: none"])'
      );
      if (!rows.length) return;
      const data = [...rows].map(tr => ({
        ticker: tr.dataset.ticker,
        cap: tr.dataset.cap,
        industry: tr.dataset.industry,
        price: tr.dataset.price,
        mcap: tr.dataset.mcap,
        ret3d: tr.dataset['3dRet'],
        ret7d: tr.dataset['7dRet'],
        ret30d: tr.dataset['30dRet'],
        rel_vol: tr.dataset.relVol,
        beat_rate: tr.dataset.beatRate,
      }));
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = `results_ledger_${new Date().toISOString().slice(0,10)}.json`;
      a.click();
    },
  ```

- [ ] **Step 2: Syntax check**

  ```bash
  node -c earnings_engine/ui/js/modules/results_ledger.js
  ```

- [ ] **Step 3: Line count check (must be ≤ 600)**

  ```bash
  wc -l earnings_engine/ui/js/modules/results_ledger.js
  ```
  
  If over 600 lines, split utilities (PRESET_MAP, _esc, _formatDate, _relativeDateLabel) into a `results_ledger_utils.js` and import with a second `<script>` tag.

- [ ] **Step 4: Scan error ledger**

  ```bash
  ./.venv/Scripts/python.exe scripts/error_ledger.py scan
  ```

- [ ] **Step 5: Commit**

  ```bash
  git add earnings_engine/ui/js/modules/results_ledger.js
  git commit -m "feat(results-ledger): add syncCalendar, recalcPrices, summarize, export, refreshSinglePrice

  - All async operations delegate to existing API endpoints (no new routes)
  - exportCsv/exportJson operate on visible (non-hidden) rows only
  - refreshSinglePrice updates DOM price cell via updateDomRowWithMetrics
  - summarize fires only on explicit button click (anti-fabrication: on-demand AI)
  
  Co-Authored-By: Claude Code <noreply@anthropic.com>"
  ```

---

## Task 6: Wire module into dashboard.js and script_tags templates

**Files:**
- Modify: `earnings_engine/ui/js/dashboard.js` (add shims, remove extracted functions, init module)
- Modify: `earnings_engine/reports/templates/dashboard/_script_tags.html`
- Modify: `earnings_engine/reports/templates/hubs/dashboard/_script_tags.html`

**Interfaces:**
- Consumes: `window.resultsLedger` (from results_ledger.js loaded before dashboard.js)
- Produces: `app.loadResultsReport`, `app.syncResultsCalendar`, `app.recalculateResultsPrices`, `app.summarizeResults`, `app.filterResultsTable`, `app.setResultsCapFilter`, `app.setResultsTableDensity`, `app.onResultsMarketChange`, `app.onResultsPresetChange`, `app.cancelReportLoad`, `app.exportResultsToCsv`, `app.exportResultsToJson` — all shimmed to delegate to `window.resultsLedger`.

- [ ] **Step 1: Find all results-related function definitions in dashboard.js**

  ```bash
  grep -n "loadResultsReport\|syncResultsCalendar\|recalculateResultsPrices\|summarizeResults\|refreshResults\|renderResultsMonthTabs\|updateResultsMonthSummaryCards\|renderResultsDays\|filterResultsTable\|filterResultsByMonth\|setResultsCapFilter\|setResultsTableDensity\|onResultsMarketChange\|onResultsPresetChange\|exportResultsToCsv\|exportResultsToJson\|openResultsMonthModal\|getResultsPresetDetails\|selectedResultsDates\|toggleDateFilter\|applyDateFilterUI\|resultsActiveMonth\|resultsDaySections\|resultsMonths\|resultsTotalStocks\|resultsShowDays\|toggleResultsIndustryDropdown\|selectAllResultsIndustries\|clearAllResultsIndustries\|filterResultsIndustryList\|onResultsIndustryCheck" \
    earnings_engine/ui/js/dashboard.js | head -60
  ```
  
  Note the line ranges of the functions to remove.

- [ ] **Step 2: Remove extracted functions from dashboard.js**

  Delete the following function bodies from `dashboard.js` (keep their names as skeleton shims):
  - `loadResultsReport()`
  - `summarizeResults()`
  - `refreshResults()`
  - `syncResultsCalendar(btn)`
  - `recalculateResultsPrices(btn)`
  - `renderResultsMonthTabs()`
  - `updateResultsMonthSummaryCards()`
  - `renderResultsDays()`
  - `filterResultsTable(query)`
  - `filterResultsByMonth(key)`
  - `setResultsCapFilter(tier)`
  - `setResultsTableDensity(mode)`
  - `onResultsMarketChange(val)`
  - `onResultsPresetChange(val)`
  - `toggleDateFilter(dateStr, event)`
  - `applyDateFilterUI()`
  - `toggleResultsIndustryDropdown(event)`
  - `selectAllResultsIndustries()`
  - `clearAllResultsIndustries()`
  - `filterResultsIndustryList(query)`
  - `exportResultsToCsv()`
  - `exportResultsToJson()`
  - `showMoreResultsDays()`

  Replace them all with a single shim block at the location of the first removed function:

  ```js
  // ─── Results Ledger: delegated to results_ledger.js module ───────────────
  loadResultsReport()   { return window.resultsLedger?.loadReport(); },
  summarizeResults()    { return window.resultsLedger?.summarize(document.getElementById('resultsSummarizeBtn')); },
  refreshResults()      { return window.resultsLedger?.loadReport(); },
  syncResultsCalendar(btn)        { return window.resultsLedger?.syncCalendar(btn); },
  recalculateResultsPrices(btn)   { return window.resultsLedger?.recalcPrices(btn); },
  cancelReportLoad(domain)        { if (domain === 'results') window.resultsLedger?.cancel(); },
  filterResultsTable(q)           { return window.resultsLedger?.onSearchInput(q); },
  filterResultsByMonth(key)       { return window.resultsLedger?.setMonth(key); },
  setResultsCapFilter(tier)       { return window.resultsLedger?.setCapFilter(tier); },
  setResultsTableDensity(mode)    { return window.resultsLedger?.setDensity(mode); },
  onResultsMarketChange(val)      { return window.resultsLedger?.onMarketChange(val); },
  onResultsPresetChange(val)      { /* sliders handle this — no-op */ },
  toggleDateFilter(date, ev)      { return window.resultsLedger?.toggleDate(date, ev); },
  applyDateFilterUI()             { return window.resultsLedger?.filterTable(); },
  toggleResultsIndustryDropdown(ev)  { return window.resultsLedger?.toggleIndustryDropdown(ev); },
  selectAllResultsIndustries()    { return window.resultsLedger?.selectAllIndustries(); },
  clearAllResultsIndustries()     { return window.resultsLedger?.clearAllIndustries(); },
  filterResultsIndustryList(q)    { return window.resultsLedger?.filterIndustryList(q); },
  exportResultsToCsv()            { return window.resultsLedger?.exportCsv(); },
  exportResultsToJson()           { return window.resultsLedger?.exportJson(); },
  showMoreResultsDays()           { /* no-op in flat table model */ },
  // ─────────────────────────────────────────────────────────────────────────
  ```

- [ ] **Step 3: Add ResultsLedger.init() call in the app init block**

  Find the section in `dashboard.js` that calls `init()` methods for other modules (e.g., `institutionalModule.init(this)` or similar). Add:
  
  ```js
  if (window.resultsLedger) window.resultsLedger.init(this);
  ```

- [ ] **Step 4: Add script tag to _script_tags.html (both paths)**

  Find `earnings_engine/reports/templates/dashboard/_script_tags.html`. Locate where other module scripts are loaded (e.g., `institutional.js`). Add before `dashboard.js`:

  ```html
  <script src="{{ static_prefix }}/ui/js/modules/results_ledger.js?v={{ cache_bust }}"></script>
  ```

  Mirror the identical line to `earnings_engine/reports/templates/hubs/dashboard/_script_tags.html`.

- [ ] **Step 5: Syntax check dashboard.js**

  ```bash
  node -c earnings_engine/ui/js/dashboard.js
  ```
  
  Expected: syntax OK

- [ ] **Step 6: Verify line count reduction in dashboard.js**

  ```bash
  wc -l earnings_engine/ui/js/dashboard.js
  ```
  
  The count should be lower than before (at minimum the ~50+ extracted methods are gone).

- [ ] **Step 7: Commit**

  ```bash
  git add earnings_engine/ui/js/dashboard.js \
          earnings_engine/reports/templates/dashboard/_script_tags.html \
          earnings_engine/reports/templates/hubs/dashboard/_script_tags.html
  git commit -m "refactor(results-ledger): extract results module from dashboard.js, wire shims

  - Remove ~50 results-specific methods from dashboard.js
  - Add shim delegation block: app.* → window.resultsLedger.*
  - ResultsLedger.init(app) called in app init block
  - results_ledger.js loaded as <script> before dashboard.js in both _script_tags
  
  Co-Authored-By: Claude Code <noreply@anthropic.com>"
  ```

---

## Task 7: Design QA with sumi:qa and fix findings

**Files:**
- Modify: Any files flagged in QA findings

**Interfaces:**
- Consumes: The running app (or static HTML review of the template)
- Produces: Verified palette compliance (4 colours only), verified structural patterns, verified accessibility labels, verified empty states

- [ ] **Step 1: Run sumi:qa**

  Invoke the `sumi:qa` skill against the Results Ledger tab. Review all findings.

- [ ] **Step 2: Audit palette compliance manually**

  ```bash
  grep -En "blue|cyan|purple|#3b82f6|#0284c7|#22d3ee|#06b6d4|#60a5fa|#38bdf8|#818cf8|#c084fc|#a78bfa|#fbbf24" \
    earnings_engine/reports/templates/dashboard/_results.html \
    earnings_engine/ui/js/modules/results_ledger.js
  ```
  
  Any hits must be either removed or replaced with the approved palette (Ink/Pearl/Emerald/Rose).

- [ ] **Step 3: Check mirror rule**

  ```bash
  diff earnings_engine/reports/templates/dashboard/_results.html \
       earnings_engine/reports/templates/hubs/dashboard/_results.html
  ```
  
  Must output nothing (files identical).

- [ ] **Step 4: Verify all required element IDs exist**

  ```bash
  for id in rl-slider-past rl-slider-ahead rl-slider-badge rl-preset-chips resultsMarket \
             resultsLoadBtn resultsCancelBtn resultsSyncBtn resultsRecalcAllBtn resultsSummarizeBtn \
             rl-month-strip rl-month-last rl-month-this rl-month-next \
             resultsLiveSearch resultsIndustryDropdownWrapper resultsIndustryDropdownBtn \
             resultsIndustryDropdownPanel resultsIndustryBtnLabel resultsIndustrySearchInput \
             resultsIndustrySelectedCount resultsIndustryCheckboxList resultsFilterMatchCount \
             rl-cap-all rl-cap-large rl-cap-small rl-density-compact rl-density-standard \
             resultsCount rl-date-chip-rail resultsReportSections resultsReportStatus; do
    grep -q "id=\"$id\"" earnings_engine/reports/templates/dashboard/_results.html && echo "OK: $id" || echo "MISSING: $id"
  done
  ```
  
  All must print `OK:`.

- [ ] **Step 5: Fix all QA findings and re-mirror**

  ```bash
  cp earnings_engine/reports/templates/dashboard/_results.html \
     earnings_engine/reports/templates/hubs/dashboard/_results.html
  ```

- [ ] **Step 6: Final error ledger scan**

  ```bash
  ./.venv/Scripts/python.exe scripts/error_ledger.py scan
  ```

- [ ] **Step 7: Final commit and push**

  ```bash
  git add -A
  git commit -m "fix(results-ledger): design QA pass — palette compliance, element IDs, mirror parity

  - sumi:qa findings applied
  - No off-palette colours (all Ink/Pearl/Emerald/Rose)
  - All 31 required element IDs verified present
  - hubs mirror re-synced
  
  Co-Authored-By: Claude Code <noreply@anthropic.com>"
  git push origin new_report
  ```
