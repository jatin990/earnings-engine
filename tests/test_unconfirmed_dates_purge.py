"""Tests for invalidation, purging, and provenance flagging of unconfirmed algorithmic dates."""

import pytest
import pandas as pd
from earnings_engine.config import Settings
from earnings_engine.data.earnings import (
    _connect,
    upcoming_earnings,
    purge_unconfirmed_future_dates,
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


def test_upcoming_earnings_prioritizes_confirmed_over_yfinance(test_settings):
    """Verify official filing precedence over yfinance and provenance metadata attribution."""
    today = pd.Timestamp.today().normalize()
    date_confirmed = (today + pd.Timedelta(days=5)).strftime("%Y-%m-%d")
    date_unconfirmed = (today + pd.Timedelta(days=12)).strftime("%Y-%m-%d")

    with _connect(test_settings) as conn:
        # 1. TCS.NS has both official NSE filing and an unconfirmed yfinance estimate
        conn.execute(
            """
            INSERT INTO earnings_history (
                ticker, earnings_date, source, exchange_source, confirmation_status, board_meeting_purpose, filing_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("TCS.NS", date_confirmed, "nse", "NSE", "CONFIRMED", "Financial Results (BM: Post)", "NSE-BM-TCS-01"),
        )
        conn.execute(
            """
            INSERT INTO earnings_history (
                ticker, earnings_date, source, exchange_source, confirmation_status
            ) VALUES (?, ?, ?, ?, ?)
            """,
            ("TCS.NS", date_unconfirmed, "yfinance", None, "UNCONFIRMED_ESTIMATE"),
        )

        # 2. INFY.NS has ONLY an unconfirmed yfinance estimate
        conn.execute(
            """
            INSERT INTO earnings_history (
                ticker, earnings_date, source, exchange_source, confirmation_status
            ) VALUES (?, ?, ?, ?, ?)
            """,
            ("INFY.NS", date_unconfirmed, "yfinance", None, "UNCONFIRMED_ESTIMATE"),
        )
        conn.commit()

    # Query upcoming earnings
    df = upcoming_earnings(["TCS.NS", "INFY.NS"], test_settings, days=30)
    assert not df.empty

    # TCS.NS must retain ONLY the confirmed NSE filing, dropping the unconfirmed estimate
    tcs_rows = df[df["ticker"] == "TCS.NS"]
    assert len(tcs_rows) == 1
    assert tcs_rows.iloc[0]["earnings_date"].strftime("%Y-%m-%d") == date_confirmed
    assert tcs_rows.iloc[0]["exchange_source"] == "NSE"
    assert tcs_rows.iloc[0]["confirmation_status"] == "CONFIRMED"
    assert "BM: Post" in tcs_rows.iloc[0]["board_meeting_purpose"]

    # INFY.NS has no official filing yet, so it is marked as TENTATIVE / UNCONFIRMED_ESTIMATE
    infy_rows = df[df["ticker"] == "INFY.NS"]
    assert len(infy_rows) == 1
    assert infy_rows.iloc[0]["confirmation_status"] in ("TENTATIVE", "UNCONFIRMED_ESTIMATE")


def test_upcoming_earnings_confirmed_only_filter(test_settings):
    """Verify confirmed_only=True excludes all unconfirmed algorithmic estimates."""
    today = pd.Timestamp.today().normalize()
    date_confirmed = (today + pd.Timedelta(days=5)).strftime("%Y-%m-%d")
    date_unconfirmed = (today + pd.Timedelta(days=10)).strftime("%Y-%m-%d")

    with _connect(test_settings) as conn:
        conn.execute(
            """
            INSERT INTO earnings_history (
                ticker, earnings_date, source, exchange_source, confirmation_status, board_meeting_purpose, filing_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("RELIANCE.NS", date_confirmed, "nse", "NSE", "CONFIRMED", "Financial Results", "NSE-BM-REL-01"),
        )
        conn.execute(
            """
            INSERT INTO earnings_history (
                ticker, earnings_date, source, exchange_source, confirmation_status
            ) VALUES (?, ?, ?, ?, ?)
            """,
            ("WIPRO.NS", date_unconfirmed, "yfinance", None, "UNCONFIRMED_ESTIMATE"),
        )
        conn.commit()

    df = upcoming_earnings(["RELIANCE.NS", "WIPRO.NS"], test_settings, days=30, confirmed_only=True)
    assert len(df) == 1
    assert df.iloc[0]["ticker"] == "RELIANCE.NS"
    assert df.iloc[0]["confirmation_status"] == "CONFIRMED"


def test_purge_unconfirmed_future_dates(test_settings):
    """Verify purge_unconfirmed_future_dates deletes speculative future estimates."""
    today = pd.Timestamp.today().normalize()
    past_date = (today - pd.Timedelta(days=90)).strftime("%Y-%m-%d")
    future_date = (today + pd.Timedelta(days=15)).strftime("%Y-%m-%d")

    with _connect(test_settings) as conn:
        # Past yfinance record with actual EPS (must be kept!)
        conn.execute(
            """
            INSERT INTO earnings_history (ticker, earnings_date, source, eps_reported)
            VALUES ('TCS.NS', ?, 'yfinance', 32.5)
            """,
            (past_date,),
        )
        # Speculative future yfinance record (must be purged!)
        conn.execute(
            """
            INSERT INTO earnings_history (ticker, earnings_date, source, confirmation_status)
            VALUES ('TCS.NS', ?, 'yfinance', 'UNCONFIRMED_ESTIMATE')
            """,
            (future_date,),
        )
        # Official upcoming record (must be kept!)
        conn.execute(
            """
            INSERT INTO earnings_history (ticker, earnings_date, source, exchange_source, confirmation_status)
            VALUES ('INFY.NS', ?, 'nse', 'NSE', 'CONFIRMED')
            """,
            (future_date,),
        )
        conn.commit()

    purged = purge_unconfirmed_future_dates(test_settings)
    assert purged >= 1

    with _connect(test_settings) as conn:
        # Past record kept
        past = conn.execute("SELECT * FROM earnings_history WHERE ticker = 'TCS.NS' AND earnings_date = ?", (past_date,)).fetchone()
        assert past is not None

        # Future unconfirmed yfinance purged
        fut_yfinance = conn.execute("SELECT * FROM earnings_history WHERE ticker = 'TCS.NS' AND earnings_date = ?", (future_date,)).fetchone()
        assert fut_yfinance is None

        # Official future filing kept
        fut_official = conn.execute("SELECT * FROM earnings_history WHERE ticker = 'INFY.NS' AND earnings_date = ?", (future_date,)).fetchone()
        assert fut_official is not None
