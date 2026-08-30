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

    # Test confluence setups
    r_conf = client.get("/api/v1/breakout-radar/confluence?min_level=0&limit=10")
    assert r_conf.status_code == 200
    data_c = r_conf.json()
    assert data_c.get("success") is True
    assert "setups" in data_c
