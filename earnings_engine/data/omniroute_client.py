"""OmniRoute AI Gateway Client Adapter (diegosouzapw/OmniRoute).

Natively integrates with diegosouzapw/OmniRoute (https://github.com/diegosouzapw/OmniRoute),
an open-source self-hosted multi-LLM proxy and gateway (defaulting to http://localhost:20128/v1)
that aggregates 350+ AI providers and 1200+ models with quota-aware routing.
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

logger = logging.getLogger("earnings_engine.data.omniroute_client")

# Standard ports where diegosouzapw/OmniRoute may be hosted
OMNIROUTE_PROBE_PORTS = [20128, 20129, 8080, 3000]

DEFAULT_OMNIROUTE_MODELS = [
    "antigravity/gemini-3.7-flash-medium",
    "antigravity/gemini-3.7-flash-high",
    "auto/best-reasoning",
    "auto/best-fast",
    "auto/fast",
    "auto/cheap",
    "auto/best-free",
    "deepseek/deepseek-r1",
    "meta-llama/llama-3.3-70b-instruct",
    "google/gemini-2.0-flash",
    "qwen/qwen-2.5-72b-instruct",
    "gpt-4o-mini",
]
DEFAULT_OMNIROUTER_MODELS = DEFAULT_OMNIROUTE_MODELS

OMNIROUTE_SYSTEM_PROMPT = """You are an institutional trading analyst and financial quantitative engine.
Analyze the provided corporate news headline and context for an Indian or global equity.
Perform structured information extraction identifying the primary instrument, financial projections, sentiment polarity, and temporal originality.

Return your response strictly as a JSON object with the following schema:
{
  "ticker": "<primary financial instrument's ticker symbol, e.g. 'TCS.NS', 'RELIANCE.NS'>",
  "sentiment": "BULLISH" | "BEARISH" | "NEUTRAL",
  "direction": "BULLISH" | "BEARISH" | "NEUTRAL",
  "target_price": <float or null, projected short-term price target based on signal_price>,
  "stop_loss": <float or null, defensive technical invalidation price based on signal_price>,
  "financial_projections": {
    "target_price": <float or null>,
    "stop_loss": <float or null>,
    "order_value_cr": <float or null, explicit order/contract value in Crore>,
    "revenue_projection_cr": <float or null, projected revenue in Crore>,
    "ebitda_margin_pct": <float or null, projected margin %>,
    "growth_rate_pct": <float or null, projected growth rate %>,
    "raw_projections": ["<extracted forward projection or numeric quote>"]
  },
  "temporal_originality": "NEW_PUBLICATION" | "BREAKING" | "DEVELOPING" | "REPUBLICATION",
  "is_republication": <boolean, true if article is a re-hash/republication of older news, false if fresh/new>,
  "originality_rationale": "<1 sentence explaining why this is a new publication or republication>",
  "impact_score": <integer from 25 to 99 representing catalyst magnitude>,
  "impact_level": "HIGH" | "MEDIUM" | "LOW",
  "expected_horizon": "📅 1-3 Days" | "📅 1-2 Weeks" | "📅 Positional",
  "volatility_est": "±1% to ±3%" | "±2% to ±6%" | "±5% to ±12%",
  "trading_takeaway": "<1-2 sentences concise institutional trade rationale / setup explanation>",
  "confidence_pct": <integer 0-100>,
  "key_catalyst_triggers": ["<short trigger 1>", "<short trigger 2>"],
  "primary_risk": "<single biggest risk to this thesis>"
}

Directives:
- Respond with ONLY the raw JSON object. No markdown code blocks, no backticks, no commentary.
- target_price must be above signal_price for BULLISH, below signal_price for BEARISH.
- If signal_price is provided, calculate realistic price targets (typically 2% to 8% move).
- Explicitly assess temporal originality: detect if content is fresh primary news or a republication of past events.
- Focus on material revenue accretion, margin expansion/contraction, and institutional order book impact."""


class OmniRouteClient:
    """Client for diegosouzapw/OmniRoute multi-provider AI gateway."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()
        self._detected_endpoint: str | None = None
        self._last_probe_time: float = 0.0
        self._is_online: bool = False

    def get_configured_base_url(self) -> str:
        """Get the base URL from settings or environment."""
        url = (
            os.getenv("OMNIROUTER_API_URL")
            or os.getenv("OMNIROUTE_BASE_URL")
            or os.getenv("OMNIROUTE_URL")
            or os.getenv("OMNIROUTER_BASE_URL")
            or self.settings.omniroute_base_url
            or "http://localhost:20128/v1"
        ).strip().rstrip("/")
        if not url.endswith("/v1") and not url.endswith("/chat/completions"):
            url = f"{url}/v1"
        return url

    def get_api_key(self) -> str:
        """Resolve the OmniRoute API key or bearer token."""
        return (
            os.getenv("OMNIROUTER_API_KEY")
            or os.getenv("OMNIROUTE_API_KEY")
            or os.getenv("OMNI_API_KEY")
            or os.getenv("OMNIROUTER_KEY")
            or self.settings.omniroute_api_key
            or os.getenv("OPENROUTER_API_KEY")
            or os.getenv("OPENAI_API_KEY", "")
        ).strip()

    def probe_health(self, timeout: float = 1.5) -> dict[str, Any]:
        """Probe diegosouzapw/OmniRoute daemon to check availability and active models."""
        configured = self.get_configured_base_url()
        candidates = [configured]

        # Add localhost probe variations
        for port in OMNIROUTE_PROBE_PORTS:
            candidate = f"http://localhost:{port}/v1"
            if candidate not in candidates:
                candidates.append(candidate)
            ip_candidate = f"http://127.0.0.1:{port}/v1"
            if ip_candidate not in candidates:
                candidates.append(ip_candidate)

        api_key = self.get_api_key()
        headers = {"Accept": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        for base_url in candidates:
            models_endpoint = f"{base_url}/models"
            try:
                t0 = time.perf_counter()
                resp = requests.get(models_endpoint, headers=headers, timeout=timeout)
                latency = round((time.perf_counter() - t0) * 1000, 1)

                if resp.status_code == 200:
                    data = resp.json()
                    model_list = []
                    if isinstance(data, dict):
                        model_list = [m.get("id", str(m)) for m in (data.get("data") or data.get("models") or [])]
                    elif isinstance(data, list):
                        model_list = [m.get("id", str(m)) if isinstance(m, dict) else str(m) for m in data]

                    self._detected_endpoint = base_url
                    self._is_online = True
                    self._last_probe_time = time.time()
                    logger.info("[OMNIROUTE] Connected to diegosouzapw/OmniRoute at %s (%d models, %.1fms)", base_url, len(model_list), latency)
                    return {
                        "status": "online",
                        "endpoint": base_url,
                        "latency_ms": latency,
                        "models_count": len(model_list),
                        "models": model_list[:20],
                        "is_self_hosted": "localhost" in base_url or "127.0.0.1" in base_url,
                    }
                elif resp.status_code == 401 and ("omniroute" in str(resp.headers).lower() or "invalid_api_key" in resp.text or "Authentication required" in resp.text):
                    self._detected_endpoint = base_url
                    self._is_online = True
                    self._last_probe_time = time.time()
                    logger.info("[OMNIROUTE] Detected active diegosouzapw/OmniRoute on %s (Authentication Required)", base_url)
                    return {
                        "status": "auth_required" if not api_key else "auth_invalid",
                        "endpoint": base_url,
                        "latency_ms": latency,
                        "models_count": len(DEFAULT_OMNIROUTE_MODELS),
                        "models": DEFAULT_OMNIROUTE_MODELS,
                        "is_self_hosted": "localhost" in base_url or "127.0.0.1" in base_url,
                        "message": "OmniRoute daemon is active on http://localhost:20128/. Generate an API Key in the OmniRoute UI (http://localhost:20128/) and add OMNIROUTE_API_KEY to your .env file." if not api_key else "OmniRoute rejected the configured API Key. Please verify OMNIROUTE_API_KEY in .env.",
                    }
            except Exception as e:
                logger.debug("[OMNIROUTE] Probe check failed for %s: %s", base_url, e)

        # If probe failed on all candidates, check fallback gateway (OpenRouter)
        fallback_url = (
            os.getenv("OMNIROUTE_FALLBACK_URL")
            or os.getenv("OPENROUTER_BASE_URL")
            or self.settings.omniroute_fallback_url
        ).strip().rstrip("/")
        if api_key and fallback_url:
            self._detected_endpoint = fallback_url if fallback_url.endswith("/v1") else f"{fallback_url}/v1"
            self._is_online = True
            return {
                "status": "fallback_online",
                "endpoint": self._detected_endpoint,
                "latency_ms": 0.0,
                "models_count": len(DEFAULT_OMNIROUTE_MODELS),
                "models": DEFAULT_OMNIROUTE_MODELS,
                "is_self_hosted": False,
            }

        self._detected_endpoint = None
        self._is_online = False
        return {
            "status": "offline",
            "endpoint": configured,
            "latency_ms": 0.0,
            "models_count": 0,
            "models": [],
            "is_self_hosted": True,
            "message": f"OmniRoute daemon not detected on port 20128. Run 'npx omniroute' or 'docker run -p 20128:20128 diegosouzapw/omniroute'.",
        }

    def get_completions_url(self) -> str:
        """Resolve full completions URL with cached probe status."""
        configured = self.get_configured_base_url()
        # If user explicitly configured an external or custom URL in environment (not localhost default), honor it directly
        if configured and ("localhost" not in configured and "127.0.0.1" not in configured):
            return f"{configured.rstrip('/')}/chat/completions"
        if self._detected_endpoint and (time.time() - self._last_probe_time < 30.0):
            return f"{self._detected_endpoint.rstrip('/')}/chat/completions"
        health = self.probe_health()
        base = health.get("endpoint") or configured
        return f"{base.rstrip('/')}/chat/completions"

    def format_prompt(self, item: dict[str, Any]) -> str:
        """Format structured quantitative context for the OmniRoute analysis."""
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
            if signal_price and signal_price > 0:
                delta_pct = ((current_price - signal_price) / signal_price) * 100
                lines.append(f"Price Delta Since Signal: {delta_pct:+.2f}%")
        if verified_nums:
            nums_desc = ", ".join(f"{k}: {v}" for k, v in verified_nums.items() if v is not None)
            if nums_desc:
                lines.append(f"Verified Financial Figures: {nums_desc}")

        return "\n".join(lines)

    def analyze_catalyst(
        self,
        item: dict[str, Any],
        preferred_model: str | None = None,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        """Send catalyst context to diegosouzapw/OmniRoute with automatic model cascading and heuristic fallback."""
        timeout = timeout or self.settings.omniroute_timeout
        api_key = self.get_api_key()
        completions_url = self.get_completions_url()

        # If offline and no API key available, execute instant deterministic heuristic
        if not self._is_online and not api_key:
            logger.info("[OMNIROUTE] Gateway offline; using deterministic analysis for %s", item.get("ticker"))
            return self.fallback_heuristic_analysis(item)

        configured_model = preferred_model or os.getenv("OMNIROUTE_MODEL") or self.settings.omniroute_model
        models_to_try = [configured_model] if configured_model else DEFAULT_OMNIROUTER_MODELS
        for m in DEFAULT_OMNIROUTER_MODELS:
            if m not in models_to_try:
                models_to_try.append(m)

        prompt = self.format_prompt(item)
        headers = {
            "Content-Type": "application/json",
            "HTTP-Referer": "https://earnings-engine.local",
            "X-Title": "Earnings Engine diegosouzapw/OmniRoute Client",
        }
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        for model_name in models_to_try:
            if not model_name:
                continue
            try:
                logger.info("[OMNIROUTE] Querying diegosouzapw/OmniRoute for %s (model: %s, url: %s)...", item.get("ticker"), model_name, completions_url)
                t0 = time.perf_counter()
                resp = requests.post(
                    completions_url,
                    headers=headers,
                    json={
                        "model": model_name,
                        "messages": [
                            {"role": "system", "content": OMNIROUTE_SYSTEM_PROMPT},
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

                    clean_json = re.sub(r"^```(?:json)?", "", raw_content, flags=re.MULTILINE).strip()
                    clean_json = re.sub(r"```$", "", clean_json, flags=re.MULTILINE).strip()

                    try:
                        parsed = json.loads(clean_json)
                        ticker_extracted = (parsed.get("ticker") or item.get("ticker") or "UNKNOWN").strip().upper()
                        parsed["ticker"] = ticker_extracted
                        sentiment_val = (parsed.get("sentiment") or parsed.get("direction") or "NEUTRAL").strip().upper()
                        parsed["sentiment"] = sentiment_val if sentiment_val in ("BULLISH", "BEARISH", "NEUTRAL") else "NEUTRAL"
                        parsed["direction"] = parsed["sentiment"]

                        # Financial projections structured object
                        raw_proj = parsed.get("financial_projections") or {}
                        if not isinstance(raw_proj, dict):
                            raw_proj = {}
                        if parsed.get("target_price") and not raw_proj.get("target_price"):
                            raw_proj["target_price"] = parsed.get("target_price")
                        if parsed.get("stop_loss") and not raw_proj.get("stop_loss"):
                            raw_proj["stop_loss"] = parsed.get("stop_loss")
                        parsed["financial_projections"] = raw_proj

                        # Temporal originality assessment
                        temp_orig = (parsed.get("temporal_originality") or "NEW_PUBLICATION").strip().upper()
                        if temp_orig not in ("NEW_PUBLICATION", "BREAKING", "DEVELOPING", "REPUBLICATION"):
                            temp_orig = "REPUBLICATION" if parsed.get("is_republication") else "NEW_PUBLICATION"
                        parsed["temporal_originality"] = temp_orig
                        parsed["is_republication"] = bool(parsed.get("is_republication", temp_orig == "REPUBLICATION"))
                        parsed["originality_rationale"] = str(parsed.get("originality_rationale") or (
                            "Repetitive or historical recap of past event." if parsed["is_republication"] else "Novel primary news disclosure."
                        ))

                        parsed["ai_model"] = f"omniroute/{model_name}"
                        parsed["ai_analyzed_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                        parsed["latency_ms"] = latency_ms
                        parsed["tokens_used"] = total_toks
                        parsed["prompt_tokens"] = usage.get("prompt_tokens", 0)
                        parsed["completion_tokens"] = usage.get("completion_tokens", 0)
                        parsed["raw_response"] = raw_content or clean_json
                        parsed["gateway"] = "diegosouzapw/OmniRoute"
                        parsed["gateway_url"] = completions_url

                        # Validate and sanitize quantitative boundaries
                        sig_p = item.get("signal_price") or item.get("current_price")
                        if sig_p and sig_p > 0:
                            if parsed.get("direction") == "BULLISH" and (not parsed.get("target_price") or parsed.get("target_price") <= sig_p):
                                parsed["target_price"] = round(sig_p * 1.045, 2)
                                raw_proj["target_price"] = parsed["target_price"]
                            if parsed.get("direction") == "BULLISH" and (not parsed.get("stop_loss") or parsed.get("stop_loss") >= sig_p):
                                parsed["stop_loss"] = round(sig_p * 0.98, 2)
                                raw_proj["stop_loss"] = parsed["stop_loss"]
                            if parsed.get("direction") == "BEARISH" and (not parsed.get("target_price") or parsed.get("target_price") >= sig_p):
                                parsed["target_price"] = round(sig_p * 0.955, 2)
                                raw_proj["target_price"] = parsed["target_price"]
                            if parsed.get("direction") == "BEARISH" and (not parsed.get("stop_loss") or parsed.get("stop_loss") <= sig_p):
                                parsed["stop_loss"] = round(sig_p * 1.02, 2)
                                raw_proj["stop_loss"] = parsed["stop_loss"]

                        logger.info("[OMNIROUTE] Completed %s analysis via %s in %.1fms (%d tokens)", item.get("ticker"), model_name, latency_ms, total_toks)
                        return parsed
                    except json.JSONDecodeError as jde:
                        logger.warning("[OMNIROUTE] JSON decode error from %s: %s (Raw: %s)", model_name, jde, raw_content[:200])
                        continue
                else:
                    logger.warning("[OMNIROUTE] Model %s failed with HTTP %d: %s", model_name, resp.status_code, resp.text[:200])
                    continue
            except Exception as exc:
                logger.debug("[OMNIROUTE] Exception contacting %s via %s: %s", model_name, completions_url, exc)
                continue

        logger.info("[OMNIROUTE] Daemon / models unavailable; executing deterministic analysis for %s", item.get("ticker"))
        return self.fallback_heuristic_analysis(item)

    def fallback_heuristic_analysis(self, item: dict[str, Any]) -> dict[str, Any]:
        """Fast deterministic rule-based analysis used when OmniRoute is offline."""
        title = item.get("title", "")
        summary = item.get("summary", "")
        ticker = (item.get("ticker") or "UNKNOWN").strip().upper()
        sig_p = item.get("signal_price") or item.get("current_price") or 100.0

        scored = score_catalyst_headline(title, summary)
        direction = scored.get("direction", "NEUTRAL")
        sentiment = direction
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

        # Extract explicit financial projections from text and verified numbers
        order_val: float | None = None
        rev_proj: float | None = None
        margin_pct: float | None = None
        growth_pct: float | None = None
        raw_projections: list[str] = []

        combined_text = f"{title} {summary}"
        order_match = re.search(r"(?:₹|rs\.?|inr)?\s*(\d[\d,]*(?:\.\d+)?)\s*(?:cr|crore|cr\b)", combined_text, re.IGNORECASE)
        if order_match:
            try:
                order_val = float(order_match.group(1).replace(",", ""))
                raw_projections.append(f"Order/Value: ₹{order_val:,.1f} Cr")
            except Exception:
                pass

        margin_match = re.search(
            r"(?:ebitda|operating\s+margin|margin)\s*(?:expected\s*at|at|of|is)?\s*(\d[\d,]*(?:\.\d+)?)\s*%",
            combined_text,
            re.IGNORECASE,
        ) or re.search(
            r"(\d[\d,]*(?:\.\d+)?)\s*%\s*(?:ebitda|margin|operating\s+margin)",
            combined_text,
            re.IGNORECASE,
        )
        if margin_match:
            try:
                margin_pct = float(margin_match.group(1).replace(",", ""))
                raw_projections.append(f"Margin Target: {margin_pct:.1f}%")
            except Exception:
                pass

        growth_match = re.search(r"(?:grows?|surges?|up|jumps?|surge\s+by)\s*(?:by\s*)?(\d[\d,]*(?:\.\d+)?)\s*%", combined_text, re.IGNORECASE)
        if growth_match:
            try:
                growth_pct = float(growth_match.group(1).replace(",", ""))
                raw_projections.append(f"Growth Projection: +{growth_pct:.1f}%")
            except Exception:
                pass

        # Temporal Originality Rule Assessment
        repub_patterns = [
            r"\breiterates\b", r"\brepeats\b", r"\bflashback\b", r"\bearlier reported\b",
            r"\bas reported earlier\b", r"\bin 2024\b", r"\bin 2023\b", r"\bmonths ago\b",
            r"\bhistorical recap\b", r"\bthrowback\b"
        ]
        is_repub = any(re.search(p, combined_text, re.IGNORECASE) for p in repub_patterns)
        if is_repub:
            temporal_orig = "REPUBLICATION"
            orig_rationale = "Text explicitly references historical disclosures or previously reported events."
        elif impact_score >= 80:
            temporal_orig = "BREAKING"
            orig_rationale = "High-urgency primary disclosure with immediate price discovery impact."
        else:
            temporal_orig = "NEW_PUBLICATION"
            orig_rationale = "Fresh primary market announcement breaking new corporate developments."

        financial_projections = {
            "target_price": target_price,
            "stop_loss": stop_loss,
            "order_value_cr": order_val,
            "revenue_projection_cr": rev_proj,
            "ebitda_margin_pct": margin_pct,
            "growth_rate_pct": growth_pct,
            "raw_projections": raw_projections,
        }

        return {
            "ticker": ticker,
            "sentiment": sentiment,
            "direction": direction,
            "impact_score": impact_score,
            "impact_level": impact_level,
            "expected_horizon": horizon,
            "volatility_est": volatility,
            "trading_takeaway": why_it_matters or f"Calculated {direction} catalyst trigger ({volatility}) over {horizon}.",
            "target_price": target_price,
            "stop_loss": stop_loss,
            "financial_projections": financial_projections,
            "temporal_originality": temporal_orig,
            "is_republication": is_repub,
            "originality_rationale": orig_rationale,
            "confidence_pct": min(95, max(60, impact_score + 10)),
            "key_catalyst_triggers": [scored.get("category", "General Corporate News")],
            "primary_risk": "Broader market volatility or immediate profit booking at open.",
            "ai_model": "omniroute/heuristic-engine-v1",
            "ai_analyzed_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            "latency_ms": 0.4,
            "tokens_used": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "gateway": "diegosouzapw/OmniRoute (Heuristic Fallback)",
            "raw_response": json.dumps({
                "ticker": ticker,
                "sentiment": sentiment,
                "direction": direction,
                "impact_score": impact_score,
                "impact_level": impact_level,
                "target_price": target_price,
                "stop_loss": stop_loss,
                "financial_projections": financial_projections,
                "temporal_originality": temporal_orig,
                "is_republication": is_repub,
                "originality_rationale": orig_rationale,
                "gateway": "diegosouzapw/OmniRoute"
            }, indent=2),
        }
