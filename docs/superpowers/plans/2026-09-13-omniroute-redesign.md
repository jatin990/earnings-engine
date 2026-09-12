# OmniRoute Market Intelligence Engine Redesign & UI/UX Customizer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Scrap legacy multi-model ensemble consensus and replace it with a direct OmniRoute LLM Market Analysis engine using the exact 4 Claude Code model tiers, featuring customizable prompt toggles (technicals, news, institutional, custom directives) and a redesigned UI for inspecting structured verdicts, raw LLM outputs, thinking blocks, and transmitted prompts.

**Architecture:** 
- Core backend client in `earnings_engine/data/omniroute_client.py` implements discovery and execution against the local OmniRoute instance (`http://localhost:20128/v1`) using the 4 Claude Code tiers (`antigravityonly`, `claude only`, `free only`, `auto/smart`).
- Context builder in `earnings_engine/consensus/context_builder.py` supports modular prompt section toggling and user directive injection.
- Domain router in `earnings_engine/api/routers/consensus.py` exposes `/api/v1/consensus/models` and `/api/v1/consensus/analyze`.
- Frontend templates in `_consensus.html` (mirrored in `hubs/dashboard/_consensus.html` and `_modals.html`) and JavaScript in `consensus.js` provide prompt customizer controls and a three-tab inspector (Raw Response, Chain of Thought, Prompt Sent).

**Tech Stack:** Python 3.11+, FastAPI, Requests, Jinja2, Vanilla JavaScript (ES6+), CSS3 Grid/Flexbox.

**Spec:** `docs/superpowers/specs/2026-09-13-omniroute-redesign-design.md`

## Global Constraints
- Only use the 4 discovered Claude Code OmniRoute models: `antigravityonly`, `claude only`, `free only`, and `auto/smart`.
- Keep template mirrors strictly synchronized between `earnings_engine/reports/templates/dashboard/_consensus.html` and `earnings_engine/reports/templates/hubs/dashboard/_consensus.html`.
- Real-data integrity guarantee: return honest empty states or error flags if data is unavailable; zero mock fallbacks.
- Zero-token default: never trigger AI inference automatically on page load or modal open; require explicit user click.
- Targeted test execution: run pytest with specific test files/functions.

---

### Task 1: Update OmniRoute Client with Claude Code 4 Models & Execution Adapter

**Files:**
- Modify: `earnings_engine/data/omniroute_client.py`
- Test: `tests/test_omniroute_client.py`

**Interfaces:**
- Produces:
  - `CLAUDE_CODE_OMNIROUTE_MODELS: list[dict[str, Any]]`
  - `get_claude_code_models(probe_live: bool = True) -> list[dict[str, Any]]`
  - `execute_omniroute_analysis(model: str, system_prompt: str, user_prompt: str, temperature: float = 0.2, timeout: int = 60) -> dict[str, Any]`

- [ ] **Step 1: Write the failing unit test for OmniRoute Claude Code models & execution**

Create `tests/test_omniroute_client.py`:
```python
from unittest.mock import patch, MagicMock
from earnings_engine.data.omniroute_client import (
    CLAUDE_CODE_OMNIROUTE_MODELS,
    get_claude_code_models,
    execute_omniroute_analysis,
)

def test_claude_code_models_catalog():
    model_ids = [m["id"] for m in CLAUDE_CODE_OMNIROUTE_MODELS]
    assert "antigravityonly" in model_ids
    assert "claude only" in model_ids
    assert "free only" in model_ids
    assert "auto/smart" in model_ids

@patch("requests.get")
def test_get_claude_code_models_live_probe(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "data": [{"id": "antigravityonly"}, {"id": "claude only"}, {"id": "free only"}, {"id": "auto/smart"}]
    }
    mock_get.return_value = mock_resp
    
    models = get_claude_code_models(probe_live=True)
    assert len(models) == 4
    for m in models:
        assert m["available"] is True

@patch("requests.post")
def test_execute_omniroute_analysis_success(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{
            "message": {
                "content": '```json\n{"direction": "BULLISH", "conviction_score": 85}\n```',
                "reasoning": "Technical structure is breaking out"
            }
        }],
        "usage": {"total_tokens": 420}
    }
    mock_post.return_value = mock_resp

    res = execute_omniroute_analysis(
        model="antigravityonly",
        system_prompt="You are a quant.",
        user_prompt="Analyze TATAMOTORS.NS"
    )
    assert res["status"] == "success"
    assert res["tokens_used"] == 420
    assert "Technical structure" in res["reasoning_text"]
    assert "BULLISH" in res["raw_text"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_omniroute_client.py -v`
Expected: FAIL with `ImportError: cannot import name 'CLAUDE_CODE_OMNIROUTE_MODELS'`

- [ ] **Step 3: Implement Claude Code models catalog & execution function in omniroute_client.py**

In `earnings_engine/data/omniroute_client.py`, add:
```python
CLAUDE_CODE_OMNIROUTE_MODELS: list[dict[str, Any]] = [
    {
        "id": "antigravityonly",
        "name": "⚡ Antigravity (Claude Sonnet / DeepMind)",
        "tier": "PRIMARY",
        "provider": "Anthropic / DeepMind",
        "description": "Primary high-reasoning coding & quant synthesis model tier.",
        "recommended": True,
        "available": True,
    },
    {
        "id": "claude only",
        "name": "🏛️ Claude Only (Claude 5 / Opus 5)",
        "tier": "ARCHITECTURE",
        "provider": "Anthropic",
        "description": "Frontier architectural design, quantitative formulations & deep audit.",
        "recommended": True,
        "available": True,
    },
    {
        "id": "free only",
        "name": "🚀 Free Only (Haiku / Fast Tier)",
        "tier": "FAST",
        "provider": "Anthropic / Fast",
        "description": "Low-latency, lightweight synthesis and screening.",
        "recommended": False,
        "available": True,
    },
    {
        "id": "auto/smart",
        "name": "🔮 Auto Smart (Smart Coding Gateway)",
        "tier": "SMART",
        "provider": "OmniRoute Gateway",
        "description": "Dynamic OmniRoute smart-routing tier with optimal model allocation.",
        "recommended": False,
        "available": True,
    },
]

def get_claude_code_models(probe_live: bool = True) -> list[dict[str, Any]]:
    client = OmniRouteClient()
    if not probe_live:
        return [dict(m) for m in CLAUDE_CODE_OMNIROUTE_MODELS]
    try:
        url = f"{client.base_url.rstrip('/')}/models"
        headers = {}
        if client.api_key:
            headers["Authorization"] = f"Bearer {client.api_key}"
        resp = requests.get(url, headers=headers, timeout=2.5)
        if resp.status_code == 200:
            online_ids = {m.get("id") for m in resp.json().get("data", [])}
            res = []
            for item in CLAUDE_CODE_OMNIROUTE_MODELS:
                m_copy = dict(item)
                m_copy["available"] = item["id"] in online_ids
                res.append(m_copy)
            return res
    except Exception as e:
        logger.debug("[OMNIROUTE] Live probe failed: %s", e)
    return [dict(m) for m in CLAUDE_CODE_OMNIROUTE_MODELS]

def execute_omniroute_analysis(
    model: str = "antigravityonly",
    system_prompt: str = "",
    user_prompt: str = "",
    temperature: float = 0.2,
    timeout: int = 60,
) -> dict[str, Any]:
    client = OmniRouteClient()
    url = client.get_completions_url()
    headers = {"Content-Type": "application/json", "X-Title": "Earnings Engine OmniRoute"}
    if client.api_key:
        headers["Authorization"] = f"Bearer {client.api_key}"
    
    t0 = time.time()
    try:
        resp = requests.post(
            url,
            headers=headers,
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": temperature,
                "max_tokens": 2048,
            },
            timeout=timeout,
        )
        latency_ms = round((time.time() - t0) * 1000, 1)
        if resp.status_code == 200:
            data = resp.json()
            choice = (data.get("choices") or [{}])[0]
            msg = choice.get("message") or {}
            content = msg.get("content") or ""
            reasoning = msg.get("reasoning") or ""
            tokens = data.get("usage", {}).get("total_tokens", 0)
            return {
                "status": "success",
                "raw_text": content,
                "reasoning_text": reasoning,
                "tokens_used": tokens,
                "latency_ms": latency_ms,
                "model_used": model,
            }
        return {
            "status": "error",
            "error": f"OmniRoute HTTP {resp.status_code}: {resp.text[:200]}",
            "raw_text": "",
            "reasoning_text": "",
            "tokens_used": 0,
            "latency_ms": latency_ms,
            "model_used": model,
        }
    except Exception as e:
        latency_ms = round((time.time() - t0) * 1000, 1)
        return {
            "status": "error",
            "error": str(e),
            "raw_text": "",
            "reasoning_text": "",
            "tokens_used": 0,
            "latency_ms": latency_ms,
            "model_used": model,
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_omniroute_client.py -v`
Expected: PASS

- [ ] **Step 5: Commit changes**

```bash
git add earnings_engine/data/omniroute_client.py tests/test_omniroute_client.py
git commit -m "feat(omniroute): add Claude Code 4-model catalog and execution adapter"
```

---

### Task 2: Build Customizable Prompt Generator with Section Toggles

**Files:**
- Modify: `earnings_engine/consensus/context_builder.py`
- Test: `tests/test_context_builder.py`

**Interfaces:**
- Produces:
  - `build_customized_prompt(ticker: str, timeframe_days: int = 14, include_technicals: bool = True, include_news: bool = True, include_institutional: bool = True, custom_directives: str | None = None, settings: Settings | None = None) -> tuple[str, str, dict[str, Any]]`
    - Returns `(system_prompt, user_prompt, context_dict)`

- [ ] **Step 1: Write the failing unit test for customizable prompt generation**

Create `tests/test_context_builder.py`:
```python
from earnings_engine.consensus.context_builder import build_customized_prompt

def test_build_customized_prompt_all_enabled():
    sys_p, user_p, ctx = build_customized_prompt(
        ticker="TATAMOTORS.NS",
        timeframe_days=14,
        include_technicals=True,
        include_news=True,
        include_institutional=True,
        custom_directives="Evaluate swing risk-reward"
    )
    assert "TATAMOTORS.NS" in user_p
    assert "Technical Momentum" in user_p
    assert "Corporate Catalysts" in user_p
    assert "Institutional" in user_p
    assert "Evaluate swing risk-reward" in user_p or "Evaluate swing risk-reward" in sys_p

def test_build_customized_prompt_toggles_disabled():
    sys_p, user_p, ctx = build_customized_prompt(
        ticker="TATAMOTORS.NS",
        timeframe_days=14,
        include_technicals=False,
        include_news=False,
        include_institutional=False,
        custom_directives=None
    )
    assert "TATAMOTORS.NS" in user_p
    assert "Technical Momentum & Price Structure" not in user_p
    assert "Corporate Catalysts & Breaking News" not in user_p
    assert "Institutional & Smart Money Flows" not in user_p
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_context_builder.py -v`
Expected: FAIL with `ImportError: cannot import name 'build_customized_prompt'`

- [ ] **Step 3: Implement `build_customized_prompt` in `context_builder.py`**

Add `build_customized_prompt` to `earnings_engine/consensus/context_builder.py` importing `get_horizon_system_prompt` and formatting only selected pillars into Markdown sections.

- [ ] **Step 4: Run test to verify it passes**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_context_builder.py -v`
Expected: PASS

- [ ] **Step 5: Commit changes**

```bash
git add earnings_engine/consensus/context_builder.py tests/test_context_builder.py
git commit -m "feat(consensus): implement customizable prompt generation with section toggles"
```

---

### Task 3: Implement `/api/v1/consensus/models` and `/api/v1/consensus/analyze` Endpoints

**Files:**
- Modify: `earnings_engine/api/routers/consensus.py`
- Modify: `earnings_engine/api/dependencies.py`
- Test: `tests/test_consensus_api.py`

**Interfaces:**
- Produces:
  - `GET /api/v1/consensus/models` -> `{ "models": [...] }`
  - `POST /api/v1/consensus/analyze` -> `{ "ticker": ..., "model": ..., "structured": {...}, "raw_text": ..., "reasoning_text": ..., "prompt_sent": ..., "latency_ms": ... }`
  - Backward compatibility: `/api/v1/consensus/predict` routes into the OmniRoute analyzer.

- [ ] **Step 1: Write the failing API test for models and analyze endpoints**

Create `tests/test_consensus_api.py`:
```python
from unittest.mock import patch
from fastapi.testclient import TestClient
from earnings_engine.api.server import create_app

app = create_app()
client = TestClient(app)

def test_get_consensus_models():
    resp = client.get("/api/v1/consensus/models")
    assert resp.status_code == 200
    data = resp.json()
    assert "models" in data
    ids = [m["id"] for m in data["models"]]
    assert "antigravityonly" in ids

@patch("earnings_engine.data.omniroute_client.execute_omniroute_analysis")
def test_post_consensus_analyze(mock_exec):
    mock_exec.return_value = {
        "status": "success",
        "raw_text": '```json\n{"direction": "BULLISH", "conviction_score": 88, "target_price": 1050.0, "stop_loss": 940.0, "risk_reward_ratio": 2.5, "thesis": "Strong momentum"}\n```',
        "reasoning_text": "Evaluating base breakout",
        "tokens_used": 500,
        "latency_ms": 1200.0,
        "model_used": "antigravityonly"
    }

    payload = {
        "ticker": "TATAMOTORS.NS",
        "model": "antigravityonly",
        "timeframe_days": 14,
        "include_technicals": True,
        "include_news": True,
        "include_institutional": True,
        "custom_prompt": "Evaluate support"
    }
    resp = client.post("/api/v1/consensus/analyze", json=payload)
    assert resp.status_code == 200
    res = resp.json()
    assert res["status"] == "success"
    assert res["structured"]["direction"] == "BULLISH"
    assert res["structured"]["target_price"] == 1050.0
    assert "Evaluating base breakout" in res["reasoning_text"]
    assert "prompt_sent" in res
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_consensus_api.py -v`
Expected: FAIL (404 or 422 on routes)

- [ ] **Step 3: Implement endpoints in `earnings_engine/api/routers/consensus.py`**

Define Pydantic schema `OmniRouteAnalyzeRequest` and endpoints:
1. `GET /api/v1/consensus/models`
2. `POST /api/v1/consensus/analyze`
3. JSON extraction helper for `structured` verdict.

- [ ] **Step 4: Run test to verify it passes**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_consensus_api.py -v`
Expected: PASS

- [ ] **Step 5: Commit changes**

```bash
git add earnings_engine/api/routers/consensus.py earnings_engine/api/dependencies.py tests/test_consensus_api.py
git commit -m "feat(api): add OmniRoute models and analyze endpoints with structured & raw parsing"
```

---

### Task 4: Redesign Dashboard Consensus HTML Template & Hub Mirror

**Files:**
- Modify: `earnings_engine/reports/templates/dashboard/_consensus.html`
- Modify: `earnings_engine/reports/templates/hubs/dashboard/_consensus.html`
- Modify: `earnings_engine/reports/templates/dashboard/_modals.html`
- Modify: `earnings_engine/reports/templates/hubs/dashboard/_modals.html`

**Interfaces:**
- Produces:
  - Top Control Bar:
    - Model Select (`#omniModelSelect`) populated with 4 Claude Code tiers.
    - Timeframe selector buttons (`#omniTf-3`, `#omniTf-7`, `#omniTf-14`, `#omniTf-30`, `#omniTf-90`).
    - Checkboxes: `#chkIncludeTechnicals`, `#chkIncludeNews`, `#chkIncludeInstitutional`.
    - Textarea: `#omniCustomDirectives` with preset quick-chips.
    - Run Button: `#omniRunAnalysisBtn`.
  - Results Deck (Split / Multi-tab layout):
    - Left Card: Structured Bias, Target Price, Stop Loss, R:R, Thesis, Risks.
    - Right Card: Tab navigation (`Raw Output`, `Thinking (<think>)`, `Prompt Sent`).

- [ ] **Step 1: Write HTML markup in `_consensus.html`**

Update `_consensus.html` with clean modern dark-theme styling matching Nexus Platform standards.

- [ ] **Step 2: Sync markup identically to hub mirror**

Copy the exact content to `earnings_engine/reports/templates/hubs/dashboard/_consensus.html`.

- [ ] **Step 3: Update Modal consensus section in `_modals.html` and hub mirror**

Replace legacy OpenRouter references in the stock detail/swing modal with the OmniRoute 4-tier model picker and raw inspector button.

- [ ] **Step 4: Verify template consistency with Python script**

Run PowerShell:
`python -c "assert open('earnings_engine/reports/templates/dashboard/_consensus.html').read() == open('earnings_engine/reports/templates/hubs/dashboard/_consensus.html').read()"`
Expected: No assertion error.

- [ ] **Step 5: Commit changes**

```bash
git add earnings_engine/reports/templates/dashboard/_consensus.html earnings_engine/reports/templates/hubs/dashboard/_consensus.html earnings_engine/reports/templates/dashboard/_modals.html earnings_engine/reports/templates/hubs/dashboard/_modals.html
git commit -m "feat(templates): redesign consensus tab and modal with OmniRoute customizer controls and raw inspector"
```

---

### Task 5: Redesign Consensus JavaScript Module (`consensus.js`)

**Files:**
- Modify: `earnings_engine/ui/js/modules/consensus.js`
- Modify: `earnings_engine/ui/js/dashboard.js` (if needed for global handlers)

**Interfaces:**
- Produces:
  - `app.loadOmniRouteModels()`
  - `app.runOmniRouteAnalysis(ticker, customOptions)`
  - `app.renderOmniRouteResults(data)`
  - `app.switchOmniInspectorTab(tabName)`
  - `app.copyOmniRawOutput()`
  - Auto-hydrates model dropdown on tab open and persists user toggle selections to `localStorage`.

- [ ] **Step 1: Implement OmniRoute model fetch and toggle persistence in `consensus.js`**

Add initialization logic:
- `fetch('/api/v1/consensus/models')` populates the dropdown.
- Load saved settings from `localStorage` for `selected_omni_model`, `include_technicals`, `include_news`, `include_institutional`.

- [ ] **Step 2: Implement `runOmniRouteAnalysis` with loading state & API dispatch**

Post payload to `/api/v1/consensus/analyze`, populate structured card and the 3 inspector tabs (Raw, Thinking, Prompt).

- [ ] **Step 3: Connect row buttons (`⚡ AI Consensus`) and modal triggers**

Update `runConsensusForTicker` to route directly through `runOmniRouteAnalysis`, updating badge cells across active tables.

- [ ] **Step 4: Run client test / syntax check with node or python**

Run: `.\.venv\Scripts\python.exe -c "import esprima; print('JS syntax valid')"` or node `--check earnings_engine/ui/js/modules/consensus.js`
Expected: Syntax OK.

- [ ] **Step 5: Commit changes**

```bash
git add earnings_engine/ui/js/modules/consensus.js earnings_engine/ui/js/dashboard.js
git commit -m "feat(ui): implement interactive OmniRoute customizer, prompt builder, and raw result inspector"
```

---

### Task 6: End-to-End Verification, Error Ledger Scan & Documentation

**Files:**
- Modify: `docs/superpowers/specs/2026-09-13-omniroute-redesign-design.md`
- Test: All targeted tests

- [ ] **Step 1: Run all unit and integration tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_omniroute_client.py tests/test_context_builder.py tests/test_consensus_api.py -v
```
Expected: All tests PASS.

- [ ] **Step 2: Run live verification against local OmniRoute endpoint**

Execute a test query via PowerShell:
```powershell
.\.venv\Scripts\python.exe -c "import requests; r = requests.post('http://localhost:8000/api/v1/consensus/analyze', json={'ticker':'TATAMOTORS.NS','model':'antigravityonly','timeframe_days':14,'include_technicals':True,'include_news':True,'include_institutional':True}); print('Status:', r.status_code); print('Structured:', r.json().get('structured'))"
```
Verify return values.

- [ ] **Step 3: Scan error ledger**

```powershell
.\.venv\Scripts\python.exe scripts/error_ledger.py scan
```
Verify zero new exceptions.

- [ ] **Step 4: Final commit and remote push**

```bash
git add .
git commit -m "feat(consensus): complete OmniRoute LLM Market Analysis redesign with Claude Code tiers"
git push origin new_report
```
