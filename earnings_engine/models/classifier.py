"""Gradient-boosted direction classifier with probability calibration.

LightGBM on the Phase 2 feature set, wrapped in Platt (sigmoid) calibration
so that predict_proba is a usable confidence: trades filtered at a higher
threshold should genuinely hit more often. Hyperparameters are deliberately
conservative — earnings-event datasets are small (hundreds to a few thousand
rows) and noisy, so the model is kept shallow and heavily regularized.
"""

import numpy as np
import pandas as pd

from earnings_engine.models.base import DirectionModel

def _require_gbm_dependencies():
    """Lazily load LightGBM and scikit-learn with clear diagnostics if missing."""
    try:
        from lightgbm import LGBMClassifier
        from sklearn.calibration import CalibratedClassifierCV
        return LGBMClassifier, CalibratedClassifierCV
    except ImportError as e:
        raise RuntimeError(
            "LightGBM and scikit-learn are required to fit the GBClassifier model. "
            "Please install them via: pip install lightgbm scikit-learn"
        ) from e

DEFAULT_PARAMS = dict(
    n_estimators=120,
    learning_rate=0.05,
    num_leaves=7,
    max_depth=3,
    min_child_samples=30,
    subsample=0.8,
    subsample_freq=1,
    colsample_bytree=0.8,
    reg_lambda=5.0,
    verbosity=-1,
)


class GBClassifier(DirectionModel):
    name = "gbm"

    def __init__(self, calibrate: bool = True, **params) -> None:
        self.params = {**DEFAULT_PARAMS, **params}
        self.calibrate = calibrate
        self.model = None
        self.feature_columns: list[str] | None = None

    def _features(self, df: pd.DataFrame) -> pd.DataFrame:
        # Imported here to avoid a circular import (dataset -> features only).
        from earnings_engine.dataset import FEATURE_COLUMNS

        cols = self.feature_columns or FEATURE_COLUMNS
        return df[cols]

    def fit(self, train: pd.DataFrame) -> "GBClassifier":
        from earnings_engine.dataset import FEATURE_COLUMNS

        LGBMClassifier, CalibratedClassifierCV = _require_gbm_dependencies()

        self.feature_columns = FEATURE_COLUMNS
        X = self._features(train)
        y = train["label"].astype(int)
        base = LGBMClassifier(**self.params)
        if self.calibrate and len(train) >= 150 and y.nunique() == 2:
            self.model = CalibratedClassifierCV(base, method="sigmoid", cv=3)
        else:
            self.model = base
        self.model.fit(X, y)
        return self

    def predict_proba(self, events: pd.DataFrame) -> np.ndarray:
        if self.model is None:
            raise RuntimeError("Model not fitted")
        return self.model.predict_proba(self._features(events))[:, 1]

    def feature_importances(self) -> pd.Series:
        """Mean gain-based importance (averaged over calibration folds)."""
        if self.model is None or self.feature_columns is None:
            raise RuntimeError("Model not fitted")

        # Check if calibrated or standalone
        calibrated_classifiers = getattr(self.model, "calibrated_classifiers_", None)
        if calibrated_classifiers:
            imps = np.mean(
                [cc.estimator.feature_importances_ for cc in calibrated_classifiers],
                axis=0,
            )
        else:
            imps = self.model.feature_importances_
        return pd.Series(imps, index=self.feature_columns).sort_values(ascending=False)
