# Zepto Dark Store Master-Detail Operations & Metrics Expansion Design

**Date:** 2026-10-01
**Topic:** Zepto Dark Store Operations & Analytics System (Master-Detail Drawers, Domain Sub-Tabs, Ingestion Pipelines)
**Status:** Approved

---

## 1. Overview & Architecture

The Zepto Dark Store Operations Hub (`/zepto`) serves store operators managing day-to-day workforce execution, warehouse throughput, inventory damage/shrinkage loss reconciliation, and financial equity splits.

This design introduces:
1. **6 Clean Operational Domain Tabs**:
   - `[ 👥 Roster & Attendance ]` (`#attendance`) — Shift muster, timeline heatmap, capacity cards, and employee slide drawer.
   - `[ ⚡ Manpower & IPP ]` (`#utilization`) — Picker/packer throughput, Items Picked Per Hour (IPP), idle labor leakage.
   - `[ 📉 Loss & Shrinkage ]` (`#loss`) — Store DQ loss (damaged/expired items), cycle count variance, short-pick shrinkage.
   - `[ 📊 Store Scorecard ]` (`#scorecard`) — Daily sales GMV, delivered order count, AOV, SLA fulfillment %.
   - `[ 💰 Financials & P&L ]` (`#income`, `#expenses`, `#security`) — Store income, out-of-pocket expenses, 50-50 partner split.
   - `[ 📧 Linked Mailbox ]` (`#gmail`) — Live store email feed and automated attachment ingestion.

2. **Master-Detail Slide-Out Drawers (`sumi:desktop-app-design`)**:
   - **Employee Attendance & Shift Inspector Drawer (`#attEmployeeDrawer`)**: 480px sliding drawer displaying 30-day punch calendars, exact in/out timestamps, hours worked, and churn risk grading.
   - **Loss & Shrinkage Category Inspector Drawer**: Sliding drawer breaking down daily loss by category (Fruits & Vegetables, Dairy, Meat, FMCG, Pilferage).
   - **Picker IPP Throughput Drawer**: Hourly and daily picking speed trends per worker.

---

## 2. Database Schema Extensions & `SYNC_TABLES`

To support real dark store operational streams from daily emails and spreadsheets, we define three new tables with Turso sync:

### 2.1 `zepto_store_metrics`
- `id` (TEXT PRIMARY KEY, e.g. `met_JMU_<date>`)
- `store_name` (TEXT)
- `metric_date` (TEXT, YYYY-MM-DD)
- `sales_gmv` (REAL)
- `order_count` (INTEGER)
- `aov` (REAL)
- `inbound_hours` (REAL)
- `outbound_hours` (REAL)
- `packer_ipp` (REAL)
- `sla_adherence_pct` (REAL)
- `raw_source` (TEXT)
- `created_at` (TEXT)

### 2.2 `zepto_loss_records`
- `id` (TEXT PRIMARY KEY, e.g. `loss_<md5>`)
- `store_name` (TEXT)
- `record_date` (TEXT, YYYY-MM-DD)
- `loss_type` (TEXT: `DQ_LOSS`, `EXPIRY`, `SHRINKAGE`, `CYCLE_COUNT_VARIANCE`, `SHORT_PICK`)
- `category` (TEXT: `FRUITS_VEG`, `DAIRY`, `MEAT`, `FMCG`, `GENERAL`)
- `amount` (REAL)
- `sku_count` (INTEGER)
- `notes` (TEXT)
- `created_at` (TEXT)

### 2.3 `zepto_manpower_utilization`
- `id` (TEXT PRIMARY KEY, e.g. `util_<md5>`)
- `store_name` (TEXT)
- `util_date` (TEXT, YYYY-MM-DD)
- `employee_id` (TEXT)
- `employee_name` (TEXT)
- `role` (TEXT)
- `items_picked` (INTEGER)
- `active_pick_hours` (REAL)
- `idle_hours` (REAL)
- `ipp` (REAL)
- `flex_labor_cost` (REAL)
- `created_at` (TEXT)

*All 3 tables are added to `SYNC_TABLES`, `WATERMARK_CANDIDATE_COLUMNS`, and `DATE_ONLY_COLUMNS`.*

---

## 3. REST API Contracts (`earnings_engine/api/routers/zepto.py`)

- `GET /api/v1/zepto/attendance/employee/{employee_id}`: Returns 30-day chronological punch records, cumulative hours, punctuality score, and risk metrics for the slide drawer.
- `GET /api/v1/zepto/metrics/summary`: Returns GMV, order volume, AOV, and SLA adherence trends.
- `GET /api/v1/zepto/loss/summary`: Returns total DQ loss, category-wise breakdown, and shrinkage variance trends.
- `GET /api/v1/zepto/utilization/summary`: Returns team-wide picker IPP, active vs idle man-hours, and top performers.

---

## 4. Frontend Master-Detail UI Components

- `_attendance.html`: Added side-drawer modal container `#attEmployeeDrawer` with glass backdrop, punch timeline pills, and export options.
- `_utilization.html`: IPP leaderboard, active vs idle gauge, and hourly throughput chart.
- `_loss.html`: Category damage breakdown donuts, shrinkage trendline, and RTV recovery ledger.
- `_scorecard.html`: Daily GMV cards, order volume timelines, and SLA fulfillment radar.
- `zepto.js`: Added event handlers `openEmployeeDrawer(empId)`, `renderEmployeeDrawer(data)`, `closeEmployeeDrawer()`, and keyboard listener (`Escape` to close).

---

## 5. Testing & Verification

1. **Unit & DAL Tests**: `tests/test_zepto_hub.py`, `tests/test_zepto_attendance_db.py` covering drawer endpoints, schema migration, and metric aggregations.
2. **UI & Routing Tests**: Verify navigation across all 6 tabs without console errors.
3. **Turso Sync Verification**: Ensure tables are tracked in `SYNC_TABLES`.
