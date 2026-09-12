"""Test suite for Modular Market Pulse APIs, Nifty IT sector returns, and Confluence Radar."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from earnings_engine.config import Settings
from earnings_engine.data.market_pulse import (
    compute_indices_quotes,
    compute_sector_heatmap,
    compute_net_cash_liquidity,
    compute_market_sentiment_matrix,
    get_market_pulse_data,
)
from earnings_engine.data.cross_strategy import (
    compute_and_save_confluence_radar,
    load_confluence_radar_from_db,
)
from earnings_engine.api.server import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_compute_indices_quotes(temp_settings):
    quotes = compute_indices_quotes(settings=temp_settings, force_refresh=True)
    assert isinstance(quotes, list)
    assert len(quotes) > 0

    symbols = {q.get("symbol") for q in quotes}
    names = {q.get("name") for q in quotes}
    assert "^NSEI" in symbols or "^CNXIT" in symbols or "NIFTY 50" in names

    for q in quotes:
        assert "symbol" in q or "name" in q
        assert "current_price" in q
        assert "change_pct" in q
        assert "change_7d" in q
        assert "change_30d" in q


def test_compute_sector_heatmap(temp_settings):
    sectors = compute_sector_heatmap(settings=temp_settings, force_refresh=True)
    assert isinstance(sectors, list)
    assert len(sectors) > 0

    sector_names = [s.get("name") for s in sectors]
    assert "Nifty IT" in sector_names or "Nifty Bank" in sector_names

    # Check that Nifty IT has return metrics and constituent counts
    it_sector = next((s for s in sectors if s.get("name") in ("Nifty IT", "IT", "Information Technology")), None)
    if it_sector:
        assert "change_1d" in it_sector
        assert "change_7d" in it_sector
        assert "change_30d" in it_sector
        assert isinstance(it_sector["change_1d"], (int, float))
        assert "advances" in it_sector
        assert "declines" in it_sector


def test_compute_net_cash_liquidity(temp_settings):
    liq = compute_net_cash_liquidity(settings=temp_settings, force_refresh=True)
    assert isinstance(liq, dict)
    assert "fii_net_cr" in liq
    assert "dii_net_cr" in liq
    assert "total_net_cr" in liq
    assert "regime_badge" in liq
    assert "history_7d" in liq
    assert "history_30d" in liq
    assert "fii_7d_total_cr" in liq
    assert "total_7d_total_cr" in liq


def test_compute_market_sentiment_matrix(temp_settings):
    sent = compute_market_sentiment_matrix(settings=temp_settings)
    assert isinstance(sent, dict)
    assert "fear_greed_score" in sent
    assert "fear_greed_label" in sent
    assert "vix_level" in sent
    assert "vix_regime" in sent
    assert "breadth" in sent


def test_confluence_radar_persistence_and_loading(temp_settings):
    # Execute background scheduled job
    setups = compute_and_save_confluence_radar(temp_settings)
    assert isinstance(setups, list)

    # Load from DB
    loaded = load_confluence_radar_from_db(min_level=0, limit=20, settings=temp_settings)
    assert isinstance(loaded, list)


def test_api_modular_market_pulse_endpoints(client: TestClient):
    # Test indices quotes
    r_indices = client.get("/api/v1/market-pulse/indices")
    assert r_indices.status_code == 200
    data = r_indices.json()
    assert data.get("success") is True
    assert isinstance(data.get("indices"), list)

    # Test sector heatmap
    r_sectors = client.get("/api/v1/market-pulse/sectors")
    assert r_sectors.status_code == 200
    data_s = r_sectors.json()
    assert data_s.get("success") is True
    assert isinstance(data_s.get("sectors"), list)

    # Test liquidity overview
    r_liq = client.get("/api/v1/market-pulse/liquidity")
    assert r_liq.status_code == 200
    data_l = r_liq.json()
    assert data_l.get("success") is True
    assert "liquidity" in data_l

    # Test sentiment matrix
    r_sent = client.get("/api/v1/market-pulse/sentiment")
    assert r_sent.status_code == 200
    data_sent = r_sent.json()
    assert data_sent.get("success") is True
    assert "sentiment" in data_sent

    # Test modular participant-oi endpoint
    r_oi = client.get("/api/v1/market-pulse/participant-oi")
    assert r_oi.status_code == 200
    data_oi = r_oi.json()
    assert data_oi.get("success") is True
    assert "participant_oi" in data_oi
    assert "participants" in data_oi["participant_oi"]
    assert len(data_oi["participant_oi"]["participants"]) == 4
    assert "contrarian_prediction" in data_oi["participant_oi"]

    # Test modular playbook endpoint
    r_playbook = client.get("/api/v1/market-pulse/playbook")
    assert r_playbook.status_code == 200
    data_pb = r_playbook.json()
    assert data_pb.get("success") is True
    assert "playbook" in data_pb

    # Test confluence setups
    r_conf = client.get("/api/v1/breakout-radar/confluence?min_level=0&limit=10")
    assert r_conf.status_code == 200
    data_c = r_conf.json()
    assert data_c.get("success") is True
    assert "setups" in data_c


def test_get_expected_latest_trading_date():
    from datetime import datetime, timezone
    from earnings_engine.data.market_pulse import get_expected_latest_trading_date

    # Saturday UTC 06:30 = Saturday 12:00 IST -> Expected latest trading day is Friday
    sat_utc = datetime(2026, 9, 12, 6, 30, tzinfo=timezone.utc)
    assert get_expected_latest_trading_date(sat_utc) == "2026-09-11"

    # Sunday UTC 04:30 = Sunday 10:00 IST -> Expected latest trading day is Friday
    sun_utc = datetime(2026, 9, 13, 4, 30, tzinfo=timezone.utc)
    assert get_expected_latest_trading_date(sun_utc) == "2026-09-11"

    # Monday UTC 04:30 = Monday 10:00 IST (pre-18:00 IST cutoff) -> Expected is previous Friday
    mon_morning_utc = datetime(2026, 9, 14, 4, 30, tzinfo=timezone.utc)
    assert get_expected_latest_trading_date(mon_morning_utc) == "2026-09-11"

    # Monday UTC 13:30 = Monday 19:00 IST (post-18:00 IST cutoff) -> Expected is Monday
    mon_evening_utc = datetime(2026, 9, 14, 13, 30, tzinfo=timezone.utc)
    assert get_expected_latest_trading_date(mon_evening_utc) == "2026-09-14"

    # Tuesday UTC 05:00 = Tuesday 10:30 IST (pre-cutoff) -> Expected is Monday
    tue_morning_utc = datetime(2026, 9, 15, 5, 0, tzinfo=timezone.utc)
    assert get_expected_latest_trading_date(tue_morning_utc) == "2026-09-14"


def test_fii_dii_missing_checks_and_auto_sync(temp_settings, monkeypatch):
    from unittest.mock import MagicMock
    from earnings_engine.data.db import get_db_connection
    from earnings_engine.data import market_pulse

    conn = get_db_connection(temp_settings)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS institutional_net_flows (
            date TEXT PRIMARY KEY,
            day_label TEXT NOT NULL,
            fii_buy_cr REAL NOT NULL DEFAULT 0.0,
            fii_sell_cr REAL NOT NULL DEFAULT 0.0,
            fii_net_cr REAL NOT NULL DEFAULT 0.0,
            dii_buy_cr REAL NOT NULL DEFAULT 0.0,
            dii_sell_cr REAL NOT NULL DEFAULT 0.0,
            dii_net_cr REAL NOT NULL DEFAULT 0.0,
            total_net_cr REAL NOT NULL DEFAULT 0.0,
            stance TEXT NOT NULL DEFAULT 'Neutral',
            updated_at TEXT NOT NULL
        )
    """)
    # Insert older records (latest is 2026-09-08, so missing 2026-09-11)
    conn.execute("""
        INSERT OR REPLACE INTO institutional_net_flows (
            date, day_label, fii_buy_cr, fii_sell_cr, fii_net_cr,
            dii_buy_cr, dii_sell_cr, dii_net_cr, total_net_cr, stance, updated_at
        ) VALUES ('2026-09-08', '08 Sep (Tue)', 10000, 9900, 100, 10000, 9500, 500, 600, 'NET INFLOW (BULLISH)', '2026-09-08T18:00:00Z')
    """)
    conn.commit()

    # Track if sync_real_fii_dii_cash_flows is invoked automatically when latest day is missing
    sync_mock = MagicMock(return_value=1)
    monkeypatch.setattr(market_pulse, "sync_real_fii_dii_cash_flows", sync_mock)
    monkeypatch.setattr(market_pulse, "_LAST_FII_DII_SYNC_ATTEMPT", 0.0)

    # Calling compute_net_cash_liquidity with force_refresh=False
    market_pulse._LIQUIDITY_CACHE.clear()
    liq = market_pulse.compute_net_cash_liquidity(settings=temp_settings, force_refresh=False)

    # Sync MUST have been triggered because 2026-09-08 is older than expected latest trading date
    assert sync_mock.called, "sync_real_fii_dii_cash_flows should have been automatically triggered due to missing latest trading date"

