"""Unit and Integration Tests for Universal Hot / Warm / Cold Tier & Pool Management Plugin."""
from __future__ import annotations

import os
import sqlite3
from typing import Any
import pytest

from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection
from earnings_engine.data.migrations import apply_migrations, reset_migration_cache
from earnings_engine.data.tier_pools import (
    TierPoolConfig,
    TierPoolManager,
    PoolEntry,
)


@pytest.fixture
def test_settings(tmp_path) -> Settings:
    """Create isolated test settings pointing to temporary database path."""
    db_file = tmp_path / "test_tiers.sqlite3"
    s = Settings()
    s.data_dirs["prices"] = tmp_path
    os.environ["EARNINGS_ENGINE_DB_NAME"] = "test_tiers.sqlite3"

    # Reset cache and run migrations on the fresh isolated database
    reset_migration_cache()
    apply_migrations(s, force=True)

    return s


def test_tier_pool_config_defaults():
    """Verify default configuration thresholds and parameters."""
    cfg = TierPoolConfig(domain="test_domain")
    assert cfg.domain == "test_domain"
    assert cfg.hot_threshold == 60.0
    assert cfg.warm_threshold == 25.0
    assert cfg.hot_demotion_threshold == 45.0
    assert cfg.warm_demotion_threshold == 15.0
    assert cfg.demotion_strikes == 2
    assert cfg.audit_table_name == "strategy_tier_audit_log"


def test_tier_evaluation_and_promotion(test_settings: Settings):
    """Verify state machine promotion transitions from Cold to Warm to Hot."""
    cfg = TierPoolConfig(
        domain="breakout_test",
        hot_threshold=60.0,
        warm_threshold=25.0,
    )
    mgr = TierPoolManager(cfg)

    # 1. Cold Candidate (< 25)
    cand_cold = {"ticker": "COLD1.NS", "strategy": "CLASSIC", "composite_score": 18.5, "current_price": 100.0}
    tier = mgr.evaluate_tier(cand_cold)
    assert tier == "COLD"
    res = mgr.promote_or_update(cand_cold, settings=test_settings)
    assert res == "COLD"

    # 2. Warm Candidate (25 <= score < 60)
    cand_warm = {"ticker": "WARM1.NS", "strategy": "CLASSIC", "composite_score": 35.0, "current_price": 200.0}
    tier = mgr.evaluate_tier(cand_warm)
    assert tier == "WARM"
    res = mgr.promote_or_update(cand_warm, settings=test_settings)
    assert res == "WARM"
    assert "WARM1.NS::CLASSIC" in mgr._pool["warm"]

    # 3. Hot Candidate (>= 60)
    cand_hot = {"ticker": "HOT1.NS", "strategy": "CLASSIC", "composite_score": 75.0, "current_price": 500.0}
    tier = mgr.evaluate_tier(cand_hot)
    assert tier == "HOT"
    res = mgr.promote_or_update(cand_hot, settings=test_settings)
    assert res == "HOT"
    assert "HOT1.NS::CLASSIC" in mgr._pool["hot"]
    assert "HOT1.NS::CLASSIC" not in mgr._pool["warm"]

    # 4. Check Pool Stats
    stats = mgr.get_pool_stats(settings=test_settings)
    assert stats["hot_count"] == 1
    assert stats["warm_count"] == 1
    assert stats["total_count"] == 2


def test_two_strike_hysteresis_demotion(test_settings: Settings):
    """Verify 2-strike hysteresis demotion and strike reset mechanics."""
    cfg = TierPoolConfig(
        domain="swing_test",
        hot_threshold=50.0,
        warm_threshold=25.0,
        hot_demotion_threshold=35.0,
        warm_demotion_threshold=15.0,
        demotion_strikes=2,
    )
    mgr = TierPoolManager(cfg)

    # Promote to HOT initially
    cand = {"ticker": "SWING1.NS", "strategy": "SUPPORT_BOUNCE", "composite_score": 65.0, "current_price": 300.0}
    mgr.promote_or_update(cand, settings=test_settings)
    key = "SWING1.NS::SUPPORT_BOUNCE"
    assert key in mgr._pool["hot"]

    # Strike 1: Score drops below hot_demotion_threshold (30.0 < 35.0)
    updated_1 = {"ticker": "SWING1.NS", "strategy": "SUPPORT_BOUNCE", "composite_score": 30.0, "current_price": 295.0}
    tier_1 = mgr.check_hot_demotion(key, updated_1, settings=test_settings)
    assert tier_1 == "HOT"  # Retained in HOT due to 1st strike
    assert mgr._pool["hot"][key].consecutive_low == 1

    # Strike 2: Score drops again -> Triggers demotion to WARM
    updated_2 = {"ticker": "SWING1.NS", "strategy": "SUPPORT_BOUNCE", "composite_score": 28.0, "current_price": 290.0}
    tier_2 = mgr.check_hot_demotion(key, updated_2, settings=test_settings)
    assert tier_2 == "WARM"  # Demoted to WARM
    assert key not in mgr._pool["hot"]
    assert key in mgr._pool["warm"]
    assert mgr._pool["warm"][key].consecutive_low == 0  # Reset for warm tier

    # Demote from WARM to COLD (2 strikes below warm_demotion_threshold 15.0)
    low_warm_1 = {"ticker": "SWING1.NS", "strategy": "SUPPORT_BOUNCE", "composite_score": 10.0, "current_price": 280.0}
    w_tier_1 = mgr.check_warm_demotion(key, low_warm_1, settings=test_settings)
    assert w_tier_1 == "WARM"
    assert mgr._pool["warm"][key].consecutive_low == 1

    low_warm_2 = {"ticker": "SWING1.NS", "strategy": "SUPPORT_BOUNCE", "composite_score": 8.0, "current_price": 275.0}
    w_tier_2 = mgr.check_warm_demotion(key, low_warm_2, settings=test_settings)
    assert w_tier_2 == "COLD"
    assert key not in mgr._pool["warm"]
    assert key not in mgr._pool["hot"]


def test_audit_log_counter_deduplication(test_settings: Settings):
    """Verify that identical consecutive state transitions increment the counter rather than inserting duplicate rows."""
    cfg = TierPoolConfig(domain="audit_test", audit_table_name="strategy_tier_audit_log")
    mgr = TierPoolManager(cfg)

    # 1st Transition
    mgr.record_transition(
        ticker="TATAMOTORS.NS",
        event_type="PROMOTED_HOT",
        from_tier="WARM",
        to_tier="HOT",
        score_after=82.5,
        price=950.0,
        strategy="MOMENTUM",
        settings=test_settings,
    )

    # 2nd Transition (identical event, score slightly updated)
    mgr.record_transition(
        ticker="TATAMOTORS.NS",
        event_type="PROMOTED_HOT",
        from_tier="WARM",
        to_tier="HOT",
        score_after=85.0,
        price=955.0,
        strategy="MOMENTUM",
        settings=test_settings,
    )

    # Verify audit log query
    log_data = mgr.get_audit_log(ticker="TATAMOTORS.NS", settings=test_settings)
    entries = log_data.get("logs", [])
    assert len(entries) == 1
    assert entries[0]["ticker"] == "TATAMOTORS.NS"
    assert entries[0]["counter"] == 2
    assert entries[0]["score_after"] == 85.0
    assert entries[0]["price"] == 955.0


def test_custom_fast_track_qualifiers_and_demotion_guards(test_settings: Settings):
    """Verify custom hooks for instant fast-track promotion and demotion protection."""
    # Fast-track hook: if volume_ratio > 3.0, fast track to HOT even if score < 60
    def custom_hot(cand: dict[str, Any]) -> bool:
        return float(cand.get("volume_ratio", 0) or 0) >= 3.0

    # Guard hook: do not demote if dist_to_support_pct <= 2.0
    def custom_guard(cand: dict[str, Any]) -> bool:
        return float(cand.get("dist_to_support_pct", 10.0) or 10.0) <= 2.0

    cfg = TierPoolConfig(
        domain="custom_hooks_test",
        hot_threshold=60.0,
        custom_hot_qualifier=custom_hot,
        custom_hot_demotion_guard=custom_guard,
    )
    mgr = TierPoolManager(cfg)

    # Candidate with low score (40.0) but massive volume surge (4.5x)
    cand_fast = {
        "ticker": "FAST1.NS",
        "strategy": "VOL_SPIKE",
        "composite_score": 40.0,
        "volume_ratio": 4.5,
        "current_price": 150.0,
    }
    tier = mgr.evaluate_tier(cand_fast)
    assert tier == "HOT"
    mgr.promote_or_update(cand_fast, settings=test_settings)
    key = "FAST1.NS::VOL_SPIKE"
    assert key in mgr._pool["hot"]

    # Try demoting candidate with low score but protected by support guard
    updated_low = {
        "ticker": "FAST1.NS",
        "strategy": "VOL_SPIKE",
        "composite_score": 20.0,
        "dist_to_support_pct": 1.2,  # Guarded!
        "current_price": 148.0,
    }
    tier_demote = mgr.check_hot_demotion(key, updated_low, settings=test_settings)
    assert tier_demote == "HOT"
    assert mgr._pool["hot"][key].consecutive_low == 0  # Guard prevented strike accumulation
