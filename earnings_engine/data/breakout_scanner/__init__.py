"""Breakout Scanner Package Facade.

Re-exports all constants, state containers, indicators, quantitative strategies,
order flow analytics, composite scoring, database storage, and pipeline execution.
"""

from __future__ import annotations

# 1. Constants & Configuration
from earnings_engine.data.breakout_scanner.constants import (
    BREAKOUT_MIN_SCORE,
    BREAKOUT_MAX_CANDIDATES,
    HOT_THRESHOLD,
    WARM_THRESHOLD,
    HOT_DEMOTION_THRESHOLD,
    WARM_DEMOTION_THRESHOLD,
    COLD_INTERVAL_MIN,
    WARM_INTERVAL_MIN,
    HOT_INTERVAL_MIN,
    BREAKOUT_SCAN_INTERVAL_MIN,
    BREAKOUT_STRATEGIES,
    get_breakout_strategies,
    BREAKOUT_RADAR_COLS,
    BREAKOUT_TRACKED_COLS,
    _BREAKOUT_RADAR_COLS,
    _BREAKOUT_TRACKED_COLS,
)

# 2. State & Pool
from earnings_engine.data.breakout_scanner.state import (
    _pool,
    _cache,
    _pool_key,
    _rebuild_candidates,
    _AI_REASONING_CACHE,
)

# 3. Indicators
from earnings_engine.data.breakout_scanner.indicators import (
    _score_resistance_proximity,
    _score_volume_surge,
    _calc_atr_pct,
    _score_price_compression,
    _score_momentum,
    _score_fundamental,
    _calculate_volume_profile_detailed,
    _calculate_volume_profile,
    _calculate_donchian_ttm_squeeze,
    _detect_vcp_pattern,
    compute_technical_decision_metrics,
)

# 4. Strategies
from earnings_engine.data.breakout_scanner.strategies import (
    _score_classic_technical,
    _score_nse_delivery_absorption,
    _score_fo_call_wall,
    _score_volume_profile_vah,
    _score_donchian_squeeze,
)

# 5. Order Flow
from earnings_engine.data.breakout_scanner.order_flow import (
    get_order_flow_analytics,
)

# 6. Scoring & AI Reasoning
from earnings_engine.data.breakout_scanner.scoring import (
    _should_be_hot,
    score_breakout,
    generate_breakout_ai_reasoning,
    _score_single_ticker,
)

# 7. Storage, Audit & Outcomes
from earnings_engine.data.db import get_db_connection
from earnings_engine.data.breakout_scanner.storage import (
    _init_breakout_db,
    save_breakout_pool_to_db,
    load_breakout_pool_from_db,
    record_breakout_transition,
    get_breakout_audit_log,
    get_breakout_audit_log_count,
    get_breakout_audit_summary_stats,
    get_breakout_pool_stats,
    prune_breakout_audit_log,
    get_stock_breakout_timeline,
    _extract_strategy_id_from_setup,
    get_tracked_breakouts,
    delete_tracked_breakout,
    delete_tracked_breakouts_by_ticker,
    _promote,
    _demote_hot,
    _demote_warm,
    get_tracked_ticker_set,
    confirm_breakout_outcomes,
)

# 8. Pipeline, Scanners, Search & Backtest
from earnings_engine.data.breakout_scanner.pipeline import (
    get_cached_scan_results,
    get_scan_status,
    _resolve_universe_tickers,
    run_multi_strategy_parallel_scan,
    run_cold_scan,
    run_warm_rescore,
    run_hot_rescore,
    run_breakout_scan,
    evaluate_stock_breakout,
    set_ticker_tier,
    search_breakout_tickers,
    run_historical_backtest,
    tiered_scanner_loop,
    breakout_scanner_loop,
)

import logging
logger = logging.getLogger(__name__)

__all__ = [
    # Constants
    "BREAKOUT_MIN_SCORE",
    "BREAKOUT_MAX_CANDIDATES",
    "HOT_THRESHOLD",
    "WARM_THRESHOLD",
    "HOT_DEMOTION_THRESHOLD",
    "WARM_DEMOTION_THRESHOLD",
    "COLD_INTERVAL_MIN",
    "WARM_INTERVAL_MIN",
    "HOT_INTERVAL_MIN",
    "BREAKOUT_SCAN_INTERVAL_MIN",
    "BREAKOUT_STRATEGIES",
    "get_breakout_strategies",
    "BREAKOUT_RADAR_COLS",
    "BREAKOUT_TRACKED_COLS",
    "_BREAKOUT_RADAR_COLS",
    "_BREAKOUT_TRACKED_COLS",
    # State
    "_pool",
    "_cache",
    "_pool_key",
    "_rebuild_candidates",
    "_AI_REASONING_CACHE",
    # Indicators
    "_score_resistance_proximity",
    "_score_volume_surge",
    "_calc_atr_pct",
    "_score_price_compression",
    "_score_momentum",
    "_score_fundamental",
    "_calculate_volume_profile_detailed",
    "_calculate_volume_profile",
    "_calculate_donchian_ttm_squeeze",
    "_detect_vcp_pattern",
    "compute_technical_decision_metrics",
    # Strategies
    "_score_classic_technical",
    "_score_nse_delivery_absorption",
    "_score_fo_call_wall",
    "_score_volume_profile_vah",
    "_score_donchian_squeeze",
    # Order Flow
    "get_order_flow_analytics",
    # Scoring
    "_should_be_hot",
    "score_breakout",
    "generate_breakout_ai_reasoning",
    "_score_single_ticker",
    # Storage
    "_init_breakout_db",
    "save_breakout_pool_to_db",
    "load_breakout_pool_from_db",
    "record_breakout_transition",
    "get_breakout_audit_log",
    "get_breakout_audit_log_count",
    "get_breakout_audit_summary_stats",
    "get_breakout_pool_stats",
    "prune_breakout_audit_log",
    "get_stock_breakout_timeline",
    "_extract_strategy_id_from_setup",
    "get_tracked_breakouts",
    "delete_tracked_breakout",
    "delete_tracked_breakouts_by_ticker",
    "_promote",
    "_demote_hot",
    "_demote_warm",
    "get_tracked_ticker_set",
    "confirm_breakout_outcomes",
    # Pipeline
    "get_cached_scan_results",
    "get_scan_status",
    "_resolve_universe_tickers",
    "run_multi_strategy_parallel_scan",
    "run_cold_scan",
    "run_warm_rescore",
    "run_hot_rescore",
    "run_breakout_scan",
    "evaluate_stock_breakout",
    "set_ticker_tier",
    "search_breakout_tickers",
    "run_historical_backtest",
    "tiered_scanner_loop",
    "breakout_scanner_loop",
]
