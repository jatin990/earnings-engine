"""Tests for consensus latency averaging and rate-limit gating.

Covers:
- RateLimitTracker.get_average_latency: correct sliding-window mean
- RateLimitTracker.is_rate_limited: 1m / 24h quota and high-latency degradation
- module-level convenience wrappers: get_average_latency, is_rate_limited
- aggregator.compute_latency_average: delegation to rate_limits
"""
from __future__ import annotations

import time
import collections
import pytest

from earnings_engine.rate_limits import RateLimitTracker, get_average_latency, is_rate_limited, is_degraded
from earnings_engine.consensus.aggregator import compute_latency_average


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tracker() -> RateLimitTracker:
    """Return a fresh RateLimitTracker with hydration disabled."""
    t = object.__new__(RateLimitTracker)
    import threading
    t._lock = threading.Lock()
    t._is_hydrated = True  # skip DB hydration
    t._request_timestamps = collections.defaultdict(lambda: collections.deque(maxlen=10000))
    t._generation_history = collections.defaultdict(lambda: collections.deque(maxlen=5000))
    t._openrouter_headers = {"limit": None, "remaining": None, "reset": None, "last_updated": None}
    t._openrouter_key_cache = {}
    t._openrouter_key_last_fetched = 0.0
    return t


# ---------------------------------------------------------------------------
# get_average_latency
# ---------------------------------------------------------------------------

class TestGetAverageLatency:
    def test_returns_correct_mean_within_window(self):
        tracker = _make_tracker()
        now = time.time()
        key = "test-model"
        for lat in [100.0, 200.0, 300.0]:
            tracker._generation_history[key].append({"timestamp": now, "latency_ms": lat, "success": True})

        avg = tracker.get_average_latency(key, window_seconds=3600)
        assert avg == pytest.approx(200.0, abs=0.1)

    def test_ignores_records_outside_window(self):
        tracker = _make_tracker()
        now = time.time()
        key = "test-model-old"
        # Add an old record (outside window)
        tracker._generation_history[key].append({"timestamp": now - 7200, "latency_ms": 9999.0, "success": True})
        # Add a recent record
        tracker._generation_history[key].append({"timestamp": now, "latency_ms": 500.0, "success": True})

        avg = tracker.get_average_latency(key, window_seconds=3600)
        assert avg == pytest.approx(500.0, abs=0.1)

    def test_falls_back_to_all_time_when_window_empty(self):
        tracker = _make_tracker()
        now = time.time()
        key = "fallback-model"
        # Only old records
        tracker._generation_history[key].append({"timestamp": now - 7200, "latency_ms": 1234.0, "success": True})

        avg = tracker.get_average_latency(key, window_seconds=3600)
        assert avg == pytest.approx(1234.0, abs=0.1)

    def test_returns_benchmark_default_when_no_records(self):
        tracker = _make_tracker()
        # deepseek-r1 has benchmark_avg_s=3.4 -> 3400ms
        avg = tracker.get_average_latency("deepseek/deepseek-r1", window_seconds=3600)
        assert avg == pytest.approx(3400.0, abs=1.0)

    def test_module_wrapper_delegates(self):
        # Module-level helper should not raise and return a float
        result = get_average_latency("mistralai/mistral-large", window_seconds=3600)
        assert isinstance(result, float)
        assert result > 0


# ---------------------------------------------------------------------------
# is_rate_limited & is_degraded
# ---------------------------------------------------------------------------

class TestIsRateLimited:
    def test_returns_none_when_under_limits(self):
        tracker = _make_tracker()
        result = tracker.is_rate_limited("meta-llama/llama-3.3-70b-instruct")
        assert result is None

    def test_detects_1m_quota_exhaustion(self):
        tracker = _make_tracker()
        key = "deepseek/deepseek-r1"
        now = time.time()
        # Simulate 20 requests in the last 60s (limit is 20)
        for _ in range(20):
            tracker._request_timestamps[key].append(now)

        result = tracker.is_rate_limited(key)
        assert result is not None
        assert "1m quota" in result.lower()

    def test_detects_24h_quota_exhaustion(self):
        tracker = _make_tracker()
        key = "qwen/qwen-2.5-72b-instruct"
        now = time.time()
        # Simulate 200 requests spread across last 24h (limit is 200)
        for i in range(200):
            tracker._request_timestamps[key].append(now - i * 60)

        result = tracker.is_rate_limited(key)
        assert result is not None
        assert "24h quota" in result.lower()

    def test_high_latency_does_not_block_rate_limit_or_degrade(self):
        tracker = _make_tracker()
        key = "mistralai/mistral-large"
        now = time.time()
        # Inject a high latency record in the last hour (15s)
        tracker._generation_history[key].append({"timestamp": now, "latency_ms": 15000.0, "success": True})

        # High latency must NOT trigger a hard rate-limit block or degradation block
        rl_res = tracker.is_rate_limited(key)
        assert rl_res is None

        deg_res = tracker.is_degraded(key)
        assert deg_res is None

    def test_local_models_never_rate_limited(self):
        tracker = _make_tracker()
        # Saturate timestamps for a local key
        now = time.time()
        for _ in range(9999):
            tracker._request_timestamps["local/deepseek-r1:8b"].append(now)

        result = tracker.is_rate_limited("local/deepseek-r1:8b")
        assert result is None

    def test_module_wrapper_delegates(self):
        result = is_rate_limited("meta-llama/llama-3.3-70b-instruct")
        # Returns None (ok) or a string (limited); both are valid types
        assert result is None or isinstance(result, str)

        deg_res = is_degraded("meta-llama/llama-3.3-70b-instruct")
        assert deg_res is None or isinstance(deg_res, str)


# ---------------------------------------------------------------------------
# aggregator.compute_latency_average
# ---------------------------------------------------------------------------

class TestComputeLatencyAverage:
    def test_returns_float(self):
        result = compute_latency_average("deepseek/deepseek-r1", window_seconds=3600)
        assert isinstance(result, float)
        assert result > 0

    def test_unknown_model_returns_safe_default(self):
        result = compute_latency_average("unknown/nonexistent-model", window_seconds=3600)
        assert isinstance(result, float)
        assert result == pytest.approx(5000.0, abs=1.0)
