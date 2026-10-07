# CLAUDE.md - Nexus Intelligence Platform (Earnings Engine)
> Quantitative equity research and operations platform for NSE India (.NS) and US equities. Single source of truth. CLI: COMMANDS.md.

## 1. Core Hubs and Architecture
- Market and Quant: 13,133+ PIT dataset, LightGBM + Platt scaling (1-day reaction), Kronos AI (14-day PyTorch forecast), AI Consensus (DeepSeek-R1, Llama-3.3-70B, Qwen-2.5-72B, Mistral-Large via OmniRoute).
- Scanners and Radar: Breakout (/dashboard#breakout), Swing (#swing), Tri-Confluence (#tri-confluence), Options OI (#options), Premarket (#premarket), News (#news), Trading Agents (#trading-agents).
- Institutional Forensics: Shareholding patterns, QoQ fund accumulation, AMFI portfolio tracking, quarantine (#institutional).
- Operations and Lifestyle: Net Worth (/net-worth), Credit Cards (/credit-cards), Trips (/trips), Zepto P&L (/zepto).
- Security and Auth: Portal (/portal), Passcode (NEXUS-<CODE>), 6-digit OTP, HMAC-SHA256 sessions, RBAC.

## 2. Critical Operating Rules
- Git Branch and Push: Work directly on new_report. Always commit and push directly to origin/new_report upon task completion. Follow conventional commits (feat:, fix:, etc.) + co-authorship.
- Error Ledger: Pre-task: ./.venv/Scripts/python.exe scripts/error_ledger.py open. Post-task: scripts/error_ledger.py scan. Resolution: scripts/error_ledger.py resolve <id> "<details>". Use forward slashes in ./.venv/Scripts/python.exe.
- Point-in-Time (PIT): Zero future leak in features/, dataset.py, backtest/. Event date T uses prices <= T-1 (prices.loc[prices.index <= asof_date]). Reaction: (close(T+1) / close(T-1)) - 1. Label: 1 if reaction > 0 else 0 (None if missing bars or gap > 10d). Chronological walk-forward splits with per-fold retraining.
- Timeframe and Freshness: Every metric, delta, signal, flow, and prediction MUST explicitly state window/baseline in backend and UI (e.g. 7D Return, QoQ (~90d), 5D vs 63D avg, 14-Day Horizon, Live Quote, EOD Snapshot, timestamp).
- Anti-Fabrication: Zero mock/dummy/hash data. Return None, 0.0, or [] with truthful status (Market Closed, No Filings On Record).
- On-Demand AI: Zero automatic LLM inference on load/render. Default 0 tokens. AI inference runs strictly on explicit user action.
- Turso Sync (SYNC_TABLES): Local SQLite (data/cache/prices/prices.sqlite3 / earnings_engine.db) replicates to Turso via earnings_engine/data/turso_sync.py. For any new table: (1) Add to SYNC_TABLES, (2) Add date/timestamp col to WATERMARK_CANDIDATE_COLUMNS (and DATE_ONLY_COLUMNS if YYYY-MM-DD), (3) Ensure INSERT OR IGNORE compatibility. Always wrap Turso calls with local SQLite fallback.
- FastAPI Routes: Define static/literal routes before parameterized routes (e.g. /quotes before /{symbol}).
- Tickers: Indian equities require .NS (TCS.NS), US have no suffix. Resolve via market_of(ticker) from earnings_engine.config.
- Testing and Hygiene: Targeted tests only (./.venv/Scripts/python.exe -m pytest tests/<file>.py -k "<test>"), never slow E2E/full-suite during iteration. Batch tool calls. Bound outputs (head_limit, offsets). Persist new schemas/contracts to .claude/projects/.../memory/.
- Model Tiers: ANTHROPIC_DEFAULT_SONNET_MODEL / ANTHROPIC_DEFAULT_HAIKU_MODEL ('claude only' / 'gemini-3.8-fast' / 'gemini-3.8-plan') for planning & architecture; ANTHROPIC_SMALL_FAST_MODEL ('free only') for routine/mundane non-intensive tasks; ANTHROPIC_MODEL / ANTHROPIC_DEFAULT_OPUS_MODEL ('gemini-3.7-fast' / 'antigravityonly') for fast coding, test execution, and active workflow.

## 3. Directory Layout
earnings-engine/
- earnings_engine/api/: FastAPI app (server.py) and domain routers (routers/)
- earnings_engine/data/: SQLite pools, turso_sync.py (SYNC_TABLES), scrapers
- earnings_engine/features/: PIT price and earnings features, labels.py
- earnings_engine/models/: LightGBM classifiers, Platt calibration, kronos_predictor.py
- earnings_engine/consensus/: Multi-model AI runner, aggregator, context builder
- earnings_engine/breakout/: Breakout Radar detection and tracking
- earnings_engine/brokers/: Broker APIs (Angel One, Zerodha, Dhan, Fyers, TOTP)
- earnings_engine/trading_agents/: Autonomous execution agents and strategies
- earnings_engine/reports/: Jinja2 templates (dashboard/, stock_detail.html)
- earnings_engine/ui/: Static JS (dashboard.js, stock_detail.js) and CSS
- scripts/: error_ledger.py, verify_and_sync_all_data.py
- tests/: Pytest test suite

## 4. Capability Map

| Task / Goal | Key Files |
| :--- | :--- |
| REST API Route | earnings_engine/api/routers/<domain>.py + mount in server.py |
| New SQLite Table | earnings_engine/data/db.py + data/turso_sync.py (SYNC_TABLES) |
| Feature Engineering | earnings_engine/features/{price,earnings}_features.py + dataset.py |
| Reaction / Label | earnings_engine/features/labels.py (compute_reaction) |
| AI Model in Consensus | earnings_engine/rate_limits.py (AVAILABLE_AI_MODELS) + consensus/model_runner.py |
| Breakout / Swing / Confluence | earnings_engine/breakout/radar.py, data/swing_ranges.py, routers/tri_confluence.py |
| Institutional / AMFI | earnings_engine/data/institutional.py + api/routers/institutional.py |
| Options / Open Interest | earnings_engine/data/options.py + api/routers/options.py |
| Dashboard UI | reports/templates/dashboard/ + earnings_engine/ui/js/dashboard.js |
| Stock Detail View | reports/templates/stock_detail.html + earnings_engine/ui/js/stock_detail.js |
| CLI Command | earnings_engine/cli.py + document in COMMANDS.md |
| Walk-Forward Backtest | earnings_engine/backtest/engine.py |
