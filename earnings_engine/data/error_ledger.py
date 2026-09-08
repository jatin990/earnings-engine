"""Local Error Ledger and Diagnostic Engine for Earnings Engine.

Captures, deduplicates, stores, and manages runtime errors, database query failures,
unhandled exceptions, and log errors across local SQLite and logs/error_ledger.json.
Provides utilities for automated pre/post-task error scanning and resolution tracking.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from earnings_engine.config import PROJECT_ROOT, Settings
from earnings_engine.data.db import get_db_connection
from earnings_engine.logging_utils import get_logger

logger = get_logger("earnings_engine.data.error_ledger")
_STREAM_LOCK = threading.Lock()


def get_error_stream_path(base_dir: Path | None = None) -> Path:
    """Return the absolute path to the active error stream JSONL file."""
    base = Path(base_dir or PROJECT_ROOT)
    logs_dir = base / "logs"
    try:
        logs_dir.mkdir(parents=True, exist_ok=True)
        return logs_dir / "active_error_stream.jsonl"
    except (OSError, PermissionError):
        tmp_dir = Path("/tmp/logs")
        tmp_dir.mkdir(parents=True, exist_ok=True)
        return tmp_dir / "active_error_stream.jsonl"


def append_to_error_stream(entry: dict[str, Any], base_dir: Path | None = None) -> bool:
    """Append a structured error event to the active error stream file."""
    stream_path = get_error_stream_path(base_dir)
    try:
        line = json.dumps(entry, ensure_ascii=False) + "\n"
        with _STREAM_LOCK:
            with open(stream_path, "a", encoding="utf-8") as f:
                f.write(line)
        return True
    except Exception as e:
        logger.debug("Failed appending to error stream %s: %s", stream_path, e)
        return False


def read_error_stream(base_dir: Path | None = None) -> list[dict[str, Any]]:
    """Read all active unconsumed error records from the error stream."""
    stream_path = get_error_stream_path(base_dir)
    if not stream_path.exists():
        return []

    events = []
    with _STREAM_LOCK:
        try:
            with open(stream_path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            logger.debug("Failed reading error stream: %s", e)
    return events


def clear_error_stream(base_dir: Path | None = None) -> int:
    """Clear / truncate the active error stream and return the number of items cleared."""
    stream_path = get_error_stream_path(base_dir)
    if not stream_path.exists():
        return 0

    with _STREAM_LOCK:
        try:
            # Count lines first
            count = 0
            with open(stream_path, "r", encoding="utf-8", errors="replace") as f:
                count = sum(1 for line in f if line.strip())
            # Truncate file
            with open(stream_path, "w", encoding="utf-8") as f:
                f.truncate(0)
            return count
        except Exception as e:
            logger.debug("Failed clearing error stream: %s", e)
            return 0


def consume_error_stream(
    base_dir: Path | None = None,
    clear_after: bool = True,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Read all new error events from the active stream, record them in the ledger in a batch, and clear stream."""
    stream_events = read_error_stream(base_dir)
    if not stream_events:
        return {
            "mode": "stream",
            "stream_count": 0,
            "errors_found": 0,
            "newly_recorded": 0,
            "cleared": False,
            "stream_file": str(get_error_stream_path(base_dir)),
        }

    settings = settings or Settings()
    init_error_ledger(settings)
    total_found = len(stream_events)
    now_str = datetime.now(timezone.utc).isoformat(timespec="seconds")

    # Aggregate stream events by signature in memory first (O(N) in Python, O(1) DB writes)
    grouped: dict[str, dict[str, Any]] = {}
    for event in stream_events:
        clean_type = (event.get("error_type") or f"{event.get('logger', 'unknown')}.{event.get('level', 'ERROR')}").strip()
        clean_msg = (event.get("message") or "").strip()
        source_file = event.get("source_file")
        sig = _get_signature(clean_type, clean_msg, source_file)

        if sig not in grouped:
            grouped[sig] = {
                "error_type": clean_type,
                "message": clean_msg,
                "stack_trace": event.get("stack_trace"),
                "source_file": source_file,
                "line_no": event.get("line_no"),
                "context_data": event.get("context_data") or {"streamed": True, "timestamp": event.get("timestamp")},
                "count": 1,
            }
        else:
            grouped[sig]["count"] += 1
            if event.get("stack_trace"):
                grouped[sig]["stack_trace"] = event.get("stack_trace")
            if source_file:
                grouped[sig]["source_file"] = source_file
            if event.get("line_no"):
                grouped[sig]["line_no"] = event.get("line_no")

    newly_recorded = 0
    conn = get_db_connection(settings)
    with conn:
        for sig, data in grouped.items():
            existing = conn.execute(
                "SELECT id, occurrences, status FROM error_ledger WHERE signature = ?",
                (sig,),
            ).fetchone()

            ctx_json = json.dumps(data["context_data"]) if data.get("context_data") else None

            if existing:
                _, _, status = existing
                new_status = "OPEN" if status == "RESOLVED" else status
                conn.execute(
                    """
                    UPDATE error_ledger
                    SET occurrences = occurrences + ?,
                        last_seen_at = ?,
                        message = ?,
                        stack_trace = COALESCE(?, stack_trace),
                        source_file = COALESCE(?, source_file),
                        line_no = COALESCE(?, line_no),
                        context_data = COALESCE(?, context_data),
                        status = ?
                    WHERE signature = ?
                    """,
                    (
                        data["count"],
                        now_str,
                        data["message"],
                        data["stack_trace"],
                        data["source_file"],
                        data["line_no"],
                        ctx_json,
                        new_status,
                        sig,
                    ),
                )
            else:
                err_id = f"err_{sig[:10]}"
                conn.execute(
                    """
                    INSERT INTO error_ledger (
                        id, signature, error_type, message, stack_trace, source_file,
                        line_no, context_data, status, occurrences, first_seen_at, last_seen_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', ?, ?, ?)
                    """,
                    (
                        err_id,
                        sig,
                        data["error_type"],
                        data["message"],
                        data["stack_trace"],
                        data["source_file"],
                        data["line_no"],
                        ctx_json,
                        data["count"],
                        now_str,
                        now_str,
                    ),
                )
                newly_recorded += 1

    _export_json_snapshot(settings)

    cleared_count = 0
    if clear_after:
        cleared_count = clear_error_stream(base_dir)

    return {
        "mode": "stream",
        "stream_count": total_found,
        "errors_found": total_found,
        "newly_recorded": newly_recorded,
        "cleared": clear_after,
        "cleared_count": cleared_count,
        "stream_file": str(get_error_stream_path(base_dir)),
    }


def _get_signature(error_type: str, message: str, source_file: str | None = None) -> str:
    """Generate a stable deterministic signature hash for error grouping."""
    # Normalize message: strip memory addresses, timestamps, dynamic UUIDs/codes
    norm_msg = re.sub(r"0x[0-9a-fA-F]+", "0x...", message or "")
    norm_msg = re.sub(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}", "<TIMESTAMP>", norm_msg)
    norm_msg = re.sub(r"NEXUS-[A-Za-z0-9]+", "NEXUS-<CODE>", norm_msg)
    norm_msg = norm_msg.strip()
    
    raw = f"{error_type.strip()}||{norm_msg}||{(source_file or '').strip()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def init_error_ledger(settings: Settings | None = None) -> None:
    """Ensure the error_ledger table and index exist in the database."""
    settings = settings or Settings()
    conn = get_db_connection(settings)
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS error_ledger (
                id TEXT PRIMARY KEY,
                signature TEXT UNIQUE NOT NULL,
                error_type TEXT NOT NULL,
                message TEXT NOT NULL,
                stack_trace TEXT,
                source_file TEXT,
                line_no INTEGER,
                context_data TEXT,
                status TEXT NOT NULL DEFAULT 'OPEN',
                occurrences INTEGER NOT NULL DEFAULT 1,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                resolved_at TEXT,
                resolution_notes TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_error_ledger_status ON error_ledger (status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_error_ledger_signature ON error_ledger (signature)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_error_ledger_last_seen ON error_ledger (last_seen_at DESC)")


def record_error(
    error_type: str,
    message: str,
    stack_trace: str | None = None,
    source_file: str | None = None,
    line_no: int | None = None,
    context_data: dict[str, Any] | None = None,
    settings: Settings | None = None,
    skip_snapshot: bool = False,
) -> dict[str, Any]:
    """Record an error in the ledger. Deduplicates by signature and increments occurrences."""
    settings = settings or Settings()
    init_error_ledger(settings)

    clean_type = (error_type or "UnknownError").strip()
    clean_msg = (message or "").strip()
    now_str = datetime.now(timezone.utc).isoformat(timespec="seconds")
    signature = _get_signature(clean_type, clean_msg, source_file)
    context_json = json.dumps(context_data) if context_data else None

    conn = get_db_connection(settings)
    with conn:
        existing = conn.execute(
            "SELECT id, occurrences, status FROM error_ledger WHERE signature = ?",
            (signature,),
        ).fetchone()

        if existing:
            err_id, occ, status = existing
            # If it was resolved but popped up again, reopen it
            new_status = "OPEN" if status == "RESOLVED" else status
            conn.execute(
                """
                UPDATE error_ledger
                SET occurrences = occurrences + 1,
                    last_seen_at = ?,
                    message = ?,
                    stack_trace = COALESCE(?, stack_trace),
                    source_file = COALESCE(?, source_file),
                    line_no = COALESCE(?, line_no),
                    context_data = COALESCE(?, context_data),
                    status = ?
                WHERE signature = ?
                """,
                (now_str, clean_msg, stack_trace, source_file, line_no, context_json, new_status, signature),
            )
            total_occ = occ + 1
        else:
            err_id = f"err_{signature[:10]}"
            conn.execute(
                """
                INSERT INTO error_ledger (
                    id, signature, error_type, message, stack_trace, source_file,
                    line_no, context_data, status, occurrences, first_seen_at, last_seen_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', 1, ?, ?)
                """,
                (err_id, signature, clean_type, clean_msg, stack_trace, source_file, line_no, context_json, now_str, now_str),
            )
            total_occ = 1

    # Mirror to local JSON snapshot for agent transparency (skipped during batch consumption)
    if not skip_snapshot:
        _export_json_snapshot(settings)

    return {
        "id": err_id,
        "signature": signature,
        "error_type": clean_type,
        "message": clean_msg,
        "status": "OPEN",
        "occurrences": total_occ,
        "last_seen_at": now_str,
    }


def get_open_errors(settings: Settings | None = None, limit: int = 50) -> list[dict[str, Any]]:
    """Fetch all active un-resolved errors from the ledger."""
    settings = settings or Settings()
    init_error_ledger(settings)

    conn = get_db_connection(settings)
    with conn:
        rows = conn.execute(
            """
            SELECT id, signature, error_type, message, stack_trace, source_file,
                   line_no, context_data, status, occurrences, first_seen_at, last_seen_at,
                   resolved_at, resolution_notes
            FROM error_ledger
            WHERE status IN ('OPEN', 'INVESTIGATING')
            ORDER BY last_seen_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [_row_to_dict(r) for r in rows]


def get_all_errors(settings: Settings | None = None, limit: int = 100) -> list[dict[str, Any]]:
    """Fetch all recorded errors in the ledger."""
    settings = settings or Settings()
    init_error_ledger(settings)

    conn = get_db_connection(settings)
    with conn:
        rows = conn.execute(
            """
            SELECT id, signature, error_type, message, stack_trace, source_file,
                   line_no, context_data, status, occurrences, first_seen_at, last_seen_at,
                   resolved_at, resolution_notes
            FROM error_ledger
            ORDER BY last_seen_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [_row_to_dict(r) for r in rows]


def mark_error_resolved(
    identifier: str,
    resolution_notes: str = "Resolved by agent task fix",
    settings: Settings | None = None,
) -> bool:
    """Mark an error as resolved by its ID or signature hash."""
    settings = settings or Settings()
    init_error_ledger(settings)

    now_str = datetime.now(timezone.utc).isoformat(timespec="seconds")
    clean_id = identifier.strip()

    conn = get_db_connection(settings)
    with conn:
        cur = conn.execute(
            """
            UPDATE error_ledger
            SET status = 'RESOLVED',
                resolved_at = ?,
                resolution_notes = ?
            WHERE id = ? OR signature = ?
            """,
            (now_str, resolution_notes.strip(), clean_id, clean_id),
        )
        updated = cur.rowcount > 0

    if updated:
        _export_json_snapshot(settings)
    return updated


def get_error_summary(settings: Settings | None = None) -> dict[str, Any]:
    """Return error summary KPIs and health metrics."""
    settings = settings or Settings()
    init_error_ledger(settings)

    conn = get_db_connection(settings)
    with conn:
        total = conn.execute("SELECT COUNT(*) FROM error_ledger").fetchone()[0]
        open_cnt = conn.execute("SELECT COUNT(*) FROM error_ledger WHERE status IN ('OPEN', 'INVESTIGATING')").fetchone()[0]
        resolved_cnt = conn.execute("SELECT COUNT(*) FROM error_ledger WHERE status = 'RESOLVED'").fetchone()[0]
        total_occurrences = conn.execute("SELECT COALESCE(SUM(occurrences), 0) FROM error_ledger").fetchone()[0]
        
        top_open = conn.execute(
            """
            SELECT id, error_type, message, occurrences, last_seen_at
            FROM error_ledger
            WHERE status IN ('OPEN', 'INVESTIGATING')
            ORDER BY occurrences DESC, last_seen_at DESC
            LIMIT 5
            """
        ).fetchall()

    return {
        "total_unique_errors": total,
        "open_errors": open_cnt,
        "resolved_errors": resolved_cnt,
        "total_occurrences": total_occurrences,
        "is_healthy": open_cnt == 0,
        "top_open_errors": [
            {
                "id": r[0],
                "error_type": r[1],
                "message": r[2],
                "occurrences": r[3],
                "last_seen_at": r[4],
            }
            for r in top_open
        ],
    }


def scan_log_files(
    base_dir: Path | None = None,
    full_scan: bool = False,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Scan for errors. Consumes the active error stream by default (O(1)), or performs a full log scan."""
    base = Path(base_dir or PROJECT_ROOT)

    # 1. Fast path: consume active error stream if available
    if not full_scan:
        stream_res = consume_error_stream(base_dir=base, clear_after=True, settings=settings)
        if stream_res.get("stream_count", 0) > 0:
            return {
                "mode": "stream",
                "scanned_files": 1,
                "errors_found": stream_res["errors_found"],
                "newly_recorded": stream_res["newly_recorded"],
                "stream_cleared": stream_res["cleared"],
            }

    # 2. File scan path
    logs_dir = base / "logs"
    if not logs_dir.exists():
        return {"mode": "files", "scanned_files": 0, "errors_found": 0, "newly_recorded": 0}

    all_logs = sorted(logs_dir.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    # If not full scan and stream was empty, scan top 3 most recent logs
    log_files = all_logs if full_scan else all_logs[:3]
    
    error_pattern = re.compile(
        r"^(?P<timestamp>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2},\d{3})\s+(?P<level>ERROR|CRITICAL)\s+(?P<logger>[\w\.\-]+)\s+(?P<message>.*)$"
    )
    
    total_found = 0
    newly_recorded = 0

    for log_path in log_files:
        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except Exception:
            continue

        idx = 0
        while idx < len(lines):
            line = lines[idx]
            match = error_pattern.match(line.strip())
            if match:
                total_found += 1
                level = match.group("level")
                logger_name = match.group("logger")
                msg = match.group("message")
                
                # Check for subsequent traceback lines
                traceback_lines = []
                idx += 1
                while idx < len(lines) and (lines[idx].startswith("  ") or lines[idx].startswith("Traceback") or "File \"" in lines[idx]):
                    traceback_lines.append(lines[idx])
                    idx += 1

                stack_trace = "".join(traceback_lines) if traceback_lines else None
                
                # Determine error type
                error_type = f"{logger_name}.{level}"
                if "[TURSO-QUERY-ERROR]" in msg:
                    error_type = "DatabaseQueryError"
                elif "SQLite input error" in msg:
                    error_type = "SQLiteInputError"
                elif stack_trace:
                    last_line = [l.strip() for l in traceback_lines if l.strip()][-1] if traceback_lines else ""
                    if ":" in last_line:
                        error_type = last_line.split(":", 1)[0].strip()

                # Extract source file / line if present
                source_file = None
                line_no = None
                if stack_trace:
                    file_matches = re.findall(r'File "([^"]+)", line (\d+)', stack_trace)
                    if file_matches:
                        source_file, line_no = file_matches[-1]
                        line_no = int(line_no)

                res = record_error(
                    error_type=error_type,
                    message=msg,
                    stack_trace=stack_trace,
                    source_file=source_file,
                    line_no=line_no,
                    context_data={"log_file": log_path.name},
                    settings=settings,
                    skip_snapshot=True,
                )
                if res.get("occurrences", 1) == 1:
                    newly_recorded += 1
            else:
                idx += 1

    _export_json_snapshot(settings)

    return {
        "scanned_files": len(log_files),
        "errors_found": total_found,
        "newly_recorded": newly_recorded,
    }


def _export_json_snapshot(settings: Settings | None = None) -> None:
    """Export error ledger state to logs/error_ledger.json for fast agent read/inspection."""
    try:
        base = PROJECT_ROOT
        logs_dir = base / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        json_path = logs_dir / "error_ledger.json"

        summary = get_error_summary(settings)
        open_errs = get_open_errors(settings, limit=100)

        payload = {
            "last_updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "summary": summary,
            "open_errors": open_errs,
        }
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
    except Exception as e:
        logger.debug("Failed saving error_ledger.json snapshot: %s", e)


def _row_to_dict(row: tuple) -> dict[str, Any]:
    return {
        "id": row[0],
        "signature": row[1],
        "error_type": row[2],
        "message": row[3],
        "stack_trace": row[4],
        "source_file": row[5],
        "line_no": row[6],
        "context_data": json.loads(row[7]) if row[7] else None,
        "status": row[8],
        "occurrences": row[9],
        "first_seen_at": row[10],
        "last_seen_at": row[11],
        "resolved_at": row[12],
        "resolution_notes": row[13],
    }
