# Phase 2 — Event Dataset: Features & Labels

**Status: Complete** (2026-06-10)

## Goal

Turn the raw cached data into a modeling-ready **event dataset**: one row per
ticker × past earnings event, with point-in-time features and a realized
1-day direction label. Output: `data/cache/dataset.parquet` via
`earnings-engine build-dataset`.

## Label definition

yfinance doesn't reliably indicate announcement timing (before open / after
close / mid-day, common on NSE), so the reaction window brackets the event:

```
reaction_return = close(T+1) / close(T-1) − 1      label = 1 if > 0 else 0
```

where T is the announcement date and T±1 are the nearest trading days on
either side. This captures the earnings move regardless of intraday timing,
at the cost of including one extra day of market noise. Events where the
bracket spans more than 10 calendar days (halts, delistings) are dropped.
Implemented in [labels.py](../earnings_engine/labels.py).

## Point-in-time discipline

Every feature is computed using **only data up to `asof_date`** — the last
trading day strictly before the announcement. Earnings-history features use
only strictly earlier events. A test mutates all prices after `asof_date`
and asserts features don't change (`test_price_features_point_in_time`).

## Feature dictionary

### Price/volume features (`features/price_features.py`) — as of T-1

| Feature | Definition | Intuition |
|---|---|---|
| `ret_5d` / `ret_21d` / `ret_63d` | trailing close-to-close return | pre-earnings run-up / drift |
| `vol_21d` | std of daily returns, 21d | baseline risk regime |
| `vol_ratio_5d_63d` | 5d vol ÷ 63d vol | volatility expanding into the event? |
| `volume_ratio_5d_63d` | 5d avg volume ÷ 63d avg | unusual positioning/interest |
| `abs_ret_mean_21d` | mean |daily return|, 21d | recent choppiness |
| `dist_52w_high` / `dist_52w_low` | last close vs 252d max/min − 1 | where in the yearly range |

Events with fewer than 70 prior trading days are dropped (`MIN_HISTORY_DAYS`).

### Earnings-history features (`features/earnings_features.py`) — strictly earlier events

| Feature | Definition |
|---|---|
| `n_past_events` | number of earlier labeled events for this ticker |
| `past_reaction_mean` / `past_reaction_std` | mean/std of past reaction returns |
| `past_up_rate` | share of past reactions that were up |
| `last_reaction_return` | previous event's reaction return |
| `last_surprise_pct` | previous event's EPS surprise % (mostly US-only) |

### Context

| Feature | Definition |
|---|---|
| `is_in_market` | 1 for NSE (`.NS`), 0 for US |

NaNs are left as-is (first events have no history; NSE lacks surprise data) —
LightGBM handles missing values natively, and the Phase 3 baseline ignores
these columns.

## Dataset schema

`ID_COLUMNS`: ticker, market, earnings_date, asof_date, reaction_date
`FEATURE_COLUMNS`: the 16 features above · `LABEL_COLUMNS`: reaction_return, label
Rows sorted by earnings_date — walk-forward splits in Phase 3 slice this directly.

## Verification

- 13/13 tests pass, including: reaction window brackets weekends correctly,
  point-in-time immutability, thin-history rejection, chronological
  accumulation of earnings-history features.
- Live build on 8 tickers (4 NSE + 4 US): **359 events**, 2015→2026,
  180 US / 179 IN, up-label rate 52.4%, mean |reaction| 3.9%.
- NaN rates ≤ 4.5%, confined to first-event history features as expected.

## Usage

```bash
.venv/bin/earnings-engine ingest                  # if cache is empty/stale
.venv/bin/earnings-engine build-dataset           # full universe
.venv/bin/earnings-engine build-dataset --market IN
.venv/bin/earnings-engine build-dataset -t AAPL -t TCS.NS
```

## Next: Phase 3 — Baseline model + backtester

Walk-forward event backtest with a statistical baseline (predict using
`past_up_rate` / historical drift). Establishes the metrics (hit rate, PnL,
vs. always-up) that the Phase 4 ML model must beat. Deliverable doc:
backtest methodology.
