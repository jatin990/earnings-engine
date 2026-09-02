# 01 — Project Overview

> Related: [00-index](00-index.md) → [02-data-layer](02-data-layer.md) → [10-data-flow](10-data-flow.md)

**Package:** `earnings-engine` v0.1.0  
**Purpose:** Quantitative equity research engine and intelligence dashboard for NSE India (`.NS`) and US equities.  
**Capabilities:** 1-day LightGBM post-earnings reaction modeling, 14-day Kronos neural forecasting, Multi-Model AI Consensus (OmniRoute), 410+ Institutional flow tracking, 5-Strategy Breakout Radar, and multi-hub FastAPI dashboard.  
**Entry point:** `earnings-engine` CLI (`earnings_engine.cli:cli`)  
**Python:** >= 3.11

## Key Dependencies
- `yfinance>=0.2.40`, `nselib>=2.5.0`, `jugaad-data>=0.35.0` — market and NSE data
- `pandas>=2.0`, `pyarrow>=14.0` — DataFrames and SQLite storage
- `lightgbm>=4.0`, `scikit-learn>=1.4`, `torch` — ML models + calibration + neural forecasting
- `fastapi>=0.100.0`, `uvicorn>=0.23.0`, `jinja2>=3.1.0` — API server, templating, and dashboard
- `click>=8.0` — CLI framework
- `python-dotenv>=1.0`, `pyotp>=2.9.0`, `cryptography>=42.0.0` — configuration, TOTP, and security

## Directory Structure
```
earnings_engine/
├── __init__.py
├── cli.py                    # Click CLI entrypoint (ingest, predict, kronos, backtest, dashboard, etc.)
├── config.py                 # Settings dataclass, OmniRoute config, paths, market_of()
├── dataset.py                # build_ticker_events(), build_dataset(), load_dataset()
├── labels.py                 # compute_reaction() → Reaction dataclass
├── predict.py                # build_upcoming_events(), predict_upcoming() (LightGBM)
├── kronos_predictor.py       # predict_portfolio() — Kronos AI PyTorch / CUDA sequence forecasts
├── logging_utils.py          # SafeStreamHandler, get_logger(), run logs
├── port_utils.py             # Automatic port verification and process killing
├── rate_limits.py            # Sliding-window rate limiter per AI model / provider
├── api/
│   ├── server.py             # FastAPI factory, security middleware, static mount
│   ├── routers/              # Modular routers (stocks, consensus, institutional, breakout, news, etc.)
│   ├── stock_api.py          # Stock intelligence, EPS surprise, valuation
│   ├── dashboard_api.py      # Aggregations, coverage, watchlists
│   └── cancellation.py       # Universal tab request cancellation tokens
├── consensus/                # Multi-Model AI Consensus Engine
│   ├── context_builder.py    # Point-in-time quantitative context builder
│   ├── model_runner.py       # Parallel async queries to OmniRoute / LLM providers
│   ├── aggregator.py         # Consensus voting, price targets, stop losses
│   └── storage.py            # Consensus persistence and outcome audit trail
├── brokers/                  # Broker adapters (Angel One, Zerodha, Dhan, Fyers, TOTP)
├── data/
│   ├── db.py                 # SQLite table creation and connection pooling
│   ├── turso_sync.py         # Watermark-tracked Turso Cloud delta sync
│   ├── prices.py             # Daily OHLCV price ingestion and caching
│   ├── earnings.py           # Earnings history, EPS surprise, calendar
│   ├── amfi_holdings.py      # AMFI mutual fund portfolio ingestion
│   ├── nse_shareholding.py   # Corporate shareholding pattern ingestion
│   ├── institutional_accumulation.py # Institutional flow metrics & cache
│   ├── institutional_catalog.py # 410+ DII/FII/Super Investor entities
│   ├── tri_confluence.py     # Tri-Factor Synergy & Cross-Correlation engine
│   ├── breakout_scanner.py   # 5-strategy breakout scanner and tracking
│   ├── market_pulse.py       # 7-day Participant OI matrix & index metrics
│   ├── news_pipeline.py      # RSS / exchange news ingestion & extraction
│   ├── omniroute_client.py   # Universal OmniRoute AI Gateway client
│   ├── scheduler_engine.py   # Master background scheduler engine
│   └── universe.py           # SQLite-backed universe management
├── features/
│   ├── earnings_features.py  # Historical surprise streaks & beat frequency
│   ├── price_features.py     # 16 technical momentum, volatility & surge metrics
│   └── fundamental_pipeline.py # Fundamental ratio and quality pipelines
├── models/
│   ├── base.py               # DirectionModel ABC
│   ├── baseline.py           # AlwaysUp, PastUpRate heuristics
│   ├── classifier.py         # GBClassifier (LightGBM + Platt calibration)
│   └── registry.py           # Model factory and registry
├── backtest/
│   ├── engine.py             # Walk-forward quarterly backtester
│   ├── breakout_backtest.py  # Breakout strategy backtest engine
│   └── swing_backtest.py     # Swing channel backtest engine
├── reports/
│   ├── render.py             # HTML / CSV report rendering
│   └── templates/            # Jinja2 & HTML templates for dashboard & hubs
├── trading_agents/           # Autonomous financial multi-agent workflows
└── ui/                       # Frontend static assets (CSS, modular JS)
```