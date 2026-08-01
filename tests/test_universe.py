import pytest

from earnings_engine.config import market_of
from earnings_engine.data.universe import load_all, load_universe


def test_load_in_universe():
    tickers = load_universe("IN")
    assert len(tickers) >= 40
    assert all(t.endswith(".NS") for t in tickers)


def test_us_universe_is_supported():
    tickers = load_universe("US")
    assert len(tickers) >= 40
    assert not any(t.endswith(".NS") for t in tickers)


def test_load_all_combines_both_universes():
    assert len(load_all()) == len(load_universe("IN")) + len(load_universe("US"))


def test_market_of():
    assert market_of("RELIANCE.NS") == "IN"
    assert market_of("AAPL") == "US"
