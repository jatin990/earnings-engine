# Phase 5 — Prediction CLI & Reports (User Guide)

**Status: Complete** (2026-06-10)

## What Phase 5 adds

- **`earnings-engine predict`** — trains the chosen model on every labeled
  event in the dataset, builds feature rows for earnings announcements in the
  next N days (price features as of the latest cached trading day,
  earnings-history features from the labeled dataset), and prints direction +
  calibrated confidence per event, sorted by confidence.
- **Reports** — each predict run also writes `reports/output/predictions-YYYY-MM-DD.csv`
  and a self-contained styled HTML page, unless `--no-report` is passed.

## End-to-end workflow

```bash
# 0. one-time setup
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"

# 1. refresh data (run daily/weekly; cache makes reruns cheap)
.venv/bin/earnings-engine ingest                      # full IN+US universe
.venv/bin/earnings-engine calendar --days 30          # sanity-check the calendar

# 2. rebuild the labeled event dataset
.venv/bin/earnings-engine build-dataset

# 3. validate the model out-of-sample (do this before trusting predictions)
.venv/bin/earnings-engine backtest --model gbm
.venv/bin/earnings-engine backtest --model gbm --threshold 0.6
.venv/bin/earnings-engine backtest --model past_up_rate   # baseline reference

# 4. predict upcoming earnings
.venv/bin/earnings-engine predict --days 14
.venv/bin/earnings-engine predict --market IN --days 30
.venv/bin/earnings-engine predict -t TCS.NS -t AAPL --model past_up_rate
```

## Reading the output

| Column | Meaning |
|---|---|
| `direction` | predicted sign of the close(T−1)→close(T+1) move around the announcement |
| `p_up` | calibrated model probability the move is up |
| `confidence` | max(p_up, 1−p_up) — conviction regardless of side |
| `n_past_events` | how many labeled historical events back this ticker's features |

**Use the backtested threshold.** Phase 4 showed confidence is meaningful but
full-coverage accuracy is ~chance: only predictions above the threshold that
backtested well (0.6 on the smoke universe) deserve attention. Low
`n_past_events` rows lean on price features alone — weigh them less.

## How prediction stays consistent with training

`predict.py` builds upcoming rows with the *same* feature functions as the
training dataset (`compute_price_features`, `compute_earnings_features`) —
the only difference is `asof_date` = latest cached trading day instead of
T−1. Schema drift between train and inference is therefore impossible
without a test failing.

## Operational notes

- **Always `ingest` before `predict`** — predictions are only as fresh as the
  price cache, and the upcoming calendar comes from the cache too.
- yfinance NSE earnings dates can be missing or approximate; cross-check
  critical dates against NSE announcements.
- Reports land in `reports/output/` (gitignored). Open the HTML in a browser.
- Not financial advice; this is a research tool. Reaction window includes a
  full day of market noise on each side of the announcement.

## Verification

27/27 tests pass. Phase 5 coverage: upcoming-row schema matches the training
feature set (no label column), prediction direction consistent with p_up,
confidence sorted and bounded, CSV/HTML report rendering.

## Project complete — future directions

All five phases are done. Natural next steps, in rough order of value:

1. **Scale the universe** (NIFTY 500 / Russell 1000) — more events is the
   single biggest model improvement available.
2. **Better NSE earnings dates** — swap NSE corporate announcements into
   `data/earnings.py`.
3. **New features** — options-implied move, estimate revisions, sector
   relative strength.
4. **Magnitude/volatility heads** — predict size of move for position sizing.
5. **Hyperparameter tuning** with nested walk-forward.
