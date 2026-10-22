"""Constants, configuration, and caching infrastructure for Market Pulse."""

from __future__ import annotations

import threading
from datetime import timedelta, timezone
from typing import Any

# IST timezone: UTC+5:30
IST_OFFSET = timedelta(hours=5, minutes=30)
IST_TZ = timezone(IST_OFFSET)

# In-memory caches with thread-safe locks
_PULSE_CACHE: dict[str, Any] = {}
_PULSE_CACHE_TTL: float = 60.0
_PULSE_LOCK = threading.Lock()

_INDICES_CACHE: dict[str, Any] = {}
_INDICES_CACHE_TTL: float = 30.0
_INDICES_LOCK = threading.Lock()

_SECTORS_CACHE: dict[str, Any] = {}
_SECTORS_CACHE_TTL: float = 30.0
_SECTORS_LOCK = threading.Lock()

_LIQUIDITY_CACHE: dict[str, Any] = {}
_LIQUIDITY_CACHE_TTL: float = 60.0
_LIQUIDITY_LOCK = threading.Lock()

_SENTIMENT_CACHE: dict[str, Any] = {}
_SENTIMENT_CACHE_TTL: float = 30.0
_SENTIMENT_LOCK = threading.Lock()

_PARTICIPANT_OI_CACHE: dict[str, Any] = {}
_PARTICIPANT_OI_CACHE_TTL: float = 120.0
_PARTICIPANT_OI_LOCK = threading.Lock()

_LAST_FII_DII_SYNC_ATTEMPT: float = 0.0
_FAILED_NSE_OI_DATES: dict[str, float] = {}
_FAILED_NSE_OI_TTL: float = 1800.0  # 30 min negative cache cooldown
_PARTICIPANT_OI_SYNC_LOCK = threading.Lock()
_INSTITUTIONAL_FLOWS_SYNC_LOCK = threading.Lock()

# ---------------------------------------------------------------------------
# Authoritative Index Definitions
# ---------------------------------------------------------------------------

INDICES_CONFIG: list[dict[str, Any]] = [
    {"symbol": "^NSEI", "name": "NIFTY 50", "category": "Benchmark", "type": "broad", "weight": 0.40, "base": 24850.0},
    {"symbol": "^NSEBANK", "name": "BANK NIFTY", "category": "Banking", "type": "sector", "weight": 0.25, "base": 53200.0},
    {"symbol": "^INDIAVIX", "name": "INDIA VIX", "category": "Volatility", "type": "volatility", "weight": 0.0, "base": 13.8},
    {"symbol": "^CNXIT", "name": "NIFTY IT", "category": "Technology", "type": "sector", "weight": 0.15, "base": 41500.0},
    {"symbol": "^CNXAUTO", "name": "NIFTY AUTO", "category": "Automobiles", "type": "sector", "weight": 0.05, "base": 25400.0},
    {"symbol": "^CNXPHARMA", "name": "NIFTY PHARMA", "category": "Healthcare", "type": "sector", "weight": 0.05, "base": 21800.0},
    {"symbol": "^CNXMETAL", "name": "NIFTY METAL", "category": "Metals & Mining", "type": "sector", "weight": 0.05, "base": 9200.0},
    {"symbol": "^CNXFMCG", "name": "NIFTY FMCG", "category": "Consumer", "type": "sector", "weight": 0.05, "base": 57800.0},
    {"symbol": "^CNXENERGY", "name": "NIFTY ENERGY", "category": "Energy", "type": "sector", "weight": 0.05, "base": 39500.0},
    {"symbol": "^CNXREALTY", "name": "NIFTY REALTY", "category": "Real Estate", "type": "sector", "weight": 0.05, "base": 1050.0},
    {"symbol": "^CNXPSUBANK", "name": "NIFTY PSU BANK", "category": "PSU Banking", "type": "sector", "weight": 0.05, "base": 6800.0},
    {"symbol": "^CNXMEDIA", "name": "NIFTY MEDIA", "category": "Media", "type": "sector", "weight": 0.02, "base": 1950.0},
    {"symbol": "^CNXSC", "name": "NIFTY SMALLCAP", "category": "Broad Market", "type": "broad", "weight": 0.10, "base": 18900.0},
    {"symbol": "^GSPC", "name": "S&P 500", "category": "US Benchmark", "type": "global", "weight": 0.0, "base": 5850.0},
]

# ---------------------------------------------------------------------------
# Authoritative Sector Heatmap Configurations
# ---------------------------------------------------------------------------

SECTOR_CONFIG: list[dict[str, Any]] = [
    {
        "name": "Nifty IT",
        "index_symbol": "^CNXIT",
        "alt_symbols": ["NIFTYIT.NS", "^NSEIT"],
        "basket": ["TCS.NS", "INFY.NS", "HCLTECH.NS", "WIPRO.NS", "TECHM.NS", "LTIM.NS"],
        "constituents": ["TCS.NS", "INFY.NS", "HCLTECH.NS", "WIPRO.NS", "TECHM.NS", "LTIM.NS"],
        "color": "cyan",
    },
    {
        "name": "Nifty Bank",
        "index_symbol": "^NSEBANK",
        "alt_symbols": ["BANKNIFTY.NS", "^BANKNIFTY"],
        "basket": ["HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS", "KOTAKBANK.NS", "AXISBANK.NS"],
        "constituents": ["HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS", "KOTAKBANK.NS", "AXISBANK.NS"],
        "color": "indigo",
    },
    {
        "name": "Nifty Auto",
        "index_symbol": "^CNXAUTO",
        "alt_symbols": ["NIFTYAUTO.NS"],
        "basket": ["TATAMOTORS.NS", "MARUTI.NS", "M&M.NS", "BAJAJ-AUTO.NS", "HEROMOTOCO.NS"],
        "constituents": ["TATAMOTORS.NS", "MARUTI.NS", "M&M.NS", "BAJAJ-AUTO.NS", "HEROMOTOCO.NS"],
        "color": "amber",
    },
    {
        "name": "Nifty Pharma",
        "index_symbol": "^CNXPHARMA",
        "alt_symbols": ["NIFTYPHARMA.NS"],
        "basket": ["SUNPHARMA.NS", "CIPLA.NS", "DRREDDY.NS", "DIVISLAB.NS", "APOLLOHOSP.NS"],
        "constituents": ["SUNPHARMA.NS", "CIPLA.NS", "DRREDDY.NS", "DIVISLAB.NS", "APOLLOHOSP.NS"],
        "color": "emerald",
    },
    {
        "name": "Nifty FMCG",
        "index_symbol": "^CNXFMCG",
        "alt_symbols": ["NIFTYFMCG.NS"],
        "basket": ["HINDUNILVR.NS", "ITC.NS", "NESTLEIND.NS", "BRITANNIA.NS", "TATACONSUM.NS"],
        "constituents": ["HINDUNILVR.NS", "ITC.NS", "NESTLEIND.NS", "BRITANNIA.NS", "TATACONSUM.NS"],
        "color": "rose",
    },
    {
        "name": "Nifty Metal",
        "index_symbol": "^CNXMETAL",
        "alt_symbols": ["NIFTYMETAL.NS"],
        "basket": ["TATASTEEL.NS", "JSWSTEEL.NS", "HINDALCO.NS", "VEDL.NS", "COALINDIA.NS"],
        "constituents": ["TATASTEEL.NS", "JSWSTEEL.NS", "HINDALCO.NS", "VEDL.NS", "COALINDIA.NS"],
        "color": "orange",
    },
    {
        "name": "Nifty Energy",
        "index_symbol": "^CNXENERGY",
        "alt_symbols": ["NIFTYENERGY.NS"],
        "basket": ["RELIANCE.NS", "NTPC.NS", "ONGC.NS", "POWERGRID.NS", "BPCL.NS"],
        "constituents": ["RELIANCE.NS", "NTPC.NS", "ONGC.NS", "POWERGRID.NS", "BPCL.NS"],
        "color": "yellow",
    },
    {
        "name": "Nifty Realty",
        "index_symbol": "^CNXREALTY",
        "alt_symbols": ["NIFTYREALTY.NS"],
        "basket": ["DLF.NS", "GODREJPROP.NS", "OBEROIRLTY.NS", "PHOENIXLTD.NS"],
        "constituents": ["DLF.NS", "GODREJPROP.NS", "OBEROIRLTY.NS", "PHOENIXLTD.NS"],
        "color": "violet",
    },
    {
        "name": "Nifty PSU Bank",
        "index_symbol": "^CNXPSUBANK",
        "alt_symbols": ["NIFTYPSUBANK.NS"],
        "basket": ["SBIN.NS", "BANKBARODA.NS", "PNB.NS", "CANBK.NS", "UNIONBANK.NS"],
        "constituents": ["SBIN.NS", "BANKBARODA.NS", "PNB.NS", "CANBK.NS", "UNIONBANK.NS"],
        "color": "blue",
    },
    {
        "name": "Nifty Media",
        "index_symbol": "^CNXMEDIA",
        "alt_symbols": ["NIFTY_MEDIA.NS"],
        "basket": ["ZEEL.NS", "SUNTV.NS", "PVRINOX.NS", "NETWORK18.NS", "NAZARA.NS"],
        "constituents": ["ZEEL.NS", "SUNTV.NS", "PVRINOX.NS", "NETWORK18.NS", "NAZARA.NS"],
        "color": "purple",
    },
]

# Labels mapping for UI participant categories
labels_map = {
    "FII": "🏛️ Foreign Institutions (FII / FPI)",
    "DII": "🏢 Domestic Institutions (DII / MF)",
    "PRO": "⚡ Proprietary Desks (Algo / MM)",
    "CLIENT": "👤 Retail Investors & HNIs",
}
