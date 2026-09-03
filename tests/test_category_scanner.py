"""Tests for Active Multi-Category Stock Scanner Hub and Sweep Engine."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from earnings_engine.api.server import app
from earnings_engine.config import Settings
from earnings_engine.data.category_scanner import (
    SCANNER_CATEGORIES,
    scan_category,
    get_categories_overview,
    deep_universe_sweep,
)
from earnings_engine.data import category_scanner as cs


@pytest.fixture(autouse=True)
def mock_news_network_harvest(monkeypatch):
    """Keep tests fast and offline by mocking external news RSS scraping."""
    monkeypatch.setattr(
        cs,
        "scan_watchlist_catalysts",
        lambda *args, **kwargs: {"catalysts_fetched": 0, "scanned_tickers": 0},
    )


def test_scanner_categories_definitions():
    assert len(SCANNER_CATEGORIES) >= 8
    required_keys = [
        "order_wins", "earnings_beats", "regulatory_approvals",
        "ma_expansion", "squeeze_coils", "blue_sky_52w",
        "sector_waves", "oversold_reversals", "risk_alerts"
    ]
    for k in required_keys:
        assert k in SCANNER_CATEGORIES
        cat = SCANNER_CATEGORIES[k]
        assert "name" in cat
        assert "badge" in cat
        assert "type" in cat
        assert "icon" in cat


def test_scan_category_technical_setups():
    settings = Settings()

    # 1. Squeeze Coils
    coils = scan_category("squeeze_coils", universe_or_watchlist="NSE_TOP", limit=5, settings=settings)
    assert isinstance(coils, list)
    if coils:
        assert "confidence_score" in coils[0]
        assert "trigger_level" in coils[0]
        assert "expected_horizon" in coils[0]

    # 2. 52W High Breakouts
    breakouts = scan_category("blue_sky_52w", universe_or_watchlist="NSE_TOP", limit=5, settings=settings)
    assert isinstance(breakouts, list)

    # 3. Sector Waves
    waves = scan_category("sector_waves", universe_or_watchlist="NSE_TOP", limit=5, settings=settings)
    assert isinstance(waves, list)


def test_scan_category_fundamental_catalysts():
    settings = Settings()

    # 1. Order Wins
    order_wins = scan_category("order_wins", universe_or_watchlist="NSE_TOP", limit=5, settings=settings)
    assert isinstance(order_wins, list)

    # 2. Risk Alerts
    risk_items = scan_category("risk_alerts", universe_or_watchlist="NSE_TOP", limit=5, settings=settings)
    assert isinstance(risk_items, list)


def test_get_categories_overview():
    settings = Settings()
    overview = get_categories_overview(universe_or_watchlist="NSE_TOP", settings=settings)
    assert isinstance(overview, list)
    assert len(overview) == len(SCANNER_CATEGORIES)
    for cat in overview:
        assert "id" in cat
        assert "count" in cat
        assert "top_candidates" in cat


def test_deep_universe_sweep():
    settings = Settings()
    sweep_res = deep_universe_sweep(universe_or_watchlist="NSE_TOP", settings=settings)
    assert isinstance(sweep_res, dict)
    assert sweep_res["universe"] == "NSE_TOP"
    assert "total_categories" in sweep_res
    assert "categories" in sweep_res


def test_scanner_api_endpoints():
    client = TestClient(app)

    # 1. Categories overview endpoint
    res_cats = client.get("/api/v1/scanner/categories?universe=NSE_TOP")
    assert res_cats.status_code == 200
    cats_data = res_cats.json()
    assert cats_data["success"] is True
    assert "categories" in cats_data

    # 2. Specific category candidate query
    res_cat = client.get("/api/v1/scanner/category/squeeze_coils?universe=NSE_TOP&limit=5")
    assert res_cat.status_code == 200
    cat_data = res_cat.json()
    assert cat_data["success"] is True
    assert cat_data["category_id"] == "squeeze_coils"
    assert "candidates" in cat_data

    # 3. Deep sweep endpoint
    res_sweep = client.post("/api/v1/scanner/sweep", json={"universe": "NSE_TOP"})
    assert res_sweep.status_code == 200
    sweep_data = res_sweep.json()
    assert sweep_data["success"] is True
    assert "total_candidates_found" in sweep_data


def test_scheduled_category_scanner_job_and_fields():
    """Verify scheduled_category_scanner_job executes and populates breakout-style fields."""
    from earnings_engine.data.category_scanner import scheduled_category_scanner_job, scan_category

    # Run scheduled sweep
    res = scheduled_category_scanner_job(universes=["NSE_TOP"], limit_per_category=5)
    assert res["status"] == "success"
    assert "total_candidates" in res

    # Check candidates for presence of breakout fields
    candidates = scan_category("squeeze_coils", universe_or_watchlist="NSE_TOP", limit=5)
    if candidates:
        cand = candidates[0]
        assert "signal_date" in cand
        assert "signal_price" in cand
        assert "target_price" in cand
        assert "stop_loss" in cand
        assert "severity" in cand
        assert "outcome" in cand
        assert "outcome_label" in cand
        assert "outcome_badge" in cand


def test_compute_and_save_scanner_universe_positional_and_slices(monkeypatch):
    """Regression test: verify positional settings passing and category candidate slicing."""
    from earnings_engine.data import category_scanner as cs
    settings = Settings()

    # Mock news network harvest to keep test instant and offline
    monkeypatch.setattr(cs, "scan_watchlist_catalysts", lambda *args, **kwargs: {"catalysts_fetched": 0, "scanned_tickers": 0})

    # 1. Test _compute_category_candidates_live with positional Settings as 3rd arg
    res_live = cs._compute_category_candidates_live("blue_sky_52w", "NSE_TOP", settings)
    assert isinstance(res_live, list)

    # 2. Test compute_and_save_scanner_universe with positional Settings as 2nd arg
    res_pos = cs.compute_and_save_scanner_universe("NSE_TOP", settings)
    assert isinstance(res_pos, dict)
    assert "total_saved" in res_pos

    # 3. Test with keyword arguments
    res_kw = cs.compute_and_save_scanner_universe("NSE_TOP", limit_per_category=10, settings=settings)
    assert isinstance(res_kw, dict)
    assert "total_saved" in res_kw



