"""Tests for the Multi-Provider Data Layer and Option Chain Analytics."""

from __future__ import annotations

import pandas as pd
import pytest

from earnings_engine.data.option_chain import (
    _calculate_max_pain,
    _calculate_option_metrics_from_records,
    analyze_option_chain,
)
from earnings_engine.data.providers.base import DataProvider
from earnings_engine.data.providers.nse_provider import NSEDirectProvider
from earnings_engine.data.providers.provider_manager import DataProviderManager, get_data_manager
from earnings_engine.data.providers.yfinance_provider import YFinanceProvider


class TestDataProviders:
    def test_yfinance_provider_interface(self) -> None:
        p = YFinanceProvider()
        assert p.name == "yfinance"
        assert isinstance(p.is_available, bool)

    def test_nse_direct_provider_interface(self) -> None:
        p = NSEDirectProvider()
        assert p.name == "nse_direct"
        assert isinstance(p.is_available, bool)

    def test_provider_manager_routing(self) -> None:
        mgr = get_data_manager()
        assert mgr.get_provider("yfinance") is not None
        assert mgr.get_provider("nse_direct") is not None

    def test_bhavcopy_empty_fallback(self) -> None:
        mgr = get_data_manager()
        # Even if offline, should return DataFrame with standard columns
        df = mgr.fetch_bhavcopy("2026-01-01")
        assert isinstance(df, pd.DataFrame)
        assert "ticker" in df.columns or df.empty

    def test_option_chain_rate_limit_tracked(self) -> None:
        from earnings_engine.rate_limits import get_ratelimits_summary
        initial_nse_count = get_ratelimits_summary()["downstreams"]["nse"]["timeframes"]["24h"]["current"]

        provider = NSEDirectProvider()
        # Fetching option chain (even when nselib is not installed or returns empty) must record request
        provider.fetch_option_chain("INFY.NS")

        new_nse_count = get_ratelimits_summary()["downstreams"]["nse"]["timeframes"]["24h"]["current"]
        assert new_nse_count >= initial_nse_count + 1

    def test_resolve_nse_index_name(self) -> None:
        from earnings_engine.data.providers.nse_provider import resolve_nse_index_name

        assert resolve_nse_index_name("^NSEBANK") == "NIFTY BANK"
        assert resolve_nse_index_name("BANKNIFTY") == "NIFTY BANK"
        assert resolve_nse_index_name("NIFTY BANK") == "NIFTY BANK"
        assert resolve_nse_index_name("^NSEI") == "NIFTY 50"
        assert resolve_nse_index_name("NIFTY") == "NIFTY 50"
        assert resolve_nse_index_name("NIFTY 50") == "NIFTY 50"
        assert resolve_nse_index_name("^CNXIT") == "NIFTY IT"
        assert resolve_nse_index_name("NIFTY IT") == "NIFTY IT"
        assert resolve_nse_index_name("^CNXFIN") == "NIFTY FINANCIAL SERVICES"
        assert resolve_nse_index_name("FINNIFTY") == "NIFTY FINANCIAL SERVICES"
        assert resolve_nse_index_name("^CNXAUTO") == "NIFTY AUTO"
        assert resolve_nse_index_name("^CNXPHARMA") == "NIFTY PHARMA"
        assert resolve_nse_index_name("^CNXENERGY") == "NIFTY ENERGY"
        assert resolve_nse_index_name("^CNXMETAL") == "NIFTY METAL"
        assert resolve_nse_index_name("^CNXREALTY") == "NIFTY REALTY"
        assert resolve_nse_index_name("^CNXPSUBANK") == "NIFTY PSU BANK"
        assert resolve_nse_index_name("^INDIAVIX") == "INDIA VIX"
        assert resolve_nse_index_name("INFY.NS") is None
        assert resolve_nse_index_name("RELIANCE") is None

    def test_resolve_fno_symbol_and_is_fno_eligible(self) -> None:
        from earnings_engine.data.universe import is_fno_eligible, resolve_fno_symbol

        # Indices
        assert resolve_fno_symbol("^NSEBANK") == "BANKNIFTY"
        assert resolve_fno_symbol("BANKNIFTY") == "BANKNIFTY"
        assert resolve_fno_symbol("NIFTY BANK") == "BANKNIFTY"
        assert resolve_fno_symbol("^NSEI") == "NIFTY"
        assert resolve_fno_symbol("NIFTY 50") == "NIFTY"
        assert resolve_fno_symbol("^CNXFIN") == "FINNIFTY"
        assert resolve_fno_symbol("FINNIFTY") == "FINNIFTY"
        assert resolve_fno_symbol("MIDCPNIFTY") == "MIDCPNIFTY"

        # F&O Eligibility checks
        assert is_fno_eligible("^NSEBANK") is True
        assert is_fno_eligible("BANKNIFTY") is True
        assert is_fno_eligible("NIFTY BANK") is True
        assert is_fno_eligible("^NSEI") is True
        assert is_fno_eligible("NIFTY 50") is True
        assert is_fno_eligible("NIFTY") is True
        assert is_fno_eligible("RELIANCE") is True
        assert is_fno_eligible("RELIANCE.NS") is True
        assert is_fno_eligible("TCS.NS") is True
        assert is_fno_eligible("UNKNOWN_NON_FNO_STOCK") is False
        assert is_fno_eligible("") is False

    def test_non_nse_index_bypass(self) -> None:
        """Verify non-NSE tickers like ^GSPC or ^IXIC do not invoke stock_df/index_df and return empty."""
        provider = NSEDirectProvider()
        df = provider.fetch_ohlcv("^GSPC", start_date="2026-09-25", end_date="2026-10-02")
        assert df.empty
        q = provider.fetch_quote("^GSPC")
        assert q["price"] is None

    def test_yfinance_provider_normalization(self) -> None:
        p = YFinanceProvider()
        assert p._normalize_symbol("NIFTY") == "^NSEI"
        assert p._normalize_symbol("BANKNIFTY") == "^NSEBANK"
        assert p._normalize_symbol("NIFTY AUTO") == "^CNXAUTO"
        assert p._normalize_symbol("NIFTY PHARMA") == "^CNXPHARMA"
        assert p._normalize_symbol("SENSEX") == "^BSESN"
        assert p._normalize_symbol("^GSPC") == "^GSPC"
        assert p._normalize_symbol("AAPL") == "AAPL"
        assert p._normalize_symbol("RELIANCE") == "RELIANCE.NS"
        assert p._normalize_symbol("RELIANCE.NS") == "RELIANCE.NS"

    def test_fetch_ohlcv_routes_index_without_stock_df(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify ^NSEBANK is routed to index data and does not call equity stock_df."""
        provider = NSEDirectProvider()

        called_methods = []

        def mock_stock_df(*args, **kwargs):
            called_methods.append("stock_df")
            raise RuntimeError("stock_df should not be called for indices")

        def mock_index_data(index, from_date, to_date):
            called_methods.append(f"index_data:{index}")
            return pd.DataFrame({
                "INDEX_NAME": ["NIFTY BANK"],
                "OPEN_INDEX_VAL": [54000.0],
                "HIGH_INDEX_VAL": [54500.0],
                "LOW_INDEX_VAL": [53800.0],
                "CLOSE_INDEX_VAL": [54200.0],
                "TRADED_QTY": [1000000],
                "TIMESTAMP": ["01-OCT-2026"],
            })

        try:
            import nselib.capital_market as ncm
            monkeypatch.setattr(ncm, "index_data", mock_index_data)
        except Exception:
            pass

        try:
            import jugaad_data.nse as jnse
            monkeypatch.setattr(jnse, "stock_df", mock_stock_df)
        except Exception:
            pass

        df = provider.fetch_ohlcv("^NSEBANK", start_date="2026-09-25", end_date="2026-10-02")
        assert "stock_df" not in called_methods
        assert "index_data:NIFTY BANK" in called_methods
        assert not df.empty
        assert "close" in df.columns
        assert float(df["close"].iloc[0]) == 54200.0

    def test_fetch_quote_routes_index(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify fetch_quote routes ^NSEBANK to live_index."""
        provider = NSEDirectProvider()

        class MockNSELive:
            def live_index(self, symbol: str):
                return {
                    "data": [{
                        "symbol": symbol,
                        "lastPrice": 54450.75,
                        "open": 54583.05,
                        "dayHigh": 55091.45,
                        "dayLow": 54066.6,
                        "previousClose": 54633.05,
                        "change": -182.3,
                        "pChange": -0.33,
                    }]
                }

        from earnings_engine.data.providers import nse_provider
        monkeypatch.setattr(nse_provider, "_get_nselive_client", lambda: MockNSELive())

        q = provider.fetch_quote("^NSEBANK")
        assert q["symbol"] == "^NSEBANK"
        assert q["price"] == 54450.75
        assert q["previous_close"] == 54633.05



class TestOptionChainAnalytics:
    def test_max_pain_calculation(self) -> None:
        # 3 strikes: 100, 105, 110
        strikes_data = [
            {"strike": 100.0, "call_oi": 1000.0, "put_oi": 5000.0},
            {"strike": 105.0, "call_oi": 5000.0, "put_oi": 5000.0},
            {"strike": 110.0, "call_oi": 5000.0, "put_oi": 1000.0},
        ]
        mp = _calculate_max_pain(strikes_data)
        assert mp == 105.0

    def test_pcr_and_sentiment_from_records(self) -> None:
        records = [
            {"strikePrice": 100, "CE_openInterest": 1000, "PE_openInterest": 1500, "CE_totalTradedVolume": 100, "PE_totalTradedVolume": 150},
            {"strikePrice": 110, "CE_openInterest": 1000, "PE_openInterest": 1500, "CE_totalTradedVolume": 100, "PE_totalTradedVolume": 150},
        ]
        res = _calculate_option_metrics_from_records("NIFTY", records, 105.0)
        assert res["pcr_oi"] == 1.5  # 3000 / 2000 = 1.5
        assert res["sentiment"] == "BULLISH"  # PCR > 1.2

    def test_bearish_pcr_sentiment(self) -> None:
        records = [
            {"strikePrice": 100, "CE_openInterest": 3000, "PE_openInterest": 1000, "CE_totalTradedVolume": 300, "PE_totalTradedVolume": 100},
        ]
        res = _calculate_option_metrics_from_records("BANKNIFTY", records, 100.0)
        assert res["pcr_oi"] == 0.33
        assert res["sentiment"] == "BEARISH"  # PCR < 0.8

    def test_analyze_option_chain_fallback(self) -> None:
        res = analyze_option_chain("RELIANCE.NS", spot_price=2500.0)
        assert res["symbol"] == "RELIANCE"
        assert "pcr_oi" in res
        assert "max_pain_strike" in res
        assert res["status"] in ("LIVE", "ESTIMATED")

    def test_market_of_and_symbol_normalization(self) -> None:
        from earnings_engine.config import market_of
        from earnings_engine.data.providers.yfinance_provider import YFinanceProvider

        # market_of checks
        assert market_of("RELIANCE.NS") == "IN"
        assert market_of("LICHSGFIN.NS") == "IN"
        assert market_of("LICHSGFIN") == "IN"  # Bare NSE F&O underlying
        assert market_of("NIFTY") == "IN"
        assert market_of("BANKNIFTY") == "IN"
        assert market_of("^NSEBANK") == "IN"
        assert market_of("^CNXAUTO") == "IN"
        assert market_of("^CNXPHARMA") == "IN"
        assert market_of("^INDIAVIX") == "IN"
        assert market_of("SENSEX") == "IN"
        assert market_of("^BSESN") == "IN"
        assert market_of("^GSPC") == "US"
        assert market_of("^IXIC") == "US"
        assert market_of("^DJI") == "US"
        assert market_of("AAPL") == "US"
        assert market_of("MSFT") == "US"

        # yfinance normalization checks
        assert YFinanceProvider._normalize_symbol("LICHSGFIN") == "LICHSGFIN.NS"
        assert YFinanceProvider._normalize_symbol("RELIANCE.NS") == "RELIANCE.NS"
        assert YFinanceProvider._normalize_symbol("NIFTY") == "^NSEI"
        assert YFinanceProvider._normalize_symbol("BANKNIFTY") == "^NSEBANK"
        assert YFinanceProvider._normalize_symbol("AAPL") == "AAPL"

