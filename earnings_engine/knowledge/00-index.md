# Earnings Engine — Knowledge Index

> Master entry point. Read the relevant chunk instead of the whole knowledge base.
> Last updated: 2026-08-02

## How to use this index
1. Find your goal in the **Capability Map** below.
2. Read the listed chunk(s) in order.
3. Follow the **Related** cross-links at the top of each chunk to catch downstream dependencies.

## Chunk list
| Chunk | Contents |
|-------|----------|
| [01-overview](01-overview.md) | Project overview, directory structure, key deps, entry point |
| [02-data-layer](02-data-layer.md) | SQLite schemas + data/ modules (earnings, prices, universe, market_context, predictions) |
| [03-features-labels](03-features-labels.md) | labels.py, price_features, earnings_features |
| [04-models](04-models.md) | models/ (base, baseline, classifier, registry) |
| [05-backtest](05-backtest.md) | backtest/engine.py |
| [06-dataset-predict](06-dataset-predict.md) | dataset.py, predict.py |
| [07-reports](07-reports.md) | reports/render.py + templates |
| [08-api-dashboard](08-api-dashboard.md) | api/server.py, api/dashboard_api.py, kronos_predictor.py |
| [09-cli-config](09-cli-config.md) | cli.py, config.py, logging_utils, emailing |
| [10-data-flow](10-data-flow.md) | Data flow (ingestion, dataset, backtest, prediction, report) |
| [11-notes](11-notes.md) | Implementation notes (point-in-time, freshness, threading, yfinance, templates, quality scale, formatting) |
| [12-tests](12-tests.md) | Test coverage |
| [13-config-env](13-config-env.md) | Configuration & environment |
| [14-modification-points](14-modification-points.md) | Common modification points |
| [15-changelog](15-changelog.md) | Recent changes log |

## Capability Map
| Goal | Read |
|------|------|
| Understand the whole project | 01-overview → 10-data-flow → 11-notes |
| Add a new feature | 03-features-labels + 06-dataset-predict |
| Change label definition | 03-features-labels |
| Add a new model | 04-models |
| Change backtest logic | 05-backtest |
| Modify report layout/data | 07-reports |
| Add CLI command | 09-cli-config |
| Change cache behavior | 02-data-layer |
| Modify universe | 02-data-layer |
| Change email behavior | 09-cli-config |
| Add/change API endpoint | 08-api-dashboard |
| Kronos predictions / audit | 08-api-dashboard + 02-data-layer (predictions) |
| Multi-Model AI Consensus & OmniRoute | 04-models + 08-api-dashboard |
| Institutional Flow & AMFI Catalog | 02-data-layer + 08-api-dashboard |
| Tri-Factor Synergy & Cross-Correlation | 02-data-layer + 08-api-dashboard |
| Breakout Radar & 5-Strategy Scanner | 05-backtest + 08-api-dashboard |
| Market Pulse & Participant OI Matrix | 02-data-layer + 08-api-dashboard |
| Run tests | 12-tests |
| Change env/config | 13-config-env |
| See what changed recently | 15-changelog |

## Dependency chain (follow to avoid missing downstream files)
```
01-overview
  → 02-data-layer
    → 03-features-labels
      → 06-dataset-predict
        → 05-backtest
        → 07-reports
          → 09-cli-config
          → 08-api-dashboard
  → 10-data-flow
  → 11-notes