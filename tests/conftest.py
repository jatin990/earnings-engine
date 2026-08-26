"""Global test configuration and speed optimizations for pytest."""
import os
import sqlite3
import pytest

from earnings_engine.config import Settings
from earnings_engine.data.migrations import apply_migrations


@pytest.fixture(autouse=True)
def force_local_sqlite_in_tests(monkeypatch, tmp_path):
    """Force local isolated SQLite and disable Turso Cloud WAN calls during test execution.
    
    This ensures tests run locally at in-memory speeds (< 1 second) rather than making
    remote WAN network round-trips over HTTPS to cloud databases, and prevents tests
    from polluting the production database.
    """
    monkeypatch.setenv("TURSO_DATABASE_URL", "")
    monkeypatch.setenv("TURSO_AUTH_TOKEN", "")
    test_db_file = f"test_suite_{os.getpid()}.sqlite3"
    monkeypatch.setenv("EARNINGS_ENGINE_DB_NAME", test_db_file)


from unittest.mock import MagicMock
import pandas as pd
import yfinance as yf
from earnings_engine.data.providers import provider_manager


@pytest.fixture(autouse=True)
def mock_external_network_in_tests(monkeypatch):
    """Prevent tests from making real network calls to Yahoo Finance or NSE."""
    dummy_ticker = MagicMock()
    dummy_ticker.fast_info = {"market_cap": 1000000.0, "last_price": 100.0, "year_high": 120.0, "year_low": 80.0}
    dummy_ticker.info = {"industry": "Software", "sector": "Technology"}
    dummy_ticker.calendar = None
    dummy_ticker.earnings_dates = None
    dummy_ticker.get_earnings_dates = MagicMock(return_value=pd.DataFrame())
    dummy_ticker.history = MagicMock(return_value=pd.DataFrame())
    dummy_ticker.news = []
    monkeypatch.setattr(yf, "Ticker", lambda *args, **kwargs: dummy_ticker)

    # Default dummy download if not overridden by test
    def dummy_download(*args, **kwargs):
        return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])

    monkeypatch.setattr(yf, "download", dummy_download)


from earnings_engine.config import Settings


@pytest.fixture
def temp_settings(tmp_path):
    """Provide isolated Settings object pointing to a temporary test directory."""
    s = Settings(
        data_dirs={
            "prices": tmp_path / "prices",
            "earnings": tmp_path / "earnings",
            "reports": tmp_path / "reports",
            "logs": tmp_path / "logs",
            "cache": tmp_path / "cache",
        }
    )
    s.ensure_dirs()
    return s

