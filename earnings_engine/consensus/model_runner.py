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

# Default model suite via OpenRouter
DEFAULT_MODELS = [
    "deepseek/deepseek-r1",
    "meta-llama/llama-3.3-70b-instruct",
    "qwen/qwen-2.5-72b-instruct",
    "mistralai/mistral-large",
]

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

SYSTEM_PROMPT = """You are a quantitative stock analyst and swing trader. Given the stock analysis context below, provide your prediction as a STRICT JSON object with exactly these fields:

{
  "direction": "BULLISH" or "BEARISH" or "NEUTRAL",
  "confidence_pct": <integer 0-100>,
  "target_return_pct": <float, expected % return over the timeframe>,
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
}

Rules:
- Respond with ONLY the JSON object. No markdown, no explanation, no commentary.
- confidence_pct reflects how certain you are in the direction call (0-100).
- target_return_pct is positive for BULLISH, negative for BEARISH, near-zero for NEUTRAL.
- stop_loss_price should be a sensible invalidation level below support (for bullish) or above resistance (for bearish).
- key_drivers should list 2-3 concise reasons for your directional call.
- primary_risk should state the single biggest risk to your thesis.
- All price fields should use the same currency as the context."""

# Short display names for model IDs
MODEL_DISPLAY_NAMES: dict[str, str] = {
    "deepseek/deepseek-r1": "DeepSeek-R1",
    "deepseek/deepseek-chat": "DeepSeek-V3",
    "meta-llama/llama-3.3-70b-instruct": "Llama-3.3-70B",
    "qwen/qwen-2.5-72b-instruct": "Qwen-2.5-72B",
    "mistralai/mistral-large": "Mistral-Large",
    "mistralai/mistral-large-2411": "Mistral-Large",
    "mistralai/mistral-large-2407": "Mistral-Large",
}


def _get_api_key() -> str:
    """Retrieve OpenRouter API key from environment."""
    key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not key:
        raise ValueError(
            "OPENROUTER_API_KEY not set. Add it to your .env file. "
            "Get one at https://openrouter.ai/keys"
        )
    return key


def _query_single_model(
    model_id: str,
    prompt: str,
    api_key: str,
    timeout: int = 60,
) -> dict[str, Any]:
    """Send a prediction request to a single model via OpenRouter.

    Returns a dict with model_name, the parsed prediction fields,
    or an error entry if the call fails.
    """
    display_name = MODEL_DISPLAY_NAMES.get(model_id, model_id.split("/")[-1])
    start = time.perf_counter()

    try:
        resp = requests.post(
            OPENROUTER_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://earnings-engine.local",
                "X-Title": "Earnings Engine Consensus",
            },
            json={
                "model": model_id,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.3,
                "max_tokens": 2048,
            },
            timeout=timeout,
        )

        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info("[CONSENSUS] %s responded in %.0fms (HTTP %d)", display_name, elapsed_ms, resp.status_code)

        if resp.status_code != 200:
            logger.warning("[CONSENSUS] %s HTTP error %d: %s", display_name, resp.status_code, resp.text[:200])
            return {"model_name": display_name, "model_id": model_id, "error": f"HTTP {resp.status_code}", "raw": resp.text[:200]}

        data = resp.json()
        choice = (data.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        content = msg.get("content") or ""
        reasoning = msg.get("reasoning") or ""

        # For reasoning models where content might be null/empty, check reasoning or alternative fields
        if not content and reasoning:
            content = reasoning

        # Parse the JSON response — handle markdown code fences and reasoning tags
        prediction = _parse_model_json(content)
        if prediction is None:
            raw_preview = (content if isinstance(content, str) else str(content)) or ""
            logger.warning("[CONSENSUS] %s returned unparseable response: %.200s", display_name, raw_preview)
            return {"model_name": display_name, "model_id": model_id, "error": "Unparseable JSON", "raw_response": raw_preview[:500]}

        prediction["model_name"] = display_name
        prediction["model_id"] = model_id
        prediction["latency_ms"] = round(elapsed_ms)

        # Usage stats if available
        usage = data.get("usage", {})
        if usage:
            prediction["tokens_used"] = usage.get("total_tokens", 0)

        return prediction

    except requests.Timeout:
        logger.warning("[CONSENSUS] %s timed out after %ds", display_name, timeout)
        return {"model_name": display_name, "model_id": model_id, "error": f"Timeout after {timeout}s"}
    except Exception as e:
        logger.error("[CONSENSUS] %s unexpected error: %s", display_name, e)
        return {"model_name": display_name, "model_id": model_id, "error": str(e)}


def _parse_model_json(content: Any) -> dict[str, Any] | None:
    """Extract and parse JSON from model response, handling code fences and thinking tags."""
    if not content or not isinstance(content, str):
        return None

    # Strip thinking tags (DeepSeek-R1 uses <think>...</think>)
    import re
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()

    # Try direct parse first
    try:
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    # Try extracting from markdown code fences
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

    return None


def run_consensus_models(
    context: dict[str, Any],
    models: list[str] | None = None,
    timeout: int = 60,
) -> list[dict[str, Any]]:
    """Run prediction prompts across multiple LLMs in parallel.

    Args:
        context: The assembled context dict from context_builder.build_context().
        models: List of OpenRouter model IDs. Defaults to DEFAULT_MODELS.
        timeout: Per-model timeout in seconds.

    Returns:
        List of prediction dicts, one per model (including errored ones).
    """
    models = models or DEFAULT_MODELS
    api_key = _get_api_key()
    prompt = context_to_prompt(context)
    ticker = context.get("ticker", "UNKNOWN")
    timeframe = context.get("timeframe_days", 14)

    # Add the prediction ask to the prompt
    full_prompt = f"{prompt}\n\n---\n**Task:** Predict the price direction of {ticker} over the next {timeframe} trading days. Respond with ONLY a JSON object."

    logger.info("[CONSENSUS] Dispatching %s to %d models...", ticker, len(models))

    results: list[dict[str, Any]] = []

    with ThreadPoolExecutor(max_workers=len(models)) as executor:
        futures = {
            executor.submit(_query_single_model, model_id, full_prompt, api_key, timeout): model_id
            for model_id in models
        }
        for future in as_completed(futures):
            model_id = futures[future]
            try:
                result = future.result()
                result["timeframe_days"] = timeframe
                results.append(result)
            except Exception as e:
                display_name = MODEL_DISPLAY_NAMES.get(model_id, model_id)
                logger.error("[CONSENSUS] %s future error: %s", display_name, e)
                results.append({"model_name": display_name, "model_id": model_id, "error": str(e)})

    successful = sum(1 for r in results if "error" not in r)
    logger.info("[CONSENSUS] %s: %d/%d models responded successfully", ticker, successful, len(models))

    return results
