"""Free AI News & Catalyst Analysis Engine powered by OmniRouter.

Executes real-time quantitative and structural catalyst analysis using OmniRouter
(OpenAI-compatible multi-model gateway e.g. https://api.omnirouter.ai/v1 or custom proxy)
with instant heuristic fallback when offline.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from typing import Any

import requests

from earnings_engine.config import Settings
from earnings_engine.data.catalysts_news import score_catalyst_headline

logger = logging.getLogger("earnings_engine.data.ai_news_analyzer")

# OmniRouter Configuration
DEFAULT_OMNIROUTER_URL = "https://api.omnirouter.ai/v1/chat/completions"

DEFAULT_OMNIROUTER_MODELS = [
    "deepseek/deepseek-r1:free",
    "google/gemma-4-31b-it:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "google/gemini-2.0-flash-001",
    "deepseek/deepseek-r1",
    "meta-llama/llama-3.3-70b-instruct",
    "google/gemini-2.0-flash",
    "qwen/qwen-2.5-72b-instruct",
    "gpt-4o-mini",
]

AI_SYSTEM_PROMPT = """You are an institutional trading analyst and financial quantitative engine.
Analyze the provided corporate news headline and context for an Indian or global equity.
Evaluate the market sentiment, short-term volatility impact, price trajectory, and key catalyst drivers.

Return your response strictly as a JSON object with the following schema:
{
  "direction": "BULLISH" | "BEARISH" | "NEUTRAL",
  "impact_score": <integer from 25 to 99 representing catalyst magnitude>,
  "impact_level": "HIGH" | "MEDIUM" | "LOW",
  "expected_horizon": "📅 1-3 Days" | "📅 1-2 Weeks" | "📅 Positional",
  "volatility_est": "±1% to ±3%" | "±2% to ±6%" | "±5% to ±12%",
  "trading_takeaway": "<1-2 sentences concise institutional trade rationale / setup explanation>",
  "target_price": <float or null, projected short-term price target based on signal_price>,
  "stop_loss": <float or null, defensive technical invalidation price based on signal_price>,
  "confidence_pct": <integer 0-100>,
  "key_catalyst_triggers": ["<short trigger 1>", "<short trigger 2>"],
  "primary_risk": "<single biggest risk to this thesis>"
}

Directives:
- Respond with ONLY the raw JSON object. No markdown code blocks, no backticks, no commentary.
- target_price must be above signal_price for BULLISH, below signal_price for BEARISH.
- If signal_price is provided, calculate realistic price targets (typically 2% to 8% move).
- Focus on material revenue accretion, margin expansion/contraction, and institutional order book impact."""


def get_omnirouter_endpoint() -> str:
    """Resolve the active OmniRouter chat completions URL from environment."""
    url = os.getenv("OMNIROUTER_API_URL") or os.getenv("OMNI_ROUTER_URL")
    if url:
        url = url.strip()
        if not url.endswith("/chat/completions"):
            url = url.rstrip("/") + "/chat/completions" if "/v1" in url else url.rstrip("/") + "/v1/chat/completions"
        return url

    base = os.getenv("OMNIROUTER_BASE_URL") or os.getenv("OMNI_BASE_URL")
    if base:
        base = base.strip().rstrip("/")
        return f"{base}/chat/completions" if "/v1" in base else f"{base}/v1/chat/completions"

    # If OPENROUTER_API_KEY is configured in .env and no custom OMNIROUTER_URL, use OpenRouter gateway
    if os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENROUTER_BASE_URL"):
        return os.getenv("OPENROUTER_BASE_URL") or "https://openrouter.ai/api/v1/chat/completions"

    return DEFAULT_OMNIROUTER_URL


def get_omnirouter_api_key() -> str:
    """Resolve OmniRouter API key from environment with OpenRouter/OpenAI fallback."""
    return (
        os.getenv("OMNIROUTER_API_KEY")
        or os.getenv("OMNI_API_KEY")
        or os.getenv("OMNIROUTER_KEY")
        or os.getenv("OPENROUTER_API_KEY")
        or os.getenv("OPENAI_API_KEY", "")
    ).strip()


def build_news_analysis_prompt(item: dict[str, Any]) -> str:
    """Format structured context for the LLM news analysis."""
    ticker = item.get("ticker", "UNKNOWN")
    stock_name = item.get("stock_name") or ticker
    title = item.get("title", "").strip()
    summary = item.get("summary", "").strip()
    signal_price = item.get("signal_price")
    current_price = item.get("current_price") or signal_price
    published_at = item.get("published_at", "")
    verified_nums = item.get("verified_numbers") or {}
    if isinstance(verified_nums, str):
        try:
            verified_nums = json.loads(verified_nums)
        except Exception:
            verified_nums = {}

    lines = [
        f"Ticker: {ticker} ({stock_name})",
        f"Headline: {title}",
        f"Summary / Excerpt: {summary}",
        f"Published At: {published_at}",
    ]
    if signal_price and signal_price > 0:
        lines.append(f"Pre-News Reference Close (Signal Price): INR {signal_price:.2f}")
    if current_price and current_price > 0:
        lines.append(f"Latest Market Price: INR {current_price:.2f}")
    if verified_nums:
        nums_desc = ", ".join(f"{k}: {v}" for k, v in verified_nums.items() if v is not None)
        if nums_desc:
            lines.append(f"Verified Financial Figures: {nums_desc}")

    return "\n".join(lines)


def _heuristic_fallback_analysis(item: dict[str, Any]) -> dict[str, Any]:
    """Fast deterministic rule-based analysis used when offline or without API keys."""
    title = item.get("title", "")
    summary = item.get("summary", "")
    sig_p = item.get("signal_price") or item.get("current_price") or 100.0

    scored = score_catalyst_headline(title, summary)
    direction = scored.get("direction", "NEUTRAL")
    impact_score = scored.get("impact_score", 50)
    impact_level = scored.get("impact_level", "MEDIUM")
    horizon = scored.get("expected_horizon", "📅 1-3 Days")
    volatility = scored.get("volatility_est", "±1% to ±4%")
    why_it_matters = scored.get("why_it_matters", "")

    target_price = None
    stop_loss = None
    if sig_p and sig_p > 0:
        if direction == "BULLISH":
            target_price = round(sig_p * 1.045, 2)
            stop_loss = round(sig_p * 0.98, 2)
        elif direction == "BEARISH":
            target_price = round(sig_p * 0.955, 2)
            stop_loss = round(sig_p * 1.02, 2)

    return {
        "direction": direction,
        "impact_score": impact_score,
        "impact_level": impact_level,
        "expected_horizon": horizon,
        "volatility_est": volatility,
        "trading_takeaway": why_it_matters or f"Calculated {direction} catalyst trigger ({volatility}) over {horizon}.",
        "target_price": target_price,
        "stop_loss": stop_loss,
        "confidence_pct": min(95, max(60, impact_score + 10)),
        "key_catalyst_triggers": [scored.get("category", "General Corporate News")],
        "primary_risk": "Broader market volatility or immediate profit booking at open.",
        "ai_model": "heuristic-engine-v1",
        "ai_analyzed_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "latency_ms": 0.4,
        "tokens_used": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "raw_response": json.dumps({
            "direction": direction,
            "impact_score": impact_score,
            "impact_level": impact_level,
            "target_price": target_price,
            "stop_loss": stop_loss,
            "engine": "heuristic-engine-v1"
        }, indent=2),
    }


def analyze_news_catalyst_ai(
    item: dict[str, Any],
    settings: Settings | None = None,
    preferred_model: str | None = None,
    timeout: int = 15,
) -> dict[str, Any]:
    """Execute AI analysis of a news catalyst using OmniRouter with heuristic fallback."""
    settings = settings or Settings()
    api_key = get_omnirouter_api_key()
    endpoint = get_omnirouter_endpoint()

    # Determine model list
    configured_model = os.getenv("OMNIROUTER_MODEL") or preferred_model
    models_to_try = [configured_model] if configured_model else DEFAULT_OMNIROUTER_MODELS

    prompt = build_news_analysis_prompt(item)

    for model_name in models_to_try:
        if not model_name:
            continue
        try:
            logger.info("[OMNIROUTER] Analyzing news for %s using model %s at %s...", item.get("ticker"), model_name, endpoint)
            
            headers = {
                "Content-Type": "application/json",
                "HTTP-Referer": "https://earnings-engine.local",
                "X-Title": "Earnings Engine OmniRouter",
            }
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"

            t0 = time.perf_counter()
            resp = requests.post(
                endpoint,
                headers=headers,
                json={
                    "model": model_name,
                    "messages": [
                        {"role": "system", "content": AI_SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.2,
                    "max_tokens": 350,
                },
                timeout=timeout,
            )
            latency_ms = round((time.perf_counter() - t0) * 1000, 1)

            if resp.status_code == 200:
                data = resp.json()
                choice = (data.get("choices") or [{}])[0]
                msg = choice.get("message") or {}
                raw_content = (msg.get("content") or msg.get("reasoning") or "").strip()
                usage = data.get("usage") or {}
                total_toks = usage.get("total_tokens") or (usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0))

                # Clean markdown wrapper if model returns ```json ... ```
                clean_json = re.sub(r"^```(?:json)?", "", raw_content, flags=re.MULTILINE).strip()
                clean_json = re.sub(r"```$", "", clean_json, flags=re.MULTILINE).strip()

                try:
                    parsed = json.loads(clean_json)
                    parsed["ai_model"] = f"omnirouter/{model_name}"
                    parsed["ai_analyzed_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                    parsed["latency_ms"] = latency_ms
                    parsed["tokens_used"] = total_toks
                    parsed["prompt_tokens"] = usage.get("prompt_tokens")
                    parsed["completion_tokens"] = usage.get("completion_tokens")
                    parsed["raw_response"] = raw_content or clean_json
                    parsed["prompt_used"] = prompt
                    logger.info("[OMNIROUTER] Successfully analyzed %s with %s in %sms (direction=%s, impact=%s)",
                                item.get("ticker"), model_name, latency_ms, parsed.get("direction"), parsed.get("impact_score"))
                    return parsed
                except json.JSONDecodeError:
                    m = re.search(r"\{.*\}", clean_json, re.DOTALL)
                    if m:
                        try:
                            parsed = json.loads(m.group(0))
                            parsed["ai_model"] = f"omnirouter/{model_name}"
                            parsed["ai_analyzed_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                            parsed["latency_ms"] = latency_ms
                            parsed["tokens_used"] = total_toks
                            parsed["prompt_tokens"] = usage.get("prompt_tokens")
                            parsed["completion_tokens"] = usage.get("completion_tokens")
                            parsed["raw_response"] = raw_content or clean_json
                            parsed["prompt_used"] = prompt
                            return parsed
                        except Exception:
                            pass
            elif resp.status_code in (429, 404, 503):
                logger.warning("[OMNIROUTER] Model %s returned HTTP %s; trying next model...", model_name, resp.status_code)
                continue
            else:
                logger.warning("[OMNIROUTER] Model %s failed with HTTP %s: %.150s", model_name, resp.status_code, resp.text)
                continue
        except Exception as e:
            logger.debug("[OMNIROUTER] Exception querying %s: %s", model_name, e)
            continue

    logger.info("[OMNIROUTER] Endpoint unavailable or offline; using deterministic analysis for %s", item.get("ticker"))
    return _heuristic_fallback_analysis(item)
