"""Tests for official NSE financial results calendar ingestion and classification."""

import pytest
from unittest.mock import patch
import pandas as pd
from earnings_engine.config import Settings
from earnings_engine.data.earnings import (
    _connect,
    ingest_nse_result_calendar,
    classify_board_meeting_purpose,
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


def test_classify_board_meeting_purpose_strict():
    """Verify strict purpose keywords and rejection of non-results corporate actions."""
    # Rejections (non-results meetings)
    res_div = classify_board_meeting_purpose("To consider declaration of interim dividend only")
    assert not res_div["is_results"], "Dividend-only meeting should be rejected"

    res_qip = classify_board_meeting_purpose("Meeting of Board of Directors to consider Fund Raising via QIP")
    assert not res_qip["is_results"], "Fund raising meeting should be rejected"

    res_agm = classify_board_meeting_purpose("35th Annual General Meeting of the Company")
    assert not res_agm["is_results"], "AGM should be rejected"

    res_war = classify_board_meeting_purpose("Allotment of convertible warrants on preferential basis")
    assert not res_war["is_results"], "Warrants allotment should be rejected"

    # Acceptances
    res_fin = classify_board_meeting_purpose("Consider and approve Unaudited Financial Results for Q2")
    assert res_fin["is_results"], "Financial results must be accepted"

    res_combo = classify_board_meeting_purpose("To consider financial results and interim dividend")
    assert res_combo["is_results"], "Results + dividend combo must be accepted"

    res_aud = classify_board_meeting_purpose("Audited Financial Results for the quarter and year ended March 31")
    assert res_aud["is_results"], "Audited results must be accepted"


def test_classify_session_timing():
    """Verify session timing extraction (Pre-Market, During Market, Post-Market)."""
    # From explicit time
    t_pre = classify_board_meeting_purpose("Quarterly Financial Results", time_str="08:30")
    assert t_pre["session_timing"] == "BM: Pre"

    t_post = classify_board_meeting_purpose("Quarterly Financial Results", time_str="16:30")
    assert t_post["session_timing"] == "BM: Post"

    t_during = classify_board_meeting_purpose("Quarterly Financial Results", time_str="12:00")
    assert t_during["session_timing"] == "BM: During"

    # From purpose text
    t_text_post = classify_board_meeting_purpose("Financial Results (After Market Hours)")
    assert t_text_post["session_timing"] == "BM: Post"

    t_text_pre = classify_board_meeting_purpose("Financial Results (Pre-Market)")
    assert t_text_pre["session_timing"] == "BM: Pre"


def test_ingest_nse_calendar_provenance_and_supersede(test_settings):
    """Verify that official NSE ingestion populates provenance and handles rescheduling."""
    mock_payload = {
        "data": [
            {
                "symbol": "TCS",
                "purpose": "Financial Results for Q2 FY27 (Post-Market)",
                "bmDate": "2026-10-25",
                "id": "NSE-BM-20261025-001",
            },
            {
                "symbol": "INFY",
                "purpose": "To consider dividend payment only",
                "bmDate": "2026-10-24",
                "id": "NSE-BM-20261024-002",
            },
        ]
    }

    # First, seed an unconfirmed yfinance future date for TCS.NS to verify it gets purged
    with _connect(test_settings) as conn:
        conn.execute(
            """
            INSERT INTO earnings_history (ticker, earnings_date, source, confirmation_status)
            VALUES ('TCS.NS', '2026-10-30', 'yfinance', 'UNCONFIRMED_ESTIMATE')
            """
        )
        conn.commit()

    with patch("earnings_engine.data.earnings.fetch_event_calendar", return_value=mock_payload):
        summary = ingest_nse_result_calendar(test_settings)

    assert summary["inserted"] >= 1

    with _connect(test_settings) as conn:
        # INFY should NOT have been inserted (dividend only)
        infy_row = conn.execute("SELECT * FROM earnings_history WHERE ticker = 'INFY.NS'").fetchone()
        assert infy_row is None

        # TCS should have been inserted with verified metadata
        tcs_rows = conn.execute(
            """
            SELECT earnings_date, exchange_source, confirmation_status, board_meeting_purpose, filing_id
            FROM earnings_history
            WHERE ticker = 'TCS.NS'
            ORDER BY earnings_date
            """
        ).fetchall()

        assert len(tcs_rows) == 1
        tcs = tcs_rows[0]
        assert tcs[0] == "2026-10-25"
        assert tcs[1] == "NSE"
        assert tcs[2] == "CONFIRMED"
        assert "BM: Post" in tcs[3]
        assert tcs[4] == "NSE-BM-20261025-001"
