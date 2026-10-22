"""Market Pulse: Macro Market Sentiment, Institutional Cash Liquidity, Sector Heatmap,

Indices Overview, Participant Open Interest Matrix, and Algorithmic Next-Day Playbook.
"""

from __future__ import annotations

from earnings_engine.data.market_pulse.aggregation import get_market_pulse_data
from earnings_engine.data.market_pulse.constants import (
    INDICES_CONFIG,
    IST_OFFSET,
    IST_TZ,
    SECTOR_CONFIG,
    _FAILED_NSE_OI_DATES,
    _FAILED_NSE_OI_TTL,
    _INSTITUTIONAL_FLOWS_SYNC_LOCK,
    _LAST_FII_DII_SYNC_ATTEMPT,
    _LIQUIDITY_CACHE,
    _LIQUIDITY_LOCK,
    _PARTICIPANT_OI_SYNC_LOCK,
    _PULSE_CACHE_TTL,
    labels_map,
)
from earnings_engine.data.market_pulse.glossary import get_metric_glossary
from earnings_engine.data.market_pulse.indices import compute_indices_quotes
import earnings_engine.data.market_pulse.liquidity as _liquidity_mod
from earnings_engine.data.market_pulse.participant_oi import (
    _classify_oi_regime,
    compute_participant_oi_matrix,
    sync_nse_participant_oi_data,
)
from earnings_engine.data.market_pulse.playbook import compute_next_day_market_playbook
from earnings_engine.data.market_pulse.sectors import compute_sector_heatmap
from earnings_engine.data.market_pulse.sentiment import compute_market_sentiment_matrix
from earnings_engine.data.market_pulse.timing import (
    compute_fii_dii_release_schedule,
    format_iso_to_ist,
    get_expected_latest_trading_date,
    is_market_open,
)

def compute_net_cash_liquidity(*args, **kwargs):
    return _liquidity_mod.compute_net_cash_liquidity(*args, **kwargs)

def sync_real_fii_dii_cash_flows(*args, **kwargs):
    return _liquidity_mod.sync_real_fii_dii_cash_flows(*args, **kwargs)


__all__ = [
    # Constants & Configuration
    "IST_OFFSET",
    "IST_TZ",
    "INDICES_CONFIG",
    "SECTOR_CONFIG",
    "labels_map",
    "_LAST_FII_DII_SYNC_ATTEMPT",
    "_LIQUIDITY_CACHE",
    "_LIQUIDITY_LOCK",
    "_PULSE_CACHE_TTL",
    "_FAILED_NSE_OI_DATES",
    "_FAILED_NSE_OI_TTL",
    "_PARTICIPANT_OI_SYNC_LOCK",
    "_INSTITUTIONAL_FLOWS_SYNC_LOCK",
    # Timing & Market Hours
    "is_market_open",
    "format_iso_to_ist",
    "compute_fii_dii_release_schedule",
    "get_expected_latest_trading_date",
    # Sub-Engine Computations
    "compute_indices_quotes",
    "compute_sector_heatmap",
    "sync_real_fii_dii_cash_flows",
    "compute_net_cash_liquidity",
    "sync_nse_participant_oi_data",
    "_classify_oi_regime",
    "compute_participant_oi_matrix",
    "compute_market_sentiment_matrix",
    "compute_next_day_market_playbook",
    "get_metric_glossary",
    # Composed Master Aggregation
    "get_market_pulse_data",
]
