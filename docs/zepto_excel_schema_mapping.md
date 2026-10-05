# Zepto Dark Store Excel Schema Mapping & Operational Data Contracts

> **Authoritative Specification** for Zepto dark store operational spreadsheet ingestion, multi-sheet workbook extraction, date/time serial conversions, database schema mapping, and cross-domain attendance-manpower synchronization.

---

## 1. Overview & Architecture

The Zepto Dark Store analytics subsystem automatically extracts, parses, validates, and persists operational intelligence from dark store Excel reports downloaded from Zepto internal portals (Thor, Packman, Darwinbox) or received via automated Gmail operational feeds.

```
┌────────────────────────────────────────────────────────────────────────┐
│                        Zepto Operational Ingestion                     │
├────────────────────────────┬───────────────────────────────────────────┤
│ 1. Attendance Muster       │ Darwinbox / Shift Incharge (.xlsx)        │
│ 2. DQ Loss & Spoilage      │ Daily Expiry & Damage Audit (.xlsx)       │
│ 3. Shrinkage Ledger        │ Inhouse DOD & MTD Cycle Counts (.xlsx)    │
│ 4. Store Metric & Manpower │ Thor Scanner & Packman Daily Roster (.xlsx)│
└─────────────┬──────────────┴─────────────────────────────┬─────────────┘
              │                                            │
              ▼                                            ▼
   Zero-Dependency Parser                    Cross-Table Synchronization
  (_extract_xlsx_sheets_native)             (Manpower Punches -> Attendance)
              │                                            │
              ├──────────────────────┬─────────────────────┤
              ▼                      ▼                     ▼
   zepto_attendance_records   zepto_loss_records   zepto_manpower_utilization
   zepto_attendance_imports                        zepto_store_metrics
              │
              ▼
   Prorated Payroll Forensics Engine & Dashboard Analytics
```

---

## 2. Report Specifications & Column Mappings

### 2.1 Attendance Muster Report (`Attendance`)

Captures daily employee shift rosters, punch status, and employment metadata.

- **Primary Sheet Name**: `Attendance` (or single-sheet muster)
- **Target SQLite Tables**: `zepto_attendance_imports`, `zepto_attendance_records`

#### Column Mapping Matrix

| Source Header Aliases | Canonical Field | Data Type | Description / Conversion Rule |
| :--- | :--- | :--- | :--- |
| `store_name`, `store`, `darkstore` | `store_name` | `TEXT` | Canonicalized via `normalize_store_name()` (e.g., `"JMU-Sainik Colony"`). |
| `scheduled_date`, `shift_date`, `date` | `shift_date` | `TEXT` | Converted from Excel serial (`46276`) or date string to `YYYY-MM-DD` (`2026-09-11`). |
| `full_name`, `emp_name`, `employee_name` | `employee_name` | `TEXT` | Worker full name (whitespace trimmed). |
| `employee_code`, `employee_id`, `emp_id` | `employee_id` | `TEXT` | Unique employee code / ID string. |
| `DOJ`, `joining_date` | `joining_date` | `TEXT` | Date of joining (`YYYY-MM-DD`). |
| `current_role_name`, `role`, `designation` | `designation` | `TEXT` | Role title (`"PACKER"`, `"PICKER"`, `"SHIFT_INCHARGE"`, `"SECURITY_GUARD"`). |
| `user_status`, `status` | `user_status` | `TEXT` | Employment status (`"ACTIVE"`, `"INACTIVE"`, `"RESIGNED"`). |
| `muster_status`, `attendance_status` | `status` | `TEXT` | Normalized: `P` -> `PRESENT`, `A` -> `ABSENT`, `WO` -> `WEEK_OFF`, `HD` -> `HALF_DAY`, `HL` -> `HOLIDAY`, `L` -> `LEAVE`. |
| `in_time`, `punch_in`, `actual_in_time` | `punch_in` | `TEXT` | Punch-in time (`HH:MM:SS`). |
| `out_time`, `punch_out`, `actual_out_time` | `punch_out` | `TEXT` | Punch-out time (`HH:MM:SS`). |
| `work_duration`, `work_hours` | `work_duration_mins` | `INTEGER` | Minutes worked (converted from float hours or string duration). |

---

### 2.2 DQ Loss & Spoilage Report (`DQ_Details`)

Captures damaged, expired, or spoiled SKUs removed from active inventory.

- **Primary Sheet Name**: `DQ_Details` (or single-sheet DQ report)
- **Target SQLite Table**: `zepto_loss_records` (where `loss_type = 'DQ_LOSS'`)

#### Column Mapping Matrix

| Source Header Aliases | Canonical Field | Data Type | Description / Conversion Rule |
| :--- | :--- | :--- | :--- |
| `crtdate`, `date`, `record_date` | `record_date` | `TEXT` | Excel serial or ISO date string -> `YYYY-MM-DD`. |
| `store_name`, `store` | `store_name` | `TEXT` | Normalized dark store name. |
| `sku_id`, `item_id`, `code` | `sku_id` | `TEXT` | Unique SKU identifier. |
| `sku_name`, `item_name`, `product_name` | `item_name` | `TEXT` | Full SKU / product title. |
| `category` | `category` | `TEXT` | Top-level item category (`DAIRY`, `FRUITS & VEGETABLES`, `STAPLES`, etc.). |
| `SubCategory`, `sub_category` | `sub_category` | `TEXT` | Specific product sub-category. |
| `dq_value`, `loss_amount`, `amount` | `amount` | `REAL` | Currency value of spoiled/damaged items (positive float). |
| `dq`, `quantity`, `units` | `sku_count` | `INTEGER` | Quantity of damaged units. |

---

### 2.3 Shrinkage & Inventory Variance Report (`Inhouse_DOD` & `MTD_Summary`)

Multi-sheet ledger tracking daily inhouse damage, short picks, cycle count adjustments, and monthly cumulative shrinkage.

- **Primary Sheet Names**: `Inhouse_DOD` (21 columns), `MTD_Summary` (32 columns)
- **Target SQLite Table**: `zepto_loss_records` (where `loss_type = 'SHRINKAGE'`)

#### Column Mapping Matrix (`Inhouse_DOD`)

| Source Header Aliases | Canonical Field | Data Type | Description / Conversion Rule |
| :--- | :--- | :--- | :--- |
| `date`, `report_date` | `record_date` | `TEXT` | Excel serial -> `YYYY-MM-DD`. |
| `store_name`, `store`, `city` | `store_name` | `TEXT` | Normalized dark store name. |
| `sku_id` | `sku_id` | `TEXT` | Unique SKU identifier. |
| `sku_name`, `item_name` | `item_name` | `TEXT` | SKU title. |
| `category`, `sub_category` | `category` | `TEXT` | Categorization string. |
| `inhouse_net_amount`, `adjustment_amount`, `short_pick_amount` | `amount` | `REAL` | Net loss/surplus amount. Supports accounting parentheses `(100.0)` or negative values `-200.0` for surplus stock found. |
| `inhouse_net`, `rto`, `fcc`, `short_pick` | `sku_count` | `INTEGER` | Net unit variance. |

---

### 2.4 Store Metric Summary & Manpower Utilization (`Packer_Thor_Raw`, `Flex_Worker_Thor_Raw`, `Packman_PunchOut_Missed_Raw`)

44-column granular worker scorecard and scanner throughput data from Thor & Packman systems.

- **Primary Sheet Names**: `Packer_Thor_Raw`, `Flex_Worker_Thor_Raw`, `Packman_PunchOut_Missed_Raw`
- **Target SQLite Tables**:
  - `zepto_manpower_utilization` (individual worker records)
  - `zepto_store_metrics` (store-level daily rollups)
  - `zepto_attendance_records` (cross-table punch & hours enrichment)

#### Column Mapping Matrix (`Packer_Thor_Raw` & `Flex_Worker_Thor_Raw`)

| Source Header Aliases | Canonical Field | Data Type | Description / Conversion Rule |
| :--- | :--- | :--- | :--- |
| `Scheduled_date`, `scheduled_date` | `util_date` | `TEXT` | Excel serial -> `YYYY-MM-DD`. |
| `Packer_id`, `Employee_id`, `Employee_code` | `employee_id` | `TEXT` | Priority: `Employee_code` > `Employee_id` > `Packer_id`. |
| `Emp_Name`, `worker_name`, `full_name` | `employee_name` | `TEXT` | Worker name. |
| `Emplyoee_role`, `role`, `designation` | `role` | `TEXT` | Default: `"Packer"` (or `"Flex Packer"`). |
| `Packman_punch_in_time`, `Thor_punch_in_time`, `actual_in_time` | `punch_in` | `TEXT` | Converted from day fraction serial (`0.25`) or string (`"06:00:00"`) to `HH:MM:SS`. |
| `Packman_punch_out_time`, `actual_out_time` | `punch_out` | `TEXT` | Converted from day fraction serial (`0.604`) or string (`"14:30:00"`) to `HH:MM:SS`. |
| `Thor_work_hour`, `Packman_work_hour` | `thor_work_hours` | `REAL` | Total recorded Thor work duration (hours). |
| `IB_work_hour`, `inbound_hours` | `ib_work_hours` | `REAL` | Inbound staging work duration (hours). |
| `OB_hour`, `outbound_hours` | `ob_work_hours` | `REAL` | Outbound packing/dispatch duration (hours). |
| `Break_hour` | `break_hours` | `REAL` | Break duration (hours). |
| `Idle_hour` | `idle_hours` | `REAL` | Unassigned / idle duration (hours). |
| `Day_ob_order_handled` | `day_orders_handled` | `INTEGER` | Total orders picked/packed. |
| `Day_ob_order_packed_qty` | `items_picked` | `INTEGER` | Total unit quantity picked/packed. |
| `Day_ob_ipp` | `ipp` | `REAL` | Items Picked Per Hour throughput. |
| `Day_task_adherence` | `adherence_pct` | `REAL` | Task completion rate percentage (e.g. `95.2%` -> `95.2`). |
| `flex_labor_cost` | `flex_labor_cost` | `REAL` | Third-party / flex worker payout cost. |

---

## 3. Date & Time Conversion Engine

### 3.1 Excel Date Serial to ISO `YYYY-MM-DD`
Excel dates represent the number of elapsed days since `1899-12-30`:
$$\text{ISO Date} = \text{datetime}(1899, 12, 30) + \text{timedelta}(\text{days} = \text{serial})$$
- Serial `46276` $\rightarrow$ `2026-09-11`
- Serial `46282` $\rightarrow$ `2026-09-17`

### 3.2 Excel Fractional Day to Time `HH:MM:SS`
Excel timestamps represent decimal fractions of a 24-hour day ($86,400\text{ seconds}$):
$$\text{Total Seconds} = \text{round}((\text{val} - \lfloor \text{val} \rfloor) \times 86400)$$
- `0.250000` $\rightarrow$ $0.25 \times 86400 = 21600\text{s} \rightarrow$ `06:00:00`
- `0.604167` $\rightarrow$ $0.604167 \times 86400 = 52200\text{s} \rightarrow$ `14:30:00`
- String formats (`"06:00:00"`, `"6:00 AM"`, `"2:30 PM"`) are parsed via regular expressions with 24-hour modulus adjustment.

---

## 4. Cross-Table Synchronization Contract

When `save_manpower_utilization_batch()` persists scanner and worker records into `zepto_manpower_utilization`, it automatically enriches existing attendance records in `zepto_attendance_records`:

```sql
UPDATE zepto_attendance_records
SET punch_in = CASE WHEN :punch_in != '' THEN :punch_in ELSE punch_in END,
    punch_out = CASE WHEN :punch_out != '' THEN :punch_out ELSE punch_out END,
    work_duration_mins = CASE WHEN :duration_mins > 0 THEN :duration_mins ELSE work_duration_mins END,
    updated_at = :now_iso
WHERE shift_date = :date_str
  AND (
      LOWER(TRIM(store_name)) = LOWER(TRIM(:store_name))
      OR (:store_name = 'JMU-Sainik Colony' AND store_name LIKE '%Sainik%')
  )
  AND (
      (:emp_id != '' AND LOWER(TRIM(employee_id)) = LOWER(TRIM(:emp_id)))
      OR
      (:emp_name != '' AND LOWER(TRIM(employee_name)) = LOWER(TRIM(:emp_name)))
  );
```

---

## 5. Prorated Monthly Salary & Payroll Forensics

Payroll metrics are computed point-in-time for any selected calendar month $M$ (e.g. `2026-09` with $N = 30$ days):

### 5.1 Base Salary Hierarchy & Fallbacks
1. If `zepto_employees.base_salary_monthly > 0`, use configured master salary.
2. If salary is 0 or employee is unassigned/unregistered:
   - **Shift Incharge / Manager / Lead / Supervisor / Head / SI**: ₹20,000.00 / month
   - **Security Guard**: ₹16,000.00 / month
   - **Picker / Packer / Housekeeping / Other**: ₹14,000.00 / month

### 5.2 Mathematical Formulation
- **Daily Rate**:
  $$\text{Daily Rate} = \frac{\text{Base Salary}}{N}$$
- **Payable Days**:
  $$\text{Payable Days} = \text{Present} + \text{Week Off} + \text{Holiday} + 0.5 \times \text{Half Day}$$
- **Expected Monthly Payout**:
  $$\text{Expected Payout} = \text{Payable Days} \times \text{Daily Rate}$$
- **Absenteeism Deduction**:
  $$\text{Deduction} = \text{Absent Days} \times \text{Daily Rate}$$

---

## 6. Turso Cloud Replication & Invariants

All Zepto operational tables are registered in `SYNC_TABLES` in `earnings_engine/data/turso_sync.py`:
- `zepto_employees`
- `zepto_salaries`
- `zepto_monthly_ratings`
- `zepto_expenses`
- `zepto_store_income`
- `zepto_income_split_settings`
- `zepto_candidates`
- `zepto_security_capital`
- `zepto_staffing_targets`
- `zepto_gmail_auth`
- `zepto_attendance_imports`
- `zepto_attendance_records`
- `zepto_store_metrics`
- `zepto_loss_records`
- `zepto_manpower_utilization`
- `zepto_gmail_messages`
- `zepto_offer_letters`

All local reads and writes execute with zero external network dependencies on SQLite with WAL mode (`journal_mode=WAL`, `busy_timeout=5000`).
