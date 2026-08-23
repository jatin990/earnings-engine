---
name: llm-consensus-engine
description: Multi-model AI consensus forecasting, ensemble reasoning, temperature calibration, structured schema extraction, and post-mortem failure diagnostics across DeepSeek-R1, Llama-3.3-70B, Claude, and Gemini.
---

# LLM Consensus Engine Skill

## Overview
Architectural patterns for multi-model ensemble intelligence in financial forecasting, earnings prediction, and market thesis generation.

## Multi-Model Ensemble Workflow

```
                   ┌───────────────────────────────────┐
                   │ Market Data + Earnings + Catalysts│
                   └─────────────────┬─────────────────┘
                                     │
         ┌───────────────────────────┼───────────────────────────┐
         ▼                           ▼                           ▼
┌─────────────────┐         ┌─────────────────┐         ┌─────────────────┐
│ DeepSeek-R1     │         │ Llama-3.3-70B   │         │ Gemini 2.5 Pro  │
│ (Deep Reasoning)│         │ (Macro Context) │         │ (Multi-Modal)   │
└────────┬────────┘         └────────┬────────┘         └────────┬────────┘
         │                           │                           │
         └───────────────────────────┼───────────────────────────┘
                                     ▼
                   ┌───────────────────────────────────┐
                   │ Consensus Arbiter / Aggregator    │
                   │ (Weighted Voting & Bias Filter)   │
                   └─────────────────┬─────────────────┘
                                     ▼
                   ┌───────────────────────────────────┐
                   │ Direction, Target Range & Win Prob│
                   └───────────────────────────────────┘
```

## Prompt Engineering & Structured Outputs
1. **JSON Enforcement**: Always use JSON Mode / Pydantic schema validation for consensus responses.
2. **Temperature Calibration**:
   - DeepSeek-R1 / Reasoning: `temperature=0.6`
   - Numeric & Statistical Estimates: `temperature=0.1` - `0.2`
   - General Synthesis & Thesis: `temperature=0.4`
3. **Automated Post-Mortem Diagnostics**:
   - When realized price diverges from forecast by > 5%, trigger an automated diagnostic routine categorizing the failure cause:
     - `BROAD_MARKET_CORRECTION` (Beta shock)
     - `GUIDANCE_MISS` (Fundamental surprise)
     - `MACRO_GEOPOLITICAL` (Exogenous shock)
     - `TECHNICAL_BREAKDOWN` (Failed support zone)
