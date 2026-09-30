# Zepto Dark Store Attendance Report Parser & Analytics Hub — Design Spec

**Date:** 2026-09-30  
**Target:** Zepto Dark Store Management Hub (`/zepto#attendance` & `/zepto#gmail`)  
**Status:** Validated Design  

---

## 1. Overview & Business Intent

Zepto Dark Store operations receive automated daily / periodic Excel attendance muster reports via email (e.g. `JMU-Sainik_Colony-Attendance-report-8165178.xlsx`). Dark store managers and central ops need visibility into:
1. **Attendance & Absenteeism Rates**: Daily / monthly present rate (`P`), absenteeism (`A`), week-offs (`WO`), festive offs (`F`), half-days (`HD`), and unapproved leaves.
2. **Staffing & Roster Adherence**: Role-wise breakdown (`FR_Packer`, `FR_Shift Incharge`, `FM_Multi Skilled Technician`, `DH_DHM Hybrid`, `DH_Quality Associate`, etc.) across day and night shifts.
3. **Punctuality & Working Hours**: In-punch, out-punch, effective working duration (hours/minutes), and break analysis.
4. **Seamless Ingestion**:
   - **Manual Upload**: Drag-and-drop Excel file upload in the Hub.
   - **Gmail 1-Click Ingestion**: Automatic extraction of Excel attendance report attachments from linked dark store Gmail accounts via the OAuth 2.0 subsystem.

---

## 2. Architecture & Data Flow

```
+-------------------------------------------------------------------------+
|                              Ingestion                                  |
|   Manual .xlsx Upload (UI)  OR  Gmail OAuth Attachment Auto-Scan        |
+-------------------------------------------------------------------------+
                                    │
                                    ▼
+-------------------------------------------------------------------------+
|                  zepto_attendance_parser.py                             |
|   - Zero-dependency XML/Zip .xlsx parser (fallback to openpyxl)         |
|   - Excel date serial conversion (1899-12-30 epoch -> ISO YYYY-MM-DD)   |
|   - Header normalization & column mapping                              |
|   - Status normalization (P, A, WO, HD, F, A-R, etc.)                   |
+-------------------------------------------------------------------------+
                                    │
                                    ▼
+-------------------------------------------------------------------------+
|                       SQLite / Turso Sync Engine                        |
|   - zepto_attendance_imports (metadata, store, period, counts)         |
|   - zepto_attendance_records (granular punch/status records)           |
|   - Registered in SYNC_TABLES with watermark columns                    |
+-------------------------------------------------------------------------+
                                    │
                                    ▼
+-------------------------------------------------------------------------+
|                         FastAPI REST Routers                            |
|   - POST /api/v1/zepto/attendance/upload                                |
|   - GET  /api/v1/zepto/attendance/summary                               |
|   - GET  /api/v1/zepto/attendance/records                               |
|   - POST /api/v1/zepto/gmail/sync-attendance                            |
+-------------------------------------------------------------------------+
                                    │
                                    ▼
+-------------------------------------------------------------------------+
|                      Zepto Dark Store Hub UI                            |
|   - Attendance KPIs (Present Rate, Total Man-Hours, Active Headcount)   |
|   - Role Distribution & Daily Muster Chart                             |
|   - Filterable Attendance Ledger Table with Status Badges               |
|   - Manual Dropzone & Gmail Sync Action Bar                             |
+-------------------------------------------------------------------------+
```

---

## 3. Database Schema

### 3.1 `zepto_attendance_imports`
Tracks uploaded or fetched batch files:
```sql
CREATE TABLE IF NOT EXISTS zepto_attendance_imports (
    id TEXT PRIMARY KEY,                       -- e.g. imp_8165178_20260930
    file_name TEXT NOT NULL,
    store_name TEXT NOT NULL,
    start_date TEXT NOT NULL,                  -- YYYY-MM-DD
    end_date TEXT NOT NULL,                    -- YYYY-MM-DD
    total_records INTEGER NOT NULL DEFAULT 0,
    total_employees INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL DEFAULT 'UPLOAD',     -- 'UPLOAD' | 'GMAIL'
    imported_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

### 3.2 `zepto_attendance_records`
Stores normalized per-employee per-day attendance entries:
```sql
CREATE TABLE IF NOT EXISTS zepto_attendance_records (
    id TEXT PRIMARY KEY,                       -- MD5(store_name + employee_id + shift_date)
    import_id TEXT NOT NULL,
    store_name TEXT NOT NULL,
    employee_id TEXT NOT NULL,
    employee_name TEXT NOT NULL,
    designation TEXT NOT NULL,
    shift_date TEXT NOT NULL,                  -- YYYY-MM-DD
    shift_name TEXT,                           -- e.g. "Shift 1", "General"
    shift_time TEXT,                           -- e.g. "06:00 - 15:00"
    punch_in TEXT,                             -- e.g. "06:02:14"
    punch_out TEXT,                            -- e.g. "15:05:30"
    work_duration_mins INTEGER DEFAULT 0,      -- normalized minutes worked
    break_duration_mins INTEGER DEFAULT 0,     -- normalized break minutes
    raw_status TEXT NOT NULL,                  -- 'P', 'A', 'WO', 'HD', 'F', 'A-R'
    status TEXT NOT NULL,                      -- 'PRESENT', 'ABSENT', 'WEEK_OFF', 'HALF_DAY', 'HOLIDAY'
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(import_id) REFERENCES zepto_attendance_imports(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_zepto_att_store_date ON zepto_attendance_records(store_name, shift_date);
CREATE INDEX IF NOT EXISTS idx_zepto_att_emp ON zepto_attendance_records(employee_id, shift_date);
CREATE INDEX IF NOT EXISTS idx_zepto_att_status ON zepto_attendance_records(status);
```

### 3.3 Turso Cloud Sync Registration
`SYNC_TABLES` updated to include:
- `zepto_attendance_imports`
- `zepto_attendance_records`

Watermark tracking uses `updated_at` / `created_at` / `shift_date`.

---

## 4. Parser Specification (`zepto_attendance_parser.py`)

### 4.1 Excel Layout & Column Recognition
Based on actual Zepto Dark Store Excel muster format (`JMU-Sainik_Colony-Attendance-report-8165178.xlsx`):
- **Store Identification**: Extracted from header lines or filename pattern (`JMU-Sainik_Colony` -> `JMU-Sainik Colony`).
- **Standard Columns**:
  - `Emp ID` / `Employee Code` -> `employee_id`
  - `Emp Name` / `Employee Name` -> `employee_name`
  - `Designation` / `Role` -> `designation` (e.g., `FR_Packer`, `DH_DHM Hybrid`)
  - `Date` / `Attendance Date` -> `shift_date` (Parsed from serial floating dates like `46291` -> `2026-09-29`)
  - `Shift` / `Shift Name` -> `shift_name`
  - `Shift Timings` -> `shift_time`
  - `In Time` / `First In` -> `punch_in`
  - `Out Time` / `Last Out` -> `punch_out`
  - `Work Duration` / `Actual Hours` -> `work_duration_mins`
  - `Total Break` -> `break_duration_mins`
  - `Status` / `Muster Status` -> `raw_status`

### 4.2 Status Categorization Matrix
| Raw Code | Normalized Status | Description |
| :--- | :--- | :--- |
| `P` | `PRESENT` | Full day shift completed |
| `A`, `A-R` | `ABSENT` | Absent without / with leave request |
| `WO` | `WEEK_OFF` | Scheduled weekly rest day |
| `HD` | `HALF_DAY` | Partial shift (< 4.5 hours) |
| `F` | `HOLIDAY` | Festive / National dark store holiday |

### 4.3 Zero-Dependency Zip/XML Parser Architecture
To ensure seamless execution in restricted environments without C-extensions or mandatory third-party pip packages:
- Inspects `.xlsx` as a `zipfile.ZipFile`.
- Reads `xl/sharedStrings.xml` for text lookups.
- Reads `xl/worksheets/sheet1.xml` for cell coordinates (`c r="A1" t="s"`).
- Automatically converts Excel date serial numbers (`(serial - 25569) * 86400`) to UTC datetime.
- If `openpyxl` is present in the environment, uses it for even higher performance while keeping the pure stdlib fallback.

---

## 5. REST API Contracts

### 5.1 `POST /api/v1/zepto/attendance/upload`
- **Request**: Multipart Form Data (`file: UploadFile`)
- **Response**:
```json
{
  "status": "success",
  "import_id": "imp_8165178_20260930_120000",
  "store_name": "JMU-Sainik Colony",
  "date_range": {
    "start": "2026-08-26",
    "end": "2026-09-29"
  },
  "total_records": 406,
  "total_employees": 27,
  "metrics": {
    "present_count": 305,
    "absent_count": 48,
    "week_off_count": 41,
    "attendance_rate_pct": 86.4
  }
}
```

### 5.2 `GET /api/v1/zepto/attendance/summary`
- **Query Params**: `store_name?: str`, `start_date?: str`, `end_date?: str`
- **Response**:
```json
{
  "store_name": "JMU-Sainik Colony",
  "period": { "start": "2026-08-26", "end": "2026-09-29" },
  "headcount": 27,
  "total_shifts_scheduled": 406,
  "attendance_rate_pct": 86.4,
  "total_hours_worked": 2745.5,
  "avg_daily_present": 8.7,
  "status_distribution": {
    "PRESENT": 305,
    "ABSENT": 48,
    "WEEK_OFF": 41,
    "HALF_DAY": 2,
    "HOLIDAY": 10
  },
  "role_breakdown": [
    { "role": "FR_Packer", "headcount": 14, "present_rate_pct": 88.2 },
    { "role": "DH_DHM Hybrid", "headcount": 4, "present_rate_pct": 82.5 }
  ],
  "daily_trend": [
    { "date": "2026-09-29", "present": 10, "absent": 1, "week_off": 1, "total": 12 }
  ]
}
```

### 5.3 `GET /api/v1/zepto/attendance/records`
- **Query Params**: `store_name?: str`, `employee_id?: str`, `designation?: str`, `status?: str`, `date?: str`, `limit=50`, `offset=0`
- **Response**: Paginated list of detailed punch records with computed durations.

### 5.4 `POST /api/v1/zepto/gmail/sync-attendance`
- Scans user's linked Gmail inbox for messages with subject matching `Attendance` or attachments with `.xlsx` from Zepto domain.
- Downloads attachments, parses them, updates SQLite, and returns import summary.

---

## 6. Frontend UI Components (`/zepto#attendance`)

1. **Header Control Bar**:
   - Quick Date Filter (Last 7 Days, Last 30 Days, Custom Range).
   - "Sync from Gmail" button with sync state animation.
   - "Upload Attendance Report (.xlsx)" file picker dropzone.
2. **Top Metric Cards**:
   - Overall Present Rate (%) with trend indicator.
   - Total Active Headcount & Scheduled Shifts.
   - Total Work Hours & Avg Shift Length.
   - Unplanned Absenteeism Count & Alert badge.
3. **Role & Shift Composition**:
   - Distribution chart / progress bars for roles (`FR_Packer`, `DH_DHM Hybrid`, etc.).
   - Shift Distribution (Day vs Night vs General).
4. **Interactive Attendance Muster Table**:
   - Filter by Employee Name, Role, Date, Status badge (`PRESENT` emerald, `ABSENT` rose, `WEEK_OFF` slate, `HALF_DAY` amber).
   - Detailed punch in/out timestamps and total hours worked.
   - Export filtered muster view to CSV.

---

## 7. Testing & Verification Strategy

1. **Unit Tests (`tests/test_zepto_attendance_parser.py`)**:
   - Verify parsing of actual Excel bytes and files without errors.
   - Verify date serial conversion to ISO strings (`46291` -> `2026-09-29`).
   - Verify status mapping matrix (`P` -> `PRESENT`, `A-R` -> `ABSENT`, etc.).
   - Verify duration calculation from punch strings.
2. **Database & Sync Tests (`tests/test_zepto_attendance_db.py`)**:
   - Test CRUD for `zepto_attendance_imports` and `zepto_attendance_records`.
   - Test `SYNC_TABLES` contains new attendance tables.
   - Test aggregation queries (`get_attendance_summary`, role breakdown, daily trends).
3. **API Integration Tests (`tests/test_zepto_attendance_api.py`)**:
   - Test file upload endpoint with mock `.xlsx`.
   - Test summary and records endpoints with filtering and pagination.
4. **UI Integration (`tests/test_zepto_hub.py`)**:
   - Verify attendance tab and UI elements render cleanly.
