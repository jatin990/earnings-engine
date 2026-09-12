# CLAUDE.md — Breakout Radar Subsystem (`earnings_engine/breakout/`)

> Subsystem guide for Breakout Radar detection algorithms, swing ranges, momentum criteria, and volume tracking.

---

## 1. Scope & Architecture

The breakout subsystem detects and monitors high-probability price and volume breakouts across NSE India and US equities.

- **Detection Core**: `earnings_engine/breakout/radar.py` (vectorized screening, breakout identification)
- **Tracking & History**: `earnings_engine/breakout/tracker.py` (monitoring late breakouts, follow-through)
- **Data Dependencies**: `earnings_engine/data/swing_ranges.py`, `earnings_engine/data/prices.py`
- **Router**: `earnings_engine/api/routers/breakout.py` (`/dashboard#breakout`)

---

## 2. Mandatory Rules & Invariants

### 2.1 Volume Surge & Temporal Baseline Conventions
- **Volume Ratio Protocol**: Volume surges must be computed as 5-day average volume compared against the 63-day benchmark:
  $$\text{Volume Surge} = \frac{\text{AvgVolume}_{5\text{D}}}{\text{AvgVolume}_{63\text{D}}}$$
- Every radar card and API payload must explicitly declare its lookback window (e.g., `Volume Surge: 2.4x (5D vs 63D avg)`, `52W High Distance: -1.2%`).

### 2.2 Elite Hot & Late Detection Classification
- Categorize candidates strictly according to quantified criteria:
  - **Early Stage**: Emerging from base, volume expansion, within 2% of breakout level.
  - **Elite Hot**: Multi-factor confluence (volume surge $>2.0x$, positive institutional flows, tight consolidation base).
  - **Late / Extended**: Price extended $>7\%$ beyond initial pivot point.

### 2.3 Real Data Only
- Never generate synthetic breakout scores or placeholder momentum numbers. If market data is incomplete, return honest status flags.

---

## 3. Targeted Testing

```powershell
# Run breakout radar tests
.\.venv\Scripts\python.exe -m pytest tests/test_breakout.py -v
.\.venv\Scripts\python.exe -m pytest tests/test_breakout_radar.py -v
```
