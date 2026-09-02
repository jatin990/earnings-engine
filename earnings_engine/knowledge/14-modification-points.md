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
| Add/change API endpoint | `api/server.py` + `api/routers/*.py` + `api/dashboard_api.py` |
| Kronos prediction/audit | `data/predictions.py` + `kronos_predictor.py` + `api/routers/kronos.py` |
| Multi-Model AI Consensus | `consensus/model_runner.py` + `consensus/aggregator.py` + `data/omniroute_client.py` |
| Institutional Tracking | `data/institutional_accumulation.py` + `data/institutional_catalog.py` + `data/amfi_holdings.py` |
| Tri-Factor Synergy Tab | `data/tri_confluence.py` + `api/routers/tri_confluence.py` + `ui/js/modules/tri_confluence.js` + `reports/templates/hubs/dashboard/_tri_confluence.html` |
| Breakout Radar Scanner | `data/breakout_scanner.py` + `backtest/breakout_backtest.py` + `api/routers/breakout.py` |
| Market Pulse & OI Matrix | `data/market_pulse.py` + `data/option_chain.py` + `api/routers/dashboard.py` |
| UI Module logic | `ui/js/modules/*.js` + `ui/js/dashboard.js` |