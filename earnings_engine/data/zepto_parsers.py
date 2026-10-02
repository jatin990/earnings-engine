"""
Zepto Dark Store Operational Parsers & Email Metrics Extraction Engine.
Robust zero-dependency XML/Zip parsers for Store Performance Scorecard, DQ Loss, and Shrinkage reports,
with structured regex heuristics for extracting KPI metrics from raw Zepto operational emails.
"""

from __future__ import annotations

import io
import os
import re
from datetime import datetime, date
from typing import Any, Dict, List, Optional, Union

from earnings_engine.data.zepto_attendance_parser import (
    _extract_xlsx_native,
    excel_date_to_iso,
    parse_duration_to_mins,
)


# ===========================================================================
# Deterministic Subject Line Pattern Registry & Classifier
# ===========================================================================

ZEPTO_SUBJECT_PATTERNS = [
    # 1. DQ Loss & Spoilage Audits (e.g. "JMU-Sainik Colony DQ Loss - 2026-09-30", "Store BLR-01 - Daily Shift Summary & DQ Loss Audit - 2026-09-30")
    {
        "category": "DQ_LOSS",
        "category_label": "DQ Loss & Expiry",
        "badge_color": "rose",
        "icon": "⚠️",
        "pattern": re.compile(
            r"^(?:Store\s+)?(?P<store>[A-Za-z0-9_\-\s]+?)\s*[-–:]\s*(?:Daily\s+)?(?:Shift\s+Summary\s+&\s+)?DQ\s+Loss(?:\s+Audit)?(?:\s*&\s*Expiry)?\s*[-–:]\s*(?P<date>\d{4}-\d{2}-\d{2})",
            re.IGNORECASE,
        ),
    },
    # 2. Shrinkage & Inventory Variance (e.g. "JMU-Sainik Colony Shrinkage - 2026-09-30", "Weekly Store Shrinkage & Cycle Count Variance")
    {
        "category": "SHRINKAGE",
        "category_label": "Shrinkage & Variance",
        "badge_color": "amber",
        "icon": "📉",
        "pattern": re.compile(
            r"^(?:Store\s+)?(?P<store>[A-Za-z0-9_\-\s]+?)\s*[-–:]\s*(?:Daily\s+|Weekly\s+)?(?:Store\s+)?Shrinkage(?:\s*&\s*(?:Cycle\s+Count\s+)?Variance)?\s*[-–:]\s*(?P<date>\d{4}-\d{2}-\d{2})",
            re.IGNORECASE,
        ),
    },
    # 3. Attendance Muster Reports (e.g. "JMU-Sainik_Colony-Attendance-report-8165178", "Store JMU - Attendance - 2026-09-30")
    {
        "category": "ATTENDANCE",
        "category_label": "Attendance & Shifts",
        "badge_color": "sky",
        "icon": "👥",
        "pattern": re.compile(
            r"^(?P<store>[A-Za-z0-9_\-\s]+?)[-_]Attendance[-_]report[-_](?P<report_id>\d+)",
            re.IGNORECASE,
        ),
    },
    {
        "category": "ATTENDANCE",
        "category_label": "Attendance & Shifts",
        "badge_color": "sky",
        "icon": "👥",
        "pattern": re.compile(
            r"^(?:Store\s+)?(?P<store>[A-Za-z0-9_\-\s]+?)\s*[-–:]\s*(?:Daily\s+)?(?:Staff\s+)?Attendance(?:\s+Muster|\s+Report)?\s*[-–:]\s*(?P<date>\d{4}-\d{2}-\d{2})",
            re.IGNORECASE,
        ),
    },
    # 4. Daily Store Metrics & Performance Scorecard (e.g. "Store JMU-Sainik Colony Daily Update - 2026-09-30", "Store Metrics Summary - 2026-09-30")
    {
        "category": "STORE_METRICS",
        "category_label": "Store Metric Summary",
        "badge_color": "emerald",
        "icon": "📊",
        "pattern": re.compile(
            r"^(?:Store\s+)?(?P<store>[A-Za-z0-9_\-\s]+?)\s*[-–:]\s*(?:Daily\s+)?(?:Store\s+)?(?:Metrics?(?:\s+Summary)?|Update|Scorecard|Performance)\s*[-–:]\s*(?P<date>\d{4}-\d{2}-\d{2})",
            re.IGNORECASE,
        ),
    },
    # 5. Manpower Utilization & Roster
    {
        "category": "MANPOWER_UTILIZATION",
        "category_label": "Manpower Utilization",
        "badge_color": "purple",
        "icon": "⚡",
        "pattern": re.compile(
            r"^(?:Store\s+)?(?P<store>[A-Za-z0-9_\-\s]+?)\s*[-–:]\s*(?:Manpower\s+Plan|Utilization|Picker\s+IPP|Staffing\s+Roster)\s*[-–:]\s*(?P<date>\d{4}-\d{2}-\d{2})",
            re.IGNORECASE,
        ),
    },
    # 6. Monthly Manpower Planning
    {
        "category": "MANPOWER_PLAN",
        "category_label": "Monthly Manpower Plan",
        "badge_color": "indigo",
        "icon": "📋",
        "pattern": re.compile(
            r"(?:Monthly\s+)?Manpower\s+Plan(?:ning)?|Target\s+(?:Headcount|HC)|Staffing\s+Budget",
            re.IGNORECASE,
        ),
    },
    # 7. Security Alert
    {
        "category": "SECURITY_ALERT",
        "category_label": "Security Alert",
        "badge_color": "slate",
        "icon": "🔒",
        "pattern": re.compile(
            r"Security\s+Alert|Critical\s+Security|Unauthorized\s+Access|Password\s+Reset",
            re.IGNORECASE,
        ),
    },
]


def match_zepto_subject_pattern(
    subject: str,
    sender: str = "",
    snippet: str = "",
) -> Dict[str, Any]:
    """
    Deterministic pattern matcher for Zepto operational emails.
    Extracts store name, date, report type, report id, and metadata directly from subject line.
    Falls back to keyword matching if regex pattern does not strictly match.
    """
    sub_clean = (subject or "").strip()
    from_clean = (sender or "").strip().lower()
    snip_clean = (snippet or "").strip().lower()

    for item in ZEPTO_SUBJECT_PATTERNS:
        pat = item["pattern"]
        m = pat.search(sub_clean)
        if m:
            groups = m.groupdict()
            store_name = groups.get("store", "").strip().replace("_", " ") if groups.get("store") else ""
            record_date = groups.get("date", "").strip() if groups.get("date") else ""
            report_id = groups.get("report_id", "").strip() if groups.get("report_id") else ""

            return {
                "category": item["category"],
                "category_label": item["category_label"],
                "badge_color": item["badge_color"],
                "icon": item["icon"],
                "store_name": store_name,
                "record_date": record_date,
                "report_id": report_id,
                "is_pattern_matched": True,
            }

    # Fallback keyword classification if exact regex pattern didn't match
    sub_lower = sub_clean.lower()
    if "store metric summary" in sub_lower or "store metric" in sub_lower or "daily scorecard" in sub_lower:
        cat = "STORE_METRICS"
        lbl = "Store Metric Summary"
        color = "emerald"
        icon = "📊"
    elif "attendance" in sub_lower or "muster" in sub_lower or "shift report" in sub_lower:
        cat = "ATTENDANCE"
        lbl = "Attendance & Shifts"
        color = "sky"
        icon = "👥"
    elif "manpower utilization" in sub_lower or "utilization" in sub_lower or "picker ipp" in sub_lower:
        cat = "MANPOWER_UTILIZATION"
        lbl = "Manpower Utilization"
        color = "purple"
        icon = "⚡"
    elif "dq loss" in sub_lower or "damage" in sub_lower or "expiry" in sub_lower or "spoilage" in sub_lower:
        cat = "DQ_LOSS"
        lbl = "DQ Loss & Expiry"
        color = "rose"
        icon = "⚠️"
    elif "shrinkage" in sub_lower or "cycle count" in sub_lower or "fcc" in sub_lower or "short-pick" in sub_lower:
        cat = "SHRINKAGE"
        lbl = "Shrinkage & Variance"
        color = "amber"
        icon = "📉"
    elif "manpower plan" in sub_lower or "headcount" in sub_lower or "target hc" in sub_lower:
        cat = "MANPOWER_PLAN"
        lbl = "Monthly Manpower Plan"
        color = "indigo"
        icon = "📋"
    elif "security alert" in sub_lower or "critical security" in sub_lower or "google" in from_clean:
        cat = "SECURITY_ALERT"
        lbl = "Security Alert"
        color = "slate"
        icon = "🔒"
    else:
        cat = "OPERATIONAL"
        lbl = "Operational Update"
        color = "slate"
        icon = "📧"

    # Extract store name heuristically from subject if available
    inferred_store = ""
    store_match = re.search(r"([A-Z]{2,4}-[A-Za-z0-9_]+)", sub_clean)
    if store_match:
        inferred_store = store_match.group(1).replace("_", " ")

    # Extract date heuristically if present
    inferred_date = ""
    date_match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", sub_clean)
    if date_match:
        inferred_date = date_match.group(1)

    return {
        "category": cat,
        "category_label": lbl,
        "badge_color": color,
        "icon": icon,
        "store_name": inferred_store,
        "record_date": inferred_date,
        "report_id": "",
        "is_pattern_matched": False,
    }


def build_targeted_gmail_query(month: str | None = None) -> tuple[str, str]:
    """
    Build targeted Gmail API query string focusing strictly on Zepto operational pattern keywords.
    Avoids fetching random or noisy unrelated personal emails.
    Returns (clean_month_ym, gmail_q_str).
    """
    pattern_clause = 'subject:("DQ Loss" OR "Shrinkage" OR "Attendance-report" OR "Attendance" OR "Metrics" OR "Manpower" OR "Daily Update" OR "Scorecard" OR "Shift Summary" OR "Muster")'

    if not month or month.upper() in ("CURRENT", "NOW"):
        clean_month = datetime.now().strftime("%Y-%m")
    elif month.upper() == "ALL":
        return ("ALL", pattern_clause)
    else:
        clean_month = month.strip()

    try:
        parts = clean_month.split("-")
        y = int(parts[0])
        m = int(parts[1])
        start_date = f"{y:04d}/{m:02d}/01"
        if m == 12:
            next_y, next_m = y + 1, 1
        else:
            next_y, next_m = y, m + 1
        end_date = f"{next_y:04d}/{next_m:02d}/01"
        return (clean_month, f"{pattern_clause} after:{start_date} before:{end_date}")
    except Exception:
        return (clean_month, pattern_clause)


# ---------------------------------------------------------------------------
# 1. Store Metrics / Scorecard Excel & Email Parser
# ---------------------------------------------------------------------------

def parse_zepto_store_metrics_excel(
    file_source: Union[str, bytes, io.BytesIO],
    file_name: str = "",
) -> Dict[str, Any]:
    """
    Parse Zepto Dark Store daily metric summary spreadsheet.
    Extracts sales GMV, order volume, AOV, inbound/outbound hours, IPP, and 10-min SLA adherence.
    """
    if isinstance(file_source, str) and not file_name:
        file_name = os.path.basename(file_source)

    matrix = _extract_xlsx_native(file_source)
    if not matrix:
        raise ValueError("Store metrics spreadsheet contains no readable rows.")

    # Infer Store Name
    inferred_store = "Zepto Dark Store"
    if file_name:
        clean_name = os.path.splitext(file_name)[0]
        m = re.search(r"([A-Z]{3,}-[A-Za-z0-9_]+)", clean_name)
        if m:
            inferred_store = m.group(1).replace("_", " ")

    # Expected column aliases
    alias_map = {
        "metric_date": ["date", "metric date", "report date", "day", "order date"],
        "store_name": ["store", "store name", "darkstore", "dark store", "hub"],
        "sales_gmv": ["sales gmv", "gmv", "total sales", "revenue", "gross sales", "sales"],
        "order_count": ["orders", "order count", "total orders", "dispatched orders", "delivered orders", "orders count"],
        "aov": ["aov", "average order value", "avg order value", "basket size"],
        "inbound_hours": ["inbound hours", "inbound hrs", "inbound", "grn hours"],
        "outbound_hours": ["outbound hours", "outbound hrs", "outbound", "dispatch hours"],
        "packer_ipp": ["packer ipp", "ipp", "picker ipp", "items per hour", "packer throughput"],
        "sla_adherence_pct": ["sla adherence", "sla %", "10 min sla", "10-min sla", "sla adherence %", "sla"],
    }

    header_idx = -1
    col_map = {}

    for idx, row in enumerate(matrix[:20]):
        row_lower = [str(c).strip().lower() for c in row]
        matched = {}
        for canonical, aliases in alias_map.items():
            for c_idx, cell_str in enumerate(row_lower):
                if cell_str in aliases or any(alias == cell_str for alias in aliases):
                    matched[canonical] = c_idx
                    break
            if canonical not in matched:
                for c_idx, cell_str in enumerate(row_lower):
                    if any(alias in cell_str for alias in aliases):
                        matched[canonical] = c_idx
                        break

        # Check for core columns
        if "metric_date" in matched or "sales_gmv" in matched or "order_count" in matched:
            header_idx = idx
            col_map = matched
            break

    records = []
    if header_idx != -1:
        data_rows = matrix[header_idx + 1:]
    else:
        # If no explicit header row, try parsing row by row heuristically
        data_rows = matrix

    for r_idx, row in enumerate(data_rows):
        if not any(row):
            continue

        raw_date = row[col_map["metric_date"]] if "metric_date" in col_map and col_map["metric_date"] < len(row) else ""
        metric_date = excel_date_to_iso(raw_date) or datetime.now().strftime("%Y-%m-%d")

        store = (
            str(row[col_map["store_name"]]).strip()
            if "store_name" in col_map and col_map["store_name"] < len(row) and str(row[col_map["store_name"]]).strip()
            else inferred_store
        )

        def _to_float(val: Any, default: float = 0.0) -> float:
            if val is None or val == "":
                return default
            try:
                # Remove commas, currency symbols, and percentage signs
                clean_v = re.sub(r"[₹$,% ]", "", str(val).strip())
                return float(clean_v)
            except (ValueError, TypeError):
                return default

        sales_gmv = _to_float(row[col_map["sales_gmv"]]) if "sales_gmv" in col_map and col_map["sales_gmv"] < len(row) else 0.0
        order_count = int(_to_float(row[col_map["order_count"]])) if "order_count" in col_map and col_map["order_count"] < len(row) else 0
        aov = _to_float(row[col_map["aov"]]) if "aov" in col_map and col_map["aov"] < len(row) else 0.0
        if aov == 0.0 and order_count > 0 and sales_gmv > 0.0:
            aov = round(sales_gmv / order_count, 2)

        inbound_hours = _to_float(row[col_map["inbound_hours"]]) if "inbound_hours" in col_map and col_map["inbound_hours"] < len(row) else 0.0
        outbound_hours = _to_float(row[col_map["outbound_hours"]]) if "outbound_hours" in col_map and col_map["outbound_hours"] < len(row) else 0.0
        packer_ipp = _to_float(row[col_map["packer_ipp"]]) if "packer_ipp" in col_map and col_map["packer_ipp"] < len(row) else 0.0
        sla_pct = _to_float(row[col_map["sla_adherence_pct"]], default=100.0) if "sla_adherence_pct" in col_map and col_map["sla_adherence_pct"] < len(row) else 100.0
        if 0 < sla_pct <= 1.0: # Fraction represented as 0.985
            sla_pct = round(sla_pct * 100.0, 2)

        if sales_gmv > 0 or order_count > 0 or packer_ipp > 0:
            records.append({
                "store_name": store,
                "metric_date": metric_date,
                "sales_gmv": sales_gmv,
                "order_count": order_count,
                "aov": aov,
                "inbound_hours": inbound_hours,
                "outbound_hours": outbound_hours,
                "packer_ipp": packer_ipp,
                "sla_adherence_pct": sla_pct,
                "raw_source": "EXCEL_UPLOAD",
            })

    return {
        "store_name": inferred_store,
        "total_records": len(records),
        "records": records,
    }


def extract_metrics_from_email_body(text: str) -> Dict[str, Any]:
    """
    Extract key operational numbers from plain text / snippet of Zepto operational emails.
    Identifies GMV sales, order throughput, AOV, SLA adherence %, and IPP.
    """
    metrics: Dict[str, Any] = {}
    if not text:
        return metrics

    clean_text = text.replace(",", "").strip()

    # 1. GMV / Sales (e.g. "GMV: ₹4,52,000", "Sales of 350000", "GMV 2.4L")
    gmv_match = re.search(r"(?:gmv|sales|revenue)(?:\s+of)?[:\s\-]+(?:rs\.?|inr|₹)?\s*([\d\.]+(?:\s*(?:k|lakhs?|l|cr))?)", clean_text, re.I)
    if gmv_match:
        val_str = gmv_match.group(1).lower().strip()
        val = 0.0
        if "l" in val_str or "lakh" in val_str:
            num = float(re.sub(r"[^\d\.]", "", val_str) or 0)
            val = num * 100000.0
        elif "cr" in val_str:
            num = float(re.sub(r"[^\d\.]", "", val_str) or 0)
            val = num * 10000000.0
        elif "k" in val_str:
            num = float(re.sub(r"[^\d\.]", "", val_str) or 0)
            val = num * 1000.0
        else:
            try:
                val = float(val_str)
            except ValueError:
                pass
        if val > 0:
            metrics["sales_gmv"] = val

    # 2. Orders count (e.g. "Orders: 1,420", "1250 orders dispatched", "Total Orders: 980")
    order_match = re.search(r"(?:orders?|total orders|dispatched)[:\s\-]+(\d+)", clean_text, re.I)
    if not order_match:
        order_match = re.search(r"(\d+)\s+orders", clean_text, re.I)
    if order_match:
        metrics["order_count"] = int(order_match.group(1))

    # 3. AOV (e.g. "AOV: ₹340", "Basket: 412")
    aov_match = re.search(r"(?:aov|basket|avg order value)[:\s\-]+(?:rs\.?|inr|₹)?\s*([\d\.]+)", clean_text, re.I)
    if aov_match:
        metrics["aov"] = float(aov_match.group(1))

    # 4. SLA Adherence % (e.g. "SLA: 98.4%", "10-min SLA 99.2%")
    sla_match = re.search(r"(?:sla|10-?min(?:ute)? sla|adherence)[:\s\-]+([\d\.]+)%", clean_text, re.I)
    if sla_match:
        metrics["sla_adherence_pct"] = float(sla_match.group(1))

    # 5. IPP Throughput (e.g. "IPP: 132", "Picker IPP 140")
    ipp_match = re.search(r"(?:ipp|picker ipp|packer ipp)[:\s\-]+([\d\.]+)", clean_text, re.I)
    if ipp_match:
        metrics["packer_ipp"] = float(ipp_match.group(1))

    # 6. Loss / Shrinkage Amount (e.g. "DQ Loss: ₹4,500", "Damages: Rs. 1,200", "Shrinkage: 1450")
    # First, strip date stamps like '2026-09-30' or '2026/09/30' from text to avoid false year capture
    sanitized_text = re.sub(r"\b202\d[-/]\d{2}[-/]\d{2}\b", " ", clean_text)
    sanitized_text = re.sub(r"\b\d{2}[-/]\d{2}[-/]202\d\b", " ", sanitized_text)
    loss_match = re.search(r"(?:dq\s*loss|shrinkage|spoilage|damage|defect\s*loss)\s*[:=]\s*(?:rs\.?|inr|₹)?\s*([\d\.]+)", sanitized_text, re.I)
    if not loss_match:
        loss_match = re.search(r"(?:dq\s*loss|shrinkage|spoilage|damage|defect\s*loss)\s*(?:of)?\s*(?:rs\.?|inr|₹)\s*([\d\.]+)", sanitized_text, re.I)
    if not loss_match:
        # Check for trailing monetary indicator e.g. "₹4,500 in DQ Loss" or "Rs. 1,200 damage"
        loss_match = re.search(r"(?:rs\.?|inr|₹)\s*([\d\.]+)\s*(?:in\s+|of\s+)?(?:dq\s*loss|shrinkage|spoilage|damage|defect\s*loss)", sanitized_text, re.I)
    if loss_match:
        amt = float(loss_match.group(1))
        # Ensure it is not a stray 4-digit calendar year unless explicit currency was matched
        matched_str = loss_match.group(0).lower()
        has_curr = "₹" in matched_str or "rs" in matched_str or "inr" in matched_str
        if not (2020 <= amt <= 2035 and not has_curr):
            metrics["loss_amount"] = amt

    return metrics


# ---------------------------------------------------------------------------
# 2. DQ Loss & Shrinkage Excel Parser
# ---------------------------------------------------------------------------

def parse_zepto_loss_shrinkage_excel(
    file_source: Union[str, bytes, io.BytesIO],
    file_name: str = "",
) -> Dict[str, Any]:
    """
    Parse Zepto Dark Store DQ Loss, Spoilage, and Inventory Shrinkage Excel report.
    Extracts SKU defect counts, loss type (DQ_LOSS, SHRINKAGE, SPOILAGE), category, and monetary damage.
    """
    if isinstance(file_source, str) and not file_name:
        file_name = os.path.basename(file_source)

    matrix = _extract_xlsx_native(file_source)
    if not matrix:
        raise ValueError("Loss/Shrinkage spreadsheet contains no readable rows.")

    inferred_store = "Zepto Dark Store"
    if file_name:
        clean_name = os.path.splitext(file_name)[0]
        m = re.search(r"([A-Z]{3,}-[A-Za-z0-9_]+)", clean_name)
        if m:
            inferred_store = m.group(1).replace("_", " ")

    alias_map = {
        "record_date": ["date", "record date", "damage date", "audit date", "loss date"],
        "store_name": ["store", "store name", "darkstore", "hub"],
        "loss_type": ["loss type", "type", "defect type", "classification", "loss category"],
        "category": ["category", "dept", "department", "sku category", "item group"],
        "sku_id": ["sku id", "sku_id", "sku code", "sku_code", "sku", "item code", "item_code", "article id", "article_id", "barcode", "product code"],
        "item_name": ["item name", "item_name", "product name", "product_name", "sku name", "sku_name", "item description", "product description", "item"],
        "amount": ["amount", "loss amount", "value", "total loss", "cost", "damage value", "cost value"],
        "sku_count": ["sku count", "skus", "quantity", "qty", "units", "items", "defect count", "count"],
        "notes": ["notes", "remarks", "reason", "defect reason", "root cause", "comments", "description"],
    }

    header_idx = -1
    col_map = {}

    for idx, row in enumerate(matrix[:25]):
        row_lower = [str(c).strip().lower() for c in row]
        matched = {}
        for canonical, aliases in alias_map.items():
            for c_idx, cell_str in enumerate(row_lower):
                if cell_str in aliases:
                    matched[canonical] = c_idx
                    break
            if canonical not in matched:
                for c_idx, cell_str in enumerate(row_lower):
                    if any(alias in cell_str for alias in aliases):
                        matched[canonical] = c_idx
                        break

        if "amount" in matched or "loss_type" in matched or "sku_count" in matched:
            header_idx = idx
            col_map = matched
            break

    records = []
    data_rows = matrix[header_idx + 1:] if header_idx != -1 else matrix

    for row in data_rows:
        if not any(row):
            continue

        raw_date = row[col_map["record_date"]] if "record_date" in col_map and col_map["record_date"] < len(row) else ""
        record_date = excel_date_to_iso(raw_date) or datetime.now().strftime("%Y-%m-%d")

        store = (
            str(row[col_map["store_name"]]).strip()
            if "store_name" in col_map and col_map["store_name"] < len(row) and str(row[col_map["store_name"]]).strip()
            else inferred_store
        )

        def _clean_num(val: Any, default: float = 0.0) -> float:
            if val is None or val == "":
                return default
            try:
                clean_v = re.sub(r"[₹$,% ]", "", str(val).strip())
                return float(clean_v)
            except (ValueError, TypeError):
                return default

        amount = _clean_num(row[col_map["amount"]]) if "amount" in col_map and col_map["amount"] < len(row) else 0.0
        sku_count = int(_clean_num(row[col_map["sku_count"]])) if "sku_count" in col_map and col_map["sku_count"] < len(row) else 1

        raw_type = str(row[col_map["loss_type"]]).strip().upper() if "loss_type" in col_map and col_map["loss_type"] < len(row) else "DQ_LOSS"
        loss_type = "DQ_LOSS"
        if "SHRINK" in raw_type or "VARIANCE" in raw_type or "CYCLE" in raw_type:
            loss_type = "SHRINKAGE"
        elif "DAMAGE" in raw_type or "TRANSIT" in raw_type:
            loss_type = "TRANSIT_DAMAGE"
        elif "EXPIRY" in raw_type or "SPOIL" in raw_type or "FRESH" in raw_type:
            loss_type = "SPOILAGE"

        raw_cat = str(row[col_map["category"]]).strip().upper() if "category" in col_map and col_map["category"] < len(row) else "GENERAL"
        category = "GENERAL"
        if "FRUIT" in raw_cat or "VEG" in raw_cat or "F&V" in raw_cat:
            category = "FRUITS_VEG"
        elif "DAIRY" in raw_cat or "MILK" in raw_cat:
            category = "DAIRY"
        elif "MEAT" in raw_cat or "FROZEN" in raw_cat:
            category = "FROZEN_MEAT"
        elif "FMCG" in raw_cat or "SNACK" in raw_cat or "GROCERY" in raw_cat:
            category = "FMCG_PACKAGED"
        elif "BEVERAGE" in raw_cat or "DRINK" in raw_cat:
            category = "BEVERAGES"
        elif raw_cat:
            category = raw_cat

        sku_id = (
            str(row[col_map["sku_id"]]).strip()
            if "sku_id" in col_map and col_map["sku_id"] < len(row) and row[col_map["sku_id"]] is not None and str(row[col_map["sku_id"]]).strip() != "None"
            else ""
        )
        item_name = (
            str(row[col_map["item_name"]]).strip()
            if "item_name" in col_map and col_map["item_name"] < len(row) and row[col_map["item_name"]] is not None and str(row[col_map["item_name"]]).strip() != "None"
            else ""
        )
        notes = (
            str(row[col_map["notes"]]).strip()
            if "notes" in col_map and col_map["notes"] < len(row) and row[col_map["notes"]] is not None and str(row[col_map["notes"]]).strip() != "None"
            else ""
        )

        if not notes:
            notes = item_name or sku_id or "Defect item"
        if not item_name and notes and not sku_id:
            item_name = notes

        if amount > 0 or sku_count > 0:
            records.append({
                "store_name": store,
                "record_date": record_date,
                "loss_type": loss_type,
                "category": category,
                "sku_id": sku_id,
                "item_name": item_name,
                "amount": amount,
                "sku_count": sku_count,
                "notes": notes,
            })

    return {
        "store_name": inferred_store,
        "total_records": len(records),
        "records": records,
    }
