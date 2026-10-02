# Commodities Hub: Gold, Silver, Energy Smart Chart, Key Levels, Trendlines & Order Blocks Design

**Date:** 2026-10-01  
**Status:** Approved  
**Author:** DeepMind / Nexus Architecture Team  
**Scope:** Commodities Hub (`#commodities` / `tab-commodities`)

---

## 1. Executive Summary

The **Commodities Hub** delivers institutional-grade real-time market intelligence and quantitative technical execution plans for precious metals (Gold, Silver) and major energy commodities (Crude Oil, Natural Gas, Copper). 

The module features a high-density, interactive TradingView Lightweight Charts canvas loaded with dynamic Session VWAP ($\pm 1.5\sigma$ volatility bands), 15-minute Opening Range Breakouts (ORB-15), Smart Money Concepts (Bullish/Bearish Order Blocks and Fair Value Gaps), Algorithmic Pivot/ATR Levels, Dynamic Trendlines, and an actionable 3-column "Where to Buy & Where to Sell" Tactical Trade HUD deck.

---

## 2. Quantitative Engine Specifications (`commodities_chart_engine.py`)

### 2.1 Symbol Mapping & Asset Coverage
The engine supports both Indian liquid instruments (ETFs / NSE commodities) and global benchmark commodity futures:

| Asset | Primary Symbol | Benchmark Future | Underlying Type |
|---|---|---|---|
| **Gold** | `GOLD` (`GOLDBEES.NS`) | `GC=F` (COMEX Gold) | Precious Metal |
| **Silver** | `SILVER` (`SILVERBEES.NS`) | `SI=F` (COMEX Silver) | Precious Metal |
| **Crude Oil** | `CRUDEOIL` (`CRUDEOIL.NS` / proxy) | `CL=F` (WTI Crude Oil) | Energy |
| **Natural Gas** | `NATGAS` | `NG=F` (Henry Hub Gas) | Energy |
| **Copper** | `COPPER` | `HG=F` (COMEX High Grade Copper) | Industrial Metal |

### 2.2 Core Technical & Smart Money Algorithms
1. **Session-Anchored VWAP**:
   $$\text{VWAP}_t = \frac{\sum (P_{\text{typical}, i} \times V_i)}{\sum V_i}, \quad P_{\text{typical}} = \frac{H+L+C}{3}$$
   - Dynamic Standard Deviation Dispersion Bands: $\text{VWAP} \pm 1.5\sigma$.
2. **Opening Range Breakout (ORB-15)**:
   - Evaluates the first 15 minutes of the active trading session to compute $\text{ORB}_{\text{high}}$ and $\text{ORB}_{\text{low}}$.
   - Projects expansion targets: $+1.0\times$ and $+2.0\times$ range width.
3. **Smart Money Concepts (SMC)**:
   - **Bullish Order Block (OB)**: The last down-close candle prior to an impulsive swing break high ($R_{\text{swing}}$), defining a support demand zone.
   - **Bearish Order Block (OB)**: The last up-close candle prior to an impulsive swing break low ($S_{\text{swing}}$), defining a supply resistance zone.
   - **Fair Value Gaps (FVG)**: 3-candle imbalance detection ($\text{Low}(\text{Candle}_1) > \text{High}(\text{Candle}_3)$ for Bullish FVG, $\text{High}(\text{Candle}_1) < \text{Low}(\text{Candle}_3)$ for Bearish FVG) with mitigation tracking.
4. **Algorithmic Trendlines**:
   - Rolling swing pivot detection $(N=5)$ connecting higher lows (Ascending Support) and lower highs (Descending Resistance).
5. **Key Commodity Levels & Ratios**:
   - **Classical Floor Pivots**: Pivot Point ($P$), Resistance ($R_1, R_2, R_3$), Support ($S_1, S_2, S_3$).
   - **Dynamic ATR Volatility Bands**: $14$-period ATR expansion levels above/below current spot.
   - **Psychological Round Numbers**: Dynamic rounding levels based on asset scale (e.g. ₹100 intervals for ETFs, \$50/\$100 for global gold/silver futures).
   - **Gold / Silver Ratio (GSR)**: Spot Gold price divided by Spot Silver price as a macro valuation indicator.
6. **Tactical Trade Confluence Generator**:
   - Compiles technical confluence into concrete, risk-managed setups:
     - **Where to Buy**: Entry Zone, Invalidation Stop-Loss, Target 1, Target 2, Risk/Reward Ratio.
     - **Where to Sell**: Entry Zone, Invalidation Stop-Loss, Target 1, Target 2, Risk/Reward Ratio.
     - **Regime**: Market bias (`BULLISH_CONTINUATION`, `BEARISH_EXHAUSTION`, `RANGE_BOUND`), VWAP alignment, and volatility status.

---

## 3. REST API Contract (`/api/v1/commodities`)

### 3.1 Endpoint: `GET /api/v1/commodities/symbols`
Returns list of supported commodity assets with proxy mapping, names, and categories.

### 3.2 Endpoint: `GET /api/v1/commodities/chart-intelligence`
**Query Parameters**:
- `symbol` (str, default: `"GOLD"`): Commodity identifier.
- `interval` (str, default: `"5m"`): Candle timeframe (`1m`, `5m`, `15m`, `1h`, `1d`).
- `period` (str, default: `"5d"`): Lookback window.
- `force_refresh` (bool, default: `False`): Bypass in-memory cache.

**Response Schema**:
```json
{
  "success": true,
  "symbol": "GOLD",
  "name": "Gold (Spot / ETF)",
  "spot_price": 78450.0,
  "change_24h": 0.85,
  "high_24h": 78900.0,
  "low_24h": 78100.0,
  "gsr": 84.2,
  "candles": [
    {"time": 1727755200, "open": 78200.0, "high": 78350.0, "low": 78150.0, "close": 78300.0, "volume": 12500}
  ],
  "indicators": {
    "vwap": [{"time": 1727755200, "value": 78250.0}],
    "vwap_upper": [{"time": 1727755200, "value": 78420.0}],
    "vwap_lower": [{"time": 1727755200, "value": 78080.0}],
    "orb": {
      "active": true,
      "high": 78400.0,
      "low": 78100.0,
      "target_long_1": 78700.0,
      "target_short_1": 77800.0
    },
    "pivots": {
      "p": 78300.0,
      "r1": 78600.0,
      "r2": 78900.0,
      "s1": 78000.0,
      "s2": 77700.0
    },
    "atr_bands": {
      "upper": 78750.0,
      "lower": 77850.0
    },
    "psychological_levels": [78000.0, 78500.0, 79000.0]
  },
  "smart_money": {
    "order_blocks": [
      {"type": "BULLISH_OB", "top": 78150.0, "bottom": 78080.0, "time": 1727751600, "mitigated": false}
    ],
    "fair_value_gaps": [
      {"type": "BULLISH_FVG", "top": 78300.0, "bottom": 78220.0, "time": 1727753400, "mitigated": false}
    ]
  },
  "trendlines": [
    {"type": "SUPPORT", "start_time": 1727740000, "start_price": 77900.0, "end_time": 1727755200, "end_price": 78200.0}
  ],
  "tactical_signals": {
    "regime": "BULLISH_MOMENTUM",
    "where_to_buy": {
      "entry_zone": "78,100 - 78,180",
      "trigger": "Retest of Bullish Order Block & Session VWAP",
      "stop_loss": 77950.0,
      "target_1": 78600.0,
      "target_2": 78900.0,
      "risk_reward": "1:2.8"
    },
    "where_to_sell": {
      "entry_zone": "78,850 - 78,920",
      "trigger": "Rejection at R2 Pivot & Upper ATR Band",
      "stop_loss": 79050.0,
      "target_1": 78300.0,
      "target_2": 78000.0,
      "risk_reward": "1:3.2"
    }
  }
}
```

---

## 4. Frontend UI & Interaction Architecture

### 4.1 UI Layout (`_commodities.html`)
- **Metric Deck**: Asset Quick Switcher (`GOLD`, `SILVER`, `CRUDE OIL`, `NATURAL GAS`, `COPPER`), Spot Price badge, 24h change, Session High/Low, Gold/Silver Ratio (GSR) card.
- **Controls Toolbar**: Timeframe selectors (`1m`, `5m`, `15m`, `1h`, `1D`), Layer toggle pills (`VWAP`, `Order Blocks`, `Key Levels`, `ORB`, `Trendlines`), Fullscreen toggle button.
- **Chart Canvas**: TradingView Lightweight Charts canvas (`#commoditiesSmartChartCanvas`).
- **Tactical Trade HUD (3-Column Grid)**:
  - **Where to Buy**: Emerald theme, Entry Range, Trigger condition, SL, T1, T2, R:R.
  - **Where to Sell**: Rose theme, Entry Range, Trigger condition, SL, T1, T2, R:R.
  - **Regime & Microstructure**: Market Bias, VWAP distance, Pivot position, ATR status.

### 4.2 State Management & Viewport Preservation (`commodities_hub.js`)
- **15-Second Background Polling**: Updates candles and calculations seamlessly without spinner interruption.
- **Viewport Lock**: Preserves user zoom and scroll offset via `chart.timeScale().getVisibleLogicalRange()` and `setVisibleLogicalRange()`.
- **Fullscreen Expansion**: Full `100vw × 100vh` modal expansion with `Esc` key shortcut and instant resize observer handling.
- **Template Mirror Rule**: Mirrored across `reports/templates/dashboard/_commodities.html` and `reports/templates/hubs/dashboard/_commodities.html`.
- **Sidebar & Router Integration**: Registered in `_sidebar.html`, `dashboard.js` (`TAB_MODULES['commodities']`, `switchTab('commodities')`).

---

## 5. Testing & Validation Strategy

1. **Unit Tests (`tests/test_commodities_chart_engine.py`)**:
   - Test data fetch and symbol resolution for Gold, Silver, Crude Oil.
   - Test VWAP and $\pm 1.5\sigma$ calculations.
   - Test ORB-15 high/low and target projection.
   - Test Order Block and FVG detection.
   - Test Classical Floor Pivots and ATR band projections.
   - Test Tactical Buy/Sell signal generation.
2. **API Tests (`tests/test_api_commodities.py`)**:
   - Test `GET /api/v1/commodities/symbols`.
   - Test `GET /api/v1/commodities/chart-intelligence` for valid symbols and unsupported symbols.
3. **Frontend & Regression Hygiene**:
   - Verify zero console errors, smooth layer toggling, and clean fullscreen exit.
   - Verify `error_ledger.py scan` passes with zero unresolved exceptions.
