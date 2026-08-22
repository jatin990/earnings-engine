"""Abstract Base Broker adapter interface.

Unifies broker operations across Zerodha (kiteconnect), Angel One (smartapi),
Dhan (dhanhq), and Fyers (fyers-apiv3).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseBroker(ABC):
    """Abstract interface for stock broker connections and order execution."""

    @property
    @abstractmethod
    def broker_name(self) -> str:
        """Name of the broker (e.g. 'zerodha', 'angel_one', 'dhan', 'fyers')."""
        pass

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """True if session is authenticated and active."""
        pass

    @abstractmethod
    def authenticate(self, **credentials: Any) -> bool:
        """Authenticate session using API keys, TOTP (pyotp), or access token.

        Returns True on successful login.
        """
        pass

    @abstractmethod
    def get_profile(self) -> dict[str, Any]:
        """Fetch user account and profile metadata."""
        pass

    @abstractmethod
    def get_funds(self) -> dict[str, Any]:
        """Fetch available margin / cash balance."""
        pass

    @abstractmethod
    def get_positions(self) -> list[dict[str, Any]]:
        """Fetch open trading positions."""
        pass

    @abstractmethod
    def get_holdings(self) -> list[dict[str, Any]]:
        """Fetch long-term equity portfolio holdings."""
        pass

    @abstractmethod
    def get_quote(self, symbol: str) -> dict[str, Any]:
        """Fetch real-time live quote (LTP, bid/ask, volume, OHLC)."""
        pass

    @abstractmethod
    def place_order(
        self,
        symbol: str,
        side: str,  # 'BUY' | 'SELL'
        quantity: int,
        order_type: str = "MARKET",  # 'MARKET' | 'LIMIT' | 'SL'
        price: float | None = None,
        product: str = "CNC",  # 'CNC' (delivery) | 'MIS' (intraday)
        tag: str | None = None,
    ) -> dict[str, Any]:
        """Submit a buy or sell order.

        Returns order confirmation dict with order_id and status.
        """
        pass

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order."""
        pass
