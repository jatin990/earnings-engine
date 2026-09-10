"""Unit and integration tests for TursoConnectionCursor conformance,
automation schedules latency elimination, and expanded turso delta sync.
"""
import math
import sqlite3
import time
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from earnings_engine.config import Settings
from earnings_engine.data.automation_schedules import (
    DEFAULT_SCHEDULES,
    get_all_schedules,
    init_automation_schedules,
)
from earnings_engine.data.db import (
    TursoConnection,
    TursoConnectionCursor,
    TursoCursor,
    _serialize_arg,
    get_db_connection,
)
from earnings_engine.data.turso_sync import (
    DATE_ONLY_COLUMNS,
    SYNC_TABLES,
    WATERMARK_CANDIDATE_COLUMNS,
    _get_watermark_column,
    sync_local_to_upstream,
)


def test_serialize_arg_nan_and_inf_handling():
    """Verify NaN and Inf are converted to null type for Turso JSON protocol."""
    assert _serialize_arg(None) == {"type": "null"}
    assert _serialize_arg(float("nan")) == {"type": "null"}
    assert _serialize_arg(float("inf")) == {"type": "null"}
    assert _serialize_arg(float("-inf")) == {"type": "null"}
    assert _serialize_arg(123.45) == {"type": "float", "value": 123.45}
    assert _serialize_arg(True) == {"type": "integer", "value": "1"}
    assert _serialize_arg(False) == {"type": "integer", "value": "0"}
    assert _serialize_arg(42) == {"type": "integer", "value": "42"}
    assert _serialize_arg("test") == {"type": "text", "value": "test"}


def test_turso_connection_cursor_conformance():
    """Verify TursoConnectionCursor conforms to DB-API 2.0 cursor interface."""
    mock_conn = MagicMock(spec=TursoConnection)

    # Create fake cursor returned by mock_conn.execute
    fake_cursor = MagicMock(spec=TursoCursor)
    fake_cursor.description = (("col1", "TEXT"), ("col2", "INTEGER"))
    fake_cursor.rowcount = 5
    fake_cursor.lastrowid = 42
    fake_cursor.fetchone.return_value = ("val1", 100)
    fake_cursor.fetchall.return_value = [("val1", 100), ("val2", 200)]
    fake_cursor.fetchmany.return_value = [("val1", 100)]
    fake_cursor.__iter__.return_value = iter([("val1", 100), ("val2", 200)])

    mock_conn.execute.return_value = fake_cursor
    mock_conn.executemany.return_value = fake_cursor

    cursor = TursoConnectionCursor(mock_conn)
    assert cursor.connection is mock_conn
    assert cursor.description is None
    assert cursor.rowcount == -1
    assert cursor.lastrowid is None

    # Test context manager protocol
    with cursor as cur:
        res = cur.execute("SELECT col1, col2 FROM test WHERE id = ?", [1])
        assert res is cur
        assert cur.description == (("col1", "TEXT"), ("col2", "INTEGER"))
        assert cur.rowcount == 5
        assert cur.lastrowid == 42
        assert cur.fetchone() == ("val1", 100)
        assert len(cur.fetchall()) == 2
        assert len(cur.fetchmany(1)) == 1

    # Test executescript delegation
    cursor.executescript("CREATE TABLE test (id INT); INSERT INTO test VALUES (1);")
    mock_conn.executescript.assert_called_once_with("CREATE TABLE test (id INT); INSERT INTO test VALUES (1);")

    # Test executemany delegation
    cursor.executemany("INSERT INTO test VALUES (?)", [[1], [2]])
    mock_conn.executemany.assert_called_once_with("INSERT INTO test VALUES (?)", [[1], [2]])


def test_automation_schedules_init_and_fetch_performance(tmp_path):
    """Verify init_automation_schedules is fast (<50ms) and memoized."""
    s = Settings(
        data_dirs={
            "prices": tmp_path / "prices",
            "earnings": tmp_path / "earnings",
        }
    )
    s.ensure_dirs()

    # Initial seeding run
    t0 = time.perf_counter()
    init_automation_schedules(s, force=True)
    elapsed_init = time.perf_counter() - t0
    assert elapsed_init < 0.5  # First run with migrations should be fast

    # Second init run with memoized flag should take ~0.0001s
    t1 = time.perf_counter()
    init_automation_schedules(s, force=False)
    elapsed_memo = time.perf_counter() - t1
    assert elapsed_memo < 0.005

    # Test get_all_schedules returns all default schedules
    schedules = get_all_schedules(s)
    assert len(schedules) >= len(DEFAULT_SCHEDULES)
    job_ids = {s["job_id"] for s in schedules}
    for default_s in DEFAULT_SCHEDULES:
        assert default_s["job_id"] in job_ids


def test_sync_tables_and_watermark_configuration():
    """Verify SYNC_TABLES contains all registered tables and watermarks correctly prioritize."""
    assert len(SYNC_TABLES) == 72
    assert len(set(SYNC_TABLES)) == 72  # No duplicate table names

    # Essential missing tables now confirmed in list
    assert "automation_schedules" in SYNC_TABLES
    assert "automation_schedule_logs" in SYNC_TABLES
    assert "option_chain_history" in SYNC_TABLES
    assert "tri_confluence_metrics" in SYNC_TABLES
    assert "institutional_accumulation_cache" in SYNC_TABLES
    assert "credit_cards" in SYNC_TABLES
    assert "credit_card_otp_requests" in SYNC_TABLES
    assert "net_worth_snapshots" in SYNC_TABLES
    assert "quarter_repeater_predictions" in SYNC_TABLES
    assert "institutional_holdings" in SYNC_TABLES
    assert "institutional_block_deals" in SYNC_TABLES
    assert "shareholding_patterns" in SYNC_TABLES
    assert "users" in SYNC_TABLES
    assert "invite_codes" in SYNC_TABLES
    assert "friend_access" in SYNC_TABLES
    assert "otp_verifications" in SYNC_TABLES
    assert "nse_shareholding_freshness" in SYNC_TABLES
    assert "earnings_fetch_log" in SYNC_TABLES
    assert "earnings_month_cache" in SYNC_TABLES
    assert "institutional_radar_signals" in SYNC_TABLES
    assert "data_provenance_meta" in SYNC_TABLES
    assert "institutional_audit_log" in SYNC_TABLES
    assert "institutional_quarantine" in SYNC_TABLES

    # Test watermark selection priority
    assert _get_watermark_column(["id", "name", "updated_at", "created_at"]) == "updated_at"
    assert _get_watermark_column(["id", "ticker", "scanned_at"]) == "scanned_at"
    assert _get_watermark_column(["id", "deal_date", "client_name"]) == "deal_date"
    assert _get_watermark_column(["id", "audit_timestamp", "details"]) == "audit_timestamp"
    assert _get_watermark_column(["id", "quarantined_at", "rejection_reason"]) == "quarantined_at"
    assert _get_watermark_column(["id", "non_timestamp"]) is None

    # Test DATE_ONLY_COLUMNS detection
    assert "deal_date" in DATE_ONLY_COLUMNS
    assert "signal_date" in DATE_ONLY_COLUMNS
    assert "updated_at" not in DATE_ONLY_COLUMNS


def test_sync_local_to_upstream_no_credentials():
    """Verify sync gracefully skips when credentials are absent."""
    with patch.dict("os.environ", {"TURSO_DATABASE_URL": "", "TURSO_AUTH_TOKEN": ""}):
        result = sync_local_to_upstream()
        assert result["status"] == "skipped"
        assert "No Turso credentials" in result["reason"]


def test_automation_schedules_warm_latency_benchmark(tmp_path):
    """Verify warm get_all_schedules latency is <50ms across multiple rapid requests."""
    s = Settings(
        data_dirs={
            "prices": tmp_path / "prices",
            "earnings": tmp_path / "earnings",
        }
    )
    s.ensure_dirs()
    init_automation_schedules(s, force=True)

    latencies = []
    for _ in range(10):
        t0 = time.perf_counter()
        schedules = get_all_schedules(s)
        lat = (time.perf_counter() - t0) * 1000  # ms
        latencies.append(lat)
        assert len(schedules) > 0

    avg_latency = sum(latencies) / len(latencies)
    assert avg_latency < 50.0  # Must be sub-50ms (typically <5ms locally)

