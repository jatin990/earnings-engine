import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
import pandas as pd
from earnings_engine.config import Settings
from earnings_engine.api.stock_api import calculate_or_fetch_eps
from earnings_engine.api.server import app

client = TestClient(app)


def test_calculate_or_fetch_eps_derives_estimate_and_audits():
    """Verify calculate_or_fetch_eps derives estimate from income statements and audits diff."""
    settings = Settings()
    
    # Mock yfinance quarterly income stmt with multiple quarters
    mock_inc_stmt = pd.DataFrame(
        {
            pd.Timestamp("2026-08-26"): [1.27, 1000000.0, 787401.57],
            pd.Timestamp("2026-05-20"): [1.15, 900000.0, 782608.69],
            pd.Timestamp("2026-02-15"): [1.10, 850000.0, 772727.27],
            pd.Timestamp("2025-11-10"): [1.05, 800000.0, 761904.76],
        },
        index=["Diluted EPS", "Net Income", "Diluted Average Shares"],
    )

    mock_ticker_obj = MagicMock()
    mock_ticker_obj.get_earnings_dates.return_value = pd.DataFrame()
    mock_ticker_obj.quarterly_income_stmt = mock_inc_stmt
    mock_ticker_obj.fast_info = MagicMock(trailing_pe=25.0, last_price=120.0)

    with patch("yfinance.Ticker", return_value=mock_ticker_obj):
        res = calculate_or_fetch_eps("JIOFIN.NS", earnings_date="2026-08-26", settings=settings)
        assert res["success"] is True
        assert res["eps_reported"] == 1.27
        assert res["eps_estimate"] is not None
        assert res["surprise_pct"] is not None
        assert "audit_id" in res or "recalculate" in res


def test_calculate_eps_api_endpoint():
    """Verify POST /api/v1/stock/{ticker}/calculate-eps endpoint returns audit details."""
    response = client.post("/api/v1/stock/TCS.NS/calculate-eps", json={"earnings_date": "2026-08-07"})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["ticker"] == "TCS.NS"
    assert "method" in data
