"""Tests for automated TOTP and multi-broker adapter layer."""

from __future__ import annotations

import pyotp
import pytest

from earnings_engine.brokers.angel_one import AngelOneBroker
from earnings_engine.brokers.broker_manager import BrokerManager, get_broker_manager
from earnings_engine.brokers.dhan import DhanBroker
from earnings_engine.brokers.fyers import FyersBroker
from earnings_engine.brokers.totp import generate_totp, verify_totp
from earnings_engine.brokers.zerodha import ZerodhaBroker


class TestTOTP:
    def test_generate_and_verify_totp(self) -> None:
        # Generate a valid random base32 secret
        secret = pyotp.random_base32()
        code = generate_totp(secret)
        assert isinstance(code, str)
        assert len(code) == 6
        assert code.isdigit()
        assert verify_totp(secret, code) is True

    def test_invalid_totp_secret_raises(self) -> None:
        with pytest.raises(ValueError):
            generate_totp("INVALID_SECRET_123!!!")


class TestBrokerAdapters:
    def test_zerodha_disconnected_state(self) -> None:
        b = ZerodhaBroker()
        assert b.broker_name == "zerodha"
        assert b.is_connected is False
        assert b.get_positions() == []
        assert b.get_holdings() == []
        res = b.place_order("INFY", "BUY", 10)
        assert res["success"] is False

    def test_angel_one_disconnected_state(self) -> None:
        b = AngelOneBroker()
        assert b.broker_name == "angel_one"
        assert b.is_connected is False
        assert b.get_funds()["available_margin"] == 0.0
        res = b.place_order("TCS", "BUY", 5)
        assert res["success"] is False

    def test_dhan_disconnected_state(self) -> None:
        b = DhanBroker()
        assert b.broker_name == "dhan"
        assert b.is_connected is False
        assert b.get_funds()["available_margin"] == 0.0
        res = b.place_order("RELIANCE", "BUY", 1)
        assert res["success"] is False

    def test_fyers_disconnected_state(self) -> None:
        b = FyersBroker()
        assert b.broker_name == "fyers"
        assert b.is_connected is False
        assert b.get_funds()["available_margin"] == 0.0
        res = b.place_order("SBIN", "BUY", 10)
        assert res["success"] is False


class TestBrokerManager:
    def test_manager_status(self) -> None:
        mgr = get_broker_manager()
        st = mgr.get_status()
        assert "brokers" in st
        assert "zerodha" in st["brokers"]
        assert "angel_one" in st["brokers"]
        assert "dhan" in st["brokers"]
        assert "fyers" in st["brokers"]

    def test_paper_trade_execution(self) -> None:
        mgr = get_broker_manager()
        mgr.trading_mode = "PAPER"

        res = mgr.execute_signal(
            symbol="RELIANCE.NS",
            signal="BULLISH",
            quantity=5,
            price=2500.0,
            strategy_name="Breakout_Test",
        )
        assert res["success"] is True
        assert res["mode"] == "PAPER"
        assert res["side"] == "BUY"
        assert res["quantity"] == 5
        assert "order_id" in res
        assert res["order_id"].startswith("PAPER_")
