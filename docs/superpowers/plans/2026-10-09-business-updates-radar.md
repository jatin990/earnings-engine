# Business Updates Radar & Pre-Earnings Alpha Studio Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a dedicated Business Updates screen in News Harvester with corporate operational disclosures filtering, predictive seasonality scheduler (e.g. PC Jeweller, Titan, DMart, Realty, Auto), and pre-earnings move tracking.

**Architecture:** A multi-tier pipeline: (1) Rule-based & regex classifier in `catalysts_news.py` to isolate operational/business updates from routine result filings, (2) `business_update_schedules` table with Turso sync, (3) Seasonality engine predicting disclosure windows, (4) REST API endpoints in `news.py`, and (5) Subtab UI in `_catalysts.html` and `catalysts.js`.

**Tech Stack:** Python 3.11+, FastAPI, SQLite/Turso libSQL, HTML5/CSS/JavaScript (Nexus Vercel-dark UI).

**Spec:** `docs/superpowers/specs/2026-10-09-business-updates-radar-design.md`

## Global Constraints

- **Anti-Fabrication**: Zero mock/dummy records. If no filings or schedules exist, return empty lists `[]` with explicit empty states.
- **Turso Sync Contract**: Register `business_update_schedules` in `SYNC_TABLES`, `WATERMARK_CANDIDATE_COLUMNS`, and `DATE_ONLY_COLUMNS` in `earnings_engine/data/turso_sync.py`.
- **API Precedence**: Explicit static routes before parameterized routes in `news.py`.
- **Frontend Governance**: JavaScript files validated with `node -c`, zero inline scripts.

## Review Focus

1. **False Positive Result Intimations**: Regular "Board meeting for financial results" must not be tagged as business updates.
2. **Date Window Edge Cases**: End of quarter calculation across Leap Years and Month-end transitions (e.g., Dec 31 -> Jan 1-10 window).
3. **Empty / Market Closed State**: Clean fallback UI when no updates have been reported in the selected lookback window.
4. **Symbol Resolution**: Proper handling of NSE `.NS` ticker formatting.
5. **Turso Sync Watermark**: Graceful handling when SQLite is queried locally without cloud connection.

---

### Task 1: Data Model, Classification Engine & Turso Sync Contract

**Files:**
- Modify: `earnings_engine/data/db.py`
- Modify: `earnings_engine/data/turso_sync.py`
- Modify: `earnings_engine/data/catalysts_news.py`
- Test: `tests/test_business_updates_classification.py`

**Interfaces:**
- Produces: `is_business_update_headline(title: str, summary: str = "") -> bool`, `CATALYST_RULES["Business Updates & Operational Disclosures"]`, `business_update_schedules` table.

- [ ] **Step 1: Write the failing classification test**

```python
# tests/test_business_updates_classification.py
from earnings_engine.data.catalysts_news import is_business_update_headline, classify_catalyst_category

def test_business_update_detection():
    # True positives: Operational & Business updates
    assert is_business_update_headline("PC Jeweller Ltd: Quarterly Business Update for Q3 FY25")
    assert is_business_update_headline("Titan Company: Key Operational Highlights for Q3")
    assert is_business_update_headline("Avenue Supermarts (DMart): Standalone Revenue & Store Count Update")
    assert is_business_update_headline("Godrej Properties: Q3 Pre-Sales & Gross Booking Value reaches record high")
    assert is_business_update_headline("Bajaj Auto: Monthly Sales & Dispatches December 2024")
    assert is_business_update_headline("HDFC Bank: Gross Advances and Deposits Update for Quarter ended Dec 31")

    # False positives: Regular results or routine board meetings
    assert not is_business_update_headline("TCS: Board Meeting on Jan 12 to consider Financial Results")
    assert not is_business_update_headline("Infosys Ltd: Un-audited Financial Results for Q3 FY25")
    assert not is_business_update_headline("Reliance Industries: Notice of Postal Ballot")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_business_updates_classification.py -v`
Expected: FAIL with `ImportError` or `AssertionError`.

- [ ] **Step 3: Implement Schema, Classification Rule, and Turso Sync**

Update `earnings_engine/data/catalysts_news.py` to add `is_business_update_headline` and update `CATALYST_RULES` with `Business Updates & Operational Disclosures`.
Update `earnings_engine/data/db.py` to add `business_update_schedules` table schema.
Update `earnings_engine/data/turso_sync.py` to add `business_update_schedules` to `SYNC_TABLES`.

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_business_updates_classification.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add earnings_engine/data/db.py earnings_engine/data/turso_sync.py earnings_engine/data/catalysts_news.py tests/test_business_updates_classification.py
git commit -m "feat(news): add business updates classification rules, schema and Turso sync contract"
```

---

### Task 2: Predictive Seasonality & Anticipated Schedule Engine

**Files:**
- Create: `earnings_engine/data/business_updates_scheduler.py`
- Test: `tests/test_business_updates_scheduler.py`

**Interfaces:**
- Consumes: `Settings`, SQLite connection from `earnings_engine.data.db`.
- Produces: `compute_anticipated_business_update_schedules(settings, as_of_date=None) -> list[dict]`, `get_anticipated_schedules(settings, status=None, days_ahead=14) -> list[dict]`, `sync_business_update_schedules_db(settings) -> int`.

- [ ] **Step 1: Write the failing scheduler test**

```python
# tests/test_business_updates_scheduler.py
from datetime import date
from earnings_engine.data.business_updates_scheduler import (
    compute_anticipated_business_update_schedules,
    KNOWN_UPDATE_CADENCES,
)

def test_cadence_calculation():
    # Test for Q3 season (as of Jan 2)
    schedules = compute_anticipated_business_update_schedules(as_of_date=date(2025, 1, 2))
    assert len(schedules) > 0
    pcj = next((s for s in schedules if "PCJEWELLER" in s["ticker"]), None)
    assert pcj is not None
    assert pcj["status"] in ["ANTICIPATED", "DUE_NOW"]
    assert "2025-01" in pcj["next_expected_window_start"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_business_updates_scheduler.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `earnings_engine/data/business_updates_scheduler.py`**

Implement cadence calculations, quarter/month-end projections, and DB upsert logic.

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_business_updates_scheduler.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add earnings_engine/data/business_updates_scheduler.py tests/test_business_updates_scheduler.py
git commit -m "feat(news): implement predictive business updates seasonality and schedule engine"
```

---

### Task 3: REST API Endpoints

**Files:**
- Modify: `earnings_engine/api/routers/news.py`
- Test: `tests/test_business_updates_api.py`

**Interfaces:**
- Produces:
  - `GET /api/v1/news/business-updates`
  - `GET /api/v1/news/business-updates/schedules`
  - `POST /api/v1/news/business-updates/sync-schedules`

- [ ] **Step 1: Write the failing API test**

```python
# tests/test_business_updates_api.py
from fastapi.testclient import TestClient
from earnings_engine.api.server import app

client = TestClient(app)

def test_get_business_updates():
    resp = client.get("/api/v1/news/business-updates?days=30")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "updates" in data
    assert "stats" in data

def test_get_business_update_schedules():
    resp = client.get("/api/v1/news/business-updates/schedules")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "schedules" in data
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_business_updates_api.py -v`
Expected: FAIL with 404 Not Found.

- [ ] **Step 3: Implement API endpoints in `earnings_engine/api/routers/news.py`**

Declare endpoints before parameterized routes as per CLAUDE.md guidelines.

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_business_updates_api.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add earnings_engine/api/routers/news.py tests/test_business_updates_api.py
git commit -m "feat(api): add REST endpoints for business updates and anticipated schedules"
```

---

### Task 4: UI Subtab, KPI Cards & Navigation in News Harvester

**Files:**
- Modify: `earnings_engine/reports/templates/dashboard/_catalysts.html`
- Modify: `earnings_engine/reports/templates/dashboard/_sidebar.html`
- Modify: `earnings_engine/ui/js/modules/catalysts.js`

**Interfaces:**
- Subtab navigation: `feed`, `business-updates`, `schedules`, `outcomes`.
- Methods: `app.loadBusinessUpdates()`, `app.loadBusinessUpdateSchedules()`, `app.renderBusinessUpdates()`, `app.renderBusinessUpdateSchedules()`.

- [ ] **Step 1: Add HTML views and controls to `_catalysts.html` and `_sidebar.html`**

Add `catalystsBusinessUpdatesView` and `catalystsSchedulesView` with KPI cards, filters, and high-density responsive tables/cards. Add sidebar subtab links in `_sidebar.html`.

- [ ] **Step 2: Add JavaScript module methods to `catalysts.js`**

Implement data fetching, filtering, rendering, and inspector drawer binding.

- [ ] **Step 3: Validate JavaScript syntax**

Run: `node -c earnings_engine/ui/js/modules/catalysts.js`
Expected: Clean pass with no syntax errors.

- [ ] **Step 4: Commit and Push to `origin/new_report`**

```bash
git add earnings_engine/reports/templates/dashboard/_catalysts.html earnings_engine/reports/templates/dashboard/_sidebar.html earnings_engine/ui/js/modules/catalysts.js
git commit -m "feat(ui): add dedicated Business Updates screen and Anticipated Schedules calendar to News Harvester"
git push origin new_report
```
