"""Abstract base protocol for market data providers.

Standardizes data fetching across multiple sources:
- Direct NSE Archives (nselib, jugaad-data)
- Yahoo Finance (yfinance)
- Broker live feeds (Zerodha, Angel One, Dhan, Fyers)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

import pandas as pd


class DataProvider(ABC):
    """Abstract interface for stock market data providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider identifier."""
        pass

    @property
    @abstractmethod
    def is_available(self) -> bool:
        """Check if provider dependencies and connectivity are ready."""
        pass

    @abstractmethod
    def fetch_ohlcv(
        self,
        ticker: str,
        start_date: str,
        end_date: str | None = None,
        interval: str = "1d",
    ) -> pd.DataFrame:
        """Fetch historical OHLCV data.

        Returns DataFrame with columns: ['open', 'high', 'low', 'close', 'volume']
        indexed by date string 'YYYY-MM-DD'.
        """
        pass

    @abstractmethod
    def fetch_quote(self, ticker: str) -> dict[str, Any]:
        """Fetch latest price snapshot (price, change, volume, high, low)."""
        pass

    def fetch_bhavcopy(self, date_str: str) -> pd.DataFrame:
        """Fetch bulk daily bhavcopy for all securities on a specific date.

        Returns DataFrame with columns: ['ticker', 'open', 'high', 'low', 'close', 'volume']
        """
        raise NotImplementedError(f"{self.name} does not support bulk bhavcopy download")

    def fetch_option_chain(self, symbol: str, expiry_date: str | None = None) -> dict[str, Any]:
        """Fetch live or historical Option Chain (strikes, OI, change in OI, PCR, IV)."""
        raise NotImplementedError(f"{self.name} does not support option chain data")

    def fetch_index_data(self, index_name: str, start_date: str, end_date: str | None = None) -> pd.DataFrame:
        """Fetch historical index values (e.g. NIFTY 50, NIFTY BANK, SP500)."""
        raise NotImplementedError(f"{self.name} does not support index data")
