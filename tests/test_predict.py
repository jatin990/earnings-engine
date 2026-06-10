import numpy as np
import pandas as pd
import pytest

import earnings_engine.predict as predict_mod
from earnings_engine.config import Settings
from earnings_engine.dataset import FEATURE_COLUMNS
from earnings_engine.predict import build_upcoming_events, predict_upcoming
from earnings_engine.reports.render import render_predictions


def make_prices(days=400, seed=5):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=days)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0005, 0.015, days)))
    return pd.DataFrame(
        {"open": close, "high": close * 1.01, "low": close * 0.99,
         "close": close, "volume": rng.integers(1e5, 1e6, days).astype(float)},
        index=pd.DatetimeIndex(dates, name="date"),
    )


def make_labeled_dataset(n=300, seed=9):
    rng = np.random.default_rng(seed)
    df = pd.DataFrame({c: rng.normal(0, 1, n) for c in FEATURE_COLUMNS})
    df["n_past_events"] = rng.integers(0, 10, n)
    df["is_in_market"] = rng.integers(0, 2, n)
    ret = rng.normal(0, 0.04, n)
    df["reaction_return"] = ret
    df["label"] = (ret > 0).astype(int)
    df["ticker"] = rng.choice(["AAA", "BBB.NS"], n)
    df["market"] = np.where(df["ticker"].str.endswith(".NS"), "IN", "US")
    df["earnings_date"] = pd.date_range("2019-01-01", periods=n, freq="5D")
    return df


@pytest.fixture
def wired(monkeypatch, tmp_path):
    prices = make_prices()
    future = pd.Timestamp.today().normalize() + pd.Timedelta(days=4)
    earnings = pd.DataFrame({
        "earnings_date": [pd.Timestamp("2024-02-01"), future],
        "eps_estimate": [1.0, 1.2], "eps_reported": [1.1, None], "surprise_pct": [10.0, None],
    })
    dataset = make_labeled_dataset()

    monkeypatch.setattr(predict_mod, "load_prices", lambda t, s: prices)
    monkeypatch.setattr(predict_mod, "load_earnings", lambda t, s: earnings)
    monkeypatch.setattr(
        predict_mod, "upcoming_earnings",
        lambda tickers, s, days=14: pd.DataFrame(
            [{"ticker": t, "earnings_date": future} for t in tickers]
        ),
    )
    monkeypatch.setattr(predict_mod, "load_dataset", lambda: dataset)
    return dataset


def test_build_upcoming_events_schema(wired):
    df = build_upcoming_events(["AAA", "BBB.NS"], Settings())
    assert len(df) == 2
    assert set(FEATURE_COLUMNS).issubset(df.columns)
    assert "label" not in df.columns


def test_predict_upcoming(wired):
    preds = predict_upcoming(["AAA", "BBB.NS"], Settings(), model_name="gbm")
    assert len(preds) == 2
    assert preds["direction"].isin(["UP", "DOWN"]).all()
    assert ((preds["confidence"] >= 0.5) & (preds["confidence"] <= 1.0)).all()
    # Sorted by confidence descending.
    assert preds["confidence"].is_monotonic_decreasing
    # Direction consistent with p_up.
    assert ((preds["p_up"] >= 0.5) == (preds["direction"] == "UP")).all()


def test_render_predictions(wired, tmp_path, monkeypatch):
    import earnings_engine.reports.render as render_mod
    monkeypatch.setattr(render_mod, "OUTPUT_DIR", tmp_path)
    preds = predict_upcoming(["AAA", "BBB.NS"], Settings(), model_name="gbm")
    csv_path, html_path = render_predictions(preds)
    assert csv_path.exists() and html_path.exists()
    html = html_path.read_text()
    assert "AAA" in html and "Direction" in html or "direction" in html
    assert len(pd.read_csv(csv_path)) == 2
