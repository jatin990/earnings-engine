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

---

## `data/strategy_auditor.py` — Multi-Strategy Backtesting & Historical Audit

**Key Functions:**
- `import_kronos_predictions(settings, force=False) -> dict`:
  - Imports all existing Kronos AI forecasts from `kronos_predictions` into `strategy_predictions` under strategy `'Kronos_AI'`.
  - Automatically maps 14-day horizons and audits outcomes against historical price data in `price_history`.
- `backtest_strategy_history(strategy_name="ALL", days=365, universe=None, settings=None) -> dict`:
  - Runs a 1-year historical backtest simulation across multiple core strategies:
    1. `Kronos_1Y_Backtest` / `Kronos_AI`: 14-day multi-factor trend and momentum models.
    2. `News_Momentum_Breakout`: 5-day volume surge and 20-day high breakouts.
    3. `Earnings_Drift_GBM`: Post-earnings drift prediction from 13,133 event dataset.
    4. `Mean_Reversion_52W`: 5-day mean reversion setups at 52-week extremes.
  - Persists decisions to `strategy_predictions` and outcome logs to `strategy_audit_logs`.
- `calculate_strategy_metrics(strategy_name=None, settings=None) -> dict`:
  - Computes Win Rate %, Profit Factor, Sharpe Ratio, Sortino Ratio, Brier Score, and directional precision.