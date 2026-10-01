# CLAUDE.md — AI Consensus Engine (`earnings_engine/consensus/`)

> Subsystem guide for Multi-Model AI Consensus Engine, context builders, prompt templates, and OmniRoute gateway.

---

## 1. Scope & Architecture

The consensus subsystem orchestrates multi-model quantitative equity deliberations across frontier LLMs (DeepSeek-R1, Llama-3.3-70B, Qwen-2.5-72B, Mistral-Large) via the OmniRoute/OpenRouter gateway.

- **Model Runner**: `earnings_engine/consensus/model_runner.py` (parallel model dispatch, retries, parsing)
- **Consensus Aggregator**: `earnings_engine/consensus/aggregator.py` (vote weighting, settlement, confidence scoring)
- **Context Builder**: `earnings_engine/consensus/context_builder.py` (PIT context assembly, financial metrics, news)
- **Result Storage**: `earnings_engine/consensus/storage.py` (persisting verdicts to SQLite & Turso sync)
- **Rate Limits**: `earnings_engine/rate_limits.py` (`AVAILABLE_AI_MODELS`, sliding-window throttle)

---

## 2. Core Invariants & Operating Rules

### 2.1 On-Demand Zero-Token Default
- **Strict Prohibition**: Never invoke automated consensus runs or LLM inference on page load, table sorting, or modal render.
- Ingestion, scanning, and inspection default to **zero token usage**. AI inference requires an explicit user action (e.g., clicking "Run AI Consensus").

### 2.2 Rate Limiting & Graceful Degradation
- Always pass model requests through `earnings_engine/rate_limits.py`.
- Handle provider rate limits (HTTP 429) or timeouts with exponential backoff and transparent error reporting in the UI.

### 2.3 Context Freshness & PIT Preservation
- When compiling LLM context for historical event dates, strictly enforce Point-in-Time constraints via `context_builder.py`.
- Every consensus verdict must record its model version, timestamp, confidence breakdown, and individual model rationales.

---

## 3. Targeted Testing

```bash
# Run consensus aggregator and runner tests
./.venv/Scripts/python.exe -m pytest tests/test_consensus.py -v
./.venv/Scripts/python.exe -m pytest tests/ -k "consensus or model_runner"
```
