"""Tests for earnings_history filing provenance schema extensions."""

import pytest
import sqlite3
from earnings_engine.config import Settings
from earnings_engine.data.earnings import (
    _connect,
    ensure_earnings_history_schema,
    COLUMNS,
)
from earnings_engine.data.turso_sync import (
    SYNC_TABLES,
    WATERMARK_CANDIDATE_COLUMNS,
    DATE_ONLY_COLUMNS,
)
from earnings_engine.data.migrations import apply_migrations, reset_migration_cache


@pytest.fixture
def test_settings(tmp_path, monkeypatch):
    monkeypatch.delenv("TURSO_DATABASE_URL", raising=False)
    monkeypatch.delenv("TURSO_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("EARNINGS_ENGINE_DB_PATH", raising=False)
    monkeypatch.setenv("EARNINGS_ENGINE_DB_NAME", f"test_{tmp_path.name}.sqlite3")
    s = Settings()
    s.data_dirs["prices"] = tmp_path
    s.data_dirs["earnings"] = tmp_path
    s.ensure_dirs()
    reset_migration_cache()
    return s


def test_earnings_provenance_columns_exist(test_settings):
    apply_migrations(test_settings, force=True)

    with _connect(test_settings) as conn:
        cursor = conn.execute("PRAGMA table_info(earnings_history)")
        columns = {row[1]: row for row in cursor.fetchall()}

        # Verify new provenance columns exist
        assert "exchange_source" in columns, "exchange_source column missing"
        assert "confirmation_status" in columns, "confirmation_status column missing"
        assert "board_meeting_purpose" in columns, "board_meeting_purpose column missing"
        assert "filing_id" in columns, "filing_id column missing"

        # Insert a sample row with provenance metadata
        conn.execute(
            """
            INSERT INTO earnings_history (
                ticker, earnings_date, eps_estimate, eps_reported, surprise_pct, source,
                exchange_source, confirmation_status, board_meeting_purpose, filing_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "TCS.NS",
                "2026-10-15",
                12.5,
                13.1,
                4.8,
                "nse",
                "NSE",
                "CONFIRMED",
                "Financial Results for Q2 FY27",
                "NSE-BM-20261015-001",
            ),
        )
        conn.commit()

        row = conn.execute(
            "SELECT exchange_source, confirmation_status, board_meeting_purpose, filing_id FROM earnings_history WHERE ticker = 'TCS.NS'"
        ).fetchone()

        assert row[0] == "NSE"
        assert row[1] == "CONFIRMED"
        assert row[2] == "Financial Results for Q2 FY27"
        assert row[3] == "NSE-BM-20261015-001"


def test_earnings_history_in_turso_sync():
    """Verify that earnings_history is registered in the SYNC_TABLES contract."""
    assert "earnings_history" in SYNC_TABLES, "earnings_history must be in SYNC_TABLES"
    assert "earnings_date" in WATERMARK_CANDIDATE_COLUMNS, "earnings_date must be in WATERMARK_CANDIDATE_COLUMNS"
    assert "earnings_date" in DATE_ONLY_COLUMNS, "earnings_date must be in DATE_ONLY_COLUMNS"
