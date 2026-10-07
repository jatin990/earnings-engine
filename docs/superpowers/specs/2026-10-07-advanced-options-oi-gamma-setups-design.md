# Advanced Options Open Interest, Dealer Gamma (GEX), & Algorithmic Setups Engine

> **Design Specification**  
> **Date:** 2026-10-07  
> **Target Subsystems:** `earnings_engine/data/option_chain.py`, `earnings_engine/data/options_chart_engine.py`, `earnings_engine/api/routers/options.py`, `earnings_engine/ui/js/modules/options_hub.js`, `earnings_engine/reports/templates/dashboard/_options.html`, `earnings_engine/reports/templates/hubs/dashboard/_options.html`

---

## 1. Executive Summary & Objectives

The Options Hub requires an institutional-grade quantitative upgrade to transform standard Open Interest (OI) bar charts into an actionable derivatives intelligence suite:
1. **Dealer Gamma Exposure (GEX) as Default**: Visualizing strike-level market-maker inventory positioning, positive vs. negative gamma regimes, and gamma flip pivot levels.
2. **Multi-Mode Chart Switching**:
   - **Mode 1 (Default): Dealer Gamma GEX Profile** — Net GEX per strike with positive (mean-reversion) vs negative (acceleration) zones.
   - **Mode 2: Total OI & Intraday $\Delta\text{OI}$** — Dual clustered bars showing accumulated walls and fresh day-flow accumulation/unwinding.
   - **Mode 3: Net OI Delta ($\text{PE }\Delta\text{OI} - \text{CE }\Delta\text{OI}$)** — Net directional institutional accumulation ladder.
   - **Mode 4: Implied Volatility (IV) Skew & Smile** — CE IV vs PE IV spline curves with ATM volatility spread.
3. **Algorithmic Market Setups Engine (Major Indices)**:
   - Automated detection of high-probability derivatives setups (Gamma Squeeze Breakout, Max Pain Dealer Pin, Put Capitulation Trap, Expected Move $1\sigma$ Rejection, IV Skew Asymmetry).
   - Prioritized for major NSE indices (`NIFTY`, `BANKNIFTY`, `FINNIFTY`, `MIDCPNIFTY`).
4. **VIX & Expected Move Integration**: Real-time India VIX tracking with dynamic $\pm 1\sigma$ and $\pm 2\sigma$ ATM straddle pricing bands.

---

## 2. Quantitative Formulation & Greeks Model

### 2.1 Black-Scholes Greeks Engine
For an option with strike $K$, spot underlying $S$, time-to-expiry $T$ in trading years ($DTE / 365.0$), risk-free rate $r = 0.065$, and implied volatility $\sigma = \text{IV} / 100.0$:

$$d_1 = \frac{\ln(S / K) + (r + \sigma^2 / 2) T}{\sigma \sqrt{T}}, \quad d_2 = d_1 - \sigma \sqrt{T}$$

- **Call Delta ($\Delta_{\text{CE}}$)**: $N(d_1)$
- **Put Delta ($\Delta_{\text{PE}}$)**: $N(d_1) - 1$
- **Gamma ($\Gamma$)**:
  $$\Gamma = \frac{N'(d_1)}{S \sigma \sqrt{T}} = \frac{e^{-d_1^2 / 2}}{S \sigma \sqrt{2\pi T}}$$
- **Theta ($\Theta$)**: Daily decay in ₹ per contract
- **Vega ($\nu$)**: Sensitivity to a 1% change in IV

### 2.2 Dealer Gamma Exposure (GEX)
Assuming dealers/market makers are net short public-purchased calls and puts:
$$\text{Call GEX}_K = \text{CE\_OI}_K \times \Gamma_K \times S^2 \times 0.01$$
$$\text{Put GEX}_K = -\text{PE\_OI}_K \times \Gamma_K \times S^2 \times 0.01$$
$$\text{Net GEX}_K = \text{Call GEX}_K + \text{Put GEX}_K$$

- **Total Net GEX**: $\sum_K \text{Net GEX}_K$
- **Gamma Flip Level**: Price level where Net GEX crosses from positive to negative.
- **Gamma Regimes**:
  - `POSITIVE_GAMMA` ($\text{Total Net GEX} > 0$): Dealers trade against the market (buy dips, sell rallies) $\rightarrow$ dampened volatility, mean reversion, pin risk.
  - `NEGATIVE_GAMMA` ($\text{Total Net GEX} < 0$): Dealers trade with the trend (sell dips, buy rallies) $\rightarrow$ accelerated momentum, gamma squeeze risk, breakout cascade.

### 2.3 Expected Move Bands
$$\text{ATM Straddle} = \text{CE}_{\text{ATM LTP}} + \text{PE}_{\text{ATM LTP}}$$
$$\text{Expected Move Upper } (1\sigma) = S + \text{ATM Straddle}$$
$$\text{Expected Move Lower } (1\sigma) = S - \text{ATM Straddle}$$
$$\text{Tail Move Bounds } (2\sigma) = [S - 1.85 \times \text{ATM Straddle}, \; S + 1.85 \times \text{ATM Straddle}]$$

---

## 3. Algorithmic Derivatives Setups (Major Indices)

The system automatically generates actionable trading setups for `NIFTY`, `BANKNIFTY`, `FINNIFTY`, and `MIDCPNIFTY`:

| Setup ID | Name | Core Conditions | Target & Invalidation |
| :--- | :--- | :--- | :--- |
| `gamma-squeeze` | **Gamma Squeeze Breakout** | Spot breaks Call Wall + Negative GEX regime + CE Change OI $< 0$ (covering) + VIX $> 13.0$ | Long breakout entry; Target = $+1\sigma$ Expected Move; SL = Call Wall $- 0.3\%$ |
| `dealer-pin` | **Dealer Max Pain Pin** | Positive GEX regime + Spot within $\pm 0.6\%$ of Max Pain + VIX $< 13.5$ | Mean-reversion scalp toward Max Pain; Target = Max Pain; SL = $\pm 0.75\%$ from Spot |
| `put-capitulation` | **Put Writer Capitulation** | Spot drops below Put Wall + PE Change OI $< 0$ + VIX $\Delta > +3.0\%$ | Short breakdown; Target = $-1\sigma$ Expected Move; SL = Put Wall $+ 0.3\%$ |
| `straddle-rejection`| **$1\sigma$ Straddle Rejection** | Spot tests $1\sigma$ Expected Move line + Counter OI writing buildup + Positive GEX | Fade scalp back toward Session VWAP / Max Pain; SL = $1\sigma \pm 0.25\%$ |
| `iv-skew-asymmetry` | **IV Skew Tail Scalp** | 25-$\Delta$ Put/Call Skew ratio $> 1.40$ or $< 0.75$ + Volume Surge $> 2\times$ OI | Asymmetric directional tail momentum; R:R $\ge 1:3.5$ |

---

## 4. REST API Contract Upgrades

### `GET /api/v1/options/chain`
Enhancements added to the existing endpoint:
```json
{
  "success": true,
  "data": {
    "symbol": "NIFTY",
    "spot_price": 25012.45,
    "pcr_oi": 1.15,
    "pcr_volume": 0.98,
    "max_pain_strike": 25000.0,
    "sentiment": "NEUTRAL",
    "gamma_profile": {
      "net_gex": 458200.0,
      "gamma_regime": "POSITIVE_GAMMA",
      "gamma_regime_label": "Positive Gamma (Mean Reverting / Dampened Vol)",
      "gamma_flip_strike": 24850.0,
      "peak_call_gex_strike": 25200.0,
      "peak_put_gex_strike": 24800.0,
      "atm_straddle_price": 174.5,
      "expected_move_upper": 25186.95,
      "expected_move_lower": 24837.95
    },
    "vix_profile": {
      "vix_value": 13.15,
      "vix_change_pct": -1.2,
      "vix_regime": "NORMAL_VOL"
    },
    "market_setups": [
      {
        "id": "dealer-pin-25000",
        "title": "Positive Gamma Expiry Pin",
        "type": "MEAN_REVERSION",
        "bias": "NEUTRAL",
        "confidence": 86,
        "entry_zone": "24980 - 25030",
        "stop_loss": 24920.0,
        "target_1": 25000.0,
        "target_2": 25060.0,
        "risk_reward": "1 : 2.5",
        "catalyst": "High positive dealer gamma pin at 25000 strike with subdued VIX (13.15)."
      }
    ],
    "strikes": [
      {
        "strike": 25000,
        "ce_oi": 185000,
        "ce_change_oi": -12000,
        "ce_ltp": 92.5,
        "ce_iv": 12.8,
        "ce_delta": 0.52,
        "ce_gamma": 0.00048,
        "ce_gex": 52400.0,
        "pe_oi": 194000,
        "pe_change_oi": 28000,
        "pe_ltp": 82.0,
        "pe_iv": 13.4,
        "pe_delta": -0.48,
        "pe_gamma": 0.00048,
        "pe_gex": -54900.0,
        "net_gex": -2500.0,
        "net_oi_delta": 40000
      }
    ]
  }
}
```

---

## 5. UI Architecture & Interactive Chart Components

### 5.1 Chart Modes & Visual Encoding
1. **Mode 1: Dealer Gamma GEX (Default Landing)**
   - Green bars ($+ \text{GEX}$) vs Red bars ($-\text{GEX}$) per strike.
   - Zero-line baseline with dashed marker for Gamma Flip Level.
   - Yellow dashed vertical line for Spot ATM.
2. **Mode 2: Total OI & $\Delta\text{OI}$**
   - Clustered bar chart: Call OI (Red), Put OI (Green).
   - Secondary translucent overlay or patterned border for positive/negative $\Delta\text{OI}$.
3. **Mode 3: Net OI Delta ($\Delta\text{PE } - \Delta\text{CE}$)**
   - Center-zero divergent bar chart: Green for Net Bullish change, Red for Net Bearish change.
4. **Mode 4: Implied Volatility (IV) Skew & Smile**
   - Dual line spline: Red line (Call IV) vs Green line (Put IV).
   - Highlight ATM IV anchor.

### 5.2 Top Macro & Gamma Radar HUD
- **Gamma Regime Badge**: 🟢 Positive Gamma (Dampened) / 🔴 Negative Gamma (Volatile Expansion).
- **India VIX Badge**: Real-time VIX + intraday direction.
- **Expected Move ($\pm 1\sigma$) Badge**: Current straddle range $[L, U]$.
- **Derived Setups Card**: Displays primary algorithmic trade setup with entry, SL, TP1, TP2, and catalyst details.

### 5.3 Template Mirroring Contract
Both files will be updated identically:
- `earnings_engine/reports/templates/dashboard/_options.html`
- `earnings_engine/reports/templates/hubs/dashboard/_options.html`

---

## 6. Verification & Test Plan

1. **Unit Tests (`tests/test_option_chain.py`)**:
   - Verify Black-Scholes Greeks calculation ($\Delta, \Gamma, \Theta, \nu$) against benchmark values.
   - Verify GEX calculation, Net GEX summation, and Gamma Flip detection.
   - Verify Expected Move ($1\sigma$) interval arithmetic.
   - Verify algorithmic market setup derivation logic for major indices (`NIFTY`, `BANKNIFTY`).
2. **API Tests (`tests/test_api_options.py`)**:
   - Verify `/api/v1/options/chain` returns `gamma_profile`, `vix_profile`, `market_setups`, and enriched strike Greeks.
3. **Frontend Syntax Validation**:
   - Verify JavaScript modules syntax using `node -c earnings_engine/ui/js/modules/options_hub.js`.
4. **Git Delivery**:
   - Commit all changes directly to `origin/new_report`.
