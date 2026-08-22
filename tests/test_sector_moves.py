"""Tests for the Industries tab: recent-earnings moves grouped by industry."""

import sqlite3

import pandas as pd
import pytest

from earnings_engine.config import Settings
from earnings_engine.data.market_context import _week_high_low_around
from earnings_engine.data.sector_moves import (
    get_recent_earnings_moves,
    group_by_industry,
    pick_best_industry,
)


@pytest.fixture
def settings(tmp_path):
    s = Settings()
    s.data_dirs = {"prices": tmp_path / "prices", "earnings": tmp_path / "earnings"}
    s.ensure_dirs()
    return s


def _db_path(settings):
    from earnings_engine.data.prices import _cache_path
    return _cache_path(settings)


def test_week_high_low_around_uses_7_trading_days_after():
    """The helper must measure high/low over the 7 trading days AFTER the result."""
    dates = pd.bdate_range("2026-01-01", periods=20)
    closes = pd.Series(
        [100, 102, 101, 103, 104, 102, 99, 101, 105, 110,
         108, 106, 112, 111, 109, 107, 113, 115, 114, 112],
        index=dates,
        name="close",
    )
    prices = closes.to_frame()
    earnings_date = dates[9]  # base close = closes[8] (104)
    result = _week_high_low_around(prices, earnings_date)
    assert result is not None
    high_pct, low_pct, high_price, low_price, high_date, low_date = result
    base = float(closes.iloc[8])        # last close strictly before earnings_date
    window = closes.iloc[10:17]         # exactly the 7 trading days after earnings
    assert high_price == float(window.max())
    assert low_price == float(window.min())
    assert high_pct == pytest.approx((float(window.max()) / base - 1.0) * 100)
    assert low_pct == pytest.approx((float(window.min()) / base - 1.0) * 100)


def test_week_high_low_around_returns_none_without_prior_close():
    """No close before the earnings date -> None (can't establish a base)."""
    closes = pd.Series([100.0], index=pd.DatetimeIndex(["2026-01-10"]), name="close")
    prices = closes.to_frame()
    assert _week_high_low_around(prices, pd.Timestamp("2026-01-05")) is None


def _seed_moves_db(settings):
    conn = sqlite3.connect(str(_db_path(settings)))
    conn.execute(
        "CREATE TABLE IF NOT EXISTS price_history (ticker TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL, volume INTEGER)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS earnings_history (ticker TEXT, earnings_date TEXT, eps_estimate REAL, eps_reported REAL, surprise_pct REAL, source TEXT)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS ticker_industry (ticker TEXT, industry TEXT, sector TEXT, fetched_at TEXT)"
    )
    today = pd.Timestamp.today().normalize()
    dates = pd.bdate_range(end=today, periods=20)
    for ticker in ["A.NS", "B.NS"]:
        for i, d in enumerate(dates):
            conn.execute(
                "INSERT INTO price_history (ticker, date, close) VALUES (?, ?, ?)",
                (ticker, d.strftime("%Y-%m-%d"), 100 + i),
            )
        res_date = (today - pd.Timedelta(days=10)).strftime("%Y-%m-%d")
        conn.execute(
            "INSERT INTO earnings_history (ticker, earnings_date, source) VALUES (?, ?, 'yfinance')",
            (ticker, res_date),
        )
        conn.execute(
            "INSERT INTO ticker_industry (ticker, industry) VALUES (?, ?)",
            (ticker, "Banks" if ticker == "A.NS" else "IT"),
        )
    conn.commit()
    conn.close()


def test_get_recent_earnings_moves_from_cache(settings):
    _seed_moves_db(settings)
    moves = get_recent_earnings_moves(["A.NS", "B.NS"], settings, lookback_days=60)
    assert len(moves) == 2
    for m in moves:
        assert m["high_pct"] is not None
        assert m["high_pct"] > 0  # monotonically rising closes


def test_get_recent_earnings_moves_empty_without_events(settings):
    _seed_moves_db(settings)
    # A ticker with no earnings in the window.
    moves = get_recent_earnings_moves(["ZZZ.NS"], settings, lookback_days=60)
    assert moves == []


# ---------------------------------------------------------------------------
# Grouping + best-industry selection
# ---------------------------------------------------------------------------

def test_group_by_industry_sorts_best_to_worst():
    moves = [
        {"ticker": "A.NS", "high_pct": 3.0, "low_pct": -1.0},
        {"ticker": "B.NS", "high_pct": 5.0, "low_pct": -2.0},
        {"ticker": "C.NS", "high_pct": 1.0, "low_pct": -3.0},
        {"ticker": "D.NS", "high_pct": None, "low_pct": None},
    ]
    industry_map = {"A.NS": "Banks", "B.NS": "Banks", "C.NS": "IT", "D.NS": "IT"}
    groups = group_by_industry(moves, industry_map)
    by_ind = {g["industry"]: g for g in groups}
    assert by_ind["Banks"]["positive_count"] == 2
    assert [r["ticker"] for r in by_ind["Banks"]["rows"]] == ["B.NS", "A.NS"]
    # None sorts last within IT.
    assert [r["ticker"] for r in by_ind["IT"]["rows"]] == ["C.NS", "D.NS"]
    assert by_ind["IT"]["positive_count"] == 1


def test_group_by_industry_falls_back_to_other():
    moves = [{"ticker": "X.NS", "high_pct": 2.0, "low_pct": -1.0}]
    groups = group_by_industry(moves, {})  # no industry map -> "Other"
    assert groups[0]["industry"] == "Other"


def test_pick_best_industry_most_positive():
    groups = [
        {"industry": "IT", "positive_count": 1, "avg_high_pct": 9.0},
        {"industry": "Banks", "positive_count": 3, "avg_high_pct": 1.0},
    ]
    assert pick_best_industry(groups)["industry"] == "Banks"


def test_pick_best_industry_empty():
    assert pick_best_industry([]) is None


# ---------------------------------------------------------------------------
# API endpoint
# ---------------------------------------------------------------------------

def test_industries_api_endpoint(settings, monkeypatch):
    _seed_moves_db(settings)
    from fastapi.testclient import TestClient
    from earnings_engine.api.server import app
    from earnings_engine.api import dashboard_api

    monkeypatch.setattr(dashboard_api, "_settings", lambda: settings)
    monkeypatch.setattr(dashboard_api, "_resolve_tickers", lambda market: ["A.NS", "B.NS"])

    client = TestClient(app)
    resp = client.get("/api/v1/dashboard/industries?market=WATCHLIST&lookback_days=60")
    assert resp.status_code == 200
    data = resp.json()
    assert "industries" in data
    assert "best_industry" in data
    assert data["total_results"] == 2
    assert data["best_industry"] in {"Banks", "IT"}
    for g in data["industries"]:
        assert "industry" in g
        assert "rows" in g

