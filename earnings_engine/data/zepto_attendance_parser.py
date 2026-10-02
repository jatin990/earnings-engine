"""
Zepto Dark Store Attendance Report Excel Parser.
Robust zero-dependency XML/Zip parser with openpyxl fallback support.
Converts Zepto attendance muster workbooks into structured employee records and KPI metrics.
"""

from __future__ import annotations

import io
import os
import re
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, date, timedelta
from typing import Any, Dict, List, Optional, Union

# Mapping of raw Zepto muster statuses to normalized status tags
STATUS_MAP = {
    "P": "PRESENT",
    "PRESENT": "PRESENT",
    "A": "ABSENT",
    "A-R": "ABSENT",
    "ABSENT": "ABSENT",
    "MIS": "ABSENT",
    "AB": "ABSENT",
    "WO": "WEEK_OFF",
    "WEEK OFF": "WEEK_OFF",
    "WEEKOFF": "WEEK_OFF",
    "OFF": "WEEK_OFF",
    "HD": "HALF_DAY",
    "HALF DAY": "HALF_DAY",
    "HALFDAY": "HALF_DAY",
    "F": "HOLIDAY",
    "FH": "HOLIDAY",
    "HOLIDAY": "HOLIDAY",
    "FESTIVE": "HOLIDAY",
    "PH": "HOLIDAY",
    "PL": "LEAVE",
    "CL": "LEAVE",
    "SL": "LEAVE",
    "EL": "LEAVE",
}

def normalize_muster_status(raw: Any) -> str:
    """Normalize raw muster code into clean enum string."""
    if not raw:
        return "UNKNOWN"
    s = str(raw).strip().upper()
    return STATUS_MAP.get(s, "PRESENT" if "P" in s else s)


def excel_date_to_iso(val: Any) -> str:
    """
    Convert Excel serial date or date strings to ISO YYYY-MM-DD.
    Excel serial epoch starts at 1899-12-30.
    """
    if val is None or val == "":
        return ""
    if isinstance(val, (datetime, date)):
        return val.strftime("%Y-%m-%d")

    # Try parsing numeric serial
    try:
        fval = float(val)
        # Excel base date
        base = datetime(1899, 12, 30)
        dt = base + timedelta(days=fval)
        return dt.strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        pass

    sval = str(val).strip()
    # Check YYYY-MM-DD
    if re.match(r"^\d{4}-\d{2}-\d{2}", sval):
        return sval[:10]

    # Check DD-MM-YYYY or DD/MM/YYYY
    m = re.match(r"^(\d{1,2})[-/](\d{1,2})[-/](\d{4})", sval)
    if m:
        d, m_month, y = m.groups()
        return f"{int(y):04d}-{int(m_month):02d}-{int(d):02d}"

    # Check DD-Mon-YYYY or DD-Mon-YY or DD-Mon (e.g. 26-Aug-2026, 26-Aug-26, 26-Aug)
    for fmt in ("%d-%b-%Y", "%d-%b-%y", "%d-%B-%Y", "%d/%b/%Y", "%d/%b/%y", "%d-%m-%y", "%d/%m/%y", "%Y/%m/%d", "%Y.%m.%d", "%b %d, %Y"):
        try:
            dt = datetime.strptime(sval, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            pass

    # Check DD-Mon without year (defaults to current year)
    try:
        dt = datetime.strptime(sval, "%d-%b")
        return dt.replace(year=datetime.now().year).strftime("%Y-%m-%d")
    except ValueError:
        pass

    return sval


def parse_time_str(val: Any) -> str:
    """Format time string or decimal time into HH:MM:SS."""
    if val is None or val == "":
        return ""
    if isinstance(val, (datetime, time)):
        return val.strftime("%H:%M:%S")

    try:
        fval = float(val)
        if 0 <= fval < 1:  # Fraction of day
            total_seconds = int(round(fval * 86400))
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            seconds = total_seconds % 60
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    except (ValueError, TypeError):
        pass

    s = str(val).strip()
    return s


def parse_duration_to_mins(val: Any) -> int:
    """Convert duration string (e.g. '08:45', '8.5 hrs', '525 mins') to integer minutes."""
    if not val:
        return 0

    try:
        fval = float(val)
        if 0 <= fval < 1:  # Fractional day
            return int(round(fval * 1440))
        if fval >= 1 and fval <= 24:  # Likely hours
            return int(round(fval * 60))
        return int(round(fval))
    except (ValueError, TypeError):
        pass

    s = str(val).strip()
    # Check HH:MM:SS or HH:MM
    m = re.match(r"^(\d+):(\d+)(?::(\d+))?", s)
    if m:
        hrs = int(m.group(1))
        mins = int(m.group(2))
        return hrs * 60 + mins

    # Check "Xh Ym"
    hrs_m = re.search(r"(\d+)\s*(?:h|hr|hours)", s, re.I)
    mins_m = re.search(r"(\d+)\s*(?:m|min|mins|minutes)", s, re.I)
    total = 0
    if hrs_m:
        total += int(hrs_m.group(1)) * 60
    if mins_m:
        total += int(mins_m.group(1))
    if total > 0:
        return total

    return 0


def _extract_xlsx_sheets_native(file_source: Union[str, bytes, io.BytesIO]) -> Dict[str, List[List[str]]]:
    """
    Zero-dependency extraction of all sheets and cell matrices from .xlsx using zipfile & ElementTree.
    Returns dict mapping sheet_name -> list of rows (where each row is a list of cell strings).
    """
    if isinstance(file_source, str):
        z = zipfile.ZipFile(file_source, "r")
    elif isinstance(file_source, bytes):
        z = zipfile.ZipFile(io.BytesIO(file_source), "r")
    else:
        z = zipfile.ZipFile(file_source, "r")

    # Read shared strings table
    shared_strings = []
    if "xl/sharedStrings.xml" in z.namelist():
        tree = ET.fromstring(z.read("xl/sharedStrings.xml"))
        # XML namespace agnostic search
        for si in tree.findall(".//{*}si"):
            text_nodes = si.findall(".//{*}t")
            text = "".join(t.text or "" for t in text_nodes)
            shared_strings.append(text)

    # Read workbook sheet list and relationships
    sheet_map: List[tuple[str, str]] = []  # (sheet_name, target_file)
    rels: Dict[str, str] = {}
    if "xl/_rels/workbook.xml.rels" in z.namelist():
        try:
            rel_tree = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
            for rel in rel_tree.findall(".//{*}Relationship"):
                r_id = rel.attrib.get("Id", "")
                target = rel.attrib.get("Target", "")
                if target:
                    if not target.startswith("xl/"):
                        target = f"xl/{target}" if not target.startswith("/") else target.lstrip("/")
                    rels[r_id] = target
        except Exception:
            pass

    if "xl/workbook.xml" in z.namelist():
        try:
            wb_tree = ET.fromstring(z.read("xl/workbook.xml"))
            for sheet_node in wb_tree.findall(".//{*}sheet"):
                s_name = sheet_node.attrib.get("name", "")
                r_id = ""
                for k, v in sheet_node.attrib.items():
                    if k.endswith("id") and k != "sheetId":
                        r_id = v
                        break
                target_file = rels.get(r_id, "")
                if s_name:
                    sheet_map.append((s_name, target_file))
        except Exception:
            pass

    # If sheet_map is empty or missing targets, fallback to worksheet file listing
    sheet_files = [f for f in z.namelist() if f.startswith("xl/worksheets/sheet") and f.endswith(".xml")]
    if not sheet_map:
        for idx, f in enumerate(sheet_files):
            sheet_map.append((f"Sheet{idx + 1}", f))

    def col_to_index(col_str: str) -> int:
        idx = 0
        for ch in col_str:
            idx = idx * 26 + (ord(ch.upper()) - ord('A') + 1)
        return idx - 1

    result_sheets: Dict[str, List[List[str]]] = {}

    for idx, (s_name, target_file) in enumerate(sheet_map):
        actual_target = target_file
        if not actual_target or actual_target not in z.namelist():
            if idx < len(sheet_files):
                actual_target = sheet_files[idx]
            elif sheet_files:
                actual_target = sheet_files[0]
            else:
                continue

        try:
            sheet_xml = z.read(actual_target)
            sheet_tree = ET.fromstring(sheet_xml)
        except Exception:
            continue

        matrix: List[List[str]] = []
        for row_node in sheet_tree.findall(".//{*}row"):
            row_cells: Dict[int, str] = {}
            for c in row_node.findall(".//{*}c"):
                r_attr = c.attrib.get("r", "")
                t_attr = c.attrib.get("t", "")

                col_letters = "".join([ch for ch in r_attr if ch.isalpha()])
                col_idx = col_to_index(col_letters) if col_letters else len(row_cells)

                v_node = c.find(".//{*}v")
                val = ""
                if v_node is not None and v_node.text is not None:
                    raw_v = v_node.text
                    if t_attr == "s":
                        try:
                            idx_s = int(raw_v)
                            val = shared_strings[idx_s] if idx_s < len(shared_strings) else raw_v
                        except (ValueError, IndexError):
                            val = raw_v
                    else:
                        val = raw_v
                elif t_attr == "inlineStr":
                    t_node = c.find(".//{*}t")
                    if t_node is not None and t_node.text:
                        val = t_node.text

                row_cells[col_idx] = val

            if row_cells:
                max_col = max(row_cells.keys())
                row_list = [row_cells.get(i, "") for i in range(max_col + 1)]
                matrix.append(row_list)

        result_sheets[s_name] = matrix

    return result_sheets


def _extract_xlsx_native(
    file_source: Union[str, bytes, io.BytesIO],
    sheet_name: Optional[str] = None,
) -> List[List[str]]:
    """
    Zero-dependency extraction of cell matrix from .xlsx using zipfile & ElementTree.
    Returns list of rows for the specified sheet or first sheet.
    """
    sheets = _extract_xlsx_sheets_native(file_source)
    if not sheets:
        return []
    if sheet_name and sheet_name in sheets:
        return sheets[sheet_name]
    return next(iter(sheets.values()))


def parse_zepto_attendance_excel(
    file_source: Union[str, bytes, io.BytesIO],
    file_name: str = ""
) -> Dict[str, Any]:
    """
    Parse Zepto Dark Store attendance excel workbook.
    Extracts store metadata, employee muster records, punch times, and summary aggregates.
    """
    if isinstance(file_source, str) and not file_name:
        file_name = os.path.basename(file_source)

    matrix = _extract_xlsx_native(file_source)
    if not matrix:
        raise ValueError("Excel file contains no readable tabular rows.")

    # Infer Store Name from filename if available
    inferred_store = "Zepto Dark Store"
    if file_name:
        clean_name = os.path.splitext(file_name)[0]
        # Match pattern like JMU-Sainik_Colony-Attendance-report-...
        m = re.search(r"([A-Z]{3,}-[A-Za-z0-9_]+)", clean_name)
        if m:
            inferred_store = m.group(1).replace("_", " ")

    # Find Header Row
    header_idx = -1
    col_map = {}

    # Expected column aliases in priority order (exact matches first)
    alias_map = {
        "store_name": ["store_name", "store name", "store", "darkstore", "dark store"],
        "emp_id": ["employee_code", "employee_id", "emp id", "employee id", "employee code", "emp code", "staff id", "code"],
        "emp_name": ["full_name", "fullname", "emp name", "employee name", "staff name", "name"],
        "designation": ["current_role_name", "role_name", "designation", "role", "dept", "department", "position"],
        "shift_date": ["scheduled_date", "attendance date", "shift date", "muster date", "date", "day"],
        "shift_name": ["shift name", "shift type", "shift"],
        "shift_time": ["shift timing", "shift timings", "timing", "shift time", "timings"],
        "punch_in": ["actual_in_time", "in time", "punch in", "first in", "intime", "in_time"],
        "punch_out": ["actual_out_time", "out time", "punch out", "last out", "outtime", "out_time"],
        "work_duration": ["work duration", "actual hours", "worked hours", "work hours", "duration", "total hours"],
        "break_duration": ["break duration", "break time", "total break", "break"],
        "doj": ["doj", "date of joining", "joining date", "joining_date"],
        "user_status": ["user_status", "user status", "employment status", "emp status"],
        "status": ["muster_status", "attendance status", "final status", "muster status", "status", "att status", "state"],
    }

    for idx, row in enumerate(matrix[:25]): # Search first 25 rows for headers
        row_lower = [str(c).strip().lower() for c in row]
        matched_keys = {}
        for canonical, aliases in alias_map.items():
            # Pass 1: exact string match
            found_col = None
            for c_idx, cell_str in enumerate(row_lower):
                if cell_str in aliases:
                    found_col = c_idx
                    break
            # Pass 2: substring match if not found in exact
            if found_col is None:
                for c_idx, cell_str in enumerate(row_lower):
                    if any(alias in cell_str for alias in aliases):
                        # Avoid 'status' matching 'user_status' if 'muster_status' exists
                        if canonical == "status" and "user_status" in cell_str:
                            continue
                        if canonical == "emp_name" and "store_name" in cell_str:
                            continue
                        found_col = c_idx
                        break
            if found_col is not None:
                matched_keys[canonical] = found_col

        # We need at least employee identifier, date, and status to consider this the valid header row
        if ("emp_id" in matched_keys or "emp_name" in matched_keys) and ("shift_date" in matched_keys or "status" in matched_keys):
            header_idx = idx
            col_map = matched_keys
            break

    if header_idx == -1:
        # Fallback: assume row 0 is header with index positions
        header_idx = 0
        col_map = {
            "emp_id": 0,
            "emp_name": 1,
            "designation": 2,
            "shift_date": 3,
            "shift_name": 4,
            "shift_time": 5,
            "punch_in": 6,
            "punch_out": 7,
            "work_duration": 8,
            "break_duration": 9,
            "status": 10 if len(matrix[0]) > 10 else len(matrix[0]) - 1,
        }

    records: List[Dict[str, Any]] = []
    dates_seen = set()
    employees_seen = set()

    status_counts = {
        "PRESENT": 0,
        "ABSENT": 0,
        "WEEK_OFF": 0,
        "HALF_DAY": 0,
        "HOLIDAY": 0,
        "LEAVE": 0,
        "UNKNOWN": 0,
    }

    detected_store_name = ""

    for row in matrix[header_idx + 1:]:
        if not row or not any(row):
            continue

        row_store = str(row[col_map["store_name"]]).strip() if "store_name" in col_map and col_map["store_name"] < len(row) else ""
        if row_store and not detected_store_name:
            detected_store_name = row_store

        emp_id = str(row[col_map["emp_id"]]).strip() if "emp_id" in col_map and col_map["emp_id"] < len(row) else ""
        emp_name = str(row[col_map["emp_name"]]).strip() if "emp_name" in col_map and col_map["emp_name"] < len(row) else ""

        # Skip summary or total rows
        if not emp_id and not emp_name:
            continue
        if "total" in emp_id.lower() or "total" in emp_name.lower():
            continue

        raw_date = row[col_map["shift_date"]] if "shift_date" in col_map and col_map["shift_date"] < len(row) else ""
        shift_date = excel_date_to_iso(raw_date)

        raw_status = str(row[col_map["status"]]).strip() if "status" in col_map and col_map["status"] < len(row) else "P"
        norm_status = normalize_muster_status(raw_status)

        designation = str(row[col_map["designation"]]).strip() if "designation" in col_map and col_map["designation"] < len(row) else ""
        shift_name = str(row[col_map["shift_name"]]).strip() if "shift_name" in col_map and col_map["shift_name"] < len(row) else ""
        shift_time = str(row[col_map["shift_time"]]).strip() if "shift_time" in col_map and col_map["shift_time"] < len(row) else ""

        punch_in = parse_time_str(row[col_map["punch_in"]]) if "punch_in" in col_map and col_map["punch_in"] < len(row) else ""
        punch_out = parse_time_str(row[col_map["punch_out"]]) if "punch_out" in col_map and col_map["punch_out"] < len(row) else ""

        work_dur = parse_duration_to_mins(row[col_map["work_duration"]]) if "work_duration" in col_map and col_map["work_duration"] < len(row) else 0
        break_dur = parse_duration_to_mins(row[col_map["break_duration"]]) if "break_duration" in col_map and col_map["break_duration"] < len(row) else 0

        # Track aggregates
        if shift_date:
            dates_seen.add(shift_date)
        if emp_id or emp_name:
            employees_seen.add(emp_id or emp_name)

        status_counts[norm_status] = status_counts.get(norm_status, 0) + 1

        raw_doj = row[col_map["doj"]] if "doj" in col_map and col_map["doj"] < len(row) else ""
        doj = excel_date_to_iso(raw_doj)
        user_status = str(row[col_map["user_status"]]).strip().upper() if "user_status" in col_map and col_map["user_status"] < len(row) else "ACTIVE"

        rec = {
            "employee_id": emp_id or emp_name,
            "employee_name": emp_name or emp_id,
            "designation": designation,
            "shift_date": shift_date,
            "shift_name": shift_name,
            "shift_time": shift_time,
            "punch_in": punch_in,
            "punch_out": punch_out,
            "work_duration_mins": work_dur,
            "break_duration_mins": break_dur,
            "raw_status": raw_status,
            "status": norm_status,
            "doj": doj,
            "user_status": user_status,
        }
        records.append(rec)

    # Sort dates
    sorted_dates = sorted(list(dates_seen))
    start_date = sorted_dates[0] if sorted_dates else ""
    end_date = sorted_dates[-1] if sorted_dates else ""

    # Calculate Attendance Rate: Present / (Present + Absent + HalfDay)
    denominator = status_counts.get("PRESENT", 0) + status_counts.get("ABSENT", 0) + status_counts.get("HALF_DAY", 0)
    attendance_rate = (
        round(((status_counts.get("PRESENT", 0) + 0.5 * status_counts.get("HALF_DAY", 0)) / denominator) * 100.0, 2)
        if denominator > 0
        else 0.0
    )

    return {
        "store_name": detected_store_name or inferred_store,
        "file_name": file_name,
        "start_date": start_date,
        "end_date": end_date,
        "total_records": len(records),
        "total_employees": len(employees_seen),
        "records": records,
        "summary": {
            "present_count": status_counts.get("PRESENT", 0),
            "absent_count": status_counts.get("ABSENT", 0),
            "week_off_count": status_counts.get("WEEK_OFF", 0),
            "half_day_count": status_counts.get("HALF_DAY", 0),
            "holiday_count": status_counts.get("HOLIDAY", 0),
            "leave_count": status_counts.get("LEAVE", 0),
            "attendance_rate_pct": attendance_rate,
        },
    }
