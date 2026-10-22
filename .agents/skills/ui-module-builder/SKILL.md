---
name: ui-module-builder
description: Modular vanilla JavaScript architecture, HTML template governance, baseline badging, syntax validation with node -c, and anti-bloat UI patterns. Use when modifying or adding frontend modules.
---

# UI Module Builder & Governance Protocol

Use this skill whenever authoring or modifying frontend JavaScript modules, Jinja2 templates, or UI components.

---

## 1. Modular Directory Structure & Size Limits

- **File Location**: All client scripts must reside in `earnings_engine/ui/js/modules/*.js`.
- **Size Limits**:
  - Maximum **400 lines** per JS module (hard ceiling at 500 lines).
  - If a module exceeds 400 lines, extract helper utilities into a sub-module (e.g. `stock_drawer_charts.js`).
- **No Monolithic Global Scripts**: Keep modules self-contained; export initialization functions (e.g. `export function initStockDrawer()`).

---

## 2. Template Architecture & Hygiene

- **Canonical Template Path**:
  - Live templates reside in `reports/templates/hubs/dashboard/<name>.html`.
  - If legacy path `reports/templates/dashboard/<name>.html` is present, keep them mirrored.
- **Zero Inline Script Tags**:
  - Do NOT write inline `<script>` tags containing business logic or event bindings inside HTML templates.
  - Bind event listeners cleanly via `document.addEventListener` or data attributes (`data-action="..."`) inside modular JS files.

---

## 3. Explicit Timeframe & Baseline Badging

Never render bare percentage changes. Every metric, delta, surge, or performance pill must display its baseline:
- Return pill: `7D: +4.2%`, `52W Range`, `1M: -1.8%`.
- Volume pill: `Surge: 2.4x (5D vs 63D avg)`.
- State pill: `Live Quote`, `EOD Snapshot`, `Market Closed`.

---

## 4. Frontend Syntax & Integrity Verification

Always validate JavaScript syntax before committing:
```bash
node -c earnings_engine/ui/js/modules/<your_module>.js
```
Scan the error ledger to ensure zero UI or template errors:
```bash
./.venv/Scripts/python.exe scripts/error_ledger.py scan
```
