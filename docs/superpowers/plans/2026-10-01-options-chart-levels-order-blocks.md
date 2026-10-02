# F&O Smart Chart, Key Levels, Trendlines & Order Blocks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an institutional-grade trading terminal chart in the Option Chain & F&O Hub (`/dashboard#options`) featuring live intraday candles, VWAP & volatility bands, Opening Range Breakout (ORB-15), Smart Money Order Blocks & Fair Value Gaps (FVG), Derivatives Levels (Max Pain, Call/Put Walls), Algorithmic Trendlines, and actionable "Where to Buy / Where to Sell" tactical trade setups.

**Architecture:** A quantitative Python analytics engine (`earnings_engine/data/options_chart_engine.py`) consumes intraday/daily price bars and computes SMC order blocks, session VWAP, ORB, trendlines, and tactical trade confluence against option chain metrics (Max Pain, Walls). A FastAPI endpoint (`GET /api/v1/options/chart-intelligence`) exposes the data. A TradingView Lightweight Charts canvas in `_options.html` and `options_hub.js` renders the multi-layer chart, overlay controls, and actionable buy/sell HUD deck.

**Tech Stack:** Python 3.11+, FastAPI, Pandas, NumPy, yfinance, TradingView Lightweight Charts v4.1.3, Vanilla JavaScript, Jinja2, Tailwind/CSS.

**Spec:** `docs/superpowers/specs/2026-10-01-options-chart-levels-order-blocks-design.md`

## Global Constraints

- **Anti-Fabrication**: Zero mock/random placeholder data. If data is unavailable or markets are closed, return structured metadata with honest status flags.
- **Suffixed Equities**: Indian equities require `.NS` (`TCS.NS`), indices map to yahoo symbols (`^NSEI`, `^NSEBANK`, etc.).
- **Zero-Token Default**: No LLM inference on chart load; all calculations are deterministic quant algorithms.
- **FastAPI Routing Precedence**: Static routes before parameterized routes.

## Review Focus

- **Non-FNO Equities**: Return clean `NOT_FNO` status without throwing 500 errors.
- **Zero-Volume Intraday Bars**: Guard against division by zero in VWAP when volume is zero.
- **Weekend / Market-Closed States**: Return last available session's historical intraday candles and levels cleanly.
- **Rapid Timeframe Switching**: Gracefully cancel in-flight fetches and cleanly dispose / rebuild Lightweight Chart series without memory leaks or duplicate lines.
- **Empty Order Blocks**: If no swing breaks occur, return empty lists without breaking the frontend chart layers.

---

### Task 1: Quantitative Options & Chart Analytics Engine (`options_chart_engine.py`)

**Files:**
- Create: `earnings_engine/data/options_chart_engine.py`
- Test: `tests/test_options_chart_engine.py`

**Interfaces:**
- Produces: `get_options_chart_intelligence(symbol: str, interval: str = "5m", period: str = "5d", force_refresh: bool = False, settings: Settings | None = None) -> dict[str, Any]`

- [ ] **Step 1: Write the failing unit tests for calculations**

Write `tests/test_options_chart_engine.py` testing:
1. `_calculate_session_vwap`: Computes VWAP and 1.5σ bands accurately.
2. `_calculate_orb`: Detects 09:15-09:30 range and projected targets.
3. `_detect_order_blocks_and_fvg`: Detects bullish/bearish order blocks and FVGs.
4. `_detect_trendlines`: Computes support and resistance trendlines.
5. `_generate_tactical_signals`: Produces "where_to_buy" and "where_to_sell" setups with SL and Targets.

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_options_chart_engine.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Implement `options_chart_engine.py`**

Implement `earnings_engine/data/options_chart_engine.py`:
- Symbol mapping (`NIFTY` -> `^NSEI`, `BANKNIFTY` -> `^NSEBANK`, `FINNIFTY` -> `NIFTY_FIN_SERVICE.NS`, `MIDCPNIFTY` -> `NIFTY_MID_SELECT.NS`, stock -> `SYMBOL.NS`).
- Candlestick data fetching with in-memory TTL caching.
- VWAP calculation with standard deviation bands.
- 15-minute Opening Range Breakout (ORB-15) calculation.
- Smart Money Concepts (SMC): Bullish OB, Bearish OB, and Fair Value Gaps (FVG) with mitigation status.
- Algorithmic trendlines connecting rolling swing pivots.
- Confluence engine uniting derivatives levels (Max Pain, Call Wall, Put Wall, Expected Move) with Order Blocks to output structured `where_to_buy` and `where_to_sell` trade plans.

- [ ] **Step 4: Run test to verify it passes**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_options_chart_engine.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add earnings_engine/data/options_chart_engine.py tests/test_options_chart_engine.py
git commit -m "feat(options): add quantitative chart intelligence and order block analytics engine"
```

---

### Task 2: REST API Endpoint `GET /api/v1/options/chart-intelligence`

**Files:**
- Modify: `earnings_engine/api/routers/options.py`
- Test: `tests/test_api_options.py`

**Interfaces:**
- Consumes: `options_chart_engine.get_options_chart_intelligence`
- Produces: `GET /api/v1/options/chart-intelligence?symbol={symbol}&interval={interval}&period={period}&force_refresh={bool}`

- [ ] **Step 1: Write the failing API router test**

Add test cases in `tests/test_api_options.py`:
- Test `get_chart_intelligence` with `NIFTY` (returns 200 with candles, indicators, smart_money, derivatives_levels, tactical_signals).
- Test `get_chart_intelligence` with invalid/non-FNO symbol (returns 200 with `status: "NOT_FNO"`).

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_api_options.py -k "chart_intelligence" -v`
Expected: FAIL (404 not found)

- [ ] **Step 3: Add endpoint to `earnings_engine/api/routers/options.py`**

Declare `@router.get("/api/v1/options/chart-intelligence")` with async execution via `asyncio.to_thread`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_api_options.py -k "chart_intelligence" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add earnings_engine/api/routers/options.py tests/test_api_options.py
git commit -m "feat(api): add /api/v1/options/chart-intelligence endpoint"
```

---

### Task 3: Options Hub HTML Template Enhancements (`_options.html`)

**Files:**
- Modify: `earnings_engine/reports/templates/hubs/dashboard/_options.html`

**Interfaces:**
- Produces:
  - Timeframe Switcher toolbar `[1m | 5m | 15m | 1h | 1D]`
  - Overlay toggles `[VWAP | Order Blocks | Derivatives Rays | ORB | Trendlines]`
  - Lightweight Chart container `#optionsSmartChartContainer`
  - Tactical "Where to Buy & Where to Sell" HUD cards (`#optBuySignalCard`, `#optSellSignalCard`, `#optRegimeBadge`)

- [ ] **Step 1: Add Chart Toolbar, TV Canvas container, and Tactical HUD Deck**

Update `_options.html` directly below the KPI cards to include:
- Chart controls bar with timeframe pill buttons and layer switch checkboxes.
- High-resolution chart container with loading overlay.
- 3-column Tactical Trade Setup HUD:
  - **Where to Buy (Long Setup)**: Entry Zone, Retest Trigger, Stop Loss, Target 1, Target 2, R:R.
  - **Where to Sell (Short Setup)**: Entry Zone, Resistance Trigger, Stop Loss, Target 1, Target 2, R:R.
  - **Micro-Structure & Regime**: Market bias, PCR, ORB state, and Straddle Expected Move range.

- [ ] **Step 2: Commit**

```bash
git add earnings_engine/reports/templates/hubs/dashboard/_options.html
git commit -m "feat(ui): add smart chart container, controls toolbar, and tactical trade HUD to options hub template"
```

---

### Task 4: Frontend Chart Engine & Layer Rendering (`options_hub.js`)

**Files:**
- Modify: `earnings_engine/ui/js/modules/options_hub.js`

**Interfaces:**
- Produces:
  - `app.initOptionsChart()`
  - `app.loadChartIntelligence(symbol, interval, forceRefresh)`
  - `app.renderSmartLayers(chartData)`
  - `app.updateTacticalHUD(signals, levels, orb)`
  - `app.setOptionTimeframe(tf)`
  - `app.toggleChartLayer(layerName)`

- [ ] **Step 1: Implement Lightweight Chart lifecycle & layer managers**

In `earnings_engine/ui/js/modules/options_hub.js`:
- Initialize TradingView Lightweight Chart with dark theme, candlestick series, and volume series.
- Add VWAP line series + upper/lower standard deviation band series.
- Add horizontal price lines for Max Pain (Amber), Call Wall (Red), Put Wall (Green), Straddle Expected High/Low.
- Draw Order Blocks and FVGs as shaded visual markers or price-line bounds.
- Draw ORB 15m range lines and projected targets.
- Populate Tactical HUD with dynamic Emerald/Rose styling, entry prices, SL, Targets, and R:R ratios.
- Add auto-refresh polling (15 seconds) during active market sessions.

- [ ] **Step 2: Commit**

```bash
git add earnings_engine/ui/js/modules/options_hub.js
git commit -m "feat(ui): implement TV lightweight chart layers, order block overlays, and tactical HUD in options_hub.js"
```

---

### Task 5: End-to-End Verification & Hygiene

**Files:**
- Test: Full targeted test suite

- [ ] **Step 1: Run all options and API tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_options_chart_engine.py tests/test_api_options.py -v`
Expected: ALL PASS

- [ ] **Step 2: Run Error Ledger Scan**

Run: `python scripts/error_ledger.py scan`
Expected: 0 new errors

- [ ] **Step 3: Commit and Push**

```bash
git add .
git commit -m "feat(options): complete advanced F&O smart chart, key levels, and order block execution engine"
git push origin new_report
```
