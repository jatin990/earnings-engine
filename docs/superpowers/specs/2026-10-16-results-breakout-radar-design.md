# Design Specification: Results Breakout Radar (-3 to +7 Days Window)

- **Date**: 2026-10-16
- **Status**: Approved for Planning & Implementation
- **Target Subsystem**: `earnings_engine/breakout/`, `earnings_engine/data/`, `earnings_engine/api/routers/breakout.py`, `earnings_engine/reports/templates/dashboard/_breakout.html`, `earnings_engine/ui/js/modules/`

---

## 1. Overview & Goal

Traders actively look for breakout opportunities specifically keyed around quarterly earnings announcements. Standard breakout radars scan the general market universe, often missing the unique volatility catalysts and price structures created by earnings declarations.

The **Results Breakout Radar** provides a dedicated quantitative scanner and user interface focusing exclusively on stocks reporting earnings within a customizable window—defaulting to **-3 days (declared) to +7 days (upcoming)** relative to the current date.

It captures four key result-oriented breakout archetypes:
1. **Result-Day High (RDH) Expansion**: Breaking out above the high of the reaction candle.
2. **Post-Earnings Announcement Drift (PEAD)**: Momentum continuation following high-volume positive surprise.
3. **Pre-Earnings Anticipation Coil**: Squeezing within striking distance of multi-week resistance directly ahead of earnings.
4. **Post-Result Dip Recovery**: Absorbing a knee-jerk drop and reclaiming the pre-result pivot.

---

## 2. Quantitative Architecture & Formulas

### 2.1 Universe Filtering
- Source table: `earnings_history` in local SQLite (`prices.sqlite3` / `earnings_engine.db`).
- Filter window: `earnings_date >= date(today, '-past_days day') AND earnings_date <= date(today, '+future_days day')`.
- Default: `past_days = 3`, `future_days = 7`.
- Range bounds: `past_days` [0, 30], `future_days` [0, 30].

### 2.2 Technical Reference Levels & Metrics
For each eligible stock, batch-load daily price candles to compute:
- $T_{\text{earnings}}$: Announcement date.
- $P_{\text{pre}}$: Pre-result closing price (close at $T_{-1}$).
- $RDH$: High of the earnings reaction candle.
- $RDL$: Low of the earnings reaction candle.
- $\text{Gap}_{\text{result}}\% = \frac{\text{Open}_{T} - P_{\text{pre}}}{P_{\text{pre}}} \times 100$
- $\text{Reaction}\% = \frac{\text{Close}_{T} - P_{\text{pre}}}{P_{\text{pre}}} \times 100$
- $SMA_{20}$, $Vol_{20D\_avg}$, $ATR_{14}$, $High_{20D}$, $High_{52W}$.
- $\text{Volume Ratio} = \frac{\text{Volume}_{\text{today}}}{Vol_{20D\_avg}}$

### 2.3 Setup Archetypes & Breakout Triggers

| Archetype | Timing State | Trigger Level | Setup Condition |
| :--- | :--- | :--- | :--- |
| **`RDH_EXPANSION`** | Declared ($\le 0$ days) | $\max(RDH, High_{20D})$ | Price within 2% of $RDH$, Volume Ratio $\ge 1.2\times$ |
| **`PEAD_MOMENTUM`** | Declared ($\le 0$ days) | Post-result high | Reaction $> +2.5\%$ or Surprise $> 0\%$, holding reaction open |
| **`PRE_EARNINGS_COIL`** | Upcoming ($> 0$ days) | $\max(High_{20D}, High_{52W})$ | Price within 3% of resistance, $ATR\% < 2.5\%$ |
| **`POST_RESULT_RECOVERY`** | Declared ($\le 0$ days) | $P_{\text{pre}}$ | Initial gap $< -2.0\%$, price has recovered back $\ge P_{\text{pre}}$ |

### 2.4 Composite Score (0–100)
- **Resistance & Trigger Proximity (0–30 pts)**: Exponential decay as price drops below trigger level; max points when breaking out ($0 \le \Delta \le +1\%$).
- **Volume Surge (0–25 pts)**: Scale from $1.0\times$ (0 pts) to $\ge 2.5\times$ (25 pts).
- **Earnings Quality & Surprise (0–20 pts)**: Scaled by positive surprise %, reported EPS vs estimate, or pre-earnings estimate revisions.
- **Trend & Volatility Coiling (0–15 pts)**: Squeeze intensity ($ATR_{14} / \text{Price}$) and 20D SMA alignment.
- **Reaction Day Retention (0–10 pts)**: Closing near the day's high with minimal upper wick.

---

## 3. API Contract

### Route: `GET /api/breakout/results-radar`
- **Location**: `earnings_engine/api/routers/breakout.py`
- **Query Parameters**:
  - `past_days` (int, default=3, min=0, max=30)
  - `future_days` (int, default=7, min=0, max=30)
  - `archetype` (str, default="ALL")
  - `min_score` (int, default=30)
  - `universe` (str, default="all")

### Response Payload Structure:
```json
{
  "status": "ok",
  "window": {
    "past_days": 3,
    "future_days": 7,
    "start_date": "YYYY-MM-DD",
    "end_date": "YYYY-MM-DD",
    "asof_date": "YYYY-MM-DD"
  },
  "total_candidates": 18,
  "summary": {
    "declared_count": 7,
    "upcoming_count": 11,
    "breaking_out_count": 3,
    "archetype_counts": {
      "RDH_EXPANSION": 3,
      "PEAD_MOMENTUM": 4,
      "PRE_EARNINGS_COIL": 8,
      "POST_RESULT_RECOVERY": 3
    }
  },
  "items": [
    {
      "ticker": "string",
      "company_name": "string",
      "industry": "string",
      "market": "string",
      "earnings_date": "YYYY-MM-DD",
      "timing_status": "DECLARED | UPCOMING",
      "relative_days_label": "string",
      "is_declared": true,
      "current_price": 1234.5,
      "breakout_trigger": 1250.0,
      "trigger_label": "string",
      "pct_from_trigger": -1.24,
      "is_breaking_out": false,
      "composite_score": 78,
      "tier": "HOT | WARM",
      "archetype": "RDH_EXPANSION",
      "archetype_label": "RDH Expansion",
      "archetype_badge": "RDH Breakout",
      "result_structure": {
        "pre_result_close": 1200.0,
        "result_day_high": 1250.0,
        "result_day_low": 1210.0,
        "reaction_day_gap_pct": 2.5,
        "reaction_day_return_pct": 3.1,
        "intraday_recovery_pct": 2.8,
        "post_high_move_pct": 4.1,
        "pullback_from_high_pct": -0.8
      },
      "fundamentals": {
        "eps_reported": 12.5,
        "eps_estimate": 11.8,
        "surprise_pct": 5.9,
        "quality_score": 75
      },
      "technicals": {
        "volume_ratio": 1.85,
        "atr_pct": 1.7,
        "momentum_3d_pct": 2.8,
        "momentum_7d_pct": 4.5,
        "high_52w": 1300.0,
        "high_20d": 1250.0
      },
      "trade_levels": {
        "ideal_entry": 1252.0,
        "target_price": 1310.0,
        "stop_loss": 1220.0,
        "risk_reward_ratio": 1.81
      }
    }
  ]
}
```

---

## 4. Frontend & User Interface

### 4.1 Subtab Integration
- Add subtab button `📊 Results Breakout` in:
  - `earnings_engine/reports/templates/dashboard/_breakout.html`
  - `earnings_engine/reports/templates/hubs/dashboard/_breakout.html`
- Wire subtab switcher in `earnings_engine/ui/js/modules/tracked_breakouts.js` and `breakout_radar.js`.

### 4.2 Top Obsidian Control Toolbar
- **Window Controls**:
  - Steppers/inputs for `Past (-X)` and `Future (+Y)` days.
  - Quick-preset buttons:
    - `[-3 to +7] (Default)`
    - `[-1 to +3] (Tight Earnings)`
    - `[-7 to +7] (Bi-Weekly)`
    - `[0 to +10] (Upcoming Runups)`
    - `[-10 to 0] (Post-Result PEAD)`
- **Archetype Filter**: Chips for `All`, `RDH Breakout`, `PEAD Drift`, `Pre-Earnings Coil`, `Dip Recovery`.
- **Search & Universe**: Quick-search filter by ticker and market-cap / index universe selector.

### 4.3 50-50 Split View
- **Left Table**:
  - Symbol, Timing Chip (`Declared 2D ago` / `In 3D`), Score Badge, Archetype, Trigger & % Distance, Reaction Gap %, Volume Ratio, Surprise %.
  - Row click selects item and updates inspector.
- **Right Inspector Drawer**:
  - Result price structure visualization (Pre-close, Gap, RDH, RDL, Current).
  - Setup diagnosis (clear explanation of why the setup is forming).
  - Risk/reward card (Entry, Target, Stop Loss).
  - Earnings fundamentals card (EPS Reported vs Estimate, Surprise %).

---

## 5. Verification & Testing

1. **Unit Tests**:
   - `tests/test_earnings_breakout_scanner.py`: Test date window queries, calculations of RDH/RDL, archetype classification, and composite score weighting.
   - `tests/test_breakout_router.py`: Validate `/api/breakout/results-radar` endpoint responses and status codes.
2. **Template Validation**:
   - Ensure both `dashboard/_breakout.html` and `hubs/dashboard/_breakout.html` are mirrored and identical.
   - Run `node -c` on all modified JavaScript files.
3. **End-to-End Sanity Check**:
   - Test default `-3 to +7` range as well as custom ranges.
   - Verify zero mock data and proper empty states when no stocks declare in a given range.
