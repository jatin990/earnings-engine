"""Model interface shared by baselines (Phase 3) and ML models (Phase 4).

A model consumes event-dataset rows and emits P(up) per event. The backtester
only talks to this interface, so swapping baseline -> LightGBM is a one-line
change.
"""

from abc import ABC, abstractmethod

import numpy as np
import pandas as pd


class DirectionModel(ABC):
    name: str = "model"

    @abstractmethod
    def fit(self, train: pd.DataFrame) -> "DirectionModel":
        """Fit on labeled event rows (must contain 'label')."""

    @abstractmethod
    def predict_proba(self, events: pd.DataFrame) -> np.ndarray:
        """Return P(up) in [0, 1] for each event row."""

    def predict(self, events: pd.DataFrame) -> np.ndarray:
        """Direction: 1 = up, 0 = down."""
        return (self.predict_proba(events) >= 0.5).astype(int)
