"""Tests for built-in universes, under 100 stock detection, and knowledge base descriptions in watchlists."""

from starlette.testclient import TestClient
from earnings_engine.api.server import app
from earnings_engine.data.universe import get_universe_details, UNIVERSE_METADATA
from earnings_engine.api.dashboard_api import get_all_watchlists_and_universes


def test_universe_details_contains_under_100_and_explanations():
    details = get_universe_details()
    assert len(details) >= 2

    by_name = {u["name"]: u for u in details}
    assert "nse_top" in by_name
    assert "us_top" in by_name

    nse_top = by_name["nse_top"]
    assert nse_top["is_builtin"] is True
    assert nse_top["is_under_100"] is True
    assert "NIFTY" in nse_top["explanation"] or "blue-chip" in nse_top["explanation"].lower()
    assert len(nse_top["tickers"]) <= 100

    us_top = by_name["us_top"]
    assert us_top["is_builtin"] is True
    assert us_top["is_under_100"] is True
    assert "Magnificent Seven" in us_top["explanation"] or "S&P" in us_top["explanation"]
    assert len(us_top["tickers"]) <= 100


def test_get_all_watchlists_and_universes_structure():
    data = get_all_watchlists_and_universes()
    assert "watchlists" in data
    assert "universes" in data
    assert "all_lists" in data
    assert isinstance(data["watchlists"], list)
    assert isinstance(data["universes"], list)
    assert len(data["universes"]) >= 2


def test_watchlist_all_api_endpoint():
    client = TestClient(app)
    resp = client.get("/api/v1/watchlist/all")
    assert resp.status_code == 200
    json_data = resp.json()
    assert "watchlists" in json_data
    assert "universes" in json_data
    assert "all_lists" in json_data
    
    # Check that nse_top is present in universes list
    universe_names = [u["name"] for u in json_data["universes"]]
    assert "nse_top" in universe_names
    assert "us_top" in universe_names
