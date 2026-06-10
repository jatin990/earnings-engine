# Phase 4 — Model Card: Calibrated GBM Direction Classifier

**Status: Complete** (2026-06-10)

## Model

`gbm` ([models/classifier.py](../earnings_engine/models/classifier.py)):
LightGBM binary classifier on the 16 Phase 2 features, wrapped in Platt
(sigmoid) calibration via `CalibratedClassifierCV(cv=3)`.

- **Why LightGBM:** strong default for small noisy tabular data; handles the
  dataset's structural NaNs (first-event history, NSE surprise gaps) natively.
- **Why calibration:** Phase 3 showed the baseline's confidence was unusable —
  filtering to "high confidence" trades hurt. The whole point of this model is
  that P(up) is a real confidence, so a threshold creates a quality dial.
- **Hyperparameters** are conservative and fixed (no tuning yet): 120 trees,
  lr 0.05, ≤7 leaves, depth ≤3, min 30 samples/leaf, 0.8 row/col subsampling,
  λ=5. Calibration is skipped below 150 training rows (cv splits too thin).
- Registered in [models/registry.py](../earnings_engine/models/registry.py);
  CLI default model is now `gbm`.

## Evaluation protocol

Identical walk-forward backtest as Phase 3 (quarterly folds, refit per fold,
10 bps cost). Nothing model-specific in evaluation — same folds, same costs,
same metrics as the baselines.

## Results — 8-ticker smoke universe (216 tested events)

| Model | Threshold | Coverage | Hit rate | Avg trade | Sharpe/event |
|---|---|---|---|---|---|
| past_up_rate | 0.50 | 100% | 52.8% | +0.37% | 0.077 |
| past_up_rate | 0.60 | 54% | 49.6% | +0.07% | 0.015 |
| gbm | 0.50 | 100% | 49.1% | +0.15% | 0.032 |
| gbm | 0.55 | 52% | 49.6% | +0.10% | 0.020 |
| **gbm** | **0.60** | **25%** | **57.4%** | **+0.99%** | **0.215** |

**Honest reading:**

- At full coverage the GBM is at chance — 216 training-eligible events across
  8 tickers is far too small for 16 features; the baseline's single strong
  prior wins there.
- The calibration works: GBM confidence is *monotone* (higher threshold →
  higher hit rate), the exact property the baseline lacked. At 0.6 it trades
  1 in 4 events at 57.4% hit and ~1% per trade after costs.
- n=54 trades at that threshold — promising, not proof. The required next
  step is the full ~100-ticker ingest (→ several thousand events), then rerun
  this table. Numbers here define the *protocol*, not an expectation.

## Results — full universe (4,182 events / 95 tickers, 2,511 tested)

Added after the Phase 5 full ingest:

| Model | Threshold | Coverage | Hit rate | Avg trade | Sharpe/event |
|---|---|---|---|---|---|
| past_up_rate | 0.50 | 100% | **52.3%** | +0.06% | 0.010 |
| gbm | 0.50 | 100% | 49.7% | −0.10% | −0.018 |
| gbm | 0.55 | 0.3% (7 trades) | 42.9% | +2.12% | 0.216 |

**Honest reading at scale:** the calibrated GBM pushes nearly all its
probabilities to ~0.5 — it is correctly reporting that the current 16
price/history features carry no strong per-event directional edge. The
8-ticker result above was small-sample optimism. `past_up_rate` keeps a
modest +3.2pp hit-rate edge over chance but earns roughly zero after 10 bps
costs. Conclusion: the pipeline is sound and leak-free; the *features* are
the binding constraint. The highest-value additions are options-implied
moves, estimate revisions, and proper NSE announcement dates (see Phase 5
doc, future directions).

## Known limitations

- No hyperparameter tuning (would need nested walk-forward to stay honest).
- Features are price/history only — no estimates revisions, options-implied
  moves, or sector context yet.
- Calibration is refit per fold on small trains; early folds may be rough.
- Single-name short side assumed frictionless (NSE intraday shorting differs).

## Verification

24/24 tests pass. Classifier-specific: learns a planted signal (>65% accuracy,
planted driver tops feature importances), NaN robustness, calibration skipped
on small trains, monotone confidence (high-confidence bucket hits more than
low), registry lookups.

## Usage

```bash
.venv/bin/earnings-engine backtest --model gbm                # full coverage
.venv/bin/earnings-engine backtest --model gbm --threshold 0.6
.venv/bin/earnings-engine backtest --model past_up_rate       # baseline comparison
```

## Next: Phase 5 — Prediction CLI + reports

`predict`: train on all labeled events, score upcoming earnings (direction +
calibrated confidence). `report`: HTML/CSV output. Deliverable doc: user guide.
