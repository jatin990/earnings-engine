# Zepto Dark Store Attendance Report Parser & Analytics Hub Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a robust, zero-dependency Excel attendance report parser for Zepto Dark Store muster files, persist normalized attendance data into SQLite with Turso cloud sync, expose REST API analytics endpoints, and deliver a comprehensive attendance dashboard tab with Gmail auto-sync in the Zepto Dark Store Hub (`/zepto#attendance`).

**Architecture:** A native `.xlsx` parser (`earnings_engine/data/zepto_attendance_parser.py`) converts raw workbook spreadsheets and date serials into normalized employee muster records. A data access layer in `zepto_db.py` persists imports and records into SQLite cache with cloud sync in `turso_sync.py`. FastAPI endpoints in `earnings_engine/api/routers/zepto.py` provide upload, query, summary aggregation, and Gmail attachment extraction. The frontend UI in `earnings_engine/reports/templates/hubs/zepto/` and `zepto.js` visualizes attendance KPIs, role distributions, and muster data tables.

**Tech Stack:** Python 3.11+, standard library `zipfile` & `xml.etree.ElementTree` (with `openpyxl` fallback), SQLite3 (WAL mode), FastAPI, Jinja2, Tailwind CSS, Chart.js / Vanilla JS.

**Spec:** `docs/superpowers/specs/2026-09-30-zepto-attendance-parser-design.md`

## Global Constraints

- Never use pseudo-random or dummy mock values in UI or API payloads.
- Must support pure Python stdlib parsing of `.xlsx` (via `zipfile` and XML) so it runs offline without required external C-extensions.
- All new SQLite tables (`zepto_attendance_imports`, `zepto_attendance_records`) must be registered in `SYNC_TABLES` in `earnings_engine/data/turso_sync.py`.
- Targeted unit tests must execute cleanly using `.\.venv\Scripts\python.exe -m pytest tests/<test_file>.py -v`.
- Always commit and push changes upon task completion.

## Review Focus

1. Excel date serial numbers with fractional time (e.g. `46291.35`) correctly translate to ISO date (`2026-09-29`) and standard 24h punch timestamps (`08:24:00`).
2. Robust header resolution handles alternate column casing/naming (`Emp ID`, `Employee Code`, `Staff ID`, `Punch In`, `In Time`).
3. Attendance rate calculation correctly excludes scheduled week offs (`WO`) and dark store festive closures (`F`) from the absenteeism denominator.
4. Large attendance reports (e.g. 10,000+ punches) insert efficiently via `executemany` with non-blocking SQLite transaction boundaries.
5. Ingestion of duplicate/re-uploaded reports replaces or upserts records idempotently using unique composite key hashing (`MD5(store + emp_id + date)`).

---

### Task 1: Zero-Dependency Zepto Attendance Excel Parser

**Files:**
- Create: `earnings_engine/data/zepto_attendance_parser.py`
- Test: `tests/test_zepto_attendance_parser.py`

**Interfaces:**
- Produces: `parse_zepto_attendance_excel(file_bytes_or_path, file_name: str = "") -> dict`
- Data structure returned:
  ```python
  {
      "store_name": str,
      "start_date": str, # YYYY-MM-DD
      "end_date": str,   # YYYY-MM-DD
      "total_records": int,
      "total_employees": int,
      "records": [
          {
              "employee_id": str,
              "employee_name": str,
              "designation": str,
              "shift_date": str, # YYYY-MM-DD
              "shift_name": str,
              "shift_time": str,
              "punch_in": str,
              "punch_out": str,
              "work_duration_mins": int,
              "break_duration_mins": int,
              "raw_status": str,
              "status": str, # PRESENT | ABSENT | WEEK_OFF | HALF_DAY | HOLIDAY
          }
      ],
      "summary": {
          "present_count": int,
          "absent_count": int,
          "week_off_count": int,
          "half_day_count": int,
          "holiday_count": int,
          "attendance_rate_pct": float
      }
  }
  ```

- [ ] **Step 1: Write failing unit test for the Excel parser**

`tests/test_zepto_attendance_parser.py`:
```python
import pytest
from earnings_engine.data.zepto_attendance_parser import (
    parse_zepto_attendance_excel,
    excel_date_to_iso,
    normalize_muster_status,
)

def test_excel_date_to_iso():
    assert excel_date_to_iso(46291) == "2026-09-29"
    assert excel_date_to_iso("2026-09-29") == "2026-09-29"
    assert excel_date_to_iso(46257) == "2026-08-26"

def test_normalize_muster_status():
    assert normalize_muster_status("P") == "PRESENT"
    assert normalize_muster_status("A") == "ABSENT"
    assert normalize_muster_status("A-R") == "ABSENT"
    assert normalize_muster_status("WO") == "WEEK_OFF"
    assert normalize_muster_status("HD") == "HALF_DAY"
    assert normalize_muster_status("F") == "HOLIDAY"
    assert normalize_muster_status("UNKNOWN") == "PRESENT"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_zepto_attendance_parser.py -v`  
Expected: FAIL with `ModuleNotFoundError: No module named 'earnings_engine.data.zepto_attendance_parser'`

- [ ] **Step 3: Implement `zepto_attendance_parser.py`**

Implement pure stdlib XML/Zip parser with date serial conversions, header discovery, time parsing, and summary calculations.

- [ ] **Step 4: Run tests to verify pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_zepto_attendance_parser.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add earnings_engine/data/zepto_attendance_parser.py tests/test_zepto_attendance_parser.py
git commit -m "feat(zepto): implement zero-dependency attendance excel parser with date and status normalization"
```

---

### Task 2: Database Schema & DAL Functions for Attendance

**Files:**
- Modify: `earnings_engine/data/zepto_db.py`
- Modify: `earnings_engine/data/turso_sync.py`
- Test: `tests/test_zepto_attendance_db.py`

**Interfaces:**
- Produces in `zepto_db.py`:
  - `save_attendance_batch(parsed_data: dict, source: str = 'UPLOAD') -> dict`
  - `get_attendance_summary(store_name: str = None, start_date: str = None, end_date: str = None) -> dict`
  - `get_attendance_records(store_name: str = None, employee_id: str = None, designation: str = None, status: str = None, date: str = None, limit: int = 100, offset: int = 0) -> list[dict]`
  - `get_attendance_imports(limit: int = 20) -> list[dict]`
  - `delete_attendance_import(import_id: str) -> bool`

- [ ] **Step 1: Write failing test for attendance database operations**

`tests/test_zepto_attendance_db.py`:
```python
import pytest
from earnings_engine.data.zepto_db import (
    ensure_zepto_schema,
    save_attendance_batch,
    get_attendance_summary,
    get_attendance_records,
    get_attendance_imports,
    delete_attendance_import,
)
from earnings_engine.data.turso_sync import SYNC_TABLES

def test_sync_tables_includes_attendance():
    assert "zepto_attendance_imports" in SYNC_TABLES
    assert "zepto_attendance_records" in SYNC_TABLES

def test_attendance_db_lifecycle():
    ensure_zepto_schema()
    mock_parsed = {
        "store_name": "JMU-Sainik Colony",
        "start_date": "2026-09-01",
        "end_date": "2026-09-02",
        "total_records": 2,
        "total_employees": 1,
        "records": [
            {
                "employee_id": "EMP101",
                "employee_name": "Rajesh Kumar",
                "designation": "FR_Packer",
                "shift_date": "2026-09-01",
                "shift_name": "Morning",
                "shift_time": "06:00 - 15:00",
                "punch_in": "06:01:00",
                "punch_out": "15:04:00",
                "work_duration_mins": 543,
                "break_duration_mins": 45,
                "raw_status": "P",
                "status": "PRESENT"
            },
            {
                "employee_id": "EMP101",
                "employee_name": "Rajesh Kumar",
                "designation": "FR_Packer",
                "shift_date": "2026-09-02",
                "shift_name": "Morning",
                "shift_time": "06:00 - 15:00",
                "punch_in": "",
                "punch_out": "",
                "work_duration_mins": 0,
                "break_duration_mins": 0,
                "raw_status": "A",
                "status": "ABSENT"
            }
        ],
        "summary": {
            "present_count": 1,
            "absent_count": 1,
            "week_off_count": 0,
            "half_day_count": 0,
            "holiday_count": 0,
            "attendance_rate_pct": 50.0
        }
    }
    
    result = save_attendance_batch(mock_parsed, source="TEST")
    assert result["imported_records"] == 2
    
    summary = get_attendance_summary(store_name="JMU-Sainik Colony")
    assert summary["headcount"] == 1
    assert summary["total_shifts_scheduled"] == 2
    assert summary["status_distribution"]["PRESENT"] == 1
    assert summary["status_distribution"]["ABSENT"] == 1
    
    records = get_attendance_records(employee_id="EMP101")
    assert len(records) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_zepto_attendance_db.py -v`  
Expected: FAIL with missing functions / schema.

- [ ] **Step 3: Update `zepto_db.py` and `turso_sync.py`**

Add table definitions, indexes, and DAL query functions. Add tables to `SYNC_TABLES`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_zepto_attendance_db.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add earnings_engine/data/zepto_db.py earnings_engine/data/turso_sync.py tests/test_zepto_attendance_db.py
git commit -m "feat(zepto): add attendance database schema, turso sync registration, and DAL queries"
```

---

### Task 3: REST API Endpoints for Attendance & Gmail Auto-Ingestion

**Files:**
- Modify: `earnings_engine/api/routers/zepto.py`
- Test: `tests/test_zepto_attendance_api.py`

**Endpoints:**
- `POST /api/v1/zepto/attendance/upload` (Form Upload)
- `GET /api/v1/zepto/attendance/summary` (Analytics & KPIs)
- `GET /api/v1/zepto/attendance/records` (Filterable / Paginated records)
- `GET /api/v1/zepto/attendance/imports` (Import history)
- `DELETE /api/v1/zepto/attendance/imports/{import_id}` (Delete import)
- `POST /api/v1/zepto/gmail/sync-attendance` (Fetch from Gmail OAuth)

- [ ] **Step 1: Write failing API test**

`tests/test_zepto_attendance_api.py`:
```python
import pytest
from fastapi.testclient import TestClient
from earnings_engine.api.server import app
from earnings_engine.data.auth import create_session_token

@pytest.fixture
def auth_client():
    c = TestClient(app)
    token = create_session_token(
        user_id="usr_owner",
        role="owner",
        email="owner@nexus.local",
        name="Nexus Owner",
        scopes=["*"],
    )
    c.cookies.set("nexus_session", token)
    return c

def test_attendance_summary_endpoint(auth_client):
    resp = auth_client.get("/api/v1/zepto/attendance/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert "status_distribution" in data
    assert "role_breakdown" in data

def test_attendance_records_endpoint(auth_client):
    resp = auth_client.get("/api/v1/zepto/attendance/records?limit=10")
    assert resp.status_code == 200
    data = resp.json()
    assert "records" in data
    assert "total" in data
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_zepto_attendance_api.py -v`  
Expected: FAIL with 404 Not Found.

- [ ] **Step 3: Implement endpoints in `earnings_engine/api/routers/zepto.py`**

Implement the endpoints with role validation, query parsing, and Gmail API integration.

- [ ] **Step 4: Run test to verify it passes**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_zepto_attendance_api.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add earnings_engine/api/routers/zepto.py tests/test_zepto_attendance_api.py
git commit -m "feat(zepto): add attendance upload, summary metrics, query, and gmail sync endpoints"
```

---

### Task 4: Frontend Attendance Dashboard UI & Real-Time Analytics

**Files:**
- Create: `earnings_engine/reports/templates/hubs/zepto/_attendance.html`
- Modify: `earnings_engine/reports/templates/hubs/zepto/index.html`
- Modify: `earnings_engine/ui/js/modules/zepto.js`
- Test: `tests/test_zepto_hub.py`

**Features:**
- Dedicated `#tabBtn-attendance` and `#attendanceView` container.
- High-density KPI cards: Present Rate %, Active Staff Headcount, Total Working Hours, Absenteeism Alerts.
- Role composition breakdown bars & Shift distribution.
- Interactive filterable muster records table with search by employee name, role, date, and status badges.
- Drag-and-drop Excel file upload modal and "Sync from Gmail" button with loading spinners and toast notifications.

- [ ] **Step 1: Write failing template/UI test**

Update `tests/test_zepto_hub.py` to assert attendance tab rendering, navigation links, and attendance template partial inclusion.

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_zepto_hub.py -k "attendance" -v`  
Expected: FAIL.

- [ ] **Step 3: Create `_attendance.html`, update `index.html` and `zepto.js`**

Implement complete UI layout, Chart.js/custom CSS metric cards, table rendering, filters, file drag-and-drop, and Gmail sync handler.

- [ ] **Step 4: Run tests to verify pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_zepto_hub.py -v`  
Expected: PASS

- [ ] **Step 5: Commit & Remote Push**

```bash
git add earnings_engine/reports/templates/hubs/zepto/ earnings_engine/ui/js/modules/zepto.js tests/test_zepto_hub.py
git commit -m "feat(zepto): implement attendance dashboard view with analytics cards, muster table, and gmail sync"
git push origin new_report
```

---

### Task 5: End-to-End Verification with User's Real Attendance Report

**Files:**
- Test: `tests/test_zepto_attendance_e2e.py`

- [ ] **Step 1: Write E2E test parsing `C:\Users\91700\Downloads\JMU-Sainik_Colony-Attendance-report-8165178.xlsx`**
- [ ] **Step 2: Run test verifying all 406 records, 27 employees, date range 2026-08-26 to 2026-09-29, and summary metrics**
- [ ] **Step 3: Commit & Push**
