import pytest
from starlette.testclient import TestClient
from earnings_engine.api.server import app
from earnings_engine.api.stock_api import calculate_or_fetch_eps
from earnings_engine.data.earnings import refresh_earnings_from_source
from earnings_engine.data.db import get_db_connection
from earnings_engine.config import Settings
from earnings_engine.data.migrations import apply_migrations
from earnings_engine.data.auth import create_session_token


@pytest.fixture(autouse=True)
def setup_db(monkeypatch):
    monkeypatch.setenv("TURSO_DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("TURSO_AUTH_TOKEN", "")
    apply_migrations()


def test_guard_rail_prevents_overwriting_authentic_source():
    """Authentic source records (yfinance/nse) must never be overwritten by calculation heuristics."""
    settings = Settings()
    conn = get_db_connection(settings)

    with conn:
        conn.execute("""
            INSERT OR REPLACE INTO earnings_history (ticker, earnings_date, eps_estimate, eps_reported, surprise_pct, source)
            VALUES ('TESTGUARD.NS', '2026-07-20', 10.0, 12.5, 25.0, 'yfinance')
        """)
        conn.commit()

    # Call calculate_or_fetch_eps without manual overrides
    res = calculate_or_fetch_eps(
        ticker="TESTGUARD.NS",
        earnings_date="2026-07-20",
        settings=settings,
    )

    # Verify DB record remains yfinance and was not altered by heuristic calculation
    row = conn.execute(
        "SELECT eps_estimate, eps_reported, surprise_pct, source FROM earnings_history WHERE ticker = 'TESTGUARD.NS' AND earnings_date = '2026-07-20'"
    ).fetchone()

    assert row is not None
    assert row[3] == "yfinance"
    assert row[1] == 12.5
    assert row[0] == 10.0


def test_guard_rail_allows_explicit_manual_override():
    """Manual user overrides are allowed and explicitly tagged as source='manual_override'."""
    settings = Settings()
    conn = get_db_connection(settings)

    with conn:
        conn.execute("""
            INSERT OR REPLACE INTO earnings_history (ticker, earnings_date, eps_estimate, eps_reported, surprise_pct, source)
            VALUES ('TESTMAN.NS', '2026-07-20', 10.0, 12.5, 25.0, 'yfinance')
        """)
        conn.commit()

    res = calculate_or_fetch_eps(
        ticker="TESTMAN.NS",
        earnings_date="2026-07-20",
        override_reported=14.0,
        override_estimate=10.0,
        settings=settings,
    )

    assert res["success"] is True
    assert res["eps_reported"] == 14.0

    row = conn.execute(
        "SELECT eps_reported, source FROM earnings_history WHERE ticker = 'TESTMAN.NS' AND earnings_date = '2026-07-20'"
    ).fetchone()
    assert row is not None
    assert row[0] == 14.0
    assert row[1] == "manual_override"


def test_guard_rail_skips_duplicate_quarterly_income_stmt_near_auth_source():
    """Quarterly income statement rows must not be created if an authentic yfinance/nse record exists within 60 days."""
    settings = Settings()
    conn = get_db_connection(settings)

    # Insert authentic record for Q1 on 2026-07-24
    with conn:
        conn.execute("""
            INSERT OR REPLACE INTO earnings_history (ticker, earnings_date, eps_estimate, eps_reported, surprise_pct, source)
            VALUES ('TESTDUP.NS', '2026-07-24', 15.0, 16.0, 6.67, 'yfinance')
        """)
        conn.commit()

    # Call calculate_or_fetch_eps (which scans quarterly income stmt)
    calculate_or_fetch_eps(ticker="TESTDUP.NS", settings=settings)

    # Check that no duplicate row for 2026-06-30 was inserted with source='quarterly_income_stmt'
    dup_row = conn.execute(
        "SELECT * FROM earnings_history WHERE ticker = 'TESTDUP.NS' AND earnings_date = '2026-06-30' AND source = 'quarterly_income_stmt'"
    ).fetchone()

    assert dup_row is None


def test_refresh_earnings_from_source_endpoint():
    """API endpoint /api/v1/stock/{ticker}/refresh-earnings-source refreshes data cleanly."""
    token = create_session_token(
        user_id="test-admin",
        role="owner",
        email="admin@nexus.local",
        name="Test Admin",
        scopes=["*"],
    )

    client = TestClient(app)
    resp = client.post(
        "/api/v1/stock/TCS.NS/refresh-earnings-source",
        cookies={"nexus_session": token},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data.get("success") is True
    assert data.get("ticker") == "TCS.NS"
    assert "source" in data
