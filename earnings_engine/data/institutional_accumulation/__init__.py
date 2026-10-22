"""Institutional Accumulation, Fund Holdings & Smart Money Analytics Subsystem.

This package provides a clean modular decomposition of institutional accumulation,
multi-tier conviction scoring, fund-level portfolio drilldowns, period buyers inspection,
tracked radar strategy signals, and 360-degree forensic dossiers.

All public symbols are re-exported here for complete backward compatibility.
"""

from __future__ import annotations

from earnings_engine.data.db_helpers import get_ticker_variants
from earnings_engine.data.institutional_accumulation.activity import (
    get_stock_institutional_activity,
)
from earnings_engine.data.institutional_accumulation.accumulation import (
    _attach_fundamentals_and_eps,
    get_stocks_under_institutional_accumulation,
)
from earnings_engine.data.institutional_accumulation.buyers import (
    _map_buyer_macro_category,
    _normalize_query_dates,
    _parse_fiscal_quarter,
    _parse_single_query_date,
    _resolve_ticker_symbol,
    get_stock_buyers_in_period,
)
from earnings_engine.data.institutional_accumulation.cache import (
    _get_inst_cache,
    _set_inst_cache,
    clear_institutional_cache,
)
from earnings_engine.data.institutional_accumulation.constants import (
    DEFAULT_LOOKBACK_DAYS,
    MARQUEE_AMCS,
    MIN_HOLDING_VALUE_CR,
    SECTORS_MAP,
    SUPER_INVESTORS,
    _get_quarter_start_date,
    _is_marquee_amc_name,
    _is_super_investor_name,
)
from earnings_engine.data.institutional_accumulation.db import (
    _ensure_institutional_data_for_ticker,
    _recalculate_metrics_internal,
    get_institutional_db_path,
    init_institutional_db,
    recalculate_all_institutional_metrics,
)
from earnings_engine.data.institutional_accumulation.dossier import (
    get_stock_forensic_dossier,
    get_stock_quarterly_financials,
)
from earnings_engine.data.institutional_accumulation.freshness import (
    check_institutional_data_freshness,
    fetch_live_corporate_ownership,
    fetch_live_corporate_ownership_batch,
    ingest_amfi_and_nse_institutional_holdings,
)
from earnings_engine.data.nse_shareholding import get_stock_fetch_status
from earnings_engine.data.institutional_accumulation.funds import (
    get_all_funds_activity,
    get_fund_portfolio_activity,
)
from earnings_engine.data.institutional_accumulation.rankings import (
    get_top_accumulated_stocks,
    get_top_distributed_stocks,
    get_top_stake_additions,
    scan_watchlist_institutional,
)
from earnings_engine.data.institutional_accumulation.returns import (
    _fetch_price_history,
    _get_ticker_returns,
    _get_ticker_returns_batch,
)
from earnings_engine.data.institutional_accumulation.scoring import (
    _classify_market_cap,
    calculate_institutional_score,
)
from earnings_engine.data.institutional_accumulation.strategies import (
    TrackedSignalsResult,
    _get_or_create_radar_signals,
    _qualifies_block_deal_momentum,
    _qualifies_domestic_absorption,
    _qualifies_dual_acceleration,
    _qualifies_whale_conviction,
    evaluate_and_track_strategy_signals,
    get_tracked_smart_money_signals,
)

__all__ = [
    # Constants & identification
    "DEFAULT_LOOKBACK_DAYS",
    "MIN_HOLDING_VALUE_CR",
    "MARQUEE_AMCS",
    "SUPER_INVESTORS",
    "SECTORS_MAP",
    "_get_quarter_start_date",
    "_is_super_investor_name",
    "_is_marquee_amc_name",
    # Scoring
    "calculate_institutional_score",
    "_classify_market_cap",
    # Cache
    "_get_inst_cache",
    "_set_inst_cache",
    "clear_institutional_cache",
    # Database
    "get_institutional_db_path",
    "init_institutional_db",
    "recalculate_all_institutional_metrics",
    "_recalculate_metrics_internal",
    "_ensure_institutional_data_for_ticker",
    # Returns
    "_fetch_price_history",
    "_get_ticker_returns",
    "_get_ticker_returns_batch",
    # Freshness & Ingestion
    "fetch_live_corporate_ownership",
    "fetch_live_corporate_ownership_batch",
    "check_institutional_data_freshness",
    "ingest_amfi_and_nse_institutional_holdings",
    "get_stock_fetch_status",
    # Activity & Drilldown
    "get_stock_institutional_activity",
    # Rankings & Screening
    "get_top_accumulated_stocks",
    "get_top_distributed_stocks",
    "get_top_stake_additions",
    "scan_watchlist_institutional",
    # Fund directory & Portfolios
    "get_all_funds_activity",
    "get_fund_portfolio_activity",
    # Buyers inspector
    "get_stock_buyers_in_period",
    "get_ticker_variants",
    "_resolve_ticker_symbol",
    "_parse_single_query_date",
    "_parse_fiscal_quarter",
    "_normalize_query_dates",
    "_map_buyer_macro_category",
    # Accumulation Radar & EPS
    "_attach_fundamentals_and_eps",
    "get_stocks_under_institutional_accumulation",
    # Strategy signals & Lifecycle
    "TrackedSignalsResult",
    "_get_or_create_radar_signals",
    "_qualifies_whale_conviction",
    "_qualifies_block_deal_momentum",
    "_qualifies_dual_acceleration",
    "_qualifies_domestic_absorption",
    "evaluate_and_track_strategy_signals",
    "get_tracked_smart_money_signals",
    # Dossier & Quarterly financials
    "get_stock_quarterly_financials",
    "get_stock_forensic_dossier",
]
