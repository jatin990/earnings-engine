---
name: pine-script-v5
description: TradingView Pine Script v5 development, indicators, swing range overlays, alert generation, and Pine-to-Python cross-validation. Use when writing, debugging, or converting Pine Script code, creating trading signals, or synchronizing chart indicators with backend algorithms.
---

# Pine Script v5 Development Skill

## Overview
Guidelines and best practices for creating high-performance, bug-free **Pine Script v5** indicators and strategies for TradingView, cross-compatible with Earnings Engine swing setups and support/resistance channels.

## Core Pine Script v5 Principles

### 1. Compiler Header & Settings
Always specify version 5 at the top:
```pinescript
//@version=5
indicator("Earnings Engine Swing & Buy Zones", overlay=true, max_boxes_count=500, max_lines_count=500)
```

### 2. Best Practices & Optimization
- **Persistent State**: Use `var` for state that persists across bars (e.g. `var float supportLevel = na`).
- **Dynamic Box / Line Cleanup**: Always clean up or limit drawing objects using `box.delete()` / `line.delete()` or `max_boxes_count`.
- **Repainting Prevention**:
  - Never use future bar data or unconfirmed bar closes (`barstate.isconfirmed` required for alert conditions).
  - When accessing higher timeframe data via `request.security()`, use `barmerge.gaps_off` and lookahead `barmerge.lookahead_off` on historical bars.

### 3. Example: Swing Channel & Buy Zone Indicator
```pinescript
//@version=5
indicator("Swing Trading Channel [Earnings Engine]", overlay=true)

lookback = input.int(20, "Channel Lookback Days", minval=5)
lowerBound = ta.lowest(low, lookback)
upperBound = ta.highest(high, lookback)
buyZoneTop = lowerBound + (upperBound - lowerBound) * 0.25

pHigh = plot(upperBound, "Resistance (Sell Zone)", color=color.red, linewidth=2)
pLow = plot(lowerBound, "Support (Buy Zone Base)", color=color.green, linewidth=2)
pBuy = plot(buyZoneTop, "Buy Zone Upper Threshold", color=color.new(color.green, 50), style=plot.style_linebr)

fill(pLow, pBuy, color=color.new(color.green, 85), title="Active Buy Zone")

// Alert Conditions
inBuyZone = close <= buyZoneTop and close >= lowerBound
alertcondition(inBuyZone and ta.crossover(close, lowerBound), "Stock Entered Buy Zone", "Price entered support buy zone for {{ticker}}")
```

### 4. Cross-Validating Pine with Python
Ensure math parity between Python pandas (`df['low'].rolling(20).min()`) and Pine Script (`ta.lowest(low, 20)`).
