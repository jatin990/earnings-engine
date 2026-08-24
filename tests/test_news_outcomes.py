"""Unit tests for historical news catalyst outcome verification and trade metrics."""

from unittest.mock import patch
import pandas as pd
import pytest
from starlette.testclient import TestClient

from earnings_engine.api.server import app
from earnings_engine.config import Settings
from earnings_engine.data import news_outcomes, catalysts_news
from earnings_engine.data.news_outcomes import (
    evaluate_all_catalyst_outcomes,
    get_verified_catalyst_outcomes,
    compute_news_trade_metrics,
    _connect,
)


@pytest.fixture
def temp_settings(tmp_path):
    s = Settings()
    s.data_dirs["prices"] = tmp_path
    s.data_dirs["earnings"] = tmp_path
    s.ensure_dirs()
    return s


def test_evaluate_catalyst_outcomes_flow(temp_settings):
    """Test evaluating forward price action and prediction accuracy for historical news."""
    conn = _connect(temp_settings)

    # Insert mock news catalysts
    conn.execute(
        """
        INSERT OR REPLACE INTO news_catalysts (
            id, ticker, stock_name, title, publisher, link, published_at,
            summary, impact_score, impact_level, category, direction,
            expected_horizon, volatility_est, why_it_matters, source, created_at
        ) VALUES (
            1, 'RELIANCE.NS', 'Reliance Industries', 'Reliance bags Rs 10,000 Cr green energy contract',
            'Reuters', 'https://example.com/1', '2026-08-01T09:00:00Z',
            'Massive solar order win', 85, 'HIGH', 'Order Wins & Contracts', 'BULLISH',
            '1-3 Days', '±4% to ±9%', 'Significant revenue visibility', 'rss', '2026-08-01T09:00:00Z'
        )
        """
    )
    conn.execute(
        """
        INSERT OR REPLACE INTO news_catalysts (
            id, ticker, stock_name, title, publisher, link, published_at,
            summary, impact_score, impact_level, category, direction,
            expected_horizon, volatility_est, why_it_matters, source, created_at
        ) VALUES (
            2, 'INFY.NS', 'Infosys', 'SEBI initiates regulatory probe into accounting disclosures',
            'Bloomberg', 'https://example.com/2', '2026-08-01T09:00:00Z',
            'Regulator probe launched', 88, 'HIGH', 'Litigation, Risk & Probes', 'BEARISH',
            '1-2 Days', '±5% to ±10%', 'Governance overhang', 'rss', '2026-08-01T09:00:00Z'
        )
        """
    )
    conn.commit()

    # Mock prices for RELIANCE (upward rally) and INFY (downward drop)
    mock_rel_prices = pd.DataFrame([
        {"date": "2026-08-01", "open": 2800.0, "high": 2850.0, "low": 2790.0, "close": 2840.0, "volume": 10000},
        {"date": "2026-08-02", "open": 2850.0, "high": 2920.0, "low": 2840.0, "close": 2910.0, "volume": 12000},
        {"date": "2026-08-03", "open": 2910.0, "high": 2980.0, "low": 2900.0, "close": 2960.0, "volume": 15000},
        {"date": "2026-08-04", "open": 2960.0, "high": 3050.0, "low": 2950.0, "close": 3020.0, "volume": 18000},
        {"date": "2026-08-05", "open": 3020.0, "high": 3080.0, "low": 3000.0, "close": 3060.0, "volume": 14000},
        {"date": "2026-08-06", "open": 3060.0, "high": 3100.0, "low": 3040.0, "close": 3080.0, "volume": 11000},
    ])

    mock_infy_prices = pd.DataFrame([
        {"date": "2026-08-01", "open": 1800.0, "high": 1810.0, "low": 1760.0, "close": 1770.0, "volume": 8000},
        {"date": "2026-08-02", "open": 1770.0, "high": 1775.0, "low": 1720.0, "close": 1730.0, "volume": 9000},
        {"date": "2026-08-03", "open": 1730.0, "high": 1740.0, "low": 1680.0, "close": 1690.0, "volume": 11000},
        {"date": "2026-08-04", "open": 1690.0, "high": 1700.0, "low": 1650.0, "close": 1660.0, "volume": 13000},
        {"date": "2026-08-05", "open": 1660.0, "high": 1670.0, "low": 1620.0, "close": 1630.0, "volume": 10000},
        {"date": "2026-08-06", "open": 1630.0, "high": 1640.0, "low": 1600.0, "close": 1610.0, "volume": 7000},
    ])

    def _mock_load_batch(tickers, settings):
        return {
            "RELIANCE.NS": mock_rel_prices,
            "INFY.NS": mock_infy_prices,
        }

    with patch("earnings_engine.data.prices.load_prices_batch", side_effect=_mock_load_batch):
        res = evaluate_all_catalyst_outcomes(settings=temp_settings, force=True)

    assert res["total_catalysts"] >= 2
    assert res["evaluated"] >= 2
    assert res["verified"] >= 2

    # Query verified outcomes
    outcomes = get_verified_catalyst_outcomes(settings=temp_settings, sort_by="max_gain")
    assert len(outcomes) == 2

    rel_out = next(o for o in outcomes if o["ticker"] == "RELIANCE.NS")
    assert rel_out["entry_price"] == 2800.0
    assert rel_out["max_gain_pct"] > 9.0
    assert rel_out["predicted_met"] == 1
    assert rel_out["status"] == "VERIFIED"

    infy_out = next(o for o in outcomes if o["ticker"] == "INFY.NS")
    assert infy_out["entry_price"] == 1800.0
    assert infy_out["max_drawdown_pct"] < -8.0
    assert infy_out["predicted_met"] == 1
    assert infy_out["status"] == "VERIFIED"

    # Compute trade-readiness KPIs
    metrics = compute_news_trade_metrics(settings=temp_settings)
    assert metrics["total_evaluated"] == 2
    assert metrics["win_rate_pct"] == 100.0
    assert metrics["profit_factor"] >= 1.0
    assert len(metrics["max_gainers"]) >= 1
    assert len(metrics["category_performance"]) == 2
    assert "horizon_performance" in metrics


def test_news_outcomes_api_endpoints():
    """Test GET /api/v1/news/outcomes and GET /api/v1/news/trade-metrics endpoints."""
    client = TestClient(app)

    # Outcomes listing
    res = client.get("/api/v1/news/outcomes?limit=10")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert "outcomes" in data

    # Trade metrics
    metrics_res = client.get("/api/v1/news/trade-metrics")
    assert metrics_res.status_code == 200
    m_data = metrics_res.json()
    assert m_data["success"] is True
    assert "metrics" in m_data
    assert "win_rate_pct" in m_data["metrics"]

    # Evaluate trigger
    eval_res = client.post("/api/v1/news/outcomes/evaluate", json={"force": False})
    assert eval_res.status_code == 200
    assert eval_res.json()["success"] is True
