"""Tests for Results Ledger quantitative calculations, price metrics, and Buy Indicator scores."""

import pytest
import pandas as pd
import numpy as np

from earnings_engine.config import Settings
from earnings_engine.data.market_context import enrich_upcoming_results, classify_technical_setup
from earnings_engine.reports.render import compute_buy_indicator


def test_52w_high_drawdown_negative_sign(monkeypatch):
    """Verify that a stock trading below its 52W high has a negative drawdown percentage."""
    # When current_price is 90 and week_52_high is 100:
    # pct_from_52w_high must be -10.0%, NOT +10.0%
    settings = Settings()
    df = pd.DataFrame([
        {
            "ticker": "TEST.NS",
            "earnings_date": pd.Timestamp("2026-10-25"),
            "source": "nse",
        }
    ])

    dates = pd.date_range(end=pd.Timestamp("2026-10-20"), periods=100, freq="B")
    # Low=80, High=100, Close=90
    prices_df = pd.DataFrame(
        {
            "open": np.full(100, 90.0),
            "high": np.linspace(95.0, 100.0, 100),  # Max high = 100.0
            "low": np.linspace(80.0, 85.0, 100),   # Min low = 80.0
            "close": np.full(100, 90.0),            # Current/last close = 90.0
            "volume": np.full(100, 10000),
        },
        index=dates,
    )

    import earnings_engine.data.prices as prices_mod
    monkeypatch.setattr(prices_mod, "load_prices", lambda ticker, settings, **kwargs: prices_df)
    monkeypatch.setattr(prices_mod, "fetch_batch_live_quotes", lambda *args, **kwargs: {})

    enriched = enrich_upcoming_results(df, settings=settings, force=True)
    row = enriched.iloc[0]

    assert row["pct_from_52w_high"] is not None
    # 90 vs 100 high should be -10.0%
    assert row["pct_from_52w_high"] == pytest.approx(-10.0, abs=0.5)
    assert row["pct_from_52w_high"] < 0, f"Expected negative drawdown, got {row['pct_from_52w_high']}"


def test_buy_indicator_pillar1_drawdown_scoring():
    """Verify that stocks closer to 52W high get higher Pillar 1 points than stocks down 50%."""
    score_close = compute_buy_indicator(
        {"pct_from_52w_high": -5.0, "channel_position_pct": 80.0, "beat_rate": 0.8}
    )
    score_far = compute_buy_indicator(
        {"pct_from_52w_high": -50.0, "channel_position_pct": 80.0, "beat_rate": 0.8}
    )

    assert score_close["pillars"]["technical"] > score_far["pillars"]["technical"]
    # Stock with -5.0% should get 5.0 for 52W high component; stock with -50.0% gets 1.0
    diff = score_close["pillars"]["technical"] - score_far["pillars"]["technical"]
    assert diff >= 4.0
