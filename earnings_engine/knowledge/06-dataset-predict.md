# 06 — Dataset & Prediction

> Related: [03-features-labels](03-features-labels.md) → [05-backtest](05-backtest.md) → [07-reports](07-reports.md)

## `dataset.py`
**Constants:**
- `DATASET_PATH = CACHE_DIR / "dataset.parquet"` — legacy path, kept for migration
- `ID_COLUMNS = ["ticker", "market", "earnings_date", "asof_date", "reaction_date"]`
- `LABEL_COLUMNS = ["reaction_return", "label"]`
- `FEATURE_COLUMNS = PRICE_FEATURES + EARNINGS_FEATURES + ["is_in_market"]`
- `ALL_COLUMNS = ID_COLUMNS + FEATURE_COLUMNS + LABEL_COLUMNS`

**Functions:**
- `_db_path(settings)` / `_connect(settings)` — creates `event_dataset` table
- `_write_dataset(df, settings)` — writes to SQLite, replacing all rows
- `_migrate_from_parquet(settings)` — auto-migrate old `dataset.parquet`
- `build_ticker_events(ticker, settings) -> pd.DataFrame` — one row per past event for one ticker
- `build_dataset(tickers, settings, save=True) -> pd.DataFrame` — concatenate all tickers, sort by `earnings_date`, save to SQLite
- `load_dataset() -> pd.DataFrame` — load from SQLite

## `predict.py`
**Functions:**
- `build_upcoming_events(tickers, settings, days=14) -> pd.DataFrame`
  - Calls `upcoming_earnings()`, then for each event loads prices + earnings, computes features
- `predict_upcoming(tickers, settings, model_name="gbm", days=14) -> pd.DataFrame`
  - Trains on ALL labeled events, scores upcoming ones
  - Returns columns: `ticker`, `market`, `earnings_date`, `asof_date`, `p_up`, `direction`, `confidence`, `n_past_events`, `model`, `train_events`