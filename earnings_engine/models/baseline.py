"""Statistical baselines.

These set the bar the ML model must beat. If LightGBM can't outperform
"this stock usually goes up after earnings", it has learned nothing useful.
"""

import numpy as np
import pandas as pd

from earnings_engine.models.base import DirectionModel


class AlwaysUp(DirectionModel):
    """Predict up for every event, with the base rate as 'confidence'."""

    name = "always_up"

    def __init__(self) -> None:
        self.base_rate = 0.5

    def fit(self, train: pd.DataFrame) -> "AlwaysUp":
        if len(train):
            self.base_rate = float(train["label"].mean())
        return self

    def predict_proba(self, events: pd.DataFrame) -> np.ndarray:
        return np.full(len(events), max(self.base_rate, 0.5 + 1e-9))


class PastUpRate(DirectionModel):
    """P(up) = this ticker's historical post-earnings up-rate, shrunk toward
    the global base rate when the ticker has few past events.

    shrunk = (n * past_up_rate + k * base_rate) / (n + k)
    """

    name = "past_up_rate"

    def __init__(self, shrinkage: float = 4.0) -> None:
        self.shrinkage = shrinkage
        self.base_rate = 0.5

    def fit(self, train: pd.DataFrame) -> "PastUpRate":
        if len(train):
            self.base_rate = float(train["label"].mean())
        return self

    def predict_proba(self, events: pd.DataFrame) -> np.ndarray:
        n = events["n_past_events"].fillna(0).to_numpy(dtype=float)
        rate = events["past_up_rate"].fillna(self.base_rate).to_numpy(dtype=float)
        k = self.shrinkage
        return (n * rate + k * self.base_rate) / (n + k)


BASELINES = {m.name: m for m in (AlwaysUp, PastUpRate)}
