# Fix Plan: STLTECH.NS Data Quality Issues

## Issues Summary

1. **No institutional data** in Institutional & Smart Money Buyers Inspector
2. **Gross inflow shows 0** on stock detail page
3. **-5.7% vs 52 Week High** shown when stock is at 52W high (breakout drawer)
4. **7D and 30D returns blank** in breakout drawer

---

## Issue 1: No Institutional Data for STLTECH.NS

### Root Cause
`get_stock_institutional_activity()` in `earnings_engine/data/institutional_accumulation.py` only seeds institutional data from yfinance via `_ensure_institutional_data_for_ticker()` if the ticker is **completely absent** from `institutional_holdings`. STLTECH.NS likely has no rows there.

Additionally, the function calls `fetch_live_corporate_ownership()` which first checks `tickers` table — if STLTECH.NS is missing from tickers, the early exit at line 213-221 prevents any yfinance call.

### Fix
In `_ensure_institutional_data_for_ticker()` (line 457), add a yfinance fetch path even when `conn` has no pre-existing tickers table row:

```python
# Always attempt yfinance fetch if allow_network=True, regardless of ticker table presence
live_meta = fetch_live_corporate_ownership(sym, conn, allow_network=True)
```

And in `get_stock_institutional_activity()` (line 1081-1094), also pass `allow_network=True` to the seeding call so new/untracked tickers get populated:

```python
_ensure_institutional_data_for_ticker(sym, conn, allow_network=True)
```

### File
`earnings_engine/data/institutional_accumulation.py`

---

## Issue 2: Gross Inflow = 0.0 on Stock Detail

### Root Cause
`gross_inflow_cr` is computed from `institutional_holdings` rows. If STLTECH.NS has no holdings rows, all flow metrics remain 0.0 (line 1176: `gross_inflow_cr = round(gross_inflow_cr, 1)` = 0.0).

Once Issue 1 is fixed (yfinance seeding kicks in), `gross_inflow_cr` will be non-zero only if AMFI/NSE mutual fund holdings exist for STLTECH.NS. For new/small-cap stocks with no MF holdings, 0.0 is **correct data, not a bug** — but the UI should display "No Institutional Holdings On Record" rather than "₹0.0 Cr".

### Fix
In the stock detail HTML template and JS, check if `gross_inflow_cr === 0` and `funds_accumulating_count === 0`, then display "—" with an honest status tag:
```javascript
const grossInflow = inst.gross_inflow_cr > 0 ? `₹${inst.gross_inflow_cr.toLocaleString()} Cr` : '—';
```
Add a companion field `inst_status: "No Institutional Holdings On Record"` when all institutional metrics are zero.

### Files
- `earnings_engine/reports/templates/stock_detail.html` (or hubs variant)
- `earnings_engine/ui/js/stock_detail.js` or `modules/stock_note.js`

---

## Issue 3: -5.7% vs 52 Week High When At 52W High

### Root Cause
In `earnings_engine/ui/js/modules/breakout_radar.js`, `renderBreakoutSetupInspector()` at line 3762:

```javascript
const high52 = candidate.high_52w != null ? Number(candidate.high_52w) : (curPrice * 1.06);
```

The `candidate.high_52w` value comes from the scanner's `data_json` which was computed when the scan last ran. For STLTECH.NS:
- The scanner may have computed `high_52w` when the stock was at ₹X
- The stock has since reached a new 52W high (current price = new all-time high)
- But `candidate.high_52w` still holds the old value → distance shows negative

The fallback `curPrice * 1.06` produces a ~6% buffer, which coincidentally gives -5.7% (≈ -5.7% = `curPrice/1.06 - 1` when stock is at 52W high).

### Fix
When opening the inspector drawer, fetch a fresh live price and compute the current 52W high from latest price data. Override `candidate.high_52w` with fresh value:

In `selectBreakoutCandidate()` (line 1755), before calling `renderBreakoutSetupInspector`:
```javascript
// Fetch live 52W data from the API to ensure freshness
if (candidate.ticker) {
    try {
        const res = await fetch(`/api/v1/stock/${encodeURIComponent(candidate.ticker)}/quote`);
        if (res.ok) {
            const data = await res.json();
            const quote = data.quote || data;
            if (quote.week_52_high) candidate.high_52w = Number(quote.week_52_high);
            if (quote.current_price) candidate.current_price = Number(quote.current_price);
            // Also get fresh 7D/30D returns from the overview
            if (quote.return_7d_pct != null) candidate.ret_7d_pct = quote.return_7d_pct;
            if (quote.return_30d_pct != null) candidate.ret_30d_pct = quote.return_30d_pct;
        }
    } catch (e) { /* Use cached values */ }
}
```

This fixes both the 52W stale value AND provides missing 7D/30D returns.

### Files
- `earnings_engine/ui/js/modules/breakout_radar.js` (`selectBreakoutCandidate` function)

---

## Issue 4: 7D Return Blank in Breakout Drawer

### Root Cause
The breakout scanner (`earnings_engine/data/breakout_scanner.py`) computes `ret_30d_pct` in `compute_stock_metrics()` (line 3128-3131) but **never computes `ret_7d_pct`**. Therefore `ret_7d_pct` is always absent from the candidate object.

The JS drawer's fallback chain (line 3556-3557):
```javascript
const r7 = candidate.ret_7d_pct ?? candidate.return_7d ?? candidate.perf_7d ?? candidate.calculation_notes?.return_7d ?? null;
```
...resolves all to `null` → displays "7D: —".

### Fix
Add `ret_7d_pct` computation to `compute_stock_metrics()` in `earnings_engine/data/breakout_scanner.py` (around line 3127):

```python
# 7D Return %
ret_7d_pct = None
if len(closes) >= 6:
    idx_7 = max(0, len(closes) - 8)
    ret_7d_pct = round(((current_price / float(closes.iloc[idx_7])) - 1.0) * 100.0, 2)
```

And include it in the return dict:
```python
return {
    # ... existing fields ...
    "ret_30d_pct": ret_30d_pct,
    "ret_7d_pct": ret_7d_pct,
}
```

This will also require re-scanning the universe to populate the new field in cached candidates and DB.

**Secondary fix**: In `selectBreakoutCandidate()` (JS), enrich candidate with fresh quote data from the `/quote` endpoint (fixes both 52W stale and provides 7D/30D returns as described in Issue 3 fix).

### Files
- `earnings_engine/data/breakout_scanner.py` (`compute_stock_metrics` function)
- `earnings_engine/ui/js/modules/breakout_radar.js` (`selectBreakoutCandidate` function)

---

## Implementation Order

1. **Fix 4 first** (`compute_stock_metrics` — compute `ret_7d_pct`) — no external dependencies
2. **Fix 3 + 4 secondary** (`selectBreakoutCandidate` — enrich with fresh quote data) — fixes 52W staleness and 7D blanks
3. **Fix 1** (`_ensure_institutional_data_for_ticker` — allow network fetch for untracked tickers)
4. **Fix 2** (UI honest zero-state for institutional flows)

---

## Verification

1. Run `_ensure_institutional_data_for_ticker` for STLTECH.NS manually
2. Trigger a breakout scan to pick up new `ret_7d_pct` field
3. Open STLTECH.NS in breakout drawer — verify 7D, 30D, 52W all show correct live values
4. Check institutional inspector shows actual yfinance data (promoter %, inst %) rather than empty state