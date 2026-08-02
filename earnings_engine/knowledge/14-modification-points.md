# 14 — Common Modification Points

> Related: [13-config-env](13-config-env.md) → [15-changelog](15-changelog.md)

| Goal | File(s) to change |
|------|-------------------|
| Add a new feature | `features/price_features.py` or `features/earnings_features.py` + `dataset.py` `FEATURE_COLUMNS` |
| Change label definition | `labels.py` `compute_reaction()` |
| Add a new model | `models/` new class + `registry.py` `MODELS` dict |
| Change backtest logic | `backtest/engine.py` `run_backtest()` or `compute_metrics()` |
| Modify report layout | `reports/templates/*.html` |
| Change report data/formatting | `reports/render.py` |
| Add CLI command | `cli.py` |
| Change cache behavior | `data/prices.py` or `data/earnings.py` |
| Modify universe | `data/universe.py` + `data/universes/*.txt` |
| Change email behavior | `emailing.py` + `config.py` `EmailSettings` |
| Add/change API endpoint | `api/server.py` + `api/dashboard_api.py` |
| Kronos prediction/audit | `data/predictions.py` + `api/dashboard_api.py` + `dashboard.html` |