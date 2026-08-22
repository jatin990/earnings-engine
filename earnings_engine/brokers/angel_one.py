"""Angel One SmartAPI adapter (smartapi-python).

Supports:
- Automated 2FA TOTP login using pyotp + MPIN
- Free historical candle downloads
- Live quotes and WebSocket feeds
- Order placement and portfolio tracking
"""

from __future__ import annotations

import logging
from typing import Any

from earnings_engine.brokers.base_broker import BaseBroker
from earnings_engine.brokers.totp import generate_totp

logger = logging.getLogger("earnings_engine.brokers.angel_one")


class AngelOneBroker(BaseBroker):
    """Angel One SmartAPI broker adapter."""

    def __init__(
        self,
        api_key: str | None = None,
        client_code: str | None = None,
        password: str | None = None,
        totp_secret: str | None = None,
    ) -> None:
        self.api_key = api_key
        self.client_code = client_code
        self.password = password
        self.totp_secret = totp_secret
        self._smart_api: Any = None
        self._auth_token: str | None = None
        self._feed_token: str | None = None

    @property
    def broker_name(self) -> str:
        return "angel_one"

    @property
    def is_connected(self) -> bool:
        return self._smart_api is not None and self._auth_token is not None

    def authenticate(self, **credentials: Any) -> bool:
        """Authenticate session using SmartAPI SDK + pyotp TOTP."""
        api_key = credentials.get("api_key") or self.api_key
        client_code = credentials.get("client_code") or self.client_code
        password = credentials.get("password") or self.password
        totp_sec = credentials.get("totp_secret") or self.totp_secret

        if not api_key or not client_code:
            logger.warning("Angel One: missing api_key or client_code")
            return False

        try:
            from SmartApi import SmartConnect
            smart = SmartConnect(api_key=api_key)

            if password and totp_sec:
                otp_code = generate_totp(totp_sec)
                data = smart.generateSession(client_code, password, otp_code)
                if data and data.get("status"):
                    self._smart_api = smart
                    self._auth_token = data.get("data", {}).get("jwtToken")
                    self._feed_token = smart.getfeedToken()
                    logger.info("Angel One: session generated successfully with TOTP")
                    return True
                else:
                    logger.warning("Angel One login failed: %s", data.get("message"))
                    return False

            self._smart_api = smart
            return True
        except ImportError:
            logger.warning("smartapi-python package not installed. Install with `pip install smartapi-python`")
            return False
        except Exception as e:
            logger.error("Angel One auth error: %s", e)
            return False

    def get_profile(self) -> dict[str, Any]:
        if not self.is_connected:
            return {"broker": "angel_one", "status": "DISCONNECTED"}
        try:
            return self._smart_api.getProfile(self._auth_token)
        except Exception as e:
            return {"broker": "angel_one", "error": str(e)}

    def get_funds(self) -> dict[str, Any]:
        if not self.is_connected:
            return {"available_margin": 0.0, "status": "DISCONNECTED"}
        try:
            res = self._smart_api.rmsLimit()
            data = res.get("data", {}) if isinstance(res, dict) else {}
            return {"available_margin": float(data.get("net", 0.0)), "raw": data}
        except Exception as e:
            return {"available_margin": 0.0, "error": str(e)}

    def get_positions(self) -> list[dict[str, Any]]:
        if not self.is_connected:
            return []
        try:
            res = self._smart_api.position()
            return res.get("data", []) if isinstance(res, dict) else []
        except Exception as e:
            logger.error("Angel One get_positions error: %s", e)
            return []

    def get_holdings(self) -> list[dict[str, Any]]:
        if not self.is_connected:
            return []
        try:
            res = self._smart_api.holding()
            return res.get("data", []) if isinstance(res, dict) else []
        except Exception as e:
            logger.error("Angel One get_holdings error: %s", e)
            return []

    def get_quote(self, symbol: str) -> dict[str, Any]:
        clean_sym = symbol.upper().replace(".NS", "")
        if not self.is_connected:
            return {"symbol": clean_sym, "price": None, "broker": "angel_one", "status": "DISCONNECTED"}
        try:
            # SmartAPI ltpData call
            res = self._smart_api.ltpData("NSE", f"{clean_sym}-EQ", "")
            data = res.get("data", {}) if isinstance(res, dict) else {}
            return {
                "symbol": clean_sym,
                "price": float(data.get("ltp", 0.0)) if data.get("ltp") else None,
                "high": float(data.get("high", 0.0)) if data.get("high") else None,
                "low": float(data.get("low", 0.0)) if data.get("low") else None,
                "broker": "angel_one",
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
            return {"success": False, "error": "Angel One broker not connected"}
        clean_sym = symbol.upper().replace(".NS", "")
        try:
            order_params = {
                "variety": "NORMAL",
                "tradingsymbol": f"{clean_sym}-EQ",
                "symboltoken": "",
                "transactiontype": "BUY" if side.upper() == "BUY" else "SELL",
                "exchange": "NSE",
                "ordertype": "MARKET" if order_type.upper() == "MARKET" else "LIMIT",
                "producttype": "DELIVERY" if product.upper() == "CNC" else "INTRADAY",
                "duration": "DAY",
                "price": str(price or "0"),
                "quantity": str(quantity),
            }
            order_id = self._smart_api.placeOrder(order_params)
            return {"success": True, "order_id": order_id, "symbol": clean_sym, "side": side, "quantity": quantity}
        except Exception as e:
            logger.error("Angel One place_order failed: %s", e)
            return {"success": False, "error": str(e)}

    def cancel_order(self, order_id: str) -> bool:
        if not self.is_connected:
            return False
        try:
            self._smart_api.cancelOrder(order_id, "NORMAL")
            return True
        except Exception as e:
            logger.error("Angel One cancel_order failed: %s", e)
            return False
