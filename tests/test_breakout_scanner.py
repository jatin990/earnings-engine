"""Tests for the Breakout Radar scanner engine.

Validates score components, composite scoring, threshold filtering,
and the API endpoints.
"""
from __future__ import annotations

import pandas as pd
import numpy as np
import pytest
from fastapi.testclient import TestClient

from earnings_engine.data.breakout_scanner import (
    score_breakout,
    _score_resistance_proximity,
    _score_volume_surge,
    _score_price_compression,
    _score_momentum,
    _score_fundamental,
    get_cached_scan_results,
    get_scan_status,
    BREAKOUT_MIN_SCORE,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_prices(n: int = 60, trend: float = 0.003, base: float = 100.0) -> pd.DataFrame:
    """Build a synthetic price DataFrame with a rising trend."""
    closes = [base * (1 + trend) ** i for i in range(n)]
    volumes = [1_000_000] * n
    return pd.DataFrame({"close": closes, "volume": volumes})


def _make_flat_prices(n: int = 60, base: float = 100.0) -> pd.DataFrame:
    """Flat / sideways price series (low volatility)."""
    closes = [base + np.sin(i * 0.1) * 0.2 for i in range(n)]
    volumes = [500_000] * n
    return pd.DataFrame({"close": closes, "volume": volumes})


# ---------------------------------------------------------------------------
# Component scorer unit tests
# ---------------------------------------------------------------------------

class TestResistanceProximity:
    def test_at_52w_high_returns_max_score(self):
        closes = pd.Series([90.0 + i * 0.1 for i in range(100)])  # monotonically rising
        score, pct = _score_resistance_proximity(closes)
        assert score == 40.0
        assert pct >= 0.0  # at or above high

    def test_far_below_high_returns_zero(self):
        closes = pd.Series([100.0] * 50 + [60.0])  # big drop at end
        score, pct = _score_resistance_proximity(closes)
        assert score == 0.0
        assert pct < -8.0

    def test_within_2pct_below_high_scores_well(self):
        # price is exactly 2% below the high
        closes = pd.Series([100.0] * 20 + [98.0])
        score, pct = _score_resistance_proximity(closes)
        assert score >= 25.0
        assert pct == pytest.approx(-2.0, abs=0.01)


class TestVolumeSurge:
    def test_moderate_volume_gives_max_score(self):
        volumes = pd.Series([1_000_000] * 20 + [1_200_000])  # 1.2× surge
        score, ratio = _score_volume_surge(volumes)
        assert score == 10.0
        assert ratio >= 1.0

    def test_below_average_volume_gives_zero(self):
        volumes = pd.Series([1_000_000] * 20 + [500_000])
        score, ratio = _score_volume_surge(volumes)
        assert score == 0.0
        assert ratio < 1.0

    def test_heavy_volume_penalized(self):
        volumes = pd.Series([1_000_000] * 20 + [2_500_000])
        score, ratio = _score_volume_surge(volumes)
        assert score == 4.0


class TestPriceCompression:
    def test_very_tight_range_gives_high_score(self):
        # near-flat prices: ATR% ≈ 0.05%
        closes = pd.Series([100.0 + np.sin(i) * 0.02 for i in range(30)])
        score, atr = _score_price_compression(closes)
        assert score >= 8.0

    def test_high_volatility_gives_zero(self):
        # 5% daily moves
        closes = pd.Series([100 * (1.05 ** (i % 2 == 0) * 0.95 ** (i % 2 != 0)) for i in range(30)])
        score, atr = _score_price_compression(closes)
        assert score == 0.0 or atr > 2.5


class TestMomentum:
    def test_strong_uptrend_above_sma_scores_25(self):
        closes = pd.Series([80.0 + i * 0.5 for i in range(60)])  # strong uptrend
        score, signal = _score_momentum(closes)
        assert score == 25.0
        assert signal == "Strong"

    def test_downtrend_below_sma_scores_zero(self):
        closes = pd.Series([120.0 - i * 0.5 for i in range(60)])  # downtrend
        score, signal = _score_momentum(closes)
        assert score == 0.0
        assert signal == "None"


class TestFundamental:
    def test_all_nines_gives_max_score(self):
        score, avg = _score_fundamental([9.0, 9.0, 9.0])
        assert score == 15.0
        assert avg == 9.0

    def test_all_ones_gives_zero(self):
        score, avg = _score_fundamental([1.0, 1.0, 1.0])
        assert score == 0.0

    def test_mixed_scores_interpolated(self):
        score, avg = _score_fundamental([5.0, 7.0, 9.0])
        assert 0.0 < score < 15.0
        assert avg == pytest.approx(7.0)

    def test_none_values_ignored(self):
        score, avg = _score_fundamental([None, 9.0, None])
        assert score == 15.0
        assert avg == 9.0

    def test_all_none_returns_zero(self):
        score, avg = _score_fundamental([None, None])
        assert score == 0.0


# ---------------------------------------------------------------------------
# Composite scorer
# ---------------------------------------------------------------------------

class TestScoreBreakout:
    def test_breakout_candidate_near_high_high_volume(self):
        # Rising price near all-time high + volume surge today
        prices = _make_prices(n=60, trend=0.005)
        prices.loc[prices.index[-1], "volume"] = 3_000_000  # surge on last day
        result = score_breakout("TEST.NS", prices, [8.0, 9.0, 7.0])
        assert result is not None
        assert result["ticker"] == "TEST.NS"
        assert result["composite_score"] > 0
        assert result["composite_score"] <= 100

    def test_flat_stock_with_good_fundamentals_passes_threshold(self):
        prices = _make_flat_prices(n=60, base=500.0)
        result = score_breakout("FLAT.NS", prices, [9.0, 9.0, 9.0])
        assert result is not None
        assert result["fundamental_score"] == 15.0

    def test_empty_dataframe_returns_none(self):
        result = score_breakout("NONE.NS", pd.DataFrame(), [])
        assert result is None

    def test_insufficient_data_returns_none(self):
        prices = pd.DataFrame({"close": [100.0, 101.0, 102.0]})
        result = score_breakout("SHORT.NS", prices, [])
        assert result is None

    def test_all_subscores_present(self):
        prices = _make_prices(60)
        result = score_breakout("CHECK.NS", prices, [7.0, 8.0, 9.0])
        assert result is not None
        for key in ("resistance_score", "volume_score", "compression_score", "momentum_score", "fundamental_score"):
            assert key in result, f"Missing key: {key}"

    def test_composite_is_sum_of_subscores(self):
        prices = _make_prices(60)
        result = score_breakout("SUM.NS", prices, [5.0, 5.0, 5.0])
        assert result is not None
        expected = round(
            result["resistance_score"] + result["volume_score"] +
            result["compression_score"] + result["momentum_score"] +
            result["fundamental_score"], 1
        )
        assert result["composite_score"] == expected


# ---------------------------------------------------------------------------
# In-memory cache
# ---------------------------------------------------------------------------

class TestCacheAccessors:
    def test_get_cached_results_returns_list(self):
        results = get_cached_scan_results()
        assert isinstance(results, list)

    def test_get_scan_status_returns_dict(self):
        status = get_scan_status()
        assert isinstance(status, dict)
        assert "status" in status
        assert "candidates_found" in status
        assert "scan_intervals" in status or "scan_interval_min" in status


# ---------------------------------------------------------------------------
# API Endpoint tests
# ---------------------------------------------------------------------------

class TestBreakoutRadarEndpoints:
    @pytest.fixture(autouse=True)
    def client(self):
        from earnings_engine.api.server import app as fastapi_app
        self.client = TestClient(fastapi_app, raise_server_exceptions=False)

    def test_get_breakout_radar_returns_success(self):
        resp = self.client.get("/api/v1/breakout-radar")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "candidates" in data
        assert "scan_status" in data
        assert isinstance(data["candidates"], list)

    def test_get_breakout_radar_min_score_filter(self):
        resp = self.client.get("/api/v1/breakout-radar?min_score=100")
        assert resp.status_code == 200
        data = resp.json()
        # With min_score=100 and cold cache, candidates list should be empty
        for c in data["candidates"]:
            assert c["composite_score"] >= 100

    def test_get_breakout_radar_sort_by_parameter(self):
        resp = self.client.get("/api/v1/breakout-radar?sort_by=fundamental_score")
        assert resp.status_code == 200

    def test_post_refresh_triggers_scan(self):
        resp = self.client.post("/api/v1/breakout-radar/refresh")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "message" in data

    def test_get_breakout_radar_nifty_50_universe(self):
        resp = self.client.get("/api/v1/breakout-radar?universe=nifty_50")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["universe"] == "nifty_50"

    def test_post_refresh_with_nifty_50_universe(self):
        resp = self.client.post("/api/v1/breakout-radar/refresh?universe=nifty_50")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "nifty_50" in data["message"]

    def test_get_breakout_radar_live_and_prediction_signals(self):
        resp = self.client.get("/api/v1/breakout-radar?live=true")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data.get("is_live") is True
        for c in data["candidates"]:
            assert "prediction_signal" in c
            assert "prediction_color" in c
            assert c["prediction_color"] in ("green", "red", "brown", "blue")

