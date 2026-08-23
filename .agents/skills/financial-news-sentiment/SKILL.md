---
name: financial-news-sentiment
description: Financial news parsing, catalyst categorization, sentiment analysis, impact scoring (0-100%), and regulatory/corporate filing extraction. Use when classifying order wins, FDA approvals, M&A deals, litigation risks, or earnings announcements.
---

# Financial News Sentiment & Catalyst Extraction Skill

## Overview
Techniques for extracting, scoring, and categorizing market-moving catalysts and breaking news headlines to generate quantitative trading signals.

## Catalyst Taxonomy & Impact Scoring

| Category | Typical Impact Score | Market Direction | Primary Signals |
| :--- | :--- | :--- | :--- |
| **Order Wins & Mega Deals** | 70% – 95% | Bullish 🟢 | Contract value as % of annual revenue, margin profile |
| **Earnings & Guidance Surprise** | 80% – 100% | Directional 🟢/🔴 | Beat/miss margin, revised forward full-year guidance |
| **Regulatory & Approvals** | 75% – 95% | Bullish 🟢 / Bearish 🔴 | US FDA approval/warning letter, CCI / SEBI clearance |
| **M&A & Strategic Expansion** | 60% – 85% | Contextual ⚡ | Synergies, debt load, acquisition multiples |
| **Litigation, Risk & Probes** | 70% – 90% | Bearish 🔴 | Government tax raids, forensic audit, auditor resignation |
| **Corporate Action & Dividends** | 50% – 70% | Bullish 🟢 | High dividend yield announcement, buyback premium |

## Signal Extraction Rules
1. **Urgency Filter**: Prioritize news timestamped within the last 24–48 hours.
2. **Attribution Disambiguation**: Match stock ticker explicitly by ISIN or exact exchange name to prevent ticker collision (e.g. `TCS` in India vs `TCS` in US).
3. **Sentiment Decay**: Decay catalyst impact exponentially with a half-life of 3–5 trading days.
