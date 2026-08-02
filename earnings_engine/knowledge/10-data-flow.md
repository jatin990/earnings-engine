# 10 — Data Flow

> Related: [01-overview](01-overview.md) → [02-data-layer](02-data-layer.md) → [11-notes](11-notes.md)

## 5.1 Ingestion
```
CLI ingest
  → prices_mod.ingest_prices(tickers)  → fetch_prices() per ticker → SQLite
  → earnings_mod.ingest_earnings(tickers) → fetch_earnings() per ticker → SQLite
  → universe_mod.ingest_market_caps(tickers) → _fetch_market_cap_for_ticker() per ticker → SQLite
```

## 5.2 Dataset Build
```
CLI build-dataset
  → build_dataset(tickers)
    → build_ticker_events(ticker) per ticker
      → load_prices() + load_earnings()
      → compute_reaction() for each past event → labels
      → compute_price_features() + compute_earnings_features() → features
    → save to SQLite (event_dataset table)
```

## 5.3 Backtest
```
CLI backtest
  → load_dataset()
  → run_backtest(df, model, cfg)
    → walk-forward folds by earnings_date
    → model.fit(train).predict_proba(test)
    → compute_metrics()
```

## 5.4 Prediction
```
CLI predict
  → predict_upcoming(tickers)
    → build_upcoming_events() → feature rows for upcoming events
    → model.fit(train).predict_proba(upcoming)
  → render_predictions() → CSV + HTML
```

## 5.5 Report Rendering
```
CLI upcoming-results
  → upcoming_earnings() → future events from cache
  → enrich_upcoming_results() → add market context (market cap from SQLite cache, prices, earnings)
  → format columns in CLI output
  → render_upcoming_results_report() → load templates/ + substitute placeholders → HTML
```

## 5.6 Dashboard / Kronos
```
GET /api/v1/dashboard/kronos
  → get_kronos_predictions(tickers, lookback, pred_len)
    → kronos_predictor.predict_portfolio()
    → store_prediction() per forecast → SQLite kronos_predictions
GET /api/v1/dashboard/kronos/latest → load_latest_predictions()
GET /api/v1/dashboard/kronos/audit → load_prediction_history()