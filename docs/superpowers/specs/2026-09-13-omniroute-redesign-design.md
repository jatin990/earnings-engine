# Design Specification: OmniRoute LLM Market Analysis Engine & UI/UX Redesign

- **Date:** 2026-09-13
- **Topic:** Scrapping legacy multi-model AI consensus engine in favor of a direct OmniRoute LLM integration using the 4 Claude Code model tiers, with customizable prompt construction and raw response inspection.
- **Status:** Approved for Implementation

---

## 1. Problem Statement & Motivation
The previous "Multi-Model AI Consensus Engine" orchestrated legacy multi-model voting (DeepSeek-R1, Llama-3.3, Qwen-2.5, Mistral-Large) via OpenRouter, with rigid voting weights, settlement tracking, and fixed prompt layouts. This added operational latency, complex error-recovery code, and opaque aggregation logic.

The user wants to:
1. **Scrap the legacy multi-model ensemble consensus engine** and its voting/settlement complexity.
2. Rely strictly on **OmniRoute** (the local multi-LLM proxy at `http://localhost:20128/v1`) using the **exact 4 models matching Claude Code**:
   - `claude only` (Claude 5 / Opus Architecture tier)
   - `antigravityonly` (Claude Sonnet / DeepMind tier)
   - `free only` (Haiku / Fast low-cost tier)
   - `auto/smart` (Dynamic Smart Coding / High-Reasoning tier)
3. **Redesign the UI/UX**:
   - Customizable prompt generation with interactive toggles:
     - Technical Structure & Momentum (52W High/Low, multi-timeframe returns, EMA alignments, volume surge, ATR)
     - Catalyst News & Impact (headlines, sentiment scores, impact ratings, publication dates)
     - Institutional & Shareholding Flows (FII/DII QoQ deltas, MF holdings)
     - Custom Directive / Instructions box (free-text guidance injected directly into prompt)
   - Comprehensive results view displaying structured targets (Direction, Confidence %, Target Price, Stop Loss, Risk-Reward) along with **raw LLM output**, **thinking/chain-of-thought blocks**, and the **exact prompt sent**.

---

## 2. Architecture & Backend Design

### 2.1 OmniRoute Client & Model Catalog (`earnings_engine/data/omniroute_client.py`)
- Define the canonical 4 Claude Code OmniRoute models:
  ```python
  CLAUDE_CODE_OMNIROUTE_MODELS = [
      {
          "id": "antigravityonly",
          "name": "⚡ Antigravity (Claude Sonnet / DeepMind)",
          "tier": "PRIMARY",
          "description": "Primary high-reasoning coding & quant synthesis model tier.",
          "recommended": True,
      },
      {
          "id": "claude only",
          "name": "🏛️ Claude Only (Claude 5 / Opus 5)",
          "tier": "ARCHITECTURE",
          "description": "Frontier architectural design, quantitative formulations & deep audit.",
          "recommended": True,
      },
      {
          "id": "free only",
          "name": "🚀 Free Only (Haiku / Fast Tier)",
          "tier": "FAST",
          "description": "Low-latency, lightweight synthesis and screening.",
          "recommended": False,
      },
      {
          "id": "auto/smart",
          "name": "🔮 Auto Smart (Smart Coding Gateway)",
          "tier": "SMART",
          "description": "Dynamic OmniRoute smart-routing tier with optimal model allocation.",
          "recommended": False,
      },
  ]
  ```
- Expose helper `get_claude_code_models(probe_live: bool = True)` which probes the running OmniRoute `/models` endpoint, validates availability, and returns the 4 models with live status.
- Implement `execute_omniroute_prompt(model: str, system_prompt: str, user_prompt: str, temperature: float = 0.2, timeout: int = 60)` returning:
  - `content`: raw markdown text
  - `reasoning`: reasoning content or `<think>` block extracted
  - `raw_response`: full text including thoughts
  - `tokens_used`: total token count
  - `latency_ms`: round-trip execution latency in ms
  - `model_used`: the model ID that fulfilled the request

### 2.2 Modular Prompt Builder (`earnings_engine/consensus/context_builder.py`)
Enhance the context and prompt builder to support selective inclusion flags:
- `include_technicals: bool = True`
- `include_news: bool = True`
- `include_institutional: bool = True`
- `custom_directives: str | None = None`

The prompt formatter generates clean, sectioned Markdown:
1. **Header & Quote**: Ticker, CMP, Sector, Market Feed Status.
2. **Technical Structure & Momentum** (if enabled): 52W range, 7D/30D/90D returns, 20/50/200 EMA status, volume surge ratio, ATR.
3. **Institutional Flows & Shareholding** (if enabled): DII/FII QoQ changes, promoter holding, MF stake deltas.
4. **Corporate Catalysts & Breaking News** (if enabled): Ranked recent headlines with dates and impact classification.
5. **Custom User Focus Directives** (if provided): Highlights specific evaluation instructions (e.g., "Look for swing entry on pullback to 20 EMA").
6. **Required Output Schema**: Strict JSON block specification with fields (`direction`, `conviction_score`, `target_price`, `stop_loss`, `risk_reward_ratio`, `catalyst_summary`, `thesis`, `key_risks`).

### 2.3 API Router (`earnings_engine/api/routers/consensus.py`)
Replace legacy consensus endpoints with clean, explicit routes:
- `GET /api/v1/consensus/models`
  - Returns the 4 configured OmniRoute Claude Code models and their online reachability.
- `POST /api/v1/consensus/analyze`
  - Input Schema (`OmniRouteAnalyzeRequest`):
    - `ticker`: str
    - `model`: str (defaults to `antigravityonly`)
    - `timeframe_days`: int (default 14)
    - `include_technicals`: bool = True
    - `include_news`: bool = True
    - `include_institutional`: bool = True
    - `custom_prompt`: str | None = None
  - Output Schema:
    - `ticker`: str
    - `model`: str
    - `structured`: parsed JSON prediction (`direction`, `target_price`, `stop_loss`, `conviction_score`, `risk_reward_ratio`, `thesis`, `key_risks`)
    - `raw_text`: full LLM markdown response
    - `reasoning_text`: extracted chain-of-thought text
    - `prompt_sent`: full user + system prompt for auditing
    - `latency_ms`: execution time
    - `tokens_used`: tokens consumed
    - `status`: "success" | "error"
- Deprecate / replace `/api/v1/consensus/predict` and redirect to the new OmniRoute analysis flow so all legacy triggers across dashboards cleanly execute via OmniRoute.

---

## 3. UI/UX Redesign

### 3.1 Dashboard Tab (`earnings_engine/reports/templates/dashboard/_consensus.html` & hubs mirror)
- **Header**: "OmniRoute Market Intelligence (Claude Code Engine)" with OmniRoute gateway badge.
- **Top Control Bar**:
  - Ticker input with quick-select watchlist dropdown.
  - Model selector dropdown (the 4 Claude Code models with tier tags).
  - Timeframe selector pill buttons (`3D`, `7D`, `14D`, `30D`, `90D`).
  - Data Inclusion Checkbox Toggles:
    - `[x] Technical Structure`
    - `[x] Corporate News & Catalysts`
    - `[x] Institutional Flows`
  - Free-form Custom Directive textarea with quick preset chips ("Swing Setup", "Breakout Verification", "Capital Preservation / Risk Assessment").
  - "Run OmniRoute Analysis" primary action button with animated loading state.
- **Two-Pane / Multi-Tab Results Deck**:
  - **Left Pane: Structured Decision Matrix**
    - High-visibility Bias Badge (`BULLISH` / `BEARISH` / `NEUTRAL`).
    - Conviction Gauge (`% Conviction`).
    - Key Price Targets: CMP, Target Price (+/- %), Stop Loss (- %), R:R ratio.
    - Executive Summary & Thesis.
    - Key Identified Risks & Invalidation Triggers.
  - **Right Pane: Interactive Inspector (3 Subtabs)**
    - **Tab 1: Raw LLM Output** — Syntax-highlighted/formatted markdown with 1-click "Copy Raw Markdown" button.
    - **Tab 2: Chain of Thought (<think>)** — Collapsible reasoning stream showing how the model worked through the trade.
    - **Tab 3: Prompt Sent** — Complete transparency into what data was compiled and sent to OmniRoute.

### 3.2 Modal & Table Badges (`earnings_engine/ui/js/modules/consensus.js` & `_modals.html`)
- Update `app.openAiDetails` and modal consensus views to use the new OmniRoute analyzer.
- Allow running the customized prompt directly from the modal or any stock row.
- Save user prompt customization options (toggles, preferred model) in `localStorage` for instant recall.

---

## 4. Verification & Testing Plan
1. **API Testing**:
   - Test `GET /api/v1/consensus/models` returns the 4 models and probes `http://localhost:20128/v1`.
   - Test `POST /api/v1/consensus/analyze` with `antigravityonly` and `claude only` for an NSE ticker (e.g. `TATAMOTORS.NS`).
   - Test toggles: verify omitting news removes news section from `prompt_sent`.
   - Test custom prompt insertion: verify custom directive is injected into `prompt_sent`.
2. **UI Verification**:
   - Verify layout in dashboard templates and hub mirrors.
   - Verify modal inspection, switching tabs between Structured Verdict, Raw LLM Output, Chain of Thought, and Prompt Sent.
3. **Regression Check**:
   - Ensure table action buttons (`⚡ AI Consensus`) cleanly trigger the redesigned OmniRoute analyzer.
