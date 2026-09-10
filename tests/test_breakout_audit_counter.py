import pytest
import sqlite3
from earnings_engine.config import Settings
from earnings_engine.data.breakout_scanner import (
    record_breakout_transition,
    get_breakout_audit_log,
    get_breakout_audit_log_count,
    prune_breakout_audit_log,
    get_stock_breakout_timeline,
    get_cached_scan_results,
    run_hot_rescore,
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

    test_db = prices_dir / "test.sqlite3"
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

    test_db = prices_dir / "test.sqlite3"
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


def test_run_hot_rescore_execution(tmp_path, monkeypatch):
    """Verify that run_hot_rescore executes cleanly without NameError or crash."""
    prices_dir = tmp_path / "prices"
    prices_dir.mkdir(parents=True, exist_ok=True)
    earnings_dir = tmp_path / "earnings"
    earnings_dir.mkdir(parents=True, exist_ok=True)
    settings = Settings(data_dirs={"prices": prices_dir, "earnings": earnings_dir})

    test_db = prices_dir / "test.sqlite3"
    db_conn_fn = lambda s=None: sqlite3.connect(str(test_db))
    monkeypatch.setattr("earnings_engine.data.db.get_db_connection", db_conn_fn)
    monkeypatch.setattr("earnings_engine.data.breakout_scanner.get_db_connection", db_conn_fn)
    apply_migrations(settings)

    _pool["hot"].clear()
    _pool["warm"].clear()
    _pool["hot"]["TCS.NS::CLASSIC_TECHNICAL"] = {
        "result": {
            "ticker": "TCS.NS",
            "composite_score": 85.0,
            "tier": "HOT",
            "company_name": "Tata Consultancy Services",
            "current_price": 3500.0,
            "signal_price": 3480.0,
        },
        "consecutive_low": 0,
    }

    # Mock external fetches
    monkeypatch.setattr("earnings_engine.data.prices.fetch_batch_live_quotes", lambda *a, **kw: {})
    monkeypatch.setattr(
        "earnings_engine.data.breakout_scanner._score_single_ticker",
        lambda t, s, **kw: {
            "ticker": t,
            "composite_score": 88.0,
            "tier": "HOT",
            "company_name": "Tata Consultancy Services",
            "current_price": 3520.0,
            "signal_price": 3480.0,
        },
    )

    # Run hot rescore - should not throw NameError
    run_hot_rescore(settings)


def test_prune_breakout_audit_log(tmp_path, monkeypatch):
    """Test pruning records older than N days from breakout_audit_log."""
    prices_dir = tmp_path / "prices"
    prices_dir.mkdir(parents=True, exist_ok=True)
    earnings_dir = tmp_path / "earnings"
    earnings_dir.mkdir(parents=True, exist_ok=True)
    settings = Settings(data_dirs={"prices": prices_dir, "earnings": earnings_dir})

    test_db = prices_dir / "test.sqlite3"
    db_conn_fn = lambda s=None: sqlite3.connect(str(test_db))
    monkeypatch.setattr("earnings_engine.data.db.get_db_connection", db_conn_fn)
    monkeypatch.setattr("earnings_engine.data.breakout_scanner.get_db_connection", db_conn_fn)
    monkeypatch.setattr("earnings_engine.data.migrations.get_db_connection", db_conn_fn)

    apply_migrations(settings)

    conn = sqlite3.connect(str(test_db))
    with conn:
        # Insert old row (>30 days ago)
        conn.execute("""
            INSERT INTO breakout_audit_log (ticker, company_name, event_type, from_tier, to_tier, strategy, counter, created_at, updated_at)
            VALUES ('OLD.NS', 'Old Stock', 'PROMOTED_HOT', 'WARM', 'HOT', 'Classic Technical', 1, '2025-01-01 10:00:00', '2025-01-01 10:00:00')
        """)
        # Insert recent row (<30 days ago)
        conn.execute("""
            INSERT INTO breakout_audit_log (ticker, company_name, event_type, from_tier, to_tier, strategy, counter, created_at, updated_at)
            VALUES ('NEW.NS', 'New Stock', 'PROMOTED_HOT', 'WARM', 'HOT', 'Classic Technical', 1, datetime('now'), datetime('now'))
        """)

    pruned = prune_breakout_audit_log(days=30, settings=settings)
    assert pruned == 1

    remaining = get_breakout_audit_log(settings=settings)
    assert len(remaining) == 1
    assert remaining[0]["ticker"] == "NEW.NS"

    count = get_breakout_audit_log_count(settings=settings)
    assert count == 1


def test_migration_033_consolidate_breakout_audit_log(tmp_path, monkeypatch):
    """Test Migration 33: prune >30d records, consolidate duplicate groups summing counter, and create index."""
    prices_dir = tmp_path / "prices"
    prices_dir.mkdir(parents=True, exist_ok=True)
    earnings_dir = tmp_path / "earnings"
    earnings_dir.mkdir(parents=True, exist_ok=True)
    settings = Settings(data_dirs={"prices": prices_dir, "earnings": earnings_dir})

    test_db = prices_dir / "test.sqlite3"
    db_conn_fn = lambda s=None: sqlite3.connect(str(test_db))
    monkeypatch.setattr("earnings_engine.data.db.get_db_connection", db_conn_fn)
    monkeypatch.setattr("earnings_engine.data.breakout_scanner.get_db_connection", db_conn_fn)
    monkeypatch.setattr("earnings_engine.data.migrations.get_db_connection", db_conn_fn)

    # First apply migrations up to 32 manually
    from earnings_engine.data.migrations import MIGRATIONS
    conn = sqlite3.connect(str(test_db))
    for m in MIGRATIONS:
        if m.version < 33:
            m.up(conn)
    conn.commit()

    with conn:
        # 1. Insert an old row (>30 days ago)
        conn.execute("""
            INSERT INTO breakout_audit_log (ticker, company_name, event_type, from_tier, to_tier, score_before, score_after, price, trigger_price, reason, strategy, counter, created_at, updated_at)
            VALUES ('STALE.NS', 'Stale Co', 'ADDED_WARM', 'COLD', 'WARM', 50.0, 70.0, 100.0, 105.0, 'Old', 'Classic Technical', 1, '2025-01-01 10:00:00', '2025-01-01 10:00:00')
        """)
        # 2. Insert duplicate group for RELIANCE.NS (3 rows)
        conn.execute("""
            INSERT INTO breakout_audit_log (ticker, company_name, event_type, from_tier, to_tier, score_before, score_after, price, trigger_price, reason, strategy, counter, created_at, updated_at)
            VALUES
            ('RELIANCE.NS', 'Reliance Industries', 'PROMOTED_HOT', 'WARM', 'HOT', 70.0, 85.0, 2900.0, 2950.0, 'First entry', 'Classic Technical', 1, '2026-08-25 10:00:00', '2026-08-25 10:00:00'),
            ('RELIANCE.NS', 'Reliance Industries', 'PROMOTED_HOT', 'WARM', 'HOT', 70.0, 88.0, 2920.0, 2950.0, 'Second entry', 'Classic Technical', 2, '2026-08-26 10:00:00', '2026-08-26 10:00:00'),
            ('RELIANCE.NS', 'Reliance Industries', 'PROMOTED_HOT', 'WARM', 'HOT', 70.0, 92.0, 2940.0, 2950.0, 'Latest entry', 'Classic Technical', 3, '2026-08-27 10:00:00', '2026-08-27 10:00:00')
        """)
        # 3. Insert a single distinct row for HDFCBANK.NS
        conn.execute("""
            INSERT INTO breakout_audit_log (ticker, company_name, event_type, from_tier, to_tier, score_before, score_after, price, trigger_price, reason, strategy, counter, created_at, updated_at)
            VALUES ('HDFCBANK.NS', 'HDFC Bank', 'ADDED_WARM', 'COLD', 'WARM', 60.0, 75.0, 1600.0, 1650.0, 'Single entry', 'Classic Technical', 1, '2026-08-26 10:00:00', '2026-08-26 10:00:00')
        """)

    # Apply Migration 33
    mig_33 = next(m for m in MIGRATIONS if m.version == 33)
    mig_33.up(conn)
    conn.commit()

    rows = conn.execute("""
        SELECT ticker, event_type, counter, created_at, updated_at, price, score_after
        FROM breakout_audit_log
        ORDER BY ticker
    """).fetchall()

    # STALE.NS must be pruned
    tickers = [r[0] for r in rows]
    assert "STALE.NS" not in tickers
    assert "HDFCBANK.NS" in tickers
    assert "RELIANCE.NS" in tickers
    assert len(rows) == 2

    # RELIANCE.NS row must have consolidated counter = 1 + 2 + 3 = 6
    rel = next(r for r in rows if r[0] == "RELIANCE.NS")
    assert rel[2] == 6  # counter
    assert rel[3] == "2026-08-25 10:00:00"  # earliest created_at preserved
    assert rel[4] == "2026-08-27 10:00:00"  # latest updated_at preserved
    assert rel[5] == 2940.0  # latest price from keep_id (MAX id)
    assert rel[6] == 92.0  # latest score_after from keep_id

    # Verify index exists
    idx_row = conn.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_breakout_audit_ticker_strat'").fetchone()
    assert idx_row is not None


    assert "TCS.NS::CLASSIC_TECHNICAL" in _pool["hot"]
    assert _pool["hot"]["TCS.NS::CLASSIC_TECHNICAL"]["result"]["composite_score"] == 88.0

