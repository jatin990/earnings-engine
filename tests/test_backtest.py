import numpy as np
import pandas as pd
import pytest

from earnings_engine.backtest.engine import BacktestConfig, compute_metrics, run_backtest
from earnings_engine.models.base import DirectionModel
from earnings_engine.models.baseline import AlwaysUp, PastUpRate


def make_dataset(n=200, seed=3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2018-01-01", periods=n, freq="7D")
    ret = rng.normal(0.002, 0.05, n)
    return pd.DataFrame(
        {
            "ticker": rng.choice(["A", "B.NS", "C"], n),
            "market": rng.choice(["US", "IN"], n),
            "earnings_date": dates,
            "reaction_return": ret,
            "label": (ret > 0).astype(int),
            "n_past_events": rng.integers(0, 20, n),
            "past_up_rate": rng.uniform(0, 1, n),
        }
    )


class Oracle(DirectionModel):
    """Cheating model used to verify trade accounting."""

    name = "oracle"

    def fit(self, train):
        return self

    def predict_proba(self, events):
        return np.where(events["reaction_return"] > 0, 1.0, 0.0)


def test_walk_forward_no_leakage_in_folds():
    df = make_dataset()
    seen = []

    class Spy(AlwaysUp):
        def fit(self, train):
            seen.append((train["earnings_date"].max(), len(train)))
            return super().fit(train)

    result = run_backtest(df, Spy(), BacktestConfig())
    # Every test prediction must postdate its fold's training data.
    for fold_start, group in result.predictions.groupby("fold_start"):
        assert group["earnings_date"].min() >= fold_start
    train_max = [t for t, _ in seen]
    assert all(train_max[i] <= train_max[i + 1] for i in range(len(train_max) - 1))


def test_oracle_hits_everything():
    df = make_dataset()
    result = run_backtest(df, Oracle(), BacktestConfig(cost_per_trade=0.0))
    assert result.metrics["hit_rate"] == 1.0
    assert result.metrics["avg_trade_return"] > 0
    # Oracle's total return must equal sum of |reaction| over tested events.
    tested = result.predictions
    assert result.metrics["total_return"] == pytest.approx(tested["reaction_return"].abs().sum())


def test_threshold_reduces_coverage():
    df = make_dataset()
    full = run_backtest(df, PastUpRate(), BacktestConfig(threshold=0.5))
    strict = run_backtest(df, PastUpRate(), BacktestConfig(threshold=0.65))
    assert strict.metrics["n_traded"] < full.metrics["n_traded"]
    assert full.metrics["coverage"] == 1.0


def test_costs_reduce_returns():
    df = make_dataset()
    free = run_backtest(df, AlwaysUp(), BacktestConfig(cost_per_trade=0.0))
    costly = run_backtest(df, AlwaysUp(), BacktestConfig(cost_per_trade=0.002))
    assert costly.metrics["total_return"] < free.metrics["total_return"]


def test_past_up_rate_shrinkage():
    model = PastUpRate(shrinkage=4.0)
    model.base_rate = 0.5
    events = pd.DataFrame({"n_past_events": [0, 100], "past_up_rate": [0.9, 0.9]})
    proba = model.predict_proba(events)
    assert proba[0] == pytest.approx(0.5)        # no history -> base rate
    assert proba[1] > 0.85                        # long history -> near own rate


def test_metrics_empty_and_skip_handling():
    preds = pd.DataFrame(
        {"side": [0, 0], "reaction_return": [0.1, -0.1], "label": [1, 0], "trade_return": [0.0, 0.0]}
    )
    m = compute_metrics(preds)
    assert m["n_traded"] == 0
    assert np.isnan(m["hit_rate"])
