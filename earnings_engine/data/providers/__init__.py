"""Multi-provider market data ingestion package."""

from earnings_engine.data.providers.base import DataProvider
from earnings_engine.data.providers.nse_provider import NSEDirectProvider
from earnings_engine.data.providers.provider_manager import DataProviderManager, get_data_manager
from earnings_engine.data.providers.yfinance_provider import YFinanceProvider

__all__ = [
    "DataProvider",
    "NSEDirectProvider",
    "YFinanceProvider",
    "DataProviderManager",
    "get_data_manager",
]
