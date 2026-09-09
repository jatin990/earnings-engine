"""Central Broker Manager & Multi-Broker Order Router.

Coordinates authentication, portfolio status, live quotes, and order execution
across Zerodha (kiteconnect), Angel One (smartapi), Dhan (dhanhq), and Fyers (fyers-apiv3),
with built-in Paper Trading simulation mode.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from earnings_engine.brokers.angel_one import AngelOneBroker
from earnings_engine.brokers.base_broker import BaseBroker
from earnings_engine.brokers.dhan import DhanBroker
from earnings_engine.brokers.fyers import FyersBroker
from earnings_engine.brokers.zerodha import ZerodhaBroker

logger = logging.getLogger("earnings_engine.brokers.manager")


class BrokerManager:
    """Manages all broker connections and routes live or paper trade executions."""

    def __init__(self) -> None:
        self.brokers: dict[str, BaseBroker] = {
            "zerodha": ZerodhaBroker(
                api_key=os.getenv("ZERODHA_API_KEY"),
                api_secret=os.getenv("ZERODHA_API_SECRET"),
                totp_secret=os.getenv("ZERODHA_TOTP_SECRET"),
            ),
            "angel_one": AngelOneBroker(
                api_key=os.getenv("ANGEL_API_KEY"),
                client_code=os.getenv("ANGEL_CLIENT_CODE"),
                password=os.getenv("ANGEL_PASSWORD"),
                totp_secret=os.getenv("ANGEL_TOTP_SECRET"),
            ),
            "dhan": DhanBroker(
                client_id=os.getenv("DHAN_CLIENT_ID"),
                access_token=os.getenv("DHAN_ACCESS_TOKEN"),
            ),
            "fyers": FyersBroker(
                client_id=os.getenv("FYERS_CLIENT_ID"),
                access_token=os.getenv("FYERS_ACCESS_TOKEN"),
            ),
        }
        self.default_broker_name: str = os.getenv("DEFAULT_BROKER", "zerodha").lower()
        self.trading_mode: str = os.getenv("TRADING_MODE", "PAPER").upper()  # 'PAPER' or 'LIVE'

    def get_broker(self, name: str | None = None) -> BaseBroker | None:
        """Get broker adapter by name, or default broker."""
        target = (name or self.default_broker_name).lower()
        return self.brokers.get(target)

    def get_status(self) -> dict[str, Any]:
        """Return connectivity status and account summary for all brokers."""
        status: dict[str, Any] = {
            "trading_mode": self.trading_mode,
            "default_broker": self.default_broker_name,
            "brokers": {},
        }
        for name, b in self.brokers.items():
            status["brokers"][name] = {
                "connected": b.is_connected,
                "name": b.broker_name,
            }
        return status

    def authenticate_broker(self, name: str, **credentials: Any) -> bool:
        """Authenticate a specific broker with supplied or environment credentials."""
        b = self.get_broker(name)
        if not b:
            logger.warning("[BROKER:AUTH] Unknown broker '%s'", name)
            return False
        logger.info("[BROKER:AUTH] Attempting authentication for %s...", name)
        res = b.authenticate(**credentials)
        if res:
            logger.info("[BROKER:AUTH] Authentication successful for %s", name)
        else:
            logger.warning("[BROKER:AUTH] Authentication failed for %s", name)
        return res

    def get_quote(self, symbol: str, broker_name: str | None = None) -> dict[str, Any]:
        """Fetch live quote from connected broker, falling back to data provider."""
        b = self.get_broker(broker_name)
        if b and b.is_connected:
            q = b.get_quote(symbol)
            if q.get("price") is not None:
                return q

        # Fallback to DataProviderManager
        from earnings_engine.data.providers.provider_manager import get_data_manager
        mgr = get_data_manager()
        return mgr.fetch_quote(symbol)

    def execute_signal(
        self,
        symbol: str,
        signal: str,  # 'BULLISH' (Buy) | 'BEARISH' (Sell)
        quantity: int = 1,
        order_type: str = "MARKET",
        price: float | None = None,
        strategy_name: str = "Strategy_Auditor",
        broker_name: str | None = None,
    ) -> dict[str, Any]:
        """Execute a strategy signal via the broker or paper trading simulator."""
        side = "BUY" if signal.upper() == "BULLISH" else "SELL"

        # 1. Paper Trading Simulation Mode
        if self.trading_mode == "PAPER":
            import random
            from datetime import datetime
            paper_order_id = f"PAPER_{int(datetime.now().timestamp())}_{random.randint(100, 999)}"
            logger.info(
                "[BROKER:ORDER] [PAPER] %s %d %s @ %s (strategy=%s, id=%s)",
                side, quantity, symbol, price or "LTP", strategy_name, paper_order_id,
            )
            return {
                "success": True,
                "mode": "PAPER",
                "order_id": paper_order_id,
                "symbol": symbol.upper(),
                "side": side,
                "quantity": quantity,
                "order_type": order_type,
                "price": price,
                "strategy": strategy_name,
                "status": "FILLED_SIMULATED",
            }

        # 2. Live Broker Execution Mode
        b = self.get_broker(broker_name)
        if not b or not b.is_connected:
            logger.warning("[BROKER:ORDER] Execution failed: Broker '%s' not connected", broker_name or self.default_broker_name)
            return {
                "success": False,
                "mode": "LIVE",
                "error": f"Broker '{broker_name or self.default_broker_name}' is not connected for live trading.",
            }

        logger.info(
            "[BROKER:ORDER] [LIVE:%s] %s %d %s @ %s (strategy=%s)",
            broker_name or self.default_broker_name, side, quantity, symbol, price or "MARKET", strategy_name
        )
        return b.place_order(
            symbol=symbol,
            side=side,
            quantity=quantity,
            order_type=order_type,
            price=price,
            tag=strategy_name[:8],
        )


# Singleton broker manager
_broker_manager_instance: BrokerManager | None = None


def get_broker_manager() -> BrokerManager:
    """Get or create singleton BrokerManager instance."""
    global _broker_manager_instance
    if _broker_manager_instance is None:
        _broker_manager_instance = BrokerManager()
    return _broker_manager_instance
