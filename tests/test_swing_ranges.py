import sqlite3
import pytest
import pandas as pd
from fastapi.testclient import TestClient

from earnings_engine.config import Settings
from earnings_engine.data.swing_ranges import (
    get_swing_range,
    set_user_range,
    record_auto_range,
    clear_user_range,
    list_ranges,
    get_cycle_history,
)
from earnings_engine.api.dashboard_api import (
    get_swing_range_api,
    set_swing_range_api,
    clear_swing_range_api,
    get_swing_cycle_history_api,
    list_swing_ranges_api,
    get_swing_setups,
)
from earnings_engine.api.server import app


@pytest.fixture
def test_settings(tmp_path):
    s = Settings()
    s.data_dirs["prices"] = tmp_path
    s.ensure_dirs()
    return s


def test_user_range_crud(test_settings):
    # Set user range
    res = set_user_range("test_list", "AAPL", 150.0, 160.0, cycles=3, settings=test_settings)
    assert res["success"] is True
    assert res["lower_bound"] == 150.0

    # Get it back
    rng = get_swing_range("test_list", "AAPL", settings=test_settings)
    assert rng is not None
    assert rng["lower_bound"] == 150.0
    assert rng["upper_bound"] == 160.0
    assert rng["source"] == "user"
    assert rng["cycles"] == 3

    # List ranges
    all_rngs = list_ranges("test_list", settings=test_settings)
    assert len(all_rngs) == 1
    assert all_rngs[0]["ticker"] == "AAPL"

    # Clear it
    clear_user_range("test_list", "AAPL", settings=test_settings)
    assert get_swing_range("test_list", "AAPL", settings=test_settings) is None


def test_auto_range_protection(test_settings):
    # Record auto range
    record_auto_range("test_list", "AAPL", 140.0, 150.0, cycles=2, settings=test_settings)
    rng = get_swing_range("test_list", "AAPL", settings=test_settings)
    assert rng is not None
    assert rng["source"] == "auto"
    assert rng["lower_bound"] == 140.0

    # Set user override
    set_user_range("test_list", "AAPL", 150.0, 160.0, settings=test_settings)

    # Try recording auto again - should be IGNORED
    record_auto_range("test_list", "AAPL", 145.0, 155.0, settings=test_settings)
    rng = get_swing_range("test_list", "AAPL", settings=test_settings)
    assert rng is not None
    assert rng["source"] == "user"
    assert rng["lower_bound"] == 150.0


def test_cycle_history(test_settings):
    cycles = [
        {"start": "2023-01-01", "end": "2023-01-10", "duration": 9, "lower": 140.0, "upper": 150.0},
        {"start": "2023-02-01", "end": "2023-02-15", "duration": 14, "lower": 142.0, "upper": 155.0},
    ]
    record_auto_range(
        "test_list", "AAPL", 140.0, 155.0,
        cycles=2, avg_days=11.5, cycles_data=cycles,
        settings=test_settings,
    )

    hist = get_cycle_history("test_list", "AAPL", settings=test_settings)
    assert len(hist) == 2
    assert hist[0]["duration"] == 9
    assert hist[1]["duration"] == 14
    assert hist[0]["start"] == "2023-01-01"


def test_dashboard_api_swing_range_helpers(monkeypatch, test_settings):
    monkeypatch.setattr("earnings_engine.api.dashboard_api._settings", lambda: test_settings)

    # Set user range
    res = set_swing_range_api("MyPicks", "PCJ", 9.0, 10.0, cycles=3)
    assert res["success"] is True
    assert res["lower_bound"] == 9.0
    assert res["upper_bound"] == 10.0

    # Get range API
    get_res = get_swing_range_api("MyPicks", "PCJ")
    assert get_res["success"] is True
    assert get_res["range"]["lower_bound"] == 9.0
    assert get_res["range"]["upper_bound"] == 10.0
    assert get_res["range"]["cycles"] == 3
    assert get_res["range"]["source"] == "user"

    # List ranges API
    ranges = list_swing_ranges_api("MyPicks")
    assert len(ranges) == 1
    assert ranges[0]["ticker"] == "PCJ"

    # Clear range API
    clear_res = clear_swing_range_api("MyPicks", "PCJ")
    assert clear_res["success"] is True
    assert clear_res["range"] is None


def test_get_swing_setups_enriches_swing_range(monkeypatch, test_settings):
    monkeypatch.setattr("earnings_engine.api.dashboard_api._settings", lambda: test_settings)
    monkeypatch.setattr("earnings_engine.api.dashboard_api._resolve_tickers", lambda market: ["PCJ"])
    
    # Mock upcoming_earnings so no external network call is made
    monkeypatch.setattr(
        "earnings_engine.data.earnings.upcoming_earnings",
        lambda tickers, settings, days=90: pd.DataFrame()
    )

    # Mock enrich_upcoming_results to return simulated metrics
    def mock_enrich(df, settings, force=False):
        return pd.DataFrame([{
            "ticker": "PCJ",
            "current_price": 9.1,
            "current_support": 8.8,
            "next_resistance": 10.2,
            "thirty_day_return_pct": 5.0,
            "prev_quarter_earnings_score": 7,
        }])

    monkeypatch.setattr("earnings_engine.api.dashboard_api.enrich_upcoming_results", mock_enrich)

    # Set custom user range for PCJ in watchlist "MyPicks"
    set_user_range("MyPicks", "PCJ", 9.0, 10.0, cycles=3, settings=test_settings)

    # Calling for MyPicks should enrich with user range
    setups = get_swing_setups(market="MyPicks", limit=10)
    assert len(setups) == 1
    setup = setups[0]
    assert setup["ticker"] == "PCJ"
    assert setup["swing_range"] is not None
    assert setup["swing_range"]["source"] == "user"
    assert setup["swing_range"]["lower_bound"] == 9.0
    assert setup["swing_range"]["upper_bound"] == 10.0
    assert setup["current_support"] == 9.0
    assert setup["next_resistance"] == 10.0
    assert setup["swing_signal"] == "Strong Buy"
    assert setup["swing_zone"] == "Buy Zone"


def test_api_endpoints_swing_range(monkeypatch, test_settings):
    monkeypatch.setattr("earnings_engine.api.dashboard_api._settings", lambda: test_settings)
    monkeypatch.setattr("earnings_engine.api.routers.swing._settings", lambda: test_settings)
    from earnings_engine.data.auth import create_session_token
    token = create_session_token(
        user_id="test-admin",
        role="owner",
        email="admin@nexus.local",
        name="Test Admin",
        scopes=["*"],
    )
    client = TestClient(app)
    client.headers.update({
        "Cookie": f"nexus_session={token}",
        "Authorization": f"Bearer {token}",
    })

    # 1. POST /api/v1/swing-range
    resp = client.post("/api/v1/swing-range", json={
        "watchlist": "GrowthList",
        "ticker": "RELIANCE.NS",
        "lower": 2800.0,
        "upper": 3100.0,
        "cycles": 4
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["lower_bound"] == 2800.0
    assert data["source"] == "user"

    # 2. GET /api/v1/swing-range
    resp = client.get("/api/v1/swing-range?watchlist=GrowthList&ticker=RELIANCE.NS")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["range"]["lower_bound"] == 2800.0
    assert data["range"]["upper_bound"] == 3100.0
    assert data["range"]["cycles"] == 4

    # 3. GET /api/v1/swing-range/list
    resp = client.get("/api/v1/swing-range/list?watchlist=GrowthList")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["ranges"]) == 1
    assert data["ranges"][0]["ticker"] == "RELIANCE.NS"

    # 4. DELETE /api/v1/swing-range
    resp = client.delete("/api/v1/swing-range?watchlist=GrowthList&ticker=RELIANCE.NS")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["range"] is None


def test_detect_swing_range_3_months_history():
    from earnings_engine.data.market_context import detect_swing_range
    import numpy as np

    # Generate 65 trading days (~3 months) of price history with oscillations between 9.0 and 10.5
    dates = pd.date_range("2026-05-01", periods=65, freq="B")
    prices = 9.5 + 0.9 * np.sin(np.linspace(0, 4 * np.pi, 65))
    series = pd.Series(prices, index=dates)

    res = detect_swing_range(series)
    assert res["lower"] is not None
    assert res["upper"] is not None
    assert res["three_month_lower"] is not None
    assert res["three_month_upper"] is not None
    assert len(res["monthly_ranges"]) >= 2
    assert len(res["cycles_data"]) >= 1


def test_watchlist_quotes_swing_signal(test_settings):
    from earnings_engine.api.dashboard_api import get_watchlist_quotes_api
    from earnings_engine.data.swing_ranges import set_user_range
    from earnings_engine.data.prices import set_cached_price_df
    import pandas as pd

    # Save price history for TEST1 (at support -> BUY), TEST2 (at resistance -> SELL), TEST3 (mid -> HOLD)
    dates = pd.date_range("2026-08-01", periods=10, freq="B")

    # TEST1: support=100, resistance=200, current=110 (10% -> BUY)
    df1 = pd.DataFrame({"open": [100.0]*10, "high": [115.0]*10, "low": [95.0]*10, "close": [110.0]*10, "volume": [1000.0]*10}, index=dates)
    set_cached_price_df("TEST1.NS", df1)
    set_user_range("TestWL", "TEST1.NS", lower=100.0, upper=200.0, settings=test_settings)

    # TEST2: support=100, resistance=200, current=190 (90% -> SELL)
    df2 = pd.DataFrame({"open": [180.0]*10, "high": [195.0]*10, "low": [175.0]*10, "close": [190.0]*10, "volume": [1000.0]*10}, index=dates)
    set_cached_price_df("TEST2.NS", df2)
    set_user_range("TestWL", "TEST2.NS", lower=100.0, upper=200.0, settings=test_settings)

    # TEST3: support=100, resistance=200, current=150 (50% -> HOLD)
    df3 = pd.DataFrame({"open": [140.0]*10, "high": [155.0]*10, "low": [135.0]*10, "close": [150.0]*10, "volume": [1000.0]*10}, index=dates)
    set_cached_price_df("TEST3.NS", df3)
    set_user_range("TestWL", "TEST3.NS", lower=100.0, upper=200.0, settings=test_settings)

    quotes = get_watchlist_quotes_api(watchlist="TestWL", tickers=["TEST1.NS", "TEST2.NS", "TEST3.NS"], settings=test_settings)
    assert quotes["success"] is True
    items = {it["ticker"]: it for it in quotes["items"]}

    assert items["TEST1.NS"]["swing_signal"] == "BUY"
    assert items["TEST1.NS"]["swing_signal_color"] == "green"

    assert items["TEST2.NS"]["swing_signal"] == "SELL"
    assert items["TEST2.NS"]["swing_signal_color"] == "red"

    assert items["TEST3.NS"]["swing_signal"] == "HOLD"
    assert items["TEST3.NS"]["swing_signal_color"] == "brown"


