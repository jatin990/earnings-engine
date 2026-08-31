import pytest
import sqlite3
from earnings_engine.config import Settings
from earnings_engine.data.breakout_scanner import (
    record_breakout_transition,
    get_breakout_audit_log,
    get_stock_breakout_timeline,
    get_cached_scan_results,
    _pool,
)
from earnings_engine.data.migrations import apply_migrations


def test_breakout_audit_counter_increment_and_deduplication(tmp_path, monkeypatch):
    _pool["hot"].clear()
    _pool["warm"].clear()
    _pool["candidates"].clear()
    _pool["strategy_pools"].clear()

    prices_dir = tmp_path / "prices"
    prices_dir.mkdir(parents=True, exist_ok=True)
    earnings_dir = tmp_path / "earnings"
    earnings_dir.mkdir(parents=True, exist_ok=True)
    settings = Settings(data_dirs={"prices": prices_dir, "earnings": earnings_dir})

    test_db = prices_dir / "prices.sqlite3"
    db_conn_fn = lambda s=None: sqlite3.connect(str(test_db))
    monkeypatch.setattr("earnings_engine.data.db.get_db_connection", db_conn_fn)
    monkeypatch.setattr("earnings_engine.data.breakout_scanner.get_db_connection", db_conn_fn)
    monkeypatch.setattr("earnings_engine.data.migrations.get_db_connection", db_conn_fn)

    # Apply all migrations including 024
    apply_migrations(settings)

    ticker = "TCS.NS"

    # Event 1: First promotion to HOT
    record_breakout_transition(
        ticker=ticker,
        event_type="PROMOTED_HOT",
        from_tier="WARM",
        to_tier="HOT",
        score_before=65.0,
        score_after=82.0,
        price=3500.0,
        trigger_price=3550.0,
        reason="Compression coiling near resistance",
        strategy="Classic Technical",
        settings=settings,
    )

    logs = get_breakout_audit_log(ticker=ticker, settings=settings)
    assert len(logs) == 1
    assert logs[0]["counter"] == 1
    assert logs[0]["strategy"] == "Classic Technical"
    assert logs[0]["event_type"] == "PROMOTED_HOT"

    # Event 2: Same event triggered again in consecutive scan
    record_breakout_transition(
        ticker=ticker,
        event_type="PROMOTED_HOT",
        from_tier="WARM",
        to_tier="HOT",
        score_before=65.0,
        score_after=84.5,
        price=3510.0,
        trigger_price=3550.0,
        reason="Updated compression coiling near resistance",
        strategy="Classic Technical",
        settings=settings,
    )

    # Should still only be 1 row, but counter incremented to 2!
    logs_after = get_breakout_audit_log(ticker=ticker, settings=settings)
    assert len(logs_after) == 1
    assert logs_after[0]["counter"] == 2
    assert logs_after[0]["price"] == 3510.0
    assert logs_after[0]["score_after"] == 84.5

    # Event 3: Third identical scan confirmation
    record_breakout_transition(
        ticker=ticker,
        event_type="PROMOTED_HOT",
        from_tier="WARM",
        to_tier="HOT",
        score_after=85.0,
        price=3515.0,
        strategy="Classic Technical",
        settings=settings,
    )

    logs_after_3 = get_breakout_audit_log(ticker=ticker, settings=settings)
    assert len(logs_after_3) == 1
    assert logs_after_3[0]["counter"] == 3
    assert logs_after_3[0]["price"] == 3515.0

    # Event 4: Distinct event (e.g. Demotion or different strategy) -> New row inserted
    record_breakout_transition(
        ticker=ticker,
        event_type="DEMOTED_WARM",
        from_tier="HOT",
        to_tier="WARM",
        score_after=60.0,
        price=3480.0,
        strategy="Classic Technical",
        settings=settings,
    )

    logs_after_distinct = get_breakout_audit_log(ticker=ticker, settings=settings)
    assert len(logs_after_distinct) == 2
    assert logs_after_distinct[0]["event_type"] == "DEMOTED_WARM"
    assert logs_after_distinct[0]["counter"] == 1
    assert logs_after_distinct[1]["event_type"] == "PROMOTED_HOT"
    assert logs_after_distinct[1]["counter"] == 3

    # Check timeline rendering
    monkeypatch.setattr("earnings_engine.data.breakout_scanner.evaluate_stock_breakout", lambda t, **kw: {
        "ticker": t,
        "company_name": "Tata Consultancy Services",
        "current_price": 3515.0,
        "signal_price": 3500.0,
        "composite_score": 85.0,
        "tier": "HOT",
    })
    timeline = get_stock_breakout_timeline(ticker, settings=settings)
    assert "events" in timeline
    assert len(timeline["events"]) >= 2
    hot_events = [e for e in timeline["events"] if e.get("event_type") == "PROMOTED_HOT"]
    assert len(hot_events) >= 1
    assert hot_events[0]["counter"] == 3
    assert "3x" in hot_events[0]["title"]


def test_migration_024_backpopulates_legacy_audit_records(tmp_path, monkeypatch):
    prices_dir = tmp_path / "prices"
    prices_dir.mkdir(parents=True, exist_ok=True)
    earnings_dir = tmp_path / "earnings"
    earnings_dir.mkdir(parents=True, exist_ok=True)
    settings = Settings(data_dirs={"prices": prices_dir, "earnings": earnings_dir})

    test_db = prices_dir / "prices.sqlite3"
    db_conn_fn = lambda s=None: sqlite3.connect(str(test_db))
    monkeypatch.setattr("earnings_engine.data.db.get_db_connection", db_conn_fn)
    monkeypatch.setattr("earnings_engine.data.breakout_scanner.get_db_connection", db_conn_fn)
    monkeypatch.setattr("earnings_engine.data.migrations.get_db_connection", db_conn_fn)

    conn = sqlite3.connect(str(test_db))
    with conn:
        # Create legacy table structure without strategy and counter
        conn.execute("""
            CREATE TABLE breakout_audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                company_name TEXT,
                event_type TEXT NOT NULL,
                from_tier TEXT NOT NULL,
                to_tier TEXT NOT NULL,
                score_before REAL,
                score_after REAL,
                price REAL,
                trigger_price REAL,
                reason TEXT,
                catalyst_impact TEXT,
                created_at TEXT NOT NULL
            )
        """)
        # Insert legacy rows
        conn.execute("""
            INSERT INTO breakout_audit_log (ticker, company_name, event_type, from_tier, to_tier, created_at)
            VALUES ('INFY.NS', 'Infosys', 'PROMOTED_HOT', 'WARM', 'HOT', '2026-08-20T10:00:00')
        """)
        conn.commit()

    # Run migration
    apply_migrations(settings)

    # Check that legacy rows were backpopulated with 'Classic Technical' and counter = 1
    logs = get_breakout_audit_log(ticker="INFY.NS", settings=settings)
    assert len(logs) == 1
    assert logs[0]["strategy"] == "Classic Technical"
    assert logs[0]["counter"] == 1
