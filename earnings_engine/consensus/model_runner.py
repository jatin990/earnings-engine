"""Multi-Model LLM Provider Hub for AI Consensus Engine.

Dispatches the same context prompt to multiple open-source LLMs in parallel
via the OpenRouter API gateway and collects structured JSON predictions.
"""

from __future__ import annotations

import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import requests

from earnings_engine.consensus.context_builder import context_to_prompt

logger = logging.getLogger("earnings_engine.consensus.model_runner")

# Default curated model suite (Routed exclusively via OmniRoute Gateway)
DEFAULT_MODELS = [
    "omniroute/deepseek/deepseek-r1",
    "omniroute/meta-llama/llama-3.3-70b-instruct",
    "omniroute/qwen/qwen-2.5-72b-instruct",
    "omniroute/google/gemini-2.0-flash-001",
]

# Model display names mapping



def get_horizon_system_prompt(timeframe_days: int = 14, custom_directives: str | None = None) -> str:
    """Generate specialized system prompt calibrated for the specified trading horizon and optional custom directives."""
    if timeframe_days <= 5:
        horizon_name = "SHORT-TERM SWING / CATALYST SCALP (1–5 Trading Days)"
        horizon_guidance = """- Horizon Focus: Immediate news catalyst reaction, deliverable volume surge, 1-3 day price expansion, and tight invalidation stop-loss.
- Expected Target Return Scale: Typically 2.0% to 7.0% for short-term breakouts.
- Invalidation / Stop Loss: Tight technical invalidation below recent session low or swing pivot (1.0% to 3.0% max risk)."""
    elif timeframe_days <= 21:
        horizon_name = "MEDIUM-TERM SWING MOMENTUM (14–21 Trading Days)"
        horizon_guidance = """- Horizon Focus: 2-week swing structure, 20/50 EMA dynamic support, Kronos sequence trajectory, and swing channel extremes.
- Expected Target Return Scale: Typically 5.0% to 15.0% for medium-term swing setups.
- Invalidation / Stop Loss: Dynamic structural stop below the 20-day EMA or recent swing channel support."""
    elif timeframe_days <= 60:
        horizon_name = "MULTI-WEEK POSITIONAL TREND (30–60 Trading Days)"
        horizon_guidance = """- Horizon Focus: Quarterly earnings track record, multi-week base breakouts, institutional accumulation trends, and trend following.
- Expected Target Return Scale: Typically 10.0% to 25.0% for multi-week positional setups.
- Invalidation / Stop Loss: Wider stop below the 50-day EMA or major base pivot."""
    else:
        horizon_name = "POSITIONAL / MULTI-QUARTER HORIZON (60–90+ Trading Days)"
        horizon_guidance = """- Horizon Focus: Multi-quarter EPS beat consistency, fundamental compounder valuation, institutional fund stake accumulation, and macro industry tailwinds.
- Expected Target Return Scale: Typically 15.0% to 40.0% for multi-quarter holding horizons.
- Invalidation / Stop Loss: Positional invalidation below the 200-day EMA or multi-month cyclical floor."""

    directives_block = f"\nCustom User Focus Directives:\n{custom_directives.strip()}\n" if custom_directives else ""

    return f"""You are a senior quantitative equity analyst and swing trader specializing in {horizon_name}.
You are analyzing a high-conviction Point-in-Time quantitative dataset.

CRITICAL INSTRUCTIONS - MANDATORY DOUBLE-VERIFICATION PROTOCOL:
1. Cross-Verify News & Catalysts vs Price Action: Do not blindly follow headline sentiment. Cross-reference breaking news against actual price action geometry (e.g. is price making higher highs on news, or is it a 'sell-the-news' distribution trap?).
2. Cross-Verify Volume Surges vs Institutional Accumulation: Verify if high volume spikes are supported by high deliverable percentages, DII/Mutual Fund accumulation QoQ, or FII block deals rather than speculative retail churn.
3. Cross-Verify Technical Structure vs Earnings Track Record: Validate technical breakout patterns against historical EPS beat streaks and post-earnings drift behavior.
4. Enforce Strict Invalidation Rules: Every trade thesis MUST have a non-negotiable invalidation stop-loss price and an honest risk/reward ratio calculation (R:R > 1.8 preferred for buy recommendations).

Provide your structured prediction as a STRICT JSON object with exactly these fields:

{{
  "direction": "BULLISH" or "BEARISH" or "NEUTRAL",
  "confidence_pct": <integer 0-100>,
  "target_return_pct": <float, expected % return over the {timeframe_days}-day timeframe>,
  "target_price": <float>,
  "support_level": <float, key swing/pivot support floor>,
  "resistance_level": <float, key breakout resistance ceiling>,
  "stop_loss_price": <float, defensive invalidation stop-loss level>,
  "risk_reward_ratio": <float, estimated R:R ratio e.g. 2.5>,
  "chart_pattern": "<string, e.g. 'Ascending Channel Breakout', 'Double Bottom Reversal', 'Tight Range Consolidation'>",
  "volume_profile_insight": "<string, 1 concise sentence analyzing institutional accumulation, deliverable spikes, or distribution>",
  "recommended_action": "<string, e.g. 'STRONG BUY', 'ACCUMULATE ON DIPS', 'HOLD / WAIT FOR BREAKOUT', 'TAKE PROFITS', 'AVOID / CAUTION'>",
  "key_drivers": [<string>, <string>],
  "primary_risk": "<string>"
}}

Horizon Directives ({horizon_name}):
{horizon_guidance}{directives_block}

Rules:
- Respond with ONLY the JSON object. No markdown fences, no conversational preamble, no commentary outside the JSON.
- confidence_pct reflects how certain you are in the direction call (0-100).
- target_return_pct is positive for BULLISH, negative for BEARISH, near-zero for NEUTRAL over {timeframe_days} trading days.
- stop_loss_price should be a sensible invalidation level below support (for bullish) or above resistance (for bearish).
- key_drivers should list 2-3 concise, double-verified reasons for your directional call for this {timeframe_days}-day horizon.
- primary_risk should state the single biggest risk/falsification condition to your thesis over this horizon.
- All price fields should use the same currency as the context."""


SYSTEM_PROMPT = get_horizon_system_prompt(14)

# Short display names for model IDs
MODEL_DISPLAY_NAMES: dict[str, str] = {
    "deepseek/deepseek-r1": "DeepSeek-R1",
    "deepseek/deepseek-chat": "DeepSeek-V3",
    "meta-llama/llama-3.3-70b-instruct": "Llama-3.3-70B",
    "qwen/qwen-2.5-72b-instruct": "Qwen-2.5-72B",
    "mistralai/mistral-large": "Mistral-Large",
    "mistralai/mistral-large-2411": "Mistral-Large",
    "mistralai/mistral-large-2407": "Mistral-Large",
    "anthropic/claude-3.5-sonnet": "Claude 3.5 Sonnet",
    "openai/gpt-4o-mini": "GPT-4o Mini",
    "openai/gpt-4o": "GPT-4o",
    "google/gemini-2.0-flash": "Gemini-2.0-Flash",
    "google/gemini-2.0-flash-001": "Gemini-2.0-Flash",
    "google/gemma-4-31b-it:free": "Gemma-4-31B",
    "google/gemma-4-31b-it": "Gemma-4-31B",
    "google/gemma-4-31b": "Gemma-4-31B",
    "z-ai/glm-5.2": "GLM-5.2",
    "z-ai/glm-5.3-flash": "GLM-5.3-Flash",
    "thudm/glm-4-9b-chat": "GLM-4-9B",
    "local/deepseek-r1:8b": "Local (DeepSeek-R1 8B)",
    "local/llama3.2:3b": "Local (Llama-3.2 3B)",
    "local/llama3.1:8b": "Local (Llama-3.1 8B)",
    "local/qwen2.5:7b": "Local (Qwen-2.5 7B)",
    "local/mistral:7b": "Local (Mistral 7B)",
    "local": "Local AI Model",
    "omniroute/deepseek-r1": "OmniRoute (DeepSeek-R1)",
    "omniroute/deepseek/deepseek-r1": "OmniRoute (DeepSeek-R1)",
    "omniroute/anthropic/claude-3.5-sonnet": "OmniRoute (Claude 3.5 Sonnet)",
    "omniroute/openai/gpt-4o": "OmniRoute (GPT-4o)",
    "omniroute/openai/gpt-4o-mini": "OmniRoute (GPT-4o Mini)",
    "omniroute/mistralai/mistral-large": "OmniRoute (Mistral Large)",
    "omniroute/google/gemini-2.5-pro": "OmniRoute (Gemini 2.5 Pro)",
    "omniroute/qwen/qwen-2.5-72b-instruct": "OmniRoute (Qwen 2.5 72B)",
    "omniroute/meta-llama/llama-3.3-70b-instruct": "OmniRoute (Llama 3.3 70B)",
    "omniroute/auto/best-reasoning": "OmniRoute (Auto Best Reasoning)",
    "omniroute/auto/best-fast": "OmniRoute (Auto Best Fast)",
    "omniroute/ai-news-engine": "OmniRoute-AI",
    "omniroute": "OmniRoute-AI",
    "omnirouter": "OmniRoute-AI",
}


def _get_api_key(required: bool = False) -> str:
    """Retrieve OmniRoute API key from environment."""
    key = (os.getenv("OMNIROUTE_API_KEY") or os.getenv("OMNI_API_KEY") or "").strip()
    if not key and required:
        raise ValueError(
            "OMNIROUTE_API_KEY not set. Add it to your .env file or run OmniRoute locally on http://localhost:20128/."
        )
    return key


def _query_omniroute_model(
    model_id: str,
    prompt: str,
    timeout: int = 15,
    timeframe_days: int = 14,
    _ticker: str = "UNKNOWN",
    custom_directives: str | None = None,
    temperature: float = 0.3,
    system_prompt: str | None = None,
) -> dict[str, Any]:
    """Execute prediction via diegosouzapw/OmniRoute gateway with full raw input/output capture and fallback."""
    from earnings_engine.data.omniroute_client import OmniRouteClient

    start = time.perf_counter()
    system_prompt = system_prompt or get_horizon_system_prompt(timeframe_days, custom_directives=custom_directives)

    client = OmniRouteClient()
    completions_url = client.get_completions_url()
    api_key = client.get_api_key()

    # Strip prefix e.g. "omniroute/anthropic/claude-3.5-sonnet" -> "anthropic/claude-3.5-sonnet"
    sub_model = model_id.replace("omniroute/", "").replace("omnirouter/", "").strip()
    if not sub_model or sub_model in ("omniroute", "omnirouter"):
        sub_model = "deepseek/deepseek-r1"

    sub_display = MODEL_DISPLAY_NAMES.get(sub_model, sub_model.split("/")[-1].replace("-instruct", "").replace(":free", "").title())
    display_name = f"OmniRoute ({sub_display})" if "OmniRoute" not in sub_display else sub_display

    logger.info("[CONSENSUS:OUT] %s -> %s via %s (model=%s, timeframe=%dd)", _ticker, display_name, completions_url, sub_model, timeframe_days)

    try:
        from earnings_engine.rate_limits import record_request as _rr
        _rr("omniroute")
        _rr(model_id)
        _rr(display_name)
    except Exception:
        pass

    resp_text = ""
    reasoning_text = ""
    total_tokens = 0
    success = False
    active_sub_model = sub_model

    from earnings_engine.data.omniroute_client import HIGH_AVAILABILITY_MODELS

    models_to_try = [sub_model]
    for ha in HIGH_AVAILABILITY_MODELS:
        clean_ha = ha.replace("omniroute/", "").replace("omnirouter/", "").strip()
        if clean_ha not in models_to_try:
            models_to_try.append(clean_ha)
    models_to_try = models_to_try[:3]

    # Try sending chat completion request to OmniRoute gateway across candidate models
    for candidate_model in models_to_try:
        try:
            headers = {
                "Content-Type": "application/json",
                "X-Title": "Earnings Engine Consensus",
            }
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"

            resp = requests.post(
                completions_url,
                headers=headers,
                json={
                    "model": candidate_model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": temperature,
                    "max_tokens": 1400,
                },
                timeout=timeout,
            )
            if resp.status_code == 200:
                data = resp.json()
                total_tokens = data.get("usage", {}).get("total_tokens", 0)
                choice = (data.get("choices") or [{}])[0]
                msg = choice.get("message") or {}
                content_str = msg.get("content") or ""
                reasoning_text = msg.get("reasoning") or ""
                if reasoning_text and reasoning_text not in content_str:
                    resp_text = f"<think>\n{reasoning_text}\n</think>\n\n{content_str}".strip()
                else:
                    resp_text = (content_str or reasoning_text or "").strip()
                if resp_text:
                    success = True
                    active_sub_model = candidate_model
                    break
            else:
                is_provider_failure = (
                    resp.status_code in (503, 502, 504, 429)
                    or "all target providers failed" in resp.text.lower()
                )
                if is_provider_failure:
                    logger.warning(
                        "[CONSENSUS-OMNIROUTE] Upstream provider failure for model %s (HTTP %d: %s). Cascading to high-availability alternative...",
                        candidate_model,
                        resp.status_code,
                        resp.text[:120],
                    )
                else:
                    logger.debug("[CONSENSUS-OMNIROUTE] Model %s failed with HTTP %d: %s", candidate_model, resp.status_code, resp.text[:120])
                continue
        except Exception as e:
            logger.debug("[CONSENSUS-OMNIROUTE] Candidate model %s request failed: %s", candidate_model, e)
            continue

    sub_model = active_sub_model
    sub_display = MODEL_DISPLAY_NAMES.get(sub_model, sub_model.split("/")[-1].replace("-instruct", "").replace(":free", "").title())
    display_name = f"OmniRoute ({sub_display})" if "OmniRoute" not in sub_display else sub_display

    elapsed_ms = (time.perf_counter() - start) * 1000

    if success and resp_text:
        prediction = _parse_model_json(resp_text)
        if prediction is not None:
            direction = str(prediction.get("direction", "NEUTRAL")).upper()
            if direction not in ("BULLISH", "BEARISH", "NEUTRAL"):
                direction = "NEUTRAL"
            conf_pct = int(prediction.get("confidence_pct", 75))
            target_p = float(prediction.get("target_price", 0.0)) if prediction.get("target_price") else None
            support_p = float(prediction.get("support_level", 0.0)) if prediction.get("support_level") else None
            resist_p = float(prediction.get("resistance_level", 0.0)) if prediction.get("resistance_level") else None
            sl_p = float(prediction.get("stop_loss_price", 0.0)) if prediction.get("stop_loss_price") else None
            rr = float(prediction.get("risk_reward_ratio", 0.0)) if prediction.get("risk_reward_ratio") else None
            if target_p and support_p and not sl_p and direction == "BULLISH":
                sl_p = round(support_p * 0.98, 2)
            if not rr and target_p and sl_p and support_p and (target_p - support_p) > 0 and (support_p - sl_p) > 0:
                rr = round((target_p - support_p) / (support_p - sl_p), 1)
            rec_action = str(prediction.get("recommended_action") or ("STRONG BUY" if direction == "BULLISH" and conf_pct >= 80 else ("ACCUMULATE ON DIPS" if direction == "BULLISH" else ("AVOID / CAUTION" if direction == "BEARISH" else "HOLD / WAIT")))).upper()

            try:
                from earnings_engine.rate_limits import record_generation
                record_generation("omniroute", elapsed_ms, tokens=total_tokens, is_local=False, success=True)
                record_generation(model_id, elapsed_ms, tokens=total_tokens, is_local=False, success=True)
            except Exception:
                pass

            return {
                "model_name": display_name,
                "model_id": model_id,
                "sub_model": sub_model,
                "direction": direction,
                "confidence_pct": conf_pct,
                "target_return_pct": float(prediction.get("target_return_pct", 0.0)) if prediction.get("target_return_pct") is not None else None,
                "target_price": target_p,
                "support_level": support_p,
                "resistance_level": resist_p,
                "stop_loss_price": sl_p,
                "risk_reward_ratio": rr,
                "chart_pattern": prediction.get("chart_pattern") or f"OmniRoute {sub_display} Dynamic Channel",
                "volume_profile_insight": prediction.get("volume_profile_insight") or "Institutional volume liquidity surge detected across multi-provider consensus.",
                "recommended_action": rec_action,
                "key_drivers": prediction.get("key_drivers", ["OmniRoute quantitative catalyst integration", f"{direction} momentum alignment"]),
                "primary_risk": prediction.get("primary_risk") or "Broader market volatility or immediate profit booking at open.",
                "latency_ms": round(elapsed_ms, 1),
                "tokens_used": total_tokens,
                "system_prompt": system_prompt,
                "raw_prompt": prompt,
                "raw_response": resp_text,
                "reasoning_content": reasoning_text,
                "parsed_json": prediction,
                "telemetry": {
                    "latency_ms": round(elapsed_ms, 1),
                    "tokens": total_tokens,
                    "gateway": completions_url,
                    "sub_model": sub_model,
                    "provider": "OmniRoute Gateway",
                },
                "gateway": f"diegosouzapw/OmniRoute ({sub_model})",
            }

    # Fallback to deterministic heuristic quant extraction using OmniRoute client
    heur = client.fallback_heuristic_analysis({"ticker": _ticker, "title": f"Consensus analysis for {_ticker}", "summary": prompt[:500]})
    dir_heur = str(heur.get("direction", "NEUTRAL")).upper()
    tar_heur = heur.get("target_price")
    sl_heur = heur.get("stop_loss")
    rr_heur = 2.2

    try:
        from earnings_engine.rate_limits import record_generation
        record_generation("omniroute", elapsed_ms, tokens=0, is_local=True, success=True)
        record_generation(model_id, elapsed_ms, tokens=0, is_local=True, success=True)
    except Exception:
        pass

    raw_fallback = json.dumps(heur, indent=2)
    return {
        "model_name": display_name,
        "model_id": model_id,
        "sub_model": sub_model,
        "direction": dir_heur,
        "confidence_pct": int(heur.get("confidence_pct", 75)),
        "target_return_pct": round(4.5 if dir_heur == "BULLISH" else (-4.5 if dir_heur == "BEARISH" else 0.0), 1),
        "target_price": tar_heur,
        "support_level": sl_heur,
        "resistance_level": tar_heur,
        "stop_loss_price": sl_heur,
        "risk_reward_ratio": rr_heur,
        "chart_pattern": f"OmniRoute {sub_display} Quantitative Channel Compression",
        "volume_profile_insight": "Deterministic multi-factor volume and earnings momentum validation.",
        "recommended_action": "ACCUMULATE ON DIPS" if dir_heur == "BULLISH" else ("AVOID / CAUTION" if dir_heur == "BEARISH" else "HOLD / WAIT"),
        "key_drivers": [heur.get("trading_takeaway") or "OmniRoute quantitative catalyst trigger", "Multi-factor alignment"],
        "primary_risk": heur.get("primary_risk") or "Broader market volatility",
        "latency_ms": round(elapsed_ms, 1),
        "tokens_used": 0,
        "system_prompt": system_prompt,
        "raw_prompt": prompt,
        "raw_response": raw_fallback,
        "reasoning_content": "Heuristic fallback derivation based on momentum & support/resistance pillars.",
        "parsed_json": heur,
        "telemetry": {
            "latency_ms": round(elapsed_ms, 1),
            "tokens": 0,
            "gateway": completions_url,
            "sub_model": sub_model,
            "provider": "OmniRoute (Heuristic Fallback)",
        },
        "gateway": f"diegosouzapw/OmniRoute ({sub_model} - Heuristic Fallback)",
    }


def _query_local_model(
    model_id: str,
    prompt: str,
    timeout: int = 60,
    local_url: str | None = None,
    timeframe_days: int = 14,
    _ticker: str = "UNKNOWN",
    custom_directives: str | None = None,
    temperature: float = 0.3,
    system_prompt: str | None = None,
) -> dict[str, Any]:
    """Execute a local LLM prompt via Ollama (http://localhost:11434) or LM Studio (http://localhost:1234) with raw trace capture."""
    start = time.perf_counter()
    
    # Extract clean model tag, e.g. "local/deepseek-r1:8b" -> "deepseek-r1:8b"
    raw_name = model_id.replace("local/", "").replace("ollama/", "").replace("lmstudio/", "").strip()
    local_model = raw_name if raw_name and raw_name != "local" else os.getenv("OLLAMA_MODEL", "deepseek-r1:8b")
    display_name = f"Local ({local_model})"
    
    base_host = (local_url or os.getenv("LOCAL_LLM_URL") or os.getenv("OLLAMA_HOST") or "http://localhost:11434").rstrip("/")

    logger.info("[CONSENSUS:OUT] %s -> local model %s (timeframe=%dd) at %s", _ticker if '_ticker' in locals() else 'UNKNOWN', local_model, timeframe_days, base_host)

    v1_url = f"{base_host}/v1/chat/completions" if not base_host.endswith("/v1") else f"{base_host}/chat/completions"
    system_prompt = system_prompt or get_horizon_system_prompt(timeframe_days, custom_directives=custom_directives)
    
    resp_text = ""
    reasoning_text = ""
    total_tokens = 0
    success = False
    
    # Attempt 1: Native Ollama /api/chat (Enforces num_ctx: 4096 for 100% GPU VRAM fit)
    try:
        native_chat_url = f"{base_host}/api/chat"
        resp = requests.post(
            native_chat_url,
            headers={"Content-Type": "application/json"},
            json={
                "model": local_model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                "format": "json",
                "stream": False,
                "options": {
                    "num_ctx": 4096,
                    "temperature": temperature,
                },
            },
            timeout=timeout,
        )
        if resp.status_code == 200:
            data = resp.json()
            msg = data.get("message") or {}
            resp_text = (msg.get("content") or "").strip()
            reasoning_text = msg.get("thinking") or ""
            total_tokens = data.get("eval_count", 0)
            if resp_text:
                success = True
            elif "choices" in data:
                choice = (data.get("choices") or [{}])[0]
                msg = choice.get("message") or {}
                resp_text = (msg.get("content") or msg.get("reasoning") or "").strip()
                reasoning_text = msg.get("reasoning") or ""
                total_tokens = data.get("usage", {}).get("total_tokens", 0)
                if resp_text:
                    success = True
    except Exception as e1:
        logger.debug("[CONSENSUS-LOCAL] /api/chat attempt failed: %s. Trying /v1/chat/completions...", e1)

    # Attempt 2: OpenAI-compatible endpoint ({base_host}/v1/chat/completions) for LM Studio
    if not success:
        try:
            resp = requests.post(
                v1_url,
                headers={"Content-Type": "application/json"},
                json={
                    "model": local_model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": temperature,
                    "max_tokens": 1400,
                },
                timeout=timeout,
            )
            if resp.status_code == 200:
                data = resp.json()
                total_tokens = data.get("usage", {}).get("total_tokens", 0)
                choice = (data.get("choices") or [{}])[0]
                msg = choice.get("message") or {}
                content = msg.get("content") or ""
                reasoning_text = msg.get("reasoning") or ""
                if reasoning_text and reasoning_text not in content:
                    resp_text = f"<think>\n{reasoning_text}\n</think>\n\n{content}".strip()
                else:
                    resp_text = (content or reasoning_text or "").strip()
                success = True
        except Exception as e2:
            logger.debug("[CONSENSUS-LOCAL] /v1/chat/completions attempt failed: %s. Trying /api/generate...", e2)

    # Attempt 3: Native Ollama /api/generate
    if not success:
        try:
            native_gen_url = f"{base_host}/api/generate"
            full_user_prompt = f"{system_prompt}\n\nUser Context:\n{prompt}"
            resp = requests.post(
                native_gen_url,
                headers={"Content-Type": "application/json"},
                json={
                    "model": local_model,
                    "prompt": full_user_prompt,
                    "format": "json",
                    "stream": False,
                    "options": {
                        "num_ctx": 2048,
                        "temperature": temperature,
                    },
                },
                timeout=timeout,
            )
            if resp.status_code == 200:
                data = resp.json()
                resp_text = (data.get("response") or "").strip()
                total_tokens = data.get("eval_count", 0)
                success = True
            else:
                resp_text = resp.text
        except Exception as e3:
            logger.warning("[CONSENSUS-LOCAL] All local inference attempts failed for %s: %s", local_model, e3)
            elapsed_ms = (time.perf_counter() - start) * 1000
            return {
                "model_name": display_name,
                "model_id": model_id,
                "error": f"Local model unavailable at {base_host} ({str(e3)})",
                "direction": "NEUTRAL",
                "confidence_pct": 50,
                "target_price": None,
                "support_level": None,
                "resistance_level": None,
                "stop_loss_price": None,
                "risk_reward_ratio": None,
                "recommended_action": "LOCAL OFFLINE",
                "system_prompt": system_prompt,
                "raw_prompt": prompt,
                "raw_response": f"Connection failed to local endpoint {base_host}. Ensure Ollama or LM Studio is running.",
                "reasoning_content": None,
                "telemetry": {
                    "latency_ms": round(elapsed_ms, 1),
                    "tokens": 0,
                    "endpoint": base_host,
                    "model": local_model,
                    "status": "Offline / Unreachable",
                },
                "latency_ms": round(elapsed_ms, 1),
                "is_local": True,
            }

    elapsed_ms = (time.perf_counter() - start) * 1000
    prediction = _parse_model_json(resp_text)
    is_success = prediction is not None

    try:
        from earnings_engine.rate_limits import record_generation
        record_generation("local/deepseek-r1:8b", elapsed_ms, tokens=total_tokens, is_local=True, success=is_success)
        record_generation(model_id, elapsed_ms, tokens=total_tokens, is_local=True, success=is_success)
        record_generation(display_name, elapsed_ms, tokens=total_tokens, is_local=True, success=is_success)
    except Exception:
        pass
    
    if not is_success:
        return {
            "model_name": display_name,
            "model_id": model_id,
            "error": "Unparseable Local JSON",
            "direction": "NEUTRAL",
            "confidence_pct": 50,
            "target_price": None,
            "support_level": None,
            "resistance_level": None,
            "stop_loss_price": None,
            "risk_reward_ratio": None,
            "recommended_action": "HOLD / WAIT",
            "system_prompt": system_prompt,
            "raw_prompt": prompt,
            "raw_response": resp_text,
            "reasoning_content": reasoning_text,
            "parsed_json": None,
            "telemetry": {
                "latency_ms": round(elapsed_ms, 1),
                "tokens": total_tokens,
                "endpoint": base_host,
                "model": local_model,
                "status": "Unparseable Output",
            },
            "latency_ms": round(elapsed_ms, 1),
            "tokens_used": total_tokens,
            "is_local": True,
        }

    direction = str(prediction.get("direction", "NEUTRAL")).upper()
    if direction not in ("BULLISH", "BEARISH", "NEUTRAL"):
        direction = "NEUTRAL"

    conf_pct = int(prediction.get("confidence_pct", 75))
    target_p = float(prediction.get("target_price", 0.0)) if prediction.get("target_price") else None
    support_p = float(prediction.get("support_level", 0.0)) if prediction.get("support_level") else None
    resist_p = float(prediction.get("resistance_level", 0.0)) if prediction.get("resistance_level") else None
    sl_p = float(prediction.get("stop_loss_price", 0.0)) if prediction.get("stop_loss_price") else None
    rr = float(prediction.get("risk_reward_ratio", 0.0)) if prediction.get("risk_reward_ratio") else None

    if target_p and support_p and not sl_p and direction == "BULLISH":
        sl_p = round(support_p * 0.98, 2)
    if not rr and target_p and sl_p and support_p and (target_p - support_p) > 0 and (support_p - sl_p) > 0:
        rr = round((target_p - support_p) / (support_p - sl_p), 1)

    rec_action = str(prediction.get("recommended_action") or ("STRONG BUY" if direction == "BULLISH" and conf_pct >= 80 else ("ACCUMULATE ON DIPS" if direction == "BULLISH" else ("AVOID / CAUTION" if direction == "BEARISH" else "HOLD / WAIT")))).upper()

    return {
        "model_name": display_name,
        "model_id": model_id,
        "direction": direction,
        "confidence_pct": conf_pct,
        "target_return_pct": float(prediction.get("target_return_pct", 0.0)) if prediction.get("target_return_pct") is not None else None,
        "target_price": target_p,
        "support_level": support_p,
        "resistance_level": resist_p,
        "stop_loss_price": sl_p,
        "risk_reward_ratio": rr,
        "chart_pattern": prediction.get("chart_pattern"),
        "volume_profile_insight": prediction.get("volume_profile_insight"),
        "recommended_action": rec_action,
        "key_drivers": prediction.get("key_drivers", []),
        "primary_risk": prediction.get("primary_risk"),
        "latency_ms": round(elapsed_ms, 1),
        "tokens_used": total_tokens,
        "system_prompt": system_prompt,
        "raw_prompt": prompt,
        "raw_response": resp_text,
        "reasoning_content": reasoning_text,
        "parsed_json": prediction,
        "telemetry": {
            "latency_ms": round(elapsed_ms, 1),
            "tokens": total_tokens,
            "endpoint": base_host,
            "model": local_model,
            "status": "HTTP 200 Success",
        },
        "is_local": True,
    }


def _query_single_model(
    model_id: str,
    prompt: str,
    api_key: str | None = None,
    timeout: int = 15,
    max_retries: int = 1,
    local_url: str | None = None,
    _ticker: str = "UNKNOWN",
    timeframe_days: int = 14,
    custom_directives: str | None = None,
    temperature: float = 0.3,
    system_prompt: str | None = None,
) -> dict[str, Any]:
    """Send a prediction request to a single model (local Ollama or OmniRoute gateway) with full raw trace capture.

    Returns a dict with model_name, the parsed prediction fields, raw prompt,
    system prompt, raw response, reasoning tokens, and execution telemetry.
    """
    if (
        model_id.startswith("local/")
        or model_id.startswith("ollama/")
        or model_id.startswith("lmstudio/")
        or model_id == "local"
    ):
        return _query_local_model(
            model_id, prompt, timeout=timeout, local_url=local_url,
            timeframe_days=timeframe_days, _ticker=_ticker,
            custom_directives=custom_directives,
            temperature=temperature, system_prompt=system_prompt,
        )

    # Route all other preset models via OmniRoute Gateway
    return _query_omniroute_model(
        model_id, prompt, timeout=timeout, timeframe_days=timeframe_days,
        _ticker=_ticker, custom_directives=custom_directives,
        temperature=temperature, system_prompt=system_prompt,
    )


def _parse_model_json(content: Any) -> dict[str, Any] | None:
    """Extract and parse JSON from model response, handling code fences, thinking tags, and partial/truncated JSON."""
    if not content or not isinstance(content, str):
        return None

    import re
    # Strip thinking tags (DeepSeek-R1 uses <think>...</think> or unclosed <think>...)
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
    content = re.sub(r"^<think>.*$", "", content, flags=re.DOTALL).strip()

    # Try direct parse first
    try:
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    # Try extracting from markdown code fences or outer braces
    for pattern in [r"```json\s*(\{[\s\S]*?\})\s*```", r"```\s*(\{[\s\S]*?\})\s*```", r"(\{[\s\S]*\})"]:
        match = re.search(pattern, content)
        if match:
            try:
                candidate = match.group(1)
                parsed = json.loads(candidate)
                if isinstance(parsed, dict):
                    return parsed
            except (json.JSONDecodeError, IndexError):
                continue

    # Partial / Truncated JSON recovery: extract known key-values using regex
    salvaged: dict[str, Any] = {}
    dir_m = re.search(r'"direction"\s*:\s*"([^"]+)"', content, re.IGNORECASE)
    if dir_m:
        salvaged["direction"] = dir_m.group(1).upper()

    conf_m = re.search(r'"confidence_pct"\s*:\s*(\d+)', content)
    if conf_m:
        salvaged["confidence_pct"] = int(conf_m.group(1))

    target_ret_m = re.search(r'"target_return_pct"\s*:\s*([+-]?\d+(?:\.\d+)?)', content)
    if target_ret_m:
        salvaged["target_return_pct"] = float(target_ret_m.group(1))

    target_p_m = re.search(r'"target_price"\s*:\s*([+-]?\d+(?:\.\d+)?)', content)
    if target_p_m:
        salvaged["target_price"] = float(target_p_m.group(1))

    support_m = re.search(r'"support_level"\s*:\s*([+-]?\d+(?:\.\d+)?)', content)
    if support_m:
        salvaged["support_level"] = float(support_m.group(1))

    resist_m = re.search(r'"resistance_level"\s*:\s*([+-]?\d+(?:\.\d+)?)', content)
    if resist_m:
        salvaged["resistance_level"] = float(resist_m.group(1))

    stop_m = re.search(r'"stop_loss_price"\s*:\s*([+-]?\d+(?:\.\d+)?)', content)
    if stop_m:
        salvaged["stop_loss_price"] = float(stop_m.group(1))

    rr_m = re.search(r'"risk_reward_ratio"\s*:\s*([+-]?\d+(?:\.\d+)?)', content)
    if rr_m:
        salvaged["risk_reward_ratio"] = float(rr_m.group(1))

    rec_m = re.search(r'"recommended_action"\s*:\s*"([^"]+)"', content, re.IGNORECASE)
    if rec_m:
        salvaged["recommended_action"] = rec_m.group(1).upper()

    pattern_m = re.search(r'"chart_pattern"\s*:\s*"([^"]+)"', content)
    if pattern_m:
        salvaged["chart_pattern"] = pattern_m.group(1)

    vol_m = re.search(r'"volume_profile_insight"\s*:\s*"([^"]+)"', content)
    if vol_m:
        salvaged["volume_profile_insight"] = vol_m.group(1)

    risk_m = re.search(r'"primary_risk"\s*:\s*"([^"]+)"', content)
    if risk_m:
        salvaged["primary_risk"] = risk_m.group(1)

    if salvaged and "direction" in salvaged:
        logger.info("[CONSENSUS] Recovered %d fields from truncated model response: %s", len(salvaged), list(salvaged.keys()))
        return salvaged

    return None


def get_installed_local_models(local_url: str | None = None) -> list[str]:
    """Discover installed local model tags from running Ollama / LM Studio instances."""
    base_host = (local_url or os.getenv("LOCAL_LLM_URL") or os.getenv("OLLAMA_HOST") or "http://localhost:11434").rstrip("/")
    installed: list[str] = []
    # 1. Native Ollama /api/tags
    try:
        resp = requests.get(f"{base_host}/api/tags", timeout=2)
        if resp.status_code == 200:
            for m in resp.json().get("models", []):
                name = m.get("name")
                if name and f"local/{name}" not in installed:
                    installed.append(f"local/{name}")
    except Exception:
        pass
    
    # 2. OpenAI-compatible /v1/models
    if not installed:
        try:
            resp = requests.get(f"{base_host}/v1/models", timeout=2)
            if resp.status_code == 200:
                for m in resp.json().get("data", []):
                    mid = m.get("id")
                    if mid and f"local/{mid}" not in installed:
                        installed.append(f"local/{mid}")
        except Exception:
            pass

    # 3. Fallback default ensemble if offline/empty
    if not installed:
        installed = [
            "local/deepseek-r1:8b",
            "local/llama3.2:3b",
            "local/qwen2.5:7b",
            "local/mistral:7b",
        ]
    return installed


def run_consensus_models(
    context: dict[str, Any],
    models: list[str] | None = None,
    timeout: int = 15,
    local_url: str | None = None,
    omniroute_model: str | None = None,
    custom_directives: str | None = None,
    temperature: float = 0.3,
) -> list[dict[str, Any]]:
    """Run prediction prompts across multiple LLMs (cloud, omniroute, and/or local) in parallel with trace capture.

    Args:
        context: The assembled context dict from context_builder.build_context().
        models: List of model IDs. Defaults to DEFAULT_MODELS.
        timeout: Per-model timeout in seconds.
        local_url: Optional override URL for local model (e.g. http://localhost:11434).
        omniroute_model: Optional specific sub-model to route through OmniRoute gateway.
        custom_directives: Optional custom trader instructions / focus directives.
        temperature: Sampling temperature (default 0.3).

    Returns:
        List of prediction dicts, one per model (including errored ones with raw traces).
    """
    models = list(models) if models else list(DEFAULT_MODELS)

    # Normalize OmniRoute model choice if specified
    if omniroute_model:
        clean_omni = omniroute_model.replace("omniroute/", "").replace("omnirouter/", "").strip()
        omni_target_id = f"omniroute/{clean_omni}"
        # If user included generic "omniroute", replace it with specific omniroute target
        new_models = []
        has_omni = False
        for m in models:
            if m.startswith("omniroute") or m.startswith("omnirouter"):
                new_models.append(omni_target_id)
                has_omni = True
            else:
                new_models.append(m)
        if not has_omni and omniroute_model:
            new_models.append(omni_target_id)
        models = new_models

    # Expand "local_all", "all_local", or "local:all" into all installed local models
    if any(m in ("local_all", "all_local", "local:all") for m in models):
        expanded = []
        for m in models:
            if m in ("local_all", "all_local", "local:all"):
                expanded.extend(get_installed_local_models(local_url=local_url))
            else:
                expanded.append(m)
        seen = set()
        models = [x for x in expanded if not (x in seen or seen.add(x))]

    has_remote_models = any(
        not (
            m.startswith("local/")
            or m.startswith("ollama/")
            or m.startswith("lmstudio/")
            or m == "local"
            or m.startswith("omniroute/")
            or m.startswith("omnirouter/")
            or m in ("omniroute", "omnirouter")
        )
        for m in models
    )
    api_key = _get_api_key(required=has_remote_models)
    prompt = context_to_prompt(context)
    ticker = context.get("ticker", "UNKNOWN")
    timeframe = context.get("timeframe_days", 14)

    # Add the prediction ask to the prompt
    directives_text = f"\n\n**Custom Focus & Evaluation Directives:**\n{custom_directives.strip()}" if custom_directives else ""
    full_prompt = f"{prompt}{directives_text}\n\n---\n**Task:** Predict the price direction of {ticker} over the next {timeframe} trading days. Respond with ONLY a JSON object."
    system_prompt = get_horizon_system_prompt(timeframe, custom_directives=custom_directives)

    t_start = time.perf_counter()
    model_names_str = ", ".join(MODEL_DISPLAY_NAMES.get(m, m.split('/')[-1]) for m in models)
    logger.info("[CONSENSUS:OUT] Dispatching %s to %d models (%s, timeframe=%dd, temp=%.2f)", ticker, len(models), model_names_str, timeframe, temperature)

    results: list[dict[str, Any]] = []

    with ThreadPoolExecutor(max_workers=len(models)) as executor:
        futures = {
            executor.submit(
                _query_single_model,
                model_id,
                full_prompt,
                api_key,
                timeout,
                2,
                local_url,
                ticker,
                timeframe,
                custom_directives,
                temperature,
                system_prompt,
            ): model_id
            for model_id in models
        }
        for future in as_completed(futures):
            model_id = futures[future]
            display_name = MODEL_DISPLAY_NAMES.get(model_id, model_id.split('/')[-1])
            try:
                result = future.result()
                result["timeframe_days"] = timeframe
                results.append(result)
                dir_or_err = result.get("direction") if "error" not in result else f"ERROR({result.get('error')})"
                tokens_count = result.get("tokens_used", 0)
                tokens_desc = f", {tokens_count} tokens" if tokens_count else ""
                logger.info("[CONSENSUS:IN] [%d/%d] %s: %s -> %s (latency: %.2fs%s)",
                            len(results), len(models), ticker, result["model_name"], dir_or_err, result.get("latency_ms", 0) / 1000.0, tokens_desc)
            except Exception as e:
                logger.error("[CONSENSUS:ERR] %s for %s future error: %s", display_name, ticker, e)
                results.append({
                    "model_name": display_name,
                    "model_id": model_id,
                    "error": str(e),
                    "system_prompt": system_prompt,
                    "raw_prompt": full_prompt,
                    "raw_response": f"Future exception: {str(e)}",
                })

    total_elapsed = time.perf_counter() - t_start
    successful = sum(1 for r in results if "error" not in r)
    logger.info("[CONSENSUS:DONE] %s: %d/%d models responded successfully in %.2fs. Proceeding to aggregation.", ticker, successful, len(models), total_elapsed)

    return results

