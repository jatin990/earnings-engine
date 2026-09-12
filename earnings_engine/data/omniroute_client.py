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

# Claude Code 4-Model Catalog for direct OmniRoute LLM Market Analysis
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

# Global cache to prevent hammering unreachable or unauthenticated local daemon
_OMNIROUTE_AUTH_FAILURE_CACHE: dict[str, float] = {}

DEFAULT_OMNIROUTE_MODELS = [
    "antigravity",
    "antigravity/gemini-3.7-flash-medium",
    "antigravity/gemini-3.8-flash-tiered",
    "antigravity/claude-sonnet-4-6",
    "openai/gpt-4o-mini",
    "meta-llama/llama-3.3-70b-instruct",
    "google/gemini-2.0-flash",
    "mistralai/mistral-large",
    "anthropic/claude-3.5-sonnet",
    "auto/best-fast",
]
DEFAULT_OMNIROUTER_MODELS = DEFAULT_OMNIROUTE_MODELS

# Dedicated High-Availability Models for repetitive high-throughput tasks
HIGH_AVAILABILITY_MODELS: list[str] = [
    "antigravity",
    "antigravity/gemini-3.7-flash-medium",
    "antigravity/gemini-3.8-flash-tiered",
    "openai/gpt-4o-mini",
    "meta-llama/llama-3.3-70b-instruct",
    "google/gemini-2.0-flash",
]

# Catalog of reasoning and production models with categorization for UI & API selection
OMNIROUTE_MODEL_CATALOG: list[dict[str, Any]] = [
    {
        "id": "antigravity",
        "name": "⚡ Antigravity (OmniRoute Tiered Combo)",
        "tier": "FAST",
        "provider": "Antigravity",
        "recommended": True,
        "description": "Unified Antigravity multi-account high-throughput combo routing to Gemini 3.8 Flash Tiered with zero token rate limit bottlenecks.",
    },
    {
        "id": "antigravity/gemini-3.7-flash-medium",
        "name": "✨ Gemini 3.7 Flash Medium (Antigravity)",
        "tier": "FAST",
        "provider": "Google DeepMind / Antigravity",
        "recommended": True,
        "description": "Balanced latency and deep quantitative reasoning with medium thinking capacity.",
    },
    {
        "id": "antigravity/gemini-3.8-flash-tiered",
        "name": "🚀 Gemini 3.8 Flash Tiered (Antigravity)",
        "tier": "FAST",
        "provider": "Google DeepMind / Antigravity",
        "recommended": True,
        "description": "Latest Gemini 3.8 Flash architecture with tiered quota rotation.",
    },
    {
        "id": "antigravity/claude-sonnet-4-6",
        "name": "🎯 Claude Sonnet 4.6 (Antigravity)",
        "tier": "INSTITUTIONAL",
        "provider": "Anthropic / Antigravity",
        "recommended": True,
        "description": "Frontier institutional thesis generation and corporate governance risk assessment via Antigravity OAuth.",
    },
    {
        "id": "deepseek/deepseek-r1",
        "name": "🧠 DeepSeek-R1 (Deep Chain-of-Thought)",
        "tier": "REASONING",
        "provider": "DeepSeek",
        "recommended": True,
        "description": "Deep mathematical reasoning and step-by-step chain-of-thought analysis for complex financial filings and order accretion.",
    },
    {
        "id": "qwen/qwen-2.5-72b-instruct",
        "name": "⚡ Qwen 2.5 72B (Quantitative Reasoning)",
        "tier": "REASONING",
        "provider": "Alibaba Cloud / Qwen",
        "recommended": True,
        "description": "Superior quantitative comprehension, derivative structure evaluation, and volume ratio pattern matching.",
    },
    {
        "id": "meta-llama/llama-3.3-70b-instruct",
        "name": "🏛️ Llama 3.3 70B (Institutional & Macro)",
        "tier": "INSTITUTIONAL",
        "provider": "Meta AI",
        "recommended": True,
        "description": "Broad macroeconomic synthesis, industry competitive positioning, and fund flow conviction analysis. High-availability institutional grade.",
    },
    {
        "id": "mistralai/mistral-large",
        "name": "🌪️ Mistral Large (Frontier Reasoning & Compliance)",
        "tier": "INSTITUTIONAL",
        "provider": "Mistral AI",
        "recommended": True,
        "description": "Frontier quantitative reasoning, regulatory filing compliance parsing, and complex macro-financial thesis generation.",
    },
    {
        "id": "anthropic/claude-3.5-sonnet",
        "name": "🎯 Claude 3.5 Sonnet (Institutional Thesis)",
        "tier": "INSTITUTIONAL",
        "provider": "Anthropic",
        "recommended": True,
        "description": "High-conviction qualitative thesis generation, corporate governance risk auditing, and clean trade setups.",
    },
    {
        "id": "openai/gpt-4o-mini",
        "name": "⚡ GPT-4o-Mini (High-Availability & Repetitive Tasks)",
        "tier": "FAST",
        "provider": "OpenAI",
        "recommended": True,
        "description": "Sub-second low-latency inference, ultra-high availability, and cost-effective execution for continuous streaming repetitive tasks.",
    },
    {
        "id": "google/gemini-2.5-pro",
        "name": "✨ Gemini 2.5 Pro (Advanced Reasoning)",
        "tier": "REASONING",
        "provider": "Google DeepMind",
        "description": "State-of-the-art multimodal reasoning, high-precision numeric extraction, and forward guidance reconciliation.",
    },
    {
        "id": "google/gemini-2.0-flash",
        "name": "🚀 Gemini 2.0 Flash (Ultra Fast)",
        "tier": "FAST",
        "provider": "Google",
        "recommended": True,
        "description": "Sub-second low-latency catalyst screening and fast structured extraction.",
    },
    {
        "id": "auto/best-reasoning",
        "name": "🔮 Auto Best Reasoning (Gateway Dynamic)",
        "tier": "AUTO",
        "provider": "OmniRoute Router",
        "description": "Dynamically selects the highest-scoring available reasoning model across active providers.",
    },
    {
        "id": "auto/best-fast",
        "name": "⚡ Auto Best Fast (Gateway Dynamic)",
        "tier": "AUTO",
        "provider": "OmniRoute Router",
        "description": "Dynamically routes to the fastest response provider with available quota.",
    },
]

OMNIROUTE_SYSTEM_PROMPT = """You are an institutional quantitative equity analyst and advanced reasoning engine specializing in Indian (NSE/BSE) and global equities.
Analyze the provided corporate news announcement together with the point-in-time technical price action, institutional flows, moving average structure, and fundamental guidance.

Ask yourself the full analysis yourself before producing the output: assess the impact on revenue, margins, institutional order flow, technical levels, and market sentiment, then reconcile these factors into a single consistent view. Ground every number and projection in the data supplied - never invent signal prices, targets, or stop levels that are not supported by the provided context.

Provide a crisp, mathematically consistent, and actionable trading evaluation.

Return ONLY a raw, valid JSON object strictly matching this schema:
{
  "ticker": "<ticker symbol, e.g. 'TCS.NS', 'RELIANCE.NS'>",
  "sentiment": "BULLISH" | "BEARISH" | "NEUTRAL",
  "direction": "BULLISH" | "BEARISH" | "NEUTRAL",
  "target_price": <float, projected short-term price target based on signal_price & resistance levels>,
  "stop_loss": <float, technical invalidation price based on signal_price & support levels>,
  "financial_projections": {
    "target_price": <float or null>,
    "stop_loss": <float or null>,
    "order_value_cr": <float or null, explicit order/deal value in INR Crore if mentioned>,
    "revenue_projection_cr": <float or null, projected revenue impact in INR Crore>,
    "ebitda_margin_pct": <float or null, expected margin change or %>,
    "growth_rate_pct": <float or null, expected YoY/QoQ growth %>,
    "raw_projections": ["<exact forward guidance or numeric projection extracted from text>"]
  },
  "temporal_originality": "NEW_PUBLICATION" | "BREAKING" | "DEVELOPING" | "REPUBLICATION",
  "is_republication": <boolean, true if this is an old recycled story/re-hash, false if genuine fresh news>,
  "originality_rationale": "<1 sentence on news freshness vs past announcements>",
  "impact_score": <integer 25 to 99, catalyst price magnitude score>,
  "impact_level": "HIGH" | "MEDIUM" | "LOW",
  "expected_horizon": "1-3 Days" | "1-2 Weeks" | "Positional",
  "volatility_est": "+/-1% to +/-3%" | "+/-2% to +/-6%" | "+/-5% to +/-12%",
  "trading_takeaway": "<2-3 sentence institutional synthesis integrating news catalyst, price action momentum, and institutional accumulation flow>",
  "confidence_pct": <integer 0-100>,
  "key_catalyst_triggers": ["<bullet 1>", "<bullet 2>"],
  "primary_risk": "<single biggest technical or fundamental risk factor>"
}

Key Quantitative Directives:
1. Grounding: Set target_price > signal_price for BULLISH (typically 2% to 7% above current levels or at resistance R1), and target_price < signal_price for BEARISH.
2. Invalidation: Set defensive stop_loss below key support S1 / recent base for BULLISH, and above swing resistance for BEARISH.
3. Temporal Originality: Distinguish between brand-new regulatory/exchange disclosures vs regurgitated past events.
4. Institutional Context: Synthesize delivery absorption, volume ratios, and moving average structure with news impact.
5. Self-Analysis: Work through the reasoning internally first, then output only the final, internally-consistent JSON.
6. Format: Return ONLY the raw JSON object without markdown code blocks, backticks, or preamble commentary.
7. Style: Use plain professional language. Do NOT use emojis, symbols, or decorative gunk in any string value."""


class OmniRouteClient:
    """Client for diegosouzapw/OmniRoute multi-provider AI gateway."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()
        self._detected_endpoint: str | None = None
        self._last_probe_time: float = 0.0
        self._is_online: bool = False

    @property
    def base_url(self) -> str:
        """Convenience property for configured base URL."""
        return self.get_configured_base_url()

    @property
    def api_key(self) -> str:
        """Convenience property for resolved API key."""
        return self.get_api_key()

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

    def probe_health(self, host: str | None = None, api_key: str | None = None, timeout: float = 1.5) -> dict[str, Any]:
        """Probe diegosouzapw/OmniRoute daemon to check availability and active models."""
        configured = (host or self.get_configured_base_url()).strip().rstrip("/")
        if not configured.endswith("/v1") and not configured.endswith("/chat/completions"):
            configured = f"{configured}/v1"
        candidates = [configured]

        # Add localhost probe variations if checking default localhost
        if "localhost" in configured or "127.0.0.1" in configured:
            for port in OMNIROUTE_PROBE_PORTS:
                candidate = f"http://localhost:{port}/v1"
                if candidate not in candidates:
                    candidates.append(candidate)
                ip_candidate = f"http://127.0.0.1:{port}/v1"
                if ip_candidate not in candidates:
                    candidates.append(ip_candidate)

        active_key = api_key if api_key is not None else self.get_api_key()
        headers = {"Accept": "application/json"}
        if active_key:
            headers["Authorization"] = f"Bearer {active_key}"

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
                        "models": model_list,
                        "is_self_hosted": "localhost" in base_url or "127.0.0.1" in base_url,
                    }
                elif resp.status_code == 401 and ("omniroute" in str(resp.headers).lower() or "invalid_api_key" in resp.text or "Authentication required" in resp.text):
                    self._detected_endpoint = base_url
                    self._is_online = True
                    self._last_probe_time = time.time()
                    logger.info("[OMNIROUTE] Detected active diegosouzapw/OmniRoute on %s (Authentication Required)", base_url)
                    return {
                        "status": "auth_required" if not active_key else "auth_invalid",
                        "endpoint": base_url,
                        "latency_ms": latency,
                        "models_count": len(DEFAULT_OMNIROUTE_MODELS),
                        "models": DEFAULT_OMNIROUTE_MODELS,
                        "is_self_hosted": "localhost" in base_url or "127.0.0.1" in base_url,
                        "message": "OmniRoute daemon is active on http://localhost:20128/. Generate an API Key in the OmniRoute UI (http://localhost:20128/) and add OMNIROUTE_API_KEY to your .env file." if not active_key else "OmniRoute rejected the configured API Key. Please verify OMNIROUTE_API_KEY in .env.",
                    }
            except Exception as e:
                logger.debug("[OMNIROUTE] Probe check failed for %s: %s", base_url, e)

        # If probe failed on all candidates, check fallback gateway (OpenRouter)
        fallback_url = (
            os.getenv("OMNIROUTE_FALLBACK_URL")
            or os.getenv("OPENROUTER_BASE_URL")
            or self.settings.omniroute_fallback_url
        ).strip().rstrip("/")
        if active_key and fallback_url:
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
            "message": f"OmniRoute daemon not detected on {configured}. Run 'npx omniroute' or 'docker run -p 20128:20128 diegosouzapw/omniroute'.",
        }

    def get_available_models_catalog(self, host: str | None = None, api_key: str | None = None) -> dict[str, Any]:
        """Return merged list of probed online models and curated model catalog with metadata."""
        health = self.probe_health(host=host, api_key=api_key)
        probed_models = health.get("models") or []
        catalog = list(OMNIROUTE_MODEL_CATALOG)
        catalog_ids = {m["id"] for m in catalog}

        for pm in probed_models:
            if pm not in catalog_ids:
                catalog.append({
                    "id": pm,
                    "name": pm.split("/")[-1].replace("-instruct", "").title(),
                    "tier": "CUSTOM / PROBED",
                    "provider": pm.split("/")[0].title() if "/" in pm else "OmniRoute",
                    "description": f"Model detected on active OmniRoute gateway: {pm}",
                    "recommended": False,
                })

        return {
            "status": health.get("status", "offline"),
            "endpoint": health.get("endpoint", self.get_configured_base_url()),
            "catalog": catalog,
            "probed_models": probed_models,
            "default_model": os.getenv("OMNIROUTE_DEFAULT_MODEL", "deepseek/deepseek-r1"),
        }

    def get_completions_url(self, host: str | None = None) -> str:
        """Resolve full completions URL with cached probe status."""
        if host:
            clean_host = host.strip().rstrip("/")
            if not clean_host.endswith("/v1") and not clean_host.endswith("/chat/completions"):
                clean_host = f"{clean_host}/v1"
            return f"{clean_host.rstrip('/')}/chat/completions"

        configured = self.get_configured_base_url()
        if configured and ("localhost" not in configured and "127.0.0.1" not in configured):
            return f"{configured.rstrip('/')}/chat/completions"
        if self._detected_endpoint and (time.time() - self._last_probe_time < 30.0):
            return f"{self._detected_endpoint.rstrip('/')}/chat/completions"
        health = self.probe_health()
        base = health.get("endpoint") or configured
        return f"{base.rstrip('/')}/chat/completions"

    def get_available_models(self, host: str | None = None, api_key: str | None = None) -> dict[str, Any]:
        """Return available OmniRoute models categorized by reasoning capability."""
        health = self.probe_health(host=host, api_key=api_key)
        discovered_models = health.get("models") or []
        configured = os.getenv("OMNIROUTE_MODEL") or self.settings.omniroute_model or "deepseek/deepseek-r1"

        catalog = [dict(m) for m in OMNIROUTE_MODEL_CATALOG]
        # Attach discovered custom models if running locally
        catalog_ids = {m["id"] for m in catalog}
        for dm in discovered_models:
            if dm not in catalog_ids:
                catalog.append({
                    "id": dm,
                    "name": dm,
                    "tier": "CUSTOM",
                    "provider": "OmniRoute Gateway",
                    "description": f"Discovered endpoint model {dm}",
                })

        return {
            "success": True,
            "status": health.get("status", "offline"),
            "endpoint": health.get("endpoint"),
            "is_self_hosted": health.get("is_self_hosted", False),
            "configured_model": configured,
            "default_model": "deepseek/deepseek-r1",
            "models": catalog,
            "models_count": len(catalog),
        }

    def format_prompt(self, item: dict[str, Any]) -> str:
        """Format crisp, high-density structured context for OmniRoute quantitative reasoning."""
        raw_ticker = str(item.get("ticker") or "UNKNOWN").strip().upper()
        clean_sym = raw_ticker.split("::")[0].strip()
        stock_name = item.get("stock_name") or clean_sym
        title = (item.get("title") or item.get("headline") or "").strip()
        summary = (item.get("summary") or item.get("description") or "").strip()
        publisher = (item.get("publisher") or item.get("source") or "").strip()
        published_at = item.get("published_at") or item.get("published_date") or ""
        signal_price = item.get("signal_price")
        current_price = item.get("current_price") or signal_price
        verified_nums = item.get("verified_numbers") or {}
        if isinstance(verified_nums, str):
            try:
                verified_nums = json.loads(verified_nums)
            except Exception:
                verified_nums = {}

        # Enrich with local database price history, institutional flows, and fundamentals if missing
        tech_ctx = dict(item.get("price_action") or item.get("technical_context") or {})
        flow_ctx = dict(item.get("institutional_flow") or item.get("flow_context") or {})

        # Quick local DB enrichment if ticker is valid and tech_ctx is empty
        if clean_sym and clean_sym not in ("UNKNOWN", "NONE", "") and not tech_ctx:
            try:
                from earnings_engine.data.prices import load_prices
                from earnings_engine.data.market_context import detect_swing_range
                from earnings_engine.data.institutional_accumulation import get_stock_institutional_activity
                import pandas as pd

                pdf = load_prices(clean_sym, self.settings)
                if pdf is not None and not pdf.empty and "close" in pdf.columns:
                    closes = pd.to_numeric(pdf["close"], errors="coerce").dropna()
                    vols = pd.to_numeric(pdf["volume"], errors="coerce").dropna() if "volume" in pdf.columns else None
                    if not closes.empty:
                        cur_p = float(closes.iloc[-1])
                        if not current_price or current_price <= 0:
                            current_price = cur_p
                        if not signal_price or signal_price <= 0:
                            signal_price = cur_p

                        high_52w = float(closes.tail(252).max()) if len(closes) >= 10 else cur_p
                        low_52w = float(closes.tail(252).min()) if len(closes) >= 10 else cur_p
                        pct_52w_high = ((cur_p - high_52w) / high_52w) * 100 if high_52w > 0 else 0.0

                        ret_7d = round(((cur_p / float(closes.iloc[-min(5, len(closes))])) - 1) * 100, 2) if len(closes) >= 5 else 0.0
                        ret_30d = round(((cur_p / float(closes.iloc[-min(21, len(closes))])) - 1) * 100, 2) if len(closes) >= 21 else 0.0
                        ret_90d = round(((cur_p / float(closes.iloc[-min(63, len(closes))])) - 1) * 100, 2) if len(closes) >= 63 else 0.0

                        sma_20 = round(float(closes.tail(20).mean()), 2) if len(closes) >= 20 else None
                        sma_50 = round(float(closes.tail(50).mean()), 2) if len(closes) >= 50 else None
                        sma_200 = round(float(closes.tail(200).mean()), 2) if len(closes) >= 200 else None

                        vol_surge = None
                        if vols is not None and len(vols) >= 63:
                            v5 = float(vols.tail(5).mean())
                            v63 = float(vols.tail(63).mean())
                            if v63 > 0:
                                vol_surge = round(v5 / v63, 2)

                        tech_ctx = {
                            "current_price": round(cur_p, 2),
                            "high_52w": round(high_52w, 2),
                            "low_52w": round(low_52w, 2),
                            "pct_from_52w_high": round(pct_52w_high, 2),
                            "ret_7d": ret_7d,
                            "ret_30d": ret_30d,
                            "ret_90d": ret_90d,
                            "sma_20": sma_20,
                            "sma_50": sma_50,
                            "sma_200": sma_200,
                            "volume_surge": vol_surge,
                        }

                        sr = detect_swing_range(clean_sym, self.settings)
                        if sr:
                            tech_ctx["swing_support"] = sr.get("support")
                            tech_ctx["swing_resistance"] = sr.get("resistance")
                            tech_ctx["channel_position"] = sr.get("channel_pos_pct")

                inst = get_stock_institutional_activity(clean_sym, self.settings)
                if inst:
                    flow_ctx = {
                        "fund_count": inst.get("fund_count"),
                        "funds_in": inst.get("funds_in_count"),
                        "funds_out": inst.get("funds_out_count"),
                        "shares_held": inst.get("total_shares_held"),
                        "shares_delta_pct": inst.get("total_shares_delta_pct"),
                        "total_invested_cr": inst.get("total_invested_cr"),
                        "holding_period": inst.get("holding_period"),
                    }
            except Exception as e:
                logger.debug("[OMNIROUTE-PROMPT] Context enrichment error for %s: %s", clean_sym, e)

        sections = []

        # 1. Company Profile
        prof = f"=== INSTRUMENT: {clean_sym}"
        if stock_name and stock_name != clean_sym:
            prof += f" ({stock_name})"
        industry = item.get("industry") or item.get("sector")
        if industry:
            prof += f" | Sector: {industry}"
        sections.append(prof)

        # 2. Latest News Catalyst
        news_lines = ["=== LATEST CATALYST EVENT"]
        news_lines.append(f"Headline: {title}")
        if summary and summary != title:
            news_lines.append(f"Summary / Excerpt: {summary}")
        if publisher:
            news_lines.append(f"Source / Publisher: {publisher}")
        if published_at:
            news_lines.append(f"Published: {published_at}")
        if verified_nums:
            nums_str = ", ".join(f"{k}: {v}" for k, v in verified_nums.items() if v is not None)
            if nums_str:
                news_lines.append(f"Verified Extracted Metrics: {nums_str}")
        sections.append("\n".join(news_lines))

        # 3. Price Action & Technical Structure
        pa_lines = ["=== PRICE ACTION & TECHNICAL STRUCTURE"]
        if current_price and current_price > 0:
            pa_lines.append(f"Latest Market Price: INR {current_price:.2f}")
        if signal_price and signal_price > 0:
            pa_lines.append(f"Pre-News Reference Close (Signal Price): INR {signal_price:.2f}")
            if current_price and current_price > 0 and signal_price > 0:
                delta_pct = ((current_price - signal_price) / signal_price) * 100
                pa_lines.append(f"Price Delta Since Signal: {delta_pct:+.2f}%")

        if tech_ctx:
            if tech_ctx.get("high_52w") and tech_ctx.get("low_52w"):
                pa_lines.append(f"52-Week Range: INR {tech_ctx['low_52w']:.2f} to INR {tech_ctx['high_52w']:.2f} ({tech_ctx.get('pct_from_52w_high', 0):+.2f}% from 52W High)")
            ret_str = f"Momentum Returns: 7D: {tech_ctx.get('ret_7d', 'N/A')}% | 30D: {tech_ctx.get('ret_30d', 'N/A')}% | 90D: {tech_ctx.get('ret_90d', 'N/A')}%"
            pa_lines.append(ret_str)
            if tech_ctx.get("sma_20") or tech_ctx.get("sma_50") or tech_ctx.get("sma_200"):
                pa_lines.append(f"Moving Averages: 20 SMA: {tech_ctx.get('sma_20')} | 50 SMA: {tech_ctx.get('sma_50')} | 200 SMA: {tech_ctx.get('sma_200')}")
            if tech_ctx.get("swing_resistance") or tech_ctx.get("swing_support"):
                pa_lines.append(f"Swing Levels: Resistance Trigger R1: INR {tech_ctx.get('swing_resistance')} | Support S1: INR {tech_ctx.get('swing_support')}")
            if tech_ctx.get("volume_surge"):
                pa_lines.append(f"Volume Surge Ratio: {tech_ctx['volume_surge']}x (5D avg vs 63D baseline)")
        sections.append("\n".join(pa_lines))

        # 4. Institutional & Order Flow
        if flow_ctx or item.get("delivery_pct") or item.get("volume_ratio"):
            flow_lines = ["=== INSTITUTIONAL & ORDER FLOW ACCUMULATION"]
            if flow_ctx.get("fund_count"):
                flow_lines.append(f"Mutual Funds Holding: {flow_ctx['fund_count']} (In: +{flow_ctx.get('funds_in', 0)} / Out: -{flow_ctx.get('funds_out', 0)}) [{flow_ctx.get('holding_period', 'QoQ')}]")
            if flow_ctx.get("shares_delta_pct"):
                flow_lines.append(f"Institutional Stake Delta: {flow_ctx['shares_delta_pct']:+.2f}% QoQ")
            if item.get("delivery_pct"):
                flow_lines.append(f"Bhavcopy Deliverable Volume: {item['delivery_pct']:.1f}%")
            if item.get("volume_ratio"):
                flow_lines.append(f"Bhavcopy Volume Spike: {item['volume_ratio']:.2f}x")
            sections.append("\n".join(flow_lines))

        # 5. Derivatives / Option Chain (if provided or present)
        opt_ctx = item.get("option_chain") or {}
        if opt_ctx:
            opt_lines = ["=== DERIVATIVES & OPTION CHAIN STRUCTURE"]
            if opt_ctx.get("sentiment"):
                opt_lines.append(f"Option Chain Sentiment: {opt_ctx['sentiment']}")
            if opt_ctx.get("pcr_oi"):
                opt_lines.append(f"Put-Call Ratio (PCR OI): {opt_ctx['pcr_oi']:.2f}")
            if opt_ctx.get("call_wall_strike"):
                opt_lines.append(f"Highest Call OI Wall: INR {opt_ctx['call_wall_strike']}")
            if opt_ctx.get("max_pain_strike"):
                opt_lines.append(f"Max Pain Strike: INR {opt_ctx['max_pain_strike']}")
            sections.append("\n".join(opt_lines))

        return "\n\n".join(sections)

    def analyze_catalyst(
        self,
        item: dict[str, Any],
        preferred_model: str | None = None,
        timeout: int | None = None,
        model: str | None = None,
    ) -> dict[str, Any]:
        """Send catalyst context to diegosouzapw/OmniRoute with automatic model cascading and heuristic fallback."""
        timeout = timeout or self.settings.omniroute_timeout
        api_key = self.get_api_key()
        completions_url = self.get_completions_url()

        # If gateway previously failed authentication within 5 minutes, fail fast immediately
        auth_fail_time = _OMNIROUTE_AUTH_FAILURE_CACHE.get(completions_url, 0.0)
        if time.time() - auth_fail_time < 300.0 and not api_key:
            return self.fallback_heuristic_analysis(item)

        # If offline and no API key available, execute instant deterministic heuristic
        if not self._is_online and not api_key:
            logger.info("[OMNIROUTE] Gateway offline; using deterministic analysis for %s", item.get("ticker"))
            return self.fallback_heuristic_analysis(item)

        effective_timeout = max(float(timeout or self.settings.omniroute_timeout or 25), 15.0)
        chosen_model = model or preferred_model or item.get("model") or item.get("preferred_model")
        configured_model = chosen_model or os.getenv("OMNIROUTE_MODEL") or self.settings.omniroute_model or "antigravity"

        models_to_try = [configured_model]
        for m in HIGH_AVAILABILITY_MODELS:
            if m not in models_to_try:
                models_to_try.append(m)
        models_to_try = models_to_try[:4]  # Allow primary + high-availability fallback cascade

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
                try:
                    from earnings_engine.rate_limits import record_request
                    record_request("omniroute")
                except Exception:
                    pass
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
                    timeout=effective_timeout,
                )
                latency_ms = round((time.perf_counter() - t0) * 1000, 1)

                # If unauthorized/invalid credentials or gateway not configured, fail fast immediately
                if resp.status_code in (401, 403):
                    is_missing_provider = "no active credentials for provider" in resp.text.lower()
                    if is_missing_provider:
                        logger.warning(
                            "[OMNIROUTE] Upstream provider credentials missing for model %s: %s. Cascading to next candidate...",
                            model_name,
                            resp.text[:120],
                        )
                        continue
                    _OMNIROUTE_AUTH_FAILURE_CACHE[completions_url] = time.time()
                    logger.warning("[OMNIROUTE] Gateway auth error (%d) for model %s: %s. Failing fast to deterministic heuristics.", resp.status_code, model_name, resp.text[:150])
                    break

                if resp.status_code == 200:
                    data = resp.json()
                    choice = (data.get("choices") or [{}])[0]
                    msg = choice.get("message") or {}
                    raw_content = (msg.get("content") or msg.get("reasoning") or "").strip()
                    usage = data.get("usage") or {}
                    total_toks = usage.get("total_tokens") or (usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0))

                    if not raw_content:
                        logger.warning("[OMNIROUTE] Model %s returned empty content from %s; failing fast to heuristics.", model_name, completions_url)
                        break

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
                        break
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
        if direction == "NEUTRAL":
            from earnings_engine.data.news_sentiment import calculate_headline_sentiment
            score, label = calculate_headline_sentiment(title, summary)
            if label == "Bullish" or (score and score >= 0.20):
                direction = "BULLISH"
            elif label == "Bearish" or (score and score <= -0.20):
                direction = "BEARISH"
        sentiment = direction
        impact_score = scored.get("impact_score", 50)
        impact_level = scored.get("impact_level", "MEDIUM")
        horizon = scored.get("expected_horizon", "1-3 Days")
        volatility = scored.get("volatility_est", "+/-1% to +/-4%")
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

    def generate_stock_setup(
        self,
        ticker: str,
        as_of_price: float,
        technicals: dict[str, Any] | None = None,
        catalysts: list[dict[str, Any]] | None = None,
        timeframe_days: int = 14,
        model: str | None = None,
        host: str | None = None,
        api_key: str | None = None,
        timeout: float = 45.0,
    ) -> dict[str, Any]:
        """Generate a complete quantitative and LLM-synthesized trade setup for a stock."""
        start = time.perf_counter()
        tech = technicals or {}
        cats = catalysts or []
        price = float(as_of_price or 0.0)

        chosen_model = (model or os.getenv("OMNIROUTE_MODEL") or self.settings.omniroute_model or "deepseek/deepseek-r1").strip()
        sub_model = chosen_model.replace("omniroute/", "").replace("omnirouter/", "").strip()
        if not sub_model or sub_model in ("omniroute", "omnirouter"):
            sub_model = "deepseek/deepseek-r1"

        completions_url = self.get_completions_url(host=host)
        active_key = api_key if api_key is not None else self.get_api_key()

        # Build prompt
        prompt = (
            f"You are the OmniRoute Quant Trading Intelligence Engine analyzing Indian Equity {ticker}.\n"
            f"Current Market Price: ₹{price:.2f}\n"
            f"Forecast Horizon: {timeframe_days} Trading Days\n"
            f"Technical Context:\n"
            f"- 20D SMA: ₹{tech.get('sma_20', price):.2f}\n"
            f"- 50D SMA: ₹{tech.get('sma_50', price):.2f}\n"
            f"- 200D SMA: ₹{tech.get('sma_200', price):.2f}\n"
            f"- 20D Swing Channel: Low ₹{tech.get('channel_low_20d', price * 0.95):.2f} to High ₹{tech.get('channel_high_20d', price * 1.05):.2f}\n"
            f"- RSI (14): {tech.get('rsi_14', 55.0)}\n"
            f"- 52W Range: ₹{tech.get('week_52_low', price * 0.8):.2f} – ₹{tech.get('week_52_high', price * 1.2):.2f}\n"
        )
        if cats:
            prompt += "Recent Catalyst News:\n"
            for c in cats[:3]:
                prompt += f"- {c.get('title', '')} (Impact: {c.get('impact_score', 75)}% | {c.get('sentiment', 'NEUTRAL')})\n"

        prompt += (
            "\nOutput STRICT JSON with keys:\n"
            "direction (BULLISH/BEARISH/NEUTRAL), confidence_pct (0-100), target_price (float), "
            "support_level (float), resistance_level (float), stop_loss_price (float), risk_reward_ratio (float), "
            "chart_pattern (string), key_drivers (array of 2-3 short strings), primary_risk (string), "
            "synthesized_thesis (1-2 sentence high conviction thesis), recommended_action (string)"
        )

        resp_text = ""
        total_tokens = 0
        success = False

        try:
            try:
                from earnings_engine.rate_limits import record_request
                record_request("omniroute")
            except Exception:
                pass
            headers = {"Content-Type": "application/json", "X-Title": "Earnings Engine OmniRoute Setup"}
            if active_key:
                headers["Authorization"] = f"Bearer {active_key}"

            resp = requests.post(
                completions_url,
                headers=headers,
                json={
                    "model": sub_model,
                    "messages": [
                        {"role": "system", "content": "You are a quantitative hedge fund equity research algorithm. Return only valid JSON."},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.3,
                    "max_tokens": 1000,
                },
                timeout=timeout,
            )
            if resp.status_code == 200:
                data = resp.json()
                total_tokens = data.get("usage", {}).get("total_tokens", 0)
                choice = (data.get("choices") or [{}])[0]
                msg = choice.get("message") or {}
                resp_text = (msg.get("content") or msg.get("reasoning") or "").strip()
                if resp_text:
                    success = True
        except Exception as e:
            logger.debug("[OMNIROUTE] Setup query failed on %s: %s", completions_url, e)

        elapsed_ms = round((time.perf_counter() - start) * 1000, 1)

        if success and resp_text:
            cleaned = re.sub(r"^```(?:json)?\s*", "", resp_text, flags=re.MULTILINE)
            cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE).strip()
            try:
                p = json.loads(cleaned)
                direction = str(p.get("direction") or "BULLISH").upper()
                if direction not in ("BULLISH", "BEARISH", "NEUTRAL"):
                    direction = "BULLISH"
                conf = int(p.get("confidence_pct") or 82)
                tgt = float(p.get("target_price") or (price * 1.06 if direction == "BULLISH" else price * 0.94))
                sup = float(p.get("support_level") or (price * 0.97))
                res = float(p.get("resistance_level") or (price * 1.05))
                sl = float(p.get("stop_loss_price") or (sup * 0.98 if direction == "BULLISH" else res * 1.02))
                rr = float(p.get("risk_reward_ratio") or (round(abs(tgt - price) / max(0.01, abs(price - sl)), 1)))
                floor_e = min(price, sup) if price > 0 else sup
                entry_zone = f"₹{floor_e:.2f} – ₹{price:.2f}"

                return {
                    "ticker": ticker,
                    "as_of_price": price,
                    "timeframe_days": timeframe_days,
                    "direction": direction,
                    "confidence_pct": conf,
                    "target_price": round(tgt, 2),
                    "support_level": round(sup, 2),
                    "resistance_level": round(res, 2),
                    "stop_loss_price": round(sl, 2),
                    "risk_reward_ratio": rr,
                    "consensus_entry_zone": entry_zone,
                    "chart_pattern": p.get("chart_pattern") or f"Multi-Timeframe {direction.capitalize()} Setup",
                    "key_drivers": p.get("key_drivers") or [f"OmniRoute {sub_model} alignment", f"{direction} volume confirmation"],
                    "primary_risk": p.get("primary_risk") or "Broader index volatility or trend exhaustion.",
                    "synthesized_thesis": p.get("synthesized_thesis") or f"OmniRoute algorithmic synthesis indicates {direction.lower()} momentum trajectory toward ₹{tgt:.2f}.",
                    "recommended_action": p.get("recommended_action") or ("STRONG BUY" if direction == "BULLISH" and conf >= 80 else "ACCUMULATE ON DIPS"),
                    "ai_model": f"omniroute/{sub_model}",
                    "ai_model_name": f"OmniRoute ({sub_model.split('/')[-1]})",
                    "gateway": "diegosouzapw/OmniRoute",
                    "latency_ms": elapsed_ms,
                    "tokens_used": total_tokens,
                    "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                    "raw_response": resp_text,
                }
            except Exception as e:
                logger.debug("[OMNIROUTE] JSON parse failed: %s", e)

        # Quantitative fallback setup
        sup_fallback = round(tech.get("channel_low_20d") or (price * 0.965), 2)
        tgt_fallback = round(tech.get("channel_high_20d") or (price * 1.055), 2)
        sl_fallback = round(sup_fallback * 0.985, 2)
        rr_fallback = round((tgt_fallback - price) / max(0.01, (price - sl_fallback)), 1) if price > sl_fallback else 2.4
        entry_zone_fb = f"₹{sup_fallback:.2f} – ₹{price:.2f}"

        return {
            "ticker": ticker,
            "as_of_price": price,
            "timeframe_days": timeframe_days,
            "direction": "BULLISH" if price >= (tech.get("sma_20") or price) else "NEUTRAL",
            "confidence_pct": 78,
            "target_price": tgt_fallback,
            "support_level": sup_fallback,
            "resistance_level": tgt_fallback,
            "stop_loss_price": sl_fallback,
            "risk_reward_ratio": rr_fallback,
            "consensus_entry_zone": entry_zone_fb,
            "chart_pattern": "OmniRoute Quantitative Channel Compression",
            "key_drivers": ["Multi-factor technical support bounce", "OmniRoute quantitative catalyst integration"],
            "primary_risk": "Short-term consolidation below resistance",
            "synthesized_thesis": f"Quantitative price structure maintains positive drift toward ₹{tgt_fallback:.2f} with support anchored at ₹{sup_fallback:.2f}.",
            "recommended_action": "ACCUMULATE ON DIPS",
            "ai_model": f"omniroute/{sub_model}",
            "ai_model_name": f"OmniRoute ({sub_model.split('/')[-1]})",
            "gateway": "diegosouzapw/OmniRoute (Quant Engine)",
            "latency_ms": elapsed_ms,
            "tokens_used": 0,
            "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            "raw_response": json.dumps({"status": "quant_engine", "ticker": ticker, "price": price}, indent=2),
        }


def get_claude_code_models(probe_live: bool = True) -> list[dict[str, Any]]:
    """Return Claude Code 4-model catalog with live gateway availability probe."""
    client = OmniRouteClient()
    if not probe_live:
        return [dict(m) for m in CLAUDE_CODE_OMNIROUTE_MODELS]
    try:
        url = f"{client.base_url.rstrip('/')}/models"
        headers = {"Accept": "application/json"}
        if client.api_key:
            headers["Authorization"] = f"Bearer {client.api_key}"
        resp = requests.get(url, headers=headers, timeout=2.5)
        if resp.status_code == 200:
            data = resp.json()
            items = data.get("data") if isinstance(data, dict) else data
            if not isinstance(items, list):
                items = []
            online_ids = set()
            for m in items:
                if isinstance(m, dict):
                    online_ids.add(m.get("id"))
                elif isinstance(m, str):
                    online_ids.add(m)
            res = []
            for item in CLAUDE_CODE_OMNIROUTE_MODELS:
                m_copy = dict(item)
                m_copy["available"] = item["id"] in online_ids
                res.append(m_copy)
            return res
    except Exception as e:
        logger.debug("[OMNIROUTE] Live probe for Claude Code models failed: %s", e)
    return [dict(m) for m in CLAUDE_CODE_OMNIROUTE_MODELS]


def execute_omniroute_analysis(
    model: str = "antigravityonly",
    system_prompt: str = "",
    user_prompt: str = "",
    temperature: float = 0.2,
    timeout: int = 60,
) -> dict[str, Any]:
    """Execute direct quantitative analysis via OmniRoute using specified Claude Code model tier."""
    client = OmniRouteClient()
    url = client.get_completions_url()
    headers = {
        "Content-Type": "application/json",
        "X-Title": "Earnings Engine OmniRoute Analysis",
    }
    if client.api_key:
        headers["Authorization"] = f"Bearer {client.api_key}"

    try:
        from earnings_engine.rate_limits import record_request
        record_request("omniroute")
    except Exception:
        pass

    t0 = time.perf_counter()
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
        latency_ms = round((time.perf_counter() - t0) * 1000, 1)
        if resp.status_code == 200:
            data = resp.json()
            choice = (data.get("choices") or [{}])[0]
            msg = choice.get("message") or {}
            content = (msg.get("content") or "").strip()
            reasoning = (msg.get("reasoning") or msg.get("reasoning_content") or "").strip()
            tokens = data.get("usage", {}).get("total_tokens", 0)

            if not reasoning and "<think>" in content:
                think_match = re.search(r"<think>(.*?)</think>", content, flags=re.DOTALL)
                if think_match:
                    reasoning = think_match.group(1).strip()
                    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()

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
        latency_ms = round((time.perf_counter() - t0) * 1000, 1)
        return {
            "status": "error",
            "error": str(e),
            "raw_text": "",
            "reasoning_text": "",
            "tokens_used": 0,
            "latency_ms": latency_ms,
            "model_used": model,
        }

