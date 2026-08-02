# Earnings Engine — Requirements

## Purpose
Predict 1-day post-earnings price direction for NSE (India) and US stocks.

## Pipeline
1. **Ingest** — Download prices (yfinance → SQLite) and earnings dates (yfinance → Parquet)
2. **Build dataset** — For each past earnings event: compute reaction_return, label, price features, earnings features
3. **Backtest** — Walk-forward by earnings_date; train model each fold, evaluate trade simulation
4. **Predict** — Train on all labeled events, score upcoming events
5. **Report** — Render HTML/CSV reports with market context

## Key Constraints
- **Point-in-time**: No future data in features or labels
- **Small datasets**: Conservative hyperparameters, heavy regularization
- **Cache freshness**: 1-day default, `--force` to bypass
- **yfinance quirks**: NSE `.NS` suffix, `fast_info` fallback to `.info`

## Data Schemas
- **Event dataset**: ticker, market, earnings_date, asof_date, reaction_date, reaction_return, label, features
- **Price cache**: SQLite (price_history, ticker_metrics tables)
- **Earnings cache**: Parquet per ticker (earnings_date, eps_estimate, eps_reported, surprise_pct)

## Models
- `always_up` — baseline: predict base rate
- `past_up_rate` — baseline: ticker-specific up-rate shrunk toward global
- `gbm` — LightGBM + Platt calibration

## Quality Scoring (1-9)
- Each quarter scored individually from EPS surprise %
- 3Q = average of individual quarter scores
- 7-9 strong beats, 5-6 in line, 3-4 missed

## Week High/Low
- Computed from previous 3 quarters' earnings dates (±4 business days)
- Shows % move and price in brackets: `+8.7% (120)`

## Report Layout
- Ledger table: 10 collapsed columns (Stock, Date, Market Cap, Price, 30D Return, Week High/Low, 52W High/Low, Quality, Resistance, Support)
- Quality cell: `Q1=4/9 | Q2=9/9 | Q3=6/9 (3Q=6/9)`
- Whole page horizontally scrollable
- Cards show individual Q1/Q2/Q3 scores

## CLI Commands
- `ingest` — download data
- `calendar` — show upcoming earnings
- `upcoming-results` — enrich + render report
- `build-dataset` — build training data
- `backtest` — walk-forward backtest
- `predict` — score upcoming events
- `test-email` — send latest report
