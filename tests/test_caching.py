import pandas as pd
import pytest

from earnings_engine.config import Settings
from earnings_engine.data import earnings as earnings_mod
from earnings_engine.data import prices as prices_mod


@pytest.fixture
def settings(tmp_path):
    s = Settings()
    s.data_dirs = {"prices": tmp_path / "prices", "earnings": tmp_path / "earnings"}
    s.ensure_dirs()
    return s


def test_prices_cache_roundtrip(settings, monkeypatch):
    fake = pd.DataFrame(
        {"Open": [1.0], "High": [2.0], "Low": [0.5], "Close": [1.5], "Volume": [100]},
        index=pd.DatetimeIndex(["2024-01-02"], name="Date"),
    )
    calls = {"n": 0}

    def fake_download(*args, **kwargs):
        calls["n"] += 1
        return fake.copy()

    monkeypatch.setattr(prices_mod.yf, "download", fake_download)

    df1 = prices_mod.fetch_prices("TEST", settings)
    assert list(df1.columns) == ["open", "high", "low", "close", "volume"]
    assert calls["n"] == 1

    # Second call within freshness window must hit the cache, not the network.
    df2 = prices_mod.fetch_prices("TEST", settings)
    assert calls["n"] == 1
    pd.testing.assert_frame_equal(df1, df2)

    # load_prices reads cache without network.
    df3 = prices_mod.load_prices("TEST", settings)
    pd.testing.assert_frame_equal(df1, df3)


def test_earnings_normalize_and_upcoming(settings, monkeypatch):
    future = pd.Timestamp.today().normalize() + pd.Timedelta(days=5)
    raw = pd.DataFrame(
        {
            "EPS Estimate": [1.0, 2.0],
            "Reported EPS": [1.1, None],
            "Surprise(%)": [10.0, None],
        },
        index=pd.DatetimeIndex([pd.Timestamp("2024-01-15"), future], name="Earnings Date").tz_localize("UTC"),
    )

    class FakeTicker:
        def __init__(self, symbol):
            pass

        def get_earnings_dates(self, limit=60):
            return raw

    monkeypatch.setattr(earnings_mod.yf, "Ticker", FakeTicker)

    df = earnings_mod.fetch_earnings("TEST", settings)
    assert list(df.columns) == earnings_mod.COLUMNS
    assert len(df) == 2
    assert df["earnings_date"].dt.tz is None

    upcoming = earnings_mod.upcoming_earnings(["TEST"], settings, days=14)
    assert len(upcoming) == 1
    assert upcoming.iloc[0]["ticker"] == "TEST"


def test_earnings_mixed_timezone_offsets(settings, monkeypatch):
    # US tickers return mixed EDT/EST offsets across a year; normalization
    # must not choke on the resulting object-dtype index.
    raw = pd.DataFrame(
        {"EPS Estimate": [1.9, 2.67], "Reported EPS": [None, 2.84], "Surprise(%)": [None, 6.25]},
        index=pd.Index(
            [pd.Timestamp("2026-07-30 16:00:00-04:00"), pd.Timestamp("2026-01-29 16:00:00-05:00")],
            name="Earnings Date",
        ),
    )

    class FakeTicker:
        def __init__(self, symbol):
            pass

        def get_earnings_dates(self, limit=60):
            return raw

    monkeypatch.setattr(earnings_mod.yf, "Ticker", FakeTicker)
    df = earnings_mod.fetch_earnings("MIXED", settings)
    assert len(df) == 2
    assert df["earnings_date"].dt.tz is None


def test_upcoming_earnings_no_duplicates(settings, monkeypatch):
    # A ticker appearing more than once in the input list (e.g. overlapping
    # watchlist + market universes) must not produce duplicate result rows.
    future = pd.Timestamp.today().normalize() + pd.Timedelta(days=5)
    raw = pd.DataFrame(
        {
            "EPS Estimate": [1.0],
            "Reported EPS": [1.1],
            "Surprise(%)": [10.0],
        },
        index=pd.DatetimeIndex([future], name="Earnings Date").tz_localize("UTC"),
    )

    class FakeTicker:
        def __init__(self, symbol):
            pass

        def get_earnings_dates(self, limit=60):
            return raw

    monkeypatch.setattr(earnings_mod.yf, "Ticker", FakeTicker)
    earnings_mod.fetch_earnings("DUP", settings)

    upcoming = earnings_mod.upcoming_earnings(["DUP", "DUP", "DUP"], settings, days=14)
    assert len(upcoming) == 1
    assert upcoming.iloc[0]["ticker"] == "DUP"


def test_earnings_empty_result_cached(settings, monkeypatch):
    calls = {"n": 0}

    class FakeTicker:
        def __init__(self, symbol):
            pass

        def get_earnings_dates(self, limit=60):
            calls["n"] += 1
            return None

    monkeypatch.setattr(earnings_mod.yf, "Ticker", FakeTicker)

    df = earnings_mod.fetch_earnings("NODATA", settings)
    assert df.empty
    assert calls["n"] == 1
    # Cached empty frame prevents repeat network calls.
    earnings_mod.fetch_earnings("NODATA", settings)
    assert calls["n"] == 1


def test_upcoming_earnings_with_start_date(settings, monkeypatch):
    """start_date shifts the look-ahead window from today to the given date."""
    # Two future events: one 20 days out, one 40 days out.
    d20 = pd.Timestamp.today().normalize() + pd.Timedelta(days=20)
    d40 = pd.Timestamp.today().normalize() + pd.Timedelta(days=40)
    raw = pd.DataFrame(
        {
            "EPS Estimate": [1.0, 2.0],
            "Reported EPS": [1.1, 2.1],
            "Surprise(%)": [10.0, 12.0],
        },
        index=pd.DatetimeIndex([d20, d40], name="Earnings Date").tz_localize("UTC"),
    )

    class FakeTicker:
        def __init__(self, symbol):
            pass

        def get_earnings_dates(self, limit=60):
            return raw

    monkeypatch.setattr(earnings_mod.yf, "Ticker", FakeTicker)
    earnings_mod.fetch_earnings("DATED", settings)

    # Default (today, days=14): window [today, today+14] -> neither 20d nor 40d out.
    upcoming = earnings_mod.upcoming_earnings(["DATED"], settings, days=14)
    assert len(upcoming) == 0

    # start_date = today+18 with days=5 -> window [today+18, today+23] -> only d20.
    start = (pd.Timestamp.today().normalize() + pd.Timedelta(days=18)).strftime("%Y-%m-%d")
    upcoming2 = earnings_mod.upcoming_earnings(["DATED"], settings, days=5, start_date=start)
    assert len(upcoming2) == 1
    assert upcoming2.iloc[0]["earnings_date"].date() == d20.date()

    # start_date = today+18 with days=25 -> window [today+18, today+43] -> both events.
    start2 = (pd.Timestamp.today().normalize() + pd.Timedelta(days=18)).strftime("%Y-%m-%d")
    upcoming3 = earnings_mod.upcoming_earnings(["DATED"], settings, days=25, start_date=start2)
    assert len(upcoming3) == 2


def test_prices_delta_fetch_merges_not_wipes(settings, monkeypatch):
    """A forced refresh on a ticker with cached rows must download only the
    missing delta and merge it into the existing history (not delete+reinsert)."""
    # Seed the cache with an old row directly.
    old = pd.DataFrame(
        {"open": [10.0], "high": [11.0], "low": [9.0], "close": [10.5], "volume": [1000]},
        index=pd.DatetimeIndex(["2024-01-02"], name="date"),
    )
    prices_mod._write_prices("DELTA", settings, old)

    # The delta download returns a NEWER date (2024-01-03) only.
    new = pd.DataFrame(
        {"Open": [10.5], "High": [11.5], "Low": [9.5], "Close": [11.0], "Volume": [1200]},
        index=pd.DatetimeIndex(["2024-01-03"], name="Date"),
    )
    captured = {}

    def fake_download(*args, **kwargs):
        captured["start"] = kwargs.get("start")
        return new.copy()

    monkeypatch.setattr(prices_mod.yf, "download", fake_download)

    # force=True bypasses the freshness check so the delta path runs.
    df = prices_mod.fetch_prices("DELTA", settings, force=True)

    # The download start should be near the last cached date (delta), not 2015.
    assert captured["start"] is not None
    assert captured["start"] > "2015-01-01"
    # Both the old and new rows must be present (merge, not wipe).
    assert len(df) == 2
    assert "2024-01-02" in [d.strftime("%Y-%m-%d") for d in df.index]
    assert "2024-01-03" in [d.strftime("%Y-%m-%d") for d in df.index]


def test_prices_full_fetch_when_no_cache(settings, monkeypatch):
    """A ticker with no cached rows must download full history from history_start."""
    full = pd.DataFrame(
        {"Open": [1.0], "High": [2.0], "Low": [0.5], "Close": [1.5], "Volume": [100]},
        index=pd.DatetimeIndex(["2024-01-02"], name="Date"),
    )
    captured = {}

    def fake_download(*args, **kwargs):
        captured["start"] = kwargs.get("start")
        return full.copy()

    monkeypatch.setattr(prices_mod.yf, "download", fake_download)

    df = prices_mod.fetch_prices("FRESH", settings)
    assert captured["start"] == settings.history_start
    assert len(df) == 1
