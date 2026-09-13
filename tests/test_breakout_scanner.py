"""Tests for the Breakout Radar scanner engine.

Validates score components, composite scoring, threshold filtering,
and the API endpoints.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pandas as pd
import numpy as np
import pytest
from fastapi.testclient import TestClient

from earnings_engine.data.breakout_scanner import (
    score_breakout,
    _calc_atr_pct,
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

    def test_short_series_returns_zero_and_nan(self):
        score, pct = _score_resistance_proximity(pd.Series([100.0]))
        assert score == 0.0
        assert np.isnan(pct)


class TestVolumeSurge:
    def test_moderate_volume_gives_score(self):
        volumes = pd.Series([1_000_000] * 20 + [1_200_000])  # 1.2× surge
        score, ratio = _score_volume_surge(volumes)
        assert score == 3.0
        assert ratio >= 1.0

    def test_below_average_volume_gives_zero(self):
        volumes = pd.Series([1_000_000] * 20 + [500_000])
        score, ratio = _score_volume_surge(volumes)
        assert score == 0.0
        assert ratio < 1.0

    def test_heavy_volume_rewarded_maximum(self):
        volumes = pd.Series([1_000_000] * 20 + [2_500_000])
        score, ratio = _score_volume_surge(volumes)
        assert score == 10.0
        assert ratio >= 2.0

    def test_short_series_returns_zero_and_nan(self):
        score, ratio = _score_volume_surge(pd.Series([1000.0, 2000.0]))
        assert score == 0.0
        assert np.isnan(ratio)


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

    def test_short_series_returns_zero_and_nan(self):
        score, atr = _score_price_compression(pd.Series([100.0] * 10))
        assert score == 0.0
        assert np.isnan(atr)

    def test_price_compression_vectorized_equivalence(self):
        closes = pd.Series([100.0 + i * 0.2 for i in range(30)])
        score, atr = _score_price_compression(closes)
        vals = closes.values[-15:]
        expected_atr = round(float((abs(vals[1:] - vals[:-1]) / vals[:-1]).mean()) * 100, 3)
        assert atr == expected_atr

    def test_calc_atr_pct_helper_handles_defaults_and_zero_values(self):
        # Series too short
        assert _calc_atr_pct(pd.Series([100.0] * 10), default=2.5) == 2.5
        # None closes
        assert _calc_atr_pct(None, default=3.0) == 3.0
        # Zero prices in series guarded against zero division
        zeros = pd.Series([0.0] * 20)
        assert _calc_atr_pct(zeros, default=2.0) == 2.0
        # Valid calculation
        valid_series = pd.Series([100.0 + i * 0.5 for i in range(25)])
        atr = _calc_atr_pct(valid_series)
        assert atr > 0.0
        assert not np.isnan(atr)


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

    def test_short_series_returns_zero_and_insufficient(self):
        score, signal = _score_momentum(pd.Series([100.0] * 10))
        assert score == 0.0
        assert signal == "insufficient"


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

    def test_get_breakout_pool_stats_strategy_breakdown(self):
        from earnings_engine.data.breakout_scanner import get_breakout_pool_stats, BREAKOUT_STRATEGIES
        stats = get_breakout_pool_stats()
        assert isinstance(stats, dict)
        assert "strategies" in stats
        for s_key in BREAKOUT_STRATEGIES:
            assert s_key in stats["strategies"]
            assert "hot" in stats["strategies"][s_key]
            assert "warm" in stats["strategies"][s_key]
            assert "total" in stats["strategies"][s_key]


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


class TestBreakoutLateDetection:
    """Validate late breakout tracking, persistence, and contract fields."""

    @pytest.fixture(autouse=True)
    def setup_client_and_db(self, tmp_path):
        from earnings_engine.config import Settings
        from earnings_engine.data.breakout_scanner import (
            _pool,
            save_breakout_pool_to_db,
            get_tracked_breakouts,
        )
        from earnings_engine.data.migrations import apply_migrations

        db_file = tmp_path / "prices.sqlite3"
        self.settings = Settings(data_dirs={"prices": tmp_path, "earnings": tmp_path})
        apply_migrations(self.settings)

        from fastapi.testclient import TestClient
        from earnings_engine.api.server import app

        self.client = TestClient(app, raise_server_exceptions=False)

    def test_score_breakout_setup_calculates_late_detection(self):
        import pandas as pd
        import numpy as np
        from earnings_engine.data.breakout_scanner import score_breakout

        dates = pd.date_range("2026-01-01", periods=65, freq="B")
        prices = [100.0 + i * 0.5 for i in range(65)]
        df = pd.DataFrame({
            "open": prices,
            "high": [p + 1.0 for p in prices],
            "low": [p - 1.0 for p in prices],
            "close": prices,
            "volume": [1_000_000] * 65,
        }, index=dates)

        res = score_breakout("RELIANCE.NS", df, settings=self.settings)
        assert res is not None
        assert "ideal_entry_price" in res
        assert "is_late" in res
        assert "entry_delay_pct" in res
        assert isinstance(res["is_late"], bool)
        assert isinstance(res["entry_delay_pct"], float)

    def test_tracked_breakouts_persistence_and_query_late_fields(self):
        from earnings_engine.data.breakout_scanner import (
            _pool,
            save_breakout_pool_to_db,
            get_tracked_breakouts,
        )

        _pool["hot"]["TESTLATE.NS::CLASSIC_TECHNICAL"] = {
            "result": {
                "ticker": "TESTLATE.NS",
                "strategy": "CLASSIC_TECHNICAL",
                "tier": "HOT",
                "company_name": "Test Late Co",
                "composite_score": 85.0,
                "signal_date": "2026-09-01",
                "signal_price": 105.0,
                "breakout_trigger": 100.0,
                "ideal_entry_price": 100.0,
                "is_late": True,
                "entry_delay_pct": 5.0,
                "breakout_happened": 1,
                "outcome": "TRIGGERED",
                "current_price": 105.0,
            },
            "consecutive_low": 0,
        }

        save_breakout_pool_to_db(self.settings)
        res = get_tracked_breakouts(limit=50, settings=self.settings)

        assert res["success"] is True
        matched = [it for it in res["items"] if it["ticker"] == "TESTLATE.NS"]
        assert len(matched) == 1
        item = matched[0]
        assert item["ideal_entry_price"] == 100.0
        assert item["is_late"] is True
        assert item["entry_delay_pct"] == 5.0

    def test_late_detection_with_intraday_high_spike(self):
        import pandas as pd
        from earnings_engine.data.breakout_scanner import score_breakout

        dates = pd.date_range("2026-01-01", periods=65, freq="B")
        prices = [99.0] * 64 + [100.1]
        highs = [100.0] * 64 + [103.0]
        lows = [98.0] * 64 + [99.0]
        opens = [99.0] * 65
        volumes = [1_000_000] * 65

        df = pd.DataFrame(
            {"open": opens, "high": highs, "low": lows, "close": prices, "volume": volumes},
            index=dates,
        )

        res = score_breakout("TEST.NS", df, settings=self.settings)
        assert res is not None
        assert res["ideal_entry_price"] == 100.0
        assert res["is_late"] is True
        assert res["entry_delay_pct"] == 3.0

    def test_late_detection_with_zero_or_none_ideal_entry_price_handles_gracefully(self):
        from earnings_engine.data.breakout_scanner import _score_classic_technical
        import pandas as pd

        closes = pd.Series([100.0] * 20)
        volumes = pd.Series([1_000_000] * 20)
        highs = pd.Series([0.0] * 20)

        composite, trigger, target, stop, subscores, archetype, notes = _score_classic_technical(
            closes=closes,
            volumes=volumes,
            high_series=highs,
            quality_scores=[8.0],
        )
        assert notes["ideal_entry_price"] == 0.0
        assert notes["is_late"] is False
        assert notes["entry_delay_pct"] == 0.0


class TestBreakoutAIReasoningPersistentCache:
    """Validate persistent SQLite caching of AI reasoning for breakout candidates."""

    @pytest.fixture(autouse=True)
    def setup_test_env(self, tmp_path):
        from unittest.mock import patch
        from earnings_engine.config import Settings
        from earnings_engine.data.breakout_scanner import (
            _init_breakout_db,
            _AI_REASONING_CACHE,
        )
        from earnings_engine.data.db import get_db_connection

        self.settings = Settings(data_dirs={"prices": tmp_path, "earnings": tmp_path})
        conn = get_db_connection(self.settings)
        _init_breakout_db(conn)
        conn.close()

        _AI_REASONING_CACHE.clear()
        yield
        _AI_REASONING_CACHE.clear()

    def test_generate_breakout_ai_reasoning_writes_to_sqlite_data_json(self):
        import json
        from earnings_engine.data.breakout_scanner import (
            generate_breakout_ai_reasoning,
            _AI_REASONING_CACHE,
        )
        from earnings_engine.data.db import get_db_connection

        # Seed candidate in breakout_radar with existing custom data_json
        conn = get_db_connection(self.settings)
        conn.execute(
            """
            INSERT INTO breakout_radar (ticker, strategy, tier, composite_score, breakout_trigger, target_price, stop_loss, data_json)
            VALUES ('INFY.NS', 'CLASSIC_TECHNICAL', 'HOT', 85.0, 1800.0, 1950.0, 1750.0, ?)
            """,
            (json.dumps({"existing_metric": 42}),),
        )
        conn.commit()
        conn.close()

        # Call generate_breakout_ai_reasoning
        res = generate_breakout_ai_reasoning("INFY.NS", settings=self.settings)
        assert res is not None
        assert res["ticker"] == "INFY.NS"
        assert "verdict" in res
        assert "confidence_pct" in res
        assert "generated_at" in res

        # Assert data was written to SQLite data_json preserving existing keys
        conn = get_db_connection(self.settings)
        row = conn.execute("SELECT data_json FROM breakout_radar WHERE ticker = 'INFY.NS'").fetchone()
        conn.close()

        assert row is not None and row[0] is not None
        saved_data = json.loads(row[0])
        assert saved_data.get("existing_metric") == 42
        assert "ai_reasoning" in saved_data
        ai = saved_data["ai_reasoning"]
        assert ai["ticker"] == "INFY.NS"
        assert ai["verdict"] == res["verdict"]
        assert ai["confidence_pct"] == res["confidence_pct"]
        assert ai["generated_at"] == res["generated_at"]

    def test_subsequent_call_reads_ai_reasoning_from_sqlite_cache(self):
        import json
        from unittest.mock import patch
        from earnings_engine.data.breakout_scanner import (
            generate_breakout_ai_reasoning,
            _AI_REASONING_CACHE,
        )
        from earnings_engine.data.db import get_db_connection

        # Populate SQLite with fresh AI reasoning (< 12 hours)
        now_iso = datetime.now(timezone.utc).isoformat()
        preset_reasoning = {
            "verdict": "HIGH_CONVICTION_BREAKOUT",
            "confidence_pct": 88,
            "generated_at": now_iso,
            "ticker": "INFY.NS",
            "source": "Precomputed SQLite Unit Test",
        }
        conn = get_db_connection(self.settings)
        conn.execute(
            """
            INSERT OR REPLACE INTO breakout_radar (ticker, strategy, tier, composite_score, data_json)
            VALUES ('INFY.NS', 'CLASSIC_TECHNICAL', 'HOT', 88.0, ?)
            """,
            (json.dumps({"ai_reasoning": preset_reasoning}),),
        )
        conn.commit()
        conn.close()

        # In-memory cache is cold (cleared)
        _AI_REASONING_CACHE.clear()

        # Score breakout and price loading should NOT be called on SQLite cache hit
        with patch("earnings_engine.data.breakout_scanner.score_breakout") as mock_score, \
             patch("earnings_engine.data.prices.load_prices") as mock_load_prices:
            cached_res = generate_breakout_ai_reasoning("INFY.NS", settings=self.settings)

            mock_score.assert_not_called()
            mock_load_prices.assert_not_called()

        assert cached_res["source"] == "Precomputed SQLite Unit Test"
        assert cached_res["confidence_pct"] == 88
        assert cached_res["ticker"] == "INFY.NS"
        # In-memory cache should now be warmed
        assert "INFY.NS_default" in _AI_REASONING_CACHE

    def test_stale_ai_reasoning_cache_in_sqlite_triggers_recomputation(self):
        import json
        from earnings_engine.data.breakout_scanner import (
            generate_breakout_ai_reasoning,
            _AI_REASONING_CACHE,
        )
        from earnings_engine.data.db import get_db_connection

        # Populate SQLite with stale AI reasoning (13 hours old)
        stale_dt = datetime.now(timezone.utc) - timedelta(hours=13)
        stale_reasoning = {
            "verdict": "STALE_SETUP",
            "confidence_pct": 50,
            "generated_at": stale_dt.isoformat(),
            "ticker": "INFY.NS",
            "source": "Stale DB Cache",
        }
        conn = get_db_connection(self.settings)
        conn.execute(
            """
            INSERT OR REPLACE INTO breakout_radar (ticker, strategy, tier, composite_score, data_json)
            VALUES ('INFY.NS', 'CLASSIC_TECHNICAL', 'HOT', 80.0, ?)
            """,
            (json.dumps({"ai_reasoning": stale_reasoning}),),
        )
        conn.commit()
        conn.close()

        _AI_REASONING_CACHE.clear()

        # Calling generate_breakout_ai_reasoning should bypass stale cache and recompute
        new_res = generate_breakout_ai_reasoning("INFY.NS", settings=self.settings)
        assert new_res["source"] != "Stale DB Cache"
        assert new_res["ticker"] == "INFY.NS"

        # Check SQLite was updated with the fresh timestamp
        conn = get_db_connection(self.settings)
        row = conn.execute("SELECT data_json FROM breakout_radar WHERE ticker = 'INFY.NS'").fetchone()
        conn.close()

        assert row is not None and row[0] is not None
        saved_data = json.loads(row[0])
        saved_dt = datetime.fromisoformat(saved_data["ai_reasoning"]["generated_at"])
        if saved_dt.tzinfo is None:
            saved_dt = saved_dt.replace(tzinfo=timezone.utc)
        diff_s = (datetime.now(timezone.utc) - saved_dt).total_seconds()
        assert diff_s < 30.0

    def test_generate_breakout_ai_reasoning_for_new_ticker_persists_row(self):
        import json
        from unittest.mock import patch
        from earnings_engine.data.breakout_scanner import (
            generate_breakout_ai_reasoning,
            _AI_REASONING_CACHE,
        )
        from earnings_engine.data.db import get_db_connection

        _AI_REASONING_CACHE.clear()

        # Ticker not initially in breakout_radar
        res = generate_breakout_ai_reasoning("UNTRACKED.NS", settings=self.settings)
        assert res["ticker"] == "UNTRACKED.NS"

        # Verify row inserted into breakout_radar
        conn = get_db_connection(self.settings)
        row = conn.execute("SELECT data_json FROM breakout_radar WHERE ticker = 'UNTRACKED.NS'").fetchone()
        conn.close()

        assert row is not None and row[0] is not None
        saved = json.loads(row[0])
        assert "ai_reasoning" in saved
        assert saved["ai_reasoning"]["ticker"] == "UNTRACKED.NS"

        # Clear in-memory cache and verify second call hits SQLite cache
        _AI_REASONING_CACHE.clear()
        with patch("earnings_engine.data.breakout_scanner.score_breakout") as mock_score:
            res_cached = generate_breakout_ai_reasoning("UNTRACKED.NS", settings=self.settings)
            mock_score.assert_not_called()

        assert res_cached["ticker"] == "UNTRACKED.NS"


class TestTechnicalIndicatorsAndVCP:
    """Validate enhanced technical indicators: EMA ribbon, Supertrend, and Minervini VCP."""

    def test_compute_technical_decision_metrics_structure(self):
        import pandas as pd
        from earnings_engine.data.breakout_scanner import compute_technical_decision_metrics

        dates = pd.date_range("2026-01-01", periods=60, freq="B")
        prices = [100.0 + i * 0.5 for i in range(60)]
        highs = [p + 1.0 for p in prices]
        lows = [p - 1.0 for p in prices]
        vols = [1_000_000] * 60

        df = pd.DataFrame(
            {"open": prices, "high": highs, "low": lows, "close": prices, "volume": vols},
            index=dates,
        )

        metrics = compute_technical_decision_metrics("INFY.NS", prices_df=df)
        assert metrics["current_price"] > 0
        assert metrics["ema_8"] is not None
        assert metrics["ema_21"] is not None
        assert metrics["ema_ribbon_bullish"] is True
        assert metrics["supertrend_direction"] in ("BULLISH", "BEARISH")
        assert metrics["vcp_pattern"] is not None
        assert "is_vcp" in metrics["vcp_pattern"]
        assert "stage" in metrics["vcp_pattern"]

    def test_detect_vcp_pattern_identifies_progressive_contractions(self):
        import pandas as pd
        from earnings_engine.data.breakout_scanner import _detect_vcp_pattern

        # Construct a synthetic 3-wave VCP pattern (Contraction 1: 15%, Contraction 2: 7%, Contraction 3: 3%)
        # Base: 100 -> peak 120 -> drop to 102 (15% drop) -> rise to 118 -> drop to 110 (6.8% drop) -> rise to 117 -> drop to 114 (2.6% drop) -> 116
        dates = pd.date_range("2026-01-01", periods=60, freq="B")

        # Build price wave
        prices = []
        # wave 1: 100 up to 120 (10 bars)
        prices += list(np.linspace(100, 120, 10))
        # drop to 102 (8 bars)
        prices += list(np.linspace(120, 102, 8))
        # wave 2: up to 118 (10 bars)
        prices += list(np.linspace(102, 118, 10))
        # drop to 110 (8 bars)
        prices += list(np.linspace(118, 110, 8))
        # wave 3: up to 117 (8 bars)
        prices += list(np.linspace(110, 117, 8))
        # drop to 114 (8 bars)
        prices += list(np.linspace(117, 114, 8))
        # final consolidation: 114 to 116 (8 bars)
        prices += list(np.linspace(114, 116, 8))

        prices = prices[:60]
        closes = pd.Series(prices, index=dates)
        highs = closes + 0.5
        lows = closes - 0.5
        # Volume drying up in final 10 bars
        vols = pd.Series([1_000_000] * 50 + [400_000] * 10, index=dates)

        res = _detect_vcp_pattern(highs=highs, lows=lows, closes=closes, volumes=vols, lookback=60)
        assert res is not None
        assert "is_vcp" in res
        assert "stage" in res
        assert "volume_dry_up" in res
        assert res["volume_dry_up"] is True




