"""Downstream API Rate Limit & Quota Tracking Engine.

Tracks API consumption, rate limit criteria, free-tier quotas, and response headers
across all downstreams (OpenRouter, Yahoo Finance, NSE, Gemini, etc.) across multiple timeframes.
"""
from __future__ import annotations

import collections
import os
import threading
import time
from datetime import datetime, timezone, timedelta
from typing import Any

import requests

from earnings_engine.config import Settings
from earnings_engine.logging_utils import get_logger

logger = get_logger("earnings_engine.rate_limits")

# Downstream default criteria definition (Free tier and standard limits)
DOWNSTREAM_CRITERIA: dict[str, dict[str, Any]] = {
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
    "kronos": {
        "service_name": "Kronos AI (14-Day Sequence Forecaster)",
        "icon": "⚡",
        "description": "Deep sequence transformer generating 14-day price trajectories and support/resistance zones.",
        "free_tier_limits": {
            "1m": 60,
            "1h": 500,
            "24h": 2000,
        },
        "default_limits": {
            "1m": 120,
            "1h": 1000,
            "24h": 5000,
        },
        "unit": "inferences",
        "docs_url": "https://pytorch.org",
    },
    "local_ai": {
        "service_name": "Local AI (Ollama / DeepSeek-R1 / Llama-3)",
        "icon": "💻",
        "description": "Offline on-device GPU inference. Free, unlimited, and private.",
        "free_tier_limits": {
            "1m": 9999,
            "1h": 9999,
            "24h": 9999,
        },
        "default_limits": {
            "1m": 9999,
            "1h": 9999,
            "24h": 9999,
        },
        "unit": "inferences",
        "docs_url": "https://ollama.com",
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
        "benchmark_avg_s": 3.4,
        "benchmark_success_rate_pct": 99.2,
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
        "benchmark_avg_s": 2.1,
        "benchmark_success_rate_pct": 99.8,
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
        "benchmark_avg_s": 2.3,
        "benchmark_success_rate_pct": 99.6,
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
        "benchmark_avg_s": 1.9,
        "benchmark_success_rate_pct": 99.7,
        "default_limit_1m": 20,
        "default_limit_1h": 100,
        "default_limit_24h": 200,
    },
    {
        "id": "google/gemma-4-31b-it:free",
        "name": "Gemma-4-31B",
        "icon": "💎",
        "badge": "Multimodal Free",
        "description": "Google DeepMind dense multimodal model (30.7B) with 256K context, optimized for numerical structures & reasoning.",
        "color": "#06b6d4",
        "benchmark_avg_s": 1.6,
        "benchmark_success_rate_pct": 100.0,
        "default_limit_1m": 30,
        "default_limit_1h": 200,
        "default_limit_24h": 500,
    },
    {
        "id": "z-ai/glm-5.2",
        "name": "GLM-5.2",
        "icon": "🐉",
        "badge": "Deep Reasoning (Z.ai)",
        "description": "Z.ai flagship 753B reasoning & long-horizon architecture with 1M context, specialized for financial modeling.",
        "color": "#ec4899",
        "benchmark_avg_s": 3.8,
        "benchmark_success_rate_pct": 99.1,
        "default_limit_1m": 20,
        "default_limit_1h": 100,
        "default_limit_24h": 200,
    },
    {
        "id": "local/deepseek-r1:8b",
        "name": "Local-AI",
        "icon": "💻",
        "badge": "Local GPU/CPU",
        "description": "Local offline LLM (Ollama / LM Studio / DeepSeek-R1 / Llama-3). Zero API quota consumed.",
        "color": "#10b981",
        "benchmark_avg_s": 1.2,
        "benchmark_success_rate_pct": 100.0,
        "default_limit_1m": 9999,
        "default_limit_1h": 9999,
        "default_limit_24h": 9999,
    },
]


class RateLimitTracker:
    """Thread-safe in-memory sliding window request tracker with SQLite persistence and OpenRouter quota cache."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._is_hydrated: bool = False
        # Deque of timestamps per downstream and model
        self._request_timestamps: dict[str, collections.deque[float]] = {
            k: collections.deque(maxlen=10000) for k in DOWNSTREAM_CRITERIA
        }
        # Deque of detailed generation metrics (timestamp, latency_ms, tokens, is_local) per model
        self._generation_history: dict[str, collections.deque[dict[str, Any]]] = {
            k: collections.deque(maxlen=5000) for k in DOWNSTREAM_CRITERIA
        }
        for m in AVAILABLE_AI_MODELS:
            self._request_timestamps[m["id"].lower()] = collections.deque(maxlen=10000)
            self._request_timestamps[m["name"].lower()] = collections.deque(maxlen=10000)
            self._generation_history[m["id"].lower()] = collections.deque(maxlen=5000)
            self._generation_history[m["name"].lower()] = collections.deque(maxlen=5000)

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

        # Auto-hydrate historical real model generation records from database
        try:
            self.hydrate_from_db()
        except Exception:
            pass

    def hydrate_from_db(self, force: bool = False) -> None:
        """Load all historical real model generation latencies and API call counts from SQLite database."""
        if self._is_hydrated and not force:
            return
        try:
            from earnings_engine.config import Settings
            from earnings_engine.data.db import get_db_connection
            settings = Settings()
            conn = get_db_connection(settings)

            # Ensure ai_model_telemetry table exists
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ai_model_telemetry (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    model_id TEXT NOT NULL,
                    model_name TEXT,
                    created_at TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    latency_ms REAL NOT NULL,
                    tokens INTEGER,
                    is_local INTEGER DEFAULT 0,
                    success INTEGER DEFAULT 1,
                    error_message TEXT,
                    ticker TEXT
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_telemetry_model ON ai_model_telemetry(model_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_telemetry_ts ON ai_model_telemetry(timestamp)")

            # Ensure downstream_api_calls table exists
            conn.execute("""
                CREATE TABLE IF NOT EXISTS downstream_api_calls (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    service TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    status_code INTEGER DEFAULT 200
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_api_calls_service ON downstream_api_calls(service)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_api_calls_ts ON downstream_api_calls(timestamp)")
            conn.commit()

            # Backfill from consensus_predictions if telemetry table is empty
            tel_count = conn.execute("SELECT COUNT(*) FROM ai_model_telemetry").fetchone()[0]
            if tel_count == 0:
                try:
                    import json
                    from datetime import datetime
                    cp_rows = conn.execute("SELECT ticker, created_at, models_breakdown_json FROM consensus_predictions").fetchall()
                    for ticker, created_at, m_json in cp_rows:
                        try:
                            models = json.loads(m_json)
                            try:
                                dt = datetime.fromisoformat(created_at)
                                ts = dt.timestamp()
                            except Exception:
                                ts = time.time()
                            for m in models:
                                lat = m.get("latency_ms")
                                if lat is not None:
                                    m_id = m.get("model_id") or m.get("model_name") or "unknown"
                                    m_name = m.get("model_name")
                                    is_succ = 1 if not m.get("error") else 0
                                    conn.execute(
                                        "INSERT INTO ai_model_telemetry (model_id, model_name, created_at, timestamp, latency_ms, tokens, is_local, success, error_message, ticker) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                                        (m_id, m_name, created_at, ts, float(lat), m.get("tokens"), 1 if m.get("is_local") else 0, is_succ, m.get("error"), ticker)
                                    )
                        except Exception:
                            pass
                    conn.commit()
                except Exception as eb:
                    logger.debug("Telemetry backfill from consensus_predictions skipped: %s", eb)

            # Hydrate in-memory history deques
            rows = conn.execute("SELECT model_id, model_name, timestamp, latency_ms, tokens, is_local, success FROM ai_model_telemetry ORDER BY timestamp ASC").fetchall()
            with self._lock:
                for r in rows:
                    m_id = str(r[0]).lower().strip()
                    m_name = str(r[1] or "").lower().strip()
                    record = {
                        "timestamp": float(r[2]),
                        "latency_ms": float(r[3]),
                        "tokens": r[4],
                        "is_local": bool(r[5]),
                        "success": bool(r[6]),
                    }
                    if m_id not in self._generation_history:
                        self._generation_history[m_id] = collections.deque(maxlen=5000)
                    self._generation_history[m_id].append(record)

                    if m_name and m_name != m_id:
                        if m_name not in self._generation_history:
                            self._generation_history[m_name] = collections.deque(maxlen=5000)
                        self._generation_history[m_name].append(record)

                    if m_id not in self._request_timestamps:
                        self._request_timestamps[m_id] = collections.deque(maxlen=10000)
                    self._request_timestamps[m_id].append(float(r[2]))

            # Hydrate downstream API call timestamps from past 7 days
            seven_days_ago = time.time() - 604800
            call_rows = conn.execute(
                "SELECT service, timestamp FROM downstream_api_calls WHERE timestamp >= ? ORDER BY timestamp ASC",
                (seven_days_ago,)
            ).fetchall()
            with self._lock:
                for s_name, s_ts in call_rows:
                    s_key = str(s_name).lower().strip()
                    if s_key not in self._request_timestamps:
                        self._request_timestamps[s_key] = collections.deque(maxlen=10000)
                    self._request_timestamps[s_key].append(float(s_ts))

            self._is_hydrated = True
            logger.info("Hydrated %d empirical model generation records and %d API calls from DB", len(rows), len(call_rows))
        except Exception as e:
            logger.warning("Failed hydrating AI model telemetry from DB: %s", e)

    def record_request(self, service: str, status_code: int = 200) -> None:
        """Record an outbound request timestamp for the given downstream service or model."""
        now = time.time()
        service_key = service.lower().strip()
        with self._lock:
            if service_key not in self._request_timestamps:
                self._request_timestamps[service_key] = collections.deque(maxlen=10000)
            self._request_timestamps[service_key].append(now)

        # Asynchronously persist to downstream_api_calls
        def _persist_call():
            try:
                from earnings_engine.config import Settings
                from earnings_engine.data.db import get_db_connection
                conn = get_db_connection(Settings())
                created_at = datetime.now(timezone.utc).isoformat()
                conn.execute(
                    "INSERT INTO downstream_api_calls (service, created_at, timestamp, status_code) VALUES (?, ?, ?, ?)",
                    (service_key, created_at, now, status_code)
                )
                conn.commit()
            except Exception:
                pass
        threading.Thread(target=_persist_call, daemon=True).start()

    def record_generation(
        self,
        model: str,
        latency_ms: float,
        tokens: int | None = None,
        is_local: bool = False,
        success: bool = True,
        ticker: str | None = None,
        error_message: str | None = None,
    ) -> None:
        """Record an AI inference generation run with latency, success status and tokens across time horizons."""
        now = time.time()
        m_key = model.lower().strip()
        record = {
            "timestamp": now,
            "latency_ms": float(latency_ms),
            "tokens": tokens,
            "is_local": is_local,
            "success": bool(success),
        }
        with self._lock:
            if m_key not in self._generation_history:
                self._generation_history[m_key] = collections.deque(maxlen=5000)
            self._generation_history[m_key].append(record)
            if m_key not in self._request_timestamps:
                self._request_timestamps[m_key] = collections.deque(maxlen=10000)
            self._request_timestamps[m_key].append(now)

        # Persist to ai_model_telemetry table in background thread
        def _persist():
            try:
                from earnings_engine.config import Settings
                from earnings_engine.data.db import get_db_connection
                conn = get_db_connection(Settings())
                created_at = datetime.now(timezone.utc).isoformat()
                m_short = model.split("/")[-1]
                conn.execute(
                    "INSERT INTO ai_model_telemetry (model_id, model_name, created_at, timestamp, latency_ms, tokens, is_local, success, error_message, ticker) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (model, m_short, created_at, now, float(latency_ms), tokens, 1 if is_local else 0, 1 if success else 0, error_message, ticker)
                )
                conn.commit()
            except Exception:
                pass
        threading.Thread(target=_persist, daemon=True).start()

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
        """Return list of models with quota consumption and empirical multi-horizon generation latency & success rate metrics."""
        self.hydrate_from_db()
        now = time.time()
        or_remaining_1m = self._openrouter_headers["remaining"] if self._openrouter_headers["remaining"] is not None else 20
        or_remaining_24h = 200

        out = []
        with self._lock:
            for m in AVAILABLE_AI_MODELS:
                m_id = m["id"].lower()
                m_name = m["name"].lower()
                m_short = m_id.split("/")[-1]

                # Match all related keys (ID, display name, short tag)
                matched_keys = {m_id, m_name, m_short}
                if "local" in m_id or "local" in m_name:
                    for k in self._generation_history.keys():
                        if "local" in k or "ollama" in k:
                            matched_keys.add(k)

                timestamps: list[float] = []
                gen_records: list[dict[str, Any]] = []
                for k in matched_keys:
                    timestamps.extend(self._request_timestamps.get(k, []))
                    gen_records.extend(self._generation_history.get(k, []))

                # Deduplicate generation records by timestamp & latency
                seen_ts = set()
                dedup_gens: list[dict[str, Any]] = []
                for g in gen_records:
                    ts_key = (round(g["timestamp"], 2), round(g["latency_ms"], 1))
                    if ts_key not in seen_ts:
                        seen_ts.add(ts_key)
                        dedup_gens.append(g)

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

                # Multi-range generation latency & success rate analytics
                g_1h = [g for g in dedup_gens if now - g["timestamp"] <= 3600]
                g_24h = [g for g in dedup_gens if now - g["timestamp"] <= 86400]
                g_7d = [g for g in dedup_gens if now - g["timestamp"] <= 604800]

                avg_1h_ms = round(sum(g["latency_ms"] for g in g_1h) / len(g_1h), 1) if g_1h else None
                avg_24h_ms = round(sum(g["latency_ms"] for g in g_24h) / len(g_24h), 1) if g_24h else None
                avg_7d_ms = round(sum(g["latency_ms"] for g in g_7d) / len(g_7d), 1) if g_7d else None
                avg_all_ms = round(sum(g["latency_ms"] for g in dedup_gens) / len(dedup_gens), 1) if dedup_gens else None

                latest_ms = round(dedup_gens[-1]["latency_ms"], 1) if dedup_gens else None
                min_ms = round(min(g["latency_ms"] for g in dedup_gens), 1) if dedup_gens else None
                max_ms = round(max(g["latency_ms"] for g in dedup_gens), 1) if dedup_gens else None

                # Success rates
                b_success = m.get("benchmark_success_rate_pct", 100.0)
                b_avg_s = m.get("benchmark_avg_s", 5.0)

                succ_1h = sum(1 for g in g_1h if g.get("success", True))
                succ_rate_1h = round((succ_1h / len(g_1h)) * 100.0, 1) if g_1h else b_success

                succ_24h = sum(1 for g in g_24h if g.get("success", True))
                succ_rate_24h = round((succ_24h / len(g_24h)) * 100.0, 1) if g_24h else b_success

                succ_7d = sum(1 for g in g_7d if g.get("success", True))
                succ_rate_7d = round((succ_7d / len(g_7d)) * 100.0, 1) if g_7d else b_success

                succ_all = sum(1 for g in dedup_gens if g.get("success", True))
                succ_rate_all = round((succ_all / len(dedup_gens)) * 100.0, 1) if dedup_gens else b_success

                # True empirical average return time in seconds
                if dedup_gens:
                    effective_avg_s = round(avg_all_ms / 1000.0, 1) if avg_all_ms is not None else b_avg_s
                    effective_success_rate = succ_rate_all
                    has_empirical_runs = True
                else:
                    effective_avg_s = b_avg_s
                    effective_success_rate = b_success
                    has_empirical_runs = False

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
                    "is_rate_limited": (rem_1m <= 0 or rem_24h <= 0),
                    "is_degraded": bool(avg_1h_ms and avg_1h_ms > 8000),
                    "degraded_reason": f"High latency degradation (1h avg {avg_1h_ms:.0f}ms > 8000ms threshold)" if (avg_1h_ms and avg_1h_ms > 8000) else None,
                    "status": "rate_limited" if (rem_1m <= 0 or rem_24h <= 0) else ("degraded" if (avg_1h_ms and avg_1h_ms > 8000) else "ready"),
                    # Multi-horizon Generation Latency & Success Rate Metrics
                    "total_generations": len(dedup_gens),
                    "has_empirical_runs": has_empirical_runs,
                    "success_count": succ_all,
                    "failure_count": len(dedup_gens) - succ_all,
                    "success_rate_pct": effective_success_rate,
                    "avg_return_time_s": effective_avg_s,
                    "benchmark_avg_s": b_avg_s,
                    "benchmark_success_rate_pct": b_success,
                    "latest_latency_ms": latest_ms,
                    "latest_latency_s": round(latest_ms / 1000, 1) if latest_ms else None,
                    "min_latency_s": round(min_ms / 1000, 1) if min_ms else None,
                    "max_latency_s": round(max_ms / 1000, 1) if max_ms else None,
                    "avg_latency_1h_ms": avg_1h_ms,
                    "avg_latency_1h_s": round(avg_1h_ms / 1000, 1) if avg_1h_ms else effective_avg_s,
                    "avg_latency_24h_ms": avg_24h_ms,
                    "avg_latency_24h_s": round(avg_24h_ms / 1000, 1) if avg_24h_ms else effective_avg_s,
                    "avg_latency_7d_ms": avg_7d_ms,
                    "avg_latency_7d_s": round(avg_7d_ms / 1000, 1) if avg_7d_ms else effective_avg_s,
                    "avg_latency_all_ms": avg_all_ms,
                    "avg_latency_all_s": effective_avg_s,
                    "min_latency_ms": min_ms,
                    "max_latency_ms": max_ms,
                    "generation_stats": {
                        "1h": {"count": len(g_1h), "success_count": succ_1h, "success_rate_pct": succ_rate_1h, "avg_ms": avg_1h_ms, "avg_s": round(avg_1h_ms / 1000, 1) if avg_1h_ms else effective_avg_s},
                        "24h": {"count": len(g_24h), "success_count": succ_24h, "success_rate_pct": succ_rate_24h, "avg_ms": avg_24h_ms, "avg_s": round(avg_24h_ms / 1000, 1) if avg_24h_ms else effective_avg_s},
                        "7d": {"count": len(g_7d), "success_count": succ_7d, "success_rate_pct": succ_rate_7d, "avg_ms": avg_7d_ms, "avg_s": round(avg_7d_ms / 1000, 1) if avg_7d_ms else effective_avg_s},
                        "all_time": {"count": len(dedup_gens), "success_count": succ_all, "success_rate_pct": succ_rate_all, "avg_ms": avg_all_ms, "avg_s": effective_avg_s},
                    }
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


    def get_average_latency(self, model_key: str, window_seconds: int = 3600) -> float:
        """Return sliding-window average generation latency (ms) for a model.

        Reads from the in-memory ``_generation_history`` deque for records within
        ``window_seconds``.  Falls back to the model benchmark default if no
        empirical records exist in the window.

        Args:
            model_key: Model ID, display name, or short tag (case-insensitive).
            window_seconds: Sliding window size in seconds (default 3600 = 1 hour).

        Returns:
            Average latency in milliseconds.
        """
        m_key = model_key.lower().strip()
        now = time.time()
        cutoff = now - window_seconds

        with self._lock:
            records = list(self._generation_history.get(m_key, []))

        windowed = [r["latency_ms"] for r in records if r.get("timestamp", 0) >= cutoff]
        if windowed:
            return round(sum(windowed) / len(windowed), 1)

        # Fall back to all-time average if no records in window
        all_lats = [r["latency_ms"] for r in records if r.get("latency_ms") is not None]
        if all_lats:
            return round(sum(all_lats) / len(all_lats), 1)

        # Final fallback: benchmark default from AVAILABLE_AI_MODELS
        for m in AVAILABLE_AI_MODELS:
            if m["id"].lower() == m_key or m["name"].lower() == m_key or m["id"].lower().split("/")[-1] == m_key:
                return round(m.get("benchmark_avg_s", 5.0) * 1000, 1)
        return 5000.0  # 5s generic default

    def is_rate_limited(self, model_key: str) -> str | None:
        """Check whether a model is currently hard rate-limited on the 1m or 24h quota window.

        Note: Latency degradation does NOT block execution or trigger rate-limiting;
        call is_degraded() to check for high latency warnings.

        Args:
            model_key: Model ID, display name, or short tag (case-insensitive).

        Returns:
            A human-readable reason string if hard quota is exhausted, or ``None`` if OK to execute.
        """
        m_key = model_key.lower().strip()
        now = time.time()

        # Local models are never rate-limited by quota
        if m_key.startswith("local") or m_key.startswith("ollama") or m_key.startswith("lmstudio"):
            return None

        # Find declared limits for this model
        allowed_1m = 20
        allowed_24h = 200
        for m in AVAILABLE_AI_MODELS:
            if m["id"].lower() == m_key or m["name"].lower() == m_key or m["id"].lower().split("/")[-1] == m_key:
                allowed_1m = m.get("default_limit_1m", 20)
                allowed_24h = m.get("default_limit_24h", 200)
                break

        with self._lock:
            timestamps = list(self._request_timestamps.get(m_key, []))

        count_1m = sum(1 for t in timestamps if now - t <= 60)
        count_24h = sum(1 for t in timestamps if now - t <= 86400)

        if count_1m >= allowed_1m:
            return f"1m quota exhausted ({count_1m}/{allowed_1m} requests in last 60s)"
        if count_24h >= allowed_24h:
            return f"24h quota exhausted ({count_24h}/{allowed_24h} requests today)"

        # Also honour live OpenRouter remaining header if available
        with self._lock:
            or_remaining = self._openrouter_headers.get("remaining")
        if or_remaining is not None and or_remaining <= 0:
            return "OpenRouter global quota exhausted (x-ratelimit-remaining=0)"

        return None

    def is_degraded(self, model_key: str) -> str | None:
        """Check whether a model is currently experiencing high latency degradation (>8000ms 1h avg).

        Returns:
            A human-readable degradation reason string if degraded, or ``None`` if normal.
        """
        m_key = model_key.lower().strip()
        if m_key.startswith("local") or m_key.startswith("ollama") or m_key.startswith("lmstudio"):
            return None

        avg_1h = self.get_average_latency(m_key, window_seconds=3600)
        if avg_1h > 8000:
            return f"High latency degradation (1h avg {avg_1h:.0f}ms > 8000ms threshold)"
        return None

    def get_api_usage_summary(self, settings: Settings | None = None) -> dict[str, Any]:
        """Aggregate total API calls, today's calls (IST), 1h calls, and status for yfinance, nse, jugaad, and AI models."""
        self.hydrate_from_db()
        now = time.time()
        ist_offset = timezone(timedelta(hours=5, minutes=30))
        now_ist = datetime.now(ist_offset)
        today_start_ist = now_ist.replace(hour=0, minute=0, second=0, microsecond=0)
        today_start_ts = today_start_ist.timestamp()

        from earnings_engine.config import Settings
        from earnings_engine.data.db import get_db_connection
        settings = settings or Settings()

        all_time_counts: dict[str, int] = {}
        today_db_counts: dict[str, int] = {}
        try:
            conn = get_db_connection(settings)
            rows = conn.execute("SELECT service, COUNT(*) FROM downstream_api_calls GROUP BY service").fetchall()
            for s, c in rows:
                all_time_counts[str(s).lower().strip()] = int(c)

            today_rows = conn.execute("SELECT service, COUNT(*) FROM downstream_api_calls WHERE timestamp >= ? GROUP BY service", (today_start_ts,)).fetchall()
            for s, c in today_rows:
                today_db_counts[str(s).lower().strip()] = int(c)
        except Exception as e:
            logger.debug("Failed querying downstream_api_calls counts: %s", e)

        downstreams: list[dict[str, Any]] = []
        with self._lock:
            for key, meta in DOWNSTREAM_CRITERIA.items():
                ts_list = list(self._request_timestamps.get(key, []))
                count_1m = sum(1 for t in ts_list if now - t <= 60)
                count_1h = sum(1 for t in ts_list if now - t <= 3600)
                count_today_mem = sum(1 for t in ts_list if t >= today_start_ts)

                total_calls = max(len(ts_list), all_time_counts.get(key, 0))
                calls_today = max(count_today_mem, today_db_counts.get(key, 0))

                allowed_1m = meta["default_limits"].get("1m", 60)
                allowed_1h = meta["default_limits"].get("1h", 500)
                allowed_24h = meta["default_limits"].get("24h", 2000)

                status = "ready"
                status_badge = "🟢 Normal / Ready"
                if count_1m >= allowed_1m:
                    status = "throttled"
                    status_badge = "🔴 Throttled (1m)"
                elif count_1m >= allowed_1m * 0.8:
                    status = "warning"
                    status_badge = "🟡 High Traffic"

                downstreams.append({
                    "id": key,
                    "name": meta["service_name"],
                    "icon": meta["icon"],
                    "description": meta["description"],
                    "total_calls": total_calls,
                    "calls_today": calls_today,
                    "calls_1h": count_1h,
                    "calls_1m": count_1m,
                    "limit_1m": allowed_1m,
                    "limit_1h": allowed_1h,
                    "limit_24h": allowed_24h,
                    "status": status,
                    "status_badge": status_badge,
                    "unit": meta.get("unit", "requests"),
                    "docs_url": meta.get("docs_url", ""),
                })

        # AI Models summary
        models_summary = self.get_models_summary()
        ai_models: list[dict[str, Any]] = []
        for m in models_summary:
            m_id = m["id"].lower()
            m_short = m_id.split("/")[-1]
            all_calls = max(m.get("total_generations", 0), all_time_counts.get(m_id, 0), all_time_counts.get(m_short, 0))
            today_calls = max(m.get("count_24h", 0), today_db_counts.get(m_id, 0), today_db_counts.get(m_short, 0))
            ai_models.append({
                "id": m["id"],
                "name": m["name"],
                "icon": m["icon"],
                "badge": m["badge"],
                "description": m["description"],
                "color": m["color"],
                "total_calls": all_calls,
                "calls_today": today_calls,
                "calls_1h": m.get("count_1h", 0),
                "calls_1m": m.get("count_1m", 0),
                "remaining_1m": m.get("remaining_1m", 20),
                "remaining_24h": m.get("remaining_24h", 200),
                "avg_latency_s": m.get("avg_return_time_s"),
                "success_rate_pct": m.get("success_rate_pct", 100.0),
                "status": m.get("status", "ready"),
                "status_badge": m.get("status_badge", "🟢 Ready"),
            })

        total_all_time = sum(d["total_calls"] for d in downstreams) + sum(a["total_calls"] for a in ai_models)
        total_today = sum(d["calls_today"] for d in downstreams) + sum(a["calls_today"] for a in ai_models)

        return {
            "success": True,
            "as_of": now_ist.strftime("%Y-%m-%d %H:%M:%S IST"),
            "totals": {
                "total_calls_all_time": total_all_time,
                "total_calls_today": total_today,
                "yfinance_total": next((d["total_calls"] for d in downstreams if d["id"] == "yfinance"), 0),
                "yfinance_today": next((d["calls_today"] for d in downstreams if d["id"] == "yfinance"), 0),
                "nse_total": next((d["total_calls"] for d in downstreams if d["id"] == "nse"), 0),
                "nse_today": next((d["calls_today"] for d in downstreams if d["id"] == "nse"), 0),
                "jugaad_total": next((d["total_calls"] for d in downstreams if d["id"] == "jugaad_data"), 0),
                "jugaad_today": next((d["calls_today"] for d in downstreams if d["id"] == "jugaad_data"), 0),
                "ai_total": sum(a["total_calls"] for a in ai_models),
                "ai_today": sum(a["calls_today"] for a in ai_models),
            },
            "downstreams": downstreams,
            "ai_models": ai_models,
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


def get_api_usage_summary(settings: Settings | None = None) -> dict[str, Any]:
    """Retrieve API usage and count metrics for yfinance, nse, jugaad_data, and AI models."""
    return tracker.get_api_usage_summary(settings)


def record_generation(
    model: str,
    latency_ms: float,
    tokens: int | None = None,
    is_local: bool = False,
    success: bool = True,
    ticker: str | None = None,
    error_message: str | None = None,
) -> None:
    """Convenience helper to record generation latency and success metrics across time horizons."""
    tracker.record_generation(model, latency_ms, tokens=tokens, is_local=is_local, success=success, ticker=ticker, error_message=error_message)


def get_models_rate_limits() -> list[dict[str, Any]]:
    """Retrieve list of supported models and their live rate limit and generation latency stats."""
    return tracker.get_models_summary()


def get_average_latency(model_key: str, window_seconds: int = 3600) -> float:
    """Return the sliding-window average generation latency (ms) for a model."""
    return tracker.get_average_latency(model_key, window_seconds=window_seconds)


def is_rate_limited(model_key: str) -> str | None:
    """Check whether a model is currently hard rate-limited on quota (1m or 24h).

    Returns a human-readable reason string if hard-limited, or ``None`` if the model is OK to call.
    """
    return tracker.is_rate_limited(model_key)


def is_degraded(model_key: str) -> str | None:
    """Check whether a model is currently experiencing high latency degradation.

    Returns a reason string if degraded, or ``None`` if latency is within normal thresholds.
    """
    return tracker.is_degraded(model_key)
