# Playground — yfinance / NSE / Kronos API sandbox

Interactive scripts for exploring the three data/ML APIs used by earnings-engine:

| Script | API(s) exercised | What you can try |
|--------|------------------|------------------|
| [`01_yfinance_playground.py`](01_yfinance_playground.py) | `yfinance` (prices, info, earnings, dividends, fast_info) | Fetch OHLCV history, spot quotes, fundamentals, earnings calendar, `.NS` suffix quirks |
| [`02_nse_playground.py`](02_nse_playground.py) | `nsetools` + yfinance (`load_nse_all`, `load_nse_large_cap`) | Pull the full NSE stock-code list, filter large caps > 1000 cr, inspect universes |
| [`03_kronos_playground.py`](03_kronos_playground.py) | `kronos_predictor`, `data/predictions` (audit), `api/dashboard_api` | Single-stock 14-day forecast, batch portfolio prediction, audit-trail persistence |
| [`04_api_playground.py`](04_api_playground.py) | FastAPI dashboard endpoints (via `httpx`/`requests`) | Hit `POST /api/v1/dashboard/kronos/run`, `GET .../kronos/latest`, `GET .../kronos/audit` |
| `playground_utils.py` | Shared helpers | ANSI colors, ticker prompts, safe float parsing |

## Recommended order

```bash
# 1. Market data
python playground/01_yfinance_playground.py

# 2. NSE universe (uses nsetools)
python playground/02_nse_playground.py

# 3. Kronos prediction (requires the Kronos model checkpoint + RayCodes_Kronos on disk)
python playground/03_kronos_playground.py

# 4. API endpoints (requires the FastAPI server running)
python run_api.py &
python playground/04_api_playground.py
```

## Quick checks

```bash
python -c "import yfinance; print(yfinance.__version__)"
python -c "from nsetools import Nse; print(len(Nse().get_stock_codes()), 'NSE codes')"
python -c "from earnings_engine.kronos_predictor import predict_single_stock; print(predict_single_stock('RELIANCE.NS'))"
```

## Notes

- **NSE tickers need the `.NS` suffix** for yfinance (`market_of()` infers `"IN"` from it).
- `fast_info` is tried first for market cap; falls back to `.info`.
- The multithreaded ingestion pattern (10 workers, batches of 50, 2s gap) exists to avoid yfinance rate limits — keep that in mind when running bulk scripts.
- Kronos predictions are persisted to the `kronos_predictions` table in `prices.sqlite3` (audit trail). Use `data/predictions.py` to query them.