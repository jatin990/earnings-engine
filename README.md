# Earnings Prediction Engine

A quantitative research engine that predicts the **1-day post-earnings price direction** (up/down with calibrated confidence) for **NSE India and US equities**, built on free Yahoo Finance data. Ships as an installable Python package with a five-command CLI covering the full research workflow: data ingestion → event dataset construction → walk-forward backtesting → prediction → reporting.

> Research tool only — not financial advice and not connected to any execution system.

## Highlights

- **Strict point-in-time discipline.** Every feature is computed exclusively from data available before the announcement; tests tamper with post-event data and assert features are unchanged. The backtester is walk-forward with per-fold refits, so no prediction ever sees its own future.
- **Market-agnostic core.** India vs US is inferred from the ticker suffix (`.NS`); there are no per-market code paths downstream. The current universe is ~50 NSE + ~50 US large caps, defined in editable plain-text files.
- **Calibrated probabilities, honestly reported.** The LightGBM classifier is wrapped in Platt calibration so its confidence is a usable trading filter — and on 4,182 real events it correctly reports that price-history features alone carry little per-event edge, rather than overfitting one.
- **Local-first and cheap to rerun.** All data lands in a per-ticker parquet cache with freshness checks; a full refresh of ~100 tickers takes a few minutes, reruns are near-instant.
- **Fully offline test suite.** 27 tests with Yahoo Finance mocked throughout, including leakage guards, trade-accounting verification via an oracle model, and calibration monotonicity checks.

## Architecture

```
                    ┌─────────────────────────────────────────────┐
                    │                  CLI (click)                │
                    │ ingest · calendar · build-dataset ·         │
                    │ backtest · predict                          │
                    └──────┬──────────────────────────────────────┘
                           │
   ┌───────────────┐   ┌───▼───────────────┐   ┌──────────────────┐
   │  data layer   │   │  event dataset    │   │   models         │
   │  prices.py    ├──▶│  one row per      ├──▶│  base interface  │
   │  earnings.py  │   │  ticker × event:  │   │  always_up       │
   │  universe.py  │   │  16 PIT features  │   │  past_up_rate    │
   │  (parquet     │   │  + 1-day label    │   │  gbm (LightGBM + │
   │   cache)      │   │                   │   │  Platt calib.)   │
   └───────────────┘   └───────────────────┘   └────┬─────────────┘
                                                    │
                                  ┌─────────────────┼──────────────┐
                                  ▼                 ▼              ▼
                          ┌──────────────┐  ┌──────────────┐ ┌───────────┐
                          │ walk-forward │  │ predict      │ │ reports   │
                          │ backtester   │  │ upcoming     │ │ CSV/HTML  │
                          └──────────────┘  └──────────────┘ └───────────┘
```

**Label definition.** Announcement timing (pre-open / post-close / mid-session) is unreliable in free data, so the reaction is measured bracketing the event: `close(T+1) / close(T−1) − 1`, where T is the announcement date. The label is the sign of that return.

**Feature set (16).** Pre-event momentum (5/21/63-day returns), volatility level and expansion, volume surge, 21-day choppiness, position in the 52-week range, plus the ticker's own earnings-reaction history (count, mean/std, up-rate, last reaction, last EPS surprise) and a market indicator. Missing values are left intact — LightGBM handles them natively.

**Backtest protocol.** Events sorted by date; the first 40% seed the train set, then quarterly test windows step forward with a refit each fold. Per event: long if P(up) ≥ threshold, short if P(up) ≤ 1−threshold, else skip; returns are net of a configurable round-trip cost (default 10 bps).

## Installation

Requires Python ≥ 3.11.

```bash
git clone https://github.com/chandewardnyanesh/earnings-engine.git
cd earnings-engine
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

## Usage

```bash
# 1. Refresh data (full IN+US universe; cached, so reruns are cheap)
earnings-engine ingest
earnings-engine calendar --days 30            # sanity-check upcoming events

# 2. Build the labeled event dataset
earnings-engine build-dataset

# 3. Validate out-of-sample before trusting anything
earnings-engine backtest --model gbm
earnings-engine backtest --model gbm --threshold 0.6
earnings-engine backtest --model past_up_rate   # baseline reference

# 4. Score upcoming earnings (also writes CSV + HTML to reports/output/)
earnings-engine predict --days 14
earnings-engine predict --market IN --days 30
earnings-engine predict -t TCS.NS -t AAPL

# 5. Launch interactive dashboard for exploring ticker data
earnings-engine dashboard
```

The `dashboard` command starts the API server and opens the fully interactive dashboard in your browser. It provides:
- Ticker search with autocomplete
- Interactive price charts (line/candlestick with SMA/EMA/volume indicators)
- Earnings history with surprise percentages and sorting/filtering
- Market context (market cap, 52-week high/low, earnings scores, support/resistance)
- Watchlist management (saved to localStorage)
- Multi-ticker comparison
- CSV data export
- Dark/light theme toggle
- Auto-refresh every 5 minutes
- Fully responsive mobile design

The dashboard is served at `http://localhost:8000/dashboard` and calls the FastAPI REST endpoints directly. You can also access it manually:

```bash
# Start the API server
python -m earnings_engine.api.server

# Then open the dashboard
open http://localhost:8000/dashboard
```

```
ticker market earnings_date direction confidence  p_up  n_past_events
  ORCL     US    2026-06-10        UP      50.7% 50.7%             44
  ADBE     US    2026-06-11        UP      50.9% 50.9%             44
```

## Results (walk-forward, 4,182 events / 95 tickers, 2015–2026)

| Model | Threshold | Coverage | Hit rate | Avg trade (net) |
|---|---|---|---|---|
| always_up | 0.50 | 100% | 49.5% | ~0 |
| past_up_rate | 0.50 | 100% | **52.3%** | +0.06% |
| gbm (calibrated) | 0.50 | 100% | 49.7% | −0.10% |

The candid takeaway: ticker-level reaction history carries a real +3.2pp hit-rate edge over chance, but it does not survive realistic costs, and the calibrated classifier concentrates its probabilities near 50% — correctly signalling that the current feature set has no strong per-event directional edge. The value of the project is the leak-free evaluation pipeline; the roadmap below targets the features most likely to add edge.

## Documentation

### Core Documentation

Each build phase has a detailed design document:

| Doc | Covers |
|---|---|
| [docs/phase-1-data-layer.md](docs/phase-1-data-layer.md) | Data sources, parquet cache design, schemas, known data gotchas |
| [docs/phase-2-features-labels.md](docs/phase-2-features-labels.md) | Full feature dictionary, label rationale, point-in-time guarantees |
| [docs/phase-3-backtest-baseline.md](docs/phase-3-backtest-baseline.md) | Walk-forward methodology, baseline models, trade simulation |
| [docs/phase-4-model-card.md](docs/phase-4-model-card.md) | Model card: architecture, calibration, results, limitations |
| [docs/phase-5-user-guide.md](docs/phase-5-user-guide.md) | End-to-end user guide and operational notes |

### API Server Documentation

- **[API_README.md](API_README.md)** - Complete guide to the FastAPI REST server, including setup, all endpoints, usage examples, and Postman integration
- **[POSTMAN_GUIDE.md](POSTMAN_GUIDE.md)** - Detailed Postman setup guide with example requests and test scenarios

**Quick API Start:**
```bash
# Start the API server
python -m earnings_engine.api.server

# Visit interactive docs
open http://localhost:8000/docs
```

## Testing

```bash
.venv/bin/pytest
```

All 27 tests run offline (network mocked). Notable coverage: point-in-time immutability of features, fold chronology in the backtester, exact trade accounting verified against an oracle model, probability-calibration monotonicity, cache freshness and empty-result handling, mixed-timezone earnings timestamps.

## Roadmap

1. **Universe scale-up** — NIFTY 500 / Russell 1000 for an order of magnitude more events.
2. **Better NSE earnings dates** — replace Yahoo's patchy NSE calendar with exchange corporate announcements (the data layer is designed for this swap).
3. **Edge-bearing features** — options-implied expected move, analyst estimate revisions, sector relative strength.
4. **Magnitude & volatility heads** — predict move size for position sizing and event-vol strategies.
5. **Hyperparameter search** under nested walk-forward.

## Limitations

- Yahoo Finance NSE earnings dates can be missing or approximate; verify critical dates against exchange filings.
- The reaction window includes a full day of market noise on each side of the announcement.
- Short-side simulation assumes frictionless shorting, which differs from NSE intraday reality.

## License

MIT
