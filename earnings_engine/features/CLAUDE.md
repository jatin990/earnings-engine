# CLAUDE.md — Features & Quant Pipeline (`earnings_engine/features/`)

> Subsystem guide for Point-in-Time (PIT) feature engineering, reaction returns, and binary classification labels.

---

## 1. Scope & Architecture

The features subsystem calculates technical, momentum, volatility, and fundamental metrics used by machine learning models (`LightGBM`, `Platt scaling`, `Kronos AI neural forecasts`) and backtesting engines.

- **Technical Features**: `earnings_engine/features/price_features.py` (RSI, ATR, moving averages, volume surges)
- **Earnings Features**: `earnings_engine/features/earnings_features.py` (surprise metrics, reporting deltas)
- **Labels & Reactions**: `earnings_engine/features/labels.py` (post-earnings reaction calculations)
- **Dataset Assembly**: `earnings_engine/dataset.py` (combines features with strict chronological boundaries)

---

## 2. Mandatory Rules & Invariants

### 2.1 Strict Point-in-Time (PIT) Guarantee (No Lookahead Bias)
- **$T-1$ Price Bar Filter**: For any event occurring at date $T$, feature calculation must strictly filter price bars up to $T-1$:
  ```python
  prices_pit = prices.loc[prices.index <= asof_date]
  ```
- Technical indicators (RSI, SMA, 21-day volatility, volume ratios) must be calculated exclusively on `prices_pit`. Under no circumstances may $T$ or future bars contaminate feature values.

### 2.2 Reaction Return & Binary Label Contract
- **Reaction Return Formula**:
  $$\text{reaction\_return} = \left(\frac{\text{close}(T+1)}{\text{close}(T-1)}\right) - 1$$
- **Binary Label**: $1$ if $\text{reaction\_return} > 0$, else $0$.
- **Missing Data Gate**: Return `None` if:
  1. Either $T-1$ or $T+1$ trading bar is missing.
  2. The calendar gap between $T-1$ and $T+1$ exceeds 10 days (unusual suspension/delisting).

### 2.3 Explicit Timeframe Protocol
- Metric outputs must declare their temporal baseline:
  - Return: `7D Return`, `30D Return`, `52W High/Low` (never standalone `+X%`)
  - Volume: `Volume Surge (5D vs 63D avg)`
  - Volatility: `21-Day Annualized Volatility`

---

## 3. Targeted Testing

```bash
# Run feature calculations and PIT compliance tests
./.venv/Scripts/python.exe -m pytest tests/test_features.py -v
./.venv/Scripts/python.exe -m pytest tests/test_labels.py -v
```
