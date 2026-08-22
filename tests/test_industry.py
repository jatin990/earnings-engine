"""Tests for industry classification caching (yfinance -> SQLite)."""

import pytest

from earnings_engine.config import Settings
from earnings_engine.data import industry as industry_mod


@pytest.fixture
def settings(tmp_path):
    s = Settings()
    s.data_dirs = {"prices": tmp_path / "prices", "earnings": tmp_path / "earnings"}
    s.ensure_dirs()
    return s


class FakeInfoTicker:
    """yfinance Ticker stub whose .info carries industry + sector keys."""

    def __init__(self, symbol):
        self._symbol = symbol
        self.info = {"industry": "Banks", "sector": "Financial Services"}


class FakeInfoTickerNoIndustry:
    """yfinance Ticker stub with no industry -> must fall back to sector."""

    def __init__(self, symbol):
        self._symbol = symbol
        self.info = {"industry": None, "sector": "Technology"}


def test_fetch_and_cache_industry(settings):
    ticker = "RELIANCE.NS"
    # Verify the store/load/freshness round-trip.
    industry_mod._store(ticker, "Banks", "Financial Services", settings)
    assert industry_mod.load_industry(ticker, settings) == "Banks"
    assert industry_mod._is_fresh(ticker, settings)


def test_fetch_industry_uses_industry_then_falls_back_to_sector(monkeypatch):
    monkeypatch.setattr(industry_mod.yf, "Ticker", FakeInfoTicker)
    ticker, industry, sector = industry_mod._fetch_for_ticker("A.NS")
    assert industry == "Banks"
    assert sector == "Financial Services"

    monkeypatch.setattr(industry_mod.yf, "Ticker", FakeInfoTickerNoIndustry)
    ticker, industry2, sector2 = industry_mod._fetch_for_ticker("B.NS")
    assert industry2 is None
    assert sector2 == "Technology"


def test_ingest_industries_caches_and_skips_fresh(settings, monkeypatch):
    monkeypatch.setattr(industry_mod.yf, "Ticker", FakeInfoTicker)
    res = industry_mod.ingest_industries(["RELIANCE.NS", "TCS.NS"], settings)
    assert res["RELIANCE.NS"] == 1
    assert res["TCS.NS"] == 1

    indmap = industry_mod.load_industry_map(["RELIANCE.NS", "TCS.NS"], settings)
    assert indmap["RELIANCE.NS"] == "Banks"
    assert indmap["TCS.NS"] == "Banks"

    # Second call should be a pure cache hit (no fetch over the wire).
    res2 = industry_mod.ingest_industries(["RELIANCE.NS", "TCS.NS"], settings, force=False)
    assert res2["RELIANCE.NS"] == 1 and res2["TCS.NS"] == 1


def test_get_industry_map_fetches_missing_only(settings, monkeypatch):
    # Pre-seed one ticker so it must NOT be re-fetched.
    industry_mod._store("CACHED.NS", "Energy", None, settings)
    monkeypatch.setattr(industry_mod.yf, "Ticker", FakeInfoTicker)

    indmap = industry_mod.get_industry_map(["CACHED.NS", "NEW.NS"], settings)
    assert indmap["CACHED.NS"] == "Energy"  # from cache
    assert indmap["NEW.NS"] == "Banks"      # fetched + cached
