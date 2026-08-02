# 05 — Backtest

> Related: [04-models](04-models.md) → [06-dataset-predict](06-dataset-predict.md)

## `backtest/engine.py`
**Dataclasses:**
- `BacktestConfig`:
  - `initial_train_frac: float = 0.4`
  - `test_window_days: int = 90`
  - `threshold: float = 0.5`
  - `cost_per_trade: float = 0.001`
- `BacktestResult`:
  - `predictions: pd.DataFrame`
  - `metrics: dict`
  - `fold_metrics: pd.DataFrame | None`

**Functions:**
- `run_backtest(dataset, model, cfg=None) -> BacktestResult`
  - Walk-forward by `earnings_date`
  - Trade simulation: long if `proba >= threshold`, short if `proba <= 1-threshold`, else skip
  - `trade_return = side * reaction_return - cost_per_trade`
- `compute_metrics(preds) -> dict`
  - Keys: `n_events`, `n_traded`, `coverage`, `hit_rate`, `avg_trade_return`, `total_return`, `sharpe_per_event`, `base_up_rate`