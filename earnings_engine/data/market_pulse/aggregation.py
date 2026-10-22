"""Composed master aggregation function for Market Pulse."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

from earnings_engine.config import Settings
from earnings_engine.data.market_pulse.constants import (
    _PULSE_CACHE,
    _PULSE_CACHE_TTL,
)
from earnings_engine.data.market_pulse.glossary import get_metric_glossary
from earnings_engine.data.market_pulse.indices import compute_indices_quotes
from earnings_engine.data.market_pulse.liquidity import compute_net_cash_liquidity
from earnings_engine.data.market_pulse.participant_oi import compute_participant_oi_matrix
from earnings_engine.data.market_pulse.playbook import compute_next_day_market_playbook
from earnings_engine.data.market_pulse.sectors import compute_sector_heatmap
from earnings_engine.data.market_pulse.sentiment import compute_market_sentiment_matrix
from earnings_engine.data.market_pulse.timing import (
    get_expected_latest_trading_date,
    is_market_open,
)

logger = logging.getLogger(__name__)


def get_market_pulse_data(
    settings: Settings | None = None,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """Retrieve full macro market overview composed from modular sub-components."""
    global _PULSE_CACHE
    now_ts = time.time()

    if not force_refresh and "data" in _PULSE_CACHE:
        cached_ts = _PULSE_CACHE.get("ts", 0)
        if (now_ts - cached_ts) < _PULSE_CACHE_TTL:
            return _PULSE_CACHE["data"]
        if not is_market_open(now_ts) and not is_market_open(cached_ts):
            cached_liquidity_date = _PULSE_CACHE.get("data", {}).get("institutional_flows", {}).get("as_of_date", "")
            expected_date = get_expected_latest_trading_date()
            if (now_ts - cached_ts) < 300.0 and (not expected_date or cached_liquidity_date >= expected_date):
                return _PULSE_CACHE["data"]

    settings = settings or Settings()

    # 1. Modular Indices
    indices_data = compute_indices_quotes(settings=settings, force_refresh=force_refresh)

    # 2. Modular Sectors (Authoritative NSE Index Pricing)
    sectors = compute_sector_heatmap(settings=settings, force_refresh=force_refresh)

    # 3. Modular Net Cash Liquidity
    liquidity = compute_net_cash_liquidity(settings=settings, force_refresh=force_refresh)

    # 4. Modular Sentiment, VIX, and Breadth
    sentiment_data = compute_market_sentiment_matrix(
        settings=settings,
        indices_data=indices_data,
        force_refresh=force_refresh,
    )

    # 5. Modular Participant Derivatives OI & Long/Short Positioning Matrix
    participant_oi = compute_participant_oi_matrix(
        settings=settings,
        force_refresh=force_refresh,
    )

    # 6. Algorithmic Next-Day Actionable Market Playbook
    next_day_playbook = compute_next_day_market_playbook(
        settings=settings,
        indices_data=indices_data,
        liquidity=liquidity,
        participant_oi=participant_oi,
        sentiment_data=sentiment_data,
        sectors=sectors,
    )

    # 7. Comprehensive Metric Glossary Knowledge Base
    metric_glossary = get_metric_glossary()

    payload = {
        "success": True,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "market_status": "OPEN" if is_market_open(now_ts) else "CLOSED",
        "market_status_label": "🟢 Market Open" if is_market_open(now_ts) else "🔴 Market Closed (EOD Data)",
        "timestamps": {
            "sentiment_as_of": sentiment_data.get("as_of"),
            "sentiment_as_of_ist": sentiment_data.get("as_of_ist"),
            "session_date": sentiment_data.get("session_date"),
            "data_freshness": sentiment_data.get("data_freshness"),
            "freshness_badge": sentiment_data.get("freshness_badge"),
            "vix_as_of": sentiment_data.get("as_of"),
            "vix_as_of_ist": sentiment_data.get("as_of_ist"),
            "fii_dii_latest_arrival_ist": liquidity.get("latest_arrived_at_ist"),
            "fii_dii_next_release": liquidity.get("next_release_schedule"),
            "participant_oi_as_of": participant_oi.get("as_of_date"),
            "participant_oi_as_of_ist": participant_oi.get("as_of_ist"),
        },
        "indices": indices_data,
        "fear_greed_score": sentiment_data["fear_greed_score"],
        "fear_greed_label": sentiment_data["fear_greed_label"],
        "fear_greed_color": sentiment_data["fear_greed_color"],
        "fear_greed_desc": sentiment_data["fear_greed_desc"],
        "fear_and_greed": {
            "score": sentiment_data["fear_greed_score"],
            "label": sentiment_data["fear_greed_label"],
            "color": sentiment_data["fear_greed_color"],
            "desc": sentiment_data["fear_greed_desc"],
            "vix_factor": sentiment_data.get("sub_factors", {}).get("vix_factor", 50.0),
            "sub_factors": sentiment_data.get("sub_factors", {}),
        },
        "volatility": {
            "vix_level": sentiment_data["vix_level"],
            "regime": sentiment_data["vix_regime"],
        },
        "sub_factors": sentiment_data["sub_factors"],
        "vix_level": sentiment_data["vix_level"],
        "vix_regime": sentiment_data["vix_regime"],
        "breadth": sentiment_data["breadth"],
        "institutional_flows": liquidity,
        "liquidity": liquidity,
        "sentiment": sentiment_data,
        "playbook": next_day_playbook,
        "fii_net_cr": liquidity["fii_net_cr"],
        "dii_net_cr": liquidity["dii_net_cr"],
        "total_net_cr": liquidity["total_net_cr"],
        "fii_7d_total": liquidity["fii_7d_total"],
        "dii_7d_total": liquidity["dii_7d_total"],
        "combined_7d_total": liquidity["combined_7d_total"],
        "fii_30d_total": liquidity["fii_30d_total"],
        "dii_30d_total": liquidity["dii_30d_total"],
        "combined_30d_total": liquidity["combined_30d_total"],
        "institutional_history_7d": liquidity["history_7d"],
        "institutional_history_extended": liquidity["history_30d"],
        "sectors": sectors,
        "prediction": sentiment_data["prediction"],
        "macro_charts": sentiment_data["macro_charts"],
        "participant_oi": participant_oi,
        "next_day_playbook": next_day_playbook,
        "metric_glossary": metric_glossary,
    }

    _PULSE_CACHE = {"ts": now_ts, "data": payload}
    return payload
