# Phase 3 — Baseline Models & Walk-Forward Backtester

**Status: Complete** (2026-06-10)

## Goal

Build the evaluation machinery that makes Phase 4's ML model honest: a
walk-forward event backtester and statistical baselines that set the bar to
beat. CLI: `earnings-engine backtest --model <name>`.

## Model interface

[models/base.py](../earnings_engine/models/base.py) defines `DirectionModel`
with `fit(train_df)` and `predict_proba(events_df) -> P(up)`. The backtester
talks only to this interface, so Phase 4's LightGBM plugs in unchanged.

## Baselines ([models/baseline.py](../earnings_engine/models/baseline.py))

- **`always_up`** — predicts up for every event. Measures the market's
  natural post-earnings drift; any model must out-earn it.
- **`past_up_rate`** — P(up) = the ticker's own historical post-earnings
  up-rate, shrunk toward the global base rate when history is thin:
  `(n·rate + k·base) / (n + k)` with k=4. The classic "this stock usually
  pops on earnings" heuristic, made statistically careful.

## Backtest methodology ([backtest/engine.py](../earnings_engine/backtest/engine.py))

**Walk-forward folds.** Events sorted by `earnings_date`. The first 40% (by
time) form the initial train set; then quarterly (90-day) test windows step
forward, refitting the model each fold on all data strictly before the fold
start. No prediction ever uses a model that saw its own period — the temporal
counterpart of Phase 2's point-in-time feature guarantee (verified by a spy
test asserting train data always predates test data).

**Trade simulation.** Per event: long if P(up) ≥ threshold, short if
P(up) ≤ 1−threshold, else skip. Trade return = ±reaction_return − cost.
Default cost 10 bps round trip (`cost_per_trade=0.001`).

**Metrics** (`compute_metrics`): events tested, coverage, hit rate vs base
up-rate, average/total trade return, per-event Sharpe (deliberately not
annualized — events are irregularly spaced). Per-fold metrics are also
returned for stability inspection.

## Results on the 8-ticker dataset (359 events, 216 tested)

| Model | Threshold | Coverage | Hit rate | Avg trade | Total |
|---|---|---|---|---|---|
| always_up | 0.50 | 100% | 49.5% | +0.15% | +32.9% |
| past_up_rate | 0.50 | 100% | **52.8%** | **+0.37%** | +80.7% |
| past_up_rate | 0.60 | 54% | 49.6% | +0.07% | +8.1% |

Reading: ticker-level reaction history carries real signal (+3.3pp hit rate
over always-up at full coverage), but the baseline's confidence is not
well calibrated — filtering to its "high confidence" trades *hurts*. That
calibration gap is precisely what Phase 4's calibrated classifier targets.

Caveat: 8 tickers is a smoke-test universe. Run the full ~100-ticker ingest
before treating any number here as an expectation.

## Verification

19/19 tests pass. Backtest-specific coverage: fold chronology / no temporal
leakage (spy model), trade accounting via a cheating oracle (hit rate must be
100% and total return must equal Σ|reaction|), threshold reduces coverage,
costs reduce returns, shrinkage pulls thin histories to the base rate,
empty/all-skip edge cases.

## Usage

```bash
.venv/bin/earnings-engine backtest --model past_up_rate
.venv/bin/earnings-engine backtest --model always_up --market IN
.venv/bin/earnings-engine backtest --model past_up_rate --threshold 0.6 --cost 0.002
```

## Next: Phase 4 — ML classifier

LightGBM on the 16 Phase 2 features with probability calibration, evaluated
through this exact backtester against `past_up_rate`. Deliverable doc:
model card.
