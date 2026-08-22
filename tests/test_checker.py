"""Tests for the report checker subworkflow."""

import pandas as pd
import pytest

from earnings_engine.config import Settings
from earnings_engine.data import prices as prices_mod
from earnings_engine.reports import checker as checker_mod
from earnings_engine.reports.checker import check_report_csv, check_report_frame


@pytest.fixture
def settings(tmp_path):
    s = Settings()
    s.data_dirs = {"prices": tmp_path / "prices", "earnings": tmp_path / "earnings"}
    s.ensure_dirs()
    return s


def _make_prices():
    """A small price frame with known values for recomputation checks."""
    return pd.DataFrame(
        {
            "open": [100, 101, 102, 103, 104, 105, 106, 107, 108, 109],
            "high": [101, 102, 103, 104, 105, 106, 107, 108, 109, 110],
            "low": [99, 100, 101, 102, 103, 104, 105, 106, 107, 108],
            "close": [100, 101, 102, 103, 104, 105, 106, 107, 108, 109],
            "volume": [1_000] * 10,
        },
        index=pd.date_range("2024-01-01", periods=10, freq="D"),
    )


def _make_earnings():
    return pd.DataFrame(
        {
            "earnings_date": pd.to_datetime(["2024-01-01", "2024-04-01", "2024-07-01"]),
            "surprise_pct": [20.0, 18.0, 2.0],
        }
    )


def _make_cached_metrics():
    """A ticker_metrics payload for the cache-verified fields."""
    return {
        "market_cap": 1_000_000_000,
        "current_price": 109.0,
        "week_change": 0.05,
        "pct_from_52w_high": 10.0,
        "pct_from_52w_low": 5.0,
        "week_high": 120.0,
        "week_low": 90.0,
    }


def test_check_report_frame_verifies_matching_fields(monkeypatch, settings):
    """Fields that match the cached/recomputed source are counted as verified."""
    prices = _make_prices()
    earnings = _make_earnings()
    cached = _make_cached_metrics()

    monkeypatch.setattr(checker_mod, "load_prices", lambda ticker, s: prices)
    monkeypatch.setattr(checker_mod, "load_earnings", lambda ticker, s: earnings)
    monkeypatch.setattr(prices_mod, "load_price_metrics", lambda ticker, settings: cached)

    # Build a report frame with values that match the cached + recomputed source.
    closes = prices["close"].astype(float)
    latest = float(closes.iloc[-1])
    prior_30 = float(closes.iloc[0])
    thirty_day = ((latest - prior_30) / prior_30) * 100
    prior_week = float(closes.iloc[-5])
    week_move = ((latest - prior_week) / prior_week) * 100
    week_high = float(closes.max())
    week_low = float(closes.min())

    df = pd.DataFrame([
        {
            "ticker": "AAA",
            "market_cap": cached["market_cap"],
            "current_price": cached["current_price"],
            "week_change": cached["week_change"],
            "pct_from_52w_high": cached["pct_from_52w_high"],
            "pct_from_52w_low": cached["pct_from_52w_low"],
            "week_high": cached["week_high"],
            "week_low": cached["week_low"],
            "thirty_day_return_pct": thirty_day,
            "earnings_week_move_pct": week_move,
            "next_resistance": week_high,
            "current_support": week_low,
            "prev_quarter_earnings_score": 6,
            "prev_3q_earnings_score": 8,
            "q1_earnings_score": 9,
            "q2_earnings_score": 9,
            "q3_earnings_score": 6,
            "eps_estimate": None,
            "eps_reported": None,
            "surprise_pct": 2.0,
        }
    ])

    result = check_report_frame(df, settings)
    assert result.inconsistencies == []
    assert result.verified > 0


def test_check_report_frame_detects_inconsistency(monkeypatch, settings):
    """A report value that differs from the source is flagged."""
    prices = _make_prices()
    earnings = _make_earnings()
    cached = _make_cached_metrics()

    monkeypatch.setattr(checker_mod, "load_prices", lambda ticker, s: prices)
    monkeypatch.setattr(checker_mod, "load_earnings", lambda ticker, s: earnings)
    monkeypatch.setattr(prices_mod, "load_price_metrics", lambda ticker, settings: cached)

    # Report says current_price is wrong (e.g. 50 instead of cached 109).
    df = pd.DataFrame([
        {
            "ticker": "AAA",
            "market_cap": cached["market_cap"],
            "current_price": 50.0,
            "week_change": cached["week_change"],
            "pct_from_52w_high": cached["pct_from_52w_high"],
            "pct_from_52w_low": cached["pct_from_52w_low"],
            "week_high": cached["week_high"],
            "week_low": cached["week_low"],
            "thirty_day_return_pct": None,
            "earnings_week_move_pct": None,
            "next_resistance": None,
            "current_support": None,
            "prev_quarter_earnings_score": None,
            "prev_3q_earnings_score": None,
            "q1_earnings_score": None,
            "q2_earnings_score": None,
            "q3_earnings_score": None,
            "eps_estimate": None,
            "eps_reported": None,
            "surprise_pct": None,
        }
    ])

    result = check_report_frame(df, settings)
    assert any(inc.field == "current_price" for inc in result.inconsistencies)


def test_check_report_frame_marks_unverified_when_cache_missing(monkeypatch, settings):
    """Cache-verified fields with no ticker_metrics row are marked unverified,
    not falsely flagged as inconsistencies."""
    prices = _make_prices()
    earnings = _make_earnings()

    monkeypatch.setattr(checker_mod, "load_prices", lambda ticker, s: prices)
    monkeypatch.setattr(checker_mod, "load_earnings", lambda ticker, s: earnings)
    monkeypatch.setattr(prices_mod, "load_price_metrics", lambda ticker, settings: None)

    df = pd.DataFrame([
        {
            "ticker": "AAA",
            "market_cap": 1_000_000_000,
            "current_price": 109.0,
            "week_change": 0.05,
            "pct_from_52w_high": 10.0,
            "pct_from_52w_low": 5.0,
            "week_high": 120.0,
            "week_low": 90.0,
            "thirty_day_return_pct": None,
            "earnings_week_move_pct": None,
            "next_resistance": None,
            "current_support": None,
            "prev_quarter_earnings_score": None,
            "prev_3q_earnings_score": None,
            "q1_earnings_score": None,
            "q2_earnings_score": None,
            "q3_earnings_score": None,
            "eps_estimate": None,
            "eps_reported": None,
            "surprise_pct": None,
        }
    ])

    result = check_report_frame(df, settings)
    # No cache -> cache-verified fields are unverified, not inconsistencies.
    assert result.unverified > 0
    assert not any(inc.field in ("current_price", "week_change", "week_high", "week_low")
                   for inc in result.inconsistencies)


def test_check_report_frame_recomputes_earnings_scores(monkeypatch, settings):
    """Earnings scores are recomputed from earnings_history (ALPHAGEO regression)."""
    prices = _make_prices()
    earnings = _make_earnings()  # surprises [20, 18, 2] -> scores [9, 9, 6]
    cached = _make_cached_metrics()

    monkeypatch.setattr(checker_mod, "load_prices", lambda ticker, s: prices)
    monkeypatch.setattr(checker_mod, "load_earnings", lambda ticker, s: earnings)
    monkeypatch.setattr(prices_mod, "load_price_metrics", lambda ticker, settings: cached)

    # Report has correct earnings scores; the checker must recompute them
    # (not flag "report has a value but the original source is empty").
    df = pd.DataFrame([
        {
            "ticker": "AAA",
            "market_cap": cached["market_cap"],
            "current_price": cached["current_price"],
            "week_change": cached["week_change"],
            "pct_from_52w_high": cached["pct_from_52w_high"],
            "pct_from_52w_low": cached["pct_from_52w_low"],
            "week_high": cached["week_high"],
            "week_low": cached["week_low"],
            "thirty_day_return_pct": None,
            "earnings_week_move_pct": None,
            "next_resistance": None,
            "current_support": None,
            "prev_quarter_earnings_score": 6,
            "prev_3q_earnings_score": 8,
            "q1_earnings_score": 9,
            "q2_earnings_score": 9,
            "q3_earnings_score": 6,
            "eps_estimate": None,
            "eps_reported": None,
            "surprise_pct": 2.0,
        }
    ])

    result = check_report_frame(df, settings)
    # No false "source empty" inconsistencies for the earnings score fields.
    assert not any(inc.field in ("prev_quarter_earnings_score", "prev_3q_earnings_score",
                                 "q1_earnings_score", "q2_earnings_score", "q3_earnings_score")
                   for inc in result.inconsistencies)


def test_check_report_csv_loads_and_checks(tmp_path, monkeypatch, settings):
    """check_report_csv reads a CSV and runs the checker."""
    prices = _make_prices()
    earnings = _make_earnings()
    cached = _make_cached_metrics()

    monkeypatch.setattr(checker_mod, "load_prices", lambda ticker, s: prices)
    monkeypatch.setattr(checker_mod, "load_earnings", lambda ticker, s: earnings)
    monkeypatch.setattr(prices_mod, "load_price_metrics", lambda ticker, settings: cached)

    csv_path = tmp_path / "report.csv"
    pd.DataFrame([
        {
            "ticker": "AAA",
            "market_cap": cached["market_cap"],
            "current_price": cached["current_price"],
            "week_change": cached["week_change"],
            "pct_from_52w_high": cached["pct_from_52w_high"],
            "pct_from_52w_low": cached["pct_from_52w_low"],
            "week_high": cached["week_high"],
            "week_low": cached["week_low"],
            "thirty_day_return_pct": None,
            "earnings_week_move_pct": None,
            "next_resistance": None,
            "current_support": None,
            "prev_quarter_earnings_score": None,
            "prev_3q_earnings_score": None,
            "q1_earnings_score": None,
            "q2_earnings_score": None,
            "q3_earnings_score": None,
            "eps_estimate": None,
            "eps_reported": None,
            "surprise_pct": None,
        }
    ]).to_csv(csv_path, index=False)

    result = check_report_csv(csv_path, settings)
    # current_price matches the cached value
    assert any(inc.field == "current_price" for inc in result.inconsistencies) is False
    assert result.verified > 0