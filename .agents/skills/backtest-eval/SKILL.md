---
name: backtest-eval
description: Quantitative backtesting evaluation and trading strategy performance analytics. Use when computing Sharpe ratio, Sortino ratio, Maximum Drawdown (MDD), Profit Factor, Win Rate, Expectancy, and modeling transaction costs/slippage.
---

# Backtest Evaluation & Quantitative Analytics Skill

## Overview
Comprehensive statistical and quantitative analytics framework for evaluating algorithmic trading strategies, event-driven earnings setups, and swing trading models.

## Key Performance Indicators (KPIs)

### 1. Risk-Adjusted Returns
- **Sharpe Ratio**: `(Annualized Return - Risk-Free Rate) / Annualized Standard Deviation of Returns` (Benchmark Rf ≈ 6.5% for INR, 4.0% for USD; Sharpe > 1.5 is strong, > 2.0 is institutional grade).
- **Sortino Ratio**: `(Annualized Return - Risk-Free Rate) / Downside Deviation` (Penalizes only harmful downside volatility).
- **Calmar Ratio**: `Annualized Return / Maximum Drawdown`.

### 2. Drawdown & Capital Protection
- **Maximum Drawdown (MDD)**: `(Trough Value - Peak Value) / Peak Value`
- **Drawdown Duration**: Trading days from equity peak to recovery.
- **Value at Risk (VaR 95% / 99%)**: Historical or parametric estimated maximum loss over 1-day or 10-day horizon.

### 3. Trade Statistics & Expectancy
- **Win Rate (%)**: `(Winning Trades / Total Trades) * 100`
- **Profit Factor**: `Gross Profits / |Gross Losses|` (> 1.6 indicates solid edge)
- **Payoff Ratio (Win/Loss Ratio)**: `Average Profit per Win / Average Loss per Loss`
- **Trade Expectancy**: `(Win Rate * Avg Win) - (Loss Rate * Avg Loss)`

## Simulation Best Practices
1. **Lookahead Bias Prevention**: Never use future data points (e.g. end-of-day close for intra-day entry decisions).
2. **Slippage & Commission Modeling**:
   - Indian Equities (NSE): Model 0.10%–0.15% per round-trip (STT, exchange fees, brokerage, GST).
   - US Equities: Model $0.005/share + 0.05% estimated bid-ask spread slippage.
3. **Out-of-Sample Walk-Forward Optimization**: Split datasets into 70% in-sample calibration and 30% out-of-sample forward test to prevent overfitting.
