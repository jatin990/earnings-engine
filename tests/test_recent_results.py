"""Tests for the Buy-the-Dip recent-results feature."""

import sqlite3
from datetime import datetime, timedelta

import pandas as pd
import pytest

from earnings_engine.config import Settings
from earnings_engine.data.recent_results import (
    MARKET_CLOSE_HOUR,
    RECENT_WINDOW_DAYS,
    _eligible_dates,
    _is_after_market,
    compute_earnings_verdicts,
    get_recent_results,
    load_recent_results,
)


@pytest.fixture
def settings(tmp_path):
    s = Settings()
    s.data_dirs = {"prices": tmp_path / "prices", "earnings": tmp_path / "earnings"}
    s.ensure_dirs()
    return s


def _db_path(settings):
    from earnings_engine.data.prices import _cache_path
    return _cache_path(settings)


# ---------------------------------------------------------------------------
# Market-close gating
# ---------------------------------------------------------------------------

def test_is_after_market_uses_cutoff_hour():
    before = datetime(2026, 5, 15, MARKET_CLOSE_HOUR - 1, 0)
    after = datetime(2026, 5, 15, MARKET_CLOSE_HOUR, 0)
    assert not _is_after_market(before)
    assert _is_after_market(after)


def test_eligible_dates_scan_recent_window():
    """The recent-results scan covers the last few days (not just yesterday), and
    today is added only after market close."""
    noon = datetime(2026, 5, 15, 12, 0)   # before close
    evng = datetime(2026, 5, 15, 17, 0)   # after close
    expected_prior = {((datetime(2026, 5, 15) - timedelta(days=i)).date()).isoformat()
                      for i in range(1, RECENT_WINDOW_DAYS)}
    assert set(_eligible_dates(noon)) == expected_prior
    assert set(_eligible_dates(evng)) == expected_prior | {"2026-05-15"}


# ---------------------------------------------------------------------------
# Seed database
# ---------------------------------------------------------------------------

_IDX = pd.bdate_range("2026-05-12", periods=10)  # 05-12 .. 05-25


def _seed(settings, events, now, idx=None):
    """Seed price_history + earnings_history.

    events: list of (ticker, earnings_date, closes_list)
    """
    conn = sqlite3.connect(str(_db_path(settings)))
    conn.execute(
        "CREATE TABLE IF NOT EXISTS price_history (ticker TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL, volume INTEGER)"
    )
    conn.execute("CREATE TABLE IF NOT EXISTS earnings_history (ticker TEXT, earnings_date TEXT, source TEXT, surprise_pct REAL, eps_reported REAL, eps_estimate REAL)")
    idx = _IDX if idx is None else idx
    for ticker, edate, closes in events:
        for i, d in enumerate(idx):
            conn.execute(
                "INSERT INTO price_history (ticker, date, open, close) VALUES (?, ?, ?, ?)",
                (ticker, d.strftime("%Y-%m-%d"), closes[i], closes[i]),
            )
        conn.execute(
            "INSERT INTO earnings_history (ticker, earnings_date, source) VALUES (?, ?, 'yfinance')",
            (ticker, edate),
        )
    conn.commit()
    conn.close()


def _now():
    return datetime(2026, 5, 15, 17, 0)  # after market close; yesterday = 05-14


# ---------------------------------------------------------------------------
# Buy-dip flag
# ---------------------------------------------------------------------------

def test_get_recent_results_marks_buy_dip(settings):
    # DIP.NS: base 100 before result, ran to 120 then pulled back to 109.
    dip_closes = [99, 100, 110, 120, 118, 112, 110, 111, 112, 109]
    # HOLD.NS: ran up and stayed near the high (no meaningful correction).
    hold_closes = [99, 100, 110, 120, 122, 121, 120, 121, 122, 121]
    _seed(settings, [
        ("DIP.NS", "2026-05-14", dip_closes),
        ("HOLD.NS", "2026-05-14", hold_closes),
    ], _now())

    result = get_recent_results(["DIP.NS", "HOLD.NS"], settings, correction_pct=5.0, now=_now())

    by_ticker = {r["ticker"]: r for r in result["rows"]}
    assert by_ticker["DIP.NS"]["is_buy_dip"] is True
    assert by_ticker["DIP.NS"]["high_pct"] == pytest.approx(20.0)  # 120/100
    assert by_ticker["DIP.NS"]["pullback_from_high"] <= -5.0
    assert by_ticker["DIP.NS"]["day_label"] == "Yesterday"

    # HOLD pulled back only ~0.8% from the high -> not a buy-dip.
    assert by_ticker["HOLD.NS"]["is_buy_dip"] is False
    assert by_ticker["HOLD.NS"]["pullback_from_high"] > -5.0


def test_get_recent_results_honors_correction_threshold(settings):
    # ~4% pullback from a 112 high: flag only when threshold <= 4%.
    closes = [99, 100, 110, 112, 110, 111, 110, 111, 112, 107.5]
    _seed(settings, [("MID.NS", "2026-05-14", closes)], _now())

    strict = get_recent_results(["MID.NS"], settings, correction_pct=3.0, now=_now())
    assert strict["rows"][0]["is_buy_dip"] is True   # -4 <= -3

    loose = get_recent_results(["MID.NS"], settings, correction_pct=10.0, now=_now())
    assert loose["rows"][0]["is_buy_dip"] is False    # -4 > -10


def test_get_recent_results_gates_today_by_market_close(settings):
    # Ticker with earnings TODAY (05-15). Shown only after market close.
    closes = [99, 100, 110, 120, 112, 110, 111, 112, 109, 108]
    _seed(settings, [("TODAY.NS", "2026-05-15", closes)], _now())

    before_close = get_recent_results(["TODAY.NS"], settings, now=datetime(2026, 5, 15, 12, 0))
    assert before_close["rows"] == []  # today's result not eligible pre-close

    after_close = get_recent_results(["TODAY.NS"], settings, now=_now())
    assert after_close["rows"][0]["day_label"] == "Today"
    assert after_close["today_count"] == 1


# ---------------------------------------------------------------------------
# API endpoint
# ---------------------------------------------------------------------------

class _FakeDatetime(datetime):
    """datetime subclass returning a fixed 'now' for the recent-results module."""

    @classmethod
    def now(cls, tz=None):
        return datetime(2026, 5, 15, 17, 0)


def test_recent_results_api_endpoint(settings, monkeypatch):
    _seed(settings, [("DIP.NS", "2026-05-14", [99, 100, 110, 120, 118, 112, 110, 111, 112, 109])], _now())
    from fastapi.testclient import TestClient
    from earnings_engine.api.server import app
    from earnings_engine.api import dashboard_api
    from earnings_engine.data import recent_results as rr_mod

    monkeypatch.setattr(dashboard_api, "_settings", lambda: settings)
    monkeypatch.setattr(dashboard_api, "_resolve_tickers", lambda market: ["DIP.NS"])
    # Freeze "now" so the endpoint sees yesterday = 05-14.
    monkeypatch.setattr(rr_mod, "datetime", _FakeDatetime)

    client = TestClient(app)
    resp = client.get("/api/v1/dashboard/recent-results?market=WATCHLIST&correction_pct=5")
    assert resp.status_code == 200
    data = resp.json()
    assert "rows" in data
    assert "buy_dip_count" in data
    assert data["buy_dip_count"] >= 1
    for row in data["rows"]:
        for key in ["ticker", "earnings_date", "day_label", "high_pct", "low_pct",
                    "current_price", "current_pct", "pullback_from_high", "momentum_3d", "is_buy_dip"]:
            assert key in row


# ---------------------------------------------------------------------------
# Buy-the-Dip: close before / next-day open / momentum (3D/7D/30D)
# ---------------------------------------------------------------------------

def test_get_recent_results_close_before_open_after_and_momentum(settings):
    # 10 trading days (05-12 .. 05-25); result on 05-14 (index 2).
    # Seed open == close so the next-day-open path is exercised.
    closes = [99, 100, 110, 120, 118, 112, 110, 111, 112, 109]
    _seed(settings, [("DIP.NS", "2026-05-14", closes)], _now())

    res = get_recent_results(["DIP.NS"], settings, correction_pct=5.0, now=_now())
    assert res["rows"], "expected at least one row"
    row = res["rows"][0]

    # result-day OHLC on 05-14 (open=close=110; high/low not seeded in test)
    assert row["result_ohlc"] == {
        "open": 110.0, "high": None, "low": None, "close": 110.0,
        "open_pct": pytest.approx((110 / 100 - 1.0) * 100), "high_pct": None,
        "low_pct": None, "close_pct": pytest.approx((110 / 100 - 1.0) * 100),
    }
    # next-day (05-15) open=close=120, % vs result-day close 110
    assert row["next_day_ohlc"] == {
        "open": 120.0, "close": 120.0,
        "open_pct": pytest.approx((120 / 110 - 1.0) * 100),
        "close_pct": pytest.approx((120 / 110 - 1.0) * 100),
    }
    assert row["earnings_date"] == "2026-05-14"

    # 3D / 7D momentum (calendar-day windows): closes[-1]=109 on 05-25 vs the
    # last close on/before 3 cal days (05-22=112) and 7 cal days (05-18=118) ago.
    assert row["momentum_3d"] == pytest.approx((109 / 112 - 1.0) * 100, abs=1e-6)
    assert row["momentum_7d"] == pytest.approx((109 / 118 - 1.0) * 100, abs=1e-6)
    # only ~2 weeks of closes -> 30 calendar days back not available
    assert row["momentum_30d"] is None


def test_get_recent_results_momentum_30d_with_long_series(settings):
    # 35 trading days ending exactly on the result date so 30-day momentum is defined.
    edate = pd.Timestamp("2026-04-15")
    long_idx = pd.bdate_range(end=edate, periods=35)  # long_idx[-1] == edate
    closes = [100 + i for i in range(35)]             # 100 .. 134
    _seed(settings, [("T30.NS", edate.strftime("%Y-%m-%d"), closes)], _now(), idx=long_idx)
    # now = next calendar day, after market close -> edate is "yesterday" and eligible
    now = datetime(2026, 4, 16, 17, 0)

    res = get_recent_results(["T30.NS"], settings, now=now)
    assert res["rows"], "expected a row for the eligible result"
    row = res["rows"][0]

    assert row["earnings_date"] == "2026-04-15"
    assert row["result_ohlc"]["close"] == pytest.approx(134.0)  # result day OHLC (high/low not seeded)
    assert row["result_ohlc"]["open"] == pytest.approx(134.0)
    assert row["result_ohlc"]["close_pct"] == pytest.approx((134 / 133 - 1.0) * 100)  # vs pre-result close 133
    assert row["next_day_ohlc"] is None                                      # no next trading day
    # Calendar-day momentum from the last close (134, 04-15): 3d -> 04-12=131,
    # 7d -> 04-08=129, 30d -> 03-16=112.
    assert row["momentum_3d"] == pytest.approx((134 / 131 - 1.0) * 100, abs=1e-6)
    assert row["momentum_7d"] == pytest.approx((134 / 129 - 1.0) * 100, abs=1e-6)
    assert row["momentum_30d"] == pytest.approx((134 / 112 - 1.0) * 100, abs=1e-6)


# ---------------------------------------------------------------------------
# Industry column + best-to-worst sort
# ---------------------------------------------------------------------------

def _seed_industry(settings, rows):
    conn = sqlite3.connect(str(_db_path(settings)))
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS tickers (
            ticker TEXT PRIMARY KEY,
            company_name TEXT,
            industry TEXT,
            sector TEXT,
            market_cap REAL,
            current_price REAL,
            earnings_fetched_at TEXT,
            prices_fetched_at TEXT,
            last_updated TEXT
        )
        """
    )
    for ticker, industry, sector in rows:
        conn.execute(
            """
            INSERT INTO tickers (ticker, industry, sector) VALUES (?, ?, ?)
            ON CONFLICT(ticker) DO UPDATE SET industry = excluded.industry, sector = excluded.sector
            """,
            (ticker, industry, sector),
        )
    conn.commit()
    conn.close()


def test_get_recent_results_includes_industry(settings):
    closes = [99, 100, 110, 120, 118, 112, 110, 111, 112, 109]
    _seed(settings, [("DIP.NS", "2026-05-14", closes)], _now())
    _seed_industry(settings, [("DIP.NS", "Software—Infrastructure", "Technology")])

    res = get_recent_results(["DIP.NS"], settings, now=_now())
    assert res["rows"][0]["industry"] == "Software—Infrastructure"


def test_get_recent_results_industry_missing_is_none(settings, monkeypatch):
    from earnings_engine.data import industry as industry_mod
    monkeypatch.setattr(industry_mod, "_fetch_for_ticker", lambda t: (t, None, None))
    closes = [99, 100, 110, 120, 118, 112, 110, 111, 112, 109]
    _seed(settings, [("NODATA.NS", "2026-05-14", closes)], _now())
    res = get_recent_results(["NODATA.NS"], settings, now=_now())
    assert res["rows"][0]["industry"] is None


def test_get_recent_results_sorted_best_to_worst(settings):
    # Both end on the same last close; pick a different final close per ticker so
    # current_pct (vs each ticker's own pre-result close = 100) is unambiguous.
    best_closes = [99, 100, 110, 115, 113, 111, 110, 112, 114, 125]   # current +25%
    mid_closes = [99, 100, 110, 115, 113, 111, 110, 112, 114, 118]    # current +18%
    worst_closes = [99, 100, 110, 115, 113, 111, 110, 112, 114, 105]  # current +5%
    _seed(settings, [
        ("BEST.NS", "2026-05-14", best_closes),
        ("MID.NS", "2026-05-14", mid_closes),
        ("WORST.NS", "2026-05-14", worst_closes),
    ], _now())

    res = get_recent_results(["BEST.NS", "MID.NS", "WORST.NS"], settings, now=_now())
    order = [r["ticker"] for r in res["rows"]]
    assert order == ["BEST.NS", "MID.NS", "WORST.NS"]
    pcts = [r["current_pct"] for r in res["rows"]]
    assert pcts == sorted(pcts, reverse=True)


# ---------------------------------------------------------------------------
# New: date-range scan, dip-then-recovery signal, opt-in verdict
# ---------------------------------------------------------------------------

def test_get_recent_results_respects_date_range(settings):
    # INRANGE reports on 05-14 (within range), OUTSIDE on 04-01 (outside range).
    _seed(settings, [
        ("INRANGE.NS", "2026-05-14", [99, 100, 101, 102, 103, 104, 105, 106, 107, 108]),
        ("OUTSIDE.NS", "2026-04-01", [10, 11, 12, 13, 14, 15, 16, 17, 18, 19]),
    ], _now())

    res = get_recent_results(
        ["INRANGE.NS", "OUTSIDE.NS"], settings,
        start_date="2026-05-10", end_date="2026-05-20", now=_now(),
    )
    tickers = {r["ticker"] for r in res["rows"]}
    assert "INRANGE.NS" in tickers
    assert "OUTSIDE.NS" not in tickers


def test_get_recent_results_marks_dip_recovery(settings):
    # DIP.NS: base (pre-result close) = 100; reaction-day open 90 (gap down ~10%),
    # closes back above its open (open == close == 90 in the seeded series) -> recovery.
    dip_closes = [99, 100, 90, 91, 92, 93, 94, 95, 96, 97]
    # HOLDDOWN.NS: reaction-day open 110 (no gap down) -> not a dip-recovery.
    hold_closes = [99, 100, 110, 108, 106, 104, 102, 100, 98, 96]
    _seed(settings, [
        ("DIPR.NS", "2026-05-14", dip_closes),
        ("NODIPR.NS", "2026-05-14", hold_closes),
    ], _now())

    res = get_recent_results(["DIPR.NS", "NODIPR.NS"], settings, drop_pct=3.0, now=_now())
    by = {r["ticker"]: r for r in res["rows"]}

    # DIPR gapped down at the open by ~10% then closed back up -> flagged.
    assert by["DIPR.NS"]["drop_at_open_pct"] is not None
    assert by["DIPR.NS"]["drop_at_open_pct"] <= -3.0
    assert by["DIPR.NS"]["closed_above_open"] is True
    assert by["DIPR.NS"]["is_dip_recovery"] is True
    # NODIPR opened above base (no gap down) -> not flagged.
    assert by["NODIPR.NS"]["is_dip_recovery"] is False


def test_compute_earnings_verdicts_uses_surprise(settings):
    _seed(settings, [("BEATV.NS", "2026-05-14", [99, 100, 101, 102, 103, 104, 105, 106, 107, 108])], _now())
    conn = sqlite3.connect(str(_db_path(settings)))
    conn.execute(
        "UPDATE earnings_history SET surprise_pct=?, eps_reported=?, eps_estimate=? WHERE ticker=?",
        (12.0, 2.24, 2.0, "BEATV.NS"),
    )
    conn.commit()
    conn.close()

    from earnings_engine.data import prices as prices_mod
    events = load_recent_results(["BEATV.NS"], settings, now=_now())
    pm = {t: prices_mod.fetch_prices(t, settings) for t, _ in events}
    v = compute_earnings_verdicts(events, pm, settings)
    assert v["BEATV.NS"]["verdict"] == "Beat"


def test_compute_earnings_verdicts_vs_sector_peers(settings):
    # No surprise present; both in the same industry so the verdict comes from the
    # peer comparison. STRONG returns more after the result than WEAK.
    weak_closes = [99, 100, 110, 108, 106, 104, 102, 100, 98, 96]
    strong_closes = [99, 100, 120, 118, 116, 114, 112, 110, 108, 106]
    _seed(settings, [
        ("WEAKV.NS", "2026-05-14", weak_closes),
        ("STRONGV.NS", "2026-05-14", strong_closes),
    ], _now())
    _seed_industry(settings, [
        ("WEAKV.NS", "Banks", "Banks"),
        ("STRONGV.NS", "Banks", "Banks"),
    ])

    from earnings_engine.data import prices as prices_mod
    events = load_recent_results(["WEAKV.NS", "STRONGV.NS"], settings, now=_now())
    pm = {t: prices_mod.fetch_prices(t, settings) for t, _ in events}
    v = compute_earnings_verdicts(events, pm, settings)
    assert v["STRONGV.NS"]["verdict"] == "Strong"
    assert v["WEAKV.NS"]["verdict"] == "Weak"


def test_compute_patterns_metrics(settings):
    _seed(settings, [
        ("POSA.NS", "2026-05-14", [99, 100, 105, 102, 101, 100, 99, 98, 97, 96]),
        ("POSB.NS", "2026-05-14", [99, 100, 106, 108, 110, 112, 114, 116, 118, 120]),
        ("NEGA.NS", "2026-05-14", [99, 100, 94, 96, 95, 94, 93, 92, 91, 90]),
    ], _now())
    _seed_industry(settings, [
        ("POSA.NS", "Tech", "Tech"),
        ("POSB.NS", "Tech", "Tech"),
        ("NEGA.NS", "Health", "Health"),
    ])

    from earnings_engine.data.recent_results import compute_patterns
    res = compute_patterns(["POSA.NS", "POSB.NS", "NEGA.NS"], settings, start_date="2026-05-10", end_date="2026-05-20")
    assert res["total"] == 3
    assert res["positive"] == 2
    assert res["negative"] == 1
    assert res["best_positive_industry"]["industry"] == "Tech"
    assert res["best_ratio_industry"]["industry"] == "Tech"
    assert res["kept_dipping_total"] == 1  # POSA ends the lookahead below its base


def _seed_ohlc(settings, ticker, edate, idx, ohlc_rows):
    conn = sqlite3.connect(str(_db_path(settings)))
    conn.execute("CREATE TABLE IF NOT EXISTS price_history (ticker TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL, volume INTEGER)")
    conn.execute("CREATE TABLE IF NOT EXISTS earnings_history (ticker TEXT, earnings_date TEXT, source TEXT)")
    for d, (o, h, l, c) in zip(idx, ohlc_rows):
        conn.execute(
            "INSERT OR REPLACE INTO price_history (ticker, date, open, high, low, close, volume) VALUES (?,?,?,?,?,?,?)",
            (ticker, d.strftime("%Y-%m-%d"), o, h, l, c, 0),
        )
    conn.execute(
        "INSERT OR REPLACE INTO earnings_history (ticker, earnings_date, source) VALUES (?,?,?)",
        (ticker, edate.strftime("%Y-%m-%d"), "yfinance"),
    )
    conn.commit()
    conn.close()


def test_compute_patterns_dip_recovery(settings):
    idx = pd.bdate_range("2026-05-12", periods=6)
    edate = idx[2]  # 05-14
    # RECOVER: positive; gapped down 05-14 (open 94 < base 102), low 92, recovered (close 103) then keeps rising.
    _seed_ohlc(settings, "RECOVER.NS", edate, idx,
               [(100, 100, 99, 100), (102, 103, 100, 102), (94, 103, 92, 103), (105, 106, 104, 105), (106, 107, 105, 106), (107, 108, 106, 107)])
    # NODIP: positive; no gap down (open 110 > base).
    _seed_ohlc(settings, "NODIP.NS", edate, idx,
               [(100, 100, 99, 100), (102, 103, 100, 102), (110, 112, 108, 111), (115, 116, 113, 115), (116, 117, 114, 116), (117, 118, 115, 117)])
    _seed_industry(settings, [
        ("RECOVER.NS", "Tech", "Tech"),
        ("NODIP.NS", "Tech", "Tech"),
    ])

    from earnings_engine.data.recent_results import compute_patterns
    res = compute_patterns(["RECOVER.NS", "NODIP.NS"], settings, start_date="2026-05-10", end_date="2026-05-20")
    by = {r["ticker"]: r for r in res["rows"]}
    assert by["RECOVER.NS"]["result_class"] == "positive"
    assert by["RECOVER.NS"]["dipped"] is True
    assert by["RECOVER.NS"]["comeback_50"] is True
    assert by["RECOVER.NS"]["kept_dipping"] is False
    assert by["NODIP.NS"]["result_class"] == "positive"
    assert by["NODIP.NS"]["dipped"] is False
    assert res["comeback_50_total"] == 1
    assert res["positive_dipped_total"] == 1


def test_prices_recent_enough_no_stamp_is_usable(settings):
    from earnings_engine.data import prices as prices_mod
    # Rows seeded directly have no fetch stamp -> must stay usable (keeps tests offline).
    assert prices_mod.prices_recent_enough("NOFETCH.NS", settings) is True


def test_prices_recent_enough_fresh_uses_cache(settings):
    from earnings_engine.data import prices as prices_mod
    prices_mod._mark_fetched("FRESH2.NS", settings)
    assert prices_mod.prices_recent_enough("FRESH2.NS", settings) is True


def test_prices_recent_enough_after_market_uses_cache(settings, monkeypatch):
    import datetime as _dt
    from earnings_engine.data import prices as prices_mod

    class _Fixed(_dt.datetime):
        fixed = _dt.datetime(2026, 5, 15, 17, 0, 0)  # after market close

        @classmethod
        def now(cls, tz=None):
            return cls(cls.fixed.year, cls.fixed.month, cls.fixed.day, cls.fixed.hour, cls.fixed.minute, cls.fixed.second)

    conn = prices_mod._connect(settings)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS tickers (
            ticker TEXT PRIMARY KEY,
            company_name TEXT,
            industry TEXT,
            sector TEXT,
            market_cap REAL,
            current_price REAL,
            earnings_fetched_at TEXT,
            prices_fetched_at TEXT,
            last_updated TEXT
        )
        """
    )
    conn.execute(
        """
        INSERT INTO tickers (ticker, prices_fetched_at) VALUES (?, ?)
        ON CONFLICT(ticker) DO UPDATE SET prices_fetched_at = excluded.prices_fetched_at
        """,
        ("OLDAM2.NS", (_dt.datetime(2026, 5, 15, 17, 0) - _dt.timedelta(days=1)).isoformat()),
    )
    conn.commit()
    conn.close()
    monkeypatch.setattr(prices_mod, "datetime", _Fixed)
    assert prices_mod.prices_recent_enough("OLDAM2.NS", settings) is True


def test_prices_recent_enough_stale_during_trading_refetches(settings, monkeypatch):
    import datetime as _dt
    from earnings_engine.data import prices as prices_mod

    class _Fixed(_dt.datetime):
        fixed = _dt.datetime(2026, 5, 15, 12, 0, 0)  # trading hours

        @classmethod
        def now(cls, tz=None):
            return cls(cls.fixed.year, cls.fixed.month, cls.fixed.day, cls.fixed.hour, cls.fixed.minute, cls.fixed.second)

    conn = prices_mod._connect(settings)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS tickers (
            ticker TEXT PRIMARY KEY,
            company_name TEXT,
            industry TEXT,
            sector TEXT,
            market_cap REAL,
            current_price REAL,
            earnings_fetched_at TEXT,
            prices_fetched_at TEXT,
            last_updated TEXT
        )
        """
    )
    conn.execute(
        """
        INSERT INTO tickers (ticker, prices_fetched_at) VALUES (?, ?)
        ON CONFLICT(ticker) DO UPDATE SET prices_fetched_at = excluded.prices_fetched_at
        """,
        ("STALE2.NS", (_dt.datetime(2026, 5, 15, 12, 0) - _dt.timedelta(days=1)).isoformat()),
    )
    conn.commit()
    conn.close()
    monkeypatch.setattr(prices_mod, "datetime", _Fixed)
    assert prices_mod.prices_recent_enough("STALE2.NS", settings) is False


