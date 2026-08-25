import pytest
from starlette.testclient import TestClient
from earnings_engine.api.server import app
from earnings_engine.api.stock_api import calculate_or_fetch_eps
from earnings_engine.data.db import get_db_connection
from earnings_engine.config import Settings
from earnings_engine.data.migrations import apply_migrations


@pytest.fixture(autouse=True)
def setup_db(monkeypatch):
    monkeypatch.setenv("TURSO_DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("TURSO_AUTH_TOKEN", "")
    apply_migrations()


def test_calculate_or_fetch_eps_manual_override():
    settings = Settings()
    conn = get_db_connection(settings)
    
    # 1. Insert a blank past earnings record without EPS
    with conn:
        conn.execute("""
            INSERT OR REPLACE INTO earnings_history (ticker, earnings_date, eps_estimate, eps_reported, surprise_pct, source)
            VALUES ('TCS.NS', '2026-08-07', NULL, NULL, NULL, 'nse')
        """)
        conn.commit()

    # 2. Call calculate_or_fetch_eps with manual overrides
    res = calculate_or_fetch_eps(
        ticker="TCS.NS",
        earnings_date="2026-08-07",
        override_estimate=37.0,
        override_reported=39.22,
        settings=settings,
    )

    assert res["success"] is True
    assert res["ticker"] == "TCS.NS"
    assert res["earnings_date"] == "2026-08-07"
    assert res["eps_estimate"] == 37.0
    assert res["eps_reported"] == 39.22
    assert res["surprise_pct"] == 6.0 # ((39.22 - 37.0) / 37.0) * 100 = +6.0%

    # 3. Verify DB record was updated
    row = conn.execute("SELECT eps_estimate, eps_reported, surprise_pct FROM earnings_history WHERE ticker = 'TCS.NS' AND earnings_date = '2026-08-07'").fetchone()
    assert row is not None
    assert row[0] == 37.0
    assert row[1] == 39.22
    assert row[2] == 6.0


def test_calculate_eps_api_endpoint():
    client = TestClient(app)
    
    settings = Settings()
    conn = get_db_connection(settings)
    with conn:
        conn.execute("""
            INSERT OR REPLACE INTO earnings_history (ticker, earnings_date, eps_estimate, eps_reported, surprise_pct, source)
            VALUES ('INFY.NS', '2026-08-07', NULL, NULL, NULL, 'nse')
        """)
        conn.commit()

    # Call API endpoint
    resp = client.post(
        "/api/v1/stock/INFY.NS/calculate-eps",
        json={
            "earnings_date": "2026-08-07",
            "override_estimate": 18.5,
            "override_reported": 19.425,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["eps_estimate"] == 18.5
    assert data["eps_reported"] == 19.425
    assert data["surprise_pct"] == 5.0

    # Test overview returns the updated earnings history
    overview_resp = client.get("/api/v1/stock/INFY.NS/overview")
    assert overview_resp.status_code == 200
    history = overview_resp.json().get("earnings_history", [])
    assert len(history) >= 1
    matching = [h for h in history if h["earnings_date"] == "2026-08-07"]
    assert len(matching) == 1
    assert matching[0]["eps_reported"] == 19.425
