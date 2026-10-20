"""Tests for multi-exchange BSE corporate filings reconciliation and conflict resolution."""

import pytest
from unittest.mock import patch
import pandas as pd
from earnings_engine.config import Settings
from earnings_engine.data.earnings import (
    _connect,
    ingest_bse_result_calendar,
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
    apply_migrations(s, force=True)
    return s


def test_bse_calendar_ingestion_and_nse_precedence(test_settings):
    """Verify BSE ingestion, filtering, and NSE precedence for dual-listed stocks."""
    today_str = pd.Timestamp.today().normalize().strftime("%Y-%m-%d")
    future_date_nse = (pd.Timestamp.today() + pd.Timedelta(days=5)).strftime("%Y-%m-%d")
    future_date_bse_conflict = (pd.Timestamp.today() + pd.Timedelta(days=6)).strftime("%Y-%m-%d")
    future_date_bse_exclusive = (pd.Timestamp.today() + pd.Timedelta(days=7)).strftime("%Y-%m-%d")
    future_date_dual_new = (pd.Timestamp.today() + pd.Timedelta(days=8)).strftime("%Y-%m-%d")

    # Seed an authoritative NSE record for RELIANCE.NS
    with _connect(test_settings) as conn:
        conn.execute(
            """
            INSERT INTO earnings_history (
                ticker, earnings_date, source, exchange_source, confirmation_status, board_meeting_purpose, filing_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "RELIANCE.NS",
                future_date_nse,
                "nse",
                "NSE",
                "CONFIRMED",
                "Financial Results Q2 FY27",
                "NSE-BM-RELIANCE-01",
            ),
        )
        conn.commit()

    # Mock BSE feed returning:
    # 1. RELIANCE.NS (dual-listed, conflicting date -> must be ignored due to NSE precedence)
    # 2. LOTUSCHO.BO (BSE-exclusive -> must be ingested with exchange_source='BSE')
    # 3. TATAMOTORS.NS (dual-listed, but no prior NSE date -> must be ingested with exchange_source='BSE')
    # 4. EXCLUDED.BO (dividend only meeting -> must be rejected)
    mock_bse_events = [
        {
            "ticker": "RELIANCE.NS",
            "earnings_date": future_date_bse_conflict,
            "company_name": "Reliance Industries Limited",
            "market_cap": 2000000.0,
            "source": "bse",
            "purpose": "Financial Results",
        },
        {
            "ticker": "LOTUSCHO.BO",
            "earnings_date": future_date_bse_exclusive,
            "company_name": "Lotus Chocolate Company Ltd",
            "market_cap": 1500.0,
            "source": "bse",
            "purpose": "Audited Financial Results and Accounts",
        },
        {
            "ticker": "TATAMOTORS.NS",
            "earnings_date": future_date_dual_new,
            "company_name": "Tata Motors Ltd",
            "market_cap": 300000.0,
            "source": "bse",
            "purpose": "Quarterly Financial Results",
        },
        {
            "ticker": "EXCLUDED.BO",
            "earnings_date": future_date_bse_exclusive,
            "company_name": "Excluded Corp",
            "market_cap": 100.0,
            "source": "bse",
            "purpose": "To consider payment of interim dividend only",
        },
    ]

    with patch("earnings_engine.data.earnings.fetch_bse_result_calendar", return_value=mock_bse_events):
        summary = ingest_bse_result_calendar(test_settings)

    assert summary["inserted"] >= 2

    with _connect(test_settings) as conn:
        # 1. Verify RELIANCE.NS retained the authoritative NSE date and was not overwritten
        rel_row = conn.execute(
            "SELECT earnings_date, exchange_source, confirmation_status FROM earnings_history WHERE ticker = 'RELIANCE.NS'"
        ).fetchall()
        assert len(rel_row) == 1
        assert rel_row[0][0] == future_date_nse, "NSE date must be preserved for dual-listed ticker"
        assert rel_row[0][1] == "NSE"
        assert rel_row[0][2] == "CONFIRMED"

        # 2. Verify LOTUSCHO.BO was inserted with exchange_source='BSE'
        lotus_row = conn.execute(
            "SELECT earnings_date, exchange_source, confirmation_status, board_meeting_purpose FROM earnings_history WHERE ticker = 'LOTUSCHO.BO'"
        ).fetchone()
        assert lotus_row is not None
        assert lotus_row[0] == future_date_bse_exclusive
        assert lotus_row[1] == "BSE"
        assert lotus_row[2] == "CONFIRMED"

        # 3. Verify TATAMOTORS.NS was inserted with exchange_source='BSE' since no prior NSE date existed
        tata_row = conn.execute(
            "SELECT earnings_date, exchange_source, confirmation_status FROM earnings_history WHERE ticker = 'TATAMOTORS.NS'"
        ).fetchone()
        assert tata_row is not None
        assert tata_row[0] == future_date_dual_new
        assert tata_row[1] == "BSE"
        assert tata_row[2] == "CONFIRMED"

        # 4. Verify EXCLUDED.BO was rejected
        ex_row = conn.execute("SELECT * FROM earnings_history WHERE ticker = 'EXCLUDED.BO'").fetchone()
        assert ex_row is None
