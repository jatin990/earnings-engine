# 04 — Models

> Related: [03-features-labels](03-features-labels.md) → [05-backtest](05-backtest.md) → [06-dataset-predict](06-dataset-predict.md)

## `models/base.py`
**Abstract class:**
```python
class DirectionModel(ABC):
    name: str = "model"
    def fit(self, train: pd.DataFrame) -> "DirectionModel"
    def predict_proba(self, events: pd.DataFrame) -> np.ndarray
    def predict(self, events: pd.DataFrame) -> np.ndarray  # default: proba >= 0.5
```

## `models/baseline.py`
**Classes:**
- `AlwaysUp` — predicts base rate, `name="always_up"`
- `PastUpRate` — ticker-specific up-rate shrunk toward global base, `name="past_up_rate"`, shrinkage=4.0

## `models/classifier.py`
**Class:** `GBClassifier(DirectionModel)`, `name="gbm"`

**Default params:**
```python
DEFAULT_PARAMS = dict(
    n_estimators=120, learning_rate=0.05, num_leaves=7,
    max_depth=3, min_child_samples=30, subsample=0.8,
    subsample_freq=1, colsample_bytree=0.8, reg_lambda=5.0, verbosity=-1,
)
```

**Behavior:**
- Uses `LGBMClassifier`
- Calibrates with `CalibratedClassifierCV(method="sigmoid", cv=3)` if `len(train) >= 150` and both labels present
- `feature_importances()` returns mean gain-based importance

## `models/registry.py`
**Function:**
- `make_model(name: str) -> DirectionModel`
- `MODELS = {"always_up": AlwaysUp, "past_up_rate": PastUpRate, "gbm": GBClassifier}`