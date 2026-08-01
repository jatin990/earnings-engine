import numpy as np
import pandas as pd
import pytest

from earnings_engine.config import Settings
from earnings_engine.dataset import FEATURE_COLUMNS, build_ticker_events
from earnings_engine.features.price_features import compute_price_features
from earnings_engine.labels import compute_reaction


def make_prices(start="2022-01-03", days=400, seed=7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(start, periods=days)
    rets = rng.normal(0.0005, 0.015, days)
    close = 100 * np.exp(np.cumsum(rets))
    return pd.DataFrame(
        {
            "open": close * 0.995,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": rng.integers(1e5, 1e6, days).astype(float),
        },
        index=pd.DatetimeIndex(dates, name="date"),
    )


def test_reaction_window_brackets_event():
    prices = make_prices()
    # Pick an event date that is a Saturday: T-1 = Friday, T+1 = Monday.
    event = pd.Timestamp("2023-03-11")
    r = compute_reaction(prices, event)
    assert r is not None
    assert r.asof_date < event < r.reaction_date
    expected = prices.loc[r.reaction_date, "close"] / prices.loc[r.asof_date, "close"] - 1
    assert r.reaction_return == pytest.approx(expected)
    assert r.label == int(expected > 0)


def test_reaction_none_outside_history():
    prices = make_prices(days=100)
    assert compute_reaction(prices, pd.Timestamp("2010-01-01")) is None
    assert compute_reaction(prices, prices.index[-1] + pd.Timedelta(days=30)) is None


def test_reaction_none_for_missing_close_values():
    prices = make_prices(days=40)
    event = prices.index[10]
    prices.loc[prices.index[9], "close"] = None
    prices.loc[prices.index[11], "close"] = float("nan")
    assert compute_reaction(prices, event) is None


def test_price_features_point_in_time():
    prices = make_prices()
    asof = prices.index[200]
    feats = compute_price_features(prices, asof)
    assert feats is not None
    # Mutating data after asof must not change the features.
    tampered = prices.copy()
    tampered.loc[tampered.index > asof, "close"] = 9999.0
    feats2 = compute_price_features(tampered, asof)
    assert feats == feats2


def test_price_features_thin_history():
    prices = make_prices(days=40)
    assert compute_price_features(prices, prices.index[-1]) is None


@pytest.fixture
def cached(tmp_path, monkeypatch):
    """Wire build_ticker_events to synthetic cached data."""
    prices = make_prices()
    earnings = pd.DataFrame(
        {
            "earnings_date": pd.to_datetime(["2022-10-20", "2023-01-19", "2023-04-20"]),
            "eps_estimate": [1.0, 1.1, 1.2],
            "eps_reported": [1.2, 1.0, None],
            "surprise_pct": [20.0, -9.0, None],
        }
    )
    import earnings_engine.dataset as ds

    monkeypatch.setattr(ds, "load_prices", lambda t, s: prices)
    monkeypatch.setattr(ds, "load_earnings", lambda t, s: earnings)
    return prices, earnings


def test_build_ticker_events(cached):
    df = build_ticker_events("TEST.NS", Settings())
    assert len(df) == 3
    assert set(FEATURE_COLUMNS).issubset(df.columns)
    assert df["market"].eq("IN").all()
    assert df["is_in_market"].eq(1).all()
    assert df["label"].isin([0, 1]).all()
    # Earnings-history features accumulate chronologically.
    assert df.iloc[0]["n_past_events"] == 0
    assert df.iloc[1]["n_past_events"] == 1
    assert df.iloc[2]["n_past_events"] == 2
    assert df.iloc[1]["last_reaction_return"] == pytest.approx(df.iloc[0]["reaction_return"])
    # Second event sees the first event's surprise.
    assert df.iloc[1]["last_surprise_pct"] == pytest.approx(20.0)
