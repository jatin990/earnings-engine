# Earnings Prediction Engine

Predicts the **1-day post-earnings price direction** (up/down + confidence) for
NSE India and US stocks, using free yfinance data. Standalone research project
with a CLI and report output — not connected to any live trading system.

## Architecture

```
ingest (yfinance → parquet cache)
   └→ event dataset (features + labels, point-in-time)      [Phase 2]
        └→ baseline model + walk-forward backtester          [Phase 3]
             └→ ML classifier (LightGBM, calibrated)         [Phase 4]
                  └→ predict CLI + HTML/CSV reports          [Phase 5]
```

## Phases

| Phase | Deliverable | Doc | Status |
|-------|-------------|-----|--------|
| 1 | Scaffold + data layer (prices, earnings, cache, CLI) | [docs/phase-1-data-layer.md](docs/phase-1-data-layer.md) | ✅ Done |
| 2 | Event dataset: features + 1-day direction labels | docs/phase-2 (feature dictionary) | Pending |
| 3 | Statistical baseline + event backtester | docs/phase-3 (backtest methodology) | Pending |
| 4 | LightGBM classifier + calibration | docs/phase-4 (model card) | Pending |
| 5 | Prediction CLI + reports | docs/phase-5 (user guide) | Pending |

## Quick start

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/earnings-engine ingest            # download prices + earnings dates
.venv/bin/earnings-engine calendar --days 30
.venv/bin/pytest                            # offline test suite
```
