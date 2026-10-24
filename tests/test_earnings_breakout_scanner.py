"""Unit and edge-case tests for the Results Breakout Radar quantitative scanner."""
import sqlite3
from datetime import datetime

import pandas as pd
import pytest

from earnings_engine.config import Settings
from earnings_engine.data.earnings_breakout_scanner import (
    ARCHETYPE_METADATA,
    VALID_ARCHETYPES,
    get_results_breakout_candidates,
)
from earnings_engine.data.prices import _cache_path, clear_price_df_cache


@pytest.fixture
def settings(tmp_path):
    s = Settings()
    s.data_dirs = {"prices": tmp_path / "prices", "earnings": tmp_path / "earnings"}
    s.ensure_dirs()
    clear_price_df_cache()
    return s


def _seed_db(settings, events: list[dict]):
    """Seed price_history + earnings_history into isolated SQLite db."""
    clear_price_df_cache()
    db_file = _cache_path(settings)
    with sqlite3.connect(str(db_file)) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS price_history (
                ticker TEXT,
                date TEXT,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume INTEGER
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS earnings_history (
                ticker TEXT,
                earnings_date TEXT,
                source TEXT,
                surprise_pct REAL,
                eps_reported REAL,
                eps_estimate REAL
            )
            """
        )
        for ev in events:
            ticker = ev["ticker"]
            edate = ev["earnings_date"]
            conn.execute(
                """
                INSERT INTO earnings_history (ticker, earnings_date, source, surprise_pct, eps_reported, eps_estimate)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    ticker,
                    edate,
                    ev.get("source", "nse"),
                    ev.get("surprise_pct"),
                    ev.get("eps_reported"),
                    ev.get("eps_estimate"),
                ),
            )
            bars = ev.get("bars", [])
            for bar in bars:
                conn.execute(
                    """
                    INSERT INTO price_history (ticker, date, open, high, low, close, volume)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        ticker,
                        bar["date"],
                        bar.get("open", bar["close"]),
                        bar.get("high", bar["close"]),
                        bar.get("low", bar["close"]),
                        bar["close"],
                        bar.get("volume", 100000),
                    ),
                )
        conn.commit()


def test_empty_window(settings):
    """When DB has no earnings events, returns structured empty payload without error."""
    now = datetime(2026, 5, 20, 16, 0)
    res = get_results_breakout_candidates(settings=settings, past_days=3, future_days=7, now=now)
    assert res["status"] == "ok"
    assert res["total_candidates"] == 0
    assert res["items"] == []
    assert res["summary"]["declared_count"] == 0
    assert res["summary"]["upcoming_count"] == 0


def test_declared_rdh_expansion(settings):
    """Stock declared 1 day ago. Current price breaches RDH with volume surge."""
    now = datetime(2026, 5, 20, 16, 0)  # Today: 2026-05-20
    # Declared on 2026-05-19.
    # Pre-close on 05-18 = 1000.
    # On 05-19: Open 1020, High 1050 (RDH), Low 1010, Close 1040.
    # On 05-20: Open 1045, High 1060, Low 1040, Close 1055 (above RDH 1050), volume surge 2.5x
    dates = pd.date_range("2026-04-15", "2026-05-20", freq="B")
    bars = []
    for d in dates:
        d_str = d.strftime("%Y-%m-%d")
        if d_str == "2026-05-18":
            bars.append({"date": d_str, "open": 995, "high": 1005, "low": 990, "close": 1000, "volume": 50000})
        elif d_str == "2026-05-19":
            bars.append({"date": d_str, "open": 1020, "high": 1050, "low": 1010, "close": 1040, "volume": 80000})
        elif d_str == "2026-05-20":
            bars.append({"date": d_str, "open": 1045, "high": 1060, "low": 1040, "close": 1055, "volume": 150000})
        else:
            bars.append({"date": d_str, "open": 980, "high": 1000, "low": 970, "close": 990, "volume": 50000})

    _seed_db(
        settings,
        [
            {
                "ticker": "TECHM.NS",
                "earnings_date": "2026-05-19",
                "surprise_pct": 8.5,
                "eps_reported": 18.5,
                "eps_estimate": 17.0,
                "bars": bars,
            }
        ],
    )

    res = get_results_breakout_candidates(settings=settings, past_days=3, future_days=7, now=now)
    assert res["total_candidates"] == 1
    item = res["items"][0]
    assert item["ticker"] == "TECHM.NS"
    assert item["symbol"] == "TECHM"
    assert item["archetype"] == "RDH_EXPANSION"
    assert item["is_declared"] is True
    assert item["is_breaking_out"] is True
    assert item["result_structure"]["result_day_high"] == 1050.0
    assert item["current_price"] == 1055.0
    assert item["composite_score"] >= 60
    assert item["tier"] == "HOT"
    assert item["trade_levels"]["target_price"] > item["trade_levels"]["ideal_entry"]
    assert item["trade_levels"]["stop_loss"] < item["trade_levels"]["ideal_entry"]
    assert item["target_1"] == item["trade_levels"]["target_1"]
    assert item["target_2"] == item["trade_levels"]["target_2"]
    assert item["breakout_trigger"] == item["trade_levels"]["breakout_trigger"]
    assert "volume_polarity" in item
    assert item["volume_polarity"] in ["BULLISH", "BEARISH", "NEUTRAL"]
    assert item["is_fno"] is True
    assert "volume_polarity" in item["technicals"]
    assert "vol_badge_label" in item["technicals"]
    assert "vol_badge_color" in item["technicals"]


def test_upcoming_pre_earnings_coil(settings):
    """Stock reporting in 4 days (+4D), consolidating tightly near resistance with low ATR."""
    now = datetime(2026, 5, 20, 16, 0)
    # Earnings date: 2026-05-24 (+4 days)
    dates = pd.date_range("2026-04-15", "2026-05-20", freq="B")
    bars = []
    for d in dates:
        d_str = d.strftime("%Y-%m-%d")
        # Steady uptrend reaching resistance 500
        bars.append({"date": d_str, "open": 490, "high": 500, "low": 488, "close": 495, "volume": 60000})

    _seed_db(
        settings,
        [
            {
                "ticker": "COIL.NS",
                "earnings_date": "2026-05-24",
                "bars": bars,
            }
        ],
    )

    res = get_results_breakout_candidates(settings=settings, past_days=3, future_days=7, now=now)
    assert res["total_candidates"] == 1
    item = res["items"][0]
    assert item["ticker"] == "COIL.NS"
    assert item["archetype"] == "PRE_EARNINGS_COIL"
    assert item["is_declared"] is False
    assert item["timing_status"] == "UPCOMING"
    assert item["days_relative"] == 4
    assert item["breakout_trigger"] == 500.0


def test_post_result_recovery(settings):
    """Stock gap down -3.0% on result day, then recovered back above pre-result close."""
    now = datetime(2026, 5, 20, 16, 0)
    dates = pd.date_range("2026-04-15", "2026-05-20", freq="B")
    bars = []
    for d in dates:
        d_str = d.strftime("%Y-%m-%d")
        if d_str == "2026-05-18":
            # Pre-result close: 200
            bars.append({"date": d_str, "open": 198, "high": 202, "low": 197, "close": 200, "volume": 100000})
        elif d_str == "2026-05-19":
            # Result day: Knee-jerk gap down to 194 (-3%), intraday low 192, closes at 197
            bars.append({"date": d_str, "open": 194, "high": 198, "low": 192, "close": 197, "volume": 200000})
        elif d_str == "2026-05-20":
            # Dip absorbed, reclaims pre-close 200, closes at 203
            bars.append({"date": d_str, "open": 198, "high": 204, "low": 197, "close": 203, "volume": 250000})
        else:
            bars.append({"date": d_str, "open": 195, "high": 200, "low": 194, "close": 198, "volume": 100000})

    _seed_db(
        settings,
        [
            {
                "ticker": "RECOV.NS",
                "earnings_date": "2026-05-19",
                "surprise_pct": -1.0,
                "bars": bars,
            }
        ],
    )

    res = get_results_breakout_candidates(settings=settings, past_days=3, future_days=7, now=now)
    assert res["total_candidates"] == 1
    item = res["items"][0]
    assert item["ticker"] == "RECOV.NS"
    assert item["archetype"] == "POST_RESULT_RECOVERY"
    assert item["result_structure"]["reaction_day_gap_pct"] == -3.0
    assert item["current_price"] >= item["result_structure"]["pre_result_close"]
    assert item["breakout_trigger"] == 200.0


def test_pead_momentum(settings):
    """Strong positive surprise with continuation drift above reaction candle."""
    now = datetime(2026, 5, 20, 16, 0)
    dates = pd.date_range("2026-04-15", "2026-05-20", freq="B")
    bars = []
    for d in dates:
        d_str = d.strftime("%Y-%m-%d")
        if d_str == "2026-05-18":
            # Pre-result close: 100
            bars.append({"date": d_str, "open": 98, "high": 101, "low": 98, "close": 100, "volume": 80000})
        elif d_str == "2026-05-19":
            # Reaction day: +6% return
            bars.append({"date": d_str, "open": 102, "high": 110, "low": 101, "close": 106, "volume": 300000})
        elif d_str == "2026-05-20":
            # Holding reaction gains, trading at 104 (within range)
            bars.append({"date": d_str, "open": 106, "high": 107, "low": 103, "close": 104, "volume": 150000})
        else:
            bars.append({"date": d_str, "open": 95, "high": 100, "low": 94, "close": 98, "volume": 80000})

    _seed_db(
        settings,
        [
            {
                "ticker": "PEAD.NS",
                "earnings_date": "2026-05-19",
                "surprise_pct": 12.0,
                "bars": bars,
            }
        ],
    )

    res = get_results_breakout_candidates(settings=settings, past_days=3, future_days=7, now=now)
    assert res["total_candidates"] == 1
    item = res["items"][0]
    assert item["ticker"] == "PEAD.NS"
    assert item["archetype"] in ("PEAD_MOMENTUM", "RDH_EXPANSION")
    assert item["result_structure"]["reaction_day_return_pct"] == 6.0


def test_insufficient_bars_edge_case(settings):
    """Stock with only 3 bars of price history handles SMA/ATR calculation safely."""
    now = datetime(2026, 5, 20, 16, 0)
    bars = [
        {"date": "2026-05-18", "open": 50, "high": 52, "low": 49, "close": 50, "volume": 1000},
        {"date": "2026-05-19", "open": 50, "high": 55, "low": 50, "close": 54, "volume": 2000},
        {"date": "2026-05-20", "open": 54, "high": 56, "low": 53, "close": 55, "volume": 3000},
    ]
    _seed_db(
        settings,
        [
            {
                "ticker": "NEWCO.NS",
                "earnings_date": "2026-05-19",
                "bars": bars,
            }
        ],
    )

    # Must complete without unhandled exception or NaN in critical fields
    res = get_results_breakout_candidates(settings=settings, past_days=3, future_days=7, min_score=0, now=now)
    assert res["status"] == "ok"
    assert res["total_candidates"] == 1
    item = res["items"][0]
    assert item["ticker"] == "NEWCO.NS"
    assert item["current_price"] == 55.0
    assert item["technicals"]["atr_val"] is not None
    assert item["trade_levels"]["target_price"] is not None
    # Dual-key aliases and native types
    assert item["days_since_result"] == item["days_relative"]
    assert item["breakout_trigger"] == item["trade_levels"]["breakout_trigger"]
    assert item["pct_from_trigger"] == item["trade_levels"]["dist_to_trigger_pct"]
    assert item["target_1"] == item["trade_levels"]["target_1"]
    assert item["target_2"] == item["trade_levels"]["target_2"]
    assert item["stop_loss"] == item["trade_levels"]["stop_loss"]
    assert isinstance(item["composite_score"], int)
    assert isinstance(item["current_price"], float)
