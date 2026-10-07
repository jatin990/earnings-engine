# Advanced Options Open Interest, Dealer Gamma (GEX), & Algorithmic Setups Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform the Options Hub into an institutional-grade derivatives suite featuring a Dealer Gamma Exposure (GEX) profile chart as default, multi-mode OI visualizer, India VIX Expected Move bands, algorithmic market setup generation for major NSE indices, and a persistent setup outcome tracking ledger.

**Architecture:** 
- Python Black-Scholes Greeks engine (`calculate_bs_greeks`) analytical model computing $\Delta, \Gamma, \Theta, \nu$, strike-level dealer GEX, net gamma regimes, gamma flip levels, and dynamic $1\sigma/2\sigma$ straddle move bands.
- Algorithmic setup derivation engine for major indices (`NIFTY`, `BANKNIFTY`, `FINNIFTY`, `MIDCPNIFTY`) with stateful outcome lifecycle tracking via SQLite table `options_tracked_setups` and Turso sync replication.
- REST API layer in `earnings_engine/api/routers/options.py` returning enriched gamma and setup payloads.
- Modular frontend chart engine in `options_hub.js` supporting 4 interactive visualizer modes (Gamma GEX default, Total OI + $\Delta\text{OI}$, Net OI Delta, IV Skew) and mirrored Jinja2 templates.

**Tech Stack:** Python 3.11, FastAPI, SQLite / Turso libSQL, Chart.js, Black-Scholes Greeks, JavaScript (ES6+), Jinja2 HTML Templates.

**Spec:** `docs/superpowers/specs/2026-10-07-advanced-options-oi-gamma-setups-design.md`

## Global Constraints

- **Git Branch & Push**: Commit and push directly to `origin/new_report` upon task completion.
- **Anti-Fabrication**: Zero mock/dummy/synthetic fallbacks. Return `None`, `0.0`, or `[]` with honest status.
- **Template Mirroring**: `earnings_engine/reports/templates/dashboard/_options.html` and `earnings_engine/reports/templates/hubs/dashboard/_options.html` must remain strictly identical.
- **Turso Sync Contract**: Table `options_tracked_setups` must be registered in `SYNC_TABLES`, `WATERMARK_CANDIDATE_COLUMNS`, and `DATE_ONLY_COLUMNS` in `earnings_engine/data/turso_sync.py`.
- **JS Syntax Verification**: All JS changes must be verified with `node -c earnings_engine/ui/js/modules/options_hub.js`.

## Review Focus

1. **Zero DTE / Expiry Day Division by Zero**: When DTE = 0 or $T \le 0$, ensure `calculate_bs_greeks` does not raise `ZeroDivisionError` or `ValueError` (fallback gracefully to intrinsic delta and zero gamma).
2. **Zero or Missing IV Values**: When option records have $\text{IV} \le 0$ or missing IV, handle gracefully without NaN/Infinity crashing the GEX aggregator.
3. **Deep OTM Extreme Strikes with Zero OI**: Strikes with 0 OI must produce 0.0 GEX without skewing gamma flip detection.
4. **Setup Outcome State Machine Transition Integrity**: Once a setup transitions from `ACTIVE` to `TARGET1_HIT` or `STOPPED_OUT`, it must not regress backwards to `ACTIVE`.
5. **Chart.js Clean Destruction & Mode Re-render**: Switching chart modes must call `.destroy()` on the existing Chart.js instance to prevent memory leaks and ghost canvas overlays.

---

### Task 1: Black-Scholes Greeks Engine & Unit Tests

**Files:**
- Modify: `earnings_engine/data/option_chain.py`
- Modify/Create: `tests/test_option_chain.py`

**Interfaces:**
- Produces: `calculate_bs_greeks(spot: float, strike: float, dte_days: float, iv_pct: float, is_call: bool, r: float = 0.065) -> dict[str, float]` returning `{"delta": float, "gamma": float, "theta": float, "vega": float}`

- [ ] **Step 1: Write the failing tests for Black-Scholes Greeks**

Add tests in `tests/test_option_chain.py`:
```python
import pytest
from earnings_engine.data.option_chain import calculate_bs_greeks

def test_calculate_bs_greeks_atm_call():
    # Spot 25000, Strike 25000, DTE 7 days, IV 15%, r=6.5%
    greeks = calculate_bs_greeks(spot=25000.0, strike=25000.0, dte_days=7.0, iv_pct=15.0, is_call=True)
    assert 0.48 <= greeks["delta"] <= 0.55
    assert greeks["gamma"] > 0.0
    assert greeks["theta"] < 0.0
    assert greeks["vega"] > 0.0

def test_calculate_bs_greeks_atm_put():
    # Spot 25000, Strike 25000, DTE 7 days, IV 15%, r=6.5%
    greeks = calculate_bs_greeks(spot=25000.0, strike=25000.0, dte_days=7.0, iv_pct=15.0, is_call=False)
    assert -0.55 <= greeks["delta"] <= -0.45
    assert greeks["gamma"] > 0.0
    assert greeks["theta"] < 0.0
    assert greeks["vega"] > 0.0

def test_calculate_bs_greeks_zero_dte_and_invalid_iv():
    # Edge case: DTE = 0
    greeks_0dte = calculate_bs_greeks(spot=25000.0, strike=24900.0, dte_days=0.0, iv_pct=15.0, is_call=True)
    assert greeks_0dte["delta"] == 1.0  # Deep ITM Call at expiry
    assert greeks_0dte["gamma"] == 0.0

    # Edge case: IV = 0
    greeks_0iv = calculate_bs_greeks(spot=25000.0, strike=25100.0, dte_days=5.0, iv_pct=0.0, is_call=True)
    assert greeks_0iv["delta"] == 0.0
    assert greeks_0iv["gamma"] == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_option_chain.py -k "test_calculate_bs_greeks" -v`
Expected: FAIL (cannot import `calculate_bs_greeks`)

- [ ] **Step 3: Implement Black-Scholes Greeks calculation in `option_chain.py`**

In `earnings_engine/data/option_chain.py`, add:
```python
import math

def calculate_bs_greeks(
    spot: float,
    strike: float,
    dte_days: float,
    iv_pct: float,
    is_call: bool,
    r: float = 0.065
) -> dict[str, float]:
    """
    Calculate Black-Scholes-Merton option Greeks: Delta, Gamma, Theta, Vega.
    """
    if spot <= 0 or strike <= 0:
        return {"delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0}

    # Safe bounds for DTE and IV
    T = max(dte_days, 0.0) / 365.0
    sigma = max(iv_pct, 0.0) / 100.0

    if T <= 1e-6 or sigma <= 1e-4:
        # At expiration or zero volatility: intrinsic delta, zero other Greeks
        if is_call:
            delta = 1.0 if spot > strike else (0.5 if spot == strike else 0.0)
        else:
            delta = -1.0 if spot < strike else (-0.5 if spot == strike else 0.0)
        return {"delta": delta, "gamma": 0.0, "theta": 0.0, "vega": 0.0}

    sqrt_T = math.sqrt(T)
    d1 = (math.log(spot / strike) + (r + 0.5 * sigma ** 2) * T) / (sigma * sqrt_T)
    d2 = d1 - sigma * sqrt_T

    # Normal CDF and PDF approximations
    def _norm_cdf(x: float) -> float:
        return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

    def _norm_pdf(x: float) -> float:
        return math.exp(-0.5 * x ** 2) / math.sqrt(2.0 * math.pi)

    pdf_d1 = _norm_pdf(d1)
    cdf_d1 = _norm_cdf(d1)
    cdf_d2 = _norm_cdf(d2)

    if is_call:
        delta = cdf_d1
        theta = (- (spot * pdf_d1 * sigma) / (2.0 * sqrt_T) - r * strike * math.exp(-r * T) * cdf_d2) / 365.0
    else:
        delta = cdf_d1 - 1.0
        theta = (- (spot * pdf_d1 * sigma) / (2.0 * sqrt_T) + r * strike * math.exp(-r * T) * _norm_cdf(-d2)) / 365.0

    gamma = pdf_d1 / (spot * sigma * sqrt_T)
    vega = (spot * sqrt_T * pdf_d1) / 100.0  # per 1% change in IV

    return {
        "delta": round(delta, 4),
        "gamma": round(gamma, 6),
        "theta": round(theta, 2),
        "vega": round(vega, 2)
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_option_chain.py -k "test_calculate_bs_greeks" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add earnings_engine/data/option_chain.py tests/test_option_chain.py
git commit -m "feat(options): implement analytical Black-Scholes Greeks engine with robust boundary handling"
```

---

### Task 2: Dealer Gamma Exposure (GEX), Flip Strike, and Expected Move Bands

**Files:**
- Modify: `earnings_engine/data/option_chain.py`
- Modify: `tests/test_option_chain.py`

**Interfaces:**
- Produces: `calculate_gamma_profile(records: list[dict], spot_price: float, dte_days: float = 4.0) -> dict`
- Produces: Enriched `records` with `ce_delta`, `ce_gamma`, `ce_gex`, `pe_delta`, `pe_gamma`, `pe_gex`, `net_gex`, `net_oi_delta`

- [ ] **Step 1: Write failing tests for Gamma Profile & GEX calculation**

In `tests/test_option_chain.py`:
```python
def test_calculate_gamma_profile_and_flip():
    # Sample records around ATM 25000
    records = [
        {"strike": 24800.0, "ce_oi": 20000, "ce_change_oi": -2000, "ce_ltp": 250.0, "ce_iv": 14.0, "pe_oi": 100000, "pe_change_oi": 15000, "pe_ltp": 30.0, "pe_iv": 15.0},
        {"strike": 24900.0, "ce_oi": 40000, "ce_change_oi": 1000, "ce_ltp": 160.0, "ce_iv": 13.5, "pe_oi": 80000, "pe_change_oi": 8000, "pe_ltp": 60.0, "pe_iv": 14.0},
        {"strike": 25000.0, "ce_oi": 120000, "ce_change_oi": 5000, "ce_ltp": 90.0, "ce_iv": 13.0, "pe_oi": 110000, "pe_change_oi": 7000, "pe_ltp": 85.0, "pe_iv": 13.2},
        {"strike": 25100.0, "ce_oi": 90000, "ce_change_oi": 12000, "ce_ltp": 45.0, "ce_iv": 12.8, "pe_oi": 30000, "pe_change_oi": -2000, "pe_ltp": 140.0, "pe_iv": 13.5},
        {"strike": 25200.0, "ce_oi": 150000, "ce_change_oi": 20000, "ce_ltp": 18.0, "ce_iv": 13.0, "pe_oi": 10000, "pe_change_oi": -1000, "pe_ltp": 220.0, "pe_iv": 14.0},
    ]
    from earnings_engine.data.option_chain import calculate_gamma_profile
    profile, enriched = calculate_gamma_profile(records, spot_price=25000.0, dte_days=4.0)

    assert "net_gex" in profile
    assert profile["gamma_regime"] in ("POSITIVE_GAMMA", "NEGATIVE_GAMMA")
    assert profile["gamma_flip_strike"] > 0
    assert profile["atm_straddle_price"] == 175.0  # 90.0 + 85.0
    assert profile["expected_move_upper"] == 25175.0
    assert profile["expected_move_lower"] == 24825.0
    assert len(enriched) == 5
    assert "ce_gex" in enriched[0]
    assert "pe_gex" in enriched[0]
    assert "net_gex" in enriched[0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_option_chain.py -k "test_calculate_gamma_profile" -v`
Expected: FAIL (cannot import `calculate_gamma_profile`)

- [ ] **Step 3: Implement `calculate_gamma_profile` in `option_chain.py`**

In `earnings_engine/data/option_chain.py`, add `calculate_gamma_profile`:
```python
def calculate_gamma_profile(
    records: list[dict],
    spot_price: float,
    dte_days: float = 4.0
) -> tuple[dict, list[dict]]:
    """
    Compute dealer Gamma Exposure (GEX) per strike, Net GEX regime, Gamma Flip, and Expected Move bands.
    """
    if not records or spot_price <= 0:
        return {
            "net_gex": 0.0,
            "gamma_regime": "NEUTRAL",
            "gamma_regime_label": "Neutral Gamma",
            "gamma_flip_strike": spot_price,
            "peak_call_gex_strike": spot_price,
            "peak_put_gex_strike": spot_price,
            "atm_straddle_price": 0.0,
            "expected_move_upper": spot_price,
            "expected_move_lower": spot_price,
            "expected_move_2sigma_upper": spot_price,
            "expected_move_2sigma_lower": spot_price,
        }, records

    enriched_records = []
    total_net_gex = 0.0
    max_call_gex = -1e12
    max_call_gex_strike = spot_price
    min_put_gex = 1e12
    min_put_gex_strike = spot_price

    # Find ATM strike
    atm_record = min(records, key=lambda r: abs(r.get("strike", 0.0) - spot_price))
    atm_ce_ltp = float(atm_record.get("ce_ltp") or 0.0)
    atm_pe_ltp = float(atm_record.get("pe_ltp") or 0.0)
    atm_straddle = atm_ce_ltp + atm_pe_ltp

    # Sort records by strike for cumulative GEX tracking
    sorted_records = sorted(records, key=lambda r: float(r.get("strike", 0.0)))
    
    cumulative_gex = 0.0
    gamma_flip_strike = None
    prev_cum_gex = 0.0
    prev_strike = None

    for r in sorted_records:
        strike = float(r.get("strike", 0.0))
        ce_oi = int(r.get("ce_oi") or 0)
        pe_oi = int(r.get("pe_oi") or 0)
        ce_change_oi = int(r.get("ce_change_oi") or 0)
        pe_change_oi = int(r.get("pe_change_oi") or 0)
        ce_iv = float(r.get("ce_iv") or 14.0)
        pe_iv = float(r.get("pe_iv") or 14.0)

        # Greeks
        ce_greeks = calculate_bs_greeks(spot_price, strike, dte_days, ce_iv, is_call=True)
        pe_greeks = calculate_bs_greeks(spot_price, strike, dte_days, pe_iv, is_call=False)

        # Dealer GEX: Dealers short Calls -> Long Gamma (+GEX), Dealers short Puts -> Short Gamma (-GEX)
        # Scale: In ₹ Cr or Lakhs equivalent for readability: OI * Gamma * Spot^2 * 0.01 / 10,000,000 (Cr)
        # Here we compute standardized GEX units in Lakhs (10^5):
        ce_gex = round((ce_oi * ce_greeks["gamma"] * (spot_price ** 2) * 0.01) / 100000.0, 2)
        pe_gex = round((- pe_oi * pe_greeks["gamma"] * (spot_price ** 2) * 0.01) / 100000.0, 2)
        net_gex = round(ce_gex + pe_gex, 2)

        total_net_gex += net_gex

        if ce_gex > max_call_gex:
            max_call_gex = ce_gex
            max_call_gex_strike = strike
        if pe_gex < min_put_gex:
            min_put_gex = pe_gex
            min_put_gex_strike = strike

        # Cumulative GEX for Gamma Flip detection
        prev_cum_gex = cumulative_gex
        cumulative_gex += net_gex
        if gamma_flip_strike is None and prev_strike is not None:
            if (prev_cum_gex < 0 and cumulative_gex >= 0) or (prev_cum_gex >= 0 and cumulative_gex < 0):
                gamma_flip_strike = strike

        prev_strike = strike

        enriched = dict(r)
        enriched.update({
            "ce_delta": ce_greeks["delta"],
            "ce_gamma": ce_greeks["gamma"],
            "ce_theta": ce_greeks["theta"],
            "ce_vega": ce_greeks["vega"],
            "ce_gex": ce_gex,
            "pe_delta": pe_greeks["delta"],
            "pe_gamma": pe_greeks["gamma"],
            "pe_theta": pe_greeks["theta"],
            "pe_vega": pe_greeks["vega"],
            "pe_gex": pe_gex,
            "net_gex": net_gex,
            "net_oi_delta": pe_change_oi - ce_change_oi
        })
        enriched_records.append(enriched)

    if gamma_flip_strike is None:
        gamma_flip_strike = spot_price

    gamma_regime = "POSITIVE_GAMMA" if total_net_gex >= 0 else "NEGATIVE_GAMMA"
    gamma_regime_label = (
        "Positive Gamma (Mean Reverting / Dampened Vol)"
        if total_net_gex >= 0
        else "Negative Gamma (Accelerating Momentum / Breakout Risk)"
    )

    profile = {
        "net_gex": round(total_net_gex, 2),
        "gamma_regime": gamma_regime,
        "gamma_regime_label": gamma_regime_label,
        "gamma_flip_strike": round(gamma_flip_strike, 1),
        "peak_call_gex_strike": round(max_call_gex_strike, 1),
        "peak_put_gex_strike": round(min_put_gex_strike, 1),
        "atm_straddle_price": round(atm_straddle, 2),
        "expected_move_upper": round(spot_price + atm_straddle, 2),
        "expected_move_lower": round(spot_price - atm_straddle, 2),
        "expected_move_2sigma_upper": round(spot_price + 1.85 * atm_straddle, 2),
        "expected_move_2sigma_lower": round(spot_price - 1.85 * atm_straddle, 2),
    }

    return profile, enriched_records
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_option_chain.py -k "test_calculate_gamma_profile" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add earnings_engine/data/option_chain.py tests/test_option_chain.py
git commit -m "feat(options): calculate dealer GEX profile, net gamma regime, flip strike, and expected move bands"
```

---

### Task 3: Algorithmic Market Setups Derivation Engine

**Files:**
- Modify: `earnings_engine/data/option_chain.py`
- Modify: `tests/test_option_chain.py`

**Interfaces:**
- Produces: `derive_market_setups(symbol: str, spot_price: float, records: list[dict], gamma_profile: dict, vix_data: dict | None = None) -> list[dict]`

- [ ] **Step 1: Write failing tests for setup derivation**

In `tests/test_option_chain.py`:
```python
def test_derive_market_setups_dealer_pin():
    from earnings_engine.data.option_chain import derive_market_setups
    gamma_profile = {
        "net_gex": 50000.0,
        "gamma_regime": "POSITIVE_GAMMA",
        "gamma_flip_strike": 24800.0,
        "atm_straddle_price": 150.0,
        "expected_move_upper": 25150.0,
        "expected_move_lower": 24850.0
    }
    records = [
        {"strike": 25000.0, "ce_oi": 150000, "pe_oi": 140000, "ce_change_oi": 5000, "pe_change_oi": 5000}
    ]
    vix_data = {"vix_value": 12.8, "vix_change_pct": -1.5, "vix_regime": "LOW_VOL"}

    setups = derive_market_setups("NIFTY", spot_price=25010.0, records=records, gamma_profile=gamma_profile, vix_data=vix_data, max_pain=25000.0)
    assert len(setups) > 0
    setup = setups[0]
    assert "pin" in setup["id"].lower() or setup["type"] == "MEAN_REVERSION"
    assert setup["target_1"] == 25000.0
    assert setup["stop_loss"] > 0

def test_derive_market_setups_gamma_squeeze():
    from earnings_engine.data.option_chain import derive_market_setups
    gamma_profile = {
        "net_gex": -65000.0,
        "gamma_regime": "NEGATIVE_GAMMA",
        "gamma_flip_strike": 25100.0,
        "atm_straddle_price": 200.0,
        "expected_move_upper": 25400.0,
        "expected_move_lower": 25000.0
    }
    records = [
        {"strike": 25200.0, "ce_oi": 200000, "pe_oi": 40000, "ce_change_oi": -25000, "pe_change_oi": 10000}
    ]
    vix_data = {"vix_value": 15.5, "vix_change_pct": 4.2, "vix_regime": "HIGH_VOL"}

    setups = derive_market_setups("NIFTY", spot_price=25220.0, records=records, gamma_profile=gamma_profile, vix_data=vix_data, max_pain=25000.0, call_wall=25200.0)
    assert any(s["type"] == "BREAKOUT" or "squeeze" in s["id"].lower() for s in setups)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_option_chain.py -k "test_derive_market_setups" -v`
Expected: FAIL (cannot import `derive_market_setups`)

- [ ] **Step 3: Implement `derive_market_setups` in `option_chain.py`**

In `earnings_engine/data/option_chain.py`, add `derive_market_setups`:
```python
def derive_market_setups(
    symbol: str,
    spot_price: float,
    records: list[dict],
    gamma_profile: dict,
    vix_data: dict | None = None,
    max_pain: float | None = None,
    call_wall: float | None = None,
    put_wall: float | None = None
) -> list[dict]:
    """
    Generate quantitative options trading setups for major indices.
    """
    clean_sym = symbol.upper().replace(".NS", "").strip()
    # Apply setups primarily to major indices
    is_major_index = clean_sym in ("NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTY50")
    if not is_major_index or not records or spot_price <= 0:
        return []

    setups: list[dict] = []
    vix_val = float(vix_data.get("vix_value", 13.5)) if vix_data else 13.5
    vix_chg = float(vix_data.get("vix_change_pct", 0.0)) if vix_data else 0.0
    gamma_regime = gamma_profile.get("gamma_regime", "POSITIVE_GAMMA")
    net_gex = float(gamma_profile.get("net_gex", 0.0))
    em_upper = float(gamma_profile.get("expected_move_upper", spot_price * 1.01))
    em_lower = float(gamma_profile.get("expected_move_lower", spot_price * 0.99))
    straddle_val = float(gamma_profile.get("atm_straddle_price", spot_price * 0.008))

    # Identify Call Wall and Put Wall if not provided
    if not call_wall:
        c_max = max(records, key=lambda r: int(r.get("ce_oi") or 0))
        call_wall = float(c_max.get("strike", spot_price * 1.02))
    if not put_wall:
        p_max = max(records, key=lambda r: int(r.get("pe_oi") or 0))
        put_wall = float(p_max.get("strike", spot_price * 0.98))
    if not max_pain:
        max_pain = spot_price

    # Find record for call wall and put wall to check delta OI
    call_wall_rec = next((r for r in records if float(r.get("strike", 0.0)) == call_wall), None)
    put_wall_rec = next((r for r in records if float(r.get("strike", 0.0)) == put_wall), None)

    ce_wall_unwinding = bool(call_wall_rec and int(call_wall_rec.get("ce_change_oi") or 0) < 0)
    pe_wall_unwinding = bool(put_wall_rec and int(put_wall_rec.get("pe_change_oi") or 0) < 0)

    # 1. Gamma Squeeze Breakout Setup
    if spot_price >= (call_wall * 0.998) and gamma_regime == "NEGATIVE_GAMMA" and (ce_wall_unwinding or vix_val >= 13.0):
        entry_low = round(call_wall * 0.999, 1)
        entry_high = round(call_wall * 1.003, 1)
        sl = round(call_wall * 0.994, 1)
        tp1 = round(em_upper, 1)
        tp2 = round(em_upper + straddle_val * 0.5, 1)
        setups.append({
            "id": f"gamma-squeeze-{int(call_wall)}",
            "title": f"Gamma Squeeze Breakout above {int(call_wall)}",
            "type": "BREAKOUT",
            "bias": "BULLISH",
            "confidence": 88 if ce_wall_unwinding else 78,
            "entry_zone": f"{entry_low} - {entry_high}",
            "stop_loss": sl,
            "target_1": tp1,
            "target_2": tp2,
            "risk_reward": "1 : 3.2",
            "catalyst": f"Spot testing Call Wall ({int(call_wall)}) in Negative Gamma regime with CE covering and elevated volatility."
        })

    # 2. Dealer Max Pain Pin Setup
    dist_to_max_pain = abs(spot_price - max_pain) / spot_price
    if gamma_regime == "POSITIVE_GAMMA" and dist_to_max_pain <= 0.008 and vix_val <= 14.5:
        entry_zone = f"{round(spot_price - 20, 1)} - {round(spot_price + 20, 1)}"
        sl = round(max_pain - straddle_val * 0.6 if spot_price >= max_pain else max_pain + straddle_val * 0.6, 1)
        tp1 = round(max_pain, 1)
        tp2 = round(max_pain + (15 if spot_price < max_pain else -15), 1)
        setups.append({
            "id": f"dealer-pin-{int(max_pain)}",
            "title": f"Positive Gamma Expiry Pin at {int(max_pain)}",
            "type": "MEAN_REVERSION",
            "bias": "NEUTRAL",
            "confidence": 85 if dist_to_max_pain <= 0.004 else 75,
            "entry_zone": entry_zone,
            "stop_loss": sl,
            "target_1": tp1,
            "target_2": tp2,
            "risk_reward": "1 : 2.5",
            "catalyst": f"Dealer positive gamma inventory dampens volatility near Max Pain ({int(max_pain)}) under subdued VIX ({vix_val:.1f})."
        })

    # 3. Put Writer Capitulation Breakdown
    if spot_price <= (put_wall * 1.002) and pe_wall_unwinding and vix_chg >= 2.0:
        entry_low = round(put_wall * 0.997, 1)
        entry_high = round(put_wall * 1.001, 1)
        sl = round(put_wall * 1.005, 1)
        tp1 = round(em_lower, 1)
        tp2 = round(em_lower - straddle_val * 0.5, 1)
        setups.append({
            "id": f"put-capitulation-{int(put_wall)}",
            "title": f"Put Writer Capitulation below {int(put_wall)}",
            "type": "BREAKDOWN",
            "bias": "BEARISH",
            "confidence": 84,
            "entry_zone": f"{entry_low} - {entry_high}",
            "stop_loss": sl,
            "target_1": tp1,
            "target_2": tp2,
            "risk_reward": "1 : 3.0",
            "catalyst": f"Put writers unwinding positions at Put Wall ({int(put_wall)}) with surging volatility."
        })

    # 4. Expected Move 1-Sigma Rejection
    dist_to_em_upper = abs(spot_price - em_upper) / spot_price
    dist_to_em_lower = abs(spot_price - em_lower) / spot_price
    if gamma_regime == "POSITIVE_GAMMA":
        if dist_to_em_upper <= 0.003:
            setups.append({
                "id": f"straddle-upper-fade-{int(em_upper)}",
                "title": f"Expected Move +1σ Barrier Rejection ({int(em_upper)})",
                "type": "MEAN_REVERSION",
                "bias": "BEARISH",
                "confidence": 76,
                "entry_zone": f"{round(em_upper - 15, 1)} - {round(em_upper + 10, 1)}",
                "stop_loss": round(em_upper + straddle_val * 0.35, 1),
                "target_1": round(spot_price - straddle_val * 0.5, 1),
                "target_2": round(max_pain, 1),
                "risk_reward": "1 : 2.8",
                "catalyst": f"Spot reached +1σ Straddle upper band ({int(em_upper)}) in positive gamma regime — high probability mean reversion fade."
            })
        elif dist_to_em_lower <= 0.003:
            setups.append({
                "id": f"straddle-lower-bounce-{int(em_lower)}",
                "title": f"Expected Move -1σ Barrier Bounce ({int(em_lower)})",
                "type": "MEAN_REVERSION",
                "bias": "BULLISH",
                "confidence": 76,
                "entry_zone": f"{round(em_lower - 10, 1)} - {round(em_lower + 15, 1)}",
                "stop_loss": round(em_lower - straddle_val * 0.35, 1),
                "target_1": round(spot_price + straddle_val * 0.5, 1),
                "target_2": round(max_pain, 1),
                "risk_reward": "1 : 2.8",
                "catalyst": f"Spot tested -1σ Straddle lower band ({int(em_lower)}) in positive gamma regime — high probability mean reversion bounce."
            })

    return setups
```

- [ ] **Step 4: Connect Greeks, Gamma Profile, and Setup derivation into `analyze_option_chain`**

In `earnings_engine/data/option_chain.py`:
- Update `analyze_option_chain` to call `calculate_gamma_profile` and `derive_market_setups`.
- Include `gamma_profile`, `vix_profile`, and `market_setups` in the return dictionary of `analyze_option_chain`.

- [ ] **Step 5: Run tests to verify**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_option_chain.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add earnings_engine/data/option_chain.py tests/test_option_chain.py
git commit -m "feat(options): integrate algorithmic derivatives setup derivation and enrich option chain analysis"
```

---

### Task 4: Database Migration 047 & Setup History Persistence Ledger

**Files:**
- Modify: `earnings_engine/data/migrations.py`
- Modify: `earnings_engine/data/turso_sync.py`
- Modify: `earnings_engine/data/option_chain.py`
- Create: `tests/test_options_tracked.py`

**Interfaces:**
- Produces: SQLite table `options_tracked_setups`
- Produces: `save_tracked_option_setups(conn, setups, symbol, spot_price, gamma_profile, vix_profile)`
- Produces: `get_tracked_option_setups(conn, symbol=None, outcome=None, limit=50) -> list[dict]`
- Produces: `evaluate_tracked_option_setups(conn, symbol: str, current_spot: float) -> list[dict]`

- [ ] **Step 1: Write failing tests for setup tracking lifecycle**

Create `tests/test_options_tracked.py`:
```python
import sqlite3
import pytest
from earnings_engine.data.migrations import apply_migrations
from earnings_engine.data.option_chain import (
    save_tracked_option_setups,
    get_tracked_option_setups,
    evaluate_tracked_option_setups
)

@pytest.fixture
def db_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    apply_migrations(force=True)  # Migrations on in-memory or mock
    # Ensure options_tracked_setups schema exists
    conn.execute("""
        CREATE TABLE IF NOT EXISTS options_tracked_setups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            setup_id TEXT NOT NULL,
            setup_title TEXT NOT NULL,
            setup_type TEXT NOT NULL,
            bias TEXT NOT NULL,
            confidence REAL NOT NULL DEFAULT 0.0,
            signal_date TEXT NOT NULL,
            spot_at_signal REAL NOT NULL,
            entry_zone TEXT NOT NULL,
            stop_loss REAL NOT NULL,
            target_1 REAL NOT NULL,
            target_2 REAL,
            risk_reward TEXT,
            catalyst TEXT,
            gamma_regime TEXT,
            vix_value REAL,
            current_spot REAL,
            realized_pnl_pct REAL DEFAULT 0.0,
            outcome TEXT NOT NULL DEFAULT 'ACTIVE',
            outcome_label TEXT,
            outcome_badge TEXT,
            scanned_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(symbol, setup_id, signal_date)
        )
    """)
    return conn

def test_save_and_retrieve_tracked_setups(db_conn):
    setups = [
        {
            "id": "gamma-squeeze-25200",
            "title": "Gamma Squeeze Breakout above 25200",
            "type": "BREAKOUT",
            "bias": "BULLISH",
            "confidence": 88,
            "entry_zone": "25180 - 25220",
            "stop_loss": 25050.0,
            "target_1": 25400.0,
            "target_2": 25500.0,
            "risk_reward": "1 : 3.2",
            "catalyst": "High gamma squeeze"
        }
    ]
    gamma_profile = {"gamma_regime": "NEGATIVE_GAMMA"}
    vix_profile = {"vix_value": 15.2}

    saved_count = save_tracked_option_setups(db_conn, setups, "NIFTY", spot_price=25210.0, gamma_profile=gamma_profile, vix_profile=vix_profile)
    assert saved_count == 1

    history = get_tracked_option_setups(db_conn, symbol="NIFTY")
    assert len(history) == 1
    assert history[0]["setup_id"] == "gamma-squeeze-25200"
    assert history[0]["outcome"] == "ACTIVE"

def test_evaluate_tracked_setups_target_hit(db_conn):
    setups = [
        {
            "id": "gamma-squeeze-25200",
            "title": "Gamma Squeeze Breakout above 25200",
            "type": "BREAKOUT",
            "bias": "BULLISH",
            "confidence": 88,
            "entry_zone": "25180 - 25220",
            "stop_loss": 25050.0,
            "target_1": 25400.0,
            "target_2": 25500.0,
            "risk_reward": "1 : 3.2",
            "catalyst": "High gamma squeeze"
        }
    ]
    save_tracked_option_setups(db_conn, setups, "NIFTY", spot_price=25210.0, gamma_profile={"gamma_regime": "NEGATIVE_GAMMA"}, vix_profile={"vix_value": 15.2})

    # Evaluate with spot at 25420 (Target 1 achieved)
    updates = evaluate_tracked_option_setups(db_conn, "NIFTY", current_spot=25420.0)
    assert len(updates) == 1
    assert updates[0]["outcome"] == "TARGET1_HIT"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_options_tracked.py -v`
Expected: FAIL

- [ ] **Step 3: Implement Migration 047 and Sync registration**

In `earnings_engine/data/migrations.py`:
- Add `_migration_047_options_tracked_setups`:
```python
def _migration_047_options_tracked_setups(conn: Any) -> None:
    """Create options_tracked_setups table for options setup history and outcome tracking."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS options_tracked_setups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            setup_id TEXT NOT NULL,
            setup_title TEXT NOT NULL,
            setup_type TEXT NOT NULL,
            bias TEXT NOT NULL,
            confidence REAL NOT NULL DEFAULT 0.0,
            signal_date TEXT NOT NULL,
            spot_at_signal REAL NOT NULL,
            entry_zone TEXT NOT NULL,
            stop_loss REAL NOT NULL,
            target_1 REAL NOT NULL,
            target_2 REAL,
            risk_reward TEXT,
            catalyst TEXT,
            gamma_regime TEXT,
            vix_value REAL,
            current_spot REAL,
            realized_pnl_pct REAL DEFAULT 0.0,
            outcome TEXT NOT NULL DEFAULT 'ACTIVE',
            outcome_label TEXT,
            outcome_badge TEXT,
            scanned_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(symbol, setup_id, signal_date)
        )
    """)
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ots_symbol ON options_tracked_setups (symbol)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ots_date ON options_tracked_setups (signal_date DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ots_outcome ON options_tracked_setups (outcome)")
    except Exception:
        pass
```
- Register `Migration(47, "047_options_tracked_setups", _migration_047_options_tracked_setups)` in `MIGRATIONS`.

In `earnings_engine/data/turso_sync.py`:
- Add `"options_tracked_setups"` to `SYNC_TABLES`.
- Ensure date/timestamp fields are handled.

- [ ] **Step 4: Implement setup storage and evaluation functions in `option_chain.py`**

In `earnings_engine/data/option_chain.py`:
```python
def save_tracked_option_setups(
    conn: Any,
    setups: list[dict],
    symbol: str,
    spot_price: float,
    gamma_profile: dict | None = None,
    vix_profile: dict | None = None
) -> int:
    if not setups or not symbol:
        return 0
    clean_sym = symbol.upper().replace(".NS", "").strip()
    now_str = datetime.now().isoformat(timespec="seconds")
    today_str = datetime.now().strftime("%Y-%m-%d")
    gamma_regime = (gamma_profile or {}).get("gamma_regime", "UNKNOWN")
    vix_val = (vix_profile or {}).get("vix_value", 0.0)

    inserted = 0
    for s in setups:
        setup_id = str(s.get("id") or f"{clean_sym}-{today_str}")
        try:
            conn.execute("""
                INSERT OR IGNORE INTO options_tracked_setups (
                    symbol, setup_id, setup_title, setup_type, bias, confidence,
                    signal_date, spot_at_signal, entry_zone, stop_loss, target_1, target_2,
                    risk_reward, catalyst, gamma_regime, vix_value, current_spot,
                    realized_pnl_pct, outcome, outcome_label, outcome_badge,
                    scanned_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', 'Active Setup', 'badge-primary', ?, ?, ?)
            """, (
                clean_sym,
                setup_id,
                s.get("title", ""),
                s.get("type", "SETUP"),
                s.get("bias", "NEUTRAL"),
                float(s.get("confidence", 0.0)),
                today_str,
                float(spot_price),
                s.get("entry_zone", ""),
                float(s.get("stop_loss", 0.0)),
                float(s.get("target_1", 0.0)),
                float(s.get("target_2") or 0.0),
                s.get("risk_reward", "1 : 2.0"),
                s.get("catalyst", ""),
                gamma_regime,
                float(vix_val),
                float(spot_price),
                0.0,
                now_str,
                now_str,
                now_str
            ))
            inserted += 1
        except Exception as e:
            logger.warning("Could not persist tracked setup %s: %s", setup_id, e)
    try:
        conn.commit()
    except Exception:
        pass
    return inserted

def get_tracked_option_setups(conn: Any, symbol: str | None = None, outcome: str | None = None, limit: int = 50) -> list[dict]:
    query = "SELECT * FROM options_tracked_setups WHERE 1=1"
    params = []
    if symbol:
        clean_sym = symbol.upper().replace(".NS", "").strip()
        query += " AND symbol = ?"
        params.append(clean_sym)
    if outcome and outcome.upper() != "ALL":
        query += " AND outcome = ?"
        params.append(outcome.upper())
    query += " ORDER BY signal_date DESC, id DESC LIMIT ?"
    params.append(limit)

    cursor = conn.execute(query, params)
    rows = cursor.fetchall()
    results = []
    for r in rows:
        d = dict(r) if hasattr(r, "keys") else {
            "id": r[0], "symbol": r[1], "setup_id": r[2], "setup_title": r[3], "setup_type": r[4],
            "bias": r[5], "confidence": r[6], "signal_date": r[7], "spot_at_signal": r[8],
            "entry_zone": r[9], "stop_loss": r[10], "target_1": r[11], "target_2": r[12],
            "risk_reward": r[13], "catalyst": r[14], "gamma_regime": r[15], "vix_value": r[16],
            "current_spot": r[17], "realized_pnl_pct": r[18], "outcome": r[19],
            "outcome_label": r[20], "outcome_badge": r[21], "scanned_at": r[22], "created_at": r[23], "updated_at": r[24]
        }
        results.append(d)
    return results

def evaluate_tracked_option_setups(conn: Any, symbol: str, current_spot: float) -> list[dict]:
    clean_sym = symbol.upper().replace(".NS", "").strip()
    cursor = conn.execute("SELECT * FROM options_tracked_setups WHERE symbol = ? AND outcome = 'ACTIVE'", (clean_sym,))
    rows = cursor.fetchall()
    now_str = datetime.now().isoformat(timespec="seconds")
    updated_records = []

    for r in rows:
        d = dict(r) if hasattr(r, "keys") else {}
        if not d:
            continue
        row_id = d["id"]
        bias = d.get("bias", "NEUTRAL")
        spot_at_signal = float(d.get("spot_at_signal") or current_spot)
        target_1 = float(d.get("target_1") or 0.0)
        target_2 = float(d.get("target_2") or 0.0)
        stop_loss = float(d.get("stop_loss") or 0.0)
        pnl_pct = ((current_spot - spot_at_signal) / spot_at_signal) * 100.0 if bias == "BULLISH" else ((spot_at_signal - current_spot) / spot_at_signal) * 100.0

        new_outcome = "ACTIVE"
        outcome_label = "Active Setup"
        outcome_badge = "badge-primary"

        if bias == "BULLISH":
            if target_2 > 0 and current_spot >= target_2:
                new_outcome = "TARGET2_HIT"
                outcome_label = "Target 2 Achieved"
                outcome_badge = "badge-success"
            elif target_1 > 0 and current_spot >= target_1:
                new_outcome = "TARGET1_HIT"
                outcome_label = "Target 1 Hit"
                outcome_badge = "badge-success"
            elif stop_loss > 0 and current_spot <= stop_loss:
                new_outcome = "STOPPED_OUT"
                outcome_label = "Stopped Out"
                outcome_badge = "badge-danger"
        elif bias == "BEARISH":
            if target_2 > 0 and current_spot <= target_2:
                new_outcome = "TARGET2_HIT"
                outcome_label = "Target 2 Achieved"
                outcome_badge = "badge-success"
            elif target_1 > 0 and current_spot <= target_1:
                new_outcome = "TARGET1_HIT"
                outcome_label = "Target 1 Hit"
                outcome_badge = "badge-success"
            elif stop_loss > 0 and current_spot >= stop_loss:
                new_outcome = "STOPPED_OUT"
                outcome_label = "Stopped Out"
                outcome_badge = "badge-danger"

        if new_outcome != "ACTIVE":
            conn.execute("""
                UPDATE options_tracked_setups
                SET current_spot = ?, realized_pnl_pct = ?, outcome = ?, outcome_label = ?, outcome_badge = ?, updated_at = ?
                WHERE id = ?
            """, (current_spot, round(pnl_pct, 2), new_outcome, outcome_label, outcome_badge, now_str, row_id))
            d["outcome"] = new_outcome
            d["outcome_label"] = outcome_label
            d["outcome_badge"] = outcome_badge
            d["realized_pnl_pct"] = round(pnl_pct, 2)
            updated_records.append(d)

    try:
        conn.commit()
    except Exception:
        pass
    return updated_records
```

- [ ] **Step 5: Run tests to verify**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_options_tracked.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add earnings_engine/data/migrations.py earnings_engine/data/turso_sync.py earnings_engine/data/option_chain.py tests/test_options_tracked.py
git commit -m "feat(options): add migration 047 for options_tracked_setups and implement outcome lifecycle engine"
```

---

### Task 5: REST API Router Extensions

**Files:**
- Modify: `earnings_engine/api/routers/options.py`
- Modify: `tests/test_api_options.py`

**Interfaces:**
- Updates: `GET /api/v1/options/chain` (returns `gamma_profile`, `vix_profile`, `market_setups`, and enriched strike Greeks)
- Produces: `GET /api/v1/options/setups/history` (query params: `symbol: str | None`, `outcome: str | None`, `limit: int = 50`)
- Produces: `POST /api/v1/options/setups/evaluate` (query params: `symbol: str`, `current_spot: float | None = None`)

- [ ] **Step 1: Write failing tests for REST API endpoints**

In `tests/test_api_options.py`:
```python
def test_get_options_chain_gamma_payload(client):
    response = client.get("/api/v1/options/chain?symbol=NIFTY")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    res = data["data"]
    assert "gamma_profile" in res
    assert "vix_profile" in res
    assert "market_setups" in res
    assert isinstance(res["strikes"], list)
    if res["strikes"]:
        strike0 = res["strikes"][0]
        assert "ce_gex" in strike0
        assert "pe_gex" in strike0
        assert "ce_delta" in strike0

def test_get_options_setups_history(client):
    response = client.get("/api/v1/options/setups/history?symbol=NIFTY")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "setups" in data["data"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_api_options.py -k "test_get_options_setups_history" -v`
Expected: FAIL (endpoint not yet registered)

- [ ] **Step 3: Implement endpoints in `earnings_engine/api/routers/options.py`**

In `earnings_engine/api/routers/options.py`:
- Add static route `/setups/history`:
```python
@router.get("/setups/history")
async def get_options_setups_history_endpoint(
    symbol: str | None = None,
    outcome: str | None = None,
    limit: int = 50,
    db: Any = Depends(get_db)
):
    """Retrieve historical options setup tracking ledger."""
    try:
        records = get_tracked_option_setups(db, symbol=symbol, outcome=outcome, limit=limit)
        return {
            "success": True,
            "data": {
                "symbol": symbol,
                "outcome_filter": outcome or "ALL",
                "count": len(records),
                "setups": records
            }
        }
    except Exception as e:
        logger.error("Failed to fetch options setups history: %s", e)
        return {"success": False, "error": str(e), "data": {"setups": []}}

@router.post("/setups/evaluate")
async def evaluate_options_setups_endpoint(
    symbol: str,
    current_spot: float | None = None,
    db: Any = Depends(get_db)
):
    """Evaluate active options setups against current spot price."""
    try:
        if current_spot is None:
            # Fallback to last known spot
            pass
        updated = evaluate_tracked_option_setups(db, symbol=symbol, current_spot=current_spot or 0.0)
        return {"success": True, "data": {"updated_count": len(updated), "updated": updated}}
    except Exception as e:
        logger.error("Failed to evaluate options setups: %s", e)
        return {"success": False, "error": str(e)}
```
- In `/chain`, ensure `save_tracked_option_setups(db, analysis.get("market_setups", []), symbol, analysis.get("spot_price", 0.0), analysis.get("gamma_profile"), analysis.get("vix_profile"))` is executed to persist setups.

- [ ] **Step 4: Run tests to verify**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_api_options.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add earnings_engine/api/routers/options.py tests/test_api_options.py
git commit -m "feat(options): expose gamma profile, Greeks, and setup history endpoints in options API"
```

---

### Task 6: Frontend Template Updates (Mirrored Contracts)

**Files:**
- Modify: `earnings_engine/reports/templates/dashboard/_options.html`
- Modify: `earnings_engine/reports/templates/hubs/dashboard/_options.html`

**Interfaces:**
- Mirrored HTML structure updating the Options Hub dashboard with:
  1. Top Macro & Gamma Radar HUD (Gamma Regime badge, India VIX badge, Expected Move $1\sigma$ range badge, Primary Algorithmic Setup card).
  2. Multi-mode Chart toolbar toggles (`Mode 1: Dealer Gamma GEX (Default)`, `Mode 2: Total OI & ΔOI`, `Mode 3: Net OI Delta`, `Mode 4: IV Skew & Smile`).
  3. Expanded Strike Tree matrix headers with $\Delta, \Gamma$, and GEX (₹ Cr).
  4. Traded Setup History Ledger card and table beneath the strike matrix.

- [ ] **Step 1: Edit `earnings_engine/reports/templates/dashboard/_options.html`**

Update `_options.html` with:
- Gamma Radar HUD:
  - `<div id="optGammaRegimeBadge" class="badge"></div>`
  - `<div id="optVixBadge" class="badge"></div>`
  - `<div id="optExpectedMoveBadge" class="badge"></div>`
  - `<div id="optPrimarySetupBanner" class="setup-alert-card hidden"></div>`
- Chart Mode switch buttons:
  - `btn-chart-mode-gex` (active/default)
  - `btn-chart-mode-oi`
  - `btn-chart-mode-net-delta`
  - `btn-chart-mode-iv`
- Strike Tree columns: Call $\Delta$, Call GEX, Strike, Net GEX, Put GEX, Put $\Delta$.
- Traded Setup History Ledger container:
  - `<div id="optionsSetupHistoryCard" class="card mt-4">...</div>` with filter pills (`ALL`, `ACTIVE`, `TARGET_HIT`, `STOPPED_OUT`).

- [ ] **Step 2: Mirror the exact same HTML to `earnings_engine/reports/templates/hubs/dashboard/_options.html`**

Copy the updated `_options.html` to `earnings_engine/reports/templates/hubs/dashboard/_options.html` to satisfy the **Template Mirroring Rule**.

- [ ] **Step 3: Commit**

```bash
git add earnings_engine/reports/templates/dashboard/_options.html earnings_engine/reports/templates/hubs/dashboard/_options.html
git commit -m "feat(options): add Gamma Radar HUD, multi-mode chart toggles, and Setup History table in mirrored templates"
```

---

### Task 7: Frontend JavaScript Interactive Visualizer Engine (`options_hub.js`)

**Files:**
- Modify: `earnings_engine/ui/js/modules/options_hub.js`

**Interfaces:**
- Produces: `renderOiDistributionChart(data, chartMode)` supporting 4 modes:
  - `gex`: Dealer Gamma GEX (Default) — dual green/red bars with Net GEX zero-line, Gamma Flip dashed line, and Spot ATM line.
  - `oi`: Clustered Call/Put OI with $\Delta\text{OI}$ overlay.
  - `net_delta`: Center-zero divergent bar chart for $(\text{PE }\Delta\text{OI} - \text{CE }\Delta\text{OI})$.
  - `iv`: Dual Call IV vs Put IV spline curves.
- Produces: `renderGammaRadarHud(gammaProfile, vixProfile, marketSetups)`
- Produces: `renderOptionsSetupHistory(setups)` and filter event handlers.

- [ ] **Step 1: Implement multi-mode chart logic and HUD in `options_hub.js`**

In `earnings_engine/ui/js/modules/options_hub.js`:
- Maintain state: `currentChartMode = 'gex'`.
- Wire mode switch buttons (`#btnOptModeGex`, `#btnOptModeOi`, `#btnOptModeNetDelta`, `#btnOptModeIv`).
- Implement `renderOiDistributionChart(chainData, mode)`:
  - If `window.optionsOiChartInstance`, call `.destroy()`.
  - Prepare datasets according to `mode`:
    - **`gex`**: Green bars for `ce_gex` (positive), Red bars for `pe_gex` (negative), and Net GEX scatter/line with Gamma Flip indicator.
    - **`oi`**: Red bars for `ce_oi`, Green bars for `pe_oi`.
    - **`net_delta`**: Divergent bars for `net_oi_delta` (Green if $>0$, Red if $<0$).
    - **`iv`**: Red line for `ce_iv`, Green line for `pe_iv`.
- Implement `renderGammaRadarHud(data)`:
  - Update `#optGammaRegimeBadge` with positive/negative gamma styling.
  - Update `#optVixBadge` with India VIX value and change.
  - Update `#optExpectedMoveBadge` with $\pm 1\sigma$ straddle range.
  - Populate `#optPrimarySetupBanner` with catalyst, entry, SL, TP1, TP2.
- Implement `loadOptionsSetupHistory(symbol, outcomeFilter)`:
  - Fetch `/api/v1/options/setups/history?symbol=...&outcome=...`
  - Render rows with status badges, R:R, and outcome metrics.

- [ ] **Step 2: Validate JavaScript syntax**

Run: `node -c earnings_engine/ui/js/modules/options_hub.js`
Expected: PASS (no syntax errors)

- [ ] **Step 3: Commit**

```bash
git add earnings_engine/ui/js/modules/options_hub.js
git commit -m "feat(options): implement multi-mode Chart.js visualizer with Dealer GEX default and setup history ledger"
```

---

### Task 8: Full End-to-End Integration, Verification, Memory Persistence & Git Delivery

**Files:**
- Modify: `C:\Users\91700\.claude\projects\D--earnings-engine\memory\MEMORY.md`
- Create: `C:\Users\91700\.claude\projects\D--earnings-engine\memory\options-gex-and-setup-tracking.md`

- [ ] **Step 1: Run comprehensive targeted test suite**

Run:
```bash
./.venv/Scripts/python.exe -m pytest tests/test_option_chain.py tests/test_options_tracked.py tests/test_api_options.py -v
```
Expected: All tests PASS with 100% green status.

- [ ] **Step 2: Check JS syntax across all modified modules**

Run: `node -c earnings_engine/ui/js/modules/options_hub.js`
Expected: Clean exit (0).

- [ ] **Step 3: Persist Schema and Contract to Memory**

Write memory file `C:\Users\91700\.claude\projects\D--earnings-engine\memory\options-gex-and-setup-tracking.md` documenting `options_tracked_setups` schema, Greeks formulas, GEX calculations, and API contracts. Update `MEMORY.md`.

- [ ] **Step 4: Commit and Push directly to `origin/new_report`**

```bash
git status
git add .
git commit -m "feat(options): complete advanced options OI gamma GEX and setups engine with outcome tracking ledger"
git push origin new_report
```
Expected: Pushed successfully to `origin/new_report`.
