"""Central Provider Manager and Market Data Router.

Automatically selects the optimal provider based on:
- Asset market (Indian NSE vs US)
- Provider availability (NSE Direct / nselib / jugaad-data vs yfinance)
- Request type (single OHLCV, bulk daily Bhavcopy, live quotes, or Option Chain)
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from earnings_engine.config import Settings, market_of
from earnings_engine.data.providers.base import DataProvider
from earnings_engine.data.providers.nse_provider import NSEDirectProvider
from earnings_engine.data.providers.yfinance_provider import YFinanceProvider

logger = logging.getLogger("earnings_engine.data.providers.manager")


class DataProviderManager:
    """Manages active market data providers and routes data requests."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()
        self._providers: dict[str, DataProvider] = {
            "nse_direct": NSEDirectProvider(),
            "yfinance": YFinanceProvider(),
        }

    def get_provider(self, name: str) -> DataProvider | None:
        return self._providers.get(name)

    def fetch_ohlcv(
        self,
        ticker: str,
        start_date: str,
        end_date: str | None = None,
        interval: str = "1d",
        preferred_provider: str | None = None,
    ) -> pd.DataFrame:
        """Fetch historical OHLCV data with automatic provider fallback."""
        mkt = market_of(ticker)

        # 1. Preferred provider if specified
        if preferred_provider and preferred_provider in self._providers:
            prov = self._providers[preferred_provider]
            if prov.is_available:
                logger.info("[PROVIDER-ROUTE] Querying preferred provider '%s' for ticker=%s...", preferred_provider, ticker)
                df = prov.fetch_ohlcv(ticker, start_date, end_date, interval)
                if not df.empty:
                    logger.info("[PROVIDER-SUCCESS] Fetched %d rows from '%s' for %s", len(df), preferred_provider, ticker)
                    return df

        # 2. For Indian equities: try NSE Direct first
        if mkt == "IN":
            nse_prov = self._providers["nse_direct"]
            if nse_prov.is_available:
                logger.info("[PROVIDER-ROUTE] [NSE-Direct] Querying official NSE archives (nselib / jugaad-data) for %s...", ticker)
                df = nse_prov.fetch_ohlcv(ticker, start_date, end_date, interval)
                if not df.empty:
                    logger.info("[PROVIDER-SUCCESS] [NSE-Direct] Retrieved %d bars for %s", len(df), ticker)
                    return df
                else:
                    logger.info("[PROVIDER-FALLBACK] [NSE-Direct] returned empty for %s; falling back to yfinance", ticker)

        # 3. Fallback to yfinance
        yf_prov = self._providers["yfinance"]
        if yf_prov.is_available:
            logger.info("[PROVIDER-ROUTE] [yfinance] Querying Yahoo Finance for %s (%s to %s)...", ticker, start_date, end_date or "now")
            df = yf_prov.fetch_ohlcv(ticker, start_date, end_date, interval)
            if not df.empty:
                logger.info("[PROVIDER-SUCCESS] [yfinance] Retrieved %d bars for %s", len(df), ticker)
            return df

        logger.warning("[PROVIDER-ERROR] No available provider succeeded for ticker=%s", ticker)
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    def fetch_quote(self, ticker: str) -> dict[str, Any]:
        """Fetch latest price snapshot with fallback."""
        mkt = market_of(ticker)
        if mkt == "IN":
            nse_prov = self._providers["nse_direct"]
            if nse_prov.is_available:
                logger.info("[PROVIDER-QUOTE] [NSE-Direct] Fetching real-time quote for %s...", ticker)
                res = nse_prov.fetch_quote(ticker)
                if res.get("price") is not None:
                    return res
                logger.info("[PROVIDER-QUOTE] [NSE-Direct] Quote empty for %s, falling back to yfinance", ticker)

        yf_prov = self._providers["yfinance"]
        logger.info("[PROVIDER-QUOTE] [yfinance] Fetching quote for %s...", ticker)
        return yf_prov.fetch_quote(ticker)

    def fetch_bhavcopy(self, date_str: str) -> pd.DataFrame:
        """Fetch bulk daily bhavcopy for all NSE equities."""
        nse_prov = self._providers["nse_direct"]
        if nse_prov.is_available:
            logger.info("[PROVIDER-BHAVCOPY] [NSE-Direct] Fetching bulk daily bhavcopy for %s...", date_str)
            return nse_prov.fetch_bhavcopy(date_str)
        logger.warning("[PROVIDER-BHAVCOPY] NSE Direct provider not available for bhavcopy on %s", date_str)
        return pd.DataFrame(columns=["ticker", "open", "high", "low", "close", "volume"])

    def fetch_option_chain(self, symbol: str, expiry_date: str | None = None) -> dict[str, Any]:
        """Fetch Option Chain data for an NSE symbol or index."""
        nse_prov = self._providers["nse_direct"]
        if nse_prov.is_available:
            logger.info("[PROVIDER-OPTIONS] [NSE-Direct] Querying live Option Chain for %s (expiry=%s)...", symbol, expiry_date)
            return nse_prov.fetch_option_chain(symbol, expiry_date=expiry_date)
        logger.warning("[PROVIDER-OPTIONS] NSE Direct provider (nselib / jugaad-data) unavailable for Option Chain on %s", symbol)
        return {"symbol": symbol, "records_count": 0, "data": [], "expiries": [], "selected_expiry": None}

    def fetch_index_data(self, index_name: str, start_date: str, end_date: str | None = None) -> pd.DataFrame:
        """Fetch index history (NIFTY 50, NIFTY BANK, etc.)."""
        nse_prov = self._providers["nse_direct"]
        if nse_prov.is_available:
            df = nse_prov.fetch_index_data(index_name, start_date, end_date)
            if not df.empty:
                return df

        # Fallback to yfinance with ^ prefix (e.g. ^NSEI)
        sym_map = {
            "NIFTY 50": "^NSEI",
            "NIFTY BANK": "^NSEBANK",
            "NIFTY IT": "^CNXIT",
        }
        yf_sym = sym_map.get(index_name.upper(), index_name)
        return self._providers["yfinance"].fetch_ohlcv(yf_sym, start_date, end_date)


# Singleton accessor
_manager_instance: DataProviderManager | None = None


def get_data_manager(settings: Settings | None = None) -> DataProviderManager:
    """Get or create singleton DataProviderManager instance."""
    global _manager_instance
    if _manager_instance is None or settings is not None:
        _manager_instance = DataProviderManager(settings)
    return _manager_instance
