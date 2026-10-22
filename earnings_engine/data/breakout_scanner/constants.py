"""Constants, schemas, and strategy registry for Breakout Radar."""

from __future__ import annotations

import os
from typing import Any

# ---------------------------------------------------------------------------
# Configuration (overridable via environment variables)
# ---------------------------------------------------------------------------
BREAKOUT_MIN_SCORE: int = int(os.environ.get("BREAKOUT_MIN_SCORE", "40"))
BREAKOUT_MAX_CANDIDATES: int = int(os.environ.get("BREAKOUT_MAX_CANDIDATES", "100"))

# Tier thresholds (Tightened for elite momentum setups)
HOT_THRESHOLD: int = int(os.environ.get("BREAKOUT_HOT_THRESHOLD", "60"))
WARM_THRESHOLD: int = int(os.environ.get("BREAKOUT_WARM_THRESHOLD", "25"))
HOT_DEMOTION_THRESHOLD: int = int(os.environ.get("BREAKOUT_HOT_DEMOTION", "45"))
WARM_DEMOTION_THRESHOLD: int = int(os.environ.get("BREAKOUT_WARM_DEMOTION", "15"))

# Scan intervals (minutes)
COLD_INTERVAL_MIN: int = int(os.environ.get("BREAKOUT_COLD_INTERVAL_MIN", "60"))
WARM_INTERVAL_MIN: int = int(os.environ.get("BREAKOUT_WARM_INTERVAL_MIN", "15"))
HOT_INTERVAL_MIN: int = int(os.environ.get("BREAKOUT_HOT_INTERVAL_MIN", "5"))

# Legacy compat alias
BREAKOUT_SCAN_INTERVAL_MIN: int = COLD_INTERVAL_MIN

# ---------------------------------------------------------------------------
# Multi-Strategy Quantitative Models Registry
# ---------------------------------------------------------------------------
BREAKOUT_STRATEGIES: dict[str, dict[str, Any]] = {
    "CLASSIC_TECHNICAL": {
        "id": "CLASSIC_TECHNICAL",
        "name": "⚡ Classic Technical Coiling",
        "short_name": "Classic Technical",
        "badge": "Classic 20D/52W Coil",
        "icon": "⚡",
        "description": "52-Week & 20-Day High proximity with ATR compression coiling, volume confirmation, and fundamental quality.",
        "trigger_name": "max(20D High, 52W High)",
        "formula": "30% Resistance + 20% Volume + 15% Squeeze + 15% Momentum + 20% Quality",
        "weights": {
            "resistance": 30,
            "volume": 20,
            "compression": 15,
            "momentum": 15,
            "fundamental": 20,
        },
    },
    "NSE_DELIVERY_ABSORPTION": {
        "id": "NSE_DELIVERY_ABSORPTION",
        "name": "🏛️ NSE Institutional Delivery Breakout",
        "short_name": "NSE Delivery",
        "badge": "Bhavcopy Delivery Surge",
        "icon": "🏛️",
        "description": "Bhavcopy deliverable volume spikes (>60%) with FII/DII accumulation absorbing retail supply at resistance.",
        "trigger_name": "Delivery Resistance High (Top 3 Volume Days)",
        "formula": "35% Delivery Surge + 25% Institutional Inflows + 20% Resistance Proximity + 20% Quality",
        "weights": {
            "delivery_surge": 35,
            "institutional_inflows": 25,
            "resistance_proximity": 20,
            "fundamental": 20,
        },
    },
    "NSE_FO_CALL_WALL": {
        "id": "NSE_FO_CALL_WALL",
        "name": "🎯 NSE Option Chain & Call OI Squeeze",
        "short_name": "NSE Call OI Wall",
        "badge": "Call OI Gamma Squeeze",
        "icon": "🎯",
        "description": "Option chain Call Open Interest Wall resistance breach forcing short-call gamma unwinding.",
        "trigger_name": "Highest Call OI Strike (Call Wall)",
        "formula": "35% Call OI Wall + 25% PCR Trend + 20% Call Unwinding + 20% Trend Strength",
        "weights": {
            "call_oi_wall": 35,
            "pcr_trend": 25,
            "call_unwinding": 20,
            "trend_strength": 20,
        },
    },
    "VOLUME_PROFILE_VAH": {
        "id": "VOLUME_PROFILE_VAH",
        "name": "📊 Volume Profile & VAH Expansion",
        "short_name": "Volume Profile VAH",
        "badge": "Value Area High VAH",
        "icon": "📊",
        "description": "63-day Point of Control (POC) compression breaking above Value Area High (VAH 70% volume ceiling).",
        "trigger_name": "Value Area High (VAH)",
        "formula": "35% VAH Breakout + 30% Low Volume Node Vacuum + 20% Relative Volume + 15% Consolidation Time",
        "weights": {
            "vah_breakout": 35,
            "lvn_vacuum": 30,
            "relative_volume": 20,
            "consolidation": 15,
        },
    },
    "DONCHIAN_TTM_SQUEEZE": {
        "id": "DONCHIAN_TTM_SQUEEZE",
        "name": "🌪️ Volatility Compression & Donchian Squeeze",
        "short_name": "Donchian Squeeze",
        "badge": "TTM Squeeze + 55D Donchian",
        "icon": "🌪️",
        "description": "Bollinger Bands contracting inside Keltner Channels (TTM Squeeze) breaking 55-Day Donchian Channels.",
        "trigger_name": "55-Day Donchian Upper Channel",
        "formula": "35% TTM Squeeze Energy + 30% 55-Day Donchian Breach + 20% Momentum Oscillator + 15% Volume Surge",
        "weights": {
            "ttm_squeeze": 35,
            "donchian_breach": 30,
            "momentum_osc": 20,
            "volume_surge": 15,
        },
    },
}


def get_breakout_strategies() -> list[dict[str, Any]]:
    """Return all registered breakout strategies metadata."""
    return list(BREAKOUT_STRATEGIES.values())


# ---------------------------------------------------------------------------
# Database table column schemas
# ---------------------------------------------------------------------------
BREAKOUT_RADAR_COLS: list[str] = [
    "ticker", "strategy", "tier", "company_name", "industry", "composite_score",
    "resistance_score", "volume_score", "compression_score", "momentum_score", "fundamental_score",
    "signal_date", "signal_price", "predicted_value", "breakout_trigger", "ideal_entry_price",
    "is_late", "entry_delay_pct", "target_price", "stop_loss", "risk_reward_ratio",
    "current_price", "current_date", "realized_return_pct", "max_gain_pct", "breakout_happened",
    "outcome", "outcome_label", "outcome_badge", "days_elapsed", "setup_archetype",
    "volume_ratio", "atr_pct", "pct_from_high", "avg_quality_score", "scanned_at",
    "data_json", "updated_at",
]

BREAKOUT_TRACKED_COLS: list[str] = [
    "ticker", "strategy", "tier", "company_name", "industry", "composite_score",
    "resistance_score", "volume_score", "compression_score", "momentum_score", "fundamental_score",
    "signal_date", "signal_price", "predicted_value", "breakout_trigger", "ideal_entry_price",
    "is_late", "entry_delay_pct", "target_price", "stop_loss", "risk_reward_ratio",
    "current_price", "current_date", "realized_return_pct", "max_gain_pct", "breakout_happened",
    "outcome", "outcome_label", "outcome_badge", "days_elapsed", "setup_archetype",
    "volume_ratio", "atr_pct", "pct_from_high", "avg_quality_score", "scanned_at",
    "data_json", "created_at", "updated_at",
]

# Aliases for backward compatibility
_BREAKOUT_RADAR_COLS = BREAKOUT_RADAR_COLS
_BREAKOUT_TRACKED_COLS = BREAKOUT_TRACKED_COLS
