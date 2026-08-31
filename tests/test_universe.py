import pytest

from earnings_engine.config import Settings, market_of
from earnings_engine.data.universe import (
    add_to_universe,
    get_universe,
    ingest_market_caps,
    is_market_cap_fresh,
    is_universe_fresh,
    list_universes,
    load_all,
    load_all_market_caps,
    load_market_cap,
    load_nse_all,
    load_nse_large_cap,
    load_universe,
    remove_from_universe,
    store_market_cap,
    store_universe,
)


@pytest.fixture
def u_settings(tmp_path):
    """Settings with temporary SQLite database directory."""
    s = Settings()
    s.data_dirs = {"prices": tmp_path / "prices", "earnings": tmp_path / "earnings"}
    s.ensure_dirs()
    return s


def test_load_in_universe(u_settings):
    tickers = load_universe("IN", settings=u_settings)
    assert len(tickers) >= 40
    assert all(t.endswith(".NS") for t in tickers)


def test_us_universe_is_supported(u_settings):
    tickers = load_universe("US", settings=u_settings)
    assert len(tickers) >= 40
    assert not any(t.endswith(".NS") for t in tickers)


def test_load_all_combines_both_universes(u_settings):
    assert len(load_all(settings=u_settings)) == len(load_universe("IN", settings=u_settings)) + len(load_universe("US", settings=u_settings))


def test_market_of():
    assert market_of("RELIANCE.NS") == "IN"
    assert market_of("AAPL") == "US"


def test_sqlite_universe_crud(u_settings):
    # 1. Store a custom universe in SQLite
    store_universe("tech_stocks", ["TCS.NS", "INFY.NS", "WIPRO.NS"], settings=u_settings)
    assert get_universe("tech_stocks", settings=u_settings) == ["TCS.NS", "INFY.NS", "WIPRO.NS"]

    # 2. Add ticker to universe
    add_to_universe("tech_stocks", "HCLTECH.NS", settings=u_settings)
    assert "HCLTECH.NS" in get_universe("tech_stocks", settings=u_settings)

    # 3. Remove ticker from universe
    remove_from_universe("tech_stocks", "WIPRO.NS", settings=u_settings)
    assert "WIPRO.NS" not in get_universe("tech_stocks", settings=u_settings)

    # 4. List universes
    all_univs = list_universes(settings=u_settings)
    names = [u["name"] for u in all_univs]
    assert "tech_stocks" in names
    assert "IN" in names
    assert "US" in names

    # 5. Load universe via load_universe
    loaded = load_universe("tech_stocks", settings=u_settings)
    assert loaded == ["TCS.NS", "INFY.NS", "HCLTECH.NS"]


def test_load_nse_all_uses_sqlite_cache_when_fresh(monkeypatch, u_settings):
    """Test that load_nse_all uses cached SQLite rows when fresh."""
    from earnings_engine.data import universe as universe_mod

    # Pre-store NSE_ALL in SQLite
    store_universe("NSE_ALL", ["RELIANCE.NS", "TCS.NS", "INFY.NS"], settings=u_settings)

    # Mock _fetch_nse_all_from_nsetools to ensure it is NOT called
    def _mock_fetch():
        raise AssertionError("Should not fetch from nsetools when SQLite cache is fresh")

    monkeypatch.setattr(universe_mod, "_fetch_nse_all_from_nsetools", _mock_fetch)

    tickers = load_nse_all(force_refresh=False, settings=u_settings)
    assert tickers == ["RELIANCE.NS", "TCS.NS", "INFY.NS"]


def test_load_nse_all_refreshes_when_forced(monkeypatch, u_settings):
    """Test that load_nse_all refreshes from nsetools when forced."""
    from earnings_engine.data import universe as universe_mod

    # Pre-store old data
    store_universe("NSE_ALL", ["OLD.NS"], settings=u_settings)

    # Mock fetch to return new tickers
    monkeypatch.setattr(universe_mod, "_fetch_nse_all_from_nsetools", lambda: ["NEW1.NS", "NEW2.NS"])

    tickers = load_nse_all(force_refresh=True, settings=u_settings)
    assert tickers == ["NEW1.NS", "NEW2.NS"]
    assert get_universe("NSE_ALL", settings=u_settings) == ["NEW1.NS", "NEW2.NS"]


def test_load_nse_large_cap_uses_sqlite_cache_when_fresh(monkeypatch, u_settings):
    """Test that load_nse_large_cap uses SQLite cache when fresh."""
    from earnings_engine.data import universe as universe_mod

    # Pre-store in SQLite
    store_universe("NSE_LARGE_CAP", ["RELIANCE.NS", "TCS.NS"], settings=u_settings)

    def _mock_fetch(settings=None):
        raise AssertionError("Should not fetch from yfinance when SQLite cache is fresh")

    monkeypatch.setattr(universe_mod, "_fetch_nse_large_cap_from_yfinance", _mock_fetch)

    tickers = load_nse_large_cap(force_refresh=False, settings=u_settings)
    assert tickers == ["RELIANCE.NS", "TCS.NS"]


# ---------------------------------------------------------------------------
# Market cap caching tests
# ---------------------------------------------------------------------------

def test_store_and_load_market_cap(u_settings):
    """Test that market cap can be stored and loaded from SQLite."""
    store_market_cap("TEST.NS", 1_000_000_000, u_settings)
    result = load_market_cap("TEST.NS", u_settings)
    assert result == 1_000_000_000


def test_market_cap_freshness(u_settings):
    """Test that market cap freshness check works."""
    assert not is_market_cap_fresh("FRESH_TEST.NS", u_settings)
    store_market_cap("FRESH_TEST.NS", 1_000_000_000, u_settings)
    assert is_market_cap_fresh("FRESH_TEST.NS", u_settings)


def test_market_cap_not_found(u_settings):
    """Test that load_market_cap returns None for unknown ticker."""
    result = load_market_cap("UNKNOWN.NS", u_settings)
    assert result is None


def test_load_all_market_caps(u_settings):
    """Test that load_all_market_caps returns all cached market caps."""
    store_market_cap("A.NS", 1_000, u_settings)
    store_market_cap("B.NS", 2_000, u_settings)
    store_market_cap("C.NS", None, u_settings)

    result = load_all_market_caps(u_settings)
    assert result.get("A.NS") == 1_000
    assert result.get("B.NS") == 2_000
    assert "C.NS" not in result


def test_ingest_market_caps_uses_cache(u_settings, monkeypatch):
    """Test that ingest_market_caps skips tickers with fresh cache."""
    store_market_cap("CACHED.NS", 5_000_000_000, u_settings)

    from earnings_engine.data import universe as universe_mod

    def _mock_fetch(ticker):
        if ticker == "CACHED.NS":
            raise AssertionError("Should not fetch cached ticker")
        return (ticker, 3_000_000_000)

    monkeypatch.setattr(universe_mod, "_fetch_market_cap_for_ticker", _mock_fetch)

    results = ingest_market_caps(["CACHED.NS", "NEW.NS"], force=False, settings=u_settings)
    assert results["CACHED.NS"] == 1
    assert results["NEW.NS"] == 1


def test_groww_benchmark_indices(u_settings):
    """Test resolution and constituent scaling of Groww-style indices."""
    nifty_50 = load_universe("NIFTY_50", settings=u_settings)
    assert len(nifty_50) >= 50
    assert "RELIANCE.NS" in nifty_50
    assert "TCS.NS" in nifty_50

    nifty_next_50 = load_universe("NIFTY_NEXT_50", settings=u_settings)
    assert len(nifty_next_50) >= 45
    assert "HAL.NS" in nifty_next_50 or "DLF.NS" in nifty_next_50

    nifty_100 = load_universe("NIFTY_100", settings=u_settings)
    assert len(nifty_100) >= 95

    nifty_200 = load_universe("NIFTY_200", settings=u_settings)
    assert len(nifty_200) >= 180

    mid_cap = load_universe("NSE_MID_CAP", settings=u_settings)
    assert len(mid_cap) >= 80

    small_cap = load_universe("NSE_SMALL_CAP", settings=u_settings)
    assert len(small_cap) >= 70

