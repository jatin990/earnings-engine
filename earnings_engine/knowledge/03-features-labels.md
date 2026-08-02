# 03 — Features & Labels

> Related: [02-data-layer](02-data-layer.md) → [06-dataset-predict](06-dataset-predict.md)

## `labels.py`
**Dataclass:**
```python
@dataclass
class Reaction:
    asof_date: pd.Timestamp      # T-1
    reaction_date: pd.Timestamp  # T+1
    reaction_return: float
    label: int
```

**Function:**
- `compute_reaction(prices, earnings_date) -> Reaction | None`
- Label: `reaction_return = close(T+1) / close(T-1) - 1`, `label = int(reaction_return > 0)`
- Returns `None` if: no T-1/T+1, gap > 10 days, NaN/zero close

## `features/price_features.py`
**Constants:** `MIN_HISTORY_DAYS = 70`

**Feature list:**
```python
PRICE_FEATURES = [
    "ret_5d", "ret_21d", "ret_63d",
    "vol_21d", "vol_ratio_5d_63d", "volume_ratio_5d_63d",
    "abs_ret_mean_21d", "dist_52w_high", "dist_52w_low",
]
```

**Function:**
- `compute_price_features(prices, asof_date) -> dict | None`
- Returns `None` if `< MIN_HISTORY_DAYS` bars or `ret_63d` is NaN

## `features/earnings_features.py`
**Feature list:**
```python
EARNINGS_FEATURES = [
    "n_past_events", "past_reaction_mean", "past_reaction_std",
    "past_up_rate", "last_reaction_return", "last_surprise_pct",
]
```

**Function:**
- `compute_earnings_features(past_events, earnings, earnings_date) -> dict`
- `past_events`: earlier events with `reaction_return` column
- `earnings`: raw cached earnings frame
- Computes stats from past events + last prior surprise