# Design Spec: Advanced F&O Smart Chart, Key Levels, Trendlines & Order Block Execution Engine

**Date:** 2026-10-01  
**Status:** Approved for Implementation  
**Topic:** Real-time intraday candlestick charting, VWAP, ORB, Smart Money Order Blocks (SMC), Derivatives Levels (Max Pain, Call/Put Walls), Algorithmic Trendlines, and Tactical "Where to Buy / Where to Sell" Signal Generation for NSE Option Chain & F&O Hub.

---

## 1. Overview & Business Intent

The NSE Option Chain & Derivatives Hub (`/dashboard#options`) currently provides strike trees, Max Pain, PCR, and an Open Interest distribution bar chart. 

Traders require a **complete visual execution cockpit** that connects price action directly with derivatives intelligence:
1. Identifying exact **institutional demand and supply zones** (Order Blocks & Fair Value Gaps).
2. Seeing **Derivatives Structural Levels** (Max Pain, Call Wall, Put Wall, Straddle Expected Move) plotted directly on live price candles.
3. Tracking **Intraday Market State** (Session VWAP with $\pm 1\sigma, \pm 2\sigma$ bands, Opening Range Breakout / ORB-15).
4. Receiving unambiguous **"Where to Buy" (Long Setup) & "Where to Sell" (Short Setup)** trade zones with defined Entry, Stop Loss, Target 1, Target 2, and Risk-to-Reward (R:R) metrics.

---

## 2. Architecture & Subsystem Components

```
┌────────────────────────────────────────────────────────────────────────┐
│                        FastAPI REST Layer                              │
│         GET /api/v1/options/chart-intelligence?symbol=NIFTY            │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│               earnings_engine/data/options_chart_engine.py             │
│                                                                        │
│  ┌───────────────────────┐  ┌────────────────────────────────────────┐ │
│  │ Price & Candle Feed   │  │ Intraday Indicator Engine              │ │
│  │ (1m, 5m, 15m, 1h, 1D) │  │ • Session VWAP & Volatility Bands      │ │
│  │ yfinance / Cache / DB │  │ • Opening Range Breakout (ORB-15)      │ │
│  └───────────┬───────────┘  └───────────────────┬────────────────────┘ │
│              │                                  │                      │
│              ▼                                  ▼                      │
│  ┌───────────────────────┐  ┌────────────────────────────────────────┐ │
│  │ Smart Money Concepts  │  │ Derivatives Level Overlay Engine       │ │
│  │ • Bullish/Bearish OB  │  │ • Max Pain, Call Wall, Put Wall        │ │
│  │ • Fair Value Gaps FVG │  │ • ATM Straddle Expected Move Bands     │ │
│  │ • Dynamic Trendlines  │  │ • PCR & Participant Sentiment           │ │
│  └───────────┬───────────┘  └───────────────────┬────────────────────┘ │
│              │                                  │                      │
│              └─────────────────┬────────────────┘                      │
│                                ▼                                       │
│             ┌─────────────────────────────────────┐                    │
│             │ Tactical Confluence Trade Generator │                    │
│             │ • "Where to Buy" (Entry, SL, T1, T2)│                    │
│             │ • "Where to Sell" (Entry, SL, T1,T2)│                    │
│             │ • Regime & Confidence Scoring       │                    │
│             └─────────────────────────────────────┘                    │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ JSON
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                        Frontend UI Subsystem                           │
│  • TradingView Lightweight Charts Canvas (v4.1.3)                      │
│  • Order Block & FVG Shading Layers                                    │
│  • Level Rays: Max Pain, Call Wall, Put Wall, VWAP                     │
│  • Timeframe & Layer Controls [1m|5m|15m|1h|1D] [VWAP|OB|Walls|ORB]    │
│  • Tactical "Where to Buy & Where to Sell" HUD Deck                    │
│  • Unified Strike Distribution Bar Chart & Matrix Table                │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Quantitative Formulation & Algorithms

### 3.1 Intraday Session VWAP & Bands
For intraday bars $i = 1, \dots, N$ of the current trading day:
$$\text{Typical Price } P_i = \frac{\text{High}_i + \text{Low}_i + \text{Close}_i}{3}$$
$$\text{VWAP}_k = \frac{\sum_{i=1}^k P_i \cdot V_i}{\sum_{i=1}^k V_i}$$
$$\sigma_k = \sqrt{\frac{\sum_{i=1}^k V_i \cdot (P_i - \text{VWAP}_k)^2}{\sum_{i=1}^k V_i}}$$
$$\text{Upper Band}_k = \text{VWAP}_k + 1.5 \cdot \sigma_k, \quad \text{Lower Band}_k = \text{VWAP}_k - 1.5 \cdot \sigma_k$$

### 3.2 Opening Range Breakout (ORB-15)
* Captures all candles in the 09:15–09:30 IST window.
* $\text{ORB High} = \max(\text{High}_{09:15\dots09:30})$, $\text{ORB Low} = \min(\text{Low}_{09:15\dots09:30})$.
* $\text{Range} = \text{ORB High} - \text{ORB Low}$.
* Projections:
  * Bullish Targets: $\text{Target}_1 = \text{ORB High} + 1.0 \times \text{Range}$, $\text{Target}_2 = \text{ORB High} + 2.0 \times \text{Range}$.
  * Bearish Targets: $\text{Target}_1 = \text{ORB Low} - 1.0 \times \text{Range}$, $\text{Target}_2 = \text{ORB Low} - 2.0 \times \text{Range}$.

### 3.3 Smart Money Order Blocks & Fair Value Gaps (FVG)
* **Bullish Order Block (OB)**:
  * Identified when a bearish candle is followed by an impulsive upward move ($>1.2 \times \text{ATR}$ or break of recent swing high).
  * Range: $[\text{Low}_{\text{candle}}, \text{High}_{\text{candle}}]$.
  * State: `UNMITIGATED` until a subsequent candle's Low pierces into the block.
* **Bearish Order Block (OB)**:
  * Identified when a bullish candle is followed by an impulsive downward move.
  * Range: $[\text{Low}_{\text{candle}}, \text{High}_{\text{candle}}]$.
  * State: `UNMITIGATED` until a subsequent candle's High pierces into the block.
* **Fair Value Gap (FVG)**:
  * Bullish FVG: $\text{Low}(\text{Candle}_{i}) > \text{High}(\text{Candle}_{i-2})$. Gap range $= [\text{High}_{i-2}, \text{Low}_i]$.
  * Bearish FVG: $\text{High}(\text{Candle}_i) < \text{Low}(\text{Candle}_{i-2})$. Gap range $= [\text{High}_i, \text{Low}_{i-2}]$.

### 3.4 Algorithmic Trendlines
* Rolling 5-bar fractal swing highs and swing lows.
* Resistance line: Formed by connecting the 2 most prominent swing highs.
* Support line: Formed by connecting the 2 most prominent swing lows.

### 3.5 Tactical "Where to Buy & Where to Sell" Signal Generation
Synthesizes the multi-factor confluence score:
* **Long Entry Confluence**:
  * Price near Put Wall (Max Put OI support) OR Bullish Order Block OR Lower VWAP Band.
  * Sentiment $\ge \text{NEUTRAL}$ ($PCR > 0.85$).
  * Stop Loss: Set $0.25\% - 0.50\%$ below the structural support level.
  * Target 1: Max Pain or Session VWAP.
  * Target 2: Call Wall or ORB Breakout Target 2.
* **Short Entry Confluence**:
  * Price near Call Wall (Max Call OI resistance) OR Bearish Order Block OR Upper VWAP Band.
  * Sentiment $\le \text{NEUTRAL}$ ($PCR < 1.15$).
  * Stop Loss: Set $0.25\% - 0.50\%$ above the structural resistance level.
  * Target 1: Session VWAP or Max Pain.
  * Target 2: Put Wall or ORB Breakdown Target 2.

---

## 4. API Endpoint Contract

`GET /api/v1/options/chart-intelligence`

* **Parameters**:
  * `symbol` (str, default: `"NIFTY"`)
  * `interval` (str, default: `"5m"`, options: `"1m"`, `"5m"`, `"15m"`, `"1h"`, `"1d"`)
  * `period` (str, default: `"5d"`)
  * `force_refresh` (bool, default: `false`)

* **Response**:
```json
{
  "success": true,
  "symbol": "NIFTY",
  "underlying_name": "NIFTY 50",
  "interval": "5m",
  "current_price": 24920.50,
  "price_change": 142.30,
  "price_change_pct": 0.57,
  "as_of": "2026-10-01 15:30:00 IST",
  "candles": [
    { "time": 1727754300, "open": 24810.0, "high": 24835.5, "low": 24805.0, "close": 24830.0, "volume": 125400 }
  ],
  "indicators": {
    "vwap": [ { "time": 1727754300, "value": 24822.4 } ],
    "vwap_upper_1": [ { "time": 1727754300, "value": 24865.0 } ],
    "vwap_lower_1": [ { "time": 1727754300, "value": 24780.0 } ],
    "orb": {
      "active": true,
      "time_range": "09:15 - 09:30 IST",
      "high": 24850.0,
      "low": 24790.0,
      "range": 60.0,
      "status": "BREAKOUT_BULLISH",
      "target_1": 24910.0,
      "target_2": 24970.0
    }
  },
  "smart_money": {
    "order_blocks": [
      {
        "id": "ob-bull-1",
        "type": "BULLISH_OB",
        "top": 24815.0,
        "bottom": 24790.0,
        "start_time": 1727757900,
        "mitigated": false,
        "strength": "HIGH",
        "label": "Demand OB"
      }
    ],
    "fvg_gaps": [
      { "type": "BULLISH_FVG", "top": 24860.0, "bottom": 24840.0, "time": 1727761500, "filled": false }
    ],
    "trendlines": [
      { "type": "RESISTANCE", "p1": { "time": 1727756100, "price": 25050.0 }, "p2": { "time": 1727765100, "price": 24980.0 }, "slope": -0.0078, "broken": false }
    ]
  },
  "derivatives_levels": {
    "max_pain": 24900.0,
    "call_wall": 25100.0,
    "call_wall_oi": 14205000,
    "put_wall": 24800.0,
    "put_wall_oi": 15890000,
    "pcr_oi": 1.18,
    "sentiment": "BULLISH",
    "straddle_expected_high": 25060.0,
    "straddle_expected_low": 24780.0
  },
  "tactical_signals": {
    "primary_bias": "BULLISH_MOMENTUM",
    "regime": "⚡ Bullish ORB Breakout above VWAP",
    "confidence_score": 85,
    "where_to_buy": {
      "label": "Aggressive Pullback Long",
      "entry_low": 24840.0,
      "entry_high": 24865.0,
      "trigger": "Retest of Bullish FVG & VWAP +1σ Band",
      "stop_loss": 24795.0,
      "target_1": 24980.0,
      "target_2": 25080.0,
      "risk_reward": "1 : 3.1"
    },
    "where_to_sell": {
      "label": "Exhaustion Supply Short",
      "entry_low": 25110.0,
      "entry_high": 25140.0,
      "trigger": "Rejection at Call Wall (25,100) & Bearish Supply OB",
      "stop_loss": 25165.0,
      "target_1": 24950.0,
      "target_2": 24850.0,
      "risk_reward": "1 : 3.4"
    }
  }
}
```

---

## 5. UI Layout & User Experience

1. **Top Hub Controls**: Symbol search input + quick pills (`NIFTY`, `BANKNIFTY`, `FINNIFTY`, `MIDCPNIFTY`, `RELIANCE`, `HDFCBANK`, etc.) + Expiry dropdown + Strike Range filter.
2. **Chart Control Toolbar**: Timeframe pill switches `[ 1m | 5m | 15m | 1h | 1D ]` + Overlay toggle switches (`VWAP`, `Order Blocks`, `Derivatives Rays`, `ORB`, `Trendlines`) + Auto-refresh indicator (15s live timer).
3. **Interactive TradingView Chart Canvas**: Full-width high-resolution container rendering candlesticks, shaded Order Block / FVG zones, VWAP line, and dashed derivative key levels.
4. **Tactical Action HUD**:
   * **Where to Buy Box**: Emerald themed, showing exact Entry Zone, Trigger, Stop Loss, Target 1, Target 2, and R:R ratio.
   * **Where to Sell Box**: Rose themed, showing exact Short Entry Zone, Resistance Trigger, Stop Loss, Downside Targets, and R:R ratio.
   * **Regime Badge**: Active market structure diagnosis.
5. **Derivatives Lower Deck**:
   * Open Interest Distribution Bar Chart.
   * Complete Strike Tree Matrix (Calls / Puts).
   * Historical Positioning Snapshots.

---

## 6. Verification & Test Plan

1. **Backend Engine Tests (`tests/test_options_chart_engine.py`)**:
   * Test candle parsing and time sorting.
   * Test VWAP calculation with positive volume.
   * Test ORB calculation on 9:15-9:30 window.
   * Test Order Block detection (Bullish/Bearish) and unmitigated tracking.
   * Test Fair Value Gap (FVG) detection.
   * Test Tactical Buy/Sell signal generation.
2. **API Router Tests (`tests/test_api_options.py`)**:
   * Test `GET /api/v1/options/chart-intelligence` with valid symbol.
   * Test parameter validation (`interval`, `period`).
   * Test non-FNO symbols response.
3. **Error Ledger Verification**:
   * Execute `python scripts/error_ledger.py scan` to ensure no uncaught runtime exceptions.
