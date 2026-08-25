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

# Fallback models when primary model encounters 429 rate limit or 404 endpoint deprecation
MODEL_FALLBACKS: dict[str, str] = {
    "mistralai/mistral-large": "google/gemini-2.0-flash-001",
    "mistralai/mistral-large-2411": "mistralai/mistral-large",
    "mistralai/mistral-large-2407": "mistralai/mistral-large",
    "qwen/qwen-2.5-72b-instruct": "meta-llama/llama-3.3-70b-instruct",
    "deepseek/deepseek-r1": "deepseek/deepseek-chat",
}

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
    "google/gemini-2.0-flash-001": "Gemini-2.0-Flash",
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
    max_retries: int = 2,
) -> dict[str, Any]:
    """Send a prediction request to a single model via OpenRouter with rate limit retry & fallback.

    Returns a dict with model_name, the parsed prediction fields,
    or an error entry if the call fails.
    """
    display_name = MODEL_DISPLAY_NAMES.get(model_id, model_id.split("/")[-1])
    current_model = model_id

    for attempt in range(max_retries + 1):
        start = time.perf_counter()
        logger.info("[CONSENSUS] Querying %s (%s, attempt %d/%d)...", display_name, current_model, attempt + 1, max_retries + 1)
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
                    "model": current_model,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.3,
                    "max_tokens": 4096,
                },
                timeout=timeout,
            )

            try:
                from earnings_engine.rate_limits import record_request, update_openrouter_headers
                record_request("openrouter", resp.status_code)
                record_request(current_model, resp.status_code)
                record_request(display_name, resp.status_code)
                update_openrouter_headers(dict(resp.headers))
            except Exception:
                pass

            elapsed_ms = (time.perf_counter() - start) * 1000

            # If rate limited (429), temporary server overload (502, 503), or model endpoint not found (404)
            if resp.status_code in (404, 429, 502, 503):
                logger.warning(
                    "[CONSENSUS] %s returned HTTP %d (attempt %d/%d in %.2fs): %.150s",
                    display_name, resp.status_code, attempt + 1, max_retries + 1, elapsed_ms / 1000.0, resp.text
                )
                if resp.status_code == 404:
                    if current_model in MODEL_FALLBACKS:
                        fallback_id = MODEL_FALLBACKS[current_model]
                        logger.info("[CONSENSUS] %s endpoint 404 not found. Failing over to fallback: %s", display_name, fallback_id)
                        current_model = fallback_id
                        display_name = f"{display_name} (via {MODEL_DISPLAY_NAMES.get(fallback_id, fallback_id.split('/')[-1])})"
                        continue
                elif attempt < max_retries:
                    sleep_sec = 1.5 * (attempt + 1)
                    time.sleep(sleep_sec)
                    continue
                elif current_model in MODEL_FALLBACKS:
                    fallback_id = MODEL_FALLBACKS[current_model]
                    logger.info("[CONSENSUS] %s rate-limited. Failing over to fallback: %s", display_name, fallback_id)
                    current_model = fallback_id
                    display_name = f"{display_name} (via {MODEL_DISPLAY_NAMES.get(fallback_id, fallback_id.split('/')[-1])})"
                    time.sleep(1.0)
                    continue

            if resp.status_code != 200:
                logger.warning("[CONSENSUS] %s HTTP error %d (in %.2fs): %s", display_name, resp.status_code, elapsed_ms / 1000.0, resp.text[:200])
                return {
                    "model_name": display_name,
                    "model_id": current_model,
                    "error": f"HTTP {resp.status_code}",
                    "direction": "NEUTRAL",
                    "confidence_pct": 50,
                    "target_price": None,
                    "support_level": None,
                    "resistance_level": None,
                    "stop_loss_price": None,
                    "risk_reward_ratio": None,
                    "recommended_action": "HOLD / WAIT",
                    "raw": resp.text[:200],
                }

            data = resp.json()
            total_tokens = data.get("usage", {}).get("total_tokens", 0)
            logger.info("[CONSENSUS] %s responded in %.2fs (HTTP 200, tokens=%d)", display_name, elapsed_ms / 1000.0, total_tokens)

            choice = (data.get("choices") or [{}])[0]
            msg = choice.get("message") or {}
            content = msg.get("content") or ""
            reasoning = msg.get("reasoning") or ""

            # For reasoning models where content might be in reasoning tag
            if not content and reasoning:
                content = reasoning

            # Parse the JSON response
            prediction = _parse_model_json(content)
            if prediction is None:
                raw_preview = (content if isinstance(content, str) else str(content)) or ""
                logger.warning("[CONSENSUS] %s returned unparseable response (%.2fs): %.200s", display_name, elapsed_ms / 1000.0, raw_preview)
                return {
                    "model_name": display_name,
                    "model_id": current_model,
                    "error": "Unparseable JSON",
                    "direction": "NEUTRAL",
                    "confidence_pct": 50,
                    "target_price": None,
                    "support_level": None,
                    "resistance_level": None,
                    "stop_loss_price": None,
                    "risk_reward_ratio": None,
                    "recommended_action": "HOLD / WAIT",
                    "raw_response": raw_preview[:500],
                }

            # Field normalization
            direction = str(prediction.get("direction", "NEUTRAL")).upper()
            if direction not in ("BULLISH", "BEARISH", "NEUTRAL"):
                direction = "NEUTRAL"

            conf_pct = int(prediction.get("confidence_pct", 75))
            target_p = float(prediction.get("target_price", 0.0)) if prediction.get("target_price") else None
            support_p = float(prediction.get("support_level", 0.0)) if prediction.get("support_level") else None
            resist_p = float(prediction.get("resistance_level", 0.0)) if prediction.get("resistance_level") else None
            sl_p = float(prediction.get("stop_loss_price", 0.0)) if prediction.get("stop_loss_price") else None
            rr = float(prediction.get("risk_reward_ratio", 0.0)) if prediction.get("risk_reward_ratio") else None

            # Fallback calculations if SL or RR missing
            if target_p and support_p and not sl_p and direction == "BULLISH":
                sl_p = round(support_p * 0.98, 2)
            if not rr and target_p and sl_p and support_p and (target_p - support_p) > 0 and (support_p - sl_p) > 0:
                rr = round((target_p - support_p) / (support_p - sl_p), 1)

            rec_action = str(prediction.get("recommended_action") or ("STRONG BUY" if direction == "BULLISH" and conf_pct >= 80 else ("ACCUMULATE ON DIPS" if direction == "BULLISH" else ("AVOID / CAUTION" if direction == "BEARISH" else "HOLD / WAIT")))).upper()

            logger.info("[CONSENSUS] %s parsed: direction=%s, conf=%d%%, target=%s, action=%s (latency=%.2fs)",
                        display_name, direction, conf_pct, target_p, rec_action, elapsed_ms / 1000.0)

            return {
                "model_name": display_name,
                "model_id": current_model,
                "direction": direction,
                "confidence_pct": conf_pct,
                "target_price": target_p,
                "target_return_pct": float(prediction.get("target_return_pct", 0.0)) if prediction.get("target_return_pct") is not None else None,
                "support_level": support_p,
                "resistance_level": resist_p,
                "stop_loss_price": sl_p,
                "risk_reward_ratio": rr,
                "recommended_action": rec_action,
                "chart_pattern": str(prediction.get("chart_pattern") or "Consolidation / Channel"),
                "volume_profile_insight": str(prediction.get("volume_profile_insight") or "Normal volume baseline"),
                "key_drivers": prediction.get("key_drivers") or [],
                "primary_risk": str(prediction.get("primary_risk") or "General market volatility"),
                "latency_ms": round(elapsed_ms),
                "tokens_used": total_tokens,
            }

        except requests.Timeout:
            if attempt < max_retries:
                time.sleep(1.0)
                continue
            logger.warning("[CONSENSUS] %s timed out after %ds", display_name, timeout)
            return {
                "model_name": display_name,
                "model_id": current_model,
                "error": f"Timeout after {timeout}s",
                "direction": "NEUTRAL",
                "confidence_pct": 50,
                "target_price": None,
                "support_level": None,
                "resistance_level": None,
                "stop_loss_price": None,
                "risk_reward_ratio": None,
                "recommended_action": "HOLD / WAIT",
            }
        except Exception as e:
            if attempt < max_retries:
                time.sleep(1.0)
                continue
            logger.error("[CONSENSUS] %s unexpected error: %s", display_name, e)
            return {
                "model_name": display_name,
                "model_id": current_model,
                "error": str(e),
                "direction": "NEUTRAL",
                "confidence_pct": 50,
                "target_price": None,
                "support_level": None,
                "resistance_level": None,
                "stop_loss_price": None,
                "risk_reward_ratio": None,
                "recommended_action": "HOLD / WAIT",
            }

    return {
        "model_name": display_name,
        "model_id": current_model,
        "error": "Max retries exceeded",
        "direction": "NEUTRAL",
        "confidence_pct": 50,
        "target_price": None,
        "support_level": None,
        "resistance_level": None,
        "stop_loss_price": None,
        "risk_reward_ratio": None,
        "recommended_action": "HOLD / WAIT",
    }


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

    t_start = time.perf_counter()
    model_names_str = ", ".join(MODEL_DISPLAY_NAMES.get(m, m.split('/')[-1]) for m in models)
    logger.info("[CONSENSUS] Dispatching %s to %d models (%s)...", ticker, len(models), model_names_str)

    results: list[dict[str, Any]] = []

    with ThreadPoolExecutor(max_workers=len(models)) as executor:
        futures = {
            executor.submit(_query_single_model, model_id, full_prompt, api_key, timeout): model_id
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
                logger.info("[CONSENSUS] [%d/%d completed] %s -> %s (latency: %.2fs)",
                            len(results), len(models), result["model_name"], dir_or_err, result.get("latency_ms", 0) / 1000.0)
            except Exception as e:
                logger.error("[CONSENSUS] %s future error: %s", display_name, e)
                results.append({"model_name": display_name, "model_id": model_id, "error": str(e)})

    total_elapsed = time.perf_counter() - t_start
    successful = sum(1 for r in results if "error" not in r)
    logger.info("[CONSENSUS] %s: %d/%d models responded successfully in %.2fs. Proceeding to aggregation.", ticker, successful, len(models), total_elapsed)

    return results
