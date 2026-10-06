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
