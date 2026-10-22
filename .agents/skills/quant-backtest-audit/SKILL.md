---
name: quant-backtest-audit
description: Point-in-Time (PIT) mathematical validation, lookahead bias prevention, walk-forward splits, reaction returns, and feature leakage auditing. Use when creating or modifying quant features, ML models, or backtests.
---

# Quantitative PIT & Backtest Audit Protocol

Use this skill whenever authoring or modifying features, ML training datasets, labels, scanners, or backtest engines.

---

## 1. Strict Point-in-Time (PIT) Guarantee

- **Zero Future Leakage**:
  For an earnings event, catalyst, or decision on date $T$, historical prices and fundamentals must strictly be bounded to $T-1$:
  ```python
  prices_pit = prices.loc[prices.index <= asof_date]
  ```
  Never include date $T$ in the calculation of pre-event technicals, moving averages, RSI, or volume baselines.

---

## 2. Standardized Reaction Returns & Labels

- **Reaction Formula**:
  $$\text{reaction} = \left(\frac{\text{close}(T+1)}{\text{close}(T-1)}\right) - 1$$
- **Binary Classification Label**:
  - `label = 1` if $\text{reaction} > 0$
  - `label = 0` if $\text{reaction} \le 0$
- **Data Gap Invalidation**:
  - If either $T-1$ or $T+1$ price bar is missing, or the calendar gap between the bars exceeds **10 days** (e.g. trading halt, suspension), return `None` (discard the row). Do not interpolate missing prices.

---

## 3. Time-Series & Walk-Forward Validation

- **Never Use Random Splits**:
  - `train_test_split(..., shuffle=True)` is strictly forbidden on financial time series.
  - Use rolling walk-forward or expanding window cross-validation:
    - Train: $[T_0, T_{\text{train}}]$
    - Embargo / Purge Gap: 5–10 trading days
    - Test: $[T_{\text{train}} + \text{gap}, T_{\text{test}}]$
- **Feature Scaling**:
  - Fit scalers, normalizers, or quantile transforms strictly on the training partition. Never fit transforms on the entire dataset.

---

## 4. Verification Check

Run targeted feature and backtesting tests:
```bash
./.venv/Scripts/python.exe -m pytest tests/test_features.py -v
./.venv/Scripts/python.exe -m pytest tests/test_backtest.py -v
```
