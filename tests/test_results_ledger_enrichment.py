"""Tests for upcoming earnings enrichment and technical setup classification."""

import numpy as np
import pandas as pd
import pytest

from earnings_engine.config import Settings
from earnings_engine.data.market_context import (
    classify_technical_setup,
    enrich_upcoming_results,
)


def test_classify_technical_setup_signatures_and_logic():
    """Verify classify_technical_setup works with keyword arguments and expected inputs."""
    setup = classify_technical_setup(
        current_price=100.0,
        current_support=95.0,
        next_resistance=110.0,
        dist_to_support_pct=5.26,
        dist_to_resistance_pct=10.0,
        rel_vol_5d_vs_63d=1.5,
        seven_day_return_pct=3.5,
        thirty_day_return_pct=8.0,
        three_day_return_pct=1.2,
        channel_position_pct=33.3,
        pct_from_52w_high=-4.0,
    )
    assert isinstance(setup, dict)
    assert "label" in setup
    assert "badge_class" in setup
    assert "description" in setup
    assert setup["label"] == "Range Base"


def test_enrich_upcoming_results_with_synthetic_prices(tmp_path, monkeypatch):
    """Verify enrich_upcoming_results enriches 7D/30D returns, price, and technical setups without crashing."""
    settings = Settings()

    # Create dummy dataframe of upcoming results
    df = pd.DataFrame(
        [
            {
                "ticker": "TEST1.NS",
                "earnings_date": pd.Timestamp.today().normalize() + pd.Timedelta(days=2),
                "source": "nse",
            },
            {
                "ticker": "TEST2.NS",
                "earnings_date": pd.Timestamp.today().normalize() + pd.Timedelta(days=5),
                "source": "yfinance",
            },
        ]
    )

    # Mock prices provider so it returns synthetic bars for TEST1.NS and TEST2.NS
    dates = pd.date_range(end=pd.Timestamp.today(), periods=100, freq="B")
    prices_test1 = pd.DataFrame(
        {
            "open": np.linspace(100, 150, 100),
            "high": np.linspace(101, 152, 100),
            "low": np.linspace(99, 148, 100),
            "close": np.linspace(100, 150, 100),
            "volume": np.full(100, 10000),
        },
        index=dates,
    )

    import earnings_engine.data.prices as prices_mod

    def mock_load_prices(ticker, settings, allow_network=False, live_enrich=False):
        return prices_test1

    monkeypatch.setattr(prices_mod, "load_prices", mock_load_prices)
    monkeypatch.setattr(prices_mod, "fetch_batch_live_quotes", lambda *args, **kwargs: {})

    enriched = enrich_upcoming_results(df, settings=settings)

    assert not enriched.empty
    assert "current_price" in enriched.columns
    assert "seven_day_return_pct" in enriched.columns
    assert "thirty_day_return_pct" in enriched.columns
    assert "three_day_return_pct" in enriched.columns
    assert "technical_setup" in enriched.columns

    # Verify values were calculated and are not None
    row = enriched.iloc[0]
    assert row["current_price"] is not None
    assert row["seven_day_return_pct"] is not None
    assert row["thirty_day_return_pct"] is not None
    assert row["technical_setup"] is not None
    assert isinstance(row["technical_setup"], dict)
    assert row["technical_setup"]["label"] != "Unknown"


def test_upcoming_earnings_nse_authoritative_dedup(monkeypatch):
    """Verify that when a ticker has both NSE and yfinance dates, the NSE date is the single source of truth."""
    import sqlite3
    from contextlib import contextmanager
    import earnings_engine.data.earnings as earnings_mod

    conn = sqlite3.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE earnings_history (
            ticker TEXT,
            earnings_date TEXT,
            source TEXT
        )
        """
    )
    # CYIENT.NS has both NSE (2026-10-20) and yfinance (2026-10-22)
    # OTHER.NS has only yfinance (2026-10-25)
    conn.executemany(
        "INSERT INTO earnings_history VALUES (?, ?, ?)",
        [
            ("CYIENT.NS", "2026-10-20", "nse"),
            ("CYIENT.NS", "2026-10-22", "yfinance"),
            ("OTHER.NS", "2026-10-25", "yfinance"),
        ],
    )
    conn.commit()

    @contextmanager
    def mock_connect(settings):
        yield conn

    monkeypatch.setattr(earnings_mod, "_connect", mock_connect)

    settings = Settings()
    res = earnings_mod.upcoming_earnings(["CYIENT.NS", "OTHER.NS"], settings=settings, days=30, start_date=pd.Timestamp("2026-10-01"))

    # CYIENT.NS should only appear once, with source="nse" and date 2026-10-20
    cyient_rows = res[res["ticker"] == "CYIENT.NS"]
    assert len(cyient_rows) == 1
    assert cyient_rows.iloc[0]["source"] == "nse"
    assert cyient_rows.iloc[0]["earnings_date"] == pd.Timestamp("2026-10-20")

    # OTHER.NS (only in yfinance) should still be retained
    other_rows = res[res["ticker"] == "OTHER.NS"]
    assert len(other_rows) == 1
    assert other_rows.iloc[0]["source"] == "yfinance"


def test_enrich_upcoming_results_return_uses_historical_close_not_live_price(monkeypatch):
    """Verify 7D/30D returns use the DB's last historical close instead of live current_price."""
    import earnings_engine.data.market_context as mc_mod

    settings = Settings()

    df = pd.DataFrame(
        [
            {
                "ticker": "CYIENT.NS",
                "earnings_date": pd.Timestamp("2026-10-20"),
                "source": "nse",
            }
        ]
    )

    # 10 business days ending on 2026-10-15
    dates = pd.date_range(end="2026-10-15", periods=10, freq="B")
    # Base close is 100, 7 calendar days ago (~5 business days ago) close was 90
    closes = [80.0, 85.0, 90.0, 92.0, 95.0, 96.0, 98.0, 99.0, 100.0, 100.0]
    prices_df = pd.DataFrame(
        {
            "open": closes,
            "high": closes,
            "low": closes,
            "close": closes,
            "volume": [1000] * 10,
        },
        index=dates,
    )

    import earnings_engine.data.prices as prices_mod

    # Last close is 100.0. Live quote is 200.0 (simulating intraday jump or different date).
    monkeypatch.setattr(prices_mod, "load_prices", lambda *args, **kwargs: prices_df)
    monkeypatch.setattr(mc_mod, "load_prices", lambda *args, **kwargs: prices_df)
    monkeypatch.setattr(mc_mod, "load_price_metrics", lambda *args, **kwargs: {"current_price": 200.0})

    enriched = enrich_upcoming_results(df, settings=settings)
    assert not enriched.empty
    row = enriched.iloc[0]

    # Live price is displayed as current_price
    assert row["current_price"] == 200.0

    # 7D return must be based on last historical close (100.0), NOT live price (200.0)
    # If it used 200.0, return would be > 100%. With 100.0, return is ~11% or similar (< 30%).
    assert row["seven_day_return_pct"] is not None
    assert row["seven_day_return_pct"] < 30.0


