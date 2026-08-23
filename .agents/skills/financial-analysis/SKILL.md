---
name: financial-analysis
description: Corporate earnings, financial statements, and quantitative valuation analysis. Use when evaluating quarterly results (EPS surprise, revenue beat, EBITDA margins), balance sheet health (debt-to-equity, current ratio), and valuation multiples (P/E, PEG, EV/EBITDA, P/B).
---

# Financial Analysis & Valuation Skill

## Overview
Provides quantitative and fundamental frameworks for evaluating corporate earnings releases, financial statements, and stock valuations across Indian (NSE/BSE) and US (NYSE/NASDAQ) equities.

## Core Financial Metrics

### 1. Quarterly Earnings Performance
- **EPS Surprise (%)**: `((Reported EPS - Estimated EPS) / |Estimated EPS|) * 100`
- **Revenue Beat (%)**: `((Reported Revenue - Estimated Revenue) / Estimated Revenue) * 100`
- **Operating Margin Expansion**: `(QoQ / YoY Change in Operating Profit / Revenue)`
- **EBITDA Margin**: `(EBITDA / Total Revenue) * 100`

### 2. Balance Sheet & Cash Flow Health
- **Debt-to-Equity (D/E)**: `Total Debt / Total Shareholders' Equity` (< 1.0 preferred for non-banking)
- **Interest Coverage Ratio**: `EBIT / Interest Expense` (> 3.0 safe threshold)
- **Free Cash Flow (FCF)**: `Operating Cash Flow - Capital Expenditures (CapEx)`
- **Return on Capital Employed (ROCE)**: `EBIT / (Total Assets - Current Liabilities)`

### 3. Valuation Multiples
- **Price-to-Earnings (P/E)**: `Current Price / Trailing 12M EPS` (compare vs. 3Y/5Y historical median & industry average)
- **PEG Ratio**: `(P/E Ratio) / (Annual EPS Growth Rate)` (PEG < 1.0 indicates undervalued relative to growth)
- **Enterprise Value to EBITDA (EV/EBITDA)**: `(Market Cap + Total Debt - Cash) / EBITDA`

## Workflow Guidelines
1. Normalize non-recurring one-off gains/losses when computing underlying core operational earnings.
2. Cross-reference quarterly earnings beats with forward guidance updates.
3. Factor in sector-specific nuances (e.g. Net Interest Margin (NIM) and Gross NPA for Banks/NBFCs vs. ARR and Dollar-Based Net Retention for SaaS).
