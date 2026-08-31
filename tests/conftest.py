"""Global test configuration and speed optimizations for pytest."""
import os
import sqlite3
import pytest

from earnings_engine.config import Settings
from earnings_engine.data.migrations import apply_migrations


from pathlib import Path

STATIC_TEST_DB = Path("data/cache/prices/test.sqlite3").resolve()

# Point environment to static test DB immediately at import time
os.environ["TURSO_DATABASE_URL"] = ""
os.environ["TURSO_AUTH_TOKEN"] = ""
os.environ["EARNINGS_ENGINE_DB_PATH"] = str(STATIC_TEST_DB)
os.environ["EARNINGS_ENGINE_DB_NAME"] = STATIC_TEST_DB.name

# One-time static setup: only runs if test.sqlite3 does NOT exist on disk
if not STATIC_TEST_DB.exists():
    STATIC_TEST_DB.parent.mkdir(parents=True, exist_ok=True)
    _conn = sqlite3.connect(str(STATIC_TEST_DB))
    try:
        _conn.execute("PRAGMA journal_mode=WAL;")
        _conn.execute("PRAGMA synchronous=NORMAL;")
    finally:
        _conn.close()
    try:
        apply_migrations(Settings())
    except Exception as e:
        print(f"[STATIC-TEST-DB] Error in one-time static setup: {e}")


@pytest.fixture(autouse=True)
def force_local_sqlite_in_tests(monkeypatch):
    """Ensure all tests reuse the same permanent static SQLite database."""
    monkeypatch.setenv("TURSO_DATABASE_URL", "")
    monkeypatch.setenv("TURSO_AUTH_TOKEN", "")
    monkeypatch.setenv("EARNINGS_ENGINE_DB_PATH", str(STATIC_TEST_DB))
    monkeypatch.setenv("EARNINGS_ENGINE_DB_NAME", STATIC_TEST_DB.name)


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

    def dummy_download(*args, **kwargs):
        return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])

    monkeypatch.setattr(yf, "download", dummy_download)

    try:
        from earnings_engine.data import news as news_mod
        monkeypatch.setattr(news_mod, "scan_watchlist_catalysts", lambda *args, **kwargs: [])
        monkeypatch.setattr(news_mod, "fetch_catalyst_news", lambda *args, **kwargs: [])
    except Exception:
        pass


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

