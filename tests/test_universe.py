import pytest

from earnings_engine.config import Settings, market_of
from earnings_engine.data.universe import (
    ingest_market_caps,
    is_market_cap_fresh,
    load_all,
    load_all_market_caps,
    load_market_cap,
    load_nse_all,
    load_universe,
    store_market_cap,
)


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


def test_load_nse_all_uses_cache_when_fresh(monkeypatch, tmp_path):
    """Test that load_nse_all uses cached file when it's fresh."""
    from earnings_engine.data import universe as universe_mod

    # Create a fresh cache file
    cache_file = tmp_path / "nse_all.txt"
    cache_file.write_text("RELIANCE.NS\nTCS.NS\nINFY.NS\n", encoding="utf-8")

    # Patch the NSE_ALL_FILE path to point to our temp file
    monkeypatch.setattr(universe_mod, "NSE_ALL_FILE", cache_file)

    # Mock _fetch_nse_all_from_nsetools to ensure it's NOT called
    def _mock_fetch():
        raise AssertionError("Should not fetch from nsetools when cache is fresh")

    monkeypatch.setattr(universe_mod, "_fetch_nse_all_from_nsetools", _mock_fetch)

    tickers = load_nse_all()
    assert tickers == ["RELIANCE.NS", "TCS.NS", "INFY.NS"]


def test_load_nse_all_refreshes_when_stale(monkeypatch, tmp_path):
    """Test that load_nse_all refreshes from nsetools when cache is stale."""
    from earnings_engine.data import universe as universe_mod
    import os
    import time

    # Create a stale cache file (modify mtime to 45 days ago, exceeding NSE_ALL_MAX_AGE_DAYS=40)
    cache_file = tmp_path / "nse_all.txt"
    cache_file.write_text("OLD.NS\n", encoding="utf-8")
    old_time = time.time() - (45 * 24 * 60 * 60)  # 45 days ago
    os.utime(cache_file, (old_time, old_time))

    # Patch the NSE_ALL_FILE path
    monkeypatch.setattr(universe_mod, "NSE_ALL_FILE", cache_file)

    # Mock _fetch_nse_all_from_nsetools to return new tickers
    def _mock_fetch():
        return ["NEW1.NS", "NEW2.NS", "NEW3.NS"]

    monkeypatch.setattr(universe_mod, "_fetch_nse_all_from_nsetools", _mock_fetch)

    tickers = load_nse_all()
    assert tickers == ["NEW1.NS", "NEW2.NS", "NEW3.NS"]
    # Verify the cache file was updated
    assert "NEW1.NS" in cache_file.read_text(encoding="utf-8")


def test_load_nse_all_fetches_when_no_cache(monkeypatch, tmp_path):
    """Test that load_nse_all fetches from nsetools when no cache exists."""
    from earnings_engine.data import universe as universe_mod

    # Point to a non-existent file
    cache_file = tmp_path / "nse_all.txt"
    monkeypatch.setattr(universe_mod, "NSE_ALL_FILE", cache_file)

    # Mock _fetch_nse_all_from_nsetools
    def _mock_fetch():
        return ["FRESH1.NS", "FRESH2.NS"]

    monkeypatch.setattr(universe_mod, "_fetch_nse_all_from_nsetools", _mock_fetch)

    tickers = load_nse_all()
    assert tickers == ["FRESH1.NS", "FRESH2.NS"]
    # Verify the cache file was created
    assert cache_file.exists()
    assert "FRESH1.NS" in cache_file.read_text(encoding="utf-8")


def test_load_nse_all_falls_back_on_error(monkeypatch, tmp_path):
    """Test that load_nse_all falls back to cached file when nsetools fails."""
    from earnings_engine.data import universe as universe_mod

    # Create a cache file with existing data
    cache_file = tmp_path / "nse_all.txt"
    cache_file.write_text("CACHED.NS\n", encoding="utf-8")
    monkeypatch.setattr(universe_mod, "NSE_ALL_FILE", cache_file)

    # Mock _fetch_nse_all_from_nsetools to raise an exception
    def _mock_fetch():
        raise Exception("Network error")

    monkeypatch.setattr(universe_mod, "_fetch_nse_all_from_nsetools", _mock_fetch)

    # Force refresh by making the file stale
    import os
    import time
    old_time = time.time() - (8 * 24 * 60 * 60)
    os.utime(cache_file, (old_time, old_time))

    tickers = load_nse_all()
    assert tickers == ["CACHED.NS"]


def test_load_universe_nse_all(monkeypatch, tmp_path):
    """Test that load_universe('NSE_ALL') calls load_nse_all()."""
    from earnings_engine.data import universe as universe_mod

    # Mock load_nse_all to return a known list
    monkeypatch.setattr(universe_mod, "load_nse_all", lambda: ["TEST1.NS", "TEST2.NS"])

    tickers = load_universe("NSE_ALL")
    assert tickers == ["TEST1.NS", "TEST2.NS"]


def test_load_nse_large_cap_uses_cache_when_fresh(monkeypatch, tmp_path):
    """Test that load_nse_large_cap uses cached file when it's fresh."""
    from earnings_engine.data import universe as universe_mod

    # Create a fresh cache file
    cache_file = tmp_path / "nse_large_cap.txt"
    cache_file.write_text("RELIANCE.NS\nTCS.NS\nINFY.NS\n", encoding="utf-8")

    # Patch the NSE_LARGE_CAP_FILE path to point to our temp file
    monkeypatch.setattr(universe_mod, "NSE_LARGE_CAP_FILE", cache_file)

    # Mock _fetch_nse_large_cap_from_yfinance to ensure it's NOT called
    def _mock_fetch():
        raise AssertionError("Should not fetch from yfinance when cache is fresh")

    monkeypatch.setattr(universe_mod, "_fetch_nse_large_cap_from_yfinance", _mock_fetch)

    tickers = universe_mod.load_nse_large_cap()
    assert tickers == ["RELIANCE.NS", "TCS.NS", "INFY.NS"]


def test_load_nse_large_cap_refreshes_when_stale(monkeypatch, tmp_path):
    """Test that load_nse_large_cap refreshes from yfinance when cache is stale."""
    from earnings_engine.data import universe as universe_mod
    import os
    import time

    # Create a stale cache file (modify mtime to 45 days ago, exceeding NSE_ALL_MAX_AGE_DAYS=40)
    cache_file = tmp_path / "nse_large_cap.txt"
    cache_file.write_text("OLD.NS\n", encoding="utf-8")
    old_time = time.time() - (45 * 24 * 60 * 60)  # 45 days ago
    os.utime(cache_file, (old_time, old_time))

    # Patch the NSE_LARGE_CAP_FILE path
    monkeypatch.setattr(universe_mod, "NSE_LARGE_CAP_FILE", cache_file)

    # Mock _fetch_nse_large_cap_from_yfinance to return new tickers
    def _mock_fetch():
        return ["NEW1.NS", "NEW2.NS", "NEW3.NS"]

    monkeypatch.setattr(universe_mod, "_fetch_nse_large_cap_from_yfinance", _mock_fetch)

    tickers = universe_mod.load_nse_large_cap()
    assert tickers == ["NEW1.NS", "NEW2.NS", "NEW3.NS"]
    # Verify the cache file was updated
    assert "NEW1.NS" in cache_file.read_text(encoding="utf-8")


def test_load_nse_large_cap_fetches_when_no_cache(monkeypatch, tmp_path):
    """Test that load_nse_large_cap fetches from yfinance when no cache exists."""
    from earnings_engine.data import universe as universe_mod

    # Point to a non-existent file
    cache_file = tmp_path / "nse_large_cap.txt"
    monkeypatch.setattr(universe_mod, "NSE_LARGE_CAP_FILE", cache_file)

    # Mock _fetch_nse_large_cap_from_yfinance
    def _mock_fetch():
        return ["FRESH1.NS", "FRESH2.NS"]

    monkeypatch.setattr(universe_mod, "_fetch_nse_large_cap_from_yfinance", _mock_fetch)

    tickers = universe_mod.load_nse_large_cap()
    assert tickers == ["FRESH1.NS", "FRESH2.NS"]
    # Verify the cache file was created
    assert cache_file.exists()
    assert "FRESH1.NS" in cache_file.read_text(encoding="utf-8")


def test_load_nse_large_cap_falls_back_on_error(monkeypatch, tmp_path):
    """Test that load_nse_large_cap falls back to cached file when yfinance fails."""
    from earnings_engine.data import universe as universe_mod

    # Create a cache file with existing data
    cache_file = tmp_path / "nse_large_cap.txt"
    cache_file.write_text("CACHED.NS\n", encoding="utf-8")
    monkeypatch.setattr(universe_mod, "NSE_LARGE_CAP_FILE", cache_file)

    # Mock _fetch_nse_large_cap_from_yfinance to raise an exception
    def _mock_fetch():
        raise Exception("Network error")

    monkeypatch.setattr(universe_mod, "_fetch_nse_large_cap_from_yfinance", _mock_fetch)

    # Force refresh by making the file stale
    import os
    import time
    old_time = time.time() - (8 * 24 * 60 * 60)
    os.utime(cache_file, (old_time, old_time))

    tickers = universe_mod.load_nse_large_cap()
    assert tickers == ["CACHED.NS"]


def test_load_universe_nse_large_cap(monkeypatch, tmp_path):
    """Test that load_universe('NSE_LARGE_CAP') calls load_nse_large_cap()."""
    from earnings_engine.data import universe as universe_mod

    # Mock load_nse_large_cap to return a known list
    monkeypatch.setattr(universe_mod, "load_nse_large_cap", lambda: ["LARGE1.NS", "LARGE2.NS"])

    tickers = load_universe("NSE_LARGE_CAP")
    assert tickers == ["LARGE1.NS", "LARGE2.NS"]


# ---------------------------------------------------------------------------
# Market cap caching tests
# ---------------------------------------------------------------------------

@pytest.fixture
def mc_settings(tmp_path):
    """Settings with temp data dirs for market cap cache testing."""
    s = Settings()
    s.data_dirs = {"prices": tmp_path / "prices", "earnings": tmp_path / "earnings"}
    s.ensure_dirs()
    return s


def test_store_and_load_market_cap(mc_settings):
    """Test that market cap can be stored and loaded from SQLite."""
    store_market_cap("TEST.NS", 1_000_000_000, mc_settings)
    result = load_market_cap("TEST.NS", mc_settings)
    assert result == 1_000_000_000


def test_market_cap_freshness(mc_settings):
    """Test that market cap freshness check works."""
    # Not fresh before storing
    assert not is_market_cap_fresh("TEST.NS", mc_settings)

    # Fresh after storing
    store_market_cap("TEST.NS", 1_000_000_000, mc_settings)
    assert is_market_cap_fresh("TEST.NS", mc_settings)


def test_market_cap_not_found(mc_settings):
    """Test that load_market_cap returns None for unknown ticker."""
    result = load_market_cap("UNKNOWN.NS", mc_settings)
    assert result is None


def test_load_all_market_caps(mc_settings):
    """Test that load_all_market_caps returns all cached market caps."""
    store_market_cap("A.NS", 1_000, mc_settings)
    store_market_cap("B.NS", 2_000, mc_settings)
    store_market_cap("C.NS", None, mc_settings)  # None should be excluded

    result = load_all_market_caps(mc_settings)
    assert result == {"A.NS": 1_000, "B.NS": 2_000}


def test_ingest_market_caps_uses_cache(mc_settings, monkeypatch):
    """Test that ingest_market_caps skips tickers with fresh cache."""
    # Pre-populate cache
    store_market_cap("CACHED.NS", 5_000_000_000, mc_settings)

    # Mock is_market_cap_fresh to use our test settings
    from earnings_engine.data import universe as universe_mod

    original_is_fresh = universe_mod.is_market_cap_fresh
    original_load_mc = universe_mod.load_market_cap

    def _mock_is_fresh(ticker, settings=None):
        return original_is_fresh(ticker, mc_settings)

    def _mock_load_mc(ticker, settings=None):
        return original_load_mc(ticker, mc_settings)

    monkeypatch.setattr(universe_mod, "is_market_cap_fresh", _mock_is_fresh)
    monkeypatch.setattr(universe_mod, "load_market_cap", _mock_load_mc)

    # Mock _fetch_market_cap_for_ticker to raise if called for cached ticker
    def _mock_fetch(ticker):
        if ticker == "CACHED.NS":
            raise AssertionError("Should not fetch cached ticker")
        return (ticker, 3_000_000_000)

    monkeypatch.setattr(universe_mod, "_fetch_market_cap_for_ticker", _mock_fetch)

    results = ingest_market_caps(["CACHED.NS", "NEW.NS"], force=False, settings=mc_settings)
    assert results["CACHED.NS"] == 1
    assert results["NEW.NS"] == 1
