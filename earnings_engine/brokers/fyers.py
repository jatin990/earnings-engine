"""Fyers API v3 broker adapter (fyers-apiv3).

Supports:
- Authentication via App ID & Access Token / TOTP
- Free market quotes and historical charting API
- Positions, holdings, margin, and order execution
"""

from __future__ import annotations

import logging
from typing import Any

from earnings_engine.brokers.base_broker import BaseBroker

logger = logging.getLogger("earnings_engine.brokers.fyers")


class FyersBroker(BaseBroker):
    """Fyers API v3 broker adapter."""

    def __init__(self, client_id: str | None = None, access_token: str | None = None) -> None:
        self.client_id = client_id
        self.access_token = access_token
        self._fyers: Any = None

    @property
    def broker_name(self) -> str:
        return "fyers"

    @property
    def is_connected(self) -> bool:
        return self._fyers is not None and self.access_token is not None

    def authenticate(self, **credentials: Any) -> bool:
        """Authenticate with Fyers API v3 SDK."""
        client_id = credentials.get("client_id") or self.client_id
        access_token = credentials.get("access_token") or self.access_token

        if not client_id or not access_token:
            logger.warning("Fyers: missing client_id (app_id) or access_token")
            return False

        try:
            from fyers_apiv3 import fyersModel
            fyers = fyersModel.FyersModel(client_id=client_id, is_async=False, token=access_token)
            self._fyers = fyers
            self.client_id = client_id
            self.access_token = access_token
            logger.info("Fyers: session authenticated successfully")
            return True
        except ImportError:
            logger.warning("fyers-apiv3 package not installed. Install with `pip install fyers-apiv3`")
            return False
        except Exception as e:
            logger.error("Fyers auth error: %s", e)
            return False

    def get_profile(self) -> dict[str, Any]:
        if not self.is_connected:
            return {"broker": "fyers", "status": "DISCONNECTED"}
        try:
            return self._fyers.get_profile()
        except Exception as e:
            return {"broker": "fyers", "error": str(e)}

    def get_funds(self) -> dict[str, Any]:
        if not self.is_connected:
            return {"available_margin": 0.0, "status": "DISCONNECTED"}
        try:
            res = self._fyers.funds()
            fund_limit = res.get("fund_limit", []) if isinstance(res, dict) else []
            margin = 0.0
            for item in fund_limit:
                if item.get("title") == "Total Balance":
                    margin = float(item.get("equityAmount", 0.0))
            return {"available_margin": margin, "raw": res}
        except Exception as e:
            return {"available_margin": 0.0, "error": str(e)}

    def get_positions(self) -> list[dict[str, Any]]:
        if not self.is_connected:
            return []
        try:
            res = self._fyers.positions()
            return res.get("netPositions", []) if isinstance(res, dict) else []
        except Exception as e:
            logger.error("Fyers get_positions error: %s", e)
            return []

    def get_holdings(self) -> list[dict[str, Any]]:
        if not self.is_connected:
            return []
        try:
            res = self._fyers.holdings()
            return res.get("holdings", []) if isinstance(res, dict) else []
        except Exception as e:
            logger.error("Fyers get_holdings error: %s", e)
            return []

    def get_quote(self, symbol: str) -> dict[str, Any]:
        clean_sym = symbol.upper().replace(".NS", "")
        fyers_sym = f"NSE:{clean_sym}-EQ"
        if not self.is_connected:
            return {"symbol": clean_sym, "price": None, "broker": "fyers", "status": "DISCONNECTED"}
        try:
            res = self._fyers.quotes({"symbols": fyers_sym})
            d = res.get("d", [{}])[0].get("v", {}) if isinstance(res, dict) and "d" in res else {}
            return {
                "symbol": clean_sym,
                "price": float(d.get("lp", 0.0)) if d.get("lp") else None,
                "high": float(d.get("high_price", 0.0)) if d.get("high_price") else None,
                "low": float(d.get("low_price", 0.0)) if d.get("low_price") else None,
                "volume": float(d.get("volume", 0.0)) if d.get("volume") else None,
                "broker": "fyers",
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
            return {"success": False, "error": "Fyers broker not connected"}
        clean_sym = symbol.upper().replace(".NS", "")
        fyers_sym = f"NSE:{clean_sym}-EQ"
        try:
            data = {
                "symbol": fyers_sym,
                "qty": quantity,
                "type": 2 if order_type.upper() == "MARKET" else 1,
                "side": 1 if side.upper() == "BUY" else -1,
                "productType": "CNC" if product.upper() == "CNC" else "INTRADAY",
                "limitPrice": price or 0.0,
                "stopPrice": 0,
                "validity": "DAY",
                "disclosedQty": 0,
                "offlineOrder": False,
            }
            res = self._fyers.place_order(data=data)
            order_id = res.get("id") if isinstance(res, dict) else str(res)
            return {"success": True, "order_id": order_id, "symbol": clean_sym, "side": side, "quantity": quantity}
        except Exception as e:
            logger.error("Fyers place_order failed: %s", e)
            return {"success": False, "error": str(e)}

    def cancel_order(self, order_id: str) -> bool:
        if not self.is_connected:
            return False
        try:
            self._fyers.cancel_order({"id": order_id})
            return True
        except Exception as e:
            logger.error("Fyers cancel_order failed: %s", e)
            return False
