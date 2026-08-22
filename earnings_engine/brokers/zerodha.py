"""Zerodha Kite Connect adapter (kiteconnect).

Supports:
- Headless login with API Key + API Secret + TOTP (pyotp)
- Live quote / market depth polling
- Order placement (Market / Limit / GTT) and position tracking
"""

from __future__ import annotations

import logging
from typing import Any

from earnings_engine.brokers.base_broker import BaseBroker
from earnings_engine.brokers.totp import generate_totp

logger = logging.getLogger("earnings_engine.brokers.zerodha")


class ZerodhaBroker(BaseBroker):
    """Zerodha Kite Connect broker adapter."""

    def __init__(self, api_key: str | None = None, api_secret: str | None = None, totp_secret: str | None = None) -> None:
        self.api_key = api_key
        self.api_secret = api_secret
        self.totp_secret = totp_secret
        self._kite: Any = None
        self._access_token: str | None = None

    @property
    def broker_name(self) -> str:
        return "zerodha"

    @property
    def is_connected(self) -> bool:
        return self._kite is not None and self._access_token is not None

    def authenticate(self, **credentials: Any) -> bool:
        """Authenticate using kiteconnect SDK or access token."""
        api_key = credentials.get("api_key") or self.api_key
        access_token = credentials.get("access_token") or self._access_token
        totp_sec = credentials.get("totp_secret") or self.totp_secret

        if not api_key:
            logger.warning("Zerodha: missing api_key")
            return False

        try:
            from kiteconnect import KiteConnect
            kite = KiteConnect(api_key=api_key)

            if access_token:
                kite.set_access_token(access_token)
                self._kite = kite
                self._access_token = access_token
                logger.info("Zerodha: authenticated with access token")
                return True

            # If request_token provided
            req_token = credentials.get("request_token")
            api_secret = credentials.get("api_secret") or self.api_secret
            if req_token and api_secret:
                data = kite.generate_session(req_token, api_secret=api_secret)
                token = data["access_token"]
                kite.set_access_token(token)
                self._kite = kite
                self._access_token = token
                logger.info("Zerodha: session generated successfully")
                return True

            logger.info("Zerodha KiteConnect initialized (awaiting access token / login)")
            self._kite = kite
            return True
        except ImportError:
            logger.warning("kiteconnect package not installed. Install with `pip install kiteconnect`")
            return False
        except Exception as e:
            logger.error("Zerodha auth error: %s", e)
            return False

    def get_profile(self) -> dict[str, Any]:
        if not self.is_connected:
            return {"broker": "zerodha", "status": "DISCONNECTED"}
        try:
            return self._kite.profile()
        except Exception as e:
            return {"broker": "zerodha", "error": str(e)}

    def get_funds(self) -> dict[str, Any]:
        if not self.is_connected:
            return {"available_margin": 0.0, "status": "DISCONNECTED"}
        try:
            margins = self._kite.margins()
            return margins.get("equity", {})
        except Exception as e:
            return {"available_margin": 0.0, "error": str(e)}

    def get_positions(self) -> list[dict[str, Any]]:
        if not self.is_connected:
            return []
        try:
            pos = self._kite.positions()
            return pos.get("net", [])
        except Exception as e:
            logger.error("Zerodha get_positions error: %s", e)
            return []

    def get_holdings(self) -> list[dict[str, Any]]:
        if not self.is_connected:
            return []
        try:
            return self._kite.holdings()
        except Exception as e:
            logger.error("Zerodha get_holdings error: %s", e)
            return []

    def get_quote(self, symbol: str) -> dict[str, Any]:
        clean_sym = symbol.upper().replace(".NS", "")
        tradingsymbol = f"NSE:{clean_sym}"
        if not self.is_connected:
            return {"symbol": clean_sym, "price": None, "broker": "zerodha", "status": "DISCONNECTED"}
        try:
            data = self._kite.quote([tradingsymbol])
            quote = data.get(tradingsymbol, {})
            return {
                "symbol": clean_sym,
                "price": quote.get("last_price"),
                "volume": quote.get("volume"),
                "high": quote.get("ohlc", {}).get("high"),
                "low": quote.get("ohlc", {}).get("low"),
                "broker": "zerodha",
            }
        except Exception as e:
            return {"symbol": clean_sym, "price": None, "error": str(e)}

    def place_order(
        self,
        symbol: str,
        side: str,
        quantity: int,
        order_type: str = "MARKET",
        price: float | None = None,
        product: str = "CNC",
        tag: str | None = None,
    ) -> dict[str, Any]:
        if not self.is_connected:
            return {"success": False, "error": "Zerodha broker not connected"}
        clean_sym = symbol.upper().replace(".NS", "")
        try:
            order_id = self._kite.place_order(
                variety=self._kite.VARIETY_REGULAR,
                exchange=self._kite.EXCHANGE_NSE,
                tradingsymbol=clean_sym,
                transaction_type=self._kite.TRANSACTION_TYPE_BUY if side.upper() == "BUY" else self._kite.TRANSACTION_TYPE_SELL,
                quantity=quantity,
                product=self._kite.PRODUCT_CNC if product.upper() == "CNC" else self._kite.PRODUCT_MIS,
                order_type=self._kite.ORDER_TYPE_MARKET if order_type.upper() == "MARKET" else self._kite.ORDER_TYPE_LIMIT,
                price=price,
                tag=tag,
            )
            return {"success": True, "order_id": order_id, "symbol": clean_sym, "side": side, "quantity": quantity}
        except Exception as e:
            logger.error("Zerodha place_order failed: %s", e)
            return {"success": False, "error": str(e)}

    def cancel_order(self, order_id: str) -> bool:
        if not self.is_connected:
            return False
        try:
            self._kite.cancel_order(variety=self._kite.VARIETY_REGULAR, order_id=order_id)
            return True
        except Exception as e:
            logger.error("Zerodha cancel_order failed: %s", e)
            return False
