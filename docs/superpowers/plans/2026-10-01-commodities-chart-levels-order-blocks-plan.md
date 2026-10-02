# Commodities Hub: Smart Chart, Key Levels, Trendlines & Order Blocks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a dedicated institutional-grade Commodities Hub in Earnings Engine featuring live/delayed intraday & daily candlestick charts for precious metals (Gold, Silver) and energy commodities (Crude Oil, Natural Gas, Copper), dynamic Session VWAP ($\pm 1.5\sigma$ bands), Opening Range Breakout (ORB-15), Smart Money Concepts (Order Blocks & Fair Value Gaps), Algorithmic Pivot/ATR Levels, Dynamic Trendlines, Gold/Silver Ratio (GSR), and an actionable 3-column "Where to Buy / Where to Sell" Tactical Trade HUD deck.

**Architecture:** 
1. `earnings_engine/data/commodities_chart_engine.py`: Quantitative Python analytics engine consuming historical/intraday bars via DataProviderManager / Yahoo Finance proxies (`GOLDBEES.NS`, `SILVERBEES.NS`, `GC=F`, `SI=F`, `CL=F`, `NG=F`, `HG=F`) and computing VWAP, ORB-15, SMC order blocks, algorithmic trendlines, ATR volatility bands, and tactical trade confluences.
2. `earnings_engine/api/routers/commodities.py`: FastAPI REST router exposing `/api/v1/commodities/symbols` and `/api/v1/commodities/chart-intelligence`.
3. `earnings_engine/reports/templates/hubs/dashboard/_commodities.html`: Jinja2 partial template with TradingView Lightweight Charts canvas, overlay toggles, asset switcher (Gold, Silver, Crude Oil, Natural Gas, Copper), and 3-column Tactical Trade HUD deck.
4. `earnings_engine/ui/js/modules/commodities.js`: Modular frontend controller coordinating Lightweight Charts rendering, timeframe switching (`1m`, `5m`, `15m`, `1h`, `1d`), live level tags, and auto-refresh intervals.

**Tech Stack:** Python 3.14, FastAPI, Pandas, NumPy, TradingView Lightweight Charts v4.1.3, Jinja2, Tailwind CSS, Vanilla JS.

**Spec:** `docs/superpowers/specs/2026-10-01-commodities-chart-levels-order-blocks-design.md`

## Global Constraints

- **Anti-Fabrication**: Zero mock/random placeholder data. If data is unavailable or market is closed, return structured metadata with honest status flags (`MARKET_CLOSED`, `SNAPSHOT`).
- **Python Path Format**: Always use `./.venv/Scripts/python.exe` with forward slashes in all commands.
- **FastAPI Routing Precedence**: Static routes before parameterized routes in `commodities.py`.
- **Zero-Token Default**: No automatic LLM inference on chart load; all calculations are deterministic quantitative algorithms.
- **Template Mirroring**: Synchronize any shared templates between `reports/templates/dashboard/` and `reports/templates/hubs/dashboard/` if applicable.

---

### Task 1: Quantitative Commodities Analytics Engine (`commodities_chart_engine.py`)

**Files:**
- Create: `earnings_engine/data/commodities_chart_engine.py`
- Create: `tests/test_commodities_chart_engine.py`

**Interfaces:**
- Produces:
  - `get_supported_commodity_symbols() -> list[dict[str, Any]]`
  - `get_commodity_chart_intelligence(symbol: str = "GOLD", interval: str = "5m", period: str = "5d", force_refresh: bool = False, settings: Settings | None = None) -> dict[str, Any]`

- [ ] **Step 1: Write failing unit tests in `tests/test_commodities_chart_engine.py`**
  - Test symbol resolution and proxy mapping (`GOLD` -> `GOLDBEES.NS` / `GC=F`, `SILVER` -> `SILVERBEES.NS` / `SI=F`, `CRUDEOIL` -> `CL=F`).
  - Test `_calculate_session_vwap` with $\pm 1.5\sigma$ dispersion bands.
  - Test `_calculate_orb` for opening 15-minute range breakout targets.
  - Test `_detect_order_blocks_and_fvg` for Bullish/Bearish SMC zones.
  - Test `_detect_trendlines` and algorithmic pivot levels ($P, R_1, R_2, S_1, S_2$).
  - Test `_generate_tactical_signals` producing actionable "Where to Buy" and "Where to Sell" trade setups.

- [ ] **Step 2: Run tests to verify failure**
  - Run: `./.venv/Scripts/python.exe -m pytest tests/test_commodities_chart_engine.py -v`
  - Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Implement `earnings_engine/data/commodities_chart_engine.py`**
  - Implement caching, candle data extraction via DataProviderManager / yfinance.
  - Implement Session VWAP, ORB-15, SMC Order Blocks (with compact `D-OB` / `S-OB` short labels), Fair Value Gaps, Classical Floor Pivots, Dynamic ATR bands, and Gold/Silver Ratio (GSR).
  - Implement tactical trade setup generator with clear risk/reward ratios.

- [ ] **Step 4: Run tests and verify they pass**
  - Run: `./.venv/Scripts/python.exe -m pytest tests/test_commodities_chart_engine.py -v`
  - Expected: PASS.

- [ ] **Step 5: Commit Task 1**
  ```bash
  git add earnings_engine/data/commodities_chart_engine.py tests/test_commodities_chart_engine.py
  git commit -m "feat(commodities): add quantitative commodities chart and smart money analytics engine"
  ```

---

### Task 2: FastAPI REST Router (`earnings_engine/api/routers/commodities.py`)

**Files:**
- Create: `earnings_engine/api/routers/commodities.py`
- Modify: `earnings_engine/api/server.py`
- Test: `tests/test_commodities_api.py`

**Interfaces:**
- Produces:
  - `GET /api/v1/commodities/symbols`
  - `GET /api/v1/commodities/chart-intelligence`

- [ ] **Step 1: Write failing API route tests in `tests/test_commodities_api.py`**
  - Test symbols endpoint returns valid commodities list.
  - Test chart intelligence endpoint returns structured candlestick data, indicators, SMC blocks, and tactical trade deck.

- [ ] **Step 2: Run test to verify failure**
  - Run: `./.venv/Scripts/python.exe -m pytest tests/test_commodities_api.py -v`
  - Expected: FAIL (404 Not Found).

- [ ] **Step 3: Implement router and mount in `server.py`**
  - Create `earnings_engine/api/routers/commodities.py` with parameter validation and exception handling.
  - Mount router `app.include_router(commodities_router, prefix="/api/v1/commodities", tags=["commodities"])` in `server.py`.

- [ ] **Step 4: Run tests and verify they pass**
  - Run: `./.venv/Scripts/python.exe -m pytest tests/test_commodities_api.py -v`
  - Expected: PASS.

- [ ] **Step 5: Commit Task 2**
  ```bash
  git add earnings_engine/api/routers/commodities.py earnings_engine/api/server.py tests/test_commodities_api.py
  git commit -m "feat(commodities): mount commodities API endpoints in server"
  ```

---

### Task 3: Jinja2 Dashboard Template (`_commodities.html`)

**Files:**
- Create: `earnings_engine/reports/templates/dashboard/_commodities.html`
- Create: `earnings_engine/reports/templates/hubs/dashboard/_commodities.html` (mirror)
- Modify: `earnings_engine/reports/templates/dashboard/index.html` (nav tab & container)

**Interfaces:**
- Produces:
  - Top Asset Switcher Bar (Gold, Silver, Crude Oil, Natural Gas, Copper) with live spot quotes and 24h deltas.
  - TradingView Lightweight Charts canvas container `#commoditiesChartCanvas`.
  - Chart Layer Overlay Toggles (VWAP, ORB, Order Blocks, Pivots, Trendlines, GSR).
  - 3-Column Tactical Trade HUD Deck ("Where to Buy", "Market Regime & Momentum", "Where to Sell").
  - Technical Metrics Bar (ATR Volatility, GSR, High/Low range, Pivot Distance).

- [ ] **Step 1: Create `_commodities.html` in both template directories**
  - Build responsive layout following obsidian glass terminal design standards.
  - Add TradingView Lightweight Charts v4.1.3 script loader.

- [ ] **Step 2: Add `#tabBtn-commodities` and container to `dashboard/index.html`**
  - Register `#commodities` in hash navigation and dashboard tabs.

- [ ] **Step 3: Commit Task 3**
  ```bash
  git add earnings_engine/reports/templates/dashboard/_commodities.html earnings_engine/reports/templates/hubs/dashboard/_commodities.html earnings_engine/reports/templates/dashboard/index.html
  git commit -m "feat(commodities): add commodities dashboard template and layout"
  ```

---

### Task 4: Frontend Controller Module (`commodities.js`)

**Files:**
- Create: `earnings_engine/ui/js/modules/commodities.js`
- Modify: `earnings_engine/ui/js/dashboard.js` (tab hook)

**Interfaces:**
- Produces:
  - `commoditiesModule.init()`
  - `commoditiesModule.loadChart(symbol, interval)`
  - `commoditiesModule.renderChart(data)`
  - `commoditiesModule.renderTacticalHUD(data)`
  - `commoditiesModule.toggleOverlay(layerName)`

- [ ] **Step 1: Implement `commodities.js`**
  - Initialize TradingView Lightweight Charts with dark obsidian theme.
  - Render CandlestickSeries, LineSeries (VWAP, upper/lower bands), PriceLines (ORB, Pivots), and Custom Order Block rectangles/markers (`D-OB`, `S-OB`).
  - Render 3-column Tactical Trade HUD deck with exact entry, stop-loss, target 1, target 2, and risk-reward ratios.
  - Add timeframe selector handlers (`1m`, `5m`, `15m`, `1h`, `1d`).

- [ ] **Step 2: Wire tab switching in `dashboard.js`**
  - Hook `#commodities` tab activation to call `commoditiesModule.init()`.

- [ ] **Step 3: Verification & Test Execution**
  - Run unit and API tests: `./.venv/Scripts/python.exe -m pytest tests/test_commodities_chart_engine.py tests/test_commodities_api.py -v`.
  - Run error ledger scan: `./.venv/Scripts/python.exe scripts/error_ledger.py scan`.

- [ ] **Step 4: Commit Task 4**
  ```bash
  git add earnings_engine/ui/js/modules/commodities.js earnings_engine/ui/js/dashboard.js
  git commit -m "feat(commodities): add frontend commodities trading module and Lightweight Charts controller"
  ```
