# Earnings Engine — Commonly Used Commands

## Data Ingestion

### Ingest everything (prices + earnings + NSE calendar + market caps)
```bash
earnings-engine ingest --market NSE_ALL
```

### Ingest only NSE top stocks
```bash
earnings-engine ingest --market IN
```

### Force reload (ignore cache, re-download everything)
```bash
earnings-engine ingest --market NSE_ALL --force
```

### Ingest only prices (skip earnings + NSE calendar)
```bash
earnings-engine ingest --market NSE_ALL --no-earnings --no-nse-calendar
```

### Ingest only earnings dates (skip prices)
```bash
earnings-engine ingest --market NSE_ALL --no-prices
```

### Ingest only the NSE result calendar (official NSE event-calendar API)
```bash
earnings-engine ingest --market NSE_ALL --no-prices --no-earnings
```

### Ingest specific tickers
```bash
earnings-engine ingest --ticker TCS.NS INFY.NS RELIANCE.NS
```

### Ingest from a custom universe file
```bash
earnings-engine ingest --universe-file my_stocks.txt
```

### Ingest only earnings that are missing (incremental — faster)
```bash
earnings-engine ingest --market NSE_ALL --incremental
```

### Ingest institutional shareholding & AMFI fund portfolios
```bash
# Ingest corporate shareholding patterns & discovered institutional entities for top 500 equities
earnings-engine ingest-institutional --limit 500

# Force re-ingest and bypass cache freshness
earnings-engine ingest-institutional --limit 500 --force --rate-limit 2.0
```

### View data coverage (dashboard tab)
Open the dashboard (`earnings-engine dashboard`) → **📊 Data Coverage** tab for per-ticker price/earnings coverage; use **⚡ Fetch Missing Earnings** to fetch only missing earnings. API: `GET /api/v1/dashboard/data-coverage?market=` and `POST /api/v1/dashboard/earnings/incremental`.

## Reports

### Generate upcoming-results report (all sources — shows both yfinance + NSE dates)
```bash
earnings-engine upcoming-results --market NSE_ALL --days 7 --source all
```

### Generate from a specific start date (e.g. next week's calendar)
```bash
earnings-engine upcoming-results --market NSE_ALL --start-date 2026-08-11 --days 7
```

### Verify a generated report against the database (checker subworkflow)
```bash
earnings-engine upcoming-results --market NSE_ALL --days 7 --check
```

  <!-- I have filters and sorting on all individual columns in the table, e.g. I wanna be filter out market cap<1000 IN the dashboard -->
### Check an existing report CSV against the database
```bash
earnings-engine check-report --csv reports/output/upcoming-results-2026-08-04.csv
```

### Generate upcoming-results from NSE calendar only
```bash
earnings-engine upcoming-results --market NSE_ALL --days 7 --source nse
```

### Generate upcoming-results from yfinance only
```bash
earnings-engine upcoming-results --market NSE_ALL --days 7 --source yfinance
```

### Generate for NSE top stocks (smaller universe, faster)
```bash
earnings-engine upcoming-results --market IN --days 7 --source all
```

### Generate for US stocks
```bash
earnings-engine upcoming-results --market US --days 7 --source all
```

### Generate for NSE large cap
```bash
earnings-engine upcoming-results --market NSE_LARGE_CAP --days 7 --source all
```

### Generate with a custom look-ahead window
```bash
earnings-engine upcoming-results --market NSE_ALL --days 30 --source all
```

### Show calendar in terminal (no report file)
```bash
earnings-engine calendar --market NSE_ALL --days 7
```

## Predictions

### Predict direction + confidence for upcoming earnings
```bash
earnings-engine predict --market NSE_ALL --days 7
```

### Predict with a specific model
```bash
earnings-engine predict --market NSE_ALL --days 7 --model gbm
```

### Force re-run predictions (ignore today's cache)
```bash
earnings-engine predict --market NSE_ALL --days 7 --force
```

### Run Kronos AI 14-day price prediction (uses CUDA GPU automatically)
```bash
earnings-engine kronos-predict --market IN
```

### Kronos for specific tickers on CUDA GPU
```bash
earnings-engine kronos-predict --ticker TCS.NS INFY.NS RELIANCE.NS --device cuda:0
```

### Force re-run Kronos (ignore today's cache)
```bash
earnings-engine kronos-predict --market IN --force --device cuda:0
```

### Kronos device options
- `--device cuda` or `--device cuda:0` — NVIDIA GPU acceleration (auto-detected by default if CUDA is available)
- `--device cpu` — Force CPU inference
- `--gpu-batch 2` — Number of ticker sequences per GPU forward pass (tuned for 6GB VRAM)
- `EARNINGS_ENGINE_KRONOS_DEVICE=cuda:0` — Environment variable override in `.env`


## Two-Phase Workflow: Cache Predictions, Then Render Reports

The recommended way to run the expensive prediction engines is to **cache them
first**, then **render reports from the cache** — so you can run the models once
and generate reports instantly (or on a schedule) without re-training/re-running.

### Step 1 — Pre-compute and cache predictions (with live progress)
```bash
earnings-engine cache-predictions --market NSE_ALL
```

This runs both engines standalone with per-ticker progress:
- **GBM** earnings-direction predictions → saved to the daily prediction cache.
- **Kronos** 14-day price predictions → saved to the daily cache **and** written
  to the SQLite audit trail, so they appear in the dashboard's **Kronos Audit**
  and **Kronos Latest** tabs.

### Step 2 — Render the report from the cache (no recompute)
```bash
earnings-engine upcoming-results --market NSE_ALL --cache-only
```

`--cache-only` renders purely from today's cached predictions and never runs the
models. If no cache exists yet, the prediction columns are left empty.

### cache-predictions options
```bash
# Only predict stocks with earnings in the next 14 days (~592 instead of 2,390)
earnings-engine cache-predictions --market NSE_ALL --earnings-only --days 14

# Kronos only (skip GBM)
earnings-engine cache-predictions --market NSE_ALL --no-gbm

# GBM only (skip Kronos)
earnings-engine cache-predictions --market NSE_ALL --no-kronos

# Force re-run both engines
earnings-engine cache-predictions --market NSE_ALL --force

# Specific tickers
earnings-engine cache-predictions --ticker TCS.NS INFY.NS RELIANCE.NS

# Custom universe file
earnings-engine cache-predictions --universe-file my_stocks.txt
```

> **Note:** `kronos-predict`, `predict`, and `upcoming-results` are all
> cache-aware. They reuse today's results **per-ticker** before ever re-running a
> model or re-downloading yfinance history:
> 1. **Daily JSON prediction cache** — whatever per-ticker coverage exists is reused.
> 2. **Kronos SQLite audit trail** — today's rows fill remaining gaps (Kronos only).
> 3. Only the **genuinely missing** tickers are computed via the model; the
>    merged result is saved back to the JSON cache and (Kronos) audit trail.
>
> So a re-run of `upcoming-results --market NSE_ALL` reuses the ~588 already
> cached/audited tickers and only fetches yfinance + runs the model for the
> handful genuinely missing (e.g. a newly-listed or previously-failed stock),
> instead of re-running all 592 every time.
>
> **Failed tickers are cached too** — stocks that fail prediction (insufficient
> data, delisted, etc.) are stored as `{"failed": true}` markers so they're NOT
> retried on the next run. This prevents an infinite retry loop.
>
> **Incremental saving** — `cache-predictions` saves to the cache + audit trail
> every 20 forecasts as they complete. If the run is interrupted (Ctrl+C), all
> completed forecasts are preserved. A re-run reuses them and only computes the
> remaining missing tickers.
>
> **Use `--earnings-only`** to limit predictions to stocks with upcoming earnings
> in the next `--days` days (~592 instead of 2,390 for NSE_ALL). This is the
> recommended way to run `cache-predictions` — it's 4x faster and avoids
> downloading yfinance history for stocks that don't have earnings soon.
>
> The dashboard is read-only for AI results: the Results tab merges Kronos from
> the audit trail and GBM from the daily cache, and the Kronos tab reuses cached
> results — so opening the dashboard never re-runs a model.
>
> `--force` bypasses the cache and audit reuse to force a fresh run of all tickers.

## Backtesting

### Run walk-forward backtest
```bash
earnings-engine backtest --model gbm --threshold 0.5 --cost 0.001
```

### Backtest on a specific market
```bash
earnings-engine backtest --market NSE_ALL --model gbm
```

## Dataset

### Build the event dataset (features + labels)
```bash
earnings-engine build-dataset --market NSE_ALL
```

## Dashboard & API

### Start the interactive dashboard (opens in browser)
```bash
earnings-engine dashboard
```

### Start dashboard on a custom port
```bash
earnings-engine dashboard --port 8080
```

### Run the API server directly
```bash
python run_api.py
```

## Email

### Send the latest report via email
```bash
earnings-engine test-email
```

## Tests

### Run the full test suite
```bash
python -m pytest tests/ -q
```

### Run a specific test file
```bash
python -m pytest tests/test_predict.py -q
```

## Playground Scripts

```bash
python playground/01_yfinance_playground.py
python playground/02_nse_playground.py
python playground/03_kronos_playground.py
python playground/04_api_playground.py
```

## Quick Reference — Market Options

| Market | Description |
|---|---|
| `IN` | NSE Top (44 stocks) |
| `US` | US Top (45 stocks) |
| `NSE_ALL` | All NSE stocks (~2,390) |
| `NSE_LARGE_CAP` | NSE stocks with market cap > 1000cr |

## Quick Reference — Source Options

| Source | Description |
|---|---|
| `all` | Both yfinance + NSE calendar (default) |
| `nse` | Official NSE event-calendar only |
| `yfinance` | yfinance per-ticker earnings only |

## Report Output Locations

- **Today's reports**: `reports/output/` (1 file per day, overwritten on re-run)
- **Previous days**: `reports/archive/` (1 file per day per type)
- **Logs**: `logs/` (auto-pruned after 3 days)