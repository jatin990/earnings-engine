"""Unit tests for the Local Error Ledger, deduplication, log scanning, and API endpoints."""
from __future__ import annotations

import os
from pathlib import Path
from starlette.testclient import TestClient

from earnings_engine.config import Settings
from earnings_engine.data.error_ledger import (
    get_all_errors,
    get_error_summary,
    get_open_errors,
    init_error_ledger,
    mark_error_resolved,
    record_error,
    scan_log_files,
)
from earnings_engine.api.server import app


def test_record_and_deduplicate_error(tmp_path: Path):
    import uuid
    settings = Settings()
    init_error_ledger(settings)

    test_msg = f"Test parsing failed at offset {uuid.uuid4().hex[:8]}"

    # 1. Record first instance
    res1 = record_error(
        error_type="TestParsingError",
        message=test_msg,
        source_file="test_file.py",
        line_no=42,
        settings=settings,
    )
    assert res1["error_type"] == "TestParsingError"
    assert res1["status"] == "OPEN"
    assert res1["occurrences"] == 1
    err_id = res1["id"]

    # 2. Record duplicate instance (same type and message)
    res2 = record_error(
        error_type="TestParsingError",
        message=test_msg,
        source_file="test_file.py",
        line_no=42,
        settings=settings,
    )
    assert res2["id"] == err_id
    assert res2["occurrences"] == 2

    # 3. Check open errors list
    open_errs = get_open_errors(settings)
    matching = [e for e in open_errs if e["id"] == err_id]
    assert len(matching) == 1
    assert matching[0]["occurrences"] == 2

    # 4. Mark resolved
    resolved = mark_error_resolved(err_id, resolution_notes="Fixed test parser regex", settings=settings)
    assert resolved is True

    # 5. Check open errors again (should be empty of this error)
    open_after = get_open_errors(settings)
    assert not any(e["id"] == err_id for e in open_after)


def test_log_scanner_and_summary(tmp_path: Path):
    settings = Settings()
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    sample_log = logs_dir / "earnings_engine-test.log"
    sample_log.write_text(
        "2026-08-24 00:00:01,100 INFO earnings_engine.test Normal execution\n"
        "2026-08-24 00:00:02,200 ERROR earnings_engine.data.db [TURSO-QUERY-ERROR] Remote statement execution failed: SQLite input error: no such column: dummy_col (SQL: SELECT dummy_col FROM test)\n"
        "2026-08-24 00:00:03,300 ERROR earnings_engine.api.test Traceback occurred\n"
        '  File "test_runner.py", line 99, in run_task\n'
        "    raise KeyError('missing_key')\n"
        "KeyError: 'missing_key'\n",
        encoding="utf-8",
    )

    scan_res = scan_log_files(base_dir=tmp_path, settings=settings)
    assert scan_res["scanned_files"] >= 1
    assert scan_res["errors_found"] >= 2

    summary = get_error_summary(settings)
    assert summary["total_unique_errors"] >= 2
    assert summary["open_errors"] >= 2


def test_error_ledger_api_endpoints():
    client = TestClient(app)

    # 1. Summary endpoint
    resp_sum = client.get("/api/v1/errors/summary")
    assert resp_sum.status_code == 200
    sum_data = resp_sum.json()
    assert "total_unique_errors" in sum_data
    assert "open_errors" in sum_data

    # 2. Open errors endpoint
    resp_open = client.get("/api/v1/errors/open")
    assert resp_open.status_code == 200
    open_data = resp_open.json()
    assert "open_errors" in open_data

    # 3. All errors endpoint
    resp_all = client.get("/api/v1/errors")
    assert resp_all.status_code == 200
    assert "errors" in resp_all.json()

    # 4. Scan logs endpoint
    resp_scan = client.post("/api/v1/errors/scan-logs")
    assert resp_scan.status_code == 200
    assert resp_scan.json()["success"] is True
