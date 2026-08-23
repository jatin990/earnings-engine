"""Tests for the Playground API console + the two bug fixes (ZOMATO timezone, Swing next-earnings)."""

from __future__ import annotations

import pandas as pd
import pytest

from earnings_engine.api.playground_api import get_endpoint_catalog, search_symbols


# ---------------------------------------------------------------------------
# Endpoint catalog
# ---------------------------------------------------------------------------

def test_endpoint_catalog_has_all_groups():
    catalog = get_endpoint_catalog()
    groups = {e["group"] for e in catalog}
    assert {"Market Data", "NSE", "yfinance", "Kronos"} <= groups
    # Every entry has the required keys
    for e in catalog:
        assert {"id", "group", "method", "path", "params", "description"} <= set(e)


def test_endpoint_catalog_includes_kronos_raw():
    catalog = get_endpoint_catalog()
    kronos = [e for e in catalog if e["group"] == "Kronos"]
    ids = {e["id"] for e in kronos}
    assert {"kronos_run", "kronos_latest", "kronos_audit", "kronos_history"} <= ids


def test_endpoint_catalog_includes_nse_calendar():
    catalog = get_endpoint_catalog()
    nse = [e for e in catalog if e["group"] == "NSE"]
    ids = {e["id"] for e in nse}
    assert {"nse_result_calendar", "nse_event_calendar", "nse_financial_calendar"} <= ids


def test_endpoint_catalog_nse_group_has_endpoints_for_dropdown():
    """Regression: the NSE group must have endpoints so the Playground 2nd
    dropdown (pgEndpoint) is populated when NSE is selected."""
    catalog = get_endpoint_catalog()
    nse = [e for e in catalog if e["group"] == "NSE"]
    # The NSE group must not be empty — otherwise the endpoint dropdown is blank.
    assert len(nse) >= 7
    ids = {e["id"] for e in nse}
    assert {
        "universe", "universe_files", "market_caps", "nse_universe_info",
        "nse_result_calendar", "nse_event_calendar", "nse_financial_calendar",
    } <= ids
    # Every NSE entry has a method + path so the dropdown shows a label.
    for e in nse:
        assert e["method"] in {"GET", "POST"}
        assert e["path"].startswith("/api/v1/")


# ---------------------------------------------------------------------------
# NSE financial calendar / result dates
# ---------------------------------------------------------------------------

def test_get_financial_calendar_normalizes_result_dates(monkeypatch):
    from earnings_engine.data import nse_api

    # Mock the raw NSE result-calendar payload.
    monkeypatch.setattr(
        nse_api,
        "fetch_result_calendar",
        lambda from_date=None, to_date=None: [
            {"symbol": "ZOMATO", "companyName": "Zomato Ltd", "resultDate": "05-08-2026"},
            {"symbol": "RELIANCE", "companyName": "Reliance Industries", "resultDate": "12-08-2026"},
        ],
    )
    result = nse_api.get_financial_calendar("ZOMATO.NS")
    assert result["symbol"] == "ZOMATO.NS"
    assert len(result["result_dates"]) == 1
    assert result["result_dates"][0]["symbol"] == "ZOMATO"
    assert result["result_dates"][0]["result_date"] == "05-08-2026"
    # Raw payload kept separate from normalized result_dates.
    assert "raw" in result
    assert len(result["raw"]) == 2


def test_get_financial_calendar_returns_error_on_failure(monkeypatch):
    from earnings_engine.data import nse_api

    monkeypatch.setattr(
        nse_api,
        "fetch_result_calendar",
        lambda from_date=None, to_date=None: {"error": "NSE blocked the request"},
    )
    result = nse_api.get_financial_calendar("RELIANCE.NS")
    assert result["symbol"] == "RELIANCE.NS"
    assert "error" in result
    assert "NSE blocked" in result["error"]


# ---------------------------------------------------------------------------
# Symbol search (autocomplete) — ZOMATO.NS must be selectable
# ---------------------------------------------------------------------------

def test_search_symbols_returns_typed_symbol_fallback(monkeypatch):
    # Simulate a stale NSE universe that misses ZOMATO.NS entirely.
    # (load_nse_all / load_universe are imported inside search_symbols, so
    # patch them at their source module.)
    monkeypatch.setattr(
        "earnings_engine.data.universe.load_nse_all",
        lambda force_refresh=False: [],
    )
    monkeypatch.setattr(
        "earnings_engine.data.universe.load_universe",
        lambda market: [],
    )
    results = search_symbols("ZOMATO")
    symbols = {r["symbol"] for r in results}
    # The typed symbol and its NSE variant must both be offered.
    assert "ZOMATO" in symbols
    assert "ZOMATO.NS" in symbols
    nse = [r for r in results if r["symbol"] == "ZOMATO.NS"]
    assert nse and nse[0]["market"] == "NSE"


def test_search_symbols_empty_query():
    assert search_symbols("") == []


# ---------------------------------------------------------------------------
# Swing next-earnings fix (regression)
# ---------------------------------------------------------------------------

def test_get_swing_setups_populates_earnings_date(monkeypatch):
    from earnings_engine.api import dashboard_api

    # Force a small universe so the loop runs fast.
    monkeypatch.setattr(
        "earnings_engine.api.dashboard_api._resolve_tickers",
        lambda market: ["RELIANCE.NS"],
    )
    # Provide an upcoming earnings event in the cache.
    upcoming_df = pd.DataFrame({
        "ticker": ["RELIANCE.NS"],
        "earnings_date": [pd.Timestamp("2026-09-01")],
    })
    monkeypatch.setattr(
        "earnings_engine.api.dashboard_api.earnings_mod.upcoming_earnings",
        lambda tickers, settings, days: upcoming_df,
    )
    # enrich_upcoming_results returns a minimal frame (no earnings_date).
    monkeypatch.setattr(
        "earnings_engine.api.dashboard_api.enrich_upcoming_results",
        lambda df, settings: pd.DataFrame({
            "ticker": ["RELIANCE.NS"],
            "thirty_day_return_pct": [5.0],
            "current_support": [100.0],
            "next_resistance": [120.0],
        }),
    )
    monkeypatch.setattr(
        "earnings_engine.api.dashboard_api.swing_ranges_mod.list_ranges",
        lambda watchlist=None, settings=None: [],
    )
    monkeypatch.setattr(
        "earnings_engine.api.dashboard_api.swing_ranges_mod.get_swing_range",
        lambda wl, ticker, settings=None: None,
    )

    rows = dashboard_api.get_swing_setups(market="IN", limit=1)
    assert len(rows) == 1
    # The bug: earnings_date was always None. Now it must be populated.
    assert rows[0]["earnings_date"] == "2026-09-01"
    assert rows[0]["swing_signal"] in ("Strong Buy", "Buy", "Neutral")


# ---------------------------------------------------------------------------
# Kronos fetch_historical_data timezone-warning retry (regression)
# ---------------------------------------------------------------------------

def test_fetch_historical_data_retries_on_timezone_warning(monkeypatch):
    from earnings_engine import kronos_predictor

    calls = {"n": 0}

    def fake_history(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise Exception("possibly delisted; no timezone found")
        # Second call returns a valid frame.
        idx = pd.date_range(end=pd.Timestamp.now(), periods=70, freq="D")
        return pd.DataFrame({
            "Open": [100.0] * 70,
            "High": [101.0] * 70,
            "Low": [99.0] * 70,
            "Close": [100.5] * 70,
            "Volume": [1000] * 70,
        }, index=idx)

    monkeypatch.setattr(kronos_predictor.yf, "Ticker", lambda symbol: type("T", (), {"history": fake_history})())
    # Prevent yf.download fallback from being reached.
    monkeypatch.setattr(kronos_predictor.yf, "download", lambda *a, **k: pd.DataFrame())

    df = kronos_predictor.fetch_historical_data("ZOMATO.NS")
    assert calls["n"] >= 2  # retried after the timezone warning
    assert len(df) >= 60
    assert {"timestamps", "open", "high", "low", "close", "volume"} <= set(df.columns)


# ---------------------------------------------------------------------------
# _resolve_tickers casing regression (custom watchlist names)
# ---------------------------------------------------------------------------

def test_resolve_tickers_preserves_original_casing_for_db_watchlist(monkeypatch):
    """Custom watchlist names with mixed/lower case must be looked up in the
    DB using their original casing — not uppercased — so e.g. 'My Picks'
    resolves the DB row 'My Picks' instead of returning empty for 'MY PICKS'."""
    from earnings_engine.api import dashboard_api
    from earnings_engine.data import watchlists as watchlists_mod

    original_get_watchlist = watchlists_mod.get_watchlist

    call_log = []

    def fake_get_watchlist(name, settings=None):
        call_log.append(name)
        # Return tickers only when called with the original (non-uppercased) name
        if name == "My Picks":
            return ["RELIANCE.NS", "TCS.NS"]
        if name == "MY PICKS":
            return []  # uppercased — should not be reached first
        return original_get_watchlist(name, settings)

    monkeypatch.setattr(watchlists_mod, "get_watchlist", fake_get_watchlist)
    # Avoid file-system fallback
    monkeypatch.setattr(dashboard_api.Path, "exists", lambda self: False)

    tickers = dashboard_api._resolve_tickers("My Picks")

    assert len(call_log) >= 1, "get_watchlist must have been called"
    assert call_log[0] == "My Picks", (
        f"First get_watchlist call should use the original casing 'My Picks', "
        f"got {call_log[0]!r}"
    )
    assert tickers == ["RELIANCE.NS", "TCS.NS"], (
        f"Expected watchlist tickers, got {tickers}"
    )


def test_resolve_tickers_falls_back_to_uppercase_casing(monkeypatch):
    """When the original-case DB lookup returns empty, the function must fall
    back to uppercase for legacy universe-file compatibility."""
    from earnings_engine.api import dashboard_api
    from earnings_engine.data import watchlists as watchlists_mod

    call_log = []

    def fake_get_watchlist(name, settings=None):
        call_log.append(name)
        return []  # always empty — force fallback to file lookup

    monkeypatch.setattr(watchlists_mod, "get_watchlist", fake_get_watchlist)

    # Patch load_universe_from_file to capture which file path was tried
    load_calls = []

    def fake_load_from_file(path):
        load_calls.append(str(path))
        return ["RELIANCE.NS", "TCS.NS"]

    monkeypatch.setattr(dashboard_api, "load_universe_from_file", fake_load_from_file)

    # Patch Path.exists so the original-case file doesn't exist but the
    # uppercase one does.
    original_exists = dashboard_api.Path.exists

    def fake_exists(self):
        path_str = str(self)
        # The original-case file "my_watchlist.txt" should NOT exist
        if path_str.endswith("my_watchlist.txt"):
            return False
        # The uppercase file "MY_WATCHLIST.txt" should exist
        if path_str.endswith("MY_WATCHLIST.txt"):
            return True
        return original_exists(self)

    monkeypatch.setattr(dashboard_api.Path, "exists", fake_exists)

    tickers = dashboard_api._resolve_tickers("my_watchlist")

    # Verify: first DB call was with original case
    assert call_log[0] == "my_watchlist", (
        f"First call should be original case 'my_watchlist', got {call_log[0]!r}"
    )
    # Verify it tried the uppercase fallback
    assert "MY_WATCHLIST" in call_log, f"Should have tried uppercase, got {call_log}"
    # Verify the uppercase file was loaded
    assert any("MY_WATCHLIST.txt" in p for p in load_calls), (
        f"Should have loaded uppercase file, got: {load_calls}"
    )
    assert tickers == ["RELIANCE.NS", "TCS.NS"], (
        f"Expected tickers from uppercase file, got {tickers}"
    )