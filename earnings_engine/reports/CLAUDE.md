# CLAUDE.md — Reports & Jinja2 Templates (`earnings_engine/reports/`)

> Subsystem guide for Jinja2 HTML templates, partial tab views, stock detail renders, and report exporters.

---

## 1. Scope & Architecture

The reports subsystem manages server-side HTML rendering, Jinja2 partial templates for the dashboard hubs, stock detail views, and CSV/HTML report generation.

- **Dashboard Templates**: `earnings_engine/reports/templates/dashboard/` (modular subtab partials: `_institutional.html`, `_breakout.html`, `_new_additions.html`, etc.)
- **Hub Mirror Templates**: `earnings_engine/reports/templates/hubs/dashboard/` (mirrored templates for scoped operations hubs)
- **Stock Detail Template**: `earnings_engine/reports/templates/stock_detail.html` (comprehensive equity intelligence view)
- **Export Engines**: `earnings_engine/reports/generator.py` (HTML/CSV report generation pipelines)

---

## 2. Core Invariants & Rules

### 2.1 Template Mirroring Rule
- When editing or adding templates that exist in both paths:
  1. `earnings_engine/reports/templates/dashboard/<name>.html`
  2. `earnings_engine/reports/templates/hubs/dashboard/<name>.html`
  - **Always keep both files synchronized and identical** to prevent divergent behavior across different entrypoints.

### 2.2 Split-Window Layout Conventions
- Standard 50-50 Split Layouts (e.g., Institutional Intelligence, Recent Additions & IPO Tracker) use responsive CSS Grid:
  ```css
  grid-template-columns: minmax(0, 1.05fr) minmax(0, 0.95fr);
  ```
- Left Pane: Data tables with sorting, filtering, and row selectors.
- Right Pane: Sticky inspector card displaying detailed breakdown modules.

### 2.3 Semantic Markup & Accessibility
- Always include explicit labels, tooltips, and timeframe badges in rendered templates.
- Maintain consistent dark-mode styling variables and high-density typography.
