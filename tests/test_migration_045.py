from earnings_engine.config import Settings
from earnings_engine.data.db import get_db_connection
from earnings_engine.data.migrations import apply_migrations


def test_migration_045_applied():
    settings = Settings()
    # Reset migration cache and apply migrations
    from earnings_engine.data.migrations import reset_migration_cache
    reset_migration_cache()
    applied = apply_migrations(settings, force=True)
    conn = get_db_connection(settings)

    # Verify tables and indexes exist
    indices = [r[1] for r in conn.execute("SELECT type, name FROM sqlite_master WHERE type='index'").fetchall()]
    assert "idx_participant_oi_date_part" in indices
    assert "idx_inst_flows_date_desc" in indices
    assert "idx_price_history_ticker_date" in indices
    assert "idx_ticker_metrics_perf" in indices
    assert "idx_daily_quotes_ticker" in indices
