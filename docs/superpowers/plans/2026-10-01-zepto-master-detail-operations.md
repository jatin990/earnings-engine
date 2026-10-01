# Zepto Dark Store Master-Detail Operations & Analytics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build comprehensive master-detail operations in the Zepto Hub with an Employee Attendance & Shift Drawer, Manpower Utilization & IPP tab, Loss & Shrinkage tab, and Daily Store Metrics Scorecard tab.

**Architecture:** Extend SQLite schemas with Turso sync (`zepto_store_metrics`, `zepto_loss_records`, `zepto_manpower_utilization`), expose REST APIs in `earnings_engine/api/routers/zepto.py`, and build high-density interactive partials and slide drawers following `sumi:desktop-app-design`.

**Tech Stack:** Python 3.14 (FastAPI, SQLite WAL), Tailwind CSS, Vanilla JS.

**Spec:** `docs/superpowers/specs/2026-10-01-zepto-master-detail-operations-design.md`

## Global Constraints
- Zero external package dependencies for charting or parsing. Pure responsive HTML/CSS/SVG.
- Strict anti-fabrication: show clear empty states if data is missing.
- Register all new tables in `SYNC_TABLES`, `WATERMARK_CANDIDATE_COLUMNS`, and `DATE_ONLY_COLUMNS` (`earnings_engine/data/turso_sync.py`).
- All interactive drawers must support smooth right-slide transition, click-outside backdrop dismiss, and `Escape` key close.

## Review Focus
1. **Employee Drawer Missing Records**: If an employee has no punch history in DB, drawer must render empty state gracefully without JS errors.
2. **Category Loss Breakdown Integrity**: Ensure damage and shrinkage totals match aggregate sums across all categories.
3. **Drawer Focus & Scrolling**: When drawer is open, background scroll must not bleed through.
4. **Date Filtering Precedence**: Verify tab date filters correctly constrain metrics across scorecard, loss, and utilization.
5. **Mobile Responsiveness**: Ensure 480px slide drawers collapse to full width on narrow screens (< 640px).

---

### Task 1: Database Schemas, SYNC_TABLES & DAL Methods
**Files:**
- Modify: `earnings_engine/data/zepto_db.py`
- Modify: `earnings_engine/data/turso_sync.py`
- Test: `tests/test_zepto_attendance_db.py`

- [ ] **Step 1: Write failing test in `tests/test_zepto_attendance_db.py` for new tables, employee shift details query, and metric DAL functions**
- [ ] **Step 2: Run pytest to verify test failure**
- [ ] **Step 3: Update `zepto_db.py` to create tables:**
  - `zepto_store_metrics`
  - `zepto_loss_records`
  - `zepto_manpower_utilization`
  - Implement `get_employee_attendance_detail(emp_id)`
  - Implement `get_store_metrics_summary()`, `get_loss_summary()`, `get_manpower_utilization_summary()`
- [ ] **Step 4: Register tables in `SYNC_TABLES` in `turso_sync.py`**
- [ ] **Step 5: Run pytest to verify all tests pass**
- [ ] **Step 6: Commit changes**

---

### Task 2: Employee Shift & Metrics REST Endpoints
**Files:**
- Modify: `earnings_engine/api/routers/zepto.py`
- Test: `tests/test_zepto_hub.py`

- [ ] **Step 1: Write failing test in `tests/test_zepto_hub.py` for `/api/v1/zepto/attendance/employee/{emp_id}`, `/metrics/summary`, `/loss/summary`, `/utilization/summary`**
- [ ] **Step 2: Run pytest to verify failure**
- [ ] **Step 3: Implement endpoints in `zepto.py` before parameterized routes**
- [ ] **Step 4: Run pytest to verify endpoints pass**
- [ ] **Step 5: Commit changes**

---

### Task 3: Interactive Employee Slide-Out Drawer (`#attEmployeeDrawer`)
**Files:**
- Modify: `earnings_engine/reports/templates/hubs/zepto/_attendance.html`
- Modify: `earnings_engine/ui/js/modules/zepto.js`
- Test: `tests/test_zepto_hub.py`

- [ ] **Step 1: Add HTML markup in `_attendance.html` for `#attEmployeeDrawer` with backdrop, hero header, 30-day punch calendar, adherence badge, and shift list**
- [ ] **Step 2: Add `openEmployeeDrawer(empId)`, `renderEmployeeDrawer(data)`, `closeEmployeeDrawer()` in `zepto.js`**
- [ ] **Step 3: Wire table row and watchlist clicks to `zeptoApp.openEmployeeDrawer(emp_id)`**
- [ ] **Step 4: Run pytest to verify template rendering**
- [ ] **Step 5: Commit changes**

---

### Task 4: Manpower Utilization, Loss & Shrinkage, and Scorecard Sub-Tabs
**Files:**
- Create: `earnings_engine/reports/templates/hubs/zepto/_utilization.html`
- Create: `earnings_engine/reports/templates/hubs/zepto/_loss.html`
- Create: `earnings_engine/reports/templates/hubs/zepto/_scorecard.html`
- Modify: `earnings_engine/reports/templates/hubs/zepto/index.html` (or main hub wrapper)
- Modify: `earnings_engine/ui/js/modules/zepto.js`
- Test: `tests/test_zepto_hub.py`

- [ ] **Step 1: Create Jinja partials `_utilization.html`, `_loss.html`, `_scorecard.html`**
- [ ] **Step 2: Update navigation tabs in Zepto Hub template**
- [ ] **Step 3: Add `loadUtilization()`, `loadLoss()`, `loadScorecard()` in `zepto.js`**
- [ ] **Step 4: Run pytest to verify all tabs render correctly**
- [ ] **Step 5: Commit changes**

---

### Task 5: End-to-End Verification & Remote Push
- [ ] **Step 1: Run complete test suite (`pytest tests/test_zepto_*.py`)**
- [ ] **Step 2: Verify git status and push to `origin/new_report`**
