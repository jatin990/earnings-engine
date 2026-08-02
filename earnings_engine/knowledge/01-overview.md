# 01 — Project Overview

> Related: [00-index](00-index.md) → [02-data-layer](02-data-layer.md) → [10-data-flow](10-data-flow.md)

**Package:** `earnings-engine` v0.1.0  
**Purpose:** Predict 1-day post-earnings price direction for NSE (India) and US stocks.  
**Pipeline:** Ingest price/earnings data → build labeled event dataset → train direction model → walk-forward backtest → predict upcoming events → render HTML/CSV reports.  
**Entry point:** `earnings-engine` CLI (`earnings_engine.cli:cli`)  
**Python:** >= 3.11

## Key Dependencies
- `yfinance>=0.2.40` — market data
- `pandas>=2.0`, `pyarrow>=14.0` — data frames / parquet
- `lightgbm>=4.0`, `scikit-learn>=1.4` — ML model + calibration
- `click>=8.0` — CLI
- `python-dotenv>=1.0` — env config
- `nsetools>=2.0` — NSE stock list fetching (for `--market NSE_ALL`)

## Directory Structure
```
earnings_engine/
├── __init__.py
├── cli.py                    # Click CLI: ingest, calendar, upcoming-results, build-dataset, backtest, predict, test-email
├── config.py                 # Settings, EmailSettings, paths, market_of()
├── dataset.py                # build_ticker_events(), build_dataset(), load_dataset()
├── labels.py                 # compute_reaction() → Reaction dataclass
├── predict.py                # build_upcoming_events(), predict_upcoming()
├── kronos_predictor.py       # predict_portfolio() — Kronos AI predictions
├── logging_utils.py          # get_logger(), per-run log files
├── emailing.py               # send_report_email()
├── api/
│   ├── server.py             # FastAPI server: REST endpoints
│   └── dashboard_api.py      # Dashboard data aggregation
├── data/
│   ├── earnings.py           # fetch/load/upcoming/ingest earnings
│   ├── prices.py             # fetch/load/store/ingest prices
│   ├── universe.py           # load_universe(), load_all(), market caps
│   ├── market_context.py     # enrich_upcoming_results()
│   ├── predictions.py        # Kronos prediction persistence + audit
│   └── universes/            # nse_top.txt, us_top.txt, nse_all.txt, nse_large_cap.txt, my_watchlist.txt
├── features/
│   ├── earnings_features.py  # EARNINGS_FEATURES, compute_earnings_features()
│   └── price_features.py     # PRICE_FEATURES, compute_price_features()
├── models/
│   ├── base.py               # DirectionModel ABC
│   ├── baseline.py           # AlwaysUp, PastUpRate
│   ├── classifier.py         # GBClassifier (LightGBM + Platt calibration)
│   └── registry.py           # make_model(), MODELS dict
├── backtest/
│   └── engine.py             # BacktestConfig, BacktestResult, run_backtest(), compute_metrics()
├── reports/
│   ├── render.py             # render_predictions(), render_upcoming_results_report(), render_dashboard()
│   └── templates/            # predictions_page, earnings_report_page, card, result_row, dashboard
└── knowledge/                # This knowledge base (chunked)
tests/                         # pytest suite
docs/                          # Phase docs (1-5)
reports/output/                # Generated CSV/HTML (gitignored)
data/cache/                    # Local parquet/SQLite caches (gitignored)