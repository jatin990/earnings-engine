import pytest
from httpx import AsyncClient, ASGITransport

from earnings_engine.api.server import app


@pytest.mark.anyio
async def test_options_symbols_endpoint():
    """Verify /api/v1/options/symbols returns index and equity symbol suggestions."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/v1/options/symbols")
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["count"] > 0
        symbols = [s["symbol"] for s in data["symbols"]]
        assert "NIFTY" in symbols
        assert "BANKNIFTY" in symbols
        assert "RELIANCE" in symbols


@pytest.mark.anyio
async def test_options_symbols_query_filter():
    """Verify symbol search query filter works as expected."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/v1/options/symbols?query=NIF")
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        for s in data["symbols"]:
            assert "NIF" in s["symbol"] or "NIF" in s["name"].upper()


@pytest.mark.anyio
async def test_options_chain_non_fno():
    """Verify cash-only / non-F&O symbol immediately returns NOT_FNO with empty strikes."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/v1/options/chain?symbol=SOUTHWEST")
        assert res.status_code == 200
        payload = res.json()
        assert payload["success"] is True
        data = payload["data"]
        assert data["status"] == "NOT_FNO"
        assert data["strikes"] == []
        assert data["symbol"] == "SOUTHWEST"
        assert "NOT_FNO_ELIGIBLE" in data["signals"]


@pytest.mark.anyio
async def test_options_chain_mocked_live(monkeypatch):
    """Verify options chain analysis and strike ladder formatting with mock provider data."""
    from earnings_engine.data.providers import provider_manager

    class DummyProvider:
        def fetch_option_chain(self, symbol, expiry_date=None):
            return {
                "underlying_value": 24500.0,
                "timestamp": "2025-03-27 15:30:00",
                "expiries": ["27-Mar-2025", "24-Apr-2025"],
                "selected_expiry": "27-Mar-2025",
                "data": [
                    {
                        "strikePrice": 24400.0,
                        "CE": {"openInterest": 15000, "changeinOpenInterest": 2000, "pchangeinOpenInterest": 15.3, "lastPrice": 180.0, "impliedVolatility": 13.5, "totalTradedVolume": 50000},
                        "PE": {"openInterest": 30000, "changeinOpenInterest": 5000, "pchangeinOpenInterest": 20.0, "lastPrice": 80.0, "impliedVolatility": 14.2, "totalTradedVolume": 75000},
                    },
                    {
                        "strikePrice": 24500.0,
                        "CE": {"openInterest": 25000, "changeinOpenInterest": 1000, "pchangeinOpenInterest": 4.1, "lastPrice": 120.0, "impliedVolatility": 13.8, "totalTradedVolume": 90000},
                        "PE": {"openInterest": 28000, "changeinOpenInterest": 3500, "pchangeinOpenInterest": 14.2, "lastPrice": 120.0, "impliedVolatility": 13.9, "totalTradedVolume": 88000},
                    },
                    {
                        "strikePrice": 24600.0,
                        "CE": {"openInterest": 35000, "changeinOpenInterest": 4000, "pchangeinOpenInterest": 12.9, "lastPrice": 75.0, "impliedVolatility": 14.1, "totalTradedVolume": 80000},
                        "PE": {"openInterest": 12000, "changeinOpenInterest": -1500, "pchangeinOpenInterest": -11.1, "lastPrice": 175.0, "impliedVolatility": 14.6, "totalTradedVolume": 45000},
                    },
                ],
                "raw_count": 3,
                "provider": "NSE_LIVE",
            }

    class DummyManager:
        def get_provider(self, name):
            return DummyProvider()

        def fetch_option_chain(self, symbol, expiry_date=None):
            return DummyProvider().fetch_option_chain(symbol, expiry_date=expiry_date)

    monkeypatch.setattr(provider_manager, "get_data_manager", lambda *args, **kwargs: DummyManager())
    monkeypatch.setattr("earnings_engine.data.option_chain.get_data_manager", lambda *args, **kwargs: DummyManager())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/v1/options/chain?symbol=NIFTY&force_refresh=true")
        assert res.status_code == 200
        payload = res.json()
        assert payload["success"] is True
        data = payload["data"]
        assert data["status"] == "LIVE"
        assert data["symbol"] == "NIFTY"
        assert data["spot_price"] == 24500.0
        assert len(data["strikes"]) == 3

        # Verify ATM identification
        atm_strike = next((s for s in data["strikes"] if s["is_atm"]), None)
        assert atm_strike is not None
        assert atm_strike["strike"] == 24500.0

        # Verify ITM / OTM flags
        s_lower = next(s for s in data["strikes"] if s["strike"] == 24400.0)
        assert s_lower["ce_itm"] is True
        assert s_lower["pe_itm"] is False

        s_higher = next(s for s in data["strikes"] if s["strike"] == 24600.0)
        assert s_higher["ce_itm"] is False
        assert s_higher["pe_itm"] is True


@pytest.mark.anyio
async def test_options_history_endpoint():
    """Verify /api/v1/options/history endpoint format."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/v1/options/history?symbol=NIFTY&limit=10")
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["symbol"] == "NIFTY"
        assert "history" in data
        assert isinstance(data["history"], list)
