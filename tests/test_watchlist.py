"""Tests for watchlist add/remove via the dashboard API."""

import pytest

from earnings_engine.api.dashboard_api import add_to_watchlist, get_watchlist, remove_from_watchlist
from earnings_engine.config import Settings


@pytest.fixture
def watchlist_settings(tmp_path):
    s = Settings()
    s.data_dirs = {"prices": tmp_path / "prices", "earnings": tmp_path / "earnings"}
    s.ensure_dirs()
    return s


def test_watchlist_add_then_remove_round_trip(watchlist_settings, monkeypatch):
    # Watchlists are SQLite-backed (data/watchlists.py); isolate the DB by
    # pointing the dashboard_api settings helper at the fixture's tmp dirs.
    monkeypatch.setattr("earnings_engine.api.dashboard_api._settings", lambda: watchlist_settings)
    add = add_to_watchlist("TEST.NS")
    assert add["success"] is True
    assert "TEST.NS" in get_watchlist()

    rem = remove_from_watchlist("TEST.NS")
    assert rem["success"] is True
    assert "TEST.NS" not in get_watchlist()


def test_watchlist_duplicate_add_is_rejected(watchlist_settings, monkeypatch):
    monkeypatch.setattr("earnings_engine.api.dashboard_api._settings", lambda: watchlist_settings)
    add_to_watchlist("DUP.NS")
    dup = add_to_watchlist("DUP.NS")
    assert dup["success"] is False
    assert "already" in (dup.get("error") or "").lower()


def test_watchlist_remove_missing_is_rejected(watchlist_settings, monkeypatch):
    monkeypatch.setattr("earnings_engine.api.dashboard_api._settings", lambda: watchlist_settings)
    bad = remove_from_watchlist("MISSING.NS")
    assert bad["success"] is False
    assert "not in" in (bad.get("error") or "").lower()