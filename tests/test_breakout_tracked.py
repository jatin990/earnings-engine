"""Unit and integration tests for Breakout Radar Tracked Signals Archive and Sub-Tab API."""

import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection
from earnings_engine.data.migrations import apply_migrations
from earnings_engine.data.breakout_scanner import (
    get_tracked_breakouts,
    save_breakout_pool_to_db,
    evaluate_stock_breakout,
)
from earnings_engine.api.server import app


@pytest.fixture(scope="module")
def app_client():
    settings = Settings()
    apply_migrations(settings)
    return TestClient(app)


def test_tracked_breakouts_presets():
    """Test that get_tracked_breakouts correctly handles day presets."""
    settings = Settings()
    apply_migrations(settings)

    # Test preset days
    for preset in [1, 3, 7, 14, 30, "all"]:
        res = get_tracked_breakouts(days=preset, settings=settings)
        assert res["success"] is True
        assert "items" in res
        assert "summary" in res
        assert "total_count" in res
        assert isinstance(res["items"], list)
        assert res["total_count"] >= 0


def test_tracked_breakouts_date_range():
    """Test that get_tracked_breakouts filters by date range."""
    settings = Settings()
    apply_migrations(settings)

    res = get_tracked_breakouts(start_date="2026-08-01", end_date="2026-08-28", settings=settings)
    assert res["success"] is True
    assert res["timeframe"]["start_date"] == "2026-08-01"
    assert res["timeframe"]["end_date"] == "2026-08-28"
    assert isinstance(res["items"], list)


def test_tracked_breakouts_filters():
    """Test filtering by tier and outcome."""
    settings = Settings()
    apply_migrations(settings)

    # Tier filter
    res_hot = get_tracked_breakouts(days=30, tier="HOT", settings=settings)
    assert res_hot["success"] is True
    for item in res_hot["items"]:
        assert item["tier"] == "HOT"

    # Outcome filter
    res_outcome = get_tracked_breakouts(days=30, outcome="TARGET_HIT", settings=settings)
    assert res_outcome["success"] is True
    for item in res_outcome["items"]:
        assert item["outcome"] == "TARGET_HIT"


def test_tracked_breakouts_rest_endpoint(app_client):
    """Test the REST endpoints /api/v1/breakout/tracked and /api/v1/breakout-radar/tracked."""
    resp = app_client.get("/api/v1/breakout/tracked?days=7")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "items" in data
    assert "summary" in data

    resp_alias = app_client.get("/api/v1/breakout-radar/tracked?days=3")
    assert resp_alias.status_code == 200
    data_alias = resp_alias.json()
    assert data_alias["success"] is True

    # Test date range query params
    resp_range = app_client.get("/api/v1/breakout/tracked?start_date=2026-08-01&end_date=2026-08-28&tier=HOT")
    assert resp_range.status_code == 200
    data_range = resp_range.json()
    assert data_range["success"] is True


def test_tracked_breakout_persistence():
    """Test that candidate setups are persisted to breakout_tracked_signals."""
    settings = Settings()
    apply_migrations(settings)

    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    test_pool = [
        {
            "ticker": "TEST_TRACKED_STOCK.NS",
            "company_name": "Test Tracked Corp",
            "industry": "Software",
            "tier": "HOT",
            "asof_date": today_str,
            "signal_date": today_str,
            "signal_price": 500.0,
            "current_price": 500.0,
            "breakout_trigger": 520.0,
            "target_price": 580.0,
            "stop_loss": 470.0,
            "risk_reward_ratio": 2.67,
            "composite_score": 88.5,
            "resistance_score": 38.0,
            "volume_score": 18.0,
            "compression_score": 12.0,
            "momentum_score": 12.0,
            "fundamental_score": 8.5,
            "volume_ratio": 2.1,
            "atr_pct": 2.2,
            "pct_from_high": -1.5,
            "setup_archetype": "🔥 High Conviction Compression Breakout",
            "realized_return_pct": 3.2,
            "max_gain_pct": 5.8,
            "breakout_happened": True,
            "outcome": "TRIGGERED",
            "outcome_label": "Breakout Fired 🚀",
            "outcome_badge": "blue",
            "days_elapsed": 1,
            "calculation_notes": {"test": True},
            "institutional_flow": {},
        }
    ]

    from earnings_engine.data.breakout_scanner import _pool
    _pool["candidates"] = test_pool
    save_breakout_pool_to_db(settings=settings)

    # Verify query
    res = get_tracked_breakouts(days=3, settings=settings)
    matching = [it for it in res["items"] if it["ticker"] == "TEST_TRACKED_STOCK.NS"]
    assert len(matching) >= 1
    assert matching[0]["signal_price"] == 500.0
    assert matching[0]["breakout_trigger"] == 520.0
    assert matching[0]["composite_score"] == 88.5

    # Clean up test row and reset pool
    _pool["candidates"] = []
    conn = get_db_connection(settings)
    conn.execute("DELETE FROM breakout_tracked_signals WHERE ticker = 'TEST_TRACKED_STOCK.NS'")
    conn.commit()


def test_delete_tracked_breakout_api(app_client):
    """Test DELETE /api/v1/breakout/tracked/{id} and DELETE /api/v1/breakout/tracked/ticker/{ticker}."""
    settings = Settings()
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Clean any stale test rows first
    conn = get_db_connection(settings)
    conn.execute("DELETE FROM breakout_tracked_signals WHERE ticker = 'TEST_DEL_TICKER.NS'")
    conn.commit()

    try:
        # Insert two test setups for a ticker
        cur1 = conn.execute(
            """
            INSERT INTO breakout_tracked_signals (
                ticker, company_name, industry, tier, signal_date,
                signal_price, current_price, breakout_trigger, target_price, stop_loss,
                composite_score, setup_archetype, outcome, scanned_at, created_at, updated_at
            ) VALUES (
                'TEST_DEL_TICKER.NS', 'Test Delete Corp', 'Software', 'HOT', ?,
                100.0, 102.0, 105.0, 120.0, 95.0, 85.0, 'Classic Technical', 'ACTIVE',
                ?, ?, ?
            )
            """,
            (today_str, today_str, today_str, today_str),
        )
        id1 = cur1.lastrowid

        cur2 = conn.execute(
            """
            INSERT INTO breakout_tracked_signals (
                ticker, company_name, industry, tier, signal_date,
                signal_price, current_price, breakout_trigger, target_price, stop_loss,
                composite_score, setup_archetype, outcome, breakout_happened, scanned_at, created_at, updated_at
            ) VALUES (
                'TEST_DEL_TICKER.NS', 'Test Delete Corp', 'Software', 'WARM', '2026-08-28',
                108.0, 110.0, 106.0, 125.0, 96.0, 75.0, 'NSE Delivery Surge', 'TRIGGERED', 1,
                ?, ?, ?
            )
            """,
            (today_str, today_str, today_str),
        )
        id2 = cur2.lastrowid
        conn.commit()
        conn.close()

        # 1. Delete single setup by ID
        del_resp1 = app_client.delete(f"/api/v1/breakout/tracked/{id1}")
        assert del_resp1.status_code == 200
        del_json1 = del_resp1.json()
        assert del_json1["success"] is True
        assert del_json1["id"] == id1

        # Verify id2 still exists in DB
        db_conn = get_db_connection(settings)
        cur_check = db_conn.execute("SELECT id FROM breakout_tracked_signals WHERE id = ?", (id2,))
        assert cur_check.fetchone() is not None
        cur_check1 = db_conn.execute("SELECT id FROM breakout_tracked_signals WHERE id = ?", (id1,))
        assert cur_check1.fetchone() is None
        db_conn.close()

        # 2. Delete all setups for ticker
        del_resp2 = app_client.delete("/api/v1/breakout/tracked/ticker/TEST_DEL_TICKER.NS")
        assert del_resp2.status_code == 200
        del_json2 = del_resp2.json()
        assert del_json2["success"] is True
        assert del_json2["deleted_count"] >= 1

        # Verify no setups remain in DB for ticker
        db_conn2 = get_db_connection(settings)
        cur_check2 = db_conn2.execute("SELECT id FROM breakout_tracked_signals WHERE ticker = 'TEST_DEL_TICKER.NS'")
        assert cur_check2.fetchall() == []
        db_conn2.close()
    finally:
        cleanup_conn = get_db_connection(settings)
        cleanup_conn.execute("DELETE FROM breakout_tracked_signals WHERE ticker = 'TEST_DEL_TICKER.NS'")
        cleanup_conn.commit()
        cleanup_conn.close()


def test_signal_day_intraday_low_does_not_trigger_false_stop_hit(monkeypatch):
    """Verify that a morning low on the signal day itself before breaking out does not falsely trigger STOP_HIT."""
    import pandas as pd
    settings = Settings()
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    conn = get_db_connection(settings)
    cur = conn.execute(
        """
        INSERT INTO breakout_tracked_signals (
            ticker, company_name, industry, tier, signal_date,
            signal_price, current_price, breakout_trigger, target_price, stop_loss,
            composite_score, setup_archetype, outcome, breakout_happened, scanned_at, created_at, updated_at
        ) VALUES (
            'SAMPLE_INTRA_SWING.NS', 'Test False Stop Co', 'Equities', 'HOT', ?,
            100.0, 100.0, 100.0, 120.0, 90.0, 75.0, 'Classic Technical', 'ACTIVE', 1,
            ?, ?, ?
        )
        """,
        (today_str, today_str, today_str, today_str),
    )
    test_id = cur.lastrowid
    conn.commit()
    conn.close()

    try:
        mock_df = pd.DataFrame(
            [{"open": 85.0, "high": 100.0, "low": 80.0, "close": 100.0, "volume": 50000}],
            index=pd.to_datetime([today_str]),
        )
        from earnings_engine.data import prices
        monkeypatch.setattr(prices, "fetch_prices", lambda sym, settings, force=False: mock_df)

        res = get_tracked_breakouts(days=7, settings=settings)
        assert res["success"] is True
        target_item = next((item for item in res["items"] if item["id"] == test_id), None)
        assert target_item is not None

        assert target_item["outcome"] == "TRIGGERED"
        assert "Stop Hit" not in target_item["outcome_label"]
        assert "Live Active" in target_item["outcome_label"]
    finally:
        clean_conn = get_db_connection(settings)
        clean_conn.execute("DELETE FROM breakout_tracked_signals WHERE id = ?", (test_id,))
        clean_conn.commit()
        clean_conn.close()


def test_portfolio_capital_simulation():
    """Verify 10L portfolio capital simulation: 70/30 target booking, stop loss enforcement, and net P&L."""
    settings = Settings()
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    conn = get_db_connection(settings)

    # Insert two test signals: 1 Target Hit and 1 Stop Loss Hit
    cur1 = conn.execute(
        """
        INSERT INTO breakout_tracked_signals (
            ticker, company_name, industry, tier, signal_date,
            signal_price, current_price, breakout_trigger, target_price, stop_loss,
            composite_score, setup_archetype, outcome, max_gain_pct, scanned_at, created_at, updated_at
        ) VALUES (
            'TEST_PORT_WIN.NS', 'Test Win Corp', 'Tech', 'HOT', ?,
            100.0, 125.0, 100.0, 110.0, 95.0,
            85.0, 'Classic Technical', 'TARGET_HIT', 20.0,
            ?, ?, ?
        )
        """,
        (today_str, today_str, today_str, today_str),
    )
    id1 = cur1.lastrowid

    cur2 = conn.execute(
        """
        INSERT INTO breakout_tracked_signals (
            ticker, company_name, industry, tier, signal_date,
            signal_price, current_price, breakout_trigger, target_price, stop_loss,
            composite_score, setup_archetype, outcome, max_gain_pct, scanned_at, created_at, updated_at
        ) VALUES (
            'TEST_PORT_LOSS.NS', 'Test Loss Corp', 'Tech', 'HOT', ?,
            100.0, 92.0, 100.0, 110.0, 95.0,
            75.0, 'Classic Technical', 'STOP_HIT', 0.0,
            ?, ?, ?
        )
        """,
        (today_str, today_str, today_str, today_str),
    )
    id2 = cur2.lastrowid
    conn.commit()
    conn.close()

    try:
        # Run simulation with 10L capital
        res = get_tracked_breakouts(days=1, capital=1000000.0, settings=settings)
        assert res["success"] is True

        items_map = {it["id"]: it for it in res["items"] if it["id"] in (id1, id2)}
        assert id1 in items_map
        assert id2 in items_map

        win_item = items_map[id1]
        loss_item = items_map[id2]

        # Target Return = (110 - 100) / 100 * 100 = +10.0%
        # Peak Gain = 20.0%
        # Simulated Return = 0.70 * 10.0 + 0.30 * 20.0 = 7.0 + 6.0 = 13.0%
        assert win_item["simulated_return_pct"] == 13.0
        assert "70% @ Target" in win_item["simulated_booking_note"]

        # Stop Return = (95 - 100) / 100 * 100 = -5.0%
        assert loss_item["simulated_return_pct"] == -5.0
        assert "100% Stop Loss Hit" in loss_item["simulated_booking_note"]

        # Check summary portfolio simulation
        sim_summary = res["summary"]["portfolio_simulation"]
        assert sim_summary["initial_capital"] == 1000000.0
        assert sim_summary["allocation_per_trade"] > 0
        assert sim_summary["final_capital"] is not None
        assert sim_summary["net_pnl"] is not None
        assert sim_summary["total_profit"] >= win_item["simulated_pnl"]
        assert sim_summary["total_loss"] >= abs(loss_item["simulated_pnl"])
    finally:
        clean_conn = get_db_connection(settings)
        clean_conn.execute("DELETE FROM breakout_tracked_signals WHERE id IN (?, ?)", (id1, id2))
        clean_conn.commit()
        clean_conn.close()


def test_portfolio_capital_simulation_api(app_client):
    """Verify that /api/v1/breakout/tracked endpoint accepts capital query parameter and returns simulation."""
    resp = app_client.get("/api/v1/breakout/tracked?days=7&capital=500000")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "portfolio_simulation" in data["summary"]
    sim = data["summary"]["portfolio_simulation"]
    assert sim["initial_capital"] == 500000.0


def test_per_strategy_breakdown_and_days_to_target():
    """Verify detailed per-strategy performance breakdown, win rates, target hits, and days-to-target evaluation."""
    settings = Settings()
    apply_migrations(settings)

    res = get_tracked_breakouts(days=30, settings=settings)
    assert res["success"] is True
    summary = res["summary"]

    # Verify summary fields
    assert "win_rate_pct" in summary
    assert "target_hit_count" in summary
    assert "target_hit_rate_pct" in summary
    assert "avg_days_to_target" in summary
    assert "per_strategy_stats" in summary

    per_strat = summary["per_strategy_stats"]
    assert isinstance(per_strat, dict)

    # Verify all 5 core breakout strategies are present in breakdown
    expected_strats = [
        "CLASSIC_TECHNICAL",
        "NSE_DELIVERY_ABSORPTION",
        "NSE_FO_CALL_WALL",
        "VOLUME_PROFILE_VAH",
        "DONCHIAN_TTM_SQUEEZE",
    ]
    for s_key in expected_strats:
        assert s_key in per_strat
        st = per_strat[s_key]
        assert "strategy_id" in st
        assert "strategy_name" in st
        assert "total_tracked" in st
        assert "win_rate_pct" in st
        assert "target_hit_count" in st
        assert "target_hit_rate_pct" in st
        assert "stop_hit_count" in st
        assert "stop_hit_rate_pct" in st
        assert "avg_days_to_target" in st
        assert "avg_return_pct" in st
        assert "avg_peak_gain_pct" in st
        assert "best_ticker" in st
        assert "best_return_pct" in st

    # Verify items have days_to_target populated when outcome is TARGET_HIT
    for item in res["items"]:
        if item.get("outcome") == "TARGET_HIT" and item.get("days_to_target") is not None:
            assert isinstance(item["days_to_target"], int)
            assert item["days_to_target"] >= 0


def test_deterministic_days_to_target_with_mocked_prices(monkeypatch):
    """Verify that a stock breaking out and hitting target on day 2 gets days_to_target = 2."""
    import pandas as pd
    settings = Settings()
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    conn = get_db_connection(settings)

    # Insert test signal from 5 days ago (use non-filtered symbol prefix)
    ticker_sym = "SPEEDRUN_TARGET_VALID.NS"
    cur = conn.execute(
        """
        INSERT INTO breakout_tracked_signals (
            ticker, company_name, industry, tier, signal_date,
            signal_price, current_price, breakout_trigger, target_price, stop_loss,
            composite_score, setup_archetype, outcome, breakout_happened, scanned_at, created_at, updated_at
        ) VALUES (
            ?, 'Speed Runner Corp', 'Equities', 'HOT', '2026-09-01',
            100.0, 115.0, 102.0, 110.0, 95.0, 85.0, 'Classic Technical Breakout', 'ACTIVE', 1,
            ?, ?, ?
        )
        """,
        (ticker_sym, today_str, today_str, today_str),
    )
    test_id = cur.lastrowid
    conn.commit()
    conn.close()

    try:
        # Mock price trajectory: Day 1 touches 105 (below target 110), Day 2 touches 112 (reaches target 110)
        dates = pd.to_datetime(["2026-09-01", "2026-09-02", "2026-09-03", "2026-09-04"])
        mock_df = pd.DataFrame(
            [
                {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 10000},  # Day 1: 2026-09-01
                {"open": 101.0, "high": 112.0, "low": 100.0, "close": 110.0, "volume": 25000},  # Day 2: 2026-09-02 reaches target 110!
                {"open": 110.0, "high": 114.0, "low": 108.0, "close": 111.0, "volume": 20000},  # Day 3: 2026-09-03
                {"open": 111.0, "high": 115.0, "low": 110.0, "close": 115.0, "volume": 30000},  # Day 4: 2026-09-04
            ],
            index=dates,
        )
        from earnings_engine.data import prices
        monkeypatch.setattr(prices, "fetch_prices", lambda sym, settings, force=False: mock_df)

        res = get_tracked_breakouts(days=60, settings=settings)
        item = next((it for it in res["items"] if it["id"] == test_id), None)
        assert item is not None
        assert item["outcome"] == "TARGET_HIT"
        assert item["days_to_target"] == 2
    finally:
        clean_conn = get_db_connection(settings)
        clean_conn.execute("DELETE FROM breakout_tracked_signals WHERE id = ?", (test_id,))
        clean_conn.commit()
        clean_conn.close()



