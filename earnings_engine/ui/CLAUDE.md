# CLAUDE.md — Frontend & UI Subsystem (`earnings_engine/ui/`)

> Subsystem guide for frontend static assets, modular JavaScript architecture, CSS styles, and interactive dashboards.

---

## 1. Scope & Architecture

The UI subsystem powers the high-density terminal interface across research radars, institutional forensics, portfolio operations, and stock detail views.

- **Main Dashboard JS**: `earnings_engine/ui/js/dashboard.js` (tab coordination, global event listeners)
- **Stock Detail JS**: `earnings_engine/ui/js/stock_detail.js` (charting, AI matrix, company intelligence)
- **Domain Modules**: `earnings_engine/ui/js/modules/*.js` (dedicated scripts for `swing.js`, `options.js`, `institutional.js`, `recent_additions.js`, etc.)
- **Styles**: `earnings_engine/ui/css/` (dark-theme terminal styling, responsive grids, high-density tables)

---

## 2. Core Invariants & Rules

### 2.1 Modular Architecture & Clean Separation
- Keep domain logic inside dedicated modules under `ui/js/modules/` rather than bloating `dashboard.js`.
- Coordinate global actions (modals, toast notifications, hash navigation) via structured event dispatchers.
- Use hash-based tab navigation (`#breakout`, `#swing`, `#tri-confluence`, `#options`, `#premarket`, `#news`, `#institutional`).

### 2.2 Strict Anti-Fabrication in the Frontend
- **Zero Mock Fallbacks**: Never insert placeholder values, static dummy numbers, or pseudo-random fallbacks in UI cards or table rows.
- If an API returns `None` or `[]`, display an explicit, honest empty state (e.g., `Market Closed · Weekend Snapshot`, `No Institutional Filings Available`).

### 2.3 Universal Timeframe & Temporal Baseline Display
- Every metric, delta, signal, accumulation flow, momentum score, and forecast rendered in UI cards MUST declare its baseline:
  - Returns: `7D: +4.2%`, `30D: -1.8%`, `52W High / Low`
  - Volume: `Surge: 2.4x (5D vs 63D avg)`
  - Freshness: Explicit timestamp badge (`🟢 Live Quote`, `📊 EOD Snapshot`, `As of 15:30 IST`)

### 2.4 On-Demand AI Execution
- Never trigger automated consensus or LLM analysis upon opening a tab or modal.
- Provide clear user-initiated triggers ("Run AI Consensus") with visual loading states.
