"""Downstream API Rate Limit & Quota Tracking Engine.

Tracks API consumption, rate limit criteria, free-tier quotas, and response headers
across all downstreams (OpenRouter, Yahoo Finance, NSE, Gemini, etc.) across multiple timeframes.
"""
from __future__ import annotations

import collections
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any

import requests

from earnings_engine.config import Settings
from earnings_engine.logging_utils import get_logger

logger = get_logger("earnings_engine.rate_limits")

# Downstream default criteria definition (Free tier and standard limits)
DOWNSTREAM_CRITERIA: dict[str, dict[str, Any]] = {
    "openrouter": {
        "service_name": "OpenRouter AI (Consensus & LLMs)",
        "icon": "🤖",
        "description": "Multi-model reasoning via DeepSeek-R1, Llama-3.3-70B, Qwen-2.5-72B, and Mistral-Large.",
        "free_tier_limits": {
            "1m": 20,      # 20 requests per minute
            "1h": 100,     # 100 requests per hour
            "24h": 200,    # 200 requests per day (Free tier cap)
        },
        "default_limits": {
            "1m": 60,
            "1h": 500,
            "24h": 2000,
        },
        "unit": "requests",
        "docs_url": "https://openrouter.ai/docs/limits",
    },
    "yfinance": {
        "service_name": "Yahoo Finance (Market & Price Data)",
        "icon": "📈",
        "description": "Historical OHLCV prices, fast_info market caps, dividends, splits, and quarterly earnings data.",
        "free_tier_limits": {
            "1m": 30,      # 30 requests per minute
            "1h": 500,     # 500 requests per hour
            "24h": 2000,   # 2000 requests per day
        },
        "default_limits": {
            "1m": 60,
            "1h": 1000,
            "24h": 5000,
        },
        "unit": "requests",
        "docs_url": "https://pypi.org/project/yfinance/",
    },
    "nse": {
        "service_name": "NSE India (Direct Archives & nselib)",
        "icon": "🏛️",
        "description": "National Stock Exchange official corporate calendar, event feeds, shareholding patterns, and index data.",
        "free_tier_limits": {
            "1m": 15,      # 15 RPM
            "1h": 150,     # 150 RPH
            "24h": 600,    # 600 RPD
        },
        "default_limits": {
            "1m": 30,
            "1h": 300,
            "24h": 1200,
        },
        "unit": "requests",
        "docs_url": "https://www.nseindia.com",
    },
    "jugaad_data": {
        "service_name": "Jugaad Data (NSE Bhavcopy & F&O)",
        "icon": "📦",
        "description": "Historical Indian equity Bhavcopy, F&O derivatives archives, and stock index series.",
        "free_tier_limits": {
            "1m": 20,      # 20 requests per minute (Rate throttled to prevent NSE CDN cooldowns)
            "1h": 200,     # 200 requests per hour
            "24h": 800,    # 800 requests per day
        },
        "default_limits": {
            "1m": 40,
            "1h": 400,
            "24h": 1500,
        },
        "unit": "requests",
        "docs_url": "https://jugaad-data.readthedocs.io/",
    },
    "bse": {
        "service_name": "BSE India (Corporate Actions & Filings)",
        "icon": "🏢",
        "description": "Bombay Stock Exchange corporate announcements, financial results, and insider trade disclosures.",
        "free_tier_limits": {
            "1m": 15,
            "1h": 150,
            "24h": 600,
        },
        "default_limits": {
            "1m": 30,
            "1h": 300,
            "24h": 1200,
        },
        "unit": "requests",
        "docs_url": "https://www.bseindia.com",
    },
    "gemini": {
        "service_name": "Google Gemini (Multimodal & News)",
        "icon": "✨",
        "description": "Multimodal financial news parsing, volume catalysts, and sentiment impact scoring.",
        "free_tier_limits": {
            "1m": 15,      # 15 RPM
            "1h": 300,     # 300 RPH
            "24h": 1500,   # 1500 RPD
        },
        "default_limits": {
            "1m": 60,
            "1h": 1000,
            "24h": 10000,
        },
        "unit": "requests",
        "docs_url": "https://ai.google.dev/pricing",
    },
}


# Available AI Models in Consensus Suite
AVAILABLE_AI_MODELS: list[dict[str, Any]] = [
    {
        "id": "deepseek/deepseek-r1",
        "name": "DeepSeek-R1",
        "icon": "🤖",
        "badge": "Reasoning",
        "description": "DeepSeek-R1 chain-of-thought quantitative and market structure reasoning.",
        "color": "#6366f1",
        "default_limit_1m": 20,
        "default_limit_1h": 100,
        "default_limit_24h": 200,
    },
    {
        "id": "meta-llama/llama-3.3-70b-instruct",
        "name": "Llama-3.3-70B",
        "icon": "🦙",
        "badge": "Institutional",
        "description": "Meta 70B flagship instruction model for macro trends and swing setups.",
        "color": "#38bdf8",
        "default_limit_1m": 20,
        "default_limit_1h": 100,
        "default_limit_24h": 200,
    },
    {
        "id": "qwen/qwen-2.5-72b-instruct",
        "name": "Qwen-2.5-72B",
        "icon": "🌐",
        "badge": "Algorithmic",
        "description": "Alibaba 72B model specialized in numerical price structures and key levels.",
        "color": "#a855f7",
        "default_limit_1m": 20,
        "default_limit_1h": 100,
        "default_limit_24h": 200,
    },
    {
        "id": "mistralai/mistral-large",
        "name": "Mistral-Large",
        "icon": "⚡",
        "badge": "Catalysts",
        "description": "Mistral AI reasoning model for corporate earnings surprises and news catalysts.",
        "color": "#f59e0b",
        "default_limit_1m": 20,
        "default_limit_1h": 100,
        "default_limit_24h": 200,
    },
]


class RateLimitTracker:
    """Thread-safe in-memory sliding window request tracker and OpenRouter quota cache."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # Deque of timestamps per downstream and model
        self._request_timestamps: dict[str, collections.deque[float]] = {
            k: collections.deque(maxlen=10000) for k in DOWNSTREAM_CRITERIA
        }
        for m in AVAILABLE_AI_MODELS:
            self._request_timestamps[m["id"].lower()] = collections.deque(maxlen=10000)
            self._request_timestamps[m["name"].lower()] = collections.deque(maxlen=10000)

        # Last known HTTP response headers from OpenRouter
        self._openrouter_headers: dict[str, Any] = {
            "limit": None,
            "remaining": None,
            "reset": None,
            "last_updated": None,
        }
        # Cached OpenRouter key metadata from /api/v1/auth/key
        self._openrouter_key_cache: dict[str, Any] = {}
        self._openrouter_key_last_fetched: float = 0.0

    def record_request(self, service: str, status_code: int = 200) -> None:
        """Record an outbound request timestamp for the given downstream service or model."""
        now = time.time()
        service_key = service.lower().strip()
        with self._lock:
            if service_key not in self._request_timestamps:
                self._request_timestamps[service_key] = collections.deque(maxlen=10000)
            self._request_timestamps[service_key].append(now)

    def update_openrouter_headers(self, headers: dict[str, Any]) -> None:
        """Store x-ratelimit-* headers from OpenRouter API responses."""
        with self._lock:
            limit_val = headers.get("x-ratelimit-limit") or headers.get("X-RateLimit-Limit")
            rem_val = headers.get("x-ratelimit-remaining") or headers.get("X-RateLimit-Remaining")
            reset_val = headers.get("x-ratelimit-reset") or headers.get("X-RateLimit-Reset")

            if limit_val is not None:
                try:
                    self._openrouter_headers["limit"] = int(limit_val)
                except (ValueError, TypeError):
                    pass
            if rem_val is not None:
                try:
                    self._openrouter_headers["remaining"] = int(rem_val)
                except (ValueError, TypeError):
                    pass
            if reset_val is not None:
                try:
                    self._openrouter_headers["reset"] = float(reset_val)
                except (ValueError, TypeError):
                    pass
            self._openrouter_headers["last_updated"] = time.time()

    def _fetch_openrouter_key_info(self, api_key: str) -> dict[str, Any]:
        """Query https://openrouter.ai/api/v1/auth/key for real-time key usage and limits."""
        now = time.time()
        # Cache key info for 60 seconds to avoid hitting OpenRouter auth endpoint excessively
        if self._openrouter_key_cache and (now - self._openrouter_key_last_fetched < 60):
            return self._openrouter_key_cache

        try:
            resp = requests.get(
                "https://openrouter.ai/api/v1/auth/key",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json().get("data", {})
                self._openrouter_key_cache = data
                self._openrouter_key_last_fetched = now
                return data
            else:
                logger.debug("OpenRouter auth/key check returned status %s", resp.status_code)
        except Exception as e:
            logger.debug("Failed checking OpenRouter key info: %s", e)

        return self._openrouter_key_cache


    def get_models_summary(self) -> list[dict[str, Any]]:
        """Compute rate limit consumption and remaining capacity for each supported AI model."""
        now = time.time()
        openrouter_summary = self.get_downstream_summary().get("downstreams", {}).get("openrouter", {})
        or_remaining_1m = openrouter_summary.get("timeframes", {}).get("1m", {}).get("remaining", 20)
        or_remaining_24h = openrouter_summary.get("timeframes", {}).get("24h", {}).get("remaining", 200)

        out = []
        with self._lock:
            for m in AVAILABLE_AI_MODELS:
                m_id = m["id"].lower()
                m_name = m["name"].lower()
                # Aggregate timestamps recorded under id or display name
                timestamps = list(self._request_timestamps.get(m_id, [])) + list(self._request_timestamps.get(m_name, []))

                count_1m = sum(1 for t in timestamps if now - t <= 60)
                count_1h = sum(1 for t in timestamps if now - t <= 3600)
                count_24h = sum(1 for t in timestamps if now - t <= 86400)

                allowed_1m = m.get("default_limit_1m", 20)
                allowed_1h = m.get("default_limit_1h", 100)
                allowed_24h = m.get("default_limit_24h", 200)

                # Effective remaining is min of model local window and openrouter overall quota
                rem_1m = max(0, min(allowed_1m - count_1m, or_remaining_1m))
                rem_24h = max(0, min(allowed_24h - count_24h, or_remaining_24h))

                status = "normal"
                status_badge = "🟢 Ready"
                if rem_1m <= 0 or rem_24h <= 0:
                    status = "throttled"
                    status_badge = "🔴 Cooldown / Limit"
                elif rem_1m <= 3 or rem_24h <= 15:
                    status = "warning"
                    status_badge = "🟡 Near Quota"

                out.append({
                    "id": m["id"],
                    "name": m["name"],
                    "icon": m["icon"],
                    "badge": m["badge"],
                    "description": m["description"],
                    "color": m["color"],
                    "status": status,
                    "status_badge": status_badge,
                    "count_1m": count_1m,
                    "allowed_1m": allowed_1m,
                    "remaining_1m": rem_1m,
                    "count_1h": count_1h,
                    "allowed_1h": allowed_1h,
                    "count_24h": count_24h,
                    "allowed_24h": allowed_24h,
                    "remaining_24h": rem_24h,
                })
        return out

    def get_downstream_summary(self, settings: Settings | None = None) -> dict[str, Any]:
        """Compute the allowed vs used metrics across 1m, 1h, and 24h timeframes for all downstreams."""
        now = time.time()
        openrouter_key = os.getenv("OPENROUTER_API_KEY", "").strip()
        is_openrouter_configured = bool(openrouter_key)

        openrouter_key_info: dict[str, Any] = {}
        is_free_tier = True
        if is_openrouter_configured:
            openrouter_key_info = self._fetch_openrouter_key_info(openrouter_key)
            if "is_free_tier" in openrouter_key_info:
                is_free_tier = bool(openrouter_key_info.get("is_free_tier"))
            elif openrouter_key_info.get("limit") is not None and openrouter_key_info.get("limit") > 0:
                is_free_tier = False

        summary: dict[str, Any] = {}

        with self._lock:
            for key, meta in DOWNSTREAM_CRITERIA.items():
                timestamps = list(self._request_timestamps.get(key, []))

                # Count requests in sliding windows
                count_1m = sum(1 for t in timestamps if now - t <= 60)
                count_1h = sum(1 for t in timestamps if now - t <= 3600)
                count_24h = sum(1 for t in timestamps if now - t <= 86400)

                # Determine limits (Free tier vs Standard)
                tier_limits = meta["free_tier_limits"] if (key == "openrouter" and is_free_tier) else meta["default_limits"]

                allowed_1m = tier_limits.get("1m", 20)
                allowed_1h = tier_limits.get("1h", 100)
                allowed_24h = tier_limits.get("24h", 200)

                # Utilization percentages
                util_1m = min(100.0, round((count_1m / max(1, allowed_1m)) * 100.0, 1))
                util_1h = min(100.0, round((count_1h / max(1, allowed_1h)) * 100.0, 1))
                util_24h = min(100.0, round((count_24h / max(1, allowed_24h)) * 100.0, 1))

                # Determine status
                max_util = max(util_1m, util_1h, util_24h)
                if max_util >= 90.0:
                    status = "throttled"
                    status_badge = "🔴 High / Near Limit"
                elif max_util >= 70.0:
                    status = "warning"
                    status_badge = "🟡 Moderate"
                else:
                    status = "normal"
                    status_badge = "🟢 Healthy"

                service_summary = {
                    "key": key,
                    "service_name": meta["service_name"],
                    "icon": meta["icon"],
                    "description": meta["description"],
                    "unit": meta["unit"],
                    "docs_url": meta["docs_url"],
                    "is_configured": is_openrouter_configured if key == "openrouter" else True,
                    "is_free_tier": is_free_tier if key == "openrouter" else True,
                    "status": status,
                    "status_badge": status_badge,
                    "max_utilization_pct": max_util,
                    "timeframes": {
                        "1m": {
                            "label": "1 Minute",
                            "current": count_1m,
                            "allowed": allowed_1m,
                            "remaining": max(0, allowed_1m - count_1m),
                            "utilization_pct": util_1m,
                        },
                        "1h": {
                            "label": "1 Hour",
                            "current": count_1h,
                            "allowed": allowed_1h,
                            "remaining": max(0, allowed_1h - count_1h),
                            "utilization_pct": util_1h,
                        },
                        "24h": {
                            "label": "24 Hours (Daily)",
                            "current": count_24h,
                            "allowed": allowed_24h,
                            "remaining": max(0, allowed_24h - count_24h),
                            "utilization_pct": util_24h,
                        },
                    },
                }

                # Extra OpenRouter details
                if key == "openrouter":
                    service_summary["openrouter_key_info"] = {
                        "label": openrouter_key_info.get("label", "Default API Key"),
                        "usage": openrouter_key_info.get("usage", 0.0),
                        "limit": openrouter_key_info.get("limit"),
                        "is_free_tier": is_free_tier,
                        "rate_limit": openrouter_key_info.get("rate_limit", {}),
                    }
                    service_summary["openrouter_live_headers"] = {
                        "limit": self._openrouter_headers.get("limit"),
                        "remaining": self._openrouter_headers.get("remaining"),
                        "reset": self._openrouter_headers.get("reset"),
                        "last_updated": self._openrouter_headers.get("last_updated"),
                    }

                summary[key] = service_summary

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "downstreams": summary,
            "openrouter_counter": {
                "current_24h": summary.get("openrouter", {}).get("timeframes", {}).get("24h", {}).get("current", 0),
                "allowed_24h": summary.get("openrouter", {}).get("timeframes", {}).get("24h", {}).get("allowed", 200),
                "remaining_24h": summary.get("openrouter", {}).get("timeframes", {}).get("24h", {}).get("remaining", 200),
                "utilization_pct": summary.get("openrouter", {}).get("timeframes", {}).get("24h", {}).get("utilization_pct", 0.0),
                "is_free_tier": is_free_tier,
                "is_configured": is_openrouter_configured,
                "status": summary.get("openrouter", {}).get("status", "normal"),
            },
        }


# Global singleton instance
tracker = RateLimitTracker()


def record_request(service: str, status_code: int = 200) -> None:
    """Convenience helper to record request metrics."""
    tracker.record_request(service, status_code)


def update_openrouter_headers(headers: dict[str, Any]) -> None:
    """Convenience helper to store OpenRouter HTTP headers."""
    tracker.update_openrouter_headers(headers)


def get_ratelimits_summary(settings: Settings | None = None) -> dict[str, Any]:
    """Retrieve the unified rate limit & quota payload."""
    return tracker.get_downstream_summary(settings)


def get_models_rate_limits() -> list[dict[str, Any]]:
    """Retrieve list of supported models and their live rate limit stats."""
    return tracker.get_models_summary()
