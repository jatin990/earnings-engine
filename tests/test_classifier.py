import numpy as np
import pandas as pd
import pytest

from earnings_engine.backtest.engine import BacktestConfig, run_backtest
from earnings_engine.dataset import FEATURE_COLUMNS
from earnings_engine.models.classifier import GBClassifier
from earnings_engine.models.registry import make_model


def make_dataset(n=600, signal=True, seed=11) -> pd.DataFrame:
    """Synthetic event dataset where ret_5d (optionally) drives the label."""
    rng = np.random.default_rng(seed)
    df = pd.DataFrame({c: rng.normal(0, 1, n) for c in FEATURE_COLUMNS})
    df["n_past_events"] = rng.integers(0, 20, n)
    df["is_in_market"] = rng.integers(0, 2, n)
    # Inject NaNs like the real dataset has.
    df.loc[df.index[:20], "past_up_rate"] = np.nan
    noise = rng.normal(0, 1, n)
    driver = df["ret_5d"] if signal else pd.Series(rng.normal(0, 1, n))
    ret = (2.0 * driver + noise) * 0.01
    df["reaction_return"] = ret
    df["label"] = (ret > 0).astype(int)
    df["ticker"] = "T"
    df["market"] = "US"
    df["earnings_date"] = pd.date_range("2016-01-01", periods=n, freq="3D")
    return df


def test_gbm_learns_planted_signal():
    df = make_dataset(signal=True)
    train, test = df.iloc[:450], df.iloc[450:]
    model = GBClassifier().fit(train)
    proba = model.predict_proba(test)
    assert proba.shape == (len(test),)
    assert np.all((proba >= 0) & (proba <= 1))
    acc = ((proba >= 0.5).astype(int) == test["label"]).mean()
    assert acc > 0.65  # planted signal is strong; well above chance

    # The planted driver should dominate importances.
    imp = model.feature_importances()
    assert imp.index[0] == "ret_5d"


def test_gbm_handles_nans():
    df = make_dataset()
    df.loc[df.index[::3], "vol_21d"] = np.nan
    model = GBClassifier().fit(df.iloc[:400])
    proba = model.predict_proba(df.iloc[400:])
    assert not np.isnan(proba).any()


def test_gbm_skips_calibration_on_small_train():
    df = make_dataset(n=120)
    model = GBClassifier().fit(df)
    from lightgbm import LGBMClassifier

    assert isinstance(model.model, LGBMClassifier)


def test_calibration_monotone_confidence():
    """Higher-confidence buckets should hit more often when signal exists."""
    df = make_dataset(n=900, signal=True)
    result = run_backtest(df, GBClassifier(), BacktestConfig(cost_per_trade=0.0))
    preds = result.predictions
    conf = np.maximum(preds["proba"], 1 - preds["proba"])
    correct = (preds["side"] == np.where(preds["reaction_return"] > 0, 1, -1))
    low = correct[conf < conf.median()].mean()
    high = correct[conf >= conf.median()].mean()
    assert high > low


def test_registry():
    assert make_model("gbm").name == "gbm"
    assert make_model("always_up").name == "always_up"
    with pytest.raises(ValueError):
        make_model("nope")
