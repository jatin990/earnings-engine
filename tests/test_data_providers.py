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
